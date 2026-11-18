# -*- coding: utf-8 -*-
"""Akilli Ent. Toplu Sorgulama ile hizli mod.

Luca'nin yeni "Akilli Ent. Toplu Sorgulama" ekrani tum entegrasyonlari (GIB e-Arsiv/e-Fatura,
GIB 5000/30000, e-SMM, TURMOB ...) tek seferde, 1 aya kadar sorguluyor. Bu modul her firma icin
iki ekrani (Alis / Satis) sirayla isler:

    1. menu                      (luca_gezinme.toplu_menuye_git)
    2. Entegrasyon Sec           (yalniz izinli entegrasyonlar; TURMOB yalniz kullanan firmada)
    3. Secili Entegrasyonlardan Getir (en fazla 1 aylik parcalarla) -> "tamamlandi" bekle
    4. Belge Ara + liste         (entegrasyon bilgisi icin)
    5. Excel (tutarlar) ve - alista - Secilenleri Indir (XML/zip)
    6. her belge tipi icin sonuc (ortak.yeni_sonuc) uretilir; rapor/e-posta ayni kalir

Basarisiz olursa None doner; cagiran (calisma.py) o firmanin ekranlarini eski ekran-ekran
yolla isler. Saf hesaplama kisimlari (entegrasyon secimi, Excel/liste esleme) tarayicisiz
test edilebilir (bkz. testler/test_toplu.py).
"""

import re
import time
from collections import OrderedDict

from .bekleme import geri_cekil, kosulu_bekle, sayfa_canli, sayfa_durulsun
from .fatura_analiz import (BOS_DEGERLER, csv_yaz, donem_satirlari, fatura_tarihi, excelden_tablo, matrah_kdv_sutunlari,
                            sutun_indeksi, sutun_tam_indeksi, tutar_cozumle)
from .gib_sorgu import belge_ara, islem_gunlugu, sorgu_bitti_mi
from .indirme import dosya_indir
from .liste_secim import ekrandaki_satirlar, hepsini_sec
from .luca_ekran import (acik_pencere, acik_pencereleri_kapat, cerceveler, dugmeye_bas,
                         fatura_yok_penceresini_kapat, pencerede_tikla,
                         tarih_araligi_yaz, tarih_kutulari, varsa_tikla, eski_kutulari_isaretle,
                         diyalog_bekle)
from .luca_gezinme import donem_ayarla, firma_sec, toplu_menuye_git
from .ortak import (AYAR, TARIH_BICIMI, dosya_adi_yap, gunluge_yaz, hedef_ay_araligi, sadelestir, tarih_araliklari,
                    tarih_cozumle, yaz, yeni_sonuc)
from . import rapor
from .sabitler import (FATURA_NO_DESENI, TOPLU_AZAMI_GUN, TOPLU_AZAMI_UZUN, TOPLU_EKSIK_BILGI,
                       TOPLU_GETIR, TOPLU_GETIR_ONAY, TOPLU_IPTAL, TOPLU_IZINLI, TOPLU_KAPSAM, TOPLU_KAYDET,
                       TOPLU_TAMAMLANDI, TOPLU_YASAK)

# Bu calismada TURMOB bilgisi girilmemis cikan firmalar: ikinci ekranda bastan secilmez
TURMOB_YOK = set()

BIRINCIL = {"alis": "e-arsiv-alis", "satis": "e-arsiv-satis"}


class TopluBasarisiz(RuntimeError):
    """Toplu Sorgulama bu firmada kullanilamadi; eski ekran-ekran yola donulur."""


# --- entegrasyon secimi (saf) -----------------------------------------------------------------

def entegrasyon_izinli(ad, turmob_var=False):
    """Entegrasyon Sec listesindeki bir satir isaretlenmeli mi?

    Isnet, QR ile Yuklenmis, NetteCAP, TreeWin, BelgeApp asla secilmez. TURMOB yalnizca
    kullanan firmada: kullanmayan firmada secilirse Luca "eksik bilgi" hatasi veriyor.
    Tanimadigimiz bir entegrasyon da secilmez (yalniz GIB/e-Arsiv/e-Fatura/5000/e-SMM bilinir).
    """
    s = sadelestir(ad)
    if not s or any(y in s for y in TOPLU_YASAK):
        return False
    if "TURMOB" in s:
        return bool(turmob_var)
    return any(k in s for k in TOPLU_IZINLI)


def entegrasyon_tipi(metin, yon):
    """Entegrasyon adi/kodundan belge tipi (e-arsiv-alis, turmob-satis ...); tanimazsa None."""
    s = sadelestir(metin).replace("_", " ")
    if not s:
        return None
    ek = "alis" if yon == "alis" else "satis"
    if "TURMOB" in s:
        return f"turmob-{ek}"
    if "SMM" in s:
        return f"esmm-{ek}"
    if "5000" in s or "30000" in s:
        return "gib-5000"
    if "ARSIV" in s:
        return f"e-arsiv-{ek}"
    if "FATURA" in s or "EFATURA" in s.replace(" ", ""):
        return f"e-fatura-{ek}"
    return None


# --- liste kayitlari (saf) ----------------------------------------------------------------------

def _anahtar(kayit, *adaylar):
    for ad in adaylar:
        for k, v in kayit.items():
            if sadelestir(str(k)).replace(" ", "").replace("_", "") == ad:
                return v
    return ""


ENTEGRASYON_ISARETI = re.compile(r"TURMOB|SMM|5000|ARSIV|\bE ?-?FATURA|EFATURA|ENTEGRASYON")


def _entegrasyon_bul(degerler, adayi=""):
    """Degerler arasinda bir entegrasyonu andiran ilk metin (adli alan bos/kodsa digerlerine bakilir)."""
    for d in [adayi] + [str(v) for v in degerler if isinstance(v, (str, int))]:
        d = str(d or "").strip()
        if d and ENTEGRASYON_ISARETI.search(sadelestir(d.replace("_", " "))):
            return d
    return str(adayi or "")


def kayit_coz(ham):
    """fatura_list.jq satiri (sozluk) ya da ekran satiri (hucre listesi) -> ortak sozluk.

    Dondurur: {"no", "entegrasyon", "tur", "onay", "unvan", "tarih"}; fatura numarasi
    bulunamazsa None.
    """
    if isinstance(ham, dict):
        no = str(_anahtar(ham, "BELGENUMARASI", "FATURANO", "FATURANUMARASI") or "").strip()
        adli = str(_anahtar(ham, "ENTEGRASYONTUR", "ENTEGRASYONNOKTASI", "ENTEGRASYON") or "")
        return {"no": no.upper(), "tip": None, "imza": (str(_anahtar(ham, "BELGETURU") or ""), adli),
                "entegrasyon": _entegrasyon_bul(
                    [v for k, v in ham.items() if sadelestir(str(k)) not in ("UNVAN", "URL", "ETTN")], adli),
                "tur": str(_anahtar(ham, "BELGETURU") or ""), "onay": str(_anahtar(ham, "ONAYDURUMU") or ""),
                "unvan": str(_anahtar(ham, "UNVAN", "UNVANADSOYAD") or ""),
                "tarih": str(_anahtar(ham, "BELGETARIHI") or "")} if no else None
    hucreler = [str(h or "").strip() for h in ham]
    no = ""
    for h in hucreler:
        e = FATURA_NO_DESENI.search(h.replace(" ", "").replace("-", ""))
        if e:
            no = e.group(1).upper()
            break
    if not no:
        return None
    ent = _entegrasyon_bul([h for h in hucreler if h.upper() != no])
    onay = next((h for h in hucreler if re.search(r"ONAY|IPTAL|ITIRAZ|RED|BEKLIYOR", sadelestir(h))), "")
    harfli = [h for h in hucreler if h.upper() != no and sum(c.isalpha() for c in h) >= 3
              and h not in (ent, onay)]
    return {"no": no, "tip": None, "imza": None, "entegrasyon": ent, "tur": "", "onay": onay,
            "unvan": max(harfli, key=len) if harfli else "", "tarih": ""}


