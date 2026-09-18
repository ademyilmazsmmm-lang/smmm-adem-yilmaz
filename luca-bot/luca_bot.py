#!/usr/bin/env python3
"""Luca portalindan tum firmalar icin e-fatura / e-arsiv belgelerini toplu ceker ve indirir."""

import argparse
import csv
import json
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

KOK = Path(__file__).resolve().parent
AYAR_DOSYASI = KOK / "ayarlar.json"
ORNEK_AYAR = KOK / "ayarlar.ornek.json"

LUCA_URL = "https://auygs.luca.com.tr/Luca/luca.do"
UST_MENU = "Akıllı Entegrasyon Noktası"

BELGE_TIPLERI = {
    "e-arsiv-alis": "e-Arşiv Alış Faturaları",
    "e-arsiv-satis": "e-Arşiv Satış Faturaları",
    "e-fatura-alis": "e-Fatura Alış Faturaları",
    "e-fatura-satis": "e-Fatura Satış Faturaları",
}

KAPAT_METINLERI = ["Bir daha gösterme", "Kapat", "Tamam"]
ONAY_METINLERI = ["Sorgula", "Getir", "Tamam", "Uygula"]


def yaz(mesaj, log_dosyasi=None):
    print(mesaj, flush=True)
    if log_dosyasi:
        with open(log_dosyasi, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {mesaj}\n")


def dosya_adi_yap(metin):
    metin = unicodedata.normalize("NFKD", metin)
    metin = "".join(c for c in metin if not unicodedata.combining(c))
    metin = re.sub(r"[^A-Za-z0-9._ -]", "_", metin).strip()
    return re.sub(r"\s+", " ", metin) or "isimsiz"


def ayarlari_oku():
    kaynak = AYAR_DOSYASI if AYAR_DOSYASI.exists() else ORNEK_AYAR
    with open(kaynak, encoding="utf-8") as f:
        return json.load(f)


def cerceveler(page):
    """Luca eski bir Struts uygulamasi; ekranlar farkli frame'lere dagilmis olabiliyor."""
    return list(page.frames)


def bul(page, kurucu, sure=15000, gorunur=True):
    bitis = time.time() + sure / 1000
    son_hata = None
    while time.time() < bitis:
        for fr in cerceveler(page):
            try:
                loc = kurucu(fr)
                if loc.count() == 0:
                    continue
                ilk = loc.first
                if not gorunur or ilk.is_visible():
                    return fr, ilk
            except Exception as e:  # frame gezinme sirasinda kopabiliyor
                son_hata = e
        page.wait_for_timeout(300)
    raise LookupError(f"Ogeye ulasilamadi (son hata: {son_hata})")


def metinle_bul(page, metin, sure=15000):
    return bul(page, lambda f: f.get_by_text(metin, exact=False), sure=sure)


def varsa_tikla(page, metinler, sure=1500):
    for metin in metinler:
        try:
            _, loc = metinle_bul(page, metin, sure=sure)
            loc.click()
            page.wait_for_timeout(400)
            return metin
        except Exception:
            continue
    return None


def firma_secici(page):
    """Sag ustteki firma listesi: en cok secenege sahip select."""
    en_iyi = None
    for fr in cerceveler(page):
        try:
            secimler = fr.locator("select")
            for i in range(secimler.count()):
                sec = secimler.nth(i)
                if not sec.is_visible():
                    continue
                secenekler = sec.locator("option").all_inner_texts()
                temiz = [s.strip() for s in secenekler if s.strip()]
                if len(temiz) < 5:
                    continue
                if any("HIZLI ERİŞİM" in s.upper() for s in temiz):
                    continue
                if en_iyi is None or len(temiz) > len(en_iyi[2]):
                    en_iyi = (fr, sec, temiz)
        except Exception:
            continue
    if en_iyi is None:
        raise LookupError("Firma listesi (select) bulunamadi")
    return en_iyi


def firma_sec(page, firma_adi):
    _, sec, _ = firma_secici(page)
    sec.select_option(label=firma_adi)
    page.wait_for_timeout(2500)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    varsa_tikla(page, KAPAT_METINLERI)


def menuye_git(page, belge_tipi):
    hedef = BELGE_TIPLERI[belge_tipi]
    _, ust = metinle_bul(page, UST_MENU)
    ust.hover()
    page.wait_for_timeout(600)
    try:
        ust.click()
        page.wait_for_timeout(600)
    except Exception:
        pass
    _, alt = metinle_bul(page, hedef, sure=8000)
    alt.click()
    page.wait_for_timeout(2500)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass


def gibden_getir(page, baslangic, bitis, log):
    _, dugme = metinle_bul(page, "GİB'den Getir")
    dugme.click()
    page.wait_for_timeout(1500)

    for deger, anahtar in ((baslangic, "baslangic"), (bitis, "bitis")):
        if not deger:
            continue
        try:
            fr, _ = bul(page, lambda f: f.locator("input[type=text]"), sure=1500)
            kutular = fr.locator("input[type=text]")
            idx = 0 if anahtar == "baslangic" else 1
            if kutular.count() > idx:
                hedef = kutular.nth(idx)
                if hedef.is_visible() and re.search(r"\d{2}[./]\d{2}[./]\d{4}", hedef.input_value() or ""):
                    hedef.fill(deger)
        except Exception:
            pass

    varsa_tikla(page, ONAY_METINLERI, sure=1200)
    page.wait_for_timeout(4000)
    try:
        page.wait_for_load_state("networkidle", timeout=60000)
    except Exception:
        pass
    yaz("    GİB'den Getir tamamlandi", log)


def tabloyu_oku(page):
    for fr in cerceveler(page):
        try:
            if fr.get_by_text("Belge Numarası", exact=False).count() == 0:
                continue
            satirlar = fr.locator("table tr")
            veriler = []
            for i in range(satirlar.count()):
                hucreler = satirlar.nth(i).locator("td").all_inner_texts()
                temiz = [h.strip() for h in hucreler if h.strip()]
                if len(temiz) >= 4:
                    veriler.append(temiz)
            if veriler:
                return fr, veriler
        except Exception:
            continue
    return None, []


def hepsini_sec(page, fr):
    kutular = fr.locator("input[type=checkbox]")
    sayi = kutular.count()
    if sayi == 0:
        return 0
    try:
        kutular.first.check()
        page.wait_for_timeout(800)
        if sum(1 for i in range(sayi) if kutular.nth(i).is_checked()) > 1:
            return sayi
    except Exception:
        pass
    secilen = 0
    for i in range(sayi):
        try:
            kutu = kutular.nth(i)
            if kutu.is_visible() and not kutu.is_checked():
                kutu.check()
                secilen += 1
        except Exception:
            continue
    page.wait_for_timeout(500)
    return secilen


def indir(page, dugme_metni, hedef_klasor, on_ek, log):
    try:
        _, dugme = metinle_bul(page, dugme_metni, sure=8000)
    except LookupError:
        yaz(f"    '{dugme_metni}' butonu bulunamadi, atlandi", log)
        return None
    try:
        with page.expect_download(timeout=180000) as bilgi:
            dugme.click()
        dosya = bilgi.value
        ad = f"{on_ek}_{dosya.suggested_filename}"
        yol = hedef_klasor / ad
        dosya.save_as(str(yol))
        yaz(f"    indirildi: {ad}", log)
        return yol
    except Exception as e:
        yaz(f"    '{dugme_metni}' indirilemedi: {type(e).__name__}", log)
        return None


def firma_isle(page, firma, belge_tipi, ayarlar, cikti_kok, log):
    sonuc = {"firma": firma, "belge_tipi": belge_tipi, "fatura_sayisi": 0, "durum": "", "dosyalar": []}
    klasor = cikti_kok / dosya_adi_yap(firma) / belge_tipi
    klasor.mkdir(parents=True, exist_ok=True)

    firma_sec(page, firma)
    menuye_git(page, belge_tipi)
    gibden_getir(page, ayarlar.get("baslangic_tarihi"), ayarlar.get("bitis_tarihi"), log)

    fr, satirlar = tabloyu_oku(page)
    sonuc["fatura_sayisi"] = len(satirlar)
    yaz(f"    {len(satirlar)} satir listelendi", log)

    if satirlar:
        with open(klasor / "liste.csv", "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerows(satirlar)

    if fr is not None and satirlar:
        hepsini_sec(page, fr)
        for dugme, on_ek in (("Seçilenleri İndir", "belgeler"), ("Excel", "liste")):
            yol = indir(page, dugme, klasor, on_ek, log)
            if yol:
                sonuc["dosyalar"].append(yol.name)
        sonuc["durum"] = "tamam"
    else:
        sonuc["durum"] = "fatura yok"
    return sonuc


def hata_kaydet(page, klasor, firma):
    klasor.mkdir(parents=True, exist_ok=True)
    ad = dosya_adi_yap(firma)
    try:
        page.screenshot(path=str(klasor / f"{ad}.png"), full_page=True)
    except Exception:
        pass
    try:
        (klasor / f"{ad}.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass


def main():
    ayarlar = ayarlari_oku()
    p = argparse.ArgumentParser(description="Luca toplu e-fatura indirme botu")
    p.add_argument("--firma", action="append", help="Sadece bu firma(lar) islensin")
    p.add_argument("--belge-tipi", default=ayarlar.get("belge_tipi", "e-arsiv-alis"), choices=list(BELGE_TIPLERI))
    p.add_argument("--limit", type=int, help="Ilk N firma ile sinirla")
    p.add_argument("--listele", action="store_true", help="Sadece firma listesini yazdir, islem yapma")
    args = p.parse_args()

    cikti_kok = Path(ayarlar.get("indirme_klasoru") or "indirilenler").expanduser()
    if not cikti_kok.is_absolute():
        cikti_kok = KOK / cikti_kok
    calisma = cikti_kok / date.today().isoformat()
    calisma.mkdir(parents=True, exist_ok=True)
    log = calisma / "calisma.log"
    profil = KOK / ".tarayici-profili"

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(profil), headless=False, accept_downloads=True, args=["--start-maximized"], no_viewport=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.on("dialog", lambda d: d.accept())
        page.goto(LUCA_URL)

        yaz("\n>>> Tarayici acildi. Luca'ya giris yapip firma ekrani gelince buraya donun.", log)
        input(">>> Giris tamamlandiysa ENTER'a basin: ")

        varsa_tikla(page, KAPAT_METINLERI)
        _, _, firmalar = firma_secici(page)
        yaz(f"{len(firmalar)} firma bulundu", log)

        if args.listele:
            for f in firmalar:
                print(" -", f)
            ctx.close()
            return

        if args.firma:
            istenen = {f.strip().upper() for f in args.firma}
            firmalar = [f for f in firmalar if f.strip().upper() in istenen]
        atlanacak = {a.strip().upper() for a in ayarlar.get("atlanacak_firmalar", [])}
        firmalar = [f for f in firmalar if f.strip().upper() not in atlanacak]
        if args.limit:
            firmalar = firmalar[: args.limit]

        yaz(f"Islenecek firma sayisi: {len(firmalar)} | belge tipi: {args.belge_tipi}\n", log)

        sonuclar = []
        for i, firma in enumerate(firmalar, 1):
            yaz(f"[{i}/{len(firmalar)}] {firma}", log)
            try:
                sonuclar.append(firma_isle(page, firma, args.belge_tipi, ayarlar, calisma, log))
            except Exception as e:
                yaz(f"    HATA: {type(e).__name__}: {e}", log)
                hata_kaydet(page, calisma / "hatalar", firma)
                sonuclar.append({"firma": firma, "belge_tipi": args.belge_tipi, "fatura_sayisi": 0,
                                 "durum": f"hata: {type(e).__name__}", "dosyalar": []})
                page.goto(LUCA_URL)
                page.wait_for_timeout(2000)

        ozet = calisma / "ozet.csv"
        with open(ozet, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Firma", "Belge Tipi", "Fatura Sayisi", "Durum", "Dosyalar"])
            for s in sonuclar:
                w.writerow([s["firma"], s["belge_tipi"], s["fatura_sayisi"], s["durum"], "; ".join(s["dosyalar"])])

        basarili = sum(1 for s in sonuclar if s["durum"] == "tamam")
        toplam_fatura = sum(s["fatura_sayisi"] for s in sonuclar)
        yaz(f"\nBitti. {basarili}/{len(sonuclar)} firma tamamlandi, {toplam_fatura} fatura listelendi.", log)
        yaz(f"Dosyalar: {calisma}", log)
        yaz(f"Ozet: {ozet}", log)

        input(">>> Tarayiciyi kapatmak icin ENTER'a basin: ")
        ctx.close()


if __name__ == "__main__":
    sys.exit(main())
