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
                    deger[alan] = tutar_cozumle(hucre[i + 1])
    if "kar" not in deger and "zarar" not in deger:
        return None
    g = lambda ad: deger.get(ad, 0.0)
    return {"satis": round(g("hasilat") + g("diger_gelir"), 2), "mal_alis": round(g("mal_alis"), 2),
            "gider": round(g("giderler") + g("amortisman"), 2), "kar": round(g("kar") - g("zarar"), 2),
            "ayrinti": deger}


def defter_turu(metin, vkn, kesin=False):
    """Ust cubuktaki '6170780106 - İŞLETME' yazisindan defter turu (buyuk harf); yoksa ''.

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


# --- giris -------------------------------------------------------------------------

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
    for secici in ("input.select2-search__field", "input[type=search]", "[role=searchbox]",
                   ".select2-search input", "input[placeholder*=Ara]"):
        k = page.locator(secici).first
        try:
            if k.count() and k.is_visible():
                return k
        except Exception:
            continue
    return None


def mukellef_sec(page, vkn, log=None):
    """Mukellef Yonetimi'nde VKN'yi arayip secer ve Hizli Gecis Yap'a basar.

    Dondurur: defter turu ('ISLETME' ...); mukellef listede yoksa None.
    """
    page.goto(ADRES + MUKELLEF_YONETIMI, wait_until="domcontentloaded", timeout=60000)
    sayfa_durulsun(page, azami_ms=2000)
    kutu = None
    for ac in (lambda: page.locator(".select2-selection, [role=combobox]").first.click(timeout=5000),
               lambda: page.get_by_text("Vergi Kimlik Numarası", exact=True).last.click(timeout=5000)):
        try:
            ac()
        except Exception:
            continue
        kutu = kosulu_bekle(page, lambda: _arama_kutusu(page), 3000, aralik_ms=200)
        if kutu:
            break
    if not kutu:
        raise LookupError("Mükellef seçim kutusu açılmadı")
    kutu.fill(vkn)
    secenek = page.get_by_role("option").filter(has_text=vkn).first
    bulundu = kosulu_bekle(page, lambda: secenek.count() > 0 and secenek.is_visible(), 6000, aralik_ms=300)
    if not bulundu:
        page.keyboard.press("Escape")
        return None
    secenek.click(timeout=5000)
    page.get_by_role("button", name=re.compile("Hızlı Geçiş")).click(timeout=8000)
    # sayfa degisene kadar mukellef listesindeki "<vkn> - <unvan>" yazisi tur sanilmasin
    tur = kosulu_bekle(
        page, lambda: defter_turu(_govde(page), vkn, kesin=True)
        or (MUKELLEF_YONETIMI not in page.url and defter_turu(_govde(page), vkn)), 25000, aralik_ms=500)
    if not tur:
        raise LookupError(f"{vkn} mükellefine geçilemedi")
    return tur


def hesap_ozeti_oku(page, bas, bit, log=None):
    """Hesap Ozeti sayfasinda tarihleri yazip Olustur'a basar; cozumlenmis ozet dondurur."""
    page.goto(ADRES + HESAP_OZETI, wait_until="domcontentloaded", timeout=60000)
    sayfa_durulsun(page, azami_ms=2000)
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
        raise LookupError("Mali Hesap Özeti istenen dönem için oluşmadı")
    sayfa_durulsun(page, azami_ms=1000)
    ozet = hesap_ozeti_cozumle(tablolari_al(page))
    if ozet is None:
        raise LookupError("Mali Hesap Özeti tablosu okunamadı")
    return ozet


def mukelleften_cik(page):
    """'Kendi Hesabıma Geri Dön'; sonraki mukellef icin Mukellef Yonetimi acilir."""
    try:
        page.get_by_text("Kendi Hesabıma Geri Dön").first.click(timeout=8000)
        sayfa_durulsun(page, azami_ms=1500)
    except Exception:
        pass  # bir sonraki mukellef secimi zaten Mukellef Yonetimi'ne gider
