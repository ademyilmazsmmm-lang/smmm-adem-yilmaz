# -*- coding: utf-8 -*-
"""Luca'da gezinme: firma secimi, calisma donemi ve menuden ekrana gitme."""

import time

from .bekleme import (degisiklik_baslat, degisip_durulsun, kosulu_bekle,
                      sayfa_durulsun)
from .luca_ekran import (acik_pencereleri_kapat, cerceveler, gorunur_mu,
                         menu_metinleri, metinle_bul, sayfayi_toparla,
                         varsa_tikla)
from .ortak import AYAR, karsilastir, sadelestir, tarih_cozumle, yaz
from .sabitler import (BELGE_TIPLERI, DONEM_DESENI, GIB_GETIR, IKI_KADEMELI,
                       INTERAKTIF_LISTELE, KAPAT_METINLERI, MENU_KELIMELERI,
                       MODUL_ADAYLARI, UST_MENU)


# --- firma listesi ------------------------------------------------------------

def menu_listesi_mi(secenekler):
    isabet = sum(1 for s in secenekler if any(k in sadelestir(s) for k in MENU_KELIMELERI))
    return isabet >= 3


def firma_adaylari(page):
    """Ekrandaki (en az 5 secenekli) gorunur listeler: [(cerceve, liste, secenekler)]."""
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


def firma_sayisi(page):
    """Sayfadaki firma listesinde kac firma var (liste yuklenmis mi kontrolu)."""
    try:
        return len(firma_secici(page)[2])
    except Exception:
        return 0


def firma_dogrula(page, firma_adi, sure=8000):
    """Secim gerceklesti mi: sekme basligi secili firmanin adini tasiyor (orn. 'DENTAL [ 2026 ]')."""
    hedef = sadelestir(firma_adi)
    if not hedef:
        return False
    return bool(kosulu_bekle(page, lambda: hedef in sadelestir(page.title()), sure, aralik_ms=300))


def firma_sec(page, firma_adi, log=None):
    """Firmanin bulundugu listeyi adiyla secer; secim 'Tamam' ile onaylanip dogrulanir."""
    # giris sonrasi acik kalan bilgi penceresi Tamam'a basilmasini engelliyordu
    varsa_tikla(page, KAPAT_METINLERI, sure=600)
    acik_pencereleri_kapat(page)

    def listeyi_bul():
        for _, sec, secenekler in firma_adaylari(page):
            if firma_adi in secenekler:
                return sec
        return None

    hedef = listeyi_bul()
    for _ in range(2):  # onceki firmadan sonra liste gec yuklenebiliyor
        if hedef is not None:
            break
        acik_pencereleri_kapat(page)
        hedef = kosulu_bekle(page, listeyi_bul, 3000, aralik_ms=500)
    if hedef is None:
        raise LookupError(f"'{firma_adi}' acik listelerin hicbirinde bulunamadi")

    for _ in range(3):
        try:
            hedef.select_option(label=firma_adi, timeout=15000)
        except Exception:
            pass
        # onay butonu secimden sonra beliriyor; varsa_tikla onu bekler
        varsa_tikla(page, ["Tamam"], sure=3000)
        if firma_dogrula(page, firma_adi):
            break
        varsa_tikla(page, KAPAT_METINLERI, sure=1200)
        sayfayi_toparla(page)  # gorunmez diyalog Tamam'i engelliyor olabilir
        sayfa_durulsun(page, azami_ms=1000)
    else:
        # dogrulanmadan devam edilirse baska firmanin faturalari cekilir; bu firmayi atla
        raise LookupError(f"'{firma_adi}' secimi onaylanamadi (Tamam gecmedi), firma atlandi")

    # firma degisince Luca cerceveleri yeniden yukluyor; bitmesi beklenir
    sayfa_durulsun(page, azami_ms=5000, sessizlik_ms=400)


# --- calisma donemi ---------------------------------------------------------

def donem_araligi(metin):
    eslesme = DONEM_DESENI.search(metin or "")
    if not eslesme:
        return None, None
    return (tarih_cozumle(eslesme.group(1).replace(".", "/")),
            tarih_cozumle(eslesme.group(2).replace(".", "/")))


def calisma_donemi(page):
    """Firma adinin altindaki donem kutusu (orn. '08/04/2022 - 31/12/2022')."""
    for fr in cerceveler(page):
        try:
            kutular = fr.locator("select")
            for i in range(min(kutular.count(), 12)):
                bas, bit = donem_araligi(secili_metin(kutular.nth(i)))
                if bas:
                    return bas, bit
        except Exception:
            continue
    return None, None


def donem_secici(page):
    """Calisma donemi listesi: secenekleri '01/01/2026 - 31/12/2026' bicimindeki select."""
    for fr in cerceveler(page):
        try:
            kutular = fr.locator("select")
            for i in range(min(kutular.count(), 12)):
                sec = kutular.nth(i)
                secenekler = [m.strip() for m in sec.locator("option").all_inner_texts()]
                if any(DONEM_DESENI.search(m) for m in secenekler):
                    return sec, secenekler
        except Exception:
            continue
    return None, []


