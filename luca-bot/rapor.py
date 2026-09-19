# -*- coding: utf-8 -*-
"""Gunluk calismanin tum belge tiplerini tek dosyada toplayan rapor.

Her firma icin tek satir: hangi ekrandan kac fatura geldi, ikisi arasinda fark
var mi, iptal/itiraz ve tevkifatli kac tane, ne yapilmasi gerekiyor.
Ara durum rapor.json'da tutulur; ayni gun icinde farkli belge tipleriyle
calistirildikca ayni satirlar guncellenir.
"""

import csv
import json
from datetime import datetime

# rapora sutun olarak giren belge tipleri (sira sutun sirasidir)
SUTUNLAR = [
    ("e-arsiv-alis", "e-Arşiv Alış"),
    ("e-arsiv-interaktif", "İnteraktif V.D."),
    ("e-arsiv-satis", "e-Arşiv Satış"),
    ("e-fatura-alis", "e-Fatura Alış"),
    ("e-fatura-satis", "e-Fatura Satış"),
]

# kotu durum once gelsin; firmanin genel durumu bunlarin en kotusudur
DURUM_ONCELIGI = ["hata", "dosya inmedi", "kaynaktan inmedi", "donem disi", "fatura yok",
                  "tamam", "bekliyor"]

BASLIKLAR = (["Firma", "Dönem", "Durum", "Aksiyon"]
             + [ad for _, ad in SUTUNLAR]
             + ["Fark", "Eksik Faturalar", "İptal/İtiraz", "Tevkifatlı", "İnmeyen",
                "İnen Dosya", "Not", "Son İşlem"])


def _bos_kayit(firma):
    return {"firma": firma, "donem": "", "durumlar": {}, "sayilar": {}, "iptal": {},
            "tevkifat": {}, "inmeyen": {}, "faturalar": {}, "dosya": 0, "not": "", "son": ""}


def _oku(yol):
    if not yol.exists():
        return {}
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _genel_durum(durumlar):
    for durum in DURUM_ONCELIGI:
        for d in durumlar.values():
            if d.startswith(durum):
                return d
    return next(iter(durumlar.values()), "")


def _en_yuksek(sozluk):
    """Ayni faturalar iki ekranda da goruldugu icin toplam degil en yuksek alinir."""
    return max(sozluk.values()) if sozluk else 0


def _fark(kayit):
    """Iki e-arsiv ekraninin fatura sayisi farki (ikisi de calistiysa)."""
    a = kayit["sayilar"].get("e-arsiv-alis")
    b = kayit["sayilar"].get("e-arsiv-interaktif")
    if a is None or b is None:
        return ""
    return b - a


def _eksik_faturalar(kayit, sinir=12):
    """Interaktif listede olup Luca listesinde olmayan faturalar.

    Cikti: "Unvanin ilk kelimesi + fatura numarasinin son 5 hanesi"
    (orn. "TURKCELL 00554"), boylece firmaya donup bakmaya gerek kalmaz.
    """
    faturalar = kayit.get("faturalar", {})
    luca = faturalar.get("e-arsiv-alis")
    gib = faturalar.get("e-arsiv-interaktif")
    if not gib or luca is None:
        return ""
    olanlar = {no for _, no in luca}
    eksikler = [(unvan, no) for unvan, no in gib if no not in olanlar]
    if not eksikler:
        return ""
    metin = ", ".join(f"{(unvan or '?')[:14]} {no[-5:]}" for unvan, no in eksikler[:sinir])
    if len(eksikler) > sinir:
        metin += f" ... (+{len(eksikler) - sinir})"
    return metin


def _aksiyon(kayit):
    isler = []
    durum = _genel_durum(kayit["durumlar"])
    if durum.startswith("hata"):
        isler.append("HATA - tekrar calistir")
    if durum.startswith("dosya inmedi"):
        isler.append("DOSYA INMEDI - tekrar calistir")
    if sum(kayit["inmeyen"].values()):
        isler.append("KAYNAKTAN INMEDI - tekrar sorgula")
    fark = _fark(kayit)
    if isinstance(fark, int) and fark > 0:
        eksikler = _eksik_faturalar(kayit, sinir=4)
        isler.append(f"EKSIK - {fark} fatura" + (f": {eksikler}" if eksikler else ""))
    if _en_yuksek(kayit["iptal"]):
        isler.append(f"IPTAL/ITIRAZ - {_en_yuksek(kayit['iptal'])} fatura")
    if _en_yuksek(kayit["tevkifat"]):
        isler.append(f"TEVKIFAT - {_en_yuksek(kayit['tevkifat'])} fatura, KDV2 kontrol")
    return " | ".join(isler)


