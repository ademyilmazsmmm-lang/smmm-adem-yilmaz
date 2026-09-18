#!/usr/bin/env python3
"""Luca portalindan tum firmalar icin e-fatura / e-arsiv belgelerini toplu ceker ve indirir."""

import argparse
import csv
import json
import re
import sys
import threading
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

KOK = Path(__file__).resolve().parent
AYAR_DOSYASI = KOK / "ayarlar.json"
ORNEK_AYAR = KOK / "ayarlar.ornek.json"

GIRIS_URL = "https://www.luca.com.tr"  # uygulama adresine dogrudan gidilince "LUCA HATA" veriyor
UYGULAMA_PARCASI = "/Luca/"
UST_MENU = "Akıllı Entegrasyon Noktası"
MODUL_ADAYLARI = ["İşletme Defteri", "Ser.Mes.Defteri", "Serbest Meslek Defteri",
                  "Genel Muhasebe", "Bilanço Defteri", "Muhasebe", "Defter"]

BELGE_TIPLERI = {
    "e-arsiv-alis": "e-Arşiv Alış Faturaları",
    "e-arsiv-satis": "e-Arşiv Satış Faturaları",
    "e-fatura-alis": "e-Fatura Alış Faturaları",
    "e-fatura-satis": "e-Fatura Satış Faturaları",
}

KAPAT_METINLERI = ["Bir daha gösterme"]  # sayfadaki "Tamam"/"Kapat" baska islevlere ait olabiliyor
DIYALOG_ONAY = ["Belgeleri Getir", "Sorgula", "Onayla", "Uygula"]
INDIRME_ONAY = ["Belgeleri İndir", "Dosyaları İndir", "Onayla"]
ISLEM_BITTI = "sona erdi"

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


MENU_KELIMELERI = ("ISLEMLERI", "ISLEMLER", "BEYANNAME", "RAPOR", "LISTESI", "HESAP PLANI",
                   "MAKBUZ", "DEFTER", "HIZLI ERISIM", "SORGULAMA", "FATURALARI")


def menu_listesi_mi(secenekler):
    isabet = sum(1 for s in secenekler if any(k in sadelestir(s) for k in MENU_KELIMELERI))
    return isabet >= 3


def firma_adaylari(page):
    adaylar = []
    for fr in cerceveler(page):
        try:
            secimler = fr.locator("select")
            for i in range(secimler.count()):
                sec = secimler.nth(i)
                if not sec.is_visible():
                    continue
                temiz = [s.strip() for s in sec.locator("option").all_inner_texts() if s.strip()]
                if len(temiz) < 5:
                    continue
                adaylar.append((fr, sec, temiz))
        except Exception:
            continue
    return adaylar


def secili_metin(sec):
    try:
        return sec.evaluate("el => el.selectedIndex >= 0 ? el.options[el.selectedIndex].text : ''") or ""
    except Exception:
        return ""


def firma_secici(page):
    """Firma listesi, secili degeri sayfa basliginda gecen liste (baslik ornegi: 'AKIN COBAN [ 2026 ]')."""
    adaylar = firma_adaylari(page)
    if not adaylar:
        raise LookupError("Firma listesi (select) bulunamadi")

    try:
        baslik = sadelestir(page.title())
    except Exception:
        baslik = ""
    if baslik:
        for aday in adaylar:
            secili = sadelestir(secili_metin(aday[1]))
            if len(secili) >= 3 and secili in baslik:
                return aday

    firma_gibi = [a for a in adaylar if not menu_listesi_mi(a[2])]
    if firma_gibi:
        return max(firma_gibi, key=lambda a: len(a[2]))
    raise LookupError("Firma listesi ayirt edilemedi")


def firma_sec(page, firma_adi):
    _, sec, _ = firma_secici(page)
    sec.select_option(label=firma_adi)
    page.wait_for_timeout(2500)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    varsa_tikla(page, KAPAT_METINLERI)


def gorunur_mu(page, metin, sure=1500):
    try:
        metinle_bul(page, metin, sure=sure)
        return True
    except LookupError:
        return False


