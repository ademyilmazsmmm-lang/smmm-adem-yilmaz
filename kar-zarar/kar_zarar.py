#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Donem ici kar/zarar tahmini (luca-bot'tan bagimsiz, kendi kendine yeten proje).

    python kar_zarar.py --baslangic 01/07/2026 --bitis 31/08/2026 [--firma ADEM] [--limit 5]

Isletme defteri tutan firmalar Defter Beyan'dan (Hesap Ozeti), genel muhasebe
firmalari Luca'dan (Hesap Plani Listesi) okunur; sonuc cikti/kar-zarar.json'a yazilir.
Luca girisi icin ayarlar.json (ayarlar.ornek.json'dan kopyalanir). Ayrinti: README.md.
"""

import argparse
import os
import signal
import sys
import traceback
from datetime import date
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

from karzarar import defterbeyan, hesaplama  # noqa: E402
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

CIKTI = Path(os.environ.get("KARZARAR_CIKTI") or KOK / "cikti")


def arguman_ayristirici():
    p = argparse.ArgumentParser(description="Donem ici kar/zarar tahmini (Defter Beyan + Luca)")
    p.add_argument("--baslangic", help="GG/AA/YYYY (ayarlar.json'daki degeri ezer)")
    p.add_argument("--bitis", help="GG/AA/YYYY (ayarlar.json'daki degeri ezer)")
    p.add_argument("--firma", action="append",
                   help="Sadece bu firma(lar); virgulle ayirarak birden fazla yazilabilir")
    p.add_argument("--limit", type=int, help="Ilk N firma ile sinirla")
    p.add_argument("--tarayici", choices=["chrome", "edge", "chromium"], help="Hangi tarayici kullanilsin")
    p.add_argument("--profil-yerel", action="store_true",
                   help="Tarayici profilini program klasoru yerine %%LOCALAPPDATA%% altinda tut")
    p.add_argument("--chrome-gunlugu", action="store_true", help="Chrome cokerse ayrintili gunluk tut")
    p.add_argument("--bitince-kapat", action="store_true",
                   help="Is bitince ENTER beklemeden tarayiciyi kapat; giriste kimseden cevap beklenmez")
    return p


def tarih_araligi(args, ayarlar, p):
    bas_metin = args.baslangic or ayarlar.get("baslangic_tarihi")
    bit_metin = args.bitis or ayarlar.get("bitis_tarihi")
    try:
        bas, bit = tarih_cozumle(bas_metin), tarih_cozumle(bit_metin)
    except (ValueError, AttributeError):
        p.error("Tarihler GG/AA/YYYY biciminde olmali, orn: --baslangic 01/07/2026 --bitis 31/08/2026")
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


def kar_zarar_cek(args, ayarlar, p):
    ayarlari_uygula(args, ayarlar)
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
            # VKN/TC ve kapanis tarihleri: Luca > Yonetici > Musteri Listesi (donem yili)
            try:
                musteriler = musteri_listesini_oku(page, bit.year, klasor / "tani", log)
            except LookupError as e:
                musteriler = []
                yaz(f"UYARI: Luca müşteri listesi okunamadı ({e}); firmalar yalnız Luca'dan denenecek", log)
            acik_pencereleri_kapat(page)
            firmalar = kapanmislari_ele(secim.firmalar, musteriler, bas, log)
            vkn_map = hesaplama.vkn_haritasi(firmalar, musteriler)
            yaz(f"{len(firmalar)} firma, {len(vkn_map)} tanesinin VKN'si biliniyor", log)
            kaydet_fn = lambda: hesaplama.kaydet(kayit_yolu, bas, bit, sonuclar)
            db_sayfa = ctx.new_page()
            luca_gidecek = hesaplama.defter_beyan_asamasi(
                db_sayfa, ayarlar, firmalar, vkn_map, bas, bit, sonuclar, kaydet_fn, log)
            try:
                db_sayfa.close()
            except Exception:
                pass
            page.bring_to_front()
            hesaplama.luca_asamasi(page, luca_gidecek, bas, bit, sonuclar, vkn_map,
                                   klasor / "tani", kaydet_fn, log)
        finally:
            tarayiciyi_kapat(ctx)
    tamam = sum(1 for s in sonuclar.values() if s["kar"] is not None)
    hesaplama.kaydet(kayit_yolu, bas, bit, sonuclar)
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
