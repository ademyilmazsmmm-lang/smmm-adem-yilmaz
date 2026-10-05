# -*- coding: utf-8 -*-
"""Luca'daki musteri (firma) listesini okuma.

Yol: Yönetici > Müşteri İşlemleri > Müşteri Listesi; alttaki Filtre dugmesi
"Müşteri Arama" penceresini acar (Yıl, Sınıf, Dönem Durumu), Ara'dan sonra
secilen yilin butun firmalari kisa ad, unvan, vergi dairesi, VKN ve
acilis/kapanis tarihleriyle listelenir.

Ekran gercek Luca'da henuz gorulmedigi icin tablo okuma yapidan bagimsiz
yazildi (baslik adlariyla, olmazsa hucre desenleriyle) ve her calismada
ekran goruntusu + sayfa kaynagi tani klasorune kaydedilir.
"""

import json
import re
from datetime import date, datetime

from .bekleme import CERCEVE_GORUNUR_JS, kosulu_bekle, sayfa_durulsun
from .luca_ekran import (acik_pencereleri_kapat, cerceveler, dugmeye_bas, gorunur_mu,
                         menu_metinleri, metinle_bul)
from .luca_gezinme import menu_ogesini_ac
from .ortak import sadelestir, yaz

MUSTERI_LISTESI_DOSYASI = "luca-musteri-listesi.json"
YONETICI_MENUSU = "Yönetici"
MUSTERI_ISLEMLERI = "Müşteri İşlemleri"
MUSTERI_LISTESI = "Müşteri Listesi"
FILTRE_DUGMESI = "Filtre"
ARAMA_PENCERESI = "Müşteri Arama"

VKN_DESENI = re.compile(r"^\d{10,11}$")
TARIH_DESENI = re.compile(r"(\d{2})[./-](\d{2})[./-](\d{4})|(\d{4})-(\d{2})-(\d{2})")
BASLIK_KELIMELERI = ("UNVAN", "VKN", "VERGI", "KISA", "ACILIS", "KAPANIS", "SINIF", "DONEM", "BASLANGIC", "BITIS")
TOPLAM_DESENI = re.compile(r"Kay[ıi]t\s+Say[ıi]s[ıi]\s*:?\s*(\d+)", re.I)

# Gorunen tablolar/izgaralar: her biri hucre metinlerinin satir listesi
TABLOLAR_JS = """() => {
  const metin = e => (e.innerText || e.textContent || '').replace(/\\s+/g, ' ').trim();
  const gorunur = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const kap = 'table, [role=grid], [role=treegrid]';
  const sonuc = [];
  for (const t of document.querySelectorAll(kap)) {
    if (!gorunur(t)) continue;
    const satirlar = [];
    for (const r of t.querySelectorAll('tr, [role=row]')) {
      if (r.closest(kap) !== t) continue;
      const h = [...r.querySelectorAll('td, th, [role=gridcell], [role=cell], [role=columnheader]')]
        .filter(c => c.closest('tr, [role=row]') === r).map(metin);
      if (h.length) satirlar.push(h);
    }
    if (satirlar.length) sonuc.push(satirlar);
  }
  return sonuc;
}"""

# Yil listesini bulur: secenegi tam olarak o yil olan gorunur select; "Dönem Durumu"
# yazisi yakinindaki (arama penceresindeki) tercih edilir. Bulunani isaretler.
YIL_LISTESI_JS = """yil => {
  document.querySelectorAll('[data-lucabot-yil]').forEach(e => e.removeAttribute('data-lucabot-yil'));
  const gorunur = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const adaylar = [];
  for (const s of document.querySelectorAll('select')) {
    if (!gorunur(s)) continue;
    if (![...s.options].some(o => o.text.trim() === yil)) continue;
    let puan = 0, a = s;
    for (let i = 0; i < 8 && a; i++, a = a.parentElement)
      if ((a.innerText || '').includes('Dönem Durumu')) { puan = 1; break; }
    adaylar.push([puan, s]);
  }
  if (!adaylar.length) return 0;
  adaylar.sort((x, y) => y[0] - x[0]);
  adaylar[0][1].setAttribute('data-lucabot-yil', '1');
  return adaylar.length;
}"""