def menu_ogesini_ac(page, metin, sure=4000, dogrula=None):
    """Eski Luca menuleri kimi yerde hover, kimi yerde tiklama ile aciliyor."""
    try:
        _, oge = metinle_bul(page, metin, sure=sure)
    except LookupError:
        return False
    for eylem in ("hover", "click"):
        try:
            getattr(oge, eylem)()
        except Exception:
            continue
        page.wait_for_timeout(700)
        if dogrula is None or dogrula():
            return True
    return bool(dogrula()) if dogrula else True


def menu_metinleri(page, sinir=40):
    bulunan = []
    for fr in cerceveler(page):
        try:
            ogeler = fr.locator("a, td, span")
            for i in range(min(ogeler.count(), 200)):
                oge = ogeler.nth(i)
                try:
                    if not oge.is_visible():
                        continue
                    metin = (oge.inner_text() or "").strip()
                except Exception:
                    continue
                if 3 <= len(metin) <= 40 and metin not in bulunan:
                    bulunan.append(metin)
                    if len(bulunan) >= sinir:
                        return bulunan
        except Exception:
            continue
    return bulunan


def menuye_git(page, belge_tipi):
    hedef = BELGE_TIPLERI[belge_tipi]
    ust_gorunur = lambda: gorunur_mu(page, UST_MENU, sure=1200)

    if not ust_gorunur():
        acildi = False
        for modul in MODUL_ADAYLARI:
            if menu_ogesini_ac(page, modul, sure=1200, dogrula=ust_gorunur):
                acildi = True
                break
        if not acildi:
            raise LookupError(
                f"'{UST_MENU}' menusu acilamadi. Sayfada gorunen menuler: {menu_metinleri(page)}"
            )

    menu_ogesini_ac(page, UST_MENU, sure=6000, dogrula=lambda: gorunur_mu(page, hedef, sure=1200))

    try:
        _, alt = metinle_bul(page, hedef, sure=8000)
    except LookupError:
        raise LookupError(f"'{hedef}' menu maddesi bulunamadi. Gorunen menuler: {menu_metinleri(page)}")
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


def islem_takibini_bekle(page, log, azami_saniye=900):
    """GIB sorgusu gun gun ilerliyor; 'Islem Takip' penceresi 'sona erdi' diyene kadar beklenir."""
    basla = time.time()
    pencere_goruldu = False
    while time.time() - basla < azami_saniye:
        if gorunur_mu(page, ISLEM_BITTI, sure=1000):
            yaz("    GİB sorgusu tamamlandi", log)
            varsa_tikla(page, ["Kapat"], sure=4000)
            page.wait_for_timeout(1500)
            return True
        if not pencere_goruldu:
            if gorunur_mu(page, "İşlem Takip", sure=1000):
                pencere_goruldu = True
                yaz("    GİB sorgusu suruyor, bekleniyor...", log)
            elif time.time() - basla > 45:
                return False  # islem penceresi hic acilmadi
        page.wait_for_timeout(3000)
    yaz("    UYARI: GİB sorgusu zaman asimina ugradi", log)
    varsa_tikla(page, ["Kapat"], sure=3000)
    return False


def gibden_getir(page, baslangic, bitis, log):
    _, dugme = metinle_bul(page, "GİB'den Getir")
    dugme.click()
    page.wait_for_timeout(2500)

    kutular = tarih_kutulari(page)
    if len(kutular) < 2:
        yaz(f"    UYARI: tarih kutulari bulunamadi ({len(kutular)} adet), Luca varsayilani kullanilacak", log)
    else:
        kutuya_yaz(kutular[0], baslangic)
        kutuya_yaz(kutular[1], bitis)
        try:
            yaz(f"    Tarih araligi girildi: {kutular[0].input_value()} - {kutular[1].input_value()}", log)
        except Exception:
            pass

    if not varsa_tikla(page, DIYALOG_ONAY, sure=5000):
        raise LookupError(f"'Belgeleri Getir' butonu bulunamadi. Gorunen ogeler: {menu_metinleri(page, 20)}")

    islem_takibini_bekle(page, log)

    varsa_tikla(page, ["Yenile"], sure=5000)  # sorgu sonrasi liste kendiliginden tazelenmiyor
    page.wait_for_timeout(3000)
    try:
        page.wait_for_load_state("networkidle", timeout=60000)
    except Exception:
        pass


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
        with page.expect_download(timeout=240000) as bilgi:
            dugme.click()
            page.wait_for_timeout(2500)
            varsa_tikla(page, INDIRME_ONAY, sure=2500)  # araya onay diyalogu girebiliyor
        dosya = bilgi.value
        ad = f"{on_ek}_{dosya.suggested_filename}"
        yol = hedef_klasor / ad
        dosya.save_as(str(yol))
        yaz(f"    indirildi: {ad}", log)
        return yol
    except Exception as e:
        yaz(f"    '{dugme_metni}' indirilemedi ({type(e).__name__}). Ekranda gorunenler: {menu_metinleri(page, 15)}", log)
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


