# -*- coding: utf-8 -*-
"""firmalar.xlsx sablonu ve arayuzdeki "Firma / Ekran Secimi" tablosu.

Ekran sutunlarinda: ✓ (ya da bos) = o ekran sorgulanir, X = sorgulanmaz
(bkz. sabitler.ATLA_DEGERLERI; botun okudugu taraf firma_listesi.py).
Tabloyu yazarken dosyanin yalnizca firma ve ekran / Devreden KDV hucreleri
degisir; diger sutunlar, sayfalar ve bicimler korunur, once yedek alinir.
"""

import shutil
from datetime import datetime
from pathlib import Path

from .ortak import KOK, sadelestir
from .sabitler import ATLA_DEGERLERI, EKRAN_SUTUNLARI

SORGULA = "✓"
ATLA = "X"
AD_SUTUNU = "Kısa Adı"
KAPANIS_SUTUNU = "Kapanış Tarihi"
DEVREDEN_SUTUNU = "Devreden KDV"
SABLON_SUTUNLARI = [AD_SUTUNU, KAPANIS_SUTUNU, DEVREDEN_SUTUNU] + list(EKRAN_SUTUNLARI)

ACIKLAMA = [
    ("Kısa Adı", "Firmanın Luca'daki firma listesinde görünen adı (Luca adı kısaltıyorsa baş kısmı yeter)."),
    ("Kapanış Tarihi", "Firma kapandıysa GG/AA/YYYY. Dönem başlamadan kapanmış firma atlanır. Boşsa açık."),
    ("Devreden KDV", "Önceki dönemden devreden KDV (TL). 'KDV ödemesi çıkabilir' uyarısında düşülür. Boşsa 0."),
    ("Ekran sütunları", f"{SORGULA} (ya da boş) = o ekran bu firmada sorgulanır, {ATLA} = sorgulanmaz."),
    ("Listede olmayan firma", "Hiç işlenmez. Yalnızca ilk sayfa okunur; bu açıklama sayfası okunmaz."),
]


def _yol(yol):
    yol = Path(yol)
    return yol if yol.is_absolute() else KOK / yol


