# -*- coding: utf-8 -*-
"""Akilli Ent. Toplu Sorgulama (hizli mod): saf mantik + sahte Luca ile uctan uca.

Ekran gerekir (Linux'ta: xvfb-run -a python -m unittest testler.test_toplu). Uctan uca testler
test_iki_hesap._calistir yardimcisini kullanir.
"""

import json
import os
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

    def test_getir_penceresinin_sabit_ipucu_hata_sayilmaz(self):
        pencere = ts.sadelestir("Tarih Aralığı Seçili entegrasyonlar sırayla sorgulanır. En fazla 1 aylık sorgulama yapılabilir. Getir")
        self.assertNotIn(ts.TOPLU_AZAMI_UZUN, ts.ipucusuz(pencere))
        gercek = ts.sadelestir("Uyarı: En fazla 1 aylık sorgulama yapılabilir Tamam")
        self.assertIn(ts.TOPLU_AZAMI_UZUN, ts.ipucusuz(gercek))
        ikisi = ts.ipucusuz(pencere + " " + gercek)          # pencere acikken gercek hata da gelirse yine yakalanir
        self.assertIn(ts.TOPLU_AZAMI_UZUN, ikisi)

    def test_entegrasyon_adli_alan_kod_ya_da_bos_olsa_da_bulunur(self):
        k = ts.kayit_coz({"belge_numarasi": "ABC2026000000001", "entegrasyon_tur": "7", "unvan": "X",
                          "ettn": "e-fatura-gibi", "url": "/x", "alan": "GİB E-Arşiv Entegrasyon (5000/30000)"})
        self.assertEqual(ts.entegrasyon_tipi(k["entegrasyon"], "satis"), "gib-5000")
        k = ts.kayit_coz(["", "Fatura", "GİB E-Arşiv", "ABC2026000000002", "ACME", "05/08/2026", "Onaylandı"])
        self.assertEqual(ts.entegrasyon_tipi(k["entegrasyon"], "alis"), "e-arsiv-alis")
        k = ts.kayit_coz({"belge_numarasi": "ABC2026000000003", "belge_turu": "Fatura", "entegrasyon_tur": "GIB_EFATURA"})
        self.assertEqual(ts.entegrasyon_tipi(k["entegrasyon"], "alis"), "e-fatura-alis")      # "Fatura" tek basina e-Fatura sayilmaz

    def test_taninan_ama_istenmeyen_entegrasyon_sayilmaz(self):
        excel = ts.toplu_excel_oku(self._excel())
        nolar = list(excel["faturalar"])
        kayitlar = ts.kayitlari_birlestir(
            [{"belge_numarasi": nolar[0], "entegrasyon_tur": "GİB E-Arşiv Alış Faturaları Entegrasyon"},
             {"belge_numarasi": nolar[1], "entegrasyon_tur": "GİB E-Fatura Alış Faturaları Entegrasyon"},   # istenmiyor
             {"belge_numarasi": nolar[2], "entegrasyon_tur": "GİB E-Fatura Alış Faturaları Entegrasyon"}])
        klasor = Path(tempfile.mkdtemp(prefix="toplu-d-"))
        sonuc = ts.sonuclari_hesapla("AKIN COBAN", "alis", ["e-arsiv-alis"], kayitlar, excel, lambda t: klasor / t)
        self.assertEqual(sonuc["e-arsiv-alis"]["fatura_sayisi"], 1)          # e-Fatura satirlari e-Arsiv'e yazilmaz
        self.assertEqual(sonuc["e-arsiv-alis"]["not"], "")

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