# Sinif listesini bulur: "Dönem Durumu" yazisi yakinindaki (arama penceresindeki) select'lerde
# secenegi hedeflerden birine uyan ilk secenek; bosluk/nokta/Turkce harf farki yok sayilir.
# Bulunani isaretler; {secilen, secenekler} dondurur (secenekler: pencereye ait tum listeler, tani icin).
SINIF_LISTESI_JS = """hedefler => {
  document.querySelectorAll('[data-lucabot-sinif]').forEach(e => e.removeAttribute('data-lucabot-sinif'));
  const duz = t => (t || '').toLocaleLowerCase('tr').replace(/[\\s.\\-()]/g, '');
  const gorunur = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const listeler = [...document.querySelectorAll('select')].filter(s => {
    if (!gorunur(s)) return false;
    let a = s;
    for (let i = 0; i < 8 && a; i++, a = a.parentElement)
      if ((a.innerText || '').includes('Dönem Durumu')) return true;
    return false;
  });
  const sonuc = {secilen: '', secenekler: listeler.map(s => [...s.options].map(o => o.text.trim()).join(' | '))};
  for (const h of hedefler.map(duz).filter(Boolean)) {
    for (const s of listeler) {
      const ops = [...s.options];
      const o = ops.find(o => duz(o.text) === h) || ops.find(o => duz(o.text).startsWith(h))
        || ops.find(o => duz(o.text).includes(h));
      if (o) { s.setAttribute('data-lucabot-sinif', '1'); sonuc.secilen = o.text.trim(); return sonuc; }
    }
  }
  return sonuc;
}"""


# Gercek Luca: YIL ve SINIF listelerinin onchange'i gonder('yil') cagirir; bu islev iki listenin o anki degerlerini
# okuyup sayfayi (listSirketAction.do?yil=..&sinif=..) YENIDEN YUKLER ve Musteri Arama penceresini kapatir. Bu yuzden
# pencereyi acip tek tek secmek yerine iki degeri birden ayarlayip gonder('yil') bir kez cagrilir.
FILTRE_UYGULA_JS = """arg => {
  const duz = t => (t || '').toLocaleLowerCase('tr').replace(/[\\s.\\-()]/g, '');
  const sec = (id, hedefler) => {
    const s = document.getElementById(id);
    if (!s) return null;
    const ops = [...s.options];
    for (const h of hedefler.map(duz).filter(Boolean)) {
      const o = ops.find(o => duz(o.text) === h) || ops.find(o => duz(o.text).startsWith(h))
        || ops.find(o => duz(o.text).includes(h));
      if (o) { s.value = o.value; return o.text.trim(); }
    }
    return '';
  };
  const sonuc = {hazir: typeof gonder === 'function' && !!document.getElementById('YIL'), yil: '', sinif: null, siniflar: ''};
  if (!sonuc.hazir) return sonuc;
  sonuc.yil = sec('YIL', [arg.yil]);
  const s = document.getElementById('SINIF');
  sonuc.siniflar = s ? [...s.options].map(o => o.text.trim()).join(' | ') : '';
  if (arg.sinif.length) sonuc.sinif = sec('SINIF', arg.sinif);
  return sonuc;
}"""


# --- tablodan kayit cikarma (tarayicisiz, test edilebilir) -----------------------

def tarih_metni(deger, yil=None):
    """GG/AA/YYYY ya da bos. Excel'den gelen datetime/date de kabul edilir."""
    if isinstance(deger, (datetime, date)):
        return f"{deger:%d/%m/%Y}"
    m = TARIH_DESENI.search(str(deger or ""))
    if not m:
        return ""
    if m.group(1):
        g, a, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        y, a, g = int(m.group(4)), int(m.group(5)), int(m.group(6))
    try:
        return f"{date(y, a, g):%d/%m/%Y}"
    except ValueError:
        return ""


def baslik_satiri_mi(hucreler):
    if any(VKN_DESENI.match(h.strip()) or TARIH_DESENI.search(h) for h in hucreler):
        return False
    # veri satirindaki "... VERGI DAIRESI" gibi uzun metinler baslik sanilmasin
    isabet = sum(1 for h in hucreler
                 if len(h.strip()) <= 18 and any(k in sadelestir(h) for k in BASLIK_KELIMELERI))
    return isabet >= 2


