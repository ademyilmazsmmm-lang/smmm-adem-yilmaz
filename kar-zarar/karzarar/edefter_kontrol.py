# -*- coding: utf-8 -*-
"""e-Defter oncesi kontrol sonuclari: firma sonucu, JSON ve Excel (Luca'ya dokunmaz; tarayicisiz test edilebilir).

Sonuc (cikti/edefter.json): {"donem", "firmalar": [{firma, donem, durum, hata, hatalar: [...]}]}.
Her "hatalar" ogesi bir e-Defter hata kodunun taramasidir: {kod, ad, fis_sayisi, satir_sayisi, kesildi, fisler, mesaj, hata};
fisler: [{fis_no, tarih, degismeyen, satir, evrak, bt, odeme, tutar, hesap, aciklama}] (en cok luca_edefter.FIS_SINIRI).
durum: "tamam" (hicbir kodda uyumsuz fis yok), "sorun var" (en az bir kodda uyumsuz fis var), "hata" (tarama yapilamadi ya da
bazi kodlar taranamadi ve sorun bulunmadi: kontrol TAM degil).
"""

from collections import OrderedDict
from pathlib import Path

from . import muavin_karsilastir as mk

DOSYA = "edefter.json"
DURUM_YAZISI = {"tamam": "Gönderilebilir (uyumsuz fiş yok)", "sorun var": "UYUMSUZ FİŞ VAR", "hata": "Kontrol tamamlanamadı"}

# Luca'daki hata metinleri "... nolu fis(ler)de ..." kaliplidir; tabloda kisa ad gosterilir
KISA_AD = {
    "20021": "e-Defter başlangıç tarihinden önce numaralandırılmamış fiş",
    "20025": "Dengesiz veya pasif fiş",
    "20026": "Detaysız fiş",
    "20041": "Belge türü tanımı yok",
    "20042": "Belge tür, evrak no ve tarih uyumsuz",
    "20043": "Evrak no ve tarih var ama belge türü boş",
    "20044": "Birden fazla belge",
    "20045": "Birden fazla belge türü",
    "20046": "Bir fişte çok fazla fatura (50/100 sınırı)",
    "20047": "Birden fazla ödeme yöntemi",
    "20048": "Belge türü fatura olan birden fazla belge",
}


def kod_adi(kod, ad=""):
    return KISA_AD.get(str(kod)) or ad or f"Hata kodu {kod}"


def firma_sonucu(firma, donem, hatalar, hata=""):
    """Bir firmanin e-Defter kontrol sonucu (JSON'a yazilabilir)."""
    hatalar = [dict(h) for h in hatalar or []]
    sorun = sum(h.get("fis_sayisi", 0) for h in hatalar)
    taranamayan = [h for h in hatalar if h.get("hata")]
    if hata or (taranamayan and not sorun) or not hatalar:
        durum = "hata"
    else:
        durum = "sorun var" if sorun else "tamam"
    return {"firma": firma, "donem": donem, "hata": hata, "durum": durum, "hatalar": hatalar}


def sorun_sayisi(s):
    """Firmanin toplam uyumsuz fis sayisi (ayni fis birden cok hata kodunda gecebilir: kod basina sayilir)."""
    return sum(h.get("fis_sayisi", 0) for h in s.get("hatalar") or [])


def sorunlu_kodlar(s):
    """Uyumsuz fisi olan kodlar: [(kod, ad, fis_sayisi)]."""
    return [(h["kod"], kod_adi(h["kod"], h.get("ad", "")), h["fis_sayisi"]) for h in s.get("hatalar") or [] if h.get("fis_sayisi")]


def taranamayanlar(s):
    return [(h["kod"], h["hata"]) for h in s.get("hatalar") or [] if h.get("hata")]


def duzeltmeler(s):
    """Duzeltme denenen kodlar: [(kod, {fis, satir, kaydedildi, fatura_fis, mesaj})]."""
    return [(h["kod"], h["duzeltme"]) for h in s.get("hatalar") or [] if h.get("duzeltme")]


def duzeltme_yazisi(d):
    """'3 fiş (12 satır) MF + evrak no ile düzeltildi; 2 fatura fişine dokunulmadı' / neden yapılmadığı."""
    parcalar = []
    if d.get("kaydedildi"):
        parcalar.append(f"{d.get('fis', 0)} fiş ({d.get('satir', 0)} satır) MF + evrak no ile düzeltildi, {d.get('kaydedildi', 0)} kez Kaydet")
    if d.get("silinen"):
        parcalar.append(f"{d['silinen']} detaysız fiş silindi")
    kisa = "; ".join(parcalar) or "düzeltme yapılmadı"
    ek = f"; {d['fatura_fis']} fatura fişine dokunulmadı" if d.get("fatura_fis") else ""
    return kisa + ek + (f" — {d['mesaj']}" if d.get("mesaj") else "")


