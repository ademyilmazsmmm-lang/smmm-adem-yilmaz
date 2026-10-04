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
from datetime import datetime

from . import defterbeyan, luca_hesap_plani
from lucabot.bekleme import sayfa_canli
from lucabot.firma_tablosu import luca_kaydi_bul
from lucabot.luca_ekran import acik_pencereleri_kapat
from lucabot.luca_gezinme import donem_ayarla, firma_sec
from lucabot.ortak import yaz

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


def kaydet(yol, bas, bit, sonuclar):
    yol.write_text(json.dumps({
        "donem": f"{bas:%d/%m/%Y}-{bit:%d/%m/%Y}",
        "alinma": datetime.now().isoformat(timespec="seconds"),
        "firmalar": list(sonuclar.values())}, ensure_ascii=False, indent=1), encoding="utf-8")


def oku(yol):
    """(donem metni, [sonuc]); dosya yoksa/bozuksa ValueError."""
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
        return veri["donem"], list(veri["firmalar"])
    except (OSError, KeyError, TypeError) as e:
        raise ValueError(f"{yol.name} okunamadi") from e


def _sonuc(firma, vkn, kaynak, defter, ozet=None, hata=""):
    s = {"firma": firma, "vkn": vkn, "kaynak": kaynak, "defter": defter, "hata": hata,
         "satis": None, "mal_alis": None, "gider": None, "kar": None, "ayrinti": {}}
    if ozet:
        s.update({k: ozet[k] for k in ("satis", "mal_alis", "gider", "kar", "ayrinti")})
    return s


def _ozet_yaz(ozet, log):
    yaz(f"    [OK] satış {ozet['satis']:,.2f} | mal alışı {ozet['mal_alis']:,.2f} | gider {ozet['gider']:,.2f}"
        f" | {'KÂR' if ozet['kar'] >= 0 else 'ZARAR'} {abs(ozet['kar']):,.2f}", log)


def defter_beyan_asamasi(page, ayarlar, firmalar, vkn_map, bas, bit, sonuclar, kaydet_fn, log):
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
            yaz("    Luca firma listesinde VKN bulunamadı; Luca'dan denenecek", log)
            luca_gidecek.append(firma)
            continue
        try:
            tur = defterbeyan.mukellef_sec(page, vkn, log)
            if tur is None:
                yaz("    Defter Beyan mükellef listesinde yok; Luca'dan denenecek", log)
                luca_gidecek.append(firma)
            elif not defterbeyan.isletme_mi(tur):
                yaz(f"    Defter türü {tur}; Luca'dan denenecek", log)
                luca_gidecek.append(firma)
            else:
                ozet = defterbeyan.hesap_ozeti_oku(page, bas, bit, log)
                sonuclar[firma] = _sonuc(firma, vkn, "Defter Beyan", "İşletme", ozet)
                _ozet_yaz(ozet, log)
            ardisik = 0
        except (LookupError, TimeoutError, RuntimeError) as e:
            ardisik += 1
            yaz(f"    HATA: {e}", log)
            sonuclar[firma] = _sonuc(firma, vkn, "Defter Beyan", "İşletme", hata=str(e))
        except Exception as e:  # playwright hatalari (zaman asimi, sayfa kapandi ...)
            if not sayfa_canli(page):
                raise
            ardisik += 1
            yaz(f"    HATA: {type(e).__name__}: {str(e)[:150]}", log)
            sonuclar[firma] = _sonuc(firma, vkn, "Defter Beyan", "İşletme", hata=f"{type(e).__name__}")
        finally:
            defterbeyan.mukelleften_cik(page)
        kaydet_fn()
        if ardisik >= ARDISIK_HATA_SINIRI:
            yaz(f"UYARI: Defter Beyan'da art arda {ardisik} hata; oturum kopmuş olabilir, kalan firmalar"
                " Luca'dan denenecek", log)
            luca_gidecek.extend(firmalar[i:])
            break
    return luca_gidecek


def luca_asamasi(page, firmalar, bas, bit, sonuclar, vkn_map, tani_klasoru, kaydet_fn, log):
    ardisik = 0
    for i, firma in enumerate(firmalar, 1):
        yaz(f"[{i}/{len(firmalar)}] {firma}  (Luca hesap planı)", log)
        try:
            acik_pencereleri_kapat(page)
            firma_sec(page, firma, log)
            if not donem_ayarla(page, firma, bas, bit, log):
                raise LookupError("firmanın bu döneme uygun çalışma dönemi yok")
            ozet = luca_hesap_plani.hesap_plani_oku(page, bas, bit, tani_klasoru, log)
            sonuclar[firma] = _sonuc(firma, vkn_map.get(firma, ""), "Luca", "Genel muhasebe", ozet)
            _ozet_yaz(ozet, log)
            ardisik = 0
        except LookupError as e:
            ardisik += 1
            yaz(f"    HATA: {e}", log)
            eski = sonuclar.get(firma)
            if eski is None or eski.get("kar") is None:  # Defter Beyan hatasi varsa ustune yazilir
                sonuclar[firma] = _sonuc(firma, vkn_map.get(firma, ""), "Luca", "?", hata=str(e))
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
