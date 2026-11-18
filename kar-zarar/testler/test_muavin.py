# -*- coding: utf-8 -*-
"""Muavin (191/391) / isletme defteri karsilastirmasi: Excel okuma, fatura okuma, fatura no + genel toplam kontrolu.

    python -m unittest testler.test_muavin            # yalniz mantik (tarayici yok)
"""

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from karzarar import muavin_karsilastir as mk  # noqa: E402

DONEM = (date(2026, 10, 1), date(2026, 10, 31))


def muavin_excel(yol, satirlar, bolum="191 İNDİRİLECEK KDV"):
    """Sentetik Luca muavin Excel'i: ust bilgi, hesap bolum satiri, baslik, kayitlar, toplam satiri."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["MUAVİN DEFTER"])
    ws.append(["Dönem", "01/10/2026 - 31/10/2026"])
    ws.append([bolum])
    ws.append(["Tarih", "Fiş No", "Açıklama", "Borç", "Alacak", "Bakiye"])
    for s in satirlar:
        ws.append(list(s))
    ws.append(["", "", "TOPLAM", sum(s[3] or 0 for s in satirlar), sum(s[4] or 0 for s in satirlar), ""])
    wb.save(str(yol))


def muavin_cok(yol, bolumler):
    """Tum hesaplari iceren muavin: bolumler {"191 INDIRILECEK KDV": [(tarih, fis, aciklama, borc, alacak, bakiye)], ...}."""
    from datetime import datetime
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["MUAVİN DEFTER"])
    for bolum, satirlar in bolumler.items():
        ws.append([bolum, None, None, None, "TL"])
        ws.append(["TARİH", "TİP", "FİŞ NO", "AÇIKLAMA", "BORÇ", "ALACAK", "BAKİYE", "B/A"])
        for tarih, fis, aciklama, borc, alacak, *_ in satirlar:
            ws.append([datetime.strptime(tarih, "%d/%m/%Y"), "Mahsup", fis, aciklama, borc, alacak, 0.0, 0.0])
        ws.append(["Genel Toplam :", None, None, None, 0.0, 0.0, 0.0, 0.0])
    wb.save(str(yol))


def fatura_klasoru(kok, firma, tip, satirlar, iptal=(), tevkifat=()):
    """liste.csv (18 sutunlu Toplu Sorgulama bicimi) + iptal/tevkifat csv'leri; rapor.json kaydini dondurur."""
    k = Path(kok) / firma / tip
    k.mkdir(parents=True, exist_ok=True)
    baslik = ["Fatura Tarihi", "Fatura Numarası", "Fatura Türü", "VKN/TCKN", "Açıklama", "Tevkifat Oranı", "Özel Matrah",
              "%1'lik KDV", "%8'lik KDV", "%10'lik KDV", "%18'lik KDV", "%20'lik KDV", "%1'lik Matrah", "%8'lik Matrah",
              "%10'lik Matrah", "%18'lik Matrah", "%20'lik Matrah", "Toplam"]

    def satir(no, tarih, matrah, kdv):
        return [tarih, no, "SATIS", "123", "", "", 0, 0, 0, 0, 0, kdv, 0, 0, 0, 0, matrah, matrah + kdv]

    def yaz(ad, nolar):
        with open(k / ad, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(baslik)
            for no, tarih, matrah, kdv in satirlar:
                if no in nolar:
                    w.writerow(satir(no, tarih, matrah, kdv))
    yaz("liste.csv", {s[0] for s in satirlar})
    if iptal:
        yaz("iptal-itiraz.csv", set(iptal))
    if tevkifat:
        yaz("tevkifatli.csv", set(tevkifat))
    return str(k)


class MuavinMantigi(unittest.TestCase):
    def setUp(self):
        self.klasor = Path(tempfile.mkdtemp(prefix="muavin-"))

    def _rapor(self, alis, satis, **ek):
        firma = "TEST LTD"
        klasorler = {}
        if alis is not None:
            klasorler["e-fatura-alis"] = fatura_klasoru(self.klasor, firma, "e-fatura-alis", alis, **ek)
        if satis is not None:
            klasorler["e-arsiv-satis"] = fatura_klasoru(self.klasor, firma, "e-arsiv-satis", satis)
        (self.klasor / "rapor.json").write_text(json.dumps({firma: {"klasorler": klasorler}}), encoding="utf-8")
        return firma

    def test_sinifi_bilinmeyen_firma_once_muavin_sonra_isletme_denenir(self):
        import muavin
        cagri = []

        def birinci_yok():
            cagri.append("muavin")
            raise LookupError("Muavin Defter menüsü açılamadı")

        def ikinci_var():
            cagri.append("isletme")
            return ["satir"]
        self.assertEqual(muavin.otomatik_cek(birinci_yok, ikinci_var), (["satir"], 2))
        self.assertEqual(cagri, ["muavin", "isletme"])
        self.assertEqual(muavin.otomatik_cek(lambda: ["m"], ikinci_var), (["m"], 1))     # muavin acilirsa isletmeye bakilmaz

        def ikinci_yok():
            raise LookupError("menü yok")
        with self.assertRaises(LookupError) as h:
            muavin.otomatik_cek(birinci_yok, ikinci_yok)
        self.assertIn("Muavin Defter", str(h.exception))
        self.assertIn("İşletme Defteri Dökümü", str(h.exception))

    def test_hesap_sahibi_adlari_dosyadan_okunur_yoksa_varsayilan(self):
        from lucabot import hesaplar
        eski = hesaplar._adlar_dosyasi
        try:
            hesaplar._adlar_dosyasi = lambda: None
            self.assertEqual((hesaplar.gorunen_ad("ofis"), hesaplar.gorunen_ad("isletme")), ("Ofis", "İşletme"))
            dosya = self.klasor / "hesap-adlari.json"
            dosya.write_text(json.dumps({"ofis": "Ad Bir", "isletme": "Ad Iki"}), encoding="utf-8")
            hesaplar._adlar_dosyasi = lambda: dosya
            self.assertEqual((hesaplar.gorunen_ad("ofis"), hesaplar.gorunen_ad("isletme"), hesaplar.gorunen_ad("hesap2")),
                             ("Ad Bir", "Ad Iki", "Ad Iki"))
        finally:
            hesaplar._adlar_dosyasi = eski

    def test_fatura_no_bulma(self):
        self.assertEqual(mk.fatura_no_bul("ABC2026000000123 nolu fatura"), ["ABC2026000000123"])
        self.assertEqual(mk.fatura_no_bul("x ABC-2026000000124"), ["ABC2026000000124"])
        self.assertEqual(mk.fatura_no_bul("ABC2026000000123 / DEF2026000000456"), ["ABC2026000000123", "DEF2026000000456"])
        self.assertEqual(mk.fatura_no_bul("serbest metin 12345", None), [])

    def test_muavin_excel_okunur_bolum_basligi_ve_toplam_satiri_kayit_degil(self):
        yol = self.klasor / "m191.xlsx"
        muavin_excel(yol, [("05/10/2026", 101, "ABC2026000000001 alış", 200.0, None, ""),
                           ("12/10/2026", 102, "iade ABC2026000000002", None, 50.0, ""),
                           ("20/10/2026", 103, "nolu kayıt yok", 80.0, None, "")])
        s = mk.muavin_satirlari(yol)
        self.assertEqual(len(s), 3)
        self.assertEqual(s[0]["hesap"], "191")
        self.assertEqual((s[0]["borc"], s[0]["nolar"]), (200.0, ["ABC2026000000001"]))
        self.assertEqual((s[1]["alacak"], s[1]["nolar"]), (50.0, ["ABC2026000000002"]))
        self.assertEqual(s[2]["nolar"], [])

    def test_fatura_no_ve_genel_toplam_ikisi_uyuyorsa_sorun_yok(self):
        F = lambda n, g, toplam, kdv, **ek: dict({"no": f"AAA20260000000{n:02d}", "tarih": date(2026, 10, g), "unvan": f"S{n}",
                                                   "toplam": toplam, "kdv": kdv, "tip": "x"}, **ek)
        faturalar = [F(1, 5, 1200.0, 200.0),            # numara + 320 satiri 1200: tamam
                     F(2, 6, 600.0, 100.0),             # numara hic yok: EKSIK
                     F(3, 7, 1200.0, 200.0),            # iki fiste de islenmis, ikisinde de tutar uyuyor: tamam
                     F(4, 8, 1200.0, 200.0),            # numara var, 320 satiri 900: TUTAR FARKI
                     F(5, 9, 360.0, 60.0),              # 191'de numara yok (tutar esit numarasiz satir): EKSIK
                     F(6, 9, 500.0, 0.0),               # KDV'siz: sayilmaz
                     F(7, 9, 500.0, 90.0, iptal=True),  # iptal: sayilmaz
                     F(8, 9, 700.0, None),              # KDV bilinmiyor, numara yok: EKSIK
                     F(9, 10, 590.0, 90.0),             # karsi hesap satiri yok ama 191 90 + 770 matrah 500 = 590: tamam
                     F(10, 10, 5000.0, 200.0, tevkifat=True),   # tevkifatli: yalniz numara bakilir, tamam
                     F(11, 11, 1180.0, 180.0)]          # 102 (banka) satiri 1180: tamam
        yol = self.klasor / "m.xlsx"
        muavin_cok(yol, {
            "191 İNDİRİLECEK KDV": [("05/10/2026", "1", "AAA2026000000001", 200.0, None), ("07/10/2026", "2", "AAA2026000000003", 200.0, None),
                                    ("08/10/2026", "3", "AAA2026000000003 tekrar", 200.0, None), ("08/10/2026", "4", "AAA2026000000004", 200.0, None),
                                    ("10/10/2026", "5", "fatura numarasi yazilmamis", 60.0, None), ("10/10/2026", "6", "AAA2026000000009", 90.0, None),
                                    ("10/10/2026", "7", "AAA2026000000010", 200.0, None), ("11/10/2026", "8", "AAA2026000000011", 180.0, None)],
            "320 SATICILAR": [("05/10/2026", "1", "alis", None, 1200.0), ("07/10/2026", "2", "alis", None, 1200.0),
                              ("08/10/2026", "3", "alis", None, 1200.0), ("08/10/2026", "4", "alis", None, 900.0)],
            "102 BANKALAR": [("11/10/2026", "8", "odeme", None, 1180.0)],
            "770 GENEL YÖNETİM GİDERLERİ": [("10/10/2026", "6", "matrah", 500.0, None)]})
        k = mk.karsilastir("alis", faturalar, mk.muavin_satirlari(yol))
        no = lambda liste: [f["no"][-2:] for f in liste]
        self.assertEqual(no(k["eslesen"]), ["01", "03", "09", "10", "11"])
        self.assertEqual(no(k["eksik"]), ["02", "05", "08"])
        self.assertEqual(no(k["tutar_farki"]), ["04"])
        self.assertEqual(k["tutar_farki"][0]["kayit"], [900.0])
        self.assertEqual((len(k["kdvsiz"]), len(k["iptal"])), (1, 1))

    def test_genel_toplam_karsi_hesaplar_100_102_309_320_120_108_321_121(self):
        for hesap in ("100", "102", "309", "320", "120", "108", "321", "121"):
            self.assertIn(hesap, mk.KARSI_HESAPLAR)
        f = [{"no": "AAA2026000000001", "tarih": date(2026, 10, 5), "unvan": "A", "toplam": 1200.0, "kdv": 200.0, "tip": "x"}]
        for karsi in ("100", "309", "108", "321"):
            yol = self.klasor / f"k{karsi}.xlsx"
            muavin_cok(yol, {"191 KDV": [("05/10/2026", "1", "AAA2026000000001", 200.0, None)],
                             f"{karsi} KARSI": [("05/10/2026", "1", "x", None, 1200.0)]})
            self.assertEqual(len(mk.karsilastir("alis", f, mk.muavin_satirlari(yol))["eslesen"]), 1, karsi)
        yol = self.klasor / "karsiz.xlsx"                       # 600 gibi karsi olmayan hesaptaki esit tutar sayilmaz
        muavin_cok(yol, {"191 KDV": [("05/10/2026", "1", "AAA2026000000001", 200.0, None)],
                         "255 DEMIRBAS": [("05/10/2026", "1", "x", None, 1200.0)]})
        self.assertEqual(len(mk.karsilastir("alis", f, mk.muavin_satirlari(yol))["tutar_farki"]), 1)

    def test_isletme_dokumunde_toplam_okunamazsa_yalniz_numara_kontrol_edilir(self):
        satirlar = [{"hesap": "191", "tarih": date(2026, 10, 1), "fis": "1", "tip": "", "aciklama": "", "belge": "AAA2026000000001",
                     "borc": 0.0, "alacak": 0.0, "metin": "", "toplam": 0.0, "nolar": ["AAA2026000000001"]}]
        f = [{"no": "AAA2026000000001", "tarih": date(2026, 10, 1), "unvan": "A", "toplam": 1200.0, "kdv": 200.0, "tip": "x"},
             {"no": "AAA2026000000002", "tarih": date(2026, 10, 2), "unvan": "B", "toplam": 600.0, "kdv": 100.0, "tip": "x"}]
        k = mk.karsilastir("alis", f, satirlar)
        self.assertEqual(([x["no"][-1] for x in k["eslesen"]], [x["no"][-1] for x in k["tutar_okunamadi"]],
                          [x["no"][-1] for x in k["eksik"]], k["tutar_farki"]), (["1"], ["1"], ["2"], []))
        s = mk.firma_sonucu("X", "d", {"alis": f, "satis": []}, satirlar, kaynak="isletme")
        self.assertEqual(s["yon"]["alis"]["tutar_okunamadi"], 1)

    def test_satis_391_ve_alis_191_ayri_aranir(self):
        faturalar = [{"no": "BBB2026000000001", "tarih": date(2026, 10, 5), "unvan": "M", "toplam": 2400.0, "kdv": 400.0, "tip": "x"}]
        yol = self.klasor / "m391.xlsx"
        muavin_cok(yol, {"391 HESAPLANAN KDV": [("05/10/2026", "1", "BBB2026000000001", None, 400.0)],
                         "120 ALICILAR": [("05/10/2026", "1", "satis", 2400.0, None)]})
        satirlar = mk.muavin_satirlari(yol)
        self.assertEqual(satirlar[0]["hesap"], "391")
        self.assertEqual(len(mk.karsilastir("satis", faturalar, satirlar)["eslesen"]), 1)
        self.assertEqual(len(mk.karsilastir("alis", faturalar, satirlar)["eksik"]), 1)      # 391 satiri alis (191) icin sayilmaz

    def test_eksik_satiri_no_ve_tutari_gosterir(self):
        f = {"no": "AAA2026000000002", "tarih": "06/10/2026", "unvan": "B LTD", "toplam": 1234.5, "kdv": 205.75}
        satir = mk.eksik_satiri("alis", f)
        for parca in ("AAA2026000000002", "06/10/2026", "1.234,50", "205,75", "B LTD"):
            self.assertIn(parca, satir)
        self.assertEqual(mk.tl(None), "?")

    def test_gercek_luca_muavin_bicimi_tip_sutunu_tl_bolum_satiri_ve_tekrarlanan_baslik(self):
        """Gercek dokumun yapisi: 'HESAP ADI | TL' bolum satiri, TARIH/TIP/FIS NO/ACIKLAMA/BORC/ALACAK/BAKIYE/B/A basligi
        (her hesapta tekrarlanir), tarihler datetime, 'Nakli Yekun Haric' ve 'Genel Toplam' satirlari."""
        from datetime import datetime
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["MUAVİN DEFTER"])
        ws.append(["ÖRNEK ANONİM ŞİRKETİ"])
        ws.append(["Dönem :", "01/01/2026-31/12/2026"])
        ws.append(["100.01 KASA", None, None, None, "TL"])
        ws.append(["TARİH", "TİP", "FİŞ NO", "AÇIKLAMA", "BORÇ", "ALACAK", "BAKİYE", "B/A"])
        ws.append([datetime(2026, 1, 1), None, "00001", "", 557.35, None, 0.0, 0.0])
        ws.append(["Nakli Yekün Hariç :", None, None, None, 0.0, 0.0, 0.0, 0.0])
        ws.append([])
        ws.append(["191.01 İNDİRİLECEK KDV %20", None, None, None, "TL"])
        ws.append(["TARİH", "TİP", "FİŞ NO", "AÇIKLAMA", "BORÇ", "ALACAK", "BAKİYE", "B/A"])
        ws.append([datetime(2026, 3, 13), "Mahsup", "00294", "13/03/2026-OAF2026504000599-SATICI A.Ş.", 2.47, None, 0.0, 0.0])
        ws.append([datetime(2026, 3, 14), "Mahsup", "00364", "iade", None, 99.5, 0.0, 0.0])
        ws.append(["Genel Toplam :", None, None, None, 0.0, 0.0, 0.0, 0.0])
        ws.append(["391 HESAPLANAN KDV", None, None, None, "TL"])
        ws.append(["TARİH", "TİP", "FİŞ NO", "AÇIKLAMA", "BORÇ", "ALACAK", "BAKİYE", "B/A"])
        ws.append([datetime(2026, 1, 29), "Mahsup", "00094", "29/01/2026-M012026000000045-MÜŞTERİ", None, 283333.33, 0.0, 0.0])
        yol = self.klasor / "gercek.xlsx"
        wb.save(str(yol))
        s = mk.muavin_satirlari(yol)
        self.assertEqual([(x["hesap"], x["fis"]) for x in s], [("100", "00001"), ("191", "00294"), ("191", "00364"), ("391", "00094")])
        self.assertEqual(s[1]["nolar"], ["OAF2026504000599"])
        self.assertEqual((s[3]["alacak"], s[3]["nolar"]), (283333.33, ["M012026000000045"]))

    def test_isletme_defteri_gider_alis_gelir_satis_evrak_no(self):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append([None, "İŞLETME HESABI DEFTERİ"])
        ws.append([None, "İşyerinin Unvanı", None, ":", "ORNEK KISI"])
        ws.append([None, "GİDERLER"])
        ws.append([None, None, None, None, None, None, None, "Gider", "Alınan Emtia", "İndirilecek K.D.V.", None, "Toplam"])
        ws.append([None, "Kayıt No", "Evrak No", None, None, "Tarih", "Açıklama"])
        ws.append([None, "000001", "AAA2026000000001", None, None, "07/01/2026", "SATICI A", 0.0, 1000.0, 200.0, None, 1200.0])
        ws.append([None, "000002", "AAA2026000000002", None, None, "17/01/2026", "SATICI B", 0.0, 500.0, 100.0, None, 600.0])
        ws.append([None, "000003", "elden", None, None, "18/01/2026", "numarasiz", 0.0, 50.0, 0.0, None, 50.0])
        ws.append([None, "Toplam :", None, None, None, None, None, 0.0, 1550.0, 300.0, None, 1850.0])
        ws.append([None, "GELİRLER"])
        ws.append([None, None, None, None, None, None, None, "Gelir", "Satılan Emtia", "Hesaplanan K.D.V.", None, "Toplam"])
        ws.append([None, "Kayıt No", "Evrak No", None, None, "Tarih", "Açıklama"])
        ws.append([None, "000001", "BBB2026000000001", None, None, "07/01/2026", "MUSTERI", 0.0, 2000.0, 400.0, None, 2400.0])
        ws.append([None, "Toplam :", None, None, None, None, None, 0.0, 2000.0, 400.0, None, 2400.0])
        yol = self.klasor / "isletme.xlsx"
        wb.save(str(yol))
        s = mk.isletme_defteri_satirlari(yol)
        self.assertEqual([(x["hesap"], x["belge"], x["borc"], x["alacak"], x["toplam"]) for x in s],
                         [("191", "AAA2026000000001", 200.0, 0.0, 1200.0), ("191", "AAA2026000000002", 100.0, 0.0, 600.0),
                          ("191", "elden", 0.0, 0.0, 50.0), ("391", "BBB2026000000001", 0.0, 400.0, 2400.0)])
        faturalar = [{"no": "AAA2026000000001", "tarih": date(2026, 1, 7), "unvan": "A", "toplam": 1200.0, "kdv": 200.0, "tip": "x"},
                     {"no": "AAA2026000000009", "tarih": date(2026, 1, 9), "unvan": "Z", "toplam": 360.0, "kdv": 60.0, "tip": "x"},
                     {"no": "AAA2026000000002", "tarih": date(2026, 1, 17), "unvan": "B", "toplam": 700.0, "kdv": 100.0, "tip": "x"}]
        k = mk.karsilastir("alis", faturalar, s)
        self.assertEqual(([f["no"] for f in k["eslesen"]], [f["no"] for f in k["eksik"]], [f["no"] for f in k["tutar_farki"]]),
                         (["AAA2026000000001"], ["AAA2026000000009"], ["AAA2026000000002"]))    # defterde 600, fatura 700
        self.assertEqual(k["tutar_farki"][0]["kayit"], [600.0])
        self.assertEqual(len(mk.karsilastir("satis", [dict(faturalar[0], no="BBB2026000000001", toplam=2400.0, kdv=400.0)], s)["eslesen"]), 1)
        self.assertEqual(mk.firma_sonucu("X", "d", {"alis": faturalar, "satis": []}, s, kaynak="isletme")["kaynak"], "isletme")

    def test_faturalar_rapor_json_ve_csvden_okunur_mukerrer_ekran_tek_sayilir(self):
        firma = self._rapor([("AAA2026000000001", "05/10/2026", 1000.0, 200.0),
                             ("AAA2026000000002", "20/09/2026", 500.0, 100.0)],        # donem disi
                            [("BBB2026000000001", "10/10/2026", 2000.0, 400.0)], iptal=("AAA2026000000001",))
        f = mk.faturalari_oku(self.klasor, firma, *DONEM)
        self.assertEqual([x["no"] for x in f["alis"]], ["AAA2026000000001"])
        self.assertTrue(f["alis"][0]["iptal"])
        self.assertEqual((f["satis"][0]["kdv"], f["satis"][0]["toplam"]), (400.0, 2400.0))
        self.assertEqual(mk.faturalari_oku(self.klasor, "YOK", *DONEM), {"alis": [], "satis": []})

    def test_firma_sonucu_kaydet_ve_excel(self):
        firma = self._rapor([("AAA2026000000001", "05/10/2026", 1000.0, 200.0), ("AAA2026000000002", "06/10/2026", 500.0, 100.0),
                             ("AAA2026000000003", "07/10/2026", 1000.0, 200.0)],
                            [("BBB2026000000001", "10/10/2026", 2000.0, 400.0)])
        f = mk.faturalari_oku(self.klasor, firma, *DONEM)
        m = self.klasor / "tum.xlsx"
        muavin_cok(m, {"191 İNDİRİLECEK KDV": [("05/10/2026", "1", "AAA2026000000001", 200.0, None),
                                               ("07/10/2026", "3", "AAA2026000000003", 200.0, None)],
                       "320 SATICILAR": [("05/10/2026", "1", "x", None, 1200.0), ("07/10/2026", "3", "x", None, 900.0)],
                       "391 HESAPLANAN KDV": [("10/10/2026", "9", "BBB2026000000001", None, 400.0)],
                       "120 ALICILAR": [("10/10/2026", "9", "x", 2400.0, None)]})
        s = mk.firma_sonucu(firma, "01/10/2026-31/10/2026", f, mk.muavin_satirlari(m))
        self.assertEqual(s["durum"], "fark var")
        a, t = s["yon"]["alis"], s["yon"]["satis"]
        self.assertEqual((a["eslesen"], len(a["eksik"]), len(a["tutar_farki"]), t["eslesen"], len(t["eksik"]), len(t["tutar_farki"])),
                         (1, 1, 1, 1, 0, 0))
        self.assertEqual((a["eksik"][0]["no"], a["eksik"][0]["tarih"], a["eksik"][0]["toplam"], a["eksik"][0]["kdv"]),
                         ("AAA2026000000002", "06/10/2026", 600.0, 100.0))
        self.assertEqual((a["tutar_farki"][0]["no"], a["tutar_farki"][0]["toplam"], a["tutar_farki"][0]["kayit"], a["tutar_farki"][0]["fis"]),
                         ("AAA2026000000003", 1200.0, [900.0], "3"))
        hata = mk.firma_sonucu("HATALI", "01/10/2026-31/10/2026", {}, [], hata="Muavin menüsü açılamadı")
        self.assertEqual(hata["durum"], "hata")
        yol = self.klasor / "muavin.json"
        mk.kaydet(yol, "01/10/2026-31/10/2026", {firma: s, "HATALI": hata})
        mk.kaydet(yol, "01/10/2026-31/10/2026", {firma: dict(s, durum="tamam")})       # ayni firma/donem yenisiyle degisir
        veri = json.loads(yol.read_text(encoding="utf-8"))
        self.assertEqual([x["firma"] for x in veri["firmalar"]], [firma, "HATALI"])
        self.assertEqual(veri["firmalar"][0]["durum"], "tamam")
        xlsx = mk.excel_yaz(self.klasor / "muavin.xlsx", veri["donem"], [s, hata])
        from openpyxl import load_workbook
        wb = load_workbook(str(xlsx))
        self.assertEqual(wb.sheetnames, ["Özet", "Eksik (muavinde yok)", "Tutar uyuşmuyor"])
        eksik = list(wb["Eksik (muavinde yok)"].iter_rows(values_only=True))
        self.assertEqual(eksik[0][2:7], ("Tarih", "Fatura No", "Ünvan / İsim", "KDV", "KDV dahil tutar"))   # istenen sira
        self.assertEqual((eksik[1][1], eksik[1][2], eksik[1][3], eksik[1][5], eksik[1][6]),
                         ("Alış", "06/10/2026", "AAA2026000000002", 100.0, 600.0))
        fark = list(wb["Tutar uyuşmuyor"].iter_rows(values_only=True))
        self.assertEqual((fark[1][3], fark[1][6], fark[1][7], fark[1][8]), ("AAA2026000000003", 1200.0, "900.00", "3"))