_duraklama_islenen = set()


def duraklamalari_engelle(ctx, page):
    """Luca sayfalarindaki 'debugger' duraklamalari sekmeyi dondurdugu icin atlanir."""
    if page is None or page in _duraklama_islenen:
        return
    _duraklama_islenen.add(page)
    try:
        cdp = ctx.new_cdp_session(page)
    except Exception:
        return

    def devam_et(_=None):
        try:
            cdp.send("Debugger.resume")
        except Exception:
            pass

    for komut, parametre in (
        ("Debugger.enable", None),
        ("Debugger.setSkipAllPauses", {"skip": True}),
        ("Debugger.resume", None),  # sayfa zaten duraklamissa serbest birak
    ):
        try:
            cdp.send(komut, parametre) if parametre else cdp.send(komut)
        except Exception:
            continue
    try:
        cdp.on("Debugger.paused", devam_et)
    except Exception:
        pass


def kullanici_bekle(ctx, mesaj):
    """Duz input() Playwright olaylarini dondurur; beklerken sayfa olaylari islenmeye devam etmeli."""
    hazir = threading.Event()

    def oku():
        try:
            input(mesaj)
        finally:
            hazir.set()

    threading.Thread(target=oku, daemon=True).start()
    while not hazir.is_set():
        acik = [p for p in ctx.pages if not p.is_closed()]
        for p in acik:
            duraklamalari_engelle(ctx, p)
        if acik:
            try:
                acik[0].wait_for_timeout(250)
                continue
            except Exception:
                pass
        time.sleep(0.25)


def tarayici_ac(pw, profil, log):
    """Once bilgisayarda kurulu Chrome/Edge denenir; Playwright'in kendi tarayicisi son care."""
    hatalar = []
    for kanal, ad in (("chrome", "Google Chrome"), ("msedge", "Microsoft Edge"), (None, "Playwright Chromium")):
        secenekler = {"channel": kanal} if kanal else {}
        try:
            ctx = pw.chromium.launch_persistent_context(
                str(profil), headless=False, accept_downloads=True,
                args=["--start-maximized"],
                ignore_default_args=["--enable-automation"],
                chromium_sandbox=True, no_viewport=True, **secenekler
            )
            yaz(f"Tarayici: {ad}", log)
            ctx.on("page", lambda p: duraklamalari_engelle(ctx, p))
            for p in ctx.pages:
                duraklamalari_engelle(ctx, p)
            return ctx
        except Exception as e:
            hatalar.append(f"  {ad}: {str(e).splitlines()[0][:120]}")
    raise RuntimeError(
        "Hicbir tarayici acilamadi:\n" + "\n".join(hatalar)
        + "\n\nCozum: Google Chrome kurun (google.com/chrome) veya"
        " internet baglantisi duzelince tarayici-indir.bat dosyasini calistirin."
    )


def uygulama_sayfasi_bul(ctx):
    """Giris sonrasi Luca birkac pencere aciyor; firma listesini iceren sayfayi sec."""
    acik = [p for p in ctx.pages if not p.is_closed()]
    for p in acik:
        try:
            firma_secici(p)
            return p
        except Exception:
            continue
    for p in acik:
        try:
            if UYGULAMA_PARCASI in p.url and "giris" not in p.url.lower():
                return p
        except Exception:
            continue
    return None


