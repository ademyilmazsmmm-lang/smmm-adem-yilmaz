# -*- coding: utf-8 -*-
"""Beyanname Takip uygulamasini (repodaki beyanname-takip/) Dijital Stajyer'den yonetir; pencere gerektirmeyen mantik.

Uygulama ayri bir web programidir (FastAPI, kendi zamanlayicisi, Telegram/e-posta bildirimi). Sekme:
  * yerel/ayarlar.env dosyasini yazar/gunceller (bilinmeyen satirlara dokunmaz); Luca girisi Dijital Stajyer ayarlarindan alinabilir
  * programi arka planda baslatir (pencere kapansa da calisir), kontrol.json'a port/anahtar/pid yazar; durdurur
  * saglik ve beyanname maddelerini programin kendi API'sinden okur; gunlugun sonunu gosterir
"""

import json
import os
import re
import secrets
import signal
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from http.cookiejar import CookieJar
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent          # luca-bot
ADAYLAR = (KOK.parent / "beyanname-takip", KOK / "beyanname-takip")
VARSAYILAN_PORT = 8765
ENV_AD = re.compile(r"[A-Z][A-Z0-9_]*")

# Sekmedeki formun yonettigi anahtarlar (digerleri ayarlar.env'de oldugu gibi kalir)
YONETILEN = ("WEB_SIFRE", "WEB_GIZLI", "PORT", "LUCA_HESAPLAR", "LUCA_OFIS_UYE_NO", "LUCA_OFIS_KULLANICI", "LUCA_OFIS_PAROLA",
             "LUCA_OFIS_DOGRULAMA_ANAHTARI", "LUCA_GIB_GUN", "MAIL_ALICI", "RESEND_API_KEY", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID")


def klasor():
    for yol in ADAYLAR:
        if (yol / "app" / "web.py").exists():
            return yol
    return None


def env_yolu(k):
    return Path(k) / "yerel" / "ayarlar.env"


def veri_klasoru(k):
    return Path(k) / "yerel" / "veri"


def kontrol_yolu(k):
    return veri_klasoru(k) / "kontrol.json"


def gunluk_yolu(k):
    return Path(k) / "yerel" / "program.log"


# --- ayarlar.env ------------------------------------------------------------------------------------

def env_oku(yol):
    """'AD=deger' satirlari sozluk olarak; dosya yoksa {}. (Uygulamanin kendi okuyucusuyla ayni kurallar.)"""
    try:
        metin = Path(yol).read_text(encoding="utf-8")
    except OSError:
        return {}
    sonuc = {}
    for satir in metin.lstrip("﻿").splitlines():
        if not satir.strip() or satir.lstrip().startswith("#"):
            continue
        ad, ayrac, deger = satir.partition("=")
        ad = ad.strip()
        if not ayrac or not ENV_AD.fullmatch(ad):
            continue
        deger = deger.strip()
        if len(deger) >= 2 and deger[0] == deger[-1] and deger[0] in "\"'":
            deger = deger[1:-1]
        sonuc[ad] = deger
    return sonuc


def env_yaz(yol, degerler):
    """degerler {AD: deger}: dosyada olan satirlar yerinde guncellenir, olmayanlar sona eklenir; yorumlar ve bilinmeyen satirlar korunur."""
    yol = Path(yol)
    try:
        satirlar = yol.read_text(encoding="utf-8").lstrip("﻿").splitlines()
    except OSError:
        satirlar = ["# Dijital Stajyer'in Beyanname Takip sekmesi tarafından yönetilir. Şifre içerir: kimseyle paylaşmayın."]
    yazilan = set()
    for i, satir in enumerate(satirlar):
        ad = satir.partition("=")[0].strip()
        if "=" in satir and not satir.lstrip().startswith("#") and ad in degerler:
            satirlar[i] = f"{ad}={_temiz(degerler[ad])}"
            yazilan.add(ad)
    for ad, deger in degerler.items():
        if ad not in yazilan:
            satirlar.append(f"{ad}={_temiz(deger)}")
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".env.tmp")
    gecici.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    gecici.replace(yol)


def _temiz(deger):
    return str(deger if deger is not None else "").replace("\r", " ").replace("\n", " ").strip()


def varsayilan_form(k, ana_ayarlar=None):
    """Formun ilk degerleri: ayarlar.env'deki mevcutlar; olmayanlar icin makul varsayilanlar (sayfa sifresi uretilir)."""
    e = env_oku(env_yolu(k))
    ana = ana_ayarlar or {}
    return {"WEB_SIFRE": e.get("WEB_SIFRE") or secrets.token_urlsafe(9),
            "PORT": e.get("PORT") or str(VARSAYILAN_PORT),
            "LUCA_GIB_GUN": e.get("LUCA_GIB_GUN") or "31",
            "MAIL_ALICI": e.get("MAIL_ALICI") or str(ana.get("mail_alici") or ""),
            "RESEND_API_KEY": e.get("RESEND_API_KEY", ""),
            "TELEGRAM_TOKEN": e.get("TELEGRAM_TOKEN", ""),
            "TELEGRAM_CHAT_ID": e.get("TELEGRAM_CHAT_ID", ""),
            "luca_ayarlardan": not e.get("LUCA_OFIS_PAROLA")}


