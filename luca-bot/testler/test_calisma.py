# -*- coding: utf-8 -*-
"""Ana dongunun dayanikliligi: ekran hatasi, firma secilememesi, sekme cokmesi.

Ekran akisinin kendisi (firma_isle) sahte bir fonksiyonla degistirilir;
tarayici gercektir (sekme kapanmasi/ekran goruntusu gercekten denenir).
Tarayici acilamazsa testler atlanir.

    xvfb-run -a python -m unittest testler.test_calisma -v    (Linux)
"""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sahte_luca  # noqa: E402
from lucabot import calisma as calisma_modulu  # noqa: E402
from lucabot.ekran_isleyici import FirmaSecilemedi  # noqa: E402
from lucabot.firma_listesi import FirmaSecimi  # noqa: E402
from lucabot.ortak import tarih_araliklari, tarih_cozumle, yeni_sonuc  # noqa: E402


class CalismaDayanikliligi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
            cls.pw = sync_playwright().start()
            secenek = {}
            if os.environ.get("LUCA_TEST_CHROMIUM"):
                secenek["executable_path"] = os.environ["LUCA_TEST_CHROMIUM"]
            cls.tarayici = cls.pw.chromium.launch(headless=True, **secenek)
        except Exception as e:  # pragma: no cover - ortamda tarayici yok
            raise unittest.SkipTest(f"tarayici acilamadi: {e}")
        cls.sunucu, cls.adres = sahte_luca.baslat()

    @classmethod
    def tearDownClass(cls):
        cls.tarayici.close()
        cls.pw.stop()
        cls.sunucu.shutdown()

    def setUp(self):
        self.ctx = self.tarayici.new_context()
        self.page = self.ctx.new_page()
        self.page.goto(self.adres)
        self.klasor = Path(tempfile.mkdtemp())
        self.cagrilar = []
        self._asil = calisma_modulu.firma_isle

    def tearDown(self):
        calisma_modulu.firma_isle = self._asil
        self.ctx.close()

    def _calistir(self, firmalar, tipler, sahte):
        calisma_modulu.firma_isle = sahte
        araliklar = tarih_araliklari(tarih_cozumle("01/08/2026"), tarih_cozumle("10/08/2026"))
        c = calisma_modulu.Calisma(self.pw, self.ctx, self.page, self.klasor / "profil", {},
                                   FirmaSecimi(firmalar), tipler, araliklar, self.klasor,
                                   self.klasor / "calisma.log")
        return c, c.calistir()

    def _tamam(self, firma, tip, **_):
        s = yeni_sonuc(firma, tip)
        s.update(durum="tamam", fatura_sayisi=2)
        return s

    def test_ekran_hatasi_firmanin_diger_ekranlarini_durdurmaz(self):
        def sahte(page, firma, tip, *a, **k):
            self.cagrilar.append((firma, tip))
            if tip == "gib-5000":
                raise LookupError("'GİB 5000/30000' menu maddesi bulunamadi")
            return self._tamam(firma, tip)

        c, ozet = self._calistir(["A", "B"], ["e-arsiv-alis", "gib-5000", "esmm-alis"], sahte)
        self.assertEqual(len(self.cagrilar), 6)  # her iki firmada da 3 ekran denendi
        durumlar = {(s["firma"], s["belge_tipi"]): s["durum"] for s in c.sonuclar}
        self.assertEqual(durumlar[("A", "esmm-alis")], "tamam")
        self.assertEqual(durumlar[("A", "gib-5000")], "hata: LookupError")
        self.assertEqual((ozet.basarili, ozet.sorunlu), (4, 2))
        hatali = next(s for s in c.sonuclar if s["durum"].startswith("hata"))
        self.assertTrue(Path(hatali["ekran_goruntusu"]).exists())
        self.assertEqual(c.ardisik_hata, 0)  # ekranlarin cogu calisti, firma basarisiz sayilmaz

    def test_firma_secilemezse_kalan_ekranlar_denenmez(self):
        def sahte(page, firma, tip, *a, **k):
            self.cagrilar.append((firma, tip))
            if firma == "A":
                raise FirmaSecilemedi("'A' acik listelerin hicbirinde bulunamadi")
            return self._tamam(firma, tip)

        c, ozet = self._calistir(["A", "B"], ["e-arsiv-alis", "e-fatura-alis"], sahte)
        self.assertEqual(self.cagrilar, [("A", "e-arsiv-alis"), ("B", "e-arsiv-alis"),
                                         ("B", "e-fatura-alis")])
        self.assertEqual(ozet.sorunlu, 1)

    def test_sekme_cokerse_acik_luca_sekmesinden_devam(self):
        yedek = self.ctx.new_page()  # tarayicida acik kalan ikinci Luca sekmesi
        yedek.goto(self.adres)

        def sahte(page, firma, tip, *a, **k):
            self.cagrilar.append((firma, tip, page is yedek))
            if (firma, tip) == ("A", "e-fatura-alis") and not page.is_closed() and page is not yedek:
                page.close()  # indirme sirasinda sekme coktu
                raise RuntimeError("Target page, context or browser has been closed")
            return self._tamam(firma, tip)

        c, ozet = self._calistir(["A", "B"], ["e-arsiv-alis", "e-fatura-alis"], sahte)
        # A'nin tamamlanmis ilk ekrani tekrar acilmaz; coken ekran yedek sekmede tekrar denenir
        self.assertEqual(self.cagrilar, [("A", "e-arsiv-alis", False), ("A", "e-fatura-alis", False),
                                         ("A", "e-fatura-alis", True), ("B", "e-arsiv-alis", True),
                                         ("B", "e-fatura-alis", True)])
        self.assertEqual((ozet.basarili, ozet.sorunlu), (4, 0))
        self.assertEqual(ozet.durduruldu, "")

    def test_ctrl_c_durumu_kaydeder(self):
        def sahte(page, firma, tip, *a, **k):
            if firma == "B":
                raise KeyboardInterrupt
            return self._tamam(firma, tip)

        c, ozet = self._calistir(["A", "B", "C"], ["e-arsiv-alis"], sahte)
        self.assertIn("Ctrl+C", ozet.durduruldu)
        kalan = (self.klasor / "kalan-firmalar.txt").read_text(encoding="utf-8")
        self.assertEqual(kalan, "B, C")
        self.assertTrue((self.klasor / "rapor.xlsx").exists())


    def _urun_akisi(self, adres_eki):
        from lucabot.giris import urun_sec, uygulamayi_bekle
        sahte_luca.sifirla()
        ctx = self.tarayici.new_context()
        try:
            page = ctx.new_page()
            page.goto(self.adres + adres_eki)
            self.assertTrue(urun_sec(page, None, sure=5000))
            uygulama = uygulamayi_bekle(ctx, page, None, azami_saniye=40,
                                        tani_klasoru=self.klasor / "tani")
            return (uygulama.url if uygulama else None), sahte_luca.SAYAC["sso"]
        finally:
            ctx.close()

    def test_urun_secilince_luca_ekrani_bulunur(self):
        """Uygulama ayri pencerede ve gecikmeli aciliyor; firma listeli ekran bulunmali."""
        url, acilis = self._urun_akisi("urun")
        self.assertIn("/Luca/uygulama", url or "")
        self.assertGreaterEqual(acilis, 1)

    def test_bos_kalan_pencerede_urun_yeniden_secilir(self):
        """Ilk uygulama penceresi bos kalirsa urun tekrar secilir ve Luca acilir."""
        url, acilis = self._urun_akisi("urun?ilk_bos=1")
        self.assertIn("/Luca/uygulama", url or "")
        self.assertGreaterEqual(acilis, 2)

    def test_gib_dogrulama_hatasinda_aralik_tekrar_sorgulanir(self):
        """Iptal sorgusunda GIB 'kimlik dogrulanamadi' derse beklemeden ayni aralik tekrar sorulur."""
        import time
        from lucabot.ekran_isleyici import firma_isle
        from lucabot.ortak import AYAR
        sahte_luca.sifirla()
        AYAR.update(azami_saniye=120, durgunluk_saniye=60, indirme_saniye=15)
        sahte_luca.SAYAC["gib_hatasi"] = 1
        log = self.klasor / "calisma.log"
        araliklar = tarih_araliklari(tarih_cozumle("01/08/2026"), tarih_cozumle("05/08/2026"))
        basla = time.time()
        sonuc = firma_isle(self.page, "AKIN COBAN", "e-arsiv-alis", araliklar, self.klasor, log)
        gunluk = log.read_text(encoding="utf-8")
        self.assertIn("GİB hata verdi", gunluk)
        self.assertIn("tekrar sorgulaniyor", gunluk)
        self.assertEqual(sonuc["durum"], "tamam")
        self.assertEqual(sonuc["iptal_itiraz"], 1)  # tekrar sorgu iptali buldu
        self.assertLess(time.time() - basla, 60)    # durgunluk suresi (60 sn) beklenmedi


    def test_gib_kimlik_hatasi_surerse_kalan_araliklar_atlanir(self):
        """Hata her aralikta tekrarlaniyorsa 2 araliktan sonra birakilir ve rapora not dusulur."""
        from lucabot.ekran_isleyici import firma_isle
        from lucabot.ortak import AYAR
        sahte_luca.sifirla()
        AYAR.update(azami_saniye=120, durgunluk_saniye=60, indirme_saniye=15)
        sahte_luca.SAYAC["gib_hatasi"] = 99
        log = self.klasor / "calisma.log"
        araliklar = tarih_araliklari(tarih_cozumle("01/08/2026"), tarih_cozumle("20/08/2026"))
        sonuc = firma_isle(self.page, "AKIN COBAN", "e-arsiv-alis", araliklar, self.klasor, log)
        gunluk = log.read_text(encoding="utf-8")
        self.assertIn("kalan iptal/itiraz araliklari atlaniyor", gunluk)
        self.assertEqual(gunluk.count("Iptal/itiraz sorgusu ("), 4)  # 2 aralik x 2 deneme
        self.assertIn("kimlik dogrulanamadi", sonuc["not"])
        self.assertEqual(sonuc["durum"], "tamam")

    def test_interaktif_kalici_uyari_excel_beklenir(self):
        """Ekranda hep duran 'Lutfen ...' yazisi uyari sanilmamali; gec gelen Excel beklenmeli."""
        from lucabot.ekran_isleyici import firma_isle
        from lucabot.ortak import AYAR
        sahte_luca.sifirla()
        AYAR.update(azami_saniye=120, durgunluk_saniye=60, indirme_saniye=15)
        araliklar = tarih_araliklari(tarih_cozumle("01/08/2026"), tarih_cozumle("05/08/2026"))
        sonuc = firma_isle(self.page, "AKIN COBAN", "e-arsiv-interaktif", araliklar, self.klasor,
                           self.klasor / "calisma.log")
        self.assertTrue(any(d.startswith("liste") for d in sonuc["dosyalar"]), sonuc["dosyalar"])
        self.assertEqual(sonuc["fatura_sayisi"], 4)
        self.assertTrue(all(len(f) == 3 and f[2] for f in sonuc["faturalar"]))  # tutarlar dolu


    def test_turmob_ekraninda_turmobdan_getir_dugmesi_taninir(self):
        """TÜRMOB ekranlarinda sorgu dugmesi 'TÜRMOB'dan Getir'; ekran acilmadi sanilmamali."""
        from lucabot.ekran_isleyici import firma_isle
        from lucabot.ortak import AYAR
        sahte_luca.sifirla()
        AYAR.update(azami_saniye=120, durgunluk_saniye=60, indirme_saniye=15)
        araliklar = tarih_araliklari(tarih_cozumle("01/08/2026"), tarih_cozumle("05/08/2026"))
        sonuc = firma_isle(self.page, "AKIN COBAN", "turmob-alis", araliklar, self.klasor,
                           self.klasor / "calisma.log")
        self.assertNotEqual(sonuc["durum"], "ekran acilmadi", sonuc)
        self.assertEqual(sonuc["fatura_sayisi"], 3)
        self.assertEqual(sonuc["durum"], "tamam")

    def test_firma_listesi_gec_gelirse_beklenir(self):
        """Giristen hemen sonra firma listesi henuz yoksa gece calismasi cokmemeli, liste gelince devam etmeli."""
        from lucabot.luca_gezinme import firma_secici, firma_secici_bekle
        self.page.set_content("""<div id="k">yukleniyor</div><script>setTimeout(() => {
          const s = document.createElement('select');
          for (let i = 1; i <= 8; i++) { const o = document.createElement('option'); o.text = 'FIRMA ' + i; s.add(o); }
          document.body.appendChild(s); }, 2500);</script>""")
        with self.assertRaises(LookupError):
            firma_secici(self.page)               # eskiden dogrudan boyle dusuyordu
        _, _, firmalar = firma_secici_bekle(self.page, sure=15000)
        self.assertEqual(len(firmalar), 8)

    def test_musteri_listesi_luca_menusunden_okunur(self):
        """Yönetici > Müşteri İşlemleri > Müşteri Listesi > Filtre > Yıl=2026 > Ara; yalniz 2026 firmalari gelir."""
        from lucabot import musteri_listesi
        kayitlar = musteri_listesi.listeyi_oku(self.page, 2026, self.klasor / "tani", None, bekleme_ms=15000)
        adlar = [k["ad"] for k in kayitlar]
        self.assertEqual(adlar, ["AKIN COBAN", "DENTAL SAGLIK", "FATURASIZ AS", "KEREM TICARET",
                                 "MERT INSAAT", "YENI FIRMA LTD", "NUMARASIZ KISI"])   # ESKI DONEM LTD 2025'te
        self.assertEqual(musteri_listesi.toplam_kayit(self.page), len(kayitlar))
        kerem = next(k for k in kayitlar if k["ad"] == "KEREM TICARET")
        self.assertEqual((kerem["kapanis"], kerem["acilis"], kerem["vkn"]),
                         ("28/02/2026", "01/01/2019", "5555555555"))
        self.assertEqual(kerem["vergi_dairesi"], "ÜMRANİYE VERGİ DAİRESİ")
        self.assertTrue(list((self.klasor / "tani").glob("musteri-listesi*.png")))
        # kaydet / oku
        yol = self.klasor / musteri_listesi.MUSTERI_LISTESI_DOSYASI
        musteri_listesi.kaydet(yol, 2026, kayitlar)
        self.assertEqual(musteri_listesi.oku(yol), (2026, kayitlar))

    def test_beyanname_kontrolden_pdfler_alinir(self):
        """Menu taranip Beyanname Kontrol bulunur; yalniz KDV1'in onayli PDF'leri (sekmede acilan ya da inen) kaydedilir."""
        from lucabot import luca_beyanname
        adlar = {"1111111111": "AKIN COBAN", "5555555555": "KEREM TICARET"}
        yollar, alinamayan = luca_beyanname.ekrandan_al(
            self.page, self.klasor / "pdf", self.klasor / "tani", adlar, None, None)
        adlari = sorted(y.name for y in yollar)
        self.assertEqual(adlari[0], "AKIN COBAN_1111111111_KDV1_2026-08_1.pdf")
        self.assertEqual(adlari[1], "KEREM TICARET_5555555555_KDV1_2026-08_1.pdf")
        self.assertTrue(adlari[2].startswith("MERT "), adlari)      # listede yok: satirdaki ad
        self.assertEqual(len(yollar), 3)                      # KDV2 sutunu ve Tahakkuk tiklanmadi
        self.assertEqual(alinamayan, [])
        for y in yollar:
            self.assertTrue(y.read_bytes().startswith(b"%PDF"))
            self.assertNotIn(b"yanlis", y.read_bytes())
        self.assertEqual(len(self.ctx.pages), 1)              # acilan PDF sekmeleri kapandi
        self.assertTrue(list((self.klasor / "tani").glob("beyanname-kontrol*.png")))

    def test_beyanname_menu_yolu_ayardan_izlenir(self):
        from lucabot import luca_beyanname
        self.assertTrue(luca_beyanname.ekrani_ac(self.page, "Denetim/Analiz > Beyanname Kontrol"))

    def test_musteri_listesi_baska_yil(self):
        from lucabot import musteri_listesi
        kayitlar = musteri_listesi.listeyi_oku(self.page, 2025, self.klasor / "tani", None, bekleme_ms=15000)
        self.assertIn("ESKI DONEM LTD", [k["ad"] for k in kayitlar])
        self.assertNotIn("YENI FIRMA LTD", [k["ad"] for k in kayitlar])

    def test_gizli_sekmelerdeki_cerceveler_taranmaz(self):
        """Luca'nin gizli sekmelerinde biriken eski ekranlar aramaya girmemeli."""
        from lucabot.luca_ekran import cerceveler, gorunur_mu
        gizli = "".join(f'<iframe srcdoc="<button>GİB den Getir {i}</button>"></iframe>' for i in range(4))
        acik = '<iframe srcdoc="<button>Aktif ekran</button>"></iframe>'
        self.page.set_content(f'<div style="display:none">{gizli}</div><div>{acik}</div>')
        self.page.wait_for_timeout(300)
        self.assertEqual(len(self.page.frames), 6)
        self.assertEqual(len(cerceveler(self.page)), 2)  # ana cerceve + gorunur sekme
        self.assertTrue(gorunur_mu(self.page, "Aktif ekran", sure=500))
        self.assertFalse(gorunur_mu(self.page, "GİB den Getir 1", sure=500))


    def _sure(self, f, *a, **k):
        import time
        basla = time.monotonic()
        sonuc = f(*a, **k)
        return sonuc, time.monotonic() - basla

    def test_duz_bildirim_hizli_gecilir(self):
        """Dugmesiz bildirim ("Fatura bulunamadi.") icin olmayan 'Tamam' aranmaz (eskiden ~4,5 sn)."""
        from lucabot.luca_ekran import (acik_pencere, acik_pencereleri_kapat,
                                        bilgi_penceresini_kapat, fatura_yok_penceresini_kapat)
        toast = ('<div class="luca-open-window" style="position:fixed;right:10px;bottom:10px;'
                 'width:200px;height:40px">%s</div>')
        self.page.set_content(toast % "Fatura bulunamadı.")
        self.assertIsNone(acik_pencere(self.page)[1])  # kapatilacak pencere degil
        sonuc, sure = self._sure(acik_pencereleri_kapat, self.page)
        self.assertTrue(sonuc)
        self.assertLess(sure, 0.5)
        sonuc, sure = self._sure(fatura_yok_penceresini_kapat, self.page)
        self.assertTrue(sonuc)
        self.assertLess(sure, 2.0)
        self.page.set_content(toast % "3 adet fatura bulundu. (Sayfa No: 1)")
        sonuc, sure = self._sure(bilgi_penceresini_kapat, self.page)
        self.assertIn("3 adet fatura bulundu", sonuc)
        self.assertLess(sure, 2.0)

    def test_gercek_pencereler_eskisi_gibi_kapanir(self):
        """Duz bildirim ayrimi, dugmeli pencereleri kapatmayi bozmamali."""
        from lucabot.luca_ekran import acik_pencere, acik_pencereleri_kapat, fatura_yok_penceresini_kapat
        takip = ('<div class="luca-open-window" style="width:300px;height:80px"><b>İşlem Takip</b>'
                 '<label><input type=checkbox>Otomatik aşağı kaydır</label>'
                 '<button onclick="this.parentNode.remove()">Kapat</button></div>')
        self.page.set_content(takip)
        self.assertIsNotNone(acik_pencere(self.page)[1])
        self.assertTrue(acik_pencereleri_kapat(self.page))
        self.assertEqual(self.page.locator(".luca-open-window").count(), 0)
        # "Tamam" dugmesi yazinin bulundugu kutunun disinda
        self.page.set_content('<div class="luca-open-window" style="width:300px;height:80px"><div>'
                              '<span>Her hangi bir fatura bulunamadı.</span></div>'
                              '<button onclick="this.parentNode.remove()">Tamam</button></div>')
        self.assertTrue(fatura_yok_penceresini_kapat(self.page))
        self.assertEqual(self.page.locator(".luca-open-window").count(), 0)
        # dugmesi bir tiklama olayiyla tanimlanmis pencere de kapatilacak pencere sayilir
        self.page.set_content('<div class="luca-open-window" style="width:300px;height:60px">Emin misiniz?'
                              ' <span onclick="this.parentNode.remove()">X</span></div>')
        self.assertIsNotNone(acik_pencere(self.page)[1])

    def _bildirim_sayfasi(self, js=""):
        self.page.set_content('<div id="b" class="luca-open-window" style="position:fixed;right:10px;'
                              'bottom:10px;width:260px;height:40px">3 adet fatura bulundu. (Sayfa No: 1)</div>'
                              '<script>%s</script>' % js)

    def test_sorgudan_once_kalan_bildirim_bitis_sayilmaz(self):
        """Onceki araligin bildirimi ekranda duruyorsa yeni sorgu 1 sn'de bitmis sanilmamali."""
        from lucabot.gib_sorgu import islem_takibini_bekle
        from lucabot.luca_ekran import bildirim_yazisi
        self._bildirim_sayfasi()
        eski = bildirim_yazisi(self.page)
        self.assertIn("3 adet", eski)
        sonuc, sure = self._sure(islem_takibini_bekle, self.page, None, pencere_bekleme=3,
                                 eski_bildirim=eski)
        self.assertEqual(sonuc, 0)
        self.assertGreaterEqual(sure, 3.0)  # bildirim bitis sayilmadi, pencere_bekleme beklendi
        # eski bildirim goruldugunde bekleme ESKI_BILDIRIM_BEKLEME_SANIYE ile sinirli (12 sn'nin tamami degil)
        sonuc, sure = self._sure(islem_takibini_bekle, self.page, None, pencere_bekleme=12,
                                 eski_bildirim=eski)
        self.assertEqual(sonuc, 0)
        self.assertGreaterEqual(sure, 5.0)
        self.assertLess(sure, 8.0)
        self.assertEqual(self.page.locator("#b").count(), 1)  # bildirim kapatilmaya calisilmadi

    def test_yeni_sorgunun_bildirimi_hemen_bitis_sayilir(self):
        from lucabot.gib_sorgu import islem_takibini_bekle
        self._bildirim_sayfasi()
        sonuc, sure = self._sure(islem_takibini_bekle, self.page, None, pencere_bekleme=10,
                                 eski_bildirim="")
        self.assertEqual(sonuc, 0)
        self.assertLess(sure, 4.0)

    def test_eski_bildirim_kaybolup_yeniden_cikarsa_bitis_sayilir(self):
        from lucabot.gib_sorgu import islem_takibini_bekle
        from lucabot.luca_ekran import bildirim_yazisi
        self._bildirim_sayfasi("""
          const b = document.getElementById('b'), metin = b.textContent;
          setTimeout(() => b.remove(), 600);
          setTimeout(() => { const y = document.createElement('div'); y.id = 'b2';
            y.className = 'luca-open-window'; y.style.cssText = 'position:fixed;right:10px;bottom:10px;width:260px;height:40px';
            y.textContent = metin; document.body.appendChild(y); }, 2200);""")
        eski = bildirim_yazisi(self.page)
        sonuc, sure = self._sure(islem_takibini_bekle, self.page, None, pencere_bekleme=12,
                                 eski_bildirim=eski)
        self.assertEqual(sonuc, 0)
        self.assertGreaterEqual(sure, 2.0)   # yeniden cikana kadar beklendi
        self.assertLess(sure, 6.0)           # pencere_bekleme (12 sn) dolmadan bitirildi

    def test_islem_takip_satiri_fatura_yok_uyarisi_sanilmaz(self):
        """Sorgu surerken Islem Takip'e dusen 'fatura bulunamadi' satiri sorguyu bitirmemeli."""
        from lucabot.luca_ekran import bilgi_penceresini_kapat, fatura_yok_penceresini_kapat
        takip = ('<div class="luca-open-window" style="width:600px;height:200px"><b>İşlem Takip</b>'
                 '<div>[71/82] EF02026000000588 numaralı belge sistemde kayıtlıdır.</div>'
                 '<div style="color:red">Sorgulama Tarihi: 26/09/2026 Hata mesajı: Belirtilen tarih'
                 ' aralığında fatura bulunamadı. Bu hata GİB servislerinden alınmıştır.</div>'
                 '<label><input type=checkbox>Otomatik aşağı kaydır</label><button>Kapat</button></div>')
        uyari = ('<div class="luca-open-window" style="width:300px;height:80px">'
                 '<span>Her hangi bir fatura bulunamadı.</span><button>Tamam</button></div>')
        self.page.set_content(takip)
        self.assertFalse(fatura_yok_penceresini_kapat(self.page))
        self.assertEqual(bilgi_penceresini_kapat(self.page), "")
        self.page.set_content(takip + uyari)  # gercek uyari yine yakalanir
        self.assertTrue(fatura_yok_penceresini_kapat(self.page))

    def test_gizli_pencere_ilk_siradayken_acik_pencere_bulunur(self):
        """Sayfada gizli bir .luca-open-window once gelse de acik olan bulunmali."""
        from lucabot.luca_ekran import acik_pencere
        self.page.set_content('<div class="luca-open-window" style="display:none">eski</div>'
                              '<div class="luca-open-window" style="width:200px;height:80px">'
                              'GİB\'den Getir <input value="01/09/2026"></div>')
        _, pencere = acik_pencere(self.page)
        self.assertIsNotNone(pencere)
        self.assertIn("Getir", pencere.inner_text())
        self.page.set_content('<div class="luca-open-window" style="display:none">eski</div>')
        self.assertIsNone(acik_pencere(self.page)[1])

    def _excel_sekmesi_dene(self, sekmesiz):
        from lucabot.ekran_isleyici import firma_isle
        from lucabot.ortak import AYAR
        sahte_luca.sifirla()
        AYAR.update(azami_saniye=120, durgunluk_saniye=60, indirme_saniye=15,
                    indirme_sekmesiz=sekmesiz)
        acilan = []

        def yeni_sekme(sekme):
            acilan.append(sekme)

        self.ctx.on("page", yeni_sekme)
        try:
            araliklar = tarih_araliklari(tarih_cozumle("01/08/2026"), tarih_cozumle("05/08/2026"))
            sonuc = firma_isle(self.page, "AKIN COBAN", "e-arsiv-alis", araliklar, self.klasor,
                               self.klasor / "calisma.log")
        finally:
            self.ctx.remove_listener("page", yeni_sekme)
            AYAR["indirme_sekmesiz"] = True
        self.assertIn("liste_faturalar.xlsx", sonuc["dosyalar"])
        self.assertEqual(sonuc["fatura_sayisi"], 3)
        self.assertEqual(len(self.ctx.pages), 1)  # yalnizca Luca sekmesi kaldi
        return acilan

    def test_excel_icin_bos_sekme_acilmaz(self):
        """Luca Excel'i yeni sekmede aciyor; bot bunu gizli cerceveye cevirir, sekme hic acilmaz."""
        self.assertEqual(self._excel_sekmesi_dene(True), [])

    def test_bos_sekme_ve_target_blank_gizli_cerceveye_gider(self):
        """Indirme sirasinda window.open('', ad) ve target=_blank form de sekme acmamali."""
        from lucabot.indirme import _DosyaYakalayici
        self.page.set_content(
            '<form id="f" action="%s/api/zip-durumu" target="_blank" method="get">'
            '<button id="g" type="submit">Gonder</button></form>'
            '<button id="o" onclick="window.open(\'\', \'hedefAd\')">Ac</button>' % self.adres)
        with _DosyaYakalayici(self.page, "t", True) as yakalayici:
            self.page.click("#g")
            self.page.click("#o")
            self.page.wait_for_timeout(800)
            self.assertEqual(len(self.ctx.pages), 1)                      # yeni sekme yok
            self.assertEqual(self.page.locator("iframe[name=hedefAd]").count(), 1)
            self.assertGreaterEqual(self.page.locator("iframe").count(), 2)
        self.assertEqual(self.page.locator("iframe").count(), 0)          # cikista temizlenir
        self.assertEqual(yakalayici.acilanlar, [])
        self.assertEqual(len(self.ctx.pages), 1)

    def test_excel_icin_acilan_sekme_kapanir(self):
        """Sekmesiz yol kapaliyken (ayar) acilan sekme dosya alininca kapanmali."""
        self.assertEqual(len(self._excel_sekmesi_dene(False)), 1)


    def test_yavas_excel_beklenir_ikinci_istek_gitmez(self):
        """Luca Excel'i 70 sn'de hazirlasa da beklenir; kisayolla ikinci Excel istenmez."""
        from lucabot.ekran_isleyici import firma_isle
        from lucabot.ortak import AYAR
        sahte_luca.sifirla()
        sahte_luca.SAYAC["excel_gecikme"] = 70
        AYAR.update(azami_saniye=120, durgunluk_saniye=60, indirme_saniye=15)
        araliklar = tarih_araliklari(tarih_cozumle("01/08/2026"), tarih_cozumle("05/08/2026"))
        log = self.klasor / "calisma.log"
        sonuc = firma_isle(self.page, "AKIN COBAN", "e-fatura-alis", araliklar, self.klasor, log)
        self.assertEqual(sonuc["durum"], "tamam")
        self.assertIn("liste_faturalar.xlsx", sonuc["dosyalar"])
        self.assertEqual(sahte_luca.SAYAC["excel"], 1)
        self.assertIn("hazirliyor", log.read_text(encoding="utf-8"))


    def test_ekran_acilmazsa_fatura_yok_denmez(self):
        """Ekranin kendi butonu hic gorunmediyse sonuc 'fatura yok' degil 'ekran acilmadi'."""
        from lucabot.ekran_isleyici import firma_isle
        from lucabot.ortak import AYAR, ekran_tamamlanmis_mi
        sahte_luca.sifirla()
        AYAR.update(azami_saniye=60, durgunluk_saniye=30, indirme_saniye=10)
        araliklar = tarih_araliklari(tarih_cozumle("01/08/2026"), tarih_cozumle("05/08/2026"))
        sonuc = firma_isle(self.page, "MERT INSAAT", "esmm-alis", araliklar, self.klasor,
                           self.klasor / "calisma.log")
        self.assertEqual(sonuc["durum"], "ekran acilmadi")
        self.assertFalse(ekran_tamamlanmis_mi(sonuc["durum"]))  # [D]evam'da tekrar denenir

    def test_zip_inmezse_tekrar_denenir(self):
        """Buton tepki vermezse (istek hic gitmez) belge paketi bir kez daha istenir."""
        from lucabot.ekran_isleyici import firma_isle
        from lucabot.ortak import AYAR
        sahte_luca.sifirla()
        sahte_luca.SAYAC["zip_basarisiz"] = 1
        AYAR.update(azami_saniye=120, durgunluk_saniye=60, indirme_saniye=15)
        araliklar = tarih_araliklari(tarih_cozumle("01/08/2026"), tarih_cozumle("05/08/2026"))
        log = self.klasor / "calisma.log"
        sonuc = firma_isle(self.page, "AKIN COBAN", "e-arsiv-alis", araliklar, self.klasor, log)
        self.assertEqual(sonuc["durum"], "tamam")
        self.assertTrue(any(d.startswith("belgeler_") for d in sonuc["dosyalar"]))
        self.assertFalse(sonuc.get("not"))
        self.assertIn("tekrar deneniyor", log.read_text(encoding="utf-8"))

    def test_zip_iki_denemede_de_inmezse_not_dusulur(self):
        """Iki denemede de gelmezse ekran yine tamam sayilir (Excel var) ama nota yazilir."""
        from lucabot.ekran_isleyici import firma_isle
        from lucabot.ortak import AYAR
        sahte_luca.sifirla()
        sahte_luca.SAYAC["zip_basarisiz"] = 99
        AYAR.update(azami_saniye=120, durgunluk_saniye=60, indirme_saniye=15)
        araliklar = tarih_araliklari(tarih_cozumle("01/08/2026"), tarih_cozumle("05/08/2026"))
        sonuc = firma_isle(self.page, "AKIN COBAN", "e-arsiv-alis", araliklar, self.klasor,
                           self.klasor / "calisma.log")
        self.assertEqual(sonuc["durum"], "tamam")
        self.assertFalse(any(d.startswith("belgeler_") for d in sonuc["dosyalar"]))
        self.assertIn("liste_faturalar.xlsx", sonuc["dosyalar"])
        self.assertIn("zip", sonuc["not"])


