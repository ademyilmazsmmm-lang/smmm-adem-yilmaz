# -*- coding: utf-8 -*-
"""Gunluk calismanin tum belge tiplerini tek dosyada toplayan rapor.

Her firma icin tek satir: hangi ekrandan kac fatura geldi, ikisi arasinda fark
var mi, iptal/itiraz ve tevkifatli kac tane, ne yapilmasi gerekiyor.
Ara durum rapor.json'da tutulur; ayni gun icinde farkli belge tipleriyle
calistirildikca ayni satirlar guncellenir.
"""

import csv
import json
import os
from datetime import datetime

# rapora sutun olarak giren belge tipleri (sira sutun sirasidir)
SUTUNLAR = [
    ("e-arsiv-alis", "e-Arşiv Alış"),
    ("e-arsiv-interaktif", "İnteraktif V.D."),
    ("e-arsiv-satis", "e-Arşiv Satış"),
    ("e-fatura-alis", "e-Fatura Alış"),
    ("e-fatura-satis", "e-Fatura Satış"),
    ("gib-5000", "GİB 5000/30000"),
    ("turmob-alis", "TÜRMOB Alış"),
    ("turmob-satis", "TÜRMOB Satış"),
    ("esmm-alis", "e-SMM Alış"),
    ("esmm-satis", "e-SMM Satış"),
]

# Tevkifat uyarisi yalnizca ALIS ekranlarindan uretilir: KDV2 beyani alis
# faturalarindaki tevkifat icin verilir, satis tarafindaki tevkifat bu beyana
# girmedigi icin raporu ve e-postayi bosuna dolduruyordu.
TEVKIFAT_EKRANLARI = {"e-arsiv-alis", "e-arsiv-interaktif", "e-fatura-alis",
                      "gib-5000", "turmob-alis", "esmm-alis"}

# Alis/satis toplam KDV ve matrah buradan hesaplanir. e-arsiv-interaktif
# kasten disarida: e-arsiv-alis ile ayni faturalari gosterir, ikisini de
# toplarsak alis tutari iki katina cikar. GIB 5000/30000, GIB portalinden
# elle kesilen (Luca'ya entegre olmayan) faturalarin bildirimi oldugu icin
# satis tarafinda sayilir.
ALIS_EKRANLARI = {"e-arsiv-alis", "e-fatura-alis", "turmob-alis", "esmm-alis"}
SATIS_EKRANLARI = {"e-arsiv-satis", "e-fatura-satis", "gib-5000",
                   "turmob-satis", "esmm-satis"}

# Bu gruplardaki ekranlar ayni faturalari gosterebilir (birden fazla
# entegrator, GIB 5000/30000'in e-Arsiv Satis ile ayni faturalari tasimasi
# gibi); toplamda hepsi sayilirsa tutar cifte sayilir, en yuksek olan alinir.
# Tek kaynak burasi: calisma.py de bunu rapor.ortusen_grubu() ile kullanir.
#   - e-arsiv-alis / e-arsiv-interaktif: ikisi de ayni e-arsiv alis faturalari
#   - turmob-alis / e-fatura-alis: birden fazla entegratorde ayni alis faturalari
#   - e-arsiv-satis / gib-5000 / turmob-satis / e-fatura-satis: TURMOB Satis
#     ekrani hem e-Fatura hem e-Arsiv uzerinden kesilen satis faturalarini da
#     getiriyor; GIB 5000/30000 da e-Arsiv Satis ile ayni faturalari tasiyor.
#     Dorduncusunun de ayni satis faturalarini gosterdigi durumlarda bu grup
#     hepsini kapsiyor.
ORTUSEN_GRUPLARI = [
    {"e-arsiv-alis", "e-arsiv-interaktif"},
    {"turmob-alis", "e-fatura-alis"},
    {"e-arsiv-satis", "gib-5000", "turmob-satis", "e-fatura-satis"},
]


