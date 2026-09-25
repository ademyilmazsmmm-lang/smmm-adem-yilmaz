# -*- coding: utf-8 -*-
"""Tarayici yonetimi: acma, Luca sayfasini bulma, cokunce yeniden acma.

Ayrica kullanicidan ENTER/cevap beklerken tarayicinin donmamasini saglayan
yardimcilar da buradadir.
"""

import os
import shutil
import threading
from pathlib import Path

from .bekleme import kosulu_bekle, nabiz
from .luca_gezinme import firma_sayisi, firma_secici
from .ortak import AYAR, KOK, yaz
from .sabitler import GIRIS_URL, UYGULAMA_PARCASI

# Calisan surumdeki sira: once kurulu Chrome. --tarayici ile degistirilebilir.
TARAYICILAR = [("chrome", "Google Chrome"), ("msedge", "Microsoft Edge"), (None, "Playwright Chromium")]

_duraklama_islenen = set()
_KAPATILAN = {}  # program kendisi kapattiysa "cokmus olabilir" uyarisi verilmez


def tarayiciyi_kapat(ctx):
    """Tarayiciyi bilerek kapatir (cokme uyarisi yazilmaz); hata firlatmaz."""
    if ctx is None:
        return
    _KAPATILAN[id(ctx)] = True
    try:
        ctx.close()
    except Exception:
        pass


def giris_adresi():
    """Luca giris adresi (test icin ayarlar.json'daki giris_adresi ile degistirilebilir)."""
    return AYAR.get("giris_adresi") or GIRIS_URL


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


def profil_klasoru(log=None):
    """Tarayici profilinin yeri.

    Varsayilan program klasorudur. OneDrive disina almak icin --profil-yerel
    kullanilir.
    """
    eski = KOK / ".tarayici-profili"
    if not AYAR.get("profil_yerel"):
        return eski
    yerel = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME")
    if not yerel:
        return eski
    yeni = Path(yerel) / "luca-bot" / "tarayici-profili"
    if yeni.exists():
        return yeni
    try:
        yeni.parent.mkdir(parents=True, exist_ok=True)
        if eski.exists():
            shutil.move(str(eski), str(yeni))
            yaz(f"Tarayici profili OneDrive disina tasindi: {yeni}", log)
        else:
            yeni.mkdir(parents=True, exist_ok=True)
        return yeni
    except Exception as e:
        yaz(f"UYARI: profil tasinamadi ({type(e).__name__}), eski konum kullanilacak", log)
        return eski


def kanal_profili(profil, kanal):
    """Her tarayicinin kendi profili olmali; Edge, Chrome'un profilini acamiyor."""
    if kanal == "chrome":
        return profil  # mevcut profil Chrome'a ait, oturum korunsun
    return profil.parent / f"{profil.name}-{kanal or 'chromium'}"


def tarayici_ac(pw, profil, log, gunluk=False):
    """Once bilgisayarda kurulu Chrome/Edge denenir; Playwright'in kendi tarayicisi son care.

    Hicbiri acilamazsa ne yapilmasi gerektigini soyleyen RuntimeError firlatir.
    """
    hatalar = []
    tercih = AYAR.get("tarayici")  # "chrome" / "edge" / "chromium" ya da None
    kanallar = {"chrome": "chrome", "edge": "msedge", "chromium": None}
    if tercih in kanallar:
        adaylar = [t for t in TARAYICILAR if t[0] == kanallar[tercih]]
    else:
        adaylar = TARAYICILAR
    for kanal, ad in adaylar:
        secenekler = {"channel": kanal} if kanal else {}
        if not kanal and AYAR.get("tarayici_yolu"):
            secenekler["executable_path"] = AYAR["tarayici_yolu"]
        kanal_yolu = kanal_profili(profil, kanal)
        try:
            kanal_yolu.mkdir(parents=True, exist_ok=True)
            ctx = pw.chromium.launch_persistent_context(
                str(kanal_yolu), headless=False, accept_downloads=True,
                args=["--start-maximized"] + (["--enable-logging", "--v=1"] if gunluk else []),
                # Playwright varsayilan olarak --disable-breakpad geciyor; tani
                # modunda kaldiriyoruz ki cokme Windows olay gunlugune dussun
                ignore_default_args=["--enable-automation"]
                + (["--disable-breakpad"] if gunluk else []),
                chromium_sandbox=AYAR.get("tarayici_sandbox", True), no_viewport=True, **secenekler
            )
            yaz(f"Tarayici: {ad}", log)
            ctx.on("page", lambda p: duraklamalari_engelle(ctx, p))
            ctx.on("close", lambda _: None if _KAPATILAN.get(id(ctx)) else
                   yaz("UYARI: tarayici kapandi (Chrome cokmus olabilir)", log))
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
    try:
        acik = [p for p in ctx.pages if not p.is_closed()]
    except Exception:
        return None
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


