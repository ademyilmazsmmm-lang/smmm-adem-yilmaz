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

    def test_vkn_excelden_tamamlanir(self):
        from openpyxl import Workbook
        from karzarar.hesaplama import vkn_tamamla
        wb = Workbook()
        ws = wb.active
        ws.append(["Kısa Adı", "Uzun Adı", "Vergi No", "TC Kimlik No"])
        ws.append(["ALİ VELİ", "ALİ VELİ", 100000009, None])        # basindaki sifir Excel'de kaybolmus
        ws.append(["CEMALETTIN YILDIZ", "CEMALETTIN YILDIZ", "4100000004.0", ""])
        ws.append(["TC LI FIRMA", "", "", 12345678901])
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "vkn.xlsx"
            wb.save(yol)
            h = vkn_tamamla({"ALI": "9000000001"}, ["ALI", "ALI VELI", "CEMALETTIN", "TC LI FIRMA", "YOK FIRMA"],
                            {"vkn_listesi": str(yol)})
        self.assertEqual(h, {"ALI": "9000000001", "ALI VELI": "0100000009", "CEMALETTIN": "4100000004",
                             "TC LI FIRMA": "12345678901"})

    def test_excel_raporu_kardan_zarara_siralar(self):
        from openpyxl import load_workbook
        from karzarar.rapor import excel_yaz
        sonuc = {
            "A": {"firma": "A", "vkn": "1", "kaynak": "Luca", "defter": "x", "satis": 1.0, "mal_alis": 0.0,
                  "gider": 5.0, "kar": -4.0, "hata": ""},
            "B": {"firma": "B", "vkn": "2", "kaynak": "Defter Beyan", "defter": "İşletme", "satis": 9.0,
                  "mal_alis": 0.0, "gider": 1.0, "kar": 8.0, "hata": ""},
            "C": {"firma": "C", "vkn": "3", "kaynak": "Luca", "defter": "?", "satis": None, "mal_alis": None,
                  "gider": None, "kar": None, "hata": "menü açılamadı"}}
        with tempfile.TemporaryDirectory() as d:
            yol = excel_yaz(Path(d) / "kz.xlsx", date(2026, 7, 1), date(2026, 8, 31), sonuc)
            ws = load_workbook(yol).active
            satirlar = [[h.value for h in r] for r in ws.iter_rows(min_row=4, max_row=6)]
        self.assertEqual([(s[0], s[14]) for s in satirlar], [("B", "KÂR"), ("A", "ZARAR"), ("C", "HATA")])

    def test_defter_beyan_kalemleri_excelde_ayri_sutunlar(self):
        from openpyxl import load_workbook
        from karzarar.defterbeyan import hesap_ozeti_cozumle
        from karzarar.hesaplama import _sonuc
        from karzarar.rapor import BASLIKLAR, excel_yaz
        ozet = hesap_ozeti_cozumle([(0, [["Dönem Başı Emtia Mevcudu", "1.000,00"], ["Dönem İçinde Satın Alınan Emtia", "10,00"],
                                         ["Giderler", "200,00"], ["Amortisman Giderleri", "50,00"], ["Kar", "9,00"]]),
                                    (0, [["Dönem Sonu Emtia Mevcudu", ""], ["Dönem İçinde Elde Edilen Hasılat", "300,00"],
                                         ["Gelir Diğer Gelirler", "7,00"], ["Zarar", "0,00"]])])
        self.assertIsNone(ozet["ayrinti"]["emtia_sonu"])
        self.assertEqual((ozet["ayrinti"]["emtia_basi"], ozet["ayrinti"]["amortisman"], ozet["satis"], ozet["gider"]),
                         (1000.0, 50.0, 307.0, 250.0))
        with tempfile.TemporaryDirectory() as d:
            yol = excel_yaz(Path(d) / "k.xlsx", date(2026, 7, 1), date(2026, 8, 31),
                            {"F": _sonuc("F", "1", "Defter Beyan", "İşletme", ozet),
                             "L": _sonuc("L", "2", "Luca", "Genel muhasebe", {"satis": 5.0, "mal_alis": 1.0, "gider": 2.0,
                                                                            "kar": 2.0, "ayrinti": {}})})
            ws = load_workbook(yol).active
            baslik = [c.value for c in ws[3]]
            satirlar = {r[0].value: [c.value for c in r] for r in ws.iter_rows(min_row=4, max_row=5)}
        self.assertEqual(baslik, BASLIKLAR)
        i = {b: n for n, b in enumerate(BASLIKLAR)}
        f, l = satirlar["F"], satirlar["L"]
        self.assertEqual((f[i["Hasılat"]], f[i["Diğer Gelir"]], f[i["Dönem Başı Emtia"]], f[i["Amortisman"]],
                          f[i["Dönem Sonu Emtia"]]), (300.0, 7.0, 1000.0, 50.0, None))
        self.assertEqual((l[i["Hasılat"]], l[i["Amortisman"]], l[i["Toplam Gelir (Satış)"]]), (None, None, 5.0))
        # Toplam Gider: Defter Beyan = dönem başı emtia 1000 + mal alışı 10 + giderler 200 + amortisman 50; Luca = mal alışı + gider
        self.assertEqual((f[i["Toplam Gider"]], l[i["Toplam Gider"]]), (1260.0, 3.0))

    def test_smk_ozeti_kar_satiri_olmadan_hesaplanir(self):
        from karzarar.defterbeyan import hesap_ozeti_cozumle, smk_mi
        self.assertTrue(smk_mi("SMK"))
        self.assertFalse(smk_mi("İŞLETME"))
        o = hesap_ozeti_cozumle([(0, [["Dönem İçinde Elde Edilen Hasılat", "1.000,00"], ["Giderler", "400,00"]])])
        self.assertEqual((o["satis"], o["gider"], o["kar"]), (1000.0, 400.0, 600.0))
        self.assertEqual(o["toplam_gider"], 400.0)
        self.assertIsNone(hesap_ozeti_cozumle([(0, [["Dönem İçinde Elde Edilen Hasılat", "1.000,00"]])]))  # gider yok: okunamadi

    def test_mizan_excel_okunur(self):
        """Luca Mizan Excel'i (Ana Hesap, Tarih Araligi ustbilgisi) -> kar/zarar; tarih araligi uyusmazsa hata."""
        from openpyxl import Workbook
        from karzarar.luca_mizan import mizan_kar_zarar
        wb = Workbook()
        ws = wb.active
        for satir in (["MİZAN"], ["FIRMA"], ["Dönem :", "01/01/2026-31/12/2026"], ["Tarih Aralığı :", "01/07/2026-31/08/2026"], [],
                      ["HESAP KODU", "HESAP ADI", "BORÇ", "ALACAK", "BAKİYE", " "],
                      ["15", "STOKLAR", 2787800.0, None, 2787800.0, "B"], ["153", "TİCARİ MALLAR", 2787800.0, None, 2787800.0, "B"],
                      ["6", "GELİR TABLOSU", 6540.0, 4958020.94, 4951480.94, "A"], ["60", "BRÜT SATIŞLAR", None, 4941186.64, 4941186.64, "A"],
                      ["7", "MALİYET", 252096.88, None, 252096.88, "B"], ["770", "GENEL YÖNETİM", 9375.0, None, 9375.0, "B"]):
            ws.append(satir)
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "mizan.xlsx"
            wb.save(yol)
            r = mizan_kar_zarar(yol, date(2026, 7, 1), date(2026, 8, 31))
            self.assertEqual((r["satis"], r["mal_alis"], r["gider"], r["toplam_gider"], r["kar"]),
                             (4951480.94, 2787800.0, 252096.88, 3039896.88, 1911584.06))
            with self.assertRaises(LookupError):
                mizan_kar_zarar(yol, date(2026, 7, 1), date(2026, 9, 30))

    def test_mizan_fazladan_sutun_borc_alacagi_kaydirmaz(self):
        """Doviz vb. fazladan sutun gelse de BORC/ALACAK basliktan bulunur (sutun kaymasi yanlis kar uretiyordu)."""
        from openpyxl import Workbook
        from karzarar.luca_mizan import mizan_kar_zarar
        wb = Workbook()
        ws = wb.active
        for satir in (["MİZAN"], ["Tarih Aralığı :", "01/07/2026-31/08/2026"], [],
                      ["HESAP KODU", "HESAP ADI", "DÖVİZ", "BORÇ", "ALACAK", "BAKİYE", "B/A"],
                      ["153", "TİCARİ MALLAR", "TL", 1000.0, None, 1000.0, "B"],
                      ["6", "GELİR", "TL", 50.0, 900.0, 850.0, "A"], ["7", "MALİYET", "TL", 200.0, None, 200.0, "B"]):
            ws.append(satir)
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "m.xlsx"
            wb.save(yol)
            r = mizan_kar_zarar(yol, date(2026, 7, 1), date(2026, 8, 31))
        self.assertEqual((r["satis"], r["mal_alis"], r["gider"], r["kar"]), (850.0, 1000.0, 200.0, -350.0))

    def test_mizan_bakiye_esas_alinir_tutarsizsa_hata(self):
        from openpyxl import Workbook
        from karzarar.luca_mizan import mizan_kar_zarar, mizan_satirlari
        def yaz(satirlar):
            wb = Workbook()
            ws = wb.active
            for s_ in (["Tarih Aralığı :", "01/07/2026-31/08/2026"],
                       ["HESAP KODU", "HESAP ADI", "BORÇ", "ALACAK", "BAKİYE", " "]) + tuple(satirlar):
                ws.append(s_)
            d = tempfile.mkdtemp()
            yol = Path(d) / "m.xlsx"
            wb.save(yol)
            return yol
        iyi = yaz([["6", "GELİR", 50.0, 900.0, 850.0, "A"], ["7", "MALİYET", 200.0, None, 200.0, "B"],
                   ["153", "MAL", 1000.0, None, 1000.0, "B"]])
        r = mizan_kar_zarar(iyi, date(2026, 7, 1), date(2026, 8, 31))
        self.assertEqual((r["satis"], r["mal_alis"], r["gider"], r["kar"]), (850.0, 1000.0, 200.0, -350.0))
        # borc/alacak sutunlari bakiyeyle celisirse (orn. kaymis sutun) sonuc kabul edilmez
        bozuk = yaz([["6", "GELİR", 0.0, 50.0, 850.0, "A"], ["7", "MALİYET", None, 200.0, 200.0, "B"]])
        with self.assertRaises(LookupError):
            mizan_kar_zarar(bozuk, date(2026, 7, 1), date(2026, 8, 31))
        self.assertEqual(mizan_satirlari(iyi)[1][0]["alacak"], 850.0)   # bakiye (A) alacak tarafina yazilir

    def test_tarih_zorunlu_sorulur(self):
        from kar_zarar import tarih_sor
        yanit = iter(["", "31/08/2026-01/07/2026", "abc", "01/07/2026-31/08/2026"])
        mesajlar = []
        self.assertEqual(tarih_sor(lambda _: next(yanit), mesajlar.append), (date(2026, 7, 1), date(2026, 8, 31)))
        self.assertEqual(len(mesajlar), 3)   # bos, ters aralik ve gecersiz giris reddedildi

    def test_tarih_araligi_tek_seferde(self):
        from kar_zarar import aralik_coz
        bekle = (date(2026, 7, 1), date(2026, 8, 31))
        for metin in ("01/07/2026-31/08/2026", "01.07.2026 - 31.08.2026", "1/7/2026 31/8/2026", "01-07-2026-31-08-2026"):
            self.assertEqual(aralik_coz(metin), bekle, metin)
        with self.assertRaises(ValueError):
            aralik_coz("01/07/2026")

    def test_defter_donemi_ustbilgiden(self):
        from karzarar.defterbeyan import defter_donemi
        self.assertEqual(defter_donemi("X ( Başlangıç Tarihi: 01.01.2026 - Bitiş Tarihi: Devam Ediyor ) Y"),
                         (date(2026, 1, 1), None))
        self.assertEqual(defter_donemi("( Başlangıç Tarihi: 01.01.2025 - Bitiş Tarihi: 31.12.2025 )"),
                         (date(2025, 1, 1), date(2025, 12, 31)))
        self.assertIsNone(defter_donemi("Başlangıç Tarihi: 01/01/2025 Bitiş Tarihi: 31/12/2025"))  # hesap ozeti basligi

    def test_defter_turu_ustbilgiden(self):
        from karzarar.defterbeyan import defter_turu, isletme_mi
        metin = "ÖRNEK MÜKELLEF adına işlem yapmaktasınız.\n6000000006 - İŞLETME Güvenli Çıkış"
        self.assertEqual(defter_turu(metin, "6000000006"), "İŞLETME")
        self.assertTrue(isletme_mi("İŞLETME"))
        self.assertFalse(isletme_mi("BİLANÇO"))
        self.assertEqual(defter_turu("9000000001 - SMK", "6000000006"), "")

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
        kayitlar = [{"ad": "ALFA ISLETME", "unvan": "ALFA İŞLETME", "vkn": "1111111111", "tc": "1"},
                    {"ad": "GERCEK KISI", "unvan": "GERÇEK KİŞİ", "vkn": "", "tc": "22222222222"},
                    {"ad": "NUMARASIZ", "unvan": "NUMARASIZ", "vkn": "", "tc": ""}]
        self.assertEqual(kar_zarar.vkn_haritasi(["ALFA İŞLETME", "GERCEK KISI", "NUMARASIZ", "YOK"], kayitlar),
                         {"ALFA İŞLETME": "1111111111", "GERCEK KISI": "22222222222"})
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "kz.json"
            kar_zarar.kaydet(yol, date(2026, 7, 1), date(2026, 8, 31), {"A": {"firma": "A", "kar": 5.0}})
            self.assertEqual(kar_zarar.oku(yol), ("01/07/2026-31/08/2026",
                                                   [{"firma": "A", "kar": 5.0, "donem": "01/07/2026-31/08/2026"}]))
            with self.assertRaises(ValueError):
                kar_zarar.oku(Path(d) / "yok.json")


