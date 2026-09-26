# -*- coding: utf-8 -*-
"""Ortak yardimcilar: ayarlar, gunluk, metin ve tarih islemleri.

Bu modul tarayiciya hic dokunmaz; butun diger program taslari buna dayanir.
"""

import json
import os
import re
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

# program klasoru (luca_bot.py'nin bulundugu yer)
KOK = Path(__file__).resolve().parent.parent
AYAR_DOSYASI = KOK / "ayarlar.json"
ORNEK_AYAR = KOK / "ayarlar.ornek.json"

# Calisma sirasinda kullanilan ayarlar. ayarlar.json ve komut satiri
# secenekleri luca_bot.ayarlari_uygula() ile buraya islenir; diger moduller
# yalnizca okur.
AYAR = {
    "azami_saniye": 900,        # bir GIB sorgusu icin en uzun bekleme
    "durgunluk_saniye": 180,    # Islem Takip bu sure ilerlemezse sorgu takildi sayilir
    "indirme_saniye": 30,       # dosyanin gelmesi icin beklenecek sure
    "iptal_itiraz": True,
    "donem_degistir": True,
    "chrome_gunlugu": False,
    "tarayici": None,
    "profil_yerel": False,
    "indirmeyi_yakala": True,
    "azami_fatura": 500,
    "giris_adresi": None,       # yalnizca test icin (sahte Luca); bos ise gercek Luca
    "tarayici_yolu": None,      # Playwright Chromium yerine belirli bir chrome.exe (istege bagli)
    "tarayici_sandbox": True,   # yalnizca test ortami (Linux/root) icin kapatilir
    "excel_azami_saniye": 600,  # Luca buyuk Excel'i hazirlarken en fazla bu kadar beklenir
}

TARIH_BICIMI = "%d/%m/%Y"
AZAMI_GUN = 7          # GIB sorgusu tek seferde en fazla 7 gun kabul ediyor
AYLIK_AZAMI_GUN = 30   # aylik sorguyu kabul eden ekranlar icin parca boyu


def ayarlari_oku():
    """ayarlar.json'u okur; yoksa ornek dosyayi kullanir.

    Dosya bozuksa (virgul unutulmus vb.) program anlasilmaz bir hatayla
    cokmek yerine hangi satirda sorun oldugunu soyler.
    """
    ozel = os.environ.get("LUCA_BOT_AYAR")  # farkli bir ayar dosyasi (test / ikinci buro)
    if ozel:
        kaynak = Path(ozel)
    else:
        kaynak = AYAR_DOSYASI if AYAR_DOSYASI.exists() else ORNEK_AYAR
    try:
        with open(kaynak, encoding="utf-8-sig") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise SystemExit(
            f"\nHATA: {kaynak.name} okunamadi (satir {e.lineno}, sutun {e.colno}): {e.msg}\n"
            "Dosyayi Not Defteri ile acip o satirdaki virgul/tirnak isaretlerini kontrol edin.")
    except FileNotFoundError:
        raise SystemExit(f"\nHATA: {kaynak.name} bulunamadi. ayarlar.ornek.json'u kopyalayip"
                         " adini ayarlar.json yapin.")


def yaz(mesaj, log_dosyasi=None):
    """Mesaji ekrana basar ve (verildiyse) zaman damgasiyla gunluge ekler.

    Gunluk yazilamasa bile (disk dolu, dosya kilitli) calisma durmaz.
    """
    try:
        print(mesaj, flush=True)
    except UnicodeEncodeError:  # eski Windows konsolu (chcp 65001 yapilmamis)
        print(mesaj.encode("ascii", "replace").decode("ascii"), flush=True)
    gunluge_yaz(mesaj, log_dosyasi)


