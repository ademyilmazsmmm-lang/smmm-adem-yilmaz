# -*- coding: utf-8 -*-
"""Dinamik bekleme: Selenium'daki WebDriverWait(...).until(...) karsiligi.

Bot Playwright kullaniyor; Playwright'in tiklama/yazma islemleri zaten
ogenin hazir olmasini kendisi bekliyor. Luca ise cercevelere (frame)
dagilmis eski bir uygulama: ekran degisti mi, pencere acildi mi, liste
doldu mu gibi durumlari Playwright tek basina bilemiyor. Eskiden bu
yerlerde "2 saniye bekle" gibi sabit beklemeler vardi; site hizliyken
bosuna zaman gidiyor, yavasken yetmiyordu.

Artik her bekleme bir KOSULA baglidir:

    kosulu_bekle(page, lambda: pencere_acik_mi(...), azami_ms=5000)
        kosul saglanir saglanmaz doner; saglanmazsa en gec azami_ms sonra
        None doner (hata firlatmaz, cagiran ne yapacagina kendisi karar verir).

    sayfa_durulsun(page, azami_ms=3000)
        belirli bir isaret yoksa: sayfadaki (butun cercevelerdeki) DOM
        degisiklikleri ve bekleyen ag istekleri durulana kadar bekler.

    geri_cekil(page, saniye)
        bilincli bekleme: GIB sunucusuna ust uste sorgu atmadan once nefes
        payi. Sayfanin hazir olmasiyla ilgisi yoktur.

Programin baska hicbir yerinde dogrudan bekleme (wait_for_timeout / sleep)
yoktur; hepsi bu modulden gecer.
"""

import time

# Ag istegi bu surede bitmediyse (uzun sorgu / canli baglanti) "bekleyen"
# sayilmaz; aksi halde sayfa hic durulmamis gorunurdu.
ISTEK_ZAMAN_ASIMI = 15.0
IZLENEN_ISTEKLER = {"document", "xhr", "fetch"}

# her cercevede bir kez kurulur; son DOM degisikliginden bu yana gecen ms'yi dondurur
DURULMA_JS = """() => {
  const w = window;
  if (!w.__lucaBotSon) {
    w.__lucaBotSon = performance.now();
    try {
      new MutationObserver(() => { w.__lucaBotSon = performance.now(); })
        .observe(document, {subtree: true, childList: true, attributes: true, characterData: true});
    } catch (e) {}
  }
  return performance.now() - w.__lucaBotSon;
}"""

_bekleyen_istekler = {}  # context -> {istek: baslangic}


def sayfa_canli(page):
    try:
        return page is not None and not page.is_closed()
    except Exception:
        return False


def nabiz(page, ms):
    """Bekleme dongulerinin tek adimi.

    time.sleep yerine page.wait_for_timeout kullanilir: bu sirada Playwright
    olaylari (indirme, istek yakalama, acilir pencere) islenmeye devam eder.
    Dogrudan cagrilmaz; kosulu_bekle ve benzerleri kullanir.
    """
    ms = max(1, int(ms))
    try:
        page.wait_for_timeout(ms)
    except Exception:
        time.sleep(ms / 1000)


def kosulu_bekle(page, kosul, azami_ms, aralik_ms=200, en_az_ms=0):
    """kosul() dogru bir deger dondurene kadar bekler (WebDriverWait.until).

    kosul icinde olusan hatalar "henuz degil" sayilir: Luca cerceveleri
    yeniden yuklenirken ara sira "execution context destroyed" gibi hatalar
    dogal olarak cikiyor. Sayfa kapanirsa beklemeden None doner.
    en_az_ms: kosul bu sure dolmadan kontrol edilmez (onceki islemden kalan
    bir pencerenin yanlislikla "yeni" sanilmamasi icin).
    """
    basla = time.monotonic()
    while True:
        gecen = (time.monotonic() - basla) * 1000
        if gecen >= en_az_ms:
            try:
                sonuc = kosul()
            except Exception:
                sonuc = None
            if sonuc:
                return sonuc
        if gecen >= azami_ms or not sayfa_canli(page):
            return None
        nabiz(page, min(aralik_ms, max(1, azami_ms - gecen)))


def _istek_izleyici_kur(ctx):
    kayit = {}
    _bekleyen_istekler[ctx] = kayit

    def basladi(istek):
        try:
            if istek.resource_type in IZLENEN_ISTEKLER:
                kayit[istek] = time.monotonic()
        except Exception:
            pass

    def bitti(istek):
        kayit.pop(istek, None)

    try:
        ctx.on("request", basladi)
        ctx.on("requestfinished", bitti)
        ctx.on("requestfailed", bitti)
    except Exception:
        pass
    return kayit


