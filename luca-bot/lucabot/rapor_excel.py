# -*- coding: utf-8 -*-
"""rapor.xlsx: gunun mutabakat ve ozet raporu (OpenPyXL).

Sayfalar:
    Firma Durumu          her firma tek satir; aksiyon gerekenler en ustte, renkli
    KDV Sonucu            her firmanin satis KDV - alis KDV - onceki donem devreden KDV sonucu:
                          odenecek KDV ya da sonraki doneme devreden KDV (devreden: firmalar.xlsx)
    İndirilen Faturalar   her fatura tek satir; e-Arsiv Alis <-> Interaktif V.D.
                          karsilastirmasi (Mutabakat sutunu)
    Dosyalar              inen her dosya ve klasoru (tiklayinca klasor acilir)
    Hatalar ve Uyarılar   sorunlu/bekleyen ekranlar, sebebi, ne yapilmasi gerektigi
                          ve (varsa) hata aninin ekran goruntusu

Veri rapor.json'dan gelir, yani ayni gun yapilan butun calismalari kapsar.
"""

from pathlib import Path

from . import gostergeler, rapor

BASLIK_RENGI = "1F4E78"
UYARI_RENGI = "FFF2CC"
HATA_RENGI = "F8CBAD"
IYI_RENGI = "E2EFDA"
PARA_BICIMI = '#,##0.00'
ARSIV_FARK_SEKMESI = "İnteraktif var, e-Arşiv yok"   # Excel sayfa adi en fazla 31 karakter

# Firma Durumu sayfasinda sayiya cevrilecek (TL) sutunlar
PARA_SUTUNLARI = {"Alış Matrah", "Alış KDV", "Satış Matrah", "Satış KDV"}

EKRAN_ADLARI = dict(rapor.SUTUNLAR)

NE_YAPMALI = [
    ("hata", "Programı tekrar çalıştırın ([D]evam seçeneği yalnızca bu ekranları dener)."
             " Tekrarlarsa ekran görüntüsünü gönderin."),
    ("dosya inmedi", "Tekrar çalıştırın; belge paketi inmedi."),
    ("excel inmedi", "Tekrar çalıştırın ([D]evam); Excel inmediği için tevkifat ve tutarlar eksik."),
    ("tamam (excel eksik)", "Belgeler indi, Excel inmedi; tekrar çalıştırın ([D]evam)."),
    ("ekran acilmadi", "Ekran menüden açılamadı; firmada bu ekran/modül var mı bakın,"
                       " yoksa firmalar.xlsx'te bu ekrana X koyun."),
    ("kaynaktan inmedi", "GİB kaynağı yanıt vermedi; bir süre sonra tekrar sorgulayın."),
    ("tamam (iptal eksik)", "Belgeler indi, iptal/itiraz ve Excel eksik; tekrar çalıştırın."),
    ("bekliyor", "Çalışma bu firmaya gelmeden durdu; tekrar çalıştırın."),
    ("atlandi", "Çok fatura var; e-Fatura portalinden elle indirin."),
    ("donem disi", "Firmanın bu döneme ait çalışma dönemi yok (kapanmış olabilir)."),
]


def _ne_yapmali(durum, not_metni=""):
    if "yetkisi yok" in (not_metni or ""):
        return "Firmanın bu servise yetkisi yok; firmalar.xlsx'te bu ekrana X koyabilirsiniz."
    if "kimlik dogrulanamadi" in (not_metni or ""):
        return ("Luca'da firma kartindaki GIB / Interaktif VD kullanici-sifre bilgilerini kontrol"
                " edin; bu donemin iptal/itiraz kontrolunu elle yapin.")
    if "takildi" in (not_metni or ""):
        return "GİB sorgusu yanıt vermedi; daha sonra tekrar deneyin."
    for anahtar, oneri in NE_YAPMALI:
        if (durum or "").startswith(anahtar):
            return oneri
    return ""


def _durum_grubu(durum):
    durum = durum or ""
    if durum in ("tamam (iptal eksik)", "tamam (excel eksik)"):
        return "sorunlu"
    if durum.startswith("tamam"):
        return "basarili"
    if durum == "fatura yok":
        return "bos"
    if durum.startswith("atlandi") or durum == "donem disi":
        return "atlanan"
    if durum == "bekliyor":
        return "bekliyor"
    return "sorunlu"


