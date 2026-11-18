# -*- coding: utf-8 -*-
"""Indirilen gelen/giden faturalarin Luca muavininde (191 / 391) bulunup bulunmadigini denetler.

    ALIS  faturalari  -> muavin 191 Indirilecek KDV
    SATIS faturalari  -> muavin 391 Hesaplanan KDV

2. sinif (isletme/serbest meslek defteri) firmalarda 191/391 olmadigindan ayni kontrol isletme defteri dokumundeki
GIDERLER (alis) ve GELIRLER (satis) 'Evrak No' sutununa karsi yapilir (isletme_defteri_satirlari).

Kural: fatura ancak FATURA NO ve GENEL TOPLAM (KDV dahil) tutari ikisi de uyusuyorsa sorunsuzdur.
    * numara 191/391 (isletme defterinde Evrak No) satirlarinda yok            -> EKSIK
    * numara var ama genel toplam tutar kayitlarda yok                          -> TUTAR FARKI
    * numara ve tutar uyuyor                                                    -> ESLESEN
    * iptal/itiraz edilmis fatura ve KDV'si 0 olan fatura (191/391'e dusmez)    -> sayilir, sorun sayilmaz
Muavinde genel toplam 191/391 satirinda degil, ayni fisin karsi hesap satirindadir: bu yuzden muavin TUM hesaplarla
indirilir. Numarali 191/391 satirinin fisindeki (fis no + tip + tarih) satirlardan biri 100/102/309/320/120/108/321/121
hesaplarindan birinde fatura toplamina esitse VEYA 191/391'deki KDV + fisteki matrah fatura toplamina esitse tutar uyuyor
sayilir. Isletme defterinde dogrudan satirin 'Toplam' sutunu karsilastirilir.
Tevkifatli faturalarda tutar kontrolu yapilmaz (karsi hesaba tevkifat dusulmus tutar yazilir).

Tarayiciya dokunmaz; yalniz dosyalarla calisir (bkz. testler/test_muavin.py). Muavin Excel'inin sutunlari
basliktan bulunur (Luca sablonu degisirse kod degil baslik eslemesi guncellenir).
"""

import csv
import json
import re
from collections import OrderedDict
from datetime import date, datetime
from pathlib import Path

from lucabot import rapor as fatura_rapor
from lucabot.fatura_analiz import (fatura_kimligi, matrah_kdv_sutunlari, satir_toplam_tutari, tutar_cozumle)
from lucabot.ortak import sadelestir, tarih_cozumle
from lucabot.sabitler import TARIH_DESENI

TOLERANS = 0.05          # TL; yuvarlama farklari
YON_HESAP = {"alis": "191", "satis": "391"}
YON_ADI = {"alis": "Alış", "satis": "Satış"}
HESAP_DESENI = re.compile(r"^(\d{3})(?:[.\s-]\d+)*\b")


# --- yardimcilar -------------------------------------------------------------------------------

NO_DESENI = re.compile(r"(?<![A-Za-z0-9ÇĞİÖŞÜçğıöşü])([A-Za-z0-9ÇĞİÖŞÜçğıöşü]{3}\d{13})(?![A-Za-z0-9])")


def fatura_no_bul(*metinler):
    """Metinlerde gecen fatura numaralari (16 hane: 3 on ek + yil + sira); sirali, tekrarsiz.

    Aciklama icinde numara serbest metne gomulu olabilir ("ABC2026000000123 nolu fatura"); numara
    tire/bosluk ayrimli yazildiysa ("ABC-2026000000123") tireler kaldirilarak da aranir."""
    bulunan = []
    for m in metinler:
        metin = str(m or "")
        for aday in (metin, metin.replace("-", ""), metin.replace(" ", "")):
            for e in NO_DESENI.finditer(aday):
                no = e.group(1).upper()
                if no not in bulunan:
                    bulunan.append(no)
    return bulunan


