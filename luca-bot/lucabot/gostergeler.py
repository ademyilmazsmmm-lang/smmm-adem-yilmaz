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


def kdv_sonucu(k, firma, devreden):
    """Firmanin KDV durumu: satis KDV - alis KDV - onceki donemden devreden KDV.

    fark > 0: odenecek KDV; fark < 0: sonraki doneme devreden KDV. onceki: firmalar.xlsx'te girilmemisse None
    (hesapta 0 sayilir). veri: satis ya da alis KDV'si hic okunmamissa False (sonuc anlamsiz)."""
    satis = rapor._grup_toplami(k, "kdv", rapor.SATIS_EKRANLARI)
    alis = rapor._grup_toplami(k, "kdv", rapor.ALIS_EKRANLARI)
    liste_adi = listede_bul(firma, devreden)
    onceki = devreden.get(liste_adi) if liste_adi else None
    fark = round(satis - alis - (onceki or 0), 2)
    return {"satis": satis, "alis": alis, "onceki": onceki, "fark": fark, "veri": bool(satis or alis),
            "odenecek": max(fark, 0), "devreden": max(-fark, 0)}


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
            sonuc["fark"].append({"firma": firma,
                                  "interaktif": k["sayilar"].get("e-arsiv-interaktif") or 0,
                                  "earsiv": k["sayilar"].get("e-arsiv-alis") or 0,
                                  "fark": fark, "eslesmedi": eslesmedi,
                                  "eksik": [] if eslesmedi else eksik, "fazla": [] if eslesmedi else fazla})

        for h in rapor.yeniden_denenecek(k):
            sonuc["hata"].append({"firma": firma, **h})

        kdv = kdv_sonucu(k, firma, devreden)
        if kdv["odenecek"] > 0:
            sonuc["kdv"].append({"firma": firma, "satis": kdv["satis"], "alis": kdv["alis"],
                                 "devreden": kdv["onceki"], "odeme": kdv["odenecek"]})
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
        "hata": len(g["hata"]),
    }


kisa_fatura_no = rapor.kisa_fatura_no  # arayuz ve rapor ayni gosterimi kullanir


def tl(x):
    """1234.5 -> '1.234,50 TL'."""
    return f"{x:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") + " TL"
