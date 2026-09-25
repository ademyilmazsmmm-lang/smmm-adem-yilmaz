# -*- coding: utf-8 -*-
"""Luca ekran ogeleri: buton bulma/tiklama, Luca pencereleri, tarih kutulari.

Luca eski bir Struts uygulamasi; ekranlar farkli cercevelere (frame)
dagilmis. Buradaki fonksiyonlar butun cerceveleri tarar, ogeyi yazisina gore
bulur ve bulunamazsa programi cokertmek yerine None/False dondurur (ya da
cagiranin yakalayacagi LookupError firlatir).
"""

from pathlib import Path

from .bekleme import (geri_cekil, kaybolana_kadar_bekle, kosulu_bekle,
                      sayfa_canli, sayfa_durulsun)
from .ortak import dosya_adi_yap, karsilastir, yaz
from .sabitler import (BILGI_CAPALARI, DIYALOG_CAPASI, FATURA_YOK_CAPASI,
                       GIB_HATA_METINLERI, KISAYOLLAR, TARIH_DESENI,
                       TARIH_NITELIGI)


def cerceveler(page):
    """Sayfanin butun cerceveleri (ekranlar farkli frame'lere dagilmis olabiliyor)."""
    try:
        return list(page.frames)
    except Exception:
        return []


# --- oge bulma ----------------------------------------------------------------

def bul(page, kurucu, sure=15000, gorunur=True):
    """kurucu(frame) ile tarif edilen ogeyi butun cercevelerde arar.

    Bulunana kadar (en gec `sure` ms) bekler; (cerceve, oge) doner.
    Bulunamazsa LookupError firlatir.
    """
    son_hata = [None]

    def dene():
        for fr in cerceveler(page):
            try:
                loc = kurucu(fr)
                if loc.count() == 0:
                    continue
                ilk = loc.first
                if not gorunur or ilk.is_visible():
                    return fr, ilk
            except Exception as e:  # cerceve gezinme sirasinda kopabiliyor
                son_hata[0] = e
        return None

    sonuc = kosulu_bekle(page, dene, sure, aralik_ms=300)
    if sonuc:
        return sonuc
    raise LookupError(f"Ogeye ulasilamadi (son hata: {son_hata[0]})")