if __name__ == "__main__":
    unittest.main()


class MusteriOnbellekTestleri(unittest.TestCase):
    def test_onbellek_yil_ve_sinif(self):
        import kar_zarar
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "musteri-listeleri.json"
            self.assertEqual(kar_zarar.onbellek_oku(yol, 2026), {})            # yok
            kar_zarar.onbellek_yaz(yol, 2026, {"1.Sınıf": [{"ad": "A", "vkn": "1"}], "": []})
            self.assertEqual(kar_zarar.onbellek_oku(yol, 2026)["1.Sınıf"], [{"ad": "A", "vkn": "1"}])
            self.assertEqual(kar_zarar.onbellek_oku(yol, 2027), {})            # baska yil kullanilmaz
            yol.write_text("bozuk", encoding="utf-8")
            self.assertEqual(kar_zarar.onbellek_oku(yol, 2026), {})

    def test_kayitli_liste_varsa_luca_ya_gidilmez(self):
        import kar_zarar
        with tempfile.TemporaryDirectory() as d:
            onbellek = {"1.Sınıf": [{"ad": "A"}]}
            kayitlar = kar_zarar._musteri_listesi(None, 2026, Path(d), "1.Sınıf", Path(d) / "l.log", onbellek,
                                                  Path(d) / "c.json")  # page=None: Luca'ya gidilirse AttributeError
            self.assertEqual(kayitlar, [{"ad": "A"}])


