# -*- coding: utf-8 -*-
"""Lisans (imza, tarih, saat geriye alma, dosya kurma) testleri."""

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lucabot import lisans  # noqa: E402

TOHUM = bytes(range(32))
ACIK = lisans.acik_anahtar_uret(TOHUM).hex()


class LisansTest(unittest.TestCase):
    def setUp(self):
        self.klasor = Path(tempfile.mkdtemp())
        self.dosya = self.klasor / "lisans.json"
        self.durum_dosyasi = self.klasor / "lisans-durum.json"
        for ad, deger in (("LISANS_DOSYASI", self.dosya), ("DURUM_DOSYASI", self.durum_dosyasi)):
            y = mock.patch.object(lisans, ad, deger)
            y.start()
            self.addCleanup(y.stop)

    def yaz(self, sahip="Test SMMM", bas="2026-01-01", bit="2026-12-31", dosya=None):
        veri = lisans.lisans_olustur(TOHUM, sahip, bas, bit)
        (dosya or self.dosya).write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
        return veri

    def d(self, bugun, **kw):
        return lisans.durum(bugun=bugun, acik=ACIK, **kw)

    def test_gecerli_lisans(self):
        self.yaz()
        d = self.d(date(2026, 6, 15))
        self.assertTrue(d["gecerli"], d["mesaj"])
        self.assertEqual(d["sahip"], "Test SMMM")
        self.assertEqual(d["kalan_gun"], 199)
        self.assertEqual(d["uyari"], "")

    def test_bitis_gunu_gecerli_ertesi_gun_degil(self):
        self.yaz()
        self.assertTrue(self.d(date(2026, 12, 31))["gecerli"])
        d = self.d(date(2027, 1, 1))
        self.assertFalse(d["gecerli"])
        self.assertIn("doldu", d["mesaj"])

    def test_son_30_gunde_uyari(self):
        self.yaz()
        d = self.d(date(2026, 12, 10))
        self.assertTrue(d["gecerli"])
        self.assertIn("21 gün", d["uyari"])

    def test_baslamamis_lisans(self):
        self.yaz(bas="2027-01-01", bit="2027-12-31")
        self.assertFalse(self.d(date(2026, 10, 7))["gecerli"])

    def test_tarih_elle_degistirilirse_imza_bozulur(self):
        veri = self.yaz()
        veri["bitis"] = "2030-12-31"
        self.dosya.write_text(json.dumps(veri), encoding="utf-8")
        d = self.d(date(2026, 6, 1))
        self.assertFalse(d["gecerli"])
        self.assertIn("imza", d["mesaj"])

    def test_baska_anahtarla_imzali_lisans_gecersiz(self):
        veri = lisans.lisans_olustur(bytes(reversed(range(32))), "Sahte", "2026-01-01", "2099-12-31")
        self.dosya.write_text(json.dumps(veri), encoding="utf-8")
        self.assertFalse(self.d(date(2026, 6, 1))["gecerli"])

    def test_dosya_yok_ya_da_bozuk(self):
        self.assertFalse(self.d(date(2026, 6, 1))["gecerli"])
        self.dosya.write_text("{bozuk", encoding="utf-8")
        self.assertFalse(self.d(date(2026, 6, 1))["gecerli"])
        self.dosya.write_text(json.dumps({"urun": "Dijital Stajyer"}), encoding="utf-8")
        self.assertIn("bozuk", self.d(date(2026, 6, 1))["mesaj"])

    def test_saat_geriye_alinirsa_reddedilir(self):
        self.yaz()
        self.assertTrue(self.d(date(2026, 11, 20))["gecerli"])
        d = self.d(date(2026, 3, 1))  # bilgisayar saati geri alindi
        self.assertFalse(d["gecerli"])
        self.assertIn("geriye", d["mesaj"])
        self.assertTrue(self.d(date(2026, 11, 20))["gecerli"])  # dogru tarihe donunce yine calisir

    def test_kur_gecerli_dosyayi_kopyalar_bozugu_reddeder(self):
        kaynak = self.klasor / "yeni.json"
        self.yaz(sahip="Yeni Sahip", dosya=kaynak)
        tamam, _ = lisans.kur(kaynak, acik=ACIK)
        self.assertTrue(tamam)
        self.assertEqual(self.d(date(2026, 6, 1))["sahip"], "Yeni Sahip")
        bozuk = self.klasor / "bozuk.json"
        bozuk.write_text(json.dumps({**json.loads(kaynak.read_text(encoding="utf-8")), "bitis": "2099-01-01"}),
                         encoding="utf-8")
        tamam, mesaj = lisans.kur(bozuk, acik=ACIK)
        self.assertFalse(tamam)
        self.assertIn("geçersiz", mesaj)

    def test_ed25519_resmi_test_vektoru(self):
        # RFC 8032 7.1, TEST 1 (bos mesaj)
        tohum = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
        acik = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        imza = bytes.fromhex("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
                             "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
        self.assertEqual(lisans.acik_anahtar_uret(tohum), acik)
        self.assertEqual(lisans.imzala(tohum, b""), imza)
        self.assertTrue(lisans.imza_gecerli_mi(acik, b"", imza))
        self.assertFalse(lisans.imza_gecerli_mi(acik, b"x", imza))

    def test_arac_uret_ve_kontrol(self):
        import lisans_araci
        anahtar = self.klasor / "anahtar.txt"
        anahtar.write_text(TOHUM.hex(), encoding="ascii")
        cikti = self.klasor / "uretilen.json"
        lisans_araci.main(["uret", "--anahtar", str(anahtar), "--sahip", "Ali Veli, SMMM", "--cikti", str(cikti)])
        veri = json.loads(cikti.read_text(encoding="utf-8"))
        self.assertEqual((veri["lisans_sahibi"], veri["bitis"]), ("Ali Veli, SMMM", "2026-12-31"))
        self.assertTrue(lisans._dogrula(veri, ACIK)[0])


if __name__ == "__main__":
    unittest.main()
