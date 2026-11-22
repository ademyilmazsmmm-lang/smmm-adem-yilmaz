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

    def test_fatura_191_borc_391_alacak_hareketinden_anlasilir_gerisi_fatura_degildir(self):
        satirlar = [satir(1, "01", "111", "01/07/2026", hesap="320.01 SATICI", alacak="120,00"), satir("", hesap="191.108.20 KDV", borc="20,00"),   # alis: 191 borc
                    satir("", hesap="770.01 GIDER", borc="100,00"),
                    satir(2, "02", "112", "02/07/2026", hesap="102.04 BANKA", alacak="50,00"), satir("", hesap="100.01 KASA", borc="50,00"),       # mahsup
                    satir(3, "03", "113", "03/07/2026", hesap="120.01 ALICI", borc="120,00"), satir("", hesap="391.00.20 KDV", alacak="20,00"),    # satis: 391 alacak
                    satir("", hesap="601.01 SATIS", alacak="100,00"),
                    satir(4, "04", "114", "04/07/2026", hesap="120.02 ALICI", borc="100,00"), satir("", hesap="601.01 SATIS", alacak="100,00"),   # 391 yok: fatura degil
                    satir(5, "05", "115", "05/07/2026", hesap="320.02 SATICI", alacak="100,00"), satir("", hesap="770.02 GIDER", borc="100,00"),  # KDV'siz gider
                    satir(6, "06", "116", "06/07/2026", hesap="102.01 BANKA", alacak="20,00"), satir("", hesap="780.02 KOMISYON", borc="20,00"),   # banka komisyonu
                    satir(7, "07", "117", "07/07/2026", hesap="191.108.20 KDV", alacak="20,00"), satir("", hesap="320.01 SATICI", borc="20,00"),  # 191 ALACAK (iade): fatura degil
                    satir(8, "08", "118", "08/07/2026", hesap="391.00.20 KDV", borc="20,00"), satir("", hesap="120.01 ALICI", alacak="20,00"),    # 391 BORC (iade): fatura degil
                    satir(9, "09", "119", "09/07/2026", hesap="102.05 BANKA", bt="FT")]                                                         # belge turu FT: dokunulmaz
        liste = list(le.fisleri_grupla(BASLIKLAR, satirlar).values())
        self.assertEqual([le.fatura_fisi_mi(f) for f in liste], [True, False, True, False, False, False, False, False, True])
        self.assertEqual([le.fatura_nedeni(f)[:6] for f in liste if le.fatura_fisi_mi(f)], ["191 bo", "191 bo", "belge "])
        self.assertEqual(liste[0]["hp"], ["320", "191", "770"])
        self.assertIsNone(le.fatura_fisi_mi({"hp": []}))                                  # hesap okunamadi: sinif belirsiz
        self.assertIn("(fatura fişi: 191 borç", ek.fis_satiri(dict(liste[0], fatura_fisi=True, fatura_neden=le.fatura_nedeni(liste[0]))))
        self.assertIn("(diğer fiş)", ek.fis_satiri(dict(liste[1], fatura_fisi=False)))

    def test_duzeltme_plani_yalniz_fatura_olmayan_fislerin_satirlarini_secer(self):
        satirlar = [satir(1, "01", "111", "01/07/2026", hesap="102.04 BANKA"), satir("", hesap="100.01 KASA"),
                    satir(2, "02", "112", "02/07/2026", hesap="120.02 ALICI", borc="120,00"), satir("", hesap="391.01 KDV", alacak="20,00"),
                    satir(3, "03", "113", "03/07/2026", hesap="102.01 BANKA"), satir("", hesap="120.01 ALICI"), satir("", hesap="320.01")]
        hedef, fis_sayisi, fatura = le.duzeltme_plani(BASLIKLAR, satirlar)
        self.assertEqual((hedef, fis_sayisi, fatura), ([0, 1, 4, 5, 6], 2, 1))
        hedef, fis_sayisi, _ = le.duzeltme_plani(BASLIKLAR, satirlar, son_fisi_disla=True)      # cok sayfali liste: sayfa sonundaki fis atlanir
        self.assertEqual((hedef, fis_sayisi), ([0, 1], 1))
        # fis basi gorulmeden gelen devam satirlari (onceki sayfadan) secilmez
        hedef, _, _ = le.duzeltme_plani(BASLIKLAR, [satir("", hesap="102.01")] + satirlar[:2])
        self.assertEqual(hedef, [1, 2])

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