class LucaGirisTestleri(unittest.TestCase):
    """luca_giris.py: fatura botuyla ilgisi olmayan, tek tikla giris araci."""

    @classmethod
    def setUpClass(cls):
        cls.sunucu, cls.adres = sahte_luca.baslat()

    @classmethod
    def tearDownClass(cls):
        cls.sunucu.shutdown()

    def _calistir(self, ek_ayar=None):
        import json
        import subprocess
        kok = Path(__file__).resolve().parent.parent
        klasor = Path(tempfile.mkdtemp())
        ayar = {"giris_adresi": self.adres, "tarayici": "chromium",
               "tarayici_yolu": os.environ.get("LUCA_TEST_CHROMIUM", ""),
               "tarayici_sandbox": os.name == "nt", "profil_yerel": True}
        ayar.update(ek_ayar or {})
        (klasor / "ayarlar.json").write_text(json.dumps(ayar), encoding="utf-8")
        ortam = dict(os.environ, LUCA_BOT_AYAR=str(klasor / "ayarlar.json"),
                    LOCALAPPDATA=str(klasor / "yerel"), PYTHONIOENCODING="utf-8")
        return subprocess.Popen([sys.executable, str(kok / "luca_giris.py")], cwd=str(kok),
                                env=ortam, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True)

    def _cocuk_surecler(self, pid):
        import subprocess
        try:
            return subprocess.check_output(["pgrep", "-P", str(pid)]).decode().split()
        except subprocess.CalledProcessError:
            return []

    def test_giris_yapar_ve_tarayici_acik_kalir(self):
        p = self._calistir()
        try:
            cikti = ""
            basla = time.time()
            while time.time() - basla < 40 and "Giris tamam" not in cikti:
                cikti += p.stdout.readline()
            self.assertIn("Giris tamam", cikti)
            self.assertIn("Calisilan sayfa:", cikti)
            time.sleep(1)
            self.assertIsNone(p.poll())  # program hala calisiyor, tarayici acik
        finally:
            p.terminate()
            try:
                p.wait(timeout=10)
            except Exception:
                p.kill()

    def test_tarayici_kapaninca_program_da_kapanir(self):
        import signal
        p = self._calistir()
        try:
            cikti = ""
            basla = time.time()
            while time.time() - basla < 40 and "Giris tamam" not in cikti:
                cikti += p.stdout.readline()
            self.assertIn("Giris tamam", cikti)
            cocuklar = self._cocuk_surecler(p.pid)
            self.assertTrue(cocuklar, "tarayici sureci bulunamadi")
            for pid in cocuklar:
                os.kill(int(pid), signal.SIGTERM)
            self.assertEqual(p.wait(timeout=15), 0)
        finally:
            if p.poll() is None:
                p.kill()


if __name__ == "__main__":
    unittest.main()
