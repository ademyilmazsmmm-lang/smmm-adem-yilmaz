# -*- coding: utf-8 -*-
"""Donem ici kar/zarar tahmini: isletme defterleri Defter Beyan'dan, genel muhasebe Luca'dan.

Her firma icin (sorgulanan donemde) satis/gelir, mal alisi, gider ve kar/zarar
bulunur; amac vergi cikabilecek firmalari erkenden gormektir, kesin sonuc degil.

  1. Firmanin VKN'si Luca musteri listesinden alinir (luca-musteri-listesi.json).
  2. Defter Beyan'da mukellef VKN ile secilir; ust cubukta "ISLETME" yaziyorsa Hesap
     Ozeti'nden okunur (defterbeyan.py).
  3. Defter Beyan'da bulunmayan ya da isletme olmayan firmalar Luca'da Hesap Plani
     Listesi'nden hesaplanir (luca_hesap_plani.py).

Sonuclar her firmadan sonra indirilenler/kar-zarar.json'a yazilir.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from . import defterbeyan, luca_hesap_plani, luca_mizan
from lucabot.bekleme import sayfa_canli
from lucabot.fatura_analiz import excelden_tablo, sutun_indeksi
from lucabot.firma_tablosu import luca_kaydi_bul
from lucabot.luca_ekran import acik_pencereleri_kapat
from lucabot.luca_gezinme import donem_ayarla, firma_sec
from lucabot.ortak import KOK, yaz

class DonemYok(LookupError):
    """Firmanin istenen doneme uygun calisma donemi yok: hata sayilmaz, firma atlanir."""


DOSYA = "kar-zarar.json"
ARDISIK_HATA_SINIRI = 5


def vkn_haritasi(firmalar, kayitlar):
    """{firma: vkn} (vergi no yoksa TC); eslesmeyen firma haritada yoktur."""
    harita = {}
    for f in firmalar:
        k = luca_kaydi_bul(f, kayitlar)
        if k and (k.get("vkn") or k.get("tc")):
            harita[f] = k.get("vkn") or k.get("tc")
    return harita


def _kimlik_no(deger):
    """Excel hucresinden VKN (10) / TC (11) haneli numara; Excel'in sondaki '.0'i ve bastaki sifir kaybi duzeltilir."""
    m = re.sub(r"\D", "", re.sub(r"\.0+$", "", str(deger or "").strip()))
    if len(m) in (10, 11):
        return m
    return m.zfill(10) if 8 <= len(m) < 10 else ""


def excel_kayitlari(yol, log=None):
    """VKN iceren Excel'den [{ad, unvan, vkn, tc}]; ad/VKN sutunu yoksa [].

    Aranan basliklar: 'Kisa Adi', 'Uzun Adi'/'Unvan', 'Vergi No'/'VKN', 'TC Kimlik'. Luca'nin
    Musteri Listesi Excel'i ya da firma_listesi dosyasi bu sutunlari tasiyorsa dogrudan kullanilir.
    """
    yol = Path(yol)
    if not yol.is_absolute():
        yol = KOK / yol
    if not yol.exists():
        yaz(f"UYARI: VKN listesi bulunamadı: {yol}", log)
        return []
    basliklar, satirlar = excelden_tablo(yol, log, sadece_ilk=True, satir_en_az=1)
    ad_i, unvan_i = sutun_indeksi(basliklar, "KISA AD"), sutun_indeksi(basliklar, "UZUN AD", "UNVAN")
    vkn_i, tc_i = sutun_indeksi(basliklar, "VERGI NO", "VKN"), sutun_indeksi(basliklar, "TC KIMLIK", "TCKN")
    if (ad_i is None and unvan_i is None) or (vkn_i is None and tc_i is None):
        return []
    al = lambda satir, i: satir[i].strip() if i is not None and i < len(satir) else ""
    return [{"ad": al(s, ad_i), "unvan": al(s, unvan_i), "vkn": _kimlik_no(al(s, vkn_i)), "tc": _kimlik_no(al(s, tc_i))}
            for s in satirlar]


def vkn_tamamla(harita, firmalar, ayarlar, log=None):
    """Luca'dan VKN'si bulunamayan firmalari ayarlar'daki Excel'lerden (vkn_listesi, firma_listesi) tamamlar."""
    eksik = [f for f in firmalar if f not in harita]
    for anahtar in ("vkn_listesi", "firma_listesi"):
        if not eksik or not ayarlar.get(anahtar):
            continue
        kayitlar = excel_kayitlari(ayarlar[anahtar], log)
        bulunan = vkn_haritasi(eksik, kayitlar)
        if bulunan:
            yaz(f"{ayarlar[anahtar]} dosyasından {len(bulunan)} firmanın VKN'si tamamlandı", log)
            harita.update(bulunan)
            eksik = [f for f in eksik if f not in harita]
    return harita