def sayfalari_ozetle(ctx):
    satirlar = []
    for p in ctx.pages:
        if p.is_closed():
            continue
        try:
            secenekler = []
            for fr in p.frames:
                try:
                    kutular = fr.locator("select")
                    for i in range(min(kutular.count(), 6)):
                        adet = kutular.nth(i).locator("option").count()
                        if adet:
                            secenekler.append(str(adet))
                except Exception:
                    continue
            satirlar.append(
                f"  - {p.url}\n"
                f"      baslik: {p.title()[:60]} | frame: {len(p.frames)}"
                f" | liste secenek sayilari: {', '.join(secenekler) or 'yok'}"
            )
        except Exception as e:
            satirlar.append(f"  - (sayfa okunamadi: {type(e).__name__})")
    return "\n".join(satirlar) or "  (acik sayfa yok)"


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
        page.goto(GIRIS_URL)

        yaz("\n>>> Tarayicida Luca'ya giris yapin.", log)
        yaz(">>> Girisden sonra MUHASEBE EKRANINI acin (sag ustte firma listesi gorunen ekran).", log)
        kullanici_bekle(ctx, ">>> O ekran acikken ENTER'a basin: ")

        uygulama = None
        for deneme in range(1, 6):
            uygulama = uygulama_sayfasi_bul(ctx)
            if uygulama:
                break
            yaz(f"\nFirma listesi olan ekran bulunamadi ({deneme}/5). Acik pencereler:", log)
            yaz(sayfalari_ozetle(ctx), log)
            tani = calisma / "tani"
            tani.mkdir(parents=True, exist_ok=True)
            for sira, p in enumerate([x for x in ctx.pages if not x.is_closed()], 1):
                try:
                    p.screenshot(path=str(tani / f"deneme{deneme}-sayfa{sira}.png"))
                    (tani / f"deneme{deneme}-sayfa{sira}.html").write_text(p.content(), encoding="utf-8")
                except Exception:
                    pass
            yaz(f"Ekran goruntuleri kaydedildi: {tani}", log)
            yaz("\nLuca'da muhasebe modulunu acip firma listesinin gorundugu ekrana gelin.", log)
            kullanici_bekle(ctx, ">>> Hazir oldugunuzda ENTER'a basin (vazgecmek icin pencereyi kapatin): ")

        if uygulama is None:
            yaz("\nMuhasebe ekrani bulunamadi, islem durduruldu.", log)
            yaz("Yukaridaki pencere listesini gonderirseniz duzeltirim.", log)
            input(">>> Kapatmak icin ENTER: ")
            ctx.close()
            return

        page = uygulama
        duraklamalari_engelle(ctx, page)
        page.bring_to_front()
        page.on("dialog", lambda d: d.accept())
        uygulama_url = page.url
        yaz(f"Calisilan sayfa: {uygulama_url}", log)

        varsa_tikla(page, KAPAT_METINLERI)
        _, _, firmalar = firma_secici(page)
        tumu = list(firmalar)
        yaz(f"{len(firmalar)} firma bulundu", log)

        if args.listele:
            for f in firmalar:
                print(" -", f)
            dosya = calisma / "firmalar.txt"
            dosya.write_text("\n".join(firmalar), encoding="utf-8")
            yaz(f"\nListe dosyaya da yazildi: {dosya}", log)
            kullanici_bekle(ctx, ">>> Kapatmak icin ENTER: ")
            ctx.close()
            return

        if args.firma:
            aranan = [sadelestir(f) for f in args.firma if f.strip()]
            firmalar = [f for f in firmalar if any(a in sadelestir(f) for a in aranan)]
            if not firmalar:
                yaz(f"\n'{', '.join(args.firma)}' ile eslesen firma yok.", log)
                yaz("Listedeki ilk 30 kayit:", log)
                for ad in tumu[:30]:
                    yaz(f"  - {ad}", log)
                yaz("\nNot: Luca adlari kisaltarak gosterebiliyor, adin bas kismini yazin.", log)
                kullanici_bekle(ctx, ">>> Kapatmak icin ENTER: ")
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
                try:
                    page.goto(uygulama_url)
                    page.wait_for_timeout(2000)
                except Exception:
                    yaz("    Sayfa geri yuklenemedi, oturum dusmus olabilir", log)

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