def _tarih(metin):
    if isinstance(metin, (datetime, date)):
        return metin.date() if isinstance(metin, datetime) else metin
    m = TARIH_DESENI.search(str(metin or ""))
    if not m:
        return None
    t = m.group(0).replace(".", "/").replace("-", "/")
    try:
        if re.match(r"\d{4}/", t):
            y, a, g = t.split("/")
            return date(int(y), int(a), int(g))
        return tarih_cozumle(t)
    except ValueError:
        return None


def _sayi(h):
    if h is None or h == "":
        return 0.0
    if isinstance(h, (int, float)):
        return float(h)
    return tutar_cozumle(h)


# --- muavin Excel'i -------------------------------------------------------------------------------

def muavin_satirlari(yol, varsayilan_hesap=""):
    """Muavin Excel'inden [{hesap, tarih, fis, aciklama, borc, alacak, metin, nolar}].

    Baslik satiri BORC ve ALACAK sutunlarini iceren ilk satirdir. Tarihi olan ve borc/alacagi sifirdan farkli
    satirlar kayittir; ustundeki '191 INDIRILECEK KDV' gibi satirlar hesabi belirler (yoksa varsayilan_hesap).
    Devir/toplam satirlari (tarihsiz) atlanir."""
    import warnings
    from openpyxl import load_workbook
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = load_workbook(str(yol), read_only=False, data_only=True)
    satirlar = []
    for ws in wb.worksheets:
        try:
            ws.reset_dimensions()
        except Exception:
            pass
        baslik, hesap = None, varsayilan_hesap
        for ham in ws.iter_rows(values_only=True):
            hucre = list(ham)
            if baslik is None:
                adlar = [sadelestir(str(h or "")) for h in hucre]
                if any("BORC" in a for a in adlar) and any("ALACAK" in a for a in adlar):
                    ilk = lambda *anahtar: next((i for i, a in enumerate(adlar) if any(k in a for k in anahtar)), None)
                    baslik = {"tarih": ilk("TARIH"), "fis": ilk("FIS NO", "FIS", "YEVMIYE"),
                              "aciklama": ilk("ACIKLAMA", "ACIKLAM"), "belge": ilk("BELGE", "EVRAK"),
                              "tip": ilk("TIP", "TUR"),
                              "borc": next(i for i, a in enumerate(adlar) if "BORC" in a),
                              "alacak": next(i for i, a in enumerate(adlar) if "ALACAK" in a)}
                else:
                    m = HESAP_DESENI.match(str(hucre[0] or "").strip()) if hucre else None
                    if m:
                        hesap = m.group(1)
                continue
            al = lambda i: hucre[i] if i is not None and i < len(hucre) else None
            borc, alacak = _sayi(al(baslik["borc"])), _sayi(al(baslik["alacak"]))
            tarih = _tarih(al(baslik["tarih"]))
            ilk_hucre = str(hucre[0] or "").strip() if hucre else ""
            if tarih is None or not (borc or alacak):
                m = HESAP_DESENI.match(ilk_hucre)
                if m and not (borc or alacak):   # "191 INDIRILECEK KDV" bolum satiri
                    hesap = m.group(1)
                continue
            metin = " ".join(str(h) for i, h in enumerate(hucre)
                             if h is not None and i not in (baslik["borc"], baslik["alacak"]) and not isinstance(h, (int, float)))
            satirlar.append({"hesap": hesap, "tarih": tarih, "fis": str(al(baslik["fis"]) or "").strip(),
                             "tip": str(al(baslik["tip"]) or "").strip(),
                             "aciklama": str(al(baslik["aciklama"]) or "").strip(),
                             "belge": str(al(baslik["belge"]) or "").strip(),
                             "borc": borc, "alacak": alacak, "metin": metin,
                             "nolar": fatura_no_bul(al(baslik["belge"]), al(baslik["aciklama"]), metin)})
    return satirlar


