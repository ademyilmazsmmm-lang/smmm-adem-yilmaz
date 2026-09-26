# -*- coding: utf-8 -*-
"""FATURA INDIRME: arac cubugundaki indirme butonlari (Seçilenleri İndir, Excel).

Iki yol vardir (ayarlar.json: indirmeyi_yakala):

  * yakalama (varsayilan): tarayicinin indirme mekanizmasi hic devreye
    girmez. Chrome bu makinede indirmeyi kaydettigi anda cokuyordu
    (AddKeepAlive kDownloadInProgress). Istek yakalanir, dosya govdesi
    Python tarafinda alinip diske yazilir.
  * tarayici indirmesi: klasik yol. Yakalama modunda da yedek olarak
    dinlenir; istek yakalanamazsa tarayicinin indirdigi dosya kaydedilir.
"""

import re
import time

from .bekleme import kosulu_bekle, sayfa_canli
from .luca_ekran import (acik_pencereleri_kapat, diyalogda_tikla,
                         diyalogda_tumunu_sec, dugmeye_bas,
                         fatura_yok_penceresini_kapat, indirme_diyalogu,
                         uyari_metinleri, uyari_metni)
from .ortak import AYAR, dosya_adi_yap, yaz
from .sabitler import INDIRME_ONAY, KISAYOLLAR

