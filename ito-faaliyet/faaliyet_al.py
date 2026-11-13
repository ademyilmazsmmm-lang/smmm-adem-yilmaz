"""
İTO e-Portal (eportal.ito.org.tr) — e-imzalı Faaliyet Belgesi toplu alma botu.

Her mükellef için sırayla: Ticaret Sicil No + Muker No -> Sorgula -> (listeden) Seç ->
İşleme Devam Et -> Ödemeyi Tamamla -> İletişim bilgileri -> İşlemi Tamamla.

GÜVENLİK: Ödenecek tutar 0,00 ₺ değilse bot İŞLEMİ TAMAMLAMAZ, o mükellefi "ATLANDI" yazar.

Kurulum (bir kez):   pip install playwright && playwright install chromium
Kullanım:            python faaliyet_al.py mukellefler.csv --ad "Ad Soyad" --tel 05xxxxxxxxx --eposta ofis@alanadi.com
İlk deneme:          python faaliyet_al.py mukellefler.csv ... --limit 1 --goster   (tarayıcı açık, yavaş)
CSV sütunları:       sicil,muker,unvan   (unvan isteğe bağlı; başlık satırı olmalı)
Çıktılar:            cikti/sonuc.csv (durum günlüğü), cikti/<sicil>-<muker>/ (ekran görüntüleri + inen PDF)
"""
import argparse, csv, re, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

URL = "https://eportal.ito.org.tr/faaliyet-belgesi-sorgulama-eimzali"
SURE = 25_000  # ms, her adım için bekleme


def tutar_sifir_mi(metin: str) -> bool:
    m = re.search(r"(\d[\d.]*,\d{2})", metin or "")
    return bool(m) and float(m.group(1).replace(".", "").replace(",", ".")) == 0.0


def tikla_metin(page, metin, exact=False):
    """Görünen yazıya göre düğme/bağlantı tıkla (büyük-küçük harf duyarsız)."""
    page.get_by_text(re.compile(metin if not exact else f"^{metin}$", re.I)).locator("visible=true").first.click(timeout=SURE)


