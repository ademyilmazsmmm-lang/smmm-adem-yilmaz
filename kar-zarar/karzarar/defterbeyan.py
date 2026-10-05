# -*- coding: utf-8 -*-
"""Defter Beyan Sistemi (portal.defterbeyan.gov.tr): isletme defteri mukelleflerinin Hesap Ozeti.

Akis (mali musavir hesabiyla):
  1. Giris sayfasi acilir, kullanici kodu/sifre yazilir (ayarlarda varsa); GUVENLIK KODU
     (resim) insan tarafindan girilir, bot giris tamamlanana kadar bekler.
  2. Mukellef Yonetimi'nde mukellef VKN ile aranip secilir, "Hizli Gecis Yap".
     Ust cubuktaki "<vkn> - ISLETME" yazisi defter turunu verir.
  3. Muhasebe Bilgileri > Hesap Ozeti: Baslangic/Bitis Tarihi yazilip "Olustur";
     Mali Hesap Ozeti tablosundan hasilat, emtia alisi, giderler ve kar/zarar okunur.
  4. "Kendi Hesabima Geri Don" ile mukellef degisimine hazirlanilir.
"""

import re
from datetime import date

from lucabot.bekleme import kosulu_bekle, sayfa_durulsun
from lucabot.fatura_analiz import tutar_cozumle
from lucabot.musteri_listesi import tablolari_al
from lucabot.ortak import sadelestir, yaz

ADRES = "https://portal.defterbeyan.gov.tr"
GIRIS = "/auth/login"
MUKELLEF_YONETIMI = "/mmislemleri/mukellefyonetimi"
HESAP_OZETI = "/muhasebe/hesapozeti"
SAYI = re.compile(r"^-?\d{1,3}(\.\d{3})*,\d{2}$|^-?\d+,\d{2}$")

ETIKETLER = {
    "DONEM BASI EMTIA MEVCUDU": "emtia_basi",
    "DONEM ICINDE SATIN ALINAN EMTIA": "mal_alis",
    "GIDERLER": "giderler",
    "AMORTISMAN GIDERLERI": "amortisman",
    "KAR": "kar",
    "DONEM SONU EMTIA MEVCUDU": "emtia_sonu",
    "DONEM ICINDE ELDE EDILEN HASILAT": "hasilat",
    "GELIR DIGER GELIRLER": "diger_gelir",
    "ZARAR": "zarar",
}

# iki tarih kutusunu (GG.AA.YYYY degeri olan ilk iki metin kutusu) isaretler
TARIH_KUTULARI_JS = """() => {
  document.querySelectorAll('[data-lucabot-tarih]').forEach(e => e.removeAttribute('data-lucabot-tarih'));
  const gorunur = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const kutular = [...document.querySelectorAll('input')]
    .filter(e => gorunur(e) && /^\\d{2}\\.\\d{2}\\.\\d{4}$/.test((e.value || '').trim()));
  kutular.slice(0, 2).forEach((e, i) => e.setAttribute('data-lucabot-tarih', String(i)));
  return Math.min(2, kutular.length);
}"""


# --- ozet tablosunu cozumleme (tarayicisiz, test edilebilir) ---------------------------

