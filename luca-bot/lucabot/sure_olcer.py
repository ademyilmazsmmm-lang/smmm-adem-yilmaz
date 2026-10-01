# -*- coding: utf-8 -*-
"""Adim sureleri: calisma sirasinda zaman nereye gidiyor.

Her olculen adim (pencere kapatma, tarih yazma, GIB yaniti bekleme...)
"kendi" suresiyle kaydedilir: ic ice olculen adimlarda icteki adimin suresi
distakinden dusulur, yani ayni saniye iki kez sayilmaz.

Gunluge uc tur satir yazilir (hepsi "[süre]" ile baslar):
  * her GIB tarih araligindan sonra o araligin adimlari,
  * her ekranin sonunda o ekranda en cok zaman alan adimlar,
  * calisma sonunda butun calismanin dokumu (ayrica sure-raporu.txt).
"""

import functools
import time
from contextlib import contextmanager

from .ortak import AYAR, yaz

ON_EK = "    [süre]"
RAPOR_DOSYASI = "sure-raporu.txt"
DIGER = "diğer işlemler"
GOSTERILECEK_EN_AZ = 0.2  # bundan kisa adimlar satirda gosterilmez (toplamda yine sayilir)

_toplam = {}   # adim -> [saniye, adet, en uzun]
_satir = {}    # son satir yazildiktan sonraki adimlar: adim -> [saniye, adet]
_yigin = []    # acik olcumler: [ad, baslangic, alt adimlarin suresi, kapsayici mi]


@contextmanager
def olc(ad, genel=False, kapsayici=False):
    """with olc("tarih yazma"): ...  -- adimin kendi suresini kaydeder.

    genel=True: her yerde kullanilan yardimci (buton tiklama, sayfa durulmasi).
    Belirli bir adimin (orn. "pencere kapatma") icinden cagrildiginda ayrica
    sayilmaz, o adimin suresine katilir; yalnizca bir kapsayicinin (orn.
    "GİB'den Getir") dogrudan icindeyse kendi adiyla gorunur.
    kapsayici=True: icindeki adimlar ayri ayri sayilir, kendisine yalnizca
    olculmeyen kisimlar kalir (bu yuzden adi "... (diğer)" gibi verilir).
    """
    if genel and _yigin and not _yigin[-1][3]:
        yield
        return
    kayit = [ad, time.monotonic(), 0.0, kapsayici]
    _yigin.append(kayit)
    try:
        yield
    finally:
        _yigin.pop()
        gecen = time.monotonic() - kayit[1]
        if _yigin:
            _yigin[-1][2] += gecen
        _ekle(ad, max(0.0, gecen - kayit[2]))


def olculur(ad, genel=False, kapsayici=False):
    """Fonksiyon suslemesi: @olculur("pencere kapatma")."""
    def sus(fonk):
        @functools.wraps(fonk)
        def sarili(*a, **k):
            with olc(ad, genel, kapsayici):
                return fonk(*a, **k)
        return sarili
    return sus


def _ekle(ad, sure):
    t = _toplam.setdefault(ad, [0.0, 0, 0.0])
    t[0] += sure
    t[1] += 1
    t[2] = max(t[2], sure)
    s = _satir.setdefault(ad, [0.0, 0])
    s[0] += sure
    s[1] += 1


def sifirla():
    _toplam.clear()
    _satir.clear()


def satiri_temizle():
    _satir.clear()


def an():
    """Toplamlarin o anki kopyasi; fark() ile bir bolumun (ekran, firma) dokumu alinir."""
    return {ad: list(t) for ad, t in _toplam.items()}


def fark(onceki):
    """onceki = an() cagrisindan bu yana adim -> [saniye, adet]."""
    sonuc = {}
    for ad, t in _toplam.items():
        o = onceki.get(ad, [0.0, 0, 0.0])
        sure, adet = t[0] - o[0], t[1] - o[1]
        if adet:
            sonuc[ad] = [sure, adet]
    return sonuc


def sn(saniye):
    """3.24 -> '3,2 sn', 75 -> '1 dk 15 sn'."""
    if saniye >= 60:
        dk, s = divmod(int(round(saniye)), 60)
        return f"{dk} dk {s} sn"
    return f"{saniye:.1f}".replace(".", ",") + " sn"


def _parcalar(adimlar, en_cok=None):
    sirali = sorted(adimlar.items(), key=lambda x: -x[1][0])
    gosterilen = [(ad, s, n) for ad, (s, n, *_) in sirali if s >= GOSTERILECEK_EN_AZ]
    if en_cok:
        gosterilen = gosterilen[:en_cok]
    return " · ".join(f"{ad} {sn(s)}" + (f" ({n}×)" if n > 1 else "") for ad, s, n in gosterilen)


def acik():
    return AYAR.get("sure_ayrintisi", True)


def satiri_yaz(log, baslik):
    """Son satirdan bu yana biriken adimlari tek satirda yazar ve sifirlar."""
    if _satir and acik():
        toplam = sum(s for s, _ in _satir.values())
        yaz(f"{ON_EK} {baslik} {sn(toplam)}: {_parcalar(_satir) or '-'}", log)
    _satir.clear()


def bolum_yaz(log, baslik, onceki, en_cok=6):
    """onceki = an(); o andan bu yana en cok zaman alan adimlar."""
    adimlar = fark(onceki)
    if adimlar and acik():
        toplam = sum(s for s, _ in adimlar.values())
        yaz(f"{ON_EK} {baslik} {sn(toplam)} - en çok: {_parcalar(adimlar, en_cok) or '-'}", log)


def rapor_satirlari():
    """Butun calismanin dokumu (en cok zaman alandan aza)."""
    toplam = sum(t[0] for t in _toplam.values()) or 1
    satirlar = [f"{'Adım':<34}{'Toplam':>12}{'Pay':>7}{'Adet':>8}{'Ortalama':>11}{'En uzun':>11}",
                "-" * 83]
    for ad, (s, n, en_uzun) in sorted(_toplam.items(), key=lambda x: -x[1][0]):
        satirlar.append(f"{ad:<34}{sn(s):>12}{s * 100 / toplam:>6.0f}%{n:>8}"
                        f"{sn(s / n):>11}{sn(en_uzun):>11}")
    satirlar.append("-" * 83)
    satirlar.append(f"{'TOPLAM':<34}{sn(toplam):>12}")
    return satirlar


def rapor_yaz(yol):
    """sure-raporu.txt; yazilamazsa calisma durmaz."""
    if not _toplam:
        return None
    try:
        yol.write_text(
            "Luca Bot - adım süreleri (zaman nereye gitti)\n"
            f"Oluşturma: {time.strftime('%d/%m/%Y %H:%M')}\n\n"
            "'Kendi süresi' sayılır: iç içe adımlarda içteki adımın süresi dıştakinden düşülür.\n"
            "'GİB yanıtı bekleme' Luca/GİB'in sorguyu yapma süresidir; diğerleri botun\n"
            "ekranda pencere açma, buton arama, kapatma gibi işleridir.\n\n"
            + "\n".join(rapor_satirlari()) + "\n", encoding="utf-8")
        return yol
    except OSError:
        return None
