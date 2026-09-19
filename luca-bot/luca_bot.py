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


import rapor  # gunluk toplu rapor (rapor.xlsx / rapor.csv)

KOK = Path(__file__).resolve().parent
AYAR_DOSYASI = KOK / "ayarlar.json"
ORNEK_AYAR = KOK / "ayarlar.ornek.json"

GIRIS_URL = "https://www.luca.com.tr"  # uygulama adresine dogrudan gidilince "LUCA HATA" veriyor
UYGULAMA_PARCASI = "/Luca/"
UST_MENU = "Akıllı Entegrasyon Noktası"
MODUL_ADAYLARI = ["İşletme Defteri", "Ser.Mes.Defteri", "Serbest Meslek Defteri",
                  "Basit Usül", "Basit Usul", "Genel Muhasebe", "Bilanço Defteri",
                  "Muhasebe", "Defter"]

BELGE_TIPLERI = {
    "e-arsiv-alis": "e-Arşiv Alış Faturaları",
    "e-arsiv-satis": "e-Arşiv Satış Faturaları",
    "e-fatura-alis": "e-Fatura Alış Faturaları",
    "e-fatura-satis": "e-Fatura Satış Faturaları",
    # Akilli Entegrasyon Noktasi altinda degil, modul menusunun kendisinde:
    "e-arsiv-interaktif": "E-Arşiv Faturaları Sorgulama",
}

# menusu iki kademeli olan (Akilli Entegrasyon Noktasi araciligi olmayan) ekranlar
IKI_KADEMELI = {"e-arsiv-interaktif"}

# Interaktif Vergi Dairesi ekrani
INTERAKTIF_SORGU = "İnteraktif V.D'sinden E-Arşiv Faturalarını Sorgula"
INTERAKTIF_CAPASI = "Luca Proxy ile Sorgula"  # secenek penceresinin kendi yazisi
INTERAKTIF_SERVIS = "GİB Servis ile Sorgula"
INTERAKTIF_LISTELE = "Mevcut E-Arşiv Faturalarını Listele"
INTERAKTIF_TEKRAR = 2  # Luca ilk sorguda hep getirmiyor, iki kez calistiriliyor

KAPAT_METINLERI = ["Bir daha gösterme"]  # sayfadaki "Tamam"/"Kapat" baska islevlere ait olabiliyor
DIYALOG_ONAY = ["Belgeleri Getir", "Sorgula", "Onayla", "Uygula"]
INDIRME_ONAY = ["Seçilenleri İndir", "Belgeleri İndir", "Dosyaları İndir", "İndir", "Onayla"]
ISLEM_BITTI = "sona erdi"
INDIRILEMEDI = "indirilemedi"
ISLEM_ISARETLERI = ["İşlem Takip", "sorgulandı", "belge kaydı bulundu", "Otomatik aşağı kaydır"]

KISAYOLLAR = {  # butonlarin kendi ipuclarinda yazan kisayollar (tiklama engellenirse kullanilir)
    "GİB'den Getir": "Alt+g",
    "Seçilenleri İndir": "Alt+z",
    "Yenile": "Alt+l",
    "Excel": "Alt+e",
    "Belge Seç": "Alt+b",
}

AYAR = {"azami_saniye": 900, "durgunluk_saniye": 180, "indirme_saniye": 30, "iptal_itiraz": True}  # ayarlar.json ile degistirilebilir

TARIH_BICIMI = "%d/%m/%Y"
AZAMI_GUN = 30  # GIB sorgusu tek seferde en fazla 30 gun kabul ediyor

# GIB'den iptal/itiraz sorgulama (fatura listesi indikten sonra calisir)
IPTAL_DUGME_ADAYLARI = ["GİB'den İptal/İtiraz Sorgula", "GİB'den iptal/itiraz Sorgula",
                        "iptal/itiraz Sorgula", "İptal/İtiraz Sorgula"]
IPTAL_ONAY = ["İptal/İtiraz Sorgula", "İptal/itiraz Sorgula", "İptal/İtiraz sorgula"]
IPTAL_CAPASI = "Raporlanma Tarihi"  # diyalogun kendi aciklama yazisi
IPTAL_DESENI = re.compile(r"IPTAL|ITIRAZ")
TEVKIFAT_DESENI = re.compile(r"TEVKIFAT")


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