def dogrula(form):
    """Hata metinleri listesi (bos = tamam)."""
    hatalar = []
    if len(str(form.get("WEB_SIFRE", "")).strip()) < 4:
        hatalar.append("Sayfa şifresi en az 4 karakter olmalı.")
    try:
        port = int(str(form.get("PORT", "")).strip())
        if not 1024 <= port <= 65535:
            raise ValueError
    except ValueError:
        hatalar.append("Port 1024-65535 arasında bir sayı olmalı.")
    try:
        gun = int(str(form.get("LUCA_GIB_GUN", "")).strip())
        if not 1 <= gun <= 31:
            raise ValueError
    except ValueError:
        hatalar.append("GİB gün sayısı 1-31 arasında olmalı.")
    return hatalar


def env_hazirla(k, form, ana_ayarlar):
    """Form + Dijital Stajyer ayarlarindan yerel/ayarlar.env'yi gunceller; yolunu dondurur.

    Luca girisi ayarlardan alinirsa LUCA_OFIS_* yazilir (LUCA_HESAPLAR yoksa 'ofis'); Resend anahtari bossa ve ayarlar.env'de SMTP
    yoksa, Dijital Stajyer'in smtp ayarlari e-posta icin kullanilir. Bilinmeyen satirlara dokunulmaz."""
    yol = env_yolu(k)
    mevcut = env_oku(yol)
    d = {"WEB_SIFRE": str(form["WEB_SIFRE"]).strip(),
         "WEB_GIZLI": mevcut.get("WEB_GIZLI") or secrets.token_hex(20),
         "PORT": str(form["PORT"]).strip(), "LUCA_GIB_GUN": str(form["LUCA_GIB_GUN"]).strip(),
         "MAIL_ALICI": str(form.get("MAIL_ALICI", "")).strip(), "RESEND_API_KEY": str(form.get("RESEND_API_KEY", "")).strip(),
         "TELEGRAM_TOKEN": str(form.get("TELEGRAM_TOKEN", "")).strip(),
         "TELEGRAM_CHAT_ID": str(form.get("TELEGRAM_CHAT_ID", "")).strip(),
         "TOPLAYICI": mevcut.get("TOPLAYICI") or "luca"}
    if not mevcut.get("LUCA_HESAPLAR"):
        d["LUCA_HESAPLAR"] = "ofis"
    if form.get("luca_ayarlardan", True):
        for ad, anahtar in (("UYE_NO", "uye_no"), ("KULLANICI", "kullanici_adi"), ("PAROLA", "parola"),
                            ("DOGRULAMA_ANAHTARI", "dogrulama_anahtari")):
            d[f"LUCA_OFIS_{ad}"] = str(ana_ayarlar.get(anahtar) or "")
    smtp = ana_ayarlar.get("smtp") or {}
    if not d["RESEND_API_KEY"] and not mevcut.get("SMTP_KULLANICI") and smtp.get("kullanici") and smtp.get("sifre"):
        d.update({"SMTP_HOST": str(smtp.get("sunucu") or "smtp.office365.com"), "SMTP_PORT": str(smtp.get("port") or 587),
                  "SMTP_KULLANICI": str(smtp["kullanici"]), "SMTP_PAROLA": str(smtp["sifre"]),
                  "MAIL_GONDEREN": str(smtp.get("gonderen") or smtp["kullanici"])})
    env_yaz(yol, d)
    return yol


# --- saglik, baslatma, durdurma ---------------------------------------------------------------------------------

def adres(port):
    return f"http://127.0.0.1:{int(port)}"


def saglikli_mi(port, zaman_asimi=0.8):
    try:
        with urllib.request.urlopen(adres(port) + "/saglik", timeout=zaman_asimi) as r:
            return r.status == 200 and bool(json.loads(r.read().decode("utf-8")).get("ok"))
    except (OSError, ValueError):
        return False


