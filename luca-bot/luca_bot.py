#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Luca portalindan tum firmalar icin e-fatura / e-arsiv belgelerini toplu ceker ve indirir.

Bu dosya yalnizca programin giris kapisidir: komut satiri seceneklerini ve
ayarlar.json'u okur, sonra isi lucabot paketindeki program taslarina devreder:

    1. Hazirlik     ayarlar, tarih araligi, calisma klasoru
    2. Luca Giris   tarayiciyi ac, giris yap           (lucabot.giris)
    3. Firmalar     islenecek firma/ekranlari belirle  (lucabot.firma_listesi)
    4. Islem        her firma icin sorgula ve indir    (lucabot.calisma)
    5. Raporlama    rapor.xlsx + ozet e-postasi        (lucabot.rapor, lucabot.eposta)

Kullanim ornekleri icin README.md'ye bakin; .bat dosyalari da bunu cagirir.
"""

import argparse
import os
import sys
import traceback
from datetime import date
from pathlib import Path

from lucabot import eposta, konsol
from lucabot.calisma import Calisma
from lucabot.firma_listesi import bugun_tamamlananlar, firmalari_suz
from lucabot.giris import luca_oturumu_ac
from lucabot.luca_gezinme import firma_secici
from lucabot.ortak import (AYAR, KOK, ayarlari_oku, gunluge_yaz,
                           icinde_bulunulan_ay, tarih_araliklari, tarih_cozumle,
                           yaz)
from lucabot.sabitler import BELGE_TIPLERI, TUM_BELGELER
from lucabot.tarayici import (kullanici_bekle, kullanici_metni_al,
                              profil_klasoru, tarayici_ac, tarayiciyi_kapat)


# --- 1. hazirlik ---------------------------------------------------------------

def arguman_ayristirici():
    p = argparse.ArgumentParser(description="Luca toplu e-fatura indirme botu")
    p.add_argument("--firma", action="append",
                   help="Sadece bu firma(lar) islensin; virgulle ayirarak birden fazla yazilabilir")
    p.add_argument("--belge-tipi", action="append", choices=list(BELGE_TIPLERI),
                   help="Birden fazla kez verilebilir; her firmada sirayla islenir")
    p.add_argument("--hepsi", action="store_true",
                   help="Tum belge tiplerini sirayla isle (menudeki butun ekranlar)")
    p.add_argument("--karsilastir", action="store_true",
                   help="Iki e-arsiv ekranini da calistir (Akilli Entegrasyon + Interaktif V.D.)")
    p.add_argument("--limit", type=int, help="Ilk N firma ile sinirla")
    p.add_argument("--baslangic", help="GG/AA/YYYY (ayarlar.json'daki degeri ezer)")
    p.add_argument("--bitis", help="GG/AA/YYYY (ayarlar.json'daki degeri ezer)")
    p.add_argument("--tarayici-indirsin", action="store_true",
                   help="Dosyayi tarayici indirsin (varsayilan: istek yakalanip kaydedilir)")
    p.add_argument("--profil-yerel", action="store_true",
                   help="Tarayici profilini program klasoru yerine %%LOCALAPPDATA%% altinda tut")
    p.add_argument("--tarayici", choices=["chrome", "edge", "chromium"],
                   help="Hangi tarayici kullanilsin (Chrome cokuyorsa edge deneyin)")
    p.add_argument("--chrome-gunlugu", action="store_true",
                   help="Chrome cokerse sebebini yazmasi icin ayrintili gunluk tut")
    p.add_argument("--donem-degistirme", action="store_true",
                   help="Donemi degistirme; eski donemdeki firmalari atla (sorun cikarsa)")
    p.add_argument("--azami-fatura", type=int,
                   help="Bu sayidan cok faturasi olan firmalari atla (0: sinir yok)")
    p.add_argument("--iptal-itiraz-atla", action="store_true",
                   help="Faturalari indir ama GIB iptal/itiraz sorgusunu yapma")
    p.add_argument("--listele", action="store_true", help="Sadece firma listesini yazdir, islem yapma")
    p.add_argument("--bitince-kapat", action="store_true",
                   help="Is bitince ENTER beklemeden tarayiciyi kapat (gece calistirma icin)")
    return p


def belge_tiplerini_belirle(args, ayarlar):
    if args.hepsi:
        return list(TUM_BELGELER)
    if args.karsilastir:
        return ["e-arsiv-alis", "e-arsiv-interaktif"]
    if args.belge_tipi:
        return args.belge_tipi
    varsayilan = ayarlar.get("belge_tipi", "e-arsiv-alis")
    tipler = varsayilan if isinstance(varsayilan, list) else [varsayilan]
    bilinmeyen = [t for t in tipler if t not in BELGE_TIPLERI]
    if bilinmeyen:
        raise SystemExit(f"HATA: ayarlar.json'daki belge_tipi taninmadi: {', '.join(bilinmeyen)}\n"
                         f"Gecerli degerler: {', '.join(BELGE_TIPLERI)}")
    return tipler


def tarih_araligini_belirle(args, ayarlar, p):
    bas_metin = args.baslangic or ayarlar.get("baslangic_tarihi")
    bit_metin = args.bitis or ayarlar.get("bitis_tarihi")
    if not (bas_metin and bit_metin):
        return icinde_bulunulan_ay()
    try:
        baslangic, bitis = tarih_cozumle(bas_metin), tarih_cozumle(bit_metin)
    except ValueError:
        p.error(f"Tarihler GG/AA/YYYY biciminde olmali, orn: 01/08/2026 (girilen: {bas_metin} - {bit_metin})")
    if bitis < baslangic:
        p.error("Bitis tarihi baslangictan once olamaz")
    return baslangic, bitis


def _sayi_ayari(ayarlar, ad, varsayilan, cevir=float):
    """ayarlar.json'daki sayi ayari; yanlis yazilmissa varsayilan kullanilir (program cokmez)."""
    try:
        return cevir(ayarlar.get(ad, varsayilan))
    except (TypeError, ValueError):
        yaz(f"UYARI: ayarlar.json'da '{ad}' sayi olmali; varsayilan ({varsayilan}) kullanilacak")
        return cevir(varsayilan)