def isletme_defteri_satirlari(yol):
    """Isletme/Serbest Meslek defteri dokumu (Excel) -> muavin_satirlari ile ayni bicimde satirlar.

    2. sinif firmalarda 191/391 yoktur; fatura numarasi GIDERLER (alis) ve GELIRLER (satis) tablolarinin 'Evrak No'
    sutununda aranir. Giderler 191'e, Gelirler 391'e karsilik sayilir (karsilastir() ayni mantikla calisir).
    Bolum 'GIDERLER' / 'GELIRLER' satiridir; basligi 'Evrak No' iceren satirdir; tutar sutunlari ('K.D.V.', 'Toplam')
    onceki satirdaki basliklardan bulunur. Kaydi olmayan satirlar ('Toplam :' vb.) atlanir."""
    import warnings
    from openpyxl import load_workbook
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = load_workbook(str(yol), read_only=False, data_only=True)
    ad = lambda h: re.sub(r"[^A-Z]", "", sadelestir(str(h or "")))
    satirlar = []
    for ws in wb.worksheets:
        try:
            ws.reset_dimensions()
        except Exception:
            pass
        bolum, tutar_basligi, sutun = None, {}, None
        for ham in ws.iter_rows(values_only=True):
            hucre = list(ham)
            adlar = [ad(h) for h in hucre]
            ilk = next((a for a in adlar if a), "")
            if ilk in ("GIDERLER", "GELIRLER") and sum(1 for a in adlar if a) == 1:
                bolum, tutar_basligi, sutun = ("gider" if ilk == "GIDERLER" else "gelir"), {}, None
                continue
            if bolum is None:
                continue
            if "EVRAKNO" in adlar:
                sutun = {"kayit": adlar.index("KAYITNO") if "KAYITNO" in adlar else None, "evrak": adlar.index("EVRAKNO"),
                         "tarih": adlar.index("TARIH") if "TARIH" in adlar else None,
                         "aciklama": adlar.index("ACIKLAMA") if "ACIKLAMA" in adlar else None, **tutar_basligi}
                continue
            if "TOPLAM" in adlar and sutun is None:          # tutar basliklari (Gider | Alinan Emtia | Indirilecek KDV | Toplam)
                tutar_basligi = {"kdv": next((i for i, a in enumerate(adlar) if a.endswith("KDV")), None),
                                 "toplam": adlar.index("TOPLAM")}
                continue
            if sutun is None:
                continue
            al = lambda i: hucre[i] if i is not None and i < len(hucre) else None
            evrak, tarih = str(al(sutun["evrak"]) or "").strip(), _tarih(al(sutun["tarih"]))
            if not evrak or tarih is None:
                continue
            kdv, toplam = _sayi(al(sutun.get("kdv"))), _sayi(al(sutun.get("toplam")))
            acik = str(al(sutun["aciklama"]) or "").strip()
            gider = bolum == "gider"
            satirlar.append({"hesap": "191" if gider else "391", "tarih": tarih, "fis": str(al(sutun["kayit"]) or "").strip(),
                             "aciklama": acik, "belge": evrak, "borc": kdv if gider else 0.0, "alacak": 0.0 if gider else kdv,
                             "metin": f"{evrak} {acik}", "toplam": toplam, "nolar": fatura_no_bul(evrak, acik)})
    return satirlar


# --- fatura tarafi -----------------------------------------------------------------------------

def _csv_oku(yol):
    try:
        with open(yol, encoding="utf-8-sig", newline="") as f:
            return [r for r in csv.reader(f) if any(h.strip() for h in r)]
    except OSError:
        return []


def _basligi_ayir(satirlar):
    """(basliklar, veri): ilk satir baslik gibiyse (fatura numarasi icermiyor ve harfli) baslik sayilir."""
    if not satirlar:
        return [], []
    ilk = satirlar[0]
    if fatura_kimligi(ilk) is None and any(sum(c.isalpha() for c in h) >= 3 for h in ilk):
        return ilk, satirlar[1:]
    return [], satirlar