def kontrol_oku(k):
    try:
        return json.loads(kontrol_yolu(k).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def eksik_paketler():
    import importlib.util
    return [m for m in ("fastapi", "uvicorn") if importlib.util.find_spec(m) is None]


def baslat(k, python, port, luca_bot_klasoru=KOK, ek_env=None):
    """Programi arka planda (pencere kapansa da yasayacak sekilde) baslatir; kontrol.json'a port/anahtar/pid yazar. Pid dondurur."""
    k = Path(k)
    if not env_yolu(k).exists():
        raise FileNotFoundError("yerel/ayarlar.env yok; önce ayarları kaydedin")
    veri_klasoru(k).mkdir(parents=True, exist_ok=True)
    anahtar = secrets.token_hex(16)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1", BEYANNAME_TARAYICI_ACMA="0",
               BEYANNAME_KONTROL_TOKEN=anahtar, LUCABOT_YOLU=str(luca_bot_klasoru), PORT=str(int(port)))
    env.update(ek_env or {})
    kw = {}
    if sys.platform.startswith("win"):
        kw["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000   # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW
    else:
        kw["start_new_session"] = True
    gunluk = open(gunluk_yolu(k), "a", encoding="utf-8", buffering=1)
    try:
        surec = subprocess.Popen([str(python), "-u", str(k / "yerel" / "baslat.py")], cwd=str(k), env=env,
                                 stdin=subprocess.DEVNULL, stdout=gunluk, stderr=subprocess.STDOUT, **kw)
    finally:
        gunluk.close()
    kontrol_yolu(k).write_text(json.dumps({"port": int(port), "token": anahtar, "pid": surec.pid,
                                           "baslangic": datetime.now().isoformat(timespec="seconds")}), encoding="utf-8")
    return surec.pid


def durdur(k, bekleme_sn=10):
    """Programi kapatir: once kendi kapatma ucu (kontrol.json'daki anahtarla), olmazsa surec sonlandirilir. (basarili mi, mesaj)."""
    import time
    c = kontrol_oku(k)
    port = c.get("port")
    if not port or not saglikli_mi(port):
        return True, "Program zaten çalışmıyor"
    if c.get("token"):
        istek = urllib.request.Request(adres(port) + "/api/kapat-kontrol", data=b"", method="POST",
                                       headers={"x-kontrol-token": c["token"]})
        try:
            urllib.request.urlopen(istek, timeout=3).read()
        except (OSError, ValueError):
            pass
        bitis = time.time() + bekleme_sn
        while time.time() < bitis:
            if not saglikli_mi(port, 0.4):
                return True, "Program kapatıldı"
            time.sleep(0.4)
    pid = c.get("pid")
    if pid:
        try:
            if sys.platform.startswith("win"):
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=15)
            else:
                os.kill(int(pid), signal.SIGTERM)
        except (OSError, subprocess.SubprocessError):
            pass
        for _ in range(20):
            if not saglikli_mi(port, 0.4):
                return True, "Program sonlandırıldı"
            time.sleep(0.4)
    return False, "Program kapatılamadı (kontrol anahtarı eşleşmedi; dışarıdan başlatılmış olabilir). Tarayıcıdaki sayfadan Sistem → Programı kapat'ı kullanın."


# --- veri okuma -------------------------------------------------------------------------------------------

def _oturum(port, sifre, zaman_asimi=10):
    """Programin sayfa sifresiyle oturum acmis bir urllib acicisi dondurur."""
    kurabiye = CookieJar()
    acici = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(kurabiye))
    giris = urllib.request.Request(adres(port) + "/api/giris", data=json.dumps({"sifre": sifre}).encode("utf-8"),
                                   headers={"Content-Type": "application/json"}, method="POST")
    try:
        acici.open(giris, timeout=zaman_asimi).read()
    except urllib.error.HTTPError as e:
        raise ValueError("Sayfa şifresi kabul edilmedi" if e.code in (401, 429) else f"Giriş hatası {e.code}") from e
    return acici


def veri_oku(port, sifre, zaman_asimi=10):
    """Programin API'sinden (oturum acarak) {'durum': ..., 'maddeler': [...]} okur; hata: OSError/ValueError."""
    acici = _oturum(port, sifre, zaman_asimi)
    sonuc = {}
    for ad, yol in (("durum", "/api/durum"), ("maddeler", "/api/maddeler")):
        with acici.open(adres(port) + yol, timeout=zaman_asimi) as r:
            sonuc[ad] = json.loads(r.read().decode("utf-8"))
    return sonuc


def simdi_cek(port, sifre, zaman_asimi=15):
    """Programa Luca'dan veriyi SIMDI cekmesini soyler (arka planda calisir; sonuc veri_oku ile izlenir). Telegram'a mesaj atmaz."""
    acici = _oturum(port, sifre, zaman_asimi)
    istek = urllib.request.Request(adres(port) + "/api/kontrol", data=b"", method="POST")
    with acici.open(istek, timeout=zaman_asimi) as r:
        return bool(json.loads(r.read().decode("utf-8")).get("ok"))


def log_sonu(k, satir=200, azami_bayt=60000):
    """program.log'un son satirlari."""
    try:
        with open(gunluk_yolu(k), "rb") as f:
            f.seek(0, os.SEEK_END)
            boyut = f.tell()
            f.seek(max(0, boyut - azami_bayt))
            ham = f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(ham.splitlines()[-satir:])
