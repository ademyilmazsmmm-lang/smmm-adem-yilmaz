# -*- coding: utf-8 -*-
"""e-Defter on kontrolu (edefter.py): saf mantik testleri + sahte Luca ile uctan uca.

Calistirma (kar-zarar klasorunden):  python -m unittest testler.test_edefter
Uctan uca testler Chromium ister (LUCA_TEST_CHROMIUM); ekransiz ortamda xvfb-run ile calistirin.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from karzarar import edefter_kontrol as ek  # noqa: E402
from karzarar import luca_edefter as le  # noqa: E402

BASLIKLAR = ["", "Sıra", "Fiş No", "Değişmeyen Fiş No", "Fiş Tarihi", "Hesap Kodu", "Borç", "Alacak", "Açıklama", "Evrak No",
             "Evrak Tarihi", "BT", "Ödeme Türü", "Durum"]


def satir(sira="", fis="", deg="", tarih="", hesap="102.04 BANKA", borc="0,00", alacak="0,00", evrak="89582", bt="MF", odeme=""):
    return ["", str(sira), fis, deg, tarih, hesap, borc, alacak, "açıklama", evrak, "01/07/2026", bt, odeme, ""]


class SafMantik(unittest.TestCase):
    def test_satirlar_fislere_gruplanir_ilk_satirda_fis_no_dolu_digerleri_bos(self):
        satirlar = [satir(1, "01023", "111", "01/07/2026", borc="0,00", alacak="288,00", evrak="89582"),
                    satir("", "", "", "", "780.001 GIDER", borc="288,00", alacak="0,00", evrak="89582"),
                    satir(2, "01024", "112", "02/07/2026", borc="1.000,50", evrak="168", bt="MF", odeme="NAKIT"),
                    satir("", "", "", "", "320.01", borc="0,00", alacak="1.000,50", evrak="168")]
        fisler = le.fisleri_grupla(BASLIKLAR, satirlar)
        liste = list(fisler.values())
        self.assertEqual([(f["fis_no"], f["tarih"], f["degismeyen"], f["satir"]) for f in liste],
                         [("01023", "01/07/2026", "111", 2), ("01024", "02/07/2026", "112", 2)])
        self.assertEqual(liste[0]["evrak"], ["89582"])           # ayni evrak no bir kez
        self.assertEqual(liste[0]["tutar"], 288.0)               # borc toplami
        self.assertEqual(liste[1]["tutar"], 1000.5)
        self.assertEqual((liste[1]["bt"], liste[1]["odeme"], liste[1]["hesap"]), ("MF", "NAKIT", "102.04"))

    def test_luca_durum_aciklamasi_ve_yeni_kodlar(self):
        satirlar = [satir(1, "01023", "111", "01/07/2026"), satir("", ""), satir(2, "01024", "112", "02/07/2026")]
        for s_ in (satirlar[0], satirlar[2]):
            s_[13] = "Evrak No boş olamaz."
        satirlar[1][13] = "Belge Türü , Evrak No boş olamaz."
        liste = list(le.fisleri_grupla(BASLIKLAR, satirlar).values())
        self.assertEqual(liste[0]["durum"], ["Evrak No boş olamaz.", "Belge Türü , Evrak No boş olamaz."])
        self.assertEqual(ek.fis_satiri(liste[1]).split("[")[1], "Evrak No boş olamaz.]")
        self.assertEqual(ek.kod_adi("20043"), "Evrak no ve tarih var ama belge türü boş")

    def test_fatura_fisi_191_391_hesabindan_ayirt_edilir(self):
        satirlar = [satir(1, "01", "111", "01/07/2026", hesap="320.01 SATICI"), satir("", hesap="191.108.20 KDV"), satir("", hesap="770.01 GIDER"),
                    satir(2, "02", "112", "02/07/2026", hesap="102.04 BANKA"), satir("", hesap="780.001 GIDER"),
                    satir(3, "03", "113", "03/07/2026", hesap="120.01 ALICI"), satir("", hesap="391.00.20 KDV")]
        liste = list(le.fisleri_grupla(BASLIKLAR, satirlar).values())
        self.assertEqual([le.fatura_fisi_mi(f) for f in liste], [True, False, True])
        self.assertEqual(liste[0]["hp"], ["320", "191", "770"])
        self.assertIsNone(le.fatura_fisi_mi({"hp": []}))                                  # hesap okunamadi: sinif belirsiz
        self.assertIn("(fatura fişi)", ek.fis_satiri(dict(liste[0], fatura_fisi=True)))
        self.assertIn("(diğer fiş)", ek.fis_satiri(dict(liste[1], fatura_fisi=False)))

    def test_sayfa_sinirinda_bolunen_fis_birlestirilir(self):
        fisler = le.fisleri_grupla(BASLIKLAR, [satir(1, "01023", "111", "01/07/2026", borc="10,00"), satir("", borc="5,00")])
        sonraki = le.fisleri_grupla(BASLIKLAR, [satir("", borc="7,00"), satir(2, "01024", "112", "02/07/2026")], fisler)
        liste = list(sonraki.values())
        self.assertEqual([(f["fis_no"], f["satir"], f["tutar"]) for f in liste], [("01023", 3, 22.0), ("01024", 1, 0.0)])

    def test_tutar_ve_baslik_adlari(self):
        self.assertEqual(le.tutar("3.354,75"), 3354.75)
        self.assertEqual(le.tutar(""), 0.0)
        self.assertEqual(le.HATA_KODU.search("... nolu fiş(ler)de birden fazla ödeme yöntemi mevcut.(Hata Kodu: 20047)").group(1), "20047")
        self.assertTrue(le.KAYIT_YOK.search("Kayıt bulunamadı."))
        self.assertFalse(le.KAYIT_YOK.search("Tarih alanı zorunludur"))

    def test_firma_sonucu_durumlari(self):
        temiz = {"kod": "20041", "ad": "x", "fis_sayisi": 0, "fisler": []}
        sorunlu = {"kod": "20047", "ad": "y", "fis_sayisi": 3, "fisler": [{"fis_no": "1"}]}
        hatali = {"kod": "20048", "ad": "z", "fis_sayisi": 0, "fisler": [], "hata": "liste açılmadı"}
        self.assertEqual(ek.firma_sonucu("A", "d", [temiz])["durum"], "tamam")
        self.assertEqual(ek.firma_sonucu("A", "d", [temiz, sorunlu])["durum"], "sorun var")
        self.assertEqual(ek.firma_sonucu("A", "d", [temiz, hatali])["durum"], "hata")            # tarama tam degil: 'tamam' denmez
        self.assertEqual(ek.firma_sonucu("A", "d", [sorunlu, hatali])["durum"], "sorun var")
        self.assertEqual(ek.firma_sonucu("A", "d", [], hata="menü yok")["durum"], "hata")
        self.assertEqual(ek.sorun_sayisi(ek.firma_sonucu("A", "d", [temiz, sorunlu])), 3)
        self.assertEqual(ek.taranamayanlar(ek.firma_sonucu("A", "d", [hatali])), [("20048", "liste açılmadı")])

    def test_json_ve_excel(self):
        d = Path(tempfile.mkdtemp(prefix="edefter-"))
        fis = {"fis_no": "01023", "tarih": "01/07/2026", "degismeyen": "111", "satir": 2, "evrak": ["89582"], "bt": "MF",
               "odeme": "", "tutar": 288.0, "hesap": "102.04", "aciklama": "x"}
        a = ek.firma_sonucu("A LTD", "01/07/2026-31/07/2026", [{"kod": "20041", "ad": "tanım yok", "fis_sayisi": 1, "fisler": [fis]},
                                                              {"kod": "20047", "ad": "y", "fis_sayisi": 0, "fisler": []}])
        b = ek.firma_sonucu("B LTD", "01/07/2026-31/07/2026", [], hata="Menü bulunamadı")
        yol = d / "edefter.json"
        ek.kaydet(yol, "01/07/2026-31/07/2026", {"A LTD": a, "B LTD": b})
        ek.kaydet(yol, "01/07/2026-31/07/2026", {"A LTD": dict(a, durum="tamam")})           # ayni firma yenisiyle degisir
        veri = json.loads(yol.read_text(encoding="utf-8"))
        self.assertEqual([(f["firma"], f["durum"]) for f in veri["firmalar"]], [("A LTD", "tamam"), ("B LTD", "hata")])
        from openpyxl import load_workbook
        wb = load_workbook(str(ek.excel_yaz(d / "edefter.xlsx", veri["donem"], [a, b])))
        self.assertEqual(wb.sheetnames, ["Firmalar", "Uyumsuz fişler"])
        firmalar = list(wb["Firmalar"].iter_rows(values_only=True))
        self.assertEqual(firmalar[0][:4], ("Firma", "Dönem", "Durum", "Uyumsuz fiş"))
        self.assertEqual((firmalar[1][0], firmalar[1][2], firmalar[1][3], firmalar[1][4], firmalar[1][5]),
                         ("A LTD", "UYUMSUZ FİŞ VAR", 1, 1, 0))                          # 20041: 1, 20047: 0
        self.assertEqual(firmalar[2][2], "Kontrol tamamlanamadı")
        fisler = list(wb["Uyumsuz fişler"].iter_rows(values_only=True))
        self.assertEqual((fisler[1][0], fisler[1][1], fisler[1][3], fisler[1][4], fisler[1][6]),
                         ("A LTD", "20041", "01023", "01/07/2026", "89582"))
        self.assertEqual(fisler[1][2], "Belge türü tanımı yok")


def calistir(klasor_rapor=None, veri=None, ayar=None, fis_veri=None, fis_modlar=None, fis_ayar=None, ek_arg=(), firma="ALFA ISLETME", tarih="01/10/2026-31/10/2026",
             tum_firmalar=True):
    """Sahte Luca + edefter.py: (cikis kodu, sonuc sozlugu {firma: sonuc}, cikti, sahte sunucunun kaydettikleri)."""
    import sahte_kz
    sahte_kz.sifirla()
    sahte_kz.EDEFTER_VERI.update(veri or {})
    sahte_kz.EDEFTER_AYAR.update(ayar or {})
    sahte_kz.FIS_VERI.update(fis_veri or {})
    sahte_kz.FIS_AYAR["modlar"].update(fis_modlar or {})
    sahte_kz.FIS_AYAR.update(fis_ayar or {})
    klasor = Path(tempfile.mkdtemp(prefix="edefter-uu-"))
    sunucu, adres = sahte_kz.baslat()
    ayarlar = {"giris_adresi": adres, "tarayici": "chromium", "tarayici_yolu": os.environ.get("LUCA_TEST_CHROMIUM", ""),
               "tarayici_sandbox": os.name == "nt", "profil_yerel": True}
    (klasor / "ayarlar.json").write_text(json.dumps(ayarlar), encoding="utf-8")
    ortam = dict(os.environ, LUCA_BOT_AYAR=str(klasor / "ayarlar.json"), LOCALAPPDATA=str(klasor / "yerel"),
                 KARZARAR_CIKTI=str(klasor / "cikti"), PYTHONIOENCODING="utf-8")
    komut = [sys.executable, str(KOK / "edefter.py"), "--tarih", tarih, "--firma-tam", firma,
             *(["--tum-firmalar"] if tum_firmalar else []), "--bitince-kapat", *ek_arg]
    r = subprocess.run(komut, env=ortam, cwd=str(KOK), capture_output=True, text=True, encoding="utf-8")
    sunucu.shutdown()
    try:
        sonuc = {f["firma"]: f for f in json.loads((klasor / "cikti" / "edefter.json").read_text(encoding="utf-8"))["firmalar"]}
    except OSError:
        sonuc = {}
    calistir.klasor = klasor
    return r.returncode, sonuc, r.stdout + r.stderr, dict(sahte_kz.EDEFTER_AYAR, istekler=list(sahte_kz.EDEFTER_AYAR["istekler"]),
                                                         fis_istekler=list(sahte_kz.FIS_AYAR["istekler"]))


def fis(no, deg, tarih, evrakli=True, bt="MF", durum="Evrak No boş olamaz.", fatura=False):
    return {"fis_no": no, "degismeyen": deg, "tarih": tarih, "durum": durum,
            "satirlar": ([("191.108.20", "KDV", 10, 0, "kdv", "89582", tarih, bt, "")] if fatura else []) + [
                         ("102.04", "ALBARAKA", 0, 288, "komisyon", "89582", tarih, bt, ""),
                         ("780.001", "KOMISYON VE FAIZ GIDERI", 288, 0, "komisyon", "89582", tarih, bt, ""),
                         ("102.04", "ALBARAKA", 0, 14.4, "bsmv", "89582", tarih, bt, "")]}


class UctanUca(unittest.TestCase):
    def setUp(self):
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError as e:
            self.skipTest(str(e))
        f = "ALFA ISLETME"
        self.fis_veri = {(f, "20021", "Ekim"): [{"fis_no": "00012", "tarih": "03/10/2026", "aciklama": "numarasız fiş"},
                                                 {"fis_no": "00013", "tarih": "04/10/2026", "aciklama": "ikinci"}],
                         (f, "20025", "Ekim"): [{"fis_no": "1", "tarih": "x", "aciklama": "y"}] * 3}
        self.veri = {(f, "20041"): [fis(f"0{100 + i}", f"9000{i}", f"0{i}/10/2026", fatura=(i == 2)) for i in range(1, 6)],  # 5 fis: 3 sayfa; 2.si fatura fisi
                     (f, "20047"): [fis("0200", "91000", "09/10/2026", bt="FT")]}

    def _dogrula(self, sonuc, cikti):
        s = sonuc["ALFA ISLETME"]
        self.assertEqual(s["durum"], "sorun var", cikti[-2500:])
        kodlar = {h["kod"]: h for h in s["hatalar"]}
        self.assertEqual(list(kodlar), ["20041", "20042", "20044", "20045", "20046", "20047", "20048", "20021", "20025", "20026"])
        self.assertEqual({k: h["fis_sayisi"] for k, h in kodlar.items()},
                         {"20041": 5, "20042": 0, "20044": 0, "20045": 0, "20046": 0, "20047": 1, "20048": 0,
                          "20021": 2, "20025": 3, "20026": 0})
        h = kodlar["20041"]
        self.assertEqual([f["fis_no"] for f in h["fisler"]], ["0101", "0102", "0103", "0104", "0105"])     # 3 sayfa birlestirildi
        self.assertEqual((h["satir_sayisi"], h["kesildi"], h["fisler"][0]["satir"], h["fisler"][0]["evrak"], h["fisler"][0]["bt"]),
                         (16, False, 3, ["89582"], "MF"))                                  # 15 + fatura fisinin 191 satiri
        self.assertEqual((h["fatura_fisi"], h["diger_fis"]), (1, 4))                       # 191/391 olan fis dokunulmayacak fatura fisi
        self.assertEqual([f["fatura_fisi"] for f in h["fisler"]], [False, True, False, False, False])
        self.assertEqual(h["fisler"][1]["hp"], ["191", "102", "780"])
        self.assertIn("1 fatura fişi (191/391 var: elle), 4 diğer fiş (MF + evrak no atanabilir)", cikti)
        self.assertEqual(h["fisler"][0]["tutar"], 288.0)
        self.assertEqual(h["fisler"][0]["durum"], ["Evrak No boş olamaz."])                 # Luca'nin satir aciklamasi
        self.assertEqual(kodlar["20047"]["fisler"][0]["bt"], "FT")
        self.assertFalse(any(x["hata"] for x in s["hatalar"]), s["hatalar"])
        self.assertIn("UYUMSUZ  20041  Belge türü tanımı yok: 5 fiş", cikti)
        self.assertIn("UYUMSUZ  20047", cikti)

    def test_her_hata_kodu_icin_liste_okunur_sayfalar_birlestirilir_kaydet_basilmaz(self):
        kod, sonuc, cikti, sahte = calistir(veri=self.veri, fis_veri=self.fis_veri)
        self.assertEqual(kod, 0, cikti[-2500:])
        self._dogrula(sonuc, cikti)
        self.assertEqual(sahte["kaydet"], 0)                                           # Kaydet'e hic basilmadi
        # her kod icin liste istegi: tarihler, e-Defter kutusu acik; 20041 icin sayfalar 1..3 + son sayfadan sonraki bos sayfa
        istek = [i for i in sahte["istekler"] if i["kod"] == "20041"]
        self.assertEqual([i["sayfa"] for i in istek], ["1", "2", "3", "4"])
        self.assertEqual((istek[0]["bas"], istek[0]["bit"], istek[0]["edefter"]), ("01/10/2026", "31/10/2026", "1"))
        self.assertTrue(all(i["kayit"] == "1000" for i in sahte["istekler"]), sahte["istekler"])   # sayfa basina kayit en yukseklere cikarildi
        self.assertIn("Sayfa No/Kayıt Sayısı listeleri", cikti)
        self.assertIn("[Evrak No boş olamaz.]", cikti)
        self.assertTrue((calistir.klasor / "cikti" / "edefter.xlsx").exists())

    def test_e_defter_kutusu_isaretsizse_tiklanir_etiketle_ayni_hucredeyse_de(self):
        """Gercek Luca'da kutu varsayilan isaretsiz olabilir: isaretlenmezse Luca liste getirmez (eski surum 0 fis sanirdi)."""
        for gorunum in ("isaretsiz", "ayni_hucre", "gizli", "gizli_gecikmeli"):
            kod, sonuc, cikti, sahte = calistir(veri=self.veri, ayar={"edefter_kutu": gorunum}, ek_arg=["--hata-kodu", "20041"])
            self.assertEqual(kod, 0, cikti[-2500:])
            self.assertEqual(sonuc["ALFA ISLETME"]["hatalar"][0]["fis_sayisi"], 5, (gorunum, cikti[-2000:]))
            self.assertTrue(all(i["edefter"] == "1" for i in sahte["istekler"]), sahte["istekler"])
            self.assertIn("Onay kutuları", cikti)

    def test_form_acilirken_sayfa_yenilenirse_okuma_yeniden_denenir(self):
        """Gercek Luca'da form penceresi acilirken yenilenebilir ("Execution context was destroyed"): firma iptal olmaz."""
        kod, sonuc, cikti, sahte = calistir(veri=self.veri, ayar={"form_yenile": True, "edefter_kutu": "gizli"},
                                            ek_arg=["--hata-kodu", "20041", "--hata-kodu", "20047"])
        self.assertEqual(kod, 0, cikti[-2500:])
        kodlar = {h["kod"]: h for h in sonuc["ALFA ISLETME"]["hatalar"]}
        self.assertEqual((kodlar["20041"]["fis_sayisi"], kodlar["20047"]["fis_sayisi"]), (5, 1), cikti[-2500:])
        self.assertFalse(any(h["hata"] for h in kodlar.values()), kodlar)

    def test_fis_listesi_kodlari_tablo_uyari_ve_kayit_yok(self):
        kod, sonuc, cikti, sahte = calistir(veri=self.veri, fis_veri=self.fis_veri, ek_arg=["--hata-kodu", "20021", "--hata-kodu", "20025", "--hata-kodu", "20026"])
        self.assertEqual(kod, 0, cikti[-2500:])
        s = sonuc["ALFA ISLETME"]
        kodlar = {h["kod"]: h for h in s["hatalar"]}
        self.assertEqual(list(kodlar), ["20021", "20025", "20026"])                              # Belge Turu ekrani acilmadi
        self.assertNotIn("Belge Türü Düzenleme formu açıldı", cikti)
        self.assertEqual([(f["fis_no"], f["tarih"], f["aciklama"]) for f in kodlar["20021"]["fisler"]],
                         [("00012", "03/10/2026", "numarasız fiş"), ("00013", "04/10/2026", "ikinci")])
        self.assertEqual((kodlar["20021"]["fis_sayisi"], kodlar["20025"]["fis_sayisi"], kodlar["20026"]["fis_sayisi"]), (2, 3, 0))
        self.assertIn("3 adet dengesiz", kodlar["20025"]["mesaj"])
        self.assertIn("bulunamad", kodlar["20026"]["mesaj"])
        self.assertEqual(s["durum"], "sorun var")
        # E-Defter Ay = donemin ayi (Ekim), onay kutusu isaretli, istenen kodlar sorgulandi
        self.assertEqual({(i["kod"], i["ay"], i["edefter"]) for i in sahte["fis_istekler"]},
                         {("20021", "Ekim", "1"), ("20025", "Ekim", "1"), ("20026", "Ekim", "1")})
        self.assertIn("Fiş Listesi: E-Defter Ay=Ekim", cikti)

    def test_fis_listesi_uc_onay_kutusu_tek_hucredeyse_dogru_kutu_isaretlenir(self):
        """Gercek Luca'da Fis Listesi'nde ucu tek hucrede alt alta: hucre metni etikete esit olmaz, kutu yanindaki yaziyla bulunur."""
        kod, sonuc, cikti, sahte = calistir(veri=self.veri, fis_veri=self.fis_veri, fis_ayar={"kutu": "tek_hucre"},
                                            ek_arg=["--hata-kodu", "20021"])
        self.assertEqual(kod, 0, cikti[-2500:])
        h = sonuc["ALFA ISLETME"]["hatalar"][0]
        self.assertEqual((h["kod"], h["fis_sayisi"], h["hata"]), ("20021", 2, ""), cikti[-2000:])
        self.assertTrue(all(i["edefter"] == "1" for i in sahte["fis_istekler"]), sahte["fis_istekler"])

    def test_fis_listesi_listele_dugmesi_resimli_kutuysa_basligindan_bulunur(self):
        kod, sonuc, cikti, sahte = calistir(veri=self.veri, fis_veri=self.fis_veri, fis_ayar={"dugme": "kutu_title", "kutu": "tek_hucre"},
                                            ek_arg=["--hata-kodu", "20021"])
        self.assertEqual(kod, 0, cikti[-2500:])
        self.assertEqual(sonuc["ALFA ISLETME"]["hatalar"][0]["fis_sayisi"], 2, cikti[-2000:])
        self.assertIn("DIV:Listele", cikti)

    def test_fis_listesi_sonucu_okunamazsa_hata_yazilir_gonderilebilir_denmez(self):
        kod, sonuc, cikti, sahte = calistir(veri=self.veri, fis_modlar={"20025": "hicbir"}, ek_arg=["--hata-kodu", "20025"])
        s = sonuc["ALFA ISLETME"]
        self.assertIn("tablo ya da mesaj gelmedi", s["hatalar"][0]["hata"])
        self.assertEqual(s["durum"], "hata")

    def test_belge_turu_bos_olan_kutusu_kapatilir(self):
        kod, sonuc, cikti, sahte = calistir(veri=self.veri, ayar={"belge_bos_varsayilan": True}, ek_arg=["--hata-kodu", "20041"])
        self.assertEqual(kod, 0, cikti[-2500:])
        self.assertTrue(sahte["istekler"] and all(i["belge_bos"] == "0" and i["edefter"] == "1" for i in sahte["istekler"]), sahte["istekler"])
        self.assertEqual([h["kod"] for h in sonuc["ALFA ISLETME"]["hatalar"]], ["20041"])             # yalniz istenen kod

    def test_kayit_yok_uyarisi_sorun_yok_sayilir(self):
        kod, sonuc, cikti, sahte = calistir(veri={}, ayar={"kayit_yok": "uyari"})
        self.assertEqual(kod, 0, cikti[-2500:])
        s = sonuc["ALFA ISLETME"]
        self.assertEqual(s["durum"], "tamam", cikti[-2500:])
        belge = [h for h in s["hatalar"] if h["kod"] not in le.FIS_KODLARI]
        self.assertEqual(len(belge), 7)
        self.assertTrue(all(h["fis_sayisi"] == 0 and not h["hata"] and "bulunamad" in h["mesaj"] for h in belge), s["hatalar"])
        self.assertTrue(all(h["fis_sayisi"] == 0 and not h["hata"] for h in s["hatalar"]), s["hatalar"])
        self.assertIn("e-Defter kapsamında uyumsuz fiş yok", cikti)

    def test_adi_verilen_firma_kayitli_listede_yoksa_liste_yenilenir_hala_yoksa_atlanir(self):
        """Yalniz 1. sinif: kayitli liste eskiyse bir kez yeniden cekilir; gercekten 1. sinif degilse atlanir."""
        import argparse
        from unittest import mock
        import edefter
        args = argparse.Namespace(firma=["PILSA"], firma_tam=None, listeyi_yenile=False)
        cagrilar = []

        def sahte(page, adaylar, bit, ayar, log, yenile=False, sira=0, neden=""):
            cagrilar.append(yenile)
            return list(adaylar) if yenile else []                # eski liste: yok; yeni liste: var
        with mock.patch.object(edefter.mv, "birinci_sinif_firmalari", sahte):
            self.assertEqual(edefter.birinci_sinif_suz(None, ["PILSA ENER"], None, {}, args, None, 0), ["PILSA ENER"])
        self.assertEqual(cagrilar, [False, True])
        cagrilar.clear()
        with mock.patch.object(edefter.mv, "birinci_sinif_firmalari", lambda *a, **k: cagrilar.append(k.get("yenile", a[5] if len(a) > 5 else False)) or []):
            self.assertEqual(edefter.birinci_sinif_suz(None, ["PILSA ENER"], None, {}, args, None, 0), [])      # 2. sinif: atlanir
        self.assertEqual(len(cagrilar), 2)
        # firma adi verilmediyse (tum liste) kayitli liste yeterli: yeniden cekilmez
        cagrilar.clear()
        args2 = argparse.Namespace(firma=None, firma_tam=None, listeyi_yenile=False)
        with mock.patch.object(edefter.mv, "birinci_sinif_firmalari", sahte):
            edefter.birinci_sinif_suz(None, ["A"], None, {}, args2, None, 0)
        self.assertEqual(cagrilar, [False])

    def test_liste_form_penceresinde_acilirsa_form_yeniden_acilir(self):
        kod, sonuc, cikti, sahte = calistir(veri=self.veri, ayar={"ayni_pencere": True}, ek_arg=["--hata-kodu", "20041", "--hata-kodu", "20047"])
        self.assertEqual(kod, 0, cikti[-2500:])
        kodlar = {h["kod"]: h for h in sonuc["ALFA ISLETME"]["hatalar"]}
        self.assertEqual((kodlar["20041"]["fis_sayisi"], kodlar["20047"]["fis_sayisi"]), (5, 1), cikti[-2500:])


if __name__ == "__main__":
    unittest.main()