def kayitlari_birlestir(hamlar):
    """Yakalanan ham satirlari (ayni fatura + ayni entegrasyon bir kez) cozer."""
    gorulen, sonuc = set(), []
    for ham in hamlar:
        k = kayit_coz(ham)
        if not k:
            continue
        anahtar = (k["no"], sadelestir(k["entegrasyon"]))
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        sonuc.append(k)
    return sonuc


# --- Excel (saf) --------------------------------------------------------------------------------

def _oran(metin):
    """'9/10' -> 0.9; '%90' -> 0.9; cozulemezse None."""
    s = str(metin or "").strip()
    e = re.search(r"(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)", s)
    if e:
        pay, payda = tutar_cozumle(e.group(1)), tutar_cozumle(e.group(2))
        return pay / payda if payda else None
    e = re.search(r"%\s*(\d+(?:[.,]\d+)?)", s)
    if e:
        return tutar_cozumle(e.group(1)) / 100.0
    return None


def toplu_excel_oku(yol, log=None, donem=None):
    """Toplu Sorgulama Excel'i (sayfa FATURALAR, 18 sutun) -> {"faturalar": {...}, "tekrar": n, ...}.

    Ayni fatura birden cok kez gelebiliyor (birebir ayni satir); tekrarlar atilir. Fatura basina:
    matrah, kdv, toplam, tur, oran, tevkifat_kdv.
    `donem` (bas, bit): fatura tarihi disinda kalan (sonraki aya sarkan sorgu) satirlar atilir.
    """
    basliklar, satirlar = excelden_tablo(yol, log)
    satirlar, _ = donem_satirlari(basliklar, satirlar, donem, log)
    sonuc = {"basliklar": basliklar, "satirlar": [], "faturalar": OrderedDict(), "tekrar": 0}
    if not satirlar:
        return sonuc
    i_no = sutun_indeksi(basliklar, "FATURA NUMARASI", "FATURA NO")
    i_tur = sutun_indeksi(basliklar, "FATURA TURU")
    i_oran = sutun_indeksi(basliklar, "TEVKIFAT ORANI")
    i_toplam = sutun_tam_indeksi(basliklar, "Toplam")
    i_tarih = sutun_indeksi(basliklar, "FATURA TARIHI")
    matrah_s, kdv_s = matrah_kdv_sutunlari(basliklar)
    if i_no is None:
        yaz("    UYARI: Toplu Excel'de 'Fatura Numarasi' sutunu bulunamadi", log)
        return sonuc
    gorulen = set()
    for s in satirlar:
        anahtar = tuple(s)
        if anahtar in gorulen:
            sonuc["tekrar"] += 1
            continue
        gorulen.add(anahtar)
        no = (s[i_no] if i_no < len(s) else "").strip().upper()
        if not no:
            continue
        sonuc["satirlar"].append(s)
        matrah = sum(tutar_cozumle(s[i]) for i in matrah_s if i < len(s))
        kdv = sum(tutar_cozumle(s[i]) for i in kdv_s if i < len(s))
        tur = sadelestir(s[i_tur]) if i_tur is not None and i_tur < len(s) else ""
        oran_metni = s[i_oran] if i_oran is not None and i_oran < len(s) else ""
        tevkifatli = "TEVKIFAT" in tur or sadelestir(oran_metni) not in BOS_DEGERLER
        oran = _oran(oran_metni) if tevkifatli else None
        f = sonuc["faturalar"].setdefault(no, {
            "no": no, "tarih": s[i_tarih] if i_tarih is not None and i_tarih < len(s) else "",
            "matrah": 0.0, "kdv": 0.0, "toplam": 0.0, "tevkifat": False, "tevkifat_kdv": 0.0,
            "tahmini": False, "ham": s})
        f["matrah"] += matrah
        f["kdv"] += kdv
        f["toplam"] += (tutar_cozumle(s[i_toplam]) if i_toplam is not None and i_toplam < len(s)
                        else matrah + kdv)
        if tevkifatli:
            f["tevkifat"] = True
            f["tevkifat_kdv"] += kdv * oran if oran is not None else kdv
            f["tahmini"] = f["tahmini"] or oran is None
    return sonuc


# --- sonuclar (saf) -----------------------------------------------------------------------------

