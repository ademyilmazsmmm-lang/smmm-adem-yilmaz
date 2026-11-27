import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import muavin_ara as ma  # noqa: E402


def muavin_yaz(yol, satirlar):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["191 İNDİRİLECEK KDV"])
    ws.append(["Tarih", "Fiş No", "Açıklama", "Borç", "Alacak"])
    for tarih, fis, acik, borc in satirlar:
        ws.append([tarih, fis, acik, borc, 0])
    wb.save(str(yol))


def isletme_yaz(yol, evrak, kdv):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["GİDERLER"])
    ws.append(["", "", "", "Gider", "İndirilecek KDV", "Toplam"])
    ws.append(["Kayıt No", "Tarih", "Evrak No", "Açıklama", "", ""])
    ws.append([1, date(2026, 10, 5), evrak, "mal alımı", kdv, kdv * 6])
    wb.save(str(yol))


class MuavinAraTestleri(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "2026-11-01" / "muavin" / "dosyalar").mkdir(parents=True)
        dos = self.d / "2026-11-01" / "muavin" / "dosyalar"
        muavin_yaz(dos / "muavin_FIRMA A.xlsx", [(date(2026, 10, 3), "7", "ABC2026000000111 nolu fatura", 100.0)])
        muavin_yaz(dos / "muavin_FIRMA B.xlsx", [(date(2026, 10, 4), "9", "XYZ2026000000222 alış", 50.5),
                                                  (date(2026, 10, 9), "10", "ABC2026000000333", 75.0)])
        isletme_yaz(dos / "isletme_defteri_FIRMA C.xlsx", "ABC2026000000111", 120.0)
        (dos / "baska.xlsx").write_bytes(b"x")

    def test_dosyalari_bul_firma_adi(self):
        adlar = [ma.dosya_firmasi(y) for y in ma.dosyalari_bul(self.d)]
        self.assertEqual(adlar, ["FIRMA A", "FIRMA B", "FIRMA C"])

    def test_fatura_no_hangi_firmada(self):
        s = ma.ara(ma.dosyalari_bul(self.d), nolar=["abc2026000000111"])
        self.assertEqual(sorted(x["firma"] for x in s), ["FIRMA A", "FIRMA C"])

    def test_tutar_ve_metin_ve_ozet(self):
        s = ma.ara(ma.dosyalari_bul(self.d), nolar=["ABC2026000000333", "XYZ2026000000222"], tutarlar=[75.0])
        ozet = ma.firma_ozeti(s, 2)
        self.assertEqual(ozet[0]["firma"], "FIRMA B")
        self.assertEqual(ozet[0]["no_sayisi"], 2)
        m = ma.ara(ma.dosyalari_bul(self.d), metinler=["ALIŞ"])
        self.assertEqual([x["firma"] for x in m], ["FIRMA B"])

    def test_excel_yazilir(self):
        s = ma.ara(ma.dosyalari_bul(self.d), nolar=["ABC2026000000111"])
        yol = ma.excel_yaz(self.d / "o.xlsx", s, ma.firma_ozeti(s, 1))
        self.assertTrue(Path(yol).exists())


if __name__ == "__main__":
    unittest.main()