def veri_satiri_mi(hucreler):
    return any(VKN_DESENI.match(h.strip()) for h in hucreler)


def en_iyi_tablo(tablolar):
    """tablolar: [(cerceve no, satirlar)]. Dondurur: (baslik hucreleri ya da None, veri satirlari).

    Veri tablosu en cok VKN'li satiri olandir; basligi kendi ilk satirlarinda
    ya da (baslik ayri tabloda duruyorsa) ayni cercevedeki baska bir tabloda aranir.
    """
    en_iyi, en_cok = None, 0
    for cerceve, satirlar in tablolar:
        veri = [s for s in satirlar if veri_satiri_mi(s)]
        if len(veri) > en_cok:
            en_iyi, en_cok = (cerceve, satirlar, veri), len(veri)
    if en_iyi is None:
        return None, []
    cerceve, satirlar, veri = en_iyi
    baslik = next((s for s in satirlar[:6] if baslik_satiri_mi(s)), None)
    if baslik is None:
        baslik = next((s for c, diger in tablolar if c == cerceve
                       for s in diger[:6] if baslik_satiri_mi(s)), None)
    if baslik is not None:
        # vergi no'su bos firma da listede: baslik biliniyorsa basligi tutan her satir veridir
        veri = [s for s in satirlar if not baslik_satiri_mi(s) and len(s) >= max(3, len(baslik) - 1)
                and any(h.strip() for h in s)]
    return baslik, veri


def _sutun_indeksleri(baslik):
    """Baslik hucrelerinden alan -> sutun no (bulunamayanlar yok)."""
    kurallar = (
        ("ad", lambda b: "KISA" in b),
        ("unvan", lambda b: "UNVAN" in b or "UZUN AD" in b),
        ("vergi_dairesi", lambda b: "VERGI DAIRESI" in b),
        ("vkn", lambda b: "VKN" in b or "VERGI NO" in b or "VERGI KIMLIK" in b),
        ("tc", lambda b: "KIMLIK" in b),
        ("acilis", lambda b: "ACILIS" in b or "KURULUS" in b),
        ("kapanis", lambda b: "KAPANIS" in b),
    )
    idx = {}
    for i, h in enumerate(baslik or []):
        b = sadelestir(h)
        for alan, kural in kurallar:
            if alan not in idx and kural(b):
                idx[alan] = i
                break
    if "acilis" not in idx and "kapanis" not in idx:  # baska adlandirma
        for i, h in enumerate(baslik or []):
            b = sadelestir(h)
            if "BASLANGIC" in b and "acilis" not in idx:
                idx["acilis"] = i
            elif "BITIS" in b and "kapanis" not in idx:
                idx["kapanis"] = i
    return idx


def kayit_cikar(baslik, hucreler):
    """Bir veri satirindan {ad, unvan, vergi_dairesi, vkn, acilis, kapanis, ham}."""
    hucreler = [h.strip() for h in hucreler]
    idx = _sutun_indeksleri(baslik)
    # veri satirinda basa eklenen sutunlar (kutu, sira no) varsa baslik saga hizalanir
    kayma = max(0, len(hucreler) - len(baslik)) if baslik else 0

    def al(alan):
        i = idx.get(alan)
        if i is None:
            return None
        i += kayma
        return hucreler[i] if i < len(hucreler) else ""

    vkn = al("vkn")
    if vkn is None or not VKN_DESENI.match(vkn):
        vkn = next((h for h in hucreler if VKN_DESENI.match(h)), "")
    dolu = [h for h in hucreler if h]
    ad = al("ad")
    unvan = al("unvan")
    if ad is None:  # baslik okunamadi: sirayla ilk iki metin kisa ad ve unvan
        metinler = [h for h in dolu if not VKN_DESENI.match(h) and not TARIH_DESENI.search(h)]
        ad = metinler[0] if metinler else ""
        if unvan is None:
            unvan = metinler[1] if len(metinler) > 1 else ""
    acilis, kapanis = al("acilis"), al("kapanis")
    if acilis is None and kapanis is None:
        tarihler = [h for h in hucreler if TARIH_DESENI.search(h)]
        # tek tarihin acilis mi kapanis mi oldugu bilinemez: kapanis bos birakilir
        acilis = tarihler[0] if tarihler else ""
        kapanis = tarihler[1] if len(tarihler) > 1 else ""
    return {"ad": ad or "", "unvan": unvan or "", "vergi_dairesi": al("vergi_dairesi") or "",
            "vkn": vkn, "tc": al("tc") or "", "acilis": tarih_metni(acilis), "kapanis": tarih_metni(kapanis),
            "ham": hucreler}


