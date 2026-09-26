# -*- coding: utf-8 -*-
"""Bir firmanin bir ekranini (belge tipini) bastan sona isleyen akis.

    1. firma ve calisma donemi      (luca_gezinme)
    2. menuden ekrani ac            (luca_gezinme)
    3. GIB'den sorgula              (gib_sorgu)
    4. ekrandaki listeyi oku        (liste_secim)
    5. belge paketini indir (zip)   (indirme)
    6. iptal/itiraz sorgusu         (gib_sorgu)
    7. Excel'i indir ve analiz et   (indirme + fatura_analiz)
    8. durumu belirle

Her adim kendi metodundadir; sonuc tek bir sozlukte toplanir (ortak.yeni_sonuc).
Beklenmeyen hatalar burada yutulmaz: cagiran (calisma.py) hatayi o ekranin
sonucuna yazar, ekran goruntusunu kaydeder ve bir sonraki ekrana gecer.
"""

import time

from .bekleme import geri_cekil, sayfa_canli, sayfa_durulsun
from .fatura_analiz import (csv_yaz, excelden_sonuca_isle, fatura_kimlikleri,
                            iptal_itiraz_satirlari, tevkifatli_satirlar,
                            zipten_tevkifatlilar)
from .gib_sorgu import (belge_ara, gibden_getir, iptal_itiraz_sorgula,
                        interaktif_kayit_sayisi, interaktif_sorgula,
                        listeyi_bekle, listeyi_yenile)
from .indirme import dosya_indir
from .liste_secim import ekrandaki_satirlar, hepsini_sec, secim_kutulari, tabloyu_oku
from .luca_ekran import (acik_pencereleri_kapat, dugmeye_bas,
                         fatura_yok_penceresini_kapat)
from .luca_gezinme import calisma_donemi, donem_ayarla, firma_sec, menuye_git
from .ortak import (AYAR, AYLIK_AZAMI_GUN, TARIH_BICIMI, dosya_adi_yap,
                    hedef_ay_araligi, tarih_araliklari, tarih_cozumle,
                    yaz, yeni_sonuc)
from .sabitler import (AYLIK_SORGU, IKI_KADEMELI, INTERAKTIF_LISTELE,
                       GIB_HATASI, IPTAL_EKRANLARI, SADECE_EXCEL, TAKILDI,
                       YETKI_YOK)

TEKRAR_ONCESI_SANIYE = 5  # indirilemeyen fatura kalinca ayni sorguyu tekrarlamadan once


class TarayiciKapandi(RuntimeError):
    """Tarayici indirme sirasinda kapandi; firma bastan denenmeli."""


class FirmaSecilemedi(LookupError):
    """Firma Luca'da secilemedi; bu firmanin diger ekranlarini denemek bos."""