def _sayi(metin):
    """'1.234,56' -> 1234.56; bos -> None (hucre bos kalsin)."""
    if metin in ("", None):
        return None
    if isinstance(metin, (int, float)):
        return metin
    s = str(metin).replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return metin


# --- bicimlendirme yardimcilari -------------------------------------------

def _stiller():
    from openpyxl.styles import Alignment, Font, PatternFill
    return {
        "baslik_font": Font(bold=True, color="FFFFFF"),
        "baslik_dolgu": PatternFill("solid", fgColor=BASLIK_RENGI),
        "orta": Alignment(horizontal="center", vertical="center", wrap_text=True),
        "ust": Alignment(vertical="top", wrap_text=True),
        "uyari": PatternFill("solid", fgColor=UYARI_RENGI),
        "hata": PatternFill("solid", fgColor=HATA_RENGI),
        "iyi": PatternFill("solid", fgColor=IYI_RENGI),
        "kalin": Font(bold=True),
        "buyuk": Font(bold=True, size=14, color=BASLIK_RENGI),
        "bag": Font(color="0563C1", underline="single"),
    }


def _tablo(ws, basliklar, satirlar, genislikler, stil, ilk_satir=1, filtre=True):
    """Baslikli tablo yazar; baslik satirini sabitler ve suzgec ekler."""
    from openpyxl.utils import get_column_letter
    for j, b in enumerate(basliklar, 1):
        h = ws.cell(row=ilk_satir, column=j, value=b)
        h.font = stil["baslik_font"]
        h.fill = stil["baslik_dolgu"]
        h.alignment = stil["orta"]
    for i, satir in enumerate(satirlar, ilk_satir + 1):
        for j, deger in enumerate(satir, 1):
            h = ws.cell(row=i, column=j, value=deger)
            h.alignment = stil["ust"]
    for j, g in enumerate(genislikler, 1):
        ws.column_dimensions[get_column_letter(j)].width = g
    if filtre:
        ws.freeze_panes = ws.cell(row=ilk_satir + 1, column=1)
        son = ilk_satir + max(len(satirlar), 1)
        ws.auto_filter.ref = f"A{ilk_satir}:{get_column_letter(len(basliklar))}{son}"


def _klasor_bagi(hucre, yol, stil):
    if not yol:
        return
    try:
        hucre.hyperlink = Path(yol).resolve().as_uri()
        hucre.font = stil["bag"]
    except Exception:
        pass


# --- sayfalar ----------------------------------------------------------------

def _firma_durumu_sayfasi(ws, satirlar, stil):
    ws.title = "Firma Durumu"
    para = {i for i, b in enumerate(rapor.BASLIKLAR) if b in PARA_SUTUNLARI}
    duzeltilmis = [[_sayi(d) if j in para else d for j, d in enumerate(s)] for s in satirlar]
    genislik = ([26, 22, 16, 46] + [13] * len(rapor.SUTUNLAR)
                + [8, 46, 12, 12, 11, 14, 14, 14, 14, 11, 24, 16])
    _tablo(ws, rapor.BASLIKLAR, duzeltilmis, genislik, stil)
    for i, satir in enumerate(duzeltilmis, 2):
        if satir[3]:
            dolgu = stil["hata"] if str(satir[3]).startswith("HATA") else stil["uyari"]
            for j in range(1, len(rapor.BASLIKLAR) + 1):
                ws.cell(row=i, column=j).fill = dolgu
        for j in para:
            ws.cell(row=i, column=j + 1).number_format = PARA_BICIMI


KDV_BASLIKLARI = ["Firma", "Dönem", "Satış KDV", "Alış KDV (KDV2 hariç)", "KDV2 (Tevkif Edilen KDV)",
                  "Önceki Dönem Devreden KDV", "Ödenecek KDV (KDV2 hariç)", "Sonraki Döneme Devreden KDV (KDV2 hariç)",
                  "Ödenecek KDV (KDV2 dahil)", "Sonraki Döneme Devreden KDV (KDV2 dahil)", "Not"]


