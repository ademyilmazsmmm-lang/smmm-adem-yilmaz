# -*- coding: utf-8 -*-
"""Ekrandaki fatura listesini okuma ve faturalari isaretleme.

Asil kaynak inen Excel dosyasidir (bkz. fatura_analiz.py); ekrandan okunan
liste, Excel inmezse yedek olarak ve "kac fatura var" kararini vermek icin
kullanilir.
"""

from .bekleme import sayfa_durulsun
from .luca_ekran import cerceveler, dugmeye_bas, metinle_bul, varsa_tikla
from .sabitler import BELGE_NO_DESENI, TARIH_DESENI


def fatura_satiri_mi(hucreler, en_az=3):
    """Satir fatura satiri mi: yeterli hucre + tarih ya da belge numarasi.

    Interaktif V.D. ekraninda tarih bicimi degisebildigi icin belge numarasi
    da olcut alinir; yoksa dolu listeler bos gorunuyordu.
    """
    if len(hucreler) < en_az:
        return False
    return any(TARIH_DESENI.search(h) or BELGE_NO_DESENI.search(h) for h in hucreler)


def _satir_hucreleri(satir):
    return [h.strip() for h in satir.locator("td").all_inner_texts() if h.strip()]


def cerceveden_satirlar(fr):
    try:
        satirlar = fr.locator("tr")
        adet = min(satirlar.count(), 500)
    except Exception:
        return []
    veriler = []
    for i in range(adet):
        try:
            hucreler = _satir_hucreleri(satirlar.nth(i))
        except Exception:
            continue
        if fatura_satiri_mi(hucreler, 3):
            veriler.append(hucreler)
    return veriler


# Satir hucreleri: once gercek hucre ogeleri, olmazsa dogrudan cocuklar,
# en son satir metni (izgara <td> kullanmadiginda metin tek parca geliyordu)
HUCRE_CIKAR = """el => {
  const s = el.closest('tr, [role=row], li')
    || (el.parentElement && el.parentElement.parentElement);
  if (!s) return [];
  const metin = e => (e.innerText || e.textContent || '').trim();
  let h = [...s.querySelectorAll('td, th, [role=gridcell], [role=cell]')].map(metin);
  if (h.filter(Boolean).length < 2) h = [...s.children].map(metin);
  if (h.filter(Boolean).length < 2) h = metin(s).split(/\\t|\\n|\\s{2,}/);
  return h.map(t => t.trim()).filter(Boolean);
}"""


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
            hucreler = kutular.nth(i).evaluate(HUCRE_CIKAR) or []
        except Exception:
            continue
        hucreler = [h.strip() for h in hucreler if h and h.strip()]
        if fatura_satiri_mi(hucreler, 3):
            satirlar.append(hucreler)
    return satirlar


def tabloyu_oku(page, tercih=None):
    """Fatura tablosu, isaret kutulariyla ayni cerceveden okunur.

    Tum cerceveler taranirsa baska ekranlardan kalan tablolar da fatura
    sanilip olmayan satirlar listeleniyordu.
    """
    if tercih is not None:
        # Bu cercevede satir yoksa liste gercekten bostur; genel taramaya
        # dusulurse baska ekranlarda kalan tablolar fatura saniliyor.
        return tercih, cerceveden_satirlar(tercih)

    en_iyi = (None, [])
    for fr in cerceveler(page):
        veriler = cerceveden_satirlar(fr)
        if len(veriler) > len(en_iyi[1]):
            en_iyi = (fr, veriler)
    return en_iyi


SECIM_SECICILERI = ("input[type=checkbox]", "[role=checkbox]",
                    "img[src*='check']", "img[src*='tick']", "[class*='checkbox']")


def veri_kutusu_sayisi(kutular, adet, sinir=14):
    """Kutulardan kaci gercek bir fatura satirinda duruyor.

    Ekranda sutun secimi ve suzgec satirlarinin da isaret kutusu var; bunlar
    fatura satiri sanilinca liste bos okunuyordu.
    """
    bulunan = 0
    for i in range(min(adet, sinir)):
        try:
            hucreler = [h for h in (kutular.nth(i).evaluate(HUCRE_CIKAR) or []) if h]
        except Exception:
            continue
        if fatura_satiri_mi(hucreler, 3):
            bulunan += 1
    return bulunan


