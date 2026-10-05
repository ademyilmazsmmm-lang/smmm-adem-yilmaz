# -*- coding: utf-8 -*-
"""Kar/zarar sonucu (kar-zarar/cikti/kar-zarar.json) + indirilen faturalar (rapor.json).

Luca/Defter Beyan'daki kar/zarar yalnizca islenmis donemi (orn. 1-8. ay) kapsar. O
doneme ait olmayan ama indirilmis faturalar (orn. Eylul) varsa, bunlarin matrahi
(KDV haric satis - alis) kara eklenip "faturalar dahil" tahmini ayrica gosterilir.
Faturalardan mal alisi ile gider ayrilamadigi icin alis tek kalem sayilir; maas,
amortisman gibi yevmiyeyle girilen kalemler faturada olmaz: sonuc bir TAHMINDIR.
"""

import json
import re

from . import rapor
from .ortak import sadelestir, tarih_cozumle

TARIH_DESENI = re.compile(r"\d{1,2}/\d{1,2}/\d{4}")


def donem_coz(metin):
    """'01/09/2026-30/09/2026' -> (bas, bit); bicim bozuksa None."""
    tarihler = TARIH_DESENI.findall(metin or "")
    if len(tarihler) != 2:
        return None
    try:
        return tuple(tarih_cozumle(t) for t in tarihler)
    except ValueError:
        return None


def sonuclari_oku(yol):
    """(donem metni, [firma sonuclari]); dosya yoksa/bozuksa ValueError."""
    try:
        with open(yol, encoding="utf-8") as f:
            veri = json.load(f)
        return veri["donem"], list(veri["firmalar"])
    except (OSError, KeyError, TypeError, ValueError) as e:
        raise ValueError(f"{getattr(yol, 'name', yol)} okunamadi") from e


def _eksik_ekran(kayit):
    return any(not str(d).startswith("tamam") for d in (kayit.get("durumlar") or {}).values())


def fatura_ozeti(kayit, bit):
    """Firmanin indirilmis faturalari kar/zarar donemi sonrasina aitse
    {"donem", "satis", "alis", "fark", "not"}, degilse {"not": neden}."""
    if not kayit:
        return {"not": "fatura indirilmemiş"}
    kayit = rapor._tamamla(dict(kayit))
    aralik = donem_coz(kayit.get("donem"))
    if aralik is None:
        return {"not": "fatura dönemi bilinmiyor"}
    if aralik[0] <= bit:
        return {"donem": kayit["donem"],
                "not": f"faturalar {kayit['donem']} dönemine ait; kâr/zarar dönemiyle çakışıyor"}
    k = rapor.fatura_kari(kayit)
    not_ = "bazı ekranlar eksik/inmedi" if _eksik_ekran(kayit) else ""
    return {"donem": kayit["donem"], "satis": k["satis"], "alis": k["alis"], "fark": k["fark"],
            "not": not_}


def satirlar(sonuclar, kayitlar, bit):
    """Her firma icin sonuc + fatura ozeti; kardan zarara siralidir (hatalilar sonda).

    Eklenen alanlar: fatura_donem, fatura_satis, fatura_alis, kar_dahil, fatura_not.
    """
    harita = {sadelestir(f): k for f, k in (kayitlar or {}).items()}
    cikti = []
    for s in sonuclar:
        oz = fatura_ozeti(harita.get(sadelestir(s.get("firma"))), bit)
        satir = dict(s)
        satir["fatura_donem"] = oz.get("donem", "")
        satir["fatura_satis"] = oz.get("satis")
        satir["fatura_alis"] = oz.get("alis")
        satir["fatura_not"] = oz.get("not", "")
        kar = s.get("kar")
        satir["kar_dahil"] = (round(kar + oz["fark"], 2)
                              if kar is not None and oz.get("fark") is not None else None)
        cikti.append(satir)
    cikti.sort(key=lambda x: (x.get("kar") is None, -(x.get("kar") or 0)))
    return cikti


def ozet_cumlesi(satir):
    """'1-8. ay kâr 100.000 TL; Eylül faturaları dahil edilince 120.000 TL kâr' gibi tek satir."""
    kar, dahil = satir.get("kar"), satir.get("kar_dahil")
    if kar is None:
        return satir.get("hata") or ""

    def tl(x):
        return f"{abs(x):,.0f}".replace(",", ".") + " TL " + ("kâr" if x >= 0 else "zarar")

    metin = tl(kar)
    if dahil is not None:
        metin += f"; {satir['fatura_donem']} faturaları dahil edilince {tl(dahil)}"
    return metin