def _satir(kayit):
    satir = [kayit["firma"], kayit["donem"], _genel_durum(kayit["durumlar"]), _aksiyon(kayit)]
    satir += [kayit["sayilar"].get(tip, "") for tip, _ in SUTUNLAR]
    satir += [_fark(kayit),
              _eksik_faturalar(kayit),
              _en_yuksek(kayit["iptal"]) or "",
              _en_yuksek(kayit["tevkifat"]) or "",
              sum(kayit["inmeyen"].values()) or "",
              kayit["dosya"] or "",
              kayit["not"], kayit["son"]]
    return satir


def guncelle(klasor, sonuclar, bekleyenler, belge_tipi):
    """Calisma sonuclarini gunun raporuna isler; rapor.xlsx ve rapor.csv yazar."""
    durum_yolu = klasor / "rapor.json"
    kayitlar = _oku(durum_yolu)
    simdi = datetime.now().strftime("%d/%m/%Y %H:%M")

    for s in sonuclar:
        kayit = kayitlar.setdefault(s["firma"], _bos_kayit(s["firma"]))
        tip = s.get("belge_tipi", belge_tipi)
        kayit["durumlar"][tip] = s.get("durum", "")
        kayit["sayilar"][tip] = s.get("fatura_sayisi", 0)
        kayit["iptal"][tip] = s.get("iptal_itiraz", 0)
        kayit["tevkifat"][tip] = s.get("tevkifat", 0)
        kayit["inmeyen"][tip] = s.get("indirilemeyen", 0)
        kayit.setdefault("faturalar", {})[tip] = s.get("faturalar", [])
        kayit["dosya"] = kayit.get("dosya", 0) + len(s.get("dosyalar", []))
        if s.get("donem"):
            kayit["donem"] = s["donem"]
        if s.get("not"):
            kayit["not"] = s["not"]
        kayit["son"] = simdi

    for firma in bekleyenler:
        kayit = kayitlar.setdefault(firma, _bos_kayit(firma))
        kayit["durumlar"].setdefault(belge_tipi, "bekliyor")

    with open(durum_yolu, "w", encoding="utf-8") as f:
        json.dump(kayitlar, f, ensure_ascii=False, indent=1)

    satirlar = [_satir(k) for k in kayitlar.values()]
    satirlar.sort(key=lambda r: (not r[3], r[0]))  # aksiyon gerektirenler en uste

    with open(klasor / "rapor.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(BASLIKLAR)
        w.writerows(satirlar)

    return _excel_yaz(klasor / "rapor.xlsx", satirlar)


def _excel_yaz(yol, satirlar):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        return None  # openpyxl yoksa rapor.csv yeterli

    wb = Workbook()
    ws = wb.active
    ws.title = "Firma Durumu"
    ws.append(BASLIKLAR)

    baslik_dolgu = PatternFill("solid", fgColor="1F4E78")
    for hucre in ws[1]:
        hucre.font = Font(bold=True, color="FFFFFF")
        hucre.fill = baslik_dolgu
        hucre.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    uyari = PatternFill("solid", fgColor="FFF2CC")   # aksiyon gerekiyor
    kirmizi = PatternFill("solid", fgColor="F8CBAD")  # hata
    for satir in satirlar:
        ws.append(satir)
        if satir[3]:
            dolgu = kirmizi if satir[3].startswith("HATA") else uyari
            for hucre in ws[ws.max_row]:
                hucre.fill = dolgu
        for hucre in ws[ws.max_row]:
            hucre.alignment = Alignment(vertical="top", wrap_text=True)

    genislik = [26, 22, 16, 46] + [13] * len(SUTUNLAR) + [8, 46, 12, 12, 11, 11, 24, 16]
    for i, g in enumerate(genislik, 1):
        ws.column_dimensions[get_column_letter(i)].width = g
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(BASLIKLAR))}{ws.max_row}"

    wb.save(str(yol))
    return yol