def kayitlari_cikar(tablolar):
    """(kayitlar, baslik): tablolardan firma kayitlari; ayni VKN/ad bir kez."""
    baslik, satirlar = en_iyi_tablo(tablolar)
    kayitlar, gorulen = [], set()
    for s in satirlar:
        k = kayit_cikar(baslik, s)
        if not k["ad"]:
            continue
        anahtar = (sadelestir(k["ad"]), k["vkn"], k["tc"])
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        kayitlar.append(k)
    return kayitlar, baslik


# --- ekran ------------------------------------------------------------------------

def tablolari_al(page):
    tablolar = []
    for no, fr in enumerate(cerceveler(page)):
        try:
            for satirlar in fr.evaluate(TABLOLAR_JS) or []:
                tablolar.append((no, satirlar))
        except Exception:
            continue
    return tablolar


def ekrandaki_kayitlar(page):
    return kayitlari_cikar(tablolari_al(page))


def toplam_kayit(page):
    """Ekranda 'Toplam Kayıt Sayısı: N' gibi bir yazi varsa N; yoksa None."""
    for fr in cerceveler(page):
        try:
            m = TOPLAM_DESENI.search(fr.locator("body").inner_text(timeout=2000))
        except Exception:
            continue
        if m:
            return int(m.group(1))
    return None


def tani_kaydet(page, klasor, log, ek="", ad="musteri-listesi"):
    """Ekran goruntusu ve butun cercevelerin kaynagi: ekran gercekte nasil, sonradan bakilabilsin."""
    try:
        klasor.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(klasor / f"{ad}{ek}.png"))
        for no, fr in enumerate(page.frames):
            try:
                (klasor / f"{ad}{ek}-cerceve{no}.html").write_text(fr.content(), encoding="utf-8")
            except Exception:
                continue
        yaz(f"    Tani dosyalari kaydedildi: {klasor}", log)
    except Exception as e:
        yaz(f"    Tani kaydedilemedi ({type(e).__name__})", log)


def musteri_listesini_ac(page, log=None):
    """Yönetici > Müşteri İşlemleri > Müşteri Listesi; ekranin Filtre dugmesi gorunene kadar."""
    def gorunur(metin):
        return lambda: gorunur_mu(page, metin, sure=1200)

    for _ in range(3):
        acik_pencereleri_kapat(page)
        menu_ogesini_ac(page, YONETICI_MENUSU, sure=8000, dogrula=gorunur(MUSTERI_ISLEMLERI))
        menu_ogesini_ac(page, MUSTERI_ISLEMLERI, sure=4000, dogrula=gorunur(MUSTERI_LISTESI))
        try:
            _, madde = metinle_bul(page, MUSTERI_LISTESI, sure=4000)
            madde.click(timeout=8000)
        except Exception:
            sayfa_durulsun(page, azami_ms=1000)
            continue
        if gorunur_mu(page, FILTRE_DUGMESI, sure=15000):
            return True
    raise LookupError(f"'{YONETICI_MENUSU} > {MUSTERI_ISLEMLERI} > {MUSTERI_LISTESI}' menusu acilamadi")