def karsilastir(metin):
    """Arama icin: Turkce/buyuk-kucuk farki ve bosluklar yok sayilir ('yakups' -> 'YAKUP SÖĞÜ')."""
    return sadelestir(metin).replace(" ", "")


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
    """Once butonun kendisi, sonra tam metin, en son kapsayici aranir.

    'Tamam' ve 'Vazgec' ayni kapsayicida oldugu icin kapsayiciya tiklamak
    yanlislikla Vazgec'e denk gelip secimi iptal ediyordu.
    """
    pay = max(1500, sure // 3)
    son_hata = None
    for kurucu, kurucu_sure in (
        (lambda f: f.get_by_role("button", name=metin, exact=True), pay),
        (lambda f: f.get_by_text(metin, exact=True), pay),
        (lambda f: f.get_by_text(metin, exact=False), sure),
    ):
        try:
            return bul(page, kurucu, sure=kurucu_sure)
        except LookupError as e:
            son_hata = e
    raise son_hata


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


def acik_pencere(page):
    """Luca diyaloglari kapanmazsa arkadaki butonlar tiklanamiyor (pointer events engelleniyor)."""
    for fr in cerceveler(page):
        try:
            loc = fr.locator(".luca-open-window")
            if loc.count() and loc.first.is_visible():
                return fr, loc.first
        except Exception:
            continue
    return None, None


def diyalogda_tikla(page, metinler, sure=4000):
    _, pencere = indirme_diyalogu(page)
    return pencerede_tikla(page, pencere, metinler, sure)


DIYALOG_CAPASI = "Tüm faturaları seçmek için"
FATURA_YOK_CAPASI = "fatura bulunamadı"


def metinli_diyalog(page, capa):
    """Diyalogu sinif adina degil, icindeki yaziya gore bulur."""
    for fr in cerceveler(page):
        for secici in ("div", "table", "form"):
            try:
                loc = fr.locator(secici).filter(has_text=capa)
                if loc.count() and loc.last.is_visible():
                    return fr, loc.last
            except Exception:
                continue
    return None, None


def pencerede_tikla(page, pencere, metinler, sure=4000):
    """Butona pencerenin icinden basar (yan yana duran Tamam/Iptal karismasin diye)."""
    if pencere is None:
        return None
    for metin in metinler:
        for kurucu in (lambda: pencere.get_by_role("button", name=metin, exact=True),
                       lambda: pencere.get_by_text(metin, exact=True),
                       lambda: pencere.get_by_text(metin, exact=False)):
            try:
                loc = kurucu()
                if loc.count() and loc.last.is_visible():
                    loc.last.click(timeout=sure)
                    page.wait_for_timeout(600)
                    return metin
            except Exception:
                continue
    return None


def fatura_yok_penceresini_kapat(page):
    """'Her hangi bir fatura bulunamadi' penceresi Tamam beklerken akisi kilitliyor."""
    _, pencere = metinli_diyalog(page, FATURA_YOK_CAPASI)
    if pencere is None:
        return False
    if not pencerede_tikla(page, pencere, ["Tamam"]):
        varsa_tikla(page, ["Tamam"], sure=2000)
    page.wait_for_timeout(500)
    return True


def indirme_diyalogu(page):
    fr, pencere = metinli_diyalog(page, DIYALOG_CAPASI)
    if pencere is not None:
        return fr, pencere
    _, pencere = acik_pencere(page)
    return (None, pencere) if pencere is not None else (None, None)


def diyalogda_tumunu_sec(page):
    """Indirme penceresindeki 'Tum faturalari secmek icin buraya' baglantisina tiklar.

    Pencerede iki 'buraya' var; ilki tum faturalar, ikincisi yalnizca
    onaylanmis faturalar icin.
    """
    _, pencere = indirme_diyalogu(page)
    if pencere is None:
        return False
    for kurucu in (
        lambda: pencere.get_by_text(DIYALOG_CAPASI, exact=False).first.get_by_text("buraya", exact=False),
        lambda: pencere.get_by_role("link", name="buraya", exact=True),
        lambda: pencere.get_by_text("buraya", exact=True),
        lambda: pencere.get_by_text("buraya", exact=False),
    ):
        try:
            loc = kurucu()
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=4000)
                page.wait_for_timeout(1000)
                return True
        except Exception:
            continue
    return False


def acik_pencereleri_kapat(page, log=None):
    for deneme in range(4):
        fr, pencere = acik_pencere(page)
        if pencere is None:
            return True
        if deneme == 0 and log:
            yaz("    Acik Luca penceresi kapatiliyor", log)
        if varsa_tikla(page, ["Kapat"], sure=1500):
            page.wait_for_timeout(600)
            continue
        kapandi = False
        for secici in ("[class*='close']", "[class*='kapat']", "[onclick*='close']", "[onclick*='Kapat']"):
            try:
                dugme = fr.locator(f".luca-open-window {secici}").first
                if dugme.count() and dugme.is_visible():
                    dugme.click(timeout=3000)
                    kapandi = True
                    break
            except Exception:
                continue
        if not kapandi:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
        page.wait_for_timeout(700)
    return acik_pencere(page)[1] is None


def firma_dogrula(page, firma_adi, sure=8000):
    """Secim gerceklesti mi: sekme basligi secili firmanin adini tasiyor (orn. 'DENTAL [ 2026 ]')."""
    hedef = sadelestir(firma_adi)
    bitis = time.time() + sure / 1000
    while time.time() < bitis:
        try:
            if hedef and hedef in sadelestir(page.title()):
                return True
        except Exception:
            pass
        page.wait_for_timeout(500)
    return False


DONEM_DESENI = re.compile(r"(\d{2}[./]\d{2}[./]\d{4})\s*-\s*(\d{2}[./]\d{2}[./]\d{4})")


def calisma_donemi(page):
    """Firma adinin altindaki donem kutusu (orn. '08/04/2022 - 31/12/2022')."""
    for fr in cerceveler(page):
        try:
            kutular = fr.locator("select")
            for i in range(min(kutular.count(), 12)):
                eslesme = DONEM_DESENI.search(secili_metin(kutular.nth(i)) or "")
                if eslesme:
                    return (tarih_cozumle(eslesme.group(1).replace(".", "/")),
                            tarih_cozumle(eslesme.group(2).replace(".", "/")))
        except Exception:
            continue
    return None, None


