# -*- coding: utf-8 -*-
"""Tarayici gerektirmeyen birim testleri.

    python -m unittest discover -s testler -v
"""

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))


class KarZararTestleri(unittest.TestCase):
    """Defter Beyan hesap ozeti ve Luca hesap plani listesinden kar/zarar hesabi."""

    def test_defter_beyan_ozeti_cozumlenir(self):
        from karzarar.defterbeyan import hesap_ozeti_cozumle
        giderler = [["GİDERLER", "TUTAR"], ["Dönem Başı Emtia Mevcudu", "0,00"],
                    ["Dönem İçinde Satın Alınan Emtia", "10.000,00"], ["Giderler", "972.994,06"],
                    ["Amortisman Giderleri", "500,00"], ["Kar", "122.663,79"], ["Genel Toplam", "1.095.657,85"]]
        gelirler = [["GELİRLER", "TUTAR"], ["Dönem Sonu Emtia Mevcudu", ""],
                    ["Dönem İçinde Elde Edilen Hasılat", "1.095.657,85"], ["Gelir Diğer Gelirler", "0,00"],
                    ["-", ""], ["Zarar", "0,00"], ["Genel Toplam", "1.095.657,85"]]
        o = hesap_ozeti_cozumle([(0, giderler), (0, gelirler)])
        self.assertEqual((o["satis"], o["mal_alis"], o["gider"], o["kar"]),
                         (1095657.85, 10000.0, 973494.06, 122663.79))
        gelirler[5] = ["Zarar", "5.000,00"]
        giderler[5] = ["Kar", "0,00"]
        self.assertEqual(hesap_ozeti_cozumle([(0, giderler), (0, gelirler)])["kar"], -5000.0)
        self.assertIsNone(hesap_ozeti_cozumle([(0, [["a", "b"]])]))

    def test_defter_turu_ustbilgiden(self):
        from karzarar.defterbeyan import defter_turu, isletme_mi
        metin = "ADEM MERGEN adına işlem yapmaktasınız.\n6170780106 - İŞLETME Güvenli Çıkış"
        self.assertEqual(defter_turu(metin, "6170780106"), "İŞLETME")
        self.assertTrue(isletme_mi("İŞLETME"))
        self.assertFalse(isletme_mi("BİLANÇO"))
        self.assertEqual(defter_turu("9660268213 - SMK", "6170780106"), "")

    BASLIK = ["Hesap Kodu", "Hesap Adı", "Tipi", "Borç", "Alacak", "Borç Bakiyesi", "Alacak Bakiyesi", "B/A", "Birim"]

    def _tablo(self, satirlar):
        return [(0, [self.BASLIK] + [list(s) for s in satirlar])]

    def test_hesap_plani_kar_zarar(self):
        from karzarar.luca_hesap_plani import hesap_satirlari, kar_zarar
        t = self._tablo([
            ("1", "DÖNEN VARLIKLAR", "Ana", "40.000,00", "0,00", "40.000,00", "0,00", "B", ""),
            ("153", "TİCARİ MALLAR", "Ana", "40.000,00", "0,00", "40.000,00", "0,00", "B", ""),
            ("153.01", "ALINAN", "Alt", "40.000,00", "0,00", "40.000,00", "0,00", "B", ""),
            ("6", "GELİR", "Ana", "1.000,00", "201.000,00", "0,00", "200.000,00", "A", ""),
            ("600", "YURTİÇİ", "Ana", "0,00", "201.000,00", "0,00", "201.000,00", "A", ""),
            ("7", "MALİYET", "Ana", "60.000,00", "0,00", "60.000,00", "0,00", "B", ""),
            ("770", "GENEL YÖNETİM", "Ana", "60.000,00", "0,00", "60.000,00", "0,00", "B", "")])
        r = kar_zarar(hesap_satirlari(t))
        self.assertEqual((r["satis"], r["mal_alis"], r["gider"], r["kar"]), (200000.0, 40000.0, 60000.0, 100000.0))

    def test_hesap_plani_sinif_satiri_yoksa_alt_duzeyden_toplanir(self):
        from karzarar.luca_hesap_plani import hesap_satirlari, kar_zarar
        t = self._tablo([
            ("60", "BRÜT SATIŞLAR", "Ana", "0,00", "30.000,00", "0,00", "30.000,00", "A", ""),
            ("600", "YURTİÇİ", "Ana", "0,00", "30.000,00", "0,00", "30.000,00", "A", ""),
            ("770", "GENEL YÖNETİM", "Ana", "5.000,00", "0,00", "5.000,00", "0,00", "B", ""),
            ("153.01", "ALINAN", "Alt", "8.000,00", "0,00", "8.000,00", "0,00", "B", ""),
            ("153.02", "ALINAN2", "Alt", "2.000,00", "0,00", "2.000,00", "0,00", "B", "")])
        r = kar_zarar(hesap_satirlari(t))
        self.assertEqual((r["satis"], r["mal_alis"], r["gider"], r["kar"]), (30000.0, 10000.0, 5000.0, 15000.0))
        self.assertEqual(kar_zarar([])["kar"], 0.0)

    def test_hesap_plani_basliksiz_ve_kayik_satir(self):
        from karzarar.luca_hesap_plani import hesap_satirlari
        # basliksiz: ilk iki sayi Borç ve Alacak; satir basinda fazladan hucre
        s = hesap_satirlari([(0, [["", "600", "SATIŞ", "Ana", "1,00", "2.500,00", "0,00", "2.500,00", "A", ""]])])
        self.assertEqual((s[0]["kod"], s[0]["borc"], s[0]["alacak"]), ("600", 1.0, 2500.0))
        s = hesap_satirlari([(0, [["x"], ["Başlık"]])])
        self.assertEqual(s, [])

    def test_vkn_haritasi_ve_kayit(self):
        from karzarar import hesaplama as kar_zarar
        kayitlar = [{"ad": "AKIN COBAN", "unvan": "AKIN ÇOBAN", "vkn": "1111111111", "tc": "1"},
                    {"ad": "GERCEK KISI", "unvan": "GERÇEK KİŞİ", "vkn": "", "tc": "22222222222"},
                    {"ad": "NUMARASIZ", "unvan": "NUMARASIZ", "vkn": "", "tc": ""}]
        self.assertEqual(kar_zarar.vkn_haritasi(["AKIN ÇOBAN", "GERCEK KISI", "NUMARASIZ", "YOK"], kayitlar),
                         {"AKIN ÇOBAN": "1111111111", "GERCEK KISI": "22222222222"})
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "kz.json"
            kar_zarar.kaydet(yol, date(2026, 7, 1), date(2026, 8, 31), {"A": {"firma": "A", "kar": 5.0}})
            self.assertEqual(kar_zarar.oku(yol), ("01/07/2026-31/08/2026", [{"firma": "A", "kar": 5.0}]))
            with self.assertRaises(ValueError):
                kar_zarar.oku(Path(d) / "yok.json")


if __name__ == "__main__":
    unittest.main()