def sablon_olustur(yol, firmalar=()):
    """Bos (ya da verilen firmalarla dolu) firmalar.xlsx sablonu yazar."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "Firmalar"
    ws.append(SABLON_SUTUNLARI)
    for ad in firmalar or ["ÖRNEK FİRMA A.Ş."]:
        ws.append([ad, "", ""] + [SORGULA] * len(EKRAN_SUTUNLARI))
    baslik = PatternFill("solid", fgColor="1F4E78")
    for h in ws[1]:
        h.font = Font(bold=True, color="FFFFFF")
        h.fill = baslik
        h.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 32
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 15
    ws.column_dimensions["C"].width = 15
    for i in range(4, len(SABLON_SUTUNLARI) + 1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = 12
    ws.freeze_panes = "B2"
    secim = DataValidation(type="list", formula1=f'"{SORGULA},{ATLA}"', allow_blank=True)
    secim.error = f"{SORGULA} (sorgula) ya da {ATLA} (sorgulama) yazın"
    ws.add_data_validation(secim)
    son_harf = ws.cell(row=1, column=len(SABLON_SUTUNLARI)).column_letter
    secim.add(f"D2:{son_harf}2000")
    for satir in ws.iter_rows(min_row=2, min_col=4):
        for h in satir:
            h.alignment = Alignment(horizontal="center")

    a = wb.create_sheet("Açıklama")
    a.append(["Sütun", "Ne yazılır"])
    for s in ACIKLAMA:
        a.append(list(s))
    a.column_dimensions["A"].width = 24
    a.column_dimensions["B"].width = 100
    for h in a[1]:
        h.font = Font(bold=True)
    yol = Path(yol)
    wb.save(yol)
    return yol


def _baslik_satiri(ws):
    """Ilk en az iki dolu hucreli satir (firma_listesi ile ayni kural): (satir no, basliklar)."""
    for satir in ws.iter_rows():
        degerler = [h.value for h in satir]
        if len([d for d in degerler if d not in (None, "")]) >= 2:
            return satir[0].row, ["" if d is None else str(d).strip() for d in degerler]
    return None, []


def _sutun(basliklar, ad):
    aranan = sadelestir(ad)
    for i, b in enumerate(basliklar):
        if sadelestir(b) == aranan:
            return i
    return None


def _ad_sutunu(basliklar):
    for i, b in enumerate(basliklar):
        if "KISA AD" in sadelestir(b):
            return i
    return 0


def tabloyu_oku(yol):
    """[{"ad", "ekranlar": {sorgulanacak tipler}, "devreden": metin}] (dosyadaki sirayla)."""
    from openpyxl import load_workbook
    wb = load_workbook(_yol(yol), data_only=True)
    try:
        ws = wb.worksheets[0]
        satir_no, basliklar = _baslik_satiri(ws)
        if satir_no is None:
            return []
        ad_i = _ad_sutunu(basliklar)
        ekran_i = {tip: _sutun(basliklar, baslik) for baslik, tip in EKRAN_SUTUNLARI.items()}
        dev_i = _sutun(basliklar, DEVREDEN_SUTUNU)
        firmalar = []
        for satir in ws.iter_rows(min_row=satir_no + 1, values_only=True):
            ad = str(satir[ad_i]).strip() if ad_i < len(satir) and satir[ad_i] is not None else ""
            if not ad:
                continue
            ekranlar = set()
            for tip, i in ekran_i.items():
                deger = satir[i] if i is not None and i < len(satir) else None
                if sadelestir("" if deger is None else str(deger)) not in ATLA_DEGERLERI:
                    ekranlar.add(tip)
            dev = satir[dev_i] if dev_i is not None and dev_i < len(satir) else None
            firmalar.append({"ad": ad, "ekranlar": ekranlar,
                             "devreden": "" if dev is None else str(dev).strip()})
        return firmalar
    finally:
        wb.close()


def tabloyu_yaz(yol, firmalar):
    """Arayuzde yapilan secimleri dosyaya yazar; once yedek alir. Yedegin yolunu dondurur.

    Dosya Excel'de acikken PermissionError verir (cagiran kullaniciya soyler).
    """
    from openpyxl import load_workbook
    yol = _yol(yol)
    wb = load_workbook(yol)
    ws = wb.worksheets[0]
    satir_no, basliklar = _baslik_satiri(ws)
    if satir_no is None:
        raise ValueError("Dosyada başlık satırı bulunamadı")
    ad_i = _ad_sutunu(basliklar)

    def sutun(ad):
        i = _sutun(basliklar, ad)
        if i is None:  # eski listede olmayan sutun sona eklenir
            basliklar.append(ad)
            i = len(basliklar) - 1
            ws.cell(row=satir_no, column=i + 1, value=ad)
        return i

    ekran_i = {tip: sutun(baslik) for baslik, tip in EKRAN_SUTUNLARI.items()}
    dev_i = sutun(DEVREDEN_SUTUNU)
    secimler = {f["ad"]: f for f in firmalar}
    for satir in ws.iter_rows(min_row=satir_no + 1):
        hucre = satir[ad_i] if ad_i < len(satir) else None
        ad = str(hucre.value).strip() if hucre is not None and hucre.value is not None else ""
        f = secimler.get(ad)
        if f is None:
            continue
        r = hucre.row
        for tip, i in ekran_i.items():
            ws.cell(row=r, column=i + 1, value=SORGULA if tip in f["ekranlar"] else ATLA)
        dev = (f.get("devreden") or "").strip()
        ws.cell(row=r, column=dev_i + 1, value=_sayi_ya_da_metin(dev) if dev else None)

    yedek = yol.with_name(f"{yol.stem}.yedek-{datetime.now():%Y%m%d-%H%M%S}{yol.suffix}")
    shutil.copy2(yol, yedek)
    wb.save(yol)
    return yedek


def _sayi_ya_da_metin(metin):
    from .fatura_analiz import tutar_cozumle
    t = metin.replace(" ", "").replace("TL", "")
    if not t:
        return None
    if "," not in t and t.count(".") >= 1 and all(len(p) == 3 for p in t.split(".")[1:]):
        t = t.replace(".", "")  # "5.000" binlik nokta
    deger = tutar_cozumle(t)
    return deger if deger or t.strip("0,.") == "" else metin