def secim_kutulari(page):
    """Fatura satirlarindaki isaret kutularini bulur: (kutular, adet, cerceve).

    Yalnizca "en cok kutu" olcut alinirsa baslik/suzgec satirinin kutulari
    secilebiliyor. Once kutunun durdugu satirin fatura satiri olup olmadigina
    bakilir; hicbir cercevede veri satiri yoksa eski davranisa (en cok kutu)
    dusulur.
    """
    en_iyi = (None, 0, None)
    en_iyi_veri = 0
    yedek = (None, 0, None)
    for fr in cerceveler(page):
        for secici in SECIM_SECICILERI:
            try:
                loc = fr.locator(secici)
                adet = loc.count()
                if not adet or not loc.first.is_visible():
                    continue
            except Exception:
                continue
            if adet > yedek[1]:
                yedek = (loc, adet, fr)
            veri = veri_kutusu_sayisi(loc, adet)
            if veri > en_iyi_veri or (veri and veri == en_iyi_veri and adet > en_iyi[1]):
                en_iyi, en_iyi_veri = (loc, adet, fr), veri
            if veri:  # bu cercevede fatura satiri bulundu, digerlerini deneme
                break
    return en_iyi if en_iyi[0] is not None else yedek


def ekrandaki_satirlar(page):
    """(satirlar, cerceve): isaret kutularindan, olmazsa tablodan okunan fatura satirlari."""
    kutular, sayi, fr = secim_kutulari(page)
    return kutulardan_satirlar(kutular, sayi), fr


def isaretli_sayisi(kutular, sayi):
    if kutular is None:
        return 0
    try:
        return sum(1 for i in range(sayi) if kutular.nth(i).is_checked())
    except Exception:
        return 0


def veri_satir_indisleri(fr):
    if fr is None:
        return None, []
    try:
        satirlar = fr.locator("tr")
        adet = min(satirlar.count(), 500)
    except Exception:
        return None, []
    indisler = []
    for i in range(adet):
        try:
            hucreler = _satir_hucreleri(satirlar.nth(i))
        except Exception:
            continue
        if fatura_satiri_mi(hucreler, 3):
            indisler.append(i)
    return satirlar, indisler


def belge_sec_diyalogu(page, satir_sayisi=0):
    """Luca'nin kendi secim yolu: Belge Seç -> Tümünü Seç -> Tamam.

    Satirlari tek tek isaretlemek yerine "Belge Seçiniz" penceresi kullanilir;
    pencere listedeki butun belgeleri (ekranda gorunmeyenler dahil) secer.
    """
    if not dugmeye_bas(page, "Belge Seç", sure=4000):
        return 0
    try:  # pencere acildiysa icindeki "Tümünü Seç" gorunur olur (gorunene kadar beklenir)
        _, dugme = metinle_bul(page, "Tümünü Seç", sure=5000)
        dugme.click(timeout=5000)
    except Exception:
        varsa_tikla(page, ["Kapat"])
        return 0
    sayfa_durulsun(page, azami_ms=600)
    try:
        _, tamam = metinle_bul(page, "Tamam", sure=5000)
        tamam.click(timeout=5000)
    except Exception:
        varsa_tikla(page, ["Kapat"])
        return 0
    sayfa_durulsun(page, azami_ms=1000)
    kutular, sayi, _ = secim_kutulari(page)
    return isaretli_sayisi(kutular, sayi) or satir_sayisi


def hepsini_sec(page, fr=None, satir_sayisi=0):
    """Listedeki butun faturalari isaretler; isaretlenen sayiyi dondurur (0: olmadi).

    Sirayla uc yol denenir: Luca'nin 'Belge Seç' penceresi, isaret kutulari,
    satira tiklayip bosluk tusu.
    """
    secilen = belge_sec_diyalogu(page, satir_sayisi)  # Luca'nin kendi yolu
    if secilen:
        return secilen

    kutular, sayi, kutu_cercevesi = secim_kutulari(page)
    if fr is None:
        fr = kutu_cercevesi

    if sayi:
        try:  # baslik satirindaki kutu genelde hepsini isaretler
            kutular.first.check(timeout=5000)
            sayfa_durulsun(page, azami_ms=800)
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
            sayfa_durulsun(page, azami_ms=500)
            return secilen

    # Luca'nin kendi ipucu: tabloda bosluk tusu satir seciyor
    satirlar, indisler = veri_satir_indisleri(fr)
    if satirlar is not None and indisler:
        try:
            satirlar.nth(indisler[0]).click(timeout=5000)
            sayfa_durulsun(page, azami_ms=400)
            for _ in indisler:
                page.keyboard.press("Space")
                sayfa_durulsun(page, azami_ms=150, sessizlik_ms=100, en_az_ms=0)
                page.keyboard.press("ArrowDown")
                sayfa_durulsun(page, azami_ms=150, sessizlik_ms=100, en_az_ms=0)
            return isaretli_sayisi(kutular, sayi) or len(indisler)
        except Exception:
            pass
    return 0
