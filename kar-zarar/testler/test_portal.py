# -*- coding: utf-8 -*-
"""Sahte Luca + sahte Defter Beyan ile tarayici testleri (tarayici acilamazsa atlanir).

    xvfb-run -a python -m unittest testler.test_portal -v    (Linux)
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sahte_kz as sahte_luca  # noqa: E402  (Luca taklidi + hesap plani + Defter Beyan)


class KarZararPortalTestleri(unittest.TestCase):
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

    def tearDown(self):
        self.ctx.close()

    def _db_adresi(self):
        from karzarar import defterbeyan
        sahte_luca.sifirla()
        eski, defterbeyan.ADRES = defterbeyan.ADRES, self.adres.rstrip("/")
        self.addCleanup(setattr, defterbeyan, "ADRES", eski)
        return defterbeyan

    def test_defter_beyan_hesap_ozeti_okunur(self):
        """Giris (guvenlik kodunu insan yazar), mukellef secimi, defter turu ve Mali Hesap Ozeti."""
        from datetime import date
        db = self._db_adresi()
        self.assertTrue(db.giris_yap(self.page, "kod", "sifre", bekle_saniye=30))
        self.assertEqual(db.mukellef_sec(self.page, "1111111111"), "İŞLETME")
        ozet = db.hesap_ozeti_oku(self.page, date(2026, 7, 1), date(2026, 8, 31))
        # 2 ay: hasilat 1.000.000, emtia alisi 200.000, gider 600.000
        self.assertEqual((ozet["satis"], ozet["mal_alis"], ozet["gider"], ozet["kar"]),
                         (1000000.0, 200000.0, 600000.0, 200000.0))
        db.mukelleften_cik(self.page)
        self.assertEqual(db.mukellef_sec(self.page, "2222222222"), "BİLANÇO")
        db.mukelleften_cik(self.page)
        self.assertIsNone(db.mukellef_sec(self.page, "6666666666"))   # Defter Beyan listesinde yok
        # farkli donem ayni mukellefte yeniden hesaplanir (onceki sonuc bayat sayilmaz)
        db.mukellef_sec(self.page, "5555555555")
        zarar = db.hesap_ozeti_oku(self.page, date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual((zarar["kar"], zarar["satis"]), (-50000.0, 200000.0))

    def test_defter_donemi_biten_mukellef_atlanir(self):
        """Defter donemi istenen donemden once bitmis (donem sonu var) mukellef hata degil, atlanir."""
        from datetime import date
        db = self._db_adresi()
        self.assertTrue(db.giris_yap(self.page, "kod", "sifre", bekle_saniye=30))
        self.assertEqual(db.mukellef_sec(self.page, "8888888888"), "İŞLETME")
        with self.assertRaises(db.DonemDisi):
            db.hesap_ozeti_oku(self.page, date(2026, 7, 1), date(2026, 8, 31))
        db.mukelleften_cik(self.page)
        # donem ici hesap ozeti normal mukellefte hala okunur
        self.assertEqual(db.mukellef_sec(self.page, "1111111111"), "İŞLETME")
        self.assertEqual(db.hesap_ozeti_oku(self.page, date(2026, 7, 1), date(2026, 8, 31))["kar"], 200000.0)

    def test_luca_hesap_plani_kar_zarar(self):
        from datetime import date
        from karzarar import luca_hesap_plani
        from lucabot.luca_gezinme import firma_sec
        firma_sec(self.page, "DENTAL SAGLIK")
        r = luca_hesap_plani.hesap_plani_oku(self.page, date(2026, 7, 1), date(2026, 8, 31),
                                             self.klasor / "tani")
        # aylik 100.000 gelir, 20.000 mal alisi (153), 30.000 gider (7'li); 2 ay
        self.assertEqual((r["satis"], r["mal_alis"], r["gider"], r["kar"]),
                         (200000.0, 40000.0, 60000.0, 100000.0))

    def test_mizan_excel_ile_kar_zarar(self):
        """Luca'da tutarlar Mizan Excel'inden; hesap planiyla ayni sonuc. Mizan alinamazsa Hesap Plani'na donulur."""
        from datetime import date
        from unittest import mock
        from karzarar import hesaplama, luca_mizan
        bas, bit = date(2026, 7, 1), date(2026, 8, 31)
        sonuclar = {}
        hesaplama.luca_asamasi(self.page, ["DENTAL SAGLIK", "MERT INSAAT"], bas, bit, sonuclar, {},
                               self.klasor / "tani", lambda: None, None, kaynak="mizan")
        self.assertEqual({f: (s["kar"], s["kaynak"]) for f, s in sonuclar.items()},
                         {"DENTAL SAGLIK": (100000.0, "Luca (Mizan)"), "MERT INSAAT": (-30000.0, "Luca (Mizan)")})
        self.assertEqual(sonuclar["DENTAL SAGLIK"]["toplam_gider"], 100000.0)   # mal alisi 40.000 + gider 60.000
        self.assertTrue((self.klasor / "mizan" / "mizan_DENTAL SAGLIK.xlsx").exists())
        # Mizan alinamazsa (orn. dugme/indirme sorunu) Hesap Plani'ndan okunur
        sonuclar2 = {}
        with mock.patch.object(luca_mizan, "mizan_oku", side_effect=LookupError("indirilemedi")):
            hesaplama.luca_asamasi(self.page, ["DENTAL SAGLIK"], bas, bit, sonuclar2, {}, self.klasor / "tani",
                                   lambda: None, None, kaynak="mizan")
        self.assertEqual((sonuclar2["DENTAL SAGLIK"]["kar"], sonuclar2["DENTAL SAGLIK"]["kaynak"]),
                         (100000.0, "Luca (Hesap Planı)"))

    def test_kar_zarar_iki_asama(self):
        """Isletme firmalari Defter Beyan'dan, Defter Beyan'da olmayan/bilanco firmalar Luca'dan."""
        from datetime import date
        from karzarar import hesaplama as kar_zarar
        self._db_adresi()
        firmalar = ["ALFA ISLETME", "DENTAL SAGLIK", "KEREM TICARET", "MERT INSAAT", "ESKI DONEM LTD"]
        vkn = {"ALFA ISLETME": "1111111111", "DENTAL SAGLIK": "2222222222", "KEREM TICARET": "5555555555",
               "MERT INSAAT": "6666666666"}   # ESKI DONEM LTD'nin VKN'si yok
        sonuclar, kayitlar = {}, []
        bas, bit = date(2026, 7, 1), date(2026, 8, 31)
        gidecek = kar_zarar.defter_beyan_asamasi(
            self.ctx.new_page(), {}, firmalar, vkn, bas, bit, sonuclar, lambda: kayitlar.append(1), None)
        self.assertEqual(gidecek, ["DENTAL SAGLIK", "MERT INSAAT", "ESKI DONEM LTD"])
        self.assertEqual({f: s["kar"] for f, s in sonuclar.items()},
                         {"ALFA ISLETME": 200000.0, "KEREM TICARET": -100000.0})
        kar_zarar.luca_asamasi(self.page, gidecek, bas, bit, sonuclar, vkn, self.klasor / "tani",
                               lambda: kayitlar.append(1), None)
        self.assertEqual({f: (s["kar"], s["kaynak"]) for f, s in sonuclar.items()},
                         {"ALFA ISLETME": (200000.0, "Defter Beyan"), "KEREM TICARET": (-100000.0, "Defter Beyan"),
                          "DENTAL SAGLIK": (100000.0, "Luca (Hesap Planı)"),
                          "MERT INSAAT": (-30000.0, "Luca (Hesap Planı)"),
                          "ESKI DONEM LTD": (40000.0, "Luca (Hesap Planı)")})
        self.assertTrue(kayitlar)   # her firmadan sonra kaydedildi


if __name__ == "__main__":
    unittest.main()
