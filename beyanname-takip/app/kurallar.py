"""Beyanname türleri, dönemler ve son gün hesabı.

Tablo, depodaki hatirlatma.html vergi takvimiyle aynıdır: KDV her ayın 28'i, MUHSGK her ayın 26'sı
(3 aylık olanlar Ocak/Nisan/Temmuz/Ekim 26'sı), geçici vergi Şubat/Mayıs/Ağustos/Kasım 17'si.
Son gün hafta sonu ya da resmî tatile denk gelirse ilk iş gününe kayar.

DİKKAT: Mevzuat değişebilir. Tablo BEYANNAMELER sözlüğündedir; yayına almadan önce güncel
takvimle karşılaştırın. Hesap dönemi takvim yılı olmayan mükellefler desteklenmez.
"""

import calendar
import json
import os
import re
from dataclasses import dataclass
from datetime import date, timedelta

AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
         "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

# gun: son gün; sonra: dönem bitiminden kaç ay sonra; periyotlar: seçilebilen dönem uzunlukları
BEYANNAMELER = {
    "KDV1":   {"ad": "KDV", "gun": 28, "sonra": 1, "periyotlar": ("aylik", "3aylik")},
    "MPHB":   {"ad": "MUHSGK (Muhtasar + Sigorta)", "gun": 26, "sonra": 1, "periyotlar": ("aylik", "3aylik")},
    "GECICI": {"ad": "Geçici Vergi", "gun": 17, "sonra": 2, "periyotlar": ("3aylik",)},
}
PERIYOT_AY = {"aylik": 1, "3aylik": 3}

_TR = str.maketrans("İıŞşĞğÜüÖöÇç", "IiSsGgUuOoCc")


def sade(metin):
    """Türkçe harfleri sadeleştirip büyütür, noktalamayı boşluğa çevirir (eşleştirme için)."""
    t = str(metin or "").translate(_TR).upper()
    return re.sub(r"[^A-Z0-9]+", " ", t).strip()


class Tatiller:
    """Resmî tatiller: sabit (AA-GG) ve yıla özel (dinî bayramlar) günler."""

    def __init__(self, yol=None):
        yol = yol or os.path.join(os.path.dirname(os.path.abspath(__file__)), "tatiller.json")
        try:
            with open(yol, encoding="utf-8") as f:
                v = json.load(f)
        except (OSError, ValueError):
            v = {}
        self.sabit = {str(x) for x in v.get("sabit", [])}
        self.yillar = {int(y): {str(x) for x in g} for y, g in v.get("yillar", {}).items()}

    def mi(self, d):
        return (d.weekday() >= 5 or d.strftime("%m-%d") in self.sabit
                or d.isoformat() in self.yillar.get(d.year, set()))

    def bayram_verisi_var_mi(self, yil):
        return yil in self.yillar

    def kaydir(self, d):
        while self.mi(d):
            d += timedelta(days=1)
        return d


@dataclass(frozen=True)
class Donem:
    tur: str
    periyot: str
    yil: int          # dönemin bittiği yıl
    ay: int           # dönemin bittiği ay
    bas: date
    bit: date
    son_gun: date

    @property
    def anahtar(self):
        return f"{self.yil}-{self.ay:02d}"

    @property
    def etiket(self):
        if self.periyot == "aylik":
            return f"{AYLAR[self.ay - 1]} {self.yil}"
        return f"{AYLAR[self.bas.month - 1]}–{AYLAR[self.ay - 1]} {self.yil}"


def son_gun_hesapla(tur, yil, ay, tatil):
    k = BEYANNAMELER[tur]
    y, a = divmod(yil * 12 + (ay - 1) + k["sonra"], 12)
    a += 1
    d = date(y, a, min(k["gun"], calendar.monthrange(y, a)[1]))
    return tatil.kaydir(d)


def donemler_uret(tur, periyot, bas, bit, tatil):
    """Son günü [bas, bit] aralığına düşen dönemler (kayma uygulanmış son güne göre)."""
    if periyot not in BEYANNAMELER[tur]["periyotlar"]:
        return []
    uz = PERIYOT_AY[periyot]
    sonuc = []
    for yil in range(bas.year - 1, bit.year + 1):
        for ay in range(uz, 13, uz):
            son = son_gun_hesapla(tur, yil, ay, tatil)
            if bas <= son <= bit:
                ilk_ay = ay - uz + 1
                sonuc.append(Donem(tur, periyot, yil, ay, date(yil, ilk_ay, 1),
                                   date(yil, ay, calendar.monthrange(yil, ay)[1]), son))
    return sorted(sonuc, key=lambda d: d.son_gun)


def tur_coz(ham):
    """Luca/GİB'deki beyanname adını bu programdaki türe çevirir; tanınmazsa None (yok sayılır)."""
    f = sade(ham)
    if not f:
        return None
    if re.search(r"KDV\s*([234]|9015)", f):
        return None
    if "KDV" in f:
        return "KDV1"
    if "MUHSGK" in f or "MUHTASAR" in f or "PRIM HIZMET" in f:
        return "MPHB"
    if "GECICI" in f:
        return "GECICI"
    return None


def donem_bitisi(kayit):
    """Beyanname kaydının dönem bitişi (yıl, ay); bulunamazsa (None, None)."""
    for alan in ("donem_bit", "donem"):
        s = str(kayit.get(alan) or "").strip()
        if not s:
            continue
        m = re.match(r"(\d{4})-(\d{2})", s)
        if m:
            return int(m.group(1)), int(m.group(2))
        bulunan = re.findall(r"(\d{1,2})[./-](\d{4})", s)
        if bulunan:
            a, y = bulunan[-1]
            if 1 <= int(a) <= 12:
                return int(y), int(a)
        m = re.match(r"(\d{4})[./-](\d{1,2})$", s)
        if m and 1 <= int(m.group(2)) <= 12:
            return int(m.group(1)), int(m.group(2))
    return None, None


def onayli_mi(durum):
    """Beyanname durumu onaylı sayılır mı? Boş durum (kayıt var) onaylı sayılır. Hata/iptal/bekleme sayılmaz; tanınmayan
    bir durum metni de onaylı SAYILMAZ (alarm tarafında kalmak, bir eksiği kaçırmaktan iyidir)."""
    d = sade(durum)
    if not d:
        return True
    if any(k in d for k in ("HATA", "BEKL", "ONAYLANMAMIS", "ISLEM", "IPTAL")) or re.search(r"\bRED\b", d):
        return False
    return "ONAY" in d