def ortusen_grubu(belge_tipi):
    """belge_tipi'nin ait oldugu ortusen grubu; girmiyorsa tek basina kendisi."""
    for grup in ORTUSEN_GRUPLARI:
        if belge_tipi in grup:
            return frozenset(grup)
    return frozenset({belge_tipi})

# kotu durum once gelsin; firmanin genel durumu bunlarin en kotusudur
# Once gercek sorunlar. "fatura yok" en sona yakin: bir ekranda fatura
# bulunmamasi, digerinde fatura inen firmayi "fatura yok" gostermemeli.
DURUM_ONCELIGI = ["hata", "dosya inmedi", "kaynaktan inmedi", "donem disi",
                  "atlandi", "tamam (excel", "tamam", "fatura yok", "bekliyor"]

BASLIKLAR = (["Firma", "Dönem", "Durum", "Aksiyon"]
             + [ad for _, ad in SUTUNLAR]
             + ["Fark", "Eksik/Fazla Faturalar", "İptal/İtiraz", "Tevkifatlı Alış", "İnmeyen",
                "Alış Matrah", "Alış KDV", "Satış Matrah", "Satış KDV",
                "İnen Dosya", "Not", "Son İşlem"])


def _bos_kayit(firma):
    return {"firma": firma, "donem": "", "durumlar": {}, "sayilar": {}, "iptal": {},
            "tevkifat": {}, "inmeyen": {}, "faturalar": {}, "dosya": {}, "not": "", "son": "",
            "matrah": {}, "kdv": {}, "notlar": {}, "dosya_adlari": {}, "klasorler": {},
            "goruntuler": {}, "sureler": {}}


# eski gunlerden kalan rapor.json kayitlarinda sonradan eklenen alanlar yok
_SOZLUK_ALANLARI = ("durumlar", "sayilar", "iptal", "tevkifat", "inmeyen", "faturalar",
                    "matrah", "kdv", "notlar", "dosya_adlari", "klasorler", "goruntuler", "sureler")


def _tamamla(kayit):
    for alan in _SOZLUK_ALANLARI:
        if not isinstance(kayit.get(alan), dict):
            kayit[alan] = {}
    kayit.setdefault("donem", "")
    kayit.setdefault("not", "")
    kayit.setdefault("son", "")
    return kayit


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
    """Iki e-arsiv ekraninin fatura sayisi farki.

    GIB tarafi (interaktif) Luca tarafinin ust kumesidir. Luca'da fatura
    varken GIB tarafi bos gorunuyorsa liste okunamamis demektir; boyle bir
    farki yazmak yaniltici olur, bos birakilir.
    """
    a = kayit["sayilar"].get("e-arsiv-alis")
    b = kayit["sayilar"].get("e-arsiv-interaktif")
    if a is None or b is None:
        return ""
    if b == 0 and a > 0:
        return ""
    return b - a


def _okunamadi(kayit):
    """Interaktif V.D. listesi fatura bazinda karsilastirmaya uygun mu."""
    a = kayit["sayilar"].get("e-arsiv-alis")
    b = kayit["sayilar"].get("e-arsiv-interaktif")
    if a is None or b is None:
        return False
    if b == 0 and a > 0:
        return True
    # ekran kayit sayisini verdi ama satirlari okunamadi: eksikler listelenemez
    return bool(b) and not kayit.get("faturalar", {}).get("e-arsiv-interaktif")


def _no(metin):
    """Fatura numarasini karsilastirilabilir hale getirir."""
    return "".join(ch for ch in (metin or "").upper() if ch.isalnum())


def _tutar(satir, sira=2, varsayilan=0):
    """faturalar listesindeki (unvan, no, tutar) uclusunden tutari okur.

    rapor.json'da bu ozellik eklenmeden once yazilmis eski kayitlarda tutar
    olmayabilir (iki elemanli liste); boyle durumda 0 sayilir.
    """
    return satir[sira] if len(satir) > sira else varsayilan


