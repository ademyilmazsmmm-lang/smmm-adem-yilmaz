# -*- coding: utf-8 -*-
"""Kullaniciya giden mesajlar: bolum basliklari, ilerleme, ekran sonuclari, son ozet.

Ayrintili teknik satirlar (hangi butona basildi vb.) gunluge ve ekrana
ortak.yaz ile yazilmaya devam eder; bu modul onlarin arasinda kullanicinin
bir bakista "nerede, ne durumda" oldugunu gormesini saglayan satirlari uretir.
"""

import time

from .ortak import sure_yaz, yaz
from .sabitler import BELGE_TIPLERI

CIZGI = "=" * 64
INCE_CIZGI = "-" * 64


def bolum(baslik, log=None):
    """Buyuk adim basligi: GIRIS, FIRMA LISTESI, ISLEM, RAPOR..."""
    yaz(f"\n{CIZGI}\n  {baslik}\n{CIZGI}", log)


def acilis(surum_notu, donem, belge_tipleri, klasor, gece_modu, log=None):
    bolum("LUCA BOT - e-Fatura / e-Arsiv toplu indirme", log)
    yaz(f"  Donem       : {donem}", log)
    yaz(f"  Ekranlar    : {', '.join(BELGE_TIPLERI.get(t, t) for t in belge_tipleri)}", log)
    yaz(f"  Kayit yeri  : {klasor}", log)
    yaz(f"  Calisma     : {'GECE MODU (bitince kendiliginden kapanir)' if gece_modu else 'normal'}", log)
    if surum_notu:
        yaz(f"  {surum_notu}", log)


class Ilerleme:
    """Firma sirasi ve tahmini kalan sure."""

    def __init__(self, toplam):
        self.toplam = toplam
        self.basla = time.time()
        self.biten = 0

    def firma_basladi(self, sira, firma, log=None):
        kalan = ""
        if self.biten:
            ortalama = (time.time() - self.basla) / self.biten
            kalan = f"  | tahmini kalan: {sure_yaz(ortalama * (self.toplam - sira + 1))}"
        yaz(f"\n{INCE_CIZGI}\n[{sira}/{self.toplam}] {firma}{kalan}", log)

    def firma_bitti(self):
        self.biten += 1

    def gecen(self):
        return time.time() - self.basla


def ekran_sonucu(sonuc, log=None):
    """Bir ekranin tek satirlik sonucu: '  [OK] e-Arşiv Alış: 12 fatura, 2 dosya (48 sn)'."""
    durum = sonuc.get("durum", "")
    ad = BELGE_TIPLERI.get(sonuc.get("belge_tipi"), sonuc.get("belge_tipi", ""))
    if durum == "tamam":
        etiket = "[OK]"
    elif durum in ("fatura yok", "donem disi") or durum.startswith("atlandi"):
        etiket = "[--]"
    else:
        etiket = "[!!]"
    parca = [f"{sonuc.get('fatura_sayisi') or 0} fatura"]
    if sonuc.get("dosyalar"):
        parca.append(f"{len(sonuc['dosyalar'])} dosya")
    if sonuc.get("tevkifat"):
        parca.append(f"{sonuc['tevkifat']} tevkifatli")
    if sonuc.get("iptal_itiraz"):
        parca.append(f"{sonuc['iptal_itiraz']} iptal/itiraz")
    sure = f", {sure_yaz(sonuc['sure'])}" if sonuc.get("sure") else ""
    ek = f" - {sonuc['not']}" if sonuc.get("not") else ""
    yaz(f"  {etiket} {ad}: {durum or '?'} ({', '.join(parca)}{sure}){ek}", log)


def son_ozet(ozet, log=None):
    """Calisma sonu kutusu. ozet: calisma.CalismaOzeti."""
    bolum("SONUC", log)
    yaz(f"  Islenen firma        : {ozet.firma}", log)
    yaz(f"  Islenen ekran        : {ozet.ekran}", log)
    yaz(f"    - fatura inen      : {ozet.basarili}", log)
    yaz(f"    - bos (fatura yok) : {ozet.bos}", log)
    yaz(f"    - atlanan          : {ozet.atlanan}", log)
    yaz(f"    - SORUNLU          : {ozet.sorunlu}", log)
    yaz(f"  Listelenen fatura    : {ozet.fatura}", log)
    if ozet.tevkifat:
        yaz(f"  Tevkifatli alis      : {ozet.tevkifat}  (KDV2 kontrol edin)", log)
    if ozet.iptal:
        yaz(f"  Iptal/itiraz         : {ozet.iptal}", log)
    yaz(f"  Toplam sure          : {sure_yaz(ozet.sure)}", log)
    if ozet.sorunlu_liste:
        yaz(f"\n  Sorunlu ekranlar ({len(ozet.sorunlu_liste)}):", log)
        for satir in ozet.sorunlu_liste[:15]:
            yaz(f"    - {satir}", log)
        if len(ozet.sorunlu_liste) > 15:
            yaz(f"    ... (+{len(ozet.sorunlu_liste) - 15}, hepsi rapor.xlsx 'Hatalar' sayfasinda)", log)
    yaz(INCE_CIZGI, log)