def birlestir(onceki, sonuclar, donem):
    """Onceki sorgularin sonuclari ({firma, donem} anahtarli liste) ile bu sorgununkini birlestirir.

    Ayni firma + ayni donem yeniden sorgulaninca yeni sonuc eskisinin yerini alir; baska firma/donemler
    silinmez. Yeni sorguda HATA olursa eski basarili sonuc korunur (hata 'son_hata' alanina yazilir)."""
    cikti = {(s["firma"], s.get("donem") or ""): s for s in onceki}
    for firma, yeni in sonuclar.items():
        yeni = dict(yeni, donem=donem)
        anahtar = (yeni["firma"], donem)
        eski = cikti.get(anahtar)
        if yeni.get("kar") is None and eski is not None and eski.get("kar") is not None:
            eski = dict(eski)
            eski["son_hata"] = yeni.get("hata") or "hata"
            cikti[anahtar] = eski
        else:
            cikti[anahtar] = yeni
    return list(cikti.values())


def kaydet(yol, bas, bit, sonuclar, birlestir_onceki=True):
    """kar-zarar.json'a yazar. Varsayilan: dosyadaki onceki sorgularin sonuclari korunur, bu sorgununkiler eklenir/guncellenir."""
    donem = f"{bas:%d/%m/%Y}-{bit:%d/%m/%Y}"
    onceki = []
    if birlestir_onceki:
        try:
            eski_donem, eski = oku(yol)
            onceki = [dict(s, donem=s.get("donem") or eski_donem) for s in eski]
        except ValueError:
            onceki = []
    yol.write_text(json.dumps({
        "donem": donem,
        "alinma": datetime.now().isoformat(timespec="seconds"),
        "firmalar": birlestir(onceki, sonuclar, donem)}, ensure_ascii=False, indent=1), encoding="utf-8")


def oku(yol):
    """(donem metni, [sonuc]); dosya yoksa/bozuksa ValueError."""
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
        return veri["donem"], list(veri["firmalar"])
    except (OSError, KeyError, TypeError) as e:
        raise ValueError(f"{yol.name} okunamadi") from e


def _sonuc(firma, vkn, kaynak, defter, ozet=None, hata=""):
    s = {"firma": firma, "vkn": vkn, "kaynak": kaynak, "defter": defter, "hata": hata,
         "satis": None, "mal_alis": None, "gider": None, "toplam_gider": None, "kar": None, "ayrinti": {}}
    if ozet:
        s.update({k: ozet[k] for k in ("satis", "mal_alis", "gider", "kar", "ayrinti")})
        s["toplam_gider"] = ozet.get("toplam_gider")
    return s


def _ozet_yaz(ozet, log):
    yaz(f"    [OK] satış {ozet['satis']:,.2f} | mal alışı {ozet['mal_alis']:,.2f} | gider {ozet['gider']:,.2f}"
        f" | {'KÂR' if ozet['kar'] >= 0 else 'ZARAR'} {abs(ozet['kar']):,.2f}", log)


def defter_beyan_asamasi(page, ayarlar, firmalar, vkn_map, bas, bit, sonuclar, kaydet_fn, log, tani_klasoru=None, tani_hep=False):
    """Isletme firmalarini Defter Beyan'dan okur; Luca'ya birakilacak firmalari dondurur."""
    luca_gidecek = []
    girdi = defterbeyan.giris_yap(page, ayarlar.get("defterbeyan_kullanici", ""),
                                  ayarlar.get("defterbeyan_sifre", ""), log=log)
    if not girdi:
        yaz("UYARI: Defter Beyan girişi yapılmadı; işletme firmaları atlanıp tümü Luca'dan denenecek", log)
        return list(firmalar)
    ardisik = 0
    for i, firma in enumerate(firmalar, 1):
        yaz(f"[{i}/{len(firmalar)}] {firma}  (Defter Beyan)", log)
        vkn = vkn_map.get(firma)
        if not vkn:
            yaz("    İşletme defteri müşteri listesinde (VKN) yok; Luca'dan denenecek", log)
            luca_gidecek.append(firma)
            continue
        try:
            tur = defterbeyan.mukellef_sec(page, vkn, log, tani_klasoru, tani_hep)
            if tur is None:
                yaz("    Defter Beyan mükellef listesinde yok; Luca'dan denenecek", log)
                luca_gidecek.append(firma)
            elif defterbeyan.bilanco_mu(tur):
                yaz(f"    Defter türü {tur}; Luca'dan denenecek", log)
                luca_gidecek.append(firma)
            elif not (defterbeyan.isletme_mi(tur) or defterbeyan.smk_mi(tur)):  # diger turler: tahmin yapilmaz
                yaz(f"    Defter türü {tur}; kâr/zarar tahmini yapılmaz, atlandı", log)
            else:
                ozet = defterbeyan.hesap_ozeti_oku(page, bas, bit, log, tani_klasoru, tani_hep)
                sonuclar[firma] = _sonuc(firma, vkn, "Defter Beyan",
                                         "Serbest meslek" if defterbeyan.smk_mi(tur) else "İşletme", ozet)
                _ozet_yaz(ozet, log)
            ardisik = 0
        except defterbeyan.MukellefAtlandi as e:  # bilinen sorun: bekleme/oturum hatasi sayilmaz, siradakine gec
            yaz(f"    ATLANDI: {e}", log)
            sonuclar[firma] = _sonuc(firma, vkn, "Defter Beyan", "", hata=f"ATLANDI: {e}")
        except (LookupError, TimeoutError, RuntimeError) as e:
            ardisik += 1
            yaz(f"    HATA: {e}", log)
            sonuclar[firma] = _sonuc(firma, vkn, "Defter Beyan", "", hata=str(e))
        except Exception as e:  # playwright hatalari (zaman asimi, sayfa kapandi ...)
            if not sayfa_canli(page):
                raise
            ardisik += 1
            yaz(f"    HATA: {type(e).__name__}: {str(e)[:150]}", log)
            sonuclar[firma] = _sonuc(firma, vkn, "Defter Beyan", "", hata=f"{type(e).__name__}")
        finally:
            defterbeyan.mukelleften_cik(page)
        kaydet_fn()
        if ardisik >= ARDISIK_HATA_SINIRI:
            yaz(f"UYARI: Defter Beyan'da art arda {ardisik} hata; oturum kopmuş olabilir, kalan firmalar"
                " Luca'dan denenecek", log)
            luca_gidecek.extend(firmalar[i:])
            break
    return luca_gidecek


