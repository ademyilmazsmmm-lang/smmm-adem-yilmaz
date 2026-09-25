# -*- coding: utf-8 -*-
"""LUCA GIRIS: otomatik giris, iki asamali dogrulama, urun secimi, oturum yenileme.

Giris bilgileri (uye no, kullanici adi, parola) ayarlar.json'da varsa bot
girisi kendisi yapar. Yoksa ya da bir engel cikarsa (captcha, SMS kodu)
kullanicinin elle girmesi beklenir; gece modunda (--bitince-kapat) ise
bekleyecek kimse olmadigi icin calisma baslatilmaz.
"""

from .bekleme import kosulu_bekle, sayfa_durulsun
from .luca_ekran import cerceveler, gorunur_mu, kutuya_yaz, varsa_tikla
from .ortak import yaz
from .sabitler import (CAPTCHA_ISARETLERI, DOGRULAMA_ISARETLERI, DOGRULAMA_ONAY,
                       GIRIS_DUGMESI, GIRIS_SAYFASI, KAPAT_METINLERI,
                       SISTEM_GIRIS, URUN_ADAYLARI, UYGULAMA_PARCASI)
from .tarayici import (duraklamalari_engelle, giris_adresi, kullanici_bekle,
                       sayfalari_ozetle, uygulama_sayfasi_bul)


def giris_bilgileri(ayarlar):
    """ayarlar.json'daki giris bilgileri; eksikse None."""
    uye = str(ayarlar.get("uye_no") or "").strip()
    kullanici = str(ayarlar.get("kullanici_adi") or "").strip()
    parola = str(ayarlar.get("parola") or "")
    return (uye, kullanici, parola) if uye and kullanici and parola else None


def _sayfada_yazi_var(page, metinler):
    """Metinlerden biri sayfanin herhangi bir cercevesinde geciyor mu (tek hizli bakis)."""
    kucuk = [m.lower() for m in metinler]
    for fr in cerceveler(page):
        try:
            icerik = (fr.locator("body").inner_text(timeout=1000) or "").lower()
        except Exception:
            continue
        if any(m in icerik for m in kucuk):
            return True
    return False


def dogrulama_ekrani_mi(page):
    """Girisden sonra iki asamali dogrulama ekrani cikmis mi; ciktiysa isaret yazisini dondurur."""
    for isaret in DOGRULAMA_ISARETLERI:
        if gorunur_mu(page, isaret, sure=800):
            return isaret
    return ""


def captcha_ekrani_mi(page):
    """Captcha ekrani: iki asamali dogrulama kapaliyken Luca bunu soruyor."""
    for isaret in CAPTCHA_ISARETLERI:
        if gorunur_mu(page, isaret, sure=800):
            return isaret
    return ""


def dogrulama_kodu(ayarlar, log=None):
    """ayarlar.json'daki gizli anahtardan o anki dogrulama kodunu uretir.

    Luca'da iki asamali dogrulamayi "kimlik dogrulayici uygulama" ile
    acarsaniz kurulum ekranindaki gizli anahtari dogrulama_anahtari alanina
    yazin; kodu bot kendisi hesaplar ve giris tumuyle otomatik olur.
    Uretilemezse sebebi yazilir.
    """
    anahtar = str(ayarlar.get("dogrulama_anahtari") or "").replace(" ", "")
    if not anahtar:
        yaz("    ayarlar.json'da dogrulama_anahtari yok, kod elle girilmeli", log)
        return ""
    try:
        import pyotp
    except ImportError:
        yaz("    pyotp kurulu degil (kurulum.bat calistirin), kod elle girilmeli", log)
        return ""
    try:
        return pyotp.TOTP(anahtar).now()
    except Exception as e:
        yaz(f"    Dogrulama kodu uretilemedi ({type(e).__name__}), anahtari kontrol edin", log)
        return ""


def dogrulama_kodunu_gir(page, kod):
    """Dogrulama kodunu ekrandaki kutuya yazip onaylar."""
    for secici in ("input[type=text]:visible", "input[type=tel]:visible",
                   "input[type=number]:visible", "input[type=password]:visible"):
        try:
            loc = page.locator(secici)
            if not loc.count():
                continue
            kutu = loc.first
            kutuya_yaz(kutu, kod)
            if not varsa_tikla(page, DOGRULAMA_ONAY, sure=4000):
                kutu.press("Enter")
            # kod gonderilince sayfa degisir; yeni ekran gelip oturana kadar beklenir
            sayfa_durulsun(page, azami_ms=4000, sessizlik_ms=500, en_az_ms=500)
            return True
        except Exception:
            continue
    return False


def uygulama_penceresi_acik(page):
    """Tarayicinin herhangi bir penceresinde Luca uygulamasi (/Luca/ adresi) acik mi.

    Urun secilince uygulama AYRI bir pencerede aciliyor (orn. .../Luca/ssoGiris.do);
    giris sekmesi oldugu gibi kaliyor. Yalnizca giris sekmesine bakilirsa uygulama
    acilmamis sanilip urune tekrar tiklaniyor, ikinci oturum ilkini bozuyordu.
    """
    try:
        sayfalar = [page] + [p for p in page.context.pages if p is not page]
    except Exception:
        sayfalar = [page]
    for p in sayfalar:
        try:
            if not p.is_closed() and UYGULAMA_PARCASI in p.url:
                return True
        except Exception:
            continue
    return False