def sonuclari_hesapla(firma, yon, tipler, kayitlar, excel, klasor_fn, dosyalar=(), log=None, donem=None):
    """Liste kayitlari + Excel -> {belge tipi: sonuc sozlugu} (yalniz `tipler` icin).

    kayitlar: kayitlari_birlestir() ciktisi (entegrasyon bilgisi). Bos ise (ya da hic eslesmezse)
    tum faturalar yonun birincil ekranina yazilir ve nota dusulur.
    klasor_fn(tip) -> o ekranin csv klasoru (Path).
    """
    faturalar = excel["faturalar"] if excel else {}
    if donem:   # liste kayitlari da yalniz hedef ayin faturalarini icersin (tarihi okunamayan korunur)
        kayitlar = [k for k in kayitlar if fatura_tarihi([], [k.get("tarih") or ""]) is None
                    or donem[0] <= fatura_tarihi([], [k.get("tarih") or ""]) <= donem[1]]
    tip_no = {t: OrderedDict() for t in tipler}   # tip -> {no: kayit}
    tanimsiz, dislanan = 0, set()
    for k in kayitlar:
        t = k.get("tip") or entegrasyon_tipi(k["entegrasyon"] or k["tur"], yon)
        if t is None:                     # entegrasyon anlasilamadi: birincil ekrana yazilir
            tanimsiz += 1
            t = BIRINCIL[yon] if BIRINCIL[yon] in tip_no else tipler[0]
        elif t not in tip_no:             # taninan ama bu calismada istenmeyen entegrasyon (listede eski veri durur)
            dislanan.add(k["no"])
            continue
        tip_no[t].setdefault(k["no"], k)
    bilinen = {n for d in tip_no.values() for n in d}
    eslesmeyen = [n for n in faturalar if n not in bilinen and n not in dislanan]
    if eslesmeyen:   # Excel'de olup listede gorunmeyen (sayfalama/liste okunamadi)
        t = BIRINCIL[yon] if BIRINCIL[yon] in tip_no else tipler[0]
        for n in eslesmeyen:
            tip_no[t].setdefault(n, {"no": n, "entegrasyon": "", "tur": "", "onay": "", "unvan": "",
                                     "tarih": faturalar[n]["tarih"]})
    sonuclar = {}
    for tip in tipler:
        s = yeni_sonuc(firma, tip)
        klasor = klasor_fn(tip)
        s["klasor"] = str(klasor)
        s["dosyalar"] = list(dosyalar)
        liste = tip_no[tip]
        if not liste:
            s["durum"] = "fatura yok"
            sonuclar[tip] = s
            continue
        s["durum"] = "tamam"
        s["fatura_sayisi"] = len(liste)
        iptal = [n for n, k in liste.items() if re.search(r"IPTAL|ITIRAZ", sadelestir(k["onay"]))]
        s["iptal_itiraz"] = len(iptal)
        sayilan = [n for n in liste if n not in iptal]
        satirlar_tum, tevk, iptal_satir = [], [], []
        for n, k in liste.items():
            f = faturalar.get(n)
            satir = f["ham"] if f else [n, k["tarih"], k["unvan"]]
            satirlar_tum.append(satir)
            if f and f["tevkifat"] and n not in iptal:
                tevk.append(f)
            if n in iptal:
                iptal_satir.append(satir)
        if faturalar:
            s["matrah"] = round(sum(faturalar[n]["matrah"] for n in sayilan if n in faturalar), 2)
            s["kdv"] = round(sum(faturalar[n]["kdv"] for n in sayilan if n in faturalar), 2)
        if tip in rapor.TEVKIFAT_EKRANLARI:
            s["tevkifat"] = len(tevk)
            s["tevkifat_kdv"] = round(sum(f["tevkifat_kdv"] for f in tevk), 2)
            s["tevkifat_kdv_tahmini"] = any(f["tahmini"] for f in tevk)
        s["faturalar"] = [[((k["unvan"] or "").split() or [""])[0].strip(".,"), n,
                           round(faturalar[n]["toplam"], 2) if n in faturalar else 0.0]
                          for n, k in liste.items()]
        basliklar = excel["basliklar"] if excel and excel.get("basliklar") else ["Fatura No", "Tarih", "Unvan"]
        try:
            klasor.mkdir(parents=True, exist_ok=True)
            csv_yaz(klasor / "liste.csv", [basliklar] + satirlar_tum)
            if tevk and s["tevkifat"]:
                csv_yaz(klasor / "tevkifatli.csv", [basliklar] + [f["ham"] for f in tevk])
            if iptal_satir:
                csv_yaz(klasor / "iptal-itiraz.csv", [basliklar] + iptal_satir)
        except OSError as e:
            yaz(f"    UYARI: csv yazilamadi ({e})", log)
        notlar = []
        if tanimsiz and len(tipler) > 1:   # birden fazla aday ekran varsa dagilim belirsiz
            notlar.append(f"{tanimsiz} fatura icin entegrasyon taninmadi")
        if eslesmeyen and kayitlar:
            notlar.append(f"{len(eslesmeyen)} fatura listeyle eslesmedi")
        if notlar and tip == BIRINCIL[yon]:
            s["not"] = "Toplu Sorgulama: " + ", ".join(notlar)
        sonuclar[tip] = s
    return sonuclar


# --- tarayici (Luca ekrani) ---------------------------------------------------------------------

# Entegrasyon Sec penceresindeki satirlar: adi "Entegrasyon" iceren yazi + yanindaki onay kutusu.
# jqx onay kutulari input degil div oluyor; hepsi taninir. Isaret: data-lucabot-ent
ENTEGRASYON_SATIRLARI_JS = """(kok) => {
  const gor = e => !!(e.offsetParent || e.getClientRects().length);
  const KUTU = 'input[type=checkbox], [role=checkbox], .jqx-checkbox';
  const durum = k => {
    if (k.tagName === 'INPUT') return !!k.checked;
    const a = k.getAttribute('aria-checked');
    if (a === 'true') return true; if (a === 'false') return false;
    if (k.querySelector('.jqx-checkbox-check-checked, .jqx-checkbox-checked')) return true;
    return /(^|\\s)(checked|jqx-checkbox-check-checked)(\\s|$)/.test(k.className || '');
  };
  kok = kok || document.body;
  kok.querySelectorAll('[data-lucabot-ent]').forEach(e => e.removeAttribute('data-lucabot-ent'));
  const hepsi = Array.from(kok.querySelectorAll(KUTU)).filter(gor);
  const kutular = hepsi.filter(k => !hepsi.some(d => d !== k && d.contains(k)));   // en dis onay kutusu
  const sonuc = [];
  for (const k of kutular) {
    let a = k.parentElement, ad = '';
    for (let i = 0; i < 6 && a && kok.contains(a); i++, a = a.parentElement) {
      if (Array.from(a.querySelectorAll(KUTU)).filter(gor).length > 1) break;   // baska satirin kutusu da var
      const t = (a.textContent || '').trim().replace(/\\s+/g, ' ');
      if (t) { ad = t; break; }
    }
    if (!ad || ad.length > 140) continue;
    const n = String(sonuc.length);
    k.setAttribute('data-lucabot-ent', n);
    sonuc.push({ad: ad, secili: durum(k), n: n});
  }
  return sonuc;
}"""

DURUM_JS = """(n) => { const k = document.querySelector('[data-lucabot-ent="' + n + '"]');
  if (!k) return null;
  if (k.tagName === 'INPUT') return !!k.checked;
  const a = k.getAttribute('aria-checked'); if (a === 'true') return true; if (a === 'false') return false;
  if (k.querySelector('.jqx-checkbox-check-checked, .jqx-checkbox-checked')) return true;
  return /(^|\\s)(checked|jqx-checkbox-check-checked)(\\s|$)/.test(k.className || ''); }"""


# Bir penceredeki belirli bir dugmeden (Kaydet / Getir) yukari cikarak pencerenin kendisini bulur:
# icinde en az `min` adet `secici` ogesi olan ilk ata. Luca (jqx) pencereleri ayni DOM'u yeniden
# gosterdigi icin "yeni beliren kutu" yontemi ikinci acilista yanlis kutulari buluyordu; ayrica
# arkadaki listenin satirlari (onay kutulari) entegrasyon satiri sanilmasin.
KAPSAYICI_JS = """(a) => {
  const [metinler, min, secici] = a;
  const gor = e => !!(e.offsetParent || e.getClientRects().length);
  const sade = t => (t || '').trim().replace(/\\s+/g, ' ').toLocaleLowerCase('tr');
  const hedef = metinler.map(sade);
  document.querySelectorAll('[data-lucabot-kap]').forEach(e => e.removeAttribute('data-lucabot-kap'));
  const dugmeler = Array.from(document.querySelectorAll(
    'button, a, input[type=button], input[type=submit], [role=button], .jqx-button, span, div'))
    .filter(e => gor(e) && hedef.includes(sade(e.tagName === 'INPUT' ? e.value : e.textContent)));
  for (const d of dugmeler.reverse()) {
    let ata = d.parentElement;
    for (let i = 0; i < 10 && ata; i++, ata = ata.parentElement) {
      if (Array.from(ata.querySelectorAll(secici)).filter(gor).length >= min) {
        ata.setAttribute('data-lucabot-kap', '1'); return true; }
    }
  }
  return false;
}"""

METIN_KUTUSU = "input:not([type=checkbox]):not([type=radio]):not([type=hidden]):not([type=button]):not([type=submit])"
ONAY_KUTUSU = "input[type=checkbox], [role=checkbox], .jqx-checkbox"


