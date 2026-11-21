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


def calistir(klasor_rapor=None, veri=None, ayar=None, ek_arg=(), firma="ALFA ISLETME", tarih="01/10/2026-31/10/2026"):
    """Sahte Luca + edefter.py: (cikis kodu, sonuc sozlugu {firma: sonuc}, cikti, sahte sunucunun kaydettikleri)."""
    import sahte_kz
    sahte_kz.sifirla()
    sahte_kz.EDEFTER_VERI.update(veri or {})
    sahte_kz.EDEFTER_AYAR.update(ayar or {})
    klasor = Path(tempfile.mkdtemp(prefix="edefter-uu-"))
    sunucu, adres = sahte_kz.baslat()
    ayarlar = {"giris_adresi": adres, "tarayici": "chromium", "tarayici_yolu": os.environ.get("LUCA_TEST_CHROMIUM", ""),
               "tarayici_sandbox": os.name == "nt", "profil_yerel": True}
    (klasor / "ayarlar.json").write_text(json.dumps(ayarlar), encoding="utf-8")
    ortam = dict(os.environ, LUCA_BOT_AYAR=str(klasor / "ayarlar.json"), LOCALAPPDATA=str(klasor / "yerel"),
                 KARZARAR_CIKTI=str(klasor / "cikti"), PYTHONIOENCODING="utf-8")
    komut = [sys.executable, str(KOK / "edefter.py"), "--tarih", tarih, "--firma-tam", firma, "--tum-firmalar", "--bitince-kapat",
             *ek_arg]
    r = subprocess.run(komut, env=ortam, cwd=str(KOK), capture_output=True, text=True, encoding="utf-8")
    sunucu.shutdown()
    try:
        sonuc = {f["firma"]: f for f in json.loads((klasor / "cikti" / "edefter.json").read_text(encoding="utf-8"))["firmalar"]}
    except OSError:
        sonuc = {}
    calistir.klasor = klasor
    return r.returncode, sonuc, r.stdout + r.stderr, dict(sahte_kz.EDEFTER_AYAR, istekler=list(sahte_kz.EDEFTER_AYAR["istekler"]))


def fis(no, deg, tarih, evrakli=True, bt="MF"):
    return {"fis_no": no, "degismeyen": deg, "tarih": tarih,
            "satirlar": [("102.04", "ALBARAKA", 0, 288, "komisyon", "89582", tarih, bt, ""),
                         ("780.001", "KOMISYON VE FAIZ GIDERI", 288, 0, "komisyon", "89582", tarih, bt, ""),
                         ("102.04", "ALBARAKA", 0, 14.4, "bsmv", "89582", tarih, bt, "")]}


class UctanUca(unittest.TestCase):
    def setUp(self):
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError as e:
            self.skipTest(str(e))
        f = "ALFA ISLETME"
        self.veri = {(f, "20041"): [fis(f"0{100 + i}", f"9000{i}", f"0{i}/10/2026") for i in range(1, 6)],     # 5 fis: 3 sayfa
                     (f, "20047"): [fis("0200", "91000", "09/10/2026", bt="FT")]}

    def _dogrula(self, sonuc, cikti):
        s = sonuc["ALFA ISLETME"]
        self.assertEqual(s["durum"], "sorun var", cikti[-2500:])
        kodlar = {h["kod"]: h for h in s["hatalar"]}
        self.assertEqual(list(kodlar), ["20041", "20042", "20044", "20045", "20046", "20047", "20048"])
        self.assertEqual({k: h["fis_sayisi"] for k, h in kodlar.items()},
                         {"20041": 5, "20042": 0, "20044": 0, "20045": 0, "20046": 0, "20047": 1, "20048": 0})
        h = kodlar["20041"]
        self.assertEqual([f["fis_no"] for f in h["fisler"]], ["0101", "0102", "0103", "0104", "0105"])     # 3 sayfa birlestirildi
        self.assertEqual((h["satir_sayisi"], h["kesildi"], h["fisler"][0]["satir"], h["fisler"][0]["evrak"], h["fisler"][0]["bt"]),
                         (15, False, 3, ["89582"], "MF"))
        self.assertEqual(h["fisler"][0]["tutar"], 288.0)
        self.assertEqual(kodlar["20047"]["fisler"][0]["bt"], "FT")
        self.assertFalse(any(x["hata"] for x in s["hatalar"]), s["hatalar"])
        self.assertIn("UYUMSUZ  20041  Belge türü tanımı yok: 5 fiş", cikti)
        self.assertIn("UYUMSUZ  20047", cikti)

    def test_her_hata_kodu_icin_liste_okunur_sayfalar_birlestirilir_kaydet_basilmaz(self):
        kod, sonuc, cikti, sahte = calistir(veri=self.veri)
        self.assertEqual(kod, 0, cikti[-2500:])
        self._dogrula(sonuc, cikti)
        self.assertEqual(sahte["kaydet"], 0)                                           # Kaydet'e hic basilmadi
        # her kod icin liste istegi: tarihler, e-Defter kutusu acik; 20041 icin sayfalar 1..3 + son sayfadan sonraki bos sayfa
        istek = [i for i in sahte["istekler"] if i["kod"] == "20041"]
        self.assertEqual([i["sayfa"] for i in istek], ["1", "2", "3", "4"])
        self.assertEqual((istek[0]["bas"], istek[0]["bit"], istek[0]["edefter"]), ("01/10/2026", "31/10/2026", "1"))
        self.assertTrue((calistir.klasor / "cikti" / "edefter.xlsx").exists())

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
        self.assertTrue(all(h["fis_sayisi"] == 0 and not h["hata"] and "bulunamad" in h["mesaj"] for h in s["hatalar"]), s["hatalar"])
        self.assertIn("e-Defter kapsamında uyumsuz fiş yok", cikti)

    def test_liste_form_penceresinde_acilirsa_form_yeniden_acilir(self):
        kod, sonuc, cikti, sahte = calistir(veri=self.veri, ayar={"ayni_pencere": True}, ek_arg=["--hata-kodu", "20041", "--hata-kodu", "20047"])
        self.assertEqual(kod, 0, cikti[-2500:])
        kodlar = {h["kod"]: h for h in sonuc["ALFA ISLETME"]["hatalar"]}
        self.assertEqual((kodlar["20041"]["fis_sayisi"], kodlar["20047"]["fis_sayisi"]), (5, 1), cikti[-2500:])


if __name__ == "__main__":
    unittest.main()