CD_DESENI = re.compile(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', re.I)
INDIRME_TURLERI = ("application/zip", "application/octet-stream", "application/x-zip",
                   "application/vnd.ms-excel", "application/vnd.openxmlformats",
                   "application/force-download", "application/download")
UZANTILAR = [("zip", ".zip"), ("spreadsheetml", ".xlsx"), ("ms-excel", ".xls"),
             ("csv", ".csv"), ("pdf", ".pdf"), ("xml", ".xml")]


def yanit_dosya_mi(basliklar):
    """Sunucu yaniti indirilecek bir dosya mi (ekran yerine dosya)."""
    cd = (basliklar.get("content-disposition") or "").lower()
    ct = (basliklar.get("content-type") or "").lower()
    return "attachment" in cd or any(t in ct for t in INDIRME_TURLERI)


def yanit_dosya_adi(basliklar, yedek_ad):
    """Dosya adi once Content-Disposition'dan, yoksa icerik turunden uretilir."""
    eslesme = CD_DESENI.search(basliklar.get("content-disposition") or "")
    if eslesme and eslesme.group(1).strip():
        return dosya_adi_yap(eslesme.group(1).strip())
    ct = (basliklar.get("content-type") or "").lower()
    uzanti = next((u for anahtar, u in UZANTILAR if anahtar in ct), ".dat")
    return f"{yedek_ad}{uzanti}"


class _DosyaYakalayici:
    """Indirme istegini yakalar (route) ve tarayici indirmesini yedek olarak dinler."""

    def __init__(self, page, on_ek, yakala):
        self.page = page
        self.ctx = page.context
        self.on_ek = on_ek
        self.yakala = yakala
        self.alinan = {}
        self.inenler = []
        self.suren = 0  # yaniti henuz gelmemis istek sayisi (Luca dosyayi hazirliyor olabilir)

    def suren_istek_var(self):
        return self.suren > 0

    def yeni_sekme_acildi(self):
        try:
            return any(p not in self.onceki_sekmeler for p in self.ctx.pages)
        except Exception:
            return False

    # route: her istek once buradan gecer
    def _yonlendir(self, route):
        self.suren += 1
        try:
            self._yonlendir_ic(route)
        finally:
            self.suren -= 1

    def _yonlendir_ic(self, route):
        try:
            yanit = route.fetch(timeout=0)  # buyuk Excel'ler dakikalarca surebiliyor
        except Exception:
            try:
                route.continue_()
            except Exception:
                pass
            return
        try:
            basliklar = {k.lower(): v for k, v in (yanit.headers or {}).items()}
            if not self.alinan and yanit_dosya_mi(basliklar):
                self.alinan["ad"] = yanit_dosya_adi(basliklar, self.on_ek)
                self.alinan["govde"] = yanit.body()
                # abort edilirse Luca'nin cercevesi "sayfa kullanilamiyor"
                # hatasina dusup ekrani bozuyordu; 204 ile tarayici bulundugu
                # sayfada kalir, indirme de baslamaz
                try:
                    route.fulfill(status=204, body="")
                except Exception:
                    route.abort()
                return
            route.fulfill(response=yanit)
        except Exception:
            try:
                route.continue_()
            except Exception:
                pass

    def _indirme_geldi(self, indirme):
        self.inenler.append(indirme)

    def __enter__(self):
        try:
            self.onceki_sekmeler = set(self.ctx.pages)
        except Exception:
            self.onceki_sekmeler = None
        self.page.on("download", self._indirme_geldi)
        if self.yakala:
            self.ctx.route("**/*", self._yonlendir)
        return self

    def __exit__(self, *hata):
        if self.yakala:
            try:
                self.ctx.unroute("**/*", self._yonlendir)
            except Exception:
                pass
        try:
            self.page.remove_listener("download", self._indirme_geldi)
        except Exception:
            pass
        self._yeni_sekmeleri_kapat()
        return False

    def _yeni_sekmeleri_kapat(self):
        """Indirme icin acilan bos Chrome sekmelerini kapatir.

        Luca'nin Excel butonu dosyayi yeni bir sekmede aciyor; dosya yakalandigi
        icin o sekme bos kaliyor ve her Excel'de bir tane daha birikiyordu.
        Yalnizca bu indirme sirasinda acilan sekmeler kapatilir.
        """
        if self.onceki_sekmeler is None:
            return
        try:
            yeniler = [p for p in self.ctx.pages
                       if p not in self.onceki_sekmeler and p is not self.page]
        except Exception:
            return
        for p in yeniler:
            try:
                if not p.is_closed():
                    p.close()
            except Exception:
                pass

    def geldi(self):
        return "govde" in self.alinan or bool(self.inenler)

    def kaydet(self, klasor, log):
        """Gelen dosyayi klasore yazar; yolunu dondurur (dosya yoksa None)."""
        if "govde" in self.alinan:
            yol = klasor / f"{self.on_ek}_{self.alinan['ad']}"
            yol.write_bytes(self.alinan["govde"])
            yaz(f"    indirildi (yakalanarak): {yol.name}", log)
            return yol
        if self.inenler:  # istek yakalanamadi ama tarayici indirdi
            dosya = self.inenler[0]
            yol = klasor / f"{self.on_ek}_{dosya.suggested_filename}"
            dosya.save_as(str(yol))
            yaz(f"    indirildi: {yol.name}", log)
            return yol
        return None


def _dosyayi_bekle(page, yakalayici, sure_sn, onceki_uyarilar=frozenset()):
    """Dosya gelene ya da Luca bir uyari gosterene kadar bekler; uyari metnini dondurur."""
    basla = time.monotonic()
    durum = {"uyari": None}

    def kontrol():
        if yakalayici.geldi():
            return True
        if time.monotonic() - basla >= 2 and fatura_yok_penceresini_kapat(page):
            durum["uyari"] = "Luca: fatura bulunamadi"
            return True
        uyari = uyari_metni(page, onceki_uyarilar)
        if uyari:
            durum["uyari"] = uyari
            return True
        return False

    kosulu_bekle(page, kontrol, sure_sn * 1000, aralik_ms=500)
    return durum["uyari"]


def _hazirlanan_dosyayi_bekle(page, yakalayici, dugme_metni, log):
    """Sure doldu ama Luca'ya giden istek hala suruyorsa (buyuk Excel hazirlaniyor) bekler.

    500 faturalik bir Excel'in hazirlanmasi 1 dakikayi gecebiliyor; eskiden
    bot bu sirada vazgecip kisayolla ikinci bir Excel istiyor ve sonraki
    ekrana geciyordu. En gec AYAR["excel_azami_saniye"] kadar beklenir.
    """
    if yakalayici.geldi() or not yakalayici.suren_istek_var():
        return
    azami = AYAR.get("excel_azami_saniye") or 600
    yaz(f"    Luca '{dugme_metni}' dosyasini hazirliyor, bekleniyor (en fazla {azami // 60} dk)...", log)
    basla = time.monotonic()
    while time.monotonic() - basla < azami:
        if kosulu_bekle(page, lambda: yakalayici.geldi() or not yakalayici.suren_istek_var(),
                        30000, aralik_ms=500):
            return
        yaz(f"    ... dosya hazirlaniyor ({int(time.monotonic() - basla)} sn)", log)


def dosya_indir(page, dugme_metni, hedef_klasor, on_ek, log, azami_saniye=30,
                pencere_acilir=True):
    """Indirme akisi: arac cubugu butonu -> (pencerede 'tum faturalar' -> indir) -> dosya.

    Inen dosyanin yolunu dondurur; inmezse None (hata firlatmaz, sebebi
    gunluge yazilir). pencere_acilir=False: Excel gibi onay penceresi
    acmayan butonlar (onceki islemden kalan pencere onay sanilmasin).
    """
    yakala = bool(AYAR.get("indirmeyi_yakala"))
    try:
        with _DosyaYakalayici(page, on_ek, yakala) as yakalayici:
            # onceki adimdan kalan bildirim yeni indirmeye karismasin
            fatura_yok_penceresini_kapat(page)
            onceki_uyarilar = uyari_metinleri(page)  # ekranda hep duran yazilar uyari sayilmaz
            if not dugmeye_bas(page, dugme_metni, sure=8000):
                yaz(f"    '{dugme_metni}' butonuna basilamadi, atlandi", log)
                return None

            # butonun ilk tepkisi: dosya, onay penceresi ya da Luca uyarisi
            kosulu_bekle(page, lambda: (yakalayici.geldi()
                                        or (pencere_acilir and indirme_diyalogu(page)[1] is not None)
                                        or uyari_metni(page, onceki_uyarilar)),
                         2000, aralik_ms=250)

            pencere = (indirme_diyalogu(page)[1]
                       if pencere_acilir and not yakalayici.geldi() else None)
            onay = None
            if pencere is not None:
                if diyalogda_tumunu_sec(page):
                    yaz("    Onay penceresinde 'tum faturalar' secildi", log)
                onay = diyalogda_tikla(page, INDIRME_ONAY)
                if onay:
                    yaz(f"    Onay penceresinde '{onay}' tiklandi", log)
                else:
                    yaz("    UYARI: onay penceresi tiklanamadi", log)

            # onay penceresi acilip tiklanamadiysa dosya gelmeyecek; bosuna beklenmez
            sure = 5 if (pencere is not None and not onay) else azami_saniye
            uyari = _dosyayi_bekle(page, yakalayici, sure, onceki_uyarilar)
            if not uyari:
                _hazirlanan_dosyayi_bekle(page, yakalayici, dugme_metni, log)

            # tiklama hic tutmadiysa (istek gitmedi, sekme acilmadi) butonun kendi
            # kisayolu denenir; istek gittiyse ikinci bir dosya istenmez
            kisayol = KISAYOLLAR.get(dugme_metni)
            if (kisayol and not uyari and not yakalayici.geldi()
                    and not yakalayici.suren_istek_var() and not yakalayici.yeni_sekme_acildi()):
                yaz(f"    Dosya gelmedi, '{dugme_metni}' kisayolu deneniyor ({kisayol})", log)
                try:
                    page.keyboard.press(kisayol)
                except Exception:
                    pass
                kosulu_bekle(page, yakalayici.geldi, min(azami_saniye, 15) * 1000, aralik_ms=500)

            yol = yakalayici.kaydet(hedef_klasor, log)
            if yol:
                return yol
            if uyari:
                yaz(f"    Luca uyarisi: {uyari}", log)
            else:
                yaz(f"    '{dugme_metni}' icin {int(sure)} sn icinde dosya gelmedi", log)
            return None
    except Exception as e:
        yaz(f"    '{dugme_metni}' indirilemedi ({type(e).__name__}: {e})", log)
        return None
    finally:
        if sayfa_canli(page):
            acik_pencereleri_kapat(page)  # pencere acik kalirsa sonraki adimlar kilitleniyor