def urun_sec(page, log=None, sure=30000):
    """Giris sonrasi cikan urun secim ekranindan Mali Musavir paketini secer.

    Kutular giristen birkac saniye sonra beliriyor; biri gorunene ya da
    uygulama acilana kadar beklenir. Uygulama herhangi bir pencerede aciksa
    (ya da aciliyorsa) urune bir daha TIKLANMAZ.
    """
    def dene():
        if uygulama_penceresi_acik(page):  # uygulama zaten acik / aciliyor
            return "acik"
        tiklanan = varsa_tikla(page, URUN_ADAYLARI, sure=1200)
        if tiklanan:
            yaz(f"    Urun secildi: {tiklanan}", log)
            # uygulama yeni pencerede aciliyor; o pencere gorunene kadar beklenir
            if not kosulu_bekle(page, lambda: uygulama_penceresi_acik(page), 20000, aralik_ms=300):
                yaz("    UYARI: urun secildi ama Luca uygulama penceresi 20 sn icinde acilmadi", log)
            return tiklanan
        return None

    try:
        return bool(kosulu_bekle(page, dene, sure, aralik_ms=1000))
    except Exception:
        return False


def _giris_formu_hazir(page):
    try:
        return (page.locator("input[type=password]:visible").count() > 0
                and page.locator("input[type=text]:visible, input:not([type]):visible").count() >= 2)
    except Exception:
        return False


def otomatik_giris(page, ayarlar, log):
    """Luca girisini ayarlar.json'daki bilgilerle kendisi yapar.

    Bilgiler eksikse ya da form bulunamazsa False doner; bu durumda
    kullanici elle giris yapar, akis degismez.
    """
    bilgiler = giris_bilgileri(ayarlar)
    if bilgiler is None:
        return False
    uye, kullanici, parola = bilgiler
    yaz("Otomatik giris yapiliyor...", log)
    try:
        if UYGULAMA_PARCASI in page.url:  # oturum zaten acik
            return True
        if "giris.erp" not in page.url.lower():
            varsa_tikla(page, SISTEM_GIRIS, sure=5000)
            kosulu_bekle(page, lambda: "giris.erp" in page.url.lower(), 2500, aralik_ms=250)
        if "giris.erp" not in page.url.lower():
            page.goto(GIRIS_SAYFASI)

        if not kosulu_bekle(page, lambda: _giris_formu_hazir(page), 10000, aralik_ms=300):
            yaz("UYARI: giris formu bulunamadi, elle giris yapin", log)
            return False
        parolalar = page.locator("input[type=password]:visible")
        metinler = page.locator("input[type=text]:visible, input:not([type]):visible")
        kutuya_yaz(metinler.nth(0), uye)
        kutuya_yaz(metinler.nth(1), kullanici)
        kutuya_yaz(parolalar.first, parola)
        if not varsa_tikla(page, GIRIS_DUGMESI, sure=5000):
            parolalar.first.press("Enter")

        # giris sonrasi: sayfa degisene ya da captcha/dogrulama cikana kadar
        engel = CAPTCHA_ISARETLERI + DOGRULAMA_ISARETLERI
        kosulu_bekle(page, lambda: ("giris.erp" not in page.url.lower()
                                    or _sayfada_yazi_var(page, engel)),
                     15000, aralik_ms=500)
        sayfa_durulsun(page, azami_ms=6000, sessizlik_ms=700, en_az_ms=500)

        if captcha_ekrani_mi(page):
            yaz("    Captcha ekrani cikti; bot bunu gecemez.", log)
            yaz("    Luca'da iki asamali dogrulamayi acarsaniz captcha kalkar"
                " (Luca bunu giris ekraninda kendisi yaziyor).", log)
            return False

        isaret = dogrulama_ekrani_mi(page)
        if isaret:
            kod = dogrulama_kodu(ayarlar, log)
            if kod and dogrulama_kodunu_gir(page, kod):
                yaz("    Dogrulama kodu girildi", log)
                if not dogrulama_ekrani_mi(page):
                    urun_sec(page, log)
                    return True
                yaz("    UYARI: dogrulama kodu kabul edilmedi", log)
            # kod uretilemiyorsa (SMS vb.) elle girilmesi beklenir
            dakika = max(0, int(ayarlar.get("dogrulama_bekleme_dakika", 5)))
            yaz(f"    Iki asamali dogrulama ekrani ('{isaret}')."
                f" Kodu elle girin, {dakika} dk bekleniyor...", log)
            kosulu_bekle(page, lambda: not dogrulama_ekrani_mi(page), dakika * 60000, aralik_ms=3000)
            if dogrulama_ekrani_mi(page):
                yaz("    UYARI: dogrulama tamamlanmadi, giris yapilamadi", log)
                return False
            yaz("    Dogrulama tamamlandi", log)

        urun_sec(page, log)  # urun secim ekrani cikarsa
        return True
    except Exception as e:
        yaz(f"UYARI: otomatik giris yapilamadi ({type(e).__name__}), elle giris yapin", log)
        return False


