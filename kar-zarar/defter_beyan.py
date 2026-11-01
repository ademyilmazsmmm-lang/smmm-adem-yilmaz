#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2. sinif (isletme defteri / serbest meslek) firmalarin Luca gelir-gider kayitlarini Defter Beyan'a gonderme kontrolu.

    python defter_beyan.py --tarih 01/10/2026-31/10/2026                      # yalniz KONTROL (hicbir sey gonderilmez)
    python defter_beyan.py --tarih 01/10/2026-31/10/2026 --firma-tam "OSMAN ALEM" --islem gonder   # secili firmalara GONDER

Her firma icin Luca'nin "Defter Beyan Sistemi" sayfasinda Gelirler ve Giderler sekmesinde donemin Gonderilmemis ve
Gonderilmis kayit sayisi okunur. --islem gonder ile gonderilmemisler Defter Beyan'a gonderilir ve kalan yeniden sayilir.
Sonuc cikti/defter-beyan.json'a yazilir (onceki firmalar korunur). Luca girisi ayarlar.json'dandir (kar_zarar.py ile ortak).
Gonderme GERI ALINAMAYABILIR (Luca'da 'Defter Beyan Sisteminden Sil' vardir); once --islem kontrol ile bakin.
"""

import argparse
import json
import signal
import sys
import traceback
from datetime import date
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

import kar_zarar as kz  # noqa: E402  (ortak: giris, musteri listesi onbellegi, ayarlar)
from karzarar import db_sonuc, defterbeyan_luca  # noqa: E402
from lucabot import konsol  # noqa: E402
from lucabot.firma_listesi import firmalari_suz  # noqa: E402
from lucabot.firma_tablosu import luca_kaydi_bul  # noqa: E402
from lucabot.giris import luca_oturumu_ac  # noqa: E402
from lucabot.luca_ekran import acik_pencereleri_kapat  # noqa: E402
from lucabot.luca_gezinme import donem_ayarla, firma_sec, firma_secici_bekle  # noqa: E402
from lucabot.ortak import AYAR, DURDUR_DOSYASI, ayarlari_oku, gunluge_yaz, yaz  # noqa: E402
from lucabot.tarayici import profil_klasoru, tarayici_ac, tarayiciyi_kapat  # noqa: E402

CIKTI = kz.CIKTI
# 2. sinif: bu siniflardaki firmalar (Luca Musteri Listesi'nde "Sinif")
IKINCI_SINIF = ["İşletme Defteri", "Serbest Meslek Defteri"]
ARDISIK_HATA_SINIRI = 5


def arguman_ayristirici():
    p = argparse.ArgumentParser(description="2. sinif firmalar: Luca > Defter Beyan gonderme kontrolu")
    p.add_argument("--tarih", help="Evrak tarihi araligi: 01/10/2026-31/10/2026")
    p.add_argument("--baslangic", help="GG/AA/YYYY")
    p.add_argument("--bitis", help="GG/AA/YYYY")
    p.add_argument("--islem", choices=["kontrol", "gonder"], default="kontrol",
                   help="kontrol: yalniz say (varsayilan, hicbir sey gonderilmez); gonder: gonderilmemisleri Defter Beyan'a gonder")
    p.add_argument("--firma", action="append", help="Sadece bu firma(lar) (parca eslesir, virgulle ayrilir)")
    p.add_argument("--firma-tam", action="append", dest="firma_tam",
                   help="Sadece bu firma(lar), Luca'daki adla TAM eslesen; birden fazla kez verilebilir")
    p.add_argument("--limit", type=int, help="Ilk N firma ile sinirla")
    p.add_argument("--listeyi-yenile", action="store_true", help="Luca Musteri Listesi'ni yeniden oku")
    p.add_argument("--tani", action="store_true", help="Her firma icin ekran goruntusu + sayfa kaydi (tani/) sakla")
    p.add_argument("--tum-firmalar", action="store_true",
                   help="2. sinif suzgecini kapat: Luca'daki tum firmalar (yalniz deneme icin)")
    p.add_argument("--tarayici", choices=["chrome", "edge", "chromium"])
    p.add_argument("--profil-yerel", action="store_true")
    p.add_argument("--chrome-gunlugu", action="store_true")
    p.add_argument("--bitince-kapat", action="store_true", help="Is bitince ENTER beklemeden tarayiciyi kapat")
    return p


def ikinci_sinif_firmalari(page, adaylar, bit, ayarlar, log, yenile=False):
    """Luca'daki firmalardan Musteri Listesi'nde 2. sinif (isletme/serbest meslek defteri) olanlar."""
    onbellek_yolu = CIKTI / kz.ONBELLEK
    onbellek = {} if yenile else kz.onbellek_oku(onbellek_yolu, bit.year)
    siniflar = ayarlar.get("musteri_sinifi", IKINCI_SINIF)
    kayitlar = []
    for sira, sinif in enumerate([siniflar] if isinstance(siniflar, str) else siniflar):
        kayitlar += kz._musteri_listesi(page, bit.year, CIKTI / "tani-liste", sinif, log, onbellek, onbellek_yolu) or []
    acik_pencereleri_kapat(page)
    if not kayitlar:
        yaz("UYARI: 2. sınıf firma listesi alınamadı (Müşteri Listesi okunamadı)", log)
        return []
    uygun = [f for f in adaylar if luca_kaydi_bul(f, kayitlar)]
    yaz(f"2. sınıf firma: {len(uygun)} (Luca'daki {len(adaylar)} firma içinde); "
        f"{len(adaylar) - len(uygun)} firma bu listede olmadığı için atlandı", log)
    return uygun


def defter_beyan_cek(args, ayarlar, p):
    kz.ayarlari_uygula(args, ayarlar)
    bas, bit = kz.tarih_araligi(args, ayarlar, p)
    bas_m, bit_m = f"{bas:%d/%m/%Y}", f"{bit:%d/%m/%Y}"
    gece_modu = bool(args.bitince_kapat)
    klasor = CIKTI / date.today().isoformat()
    klasor.mkdir(parents=True, exist_ok=True)
    log = klasor / "calisma.log"
    kayit_yolu = CIKTI / db_sonuc.DOSYA
    konsol.bolum(f"DEFTER BEYAN {args.islem.upper()}  {bas_m} - {bit_m}", log)
    profil = profil_klasoru(log)
    tani = klasor / "tani"
    sonuclar = {}

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = tarayici_ac(pw, profil, log, AYAR["chrome_gunlugu"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page = luca_oturumu_ac(ctx, page, ayarlar, gece_modu, tani, log)
        if page is None:
            tarayiciyi_kapat(ctx)
            return 1
        try:
            _, _, luca_firmalari = firma_secici_bekle(page)
            secim = firmalari_suz(luca_firmalari, ayarlar, args.firma, args.limit, bit, log, tam_adlar=args.firma_tam)
            if not secim.firmalar:
                yaz(f"Işlenecek firma yok: {secim.bos_sebep}.", log)
                return 1
            firmalar = list(secim.firmalar)
            if not args.tum_firmalar:
                firmalar = ikinci_sinif_firmalari(page, firmalar, bit, ayarlar, log, args.listeyi_yenile)
            if not firmalar:
                yaz("Işlenecek 2. sınıf firma yok.", log)
                return 1
            ardisik = 0
            for i, firma in enumerate(firmalar, 1):
                if page.is_closed():
                    yaz("UYARI: Luca ana penceresi kapandı; kalan firmalar atlandı", log)
                    break
                yaz(f"[{i}/{len(firmalar)}] {firma}  (Defter Beyan {args.islem})", log)
                db = None
                try:
                    acik_pencereleri_kapat(page)
                    firma_sec(page, firma, log)
                    if not donem_ayarla(page, firma, bas, bit, log):
                        raise LookupError("firmanın bu döneme uygun çalışma dönemi yok")
                    db = defterbeyan_luca.sayfayi_ac(ctx, page, log)
                    sonuc = defterbeyan_luca.firma_isle(db, firma, bas_m, bit_m, args.islem, log, tani,
                                                        tani_hep=args.tani)
                    ardisik = 0 if not sonuc["hata"] else ardisik + 1
                except LookupError as e:
                    ardisik += 1
                    yaz(f"    HATA: {e}", log)
                    sonuc = db_sonuc.bos_sonuc(firma, f"{bas_m}-{bit_m}", args.islem)
                    sonuc["hata"], sonuc["durum"] = str(e)[:200], "hata"
                except Exception as e:
                    if page.is_closed():
                        raise
                    ardisik += 1
                    yaz(f"    HATA: {type(e).__name__}: {str(e)[:150]}", log)
                    sonuc = db_sonuc.bos_sonuc(firma, f"{bas_m}-{bit_m}", args.islem)
                    sonuc["hata"], sonuc["durum"] = type(e).__name__, "hata"
                finally:
                    if db is not None:
                        try:
                            db.close()
                        except Exception:
                            pass
                sonuclar[firma] = sonuc
                db_sonuc.kaydet(kayit_yolu, f"{bas_m}-{bit_m}", {firma: sonuc})
                if ardisik >= ARDISIK_HATA_SINIRI:
                    yaz(f"UYARI: Art arda {ardisik} hata; kalan firmalar atlandı", log)
                    break
        finally:
            tarayiciyi_kapat(ctx)
    tamam = sum(1 for s in sonuclar.values() if s["durum"] == "tamam")
    bekleyen = sum(1 for s in sonuclar.values() if s["durum"] == "gönderilmemiş var")
    hatali = sum(1 for s in sonuclar.values() if s["durum"] == "hata")
    yaz(f"[OK] {len(sonuclar)} firma: {tamam} tamam, {bekleyen} gönderilmemiş kayıt var, {hatali} hata: {kayit_yolu}", log)
    return 0 if sonuclar else 1


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
        return defter_beyan_cek(args, ayarlar, p)
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
