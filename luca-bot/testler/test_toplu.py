# -*- coding: utf-8 -*-
"""Akilli Ent. Toplu Sorgulama (hizli mod): saf mantik + sahte Luca ile uctan uca.

Ekran gerekir (Linux'ta: xvfb-run -a python -m unittest testler.test_toplu). Uctan uca testler
test_iki_hesap._calistir yardimcisini kullanir.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sahte_luca  # noqa: E402
from lucabot import toplu_sorgu as ts  # noqa: E402


class SafMantik(unittest.TestCase):
    def test_entegrasyon_secimi_kurallari(self):
        izinli = ts.entegrasyon_izinli
        for ad in ("GİB E-Arşiv Alış Faturaları Entegrasyon", "GİB E-Fatura Satış Faturaları Entegrasyon",
                   "GİB 5000/30000 Entegrasyon", "GİB e-SMM Alış"):
            self.assertTrue(izinli(ad), ad)
        for ad in ("İşnet Alış Faturaları Entegrasyon", "QR ile Yüklenmiş Alış Faturaları", "NetteCAP Gider Entegrasyon",
                   "NetteCAP Gelir Entegrasyon", "TreeWin Entegrasyon", "BelgeApp Entegrasyon",
                   "İşnet Satış Faturaları Entegrasyon", "Bilinmeyen Entegrasyon"):
            self.assertFalse(izinli(ad, turmob_var=True), ad)
        turmob = "TÜRMOB Entegratörlük Alış Faturaları Entegrasyon"
        self.assertFalse(izinli(turmob))
        self.assertFalse(izinli(turmob, turmob_var=False))
        self.assertTrue(izinli(turmob, turmob_var=True))

    def test_entegrasyon_tipi(self):
        self.assertEqual(ts.entegrasyon_tipi("GİB E-Arşiv Alış Faturaları Entegrasyon", "alis"), "e-arsiv-alis")
        self.assertEqual(ts.entegrasyon_tipi("GIB_EFATURA", "satis"), "e-fatura-satis")
        self.assertEqual(ts.entegrasyon_tipi("GİB 5000/30000 Entegrasyon", "satis"), "gib-5000")
        self.assertEqual(ts.entegrasyon_tipi("TÜRMOB Entegratörlük Alış", "alis"), "turmob-alis")
        self.assertEqual(ts.entegrasyon_tipi("GİB e-SMM", "alis"), "esmm-alis")
        self.assertIsNone(ts.entegrasyon_tipi("", "alis"))

    def test_kayit_coz_json_ve_ekran_satiri(self):
        k = ts.kayit_coz({"belge_numarasi": "abc2026000000001", "entegrasyon_tur": "TURMOB", "onay_durumu": "İptal",
                          "unvan": "X LTD"})
        self.assertEqual((k["no"], k["entegrasyon"], k["onay"]), ("ABC2026000000001", "TURMOB", "İptal"))
        k = ts.kayit_coz(["", "Fatura", "GİB E-Fatura Alış Faturaları Entegrasyon", "ABC2026000000002", "123",
                          "ACME TEKSTIL", "05/08/2026", "Onaylandı", ""])
        self.assertEqual(k["no"], "ABC2026000000002")
        self.assertIn("E-Fatura", k["entegrasyon"])
        self.assertEqual(k["unvan"], "ACME TEKSTIL")
        self.assertIsNone(ts.kayit_coz(["yok", "numara"]))
        # ayni fatura + ayni entegrasyon bir kez; farkli entegrasyon ayri kayit
        liste = ts.kayitlari_birlestir([{"belge_numarasi": "ABC2026000000001", "entegrasyon_tur": "A"},
                                        {"belge_numarasi": "ABC2026000000001", "entegrasyon_tur": "A"},
                                        {"belge_numarasi": "ABC2026000000001", "entegrasyon_tur": "B"}])
        self.assertEqual(len(liste), 2)

    def test_oran(self):
        self.assertAlmostEqual(ts._oran("9/10"), 0.9)
        self.assertAlmostEqual(ts._oran("%50"), 0.5)
        self.assertIsNone(ts._oran("belirsiz"))

    def _excel(self, firma="AKIN COBAN", yon="alis", secili=None):
        sahte_luca.sifirla()
        sahte_luca.TOPLU[(firma, yon)] = {"secili": secili or sahte_luca.TOPLU_ENTEGRASYONLAR[yon][:3], "sorgulandi": True}
        yol = Path(tempfile.mkdtemp(prefix="toplu-")) / "faturalar.xlsx"
        yol.write_bytes(sahte_luca.toplu_excel_bayt(firma, yon))
        return yol

    def test_excel_tekrarlar_atilir_ve_tevkifat_hesaplanir(self):
        excel = ts.toplu_excel_oku(self._excel())
        # 3 fatura x 3 entegrasyon = 9 satir; birebir ayni satirlar tek sayilir
        self.assertEqual(len(excel["faturalar"]), 3)
        self.assertEqual(excel["tekrar"], 6)
        toplam_matrah = sum(f["matrah"] for f in excel["faturalar"].values())
        toplam_kdv = sum(f["kdv"] for f in excel["faturalar"].values())
        self.assertEqual((toplam_matrah, toplam_kdv), (3500.0, 700.0))
        tevk = [f for f in excel["faturalar"].values() if f["tevkifat"]]
        self.assertEqual(len(tevk), 1)
        self.assertAlmostEqual(tevk[0]["tevkifat_kdv"], 360.0)       # 400 KDV x 9/10
        self.assertFalse(tevk[0]["tahmini"])

    def test_sonuclar_entegrasyona_gore_dagilir(self):
        excel = ts.toplu_excel_oku(self._excel())
        kayitlar = ts.kayitlari_birlestir([
            {"belge_numarasi": no, "entegrasyon_tur": ent, "onay_durumu": "İptal" if (no.endswith("2") and "Arşiv" in ent) else "Onaylandı"}
            for ent in ("GİB E-Arşiv Alış Faturaları Entegrasyon", "GİB E-Fatura Alış Faturaları Entegrasyon")
            for no in excel["faturalar"]])
        klasor = Path(tempfile.mkdtemp(prefix="toplu-s-"))
        sonuc = ts.sonuclari_hesapla("AKIN COBAN", "alis", ["e-arsiv-alis", "e-fatura-alis", "turmob-alis"], kayitlar, excel,
                                     lambda t: klasor / t, ["toplu.xlsx"])
        arsiv, fatura, turmob = sonuc["e-arsiv-alis"], sonuc["e-fatura-alis"], sonuc["turmob-alis"]
        self.assertEqual((arsiv["fatura_sayisi"], arsiv["iptal_itiraz"]), (3, 1))
        self.assertEqual((arsiv["matrah"], arsiv["kdv"]), (3000.0, 600.0))      # iptal faturanin tutari sayilmaz
        self.assertEqual(fatura["fatura_sayisi"], 3)
        self.assertEqual((fatura["matrah"], fatura["kdv"]), (3500.0, 700.0))
        self.assertEqual((fatura["tevkifat"], fatura["tevkifat_kdv"]), (1, 360.0))
        self.assertEqual(turmob["durum"], "fatura yok")
        self.assertEqual(arsiv["dosyalar"], ["toplu.xlsx"])
        self.assertTrue((klasor / "e-fatura-alis" / "liste.csv").exists())
        self.assertTrue((klasor / "e-fatura-alis" / "tevkifatli.csv").exists())
        self.assertTrue((klasor / "e-arsiv-alis" / "iptal-itiraz.csv").exists())

    def test_liste_okunamazsa_birincil_ekrana_yazilir(self):
        excel = ts.toplu_excel_oku(self._excel())
        klasor = Path(tempfile.mkdtemp(prefix="toplu-b-"))
        sonuc = ts.sonuclari_hesapla("AKIN COBAN", "alis", ["e-arsiv-alis", "e-fatura-alis"], [], excel,
                                     lambda t: klasor / t)
        self.assertEqual(sonuc["e-arsiv-alis"]["fatura_sayisi"], 3)
        self.assertEqual(sonuc["e-fatura-alis"]["durum"], "fatura yok")

    def test_ic_ice_zipte_tevkifat_bulunur(self):
        import io
        import zipfile
        from lucabot.fatura_analiz import zipten_tevkifatlilar
        ic = io.BytesIO()
        with zipfile.ZipFile(ic, "w") as z:
            z.writestr("ABC2026000000007.xml", "<Invoice><cac:WithholdingTaxTotal/></Invoice>")
            z.writestr("ABC2026000000007.html", "<html></html>")
        yol = Path(tempfile.mkdtemp(prefix="toplu-z-")) / "secili_faturalar.zip"
        with zipfile.ZipFile(yol, "w") as z:
            z.writestr("ABC2026000000007.zip", ic.getvalue())
            z.writestr("ABC2026000000008.zip", sahte_luca.toplu_zip_bayt("YOK", "alis"))   # bos paket de sorun cikarmaz
        self.assertEqual(zipten_tevkifatlilar(yol), {"ABC2026000000007"})

    def test_kullanicinin_ornek_excelleri_okunur(self):
        """Gercek Luca ciktisi (varsa): tekrar satirlari atilir, matrah/KDV Toplam sutunundan tutarli."""
        import glob
        yollar = glob.glob("/root/.claude/uploads/*/*.xlsx")
        if not yollar:
            self.skipTest("ornek excel yok")
        for yol in yollar:
            excel = ts.toplu_excel_oku(yol)
            if excel["basliklar"] and len(excel["basliklar"]) == 18:
                self.assertTrue(excel["faturalar"], yol)


class UctanUca(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError as e:
            raise unittest.SkipTest(str(e))
        cls.sunucu, cls.adres = sahte_luca.baslat()

    @classmethod
    def tearDownClass(cls):
        cls.sunucu.shutdown()

    def setUp(self):
        sahte_luca.sifirla()
        ts.TURMOB_YOK.clear()
        self.klasor = Path(tempfile.mkdtemp(prefix="toplu-uu-"))

    def _calistir(self, firma, ek=(), tipler=("e-arsiv-alis", "e-fatura-alis", "turmob-alis", "e-arsiv-satis", "gib-5000")):
        from test_iki_hesap import _calistir
        sahte_luca.SAYAC.update(ara_menu=True, toplu=True)
        arg = ["--firma", firma, "--bastan", "--toplu"] + [x for t in tipler for x in ("--belge-tipi", t)] + list(ek)
        kod, cikti, _ = _calistir(self.klasor, self.adres, {}, arg)
        rapor = json.loads((self.klasor / "indirilenler" / "rapor.json").read_text(encoding="utf-8"))
        return kod, cikti, rapor

    def test_hizli_mod_alis_ve_satis(self):
        kod, cikti, rapor = self._calistir("AKIN")
        self.assertEqual(kod, 0, cikti[-2000:])
        d = rapor["AKIN COBAN"]["durumlar"]
        self.assertEqual(d, {"e-arsiv-alis": "tamam", "e-fatura-alis": "tamam", "turmob-alis": "tamam",
                             "e-arsiv-satis": "tamam", "gib-5000": "tamam"}, cikti[-2500:])
        S = sahte_luca.SAYAC
        self.assertEqual(S["toplu_yasak"], 0, "yasakli entegrasyon secildi")
        self.assertEqual((S["toplu_getir"], S["toplu_excel"], S["toplu_zip"]), (2, 2, 1))   # alis + satis; XML yalniz alista
        self.assertNotIn("GİB'den Getir (", cikti)                     # eski ekran-ekran yola dusulmedi
        self.assertIn("Entegrasyonlar secildi", cikti)
        # tevkifat KDV2: alis ekranlarinda 1 fatura (400 KDV x 9/10)
        kayit = rapor["AKIN COBAN"]
        self.assertEqual(kayit["tevkifat"]["e-fatura-alis"], 1)
        self.assertEqual(kayit["tevkifat_kdv"]["e-fatura-alis"], 360.0)
        self.assertEqual(kayit["sayilar"]["e-arsiv-satis"], 3)

    def test_turmob_kullanmayan_firma_turmob_secilmeden_tekrar_denenir(self):
        kod, cikti, rapor = self._calistir("KEREM")
        self.assertEqual(kod, 0, cikti[-2000:])
        self.assertIn("TÜRMOB bilgisi girilmemis", cikti)
        d = rapor["KEREM TICARET"]["durumlar"]
        self.assertEqual(d["e-arsiv-alis"], "tamam", cikti[-2000:])
        self.assertEqual(d["turmob-alis"], "fatura yok")
        self.assertEqual(sahte_luca.SAYAC["toplu_yasak"], 0)
        self.assertEqual(sahte_luca.SAYAC["toplu_getir"], 3)         # alis: hata + yeniden, satis: 1

    def test_uzun_aralik_aylik_parcalara_bolunur(self):
        kod, cikti, rapor = self._calistir("AKIN", ["--bitis", "15/10/2026"], tipler=("e-arsiv-alis", "e-arsiv-satis"))
        self.assertEqual(kod, 0, cikti[-2000:])
        self.assertEqual(sahte_luca.SAYAC["toplu_getir"], 6)         # 3 parca x (alis + satis)
        self.assertNotIn("en fazla 1 aylik", cikti)

    def test_toplu_menu_yoksa_eski_yola_donulur(self):
        from test_iki_hesap import _calistir
        sahte_luca.SAYAC.update(ara_menu=True, toplu=False)         # menude yalnizca grupsuz "Toplu Sorgulama"
        kod, cikti, _ = _calistir(self.klasor, self.adres, {}, ["--firma", "AKIN", "--bastan", "--toplu"])
        self.assertEqual(kod, 0, cikti[-2000:])
        self.assertIn("Toplu Sorgulama kullanilamadi", cikti)
        rapor = json.loads((self.klasor / "indirilenler" / "rapor.json").read_text(encoding="utf-8"))
        self.assertEqual(rapor["AKIN COBAN"]["durumlar"], {"e-arsiv-alis": "tamam"}, cikti[-1500:])


if __name__ == "__main__":
    unittest.main()
