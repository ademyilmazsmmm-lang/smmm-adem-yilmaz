# -*- coding: utf-8 -*-
"""Genel muhasebe firmalarinda Luca'daki Hesap Plani Listesi'nden kar/zarar tahmini.

Yol: Muhasebe > Hesap Planı İşlemleri > Hesap Planı Listesi. Alttaki Filtre
"Hesap Arama" penceresini acar; Başlangıç/Bitiş Tarih donemi belirler. Listede
her hesabin Borç/Alacak toplamlari ve bakiyeleri vardir (sinif satirlari dahil:
"6", "7" ...). Hesaplama:

  Gelir     = 6'li hesaplarin alacak - borc farki (satislar ve gelirler, indirimler dusulmus)
  Mal alisi = 150-153 hesaplarin borc - alacak farki
  Gider     = 7'li hesaplarin borc - alacak farki
  Kar       = Gelir - Mal alisi - Gider      (eksi ise zarar)
"""

import re

from lucabot.bekleme import kosulu_bekle, sayfa_durulsun
from lucabot.fatura_analiz import tutar_cozumle
from lucabot.luca_ekran import acik_pencereleri_kapat, dugmeye_bas, gorunur_mu
from lucabot.luca_form import alan, alanlari_isaretle, metin_yaz
from lucabot.luca_gezinme import menu_yolunu_ac
from lucabot.musteri_listesi import tablolari_al, tani_kaydet
from lucabot.ortak import sadelestir

MENU_YOLU = "Muhasebe > Hesap Planı İşlemleri > Hesap Planı Listesi"
ARAMA_PENCERESI = "Hesap Arama"
KOD_DESENI = re.compile(r"^\d+(\.\d+)*$")
SAYI_DESENI = re.compile(r"^-?\d{1,3}(\.\d{3})*,\d{2}$|^-?\d+,\d{2}$")
STOK_HESAPLARI = ("150", "151", "152", "153")


# --- listeyi satirlara cevirme (tarayicisiz, test edilebilir) --------------------------

def hesap_satirlari(tablolar):
    """tablolar: [(cerceve no, satirlar)] -> [{kod, ad, borc, alacak}] (en cok hesap satiri olan tablodan)."""
    en_iyi, en_cok = None, 0
    for _, satirlar in tablolar:
        adet = sum(1 for s in satirlar if _kod(s))
        if adet > en_cok:
            en_iyi, en_cok = satirlar, adet
    if en_iyi is None:
        return []
    baslik = next((s for s in en_iyi[:6] if sadelestir(" ".join(s)).startswith("HESAP KODU")), None)
    sutunlar = {}
    if baslik:
        for i, h in enumerate(baslik):
            sutunlar.setdefault(sadelestir(h), i)
    sonuc = []
    for s in en_iyi:
        kod = _kod(s)
        if not kod:
            continue
        i = next(j for j, h in enumerate(s[:3]) if h.strip() == kod)
        sayilar = [h for h in s[i + 1:] if SAYI_DESENI.match(h.strip())]
        kayma = max(0, len(s) - len(baslik)) if baslik else 0  # satir basinda fazladan kutu/ikon hucresi
        if ("BORC" in sutunlar and "ALACAK" in sutunlar
                and max(sutunlar["BORC"], sutunlar["ALACAK"]) + kayma < len(s)
                and SAYI_DESENI.match(s[sutunlar["BORC"] + kayma].strip())):
            borc, alacak = s[sutunlar["BORC"] + kayma], s[sutunlar["ALACAK"] + kayma]
        elif len(sayilar) >= 2:  # baslik okunamadi: ilk iki sayi Borç ve Alacak
            borc, alacak = sayilar[0], sayilar[1]
        else:
            continue
        ad = next((h for h in s[i + 1:] if h.strip() and not SAYI_DESENI.match(h.strip())), "")
        sonuc.append({"kod": kod, "ad": ad, "borc": tutar_cozumle(borc), "alacak": tutar_cozumle(alacak)})
    return sonuc


def _kod(hucreler):
    """Satir hesap satiri ise hesap kodu (ilk uc hucreden biri) ve satirda en az iki tutar var."""
    kod = next((h.strip() for h in hucreler[:3] if KOD_DESENI.match(h.strip())), "")
    if not kod:
        return ""
    return kod if sum(1 for h in hucreler if SAYI_DESENI.match(h.strip())) >= 2 else ""


