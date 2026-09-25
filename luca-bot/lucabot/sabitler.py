# -*- coding: utf-8 -*-
"""Luca ekranlarina ait sabitler: buton/menu yazilari, belge tipleri, desenler.

Luca arayuzunde bir yazi degisirse duzeltilecek yer burasidir; akisi
yoneten kodlara dokunmak gerekmez.
"""

import re

# --- adresler ---------------------------------------------------------------
GIRIS_URL = "https://www.luca.com.tr"  # uygulama adresine dogrudan gidilince "LUCA HATA" veriyor
GIRIS_SAYFASI = "https://agiris.luca.com.tr/LUCASSO/giris.erp"  # ortak giris ekrani
UYGULAMA_PARCASI = "/Luca/"

# --- giris ------------------------------------------------------------------
SISTEM_GIRIS = ["Sistem Giriş", "Sistem Girisi", "Sistem Giris"]
GIRIS_DUGMESI = ["GİRİŞ", "Giriş", "GIRIS", "Giris"]
URUN_ADAYLARI = ["LUCA MALİ MÜŞAVİR PAKETİ", "Mali Müşavir Paketi",
                 "MALİ MÜŞAVİR PAKETİ", "Luca Mali Müşavir", "MALİ MÜŞAVİR"]
# Iki asamali dogrulama ekranini taniyan yazilar
DOGRULAMA_ISARETLERI = ["İki Aşamalı Doğrulama", "Doğrulama Kodu", "Güvenlik Kodu",
                        "SMS ile gönderilen", "Tek Kullanımlık Şifre"]
# Iki asamali dogrulama KAPALIYKEN Luca captcha soruyor; bot bunu gecemez
CAPTCHA_ISARETLERI = ["Captcha doğrulaması", "Captcha doğrulama", "güvenlik kontrolünü"]
DOGRULAMA_ONAY = ["Tamam", "Doğrula", "Onayla", "GİRİŞ", "Giriş"]

# --- menu -------------------------------------------------------------------
UST_MENU = "Akıllı Entegrasyon Noktası"
MODUL_ADAYLARI = ["İşletme Defteri", "Ser.Mes.Defteri", "Serbest Meslek Defteri",
                  "Basit Usül", "Basit Usul", "Genel Muhasebe", "Bilanço Defteri",
                  "Muhasebe", "Defter"]
MENU_KELIMELERI = ("ISLEMLERI", "ISLEMLER", "BEYANNAME", "RAPOR", "LISTESI", "HESAP PLANI",
                   "MAKBUZ", "DEFTER", "HIZLI ERISIM", "SORGULAMA", "FATURALARI")

# --- belge tipleri ----------------------------------------------------------
BELGE_TIPLERI = {
    "e-arsiv-alis": "e-Arşiv Alış Faturaları",
    "e-arsiv-satis": "e-Arşiv Satış Faturaları",
    "e-fatura-alis": "e-Fatura Alış Faturaları",
    "e-fatura-satis": "e-Fatura Satış Faturaları",
    "gib-5000": "GİB 5000/30000",
    "turmob-alis": "TÜRMOB Ent. Alış Faturaları",
    "turmob-satis": "TÜRMOB Ent. Satış Faturaları",
    "esmm-alis": "GİB e-SMM Alış",
    "esmm-satis": "GİB e-SMM Satış",
    # Akilli Entegrasyon Noktasi altinda degil, modul menusunun kendisinde:
    "e-arsiv-interaktif": "E-Arşiv Faturaları Sorgulama",
}

# menusu iki kademeli olan (Akilli Entegrasyon Noktasi araciligi olmayan) ekranlar
IKI_KADEMELI = {"e-arsiv-interaktif"}

# "GİB'den İptal/İtiraz Sorgula" butonu yalnizca bu ekranlarda var; digerlerinde
# butonu aramak her ekranda yarim dakika bosa gidiyordu
IPTAL_EKRANLARI = {"e-arsiv-alis", "e-arsiv-interaktif"}

# Belge (XML/zip) indirilmeyen ekranlar. Excel her ekranda iniyor: tevkifatli
# faturalar (KDV2) ancak Excel'deki sutunlardan guvenilir sekilde gorulebiliyor.
SADECE_EXCEL = {"e-arsiv-satis", "e-fatura-alis", "e-fatura-satis",
                "turmob-alis", "turmob-satis", "esmm-alis", "esmm-satis"}