def _tutar_yaz(x):
    """1234.5 -> '1.234,50' (virgul/nokta Turkce siraya cevrilir)."""
    if not x:
        return ""
    return f"{x:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _grup_toplami(kayit, alan, ekranlar):
    """Ekran grubundaki (orn. ALIS_EKRANLARI) tutarlarin toplami.

    Ayni faturalari farkli ekranlardan gosteren gruplarda (bkz.
    ORTUSEN_GRUPLARI) en yuksek olan alinir, ikisi de toplanmaz.
    """
    degerler = kayit.get(alan) or {}
    islenen = set()
    toplam = 0
    for grup in ORTUSEN_GRUPLARI:
        ilgili = grup & ekranlar
        if not ilgili:
            continue
        toplam += max((degerler.get(tip, 0) for tip in ilgili), default=0)
        islenen |= ilgili
    for tip in ekranlar - islenen:
        toplam += degerler.get(tip, 0)
    return toplam


def fatura_farklari(kayit):
    """(GIB'de olup Luca'da olmayanlar, Luca'da olup GIB'de olmayanlar).

    Iki ekranin inen listeleri fatura numarasi uzerinden karsilastirilir.
    Listelerden biri hic yoksa (None, None) doner.
    """
    faturalar = kayit.get("faturalar") or {}
    luca = faturalar.get("e-arsiv-alis")
    gib = faturalar.get("e-arsiv-interaktif")
    if luca is None or gib is None:
        return None, None
    luca_no = {_no(s[1]) for s in luca if len(s) > 1 and _no(s[1])}
    gib_no = {_no(s[1]) for s in gib if len(s) > 1 and _no(s[1])}
    eksik = [s for s in gib if len(s) > 1 and _no(s[1]) and _no(s[1]) not in luca_no]
    fazla = [s for s in luca if len(s) > 1 and _no(s[1]) and _no(s[1]) not in gib_no]
    return eksik, fazla


def _ortak_fatura_var(kayit):
    """Iki listede ortak fatura numarasi var mi (numaralandirma ayni mi)."""
    faturalar = kayit.get("faturalar") or {}
    luca = {_no(s[1]) for s in (faturalar.get("e-arsiv-alis") or []) if len(s) > 1}
    gib = {_no(s[1]) for s in (faturalar.get("e-arsiv-interaktif") or []) if len(s) > 1}
    return bool(luca & gib)


def _fatura_listesi(kayitlar, sinir):
    """Cikti: "Unvanin ilk kelimesi + fatura numarasinin son 5 hanesi (tutar)"."""
    parcalar = []
    for satir in kayitlar[:sinir]:
        unvan, no = satir[0], satir[1]
        tutar = _tutar(satir)
        parca = f"{unvan or '?'} {no[-5:]}"
        if tutar:
            parca += f" ({_tutar_yaz(tutar)} TL)"
        parcalar.append(parca)
    metin = ", ".join(parcalar)
    if len(kayitlar) > sinir:
        metin += f" ... (+{len(kayitlar) - sinir})"
    return metin


def _eksik_faturalar(kayit, sinir=10):
    """Iki ekranin fatura listeleri arasindaki fark, iki yonlu.

    Yalnizca "GIB'de var Luca'da yok" yazilirsa, Luca'da fazladan duran
    (orn. iptal edilip GIB listesinden dusen) faturalar gorunmuyordu.
    """
    eksik, fazla = fatura_farklari(kayit)
    if eksik is None:
        if kayit["sayilar"].get("e-arsiv-interaktif") and kayit.get("faturalar", {}).get("e-arsiv-alis"):
            return "interaktif liste okunamadi"
        return ""
    if eksik and fazla and not _ortak_fatura_var(kayit):
        # hicbir numara tutmuyorsa listeler farkli bicimde numaralanmis demektir
        return "listeler eslesmedi (fatura numaralari farkli bicimde)"
    parcalar = []
    if eksik:
        parcalar.append("İnteraktif'te var, e-Arşiv'de yok: " + _fatura_listesi(eksik, sinir))
    if fazla:
        parcalar.append("e-Arşiv'de var, İnteraktif'te yok: " + _fatura_listesi(fazla, sinir))
    if not parcalar and _fark(kayit):
        # sayilar tutmuyor ama numaralar ortusuyor: ayni fatura iki kez listelenmis
        parcalar.append("sayilar farkli, fatura numaralari ayni")
    return " | ".join(parcalar)