def ayarlari_uygula(args, ayarlar):
    """ayarlar.json + komut satirini calisma ayarlarina (ortak.AYAR) isler."""
    AYAR["azami_saniye"] = max(60, int(_sayi_ayari(ayarlar, "sorgu_azami_dakika", 30) * 60))
    AYAR["durgunluk_saniye"] = max(30, int(_sayi_ayari(ayarlar, "durgunluk_dakika", 3) * 60))
    AYAR["indirme_saniye"] = max(3, int(_sayi_ayari(ayarlar, "indirme_bekleme_saniye", 30)))
    # cok faturali firmalar atlanir (0: sinir yok)
    AYAR["azami_fatura"] = max(0, int(args.azami_fatura if args.azami_fatura is not None
                                      else _sayi_ayari(ayarlar, "azami_fatura", 500)))
    AYAR["iptal_itiraz"] = bool(ayarlar.get("iptal_itiraz_sorgula", True)) and not args.iptal_itiraz_atla
    AYAR["donem_degistir"] = bool(ayarlar.get("donem_degistir", True)) and not args.donem_degistirme
    AYAR["chrome_gunlugu"] = bool(args.chrome_gunlugu)
    AYAR["profil_yerel"] = bool(args.profil_yerel) or bool(ayarlar.get("profil_yerel", False))
    AYAR["indirmeyi_yakala"] = (bool(ayarlar.get("indirmeyi_yakala", True))
                                and not args.tarayici_indirsin)
    AYAR["tarayici"] = args.tarayici or ayarlar.get("tarayici") or None
    AYAR["tarayici_yolu"] = ayarlar.get("tarayici_yolu") or None
    AYAR["giris_adresi"] = ayarlar.get("giris_adresi") or None
    AYAR["tarayici_sandbox"] = bool(ayarlar.get("tarayici_sandbox", True))
    if AYAR["chrome_gunlugu"]:
        # Playwright'in tarayici cikis mesajlarini ekrana bassin; cokme sebebi
        # genelde burada yaziyor ("Target crashed", exit code, stderr)
        os.environ["DEBUG"] = "pw:browser"