def _firmalar_devreden():
    """firmalar.xlsx'teki "Devreden KDV" sutunu ({kisa ad: tutar}); okunamazsa bos (sayfa yine yazilir)."""
    try:
        from .firma_listesi import devreden_kdvleri
        from .ortak import ayarlari_oku
        return devreden_kdvleri(ayarlari_oku().get("firma_listesi"))
    except (Exception, SystemExit):
        return {}


def _kdv_satirlari(kayitlar, devreden):
    """[(firma, donem, satis, alis, kdv2, onceki, odenecek, devreden, odenecek_kdv2, devreden_kdv2, not)]
    (KDV'si okunamayanlarda tutarlar None). Alis ve ilk iki sonuc KDV2 haric, son iki sonuc KDV2 dahildir."""
    satirlar = []
    for firma in sorted(kayitlar):
        k = kayitlar[firma]
        kdv = gostergeler.kdv_sonucu(k, firma, devreden)
        if not kdv["veri"]:
            satirlar.append((firma, k.get("donem", ""), None, None, None, kdv["onceki"], None, None, None, None,
                             "KDV tutarı okunamadı (Excel inmemiş ya da fatura yok)"))
            continue
        notlar = [] if kdv["onceki"] is not None else ["Önceki dönem devreden KDV girilmemiş (0 sayıldı)"]
        if kdv["kdv2_tahmini"]:
            notlar.append("KDV2 tahmini: tevkifat oranı okunamadı (tevkifatlı faturaların KDV'sinin tamamı sayıldı)")
        if kdv["kdv2_tutarsiz"]:
            notlar.append("KDV2 alış KDV'sinden büyük çıktı; kontrol edin")
        satirlar.append((firma, k.get("donem", ""), kdv["satis"], kdv["alis"], kdv["kdv2"], kdv["onceki"],
                         kdv["odenecek"], kdv["devreden"], kdv["odenecek_kdv2"], kdv["devreden_kdv2"],
                         "; ".join(notlar)))
    return satirlar


def _kdv_sayfasi(ws, kayitlar, devreden, stil):
    ws.title = "KDV Sonucu"
    satirlar = _kdv_satirlari(kayitlar, devreden)
    _tablo(ws, KDV_BASLIKLARI, satirlar, [26, 22, 16, 18, 18, 20, 18, 22, 18, 22, 52], stil)
    for i, satir in enumerate(satirlar, 2):
        for j in range(3, 11):
            ws.cell(row=i, column=j).number_format = PARA_BICIMI
        if satir[6]:  # odenecek KDV (KDV2 haric) var
            ws.cell(row=i, column=7).fill = stil["uyari"]
        if satir[7]:  # sonraki doneme devreden KDV (KDV2 haric) var
            ws.cell(row=i, column=8).fill = stil["iyi"]
        if satir[8]:  # odenecek KDV (KDV2 dahil) var
            ws.cell(row=i, column=9).fill = stil["uyari"]
        if satir[9]:
            ws.cell(row=i, column=10).fill = stil["iyi"]
    son = len(satirlar) + 1
    toplam = son + 1
    ws.cell(row=toplam, column=1, value="TOPLAM (süzülen satırlar)").font = stil["kalin"]
    for j, harf in ((3, "C"), (4, "D"), (5, "E"), (6, "F"), (7, "G"), (8, "H"), (9, "I"), (10, "J")):
        h = ws.cell(row=toplam, column=j, value=f"=SUBTOTAL(109,{harf}2:{harf}{max(son, 2)})")
        h.font = stil["kalin"]
        h.number_format = PARA_BICIMI
    italik = stil["kalin"].__class__(italic=True, color="595959")
    for sira, metin in enumerate((
            "Ödenecek KDV (KDV2 hariç) = satış KDV - alış KDV (KDV2 hariç) - önceki dönem devreden KDV (pozitifse); "
            "negatifse sonraki döneme devreden KDV olarak gösterilir. Önceki dönem devreden KDV firmalar.xlsx'teki "
            "\"Devreden KDV\" sütunundan gelir.",
            "KDV2 (tevkif edilen KDV): tevkifatlı faturada KDV'nin tevkifat oranı kadarı (örn. KDV 100 TL, tevkifat "
            "3/10 ise 30 TL). Luca Excel'inde tevkifatlı faturanın KDV sütunu yalnız satıcıya ödenen kısmı gösterir; tam KDV "
            "matrah x KDV oranından bulunur. Alıcı yalnız satıcıya ödenen kısmı (70 TL) hemen indirir. KDV2 ödendiğinde "
            "indirim konusu olur; ödenip ödenmeyeceği bilinemediği için iki sonuç verilir.",
            "Ödenecek KDV (KDV2 dahil) = satış KDV - (alış KDV + KDV2) - önceki dönem devreden KDV: KDV2'nin de "
            "indirildiği durumdaki sonuç."), start=2):
        ws.cell(row=toplam + sira, column=1, value=metin).font = italik