def tarayiciyi_yeniden_baslat(pw, profil, eski_ctx, log, bekleme_saniye=90, asgari_firma=5):
    """Chrome cokerse yeniden acar; profil oturumu tasidigi icin genelde giris gerekmez.

    Luca ekranini kendiliginden bulursa (ctx, page) doner, bulamazsa (ctx, None).
    """
    tarayiciyi_kapat(eski_ctx)
    yaz("Tarayici yeniden aciliyor...", log)
    try:
        ctx = tarayici_ac(pw, profil, log, AYAR.get("chrome_gunlugu", False))
    except Exception as e:
        yaz(f"Tarayici yeniden acilamadi: {type(e).__name__}: {e}", log)
        return None, None
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        page.bring_to_front()
        page.goto(giris_adresi())
    except Exception:
        pass

    def hazir():
        uygulama = uygulama_sayfasi_bul(ctx)
        # liste yarim yuklendiyse firma bulunamiyor; dolmasini bekle
        if uygulama is not None and firma_sayisi(uygulama) >= asgari_firma:
            return uygulama
        return None

    uygulama = kosulu_bekle(page, hazir, bekleme_saniye * 1000, aralik_ms=2000)
    if uygulama is not None:
        yaz(f"Luca ekrani bulundu ({firma_sayisi(uygulama)} firma), devam ediliyor.", log)
        return ctx, uygulama
    yaz("Yeniden girise ihtiyac var; Luca oturumu profilden acilmadi.", log)
    return ctx, None


def sayfayi_kurtar(ctx, log=None):
    """Calisilan sayfa kapanirsa tarayicida acik kalan Luca sayfasina gecer."""
    try:
        yeni = uygulama_sayfasi_bul(ctx)
    except Exception:
        yeni = None
    if yeni is None:
        return None
    yaz("    Sayfa kapanmisti, acik Luca sayfasina gecildi", log)
    try:
        duraklamalari_engelle(ctx, yeni)
    except Exception:
        pass
    return yeni


def sayfalari_ozetle(ctx):
    """Acik sekmelerin kisa dokumu (Luca ekrani bulunamadiginda tani icin)."""
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


def kullanici_metni_al(ctx, mesaj):
    """Kullanicidan bir satir okur (ENTER'a kadar) ve yazilani dondurur.

    Duz input() Playwright olaylarini dondurur; beklerken sayfa olaylari
    islenmeye devam etmeli (Luca'nin 'debugger' duraklamalari da atlanir).
    Komut penceresi kapanirsa / Ctrl+Z gelirse bos metin dondurur.
    """
    hazir = threading.Event()
    kutu = {"metin": ""}

    def oku():
        try:
            kutu["metin"] = input(mesaj)
        except (EOFError, OSError):
            pass
        finally:
            hazir.set()

    threading.Thread(target=oku, daemon=True).start()
    while not hazir.is_set():
        try:
            acik = [p for p in ctx.pages if not p.is_closed()]
        except Exception:
            acik = []
        for p in acik:
            duraklamalari_engelle(ctx, p)
        nabiz(acik[0] if acik else None, 250)
    return kutu["metin"]


def kullanici_bekle(ctx, mesaj):
    """Kullanici ENTER'a basana kadar bekler (tarayici donmadan)."""
    kullanici_metni_al(ctx, mesaj)

