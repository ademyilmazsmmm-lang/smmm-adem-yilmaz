# -*- coding: utf-8 -*-
"""KDV1 beyannamesi PDF'lerinden devreden KDV'nin okunmasi.

Arayuzdeki "Beyannameden Devir Al" dugmesi kullanir: secilen PDF'lerden her
birinin firmasi, donemi ve iki tutari okunur:

  * 101 - Onceki Donemden Devreden   (beyannamenin kendi donemine devreden)
  * Sonraki Doneme Devreden KDV       (bir sonraki doneme devreden)

Kontrol edilen donem Eylul ise Eylul beyannamesinin 101 satiri ya da Agustos
beyannamesinin "Sonraki Doneme Devreden" satiri ayni tutardir; hangisi
secildiyse o kullanilir (ikisi de varsa donemin kendi beyannamesi).
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from .fatura_analiz import tutar_cozumle
from .ortak import karsilastir, sadelestir

AYLAR = ["OCAK", "SUBAT", "MART", "NISAN", "MAYIS", "HAZIRAN", "TEMMUZ", "AGUSTOS",
         "EYLUL", "EKIM", "KASIM", "ARALIK"]
TUTAR = r"(\d{1,3}(?:\.\d{3})*,\d{2})"
# firma adlarinda eslesmeye katilmayan sirket turu kelimeleri
GENEL_KELIMELER = {"LTD", "LIMITED", "STI", "SIRKETI", "SIRKET", "AS", "A", "S", "ANONIM", "VE",
                   "TIC", "TICARET", "SAN", "SANAYI"}


class BeyannameDegil(ValueError):
    """PDF bir KDV1 beyannamesi degil ya da okunamadi."""


@dataclass
class Beyanname:
    dosya: str
    vkn: str
    unvan: str            # beyannamedeki "Soyadı (Unvanı)" + "Adı (Unvanın Devamı)"
    dosya_adi_firma: str  # dosya adinin basindaki kisa ad (Luca: "ADEM_MERGE_...")
    bas: date
    bit: date
    onceki_devreden: float  # Onceki Donemden Devreden (bolum yoksa 0, var ama okunamadiysa None)
    sonraki_devreden: float  # Sonraki Doneme Devreden (okunamadiysa None)
    onay: datetime = None

    @property
    def donem(self):
        return f"{self.bas:%m/%Y}" if self.bas.month == self.bit.month else \
            f"{self.bas:%m/%Y}-{self.bit:%m/%Y}"


def pdf_metni(yol):
    """PDF'in duzeni korunmus metni (etiket ve tutar ayni satirda kalir)."""
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError("PDF okuyucu (pypdf) kurulu değil; kurulum.bat'ı yeniden çalıştırın") from e
    try:
        okuyucu = PdfReader(str(yol))
        return "\n".join(s.extract_text(extraction_mode="layout") or "" for s in okuyucu.pages)
    except Exception as e:
        raise BeyannameDegil(f"PDF okunamadı ({type(e).__name__})") from e


def _deger(metin, etiket):
    """'Etiket ....   değer' satırındaki değer (ilk geçtiği yer)."""
    m = re.search(rf"^[ \t]*{etiket}[ \t]+(\S.*?)[ \t]*$", metin, re.M)
    return m.group(1).strip() if m else ""


def _tutar(metin, desen):
    m = re.search(desen + r"[^\n]*?" + TUTAR + r"[ \t]*$", metin, re.M)
    return tutar_cozumle(m.group(1)) if m else None


def _donem(metin, dosya_adi):
    # Luca dosya adi: ..._01082026-31082026_... (uc aylik beyannamede de dogru aralik)
    m = re.search(r"(\d{2})(\d{2})(\d{4})-(\d{2})(\d{2})(\d{4})", dosya_adi)
    if m:
        g1, a1, y1, g2, a2, y2 = map(int, m.groups())
        try:
            return date(y1, a1, g1), date(y2, a2, g2)
        except ValueError:
            pass
    duz = sadelestir(metin)
    yil = re.search(r"\bYIL\s+(\d{4})", duz)
    ay = re.search(r"\bAY\s+(" + "|".join(AYLAR) + r")\b", duz)
    if not (yil and ay):
        raise BeyannameDegil("beyannamenin dönemi okunamadı")
    bas = date(int(yil.group(1)), AYLAR.index(ay.group(1)) + 1, 1)
    sonraki = (bas.replace(day=28) + timedelta(days=4)).replace(day=1)
    return bas, sonraki - timedelta(days=1)