def _kapsayici(page, metinler, min_sayi, secici):
    """(cerceve, pencere konumlayicisi); bulunamazsa (None, None)."""
    for fr in cerceveler(page):
        try:
            if fr.evaluate(KAPSAYICI_JS, [list(metinler), min_sayi, secici]):
                return fr, fr.locator('[data-lucabot-kap="1"]').first
        except Exception:
            continue
    return None, None


def _entegrasyon_satirlari(page):
    """(cerceve, pencere, [{ad, secili, n}]); satir bulunamazsa bos liste."""
    fr, pencere = _kapsayici(page, ["Kaydet"], 2, ONAY_KUTUSU)
    if pencere is None:
        fr, pencere = acik_pencere(page)
    adaylar = [(fr, pencere)] if pencere is not None else []
    adaylar += [(f, None) for f in cerceveler(page)]
    for f, p in adaylar:
        try:
            satirlar = p.evaluate(ENTEGRASYON_SATIRLARI_JS) if p is not None else \
                f.evaluate(ENTEGRASYON_SATIRLARI_JS, None)
        except Exception:
            continue
        if satirlar:
            return f, p, satirlar
    return None, None, []


def entegrasyonlari_sec(page, turmob_var, log, yon=None, tipler=None):
    """Entegrasyon Sec penceresinde yalniz izinli olanlari isaretler, Kaydet'e basar.

    Dondurur: secilen entegrasyon adlari listesi. Pencere/satir bulunamazsa TopluBasarisiz.
    """
    _islem_bitsin(page, log)
    acik_pencereleri_kapat(page, log)
    if not _arac_dugmesine_bas(page, "Entegrasyon Seç", log):
        raise TopluBasarisiz("'Entegrasyon Seç' butonuna basilamadi")
    kosulu_bekle(page, lambda: bool(_entegrasyon_satirlari(page)[2]), 5000, aralik_ms=300)
    fr, pencere, satirlar = _entegrasyon_satirlari(page)
    if not satirlar:
        raise TopluBasarisiz("Entegrasyon Sec penceresinde satir/onay kutusu bulunamadi")
    gunluge_yaz("    TANI: entegrasyon satirlari: " + " | ".join(
        f"{'X' if s['secili'] else '-'} {s['ad'][:50]}" for s in satirlar), log)
    # arkadaki fatura listesinin satirlari (numara/tarih iceren) entegrasyon sayilmaz
    satirlar = [s for s in satirlar if not re.match(r"(TUMUNU|HEPSINI|TUMU\b)", sadelestir(s["ad"]))
                and not re.search(r"\d{9,}|\d{2}[./]\d{2}[./]\d{4}", s["ad"])]

    def istenen_mi(ad):   # izinli VE bu calismada istenen ekranlardan birine ait
        if not entegrasyon_izinli(ad, turmob_var):
            return False
        return not (tipler and yon) or entegrasyon_tipi(ad, yon) in tipler
    secilen = []
    for s in satirlar:
        istenen = istenen_mi(s["ad"])
        if istenen:
            secilen.append(s["ad"])
        if istenen != s["secili"]:
            try:
                fr.locator(f'[data-lucabot-ent="{s["n"]}"]').first.click(timeout=3000)
                sayfa_durulsun(page, azami_ms=300)
            except Exception as e:
                gunluge_yaz(f"    TANI: '{s['ad'][:40]}' isaretlenemedi ({type(e).__name__})", log)
    # dogrulama: istenmeyen bir entegrasyon secili kalmasin
    for s in satirlar:
        try:
            simdi = fr.evaluate(DURUM_JS, s["n"])
        except Exception:
            simdi = None
        if simdi is not None and bool(simdi) != istenen_mi(s["ad"]):
            yaz(f"    UYARI: '{s['ad'][:50]}' istenen durumda degil", log)
    if not secilen:
        raise TopluBasarisiz("secilebilecek entegrasyon bulunamadi")
    tik = pencerede_tikla(page, pencere, TOPLU_KAYDET, sure=4000) if pencere is not None else \
        varsa_tikla(page, TOPLU_KAYDET, sure=4000)
    if not tik:
        raise TopluBasarisiz("Entegrasyon Sec penceresinde Kaydet bulunamadi")
    kosulu_bekle(page, lambda: not _entegrasyon_satirlari(page)[2], 3000, aralik_ms=250)
    yaz(f"    Entegrasyonlar secildi ({len(secilen)}): " + ", ".join(a[:28] for a in secilen), log)
    return secilen


def _ekran_metni(page):
    """Gorunur cercevelerdeki yazilar (sadelestirilmis); sorgu sonucu bildirimi icin."""
    parca = []
    for fr in cerceveler(page):
        try:
            # gizli (eski sekme) cerceveleri atlanir: gizliyken innerText sayfa kodunu da dondurur
            parca.append(fr.evaluate("() => { const f = window.frameElement;"
                                     " if (f && !(f.offsetParent || f.getClientRects().length)) return '';"
                                     " return document.body ? document.body.innerText : ''; }"))
        except Exception:
            continue
    return sadelestir(" ".join(parca))


# Kisa suren bildirimleri (toast) kacirmamak icin: sayfaya eklenen metin dugumlerini toplar
GOZLEMCI_JS = """() => {
  window.__lbMsg = [];
  if (window.__lbObs) return;
  window.__lbObs = new MutationObserver(ms => {
    for (const m of ms) {
      const dugumler = Array.from(m.addedNodes || []);
      if (m.type === 'characterData' && m.target) dugumler.push(m.target);
      for (const d of dugumler) {
        const e = d.nodeType === 1 ? d : d.parentElement;
        if (!e || /^(SCRIPT|STYLE|NOSCRIPT)$/.test(e.tagName) || e.closest('script,style')) continue;   // sayfa kodu degil, gorunen yazi
        const t = ((d.nodeType === 1 ? d.innerText : d.textContent) || '').trim();
        if (t && t.length < 600 && /sorgulanmas\\S*\\s+tamamland|eksik bilgi|en fazla 1/i.test(t)) window.__lbMsg.push(t);
      }
    }
  });
  window.__lbObs.observe(document.documentElement, {childList: true, subtree: true, characterData: true});
}"""


def _gozlemci_kur(page):
    for fr in cerceveler(page):
        try:
            fr.evaluate(GOZLEMCI_JS)
        except Exception:
            continue


def _gozlenen(page):
    parca = []
    for fr in cerceveler(page):
        try:
            parca += fr.evaluate("() => window.__lbMsg || []")
        except Exception:
            continue
    return sadelestir(" ".join(parca))


BITIS_BEKLEME = 8   # Islem Takip bitti/kapandi: kesin bildirim icin beklenecek sure
def _gunluk_durulsun(page, log, sakin_saniye=2.5, azami_saniye=90):
    """Islem Takip penceresi acikken yazisi sakin_saniye boyunca degismeyene (ya da "sona erdi"ye) kadar bekler."""
    basla = son_degisim = time.time()
    onceki = None
    bildirildi = False
    while time.time() - basla < azami_saniye:
        g = islem_gunlugu(page)
        if not g or sorgu_bitti_mi(g):
            return
        if g != onceki:
            onceki, son_degisim = g, time.time()
            if time.time() - basla > sakin_saniye and not bildirildi:
                yaz("    Islem Takip hala akiyor, bekleniyor...", log)
                bildirildi = True
        elif time.time() - son_degisim >= sakin_saniye:
            return
        sayfa_durulsun(page, azami_ms=500)