def calistir(tmp, veri, ayar_degisiklik=None, ek=(), tarih="01/10/2026-31/10/2026", firma="ALFA ISLETME", onceden=None, ayar_ek=None):
    """Sahte Luca + muavin.py: (cikis kodu, sonuc sozlugu {firma: sonuc}, cikti, sahte sunucuya giden istekler)."""
    import sahte_kz
    sahte_kz.sifirla()
    sahte_kz.MUAVIN_VERI.update(veri)
    sahte_kz.MUAVIN_AYAR.update(ayar_degisiklik or {})
    if onceden:
        onceden()
    klasor = Path(tempfile.mkdtemp(prefix="muavin-uu-"))
    sunucu, adres = sahte_kz.baslat()
    ayar = {"giris_adresi": adres, "tarayici": "chromium", "tarayici_yolu": os.environ.get("LUCA_TEST_CHROMIUM", ""),
            "tarayici_sandbox": os.name == "nt", "profil_yerel": True, **(ayar_ek or {})}
    (klasor / "ayarlar.json").write_text(json.dumps(ayar), encoding="utf-8")
    ortam = dict(os.environ, LUCA_BOT_AYAR=str(klasor / "ayarlar.json"), LOCALAPPDATA=str(klasor / "yerel"),
                 KARZARAR_CIKTI=str(klasor / "cikti"), PYTHONIOENCODING="utf-8")
    komut = [sys.executable, str(KOK / "muavin.py"), "--tarih", tarih, "--fatura-klasoru", str(tmp), "--firma-tam", firma,
             "--tum-firmalar", "--bitince-kapat", *ek]
    r = subprocess.run(komut, env=ortam, cwd=str(KOK), capture_output=True, text=True, encoding="utf-8")
    sunucu.shutdown()
    try:
        sonuc = {f["firma"]: f for f in json.loads((klasor / "cikti" / "muavin.json").read_text(encoding="utf-8"))["firmalar"]}
    except OSError:
        sonuc = {}
    calistir.klasor = klasor
    return r.returncode, sonuc, r.stdout + r.stderr, list(sahte_kz.MUAVIN_AYAR["istekler"])