# "--hepsi" ile calistirilacak sira: alis/satis ekranlari, en sonda karsilastirma
TUM_BELGELER = ["e-arsiv-alis", "e-arsiv-satis", "e-fatura-alis", "e-fatura-satis",
                "gib-5000", "turmob-alis", "turmob-satis", "esmm-alis", "esmm-satis",
                "e-arsiv-interaktif"]

# Aylik sorguyu kabul eden ekranlar 7 gunluk parcalamaya gerek duymuyor
AYLIK_SORGU = {"e-arsiv-interaktif", "gib-5000"}

# firmalar.xlsx'teki ekran sutunlari: baslik -> belge tipi
EKRAN_SUTUNLARI = {
    "e-Arşiv Alış": "e-arsiv-alis",
    "e-Arşiv Satış": "e-arsiv-satis",
    "e-Fatura Alış": "e-fatura-alis",
    "e-Fatura Satış": "e-fatura-satis",
    "GİB 5000/30000": "gib-5000",
    "TÜRMOB Alış": "turmob-alis",
    "TÜRMOB Satış": "turmob-satis",
    "e-SMM Alış": "esmm-alis",
    "e-SMM Satış": "esmm-satis",
    "İnteraktif V.D.": "e-arsiv-interaktif",
}
# ekran sutununa bunlardan biri yazilirsa o ekran o firmada acilmaz
ATLA_DEGERLERI = {"X", "HAYIR", "YOK", "ATLA", "-", "0"}

# --- Interaktif Vergi Dairesi ekrani ----------------------------------------
INTERAKTIF_SORGU = "İnteraktif V.D'sinden E-Arşiv Faturalarını Sorgula"
INTERAKTIF_CAPASI = "Luca Proxy ile Sorgula"  # secenek penceresinin kendi yazisi
INTERAKTIF_SERVIS = "GİB Servis ile Sorgula"
INTERAKTIF_LISTELE = "Mevcut E-Arşiv Faturalarını Listele"
INTERAKTIF_TEKRAR = 2  # Luca ilk sorguda hep getirmiyor, iki kez calistiriliyor
# Ekranin altinda "1 / 1 (Toplam Kayit Sayisi: 7)" yazar; sorgunun bitip
# listeyi doldurdugunu anlamanin en guvenilir yolu bu
KAYIT_SAYISI_DESENI = re.compile(r"Toplam\s*Kay[ıi]t\s*Say[ıi]s[ıi]\s*[:=]?\s*(\d+)", re.I)

# --- pencereler ve butonlar -------------------------------------------------
KAPAT_METINLERI = ["Bir daha gösterme"]  # sayfadaki "Tamam"/"Kapat" baska islevlere ait olabiliyor
GIB_GETIR = "GİB'den Getir"
DIYALOG_ONAY = ["Belgeleri Getir", "Sorgula", "Onayla", "Uygula"]
INDIRME_ONAY = ["Seçilenleri İndir", "Belgeleri İndir", "Dosyaları İndir", "İndir", "Onayla"]
DIYALOG_CAPASI = "Tüm faturaları seçmek için"
FATURA_YOK_CAPASI = "fatura bulunamadı"
# Sorgu bitince Luca bazen Islem Takip yerine bilgi penceresi gosteriyor
BILGI_CAPALARI = ("adet fatura bulundu", "fatura bulundu", "işlem tamamlandı",
                  "sorgulama tamamlandı", "kayıt bulunamadı")
# Pencerenin onay dugmesi de "Belge Ara" yaziyor; arac cubugundaki ayni adli
# butona tekrar basmamak icin her zaman pencerenin icinden tiklanir
BELGE_ARA_ONAY = ["Belge Ara", "Ara", "Sorgula", "Tamam", "Uygula"]
BELGE_ARA_CAPALARI = ("Muhasebeleşmiş", "Belge Numarası", "Tarih Aralığı")

KISAYOLLAR = {  # butonlarin kendi ipuclarinda yazan kisayollar (tiklama engellenirse kullanilir)
    "GİB'den Getir": "Alt+g",
    "Seçilenleri İndir": "Alt+z",
    "Yenile": "Alt+l",
    "Excel": "Alt+e",
    "Belge Seç": "Alt+b",
}