def calisma_klasoru(ayarlar):
    kok = Path(ayarlar.get("indirme_klasoru") or "indirilenler").expanduser()
    if not kok.is_absolute():
        kok = KOK / kok
    klasor = kok / date.today().isoformat()
    klasor.mkdir(parents=True, exist_ok=True)
    return klasor


def devam_mi_bastan_mi(ctx, klasor, belge_tipleri, gece_modu, log):
    """Ayni gun yarida kalan calisma varsa: tamamlanan ekranlari atla mi, hepsini yeniden mi?

    Gece modunda (kimse cevap veremez) kaldigi yerden otomatik devam edilir;
    elle calistirmada kullaniciya sorulur, cunku bazen kasitli olarak hepsinin
    yeniden taranmasi istenebilir.
    """
    aday = bugun_tamamlananlar(klasor, belge_tipleri)
    if not aday:
        return {}
    toplam = sum(len(v) for v in aday.values())
    if gece_modu:
        yaz(f"Bugun daha once {len(aday)} firmada {toplam} ekran tamamlanmis"
            " (yarida kalan calisma), gece modunda kaldigi yerden devam ediliyor", log)
        return aday
    print(f"\nBu klasorde ({klasor.name}) bugun daha once {len(aday)} firmada"
          f" {toplam} ekran tamamlanmis gorunuyor (yarida kalan bir calisma olabilir).")
    cevap = kullanici_metni_al(
        ctx, ">>> [D]evam: kaldigi yerden surer, tamamlanmis ekranlar tekrar"
        " acilmaz  /  [B]astan: hepsi yeniden taranir (varsayilan D): ")
    if cevap.strip().lower().startswith("b"):
        yaz("Kullanici secimi: hepsi bastan taranacak", log)
        return {}
    yaz(f"Kullanici secimi: kaldigi yerden devam ({len(aday)} firmada {toplam} ekran atlanacak)", log)
    return aday


# --- 5. raporlama ----------------------------------------------------------

def sonucu_bildir(calisma, ozet, ayarlar, klasor, log):
    konsol.son_ozet(ozet, log)
    yaz(f"  Rapor    : {klasor / 'rapor.xlsx'}", log)
    yaz("             (Özet | Firma Durumu | İndirilen Faturalar | Dosyalar | Hatalar ve Uyarılar)", log)
    yaz(f"  Dosyalar : {klasor}", log)
    yaz(f"  Gunluk   : {log}", log)
    if ozet.durduruldu:
        yaz(f"\n  NOT: Calisma yarida kaldi - {ozet.durduruldu}.", log)

    if ozet.durduruldu.startswith("kullanici"):
        return  # kullanici basinda; e-posta gereksiz
    # ozet e-postasi: gonderilemezse calisma yine de tamamlanmis sayilir
    donem_metni = next((s["donem"] for s in calisma.sonuclar if s.get("donem")), "")
    try:
        eposta.gonder(ayarlar, klasor, calisma.sonuclar, lambda m: yaz(m, log), donem_metni)
    except Exception as e:
        yaz(f"UYARI: e-posta adimi hata verdi ({type(e).__name__}: {e})", log)


# --- ana akis --------------------------------------------------------------

