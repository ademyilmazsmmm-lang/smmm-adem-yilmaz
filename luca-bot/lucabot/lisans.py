# -*- coding: utf-8 -*-
"""Kullanim lisansi: imzali lisans.json dosyasi (Ed25519) ve gecerlilik kontrolu.

lisans.json:  {"urun": "Dijital Stajyer", "lisans_sahibi": "...", "baslangic": "2026-01-01",
               "bitis": "2026-12-31", "imza": "<base64>"}

Imza yalniz program sahibinin ozel anahtariyla atilabilir (lisans_araci.py); programin icindeki ACIK_ANAHTAR
ile dogrulanir. Boylece lisans dosyasindaki tarih elle degistirilemez. Bu bir caydirici onlemdir: Python
kaynak kodu acik oldugundan kodu duzenleyen birini engellemez.

    durum()       lisansin su anki durumu (gecerli mi, kime ait, ne zamana kadar, uyari metni)
    kontrol()     (gecerli mi, kullaniciya gosterilecek metin)
    kur(yol)      baska bir lisans dosyasini dogrulayip programa kurar
"""

import base64
import hashlib
import json
import os
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

URUN = "Dijital Stajyer"
KOK = Path(__file__).resolve().parent.parent
LISANS_DOSYASI = KOK / "lisans.json"
DURUM_DOSYASI = KOK / "lisans-durum.json"  # son gorulen tarih (bilgisayar saati geriye alinirsa yakalamak icin)
UYARI_GUN = 30
ILETISIM = "smmmyilmaz.com"

# Program sahibinin Ed25519 acik anahtari (32 bayt, hex). Ozel anahtar programda YOKTUR.
ACIK_ANAHTAR = "d24d1b4c30579e813740af45cb8820c47a6ebe2be2840c4318e8bb3de62dd731"


# ---- Ed25519 (RFC 8032, saf Python; ek paket gerektirmez) ------------------------------------

_P = 2 ** 255 - 19
_D = -121665 * pow(121666, _P - 2, _P) % _P
_Q = 2 ** 252 + 27742317777372353535851937790883648493
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _ters(x):
    return pow(x, _P - 2, _P)


