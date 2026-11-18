# -*- coding: utf-8 -*-
"""Luca'dan Isletme Defteri Dokumunu (Excel) indirir: 2. sinif (isletme / serbest meslek defteri) firmalar.

Yol (ekran goruntusunden): Isletme Defteri modulu > Raporlar > Genel Raporlar > Isletme Defteri Dokumu. Form: Tarih Ilk,
Tarih Son, Rapor Turu = Excel (xlsx), altta Rapor dugmesi. Dokumun GIDERLER / GELIRLER tablolarindaki Evrak No sutunu
fatura numarasini tasir (muavin_karsilastir.isletme_defteri_satirlari). Muavin ile ayni mekanik (luca_muavin).
"""

from lucabot.bekleme import kosulu_bekle
from lucabot.luca_ekran import acik_pencereleri_kapat
from lucabot.luca_gezinme import menu_yolunu_ac
from lucabot.musteri_listesi import tani_kaydet
from lucabot.ortak import dosya_adi_yap, yaz

from . import luca_mizan, luca_muavin
from .luca_hesap_plani import SON_MENU_TANISI, _yuklenmeyi_bekle, menuden_dogrudan_ac
from .muavin_karsilastir import isletme_defteri_satirlari

MENU_ETIKETI = "||||İşletme Defteri Dökümü"
MENU_ADI = "İşletme Defteri Dökümü"
MENU_YOLU = "İşletme Defteri > Raporlar > Genel Raporlar > İşletme Defteri Dökümü"
FORM = r"Tarih\s*(İlk|Son)"
TARIH_ALANLARI = (("tarih_ilk", "Tarih İlk"), ("tarih_son", "Tarih Son"),
                  ("tarih_ilk", "Başlangıç Tarihi"), ("tarih_son", "Bitiş Tarihi"))
RAPOR_TURU_ADAYLARI = ("Excel (xlsx)", "Excel Liste (xlsx)", "Excel", "xlsx")
DUGME_ADAYLARI = ("Rapor", "Raporu Al", "Excel")


def ekrani_ac(page):
    acik_pencereleri_kapat(page)
    hazir = lambda: luca_muavin._form_hazir(page, FORM)
    if menuden_dogrudan_ac(page, MENU_ETIKETI, MENU_ADI, None):
        if not kosulu_bekle(page, hazir, 120000, aralik_ms=500):
            raise LookupError("İşletme Defteri Dökümü formu açılmadı")
    else:
        neden = SON_MENU_TANISI["metin"]
        try:
            menu_yolunu_ac(page, MENU_YOLU, hazir)
        except LookupError as e:
            raise LookupError(f"İşletme Defteri Dökümü menüsü açılamadı (menü verisi: {neden}; ekran menüsü: {e})")
    _yuklenmeyi_bekle(page)


def isletme_cek(page, firma, bas, bit, indirme_klasoru, tani_klasoru, log=None, tani_hep=False):
    """Acik firmanin Isletme Defteri Dokumunu Excel indirir; muavin_satirlari bicimli satir listesi
    (gider -> hesap 191, gelir -> 391)."""
    adim = (lambda ek: tani_kaydet(page, tani_klasoru, log, ek, "isletme")) if tani_hep else (lambda ek: None)
    try:
        ekrani_ac(page)
        adim("-1-form")
        yaz(f"    İşletme defteri formu (tanı): {luca_muavin.form_tanisi(page)}", log)
        alanlar = luca_muavin.tarih_ve_rapor_turu(page, bas, bit, TARIH_ALANLARI, FORM, RAPOR_TURU_ADAYLARI,
                                                  "İşletme defteri")
        yaz(f"    İşletme defteri formu: {', '.join(f'{k}={v}' for k, v in alanlar.items())}", log)
        adim("-2-form-doldu")
        yol = luca_mizan.indir(page, indirme_klasoru, f"isletme_defteri_{dosya_adi_yap(firma)}.xlsx", log=log,
                               dugme_adlari=DUGME_ADAYLARI, rapor_adi="İşletme defteri dökümü")
        satirlar = isletme_defteri_satirlari(yol)
        yaz(f"    İşletme defteri dökümü indirildi: {yol.name} ({len(satirlar)} kayıt)", log)
        return satirlar
    except LookupError:
        tani_kaydet(page, tani_klasoru, log, "-hata", "isletme")
        raise