def _filtreyi_dogrudan_uygula(page, yil, sinif, log=None):
    """Gercek Luca'da Yıl/Sınıf'ı JS ile ayarlayip gonder('yil') ile listeyi yeniden yukler; sayfa yenilenene kadar bekler.

    Musteri Listesi ikinci kez acildiginda yeni bir sekmede/cercevede gelebilir; filtre o sirada gorunen eski cerceveye
    uygulanirsa sekme degisince gizlenir. Bu yuzden uygulandiktan sonra cercevenin hala gorunur oldugu dogrulanir,
    degilse gorunur olana yeniden uygulanir.

    Dondurur: True (uygulandi); False: bu ekran Luca'nin Musteri Listesi'ne benzemiyor (eski yola gecilir).
    """
    hedefler = [sinif] if isinstance(sinif, str) and sinif else list(sinif or [])
    for deneme in range(4):
        uygulandi = False
        for fr in page.frames:
            try:
                if fr.evaluate(CERCEVE_GORUNUR_JS) is False:  # gizli sekmede kalan eski Musteri Listesi
                    continue
                sonuc = fr.evaluate(FILTRE_UYGULA_JS, {"yil": yil, "sinif": hedefler})
            except Exception:
                continue
            if not sonuc or not sonuc.get("hazir"):
                continue
            if not sonuc["yil"]:
                yaz(f"    UYARI: Yıl listesinde '{yil}' seçeneği bulunamadı", log)
                return False
            if hedefler and not sonuc["sinif"]:
                yaz(f"    UYARI: Sınıf listesinde {' / '.join(hedefler)} seçeneği bulunamadı; Sınıf filtresiz devam"
                    f" ediliyor. Sınıf seçenekleri: {sonuc['siniflar']}", log)
            elif hedefler and deneme == 0:
                yaz(f"    Sınıf={sonuc['sinif']} seçildi", log)
            try:
                fr.evaluate("() => { window.__lucabot_eski = 1; gonder('yil'); }")
            except Exception:
                pass  # sayfa yeniden yuklenirken baglam kopabilir

            def yenilendi(fr=fr):
                try:
                    return not fr.evaluate("() => window.__lucabot_eski === 1")
                except Exception:
                    return True  # baglam koptu: sayfa yenileniyor
            if not kosulu_bekle(page, yenilendi, 30000, aralik_ms=400):
                yaz("    UYARI: filtre sonrasi liste yenilenmedi", log)
                return False
            sayfa_durulsun(page, azami_ms=3000, sessizlik_ms=700)
            uygulandi = True
            try:
                if fr.evaluate(CERCEVE_GORUNUR_JS) is False:  # baska bir sekme one gecti: gorunur olana yeniden uygula
                    break
            except Exception:
                pass
            return True
        if not uygulandi:
            return False
    return False


def yili_filtrele(page, yil, log=None, sinif=""):  # sinif: metin ya da alternatif metinler listesi
    """Filtre penceresinde Yıl'ı (ve verilmisse Sınıf'ı) secip Ara'ya basar.

    False: pencere ya da Yıl listesi bulunamadi. Sınıf listesi/secenegi bulunamazsa uyarilir,
    Sınıf filtresiz devam edilir.
    """
    yil = str(yil)
    if _filtreyi_dogrudan_uygula(page, yil, sinif, log):
        return True
    for _ in range(2):
        dugmeye_bas(page, FILTRE_DUGMESI, sure=8000)
        if gorunur_mu(page, ARAMA_PENCERESI, sure=8000):
            break
    else:
        yaz(f"    '{ARAMA_PENCERESI}' penceresi acilmadi", log)
        return False

    secici = None
    for fr in cerceveler(page):
        try:
            if fr.evaluate(YIL_LISTESI_JS, yil):
                secici = fr
                break
        except Exception:
            continue
    if secici is None:
        yaz(f"    Yıl listesinde '{yil}' secenegi bulunamadi", log)
        return False
    liste = secici.locator("[data-lucabot-yil]")
    try:
        liste.select_option(label=yil, timeout=8000)
    except Exception:
        try:
            liste.select_option(value=yil, timeout=8000)
        except Exception as e:
            yaz(f"    Yıl secilemedi ({type(e).__name__})", log)
            return False
    if sinif:
        _sinifi_sec(page, secici, sinif, log)

    for kurucu in (lambda: secici.get_by_role("button", name="Ara", exact=True),
                   lambda: secici.get_by_text("Ara", exact=True)):
        try:
            kurucu().first.click(timeout=5000)
            return True
        except Exception:
            continue
    return dugmeye_bas(page, "Ara", sure=5000)