def hesap_ozeti_cozumle(tablolar):
    """tablolar: [(cerceve no, satirlar)] -> {satis, mal_alis, gider, kar, ayrinti}; tablo bulunamazsa None.

    'Etiket | tutar' ciftlerinden okunur; kar = Kar - Zarar (zarar eksi).
    """
    deger = {}
    for _, satirlar in tablolar:
        for s in satirlar:
            hucre = [h.strip() for h in s]
            for i, h in enumerate(hucre[:-1]):
                alan = ETIKETLER.get(sadelestir(h))
                if alan and alan not in deger and (SAYI.match(hucre[i + 1]) or not hucre[i + 1]):
                    deger[alan] = tutar_cozumle(hucre[i + 1]) if hucre[i + 1] else None  # bos hucre: deger yok
    g = lambda ad: deger.get(ad) or 0.0
    hesaplanan = False
    if "kar" not in deger and "zarar" not in deger:
        if "hasilat" not in deger or "giderler" not in deger:
            return None
        # Kar/Zarar satiri olmayan ozet (orn. serbest meslek): gelir + donem sonu emtia - (donem basi emtia + alis + gider)
        hesaplanan = True
        deger["kar"] = (g("hasilat") + g("diger_gelir") + g("emtia_sonu")
                        - g("emtia_basi") - g("mal_alis") - g("giderler") - g("amortisman"))
        deger["zarar"] = 0.0
    if hesaplanan:
        deger["kar_hesaplandi"] = 1.0
    return {"satis": round(g("hasilat") + g("diger_gelir"), 2), "mal_alis": round(g("mal_alis"), 2),
            "gider": round(g("giderler") + g("amortisman"), 2), "kar": round(g("kar") - g("zarar"), 2),
            # Toplam gider = dönem başı emtia + mal alışı + giderler + amortisman (Gelir + dönem sonu emtia - bu = kâr/zarar)
            "toplam_gider": round(g("emtia_basi") + g("mal_alis") + g("giderler") + g("amortisman"), 2),
            "ayrinti": deger}


def defter_turu(metin, vkn, kesin=False):
    """Ust cubuktaki '6000000006 - İŞLETME' yazisindan defter turu (buyuk harf); yoksa ''.

    Mukellef listesinde de '<vkn> - <unvan>' yazdigi icin bilinen defter turleri
    (ISLETME, BILANCO) onceliklidir; kesin=True ise yalniz onlar kabul edilir.
    """
    bulunan = [m.group(1).strip().upper() for m in re.finditer(rf"{re.escape(vkn)}\s*-\s*([^\s|]+)", metin or "")]
    bilinen = [t for t in bulunan if sadelestir(t).startswith(("ISLETME", "BILANCO"))]
    if bilinen:
        return bilinen[-1]
    return "" if kesin or not bulunan else bulunan[-1]


def isletme_mi(tur):
    return sadelestir(tur).startswith("ISLETME")


def smk_mi(tur):
    """Serbest meslek kazanci (ust cubukta 'SMK'); Hesap Ozeti isletme defteri gibi okunur."""
    return sadelestir(tur).startswith(("SMK", "SERBEST"))


def bilanco_mu(tur):
    return sadelestir(tur).startswith("BILANCO")


# --- giris -------------------------------------------------------------------------

class MukellefAtlandi(LookupError):
    """Defter Beyan mukellefe gecisi vermiyor (orn. Mukellef Karti'na yonlendiriyor): hata sayilmaz, firma atlanir."""


class DonemDisi(MukellefAtlandi):
    """Mukellefin defter donemi istenen donemden once bitmis (donem sonu / kapanis): firma atlanir."""


# Ust cubuk: "( Başlangıç Tarihi: 01.01.2026 - Bitiş Tarihi: Devam Ediyor )" ya da bitis tarihi yazili
DEFTER_DONEMI = re.compile(
    r"Başlangıç Tarihi:\s*(\d{2})\.(\d{2})\.(\d{4})\s*[-–]\s*Bitiş Tarihi:\s*(?:(\d{2})\.(\d{2})\.(\d{4})|\S)")


def defter_donemi(metin):
    """Ust cubuktan (defter baslangici, defter bitisi ya da None=devam ediyor); cubuk yoksa None."""
    m = DEFTER_DONEMI.search(metin or "")
    if not m:
        return None
    g = m.groups()
    bit = date(int(g[5]), int(g[4]), int(g[3])) if g[3] else None
    return date(int(g[2]), int(g[1]), int(g[0])), bit


def _govde(page):
    try:
        return page.locator("body").inner_text(timeout=3000)
    except Exception:
        return ""


def girisli_mi(page):
    return page.url.startswith(ADRES) and "/auth/login" not in page.url