@unittest.skipUnless(os.environ.get("LUCA_TEST_CHROMIUM"), "LUCA_TEST_CHROMIUM yok")
class XmlSecimiDonemi(unittest.TestCase):
    """XML icin yalniz GIB e-Arsiv (alis) / GIB 5000-30000 (satis) satirlari ve yalniz hedef ayin Belge Tarihi isaretlenir."""
    HTML = """<table>
      <tr><th><input type=checkbox></th><th>Belge Turu</th><th>Entegrasyon</th><th>Belge Tarihi</th></tr>
      <tr><td><input type=checkbox></td><td>SATIS</td><td>GİB E-Arşiv Entegrasyonu Alış Faturaları</td><td>02/10/2026</td></tr>
      <tr><td><input type=checkbox></td><td>SATIS</td><td>GİB E-Arşiv Entegrasyonu Alış Faturaları</td><td>31/10/2026</td></tr>
      <tr><td><input type=checkbox></td><td>SATIS</td><td>GİB E-Arşiv Entegrasyonu Alış Faturaları</td><td>03/11/2026</td></tr>
      <tr><td><input type=checkbox></td><td>SATIS</td><td>TÜRMOB Entegratörlük Alış Faturaları Entegrasyon</td><td>05/10/2026</td></tr>
      <tr><td><input type=checkbox></td><td>SATIS</td><td>GİB E-Arşiv Entegrasyon (5000/30000)</td><td>10/10/2026</td></tr>
      <tr><td><input type=checkbox></td><td>SATIS</td><td>GİB E-Arşiv Entegrasyon (5000/30000)</td><td>12/11/2026</td></tr></table>"""

    def _sec(self, mod, donem):
        from datetime import date
        from playwright.sync_api import sync_playwright
        from lucabot import toplu_sorgu
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=os.environ["LUCA_TEST_CHROMIUM"], args=["--no-sandbox"])
            sayfa = b.new_page()
            sayfa.set_content(self.HTML)
            sayi = toplu_sorgu.arsiv_satirlarini_sec(sayfa, None, mod, donem)
            isaretli = sayfa.evaluate("() => Array.from(document.querySelectorAll('tr')).slice(1).map(r => r.querySelector('input').checked)")
            b.close()
        return sayi, isaretli

    def test_alis_yalniz_gib_earsiv_ve_hedef_ay(self):
        from datetime import date
        sayi, isaretli = self._sec("alis", (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual((sayi, isaretli), (2, [True, True, False, False, False, False]))   # kasim ve TURMOB isaretlenmez

    def test_satis_yalniz_5000_30000_ve_hedef_ay(self):
        from datetime import date
        sayi, isaretli = self._sec("satis", (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual((sayi, isaretli), (1, [False, False, False, False, True, False]))

    def test_donem_verilmezse_eski_davranis(self):
        sayi, isaretli = self._sec("alis", None)
        self.assertEqual((sayi, isaretli), (3, [True, True, True, False, False, False]))


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
        kod, cikti, _ = _calistir(self.klasor, self.adres, {}, arg, hizli=True)
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
        self.assertEqual((S["toplu_getir"], S["toplu_excel"], S["toplu_zip"]), (2, 2, 2))   # alis + satis; XML: alista e-Arsiv, satista 5000/30000
        self.assertEqual(S.get("toplu_iptal"), 2)                      # iptal/itiraz sorgusu alista ve satista
        self.assertEqual(rapor["AKIN COBAN"]["iptal"]["e-arsiv-alis"], 1)       # sahte Luca 2. faturayi iptal isaretler
        zip_ent = set(S.get("toplu_zip_ent", []))      # XML paketine yalniz GIB e-Arsiv alis girer
        self.assertEqual(zip_ent, {"GİB E-Arşiv Alış Faturaları Entegrasyon", "GİB 5000/30000 Entegrasyon"}, zip_ent)
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

    def test_entegrasyon_kodla_gelirse_ekrandan_ogrenilir_ve_xml_yine_yalniz_earsiv(self):
        sahte_luca.SAYAC["toplu_kod"] = True      # ag yanitinda entegrasyon "K0/K1" gibi kod; ekranda acik ad
        kod, cikti, rapor = self._calistir("AKIN", tipler=("e-arsiv-alis", "e-fatura-alis"))
        self.assertEqual(kod, 0, cikti[-1500:])
        k = rapor["AKIN COBAN"]
        self.assertEqual(k["durumlar"], {"e-arsiv-alis": "tamam", "e-fatura-alis": "tamam"}, cikti[-1500:])
        self.assertEqual((k["sayilar"]["e-arsiv-alis"], k["sayilar"]["e-fatura-alis"]), (3, 3))     # dagilim dogru
        self.assertEqual(set(sahte_luca.SAYAC.get("toplu_zip_ent", [])), {"GİB E-Arşiv Alış Faturaları Entegrasyon"})

    def test_suren_sorgu_iptal_sorgusuna_gecmez(self):
        """Islem Takip gunlugu "fatura bulunamadi"/"tamamlandi" satirlari yazarken (sorgu surerken) sonraki adima gecilmez."""
        sahte_luca.SAYAC["toplu_gecikme"] = 9
        kod, cikti, rapor = self._calistir("AKIN", tipler=("e-arsiv-alis",))
        self.assertEqual(kod, 0, cikti[-1500:])
        self.assertEqual(sahte_luca.SAYAC["toplu_erken_iptal"], 0, "iptal sorgusu getir bitmeden baslatildi")
        self.assertEqual(sahte_luca.SAYAC.get("toplu_iptal"), 1)
        self.assertEqual(rapor["AKIN COBAN"]["durumlar"], {"e-arsiv-alis": "tamam"}, cikti[-1500:])

    def test_bildirim_gelmezse_ekran_durunca_devam_eder(self):
        sahte_luca.SAYAC["toplu_sessiz"] = True       # Luca faturasiz/sessiz sorguda hic bildirim gostermeyebiliyor
        eski, ts.IDLE_SANIYE = ts.IDLE_SANIYE, 4
        try:
            kod, cikti, rapor = self._calistir("AKIN", tipler=("e-arsiv-alis", "gib-5000"))
        finally:
            ts.IDLE_SANIYE = eski
        self.assertEqual(kod, 0, cikti[-1500:])
        self.assertIn("sorgu bitmis sayilip devam ediliyor", cikti)
        self.assertEqual(rapor["AKIN COBAN"]["durumlar"], {"e-arsiv-alis": "tamam", "gib-5000": "tamam"}, cikti[-1500:])

    def test_toplu_menu_yoksa_eski_ekranlara_dusulmez(self):
        from test_iki_hesap import _calistir
        sahte_luca.SAYAC.update(ara_menu=True, toplu=False)         # menude yalnizca grupsuz "Toplu Sorgulama"
        kod, cikti, _ = _calistir(self.klasor, self.adres, {}, ["--firma", "AKIN", "--bastan", "--toplu"])
        rapor = json.loads((self.klasor / "indirilenler" / "rapor.json").read_text(encoding="utf-8"))
        self.assertTrue(rapor["AKIN COBAN"]["durumlar"]["e-arsiv-alis"].startswith("hata"), cikti[-1500:])
        self.assertIn("Toplu Sorgulama kullanilamadi", cikti)
        self.assertNotIn("GİB'den Getir aciliyor", cikti)            # eski e-Arsiv Alis ekrani acilmadi

    def test_yalniz_istenen_entegrasyon_secilir_ve_liste_satirlari_karismaz(self):
        self._calistir("AKIN", tipler=("e-arsiv-alis",))
        sec = sahte_luca.TOPLU[("AKIN COBAN", "alis")]["secili"]
        self.assertEqual(sec, ["GİB E-Arşiv Alış Faturaları Entegrasyon"])   # e-Fatura/TURMOB istenmedi: secilmez


if __name__ == "__main__":
    unittest.main()
