#!/usr/bin/env python3
"""Luca portalindan tum firmalar icin e-fatura / e-arsiv belgelerini toplu ceker ve indirir."""

import argparse
import csv
import json
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta
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
ONAY_METINLERI = ["Sorgula", "GİB'den Getir", "Getir", "Onayla", "Tamam", "Uygula"]

TARIH_BICIMI = "%d/%m/%Y"
AZAMI_GUN = 30  # GIB sorgusu tek seferde en fazla 30 gun kabul ediyor


def yaz(mesaj, log_dosyasi=None):
    print(mesaj, flush=True)
    if log_dosyasi:
        with open(log_dosyasi, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {mesaj}\n")


def sadelestir(metin):
    """Turkce karakter ve buyuk/kucuk harf farkini yok sayarak karsilastirma icin."""
    metin = metin.replace("ı", "i").replace("İ", "i")
    metin = unicodedata.normalize("NFKD", metin)
    metin = "".join(c for c in metin if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", metin).strip().upper()


def dosya_adi_yap(metin):
    metin = metin.replace("ı", "i").replace("İ", "I")
    metin = unicodedata.normalize("NFKD", metin)
    metin = "".join(c for c in metin if not unicodedata.combining(c))
    metin = re.sub(r"[^A-Za-z0-9._ -]", "_", metin).strip()
    return re.sub(r"\s+", " ", metin) or "isimsiz"


def tarih_cozumle(metin):
    return datetime.strptime(metin.strip(), TARIH_BICIMI).date()


def tarih_araliklari(baslangic, bitis, gun=AZAMI_GUN):
    """30 gunluk parcalara boler; her parca bir oncekinin bitis tarihinden basliyor."""
    if bitis < baslangic:
        raise ValueError("Bitis tarihi baslangictan once olamaz")
    araliklar = []
    su_an = baslangic
    while su_an < bitis:
        son = min(su_an + timedelta(days=gun), bitis)
        araliklar.append((su_an.strftime(TARIH_BICIMI), son.strftime(TARIH_BICIMI)))
        su_an = son
    if not araliklar:
        araliklar.append((baslangic.strftime(TARIH_BICIMI), bitis.strftime(TARIH_BICIMI)))
    return araliklar


def icinde_bulunulan_ay():
    bugun = date.today()
    bas = bugun.replace(day=1)
    bit = (bas + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return bas, bit


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


def tarih_kutulari(page):
    adaylar = []
    for fr in cerceveler(page):
        try:
            kutular = fr.locator("input[type=text], input:not([type])")
            for i in range(kutular.count()):
                kutu = kutular.nth(i)
                if not kutu.is_visible():
                    continue
                deger = kutu.input_value() or ""
                nitelik = " ".join(
                    x for x in (kutu.get_attribute("name"), kutu.get_attribute("id"), kutu.get_attribute("class")) if x
                ).lower()
                if re.search(r"\d{2}[./]\d{2}[./]\d{4}", deger) or re.search(r"tarih|date", nitelik):
                    adaylar.append(kutu)
        except Exception:
            continue
    return adaylar


def kutuya_yaz(kutu, deger):
    try:
        kutu.fill(deger)
        if (kutu.input_value() or "").strip() == deger:
            return True
    except Exception:
        pass
    try:
        kutu.click()
        kutu.press("Control+a")
        kutu.type(deger, delay=40)
        if (kutu.input_value() or "").strip() == deger:
            return True
    except Exception:
        pass
    try:  # salt okunur / datepicker bagli alanlar icin son care
        kutu.evaluate(
            "(el, v) => { el.removeAttribute('readonly'); el.value = v;"
            " el.dispatchEvent(new Event('input', {bubbles:true}));"
            " el.dispatchEvent(new Event('change', {bubbles:true})); }",
            deger,
        )
        return (kutu.input_value() or "").strip() == deger
    except Exception:
        return False


def gibden_getir(page, baslangic, bitis, log):
    _, dugme = metinle_bul(page, "GİB'den Getir")
    dugme.click()
    page.wait_for_timeout(2000)

    kutular = tarih_kutulari(page)
    if len(kutular) < 2:
        yaz(f"    UYARI: tarih kutulari bulunamadi ({len(kutular)} adet), Luca varsayilani kullanilacak", log)
    else:
        if not kutuya_yaz(kutular[0], baslangic) or not kutuya_yaz(kutular[1], bitis):
            yaz("    UYARI: tarih alanlari doldurulamadi", log)

    varsa_tikla(page, ONAY_METINLERI, sure=1500)
    page.wait_for_timeout(4000)
    try:
        page.wait_for_load_state("networkidle", timeout=120000)
    except Exception:
        pass
    yaz(f"    GİB'den Getir tamam: {baslangic} - {bitis}", log)


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


def firma_isle(page, firma, belge_tipi, araliklar, cikti_kok, log):
    sonuc = {"firma": firma, "belge_tipi": belge_tipi, "fatura_sayisi": 0, "durum": "", "dosyalar": []}
    klasor = cikti_kok / dosya_adi_yap(firma) / belge_tipi
    klasor.mkdir(parents=True, exist_ok=True)

    firma_sec(page, firma)
    menuye_git(page, belge_tipi)
    for bas, bit in araliklar:
        gibden_getir(page, bas, bit, log)

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


def tarayici_ac(pw, profil, log):
    """Once bilgisayarda kurulu Chrome/Edge denenir; Playwright'in kendi tarayicisi son care."""
    hatalar = []
    for kanal, ad in (("chrome", "Google Chrome"), ("msedge", "Microsoft Edge"), (None, "Playwright Chromium")):
        secenekler = {"channel": kanal} if kanal else {}
        try:
            ctx = pw.chromium.launch_persistent_context(
                str(profil), headless=False, accept_downloads=True,
                args=["--start-maximized"], no_viewport=True, **secenekler
            )
            yaz(f"Tarayici: {ad}", log)
            return ctx
        except Exception as e:
            hatalar.append(f"  {ad}: {str(e).splitlines()[0][:120]}")
    raise RuntimeError(
        "Hicbir tarayici acilamadi:\n" + "\n".join(hatalar)
        + "\n\nCozum: Google Chrome kurun (google.com/chrome) veya"
        " internet baglantisi duzelince tarayici-indir.bat dosyasini calistirin."
    )


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
    p.add_argument("--baslangic", help="GG/AA/YYYY (ayarlar.json'daki degeri ezer)")
    p.add_argument("--bitis", help="GG/AA/YYYY (ayarlar.json'daki degeri ezer)")
    p.add_argument("--listele", action="store_true", help="Sadece firma listesini yazdir, islem yapma")
    args = p.parse_args()

    bas_metin = args.baslangic or ayarlar.get("baslangic_tarihi")
    bit_metin = args.bitis or ayarlar.get("bitis_tarihi")
    if bas_metin and bit_metin:
        try:
            baslangic, bitis = tarih_cozumle(bas_metin), tarih_cozumle(bit_metin)
        except ValueError:
            p.error("Tarihler GG/AA/YYYY biciminde olmali, orn: 01/08/2026")
        if bitis < baslangic:
            p.error("Bitis tarihi baslangictan once olamaz")
    else:
        baslangic, bitis = icinde_bulunulan_ay()
    araliklar = tarih_araliklari(baslangic, bitis)

    cikti_kok = Path(ayarlar.get("indirme_klasoru") or "indirilenler").expanduser()
    if not cikti_kok.is_absolute():
        cikti_kok = KOK / cikti_kok
    calisma = cikti_kok / date.today().isoformat()
    calisma.mkdir(parents=True, exist_ok=True)
    log = calisma / "calisma.log"
    profil = KOK / ".tarayici-profili"

    with sync_playwright() as pw:
        ctx = tarayici_ac(pw, profil, log)
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
            aranan = [sadelestir(f) for f in args.firma if f.strip()]
            firmalar = [f for f in firmalar if any(a in sadelestir(f) for a in aranan)]
            if not firmalar:
                yaz(f"'{', '.join(args.firma)}' ile eslesen firma yok. Adlari gormek icin: firmalari-listele.bat", log)
                ctx.close()
                return
            yaz(f"Eslesen firma(lar): {', '.join(firmalar)}", log)
        atlanacak = [sadelestir(a) for a in ayarlar.get("atlanacak_firmalar", []) if a.strip()]
        firmalar = [f for f in firmalar if sadelestir(f) not in atlanacak]
        if args.limit:
            firmalar = firmalar[: args.limit]

        yaz(f"Islenecek firma sayisi: {len(firmalar)} | belge tipi: {args.belge_tipi}", log)
        yaz(f"Tarih araligi: {araliklar[0][0]} - {araliklar[-1][1]} ({len(araliklar)} sorgu/firma)\n", log)

        sonuclar = []
        for i, firma in enumerate(firmalar, 1):
            yaz(f"[{i}/{len(firmalar)}] {firma}", log)
            try:
                sonuclar.append(firma_isle(page, firma, args.belge_tipi, araliklar, calisma, log))
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