def oturumu_yenile(page, ctx, ayarlar, log):
    """Luca oturumu dustugunde giris sayfasina donup yeniden girer.

    Oturum dustugunde ekranda ne menu ne firma listesi kaliyor; bot bunu
    firma hatasi sanip pes ediyordu. Giris bilgileri ayarlar.json'da varsa
    gece calismasi kaldigi yerden surebilir. Yeni Luca sayfasini ya da None dondurur.
    """
    if giris_bilgileri(ayarlar) is None:
        return None
    yaz("    Luca oturumu yenileniyor...", log)
    try:
        page.goto(giris_adresi())
    except Exception:
        return None
    if not otomatik_giris(page, ayarlar, log):
        return None
    uygulama = kosulu_bekle(page, lambda: uygulama_sayfasi_bul(ctx), 60000, aralik_ms=2000)
    if uygulama is not None:
        yaz("    Oturum yenilendi, devam ediliyor", log)
    return uygulama


def luca_oturumu_ac(ctx, page, ayarlar, gece_modu, tani_klasoru, log):
    """Girisi yapar (ya da kullanicidan bekler) ve firma listesini gosteren Luca sayfasini dondurur.

    Bulunamazsa None doner; sebep gunluge yazilir.
    """
    try:
        page.bring_to_front()
        page.goto(giris_adresi())
    except Exception as e:
        yaz(f"UYARI: Luca adresi acilamadi ({type(e).__name__}); internet baglantisini"
            " kontrol edin", log)

    if otomatik_giris(page, ayarlar, log):
        # muhasebe ekrani kendiliginden acilana kadar beklenir; bu sirada
        # urun secim ekrani gec belirmis olabilir, tekrar denenir
        def hazir():
            bulunan = uygulama_sayfasi_bul(ctx)
            # urun ekrani gec belirdiyse secilir; uygulama penceresi aciliyorsa
            # (henuz yuklenmemis olsa da) urun_sec tekrar tiklamaz
            if bulunan is None:
                urun_sec(page, log, sure=0)
            return bulunan
        kosulu_bekle(page, hazir, 90000, aralik_ms=2000)

    if uygulama_sayfasi_bul(ctx) is None:
        if gece_modu:
            # gece modunda ENTER'a basacak kimse yok; bosuna beklenmez
            yaz("\nOtomatik giris yapilamadi (dogrulama kodu ya da sifre sorunu).", log)
            yaz("Gece modunda elle giris beklenmez, calisma baslatilmadi.", log)
            return None
        yaz("\n>>> Tarayicida Luca'ya giris yapin.", log)
        yaz(">>> Girisden sonra MUHASEBE EKRANINI acin (sag ustte firma listesi gorunen ekran).", log)
        kullanici_bekle(ctx, ">>> O ekran acikken ENTER'a basin: ")
    else:
        yaz("Giris yapildi, muhasebe ekrani bulundu.", log)

    uygulama = None
    for deneme in range(1, 6):
        uygulama = uygulama_sayfasi_bul(ctx)
        if uygulama:
            break
        yaz(f"\nFirma listesi olan ekran bulunamadi ({deneme}/5). Acik pencereler:", log)
        yaz(sayfalari_ozetle(ctx), log)
        tani_klasoru.mkdir(parents=True, exist_ok=True)
        for sira, p in enumerate([x for x in ctx.pages if not x.is_closed()], 1):
            try:
                p.screenshot(path=str(tani_klasoru / f"deneme{deneme}-sayfa{sira}.png"))
                (tani_klasoru / f"deneme{deneme}-sayfa{sira}.html").write_text(p.content(), encoding="utf-8")
            except Exception:
                pass
        yaz(f"Ekran goruntuleri kaydedildi: {tani_klasoru}", log)
        if gece_modu:
            break
        yaz("\nLuca'da muhasebe modulunu acip firma listesinin gorundugu ekrana gelin.", log)
        kullanici_bekle(ctx, ">>> Hazir oldugunuzda ENTER'a basin (vazgecmek icin pencereyi kapatin): ")

    if uygulama is None:
        yaz("\nMuhasebe ekrani bulunamadi, islem durduruldu.", log)
        yaz("Yukaridaki pencere listesini gonderirseniz duzeltirim.", log)
        return None

    duraklamalari_engelle(ctx, uygulama)
    try:
        uygulama.bring_to_front()
        uygulama.on("dialog", lambda d: d.accept())
    except Exception:
        pass
    yaz(f"Calisilan sayfa: {uygulama.url}", log)
    varsa_tikla(uygulama, KAPAT_METINLERI)
    return uygulama