@unittest.skipUnless(os.environ.get("LUCA_TEST_CHROMIUM"), "LUCA_TEST_CHROMIUM yok: uctan uca atlandi")
class UctanUca(unittest.TestCase):
    def setUp(self):
        self.klasor = Path(tempfile.mkdtemp(prefix="muavin-fatura-"))
        alis = [("AAA2026000000001", "05/10/2026", 1000.0, 200.0), ("AAA2026000000002", "06/10/2026", 500.0, 100.0),
                ("AAA2026000000003", "07/10/2026", 1000.0, 200.0), ("AAA2026000000004", "08/10/2026", 1000.0, 200.0)]
        satis = [("BBB2026000000001", "10/10/2026", 2000.0, 400.0)]
        firma = "ALFA ISLETME"
        klasorler = {"e-fatura-alis": fatura_klasoru(self.klasor, firma, "e-fatura-alis", alis),
                     "e-arsiv-satis": fatura_klasoru(self.klasor, firma, "e-arsiv-satis", satis)}
        (self.klasor / "rapor.json").write_text(json.dumps({firma: {"klasorler": klasorler}}), encoding="utf-8")
        # muavin TUM hesaplarla gelir: 1 tamam, 2 yok, 3 iki fiste tamam, 4 numarasi var ama 320 satiri 900 (tutar uymuyor)
        self.veri = {(firma, "191"): [("05/10/2026", "1", "AAA2026000000001 alis", 200.0, None),
                                      ("07/10/2026", "2", "AAA2026000000003", 200.0, None),
                                      ("07/10/2026", "3", "AAA2026000000003 ikinci kez", 200.0, None),
                                      ("08/10/2026", "4", "AAA2026000000004", 200.0, None)],
                     (firma, "320"): [("05/10/2026", "1", "alis", None, 1200.0), ("07/10/2026", "2", "alis", None, 1200.0),
                                      ("07/10/2026", "3", "alis", None, 1200.0), ("08/10/2026", "4", "alis", None, 900.0)],
                     (firma, "391"): [("10/10/2026", "9", "BBB2026000000001 satis", None, 400.0)],
                     (firma, "120"): [("10/10/2026", "9", "satis", 2400.0, None)]}

    def _dogrula(self, sonuc, cikti):
        s = sonuc["ALFA ISLETME"]
        self.assertEqual(s["durum"], "fark var", cikti[-2500:])
        a, t = s["yon"]["alis"], s["yon"]["satis"]
        self.assertEqual([(f["no"], f["toplam"], f["kdv"]) for f in a["eksik"]], [("AAA2026000000002", 600.0, 100.0)])
        self.assertEqual([(f["no"], f["toplam"], f["kayit"]) for f in a["tutar_farki"]], [("AAA2026000000004", 1200.0, [900.0])])
        self.assertEqual((a["eslesen"], t["eslesen"], len(t["eksik"]), len(t["tutar_farki"])), (2, 1, 0, 0))
        self.assertIn("EKSİK  Alış  06/10/2026  AAA2026000000002", cikti)        # tarih - fatura no - unvan - KDV - tutar
        self.assertIn("KDV 100,00 TL  KDV dahil 600,00 TL", cikti)
        self.assertIn("TUTAR  Alış  08/10/2026  AAA2026000000004", cikti)
        self.assertIn("(kayıtta: 900,00; fiş 4)", cikti)

    def test_tum_hesaplarla_tek_dokum_fatura_no_ve_genel_toplam(self):
        kod, sonuc, cikti, istekler = calistir(self.klasor, self.veri)
        self.assertEqual(kod, 0, cikti[-2500:])
        self._dogrula(sonuc, cikti)
        self.assertEqual(len(istekler), 1, istekler)                                  # tek dokum
        self.assertEqual((istekler[0]["h1"], istekler[0]["h2"], istekler[0]["bas"]), ("", "", "01/10/2026"))   # hesap araligi bos: tum hesaplar
        self.assertTrue((calistir.klasor / "cikti" / "muavin.xlsx").exists())

    def test_nokta_vurusulu_muavin_formu_atlanir_tum_yazicilar_secilir(self):
        """Menude 'Muavin Defter' iki kez: ilki Nokta Vurusulu (Rapor Turu IBM/EPSON, Excel yok); Excel'li olan kullanilir."""
        kod, sonuc, cikti, istekler = calistir(self.klasor, self.veri)
        self.assertEqual(kod, 0, cikti[-2500:])
        self.assertIn("Bu Muavin Defter formunda Excel yok (Nokta Vuruşlu Yazıcılar olabilir)", cikti)
        self.assertIn("Muavin Defter açıldı (Excel seçenekli form", cikti)
        self._dogrula(sonuc, cikti)
        self.assertEqual(len(istekler), 1)

    def test_rapor_turu_excel_liste_xlsx_adiyla_da_secilir(self):
        kod, sonuc, cikti, istekler = calistir(self.klasor, self.veri, {"excel_adi": "Excel Liste (xlsx)"})
        self.assertEqual(kod, 0, cikti[-2500:])
        self._dogrula(sonuc, cikti)

    def test_ikinci_sinif_isletme_defteri_dokumunden_bakilir(self):
        import sahte_kz
        kod, sonuc, cikti, _ = calistir(self.klasor, {}, ek=["--sinif", "2"], onceden=lambda: sahte_kz.ISLETME_VERI.update({
            "ALFA ISLETME": {"gider": [("000001", "AAA2026000000001", "05/10/2026", "SATICI A", 200.0, 1200.0),
                                       ("000002", "AAA2026000000003", "07/10/2026", "SATICI C", 200.0, 1100.0),
                                       ("000003", "AAA2026000000004", "08/10/2026", "SATICI D", 200.0, 1200.0)],
                             "gelir": [("000001", "BBB2026000000001", "10/10/2026", "MUSTERI", 400.0, 2400.0)]}}))
        self.assertEqual(kod, 0, cikti[-2500:])
        s = sonuc["ALFA ISLETME"]
        self.assertEqual((s["durum"], s["kaynak"]), ("fark var", "isletme"), cikti[-2500:])
        self.assertEqual([f["no"] for f in s["yon"]["alis"]["eksik"]], ["AAA2026000000002"])
        self.assertEqual([(f["no"], f["kayit"]) for f in s["yon"]["alis"]["tutar_farki"]], [("AAA2026000000003", [1100.0])])
        self.assertEqual((s["yon"]["alis"]["eslesen"], s["yon"]["satis"]["eslesen"]), (2, 1))
        self.assertIn("(Luca işletme defteri dökümü: gider/gelir)", cikti)
        self.assertIn("EKSİK  Alış  06/10/2026  AAA2026000000002", cikti)
        self.assertIn("TUTAR  Alış  07/10/2026  AAA2026000000003", cikti)
        self.assertIn("İşletme defteri formu: Tarih İlk=01/10/2026, Tarih Son=31/10/2026", cikti)

    def test_iki_luca_hesabi_ofis_ve_isletme_sirayla_acilir_firma_bir_kez_islenir(self):
        ikinci = {"ikinci_hesap": {"etkin": True, "ad": "isletme", "uye_no": "222", "kullanici_adi": "isletme-kullanici",
                                   "parola": "x"}}
        kod, sonuc, cikti, _ = calistir(self.klasor, self.veri, ayar_ek=ikinci)
        self.assertEqual(kod, 0, cikti[-2500:])
        self.assertIn("LUCA HESABI 1/2", cikti)
        self.assertIn("LUCA HESABI 2/2", cikti)
        self.assertEqual(cikti.count("[1/1] ALFA ISLETME"), 1, cikti[-2500:])      # iki hesapta da gorunur: ilkinde islenir
        self.assertEqual(sonuc["ALFA ISLETME"]["durum"], "fark var")
        self.assertTrue(sonuc["ALFA ISLETME"]["hesap"])                            # hesabin sahibinin adi

    def test_hesap_isletme_ikinci_hesap_yoksa_hata(self):
        kod, sonuc, cikti, _ = calistir(self.klasor, self.veri, ek=["--hesap", "isletme"])
        self.assertNotEqual(kod, 0)
        self.assertIn("ikinci Luca hesabı kapalı", cikti)

    def test_sinif_otomatik_muavin_ekrani_aciliyorsa_1_sinif_sayilir(self):
        kod, sonuc, cikti, _ = calistir(self.klasor, self.veri, ek=["--sinif", "otomatik"])
        self.assertEqual(kod, 0, cikti[-2500:])
        self.assertIn("(sınıf otomatik", cikti)
        self.assertIn("Sınıf belirlendi: 1. sınıf (muavin)", cikti)
        self.assertEqual(sonuc["ALFA ISLETME"]["kaynak"], "muavin")

    def test_menu_baglantilari_html_varlikli_adlar_ve_cerceveler_arasi_eski_isareti(self):
        """Menu verisinde adlar HTML varligi olabilir; ayni adli tum girisler bulunur. Icerik baska cercevedeyse eski form ayirt edilir."""
        from playwright.sync_api import sync_playwright
        from karzarar import luca_muavin
        html = """<script>
          var menuItems = [["||||Serbest Meslek D&ouml;k&uuml;m&uuml;", "raporSerbest.do?x=1"], ["||||Muavin Defter", "raporMuavinKarakter.do"],
                           ["|||||Muavin Defter", "raporMuavinDefterHazirla.do"], ["x", ""]];
          function aktar(l) { document.getElementById('ic').srcdoc = '<table><tr><th>Başlangıç Fiş Tarihi</th><td><input></td></tr>'
            + '<tr><th>Rapor Türü</th><td><select>' + (l.indexOf('Karakter') >= 0 ? '<option>IBM Tabanlı Yazıcı</option>'
            : '<option>PDF</option><option>Excel Liste (xlsx)</option>') + '</select></td></tr></table>'; }
        </script><iframe id="ic"></iframe>"""
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=os.environ["LUCA_TEST_CHROMIUM"], args=["--no-sandbox"])
            sayfa = b.new_page()
            sayfa.set_content(html)
            self.assertEqual([l for _, l in luca_muavin.menu_baglantilari(sayfa, "Serbest Meslek Dökümü")], ["raporSerbest.do?x=1"])
            baglantilar = [l for _, l in luca_muavin.menu_baglantilari(sayfa, "Muavin Defter")]
            self.assertEqual(baglantilar, ["raporMuavinKarakter.do", "raporMuavinDefterHazirla.do"])
            sonuclar = []
            for l in baglantilar:
                self.assertTrue(luca_muavin._baglantiyi_ac(sayfa, l))
                for _ in range(40):                      # yeni form yuklenene kadar (eski isaret kaybolur)
                    r = luca_muavin._yeni_form(sayfa)
                    if r:
                        break
                    sayfa.wait_for_timeout(100)
                sonuclar.append(r[0])
            b.close()
        self.assertEqual(sonuclar, [False, True])       # Nokta Vurusulu: Excel yok; ikinci: var

    def test_faturasi_olmayan_firma_atlanir_ve_rapor_yoksa_hata(self):
        kod, sonuc, cikti, istekler = calistir(self.klasor, self.veri, ek=["--tum-firmalar"], firma="ALFA ISLETME")
        self.assertEqual(kod, 0, cikti[-1500:])
        kod2, _, cikti2, _ = calistir(Path(tempfile.mkdtemp()), self.veri)               # rapor.json yok
        self.assertNotEqual(kod2, 0)
        self.assertIn("Fatura raporu bulunamadı", cikti2)


if __name__ == "__main__":
    unittest.main()