def _luca_ozeti(page, firma, bas, bit, kaynak, tani_klasoru, log, tani_hep, yedek_hesap_plani=False):
    """(ozet, kaynak adi). kaynak 'mizan': Mizan Excel'i indirilir; alinamazsa firma HATA olur
    (yedek_hesap_plani=True ise Hesap Plani'na donulur; varsayilan kapali: Mizan tercih edilen yontemdir)."""
    if kaynak == "mizan":
        try:
            return (luca_mizan.mizan_oku(page, firma, bas, bit, tani_klasoru.parent / "mizan", tani_klasoru, log, tani_hep),
                    "Luca (Mizan)")
        except Exception as e:
            if not yedek_hesap_plani or not sayfa_canli(page):
                raise
            yaz(f"    Mizan alınamadı ({type(e).__name__}: {str(e)[:120]}); Hesap Planı'ndan okunacak", log)
    return luca_hesap_plani.hesap_plani_oku(page, bas, bit, tani_klasoru, log, tani_hep), "Luca (Hesap Planı)"


def luca_asamasi(page, firmalar, bas, bit, sonuclar, vkn_map, tani_klasoru, kaydet_fn, log, tani_hep=False,
                 kaynak="hesap-plani", yedek_hesap_plani=False):
    """kaynak: 'mizan' (Mizan Excel'i, hata olursa Hesap Plani) ya da 'hesap-plani'."""
    ardisik = 0
    for i, firma in enumerate(firmalar, 1):
        if page.is_closed():  # Luca ana penceresi kapandi (orn. rapor penceresi): kalan firmalar yapilamaz, sonuclar korunur
            yaz("UYARI: Luca ana penceresi kapandı; kalan firmalar atlandı (o ana kadarki sonuçlar kaydedildi)", log)
            break
        yaz(f"[{i}/{len(firmalar)}] {firma}  (Luca {'mizan' if kaynak == 'mizan' else 'hesap planı'})", log)
        try:
            acik_pencereleri_kapat(page)
            firma_sec(page, firma, log)
            if not donem_ayarla(page, firma, bas, bit, log):
                raise DonemYok("firmanın bu döneme uygun çalışma dönemi yok")
            ozet, kaynak_adi = _luca_ozeti(page, firma, bas, bit, kaynak, tani_klasoru, log, tani_hep, yedek_hesap_plani)
            sonuclar[firma] = _sonuc(firma, vkn_map.get(firma, ""), kaynak_adi, "Genel muhasebe", ozet)
            _ozet_yaz(ozet, log)
            ardisik = 0
        except LookupError as e:
            atlandi = isinstance(e, DonemYok)
            if not atlandi:  # donem yok = firma bu doneme ait degil, sistem hatasi degil
                ardisik += 1
            yaz(f"    {'ATLANDI' if atlandi else 'HATA'}: {e}", log)
            eski = sonuclar.get(firma)
            if eski is None or eski.get("kar") is None:  # Defter Beyan hatasi varsa ustune yazilir
                sonuclar[firma] = _sonuc(firma, vkn_map.get(firma, ""), "Luca", "?",
                                         hata=f"ATLANDI: {e}" if atlandi else str(e))
        except Exception as e:
            if not sayfa_canli(page):
                raise
            ardisik += 1
            yaz(f"    HATA: {type(e).__name__}: {str(e)[:150]}", log)
            sonuclar[firma] = _sonuc(firma, vkn_map.get(firma, ""), "Luca", "?", hata=type(e).__name__)
        kaydet_fn()
        if ardisik >= ARDISIK_HATA_SINIRI:
            yaz(f"UYARI: Luca'da art arda {ardisik} hata; kalan firmalar atlandı", log)
            break