class MizanYenidenOynatmaTestleri(unittest.TestCase):
    def _sunucu(self, yanitlar):
        import http.server
        import threading
        gelenler = []

        class H(http.server.BaseHTTPRequestHandler):
            def _ver(self):
                uzunluk = int(self.headers.get("Content-Length") or 0)
                gelenler.append((self.command, self.path, self.headers.get("Cookie"), self.rfile.read(uzunluk)))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(yanitlar[self.path])
            do_GET = do_POST = _ver

            def log_message(self, *a):
                pass

        sunucu = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=sunucu.serve_forever, daemon=True).start()
        self.addCleanup(sunucu.shutdown)
        return f"http://127.0.0.1:{sunucu.server_port}", gelenler

    def test_cerez_basligi_alan_adina_gore(self):
        from karzarar.luca_mizan import _cerez_basligi
        cerezler = [{"name": "A", "value": "1", "domain": ".luca.com.tr"},
                    {"name": "B", "value": "2", "domain": "auygs.luca.com.tr"},
                    {"name": "C", "value": "3", "domain": "baska.com"}]
        self.assertEqual(_cerez_basligi(cerezler, "https://auygs.luca.com.tr/Luca/x.do"), "A=1; B=2")
        self.assertEqual(_cerez_basligi(cerezler), "A=1; B=2; C=3")

    def test_istek_tarayicisiz_tekrarlanir(self):
        from karzarar.luca_mizan import _istegi_tekrarla
        adres, gelenler = self._sunucu({"/rapor": b"PK\x03\x04excel", "/html": b"<html>oturum yok</html>"})
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "m.xlsx"
            kayit = {"url": adres + "/rapor", "yontem": "POST", "govde": b"a=1",
                     "basliklar": {"Content-Type": "application/x-www-form-urlencoded", "X-Gereksiz": "1"}}
            self.assertTrue(_istegi_tekrarla(kayit, "S=abc", yol))
            self.assertEqual(yol.read_bytes(), b"PK\x03\x04excel")
            self.assertEqual(gelenler[0], ("POST", "/rapor", "S=abc", b"a=1"))
            yol2 = Path(d) / "h.xlsx"
            self.assertFalse(_istegi_tekrarla({"url": adres + "/html", "yontem": "GET"}, "S=abc", yol2))
            self.assertFalse(yol2.exists())  # HTML doner: dosya yazilmaz
            self.assertFalse(_istegi_tekrarla({"url": "http://127.0.0.1:1/yok"}, "S=abc", yol2))