def _tevkifatli_nolar(kayit):
    """Firmanin tevkifatli alis faturalarinin numaralari (ekran klasorlerindeki tevkifatli.csv'den)."""
    import csv
    from .fatura_analiz import fatura_kimligi
    nolar = []
    for tip in rapor.TEVKIFAT_EKRANLARI:
        klasor = (kayit.get("klasorler") or {}).get(tip)
        if not klasor:
            continue
        try:
            with open(Path(klasor) / "tevkifatli.csv", encoding="utf-8-sig", newline="") as f:
                for satir in csv.reader(f):
                    k = fatura_kimligi(satir)
                    if k and k[1] not in nolar:
                        nolar.append(k[1])
        except OSError:
            continue
    return nolar


def _ayri_sekmeler(wb, kayitlar, devreden, stil):
    """Ayri sekmeler: KDV Ödemesi (odeme cikanlar), KDV2 (tevkifatli alis), SMM (e-SMM alis) ve
    "Interaktif'te var, e-Arsiv'de yok" faturalari (e-Arsiv'de var Interaktif'te yok tarafi yazilmaz)."""
    g = gostergeler.hesapla(kayitlar, devreden)
    donem = lambda f: (kayitlar.get(f) or {}).get("donem", "")

    ws = wb.create_sheet("KDV Ödemesi")
    satirlar = [(x["firma"], donem(x["firma"]), x["satis"], x["alis"], x["kdv2"], x["devreden"], x["odeme"],
                 x["odeme_kdv2"]) for x in g["kdv"]]
    _tablo(ws, ["Firma", "Dönem", "Satış KDV", "Alış KDV (KDV2 hariç)", "KDV2 (Tevkif Edilen KDV)",
                "Önceki Dönem Devreden KDV", "Ödenecek KDV (KDV2 hariç)", "Ödenecek KDV (KDV2 dahil)"], satirlar,
           [26, 22, 16, 18, 18, 24, 18, 18], stil)
    for i in range(2, len(satirlar) + 2):
        for j in range(3, 9):
            ws.cell(row=i, column=j).number_format = PARA_BICIMI
        ws.cell(row=i, column=7).fill = stil["uyari"]
    if not satirlar:
        ws.cell(row=2, column=1, value="Ödeme çıkan firma yok.").fill = stil["iyi"]

    ws = wb.create_sheet("KDV2")
    satirlar = [(x["firma"], donem(x["firma"]), x["adet"], x["tutar"], "Evet (oran okunamadı)" if x["tahmini"] else "",
                 ", ".join(_tevkifatli_nolar(kayitlar.get(x["firma"]) or {}))) for x in g["tevkifat"]]
    _tablo(ws, ["Firma", "Dönem", "Tevkifatlı alış faturası", "Tevkifat KDV (KDV2)", "Tahmini mi", "Fatura numaraları"],
           satirlar, [26, 22, 14, 18, 20, 80], stil)
    for i in range(2, len(satirlar) + 2):
        ws.cell(row=i, column=4).number_format = PARA_BICIMI
    if not satirlar:
        ws.cell(row=2, column=1, value="Tevkifatlı alış faturası yok.").fill = stil["iyi"]

    ws = wb.create_sheet("SMM")
    satirlar = [(x["firma"], donem(x["firma"]), x["adet"], x["tutar"]) for x in g["smm"]]
    _tablo(ws, ["Firma", "Dönem", "e-SMM alış makbuzu", "Tutar"], satirlar, [26, 22, 18, 16], stil)
    for i in range(2, len(satirlar) + 2):
        ws.cell(row=i, column=4).number_format = PARA_BICIMI
    if not satirlar:
        ws.cell(row=2, column=1, value="e-SMM alış makbuzu yok.").fill = stil["iyi"]

    ws = wb.create_sheet(ARSIV_FARK_SEKMESI)
    satirlar = []
    for r in gostergeler.fark_satirlari(g["fark"]):
        if r["durum"] == gostergeler.EKSIK or (r["durum"] == gostergeler.ESLESMEDI and r["kaynak"] == gostergeler.INTERAKTIF) \
                or r["durum"] == gostergeler.BELIRSIZ:
            satirlar.append((r["firma"], donem(r["firma"]), r["durum"], r["unvan"], r["no"], r["tutar"]))
    _tablo(ws, ["Firma", "Dönem", "Durum", "Ünvan", "Fatura No", "Tutar"], satirlar, [26, 22, 32, 30, 22, 16], stil)
    for i in range(2, len(satirlar) + 2):
        ws.cell(row=i, column=6).number_format = PARA_BICIMI
    if not satirlar:
        ws.cell(row=2, column=1, value="İnteraktif'te olup e-Arşiv'de olmayan fatura yok.").fill = stil["iyi"]


