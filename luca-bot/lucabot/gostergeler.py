# -*- coding: utf-8 -*-
"""Arayuzun alt kismindaki ozet kutulari (rapor.json'dan hesaplanir).

    Alis Tevkifat KDV      tevkifatli alis faturasi olan firmalar (KDV2)
    Alis SMM               e-SMM alis makbuzu olan firmalar
    Interaktif - e-Arsiv   iki ekranin fatura sayisi tutmayan firmalar
    KDV odemesi cikabilir  satis KDV - alis KDV - devreden KDV > 0 olan firmalar (KDV2 haric; KDV2 dahil
                           sonuc ayri sutunda: bkz. kdv_sonucu)

Tutarlarda iptal/itiraz edilen faturalar yoktur; ayni faturayi gosteren
ekranlar bir kez sayilir (bkz. rapor.ALIS_BIRLESIMI / SATIS_BIRLESIMI).
"""

import re

from . import rapor
from .firma_listesi import listede_bul


def kdv_sonucu(k, firma, devreden):
    """Firmanin KDV durumu, tevkif edilen KDV'nin (KDV2) iki ayri sekilde sayildigi iki sonucla.

    Excel'deki KDV sutunu faturadaki TAM KDV kabul edilir (tevkifatli faturada 100 TL). Bunun tevkif edilen
    kismi (orn. 30 TL) KDV2'dir; satici yalniz kalan 70 TL'yi tahsil eder.
      alis        KDV2 haric alis KDV: hemen indirilen kisim (70)
      kdv2        tevkif edilen KDV: ayri sutun (30); odendiginde indirim konusu olur, odenip odenmeyecegi bilinemez
      alis_tam    alis + kdv2 (Excel'deki toplam alis KDV)
      fark/odenecek/devreden                KDV2 HARIC:  satis - alis - onceki
      fark_kdv2/odenecek_kdv2/devreden_kdv2 KDV2 DAHIL:  satis - alis_tam - onceki
    fark > 0 odenecek KDV, fark < 0 sonraki doneme devreden KDV. onceki: firmalar.xlsx'te girilmemisse None
    (hesapta 0 sayilir). veri: satis ya da alis KDV'si hic okunmamissa False (sonuc anlamsiz)."""
    satis = rapor._grup_toplami(k, "kdv", rapor.SATIS_EKRANLARI)
    alis_tam = rapor._grup_toplami(k, "kdv", rapor.ALIS_EKRANLARI)
    kdv2 = round(max(rapor.tevkifat_kdv(k) or 0, 0), 2)
    kdv2_dusulen = min(kdv2, alis_tam) if alis_tam > 0 else 0   # alis KDV'sinden fazla olamaz
    alis = round(alis_tam - kdv2_dusulen, 2)
    liste_adi = listede_bul(firma, devreden)
    onceki = devreden.get(liste_adi) if liste_adi else None
    fark = round(satis - alis - (onceki or 0), 2)
    fark_kdv2 = round(satis - alis_tam - (onceki or 0), 2)
    return {"satis": satis, "alis": alis, "alis_tam": alis_tam, "kdv2": kdv2,
            "kdv2_tahmini": bool(kdv2) and any((k.get("tevkifat_kdv_tahmini") or {}).get(t)
                                               for t in rapor.TEVKIFAT_EKRANLARI),
            "kdv2_tutarsiz": kdv2 > alis_tam + 0.01,
            "onceki": onceki, "veri": bool(satis or alis_tam),
            "fark": fark, "odenecek": max(fark, 0), "devreden": max(-fark, 0),
            "fark_kdv2": fark_kdv2, "odenecek_kdv2": max(fark_kdv2, 0), "devreden_kdv2": max(-fark_kdv2, 0)}


