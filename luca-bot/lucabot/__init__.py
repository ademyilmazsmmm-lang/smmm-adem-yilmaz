# -*- coding: utf-8 -*-
"""Luca toplu e-fatura / e-arsiv indirme botu.

Program taslari (her biri tek bir isten sorumludur):

    ortak.py          ayarlar, gunluk, metin/tarih yardimcilari
    sabitler.py       Luca ekranlarindaki yazilar, belge tipleri, desenler
    bekleme.py        dinamik bekleme (Selenium'daki WebDriverWait karsiligi)
    konsol.py         kullaniciya giden adim/ilerleme mesajlari

    tarayici.py       tarayiciyi acma, cokunce yeniden acma, kullanicidan ENTER bekleme
    giris.py          LUCA GIRIS: otomatik giris, iki asamali dogrulama, oturum yenileme
    luca_ekran.py     ekran ogeleri: buton bulma/tiklama, Luca pencereleri, tarih kutulari
    luca_gezinme.py   firma secimi, calisma donemi, menuden ekrana gitme

    gib_sorgu.py      FATURA SORGULAMA: GIB'den Getir, Islem Takip, Belge Ara,
                      Interaktif V.D., iptal/itiraz sorgusu
    liste_secim.py    ekrandaki fatura listesini okuma ve faturalari isaretleme
    indirme.py        FATURA INDIRME: belge paketi (zip) ve Excel indirme
    fatura_analiz.py  inen Excel/ZIP'ten tevkifat, iptal/itiraz, matrah/KDV cikarma
    ekran_isleyici.py bir firmanin bir ekranini bastan sona isleyen akis

    firma_listesi.py  firmalar.xlsx, atlanacak firmalar, yarida kalan calisma
    calisma.py        tum firmalari dolasan ana dongu, cokme kurtarma
    rapor.py          RAPORLAMA: gunluk rapor verisi (rapor.json)
    rapor_excel.py    RAPORLAMA: rapor.xlsx (Ozet, Firma Durumu, Faturalar, Hatalar)
    eposta.py         calisma bitince ozet e-postasi (Outlook / SMTP)
"""