class EkranIsleyici:
    def __init__(self, page, firma, belge_tipi, araliklar, cikti_kok, log,
                 azami_deneme=3, firma_secili=False):
        self.page = page
        self.firma = firma
        self.tip = belge_tipi
        self.araliklar = araliklar
        self.log = log
        self.azami_deneme = azami_deneme
        self.firma_secili = firma_secili

        self.interaktif = belge_tipi in IKI_KADEMELI
        self.sadece_excel = belge_tipi in SADECE_EXCEL  # bu ekranlarda XML inmez, Excel iner

        self.sonuc = yeni_sonuc(firma, belge_tipi)
        self.klasor = cikti_kok / dosya_adi_yap(firma) / belge_tipi
        self.sonuc["klasor"] = str(self.klasor)

        self.istenen_bas = tarih_cozumle(araliklar[0][0])
        self.istenen_bit = tarih_cozumle(araliklar[-1][1])
        self.indirme_bas, self.indirme_bit = hedef_ay_araligi(self.istenen_bas, self.istenen_bit)
        self.indirme_araligi = (self.indirme_bas.strftime(TARIH_BICIMI),
                                self.indirme_bit.strftime(TARIH_BICIMI))
        self.sorgu_araliklari = self._sorgu_araliklari()

        # adimlar arasinda tasinan durum
        self.satirlar = []      # ekrandan (ya da Excel'den) okunan fatura satirlari
        self.sayi = None        # ekranin kendi yazdigi kayit sayisi (interaktif)
        self.fr = None          # listenin bulundugu cerceve
        self.kalan_hata = 0     # GIB'de olup kaynaktan inmeyen fatura
        self.excel_alindi = False
        self.excel_bekleniyor = False  # Excel indirilmeye calisildi mi
        self.ekran_acildi = True
        self.tevkifatlilar = []
        self.ekran_tevkifat = set()

    def _yaz(self, mesaj):
        yaz(mesaj, self.log)

    def _sorgu_araliklari(self):
        # Interaktif V.D. ekraninda fatura, duzenlendigi tarihle degil ait oldugu
        # donemle listelendigi icin hedef ayin disini sorgulamaya gerek yok.
        # GIB 5000/30000 de aylik sorgu kabul ediyor; orada tarih araligi
        # daralmaz, yalnizca parca boyu 7 gunden 30 gune cikar.
        if self.interaktif:
            return tarih_araliklari(self.indirme_bas, self.indirme_bit, AYLIK_AZAMI_GUN)
        if self.tip in AYLIK_SORGU:
            return tarih_araliklari(self.istenen_bas, self.istenen_bit, AYLIK_AZAMI_GUN)
        return self.araliklar

    # --- akis -----------------------------------------------------------------

    def calistir(self):
        basla = time.time()
        self.klasor.mkdir(parents=True, exist_ok=True)
        try:
            if not self._firma_ve_donem():
                return self.sonuc
            self._ekrani_ac()
            if not self.ekran_acildi:
                # bilinmeyen bir ekranda sorgu/onay butonlarina basmak tehlikeli
                # (baska bir islevin "Uygula"sina tiklaniyordu); ekran birakilir
                self.sonuc["durum"] = "ekran acilmadi"
                self.sonuc["not"] = "menuden ekran acilamadi; firmada bu ekran/modul var mi?"
                return self.sonuc
            self._gibden_sorgula()
            self._listeyi_oku()
            self._liste_okunamadiysa_excel()
            self._ekran_satirlarini_isle()

            satir_sayisi = len(self.satirlar) or (self.sayi or 0)
            if self._cok_fatura(satir_sayisi):
                return self.sonuc
            if not satir_sayisi:
                # GIB'de fatura vardi ama kaynak sunucudan inmedi: "fatura yok" demek yaniltici
                self.sonuc["durum"] = "kaynaktan inmedi" if self.kalan_hata else "fatura yok"
                return self.sonuc

            if not self.interaktif and not self.sadece_excel:
                if self._belgeleri_indir(satir_sayisi):
                    return self.sonuc
            self._iptal_itiraz()
            self._exceli_indir(satir_sayisi)

            self.sonuc["durum"] = self._son_durum()
            return self.sonuc
        finally:
            self.sonuc["sure"] = round(time.time() - basla, 1)

    def _son_durum(self):
        """Indirilen dosyalara gore ekranin durumu.

        Belge paketi (zip) inmediyse "dosya inmedi". Excel (tevkifat, iptal,
        matrah/KDV'nin kaynagi) inmediyse ekran tamam sayilmaz; sonraki
        calistirmada [D]evam secilince bu ekran yeniden denenir.
        """
        excel_yok = self.excel_bekleniyor and not self.excel_alindi
        if self.interaktif or self.sadece_excel:
            return "excel inmedi" if excel_yok else "tamam"
        if not self.sonuc["dosyalar"]:
            return "dosya inmedi"
        return "tamam (excel eksik)" if excel_yok else "tamam"

    # 1. firma ve donem
    def _firma_ve_donem(self):
        page = self.page
        acik_pencereleri_kapat(page, self.log)
        if not self.firma_secili:  # ikinci belge tipinde firma zaten secili
            self._yaz("    Firma seciliyor")
            try:
                firma_sec(page, self.firma, self.log)
            except LookupError as e:
                raise FirmaSecilemedi(str(e)) from e
        if not donem_ayarla(page, self.firma, self.istenen_bas, self.istenen_bit, self.log):
            self.sonuc["durum"] = "donem disi"
            return False
        donem_bas, donem_bit = calisma_donemi(page)
        if donem_bas and donem_bit:
            self.sonuc["donem"] = f"{self.indirme_bas:%d/%m/%Y}-{self.indirme_bit:%d/%m/%Y}"
        if self.indirme_bit != self.istenen_bit and not self.firma_secili:
            self._yaz(f"    Hedef donem: {self.indirme_araligi[0]} - {self.indirme_araligi[1]}"
                      f" (GIB sorgusu {self.istenen_bas:%d/%m/%Y} - {self.istenen_bit:%d/%m/%Y})")
        return True

    # 2. ekran
    def _ekrani_ac(self):
        self._yaz("    Menuye gidiliyor")
        basla = time.time()
        self.ekran_acildi = menuye_git(self.page, self.tip)
        gecen = time.time() - basla
        if not self.ekran_acildi:
            self._yaz("    UYARI: ekranin kendi butonu gorunmedi; ekran acilmamis olabilir"
                      " (firmada bu modul yok mu?)")
        if gecen > 5:  # nerede beklendigi gunlukten anlasilsin
            self._yaz(f"    Menu {int(gecen)} sn'de acildi")
        # Ekranda hic fatura yoksa Luca acilista "Her hangi bir fatura bulunamadi"
        # penceresi gosteriyor; Tamam denmeden ekranla hicbir sey yapilamiyor.
        # Tek deneme yeter: pencere gec cikarsa sorgu adimlari yine kapatiyor.
        if fatura_yok_penceresini_kapat(self.page):
            self._yaz("    'Fatura bulunamadi' penceresi kapatildi")

    # 3. GIB sorgusu
    def _gibden_sorgula(self):
        page = self.page
        if self.interaktif:
            interaktif_sorgula(page, self.sorgu_araliklari, self.log, self.indirme_araligi)
            return

        ust_uste_takildi = 0
        for bas, bit in self.sorgu_araliklari:
            sonuc = self._araligi_sorgula(bas, bit)
            if sonuc == YETKI_YOK:  # servise yetki yok: kalan tarih araliklari denenmez
                break
            # Bir defalik takilma tek basina sorgunun kalanini gecersiz saymaz
            # (bazen sadece ilk parca donuyor, sonrakiler normal calisiyor);
            # ama ust uste iki kez olursa ekranin tamami yanit vermiyor demektir.
            if sonuc == TAKILDI:
                ust_uste_takildi += 1
                if ust_uste_takildi >= 2:
                    self._yaz("    Bu ekranda sorgu ust uste takildi, kalan tarih araliklari atlaniyor")
                    self.sonuc["not"] = "sorgu ust uste takildi"
                    break
            else:
                ust_uste_takildi = 0
        # liste her 7 gunluk parcada degil, tum sorgular bitince bir kez tazelenir
        listeyi_yenile(page, self.log)
        # ekranda son parcanin filtresi kalmasin; indirme tum donem uzerinden
        belge_ara(page, *self.indirme_araligi, self.log)
        self.sonuc["indirilemeyen"] = self.kalan_hata

    def _araligi_sorgula(self, bas, bit):
        """Tek tarih araligini sorgular; inmeyen fatura kalirsa birkac kez tekrarlar.

        Son islem_takibini_bekle sonucunu dondurur (YETKI_YOK / TAKILDI / sayi).
        """
        onceki_hata = None
        basarisiz = 0
        for deneme in range(1, self.azami_deneme + 1):
            try:
                basarisiz = gibden_getir(self.page, bas, bit, self.log)
            except LookupError as e:
                # bu ekranda GIB sorgusu yoksa liste yine de okunur
                self._yaz(f"    UYARI: sorgu yapilamadi ({e}); ekrandaki liste kullanilacak")
                self.sonuc["not"] = "GIB sorgusu bu ekranda yok"
                return 0
            if basarisiz == YETKI_YOK:
                self.sonuc["not"] = "bu firmanin bu servise yetkisi yok"
                return YETKI_YOK
            if basarisiz == GIB_HATASI:
                if deneme < self.azami_deneme:
                    self._yaz(f"    GİB hatasi sonrasi tekrar sorgulaniyor ({deneme + 1}/{self.azami_deneme})")
                    geri_cekil(self.page, TEKRAR_ONCESI_SANIYE)
                    continue
                self._yaz(f"    GİB {self.azami_deneme} denemede de hata verdi, bu aralik atlandi ({bas} - {bit})")
                self.sonuc["not"] = f"GIB hata verdi: {bas} - {bit}"
                return 0
            if basarisiz <= 0:  # 0: hepsi indi, TAKILDI/TAMAMLANMADI: tekrar denemek bos
                return basarisiz
            # sayi azalmiyorsa karsi sunucu yanit vermiyor demektir; tekrar denemek bos
            if onceki_hata is not None and basarisiz >= onceki_hata:
                self._yaz(f"    {basarisiz} fatura tekrarda da inmedi (kaynak sunucu yanit vermiyor)")
                self.kalan_hata += basarisiz
                return basarisiz
            if deneme == self.azami_deneme:
                self._yaz(f"    {basarisiz} fatura {self.azami_deneme} denemede de indirilemedi")
                self.kalan_hata += basarisiz
                return basarisiz
            onceki_hata = basarisiz
            self._yaz(f"    Tekrar sorgulaniyor ({deneme + 1}/{self.azami_deneme})")
            geri_cekil(self.page, TEKRAR_ONCESI_SANIYE)
        return basarisiz

    # 4. ekrandaki liste
    def _listeyi_oku(self):
        page = self.page
        self._yaz("    Tablo okunuyor")
        self.satirlar, self.fr = ekrandaki_satirlar(page)
        kutu_cercevesi = self.fr
        if not self.satirlar and self.interaktif:
            # sorgu listeyi kendiliginden doldurmadiysa kayitli faturalari listele
            self.sayi = interaktif_kayit_sayisi(page)
            self._yaz(f"    Ekrandaki kayit sayisi: "
                      f"{self.sayi if self.sayi is not None else 'okunamadi'}")
            if not self.sayi:
                dugmeye_bas(page, INTERAKTIF_LISTELE, sure=5000)
                self.sayi = listeyi_bekle(page, self.log, azami_saniye=30)
            self.satirlar, self.fr = ekrandaki_satirlar(page)
            kutu_cercevesi = self.fr
        if not self.satirlar:
            self.fr, self.satirlar = tabloyu_oku(page, kutu_cercevesi)
        # liste ekrandan okunamazsa sorun degil: asil kaynak inen Excel
        self.sonuc["fatura_sayisi"] = len(self.satirlar) or (self.sayi or 0)
        self._yaz(f"    {len(self.satirlar)} satir listelendi"
                  + (f" (ekranda {self.sayi} kayit)" if self.sayi and not self.satirlar else ""))

    def _liste_okunamadiysa_excel(self):
        """Interaktif ekranda liste de kayit sayisi da okunamadiysa Excel hemen alinir.

        Sayi biliniyorsa Excel iptal sorgusundan sonra indirilir, boylece
        iptal/itiraz durumu da dosyaya yansir. Bu ekranda Excel tum listeyi
        indirdigi icin secim yapilmaz.
        """
        if self.satirlar or not self.interaktif or self.sayi:
            return
        yol = dosya_indir(self.page, "Excel", self.klasor, "liste", self.log,
                          azami_saniye=AYAR["indirme_saniye"], pencere_acilir=False)
        if not yol:
            return
        self.excel_alindi = True
        self.sonuc["dosyalar"].append(yol.name)
        self.satirlar = excelden_sonuca_isle(self.sonuc, yol, self.klasor, self.log)
        if not self.satirlar:
            self._yaz("    Excel'de de satir bulunamadi")

    def _ekran_satirlarini_isle(self):
        """Ekrandan okunan satirlardan liste.csv, fatura kimlikleri ve tevkifat."""
        if not self.satirlar or self.excel_alindi:  # Excel'den gelenler zaten islendi
            return
        csv_yaz(self.klasor / "liste.csv", self.satirlar)
        self.sonuc["faturalar"] = [list(k) for k in fatura_kimlikleri(self.satirlar)]
        self.tevkifatlilar = tevkifatli_satirlar(self.satirlar, self.tip)
        self.ekran_tevkifat = {no for _, no in fatura_kimlikleri(self.tevkifatlilar)}
        self.sonuc["tevkifat"] = len(self.tevkifatlilar)
        if self.tevkifatlilar:
            csv_yaz(self.klasor / "tevkifatli.csv", self.tevkifatlilar)
            self._yaz(f"    DIKKAT: {len(self.tevkifatlilar)} tevkifatli alis faturasi (KDV2)")

    def _cok_fatura(self, satir_sayisi):
        """Cok faturali firmalar (e-fatura portalinden elle indirilenler) atlanir.

        Binlerce belgeyi indirmek gece calismasinin tamamini tiketiyor.
        """
        azami = AYAR.get("azami_fatura") or 0
        ekran_sayisi = interaktif_kayit_sayisi(self.page) or 0  # sayfalamada satir sayisi yaniltir
        gercek_sayi = max(satir_sayisi, ekran_sayisi)
        if not (azami and gercek_sayi > azami):
            return False
        self._yaz(f"    ATLANDI: {gercek_sayi} fatura (sinir {azami}); portalden elle indirilecek")
        self.sonuc["fatura_sayisi"] = gercek_sayi
        self.sonuc["durum"] = "atlandi (cok fatura)"
        self.sonuc["not"] = f"{gercek_sayi} fatura, sinir {azami}: portalden elle indirin"
        return True

    # 5. belge paketi
    def _belge_paketini_indir(self, satir_sayisi):
        """Tek bir 'Seçilenleri İndir' denemesi: isaretle -> indir. Inen dosyayi (ya da None) dondurur."""
        page = self.page
        secilen = hepsini_sec(page, self.fr, satir_sayisi)
        if secilen:
            self._yaz(f"    {secilen} kayit isaretlendi, indirme basliyor")
        else:
            self._yaz("    UYARI: hicbir kayit isaretlenemedi, indirme yine de denenecek")
        return dosya_indir(page, "Seçilenleri İndir", self.klasor, "belgeler", self.log,
                           azami_saniye=AYAR["indirme_saniye"])

    def _belgeleri_indir(self, satir_sayisi):
        """XML belge paketini indirir. Akis burada bitmeliyse True doner.

        Butona tiklandigi halde dosya gelmeyebiliyor (Luca'nin ara sira tepki
        vermedigi oluyor); bir kez daha denenir. Yine gelmezse ekran yine de
        tamam sayilir (Excel asil kaynak) ama rapora not dusulur.
        """
        page = self.page
        yol = self._belge_paketini_indir(satir_sayisi)
        if not yol and sayfa_canli(page):
            self._yaz("    Belge paketi (zip) inmedi, tekrar deneniyor")
            geri_cekil(page, 3)
            acik_pencereleri_kapat(page, self.log)
            yol = self._belge_paketini_indir(satir_sayisi)
            if not yol:
                self._yaz("    UYARI: belge paketi (zip) yine inmedi; Excel ile devam ediliyor")
                self.sonuc["not"] = "belge paketi (zip) inmedi, yalnizca Excel indi"
        if yol:
            self.sonuc["dosyalar"].append(yol.name)
            if yol.suffix.lower() == ".zip":
                # XML bozuk inebildigi gibi ekranda da sutun olmayabiliyor;
                # iki kaynagin birlesimi alinir
                xml_tevkifat = zipten_tevkifatlilar(yol)
                if xml_tevkifat:
                    self.sonuc["tevkifat"] = max(len(self.ekran_tevkifat | xml_tevkifat),
                                                 len(self.tevkifatlilar), len(xml_tevkifat))
                    self._yaz(f"    XML'de {len(xml_tevkifat)} tevkifatli fatura bulundu"
                              f" (toplam {self.sonuc['tevkifat']})")
        if not sayfa_canli(page):
            if yol:
                # belge paketi elimizde; firmayi tekrar sorgulamaya gerek yok
                self._yaz("    Belgeler indi ama tarayici kapandi;"
                          " Excel'in indirilme sorgusu bu firmada atlandi")
                self.sonuc["durum"] = "tamam (iptal eksik)"
                self.sonuc["not"] = "tarayici belge indirmeden sonra kapandi"
                return True
            # dosya yok: firmayi 'tamam' sayma, ana dongu bastan denesin
            raise TarayiciKapandi("tarayici indirme sirasinda kapandi")
        return False

    # 6. iptal/itiraz
    def _iptal_itiraz(self):
        """Iptal/itiraz sorgusu Excel'den ONCE yapilir; Excel boylece guncel durumu tasir."""
        if not (AYAR["iptal_itiraz"] and self.tip in IPTAL_EKRANLARI):
            return
        page = self.page
        try:
            # Sorgu tum listeye uygulanir; fatura isaretlemeye gerek yok.
            # Sorgu ile ayni araliklar kullanilir: GIB alis ekraninda 7 gunluk
            # parcalar (tek seferde sorulunca iptaller cikmiyor), interaktif
            # V.D. ekraninda donemin tamami icin tek sorgu.
            bilgi = {}
            basarili = iptal_itiraz_sorgula(page, self.sorgu_araliklari, self.log, self.interaktif,
                                            bilgi)
            if bilgi.get("gib_hatasi"):
                self.sonuc["not"] = ("Iptal/itiraz sorgulanamadi: GIB kimlik dogrulanamadi"
                                     f" ({', '.join(bilgi['gib_hatasi'])}) - firmanin GIB/"
                                     "interaktif VD bilgilerini Luca'da kontrol edin")
            if basarili:
                # sorgu durum sutununu degistirir; liste yeniden okunur
                yeni_satirlar, yeni_fr = ekrandaki_satirlar(page)
                if yeni_satirlar:
                    self.satirlar, self.fr = yeni_satirlar, yeni_fr
                    self.sonuc["fatura_sayisi"] = len(self.satirlar)
                    csv_yaz(self.klasor / "liste.csv", self.satirlar)
                    self.sonuc["tevkifat"] = len(tevkifatli_satirlar(self.satirlar, self.tip))
                iptaller = iptal_itiraz_satirlari(self.satirlar)
                self.sonuc["iptal_itiraz"] = len(iptaller)
                if iptaller:
                    csv_yaz(self.klasor / "iptal-itiraz.csv", iptaller)
                    self._yaz(f"    DIKKAT: {len(iptaller)} faturada iptal/itiraz var")
                else:
                    self._yaz("    Iptal/itiraz kaydi yok")
            elif self.interaktif:
                self._yaz("    UYARI: İnteraktif V.D.'de iptal sorgusu başarısız, Excel ile devam edilecek")
        except Exception as e:
            if not sayfa_canli(page):
                raise
            self._yaz(f"    Iptal/itiraz sorgusu yapilamadi ({type(e).__name__}: {e})")
            acik_pencereleri_kapat(page, self.log)

    # 7. Excel
    def _exceli_indir(self, satir_sayisi):
        if self.excel_alindi:
            return
        page = self.page
        acik_pencereleri_kapat(page, self.log)
        fatura_yok_penceresini_kapat(page)
        sayfa_durulsun(page, azami_ms=2000)  # iptal sorgusu sonrasi ekran otursun
        if not self.interaktif:
            # iptal sonrasi Yenile suzgeci sifirliyor; Excel hedef donemi kapsasin
            belge_ara(page, *self.indirme_araligi, self.log)
        guncel_sayi = len(self.satirlar) or satir_sayisi
        _, _, guncel_fr = secim_kutulari(page)
        # Interaktif V.D. ekraninda Excel tum listeyi indiriyor; secim gerekmiyor.
        # GIB alis ekrani ise "once faturalari seciniz" uyarisi veriyor.
        if guncel_fr is not None and not self.interaktif:
            self.fr = guncel_fr
            if not hepsini_sec(page, self.fr, guncel_sayi):
                self._yaz("    UYARI: Faturalar secilemedi")
            sayfa_durulsun(page, azami_ms=3000)
        # buyuk listelerde Luca Excel'i gec hazirliyor; sure satir sayisiyla artar
        sure = max(AYAR["indirme_saniye"], 60) + int(guncel_sayi * 0.3)
        self.excel_bekleniyor = True
        yol = dosya_indir(page, "Excel", self.klasor, "liste", self.log,
                          azami_saniye=sure, pencere_acilir=False)
        if yol:
            self.excel_alindi = True
            self.sonuc["dosyalar"].append(yol.name)
            # Excel iptal/itiraz ve tevkifat sutunlarini icerdigi icin her iki
            # ekranda da asil kaynak odur; ekran kazima yalnizca yedek
            excel_satirlari = excelden_sonuca_isle(self.sonuc, yol, self.klasor, self.log)
            if excel_satirlari:
                self.satirlar = excel_satirlari


def firma_isle(page, firma, belge_tipi, araliklar, cikti_kok, log, azami_deneme=3,
               firma_secili=False):
    """Eski adiyla kisayol: bir firmanin bir ekranini isler, sonuc sozlugunu dondurur."""
    return EkranIsleyici(page, firma, belge_tipi, araliklar, cikti_kok, log,
                         azami_deneme, firma_secili).calistir()
