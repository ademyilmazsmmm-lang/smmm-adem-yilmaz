"""Veri kaynakları: Luca'dan mükellef listesi ve verilmiş beyannameler.

Her toplayıcı `topla(bugun, captcha)` çağrısında şunu döndürür:
    {"mukellefler": [Luca müşteri kaydı, ...], "beyannameler": [{"vkn","firma","tur","donem","durum"}, ...]}
`captcha`: gerekirse `captcha.sor(png_baytlari)` ile kullanıcıdan kod istenir (CaptchaKoprusu).

  * OrnekToplayici  – deneme için uydurma veri (TOPLAYICI=ornek)
  * DosyaToplayici  – DATA_DIR/girdi/<hesap>/ altındaki dosyaları okur (TOPLAYICI=dosya):
        luca-musteri-listesi.json   Dijital Stajyer'in müşteri listesi çıktısı ({"firmalar": [...]})
        luca-beyannameler.json      {"beyannameler": [...]}  ya da  luca-beyannameler.csv
  * LucaToplayici   – Luca'ya tarayıcıyla girip ikisini kendisi çeker (TOPLAYICI=luca); luca_toplayici.py
"""

import csv
import json
import os
from datetime import timedelta
from pathlib import Path

from .kurallar import AYLAR, sade


class OrnekToplayici:
    """Uydurma 6 firma. Bazı beyannameler bilerek eksik bırakılır."""

    HESAP = "ornek"

    def topla(self, bugun, captcha=None, gib_aralik=None):
        firmalar = [
            {"ad": "ALFA TİCARET", "unvan": "ALFA TİCARET LTD. ŞTİ.", "vkn": "1111111111", "acilis": "01/01/2020", "kapanis": ""},
            {"ad": "BETA İNŞAAT", "unvan": "BETA İNŞAAT A.Ş.", "vkn": "2222222222", "acilis": "15/03/2019", "kapanis": ""},
            {"ad": "GAMA GIDA", "unvan": "GAMA GIDA SAN. LTD.", "vkn": "3333333333", "acilis": "01/06/2021", "kapanis": ""},
            {"ad": "DELTA DANIŞMANLIK", "unvan": "DELTA DANIŞMANLIK", "vkn": "4444444444", "acilis": "01/01/2018", "kapanis": ""},
            {"ad": "EPSİLON NAKLİYAT", "unvan": "EPSİLON NAKLİYAT LTD.", "vkn": "5555555555", "acilis": "01/02/2022", "kapanis": "30/06/2026"},
            {"ad": "ZETA YENİ", "unvan": "ZETA YENİ LTD.", "vkn": "6666666666", "acilis": f"01/{bugun.month:02d}/{bugun.year}", "kapanis": ""},
        ]
        # önceki 3 ayın KDV/MUHSGK'sı verilmiş sayılır; ALFA'nın son ayı ve DELTA'nın hepsi eksik
        bey = []
        for f in firmalar[:4]:
            for geri in range(1, 5):
                y, a = divmod(bugun.year * 12 + bugun.month - 1 - geri, 12)
                a += 1
                if f["ad"].startswith("DELTA") or (f["ad"].startswith("ALFA") and geri == 1):
                    continue
                for tur in ("KDV1", "MUHSGK"):
                    bey.append({"vkn": f["vkn"], "firma": f["unvan"], "tur": tur, "donem": f"{a:02d}/{y}",
                                "durum": "Onaylanmış"})
        return {"mukellefler": firmalar, "beyannameler": bey}


class DosyaToplayici:
    """DATA_DIR/girdi/<hesap>/ klasörlerini okur. Hesap = klasör adı (örn. ofis, isletme)."""

    CSV_ALIAS = {
        "vkn": ("VKN", "VERGI NO", "VERGI KIMLIK NO", "VERGI KIMLIK NUMARASI"),
        "firma": ("FIRMA", "UNVAN", "KISA AD", "KISA ADI", "MUKELLEF", "AD"),
        "tur": ("BEYANNAME TURU", "BEYANNAME", "TUR"),
        "donem": ("DONEM", "BEYANNAME DONEMI"),
        "durum": ("DURUM", "BEYANNAME DURUMU"),
    }

    def __init__(self, girdi_dizini):
        self.dizin = Path(girdi_dizini)

    def hesaplar(self):
        return sorted(p.name for p in self.dizin.iterdir() if p.is_dir()) if self.dizin.is_dir() else []

    def topla_hesap(self, hesap):
        klasor = self.dizin / hesap
        mus = json.loads((klasor / "luca-musteri-listesi.json").read_text(encoding="utf-8")).get("firmalar", [])
        bey = []
        j = klasor / "luca-beyannameler.json"
        c = klasor / "luca-beyannameler.csv"
        if j.exists():
            bey = json.loads(j.read_text(encoding="utf-8")).get("beyannameler", [])
        elif c.exists():
            bey = self._csv(c)
        else:
            raise FileNotFoundError(f"{hesap}: luca-beyannameler.json/.csv yok")
        for b in bey:
            b["hesap"] = hesap
        return mus, bey

    def _csv(self, yol):
        metin = yol.read_text(encoding="utf-8-sig", errors="replace")
        ayrac = ";" if metin.split("\n", 1)[0].count(";") >= metin.split("\n", 1)[0].count(",") else ","
        okuyucu = csv.DictReader(metin.splitlines(), delimiter=ayrac)
        esle = {}
        for ham in okuyucu.fieldnames or []:
            for alan, adaylar in self.CSV_ALIAS.items():
                if sade(ham) in adaylar and alan not in esle:
                    esle[alan] = ham
        if "tur" not in esle or "donem" not in esle:
            raise ValueError("CSV'de 'Beyanname Türü' ve 'Dönem' sütunları bulunamadı")
        return [{alan: (satir.get(ham) or "").strip() for alan, ham in esle.items()} for satir in okuyucu]

    def topla(self, bugun, captcha=None, gib_aralik=None):
        sonuc = {"mukellefler": [], "beyannameler": [], "hesaplar": {}}
        for hesap in self.hesaplar():
            mus, bey = self.topla_hesap(hesap)
            for m in mus:
                m["hesap"] = hesap
            sonuc["mukellefler"] += mus
            sonuc["beyannameler"] += bey
            sonuc["hesaplar"][hesap] = {"mukellef": len(mus), "beyanname": len(bey)}
        if not sonuc["hesaplar"]:
            raise FileNotFoundError("girdi klasöründe hesap klasörü yok (örn. girdi/ofis/)")
        return sonuc


def sec(ad, depo_dizini):
    ad = (ad or "ornek").lower()
    if ad == "ornek":
        return OrnekToplayici()
    if ad == "dosya":
        return DosyaToplayici(Path(depo_dizini) / "girdi")
    if ad == "luca":
        from .luca_toplayici import LucaToplayici
        return LucaToplayici(Path(depo_dizini))
    raise ValueError(f"Bilinmeyen TOPLAYICI: {ad}")
