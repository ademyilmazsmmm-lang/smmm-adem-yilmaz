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


if __name__ == "__main__":
    unittest.main()