def _aksiyon(kayit):
    isler = []
    durum = _genel_durum(kayit["durumlar"])
    if durum.startswith("hata"):
        isler.append("HATA - tekrar calistir")
    if durum.startswith("tamam (excel"):
        isler.append("EXCEL/IPTAL EKSIK - belgeler indi, ikinci turda tamamla")
    if durum.startswith("dosya inmedi"):
        isler.append("DOSYA INMEDI - tekrar calistir")
    if durum.startswith("atlandi"):
        isler.append("ELLE INDIR - cok fatura, e-fatura portalinden indirin")
    if sum(kayit["inmeyen"].values()):
        isler.append("KAYNAKTAN INMEDI - tekrar sorgula")
    fark = _fark(kayit)
    if _okunamadi(kayit):
        isler.append("KARSILASTIRILAMADI - interaktif V.D. listesi okunamadi")
    eksik, fazla = fatura_farklari(kayit)
    if eksik and fazla and not _ortak_fatura_var(kayit):
        eksik = fazla = []
        isler.append("KARSILASTIRILAMADI - iki listenin fatura numaralari tutmuyor")
    if eksik:
        isler.append(f"EKSIK - İnteraktif'te olup e-Arşiv'de olmayan {len(eksik)} fatura:"
                     f" {_fatura_listesi(eksik, 4)}")
    if fazla:
        isler.append(f"FAZLA - e-Arşiv'de olup İnteraktif'te olmayan {len(fazla)} fatura:"
                     f" {_fatura_listesi(fazla, 4)}")
    if not eksik and not fazla and isinstance(fark, int) and fark:
        isler.append(f"SAYI FARKI - {abs(fark)} fatura, numaralar ortusuyor")
    if _en_yuksek(kayit["iptal"]):
        isler.append(f"IPTAL/ITIRAZ - {_en_yuksek(kayit['iptal'])} fatura")
    if _en_yuksek(kayit["tevkifat"]):
        isler.append(f"TEVKIFAT - {_en_yuksek(kayit['tevkifat'])} alis faturasi, KDV2 kontrol")
    return " | ".join(isler)


def _dosya_sayisi(kayit):
    dosya = kayit.get("dosya") or {}
    return sum(dosya.values()) if isinstance(dosya, dict) else dosya


def _satir(kayit):
    satir = [kayit["firma"], kayit["donem"], _genel_durum(kayit["durumlar"]), _aksiyon(kayit)]
    satir += [kayit["sayilar"].get(tip, "") for tip, _ in SUTUNLAR]
    satir += [_fark(kayit),
              _eksik_faturalar(kayit),
              _en_yuksek(kayit["iptal"]) or "",
              _en_yuksek(kayit["tevkifat"]) or "",
              sum(kayit["inmeyen"].values()) or "",
              _tutar_yaz(_grup_toplami(kayit, "matrah", ALIS_EKRANLARI)),
              _tutar_yaz(_grup_toplami(kayit, "kdv", ALIS_EKRANLARI)),
              _tutar_yaz(_grup_toplami(kayit, "matrah", SATIS_EKRANLARI)),
              _tutar_yaz(_grup_toplami(kayit, "kdv", SATIS_EKRANLARI)),
              _dosya_sayisi(kayit) or "",
              kayit["not"], kayit["son"]]
    return satir