def klasorden_faturalar(klasor, tip):
    """Bir ekranin klasorundeki liste.csv'den [{no, tarih, unvan, toplam, kdv, tip}]; dosya yoksa []."""
    klasor = Path(klasor)
    basliklar, veri = _basligi_ayir(_csv_oku(klasor / "liste.csv"))
    _, kdv_sutunlari = matrah_kdv_sutunlari(basliklar) if basliklar else ([], [])
    iptal = set()
    ib, iv = _basligi_ayir(_csv_oku(klasor / "iptal-itiraz.csv"))
    for s in iv:
        k = fatura_kimligi(s)
        if k:
            iptal.add(k[1])
    tevkifat = set()
    tb, tv = _basligi_ayir(_csv_oku(klasor / "tevkifatli.csv"))
    for s in tv:
        k = fatura_kimligi(s)
        if k:
            tevkifat.add(k[1])
    faturalar = []
    for s in veri:
        k = fatura_kimligi(s)
        if not k:
            continue
        unvan, no = k
        kdv = None
        if kdv_sutunlari:
            kdv = round(sum(tutar_cozumle(s[i]) for i in kdv_sutunlari if i < len(s)), 2)
        tarih = next((_tarih(h) for h in s if _tarih(h)), None)
        faturalar.append({"no": no, "tarih": tarih, "unvan": unvan,
                          "toplam": satir_toplam_tutari(basliklar, s) if basliklar else 0.0,
                          "kdv": kdv, "tip": tip, "iptal": no in iptal, "tevkifat": no in tevkifat})
    return faturalar


def faturalari_oku(rapor_klasoru, firma, bas, bit):
    """indirilenler/rapor.json'daki firma kaydindan {"alis": [...], "satis": [...]}: donemdeki, mukerrersiz faturalar.

    Ayni fatura birden cok ekranda gorunebilir (TURMOB alis = e-Fatura alis; interaktif = e-Arsiv alis);
    numaraya gore tek sayilir, KDV'si bilinen kayit tercih edilir."""
    yol = Path(rapor_klasoru) / "rapor.json"
    try:
        kayit = json.loads(yol.read_text(encoding="utf-8")).get(firma)
    except (OSError, ValueError):
        kayit = None
    sonuc = {"alis": OrderedDict(), "satis": OrderedDict()}
    if not kayit:
        return {"alis": [], "satis": []}
    for tip, klasor in (kayit.get("klasorler") or {}).items():
        yon = "alis" if tip in fatura_rapor.ALIS_EKRANLARI or tip == "e-arsiv-interaktif" else \
            "satis" if tip in fatura_rapor.SATIS_EKRANLARI else None
        if yon is None or not klasor:
            continue
        for f in klasorden_faturalar(klasor, tip):
            if f["tarih"] and not (bas <= f["tarih"] <= bit):
                continue
            eski = sonuc[yon].get(f["no"])
            if eski is None or (eski["kdv"] is None and f["kdv"] is not None):
                sonuc[yon][f["no"]] = f
    return {y: list(d.values()) for y, d in sonuc.items()}


# --- karsilastirma -----------------------------------------------------------------------------

def _fis_anahtari(s):
    return (s.get("fis") or "", s.get("tip") or "", s["tarih"]) if s.get("fis") else None


KARSI_HESAPLAR = frozenset({"100", "102", "309", "320", "120", "108", "321", "121"})   # genel toplamin yazildigi hesaplar