def metinle_bul(page, metin, sure=15000):
    """Once butonun kendisi, sonra tam metin, en son metni iceren oge aranir.

    'Tamam' ve 'Vazgec' ayni kapsayicida oldugu icin kapsayiciya tiklamak
    yanlislikla Vazgec'e denk gelip secimi iptal ediyordu.
    """
    # ilk iki yontem kisa tutulur; bulunamayan her metin icin 3 kez tam sure
    # beklemek firma+menu adimlarinda saniyeler kaybettiriyordu
    pay = max(300, sure // 4)
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


def gorunur_mu(page, metin, sure=1500):
    """Sadece varlik kontrolu; tiklama icin kullanilmadigindan tek (hizli) arama yeter."""
    try:
        bul(page, lambda f: f.get_by_text(metin, exact=False), sure=sure)
        return True
    except LookupError:
        return False


def varsa_tikla(page, metinler, sure=1500, durul=True):
    """Metinlerden ilk bulunana tiklar; hicbiri yoksa None doner (hata firlatmaz).

    durul=False: tiklamadan sonra sayfaya gozlemci kurulmaz, eski surumdeki
    gibi kisa bir sure beklenir (Luca giris ekranlari icin; bkz. giris.py).
    """
    for metin in metinler:
        try:
            _, loc = metinle_bul(page, metin, sure=sure)
            loc.click()
        except Exception:
            continue
        if durul:
            sayfa_durulsun(page, azami_ms=400)
        else:
            geri_cekil(page, 0.4)
        return metin
    return None


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
            sayfa_durulsun(page, azami_ms=600)
            return True
        except Exception:
            pass
    return False


# Gorunur menu yazilari tek JS cagrisiyla alinir; oge basina is_visible +
# inner_text cagirmak cerceve basina yuzlerce gidis donus demekti
MENU_METNI_JS = """els => els.map(e => ({
  t: ((e.innerText || '').trim()).slice(0, 60),
  g: !!(e.offsetParent || e.getClientRects().length)
}))"""


def menu_metinleri(page, sinir=40):
    """Ekranda gorunen kisa yazilar (tani mesajlari ve modul tespiti icin)."""
    bulunan = []
    for fr in cerceveler(page):
        try:
            bilgiler = fr.locator("a, td, span").evaluate_all(MENU_METNI_JS)
        except Exception:
            continue
        for b in bilgiler:
            metin = (b.get("t") or "").strip()
            if b.get("g") and 3 <= len(metin) <= 40 and metin not in bulunan:
                bulunan.append(metin)
                if len(bulunan) >= sinir:
                    return bulunan
    return bulunan


def uyari_metinleri(page):
    """Ekranda gorunen 'Lütfen ...' yazilari (Luca uyarilari)."""
    bulunan = set()
    for fr in cerceveler(page):
        try:
            loc = fr.get_by_text("Lütfen", exact=False)
            for i in range(min(loc.count(), 10)):
                oge = loc.nth(i)
                if oge.is_visible():
                    bulunan.add(" ".join((oge.inner_text() or "").split())[:90])
        except Exception:
            continue
    return bulunan


def uyari_metni(page, onceki=frozenset()):
    """Yeni cikan Luca uyarisi (orn. 'Lutfen indirilecek faturalari seciniz'); yoksa None.

    onceki: islemden once ekranda zaten duran yazilar. Interaktif V.D. ekraninda
    "Lutfen faturalarinizla ekrandaki tutarlari kontrol ediniz" hep yaziyor;
    bu uyari sanilinca Excel beklenmeden birakiliyor, gec gelen dosya da
    tarayiciyi cokertiyordu.
    """
    yeni = sorted(uyari_metinleri(page) - set(onceki))
    return yeni[0] if yeni else None


def ekranda_gib_hatasi(page):
    """Islem Takip penceresi acilmadan ekrana dusen GIB hata uyarisi."""
    for fr in cerceveler(page):
        for metin in GIB_HATA_METINLERI:
            try:
                loc = fr.get_by_text(metin, exact=False)
                if loc.count() and loc.first.is_visible():
                    return True
            except Exception:
                continue
    return False


# --- Luca pencereleri (.luca-open-window) -----------------------------------

def acik_pencere(page):
    """Acik Luca penceresi. Kapanmazsa arkadaki butonlar tiklanamiyor."""
    for fr in cerceveler(page):
        try:
            loc = fr.locator(".luca-open-window")
            if loc.count() and loc.first.is_visible():
                return fr, loc.first
        except Exception:
            continue
    return None, None


def pencere_acik_mi(pencere):
    if pencere is None:
        return False
    try:
        return pencere.is_visible()
    except Exception:
        return False


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


def diyalog_bekle(page, capalar, azami_ms=4000):
    """Yazilarindan biri gorunen diyalog acilana kadar bekler; (cerceve, pencere) ya da (None, None)."""
    if isinstance(capalar, str):
        capalar = (capalar,)

    def bak():
        for capa in capalar:
            fr, pencere = metinli_diyalog(page, capa)
            if pencere is not None:
                return fr, pencere
        return None

    return kosulu_bekle(page, bak, azami_ms, aralik_ms=250) or (None, None)


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
                    sayfa_durulsun(page, azami_ms=600)
                    return metin
            except Exception:
                continue
    return None


def diyalogda_tikla(page, metinler, sure=4000):
    _, pencere = indirme_diyalogu(page)
    return pencerede_tikla(page, pencere, metinler, sure)


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
                sayfa_durulsun(page, azami_ms=1000)
                return True
        except Exception:
            continue
    return False


def _pencereyi_kapat_ve_bekle(page, pencere):
    if not pencerede_tikla(page, pencere, ["Tamam", "Kapat"]):
        varsa_tikla(page, ["Tamam"], sure=2000)
    kaybolana_kadar_bekle(pencere, 1000)


def bilgi_penceresini_kapat(page):
    """Sorgu sonucu bildiren pencereyi kapatir ve yazisini dondurur.

    Bu pencere ciktiginda sorgu bitmistir; Islem Takip penceresini beklemeye
    devam etmek bosuna zaman kaybi oluyordu.
    """
    for capa in BILGI_CAPALARI:
        _, pencere = metinli_diyalog(page, capa)
        if pencere is None:
            continue
        try:
            metin = " ".join((pencere.inner_text() or "").split())[:80]
        except Exception:
            metin = capa
        _pencereyi_kapat_ve_bekle(page, pencere)
        return metin
    return ""


def fatura_yok_penceresini_kapat(page):
    """'Her hangi bir fatura bulunamadi' penceresi Tamam beklerken akisi kilitliyor."""
    _, pencere = metinli_diyalog(page, FATURA_YOK_CAPASI)
    if pencere is None:
        return False
    if not pencerede_tikla(page, pencere, ["Tamam"]):
        varsa_tikla(page, ["Tamam"], sure=2000)
    kaybolana_kadar_bekle(pencere, 1000)
    return True


def acik_pencereleri_kapat(page, log=None):
    """Acik kalan Luca pencerelerini kapatir; hepsi kapandiysa True."""
    kapali = lambda: acik_pencere(page)[1] is None
    for deneme in range(4):
        fr, pencere = acik_pencere(page)
        if pencere is None:
            return True
        if deneme == 0 and log:
            yaz("    Acik Luca penceresi kapatiliyor", log)
        if varsa_tikla(page, ["Kapat"], sure=1500):
            kosulu_bekle(page, kapali, 600, aralik_ms=150)
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
        kosulu_bekle(page, kapali, 700, aralik_ms=150)
    return acik_pencere(page)[1] is None


def sayfayi_toparla(page):
    """Hata sonrasi acik kalan diyaloglari kapatir.

    Sayfa yeniden YUKLENMEZ: Luca uygulama adresine dogrudan gidilince oturumu
    reddedip "LUCA HATA" veriyor ve sonraki tum firmalar basarisiz oluyordu.
    """
    if not sayfa_canli(page):
        return
    acik_pencereleri_kapat(page)
    for _ in range(2):
        try:
            page.keyboard.press("Escape")
        except Exception:
            break
        sayfa_durulsun(page, azami_ms=300)


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
                sayfa_durulsun(page, azami_ms=400)
                return True
    except Exception:
        pass
    # radyo bulunamadiysa yazisina tiklamak da secimi yapar
    return bool(pencerede_tikla(page, pencere, [metin], sure=3000))


# --- tarih kutulari -----------------------------------------------------------

# Tum kutularin degeri/nitelikleri tek seferde okunur: her kutu icin ayri ayri
# is_visible/input_value/get_attribute cagirmak ekran basina 10-25 sn suruyordu.
KUTU_BILGISI = """els => els.map(el => ({
  d: el.value || '',
  n: ((el.name || '') + ' ' + (el.id || '') + ' ' + (el.className || '')).toLowerCase(),
  g: !!(el.offsetParent || el.getClientRects().length)
}))"""

TANI = {"son_kutu_hatasi": ""}  # tani icin: tek JS cagrisi neden tutmadi


def _kutu_bilgileri(kutular):
    """Kutularin degeri/nitelikleri: once tek JS cagrisi, olmazsa tek tek.

    Luca cerceveleri sik sik yeniden yuklendigi icin JS calistirma
    "execution context destroyed" ile dusebiliyor; o zaman yavas ama
    saglam olan eski yola donulur.
    """
    try:
        bilgiler = kutular.evaluate_all(KUTU_BILGISI)
        if bilgiler:
            return bilgiler
    except Exception as e:
        TANI["son_kutu_hatasi"] = type(e).__name__
    try:
        sayi = min(kutular.count(), 80)
    except Exception as e:
        TANI["son_kutu_hatasi"] = type(e).__name__
        return []
    bilgiler = []
    for i in range(sayi):
        try:
            kutu = kutular.nth(i)
            nitelik = " ".join(x for x in (kutu.get_attribute("name"), kutu.get_attribute("id"),
                                           kutu.get_attribute("class")) if x)
            bilgiler.append({"d": kutu.input_value() or "", "n": nitelik.lower(),
                             "g": kutu.is_visible()})
        except Exception:
            bilgiler.append({"d": "", "n": "", "g": False})
    return bilgiler


def _tarih_kutulari(kapsayici):
    try:
        kutular = kapsayici.locator("input[type=text], input:not([type])")
    except Exception:
        return []
    return [kutular.nth(i) for i, b in enumerate(_kutu_bilgileri(kutular))
            if b.get("g") and (TARIH_DESENI.search(b.get("d") or "")
                               or TARIH_NITELIGI.search(b.get("n") or ""))]


def tarih_kutulari(page, kapsam=None, sure=6000):
    """Tarih kutulari; kapsam (acik pencere) verilirse once orada aranir.

    Tum sayfa taranirsa ekranin arkasindaki suzgec kutulari one geciyor ve
    tarih acik pencereye degil listeye yaziliyordu. Pencere hazir olmadan
    bakilirsa kutu bulunamadigi icin kutular gorunene kadar beklenir.
    """
    son = [[]]

    def bak():
        adaylar = _tarih_kutulari(kapsam) if kapsam is not None else []
        if len(adaylar) < 2:
            hepsi = []
            for fr in cerceveler(page):
                hepsi.extend(_tarih_kutulari(fr))
            if len(hepsi) > len(adaylar):
                adaylar = hepsi
        son[0] = adaylar
        return adaylar if len(adaylar) >= 2 else None

    return kosulu_bekle(page, bak, sure, aralik_ms=400) or son[0]


def kutuya_yaz(kutu, deger):
    """Kutuya yazar ve gercekten yazildigini dogrular; uc yol sirayla denenir."""
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


def tarih_araligi_yaz(kutular, bas, bit):
    """Ilk iki tarih kutusuna aralik yazar; kutularda gercekten ne yazdigini dondurur."""
    kutuya_yaz(kutular[0], bas)
    kutuya_yaz(kutular[1], bit)
    try:
        return f"{kutular[0].input_value()} - {kutular[1].input_value()}"
    except Exception:
        return f"{bas} - {bit}"


# --- tani ---------------------------------------------------------------------

def hata_kaydet(page, klasor, ad):
    """Hata aninin ekran goruntusu ve sayfa kaydi (sonradan inceleme icin).

    Kaydedilen ekran goruntusunun yolunu dondurur (kaydedilemediyse "").
    """
    klasor = Path(klasor)
    klasor.mkdir(parents=True, exist_ok=True)
    dosya = dosya_adi_yap(ad)
    goruntu = klasor / f"{dosya}.png"
    try:
        page.screenshot(path=str(goruntu), full_page=True, timeout=15000)
    except Exception:
        goruntu = None
    try:
        (klasor / f"{dosya}.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    return str(goruntu) if goruntu else ""