def hesapla(kayitlar, devreden=None, donem=None):
    """{"tevkifat": [...], "smm": [...], "fark": [...], "kdv": [...]} (her biri firma sozlukleri).

    devreden: firmalar.xlsx'ten {kisa ad: tutar}; donem verilirse yalnizca o donemin firmalari.
    """
    devreden = devreden or {}
    sonuc = {"tevkifat": [], "smm": [], "fark": [], "kdv": [], "hata": []}
    for firma in sorted(kayitlar):
        k = rapor._tamamla(dict(kayitlar[firma]))
        if donem and k.get("donem") != donem:
            continue

        adet = rapor.tevkifat_adedi(k)
        if adet:
            sonuc["tevkifat"].append({
                "firma": firma, "adet": adet, "tutar": rapor.tevkifat_kdv(k),
                "tahmini": any(k["tevkifat_kdv_tahmini"].get(t) for t in rapor.TEVKIFAT_EKRANLARI)})

        smm_adet = k["sayilar"].get("esmm-alis") or 0
        if smm_adet:
            sonuc["smm"].append({"firma": firma, "adet": smm_adet,
                                 "tutar": k["matrah"].get("esmm-alis") or 0})

        fark = rapor._fark(k)
        if isinstance(fark, int) and fark and not rapor._okunamadi(k):
            eksik, fazla = rapor.fatura_farklari(k)
            eksik, fazla = eksik or [], fazla or []
            # hicbir numara tutmuyorsa listeler farkli numaralanmis: tek tek gosterilemez
            eslesmedi = bool(eksik and fazla and not rapor._ortak_fatura_var(k))
            ham = k.get("faturalar") or {}
            sonuc["fark"].append({"firma": firma,
                                  "interaktif": k["sayilar"].get("e-arsiv-interaktif") or 0,
                                  "earsiv": k["sayilar"].get("e-arsiv-alis") or 0,
                                  "fark": fark, "eslesmedi": eslesmedi,
                                  "eksik": [] if eslesmedi else eksik, "fazla": [] if eslesmedi else fazla,
                                  # numaralar tutmadiginda elle karsilastirmak icin iki listenin tamami
                                  "interaktif_liste": ham.get("e-arsiv-interaktif") or [],
                                  "earsiv_liste": ham.get("e-arsiv-alis") or []})

        for h in rapor.yeniden_denenecek(k):
            sonuc["hata"].append({"firma": firma, **h})

        kdv = kdv_sonucu(k, firma, devreden)
        if kdv["odenecek"] > 0:   # KDV2 haric hesapta odeme cikiyorsa (KDV2 dahil hesap daha dusuk olabilir)
            sonuc["kdv"].append({"firma": firma, "satis": kdv["satis"], "alis": kdv["alis"], "kdv2": kdv["kdv2"],
                                 "devreden": kdv["onceki"], "odeme": kdv["odenecek"],
                                 "odeme_kdv2": kdv["odenecek_kdv2"]})
    return sonuc


EKSIK, FAZLA = "e-Arşiv'de eksik", "e-Arşiv'de fazla"
ESLESMEDI, BELIRSIZ = "Eşleşmedi (numaralar tutmuyor)", "Hangi fatura belirlenemedi"
INTERAKTIF, EARSIV = "İnteraktif V.D.", "e-Arşiv Alış"


def fark_satirlari(fark):
    """hesapla()["fark"] -> duz fatura listesi: [{firma, durum, kaynak, unvan, no, tutar}] (tutar bilinmiyorsa None).

    Yalniz Interaktif'te olup e-Arsiv'de olmayan (eksik) faturalar; tersi (fazla) yazilmaz. Iki listenin numaralari hic tutmuyorsa
    (eslesmedi) Interaktif listesinin tamami yazilir; sayi farki var ama fatura belirlenemiyorsa firma tek satirla gelir."""
    def satir(firma, durum, kaynak, f):
        tutar = f[2] if len(f) > 2 and f[2] not in (None, "") else None
        return {"firma": firma, "durum": durum, "kaynak": kaynak, "unvan": f[0] if f else "",
                "no": f[1] if len(f) > 1 else "", "tutar": tutar}
    sonuc = []
    for x in fark:
        f = x["firma"]
        if x["eslesmedi"]:
            sonuc += [satir(f, ESLESMEDI, INTERAKTIF, y) for y in x.get("interaktif_liste") or []]
        else:
            sonuc += [satir(f, EKSIK, INTERAKTIF, y) for y in x["eksik"]]
            # "e-Arsiv'de var, Interaktif'te yok" (fazla) taraf raporlanmaz: yalniz Interaktif'te olup e-Arsiv'de olmayanlar
        if not any(r["firma"] == f for r in sonuc) and not x["fazla"]:
            sonuc.append({"firma": f, "durum": BELIRSIZ, "kaynak": "", "unvan": "", "no": "", "tutar": None})
    return sonuc


def tutar_girisi(metin):
    """Kullanicinin yazdigi tutar: '1000', '1.000', '1.000,50', '1000 TL' -> float (okunamazsa 0)."""
    m = re.sub(r"(?i)\s|tl", "", str(metin or ""))
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", m):  # Turkce binlik noktasi
        m = m.replace(".", "").replace(",", ".")
    else:
        m = m.replace(",", ".")
    try:
        return max(float(m), 0.0)
    except ValueError:
        return 0.0


def esik_uygula(satirlar, esik):
    """Tutari esikten kucuk olan faturalari eler (tutari bilinmeyenler kalir: sessizce kaybolmasin)."""
    if not esik:
        return list(satirlar)
    return [r for r in satirlar if r["tutar"] is None or r["tutar"] >= esik]


def toplamlar(g):
    """Kutularda gosterilecek degerler."""
    return {
        "tevkifat": sum(x["tutar"] for x in g["tevkifat"]),
        "tevkifat_adet": sum(x["adet"] for x in g["tevkifat"]),
        "smm": sum(x["tutar"] for x in g["smm"]),
        "smm_adet": sum(x["adet"] for x in g["smm"]),
        "fark": sum(abs(x["fark"]) for x in g["fark"]),
        "kdv_firma": len(g["kdv"]),
        "kdv": sum(x["odeme"] for x in g["kdv"]),
        "hata": len(g["hata"]),
    }


kisa_fatura_no = rapor.kisa_fatura_no  # arayuz ve rapor ayni gosterimi kullanir


def tl(x):
    """1234.5 -> '1.234,50 TL'."""
    return f"{x:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") + " TL"
