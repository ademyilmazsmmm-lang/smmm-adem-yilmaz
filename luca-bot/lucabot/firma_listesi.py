# -*- coding: utf-8 -*-
"""Hangi firmalarin, hangi ekranlarinin isleneceginin belirlenmesi.

Kaynaklar: Luca'daki firma listesi, --firma secenegi, ayarlar.json'daki
atlanacak_firmalar, firmalar.xlsx (kapanis tarihi + X ile isaretlenen
ekranlar) ve ayni gun yarida kalan calismanin (surekli) rapor.json'u.
"""

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .fatura_analiz import excelden_tablo, sutun_indeksi, sutun_tam_indeksi
from .ortak import KOK, ekran_tamamlanmis_mi, karsilastir, sadelestir, tarih_cozumle, yaz
from .sabitler import ATLA_DEGERLERI, EKRAN_SUTUNLARI


@dataclass
class FirmaSecimi:
    """Suzme sonucu: islenecek firmalar ve her firmada atlanacak ekranlar."""
    firmalar: list
    atlanan_ekranlar: dict = field(default_factory=dict)  # firma -> {belge tipi}
    bos_sebep: str = ""  # hic firma kalmadiysa neden


def firma_listesini_oku(yol, log=None):
    """Islenecek firmalar: {kisa ad: (kapanis tarihi, atlanacak ekranlar)}.

    Excel'de "Kısa Adı" ve "Kapanış Tarihi" sutunlari aranir. Kisa ad Luca'nin
    firma listesinde gorunen adla ayni oldugu icin eslestirme dogrudan yapilir.
    Ekran sutunlarina X yazilan belge tipleri o firmada hic acilmaz (orn.
    e-faturasi olmayan firmada e-Fatura Alis/Satis).
    """
    yol = Path(yol)
    if not yol.is_absolute():
        yol = KOK / yol
    if not yol.exists():
        yaz(f"UYARI: firma listesi bulunamadi: {yol}", log)
        return {}
    # yalnizca ilk sayfa: dosyadaki aciklama sayfasi firma sanilmasin
    # yalnizca adi yazili (diger sutunlari bos) firma satirlari da gecerli
    basliklar, satirlar = excelden_tablo(yol, log, sadece_ilk=True, satir_en_az=1)
    if not satirlar:
        yaz(f"UYARI: firma listesi okunamadi: {yol}", log)
        return {}
    ad_i = sutun_indeksi(basliklar, "KISA AD")
    kapanis_i = sutun_indeksi(basliklar, "KAPANIS")
    if ad_i is None:
        ad_i = 0
    ekran_i = {}
    for baslik, tip in EKRAN_SUTUNLARI.items():
        i = sutun_tam_indeksi(basliklar, baslik)
        if i is not None:
            ekran_i[tip] = i
    liste = {}
    for satir in satirlar:
        ad = satir[ad_i].strip() if ad_i < len(satir) else ""
        if not ad:
            continue
        kapanis = None
        if kapanis_i is not None and kapanis_i < len(satir):
            try:
                kapanis = tarih_cozumle(satir[kapanis_i])
            except Exception:
                kapanis = None
        atlanan = {tip for tip, i in ekran_i.items()
                   if i < len(satir) and sadelestir(satir[i]) in ATLA_DEGERLERI}
        liste[ad] = (kapanis, atlanan)
    return liste


def listede_bul(ad, liste):
    """Luca adi listedeki hangi kisa ada denk geliyor (kisaltilmis adlar icin).

    Once birebir eslesme aranir; yoksa bas kismi tutanlardan EN UZUN olani
    secilir. Aksi halde "ADEM", "ADEM MERGE" firmasiyla da esleserek yanlis
    firmanin ayarlarini uyguluyordu.
    """
    k = karsilastir(ad)
    if not k:
        return None
    en_iyi, en_uzun = None, -1
    for liste_adi in liste:
        a = karsilastir(liste_adi)
        if not a:
            continue
        if a == k:
            return liste_adi
        # Luca adlari kisaltarak gosterdigi icin listedeki daha uzun ad da tutar.
        # Ters yon ("ADEM" listedeki ad, Luca'da "ADEM AKÇAY") ancak yeterince
        # uzun adlarda kabul edilir; kisa adlar baska firmalara yapisiyordu.
        if (a.startswith(k) or (len(a) >= 8 and k.startswith(a))) and len(a) > en_uzun:
            en_iyi, en_uzun = liste_adi, len(a)
    return en_iyi


def _ayni_firma(ad, atlanan):
    # Luca adlari kisaltarak gosterdigi icin bas kismi tutan ad da atlanir
    k, a = karsilastir(ad), karsilastir(atlanan)
    return bool(k) and bool(a) and (k.startswith(a) or a.startswith(k))


