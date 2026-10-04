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
import signal
import sys
import traceback
from datetime import date

from lucabot import eposta, konsol
from lucabot.calisma import Calisma, etkin_firmalar, tekrar_listesini_oku, tekrar_secimi
from lucabot.firma_listesi import bugun_tamamlananlar, firmalari_suz
from lucabot.giris import luca_oturumu_ac
from lucabot.luca_beyanname import ekrandan_al
from lucabot.luca_gezinme import firma_secici_bekle
from lucabot.musteri_listesi import MUSTERI_LISTESI_DOSYASI, kaydet as musteri_listesini_kaydet, listeyi_oku
from lucabot.ortak import (AYAR, DURDUR_DOSYASI, ayarlari_oku, gunluge_yaz, icinde_bulunulan_ay,
                           indirme_koku, tarih_araliklari, tarih_cozumle, yaz)
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
    p.add_argument("--firma-listesi-cek", action="store_true",
                   help="Luca'nin Musteri Listesi'nden firma bilgilerini (acilis/kapanis dahil) cek ve kaydet")
    p.add_argument("--beyanname-cek", action="store_true",
                   help="Luca'nin GIB Beyanname Takip ekranindan KDV1 beyanname PDF'lerini indir (--baslangic: kontrol edilen donem)")
    p.add_argument("--yil", type=int,
                   help="--firma-listesi-cek icin hangi yilin firmalari (varsayilan: bu yil)")
    p.add_argument("--tekrar-listesi",
                   help="Yalniz bu dosyadaki firma/ekranlari yeniden sorgula ({firma: [belge tipi]} JSON; arayuz yazar)")
    p.add_argument("--bastan", action="store_true",
                   help="Bugun tamamlanan ekranlar da yeniden taransin (sormadan)")
    return p


def belge_tiplerini_belirle(args, ayarlar):
    if args.tekrar_listesi:  # listedeki ekranlarin birlesimi, menudeki sirayla
        istenen = set().union(*tekrar_listesini_oku(args.tekrar_listesi).values())
        return [t for t in TUM_BELGELER if t in istenen]
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
    AYAR["indirme_sekmesiz"] = bool(ayarlar.get("indirme_sekmesiz", True))
    if AYAR["chrome_gunlugu"]:
        # Playwright'in tarayici cikis mesajlarini ekrana bassin; cokme sebebi
        # genelde burada yaziyor ("Target crashed", exit code, stderr)
        os.environ["DEBUG"] = "pw:browser"


def calisma_klasoru(ayarlar):
    """Bugunun indirme/gunluk klasoru (indirme_koku()/YYYY-AA-GG)."""
    klasor = indirme_koku(ayarlar) / date.today().isoformat()
    klasor.mkdir(parents=True, exist_ok=True)
    return klasor