def firma_sec(page, firma_adi, log=None):
    """Firmanin bulundugu listeyi adiyla secer; secim 'Tamam' ile onaylanip dogrulanir."""
    # giris sonrasi acik kalan bilgi penceresi Tamam'a basilmasini engelliyordu
    varsa_tikla(page, KAPAT_METINLERI, sure=1500)
    acik_pencereleri_kapat(page)

    hedef = None
    for deneme in range(3):  # onceki firmadan sonra liste gec yuklenebiliyor
        for _, sec, secenekler in firma_adaylari(page):
            if firma_adi in secenekler:
                hedef = sec
                break
        if hedef is not None:
            break
        acik_pencereleri_kapat(page)
        page.wait_for_timeout(3000)
    if hedef is None:
        raise LookupError(f"'{firma_adi}' acik listelerin hicbirinde bulunamadi")

    for _ in range(3):
        try:
            hedef.select_option(label=firma_adi, timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(600)
        varsa_tikla(page, ["Tamam"], sure=3000)
        page.wait_for_timeout(1500)
        if firma_dogrula(page, firma_adi):
            break
        varsa_tikla(page, KAPAT_METINLERI, sure=1200)
        acik_pencereleri_kapat(page)
    else:
        # dogrulanmadan devam edilirse baska firmanin faturalari cekilir; bu firmayi atla
        raise LookupError(f"'{firma_adi}' secimi onaylanamadi (Tamam gecmedi), firma atlandi")

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass


def gorunur_mu(page, metin, sure=1500):
    """Sadece varlik kontrolu; tiklama icin kullanilmadigindan tek (hizli) arama yeter."""
    try:
        bul(page, lambda f: f.get_by_text(metin, exact=False), sure=sure)
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


def dugmeye_bas(page, metin, sure=8000):
    """Once butona tiklar; tiklama engellenirse butonun kendi klavye kisayolunu dener."""
    try:
        _, dugme = metinle_bul(page, metin, sure=sure)
        dugme.click(timeout=8000)
        return True
    except Exception:
        pass
    kisayol = KISAYOLLAR.get(metin)
    if kisayol:
        try:
            page.keyboard.press(kisayol)
            page.wait_for_timeout(600)
            return True
        except Exception:
            pass
    return False


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


def modul_menusunden_git(page, hedef):
    """Modul menusu (orn. Isletme Defteri) -> madde. Ara menu yok."""
    hedef_gorunur = lambda: gorunur_mu(page, hedef, sure=1200)
    for deneme in range(3):
        if not hedef_gorunur():
            for modul in MODUL_ADAYLARI:
                if menu_ogesini_ac(page, modul, sure=1200, dogrula=hedef_gorunur):
                    break
        try:
            _, madde = metinle_bul(page, hedef, sure=4000)
        except LookupError:
            page.wait_for_timeout(1000)
            continue
        madde.click()
        page.wait_for_timeout(2500)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        return
    raise LookupError(f"'{hedef}' menu maddesi bulunamadi. Gorunen menuler: {menu_metinleri(page)}")


def menuye_git(page, belge_tipi):
    hedef = BELGE_TIPLERI[belge_tipi]
    if belge_tipi in IKI_KADEMELI:
        return modul_menusunden_git(page, hedef)
    ust_gorunur = lambda: gorunur_mu(page, UST_MENU, sure=1200)
    hedef_gorunur = lambda: gorunur_mu(page, hedef, sure=1200)

    alt = None
    for deneme in range(3):  # menu kimi zaman hover'da acilip hemen kapaniyor
        if not ust_gorunur():
            for modul in MODUL_ADAYLARI:
                if menu_ogesini_ac(page, modul, sure=1200, dogrula=ust_gorunur):
                    break
            else:
                if deneme == 2:
                    raise LookupError(
                        f"'{UST_MENU}' menusu acilamadi. Sayfada gorunen menuler: {menu_metinleri(page)}"
                    )
                page.wait_for_timeout(1000)
                continue

        menu_ogesini_ac(page, UST_MENU, sure=6000, dogrula=hedef_gorunur)
        try:
            _, alt = metinle_bul(page, hedef, sure=4000)
            break
        except LookupError:
            page.wait_for_timeout(1000)

    if alt is None:
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


def metin_iceren_sayfa(page, metin, sure=800):
    """Islem Takip penceresi ayri bir pencerede acilabildigi icin tum sayfalara bakilir."""
    sayfalar = [page]
    try:
        sayfalar += [p for p in page.context.pages if p is not page and not p.is_closed()]
    except Exception:
        pass
    for p in sayfalar:
        try:
            metinle_bul(p, metin, sure=sure)
            return p
        except LookupError:
            continue
    return None


def islem_gunlugu(page):
    """Islem Takip penceresinin metni; pencere kapaliysa bos doner.

    Tarih diyalogu da .luca-open-window oldugu icin yalnizca islem gunlugu
    isaretlerini tasiyan pencere kabul edilir.
    """
    isaretler = [i.lower() for i in ISLEM_ISARETLERI] + [ISLEM_BITTI]
    sayfalar = [page]
    try:
        sayfalar += [p for p in page.context.pages if p is not page and not p.is_closed()]
    except Exception:
        pass
    for p in sayfalar:
        for fr in cerceveler(p):
            try:
                loc = fr.locator(".luca-open-window")
                for i in range(loc.count()):
                    pencere = loc.nth(i)
                    if not pencere.is_visible():
                        continue
                    metin = pencere.inner_text() or ""
                    if any(isaret in metin.lower() for isaret in isaretler):
                        return metin
            except Exception:
                continue
    return ""


def indirilemeyen_sayisi(sayfa):
    """Islem gunlugundeki \"url'li fatura indirilemedi\" satirlarini sayar."""
    gunluk = islem_gunlugu(sayfa)
    if gunluk:
        return gunluk.lower().count(INDIRILEMEDI)
    for fr in cerceveler(sayfa):
        try:
            if fr.get_by_text(ISLEM_BITTI, exact=False).count() == 0:
                continue
            return fr.locator("body").inner_text().lower().count(INDIRILEMEDI)
        except Exception:
            continue
    return 0


def islem_takibini_bekle(page, log, azami_saniye=900, durgunluk_saniye=180,
                         pencere_bekleme=25, en_az_saniye=3):
    """Sorgu bitene kadar bekler; indirilemeyen fatura sayisini dondurur (-1: tamamlanmadi).

    Bitis uc sekilde anlasilir: gunlukte "sona erdi" yazmasi, pencerenin
    kendiliginden kapanmasi (hizli biten sorgularda boyle oluyor) veya
    yazinin durgunluk_saniye boyunca hic degismemesi.
    """
    basla = time.time()
    pencere_goruldu = False
    son_gunluk = ""
    son_degisim = time.time()
    son_bildirim = 0

    while True:
        gecen = time.time() - basla

        if gecen >= en_az_saniye and fatura_yok_penceresini_kapat(page):
            yaz(f"    Luca: fatura bulunamadi ({int(gecen)} sn)", log)
            return 0

        gunluk = islem_gunlugu(page)

        if gunluk:
            if not pencere_goruldu:
                pencere_goruldu = True
                yaz("    İşlem Takip penceresi acildi, sorgu suruyor...", log)
            if gunluk != son_gunluk:
                son_gunluk = gunluk
                son_degisim = time.time()

            # onceki sorgunun "sona erdi" yazisi ekranda kalmis olabilir
            if ISLEM_BITTI in gunluk.lower() and gecen >= en_az_saniye:
                basarisiz = gunluk.lower().count(INDIRILEMEDI)
                yaz(f"    GİB sorgusu tamamlandi ({int(gecen)} sn)"
                    + (f", {basarisiz} fatura indirilemedi" if basarisiz else ""), log)
                varsa_tikla(page, ["Kapat"], sure=4000)
                page.wait_for_timeout(1000)
                return basarisiz

            if time.time() - son_degisim > durgunluk_saniye:
                sure_metni = (f"{int(durgunluk_saniye // 60)} dk" if durgunluk_saniye >= 60
                              else f"{int(durgunluk_saniye)} sn")
                yaz(f"    Sorgu {sure_metni} boyunca ilerlemedi, takildi sayiliyor", log)
                varsa_tikla(page, ["Kapat"], sure=3000)
                acik_pencereleri_kapat(page)
                fatura_yok_penceresini_kapat(page)
                return son_gunluk.lower().count(INDIRILEMEDI)

        elif pencere_goruldu:
            # pencere kendiliginden kapandi: sorgu bitmis demektir
            basarisiz = son_gunluk.lower().count(INDIRILEMEDI)
            yaz(f"    GİB sorgusu tamamlandi ({int(gecen)} sn, pencere kapandi)"
                + (f", {basarisiz} fatura indirilemedi" if basarisiz else ""), log)
            return basarisiz

        elif gecen > pencere_bekleme:
            yaz(f"    İşlem Takip penceresi {int(gecen)} sn icinde gorunmedi, devam ediliyor", log)
            return 0

        if gecen > azami_saniye:
            yaz(f"    UYARI: GİB sorgusu {int(gecen)} sn sonra zaman asimina ugradi", log)
            varsa_tikla(page, ["Kapat"], sure=3000)
            return -1

        if gecen - son_bildirim >= 15:
            son_bildirim = gecen
            yaz(f"    ... bekleniyor ({int(gecen)} sn)", log)
        page.wait_for_timeout(1500)


def gibden_getir(page, baslangic, bitis, log):
    yaz(f"    GİB'den Getir aciliyor ({baslangic} - {bitis})", log)
    acik_pencereleri_kapat(page, log)  # onceki sorgudan kalan pencere tiklamayi engelliyor
    fatura_yok_penceresini_kapat(page)  # onceki sorgunun bildirimi yeni sorguya karismasin
    if not dugmeye_bas(page, "GİB'den Getir"):
        raise LookupError("'GİB'den Getir' butonuna basilamadi")
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

    tiklanan = varsa_tikla(page, DIYALOG_ONAY, sure=5000)
    if not tiklanan:
        raise LookupError(f"'Belgeleri Getir' butonu bulunamadi. Gorunen ogeler: {menu_metinleri(page, 20)}")
    yaz(f"    '{tiklanan}' tiklandi, sorgu basladi", log)

    basarisiz = islem_takibini_bekle(page, log, azami_saniye=AYAR["azami_saniye"],
                                     durgunluk_saniye=AYAR["durgunluk_saniye"])
    acik_pencereleri_kapat(page, log)

    yaz("    Liste yenileniyor", log)
    dugmeye_bas(page, "Yenile", sure=5000)  # sorgu sonrasi liste kendiliginden tazelenmiyor
    page.wait_for_timeout(3000)
    try:
        page.wait_for_load_state("networkidle", timeout=60000)
    except Exception:
        pass
    return basarisiz


TARIH_DESENI = re.compile(r"\d{2}[./]\d{2}[./]\d{4}")


def cerceveden_satirlar(fr):
    try:
        satirlar = fr.locator("tr")
        adet = min(satirlar.count(), 500)
    except Exception:
        return []
    veriler = []
    for i in range(adet):
        try:
            hucreler = [h.strip() for h in satirlar.nth(i).locator("td").all_inner_texts() if h.strip()]
        except Exception:
            continue
        if len(hucreler) >= 4 and any(TARIH_DESENI.search(h) for h in hucreler):
            veriler.append(hucreler)
    return veriler


def kutulardan_satirlar(kutular, sayi):
    """Satirlari isaret kutularindan cikarir.

    Fatura izgarasi her zaman <tr>/<td> degil; kutunun en yakin satir
    atasinin metni alinirsa yapidan bagimsiz calisir ve satir sayisi
    isaretlenen kayit sayisiyla dogal olarak ayni olur.
    """
    if kutular is None:
        return []
    satirlar = []
    for i in range(sayi):
        try:
            metin = kutular.nth(i).evaluate(
                "el => { const s = el.closest('tr, [role=row], li')"
                " || (el.parentElement && el.parentElement.parentElement);"
                " return s ? s.innerText : ''; }"
            ) or ""
        except Exception:
            continue
        hucreler = [h.strip() for h in re.split(r"[\t\n]+", metin) if h.strip()]
        if len(hucreler) >= 3 and any(TARIH_DESENI.search(h) for h in hucreler):
            satirlar.append(hucreler)
    return satirlar


def tabloyu_oku(page, tercih=None):
    """Fatura tablosu, isaret kutulariyla ayni cerceveden okunur.

    Tum cerceveler taranirsa baska ekranlardan kalan tablolar da fatura
    sanilip olmayan satirlar listeleniyordu.
    """
    if tercih is not None:
        # Bu cercevede satir yoksa liste gercekten bostur; genel taramaya
        # dusulurse baska ekranlarda kalan tablolar fatura sanilıyor.
        return tercih, cerceveden_satirlar(tercih)

    en_iyi = (None, [])
    for fr in cerceveler(page):
        veriler = cerceveden_satirlar(fr)
        if len(veriler) > len(en_iyi[1]):
            en_iyi = (fr, veriler)
    return en_iyi


SECIM_SECICILERI = ("input[type=checkbox]", "[role=checkbox]",
                    "img[src*='check']", "img[src*='tick']", "[class*='checkbox']")


def secim_kutulari(page):
    """En cok isaret kutusu olan cerceveyi secer.

    Baslik ve veri satirlari ayri cercevelerde oldugu icin ilk bulunan
    alinirsa yalnizca baslik kutusu (tek kayit) isaretleniyordu.
    """
    en_iyi = (None, 0, None)
    for fr in cerceveler(page):
        for secici in SECIM_SECICILERI:
            try:
                loc = fr.locator(secici)
                adet = loc.count()
                if adet > en_iyi[1] and loc.first.is_visible():
                    en_iyi = (loc, adet, fr)
            except Exception:
                continue
    return en_iyi


def isaretli_sayisi(kutular, sayi):
    if kutular is None:
        return 0
    try:
        return sum(1 for i in range(sayi) if kutular.nth(i).is_checked())
    except Exception:
        return 0


def veri_satir_indisleri(fr):
    try:
        satirlar = fr.locator("tr")
        adet = min(satirlar.count(), 500)
    except Exception:
        return None, []
    indisler = []
    for i in range(adet):
        try:
            hucreler = [h.strip() for h in satirlar.nth(i).locator("td").all_inner_texts() if h.strip()]
        except Exception:
            continue
        if len(hucreler) >= 4 and any(TARIH_DESENI.search(h) for h in hucreler):
            indisler.append(i)
    return satirlar, indisler


def hepsini_sec(page, fr, satir_sayisi=0):
    kutular, sayi, _ = secim_kutulari(page)

    if sayi:
        try:  # baslik satirindaki kutu genelde hepsini isaretler
            kutular.first.check(timeout=5000)
            page.wait_for_timeout(800)
            isaretli = isaretli_sayisi(kutular, sayi)
            if isaretli > 1:
                return isaretli
        except Exception:
            pass
        secilen = 0
        for i in range(sayi):
            try:
                kutu = kutular.nth(i)
                if kutu.is_visible() and not kutu.is_checked():
                    kutu.check(timeout=2000)
                    secilen += 1
            except Exception:
                continue
        if secilen:
            page.wait_for_timeout(500)
            return secilen

    # Luca'nin kendi ipucu: tabloda bosluk tusu satir seciyor
    satirlar, indisler = veri_satir_indisleri(fr)
    if satirlar is not None and indisler:
        try:
            satirlar.nth(indisler[0]).click(timeout=5000)
            page.wait_for_timeout(400)
            for _ in indisler:
                page.keyboard.press("Space")
                page.wait_for_timeout(150)
                page.keyboard.press("ArrowDown")
                page.wait_for_timeout(150)
            return isaretli_sayisi(kutular, sayi) or len(indisler)
        except Exception:
            pass

    if dugmeye_bas(page, "Belge Seç", sure=3000):  # Alt+B
        page.wait_for_timeout(800)
        return isaretli_sayisi(kutular, sayi) or satir_sayisi
    return 0


def uyari_metni(page):
    """Luca uyarisi (orn. 'Lutfen indirilecek faturalari seciniz') varsa metnini dondurur."""
    for fr in cerceveler(page):
        try:
            loc = fr.get_by_text("Lütfen", exact=False)
            if loc.count() and loc.first.is_visible():
                return " ".join((loc.first.inner_text() or "").split())[:90]
        except Exception:
            continue
    return None


def indir(page, dugme_metni, hedef_klasor, on_ek, log, azami_saniye=30):
    """Indirme akisi: arac cubugu butonu -> pencerede 'tum faturalar' -> pencerede indir.

    expect_download yerine olay dinleyip beklenir; boylece Luca "faturalari
    seciniz" uyarisi verdiginde bos yere zaman asimi beklenmez.
    """
    indirilenler = []
    dinleyici = lambda d: indirilenler.append(d)
    page.on("download", dinleyici)
    try:
        if not dugmeye_bas(page, dugme_metni, sure=8000):
            yaz(f"    '{dugme_metni}' butonuna basilamadi, atlandi", log)
            return None
        page.wait_for_timeout(2000)

        _, pencere = indirme_diyalogu(page)
        diyalog_var = pencere is not None
        onay = None
        if diyalog_var:
            if diyalogda_tumunu_sec(page):
                yaz("    Onay penceresinde 'tum faturalar' secildi", log)
            onay = diyalogda_tikla(page, INDIRME_ONAY)
            if onay:
                yaz(f"    Onay penceresinde '{onay}' tiklandi", log)
            else:
                yaz("    UYARI: onay penceresi tiklanamadi", log)

        # onay penceresi acilip tiklanamadiysa dosya gelmeyecek; Excel gibi
        # pencere acmayan butonlarda ise normal sure beklenir
        sure = 5 if (diyalog_var and not onay) else azami_saniye
        uyari = None
        bitis = time.time() + sure
        while time.time() < bitis and not indirilenler:
            if fatura_yok_penceresini_kapat(page):
                uyari = "Luca: fatura bulunamadi"
                break
            uyari = uyari_metni(page)
            if uyari:
                break
            page.wait_for_timeout(500)

        if indirilenler:
            dosya = indirilenler[0]
            ad = f"{on_ek}_{dosya.suggested_filename}"
            yol = hedef_klasor / ad
            dosya.save_as(str(yol))
            yaz(f"    indirildi: {ad}", log)
            return yol

        if uyari:
            yaz(f"    Luca uyarisi: {uyari}", log)
        else:
            yaz(f"    '{dugme_metni}' icin {int(sure)} sn icinde dosya gelmedi", log)
        return None
    except Exception as e:
        yaz(f"    '{dugme_metni}' indirilemedi ({type(e).__name__})", log)
        return None
    finally:
        try:
            page.remove_listener("download", dinleyici)
        except Exception:
            pass
        acik_pencereleri_kapat(page)  # pencere acik kalirsa sonraki adimlar kilitleniyor


def radyo_sec(page, pencere, metin):
    """Secenek penceresindeki radyo dugmesini yazisina gore isaretler."""
    hedef = karsilastir(metin)
    kapsam = pencere if pencere is not None else page
    try:
        radyolar = kapsam.locator("input[type=radio]")
        for i in range(min(radyolar.count(), 10)):
            r = radyolar.nth(i)
            try:
                cevre = r.evaluate(
                    "el => { const s = el.closest('tr, li, label, div')"
                    " || el.parentElement; return s ? s.innerText : ''; }") or ""
            except Exception:
                cevre = ""
            if hedef in karsilastir(cevre):
                try:
                    r.check(timeout=4000)
                except Exception:
                    r.click(timeout=4000)
                page.wait_for_timeout(400)
                return True
    except Exception:
        pass
    # radyo bulunamadiysa yazisina tiklamak da secimi yapar
    return bool(pencerede_tikla(page, pencere, [metin], sure=3000))


def interaktif_sorgula(page, araliklar, log):
    """Interaktif Vergi Dairesi ekraninda e-arsiv faturalarini GIB servisinden ceker.

    Akis: tarih araligi -> "İnteraktif V.D'sinden E-Arşiv Faturalarını Sorgula"
    -> acilan pencerede "GİB Servis ile Sorgula" -> ayni isimli onay butonu.
    Luca ilk sorguda listeyi her zaman doldurmadigi icin iki kez calistirilir.
    """
    calisan = 0
    for bas, bit in araliklar:
        for tur in range(1, INTERAKTIF_TEKRAR + 1):
            acik_pencereleri_kapat(page, log)
            fatura_yok_penceresini_kapat(page)

            kutular = tarih_kutulari(page)
            if len(kutular) >= 2:
                kutuya_yaz(kutular[0], bas)
                kutuya_yaz(kutular[1], bit)
            else:
                yaz("    UYARI: tarih kutulari bulunamadi, Luca varsayilani kullanilacak", log)
            yaz(f"    Interaktif V.D. sorgusu ({bas} - {bit}) {tur}/{INTERAKTIF_TEKRAR}", log)

            if not dugmeye_bas(page, INTERAKTIF_SORGU, sure=8000):
                yaz(f"    '{INTERAKTIF_SORGU}' butonuna basilamadi", log)
                return calisan
            page.wait_for_timeout(2000)

            _, pencere = metinli_diyalog(page, INTERAKTIF_CAPASI)
            if pencere is None:
                # pencere yoksa onay butonu da yok; arac cubugu butonuna tekrar
                # basmamak icin burada durulur
                yaz("    UYARI: 'GİB Servis ile Sorgula' penceresi acilmadi", log)
                return calisan
            if radyo_sec(page, pencere, INTERAKTIF_SERVIS):
                yaz(f"    '{INTERAKTIF_SERVIS}' secildi", log)
            else:
                yaz(f"    UYARI: '{INTERAKTIF_SERVIS}' secenegi isaretlenemedi", log)
            if not pencerede_tikla(page, pencere, [INTERAKTIF_SORGU], sure=5000):
                yaz("    UYARI: pencerede sorgu butonu tiklanamadi", log)
                acik_pencereleri_kapat(page, log)
                return calisan

            islem_takibini_bekle(page, log, azami_saniye=AYAR["azami_saniye"],
                                 durgunluk_saniye=AYAR["durgunluk_saniye"])
            acik_pencereleri_kapat(page, log)
            calisan += 1
            page.wait_for_timeout(1500)
    return calisan


def iptal_itiraz_sorgula(page, araliklar, log):
    """Listedeki faturalar icin GIB'den iptal/itiraz durumunu sorgular.

    Luca akisi: faturalar isaretli iken arac cubugundan "GİB'den İptal/İtiraz
    Sorgula" -> acilan pencerede tarih araligi -> "İptal/İtiraz Sorgula".
    Buradaki tarih, faturanin GIB'e raporlanma tarihidir.
    """
    calisan = 0
    for bas, bit in araliklar:
        acik_pencereleri_kapat(page, log)
        fatura_yok_penceresini_kapat(page)
        if not varsa_tikla(page, IPTAL_DUGME_ADAYLARI, sure=4000):
            yaz("    'GİB'den İptal/İtiraz Sorgula' butonu bulunamadi, atlandi", log)
            return calisan
        page.wait_for_timeout(2000)

        _, pencere = metinli_diyalog(page, IPTAL_CAPASI)
        kutular = tarih_kutulari(page)
        if len(kutular) >= 2:
            kutuya_yaz(kutular[0], bas)
            kutuya_yaz(kutular[1], bit)
            yaz(f"    Iptal/itiraz sorgusu ({bas} - {bit})", log)
        else:
            yaz("    UYARI: iptal/itiraz tarih kutulari bulunamadi, Luca varsayilani kullanilacak", log)

        onay = pencerede_tikla(page, pencere, IPTAL_ONAY) if pencere is not None else None
        if not onay:
            # pencere taninmadiysa tam metinle ara; arac cubugu butonu farkli yazildigi
            # icin tam eslesme yanlislikla ona denk gelmez
            onay = varsa_tikla(page, IPTAL_ONAY, sure=4000)
        if not onay:
            yaz("    UYARI: iptal/itiraz sorgu butonu tiklanamadi", log)
            acik_pencereleri_kapat(page, log)
            return calisan

        islem_takibini_bekle(page, log, azami_saniye=AYAR["azami_saniye"],
                             durgunluk_saniye=AYAR["durgunluk_saniye"])
        acik_pencereleri_kapat(page, log)
        calisan += 1

    yaz("    Liste yenileniyor (iptal/itiraz sonrasi)", log)
    dugmeye_bas(page, "Yenile", sure=5000)
    page.wait_for_timeout(3000)
    return calisan


def iptal_itiraz_satirlari(satirlar):
    """Durum sutununda iptal/itiraz gecen satirlar."""
    return [s for s in satirlar if IPTAL_DESENI.search(sadelestir(" ".join(s)))]


def tevkifatli_satirlar(satirlar):
    """Ekranda 'tevkifat' yazan satirlar (KDV2 icin isaret)."""
    return [s for s in satirlar if TEVKIFAT_DESENI.search(sadelestir(" ".join(s)))]


def firma_isle(page, firma, belge_tipi, araliklar, cikti_kok, log, azami_deneme=3):
    sonuc = {"firma": firma, "belge_tipi": belge_tipi, "fatura_sayisi": 0,
             "durum": "", "dosyalar": [], "indirilemeyen": 0, "iptal_itiraz": 0,
             "tevkifat": 0, "donem": "", "not": ""}
    klasor = cikti_kok / dosya_adi_yap(firma) / belge_tipi
    klasor.mkdir(parents=True, exist_ok=True)

    acik_pencereleri_kapat(page, log)
    yaz("    Firma seciliyor", log)
    firma_sec(page, firma, log)
    donem_bas, donem_bit = calisma_donemi(page)
    if donem_bas and donem_bit:
        sonuc["donem"] = f"{donem_bas:%d/%m/%Y}-{donem_bit:%d/%m/%Y}"
    istenen_bas = tarih_cozumle(araliklar[0][0])
    istenen_bit = tarih_cozumle(araliklar[-1][1])
    if donem_bit and (donem_bit < istenen_bas or (donem_bas and donem_bas > istenen_bit)):
        yaz(f"    Firma donemi {donem_bas:%d/%m/%Y}-{donem_bit:%d/%m/%Y}, istenen tarihlerin disinda", log)
        sonuc["durum"] = "donem disi"
        return sonuc

    yaz("    Menuye gidiliyor", log)
    menuye_git(page, belge_tipi)

    interaktif = belge_tipi in IKI_KADEMELI
    kalan_hata = 0
    if interaktif:
        interaktif_sorgula(page, araliklar, log)
    else:
        for bas, bit in araliklar:
            onceki_hata = None
            for deneme in range(1, azami_deneme + 1):
                basarisiz = gibden_getir(page, bas, bit, log)
                if basarisiz <= 0:
                    break
                # sayi azalmiyorsa karsi sunucu yanit vermiyor demektir; tekrar denemek bos
                if onceki_hata is not None and basarisiz >= onceki_hata:
                    yaz(f"    {basarisiz} fatura tekrarda da inmedi (kaynak sunucu yanit vermiyor)", log)
                    kalan_hata += basarisiz
                    break
                if deneme == azami_deneme:
                    yaz(f"    {basarisiz} fatura {azami_deneme} denemede de indirilemedi", log)
                    kalan_hata += basarisiz
                    break
                onceki_hata = basarisiz
                yaz(f"    Tekrar sorgulaniyor ({deneme + 1}/{azami_deneme})", log)
                page.wait_for_timeout(5000)
    sonuc["indirilemeyen"] = kalan_hata

    yaz("    Tablo okunuyor", log)
    kutular, kutu_sayisi, kutu_cercevesi = secim_kutulari(page)
    satirlar = kutulardan_satirlar(kutular, kutu_sayisi)
    fr = kutu_cercevesi
    if not satirlar and interaktif and dugmeye_bas(page, INTERAKTIF_LISTELE, sure=5000):
        # sorgu listeyi kendiliginden doldurmadiysa kayitli faturalari listele
        page.wait_for_timeout(3000)
        kutular, kutu_sayisi, kutu_cercevesi = secim_kutulari(page)
        satirlar = kutulardan_satirlar(kutular, kutu_sayisi)
        fr = kutu_cercevesi
    if not satirlar:
        fr, satirlar = tabloyu_oku(page, kutu_cercevesi)
    if not satirlar:
        tani = cikti_kok / "tani"
        tani.mkdir(parents=True, exist_ok=True)
        ad = dosya_adi_yap(firma)
        try:
            page.screenshot(path=str(tani / f"{ad}-bos-liste.png"), full_page=True)
            (tani / f"{ad}-bos-liste.html").write_text(page.content(), encoding="utf-8")
            yaz(f"    Liste bos gorundu, ekran kaydi: {tani}", log)
        except Exception:
            pass
    sonuc["fatura_sayisi"] = len(satirlar)
    yaz(f"    {len(satirlar)} satir listelendi", log)

    if satirlar:
        with open(klasor / "liste.csv", "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerows(satirlar)
        tevkifatlilar = tevkifatli_satirlar(satirlar)
        sonuc["tevkifat"] = len(tevkifatlilar)
        if tevkifatlilar:
            with open(klasor / "tevkifatli.csv", "w", encoding="utf-8-sig", newline="") as f:
                csv.writer(f).writerows(tevkifatlilar)
            yaz(f"    DIKKAT: {len(tevkifatlilar)} tevkifatli fatura (KDV2)", log)

    if fr is not None and satirlar:
        secilen = hepsini_sec(page, fr, len(satirlar))
        if secilen:
            yaz(f"    {secilen} kayit isaretlendi, indirme basliyor", log)
        else:
            yaz("    UYARI: hicbir kayit isaretlenemedi, indirme yine de denenecek", log)
        if not interaktif:  # interaktif V.D. ekraninda belge indirme butonu yok
            yol = indir(page, "Seçilenleri İndir", klasor, "belgeler", log,
                        azami_saniye=AYAR["indirme_saniye"])
            if yol:
                sonuc["dosyalar"].append(yol.name)

        if AYAR["iptal_itiraz"]:
            try:
                if iptal_itiraz_sorgula(page, araliklar, log):
                    # sorgu durum sutununu degistirir; liste yeniden okunur
                    kutular, kutu_sayisi, yeni_fr = secim_kutulari(page)
                    yeni_satirlar = kutulardan_satirlar(kutular, kutu_sayisi)
                    if yeni_satirlar:
                        satirlar, fr = yeni_satirlar, yeni_fr
                        sonuc["fatura_sayisi"] = len(satirlar)
                        with open(klasor / "liste.csv", "w", encoding="utf-8-sig", newline="") as f:
                            csv.writer(f).writerows(satirlar)
                        sonuc["tevkifat"] = len(tevkifatli_satirlar(satirlar))
                    iptaller = iptal_itiraz_satirlari(satirlar)
                    sonuc["iptal_itiraz"] = len(iptaller)
                    if iptaller:
                        with open(klasor / "iptal-itiraz.csv", "w", encoding="utf-8-sig", newline="") as f:
                            csv.writer(f).writerows(iptaller)
                        yaz(f"    DIKKAT: {len(iptaller)} faturada iptal/itiraz var", log)
                    else:
                        yaz("    Iptal/itiraz kaydi yok", log)
            except Exception as e:
                yaz(f"    Iptal/itiraz sorgusu yapilamadi ({type(e).__name__}: {e})", log)
                acik_pencereleri_kapat(page, log)

        # Excel, iptal/itiraz sonrasi alinir ki durumlar guncel olsun
        if fr is not None:
            hepsini_sec(page, fr, len(satirlar))
        yol = indir(page, "Excel", klasor, "liste", log, azami_saniye=AYAR["indirme_saniye"])
        if yol:
            sonuc["dosyalar"].append(yol.name)
        sonuc["durum"] = "tamam"
    else:
        # GIB'de fatura vardi ama kaynak sunucudan inmedi: "fatura yok" demek yaniltici
        sonuc["durum"] = "kaynaktan inmedi" if kalan_hata else "fatura yok"
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


def sayfayi_toparla(page):
    """Hata sonrasi acik kalan diyaloglari kapatir.

    Sayfa yeniden YUKLENMEZ: Luca uygulama adresine dogrudan gidilince oturumu
    reddedip "LUCA HATA" veriyor ve sonraki tum firmalar basarisiz oluyordu.
    """
    acik_pencereleri_kapat(page)
    for _ in range(2):
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception:
            break


def ozet_yaz(ozet_yolu, kalan_yolu, sonuclar, bekleyenler, belge_tipi):
    """Ozeti her firmadan sonra yeniden yazar; islenmeyenler 'bekliyor' olarak gorunur."""
    with open(ozet_yolu, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Firma", "Belge Tipi", "Fatura Sayisi", "Indirilemeyen", "Iptal/Itiraz",
                    "Durum", "Dosyalar"])
        for s in sonuclar:
            w.writerow([s["firma"], s["belge_tipi"], s["fatura_sayisi"], s.get("indirilemeyen", 0),
                        s.get("iptal_itiraz", 0), s["durum"], "; ".join(s["dosyalar"])])
        for firma in bekleyenler:
            w.writerow([firma, belge_tipi, "", "", "", "bekliyor", ""])
    kalan_yolu.write_text(", ".join(bekleyenler), encoding="utf-8")


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
    p.add_argument("--firma", action="append",
                   help="Sadece bu firma(lar) islensin; virgulle ayirarak birden fazla yazilabilir")
    p.add_argument("--belge-tipi", default=ayarlar.get("belge_tipi", "e-arsiv-alis"), choices=list(BELGE_TIPLERI))
    p.add_argument("--limit", type=int, help="Ilk N firma ile sinirla")
    p.add_argument("--baslangic", help="GG/AA/YYYY (ayarlar.json'daki degeri ezer)")
    p.add_argument("--bitis", help="GG/AA/YYYY (ayarlar.json'daki degeri ezer)")
    p.add_argument("--iptal-itiraz-atla", action="store_true",
                   help="Faturalari indir ama GIB iptal/itiraz sorgusunu yapma")
    p.add_argument("--listele", action="store_true", help="Sadece firma listesini yazdir, islem yapma")
    p.add_argument("--bitince-kapat", action="store_true",
                   help="Is bitince ENTER beklemeden tarayiciyi kapat (gece calistirma icin)")
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
    azami_deneme = max(1, int(ayarlar.get("tekrar_deneme", 3)))
    AYAR["azami_saniye"] = max(60, int(float(ayarlar.get("sorgu_azami_dakika", 30)) * 60))
    AYAR["durgunluk_saniye"] = max(30, int(float(ayarlar.get("durgunluk_dakika", 3)) * 60))
    AYAR["indirme_saniye"] = max(3, int(ayarlar.get("indirme_bekleme_saniye", 30)))
    AYAR["iptal_itiraz"] = bool(ayarlar.get("iptal_itiraz_sorgula", True)) and not args.iptal_itiraz_atla
    hata_siniri = max(1, int(ayarlar.get("ardisik_hata_siniri", 5)))

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
            aranan = [(p.strip(), karsilastir(p)) for deger in args.firma for p in deger.split(",") if p.strip()]
            bulunamayan = [ham for ham, a in aranan if not any(a in karsilastir(f) for f in firmalar)]
            if bulunamayan:
                yaz(f"Eslesmeyen arama: {', '.join(bulunamayan)}", log)
            firmalar = [f for f in firmalar if any(a in karsilastir(f) for _, a in aranan)]
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
        atlama_adlari = [a for a in ayarlar.get("atlanacak_firmalar", []) if a.strip()]
        if atlama_adlari:
            def ayni_firma(ad, atlanan):
                # Luca adlari kisaltarak gosterdigi icin bas kismi tutan ad da atlanir
                k, a = karsilastir(ad), karsilastir(atlanan)
                return bool(k) and bool(a) and (k.startswith(a) or a.startswith(k))

            atlananlar = [f for f in firmalar if any(ayni_firma(f, a) for a in atlama_adlari)]
            firmalar = [f for f in firmalar if f not in atlananlar]
            if atlananlar:
                yaz(f"Atlanan firma ({len(atlananlar)}): {', '.join(atlananlar)}", log)
            eslesmeyen = [a for a in atlama_adlari if not any(ayni_firma(f, a) for f in atlananlar)]
            if eslesmeyen:
                yaz(f"UYARI: atlama listesinde eslesmeyen ad: {', '.join(eslesmeyen)}", log)
        if args.limit:
            firmalar = firmalar[: args.limit]

        yaz(f"Islenecek firma sayisi: {len(firmalar)} | belge tipi: {args.belge_tipi}", log)
        yaz(f"Tarih araligi: {araliklar[0][0]} - {araliklar[-1][1]} ({len(araliklar)} sorgu/firma)\n", log)

        sonuclar = []
        ardisik_hata = 0
        ozet = calisma / "ozet.csv"
        kalan_dosya = calisma / "kalan-firmalar.txt"
        ozet_yaz(ozet, kalan_dosya, [], firmalar, args.belge_tipi)  # bastan yazilir ki yarida kalsa da dosya olsun

        for i, firma in enumerate(firmalar, 1):
            yaz(f"[{i}/{len(firmalar)}] {firma}", log)
            try:
                sonuclar.append(firma_isle(page, firma, args.belge_tipi, araliklar, calisma, log, azami_deneme))
            except Exception as e:
                yaz(f"    HATA: {type(e).__name__}: {e}", log)
                hata_kaydet(page, calisma / "hatalar", firma)
                sonuclar.append({"firma": firma, "belge_tipi": args.belge_tipi, "fatura_sayisi": 0,
                                 "durum": f"hata: {type(e).__name__}", "dosyalar": [],
                                 "indirilemeyen": 0, "iptal_itiraz": 0, "tevkifat": 0,
                                 "donem": "", "not": str(e)[:120]})
                sayfayi_toparla(page)
                ardisik_hata += 1
            else:
                ardisik_hata = 0

            # her firmadan sonra guncellenir: gece yarida kalirsa sabah nerede kalindigi gorulur
            ozet_yaz(ozet, kalan_dosya, sonuclar, firmalar[i:], args.belge_tipi)
            try:
                rapor.guncelle(calisma, sonuclar, firmalar[i:], args.belge_tipi)
            except Exception as e:  # rapor yazilamazsa calisma durmasin
                yaz(f"    UYARI: rapor guncellenemedi ({type(e).__name__}: {e})", log)

            if ardisik_hata >= hata_siniri:
                yaz(f"\nUst uste {hata_siniri} firma basarisiz oldu; Luca oturumu bozulmus olabilir.", log)
                yaz("Islem durduruldu. Tarayicidan Luca'ya tekrar girip yeniden calistirin.", log)
                break

        basarili = sum(1 for s in sonuclar if s["durum"] == "tamam")
        toplam_fatura = sum(s["fatura_sayisi"] for s in sonuclar)
        yaz(f"\nBitti. {basarili}/{len(sonuclar)} firma tamamlandi, {toplam_fatura} fatura listelendi.", log)
        yaz(f"Dosyalar: {calisma}", log)
        yaz(f"Ozet: {ozet}", log)
        yaz(f"Rapor: {calisma / 'rapor.xlsx'} (aksiyon gereken firmalar en ustte)", log)

        if not args.bitince_kapat:
            input(">>> Tarayiciyi kapatmak icin ENTER'a basin: ")
        ctx.close()


if __name__ == "__main__":
    sys.exit(main())