def _toplam(satirlar, kod):
    """Hesap grubunun (borc, alacak) toplami.

    Once tam kodlu satir; yoksa bir alt duzeydeki satirlar (sinif icin 2 haneli, sonra 3 haneli
    ana hesaplar; ana hesap icin 'kod.xx' alt hesaplar). Bulunamazsa (0, 0): calismayan hesap.
    """
    tam = [s for s in satirlar if s["kod"] == kod]
    if tam:
        return tam[0]["borc"], tam[0]["alacak"]
    if len(kod) == 1:
        for uzunluk in (2, 3):
            alt = [s for s in satirlar if s["kod"].startswith(kod) and len(s["kod"]) == uzunluk]
            if alt:
                return sum(s["borc"] for s in alt), sum(s["alacak"] for s in alt)
    alt = [s for s in satirlar if s["kod"].startswith(kod + ".")]
    if alt:
        # ust duzey toplamlari ayri satirsa iki kat sayilmasin: yalniz en kisa kodlu alt satirlar
        en_kisa = min(len(s["kod"]) for s in alt)
        alt = [s for s in alt if len(s["kod"]) == en_kisa]
        return sum(s["borc"] for s in alt), sum(s["alacak"] for s in alt)
    return 0.0, 0.0


def kar_zarar(satirlar):
    """Hesap satirlarindan {satis, mal_alis, gider, kar, ayrinti}."""
    b6, a6 = _toplam(satirlar, "6")
    b7, a7 = _toplam(satirlar, "7")
    stok = [_toplam(satirlar, k) for k in STOK_HESAPLARI]
    gelir = a6 - b6
    mal_alis = sum(b - a for b, a in stok)
    gider = b7 - a7
    return {"satis": round(gelir, 2), "mal_alis": round(mal_alis, 2), "gider": round(gider, 2),
            "kar": round(gelir - mal_alis - gider, 2),
            "ayrinti": {"6": [b6, a6], "7": [b7, a7], **{k: list(t) for k, t in zip(STOK_HESAPLARI, stok)}}}


# --- ekran -------------------------------------------------------------------------

def _ekran_hazir(page):
    return gorunur_mu(page, "Hesap Kodu", sure=0) and gorunur_mu(page, "Hesap Adı", sure=0)


def ekrani_ac(page, yol=None):
    acik_pencereleri_kapat(page)
    return menu_yolunu_ac(page, yol or MENU_YOLU, lambda: _ekran_hazir(page))


def filtrele(page, bas, bit, log=None):
    """Filtre > Hesap Arama: Başlangıç/Bitiş Tarih yazilip Ara'ya basilir."""
    for _ in range(2):
        dugmeye_bas(page, "Filtre", sure=8000)
        if gorunur_mu(page, ARAMA_PENCERESI, sure=8000):
            break
    else:
        raise LookupError(f"'{ARAMA_PENCERESI}' penceresi acilmadi")
    cerceve = alanlari_isaretle(page, ARAMA_PENCERESI, ["Başlangıç Tarih", "Bitiş Tarih"],
                                zorunlu="Başlangıç Tarih")
    for etiket, d in (("Başlangıç Tarih", bas), ("Bitiş Tarih", bit)):
        if not metin_yaz(alan(cerceve, etiket), f"{d:%d/%m/%Y}"):
            raise LookupError(f"'{etiket}' alanina {d:%d/%m/%Y} yazilamadi")
    for kurucu in (lambda: cerceve.get_by_role("button", name="Ara", exact=True),
                   lambda: cerceve.get_by_text("Ara", exact=True)):
        try:
            kurucu().first.click(timeout=5000)
            return
        except Exception:
            continue
    raise LookupError("'Ara' dugmesine basilamadi")


def listeyi_oku(page):
    return hesap_satirlari(tablolari_al(page))


def hesap_plani_oku(page, bas, bit, tani_klasoru, log=None):
    """Acik firmanin Hesap Planı Listesi'ni donem icin suzer; kar_zarar() sonucunu dondurur."""
    try:
        ekrani_ac(page)
        filtrele(page, bas, bit, log)
    except LookupError:
        tani_kaydet(page, tani_klasoru, log, "-hata", "hesap-plani")
        raise
    kosulu_bekle(page, lambda: len(listeyi_oku(page)) > 0, 30000, aralik_ms=700)
    satirlar = []
    for _ in range(6):  # liste doldukca sayi artar; iki okuma ayni olunca tamam
        sayfa_durulsun(page, azami_ms=1500, sessizlik_ms=500)
        yeni = listeyi_oku(page)
        if yeni and len(yeni) == len(satirlar):
            break
        satirlar = yeni
    if not satirlar:
        tani_kaydet(page, tani_klasoru, log, "-bos", "hesap-plani")
        raise LookupError("Hesap planı satırı okunamadı (bu dönemde hareket yok ya da liste gelmedi)")
    return kar_zarar(satirlar)