IPTAL_AZAMI_SANIYE = 600   # iptal/itiraz sorgusu ikincildir; bir parca icin en cok bu kadar beklenir
IDLE_SANIYE = 30   # hicbir pencere/yazi degismeden bu kadar sure gecerse sorgu bitmis sayilir (5000/30000 bildirim gostermiyor)


# Getir penceresinde HER ZAMAN duran aciklama; gercek hata iletisinden ayirt edilmeli
SABIT_IPUCU = "SECILI ENTEGRASYONLAR SIRAYLA SORGULANIR. EN FAZLA 1 AYLIK SORGULAMA YAPILABILIR."


def ipucusuz(metin):
    """Ekran yazisindan Getir penceresinin sabit '...en fazla 1 aylik...' aciklamasini cikarir."""
    return metin.replace(SABIT_IPUCU, " ")


def _sonucu_bekle(page, log, azami_saniye, once=""):
    """Toplu sorgunun bittigini bekler.

    Kesin bitis: "Secili entegrasyonlarin sorgulanmasi tamamlandi" bildirimi. Bildirim gelmeyen sorgularda
    (5000/30000) Islem Takip penceresi kapandi ya da "sona erdi" yazdiysa BITIS_BEKLEME sn sonra; hicbir
    pencere/yazi yoksa ekran IDLE_SANIYE boyunca degismediyse devam edilir. Gunluk satirlari
    ("fatura bulunamadi" vb.) sorgu surerken de yazildigi icin tek basina bitis sayilmaz.
    `once`: sorgu baslamadan onceki ekran yazisi (eski bildirimler bitis sayilmasin).

    Dondurur: 'tamam' | 'tamam_turmob_eksik' | 'turmob_eksik' | 'aralik' | 'zaman_asimi'.
    """
    basla = time.time()
    son_log = 0
    son_degisim = time.time()
    son_metin = None
    gunluk_goruldu = False
    gunluk_yok = 0
    aday = None
    gunluk_onceki, gunluk_degisim = None, time.time()
    once = ipucusuz(once)
    while time.time() - basla < azami_saniye:
        m = ipucusuz(_ekran_metni(page) + " " + _gozlenen(page))
        if m != son_metin:
            son_metin, son_degisim = m, time.time()
        artti = lambda anahtar: m.count(anahtar) > once.count(anahtar)   # yalniz bu sorguyla gelen yazi
        eksik = artti(TOPLU_EKSIK_BILGI)
        if artti(TOPLU_AZAMI_UZUN):
            gunluge_yaz("    TANI: 1 aylik sinir iletisi: " + m[max(0, m.find(TOPLU_AZAMI_UZUN) - 80):][:200], log)
            return "aralik"
        yeni_tamam = artti(TOPLU_TAMAMLANDI)   # kesin bildirim: "...sorgulanmasi tamamlandi"
        if eksik and "TURMOB" in m:
            return "tamam_turmob_eksik" if yeni_tamam else "turmob_eksik"
        if yeni_tamam:
            i = m.find(TOPLU_TAMAMLANDI)
            gunluge_yaz("    TANI: sonuc iletisi: " + m[max(0, i - 70):][:220], log)
            _gunluk_durulsun(page, log)   # bildirimle birlikte Islem Takip hala akiyorsa bitmesi beklenir
            return "tamam"
        # NOT: gunluktaki "fatura bulunamadi"/"tamamlandi" gibi satirlar sorgu SURERKEN de yazilir;
        # bitis sayilmaz. Islem Takip kapandiysa/"sona erdi" yazdiysa yalnizca ADAY sayilir ve
        # kesin bildirim icin BITIS_BEKLEME sn beklenir (pencere yeniden acilirsa aday iptal olur).
        gunluk = islem_gunlugu(page)
        simdi = time.time()
        if gunluk != gunluk_onceki:
            gunluk_onceki, gunluk_degisim = gunluk, simdi
        elif gunluk and simdi - gunluk_degisim >= AYAR["durgunluk_saniye"]:
            yaz(f"    UYARI: Islem Takip {int(AYAR['durgunluk_saniye'])} sn ilerlemedi; sorgu takildi sayiliyor", log)
            return "takildi"
        if gunluk:
            gunluk_goruldu, gunluk_yok = True, 0
            if sorgu_bitti_mi(gunluk):
                aday = aday or simdi
            else:
                aday = None
        elif gunluk_goruldu:
            gunluk_yok += 1
            if gunluk_yok >= 2:
                aday = aday or simdi
        if aday and simdi - aday >= BITIS_BEKLEME:
            yaz("    Islem Takip bitti, kesin bildirim gelmedi; sorgu tamamlandi sayiliyor", log)
            return "tamam"
        if not gunluk and simdi - son_degisim >= IDLE_SANIYE and simdi - basla >= IDLE_SANIYE:
            yaz(f"    UYARI: {IDLE_SANIYE} sn boyunca ekranda degisiklik/bildirim yok; sorgu bitmis sayilip devam ediliyor", log)
            gunluge_yaz("    TANI: ekran yazisi (son 200): " + m[-200:], log)
            return "tamam"
        if time.time() - son_log >= 15:
            son_log = time.time()
            yaz(f"    ... toplu sorgu bekleniyor ({int(time.time() - basla)} sn)", log)
            gunluge_yaz("    TANI: " + (f"islem takip: {' '.join(gunluk.split())[-120:]}" if gunluk
                                       else f"ekran yazisi sonu: {m[-120:]}"), log)
        sayfa_durulsun(page, azami_ms=800)
    return "zaman_asimi"


def _modal_temizle(page, log=None):
    """Arkadaki dugmeleri engelleyen acik pencere/bildirimi ("fatura bulunamadi", sonuc iletisi...) kapatir."""
    fatura_yok_penceresini_kapat(page, bekle=False)
    varsa_tikla(page, ["Tamam", "Kapat"], sure=800)
    acik_pencereleri_kapat(page, log)
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    sayfa_durulsun(page, azami_ms=700)


def _arac_dugmesine_bas(page, ad, log, deneme=4):
    """Arac cubugu dugmesine basar; tiklama engellenirse (acik pencere/bildirim) temizleyip tekrar dener."""
    for i in range(1, deneme + 1):
        if dugmeye_bas(page, ad, sure=4000 if i == 1 else 3000):
            return True
        yaz(f"    '{ad}' tiklanamadi ({i}/{deneme}); acik pencere/bildirim temizleniyor", log)
        _modal_temizle(page, log)
        geri_cekil(page, 1.5)
    return False


def _bildirimi_kapat(page):
    varsa_tikla(page, ["Tamam", "Kapat"], sure=1500)
    kosulu_bekle(page, lambda: TOPLU_TAMAMLANDI not in _ekran_metni(page)
                 and TOPLU_EKSIK_BILGI not in _ekran_metni(page), 2500, aralik_ms=250)
    acik_pencereleri_kapat(page)


def _pencere_bekle(page, capalar, azami_ms=4000):
    """Acilan Luca penceresini bekler. Once .luca-open-window'a bakilir: listenin sutun basliklari
    ("Belge Numarasi", "Belge Tarihi") pencere yazilariyla karisip yanlis kapsayici donduruyordu."""
    kosulu_bekle(page, lambda: acik_pencere(page)[1] is not None, azami_ms, aralik_ms=200)
    _, pencere = acik_pencere(page)
    if pencere is None:
        _, pencere = diyalog_bekle(page, capalar, azami_ms=1500)
    return pencere