def firmalari_suz(luca_firmalari, ayarlar, aranan=None, limit=None, baslangic=None, log=None):
    """Luca'daki firma listesinden bu calismada islenecekleri secer.

    aranan: --firma ile verilen ad parcalari (bos ise hepsi).
    baslangic: donem baslangici; bundan once kapanmis firmalar atlanir.
    """
    firmalar = list(luca_firmalari)

    if aranan:
        parcalar = [(p.strip(), karsilastir(p)) for deger in aranan for p in deger.split(",") if p.strip()]
        bulunamayan = [ham for ham, a in parcalar if not any(a in karsilastir(f) for f in firmalar)]
        if bulunamayan:
            yaz(f"Eslesmeyen arama: {', '.join(bulunamayan)}", log)
        firmalar = [f for f in firmalar if any(a in karsilastir(f) for _, a in parcalar)]
        if not firmalar:
            return FirmaSecimi([], bos_sebep=f"'{', '.join(aranan)}' ile eslesen firma yok")
        yaz(f"Eslesen firma(lar): {', '.join(firmalar)}", log)

    atlama_adlari = [a for a in ayarlar.get("atlanacak_firmalar", []) if str(a).strip()]
    if atlama_adlari:
        atlananlar = [f for f in firmalar if any(_ayni_firma(f, a) for a in atlama_adlari)]
        firmalar = [f for f in firmalar if f not in atlananlar]
        if atlananlar:
            yaz(f"Atlanan firma ({len(atlananlar)}): {', '.join(atlananlar)}", log)
        # --firma ile calisirken zaten tek firma var; eslesmeyen adlar dogal
        if not aranan:
            eslesmeyen = [a for a in atlama_adlari if not any(_ayni_firma(f, a) for f in atlananlar)]
            if eslesmeyen:
                yaz(f"UYARI: atlama listesinde eslesmeyen ad: {', '.join(eslesmeyen)}", log)

    atlanan_ekranlar = {}
    liste_yolu = ayarlar.get("firma_listesi")
    if liste_yolu:
        izinli = firma_listesini_oku(liste_yolu, log)
        if izinli:
            yaz(f"Firma listesi: {liste_yolu} ({len(izinli)} firma)", log)
            kalanlar, disarida, kapanmis = [], [], []
            for f in firmalar:
                liste_adi = listede_bul(f, izinli)
                if liste_adi is None:
                    disarida.append(f)
                    continue
                kapanis, ekranlar = izinli[liste_adi]
                # donem baslamadan kapanmis firmada aranacak fatura yok
                if kapanis is not None and baslangic is not None and kapanis < baslangic:
                    kapanmis.append(f"{f} ({kapanis:%d/%m/%Y})")
                    continue
                kalanlar.append(f)
                if ekranlar:
                    atlanan_ekranlar[f] = ekranlar
            firmalar = kalanlar
            if disarida:
                yaz(f"Listede olmayan {len(disarida)} firma atlandi", log)
            if kapanmis:
                yaz(f"Donem oncesi kapanan {len(kapanmis)} firma atlandi: "
                    + ", ".join(kapanmis[:12])
                    + (f" ... (+{len(kapanmis) - 12})" if len(kapanmis) > 12 else ""), log)
            if atlanan_ekranlar:
                toplam = sum(len(v) for v in atlanan_ekranlar.values())
                yaz(f"Listede {len(atlanan_ekranlar)} firmada {toplam} ekran"
                    " isaretlenmis, o ekranlar acilmayacak", log)

    if limit:
        firmalar = firmalar[:limit]
    return FirmaSecimi(firmalar, atlanan_ekranlar,
                       "" if firmalar else "suzmeden sonra islenecek firma kalmadi")


def bugun_tamamlananlar(rapor_klasoru, belge_tipleri):
    """Ayni gun daha once tamamlanmis ekranlar: {firma: {belge tipi}}.

    Calisma yarida kesilip (bilgisayar kapanmasi, elektrik vb.) ayni gun
    yeniden baslatilirsa bunlar tekrar acilmaz. Rapor artik surekli (gunluk
    degil) tutuldugu icin yalnizca durum degil, o ekranin BUGUN guncellenmis
    olmasi da aranir; yoksa gecen ay tamamlanmis bir ekran sonsuza kadar
    "bugun de tamam" sanilip bir daha hic acilmazdi.
    """
    yol = Path(rapor_klasoru) / "rapor.json"
    if not yol.exists():
        return {}
    try:
        onceki = json.loads(yol.read_text(encoding="utf-8"))
    except Exception:
        return {}
    bugun = date.today().strftime("%d/%m/%Y")
    tamam = {}
    for firma, kayit in onceki.items():
        if not isinstance(kayit, dict):
            continue
        durumlar = kayit.get("durumlar", {})
        guncellenme = kayit.get("guncellenme", {})
        tipler = {tip for tip in belge_tipleri
                 if ekran_tamamlanmis_mi(durumlar.get(tip, ""))
                 and guncellenme.get(tip, "").startswith(bugun)}
        if tipler:
            tamam[firma] = tipler
    return tamam