def devam_mi_bastan_mi(ctx, rapor_klasoru, belge_tipleri, gece_modu, log):
    """Ayni gun yarida kalan calisma varsa: tamamlanan ekranlari atla mi, hepsini yeniden mi?

    Gece modunda (kimse cevap veremez) kaldigi yerden otomatik devam edilir;
    elle calistirmada kullaniciya sorulur, cunku bazen kasitli olarak hepsinin
    yeniden taranmasi istenebilir.
    """
    aday = bugun_tamamlananlar(rapor_klasoru, belge_tipleri)
    if not aday:
        return {}
    toplam = sum(len(v) for v in aday.values())
    if gece_modu:
        yaz(f"Bugun daha once {len(aday)} firmada {toplam} ekran tamamlanmis"
            " (yarida kalan calisma), gece modunda kaldigi yerden devam ediliyor", log)
        return aday
    print(f"\nBugun daha once {len(aday)} firmada"
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

def sonucu_bildir(calisma, ozet, ayarlar, klasor, rapor_klasoru, log):
    konsol.son_ozet(ozet, log)
    yaz(f"  Rapor    : {rapor_klasoru / 'rapor.xlsx'}  (surekli - her calismada guncellenir)", log)
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
        eposta.gonder(ayarlar, rapor_klasoru, calisma.sonuclar, lambda m: yaz(m, log), donem_metni)
    except Exception as e:
        yaz(f"UYARI: e-posta adimi hata verdi ({type(e).__name__}: {e})", log)


# --- firma listesi cekme -------------------------------------------------------

def firma_listesini_cek(args, ayarlar):
    """Luca > Yönetici > Müşteri Listesi'nden secilen yilin firmalarini indirilenler/luca-musteri-listesi.json'a yazar."""
    ayarlari_uygula(args, ayarlar)
    yil = args.yil or date.today().year
    gece_modu = bool(args.bitince_kapat)
    klasor = calisma_klasoru(ayarlar)
    log = klasor / "calisma.log"
    konsol.bolum(f"LUCA MUSTERI LISTESI ({yil})", log)
    profil = profil_klasoru(log)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = tarayici_ac(pw, profil, log, AYAR["chrome_gunlugu"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page = luca_oturumu_ac(ctx, page, ayarlar, gece_modu, klasor / "tani", log)
        if page is None:
            tarayiciyi_kapat(ctx)
            return 1
        try:
            firma_secici_bekle(page)  # uygulama tamamen yuklensin (menu ve firma listesi gelsin)
            kayitlar = listeyi_oku(page, yil, klasor / "tani", log)
        except LookupError as e:
            yaz(f"HATA: {e}", log)
            kayitlar = []
        finally:
            tarayiciyi_kapat(ctx)
    if not kayitlar:
        yaz("Luca'dan firma okunamadi; tani dosyalari: " + str(klasor / "tani"), log)
        return 1
    yol = indirme_koku(ayarlar) / MUSTERI_LISTESI_DOSYASI
    musteri_listesini_kaydet(yol, yil, kayitlar)
    yaz(f"[OK] {yil} yilinda {len(kayitlar)} firma okundu: {yol}", log)
    return 0


BEYANNAME_LISTESI_DOSYASI = "luca-beyannameler.json"


def beyannameleri_cek(args, ayarlar, p):
    """Luca > Muhasebe > Beyannameler > GİB Beyanname Takip'ten onayli KDV1 PDF'lerini indirir.

    Kontrol edilen donemin (--baslangic) bir onceki ayinin beyannameleri suzulur.
    PDF'ler indirilenler/beyannameler/<tarih> klasorune cikarilir, dosya listesi
    indirilenler/luca-beyannameler.json'a yazilir (arayuz buradan okur).
    """
    import json
    ayarlari_uygula(args, ayarlar)
    hedef_bas, _ = tarih_araligini_belirle(args, ayarlar, p)
    gece_modu = bool(args.bitince_kapat)
    klasor = calisma_klasoru(ayarlar)
    log = klasor / "calisma.log"
    kok = indirme_koku(ayarlar)
    pdf_klasoru = kok / "beyannameler" / date.today().isoformat()
    konsol.bolum("LUCA GIB BEYANNAME TAKIP (KDV1 PDF)", log)
    profil = profil_klasoru(log)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = tarayici_ac(pw, profil, log, AYAR["chrome_gunlugu"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page = luca_oturumu_ac(ctx, page, ayarlar, gece_modu, klasor / "tani", log)
        if page is None:
            tarayiciyi_kapat(ctx)
            return 1
        try:
            firma_secici_bekle(page)
            # beyanname menusu yalniz genel muhasebe firmalarinda var: en son isleyen firma hatirlanir
            onbellek = kok / "beyanname-firmasi.txt"
            try:
                tercih = ayarlar.get("beyanname_firmasi") or onbellek.read_text(encoding="utf-8").strip() or None
            except OSError:
                tercih = None
            bilgi = {}
            yollar, sayi = ekrandan_al(page, pdf_klasoru, klasor / "tani", hedef_bas,
                                       ayarlar.get("beyanname_menusu"), log, tercih, bilgi)
            if bilgi.get("firma"):
                onbellek.write_text(bilgi["firma"], encoding="utf-8")
        except LookupError as e:
            yaz(f"HATA: {e}", log)
            yollar, sayi = [], 0
        finally:
            tarayiciyi_kapat(ctx)
    if not yollar:
        yaz("Beyanname PDF'i alinamadi; tani dosyalari: " + str(klasor / "tani"), log)
        return 1
    (kok / BEYANNAME_LISTESI_DOSYASI).write_text(
        json.dumps({"klasor": str(pdf_klasoru), "dosyalar": [str(y) for y in yollar],
                    "listelenen": sayi}, ensure_ascii=False, indent=1), encoding="utf-8")
    yaz(f"[OK] {len(yollar)} beyanname PDF'i alindi (Luca listesi: {sayi} kayit): {pdf_klasoru}", log)
    return 0


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
    rapor_klasoru = klasor.parent  # surekli rapor: indirme_koku(), gunluk klasorun bir ustu
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
        _, _, luca_firmalari = firma_secici_bekle(page)
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
        if args.tekrar_listesi and secim.firmalar:
            # yalniz listedeki firmalar ve her birinde yalniz listedeki ekranlar yeniden sorgulanir
            secim.firmalar, ek_atlanan = tekrar_secimi(
                secim.firmalar, tekrar_listesini_oku(args.tekrar_listesi), belge_tipleri)
            for f, tipler in ek_atlanan.items():
                secim.atlanan_ekranlar.setdefault(f, set()).update(tipler)
            secim.bos_sebep = "tekrar listesindeki firmalar Luca listesinde / firma listesinde bulunamadi"
            yaz(f"Yeniden sorgulanacak: {len(secim.firmalar)} firma, {len(belge_tipleri)} ekran turu", log)
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

        if args.bastan or args.tekrar_listesi:
            yaz("Bugun tamamlanan ekranlar da yeniden taranacak"
                + (" (yeniden sorgulama)" if args.tekrar_listesi else " (--bastan)"), log)
            bugun_tamam = {}
        else:
            bugun_tamam = devam_mi_bastan_mi(ctx, rapor_klasoru, belge_tipleri, gece_modu, log)
        etkin = etkin_firmalar(secim.firmalar, belge_tipleri, secim.atlanan_ekranlar, bugun_tamam)
        if len(etkin) < len(secim.firmalar):
            yaz(f"Tum ekranlari X isaretli ya da bugun tamamlanmis {len(secim.firmalar) - len(etkin)} firma"
                " atlandi (Luca'da acilmayacak)", log)
        secim.firmalar = etkin
        if not etkin:
            yaz("\nIslenecek firma yok: secili ekranlarin hepsi firmalar.xlsx'te X ya da bugun tamamlanmis.", log)
            if not gece_modu:
                kullanici_bekle(ctx, ">>> Kapatmak icin ENTER: ")
            tarayiciyi_kapat(ctx)
            return 0
        yaz(f"Islenecek firma sayisi: {len(secim.firmalar)} | ekran: {len(belge_tipleri)}", log)

        # 4. islem
        konsol.bolum("3/4  FATURA SORGULAMA VE INDIRME  (durdurmak icin Ctrl+C)", log)
        calisma = Calisma(pw, ctx, page, profil, ayarlar, secim, belge_tipleri, araliklar,
                          klasor, log, azami_deneme, hata_siniri, bugun_tamam, rapor_klasoru)
        ozet = calisma.calistir()

        # 5. raporlama
        konsol.bolum("4/4  RAPOR", log)  # rapor her firmadan sonra zaten guncellendi
        sonucu_bildir(calisma, ozet, ayarlar, klasor, rapor_klasoru, log)

        if not gece_modu:
            kullanici_bekle(calisma.ctx, ">>> Tarayiciyi kapatmak icin ENTER'a basin: ")
        tarayiciyi_kapat(calisma.ctx)
    return 0


def _durdurma_sinyali(*_):
    raise KeyboardInterrupt


def main():
    # Arayuz (luca_arayuz.py) "Durdur"da Windows'ta CTRL_BREAK gonderir; Ctrl+C
    # ile ayni sekilde ele alinsin ki o ana kadarki sonuclar kaydedilsin
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _durdurma_sinyali)
    p = arguman_ayristirici()
    args = p.parse_args()
    ayarlar = ayarlari_oku()
    try:
        DURDUR_DOSYASI.unlink()  # onceki calismadan kalmis durdurma istegi yeni calismayi durdurmasin
    except OSError:
        pass
    try:
        if args.firma_listesi_cek:
            return firma_listesini_cek(args, ayarlar)
        if args.beyanname_cek:
            return beyannameleri_cek(args, ayarlar, p)
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