def _islem_bitsin(page, log, azami_saniye=180, durgun_saniye=60):
    """Onceki sorgunun Islem Takip penceresi hala calisiyorsa bitmesini bekler (en cok azami_saniye;
    yazisi durgun_saniye boyunca degismezse takilmis sayilir ve pencere kapatilir).

    acik_pencereleri_kapat suren bir sorguyu oldurebilir; bir sonraki adima gecmeden once Luca is bitirmeli.
    """
    basla = son_degisim = time.time()
    onceki, bildirildi = None, False
    while time.time() - basla < azami_saniye:
        gunluk = islem_gunlugu(page)
        if not gunluk or sorgu_bitti_mi(gunluk):
            return
        if gunluk != onceki:
            onceki, son_degisim = gunluk, time.time()
        elif time.time() - son_degisim >= durgun_saniye:
            break
        if not bildirildi:
            yaz("    Onceki sorgu hala suruyor, bitmesi bekleniyor...", log)
            bildirildi = True
        sayfa_durulsun(page, azami_ms=1000)
    yaz("    UYARI: onceki sorgu bitmedi/takildi; pencere kapatilip devam ediliyor", log)


def toplu_getir(page, bas, bit, log, iptal=False):
    """Secili entegrasyonlardan tek bir (en fazla 1 aylik) aralik icin getirir ya da (iptal=True)
    iptal/itiraz sorgular; _sonucu_bekle durumunu dondurur."""
    ad = "Seçili Entegrasyonlardan İptal/İtiraz Sorgula" if iptal else "Seçili Entegrasyonlardan Getir"
    dugme = TOPLU_IPTAL if iptal else TOPLU_GETIR
    onaylar = [TOPLU_IPTAL] if iptal else ["Getir", "Belgeleri Getir", "Sorgula"]
    yaz(f"    {ad} ({bas} - {bit})", log)
    _islem_bitsin(page, log)
    acik_pencereleri_kapat(page, log)
    if not _arac_dugmesine_bas(page, dugme, log):
        raise TopluBasarisiz(f"'{dugme}' butonuna basilamadi")
    pencere = None
    kosulu_bekle(page, lambda: _kapsayici(page, onaylar, 2, METIN_KUTUSU)[1] is not None, 5000, aralik_ms=250)
    fr, pencere = _kapsayici(page, onaylar, 2, METIN_KUTUSU)
    if pencere is None:   # eski yontem: yeni beliren tarih kutulari
        eski_kutulari_isaretle(page)
        pencere = _pencere_bekle(page, ["Başlangıç", "Bitiş", "Tarih Aralığı"])
        kutular = tarih_kutulari(page, pencere)
    else:
        kutular = pencere.locator(METIN_KUTUSU)
        kutular = [kutular.nth(i) for i in range(min(kutular.count(), 2))]
        try:
            gunluge_yaz("    TANI: getir penceresi: " + " ".join(pencere.inner_text(timeout=2000).split())[:160], log)
        except Exception:
            pass
    if len(kutular) < 2:
        raise TopluBasarisiz("Toplu getir tarih kutulari bulunamadi")
    for deneme in (1, 2):
        yazilan = tarih_araligi_yaz(kutular, bas, bit)
        if yazilan.replace(" ", "") == f"{bas}-{bit}":
            break
        yaz(f"    UYARI: tarih kutularinda '{yazilan}' gorunuyor, tekrar yaziliyor", log)
    else:
        raise TopluBasarisiz(f"tarih kutulari istenen araligi tutmadi ({yazilan})")
    yaz(f"    Tarih araligi girildi: {yazilan}", log)
    once = _ekran_metni(page)   # eski bildirimler bu sorgunun bitisi sayilmasin
    _gozlemci_kur(page)
    tik = pencerede_tikla(page, pencere, onaylar, sure=5000) if pencere is not None else None
    tik = tik or varsa_tikla(page, onaylar if iptal else TOPLU_GETIR_ONAY, sure=5000)
    if not tik:
        raise TopluBasarisiz("Toplu getir onay butonu bulunamadi")
    yaz(f"    '{tik}' tiklandi, sorgu basladi", log)
    durum = _sonucu_bekle(page, log, min(AYAR["azami_saniye"], IPTAL_AZAMI_SANIYE) if iptal else AYAR["azami_saniye"], once)
    if durum == "tamam":
        yaz("    Seçili entegrasyonların sorgulanması tamamlandı", log)
    _bildirimi_kapat(page)
    return durum


def toplu_iptal_sorgula(page, parcalar, log):
    """Seçili Entegrasyonlardan İptal/İtiraz Sorgula (en fazla 1 aylik parcalarla). Hata sorgulamayi
    keser ama firmanin fatura bilgisini bozmaz; basarili parca sayisini dondurur."""
    basarili = 0
    for bas, bit in parcalar:
        try:
            durum = toplu_getir(page, bas, bit, log, iptal=True)
        except TopluBasarisiz as e:
            yaz(f"    UYARI: iptal/itiraz sorgulanamadi ({e})", log)
            acik_pencereleri_kapat(page, log)
            break
        if durum not in ("tamam", "tamam_turmob_eksik"):
            yaz(f"    UYARI: iptal/itiraz sorgusu sonucu: {durum}; kalan parcalar atlandi", log)
            break
        basarili += 1
    return basarili


class _ListeYakalayici:
    """fatura_list.jq yanitlarini toplar (entegrasyon/onay bilgisi icin)."""

    def __init__(self, page):
        self.page = page
        self.hamlar = []

    def _yanit(self, r):
        try:
            if "fatura_list" not in r.url:
                return
            veri = r.json()
        except Exception:
            return
        satirlar = veri if isinstance(veri, list) else next(
            (v for v in (veri.get("rows"), veri.get("data"), veri.get("liste"), veri.get("Rows"))
             if isinstance(v, list)), []) if isinstance(veri, dict) else []
        self.hamlar.extend(x for x in satirlar if isinstance(x, (dict, list)))

    def __enter__(self):
        self.page.on("response", self._yanit)
        return self

    def __exit__(self, *a):
        try:
            self.page.remove_listener("response", self._yanit)
        except Exception:
            pass


def _imza_ogren(page, kayitlar, yon, log):
    """Agdan gelen kayitlarin entegrasyonu anlasilamiyorsa (kod/bos) ekrandaki satirlardan ogrenir.

    Ekran satirlari entegrasyonu acik adiyla gosterir. Ayni fatura numarasi hem agda hem ekranda varsa
    kaydin imzasi (belge turu + entegrasyon kodu) o tipe baglanir; ayni imzali tum kayitlara uygulanir.
    """
    belirsiz = [k for k in kayitlar if not k.get("tip")
                and entegrasyon_tipi(k["entegrasyon"] or k["tur"], yon) is None]
    if not belirsiz:
        return
    try:
        satirlar, _ = ekrandaki_satirlar(page)
    except Exception:
        return
    ekran = {}   # no -> {tipler}
    for e in kayitlari_birlestir(satirlar):
        t = entegrasyon_tipi(e["entegrasyon"], yon)
        if t:
            ekran.setdefault(e["no"], set()).add(t)
    imzalar = {}   # imza -> {tipler}
    for k in belirsiz:
        adaylar = ekran.get(k["no"], set())
        if len(adaylar) == 1 and k.get("imza") is not None:
            imzalar.setdefault(k["imza"], set()).update(adaylar)
    cozulen = {im: next(iter(ts)) for im, ts in imzalar.items() if len(ts) == 1}
    for k in belirsiz:
        if k.get("imza") in cozulen:
            k["tip"] = cozulen[k["imza"]]
    kalan = sum(1 for k in belirsiz if not k.get("tip"))
    gunluge_yaz(f"    TANI: imza ogrenildi: {len(cozulen)} imza ({len(belirsiz) - kalan}/{len(belirsiz)} kayit cozuldu)", log)


