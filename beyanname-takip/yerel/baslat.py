"""Yerel (Windows) başlatıcı: ayarlar.env dosyasını okur, programı bu bilgisayarda 127.0.0.1:8000'de çalıştırır.

Şifreler yalnızca yerel/ayarlar.env dosyasında durur (GitHub'a girmez, .gitignore'dadır).
"""

import os
import re
import sys
import threading
import webbrowser
from pathlib import Path

YEREL = Path(__file__).resolve().parent
KOK = YEREL.parent


def ayar_oku(metin):
    """'AD=değer' satırları; boş satır ve # ile başlayanlar atlanır. Değerin içindeki karakterlere dokunulmaz (parolada
    &, %, ! gibi işaretler olabilir); yalnızca baş/son boşluk ve bir çift çevreleyen tırnak atılır."""
    sonuc = {}
    for no, satir in enumerate(metin.lstrip("﻿").splitlines(), 1):
        if not satir.strip() or satir.lstrip().startswith("#"):
            continue
        ad, ayrac, deger = satir.partition("=")
        ad = ad.strip()
        if not ayrac or not re.fullmatch(r"[A-Z][A-Z0-9_]*", ad):
            raise ValueError(f"ayarlar.env {no}. satır 'AD=değer' biçiminde değil")
        deger = deger.strip()
        if len(deger) >= 2 and deger[0] == deger[-1] and deger[0] in "\"'":
            deger = deger[1:-1]
        sonuc[ad] = deger
    return sonuc


def ortami_hazirla(ayarlar, env):
    env.update({k: v for k, v in ayarlar.items() if v != ""})
    env.setdefault("TOPLAYICI", "luca")
    env.setdefault("DATA_DIR", str(YEREL / "veri"))
    env.setdefault("LUCABOT_YOLU", str(KOK / "luca-bot"))
    env["BEYANNAME_YEREL"] = "1"                 # arayüzdeki "Programı kapat" düğmesi yalnızca yerel çalışmada vardır
    eksik = [a for a in ("WEB_SIFRE",) if not env.get(a)]
    if eksik:
        raise ValueError("ayarlar.env içinde şunlar boş ya da yok: " + ", ".join(eksik))
    return env


_SISTEM = object()          # "sys.stdout/sys.stderr'i kullan" (None ise gerçekten yok demektir: pythonw)


def gunluge_yonlendir(stdout=_SISTEM, stderr=_SISTEM, dosya=None):
    """Konsolsuz çalışırken (pythonw) stdout/stderr yoktur: çıktı yerel/program.log'a yazılır (5 MB'ı aşarsa baştan başlar).
    Dönen: yönlendirilen (stdout, stderr)."""
    stdout = sys.stdout if stdout is _SISTEM else stdout
    stderr = sys.stderr if stderr is _SISTEM else stderr
    if stdout is not None and stderr is not None:
        return stdout, stderr
    dosya = Path(dosya) if dosya else YEREL / "program.log"
    try:
        if dosya.exists() and dosya.stat().st_size > 5_000_000:
            dosya.unlink()
        f = open(dosya, "a", encoding="utf-8", buffering=1)
    except OSError:
        return stdout, stderr
    return (stdout if stdout is not None else f), (stderr if stderr is not None else f)


def hata_goster(metin, baslik="Beyanname Takip"):
    """Hatayı yazar; konsol yoksa (siyah pencere olmadan başlatıldıysa) Windows'ta mesaj kutusu da gösterir."""
    print("HATA:", metin)
    if os.name == "nt" and not (sys.stdin and sys.stdin.isatty()):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, str(metin)[:1500], baslik, 0x10)
        except Exception:  # noqa: BLE001
            pass


def bekle():
    """Pencere hata yazısı okunmadan kapanmasın. baslat.bat zaten 'pause' ile bekler; çift tıklanan .py için burada beklenir."""
    if not os.environ.get("BASLAT_BAT") and sys.stdin and sys.stdin.isatty():
        input("Kapatmak için Enter'a basın...")


def main():
    dosya = YEREL / "ayarlar.env"
    if not dosya.exists():
        hata_goster("ayarlar.env yok. 'ayarlar-ornek.env' dosyasını kopyalayıp adını 'ayarlar.env' yapın ve doldurun.")
        return 1
    try:
        ortami_hazirla(ayar_oku(dosya.read_text(encoding="utf-8")), os.environ)
    except ValueError as e:
        hata_goster(e)
        return 1
    sys.path.insert(0, str(KOK))
    try:
        import uvicorn
    except ImportError:
        hata_goster("Gerekli paketler kurulu değil. Bu dosyayı doğrudan açmayın; 'Beyanname Takip' kısayoluna (ya da baslat.bat'a) çift tıklayın, ilk seferde kurulumu yapar.")
        return 1
    port = int(os.environ.get("PORT") or 8000)
    adres = f"http://127.0.0.1:{port}"
    print(f"Beyanname Takip başlıyor: {adres}  (siyah pencereyi KAPATMAYIN; kapatırsanız program durur. Konsolsuz açtıysanız Sistem sekmesindeki 'Programı kapat' düğmesini kullanın)")
    if os.environ.get("BEYANNAME_TARAYICI_ACMA") != "0":   # Dijital Stajyer sekmesi başlatırken tarayıcıyı kendisi açar/açtırmaz
        threading.Timer(3, lambda: webbrowser.open(adres)).start()
    try:
        uvicorn.run("app.web:app_fabrikasi", factory=True, host="127.0.0.1", port=port, workers=1)     # tek işçi şart
    except OSError as e:
        hata_goster(f"Program başlatılamadı: {e}. Zaten açık olabilir; tarayıcıda {adres} adresine bakın.")
        return 1
    return 0


if __name__ == "__main__":
    sys.stdout, sys.stderr = gunluge_yonlendir()
    try:
        kod = main()
    except KeyboardInterrupt:
        kod = 0
    except Exception:  # noqa: BLE001 - pencere kapanmadan hata görünsün
        import traceback
        ayrinti = traceback.format_exc()
        hata_goster(ayrinti[-1200:])
        kod = 1
    if kod:
        bekle()
    sys.exit(kod)
