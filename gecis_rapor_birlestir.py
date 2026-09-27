#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bir kerelik gecis araci: eski GUNLUK rapor.json'lari yeni SUREKLI rapora birlestirir.

Eskiden her gunun kendi klasorunde ayri bir rapor vardi
(indirilenler/2026-09-25/rapor.json, indirilenler/2026-09-26/rapor.json, ...).
Artik tek ve surekli bir rapor var (indirilenler/rapor.json). Bu arac,
gecmis gunlerin raporlarindaki bilgileri (fatura sayisi, tevkifat,
iptal/itiraz, matrah/KDV, notlar, indirilen dosya adlari) o tek rapora
isler; hicbir ekrani yeniden calistirmaya gerek kalmaz.

Eski gunluk rapor dosyalarina DOKUNULMAZ (silinmez, degistirilmez); yalnizca
okunup yeni rapor.json'a islenir. Islemden once varsa mevcut rapor.json/
rapor.xlsx/rapor.csv bir yedek klasorune kopyalanir.

Kullanim: gecis-rapor-birlestir.bat dosyasina cift tiklayin (ya da
`python gecis-rapor-birlestir.py`).
"""

import json
import re
import shutil
import sys
from datetime import datetime

from lucabot import rapor
from lucabot.ortak import ayarlari_oku
from luca_bot import indirme_koku

GUN_DESENI = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _gunluk_klasorler(kok):
    """indirilenler/ altindaki tarihli alt klasorler (eskiden en yeniye), rapor.json olanlar."""
    adaylar = [p for p in kok.iterdir()
              if p.is_dir() and GUN_DESENI.match(p.name) and (p / "rapor.json").exists()]
    return sorted(adaylar, key=lambda p: p.name)


def _veriyi_oku(yol):
    try:
        return json.loads(yol.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  UYARI: {yol} okunamadi ({type(e).__name__}), atlaniyor")
        return {}


def _kaydi_birlestir(birlesik, veri, varsayilan_tarih):
    """Bir gunun (ya da mevcut kok raporunun) kayitlarini birlesik sozluge isler.

    Ayni firma+ekran farkli gunlerde gorunuyorsa EN SON isleneni kazanir
    (fonksiyon gunler eskiden yeniye cagrildigi icin bu dogal olarak olur).
    varsayilan_tarih: o gunun klasor adi (orn. "2026-09-25"); eski kayitta
    "guncellenme" alani yoksa (yeni ozellikten once yazilmis kayitlar boyle)
    bu tarih kullanilir. Mevcut kok rapor.json icin None verilir; o kaydin
    kendi "guncellenme"/"son" alani zaten dogrudur.
    """
    for firma, kayit in veri.items():
        if not isinstance(kayit, dict):
            continue
        hedef = birlesik.setdefault(firma, rapor._bos_kayit(firma))
        rapor._tamamla(hedef)
        durumlar = kayit.get("durumlar") or {}
        eski_dosya = kayit.get("dosya")
        for tip in durumlar:
            hedef["durumlar"][tip] = durumlar[tip]
            for alan in ("sayilar", "iptal", "tevkifat", "inmeyen", "matrah", "kdv",
                        "faturalar", "dosya_adlari", "klasorler", "goruntuler",
                        "sureler", "notlar"):
                kaynak_alan = kayit.get(alan) or {}
                if tip in kaynak_alan:
                    hedef[alan][tip] = kaynak_alan[tip]
            # "dosya" (indirilen dosya adedi) eski kayitlarda bazen tek sayi
            # (tum ekranlarin toplami), bazen ekran basina dict olarak duruyordu
            if isinstance(eski_dosya, dict) and tip in eski_dosya:
                hedef["dosya"][tip] = eski_dosya[tip]
            elif tip in (kayit.get("dosya_adlari") or {}):
                hedef["dosya"][tip] = len(kayit["dosya_adlari"][tip])
            kaynak_guncellenme = (kayit.get("guncellenme") or {}).get(tip)
            hedef["guncellenme"][tip] = (kaynak_guncellenme or kayit.get("son")
                                         or (f"{varsayilan_tarih} 00:00" if varsayilan_tarih else ""))
        if kayit.get("donem"):
            hedef["donem"] = kayit["donem"]
        if kayit.get("not"):
            hedef["not"] = kayit["not"]
        if kayit.get("son"):
            hedef["son"] = kayit["son"]
        elif varsayilan_tarih and not hedef.get("son"):
            hedef["son"] = f"{varsayilan_tarih} 00:00"


def main():
    ayarlar = ayarlari_oku()
    kok = indirme_koku(ayarlar)
    gunler = _gunluk_klasorler(kok)
    if not gunler:
        print(f"Birlestirilecek gunluk rapor bulunamadi ({kok} altinda tarihli klasor yok).")
        return 0

    print(f"Bulunan gunluk raporlar ({len(gunler)}): " + ", ".join(g.name for g in gunler))

    kok_rapor = kok / "rapor.json"
    if kok_rapor.exists():
        print("Mevcut surekli rapor da bulundu, en son/guvenilir kaynak olarak dahil edilecek.")

    birlesik = {}
    for gun in gunler:
        _kaydi_birlestir(birlesik, _veriyi_oku(gun / "rapor.json"), gun.name)
    if kok_rapor.exists():
        _kaydi_birlestir(birlesik, _veriyi_oku(kok_rapor), None)

    if not birlesik:
        print("Hicbir kayit okunamadi, islem yapilmadi.")
        return 1

    # guvenlik icin: uzerine yazmadan once mevcut surekli raporu yedekle
    if kok_rapor.exists() or (kok / "rapor.xlsx").exists():
        yedek = kok / f"rapor-birlestirme-oncesi-{datetime.now():%Y%m%d-%H%M%S}"
        yedek.mkdir(parents=True, exist_ok=True)
        for ad in ("rapor.json", "rapor.xlsx", "rapor.csv"):
            kaynak = kok / ad
            if kaynak.exists():
                shutil.copy2(kaynak, yedek / ad)
        print(f"Mevcut rapor yedeklendi: {yedek}")

    gecici = kok_rapor.with_suffix(".json.tmp")
    gecici.write_text(json.dumps(birlesik, ensure_ascii=False, indent=1), encoding="utf-8")
    gecici.replace(kok_rapor)

    # rapor.csv/xlsx'i ayni verilerden yeniden uretir (belge_tipi burada
    # kullanilmiyor, cunku eklenecek yeni sonuc ya da bekleyen firma yok)
    rapor.guncelle(kok, [], [], "e-arsiv-alis")

    toplam_firma = len(birlesik)
    toplam_ekran = sum(len(k.get("durumlar") or {}) for k in birlesik.values())
    print(f"\nBirlestirme tamamlandi: {toplam_firma} firma, {toplam_ekran} ekran.")
    print(f"Yeni surekli rapor: {kok / 'rapor.xlsx'}")
    print("Eski gunluk rapor dosyalarina dokunulmadi (arsiv olarak kaliyorlar).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