def _liste_oku(page, yakalayici, log, yon="alis"):
    """Yakalanan yanitlardan, yoksa ekrandan satirlari dondurur (kayit sozlukleri)."""
    kayitlar = kayitlari_birlestir(yakalayici.hamlar)
    if kayitlar:
        _imza_ogren(page, kayitlar, yon, log)
        _liste_tanisi(kayitlar, yakalayici.hamlar, "ag yaniti", log, yon)
        return kayitlar
    satirlar, _ = ekrandaki_satirlar(page)
    kayitlar = kayitlari_birlestir(satirlar)
    if kayitlar:
        _liste_tanisi(kayitlar, satirlar, "ekran", log, yon)
    return kayitlar


def _liste_tanisi(kayitlar, hamlar, kaynak, log, yon="alis"):
    """Gunluge: hangi entegrasyon metinleri kac kayitta (kisi/fatura bilgisi yazilmaz).

    Tanimlanamayan kayit kalirsa ekrana da kisa bir ozet yazilir (neyin taninmadigi anlasilsin)."""
    sayac, bilinmeyen = {}, {}
    for k in kayitlar:
        ad = k["entegrasyon"][:50] or "(bos)"
        sayac[ad] = sayac.get(ad, 0) + 1
        if not k.get("tip") and entegrasyon_tipi(k["entegrasyon"] or k["tur"], yon) is None:
            im = f"{k.get('imza') or ad}"[:70]
            bilinmeyen[im] = bilinmeyen.get(im, 0) + 1
    ilk = hamlar[0] if hamlar else None
    gunluge_yaz(f"    TANI: liste kaynagi={kaynak}; entegrasyonlar={sayac}"
                + (f"; alanlar={sorted(ilk)[:14]}" if isinstance(ilk, dict) else ""), log)
    if bilinmeyen:
        yaz(f"    UYARI: entegrasyonu anlasilamayan kayitlar (birincil ekrana yazilir): {dict(list(bilinmeyen.items())[:4])}", log)


# Listede yalniz GIB e-Arsiv satirlarini isaretler (digerlerinin isaretini kaldirir). Dondurur:
# isaretlenen satir sayisi. Satir = kutusu olan tr / [role=row] / jqx satiri; baslik satiri atlanir.
ARSIV_SEC_JS = """(arg) => {
  const mod = arg.mod;
  // donem (yyyymmdd): satirdaki ilk GG/AA/YYYY (Belge Tarihi) bunun disindaysa isaretlenmez; tarihi okunamayan isaretlenir
  const gun = t => { const m = /(\\d{2})\\/(\\d{2})\\/(\\d{4})/.exec(t || ''); return m ? +(m[3] + m[2] + m[1]) : null; };
  const gor = e => !!(e.offsetParent || e.getClientRects().length);
  const KUTU = 'input[type=checkbox], [role=checkbox], .jqx-checkbox';
  const sade = t => (t || '').replace(/İ/g, 'I').replace(/ı/g, 'i').normalize('NFD')
    .replace(/[\\u0300-\\u036f]/g, '').toUpperCase();
  const durum = k => {
    if (k.tagName === 'INPUT') return !!k.checked;
    const a = k.getAttribute('aria-checked'); if (a === 'true') return true; if (a === 'false') return false;
    return !!k.querySelector('.jqx-checkbox-check-checked, .jqx-checkbox-checked');
  };
  let secili = 0;
  const satirlar = Array.from(document.querySelectorAll('tr, [role=row], .jqx-grid-row, .jqx-grid-cell-row'))
    .filter(r => gor(r) && !r.closest('thead') && !r.querySelector('th, [role=columnheader]'));
  for (const r of satirlar) {
    const kutular = Array.from(r.querySelectorAll(KUTU)).filter(gor);
    if (kutular.length !== 1 || satirlar.some(d => d !== r && r.contains(d) && d.querySelector(KUTU))) continue;
    const metin = sade(r.textContent);
    const tur = mod === 'satis' ? metin.includes('5000')
      : metin.includes('ARSIV') && !metin.includes('5000') && !metin.includes('TURMOB') && !/E-?FATURA/.test(metin);
    const g = gun(r.textContent);
    const donemde = !arg.bas || g === null || (g >= arg.bas && g <= arg.bit);
    const ist = tur && donemde;
    if (ist !== durum(kutular[0])) kutular[0].click();
    if (ist) secili++;
  }
  return secili;
}"""


def arsiv_satirlarini_sec(page, log, yon="alis", donem=None):
    """Listede XML indirilecek satirlari isaretler, digerlerinin isaretini kaldirir; sayiyi dondurur.

    Alis: yalniz GIB e-Arsiv Entegrasyonu Alis Faturalari. Satis: yalniz GIB e-Arsiv Entegrasyon (5000/30000).
    donem (bas, bit) verilirse yalniz Belge Tarihi bu aralikta olanlar (sorgu sonraki aya uzatilsa da yalniz hedef ay).
    """
    sayi = 0
    arg = {"mod": yon, "bas": int(f"{donem[0]:%Y%m%d}") if donem else 0, "bit": int(f"{donem[1]:%Y%m%d}") if donem else 0}
    for fr in cerceveler(page):
        try:
            sayi += int(fr.evaluate(ARSIV_SEC_JS, arg) or 0)
        except Exception:
            continue
    sayfa_durulsun(page, azami_ms=500)
    yaz(f"    XML icin isaretlenen satir ({'GİB 5000/30000' if yon == 'satis' else 'GİB e-Arşiv alış'}"
        f"{f', yalniz {donem[0]:%d/%m/%Y}-{donem[1]:%d/%m/%Y}' if donem else ''}): {sayi}", log)
    return sayi


def _firma_ve_donem(page, firma, bas, bit, log, firma_secili):
    acik_pencereleri_kapat(page, log)
    if not firma_secili:
        yaz("    Firma seciliyor", log)
        try:
            firma_sec(page, firma, log)
        except LookupError as e:
            raise TopluBasarisiz(f"firma secilemedi: {e}") from e
    if not donem_ayarla(page, firma, bas, bit, log):
        raise TopluBasarisiz("donem ayarlanamadi")
    return True


def _parcalar(araliklar):
    """Sorgu araliklari: istenen tum araligi en fazla 1 aylik parcalara boler."""
    bas, bit = tarih_cozumle(araliklar[0][0]), tarih_cozumle(araliklar[-1][1])
    return tarih_araliklari(bas, bit, TOPLU_AZAMI_GUN)


