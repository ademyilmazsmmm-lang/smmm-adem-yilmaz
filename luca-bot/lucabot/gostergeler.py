# -*- coding: utf-8 -*-
"""Arayuzun alt kismindaki ozet kutulari (rapor.json'dan hesaplanir).

    Alis Tevkifat KDV      tevkifatli alis faturasi olan firmalar (KDV2)
    Alis SMM               e-SMM alis makbuzu olan firmalar
    Interaktif - e-Arsiv   iki ekranin fatura sayisi tutmayan firmalar
    KDV odemesi cikabilir  satis KDV - alis KDV - devreden KDV > 0 olan firmalar

Tutarlarda iptal/itiraz edilen faturalar yoktur; ayni faturayi gosteren
ekranlar bir kez sayilir (bkz. rapor.ALIS_BIRLESIMI / SATIS_BIRLESIMI).
"""

from . import rapor
from .firma_listesi import listede_bul


def hesapla(kayitlar, devreden=None, donem=None):
    """{"tevkifat": [...], "smm": [...], "fark": [...], "kdv": [...]} (her biri firma sozlukleri).

    devreden: firmalar.xlsx'ten {kisa ad: tutar}; donem verilirse yalnizca o donemin firmalari.
    """
    devreden = devreden or {}
    sonuc = {"tevkifat": [], "smm": [], "fark": [], "kdv": []}
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
            sonuc["fark"].append({"firma": firma,
                                  "interaktif": k["sayilar"].get("e-arsiv-interaktif") or 0,
                                  "earsiv": k["sayilar"].get("e-arsiv-alis") or 0,
                                  "fark": fark})

        satis = rapor._grup_toplami(k, "kdv", rapor.SATIS_EKRANLARI)
        alis = rapor._grup_toplami(k, "kdv", rapor.ALIS_EKRANLARI)
        liste_adi = listede_bul(firma, devreden)
        dev = devreden.get(liste_adi) if liste_adi else None
        odeme = round(satis - alis - (dev or 0), 2)
        if odeme > 0:
            sonuc["kdv"].append({"firma": firma, "satis": satis, "alis": alis,
                                 "devreden": dev, "odeme": odeme})
    return sonuc


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
    }


def tl(x):
    """1234.5 -> '1.234,50 TL'."""
    return f"{x:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") + " TL"