def _mutabakat_durumlari(kayit):
    """e-Arsiv Alis ile Interaktif V.D. listelerini fatura numarasiyla eslestirir."""
    eksik, fazla = rapor.fatura_farklari(kayit)
    if eksik is None:
        return {}
    if eksik and fazla and not rapor._ortak_fatura_var(kayit):
        return {"*": "karşılaştırılamadı (numaralar farklı biçimde)"}
    eksik_no = {rapor._no(s[1]) for s in eksik}
    fazla_no = {rapor._no(s[1]) for s in fazla}
    durumlar = {}
    for tip in ("e-arsiv-alis", "e-arsiv-interaktif"):
        for s in kayit["faturalar"].get(tip) or []:
            no = rapor._no(s[1]) if len(s) > 1 else ""
            if no in eksik_no:
                durumlar[(tip, no)] = "e-Arşiv'de YOK (İnteraktif'te var)"
            elif no in fazla_no:
                durumlar[(tip, no)] = "İnteraktif'te YOK (e-Arşiv'de var)"
            elif no:
                durumlar[(tip, no)] = "iki ekranda da var"
    return durumlar


def _fatura_sayfasi(ws, kayitlar, stil):
    ws.title = "İndirilen Faturalar"
    satirlar, renk = [], []
    for firma in sorted(kayitlar):
        k = kayitlar[firma]
        mutabakat = _mutabakat_durumlari(k)
        for tip, ad in rapor.SUTUNLAR:
            yon = ("Alış" if tip in rapor.ALIS_EKRANLARI or tip == "e-arsiv-interaktif"
                   else "Satış" if tip in rapor.SATIS_EKRANLARI else "")
            for f in k["faturalar"].get(tip) or []:
                if len(f) < 2:
                    continue
                no = rapor._no(f[1])
                durum = mutabakat.get((tip, no)) or (mutabakat.get("*", "") if tip in (
                    "e-arsiv-alis", "e-arsiv-interaktif") else "")
                satirlar.append([firma, ad, yon, f[0], f[1], rapor._tutar(f) or None, durum])
                renk.append("YOK" in durum)
    _tablo(ws, ["Firma", "Ekran", "Yön", "Karşı Taraf", "Fatura No", "Tutar (TL)", "Mutabakat"],
           satirlar, [26, 24, 8, 26, 20, 15, 34], stil)
    for i, (satir, uyari) in enumerate(zip(satirlar, renk), 2):
        ws.cell(row=i, column=6).number_format = PARA_BICIMI
        if uyari:
            for j in range(1, 8):
                ws.cell(row=i, column=j).fill = stil["uyari"]
    if not satirlar:
        ws.cell(row=2, column=1, value="Fatura ayrıntısı yok (henüz indirilen liste yok).")