def cozumle(metin, dosya_adi=""):
    """Beyanname metninden Beyanname; KDV1 degilse BeyannameDegil."""
    duz = sadelestir(metin)
    if "KATMA DEGER VERGISI BEYANNAMESI" not in duz or "SORUMLU SIFATIYLA" in duz:
        raise BeyannameDegil("KDV1 beyannamesi değil")
    bas, bit = _donem(metin, dosya_adi)
    vkn = re.search(r"Vergi Kimlik Numarası \(TC Kimlik No\)\s+(\d{10,11})", metin)
    unvan = " ".join(x for x in (_deger(metin, r"Soyadı \(Unvanı\)"),
                                 _deger(metin, r"Adı \(Unvanın Devamı\)")) if x)
    sonraki = _tutar(metin, r"Sonraki Döneme Devreden Katma Değer Vergisi")
    # satir "Önceki Dönemden Devreden  101 - Önceki Dönemden Devreden  27.972,22" ya da
    # kodsuz "Önceki Dönemden Devreden  859.116,51" olabiliyor (bolum basligi buyuk harfli)
    onceki = _tutar(metin, r"^[ \t]*Önceki Dönemden Devreden\b")
    if onceki is None and "ONCEKI DONEMDEN DEVREDEN INDIRILECEK" not in duz:
        onceki = 0.0  # devreden yok: bolum hic basilmamis
    if sonraki is None and onceki is None:
        raise BeyannameDegil("devreden KDV satırları bulunamadı")
    onay = re.search(r"Onay Zamanı\s*:\s*(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}:\d{2}:\d{2})", metin)
    kisa = re.match(r"(.+?)_\d", Path(dosya_adi).stem)
    return Beyanname(
        dosya=Path(dosya_adi).name, vkn=vkn.group(1) if vkn else "", unvan=" ".join(unvan.split()),
        dosya_adi_firma=kisa.group(1).replace("_", " ").strip() if kisa else "",
        bas=bas, bit=bit, onceki_devreden=onceki, sonraki_devreden=sonraki,
        onay=datetime.strptime(" ".join(onay.groups()), "%d.%m.%Y %H:%M:%S") if onay else None)


def oku(yol):
    return cozumle(pdf_metni(yol), Path(yol).name)


# --- firma eslestirme ---------------------------------------------------------

def _kelimeler(metin):
    return [k for k in re.split(r"[^A-Z0-9]+", sadelestir(metin)) if k]


def _ad_puani(firma, unvan):
    """Firmanin (kisaltilmis) her kelimesi unvandaki ayri bir kelimenin basi mi; puan ya da 0.

    Luca adlari kisaltiyor ("HÜSEYİN KA"), unvanda sira farkli olabiliyor
    ("MERGEN ADEM" / "ADEM MERGEN"); sirket turu kelimeleri sayilmaz.
    """
    aranan = [k for k in _kelimeler(firma) if k not in GENEL_KELIMELER]
    kalan = [k for k in _kelimeler(unvan) if k not in GENEL_KELIMELER]
    if not aranan or not kalan:
        return 0
    # tek kelimelik ad ("ADEM") her ADEM'e yapismasin: unvan da tek kelime olmali
    if len(aranan) == 1 and len(kalan) > 1:
        return 0
    puan = 0
    for k in sorted(aranan, key=len, reverse=True):
        es = next((u for u in kalan if u.startswith(k)), None)
        if es is None:
            return 0
        kalan.remove(es)
        puan += len(k)
    return puan if puan >= 3 else 0


def _puan(firma, b):
    puan = _ad_puani(firma, b.unvan)
    k, d = karsilastir(firma), karsilastir(b.dosya_adi_firma)
    if k and d:  # dosya adindaki kisa ad (Luca 10 harfte kesiyor)
        if k == d:
            puan = max(puan, 1000)
        # kesilmis dosya adi listedeki adin basi; ters yon ("ADEM" listede,
        # dosyada "ADEM MERGE") ancak uzun adlarda, kisa adlar baska firmaya yapisiyordu
        elif (len(d) >= 8 and k.startswith(d)) or (len(k) >= 8 and d.startswith(k)):
            puan = max(puan, 500 + min(len(k), len(d)))
    return puan


def firma_bul(b, adlar):
    """Beyannamenin listedeki firmasi; bulunamaz ya da iki firmaya esit uyarsa None."""
    puanlar = sorted(((_puan(ad, b), ad) for ad in adlar), reverse=True)
    if not puanlar or puanlar[0][0] == 0:
        return None
    if len(puanlar) > 1 and puanlar[1][0] == puanlar[0][0]:
        return None
    return puanlar[0][1]


def devirleri_bul(beyannameler, adlar, hedef_bas):
    """Her firmanin hedef donemine devreden KDV'si.

    hedef_bas: kontrol edilen donemin ilk gunu. Donemin kendi beyannamesi
    (101 satiri) onceki donemin beyannamesine (Sonraki Doneme Devreden) gore
    once gelir; ayni donemin birden fazla beyannamesi varsa (duzeltme) en son
    onaylanan alinir.
    Dondurur: (eslesen [{ad, tutar, b, kaynak}], eslesmeyen [b], donemi_tutmayan [b]);
    tutar None ise beyannamedeki satir okunamamistir (elle yazilmali).
    """
    secilen, eslesmeyen, donem_disi = {}, [], []
    for b in beyannameler:
        if b.bas == hedef_bas:
            oncelik, tutar, kaynak = 2, b.onceki_devreden, "Önceki Dönemden Devreden (101)"
        elif b.bit == hedef_bas - timedelta(days=1):
            oncelik, tutar, kaynak = 1, b.sonraki_devreden, "Sonraki Döneme Devreden"
        else:
            donem_disi.append(b)
            continue
        if tutar is None:  # satir var ama tutar okunamadi: okunabilen beyanname one gecsin
            oncelik = 0
        ad = firma_bul(b, adlar)
        if ad is None:
            eslesmeyen.append(b)
            continue
        anahtar = (oncelik, b.onay or datetime.min)
        if ad not in secilen or anahtar > secilen[ad][0]:
            secilen[ad] = (anahtar, {"ad": ad, "tutar": tutar, "b": b, "kaynak": kaynak})
    return [v for _, v in secilen.values()], eslesmeyen, donem_disi
