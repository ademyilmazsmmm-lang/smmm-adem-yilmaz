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

from .bekleme import kosulu_bekle, sayfa_canli, sayfa_durulsun
from .fatura_analiz import (BOS_DEGERLER, csv_yaz, excelden_tablo, matrah_kdv_sutunlari,
                            sutun_indeksi, sutun_tam_indeksi, tutar_cozumle)
from .gib_sorgu import belge_ara
from .indirme import dosya_indir
from .liste_secim import ekrandaki_satirlar, hepsini_sec
from .luca_ekran import (acik_pencere, acik_pencereleri_kapat, cerceveler, dugmeye_bas,
                         fatura_yok_penceresini_kapat, pencerede_tikla,
                         tarih_araligi_yaz, tarih_kutulari, varsa_tikla, eski_kutulari_isaretle,
                         diyalog_bekle)
from .luca_gezinme import donem_ayarla, firma_sec, toplu_menuye_git
from .ortak import (AYAR, TARIH_BICIMI, dosya_adi_yap, gunluge_yaz, sadelestir, tarih_araliklari,
                    tarih_cozumle, yaz, yeni_sonuc)
from . import rapor
from .sabitler import (FATURA_NO_DESENI, TOPLU_AZAMI_GUN, TOPLU_AZAMI_UZUN, TOPLU_EKSIK_BILGI,
                       TOPLU_GETIR, TOPLU_GETIR_ONAY, TOPLU_IZINLI, TOPLU_KAPSAM, TOPLU_KAYDET,
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


def kayit_coz(ham):
    """fatura_list.jq satiri (sozluk) ya da ekran satiri (hucre listesi) -> ortak sozluk.

    Dondurur: {"no", "entegrasyon", "tur", "onay", "unvan", "tarih"}; fatura numarasi
    bulunamazsa None.
    """
    if isinstance(ham, dict):
        no = str(_anahtar(ham, "BELGENUMARASI", "FATURANO", "FATURANUMARASI") or "").strip()
        return {"no": no.upper(), "entegrasyon": str(_anahtar(ham, "ENTEGRASYONTUR", "ENTEGRASYONNOKTASI",
                                                              "ENTEGRASYON") or ""),
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
    ent = next((h for h in hucreler if "ENTEGRASYON" in sadelestir(h)), "")
    onay = next((h for h in hucreler if re.search(r"ONAY|IPTAL|ITIRAZ|RED|BEKLIYOR", sadelestir(h))), "")
    harfli = [h for h in hucreler if h.upper() != no and sum(c.isalpha() for c in h) >= 3
              and h not in (ent, onay)]
    return {"no": no, "entegrasyon": ent, "tur": "", "onay": onay,
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


def toplu_excel_oku(yol, log=None):
    """Toplu Sorgulama Excel'i (sayfa FATURALAR, 18 sutun) -> {"faturalar": {...}, "tekrar": n, ...}.

    Ayni fatura birden cok kez gelebiliyor (birebir ayni satir); tekrarlar atilir. Fatura basina:
    matrah, kdv, toplam, tur, oran, tevkifat_kdv.
    """
    basliklar, satirlar = excelden_tablo(yol, log)
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

def sonuclari_hesapla(firma, yon, tipler, kayitlar, excel, klasor_fn, dosyalar=(), log=None):
    """Liste kayitlari + Excel -> {belge tipi: sonuc sozlugu} (yalniz `tipler` icin).

    kayitlar: kayitlari_birlestir() ciktisi (entegrasyon bilgisi). Bos ise (ya da hic eslesmezse)
    tum faturalar yonun birincil ekranina yazilir ve nota dusulur.
    klasor_fn(tip) -> o ekranin csv klasoru (Path).
    """
    faturalar = excel["faturalar"] if excel else {}
    tip_no = {t: OrderedDict() for t in tipler}   # tip -> {no: kayit}
    tanimsiz = 0
    for k in kayitlar:
        t = entegrasyon_tipi(k["entegrasyon"] or k["tur"], yon)
        if t not in tip_no:
            tanimsiz += 1
            t = BIRINCIL[yon] if BIRINCIL[yon] in tip_no else tipler[0]
        tip_no[t].setdefault(k["no"], k)
    bilinen = {n for d in tip_no.values() for n in d}
    eslesmeyen = [n for n in faturalar if n not in bilinen]
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
        if tanimsiz:
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


def _entegrasyon_satirlari(page):
    """(cerceve, pencere, [{ad, secili, n}]); satir bulunamazsa bos liste."""
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


def entegrasyonlari_sec(page, turmob_var, log):
    """Entegrasyon Sec penceresinde yalniz izinli olanlari isaretler, Kaydet'e basar.

    Dondurur: secilen entegrasyon adlari listesi. Pencere/satir bulunamazsa TopluBasarisiz.
    """
    acik_pencereleri_kapat(page, log)
    if not dugmeye_bas(page, "Entegrasyon Seç", sure=6000):
        raise TopluBasarisiz("'Entegrasyon Seç' butonuna basilamadi")
    kosulu_bekle(page, lambda: bool(_entegrasyon_satirlari(page)[2]), 5000, aralik_ms=300)
    fr, pencere, satirlar = _entegrasyon_satirlari(page)
    if not satirlar:
        raise TopluBasarisiz("Entegrasyon Sec penceresinde satir/onay kutusu bulunamadi")
    gunluge_yaz("    TANI: entegrasyon satirlari: " + " | ".join(
        f"{'X' if s['secili'] else '-'} {s['ad'][:50]}" for s in satirlar), log)
    satirlar = [s for s in satirlar if not re.match(r"(TUMUNU|HEPSINI|TUMU\b)", sadelestir(s["ad"]))]
    secilen = []
    for s in satirlar:
        istenen = entegrasyon_izinli(s["ad"], turmob_var)
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
        if simdi is not None and bool(simdi) != entegrasyon_izinli(s["ad"], turmob_var):
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
            parca.append(fr.evaluate("() => document.body ? document.body.innerText : ''"))
        except Exception:
            continue
    return sadelestir(" ".join(parca))


def _sonucu_bekle(page, log, azami_saniye):
    """'Secili entegrasyonlarin sorgulanmasi tamamlandi' bildirimini bekler.

    Dondurur: 'tamam' | 'tamam_turmob_eksik' | 'turmob_eksik' | 'aralik' | 'zaman_asimi'.
    """
    basla = time.time()
    son_log = 0
    while time.time() - basla < azami_saniye:
        m = _ekran_metni(page)
        eksik = TOPLU_EKSIK_BILGI in m
        if TOPLU_AZAMI_UZUN in m:
            return "aralik"
        if eksik and "TURMOB" in m:
            return "tamam_turmob_eksik" if TOPLU_TAMAMLANDI in m else "turmob_eksik"
        if TOPLU_TAMAMLANDI in m:
            return "tamam"
        if time.time() - son_log >= 15:
            son_log = time.time()
            yaz(f"    ... toplu sorgu bekleniyor ({int(time.time() - basla)} sn)", log)
        sayfa_durulsun(page, azami_ms=800)
    return "zaman_asimi"


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


def toplu_getir(page, bas, bit, log):
    """Secili entegrasyonlardan tek bir (en fazla 1 aylik) aralik icin getirir; _sonucu_bekle durumu."""
    yaz(f"    Seçili Entegrasyonlardan Getir ({bas} - {bit})", log)
    acik_pencereleri_kapat(page, log)
    eski_kutulari_isaretle(page)
    if not dugmeye_bas(page, TOPLU_GETIR, sure=6000):
        raise TopluBasarisiz(f"'{TOPLU_GETIR}' butonuna basilamadi")
    pencere = _pencere_bekle(page, ["Başlangıç", "Bitiş", "Tarih Aralığı"])
    kutular = tarih_kutulari(page, pencere)
    if len(kutular) < 2:
        raise TopluBasarisiz("Toplu getir tarih kutulari bulunamadi")
    yaz(f"    Tarih araligi girildi: {tarih_araligi_yaz(kutular, bas, bit)}", log)
    tik = (pencerede_tikla(page, pencere, TOPLU_GETIR_ONAY, sure=5000) if pencere is not None else None) \
        or varsa_tikla(page, TOPLU_GETIR_ONAY, sure=5000)
    if not tik:
        raise TopluBasarisiz("Toplu getir onay butonu bulunamadi")
    yaz(f"    '{tik}' tiklandi, sorgu basladi", log)
    durum = _sonucu_bekle(page, log, AYAR["azami_saniye"])
    if durum == "tamam":
        yaz("    Seçili entegrasyonların sorgulanması tamamlandı", log)
    _bildirimi_kapat(page)
    return durum


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


def _liste_oku(page, yakalayici, log):
    """Yakalanan yanitlardan, yoksa ekrandan satirlari dondurur (kayit sozlukleri)."""
    kayitlar = kayitlari_birlestir(yakalayici.hamlar)
    if kayitlar:
        return kayitlar
    satirlar, _ = ekrandaki_satirlar(page)
    kayitlar = kayitlari_birlestir(satirlar)
    if not kayitlar:
        yaz("    UYARI: fatura listesi (entegrasyon bilgisi) okunamadi", log)
    return kayitlar


# Listede yalniz GIB e-Arsiv satirlarini isaretler (digerlerinin isaretini kaldirir). Dondurur:
# isaretlenen satir sayisi. Satir = kutusu olan tr / [role=row] / jqx satiri; baslik satiri atlanir.
ARSIV_SEC_JS = """(mod) => {
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
    const ist = mod === 'satis' ? metin.includes('5000')
      : metin.includes('ARSIV') && !metin.includes('5000') && !metin.includes('TURMOB') && !/E-?FATURA/.test(metin);
    if (ist !== durum(kutular[0])) kutular[0].click();
    if (ist) secili++;
  }
  return secili;
}"""


def arsiv_satirlarini_sec(page, log, yon="alis"):
    """Listede XML indirilecek satirlari isaretler, digerlerinin isaretini kaldirir; sayiyi dondurur.

    Alis: yalniz GIB e-Arsiv alis. Satis: yalniz GIB e-Arsiv (5000/30000).
    """
    sayi = 0
    for fr in cerceveler(page):
        try:
            sayi += int(fr.evaluate(ARSIV_SEC_JS, yon) or 0)
        except Exception:
            continue
    sayfa_durulsun(page, azami_ms=500)
    yaz(f"    XML icin isaretlenen satir ({'GİB 5000/30000' if yon == 'satis' else 'GİB e-Arşiv alış'}): {sayi}", log)
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
    firma_secili = _firma_ve_donem(page, firma, istenen_bas, istenen_bit, log, firma_secili)
    yaz(f"    Toplu Sorgulama ({'Alış' if yon == 'alis' else 'Satış'}) açılıyor", log)
    if not toplu_menuye_git(page, yon):
        raise TopluBasarisiz("Toplu Sorgulama ekrani acilamadi (menu degismis ya da modul yok)")
    fatura_yok_penceresini_kapat(page)

    turmob = turmob_var and firma not in TURMOB_YOK
    entegrasyonlari_sec(page, turmob, log)
    for bas, bit in parcalar:
        durum = toplu_getir(page, bas, bit, log)
        if durum in ("turmob_eksik", "tamam_turmob_eksik") and turmob:
            yaz("    TÜRMOB bilgisi girilmemis; TÜRMOB secilmeden devam ediliyor", log)
            TURMOB_YOK.add(firma)
            turmob = False
            entegrasyonlari_sec(page, False, log)
            if durum == "turmob_eksik":
                durum = toplu_getir(page, bas, bit, log)
        if durum == "aralik":
            raise TopluBasarisiz("Luca 'en fazla 1 aylik sorgu' dedi; aralik kisaltilmali")
        if durum == "zaman_asimi":
            raise TopluBasarisiz(f"toplu sorgu {AYAR['azami_saniye']} sn icinde bitmedi")
        if durum not in ("tamam", "tamam_turmob_eksik"):
            raise TopluBasarisiz(f"toplu sorgu sonucu: {durum}")

    klasor = cikti_kok / dosya_adi_yap(firma) / f"toplu-{yon}"
    klasor.mkdir(parents=True, exist_ok=True)
    with _ListeYakalayici(page) as yakalayici:
        belge_ara(page, istenen_bas.strftime(TARIH_BICIMI), istenen_bit.strftime(TARIH_BICIMI), log,
                  acik_pencere_once=True)
        sayfa_durulsun(page, azami_ms=2000)
        kayitlar = _liste_oku(page, yakalayici, log)
    yaz(f"    Listede {len(kayitlar)} kayit", log)

    dosyalar = []
    excel = None
    if AYAR["excel_indir"]:
        yol = dosya_indir(page, "Excel", klasor, "toplu", log,
                          azami_saniye=max(AYAR["indirme_saniye"], 60) + int(len(kayitlar) * 0.3),
                          pencere_acilir=False)
        if not yol:   # bazi ekranlar once secim istiyor
            hepsini_sec(page, None, len(kayitlar))
            yol = dosya_indir(page, "Excel", klasor, "toplu", log, azami_saniye=60, pencere_acilir=False)
        if yol:
            dosyalar.append(yol.name)
            excel = toplu_excel_oku(yol, log)
            if excel["tekrar"]:
                yaz(f"    Excel'de {excel['tekrar']} tekrarlanan satir atildi", log)
            yaz(f"    Excel'den {len(excel['faturalar'])} fatura okundu", log)
        else:
            yaz("    UYARI: Excel inmedi; tutarlar bos kalacak", log)
    azami = AYAR.get("azami_fatura") or 0
    # XML/zip: alista yalniz GIB e-Arsiv alis, satista yalniz GIB 5000/30000 (e-Fatura/TURMOB/e-Arsiv satis inmez)
    xml_tipi = "e-arsiv-alis" if yon == "alis" else "gib-5000"
    xml_kayit = [k for k in kayitlar if entegrasyon_tipi(k["entegrasyon"] or k["tur"], yon) == xml_tipi]
    if AYAR["belge_indir"] and xml_tipi in tipler and xml_kayit:
        if azami and len(xml_kayit) > azami:
            yaz(f"    XML paketi atlandi: {len(xml_kayit)} fatura (sinir {azami})", log)
        elif not arsiv_satirlarini_sec(page, log, yon):
            yaz("    UYARI: XML satirlari isaretlenemedi; paket indirilmedi (baska entegrasyon inmesin diye)", log)
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
                                 lambda t: cikti_kok / dosya_adi_yap(firma) / t, dosyalar, log)
    if AYAR["excel_indir"] and excel is None:
        for s in sonuclar.values():
            if s["durum"] == "tamam":
                s["durum"] = "excel inmedi"
    return sonuclar, firma_secili