def fis(no, deg, tarih, evrakli=True, bt="MF", durum="Evrak No boş olamaz.", fatura=False, hesap="100.01", hesaplar=None):
    ev, et = ("89582", tarih) if evrakli else ("", "")
    if hesaplar:                       # ozel hesap listesi (ilki borc, digerleri alacak)
        return {"fis_no": no, "degismeyen": deg, "tarih": tarih, "durum": durum,
                "satirlar": [(h, "HESAP", 100 if i == 0 else 0, 0 if i == 0 else 100, "x", ev, et, bt, "") for i, h in enumerate(hesaplar)]}
    return {"fis_no": no, "degismeyen": deg, "tarih": tarih, "durum": durum,
            "satirlar": ([("191.108.20", "KDV", 10, 0, "kdv", ev, et, bt, "")] if fatura else []) + [
                         ("102.04", "ALBARAKA", 0, 288, "komisyon", ev, et, bt, ""),
                         (hesap, "KASA", 288, 0, "komisyon", ev, et, bt, ""),
                         ("102.04", "ALBARAKA", 0, 14.4, "bsmv", ev, et, bt, "")]}


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
        self.assertEqual(h["fisler"][1]["hp"], ["191", "102", "100"])
        self.assertIn("1 fatura fişi (191 borç / 391 alacak / FT: elle), 4 diğer fiş (MF + evrak no atanabilir)", cikti)
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

    def _duzeltme_veri(self):
        f = "ALFA ISLETME"
        bos = dict(evrakli=False, bt="")
        return {(f, "20042"): [fis("0301", "92001", "05/10/2026", **bos),                                  # kasa/banka fisi: duzeltilir
                               fis("0302", "92002", "06/10/2026", fatura=True, **bos),                      # 191 var: dokunulmaz
                               fis("0303", "92003", "07/10/2026", hesaplar=["120.01", "391.01"], **bos),    # satis: 391 alacak: dokunulmaz
                               fis("0304", "92004", "08/10/2026", **bos)]}                                  # ikinci duzeltilebilir fis

    def test_duzelt_yalniz_fatura_olmayan_fislere_mf_evrak_no_ve_tarih_atar_kaydeder_dogrular(self):
        kod, sonuc, cikti, sahte = calistir(veri=self._duzeltme_veri(), ayar={"sayfa_boyu": 50}, ek_arg=("--duzelt", "--hata-kodu", "20042"))
        self.assertEqual(kod, 0, cikti[-3000:])
        self.assertEqual(sahte["kaydet"], 6, cikti[-3000:])
        kaydedilen = sahte["kaydet_ayrinti"]
        self.assertEqual({d["fis_no"] for d in kaydedilen}, {"0301", "0304"})                 # yalniz secilen (fatura olmayan) fislerin satirlari kaydedildi
        self.assertEqual(len(kaydedilen), 6)                                                  # 3 + 3 satir, TEK TEK
        self.assertEqual({(d["no"], d["et"], d["bt"]) for d in kaydedilen if d["fis_no"] == "0301"}, {("92001", "", "MF")})
        self.assertEqual({(d["no"], d["et"], d["bt"]) for d in kaydedilen if d["fis_no"] == "0304"}, {("92004", "", "MF")})
        h = {x["kod"]: x for x in sonuc["ALFA ISLETME"]["hatalar"]}["20042"]
        self.assertEqual((h["fis_sayisi"], h["fatura_fisi"], h["diger_fis"]), (2, 2, 0))          # kalan: yalniz fatura/satis fisleri
        self.assertEqual((h["duzeltme"]["fis"], h["duzeltme"]["satir"], h["duzeltme"]["kaydedildi"], h["duzeltme"]["fatura_fis"]), (2, 6, 1, 2))
        self.assertEqual(h["duzeltme"]["kayit_hatasi"], 0)
        self.assertEqual(sonuc["ALFA ISLETME"]["durum"], "sorun var")                          # fatura fisleri elle duzeltilecek
        self.assertIn("DÜZELTME 20042: 2 fiş (6 satır) MF + evrak no ile düzeltildi", cikti)

    def test_kdv_siz_gider_ve_satis_fisi_fatura_sayilmaz_mf_alir_iade_de_fatura_degildir(self):
        f = "ALFA ISLETME"
        veri = {(f, "20042"): [fis("0401", "93001", "05/10/2026", evrakli=False, bt="", hesaplar=["770.01", "320.01"]),     # KDV'siz gider alisi
                               fis("0402", "93002", "06/10/2026", evrakli=False, bt="", hesaplar=["120.01", "601.01"]),     # 391 olmayan satis
                               fis("0403", "93003", "07/10/2026", evrakli=False, bt="", hesaplar=["120.01", "391.01"])]}    # 391 alacak: fatura
        kod, sonuc, cikti, sahte = calistir(veri=veri, ayar={"sayfa_boyu": 50}, ek_arg=("--duzelt", "--hata-kodu", "20042"))
        self.assertEqual(kod, 0, cikti[-2500:])
        self.assertEqual({d["fis_no"] for d in sahte["kaydet_ayrinti"]}, {"0401", "0402"})                  # fatura olmayanlar MF aldi, 0403'e dokunulmadi
        h = sonuc[f]["hatalar"][0]
        self.assertEqual((h["fis_sayisi"], h["fatura_fisi"], h["diger_fis"]), (1, 1, 0))
        self.assertIn("191 borç / 391 alacak (kesin fatura)", h["fisler"][0]["fatura_neden"])

    def test_duzelt_verilmezse_kaydet_basilmaz(self):
        kod, sonuc, cikti, sahte = calistir(veri=self._duzeltme_veri(), ayar={"sayfa_boyu": 50}, ek_arg=("--hata-kodu", "20042"))
        self.assertEqual((kod, sahte["kaydet"]), (0, 0), cikti[-2000:])
        h = {x["kod"]: x for x in sonuc["ALFA ISLETME"]["hatalar"]}["20042"]
        self.assertEqual((h["fis_sayisi"], h["diger_fis"], "duzeltme" in h), (4, 2, False))

    def test_duzelt_kaydi_luca_kabul_etmezse_tekrarlanmaz_ve_bildirilir(self):
        kod, sonuc, cikti, sahte = calistir(veri=self._duzeltme_veri(), ayar={"sayfa_boyu": 50, "kaydet_kabul": False},
                                            ek_arg=("--duzelt", "--hata-kodu", "20042"))
        self.assertEqual((kod, sahte["kaydet"]), (0, 6), cikti[-2500:])               # 6 satir kaydedildi, Luca yok saydi
        h = {x["kod"]: x for x in sonuc["ALFA ISLETME"]["hatalar"]}["20042"]
        self.assertIn("hâlâ uyumsuz listeleniyor", h["duzeltme"]["mesaj"])
        self.assertEqual(sonuc["ALFA ISLETME"]["durum"], "sorun var")

    def test_duzelt_cok_sayfali_listede_sayfa_sonundaki_fis_atlanir_turlarla_tamamlanir(self):
        kod, sonuc, cikti, sahte = calistir(veri=self._duzeltme_veri(), ayar={"sayfa_boyu": 2}, ek_arg=("--duzelt", "--hata-kodu", "20042"))
        self.assertEqual(kod, 0, cikti[-3000:])
        h = {x["kod"]: x for x in sonuc["ALFA ISLETME"]["hatalar"]}["20042"]
        self.assertEqual((h["fis_sayisi"], h["diger_fis"]), (2, 0), cikti[-3000:])
        self.assertEqual({d["fis_no"] for d in sahte["kaydet_ayrinti"]}, {"0301", "0304"})   # hicbir turda fatura fisinin satiri kaydedilmedi

    def test_duzelt_satir_satir_kayit_bitene_kadar_beklenir(self):
        # her satirin kaydi 0,7 sn: 6 satir ~4,2 sn. Beklenmezse (eski 2,5 sn) liste yarim kayitla okunur ve fis kalir
        kod, sonuc, cikti, sahte = calistir(veri=self._duzeltme_veri(), ayar={"sayfa_boyu": 50, "kaydet_gecikme": 0.7},
                                            ek_arg=("--duzelt", "--hata-kodu", "20042"))
        self.assertEqual(kod, 0, cikti[-3000:])
        h = {x["kod"]: x for x in sonuc["ALFA ISLETME"]["hatalar"]}["20042"]
        self.assertEqual((h["fis_sayisi"], h["diger_fis"], h["duzeltme"]["kaydedildi"]), (2, 0, 1), cikti[-3000:])
        self.assertEqual(len(sahte["kaydet_ayrinti"]), 6)

    def test_duzelt_luca_satir_hatasi_verirse_raporlanir(self):
        kod, sonuc, cikti, sahte = calistir(veri=self._duzeltme_veri(), ayar={"sayfa_boyu": 50, "kaydet_hata": "ORA-20999: E-Defter Verileri Değiştirilemez."},
                                            ek_arg=("--duzelt", "--hata-kodu", "20042"))
        self.assertEqual(kod, 0, cikti[-3000:])
        h = {x["kod"]: x for x in sonuc["ALFA ISLETME"]["hatalar"]}["20042"]
        self.assertEqual(h["duzeltme"]["kayit_hatasi"], 6)
        self.assertIn("Luca kayıt hatası verdi", h["duzeltme"]["mesaj"])
        self.assertEqual((h["fis_sayisi"], h["diger_fis"]), (4, 2))                              # hicbir sey degismedi

    def _detaysiz(self, adet=1, borc="0,00"):
        f = "ALFA ISLETME"
        return {(f, "20026", "Ekim"): [{"fis_no": f"0124{8 + i}", "tarih": f"{20 + i}/10/2026", "aciklama": "", "borc": borc, "alacak": "0,00"} for i in range(adet)]}

    def _fis20026(self, fis_veri, ek_arg=(), **ayar):
        return calistir(fis_veri=fis_veri, fis_modlar={"20026": "liste"}, fis_ayar=ayar, ek_arg=("--hata-kodu", "20026") + tuple(ek_arg))

    def test_fis_listesi_satirlar_basliktan_sonra_dolarsa_beklenir_bos_sanilmaz(self):
        kod, sonuc, cikti, sahte = self._fis20026(self._detaysiz(), gecikme=2500)           # baslik hemen, satirlar 2,5 sn sonra
        self.assertEqual(kod, 0, cikti[-2500:])
        h = sonuc["ALFA ISLETME"]["hatalar"][0]
        self.assertEqual((h["kod"], h["fis_sayisi"], h["hata"]), ("20026", 1, ""), cikti[-2500:])
        self.assertEqual(h["fisler"][0]["fis_no"], "01248")
        self.assertEqual(sonuc["ALFA ISLETME"]["durum"], "sorun var")
        self.assertEqual(sahte["fis_istekler"] and 1, 1)

    def test_fis_listesi_donemi_tarih_kutulari_belirler_secilen_ayin_tarihleri_yazilir(self):
        # fiş Eylül'de: E-Defter Ay secimi tarih kutularina yansimadigi icin (gercek Luca) kutulara ayin ilk/son gunu yazilmali
        f = "ALFA ISLETME"
        veri = {(f, "20026", "Eylül"): [{"fis_no": "01248", "tarih": "30/09/2026", "aciklama": "", "borc": "0,00", "alacak": "0,00"}]}
        kod, sonuc, cikti, sahte = calistir(fis_veri=veri, fis_modlar={"20026": "liste"}, tarih="01/09/2026-31/10/2026", ek_arg=("--hata-kodu", "20026"))
        self.assertEqual(kod, 0, cikti[-2500:])
        h = sonuc[f]["hatalar"][0]
        self.assertEqual((h["fis_sayisi"], h["hata"]), (1, ""), cikti[-2500:])
        self.assertEqual([(i["ilk"], i["son"]) for i in sahte["fis_istekler"]], [("01/09/2026", "30/09/2026"), ("01/10/2026", "31/10/2026")])
        self.assertIn("Luca: kayıt sayısı 0", cikti)                      # Ekim'de gercekten 0: Luca'nin kayit sayisindan bilinir

    def test_fis_listesi_baska_ay_icin_listelenirse_sessizce_sifir_denmez(self):
        kod, sonuc, cikti, _ = self._fis20026(self._detaysiz(), tarih_yoksay=True)
        h = sonuc["ALFA ISLETME"]["hatalar"][0]
        self.assertIn("istenen ay için değil", h["hata"])
        self.assertEqual(sonuc["ALFA ISLETME"]["durum"], "hata")

    def test_fis_listesi_baslik_satirlarla_eslesmezse_yedek_okuyucu_kullanilir(self):
        kod, sonuc, cikti, _ = self._fis20026(self._detaysiz(2), duzen="ayri")             # baslik ayri tablo + fazladan sutun
        self.assertEqual(kod, 0, cikti[-2500:])
        self.assertEqual(sonuc["ALFA ISLETME"]["hatalar"][0]["fis_sayisi"], 2, cikti[-2500:])
        self.assertIn("yedek okuyucu", cikti)

    def test_duzelt_detaysiz_fisleri_secip_sil_ile_siler_varsayilanda_silmez(self):
        kod, sonuc, cikti, sahte = self._fis20026(self._detaysiz(2))                        # --duzelt yok: dokunulmaz
        self.assertEqual((sahte.get("fis_silinen"), sonuc["ALFA ISLETME"]["hatalar"][0]["fis_sayisi"]), (None, 2))
        import sahte_kz
        self.assertEqual(sahte_kz.FIS_AYAR["silinen"], [])
        kod, sonuc, cikti, _ = self._fis20026(self._detaysiz(2), ek_arg=("--duzelt",))
        self.assertEqual(kod, 0, cikti[-3000:])
        self.assertEqual(sorted(x[2] for x in sahte_kz.FIS_AYAR["silinen"]), ["01248", "01249"])         # ikisi de tek tek silindi
        h = sonuc["ALFA ISLETME"]["hatalar"][0]
        self.assertEqual((h["fis_sayisi"], h["duzeltme"]["silinen"]), (0, 2), cikti[-3000:])
        self.assertEqual(sonuc["ALFA ISLETME"]["durum"], "tamam")
        self.assertIn("DÜZELTME 20026: 2 detaysız fiş silindi", cikti)

    def test_detaysiz_silme_satirda_fazladan_hucre_olsa_da_borc_alacak_basliktan_okunur(self):
        kod, sonuc, cikti, _ = self._fis20026(self._detaysiz(2), ek_arg=("--duzelt",), duzen="ayri")      # satirlarda gizli fazladan hucre
        import sahte_kz
        self.assertEqual(sorted(x[2] for x in sahte_kz.FIS_AYAR["silinen"]), ["01248", "01249"], cikti[-2500:])
        self.assertEqual(sonuc["ALFA ISLETME"]["hatalar"][0]["duzeltme"]["silinen"], 2)

    def test_borcu_alacagi_dolu_fis_varsa_hicbir_sey_silinmez(self):
        kod, sonuc, cikti, _ = self._fis20026(self._detaysiz(2, borc="150,00"), ek_arg=("--duzelt",))
        import sahte_kz
        self.assertEqual(sahte_kz.FIS_AYAR["silinen"], [])
        h = sonuc["ALFA ISLETME"]["hatalar"][0]
        self.assertEqual((h["fis_sayisi"], h["duzeltme"]["silinen"]), (2, 0))
        self.assertIn("güvenlik için hiçbir fiş silinmedi", h["duzeltme"]["mesaj"])

    def test_sil_calismazsa_fis_listeden_kalkmayinca_durulur(self):
        kod, sonuc, cikti, _ = self._fis20026(self._detaysiz(2), ek_arg=("--duzelt",), sil_calismaz=True)
        h = sonuc["ALFA ISLETME"]["hatalar"][0]
        self.assertEqual((h["fis_sayisi"], h["duzeltme"]["silinen"]), (2, 0))
        self.assertIn("listeden kalkmadı", h["duzeltme"]["mesaj"])

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

    def test_fis_listesi_kutu_isaretsizken_ay_ve_hata_satirlari_gizli_dugme_liste(self):
        """Gercek Luca: kutu isaretsizken E-Defter Ay/Hata gizli, dugmenin adi 'Liste' (yaninda 'Mukerrer Kayit Denetimi' var)."""
        for gizli in (True, "gecikmeli"):
            kod, sonuc, cikti, sahte = calistir(veri=self.veri, fis_veri=self.fis_veri, ek_arg=["--hata-kodu", "20021"],
                                                fis_ayar={"gizli": gizli, "kutu": "tek_hucre", "dugme": "liste"})
            self.assertEqual(kod, 0, cikti[-2500:])
            h = sonuc["ALFA ISLETME"]["hatalar"][0]
            self.assertEqual((h["fis_sayisi"], h["hata"]), (2, ""), (gizli, cikti[-2000:]))
            self.assertIn("'BUTTON:Liste' tıklandı", cikti)

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