def donem_ortusuyor(bas, bit, istenen_bas, istenen_bit):
    """Donem okunamadiysa (None) engel cikarilmaz, sorgu denenir."""
    if bit and bit < istenen_bas:
        return False
    if bas and bas > istenen_bit:
        return False
    return True


def uygun_donem(secenekler, istenen_bas, istenen_bit):
    """Istenen yila ait donemi secer.

    Ayni yil farkli firmalarda farkli basliyor: yeni kurulanda
    '15/04/2026 - 31/12/2026', eskide '01/01/2026 - 31/12/2026'. Bu yuzden
    once yil tutturulur, gun/ay onemli degil.
    """
    adaylar = []
    for metin in secenekler:
        bas, bit = donem_araligi(metin)
        if bit and donem_ortusuyor(bas, bit, istenen_bas, istenen_bit):
            adaylar.append((metin, bit))
    if not adaylar:
        return None
    for yil in (istenen_bit.year, istenen_bas.year):
        for metin, bit in adaylar:
            if bit.year == yil:
                return metin
    return adaylar[0][0]


def donem_ayarla(page, firma_adi, istenen_bas, istenen_bit, log=None):
    """Firma eski donemde acilmissa uygun donemi secer; yoksa False doner.

    Luca her firmada en son kullanilan donemi hatirliyor. Acik bir firma 2025
    doneminde kalmis olabiliyor; bunlari atlamak yerine donemi degistirmek
    gerekiyor. Gercekten kapanmis firmalarda uygun donem secenegi bulunmaz.
    """
    bas, bit = calisma_donemi(page)
    if donem_ortusuyor(bas, bit, istenen_bas, istenen_bit):
        return True

    if not AYAR["donem_degistir"]:
        yaz(f"    Firma donemi {bas:%d/%m/%Y}-{bit:%d/%m/%Y}, donem degistirme kapali", log)
        return False

    sec, secenekler = donem_secici(page)
    if sec is None:
        yaz("    Donem listesi bulunamadi, sorgu yine de denenecek", log)
        return True

    uygun = uygun_donem(secenekler, istenen_bas, istenen_bit)
    if uygun is None:
        yaz(f"    Firma donemi {bas:%d/%m/%Y}-{bit:%d/%m/%Y}, uygun donem secenegi yok", log)
        return False

    yaz(f"    Donem degistiriliyor: {uygun}", log)
    for _ in range(2):
        try:
            sec.select_option(label=uygun, timeout=10000)
        except Exception:
            pass
        baslangic = degisiklik_baslat(page)
        varsa_tikla(page, ["Tamam"], sure=3000)
        # donem degisince Luca sayfayi tazeliyor; bitmeden bakilirsa eski donem okunur
        degisip_durulsun(page, baslangic, azami_ms=6000, degisim_ms=2000, sessizlik_ms=400)
        if donem_ortusuyor(*calisma_donemi(page), istenen_bas, istenen_bit):
            if firma_dogrula(page, firma_adi, sure=6000):
                return True
            yaz("    UYARI: donem degisti ama firma dogrulanamadi, atlandi", log)
            return False
        acik_pencereleri_kapat(page)
        sec, _ = donem_secici(page)
        if sec is None:
            break
    yaz("    UYARI: donem degistirilemedi", log)
    return False


# --- menu -------------------------------------------------------------------

_SON_MODUL = {"ad": None}  # ilk firmada calisan modul adi; sonraki firmalarda once bu denenir


def ekrandaki_modul(page):
    """Ust cubukta gercekten duran modul adi; yoksa None.

    Dokuz adayi tek tek tiklamayi denemek yerine once ekranda hangisinin
    yazdigina bakilir: bir JS cagrisi, dokuz bosa arama yerine.
    """
    try:
        gorunen = {karsilastir(m) for m in menu_metinleri(page, sinir=80)}
    except Exception:
        return None
    for modul in MODUL_ADAYLARI:
        k = karsilastir(modul)
        if k and any(g.startswith(k) for g in gorunen):
            return modul
    return None


def menu_ogesini_ac(page, metin, sure=4000, dogrula=None):
    """Eski Luca menuleri kimi yerde hover, kimi yerde tiklama ile aciliyor.

    dogrula verilirse (orn. alt menu gorundu mu) menunun acildigi ona sorulur;
    dogrula'nin kendisi gorunene kadar bekledigi icin ayrica beklenmez.
    """
    try:
        _, oge = metinle_bul(page, metin, sure=sure)
    except LookupError:
        return False
    for eylem in ("hover", "click"):
        try:
            getattr(oge, eylem)()
        except Exception:
            continue
        if dogrula is None:
            sayfa_durulsun(page, azami_ms=700)
            return True
        if dogrula():
            return True
    return bool(dogrula()) if dogrula else True