def bekleyen_istek_var(page):
    """Sayfanin tarayici baglaminda henuz yaniti gelmemis ag istegi var mi."""
    try:
        ctx = page.context
    except Exception:
        return False
    kayit = _bekleyen_istekler.get(ctx)
    if kayit is None:
        _istek_izleyici_kur(ctx)
        return False
    simdi = time.monotonic()
    for istek, basla in list(kayit.items()):
        if simdi - basla > ISTEK_ZAMAN_ASIMI:
            kayit.pop(istek, None)
    return bool(kayit)


def _dom_sessiz_ms(page):
    """Butun cercevelerde son DOM degisikliginden bu yana gecen en kisa sure."""
    en_kisa = None
    for fr in list(page.frames):
        try:
            gecen = fr.evaluate(DURULMA_JS)
        except Exception:
            return 0  # cerceve yeniden yukleniyor: sayfa henuz durulmadi
        if isinstance(gecen, (int, float)):
            en_kisa = gecen if en_kisa is None else min(en_kisa, gecen)
    return en_kisa or 0


def sayfa_durulsun(page, azami_ms=3000, sessizlik_ms=300, en_az_ms=100):
    """Sayfa "sakinlesene" kadar bekler: DOM degismiyor ve ag istegi yok.

    Belirli bir buton/pencere beklenemeyen yerlerde (tiklamanin etkisi
    gorunmez oldugunda) kullanilir. Sayfa sessizlik_ms boyunca degismezse
    hemen doner; hic durulmazsa en gec azami_ms sonra doner, yani eski sabit
    bekleme suresinden daha uzun surmez. Durulduysa True doner.
    """
    def sakin():
        if bekleyen_istek_var(page):
            return False
        return _dom_sessiz_ms(page) >= sessizlik_ms

    return bool(kosulu_bekle(page, sakin, azami_ms, aralik_ms=100, en_az_ms=en_az_ms))


def degisiklik_baslat(page):
    """Bir islemden (Yenile, Belge Ara...) HEMEN ONCE cagrilir; degisip_durulsun'a verilir.

    Sayfadaki degisiklik gozlemcilerini kurar ve baslangic anini dondurur.
    """
    _dom_sessiz_ms(page)
    return time.monotonic()


def degisip_durulsun(page, baslangic, azami_ms=15000, degisim_ms=3000, sessizlik_ms=500):
    """Islemin etkisi GORULENE kadar, sonra sayfa durulana kadar bekler.

    Yalnizca "sayfa sakin mi" diye bakmak, islem sunucuya gitmeden once
    sayfa zaten sakinken yaniltiyordu (liste henuz yenilenmeden okunuyordu).
    Once bir degisiklik (DOM degisimi ya da ag istegi) beklenir; en gec
    degisim_ms icinde hic degisiklik olmazsa beklemeden devam edilir.
    """
    def degisti():
        if bekleyen_istek_var(page):
            return True
        return _dom_sessiz_ms(page) < (time.monotonic() - baslangic) * 1000

    kosulu_bekle(page, degisti, degisim_ms, aralik_ms=100)
    kalan = azami_ms - (time.monotonic() - baslangic) * 1000
    return sayfa_durulsun(page, azami_ms=max(0, kalan), sessizlik_ms=sessizlik_ms, en_az_ms=0)


def gorunene_kadar_bekle(loc, azami_ms):
    """Playwright ogesi gorunur olana kadar bekler; olmazsa False (hata firlatmaz)."""
    try:
        loc.wait_for(state="visible", timeout=azami_ms)
        return True
    except Exception:
        return False


def kaybolana_kadar_bekle(loc, azami_ms):
    """Oge (orn. kapatilan pencere) gorunmez olana kadar bekler; olmazsa False."""
    try:
        loc.wait_for(state="hidden", timeout=azami_ms)
        return True
    except Exception:
        return False


def geri_cekil(page, saniye):
    """Bilincli, sureli bekleme. Yalnizca iki yerde kullanilir:

      * GIB bir faturayi veremediginde ayni sorguyu hemen tekrarlamadan once;
      * Luca girisinde (giris.py): Luca oturumu arka planda kuruyor ve bunu
        gosteren bir isaret yok. Erken davranilinca uygulama penceresi bos
        aciliyordu; burada sahada calistigi kanitlanmis eski sureler korunur.

    Sayfa bu sirada canli tutulur (Playwright olaylari islenir).
    """
    bitis = time.monotonic() + saniye
    while time.monotonic() < bitis and sayfa_canli(page):
        nabiz(page, min(500, (bitis - time.monotonic()) * 1000))