def giris_yap(page, kullanici="", sifre="", bekle_saniye=300, log=None):
    """Giris sayfasini acar, kod/sifreyi yazar; guvenlik kodunu insan girer. Girilirse True."""
    page.goto(ADRES + GIRIS, wait_until="domcontentloaded", timeout=60000)
    sayfa_durulsun(page, azami_ms=2000)
    if girisli_mi(page):
        return True
    try:
        sifre_kutusu = page.locator("input[type=password]").first
        metin_kutulari = page.locator("input:not([type=password]):not([type=hidden]):not([type=checkbox])")
        if kullanici and metin_kutulari.count():
            metin_kutulari.first.fill(kullanici, timeout=5000)
        if sifre and sifre_kutusu.count():
            sifre_kutusu.fill(sifre, timeout=5000)
    except Exception:
        yaz("    Kullanıcı kodu/şifre yazılamadı; tarayıcıda elle girin", log)
    yaz(">>> DEFTER BEYAN: tarayıcıda GÜVENLİK KODUNU yazıp 'GİRİŞ YAP'a basın"
        f" ({bekle_saniye // 60} dakika beklenir)", log)
    return bool(kosulu_bekle(page, lambda: girisli_mi(page), bekle_saniye * 1000, aralik_ms=1000))


# --- mukellef ----------------------------------------------------------------------

def _arama_kutusu(page):
    """Acilan listenin arama kutusu: once odaktaki kutu, sonra bilinen kutuphane seciciler."""
    for secici in (":focus:is(input, textarea)", "input.select2-search__field", "input[type=search]",
                   "[role=searchbox]", ".select2-search input", ".bs-searchbox input", ".ng-input input",
                   "[role=combobox] input", "[class*=dropdown] input[type=text]", "[class*=select] input[type=text]",
                   "[class*=search] input", "input[placeholder*=Ara]"):
        k = page.locator(secici).first
        try:
            if k.count() and k.is_visible():
                return k
        except Exception:
            continue
    return None


def _secenek(page, vkn):
    """Listede '<vkn> - <unvan>' satiri (gorunurse); tablodaki VKN hucresiyle karismasin diye ' - ' aranir."""
    desen = re.compile(rf"^\s*{re.escape(vkn)}\s*-\s*\S")
    for aday in (page.get_by_role("option").filter(has_text=desen), page.locator("li").filter(has_text=desen),
                 page.get_by_text(desen)):
        try:
            if aday.count() and aday.first.is_visible():
                return aday.first
        except Exception:
            continue
    return None


def _tani_kaydet(page, klasor, ad, log=None):
    if klasor is None:
        return
    try:
        klasor.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(klasor / f"{ad}.png"))
        (klasor / f"{ad}.html").write_text(page.content(), encoding="utf-8")
        yaz(f"    Tani dosyalari kaydedildi: {klasor}", log)
    except Exception:
        pass


def _secim_kutusunu_ac(page):
    """Mukellef Yonetimi'ni acip VKN secim kutusunu acar; kutuphane fark etmeksizin arama kutusu ya da
    secenek listesi gorunene kadar dener. Acildiysa dogru, degilse yanlis."""
    page.goto(ADRES + MUKELLEF_YONETIMI, wait_until="domcontentloaded", timeout=60000)
    sayfa_durulsun(page, azami_ms=2000)
    if MUKELLEF_YONETIMI not in page.url:  # portal ana sayfaya (Mükellef Bilgileri) atmis: menuden git
        for tikla in (lambda: page.get_by_text("Mali Müşavir İşlemleri", exact=True).first.click(timeout=3000),
                      lambda: page.locator(f'a[href="{MUKELLEF_YONETIMI}"]').last.click(timeout=5000)):
            try:
                tikla()
            except Exception:
                pass
        kosulu_bekle(page, lambda: MUKELLEF_YONETIMI in page.url, 8000, aralik_ms=300)
        sayfa_durulsun(page, azami_ms=2000)
    for ac in (lambda: page.locator(".select2-selection, [role=combobox], .ng-select, .bootstrap-select button,"
                                    " .vs__dropdown-toggle").first.click(timeout=4000),
               lambda: page.get_by_placeholder("Vergi Kimlik Numarası").first.click(timeout=4000),
               lambda: page.get_by_text("Vergi Kimlik Numarası", exact=True).last.click(timeout=4000),
               lambda: page.get_by_text("Vergi Kimlik Numarası", exact=True).first.locator(
                   "xpath=following::*[self::span or self::div or self::button][1]").click(timeout=4000)):
        try:
            ac()
        except Exception:
            continue
        if kosulu_bekle(page, lambda: _arama_kutusu(page) or page.get_by_role("option").count() > 0
                        or page.locator(".select2-results, [class*=dropdown-menu].show, [role=listbox]").count() > 0,
                        3000, aralik_ms=200):
            return True
    return False