def modul_menusunu_ac(page, dogrula):
    """Modul menusunu (Isletme Defteri vb.) acar.

    Dokuz aday sirayla denenince her ekranda saniyeler gidiyordu; bir kez
    calisan ad hatirlanip sonraki cagrilarda ilk sirada deneniyor.
    """
    adaylar = list(MODUL_ADAYLARI)
    one_al = [m for m in (_SON_MODUL["ad"], ekrandaki_modul(page)) if m in adaylar]
    for m in reversed(one_al):  # ekranda gorunen en one, sonra son calisan
        adaylar.remove(m)
        adaylar.insert(0, m)
    for modul in adaylar:
        if menu_ogesini_ac(page, modul, sure=1200, dogrula=dogrula):
            _SON_MODUL["ad"] = modul
            return True
    return False


def _cerceve_imzasi(page):
    """Acik cercevelerin adresleri: ekran degisti mi anlamak icin."""
    try:
        return tuple(sorted(f.url for f in page.frames))
    except Exception:
        return ()


def ekran_hazir_bekle(page, isaret, onceki_imza=None, azami=6000):
    """Menu tiklandiktan sonra ekranin kendi butonu gorunene kadar bekler.

    "GİB'den Getir" her ekranda var; yeni ekran acilmadan onceki ekranin
    butonunu gorup devam edersek yanlis ekrani sorgulariz. Once cerceve
    adreslerinin degismesi beklenir; 2 saniye sonra bu kontrol birakilir
    (kimi ekran ayni adrese yukleniyor).
    """
    basla = time.monotonic()
    if onceki_imza:
        kosulu_bekle(page, lambda: _cerceve_imzasi(page) != onceki_imza,
                     min(2000, azami), aralik_ms=150)
    kalan = max(0, azami - (time.monotonic() - basla) * 1000)
    return bool(kosulu_bekle(page, lambda: gorunur_mu(page, isaret, sure=400),
                             kalan, aralik_ms=200))


def _ekrana_gec(page, madde, isaret, azami):
    """Menu maddesine tiklar; ekranin kendi butonu gorunduyse True."""
    onceki_imza = _cerceve_imzasi(page)
    madde.click(timeout=8000)
    if ekran_hazir_bekle(page, isaret, onceki_imza, azami=azami):
        return True
    sayfa_durulsun(page, azami_ms=3000)
    return gorunur_mu(page, isaret, sure=1000)


def modul_menusunden_git(page, hedef, isaret=None):
    """Modul menusu (orn. Isletme Defteri) -> madde. Ara menu yok."""
    hedef_gorunur = lambda: gorunur_mu(page, hedef, sure=1200)
    for _ in range(3):
        if not hedef_gorunur():
            modul_menusunu_ac(page, hedef_gorunur)
        try:
            _, madde = metinle_bul(page, hedef, sure=8000)
        except LookupError:
            sayfa_durulsun(page, azami_ms=1000)
            continue
        return _ekrana_gec(page, madde, isaret or hedef, azami=8000)
    raise LookupError(f"'{hedef}' menu maddesi bulunamadi. Gorunen menuler: {menu_metinleri(page)}")


def menuye_git(page, belge_tipi):
    """Belge tipinin ekranini menuden acar.

    Ekranin kendi butonu (GİB'den Getir / Listele) gorunduyse True; menu
    tiklandi ama ekran gelmediyse False (orn. firmada o modul yok).
    """
    hedef = BELGE_TIPLERI[belge_tipi]
    # Ekran acildiginda mutlaka gorunen buton: bekleme bunu gorunce biter
    isaret = INTERAKTIF_LISTELE if belge_tipi in IKI_KADEMELI else GIB_GETIR
    if belge_tipi in IKI_KADEMELI:
        return modul_menusunden_git(page, hedef, isaret)
    ust_gorunur = lambda: gorunur_mu(page, UST_MENU, sure=1200)
    hedef_gorunur = lambda: gorunur_mu(page, hedef, sure=1200)

    alt = None
    for deneme in range(3):  # menu kimi zaman hover'da acilip hemen kapaniyor
        if not ust_gorunur():
            if not modul_menusunu_ac(page, ust_gorunur):
                if deneme == 2:
                    raise LookupError(
                        f"'{UST_MENU}' menusu acilamadi. Sayfada gorunen menuler: {menu_metinleri(page)}")
                sayfa_durulsun(page, azami_ms=1000)
                continue

        # ust menu her seferinde acilir: ekran basligi da hedef metni icerebildigi
        # icin "zaten gorunuyor" kontrolune guvenip menuyu atlamak yanlis ekrana
        # tiklamaya yol aciyor
        menu_ogesini_ac(page, UST_MENU, sure=6000, dogrula=hedef_gorunur)
        try:
            _, alt = metinle_bul(page, hedef, sure=4000)
            break
        except LookupError:
            sayfa_durulsun(page, azami_ms=1000)

    if alt is None:
        raise LookupError(f"'{hedef}' menu maddesi bulunamadi. Gorunen menuler: {menu_metinleri(page)}")
    return _ekrana_gec(page, alt, isaret, azami=6000)