class SonuclariBirlestirmeTestleri(unittest.TestCase):
    def test_yeni_sorgu_oncekileri_silmez(self):
        from karzarar import hesaplama
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "kar-zarar.json"
            hesaplama.kaydet(yol, date(2026, 1, 1), date(2026, 8, 31),
                             {"A": {"firma": "A", "kar": 10.0}, "B": {"firma": "B", "kar": -5.0}})
            # ikinci sorgu yalniz C: A ve B yerinde kalir
            hesaplama.kaydet(yol, date(2026, 1, 1), date(2026, 8, 31), {"C": {"firma": "C", "kar": 1.0}})
            donem, firmalar = hesaplama.oku(yol)
            self.assertEqual(donem, "01/01/2026-31/08/2026")
            self.assertEqual(sorted(s["firma"] for s in firmalar), ["A", "B", "C"])
            # ayni firma + ayni donem yeniden sorgulaninca guncellenir
            hesaplama.kaydet(yol, date(2026, 1, 1), date(2026, 8, 31), {"A": {"firma": "A", "kar": 99.0}})
            _, firmalar = hesaplama.oku(yol)
            self.assertEqual({s["firma"]: s["kar"] for s in firmalar}, {"A": 99.0, "B": -5.0, "C": 1.0})
            # baska donem: ayni firma iki kez tutulur
            hesaplama.kaydet(yol, date(2026, 1, 1), date(2026, 9, 30), {"A": {"firma": "A", "kar": 5.0}})
            donem, firmalar = hesaplama.oku(yol)
            self.assertEqual(donem, "01/01/2026-30/09/2026")
            self.assertEqual(sorted((s["firma"], s["donem"]) for s in firmalar),
                             sorted([("A", "01/01/2026-30/09/2026"), ("A", "01/01/2026-31/08/2026"),
                                     ("B", "01/01/2026-31/08/2026"), ("C", "01/01/2026-31/08/2026")]))

    def test_hatali_yeni_sonuc_eski_basariliyi_bozmaz(self):
        from karzarar import hesaplama
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "kar-zarar.json"
            hesaplama.kaydet(yol, date(2026, 1, 1), date(2026, 8, 31), {"A": {"firma": "A", "kar": 10.0}})
            hesaplama.kaydet(yol, date(2026, 1, 1), date(2026, 8, 31),
                             {"A": {"firma": "A", "kar": None, "hata": "HATA: mizan inmedi"}})
            _, firmalar = hesaplama.oku(yol)
            self.assertEqual(firmalar[0]["kar"], 10.0)
            self.assertEqual(firmalar[0]["son_hata"], "HATA: mizan inmedi")
            # eski bir hata yeni basariyla degisir
            hesaplama.kaydet(yol, date(2026, 1, 1), date(2026, 8, 31), {"A": {"firma": "A", "kar": 20.0}})
            _, firmalar = hesaplama.oku(yol)
            self.assertEqual(firmalar[0]["kar"], 20.0)
            self.assertNotIn("son_hata", firmalar[0])

    def test_eski_bicimli_dosya_donemi_ust_alandan_alinir(self):
        from karzarar import hesaplama
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "kar-zarar.json"
            yol.write_text('{"donem": "01/07/2026-31/08/2026", "firmalar": [{"firma": "Z", "kar": 1.0}]}',
                           encoding="utf-8")
            hesaplama.kaydet(yol, date(2026, 1, 1), date(2026, 8, 31), {"A": {"firma": "A", "kar": 2.0}})
            _, firmalar = hesaplama.oku(yol)
            self.assertEqual({s["firma"]: s["donem"] for s in firmalar},
                             {"Z": "01/07/2026-31/08/2026", "A": "01/01/2026-31/08/2026"})