def mukellef_sec(page, vkn, log=None, tani_klasoru=None, tani_hep=False):
    """Mukellef Yonetimi'nde VKN'yi arayip secer ve Hizli Gecis Yap'a basar.

    Dondurur: defter turu ('ISLETME' ...); mukellef listede yoksa None.
    """
    acik = _secim_kutusunu_ac(page)
    if not acik:  # onceki mukellefte kalinmis olabilir: kendi hesaba donup bir kez daha dene
        mukelleften_cik(page)
        acik = _secim_kutusunu_ac(page)
    if not acik:
        _tani_kaydet(page, tani_klasoru, "defterbeyan-mukellef-secimi", log)
        raise LookupError("Mükellef seçim kutusu açılmadı")
    kutu = _arama_kutusu(page)
    if kutu:
        kutu.fill(vkn)
    else:  # arama kutusu taninmadi ama liste acik: odaktaki alana klavyeyle yaz
        page.keyboard.type(vkn, delay=40)
    secenek = kosulu_bekle(page, lambda: _secenek(page, vkn), 6000, aralik_ms=300)
    if not secenek:
        page.keyboard.press("Escape")
        if not kutu:  # arama calismadiysa 'listede yok' demek yaniltici olur
            _tani_kaydet(page, tani_klasoru, "defterbeyan-mukellef-secenek", log)
            raise LookupError("Mükellef arama kutusu bulunamadı")
        return None
    secenek.click(timeout=5000)
    try:
        page.get_by_role("button", name=re.compile("Hızlı Geçiş")).click(timeout=8000)
    except Exception:  # dugme yok/tiklanamiyor (orn. kendi hesabiniz): bekleme/oturum hatasi degil
        _tani_kaydet(page, tani_klasoru, "defterbeyan-hizli-gecis", log)
        raise MukellefAtlandi(f"{vkn} için 'Hızlı Geçiş Yap' düğmesi kullanılamadı")
    # sayfa degisene kadar mukellef listesindeki "<vkn> - <unvan>" yazisi tur sanilmasin
    tur = kosulu_bekle(
        page, lambda: defter_turu(_govde(page), vkn, kesin=True)
        or (MUKELLEF_YONETIMI not in page.url and defter_turu(_govde(page), vkn))
        or "/mukellef/" in page.url, 25000, aralik_ms=500)  # /mukellef/...: portal Mukellef Karti'na atti
    if not tur or "/mukellef/" in page.url and not defter_turu(_govde(page), vkn):
        _tani_kaydet(page, tani_klasoru, "defterbeyan-gecis", log)
        raise MukellefAtlandi(f"{vkn} mükellefine geçilemedi (Defter Beyan Mükellef Kartı'na yönlendirdi)")
    if tani_hep:
        _tani_kaydet(page, tani_klasoru, "defterbeyan-1-mukellef-secildi", log)
    return tur