# --- Islem Takip penceresi --------------------------------------------------
ISLEM_BITTI = "sona erdi"
INDIRILEMEDI = "indirilemedi"
ISLEM_ISARETLERI = ["İşlem Takip", "sorgulandı", "belge kaydı bulundu", "Otomatik aşağı kaydır"]
# GIB'e ulasilamadiginda Luca bu uyariyi verip bekliyor; bosuna beklememek icin
GIB_HATA_ISARETLERI = ["VERILER GETIRILIRKEN HATA", "GIB INTERNET SITESINDEN",
                       "GIB INTERNET E-ARSIV", "ERISILEMEDI", "BAGLANTI KURULAMADI"]
GIB_HATA_METINLERI = ["veriler getirilirken hata", "e-Arşiv sistemine giriş",
                      "GİB internet sitesinden"]
# Firmanin o servise abonesi/yetkisi yoksa Luca bu SOAP hatasini yaziyor ve
# pencere hic kapanmiyor; ayni ekranin kalan tarih araliklarini denemek bos
YETKI_ISARETLERI = ["IZNINIZ BULUNMAMAKTADIR", "YETKINIZ BULUNMAMAKTADIR",
                    "SOAP FAULT", "YETKISIZ ISLEM"]

# islem_takibini_bekle'nin ozel donus degerleri
TAMAMLANMADI = -1  # zaman asimi
YETKI_YOK = -2     # bu ekranin atlanmasi gerekiyor
TAKILDI = -3       # sorgu durgunluk suresi boyunca ilerlemedi

# --- iptal/itiraz -----------------------------------------------------------
IPTAL_DUGME_ADAYLARI = ["GİB'den İptal/İtiraz Sorgula", "GİB'den iptal/itiraz Sorgula",
                        "iptal/itiraz Sorgula", "İptal/İtiraz Sorgula"]
IPTAL_ONAY = ["İptal/İtiraz Sorgula", "İptal/itiraz Sorgula", "İptal/İtiraz sorgula"]
IPTAL_CAPASI = "Raporlanma Tarihi"  # diyalogun kendi aciklama yazisi
IPTAL_DESENI = re.compile(r"IPTAL|ITIRAZ")
TEVKIFAT_DESENI = re.compile(r"TEVKIFAT")

# --- fatura satirlari -------------------------------------------------------
# GIB ekranlari tarihi 12/08/2026, 12.08.2026, 12-08-2026 ya da 2026-08-12 yazabiliyor
TARIH_DESENI = re.compile(r"\d{2}[./-]\d{2}[./-]\d{4}|\d{4}-\d{2}-\d{2}")
TARIH_NITELIGI = re.compile(r"tarih|date")
# ETTN'siz belge numarasi: 3 harf + 13 rakam (orn. GIB2026000000011)
BELGE_NO_DESENI = re.compile(r"[A-Za-z]{3}\d{13}")
# Fatura numarasi 16 hane: 3 on ek + 4 haneli yil + 9 haneli sira
# (orn. ABC2026000000123). On ekte rakam da olabildigi icin harf sarti yok.
FATURA_NO_DESENI = re.compile(r"\b([A-Za-z0-9ÇĞİÖŞÜçğıöşü]{3}\d{13})\b")
# kati desen tutmazsa: 16 haneli, en az bir rakam iceren herhangi bir kod
FATURA_NO_YEDEK = re.compile(r"\b(?=[A-Za-z0-9]{16}\b)[A-Za-z0-9]*\d[A-Za-z0-9]*\b")
# tevkifat isaretleri: ekran yazisi, UBL etiketi ve KDV tevkifat vergi kodu
XML_TEVKIFAT = ("tevkifat", "withholdingtaxtotal", ">9015<", "kdvtevkifat")
DONEM_DESENI = re.compile(r"(\d{2}[./]\d{2}[./]\d{4})\s*-\s*(\d{2}[./]\d{2}[./]\d{4})")

# --- dayaniklilik -----------------------------------------------------------
COKME_DENEMESI = 3  # tarayici indirme sirasinda cokerse firma kac kez tekrar denensin