def toplu_isle(page, firma, yon, tipler, araliklar, cikti_kok, log, turmob_var=True,
               firma_secili=False):
    """Bir firmanin Alis ya da Satis toplu ekranini isler.

    Dondurur: (sonuclar {tip: sonuc}, firma_secili). Kullanilamazsa TopluBasarisiz firlatir;
    cagiran eski ekran-ekran yola doner. Tarayici olurse ilgili hata oldugu gibi yukari gider.
    """
    tipler = [t for t in tipler if t in TOPLU_KAPSAM[yon]]
    if not tipler:
        return {}, firma_secili
    parcalar = _parcalar(araliklar)
    istenen_bas, istenen_bit = tarih_cozumle(parcalar[0][0]), tarih_cozumle(parcalar[-1][1])
    hedef_donem = hedef_ay_araligi(istenen_bas, istenen_bit)   # sorgu 17/11'e uzasa da rapor yalniz hedef ayi (10. ay) icerir
    firma_secili = _firma_ve_donem(page, firma, istenen_bas, istenen_bit, log, firma_secili)
    yaz(f"    Toplu Sorgulama ({'Alış' if yon == 'alis' else 'Satış'}) açılıyor", log)
    if not toplu_menuye_git(page, yon):
        raise TopluBasarisiz("Toplu Sorgulama ekrani acilamadi (menu degismis ya da modul yok)")
    fatura_yok_penceresini_kapat(page)

    sorgu_notlari = []
    turmob = turmob_var and firma not in TURMOB_YOK
    entegrasyonlari_sec(page, turmob, log, yon, tipler)
    for bas, bit in parcalar:
        durum = toplu_getir(page, bas, bit, log)
        if durum == "aralik":   # Luca araligi 1 aydan uzun saydi: ikiye bolup tekrar dene
            yari = tarih_cozumle(bas) + (tarih_cozumle(bit) - tarih_cozumle(bas)) // 2
            yaz("    Luca araligi cok uzun saydi; ikiye bolunuyor", log)
            for b2, e2 in ((bas, yari.strftime(TARIH_BICIMI)), (yari.strftime(TARIH_BICIMI), bit)):
                durum = toplu_getir(page, b2, e2, log)
                if durum not in ("tamam", "tamam_turmob_eksik"):
                    break
        if durum in ("turmob_eksik", "tamam_turmob_eksik") and turmob:
            yaz("    TÜRMOB bilgisi girilmemis; TÜRMOB secilmeden devam ediliyor", log)
            TURMOB_YOK.add(firma)
            turmob = False
            entegrasyonlari_sec(page, False, log, yon, tipler)
            if durum == "turmob_eksik":
                durum = toplu_getir(page, bas, bit, log)
        if durum == "aralik":
            raise TopluBasarisiz("Luca 'en fazla 1 aylik sorgu' dedi; aralik kisaltilmali")
        if durum == "zaman_asimi":
            raise TopluBasarisiz(f"toplu sorgu {AYAR['azami_saniye']} sn icinde bitmedi")
        if durum == "takildi":   # Luca ilerlemedi: eldeki veriyle devam, rapora not dusulur
            sorgu_notlari.append("sorgu takildi, veriler eksik olabilir")
            durum = "tamam"
        if durum not in ("tamam", "tamam_turmob_eksik"):
            raise TopluBasarisiz(f"toplu sorgu sonucu: {durum}")

    iptal_notu = ""
    if AYAR["iptal_itiraz"]:   # Excel/liste guncel iptal-itiraz durumunu tasisin diye Excel'den once
        if not toplu_iptal_sorgula(page, parcalar, log):
            iptal_notu = "iptal/itiraz sorgulanamadi"
    _islem_bitsin(page, log)
    _modal_temizle(page, log)

    klasor = cikti_kok / dosya_adi_yap(firma) / f"toplu-{yon}"
    klasor.mkdir(parents=True, exist_ok=True)
    with _ListeYakalayici(page) as yakalayici:
        for deneme in (1, 2, 3):
            if belge_ara(page, istenen_bas.strftime(TARIH_BICIMI), istenen_bit.strftime(TARIH_BICIMI), log,
                         acik_pencere_once=True):
                break
            _modal_temizle(page, log)   # Belge Ara dugmesi/penceresi acik bir pencere yuzunden tutmadi
        else:
            raise TopluBasarisiz("Belge Ara yapilamadi (liste yenilenemedi)")
        sayfa_durulsun(page, azami_ms=2000)
        kayitlar = _liste_oku(page, yakalayici, log, yon)
    yaz(f"    Listede {len(kayitlar)} kayit" if kayitlar else "    Listede fatura yok", log)

    dosyalar = []
    excel = None
    if AYAR["excel_indir"] and kayitlar:
        # Luca "Lutfen excel cikti icin faturalari seciniz" diyor: once hepsi isaretlenir
        hepsini_sec(page, None, len(kayitlar))
        yol = dosya_indir(page, "Excel", klasor, "toplu", log,
                          azami_saniye=max(AYAR["indirme_saniye"], 60) + int(len(kayitlar) * 0.3),
                          pencere_acilir=False)
        if yol:
            dosyalar.append(yol.name)
            excel = toplu_excel_oku(yol, log, hedef_donem)
            if excel["tekrar"]:
                yaz(f"    Excel'de {excel['tekrar']} tekrarlanan satir atildi", log)
            yaz(f"    Excel'den {len(excel['faturalar'])} fatura okundu", log)
        else:
            yaz("    UYARI: Excel inmedi; tutarlar bos kalacak", log)
    azami = AYAR.get("azami_fatura") or 0
    # XML/zip: alista yalniz GIB e-Arsiv alis, satista yalniz GIB 5000/30000 (e-Fatura/TURMOB/e-Arsiv satis inmez).
    # Satirlar ekrandaki yazilara gore isaretlenir; agdan gelen kayitlarin entegrasyonu taninmasa da calisir.
    xml_tipi = "e-arsiv-alis" if yon == "alis" else "gib-5000"
    if AYAR["belge_indir"] and xml_tipi in tipler and kayitlar:
        secilen = arsiv_satirlarini_sec(page, log, yon, hedef_donem)
        azami = AYAR.get("azami_fatura") or 0
        if not secilen:
            yaz("    XML icin uygun satir yok / isaretlenemedi; paket indirilmedi", log)
        elif azami and secilen > azami:
            yaz(f"    XML paketi atlandi: {secilen} fatura (sinir {azami})", log)
        else:
            yol = dosya_indir(page, "Seçilenleri İndir", klasor, "belgeler", log,
                              azami_saniye=AYAR["indirme_saniye"], tumunu_sec=False)
            if yol:
                dosyalar.append(yol.name)
            else:
                yaz("    UYARI: belge paketi (zip) inmedi", log)
    if not sayfa_canli(page):
        raise TopluBasarisiz("tarayici kapandi")

    sonuclar = sonuclari_hesapla(firma, yon, tipler, kayitlar, excel,
                                 lambda t: cikti_kok / dosya_adi_yap(firma) / t, dosyalar, log, hedef_donem)
    for ek in ([iptal_notu] if iptal_notu else []) + sorgu_notlari:
        for s in sonuclar.values():
            s["not"] = (s["not"] + "; " if s["not"] else "") + "Toplu Sorgulama: " + ek
    if AYAR["excel_indir"] and excel is None and kayitlar:
        for s in sonuclar.values():
            if s["durum"] == "tamam":
                s["durum"] = "excel inmedi"
    return sonuclar, firma_secili