def hesap_ozeti_oku(page, bas, bit, log=None, tani_klasoru=None, tani_hep=False):
    """Hesap Ozeti sayfasinda tarihleri yazip Olustur'a basar; cozumlenmis ozet dondurur."""
    page.goto(ADRES + HESAP_OZETI, wait_until="domcontentloaded", timeout=60000)
    sayfa_durulsun(page, azami_ms=2000)
    donem = defter_donemi(_govde(page))
    if donem and donem[1] and donem[1] < bas:  # defter donemi istenen donemden once bitmis: 30 sn beklemeye gerek yok
        raise DonemDisi(f"Defter dönemi {donem[0]:%d/%m/%Y}-{donem[1]:%d/%m/%Y} (dönem sonu var);"
                        f" {bas:%d/%m/%Y} döneminde defter yok")
    if not kosulu_bekle(page, lambda: page.evaluate(TARIH_KUTULARI_JS) == 2, 15000, aralik_ms=500):
        raise LookupError("Hesap özeti tarih kutuları bulunamadı")
    for sira, d in enumerate((bas, bit)):
        kutu = page.locator(f'[data-lucabot-tarih="{sira}"]')
        hedef = f"{d:%d.%m.%Y}"
        kutu.click(timeout=5000)
        kutu.press("Control+A")
        kutu.press_sequentially(hedef, delay=30)
        kutu.press("Tab")
        if kutu.input_value().strip() != hedef:  # maske/tarih secici yazimi bozduysa degeri dogrudan ata
            kutu.evaluate("(e, v) => { e.value = v; e.dispatchEvent(new Event('input', {bubbles: true}));"
                          " e.dispatchEvent(new Event('change', {bubbles: true})); }", hedef)
    page.get_by_role("button", name=re.compile("Oluştur")).click(timeout=8000)
    istenen = (f"{bas:%d/%m/%Y}", f"{bit:%d/%m/%Y}")

    def hazir():
        m = re.search(r"Başlangıç Tarihi:\s*(\d{2}/\d{2}/\d{4})\s*Bitiş Tarihi:\s*(\d{2}/\d{2}/\d{4})",
                      _govde(page))
        return m and m.groups() == istenen
    if not kosulu_bekle(page, hazir, 30000, aralik_ms=700):
        m = re.search(r"Başlangıç Tarihi:\s*(\d{2}/\d{2}/\d{4})\s*Bitiş Tarihi:\s*(\d{2}/\d{2}/\d{4})", _govde(page))
        _tani_kaydet(page, tani_klasoru, "defterbeyan-ozet", log)
        if m and date(int(m.group(2)[6:]), int(m.group(2)[3:5]), int(m.group(2)[:2])) < bas:  # ekranda eski donem
            raise DonemDisi(f"Hesap özeti {m.group(1)}-{m.group(2)} dönemini gösteriyor (dönem sonu var);"
                            f" {bas:%d/%m/%Y} döneminde defter yok")
        raise LookupError("Mali Hesap Özeti istenen dönem için oluşmadı"
                          + (f" (ekranda: {m.group(1)} - {m.group(2)})" if m else " (ekranda dönem başlığı yok)"))
    sayfa_durulsun(page, azami_ms=1000)
    if tani_hep:
        _tani_kaydet(page, tani_klasoru, "defterbeyan-2-hesap-ozeti", log)
    ozet = hesap_ozeti_cozumle(tablolari_al(page))
    if ozet is None:
        _tani_kaydet(page, tani_klasoru, "defterbeyan-ozet-okunamadi", log)
        raise LookupError("Mali Hesap Özeti tablosu okunamadı")
    return ozet


def mukelleften_cik(page):
    """'Kendi Hesabıma Geri Dön'; sonraki mukellef icin Mukellef Yonetimi acilir."""
    try:
        page.get_by_text("Kendi Hesabıma Geri Dön").first.click(timeout=8000)
        sayfa_durulsun(page, azami_ms=1500)
    except Exception:
        pass  # bir sonraki mukellef secimi zaten Mukellef Yonetimi'ne gider