def mukellef_isle(page, sicil, muker, a, klasor: Path):
    klasor.mkdir(parents=True, exist_ok=True)
    foto = lambda ad: page.screenshot(path=str(klasor / f"{ad}.png"), full_page=True)

    page.goto(URL, wait_until="domcontentloaded")
    page.get_by_label(re.compile("Ticaret Sicil No", re.I)).fill(str(sicil))
    page.get_by_label(re.compile("Muker No", re.I)).fill(str(muker))
    page.get_by_role("button", name=re.compile("^Sorgula$", re.I)).first.click()

    # Muker/şube listesi çıkarsa doğru satırdaki "Seç"e bas
    hedef = f"{sicil}-{muker}"
    page.wait_for_timeout(1500)
    satir = page.locator("tr", has_text=hedef)
    if satir.count():
        satir.first.get_by_role("button", name=re.compile("^Seç$", re.I)).click()
    page.get_by_text(re.compile(re.escape(hedef))).first.wait_for(timeout=SURE)
    foto("1-secildi")

    # Borç uyarısı çıksa da (örn. aidat) devam edilebiliyor; yalnız kaydet
    borc = page.get_by_text(re.compile("borcu bulunmaktadır", re.I)).count() > 0

    page.get_by_role("button", name=re.compile("İşleme Devam Et", re.I)).click(timeout=SURE)
    page.get_by_text(re.compile("Ödeme\\s*Listesi|Ödenecek Toplam Tutar", re.I)).first.wait_for(timeout=SURE)
    foto("2-odeme-listesi")

    toplam = page.locator("text=/Ödenecek Toplam Tutar/i").locator("xpath=ancestor::*[self::tr or self::div][1]").first.inner_text()
    if not tutar_sifir_mi(toplam):
        return "ATLANDI", f"Tutar sıfır değil, ödeme yapılmadı: {toplam.strip()!r}"

    page.get_by_role("button", name=re.compile("Ödemeyi Tamamla", re.I)).click()

    # İletişim bilgileri
    page.get_by_label(re.compile("Ad ve Soyad", re.I)).fill(a.ad)
    page.get_by_label(re.compile("Cep Telefonu", re.I)).fill(a.tel)
    yerel, alan = a.eposta.split("@", 1)
    ep = page.get_by_label(re.compile("E-posta Adresi", re.I)).first
    ep.fill(yerel)
    sel = page.locator("select").filter(has=page.locator("option", has_text="Diğer")).last
    try:
        sel.select_option(label=alan)               # alan adı listede varsa
    except Exception:
        sel.select_option(label="Diğer")
        page.get_by_placeholder(re.compile("alan|domain|\\.com", re.I)).or_(
            page.locator("input[type=text]").last).fill(alan)
    page.get_by_text(re.compile("Genel Kurallar ve Koşullar", re.I)).locator("xpath=preceding::input[@type='checkbox'][1]").check()
    foto("3-iletisim")

    toplam2 = page.locator("text=/Ödenecek Toplam Tutar/i").locator("xpath=ancestor::*[self::tr or self::div][1]").first.inner_text()
    if not tutar_sifir_mi(toplam2):
        return "ATLANDI", f"Ödeme ekranında tutar sıfır değil: {toplam2.strip()!r}"

    page.get_by_role("button", name=re.compile("İŞLEMİ TAMAMLA", re.I)).click()
    page.wait_for_load_state("networkidle", timeout=SURE)
    foto("4-sonuc")

    # Sonuç sayfasında PDF/indir bağlantısı varsa indir
    pdf = page.get_by_role("link", name=re.compile("indir|görüntüle|belge|pdf", re.I)).locator("visible=true")
    if pdf.count():
        try:
            with page.expect_download(timeout=20_000) as d:
                pdf.first.click()
            d.value.save_as(str(klasor / (d.value.suggested_filename or "faaliyet-belgesi.pdf")))
        except PWTimeout:
            pass
    return "TAMAM", ("borç uyarısı vardı; " if borc else "") + "belge e-postaya gönderilmiş olabilir, sonuç ekranı kaydedildi"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv"); p.add_argument("--ad", required=True); p.add_argument("--tel", required=True)
    p.add_argument("--eposta", required=True); p.add_argument("--limit", type=int, default=0)
    p.add_argument("--goster", action="store_true", help="tarayıcıyı göster, yavaşlat")
    p.add_argument("--cikti", default="cikti")
    a = p.parse_args()

    cikti = Path(a.cikti); cikti.mkdir(exist_ok=True)
    satirlar = list(csv.DictReader(open(a.csv, encoding="utf-8-sig")))
    if a.limit: satirlar = satirlar[: a.limit]
    log = cikti / "sonuc.csv"
    yeni = not log.exists()
    with sync_playwright() as pw, open(log, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if yeni: w.writerow(["sicil", "muker", "unvan", "durum", "not", "zaman"])
        tarayici = pw.chromium.launch(headless=not a.goster, slow_mo=300 if a.goster else 0)
        page = tarayici.new_context(accept_downloads=True, locale="tr-TR").new_page()
        page.set_default_timeout(SURE)
        for r in satirlar:
            sicil, muker = r["sicil"].strip(), r["muker"].strip()
            try:
                durum, nt = mukellef_isle(page, sicil, muker, a, cikti / f"{sicil}-{muker}")
            except Exception as e:
                durum, nt = "HATA", str(e).splitlines()[0][:200]
                try: page.screenshot(path=str(cikti / f"{sicil}-{muker}-hata.png"), full_page=True)
                except Exception: pass
            print(f"{sicil}-{muker} {r.get('unvan','')}: {durum} {nt}")
            w.writerow([sicil, muker, r.get("unvan", ""), durum, nt, time.strftime("%Y-%m-%d %H:%M:%S")]); f.flush()
            time.sleep(3)  # siteyi yormamak için
        tarayici.close()


if __name__ == "__main__":
    sys.exit(main())