def calistir(args, ayarlar, p):
    belge_tipleri = belge_tiplerini_belirle(args, ayarlar)
    baslangic, bitis = tarih_araligini_belirle(args, ayarlar, p)
    araliklar = tarih_araliklari(baslangic, bitis)
    ayarlari_uygula(args, ayarlar)
    azami_deneme = max(1, int(_sayi_ayari(ayarlar, "tekrar_deneme", 3)))
    hata_siniri = max(1, int(_sayi_ayari(ayarlar, "ardisik_hata_siniri", 5)))
    gece_modu = bool(args.bitince_kapat)

    klasor = calisma_klasoru(ayarlar)
    log = klasor / "calisma.log"
    konsol.acilis("", f"{araliklar[0][0]} - {araliklar[-1][1]} ({len(araliklar)} sorgu/firma)",
                  belge_tipleri, klasor, gece_modu, log)
    profil = profil_klasoru(log)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        # 2. Luca giris
        konsol.bolum("1/4  LUCA GIRIS", log)
        ctx = tarayici_ac(pw, profil, log, AYAR["chrome_gunlugu"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page = luca_oturumu_ac(ctx, page, ayarlar, gece_modu, klasor / "tani", log)
        if page is None:
            if not gece_modu:
                kullanici_bekle(ctx, ">>> Kapatmak icin ENTER: ")
            tarayiciyi_kapat(ctx)
            return 1

        # 3. firmalar
        konsol.bolum("2/4  FIRMA LISTESI", log)
        _, _, luca_firmalari = firma_secici(page)
        yaz(f"Luca'da {len(luca_firmalari)} firma bulundu", log)

        if args.listele:
            for f in luca_firmalari:
                print(" -", f)
            dosya = klasor / "firmalar.txt"
            dosya.write_text("\n".join(luca_firmalari), encoding="utf-8")
            yaz(f"\nListe dosyaya da yazildi: {dosya}", log)
            kullanici_bekle(ctx, ">>> Kapatmak icin ENTER: ")
            tarayiciyi_kapat(ctx)
            return 0

        secim = firmalari_suz(luca_firmalari, ayarlar, args.firma, args.limit, baslangic, log)
        if not secim.firmalar:
            yaz(f"\nIslenecek firma yok: {secim.bos_sebep}.", log)
            if args.firma:
                yaz("Listedeki ilk 30 kayit:", log)
                for ad in luca_firmalari[:30]:
                    yaz(f"  - {ad}", log)
                yaz("\nNot: Luca adlari kisaltarak gosterebiliyor, adin bas kismini yazin.", log)
            if not gece_modu:
                kullanici_bekle(ctx, ">>> Kapatmak icin ENTER: ")
            tarayiciyi_kapat(ctx)
            return 1

        bugun_tamam = devam_mi_bastan_mi(ctx, klasor, belge_tipleri, gece_modu, log)
        yaz(f"Islenecek firma sayisi: {len(secim.firmalar)} | ekran: {len(belge_tipleri)}", log)

        # 4. islem
        konsol.bolum("3/4  FATURA SORGULAMA VE INDIRME  (durdurmak icin Ctrl+C)", log)
        calisma = Calisma(pw, ctx, page, profil, ayarlar, secim, belge_tipleri, araliklar,
                          klasor, log, azami_deneme, hata_siniri, bugun_tamam)
        ozet = calisma.calistir()

        # 5. raporlama
        konsol.bolum("4/4  RAPOR", log)  # rapor her firmadan sonra zaten guncellendi
        sonucu_bildir(calisma, ozet, ayarlar, klasor, log)

        if not gece_modu:
            kullanici_bekle(calisma.ctx, ">>> Tarayiciyi kapatmak icin ENTER'a basin: ")
        tarayiciyi_kapat(calisma.ctx)
    return 0


def main():
    p = arguman_ayristirici()
    args = p.parse_args()
    ayarlar = ayarlari_oku()
    try:
        return calistir(args, ayarlar, p)
    except KeyboardInterrupt:
        print("\nKullanici tarafindan durduruldu.")
        return 130
    except SystemExit:
        raise
    except Exception as e:
        # beklenmeyen hata: ayrintisi gunluge, kullaniciya anlasilir bir ozet
        klasor = calisma_klasoru(ayarlar)
        gunluge_yaz("BEKLENMEYEN HATA\n" + traceback.format_exc(), klasor / "calisma.log")
        print(f"\nBEKLENMEYEN HATA: {type(e).__name__}: {e}")
        print(f"Ayrinti: {klasor / 'calisma.log'} (bu dosyayi gonderirseniz duzeltirim).")
        print("Tamamlanan ekranlar kaydedildi; programi yeniden calistirip [D]evam secebilirsiniz.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