def kayit_tutarlari(yon, satirlar_f, fis_indeksi):
    """(karsi, hesaplanan): faturanin numarasini tasiyan KDV satirlarinin fisinde genel toplam adaylari.

    karsi      = fisteki 100/102/309/320/120/108/321/121 satirlarinin tutari (odeme / cari karsiligi, genel toplam);
    hesaplanan = KDV + matrah: numarali KDV satiri + fisteki baska bir matrah satiri; ya da fisteki KDV ve matrah
                 taraflarinin (alis borc, satis alacak) KARSI olmayan tum satirlarinin toplami (tek faturalik fis).
    Isletme defterinde satirin 'Toplam' sutunu dogrudan genel toplamdir."""
    karsi, hesaplanan = [], []
    isletme = [s for s in satirlar_f if s.get("toplam") is not None]
    if len(isletme) > 1:    # isletme defterinde fatura kalem kalem birden cok satira bolunur: ayni numarali satirlarin toplami
        hesaplanan.append(round(sum(s["toplam"] for s in isletme), 2))
    for s in satirlar_f:
        if s.get("toplam") is not None:
            karsi.append(s["toplam"])
            continue
        fis = fis_indeksi.get(_fis_anahtari(s), [s])
        net = (lambda r: r["borc"] - r["alacak"]) if yon == "alis" else (lambda r: r["alacak"] - r["borc"])
        for r in fis:
            if r["hesap"] in KARSI_HESAPLAR or not r["hesap"]:
                karsi.append(abs(net(r)))
        matrah_tarafi = [r for r in fis if r["hesap"] not in KARSI_HESAPLAR and r["hesap"] and net(r) > 0]
        kdv = net(s)
        hesaplanan += [net(r) + kdv for r in matrah_tarafi if r is not s and r["hesap"] != YON_HESAP[yon]]
        hesaplanan.append(sum(net(r) for r in matrah_tarafi))
    return [t for t in karsi if t], [t for t in hesaplanan if t]


def karsilastir(yon, faturalar, satirlar, tol=TOLERANS):
    """Tek yon (alis/satis): {"eslesen", "eksik", "tutar_farki", "iptal", "kdvsiz", "satir"}; listeler fatura sozlukleri tasir.

    KDV hesabi (alis 191, satis 391) satirlarinda fatura numarasi aranir; bulunursa genel toplam tutari fisin satirlariyla
    karsilastirilir. satirlar tum hesaplari icerebilir (muavin); hesabi bilinmeyen satirlar da KDV satiri sayilir."""
    hesap = YON_HESAP[yon]
    kdv_satirlari = [s for s in satirlar if not s["hesap"] or s["hesap"] == hesap]
    indeks = {}
    for s in kdv_satirlari:
        for no in s["nolar"]:
            indeks.setdefault(no, []).append(s)
    fis_indeksi = {}
    for s in satirlar:
        if _fis_anahtari(s):
            fis_indeksi.setdefault(_fis_anahtari(s), []).append(s)
    sonuc = {"eslesen": [], "eksik": [], "tutar_farki": [], "iptal": [], "kdvsiz": [], "tutar_okunamadi": [],
             "satir": len(kdv_satirlari)}
    for f in faturalar:
        if f.get("iptal"):
            sonuc["iptal"].append(f)
            continue
        if f.get("kdv") is not None and abs(f["kdv"]) < tol:
            sonuc["kdvsiz"].append(f)     # KDV'siz fatura muavinde 191/391'e dusmez
            continue
        satirlar_f = indeks.get(f["no"])
        if not satirlar_f:
            sonuc["eksik"].append(f)
            continue
        toplam = f.get("toplam")
        if not toplam or f.get("tevkifat"):
            sonuc["eslesen"].append(f)    # tutar bilinmiyor / tevkifatli: yalniz numara kontrol edilir
            continue
        if all(s.get("toplam") is not None and not s["toplam"] for s in satirlar_f):
            # isletme defteri dokumunde 'Toplam' sutunu okunamadi (hepsi 0): tutar karsilastirilamaz, yalniz numara kontrol edilir
            sonuc["tutar_okunamadi"].append(f)
            sonuc["eslesen"].append(f)
            continue
        karsi, hesaplanan = kayit_tutarlari(yon, satirlar_f, fis_indeksi)
        if any(abs(t - toplam) <= tol for t in karsi + hesaplanan):
            sonuc["eslesen"].append(f)
        else:
            gorunen = sorted({round(t, 2) for t in (karsi or hesaplanan)}, reverse=True)[:4]
            toplam_kayit = round(sum(s["toplam"] for s in satirlar_f if s.get("toplam") is not None), 2) if len(satirlar_f) > 1 else None
            sonuc["tutar_farki"].append(dict(f, kayit=gorunen, kayit_toplam=toplam_kayit, fis=", ".join(sorted({s["fis"] for s in satirlar_f if s["fis"]}))))
    return sonuc


