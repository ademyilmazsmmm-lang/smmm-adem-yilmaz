# -*- coding: utf-8 -*-
"""Birden fazla Luca hesabi: ofis (ayarlar.json'daki ana giris bilgileri) + isletme (ayarlar.json "ikinci_hesap").

    "ikinci_hesap": {"etkin": true, "ad": "isletme", "uye_no": "...", "kullanici_adi": "...", "parola": "...",
                     "dogrulama_anahtari": "..."}

Fatura Indirme etkin ise her calismada once ofis, sonra isletme hesabini sirayla tarar. Her hesap kendi tarayici profilini
kullanir (oturumlar birbirine karismaz); ilk hesabin profili eskisi gibi kalir, boylece mevcut giris bozulmaz.
Rapor ortaktir (firma adina gore birlesir).
"""

import json
from pathlib import Path

ILK_AD = "ofis"
IKINCI_AD = "isletme"
KIMLIK_ANAHTARLARI = ("uye_no", "kullanici_adi", "parola", "dogrulama_anahtari")
SECIMLER = ("hepsi", "ofis", "isletme")


def _sade(metin):
    m = str(metin or "").strip().replace("İ", "i").replace("I", "ı").lower()
    return m.translate(str.maketrans("ışğüöç", "isguoc"))


def ikinci_hesap(ayarlar):
    """Etkin ve giris bilgileri tam ikinci hesap (sozluk) ya da None."""
    h = ayarlar.get("ikinci_hesap")
    if not isinstance(h, dict) or not h.get("etkin"):
        return None
    if not all(str(h.get(a) or "").strip() for a in ("uye_no", "kullanici_adi")) or not str(h.get("parola") or ""):
        return None
    return h


def ikinci_hesap_eksik_mi(ayarlar):
    """Etkin isaretli ama bilgileri eksik mi (kullaniciya uyari icin)."""
    h = ayarlar.get("ikinci_hesap")
    return isinstance(h, dict) and bool(h.get("etkin")) and ikinci_hesap(ayarlar) is None


def ikinci_ad(ayarlar):
    h = ayarlar.get("ikinci_hesap") or {}
    return _sade(h.get("ad")) or IKINCI_AD if isinstance(h, dict) else IKINCI_AD


def hesaplar(ayarlar, secim="hepsi"):
    """[(hesap adi, o hesaba gore ayar sozlugu)]. secim: 'hepsi' / 'ofis' / ikinci hesabin adi.

    Ayar sozlugu ana ayarlarin kopyasidir; yalniz giris bilgileri (uye no, kullanici, parola, dogrulama anahtari) hesabindir.
    Etkin ikinci hesap yoksa yalniz ofis doner; ikinci hesap istenip bulunamazsa ValueError."""
    secim = _sade(secim) or "hepsi"
    ilk = dict(ayarlar, hesap_adi=ILK_AD)
    liste = [(ILK_AD, ilk)]
    h = ikinci_hesap(ayarlar)
    if h is not None:
        ayar2 = dict(ayarlar, hesap_adi=ikinci_ad(ayarlar))
        for a in KIMLIK_ANAHTARLARI:
            ayar2[a] = h.get(a) or ""
        liste.append((ikinci_ad(ayarlar), ayar2))
    if secim == "hepsi":
        return liste
    secilen = [x for x in liste if x[0] == secim]
    if secilen:
        return secilen
    if secim in (IKINCI_AD, "isletme") or (len(liste) == 1 and secim != ILK_AD):
        raise ValueError("İşletme hesabı istendi ama ikinci Luca hesabı kapalı ya da bilgileri eksik "
                         "(Luca Giriş Bilgileri > İkinci hesap).")
    raise ValueError(f"Bilinmeyen hesap: {secim}")


def profil_eki(sira):
    """Ilk hesap eski profili kullanir (ek yok); sonrakiler 'hesap2' gibi eki alir."""
    return "" if sira == 0 else f"hesap{sira + 1}"


# --- gorunen adlar -----------------------------------------------------------------------------------------------
# Hesap anahtarlari ("ofis", "isletme") dahili; ekranda/gunlukte/raporda hesabin SAHIBININ adi gosterilir. Adlar kisisel oldugu icin
# depoda degil, program klasorundeki hesap-adlari.json'dadir (git'e girmez): {"ofis": "Ad Soyad", "isletme": "Ad Soyad"}.
ADLAR_DOSYASI = "hesap-adlari.json"
VARSAYILAN_ADLAR = {"ofis": "Ofis", "isletme": "İşletme"}


def _adlar_dosyasi():
    taban = Path(__file__).resolve().parent.parent
    for klasor in (taban, taban.parent / "luca-bot", taban.parent / "kar-zarar"):
        yol = klasor / ADLAR_DOSYASI
        if yol.exists():
            return yol
    return None


def adlari_oku():
    """{"ofis": ..., "isletme": ...}: dosyadaki adlar, eksikler varsayilanla tamamlanir."""
    adlar = dict(VARSAYILAN_ADLAR)
    yol = _adlar_dosyasi()
    if yol:
        try:
            for k, v in json.loads(yol.read_text(encoding="utf-8-sig")).items():
                if isinstance(v, str) and v.strip() and _sade(k) in ("ofis", "isletme"):
                    adlar[_sade(k)] = v.strip()
        except (OSError, ValueError, AttributeError):
            pass
    return adlar


def gorunen_ad(hesap_adi):
    """'ofis' -> 'Adem Yılmaz' (dosyadan); bilinmeyen hesap adi oldugu gibi doner."""
    anahtar = _sade(hesap_adi)
    anahtar = "isletme" if anahtar not in ("ofis",) and anahtar else anahtar
    return adlari_oku().get(anahtar, str(hesap_adi))