def guncelle(klasor, sonuclar, bekleyenler, belge_tipi):
    """Calisma sonuclarini gunun raporuna isler; rapor.xlsx ve rapor.csv yazar."""
    durum_yolu = klasor / "rapor.json"
    kayitlar = _oku(durum_yolu)
    simdi = datetime.now().strftime("%d/%m/%Y %H:%M")

    for kayit in kayitlar.values():
        _tamamla(kayit)

    for s in sonuclar:
        kayit = kayitlar.setdefault(s["firma"], _bos_kayit(s["firma"]))
        tip = s.get("belge_tipi", belge_tipi)
        kayit["durumlar"][tip] = s.get("durum", "")
        kayit["sayilar"][tip] = s.get("fatura_sayisi", 0)
        kayit["iptal"][tip] = s.get("iptal_itiraz", 0)
        kayit["tevkifat"][tip] = s.get("tevkifat", 0) if tip in TEVKIFAT_EKRANLARI else 0
        kayit["inmeyen"][tip] = s.get("indirilemeyen", 0)
        kayit.setdefault("matrah", {})[tip] = s.get("matrah", 0) or 0
        kayit.setdefault("kdv", {})[tip] = s.get("kdv", 0) or 0
        kayit.setdefault("faturalar", {})[tip] = s.get("faturalar", [])
        # ayni gun icinde tekrar calistirilinca sayi sismesin diye tip basina tutulur
        if not isinstance(kayit.get("dosya"), dict):
            kayit["dosya"] = {}
        kayit["dosya"][tip] = len(s.get("dosyalar", []))
        kayit["dosya_adlari"][tip] = list(s.get("dosyalar", []))
        kayit["notlar"][tip] = s.get("not", "")
        kayit["klasorler"][tip] = s.get("klasor", "")
        kayit["goruntuler"][tip] = s.get("ekran_goruntusu", "")
        kayit["sureler"][tip] = s.get("sure", 0)
        if s.get("donem"):
            kayit["donem"] = s["donem"]
        if s.get("not"):
            kayit["not"] = s["not"]
        kayit["son"] = simdi

    for firma in bekleyenler:
        kayit = kayitlar.setdefault(firma, _bos_kayit(firma))
        kayit["durumlar"].setdefault(belge_tipi, "bekliyor")

    # once gecici dosyaya yazilip yer degistirilir: yazarken elektrik/bilgisayar
    # kesilirse yarim kalan dosya yuzunden onceki gunun tum durumu kaybolmasin
    gecici = durum_yolu.with_suffix(".json.tmp")
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(kayitlar, f, ensure_ascii=False, indent=1)
    os.replace(gecici, durum_yolu)

    satirlar = [_satir(k) for k in kayitlar.values()]
    satirlar.sort(key=lambda r: (not r[3], r[0]))  # aksiyon gerektirenler en uste

    with open(klasor / "rapor.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(BASLIKLAR)
        w.writerows(satirlar)

    from . import rapor_excel  # openpyxl yoksa rapor.csv yine de yazilmis olur
    return rapor_excel.yaz(klasor / "rapor.xlsx", kayitlar, satirlar)


def ozet_csv_yaz(ozet_yolu, kalan_yolu, sonuclar, bekleyenler, belge_tipi):
    """Ekran bazinda duz ozet; her firmadan sonra yeniden yazilir, islenmeyenler 'bekliyor'."""
    with open(ozet_yolu, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Firma", "Belge Tipi", "Fatura Sayisi", "Indirilemeyen", "Iptal/Itiraz",
                    "Durum", "Dosyalar"])
        for s in sonuclar:
            w.writerow([s["firma"], s["belge_tipi"], s["fatura_sayisi"], s.get("indirilemeyen", 0),
                        s.get("iptal_itiraz", 0), s["durum"], "; ".join(s["dosyalar"])])
        for firma in bekleyenler:
            w.writerow([firma, belge_tipi, "", "", "", "bekliyor", ""])
    kalan_yolu.write_text(", ".join(bekleyenler), encoding="utf-8")
