#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Donem ici kar/zarar tahmini (luca-bot'tan bagimsiz, kendi kendine yeten proje).

    python kar_zarar.py --baslangic 01/07/2026 --bitis 31/08/2026 [--firma ADEM] [--limit 5]

Isletme defteri tutan firmalar Defter Beyan'dan (Hesap Ozeti), genel muhasebe
firmalari Luca'dan (Hesap Plani Listesi) okunur; sonuc cikti/kar-zarar.json'a yazilir.
Luca girisi icin ayarlar.json (ayarlar.ornek.json'dan kopyalanir). Ayrinti: README.md.
"""

import argparse
import json
import os
import re
import signal
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

from karzarar import defterbeyan, hesaplama, rapor  # noqa: E402
from lucabot import konsol  # noqa: E402
from lucabot.firma_listesi import firmalari_suz  # noqa: E402
from lucabot.firma_tablosu import luca_kaydi_bul  # noqa: E402
from lucabot.giris import luca_oturumu_ac  # noqa: E402
from lucabot.luca_ekran import acik_pencereleri_kapat  # noqa: E402
from lucabot.luca_gezinme import firma_secici_bekle  # noqa: E402
from lucabot.musteri_listesi import listeyi_oku as musteri_listesini_oku  # noqa: E402
from lucabot.ortak import (AYAR, DURDUR_DOSYASI, ayarlari_oku, gunluge_yaz,  # noqa: E402
                           tarih_cozumle, yaz)
from lucabot.tarayici import profil_klasoru, tarayici_ac, tarayiciyi_kapat  # noqa: E402

# Luca Musteri Listesi filtresi: yalniz isletme defteri firmalari (bilanco firmalari Defter Beyan'a sorulmaz)
MUSTERI_SINIFI = ["İşletme Defteri", "Serbest Meslek Defteri"]  # Defter Beyan Hesap Ozeti okunacak siniflar
# Luca hesap plani yalniz bu siniftaki (1. sinif / bilanco) firmalar icin sorgulanir; "" ise suzulmez
LUCA_SINIFI = "1.Sınıf"
# Luca firmalarinda tutarlar: "mizan" (Mizan Excel'i indirilir; alinamazsa Hesap Plani) ya da "hesap-plani"
LUCA_KAYNAGI = "mizan"
CIKTI = Path(os.environ.get("KARZARAR_CIKTI") or KOK / "cikti")


def arguman_ayristirici():
    p = argparse.ArgumentParser(description="Donem ici kar/zarar tahmini (Defter Beyan + Luca)")
    p.add_argument("--tarih", help="Tarih araligi tek seferde: 01/07/2026-31/08/2026 (--baslangic/--bitis'i ve"
                                   " ayarlar.json'daki degerleri ezer)")
    p.add_argument("--baslangic", help="GG/AA/YYYY (ayarlar.json'daki degeri ezer)")
    p.add_argument("--bitis", help="GG/AA/YYYY (ayarlar.json'daki degeri ezer)")
    p.add_argument("--firma", action="append",
                   help="Sadece bu firma(lar); virgulle ayirarak birden fazla yazilabilir")
    p.add_argument("--limit", type=int, help="Ilk N firma ile sinirla")
    p.add_argument("--listeyi-yenile", action="store_true",
                   help="Luca Musteri Listesi'ni yeniden oku (varsayilan: ayni yilin kayitli listesi kullanilir, Luca'dan cekilmez)")
    p.add_argument("--sadece-luca", action="store_true",
                   help="Tek firma denemesi: Musteri Listesi ve Defter Beyan'i atla, --firma ile secilen firmayi yalniz"
                        " Luca hesap planindan oku (her adimdan sonra tani dosyasi kaydedilir)")
    p.add_argument("--luca-kaynagi", choices=["mizan", "hesap-plani"],
                   help="Luca firmalarinda tutarlar nereden alinsin (ayarlar.json'daki luca_kaynagi'ni ezer; varsayilan mizan)")
    p.add_argument("--sadece-defterbeyan", action="store_true",
                   help="Tek firma denemesi: --firma ile secilen firmayi yalniz Defter Beyan'dan oku (VKN Luca Musteri"
                        " Listesi'nden alinir, Luca hesap plani atlanir; her adimdan sonra tani dosyasi kaydedilir)")
    p.add_argument("--tarayici", choices=["chrome", "edge", "chromium"], help="Hangi tarayici kullanilsin")
    p.add_argument("--profil-yerel", action="store_true",
                   help="Tarayici profilini program klasoru yerine %%LOCALAPPDATA%% altinda tut")
    p.add_argument("--chrome-gunlugu", action="store_true", help="Chrome cokerse ayrintili gunluk tut")
    p.add_argument("--bitince-kapat", action="store_true",
                   help="Is bitince ENTER beklemeden tarayiciyi kapat; giriste kimseden cevap beklenmez")
    return p


TARIH_DESENI = re.compile(r"\d{1,2}[./-]\d{1,2}[./-]\d{4}")


def aralik_coz(metin):
    """'01/07/2026-31/08/2026' (ya da '01.07.2026 - 31.08.2026', '01/07/2026 31/08/2026') -> (bas, bit); olmazsa ValueError."""
    tarihler = TARIH_DESENI.findall(metin or "")
    if len(tarihler) != 2:
        raise ValueError("iki tarih bulunamadi")
    return tuple(tarih_cozumle(t.replace(".", "/").replace("-", "/")) for t in tarihler)


def tarih_sor(sor=input, yaz_fn=print):
    """Tarih araligini zorunlu olarak sorar (gecerli bir aralik girilene kadar); (bas, bit) dondurur."""
    while True:
        metin = sor("Tarih araligi (ornek 01/07/2026-31/08/2026): ")
        try:
            bas, bit = aralik_coz(metin)
            if bit < bas:
                raise ValueError("bitis baslangictan once")
            return bas, bit
        except ValueError:
            yaz_fn("Gecerli bir tarih araligi girin, orn: 01/07/2026-31/08/2026")


def tarih_araligi(args, ayarlar, p):
    # Tarih hic verilmediyse ve konsoldan calisiliyorsa (gece/otomatik calismada degil) ayarlar.json'a sessizce dusulmez: sorulur
    if not (args.tarih or args.baslangic or args.bitis) and not args.bitince_kapat and sys.stdin and sys.stdin.isatty():
        return tarih_sor()
    try:
        if args.tarih:
            bas, bit = aralik_coz(args.tarih)
        else:
            bas_metin = args.baslangic or ayarlar.get("baslangic_tarihi")
            bit_metin = args.bitis or ayarlar.get("bitis_tarihi")
            bas, bit = tarih_cozumle(bas_metin), tarih_cozumle(bit_metin)
    except (ValueError, AttributeError):
        p.error("Tarihler GG/AA/YYYY biciminde olmali, orn: --tarih 01/07/2026-31/08/2026"
                " (ya da --baslangic 01/07/2026 --bitis 31/08/2026)")
    if bit < bas:
        p.error("Bitis tarihi baslangictan once olamaz")
    return bas, bit


def ayarlari_uygula(args, ayarlar):
    """ayarlar.json + komut satirini tarayici/giris modullerinin okudugu AYAR'a isler."""
    AYAR["chrome_gunlugu"] = bool(args.chrome_gunlugu)
    AYAR["profil_yerel"] = bool(args.profil_yerel) or bool(ayarlar.get("profil_yerel", False))
    AYAR["tarayici"] = args.tarayici or ayarlar.get("tarayici") or None
    AYAR["tarayici_yolu"] = ayarlar.get("tarayici_yolu") or None
    AYAR["giris_adresi"] = ayarlar.get("giris_adresi") or None
    AYAR["tarayici_sandbox"] = bool(ayarlar.get("tarayici_sandbox", True))
    AYAR["donem_degistir"] = bool(ayarlar.get("donem_degistir", True))
    if ayarlar.get("defterbeyan_adresi"):  # yalnizca test icin (sahte Defter Beyan)
        defterbeyan.ADRES = str(ayarlar["defterbeyan_adresi"]).rstrip("/")
    if AYAR["chrome_gunlugu"]:
        os.environ["DEBUG"] = "pw:browser"


def kapanmislari_ele(firmalar, kayitlar, bas, log):
    """Luca'da kapanis tarihi donemden once olan firmalar atlanir."""
    kalan, atlanan = [], []
    for f in firmalar:
        k = luca_kaydi_bul(f, kayitlar)
        try:
            kapanis = tarih_cozumle(k["kapanis"]) if k and k.get("kapanis") else None
        except ValueError:
            kapanis = None
        (atlanan if kapanis is not None and kapanis < bas else kalan).append(f)
    if atlanan:
        yaz(f"Dönemden önce kapanan {len(atlanan)} firma atlandı: {', '.join(atlanan[:10])}", log)
    return kalan


def _kaydet(kayit_yolu, bas, bit, sonuclar):
    """kar-zarar.json + kar-zarar.xlsx (Excel acik/yazilamazsa json yine de yazilir); Excel yolunu dondurur."""
    hesaplama.kaydet(kayit_yolu, bas, bit, sonuclar)
    try:
        return rapor.excel_yaz(kayit_yolu.with_suffix(".xlsx"), bas, bit, sonuclar)
    except Exception as e:
        return f"yazılamadı ({type(e).__name__})"


ONBELLEK = "musteri-listeleri.json"  # cikti/ altinda: {"yil", "alinma", "siniflar": {sinif: [kayit]}}


def onbellek_oku(yol, yil):
    """Ayni yilin kayitli Musteri Listesi'ni {sinif: [kayit]} dondurur; yok/eski/bozuksa {}."""
    try:
        veri = json.loads(Path(yol).read_text(encoding="utf-8"))
        if veri.get("yil") == yil and isinstance(veri.get("siniflar"), dict):
            return veri["siniflar"]
    except (OSError, ValueError, AttributeError):
        pass
    return {}


def onbellek_yaz(yol, yil, siniflar):
    gecici = Path(yol).with_suffix(".json.tmp")
    gecici.write_text(json.dumps({"yil": yil, "alinma": datetime.now().isoformat(timespec="seconds"),
                                  "siniflar": siniflar}, ensure_ascii=False, indent=1), encoding="utf-8")
    gecici.replace(yol)


def _musteri_listesi(page, yil, tani, sinif, log, onbellek=None, onbellek_yolu=None):
    """Luca Musteri Listesi (Yil + Sinif suzmeli); okunamazsa uyari yazip None.

    `onbellek` ({sinif: [kayit]}) verilirse ve sinif orada varsa Luca'ya gidilmez; Luca'dan okunan liste
    onbellege yazilir (sonraki sorgularda tekrar cekilmez)."""
    if onbellek is not None and sinif in onbellek:
        yaz(f"Müşteri listesi ({sinif or 'sınıfsız'}): kayıtlı liste kullanıldı, {len(onbellek[sinif])} firma"
            " (Luca'dan çekilmedi)", log)
        return onbellek[sinif]
    try:
        kayitlar = musteri_listesini_oku(page, yil, tani, log, sinif=sinif)
    except LookupError as e:
        yaz(f"UYARI: Luca müşteri listesi ({sinif or 'sınıfsız'}) okunamadı ({e})", log)
        return None
    if onbellek is not None and onbellek_yolu is not None:
        onbellek[sinif] = kayitlar
        try:
            onbellek_yaz(onbellek_yolu, yil, onbellek)
        except OSError:
            pass
    return kayitlar


def _luca_firmalari(adaylar, birinci, sinif, yil, log):
    """Luca hesap planina gidecek firmalar: yalniz sinif listesinde (orn. 1.Sinif, o yilin donemi) olanlar."""
    if not sinif:
        return list(adaylar)
    if birinci is None:
        yaz(f"UYARI: {sinif} firma listesi alınamadı; Luca'ya giden tüm firmalar denenecek", log)
        return list(adaylar)
    uygun = [f for f in adaylar if luca_kaydi_bul(f, birinci)]
    atlanan = [f for f in adaylar if f not in uygun]
    yaz(f"Luca hesap planı: {len(uygun)} firma ({sinif}, {yil} dönemi); {len(atlanan)} firma bu listede olmadığı için"
        f" atlandı{': ' + ', '.join(atlanan[:10]) if atlanan else ''}", log)
    return uygun


def kar_zarar_cek(args, ayarlar, p):
    ayarlari_uygula(args, ayarlar)
    if (args.sadece_luca or args.sadece_defterbeyan) and not (args.firma or args.limit):
        p.error("--sadece-luca / --sadece-defterbeyan tek firma denemesi icindir: --firma \"FIRMA ADI\""
                " (veya --limit 1) ile birlikte kullanin")
    if args.sadece_luca and args.sadece_defterbeyan:
        p.error("--sadece-luca ile --sadece-defterbeyan birlikte kullanilamaz")
    bas, bit = tarih_araligi(args, ayarlar, p)
    gece_modu = bool(args.bitince_kapat)
    klasor = CIKTI / date.today().isoformat()
    klasor.mkdir(parents=True, exist_ok=True)
    log = klasor / "calisma.log"
    kayit_yolu = CIKTI / hesaplama.DOSYA
    konsol.bolum(f"KAR / ZARAR TAHMINI  {bas:%d/%m/%Y} - {bit:%d/%m/%Y}", log)
    profil = profil_klasoru(log)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = tarayici_ac(pw, profil, log, AYAR["chrome_gunlugu"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page = luca_oturumu_ac(ctx, page, ayarlar, gece_modu, klasor / "tani", log)
        if page is None:
            tarayiciyi_kapat(ctx)
            return 1
        sonuclar = {}
        try:
            _, _, luca_firmalari = firma_secici_bekle(page)
            secim = firmalari_suz(luca_firmalari, ayarlar, args.firma, args.limit, bas, log)
            if not secim.firmalar:
                yaz(f"Islenecek firma yok: {secim.bos_sebep}.", log)
                return 1
            if args.sadece_luca:
                # tek firma denemesi: Musteri Listesi / Defter Beyan atlanir, firma dogrudan Luca hesap planindan okunur
                yaz("--sadece-luca: Müşteri Listesi ve Defter Beyan atlanıyor; her adımdan sonra tanı dosyası kaydedilir", log)
                firmalar, vkn_map, vkn_hepsi = list(secim.firmalar), {}, {}
                kaydet_fn = lambda: _kaydet(kayit_yolu, bas, bit, sonuclar)
                luca_gidecek = list(firmalar)
            else:
                # VKN/TC ve kapanis tarihleri: Luca > Yonetici > Musteri Listesi (donem yili)
                # 1) Sinif=Isletme Defteri: Defter Beyan'a sorulacak firmalar; 2) Sinif=1.Sinif: Luca hesap plani firmalari
                musteriler = []
                onbellek_yolu = CIKTI / ONBELLEK
                onbellek = {} if args.listeyi_yenile else onbellek_oku(onbellek_yolu, bit.year)
                siniflar = ayarlar.get("musteri_sinifi", MUSTERI_SINIFI)
                for sira, sinif in enumerate([siniflar] if isinstance(siniflar, str) else siniflar):
                    musteriler += _musteri_listesi(page, bit.year, klasor / (f"tani-{sira}" if sira else "tani"),
                                                   sinif, log, onbellek, onbellek_yolu) or []
                luca_sinifi = "" if args.sadece_defterbeyan else ayarlar.get("luca_sinifi", LUCA_SINIFI)
                birinci = (_musteri_listesi(page, bit.year, klasor / "tani-1sinif", luca_sinifi, log,
                                            onbellek, onbellek_yolu) if luca_sinifi else None)
                acik_pencereleri_kapat(page)
                kayitlar = musteriler + (birinci or [])
                firmalar = kapanmislari_ele(secim.firmalar, kayitlar, bas, log)
                vkn_map = hesaplama.vkn_haritasi(firmalar, musteriler)
                hesaplama.vkn_tamamla(vkn_map, firmalar, ayarlar, log)
                vkn_hepsi = {**hesaplama.vkn_haritasi(firmalar, kayitlar), **vkn_map}
                yaz(f"{len(firmalar)} firma, {len(vkn_map)} tanesinin VKN'si biliniyor", log)
                kaydet_fn = lambda: _kaydet(kayit_yolu, bas, bit, sonuclar)
                db_sayfa = ctx.new_page()
                luca_gidecek = hesaplama.defter_beyan_asamasi(
                    db_sayfa, ayarlar, firmalar, vkn_map, bas, bit, sonuclar, kaydet_fn, log, klasor / "tani",
                    tani_hep=bool(args.sadece_defterbeyan))
                try:
                    db_sayfa.close()
                except Exception:
                    pass
                if args.sadece_defterbeyan:
                    luca_gidecek = []  # tek firma denemesi: Luca hesap plani atlanir
                else:
                    luca_gidecek = _luca_firmalari(luca_gidecek, birinci, luca_sinifi, bit.year, log)
            page.bring_to_front()
            hesaplama.luca_asamasi(page, luca_gidecek, bas, bit, sonuclar, vkn_hepsi,
                                   klasor / "tani", kaydet_fn, log, tani_hep=bool(args.sadece_luca),
                                   kaynak=args.luca_kaynagi or ayarlar.get("luca_kaynagi", LUCA_KAYNAGI))
        finally:
            tarayiciyi_kapat(ctx)
    tamam = sum(1 for s in sonuclar.values() if s["kar"] is not None)
    excel = _kaydet(kayit_yolu, bas, bit, sonuclar)
    yaz(f"EXCEL RAPOR: {excel}", log)
    yaz(f"[OK] {tamam} firmanın kâr/zarar tahmini hazır, {len(sonuclar) - tamam} firmada hata: {kayit_yolu}", log)
    return 0 if tamam else 1


def _durdurma_sinyali(*_):
    raise KeyboardInterrupt


def main():
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _durdurma_sinyali)
    p = arguman_ayristirici()
    args = p.parse_args()
    ayarlar = ayarlari_oku()
    try:
        DURDUR_DOSYASI.unlink()
    except OSError:
        pass
    try:
        return kar_zarar_cek(args, ayarlar, p)
    except KeyboardInterrupt:
        print("\nKullanici tarafindan durduruldu (o ana kadarki sonuclar kaydedildi).")
        return 130
    except SystemExit:
        raise
    except Exception as e:
        CIKTI.mkdir(parents=True, exist_ok=True)
        gunluge_yaz("BEKLENMEYEN HATA\n" + traceback.format_exc(), CIKTI / "hata.log")
        print(f"\nBEKLENMEYEN HATA: {type(e).__name__}: {e}\nAyrinti: {CIKTI / 'hata.log'}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