def fis_satiri(f):
    """'01023  01/07/2026  Evrak 89582  BT MF  3 satır  1.234,56'"""
    evrak = ", ".join(f.get("evrak") or []) or "-"
    tur = {True: "fatura fişi" + (f": {f['fatura_neden']}" if f.get("fatura_neden") else ""), False: "diğer fiş"}.get(f.get("fatura_fisi"), "")
    satir = (f"{f.get('fis_no') or '?':>8}  {f.get('tarih') or '-':10}  evrak {evrak[:24]:24}  BT {f.get('bt') or '-':4}  "
             f"ödeme {f.get('odeme') or '-':6}  {f.get('satir', 0)} satır")
    return (satir + (f"  ({tur})" if tur else "")
            + (f"  [{'; '.join(f['durum'])[:70]}]" if f.get("durum") else ""))


def kaydet(yol, donem, sonuclar):
    """cikti/edefter.json: ayni (firma, donem) yenisiyle degisir, digerleri korunur (muavin.json ile ayni bicim)."""
    return mk.kaydet(yol, donem, sonuclar)


def excel_yaz(yol, donem, firmalar):
    """e-Defter kontrol raporu (.xlsx): 'Firmalar' (firma basina hata kodu sayilari) + 'Uyumsuz fişler' (fis fis liste)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    ws = wb.active
    ws.title = "Firmalar"
    baslik_stili = (Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F3A5F"))

    def tablo(sayfa, basliklar, satirlar, genislik):
        sayfa.append(basliklar)
        for h in sayfa[1]:
            h.font, h.fill = baslik_stili
            h.alignment = Alignment(horizontal="center", wrap_text=True, vertical="center")
        for s in satirlar:
            sayfa.append(s)
        for i, g in enumerate(genislik, 1):
            sayfa.column_dimensions[get_column_letter(i)].width = g
        sayfa.freeze_panes = "A2"
        if satirlar:
            sayfa.auto_filter.ref = sayfa.dimensions

    kodlar = sorted({h["kod"] for s in firmalar for h in s.get("hatalar") or []})
    ozet, fisler = [], []
    for s in firmalar:
        sayilar = {h["kod"]: h for h in s.get("hatalar") or []}
        hucre = lambda k: ("?" if sayilar[k].get("hata") else sayilar[k]["fis_sayisi"]) if k in sayilar else ""
        not_ = s.get("hata") or "; ".join(f"{k}: {h[:80]}" for k, h in taranamayanlar(s))
        for k, d in duzeltmeler(s):
            not_ = (not_ + "; " if not_ else "") + f"{k}: {duzeltme_yazisi(d)}"
        ozet.append([s["firma"], s.get("donem") or donem, DURUM_YAZISI.get(s["durum"], s["durum"]), sorun_sayisi(s)]
                    + [hucre(k) for k in kodlar] + [not_])
        for h in s.get("hatalar") or []:
            for f in h.get("fisler") or []:
                fisler.append([s["firma"], h["kod"], kod_adi(h["kod"], h.get("ad", "")), f.get("fis_no", ""), f.get("tarih", ""),
                               f.get("degismeyen", ""), ", ".join(f.get("evrak") or []), f.get("bt", ""), f.get("odeme", ""),
                               f.get("satir", 0), f.get("tutar", 0.0), f.get("hesap", ""), f.get("aciklama", ""),
                               "; ".join(f.get("durum") or []),
                               {True: "Fatura fişi (elle)", False: "Diğer fiş (MF + evrak no atanabilir)"}.get(f.get("fatura_fisi"), ""),
                               f.get("fatura_neden", "")])
            if h.get("kesildi") or h.get("fis_sayisi", 0) > len(h.get("fisler") or []):
                fisler.append([s["firma"], h["kod"], kod_adi(h["kod"], h.get("ad", "")),
                               f"… toplam {h.get('fis_sayisi', 0)} fişten {len(h.get('fisler') or [])} tanesi listelendi", "", "", "", "",
                               "", "", "", "", "", "", "", ""])
    tablo(ws, ["Firma", "Dönem", "Durum", "Uyumsuz fiş"] + [f"{k}\n{KISA_AD.get(k, '')[:30]}" for k in kodlar] + ["Not"], ozet,
          [28, 24, 30, 12] + [16] * len(kodlar) + [60])
    sayfa = wb.create_sheet("Uyumsuz fişler")
    tablo(sayfa, ["Firma", "Hata kodu", "Hata", "Fiş No", "Fiş Tarihi", "Değişmeyen Fiş No", "Evrak No", "Belge Türü (BT)",
                  "Ödeme Türü", "Satır", "Borç toplamı", "İlk hesap", "Açıklama", "Luca durum açıklaması", "Fiş türü", "Fatura sayılma nedeni"], fisler,
          [28, 10, 40, 10, 12, 22, 24, 10, 12, 7, 14, 12, 50, 40, 22, 30])
    for satir in sayfa.iter_rows(min_row=2, min_col=11, max_col=11):
        for h in satir:
            h.number_format = "#,##0.00"
    gecici = Path(yol).with_suffix(".tmp.xlsx")
    wb.save(str(gecici))
    gecici.replace(yol)
    return yol