def gunluge_yaz(mesaj, log_dosyasi):
    """Yalnizca gunluk dosyasina yazar (ekrani kalabaliklastirmayacak teknik ayrintilar)."""
    if not log_dosyasi:
        return
    try:
        with open(log_dosyasi, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {mesaj}\n")
    except OSError:
        pass


# --- metin -----------------------------------------------------------------

def sadelestir(metin):
    """Turkce karakter ve buyuk/kucuk harf farkini yok sayarak karsilastirma icin."""
    metin = (metin or "").replace("ı", "i").replace("İ", "i")
    metin = unicodedata.normalize("NFKD", metin)
    metin = "".join(c for c in metin if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", metin).strip().upper()


def karsilastir(metin):
    """Arama icin: Turkce/buyuk-kucuk farki ve bosluklar yok sayilir ('yakups' -> 'YAKUP SÖĞÜ')."""
    return sadelestir(metin).replace(" ", "")


def dosya_adi_yap(metin):
    metin = (metin or "").replace("ı", "i").replace("İ", "I")
    metin = unicodedata.normalize("NFKD", metin)
    metin = "".join(c for c in metin if not unicodedata.combining(c))
    metin = re.sub(r"[^A-Za-z0-9._ -]", "_", metin).strip()
    return re.sub(r"\s+", " ", metin) or "isimsiz"


# --- tarih -----------------------------------------------------------------

def tarih_cozumle(metin):
    return datetime.strptime(metin.strip(), TARIH_BICIMI).date()


def hedef_ay_araligi(baslangic, bitis):
    """Indirme/listeleme araligi: baslangic tarihinin ayinin tamami.

    Agustos faturalari eylulde de duzenlenebildigi icin kullanici
    01/08/2026-15/09/2026 gibi bir aralik veriyor. Eylul tarihleri yalnizca
    gec duzenlenen agustos faturalarini GIB'den cekmek icin sorgulanir;
    indirme ve listeleme agustosun tamami uzerinden yapilir.

    Sorgu araligi ayin sonundan once bitse bile (orn. 01/08-02/08 gibi kisa bir
    deneme) listeleme yine 01/08-31/08 olur: aksi halde daha once GIB'den
    cekilmis agustos faturalari "Belge Ara" suzgecine takilip listede
    gorunmuyordu.
    """
    ay_sonu = (baslangic.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return baslangic, ay_sonu


def tarih_araliklari(baslangic, bitis, gun=AZAMI_GUN):
    """`gun` gunluk parcalara boler; her parca bir oncekinin bitis tarihinden baslar."""
    if bitis < baslangic:
        raise ValueError("Bitis tarihi baslangictan once olamaz")
    araliklar = []
    su_an = baslangic
    while su_an < bitis:
        son = min(su_an + timedelta(days=gun), bitis)
        araliklar.append((su_an.strftime(TARIH_BICIMI), son.strftime(TARIH_BICIMI)))
        su_an = son
    if not araliklar:
        araliklar.append((baslangic.strftime(TARIH_BICIMI), bitis.strftime(TARIH_BICIMI)))
    return araliklar


def icinde_bulunulan_ay():
    bugun = date.today()
    bas = bugun.replace(day=1)
    bit = (bas + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return bas, bit


def sure_yaz(saniye):
    """75 -> '1 dk 15 sn', 4000 -> '1 sa 6 dk'."""
    saniye = int(max(0, saniye))
    sa, kalan = divmod(saniye, 3600)
    dk, sn = divmod(kalan, 60)
    if sa:
        return f"{sa} sa {dk} dk"
    if dk:
        return f"{dk} dk {sn} sn"
    return f"{sn} sn"


# --- sonuc kaydi -------------------------------------------------------------

def yeni_sonuc(firma, belge_tipi):
    """Bir firmanin bir ekranina ait bos sonuc kaydi.

    rapor.py ve eposta.py bu alanlari okur; yeni alan eklenirse burada
    varsayilani verilmeli ki eski kayitlarla da calissin.
    """
    return {"firma": firma, "belge_tipi": belge_tipi, "fatura_sayisi": 0,
            "durum": "", "dosyalar": [], "indirilemeyen": 0, "iptal_itiraz": 0,
            "tevkifat": 0, "donem": "", "not": "", "faturalar": [],
            "matrah": 0, "kdv": 0, "sure": 0, "klasor": "", "ekran_goruntusu": ""}


def ekran_tamamlanmis_mi(durum):
    """rapor.json'daki bir ekran durumu, o ekranin o gun bittigi anlamina mi geliyor.

    Bilgisayar/tarayici yarida kapanip calisma yeniden baslatildiginda, zaten
    tamamlanmis ekranlar tekrar acilmasin diye kullanilir. "hata: ..." ve
    "kaynaktan inmedi" gercek basarisizlik oldugu icin tamamlanmis sayilmaz;
    calisma yeniden baslayinca o ekranlar tekrar denenir.
    """
    if durum in ("tamam (excel eksik)", "tamam (iptal eksik)"):
        return False  # belgeler indi ama eksik kaldi: yeniden denenir
    return bool(durum) and (durum.startswith("tamam") or durum.startswith("atlandi")
                             or durum in ("fatura yok", "donem disi"))