KAYNAK_ADI = {"muavin": "Muavin (191/391)", "isletme": "İşletme defteri (gider/gelir)"}


def firma_sonucu(firma, donem, faturalar, muavin_satirlari_, hata="", kaynak="muavin"):
    """Bir firmanin iki yonlu sonucu; JSON'a yazilabilir (tarihler metne cevrilir).

    kaynak: "muavin" (1. sinif, 191/391) ya da "isletme" (2. sinif, isletme defteri gider/gelir dokumu)."""
    sonuc = {"firma": firma, "donem": donem, "hata": hata, "durum": "hata" if hata else "tamam", "kaynak": kaynak, "yon": {}}
    if hata:
        return sonuc
    sorun = 0
    for yon in ("alis", "satis"):
        k = karsilastir(yon, faturalar.get(yon, []), muavin_satirlari_)
        sonuc["yon"][yon] = {"fatura": len(faturalar.get(yon, [])), "eslesen": len(k["eslesen"]), "satir": k["satir"],
                             "eksik": [_f(f) for f in k["eksik"]], "tutar_farki": [_f(f) for f in k["tutar_farki"]],
                             "iptal": len(k["iptal"]), "kdvsiz": len(k["kdvsiz"]), "tutar_okunamadi": len(k["tutar_okunamadi"])}
        sorun += len(k["eksik"]) + len(k["tutar_farki"])
    sonuc["durum"] = "fark var" if sorun else "tamam"
    return sonuc


def _f(f):
    d = {"no": f["no"], "tarih": f["tarih"].strftime("%d/%m/%Y") if f.get("tarih") else "", "unvan": f.get("unvan", ""),
         "toplam": f.get("toplam", 0.0), "kdv": f.get("kdv")}
    if "kayit" in f:
        d["kayit"], d["fis"] = f["kayit"], f.get("fis", "")
        if f.get("kayit_toplam") is not None:
            d["kayit_toplam"] = f["kayit_toplam"]
    return d


def tl(tutar):
    """1234.5 -> '1.234,50' (None -> '?')."""
    if tutar is None:
        return "?"
    return f"{tutar:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def eksik_satiri(yon, f):
    """Gunluk/arayuz icin tek satir: 'Alış  06/10/2026  ABC2026000000002  UNVAN  KDV 100,00 TL  KDV dahil 600,00 TL'
    (tarih - fatura no - unvan/isim - KDV - KDV dahil tutar)."""
    satir = (f"{YON_ADI[yon]:5} {f['tarih'] or '-':10}  {f['no']}  {f.get('unvan') or '-'}  "
             f"KDV {tl(f['kdv'])} TL  KDV dahil {tl(f['toplam'])} TL")
    if f.get("kayit") is not None:
        satir += (f"  (kayıtta: {', '.join(tl(t) for t in f['kayit']) or 'tutar yok'}"
                  + (f"; satırların toplamı {tl(f['kayit_toplam'])}" if f.get("kayit_toplam") is not None else "")
                  + f"; fiş {f.get('fis') or '?'})")
    return satir


# --- kayit ve Excel ------------------------------------------------------------------------------

DOSYA = "muavin.json"