def _sinifi_sec(page, cerceve, sinif, log=None):
    """sinif: metin ya da alternatif metinler listesi; ilk uyan secilir. Bulunamazsa False (secenekler loga yazilir).

    Yil/Sinif listeleri secilince Luca formu yeniden yukluyor (onchange=gonder): isaretlenen oge kaybolabilir,
    bu yuzden sayfa durulunca islem birkac kez denenir.
    """
    hedefler = [sinif] if isinstance(sinif, str) else list(sinif)
    son = None
    for _ in range(4):
        sayfa_durulsun(page, azami_ms=3000, sessizlik_ms=700)
        try:
            sonuc = cerceve.evaluate(SINIF_LISTESI_JS, hedefler)
            if not sonuc["secilen"]:
                yaz(f"    UYARI: Sınıf listesinde {' / '.join(hedefler)} seçeneği bulunamadı; Sınıf filtresiz devam"
                    f" ediliyor. Penceredeki listeler: {sonuc['secenekler']}", log)
                return False
            cerceve.locator("[data-lucabot-sinif]").select_option(label=sonuc["secilen"], timeout=4000)
            sayfa_durulsun(page, azami_ms=3000, sessizlik_ms=700)  # secim formu yeniden yukleyebilir
            yaz(f"    Sınıf={sonuc['secilen']} seçildi", log)
            return True
        except Exception as e:
            son = e
    yaz(f"    UYARI: Sınıf seçilemedi ({type(son).__name__}); Sınıf filtresiz devam ediliyor", log)
    return False


def listeyi_oku(page, yil, tani_klasoru, log=None, bekleme_ms=30000, sinif=""):
    """Musteri Listesi ekranini acar, yili (ve Sınıf'i) suzer ve firma kayitlarini dondurur."""
    try:
        musteri_listesini_ac(page, log)
    except LookupError:
        yaz(f"    Gorunen menuler: {menu_metinleri(page)}", log)
        tani_kaydet(page, tani_klasoru, log, "-menu")
        raise
    yaz(f"Müşteri Listesi acildi; Yıl={yil}{', Sınıf=' + (sinif if isinstance(sinif, str) else '/'.join(sinif)) if sinif else ''}"
        " filtreleniyor", log)
    if not yili_filtrele(page, yil, log, sinif):
        tani_kaydet(page, tani_klasoru, log, "-filtre")
        raise LookupError("Filtre penceresi kullanilamadi (tani klasorune bakin)")

    kosulu_bekle(page, lambda: len(ekrandaki_kayitlar(page)[0]) > 0, bekleme_ms, aralik_ms=700)
    kayitlar, baslik = [], None
    for _ in range(6):  # liste doldukca sayi artar: iki okuma ayni olunca bitmistir
        sayfa_durulsun(page, azami_ms=1500, sessizlik_ms=500)
        yeni, baslik = ekrandaki_kayitlar(page)
        if yeni and len(yeni) == len(kayitlar):
            break
        kayitlar = yeni
    tani_kaydet(page, tani_klasoru, log)
    yaz(f"Tablo basligi: {baslik if baslik else 'bulunamadi (hucre desenlerinden okundu)'}", log)
    if kayitlar:
        yaz(f"Ilk kayit: {kayitlar[0]['ham']}", log)
    toplam = toplam_kayit(page)
    if toplam is not None and toplam > len(kayitlar):
        yaz(f"UYARI: ekranda toplam {toplam} kayit yazıyor, {len(kayitlar)} tanesi okunabildi"
            " (liste sayfalara bolunmus olabilir)", log)
    return kayitlar


def kaydet(yol, yil, kayitlar):
    yol.write_text(json.dumps({"yil": int(yil), "alinma": datetime.now().isoformat(timespec="seconds"),
                               "firmalar": kayitlar}, ensure_ascii=False, indent=1), encoding="utf-8")


def oku(yol):
    """kaydet() ile yazilan dosyadan (yil, kayitlar); dosya yoksa/bozuksa ValueError."""
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
        return int(veri["yil"]), list(veri["firmalar"])
    except (OSError, KeyError, TypeError) as e:
        raise ValueError(f"{yol.name} okunamadi") from e
