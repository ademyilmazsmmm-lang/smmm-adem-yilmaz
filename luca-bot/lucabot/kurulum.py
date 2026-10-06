# -*- coding: utf-8 -*-
"""Kurulum sihirbazinin (kurulum_sihirbazi.py) pencere gerektirmeyen mantigi.

    ortam_kontrol()       Python, paketler, Chromium, kar-zarar klasoru: sihirbazin ilk sayfasindaki durum satirlari
    sihirbaz_gerekli()    ilk acilista sihirbaz kendiliginden acilsin mi (Luca bilgileri hic girilmemisse)
    dogrula()             alan kontrolleri (hata metinleri listesi)
    ayarlari_olustur()    form degerlerinden ayarlar.json'a yazilacak sozluk
"""

import glob
import importlib.util
import os
import sys
from pathlib import Path

GEREKLI_ANAHTARLAR = ("uye_no", "kullanici_adi", "parola")
PAKETLER = (("playwright", "Playwright (tarayıcı otomasyonu)", True),
            ("openpyxl", "openpyxl (Excel okuma/yazma)", True),
            ("pypdf", "pypdf (beyanname PDF'leri)", False),
            ("pyotp", "pyotp (iki aşamalı doğrulama kodu)", False))


def sihirbaz_gerekli(ayarlar):
    """Luca giris bilgileri hic girilmemis ve kurulum daha once tamamlanmamissa True."""
    if ayarlar.get("kurulum_tamam"):
        return False
    return not all(str(ayarlar.get(a) or "").strip() for a in GEREKLI_ANAHTARLAR)


def chromium_yolu():
    """Playwright'in indirdigi Chromium klasoru (varsa) ya da None."""
    adaylar = []
    ozel = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if ozel and ozel != "0":
        adaylar.append(Path(ozel))
    if sys.platform.startswith("win"):
        adaylar.append(Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright")
    elif sys.platform == "darwin":
        adaylar.append(Path.home() / "Library" / "Caches" / "ms-playwright")
    else:
        adaylar.append(Path.home() / ".cache" / "ms-playwright")
    for k in adaylar:
        bulunan = sorted(glob.glob(str(k / "chromium*")))
        if bulunan:
            return Path(bulunan[-1])
    return None


def ortam_kontrol(kar_zarar_klasoru=None):
    """[(ad, durum, aciklama)]: durum 'tamam' / 'uyari' / 'hata'. Eksik olan ne yapilacagini soyler."""
    sonuc = [("Python", "tamam" if sys.version_info >= (3, 9) else "hata",
              f"{sys.version.split()[0]}" + ("" if sys.version_info >= (3, 9) else " — 3.9 veya üstü gerekli"))]
    for modul, ad, zorunlu in PAKETLER:
        var = importlib.util.find_spec(modul) is not None
        sonuc.append((ad, "tamam" if var else ("hata" if zorunlu else "uyari"),
                      "kurulu" if var else "kurulu değil — kurulum.bat dosyasını çalıştırın"))
    chromium = chromium_yolu()
    sonuc.append(("Chromium (tarayıcı)", "tamam" if chromium else "uyari",
                  "kurulu" if chromium else "bulunamadı — tarayici-indir.bat çalıştırın "
                                            "(bilgisayarda Chrome/Edge varsa onlar da denenir)"))
    var = bool(kar_zarar_klasoru)
    sonuc.append(("Kâr / Zarar programı (kar-zarar klasörü)", "tamam" if var else "uyari",
                  str(kar_zarar_klasoru) if var else "luca-bot klasörünün yanında bulunamadı — "
                                                      "Kâr / Zarar sekmesi çalışmaz"))
    return sonuc


def _epostalar(metin):
    return [a.strip() for a in str(metin or "").replace(";", ",").split(",") if a.strip()]


def dogrula(adim, v):
    """Sayfa bazinda alan kontrolu; hata metinleri listesi (bos = sorun yok). v: {alan: deger}."""
    hatalar = []
    if adim == "luca":
        for anahtar, ad in (("uye_no", "Üye No"), ("kullanici_adi", "Kullanıcı adı"), ("parola", "Parola")):
            if not str(v.get(anahtar) or "").strip():
                hatalar.append(f"{ad} boş olamaz.")
        anahtar = str(v.get("dogrulama_anahtari") or "").replace(" ", "")
        if anahtar and (len(anahtar) < 8 or not anahtar.isalnum()):
            hatalar.append("Doğrulama anahtarı yalnızca harf ve rakamlardan oluşur (en az 8 karakter); "
                           "kurulum ekranındaki gizli anahtarı olduğu gibi yazın ya da boş bırakın.")
    elif adim == "tercihler":
        if v.get("mail_gonder"):
            for a in _epostalar(v.get("mail_alici")):
                if "@" not in a or "." not in a.split("@")[-1]:
                    hatalar.append(f"E-posta adresi geçersiz: {a}")
        klasor = str(v.get("indirme_klasoru") or "").strip()
        if not klasor:
            hatalar.append("İndirme klasörü boş olamaz.")
    return hatalar


def ayarlari_olustur(mevcut, v):
    """Form degerlerini mevcut ayarlarla birlestirir (baska ayarlara dokunmaz); yeni sozlugu dondurur."""
    yeni = dict(mevcut)
    yeni["uye_no"] = str(v.get("uye_no") or "").strip()
    yeni["kullanici_adi"] = str(v.get("kullanici_adi") or "").strip()
    yeni["parola"] = str(v.get("parola") or "")
    yeni["dogrulama_anahtari"] = str(v.get("dogrulama_anahtari") or "").replace(" ", "")
    yeni["defterbeyan_kullanici"] = str(v.get("defterbeyan_kullanici") or "").strip()
    yeni["defterbeyan_sifre"] = str(v.get("defterbeyan_sifre") or "")
    yeni["indirme_klasoru"] = str(v.get("indirme_klasoru") or "indirilenler").strip() or "indirilenler"
    yeni["mail_gonder"] = bool(v.get("mail_gonder"))
    alicilar = _epostalar(v.get("mail_alici"))
    yeni["mail_alici"] = ", ".join(alicilar)
    yeni["otomatik_tekrar"] = bool(v.get("otomatik_tekrar", True))
    yeni["tema"] = v.get("tema") if v.get("tema") in ("acik", "koyu") else "acik"
    yeni["kurulum_tamam"] = True
    return yeni