def kaydet(yol, donem, sonuclar):
    """cikti/muavin.json: {"donem", "firmalar": [...]}; ayni (firma, donem) yenisiyle degisir, digerleri korunur."""
    eski = []
    try:
        eski = json.loads(Path(yol).read_text(encoding="utf-8")).get("firmalar") or []
    except (OSError, ValueError):
        pass
    anahtar = lambda s: (s["firma"], s.get("donem") or donem)
    birlesik = OrderedDict((anahtar(s), s) for s in eski)
    for s in sonuclar.values() if isinstance(sonuclar, dict) else sonuclar:
        s.setdefault("donem", donem)
        birlesik[anahtar(s)] = s
    gecici = Path(yol).with_suffix(".json.tmp")
    gecici.write_text(json.dumps({"donem": donem, "firmalar": list(birlesik.values())}, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    gecici.replace(yol)


def excel_yaz(yol, donem, firmalar):
    """Muavin karsilastirma raporu (.xlsx): 'Özet' (firma basina sayilar) + 'Eksik (muavinde yok)': inen fatura listesinde olup
    muavinde / isletme defterinde olmayan faturalar: tarih, fatura no, unvan/isim, KDV, KDV dahil tutar."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Özet"
    baslik_stili = (Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F3A5F"))

    def tablo(sayfa, basliklar, satirlar, genislik):
        sayfa.append(basliklar)
        for h in sayfa[1]:
            h.font, h.fill = baslik_stili
            h.alignment = Alignment(horizontal="center", wrap_text=True)
        for s in satirlar:
            sayfa.append(s)
        for i, g in enumerate(genislik, 1):
            sayfa.column_dimensions[chr(64 + i)].width = g
        sayfa.freeze_panes = "A2"
        if satirlar:
            sayfa.auto_filter.ref = sayfa.dimensions

    ozet, eksikler, farklar = [], [], []
    for s in firmalar:
        kaynak = KAYNAK_ADI.get(s.get("kaynak", "muavin"), "")
        if s.get("hata"):
            ozet.append([s["firma"], s.get("donem") or donem, "HATA", kaynak, "", "", "", "", "", "", "", s["hata"]])
            continue
        a, t = s["yon"]["alis"], s["yon"]["satis"]
        ozet.append([s["firma"], s.get("donem") or donem, "SORUN VAR" if s["durum"] == "fark var" else "Tamam", kaynak,
                     a["fatura"], len(a["eksik"]), len(a["tutar_farki"]), t["fatura"], len(t["eksik"]), len(t["tutar_farki"]),
                     a["iptal"] + t["iptal"] + a["kdvsiz"] + t["kdvsiz"], ""])
        for yon in ("alis", "satis"):
            for f in s["yon"][yon]["eksik"]:
                eksikler.append([s["firma"], YON_ADI[yon], f["tarih"], f["no"], f["unvan"], f["kdv"], f["toplam"]])
            for f in s["yon"][yon]["tutar_farki"]:
                farklar.append([s["firma"], YON_ADI[yon], f["tarih"], f["no"], f["unvan"], f["kdv"], f["toplam"],
                                ", ".join(f"{x:.2f}" for x in f.get("kayit", [])), f.get("fis", "")])
    tablo(ws, ["Firma", "Dönem", "Durum", "Kaynak", "Alış fatura", "Alış eksik", "Alış tutar uyuşmuyor", "Satış fatura",
               "Satış eksik", "Satış tutar uyuşmuyor", "İptal/KDV'siz (sayılmadı)", "Not"], ozet,
          [26, 24, 11, 26, 10, 10, 12, 10, 10, 12, 14, 50])
    sayfa = wb.create_sheet("Eksik (muavinde yok)")
    tablo(sayfa, ["Firma", "Yön", "Tarih", "Fatura No", "Ünvan / İsim", "KDV", "KDV dahil tutar"], eksikler,
          [26, 8, 11, 20, 34, 14, 18])
    sayfa2 = wb.create_sheet("Tutar uyuşmuyor")
    tablo(sayfa2, ["Firma", "Yön", "Tarih", "Fatura No", "Ünvan / İsim", "KDV", "KDV dahil tutar (fatura)",
                   "Kayıttaki tutarlar", "Fiş no"], farklar, [26, 8, 11, 20, 34, 14, 18, 36, 16])
    for sh, kol in ((sayfa, (6, 7)), (sayfa2, (6, 7))):
        for satir in sh.iter_rows(min_row=2, min_col=kol[0], max_col=kol[1]):
            for h in satir:
                h.number_format = "#,##0.00"
    gecici = Path(yol).with_suffix(".tmp.xlsx")
    wb.save(str(gecici))
    gecici.replace(yol)
    return yol