def _topla(a, b):
    A = (a[1] - a[0]) * (b[1] - b[0]) % _P
    B = (a[1] + a[0]) * (b[1] + b[0]) % _P
    C = 2 * a[3] * b[3] * _D % _P
    D = 2 * a[2] * b[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _carp(s, nokta):
    sonuc = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            sonuc = _topla(sonuc, nokta)
        nokta = _topla(nokta, nokta)
        s >>= 1
    return sonuc


def _esit(a, b):
    return (a[0] * b[2] - b[0] * a[2]) % _P == 0 and (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _x_bul(y, isaret):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _ters(_D * y * y + 1)
    if x2 == 0:
        return None if isaret else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != isaret:
        x = _P - x
    return x


_GY = 4 * _ters(5) % _P
_GX = _x_bul(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _sikistir(n):
    zi = _ters(n[2])
    x, y = n[0] * zi % _P, n[1] * zi % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _ac(b):
    y = int.from_bytes(b, "little")
    isaret = y >> 255
    y &= (1 << 255) - 1
    x = _x_bul(y, isaret)
    return None if x is None else (x, y, 1, x * y % _P)


def _sha512_modq(b):
    return int.from_bytes(hashlib.sha512(b).digest(), "little") % _Q


def _genislet(tohum):
    h = hashlib.sha512(tohum).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def acik_anahtar_uret(tohum):
    """32 baytlik ozel tohumdan acik anahtar (bytes)."""
    return _sikistir(_carp(_genislet(tohum)[0], _G))


def imzala(tohum, mesaj):
    a, onek = _genislet(tohum)
    A = _sikistir(_carp(a, _G))
    r = _sha512_modq(onek + mesaj)
    R = _sikistir(_carp(r, _G))
    s = (r + _sha512_modq(R + A + mesaj) * a) % _Q
    return R + int.to_bytes(s, 32, "little")


def imza_gecerli_mi(acik, mesaj, imza):
    if len(acik) != 32 or len(imza) != 64:
        return False
    A = _ac(acik)
    R = _ac(imza[:32])
    s = int.from_bytes(imza[32:], "little")
    if A is None or R is None or s >= _Q:
        return False
    h = _sha512_modq(imza[:32] + acik + mesaj)
    return _esit(_carp(s, _G), _topla(R, _carp(h, A)))


# ---- Lisans ---------------------------------------------------------------------------------

def imzalanacak_metin(sahip, baslangic, bitis):
    return f"{URUN}|1|{sahip}|{baslangic}|{bitis}".encode("utf-8")


def lisans_olustur(tohum, sahip, baslangic, bitis):
    """Imzali lisans sozlugu (lisans_araci.py kullanir). Tarihler 'YYYY-AA-GG'."""
    date.fromisoformat(baslangic)
    date.fromisoformat(bitis)
    imza = imzala(tohum, imzalanacak_metin(sahip, baslangic, bitis))
    return {"urun": URUN, "lisans_sahibi": sahip, "baslangic": baslangic, "bitis": bitis,
            "imza": base64.b64encode(imza).decode("ascii")}


def _oku(yol):
    try:
        veri = json.loads(Path(yol).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return veri if isinstance(veri, dict) else None


def _dogrula(veri, acik=None):
    """Lisans icerigi (imza + alanlar) gecerli mi: (tamam, hata metni)."""
    try:
        sahip, bas, bit = (str(veri[k]) for k in ("lisans_sahibi", "baslangic", "bitis"))
        imza = base64.b64decode(veri["imza"])
        date.fromisoformat(bas)
        date.fromisoformat(bit)
    except (KeyError, ValueError, TypeError):
        return False, "Lisans dosyası bozuk."
    if veri.get("urun") != URUN:
        return False, "Lisans bu program için değil."
    if not imza_gecerli_mi(bytes.fromhex(acik or ACIK_ANAHTAR), imzalanacak_metin(sahip, bas, bit), imza):
        return False, "Lisans dosyası geçersiz (imza doğrulanamadı); değiştirilmiş olabilir."
    return True, ""


def _son_gorulen():
    veri = _oku(DURUM_DOSYASI) or {}
    try:
        return date.fromisoformat(str(veri.get("son_gorulen")))
    except ValueError:
        return None


def _son_gorulen_yaz(bugun):
    try:
        DURUM_DOSYASI.write_text(json.dumps({"son_gorulen": bugun.isoformat()}), encoding="utf-8")
    except OSError:
        pass


def durum(bugun=None, dosya=None, acik=None, kaydet=True):
    """{'gecerli', 'sahip', 'baslangic', 'bitis', 'kalan_gun', 'mesaj', 'uyari'} (tarihler date)."""
    bugun = bugun or date.today()
    sonuc = {"gecerli": False, "sahip": "", "baslangic": None, "bitis": None, "kalan_gun": None,
             "mesaj": "", "uyari": ""}
    veri = _oku(dosya or LISANS_DOSYASI)
    if veri is None:
        sonuc["mesaj"] = f"Lisans dosyası (lisans.json) bulunamadı. Lisans için: {ILETISIM}"
        return sonuc
    tamam, hata = _dogrula(veri, acik)
    if not tamam:
        sonuc["mesaj"] = f"{hata} Lisans için: {ILETISIM}"
        return sonuc
    sonuc["sahip"] = veri["lisans_sahibi"]
    sonuc["baslangic"] = date.fromisoformat(veri["baslangic"])
    sonuc["bitis"] = date.fromisoformat(veri["bitis"])
    sonuc["kalan_gun"] = (sonuc["bitis"] - bugun).days
    son = _son_gorulen() if kaydet else None
    if son and bugun < son - timedelta(days=1):
        sonuc["mesaj"] = (f"Bilgisayar saati geriye alınmış görünüyor (en son {son.strftime('%d.%m.%Y')} "
                          "tarihinde açıldı). Tarihi düzeltip yeniden açın.")
        return sonuc
    if bugun < sonuc["baslangic"]:
        sonuc["mesaj"] = f"Lisans {sonuc['baslangic'].strftime('%d.%m.%Y')} tarihinde başlar."
        return sonuc
    if bugun > sonuc["bitis"]:
        sonuc["mesaj"] = (f"Lisans süresi {sonuc['bitis'].strftime('%d.%m.%Y')} tarihinde doldu. "
                          f"Yeni lisans için: {ILETISIM}")
        return sonuc
    sonuc["gecerli"] = True
    if kaydet and (son is None or bugun > son):
        _son_gorulen_yaz(bugun)
    if sonuc["kalan_gun"] <= UYARI_GUN:
        sonuc["uyari"] = (f"Lisansınızın bitmesine {sonuc['kalan_gun']} gün kaldı "
                          f"({sonuc['bitis'].strftime('%d.%m.%Y')}). Yenilemek için: {ILETISIM}")
    return sonuc


def kontrol(**kw):
    """(gecerli mi, gosterilecek metin): gecersizse nedeni, gecerliyse (varsa) bitis uyarisi."""
    if os.environ.get("LUCA_TEST_LISANS_ATLA") == "1":  # yalniz otomatik testler icin
        return True, ""
    d = durum(**kw)
    return d["gecerli"], (d["uyari"] if d["gecerli"] else d["mesaj"])


def ozet(d=None):
    """Hakkinda penceresi icin tek satirlik lisans ozeti."""
    d = d or durum(kaydet=False)
    if d["sahip"] and d["bitis"]:
        return f"{d['sahip']} · Geçerlilik: {d['bitis'].strftime('%d.%m.%Y')}"
    return "Lisans yok / geçersiz"


def kur(yol, acik=None):
    """Verilen lisans dosyasini dogrular ve programin lisans.json'u olarak kopyalar: (tamam, mesaj)."""
    veri = _oku(yol)
    if veri is None:
        return False, "Dosya okunamadı."
    tamam, hata = _dogrula(veri, acik)
    if not tamam:
        return False, hata
    try:
        shutil.copyfile(yol, LISANS_DOSYASI)
    except (OSError, shutil.SameFileError) as e:
        return False, f"Lisans kaydedilemedi: {e}"
    return True, "Lisans yüklendi."