def _dosya_sayfasi(ws, kayitlar, stil):
    ws.title = "Dosyalar"
    satirlar, klasorler = [], []
    for firma in sorted(kayitlar):
        k = kayitlar[firma]
        for tip, ad in rapor.SUTUNLAR:
            for dosya in k["dosya_adlari"].get(tip) or []:
                klasor = k["klasorler"].get(tip, "")
                satirlar.append([firma, ad, k["durumlar"].get(tip, ""), dosya, klasor])
                klasorler.append(klasor)
    _tablo(ws, ["Firma", "Ekran", "Durum", "Dosya", "Klasör (tıklayın)"],
           satirlar, [26, 24, 16, 40, 70], stil)
    for i, klasor in enumerate(klasorler, 2):
        _klasor_bagi(ws.cell(row=i, column=5), klasor, stil)


def _hata_sayfasi(ws, kayitlar, stil):
    ws.title = "Hatalar ve Uyarılar"
    satirlar, gorseller = [], []
    for firma in sorted(kayitlar):
        k = kayitlar[firma]
        for tip, durum in k["durumlar"].items():
            not_metni = k["notlar"].get(tip, "")
            grup = _durum_grubu(durum)
            sorunlu = grup in ("sorunlu", "bekliyor") or durum == "donem disi"
            uyari = bool(not_metni) and not sorunlu
            inmeyen = k["inmeyen"].get(tip, 0)
            if not (sorunlu or uyari or inmeyen):
                continue
            aciklama = not_metni
            if inmeyen:
                aciklama = (aciklama + " | " if aciklama else "") + f"{inmeyen} fatura kaynaktan inmedi"
            satirlar.append([firma, EKRAN_ADLARI.get(tip, tip), durum, "HATA" if grup == "sorunlu"
                             else "Uyarı", aciklama, _ne_yapmali(durum, not_metni),
                             "görüntüyü aç" if k["goruntuler"].get(tip) else ""])
            gorseller.append(k["goruntuler"].get(tip, ""))
    _tablo(ws, ["Firma", "Ekran", "Durum", "Tür", "Açıklama", "Ne yapmalı", "Ekran görüntüsü"],
           satirlar, [26, 24, 20, 8, 50, 60, 16], stil)
    for i, (satir, gorsel) in enumerate(zip(satirlar, gorseller), 2):
        dolgu = stil["hata"] if satir[3] == "HATA" else stil["uyari"]
        for j in range(1, 7):
            ws.cell(row=i, column=j).fill = dolgu
        _klasor_bagi(ws.cell(row=i, column=7), gorsel, stil)
    if not satirlar:
        h = ws.cell(row=2, column=1, value="Hata yok - bütün ekranlar sorunsuz işlendi.")
        h.fill = stil["iyi"]


def yaz(yol, kayitlar, satirlar, devreden=None):
    """rapor.xlsx'i bastan yazar; openpyxl yoksa None doner (rapor.csv yeterli).

    devreden: {kisa ad: onceki donem devreden KDV}; verilmezse firmalar.xlsx'ten okunur."""
    try:
        from openpyxl import Workbook
    except ImportError:
        return None
    for k in kayitlar.values():
        rapor._tamamla(k)
    stil = _stiller()
    wb = Workbook()
    _firma_durumu_sayfasi(wb.active, satirlar, stil)
    devreden = _firmalar_devreden() if devreden is None else devreden
    _kdv_sayfasi(wb.create_sheet(), kayitlar, devreden, stil)
    _ayri_sekmeler(wb, kayitlar, devreden, stil)
    _fatura_sayfasi(wb.create_sheet(), kayitlar, stil)
    _dosya_sayfasi(wb.create_sheet(), kayitlar, stil)
    _hata_sayfasi(wb.create_sheet(), kayitlar, stil)

    gecici = Path(yol).with_suffix(".tmp.xlsx")
    wb.save(str(gecici))
    try:
        gecici.replace(yol)
    except PermissionError:
        gecici.unlink(missing_ok=True)
        raise  # dosya Excel'de acik; cagiran kullaniciya soyler
    return yol
