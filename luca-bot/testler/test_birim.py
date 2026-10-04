# -*- coding: utf-8 -*-
"""Tarayici gerektirmeyen birim testleri.

    python -m unittest discover -s testler -v
"""

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lucabot import eposta, rapor  # noqa: E402
from lucabot.calisma import ozetle  # noqa: E402
from lucabot.fatura_analiz import (excelden_sonuca_isle, excelden_tablo,  # noqa: E402
                                   fatura_kimligi, tevkifatli_satirlar,
                                   tutar_cozumle, zipten_tevkifatlilar)
from lucabot.firma_listesi import (bugun_tamamlananlar, firma_listesini_oku,  # noqa: E402
                                   firmalari_suz, listede_bul)
from lucabot.ortak import (ekran_tamamlanmis_mi, hedef_ay_araligi,  # noqa: E402
                           sure_yaz, tarih_araliklari, tarih_cozumle, yeni_sonuc)


def _xlsx(yol, satirlar):
    from openpyxl import Workbook
    wb = Workbook()
    for s in satirlar:
        wb.active.append(s)
    wb.save(yol)
    return yol


class TarihTestleri(unittest.TestCase):
    def test_yedi_gunluk_parcalar(self):
        araliklar = tarih_araliklari(date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(araliklar[0], ("01/08/2026", "08/08/2026"))
        self.assertEqual(araliklar[-1][1], "31/08/2026")
        # her parca bir oncekinin bitisinden baslar
        for (_, bit), (bas, _) in zip(araliklar, araliklar[1:]):
            self.assertEqual(bit, bas)

    def test_tek_gun(self):
        self.assertEqual(tarih_araliklari(date(2026, 8, 1), date(2026, 8, 1)),
                         [("01/08/2026", "01/08/2026")])

    def test_ters_aralik_hata(self):
        with self.assertRaises(ValueError):
            tarih_araliklari(date(2026, 8, 2), date(2026, 8, 1))

    def test_hedef_ay_tamami(self):
        # kisa sorgu araliginda da listeleme ayin tamami olmali
        self.assertEqual(hedef_ay_araligi(date(2026, 8, 1), date(2026, 8, 2)),
                         (date(2026, 8, 1), date(2026, 8, 31)))
        self.assertEqual(hedef_ay_araligi(date(2028, 2, 1), date(2028, 3, 15))[1], date(2028, 2, 29))

    def test_tarih_cozumle(self):
        self.assertEqual(tarih_cozumle(" 05/08/2026 "), date(2026, 8, 5))

    def test_sure_yaz(self):
        self.assertEqual(sure_yaz(75), "1 dk 15 sn")
        self.assertEqual(sure_yaz(4000), "1 sa 6 dk")


class TutarVeFaturaTestleri(unittest.TestCase):
    def test_tutar(self):
        self.assertEqual(tutar_cozumle("1.234,56"), 1234.56)
        self.assertEqual(tutar_cozumle("1234,5 TL"), 1234.5)
        self.assertEqual(tutar_cozumle(1234.5), 1234.5)
        self.assertEqual(tutar_cozumle(""), 0.0)
        self.assertEqual(tutar_cozumle("-"), 0.0)

    def test_fatura_kimligi(self):
        satir = ["05/08/2026", "TURKCELL ILETISIM A.S.", "TCL2026000000123", "1.200,00"]
        self.assertEqual(fatura_kimligi(satir), ("TURKCELL", "TCL2026000000123"))
        self.assertIsNone(fatura_kimligi(["05/08/2026", "numarasiz satir", "12"]))

    def test_tevkifat_sadece_alis(self):
        satirlar = [["X", "TEVKİFATLI"], ["Y", "SATIS"]]
        self.assertEqual(len(tevkifatli_satirlar(satirlar, "e-arsiv-alis")), 1)
        self.assertEqual(tevkifatli_satirlar(satirlar, "e-arsiv-satis"), [])

    def test_zipten_tevkifat(self):
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "b.zip"
            with zipfile.ZipFile(yol, "w") as z:
                z.writestr("ABC2026000000001.xml", "<x><WithholdingTaxTotal/></x>")
                z.writestr("ABC2026000000002.xml", "<x/>")
            self.assertEqual(zipten_tevkifatlilar(yol), {"ABC2026000000001"})
            self.assertEqual(zipten_tevkifatlilar(Path(d) / "yok.zip"), set())

    def test_excelden_sonuca_isle(self):
        with tempfile.TemporaryDirectory() as d:
            klasor = Path(d)
            yol = _xlsx(klasor / "liste.xlsx", [
                ["Fatura No", "Unvan", "Tarih", "Tip", "Matrah", "KDV Tutarı", "KDV Oranı",
                 "Genel Toplam", "Durum"],
                ["AAA2026000000001", "TURKCELL", "05/08/2026", "SATIS", 1000, 200, 20, 1200, "ONAY"],
                ["AAA2026000000002", "VODAFONE", "06/08/2026", "SATIS", 500, 100, 20, 600, "İPTAL"],
                ["AAA2026000000003", "TRUGO", "07/08/2026", "TEVKIFAT", 2000, 400, 20, 2400, "ONAY"],
            ])
            sonuc = yeni_sonuc("F", "e-arsiv-alis")
            satirlar = excelden_sonuca_isle(sonuc, yol, klasor, None)
            self.assertEqual(len(satirlar), 3)
            self.assertEqual(sonuc["fatura_sayisi"], 3)
            self.assertEqual(sonuc["tevkifat"], 1)
            self.assertEqual(sonuc["iptal_itiraz"], 1)
            # iptal edilen fatura toplama girmez; KDV oran sutunu toplanmaz
            self.assertEqual(sonuc["matrah"], 3000)
            self.assertEqual(sonuc["kdv"], 600)
            self.assertEqual(sonuc["faturalar"][0], ["TURKCELL", "AAA2026000000001", 1200.0])
            self.assertTrue((klasor / "iptal-itiraz.csv").exists())

    def test_ekranda_iptal_gorunen_fatura_excelde_durum_yoksa_da_toplama_girmez(self):
        """Iptal/itiraz sorgusu durumu ekrandaki listeye yaziyor; Excel'de durum
        sutunu olmayabilir. O fatura yine de matrah/KDV toplamindan dusulmeli."""
        with tempfile.TemporaryDirectory() as d:
            klasor = Path(d)
            yol = _xlsx(klasor / "liste.xlsx", [
                ["Fatura No", "Unvan", "Tarih", "Matrah", "KDV Tutarı"],
                ["AAA2026000000001", "TURKCELL", "05/08/2026", 1000, 200],
                ["AAA2026000000002", "VODAFONE", "06/08/2026", 500, 100],
            ])
            sonuc = yeni_sonuc("F", "e-arsiv-alis")
            sonuc["iptal_itiraz"] = 1  # ekrandan sayilmisti
            excelden_sonuca_isle(sonuc, yol, klasor, None, iptal_nolari={"AAA2026000000002"})
            self.assertEqual(sonuc["matrah"], 1000)
            self.assertEqual(sonuc["kdv"], 200)
            self.assertEqual(sonuc["iptal_itiraz"], 1)

    def test_fatura_tutari(self):
        from lucabot.fatura_analiz import satir_toplam_tutari
        # Luca'nin Excel'inde genel toplam sutunu yoksa matrah + KDV
        basliklar = ["Fatura No", "Mal Hizmet Toplam Tutarı", "Hesaplanan KDV", "KDV Oranı"]
        self.assertEqual(satir_toplam_tutari(basliklar, ["X", "1.000,00", "200,00", "20"]), 1200.0)
        # genel toplam sutunu varsa o kullanilir
        basliklar = ["Fatura No", "Matrah", "KDV", "Ödenecek Tutar"]
        self.assertEqual(satir_toplam_tutari(basliklar, ["X", "1000", "200", "1150,5"]), 1150.5)

    def test_gib_hata_mesaji_taninir(self):
        from lucabot.gib_sorgu import gib_hatasi, hata_satiri, yetki_hatasi
        metin = ("İşlem Takip\nGİB e-Arşiv Sistemi Hata Mesajı:Doğrulama hatası Internet vergi"
                 " dairesinden kimlik doğrulanamadı.")
        self.assertTrue(gib_hatasi(metin))
        self.assertFalse(yetki_hatasi(metin))
        self.assertIn("kimlik", hata_satiri(metin))
        self.assertFalse(gib_hatasi("01/08 sorgulandı. 2 belge kaydı bulundu. İşlem sona erdi."))

    def test_bozuk_excel_cokertmez(self):
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "bozuk.xlsx"
            yol.write_bytes(b"bu bir excel degil")
            self.assertEqual(excelden_tablo(yol), ([], []))


class FirmaListesiTestleri(unittest.TestCase):
    def test_sadece_adi_olan_satirlar_okunur(self):
        with tempfile.TemporaryDirectory() as d:
            yol = _xlsx(Path(d) / "firmalar.xlsx", [
                ["FIRMA LISTESI"],  # tek hucrelik baslik baslik sayilmaz
                ["Kısa Adı", "Kapanış Tarihi", "e-Fatura Alış", "e-Arşiv Alış"],
                ["AKIN COBAN"],
                ["DENTAL", "", "X", ""],
                ["KAPALI", "01/03/2026", "", ""],
            ])
            liste = firma_listesini_oku(yol)
            self.assertEqual(set(liste), {"AKIN COBAN", "DENTAL", "KAPALI"})
            self.assertEqual(liste["DENTAL"][1], {"e-fatura-alis"})
            self.assertEqual(liste["KAPALI"][0], date(2026, 3, 1))

    def test_listede_bul_en_uzun_eslesme(self):
        liste = {"ADEM": 1, "ADEM MERGE": 2}
        self.assertEqual(listede_bul("ADEM MERGE", liste), "ADEM MERGE")
        self.assertEqual(listede_bul("ADEM", liste), "ADEM")

    def test_firmalari_suz(self):
        with tempfile.TemporaryDirectory() as d:
            yol = _xlsx(Path(d) / "firmalar.xlsx", [
                ["Kısa Adı", "Kapanış Tarihi", "İnteraktif V.D."],
                ["AKIN COBAN", "", "X"], ["DENTAL", "", ""], ["KAPALI", "01/03/2026", ""],
            ])
            ayarlar = {"firma_listesi": str(yol), "atlanacak_firmalar": ["DENT"]}
            secim = firmalari_suz(["AKIN COBAN", "DENTAL", "KAPALI", "LISTEDE YOK"], ayarlar,
                                  baslangic=date(2026, 8, 1))
            self.assertEqual(secim.firmalar, ["AKIN COBAN"])
            self.assertEqual(secim.atlanan_ekranlar, {"AKIN COBAN": {"e-arsiv-interaktif"}})
            bos = firmalari_suz(["AKIN COBAN"], {}, aranan=["zzz"])
            self.assertEqual(bos.firmalar, [])
            self.assertTrue(bos.bos_sebep)

    def test_bugun_tamamlananlar(self):
        bugun = date.today().strftime("%d/%m/%Y") + " 10:00"
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "rapor.json").write_text(json.dumps({
                "A": {"durumlar": {"e-arsiv-alis": "tamam", "gib-5000": "hata: X"},
                     "guncellenme": {"e-arsiv-alis": bugun, "gib-5000": bugun}},
                "B": {"durumlar": {"e-arsiv-alis": "bekliyor"}, "guncellenme": {"e-arsiv-alis": bugun}},
            }), encoding="utf-8")
            self.assertEqual(bugun_tamamlananlar(d, ["e-arsiv-alis", "gib-5000"]),
                             {"A": {"e-arsiv-alis"}})
            self.assertTrue(ekran_tamamlanmis_mi("fatura yok"))
            self.assertFalse(ekran_tamamlanmis_mi("kaynaktan inmedi"))

    def test_bugun_tamamlananlar_surekli_raporda_gecmis_gunler_sayilmaz(self):
        """Rapor artik gunluk degil surekli; gecen ayin 'tamam'i bugun sayilmamali."""
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "rapor.json").write_text(json.dumps({
                "A": {"durumlar": {"e-arsiv-alis": "tamam"},
                     "guncellenme": {"e-arsiv-alis": "01/01/2026 10:00"}},
                # eski (guncelleme alani hic olmayan) kayitlar da bugun sayilmamali
                "B": {"durumlar": {"e-arsiv-alis": "tamam"}},
            }), encoding="utf-8")
            self.assertEqual(bugun_tamamlananlar(d, ["e-arsiv-alis"]), {})


class EtkinFirmaTestleri(unittest.TestCase):
    def test_tum_ekrani_x_ya_da_tamam_olan_firma_elenir(self):
        from lucabot.calisma import etkin_firmalar
        tipler = ["e-arsiv-alis", "e-fatura-alis", "gib-5000"]
        atlanan = {"A": {"e-arsiv-alis", "e-fatura-alis", "gib-5000"},   # hepsi X
                   "B": {"e-fatura-alis"},                                # bir kismi X
                   "C": {"gib-5000"}}
        tamam = {"C": {"e-arsiv-alis", "e-fatura-alis"}}                  # kalan X, geri kalani bugun bitmis
        self.assertEqual(etkin_firmalar(["A", "B", "C", "D"], tipler, atlanan, tamam), ["B", "D"])
        self.assertEqual(etkin_firmalar([], tipler, {}, {}), [])


class RaporTestleri(unittest.TestCase):
    def _sonuc(self, firma, tip, **alanlar):
        s = yeni_sonuc(firma, tip)
        s.update(alanlar)
        return s

    def test_ortusen_ekranlar_cifte_sayilmaz(self):
        sonuclar = [
            self._sonuc("A", "e-arsiv-alis", durum="tamam", fatura_sayisi=3, tevkifat=1),
            self._sonuc("A", "e-arsiv-interaktif", durum="tamam", fatura_sayisi=4, tevkifat=1),
            self._sonuc("A", "e-fatura-alis", durum="fatura yok"),
            self._sonuc("A", "gib-5000", durum="hata: LookupError", **{"not": "menu yok"}),
        ]
        oz = ozetle(sonuclar)
        self.assertEqual((oz.firma, oz.ekran, oz.basarili, oz.bos, oz.sorunlu), (1, 4, 2, 1, 1))
        self.assertEqual(oz.fatura, 4)     # e-arsiv-alis ile interaktif ayni faturalar
        self.assertEqual(oz.tevkifat, 1)
        self.assertIn("menu yok", oz.sorunlu_liste[0])

    def test_turmob_satis_e_arsiv_ve_e_fatura_satisin_toplamidir(self):
        """TURMOB Satis = e-Arsiv Satis + e-Fatura Satis; GIB 5000 = e-Arsiv Satis.

        TURMOB ekrani acilmayan firmada satis, iki parcanin toplami olmali (en
        buyugu degil); TURMOB indiyse parcalar onun ustune eklenmemeli.
        """
        satis = rapor.SATIS_EKRANLARI
        turmobsuz = {"kdv": {"e-arsiv-satis": 100, "gib-5000": 100, "e-fatura-satis": 260}}
        self.assertEqual(rapor._grup_toplami(turmobsuz, "kdv", satis), 360)
        turmoblu = {"kdv": {"e-arsiv-satis": 100, "gib-5000": 100, "e-fatura-satis": 260,
                            "turmob-satis": 360, "esmm-satis": 40}}
        self.assertEqual(rapor._grup_toplami(turmoblu, "kdv", satis), 400)
        # parcalardan biri inmediyse TURMOB'un kendisi kullanilir
        eksik = {"kdv": {"e-arsiv-satis": 100, "turmob-satis": 360}}
        self.assertEqual(rapor._grup_toplami(eksik, "kdv", satis), 360)

    def test_alis_toplami_ortusen_ekranlari_bir_kez_sayar(self):
        kayit = {"kdv": {"turmob-alis": 2200, "e-fatura-alis": 2200, "e-arsiv-alis": 300,
                         "e-arsiv-interaktif": 300, "esmm-alis": 100, "e-fatura-satis": 999}}
        self.assertEqual(rapor._grup_toplami(kayit, "kdv", rapor.ALIS_EKRANLARI), 2600)

    def test_ozet_fatura_adedi_turmob_acilmayan_firmada_eksik_kalmaz(self):
        sonuclar = [
            self._sonuc("A", "e-arsiv-satis", durum="tamam", fatura_sayisi=5),
            self._sonuc("A", "gib-5000", durum="tamam", fatura_sayisi=5),
            self._sonuc("A", "e-fatura-satis", durum="tamam", fatura_sayisi=13),
            self._sonuc("A", "turmob-satis", durum="ekran acilmadi"),
            self._sonuc("A", "turmob-alis", durum="tamam", fatura_sayisi=22),
            self._sonuc("A", "e-fatura-alis", durum="tamam", fatura_sayisi=22),
        ]
        self.assertEqual(ozetle(sonuclar).fatura, 18 + 22)

    def test_rapor_dosyalari_ve_mutabakat(self):
        from openpyxl import load_workbook
        with tempfile.TemporaryDirectory() as d:
            klasor = Path(d)
            (klasor / "rapor.json").write_text(json.dumps({  # eski bicimde kayit
                "ESKI": {"firma": "ESKI", "donem": "", "durumlar": {"e-arsiv-alis": "tamam"},
                         "sayilar": {"e-arsiv-alis": 1}, "iptal": {}, "tevkifat": {}, "inmeyen": {},
                         "faturalar": {"e-arsiv-alis": [["X", "AAA2026000000009"]]},
                         "dosya": 2, "not": "", "son": ""}}), encoding="utf-8")
            sonuclar = [
                self._sonuc("A", "e-arsiv-alis", durum="tamam", fatura_sayisi=1,
                            faturalar=[["TURKCELL", "AAA2026000000001", 1200.0]], matrah=1000, kdv=200),
                self._sonuc("A", "e-arsiv-interaktif", durum="tamam", fatura_sayisi=2,
                            faturalar=[["TURKCELL", "AAA2026000000001", 1200.0],
                                       ["SHELL", "AAA2026000000004", 360.0]]),
                self._sonuc("B", "gib-5000", durum="hata: LookupError", **{"not": "menu yok"}),
            ]
            rapor.guncelle(klasor, sonuclar, ["C"], "e-arsiv-alis")
            wb = load_workbook(klasor / "rapor.xlsx")
            self.assertEqual(wb.sheetnames, ["Özet", "Firma Durumu", "İndirilen Faturalar",
                                             "Dosyalar", "Hatalar ve Uyarılar"])
            mutabakat = {(r[0].value, r[1].value, r[4].value): r[6].value
                         for r in wb["İndirilen Faturalar"].iter_rows(min_row=2)}
            self.assertEqual(mutabakat[("A", "İnteraktif V.D.", "AAA2026000000004")],
                             "e-Arşiv'de YOK (İnteraktif'te var)")
            self.assertEqual(mutabakat[("A", "e-Arşiv Alış", "AAA2026000000001")], "iki ekranda da var")
            hatalar = [(r[0].value, r[2].value) for r in wb["Hatalar ve Uyarılar"].iter_rows(min_row=2)]
            self.assertIn(("B", "hata: LookupError"), hatalar)
            self.assertIn(("C", "bekliyor"), hatalar)
            # Firma Durumu'ndaki tutarlar sayi olarak yazilir (Excel'de toplanabilsin)
            basliklar = [c.value for c in wb["Firma Durumu"][1]]
            j = basliklar.index("Alış Matrah")
            degerler = {r[0].value: r[j].value for r in wb["Firma Durumu"].iter_rows(min_row=2)}
            self.assertEqual(degerler["A"], 1000)
            self.assertTrue((klasor / "rapor.csv").exists())
            self.assertFalse((klasor / "rapor.json.tmp").exists())

    def test_guncellenme_bugunku_tarihi_tasir(self):
        """rapor.guncelle() her ekran icin 'bugun islendi mi' kontrolune yarayan tarihi yazar."""
        bugun = date.today().strftime("%d/%m/%Y")
        with tempfile.TemporaryDirectory() as d:
            klasor = Path(d)
            rapor.guncelle(klasor, [self._sonuc("A", "e-arsiv-alis", durum="tamam")], [], "e-arsiv-alis")
            kayitlar = json.loads((klasor / "rapor.json").read_text(encoding="utf-8"))
            self.assertTrue(kayitlar["A"]["guncellenme"]["e-arsiv-alis"].startswith(bugun))

    def test_gib5000_tevkifati_alisa_sayilmaz(self):
        """GIB 5000/30000 satis ekranidir; oradaki 'tevkifat' ibaresi KDV2'yi ilgilendirmez,
        Tevkifatli Alis sayisina/aksiyonuna karismamali (bkz. TEVKIFAT_EKRANLARI)."""
        with tempfile.TemporaryDirectory() as d:
            klasor = Path(d)
            rapor.guncelle(klasor, [self._sonuc("A", "gib-5000", durum="tamam",
                                                 fatura_sayisi=5, tevkifat=5)], [], "gib-5000")
            kayitlar = json.loads((klasor / "rapor.json").read_text(encoding="utf-8"))
            self.assertEqual(kayitlar["A"]["tevkifat"]["gib-5000"], 0)
            isler = rapor._aksiyon(kayitlar["A"])
            self.assertFalse(any("TEVKIFAT" in i for i in isler))

    def test_eposta_metni(self):
        sonuclar = [self._sonuc("A", "e-arsiv-alis", durum="tamam", fatura_sayisi=3, tevkifat=2),
                    self._sonuc("B", "esmm-alis", durum="tamam", fatura_sayisi=1)]
        metin, uyari = eposta.ozet_metni(sonuclar, "01/08/2026-31/08/2026")
        self.assertTrue(uyari)
        self.assertIn("TEVKIFATLI ALIS", metin)
        self.assertIn("e-SMM ALIS", metin)
        self.assertNotIn("*", metin)


class ArayuzOzetTestleri(unittest.TestCase):
    """Arayuzun alt kutulari: tevkifat KDV, SMM, interaktif farki, KDV odemesi."""

    def test_tevkifat_tutari_sutundan_yoksa_kdvden(self):
        from lucabot.fatura_analiz import matrah_kdv_sutunlari, tevkifat_kdv_tutari
        basliklar = ["Fatura No", "Matrah", "KDV Tutarı", "KDV Tevkifat Tutarı", "Tevkifat Oranı"]
        satirlar = [["AAA2026000000001", "1000", "200", "100", "5/10"]]
        self.assertEqual(tevkifat_kdv_tutari(basliklar, satirlar), (100.0, False))
        # tevkifat sutunu KDV toplamina ikinci kez girmez
        self.assertEqual(matrah_kdv_sutunlari(basliklar)[1], [2])
        self.assertEqual(tevkifat_kdv_tutari(["Fatura No", "Matrah", "KDV Tutarı"],
                                             [["AAA2026000000001", "1000", "200"]]), (200.0, True))
        self.assertEqual(tevkifat_kdv_tutari(basliklar, []), (0, False))

    def test_excelde_iptal_edilen_tevkifatli_fatura_tutara_girmez(self):
        with tempfile.TemporaryDirectory() as d:
            klasor = Path(d)
            yol = _xlsx(klasor / "liste.xlsx", [
                ["Fatura No", "Unvan", "Tip", "Matrah", "KDV Tutarı", "Tevkifat Tutarı", "Durum"],
                ["AAA2026000000001", "TRUGO", "TEVKIFAT", 2000, 400, 200, "ONAY"],
                ["AAA2026000000002", "SHELL", "TEVKIFAT", 1000, 200, 100, "IPTAL"],
            ])
            sonuc = yeni_sonuc("F", "e-fatura-alis")
            excelden_sonuca_isle(sonuc, yol, klasor, None)
            self.assertEqual(sonuc["tevkifat"], 2)       # uyari icin iptal de sayilir
            self.assertEqual(sonuc["tevkifat_kdv"], 200)  # tutara girmez
            self.assertFalse(sonuc["tevkifat_kdv_tahmini"])

    def test_tevkifat_adedi_e_arsiv_ve_e_fatura_alisi_toplar(self):
        """e-Arsiv Alis ile e-Fatura Alis'taki tevkifatli faturalar farkli faturalar."""
        kayit = {"tevkifat": {"e-arsiv-alis": 1, "e-arsiv-interaktif": 1, "e-fatura-alis": 4,
                              "turmob-alis": 4}}
        self.assertEqual(rapor.tevkifat_adedi(kayit), 5)

    def test_devreden_kdv_sutunu_okunur(self):
        from lucabot.firma_listesi import devreden_kdvleri
        with tempfile.TemporaryDirectory() as d:
            yol = _xlsx(Path(d) / "firmalar.xlsx", [
                ["Kısa Adı", "Kapanış Tarihi", "Devreden KDV"],
                ["BIRLIK TIC", "", 5000.5],
                ["KAYA INS", "", "5.000"],
                ["YILDIZ OTO", "", ""],
            ])
            self.assertEqual(devreden_kdvleri(yol), {"BIRLIK TIC": 5000.5, "KAYA INS": 5000.0})
            self.assertEqual(devreden_kdvleri(Path(d) / "yok.xlsx"), {})
            self.assertEqual(devreden_kdvleri(""), {})

    def test_gostergeler(self):
        from lucabot import gostergeler
        donem = "01/09/2026-30/09/2026"
        kayitlar = {
            "BIRLIK TIC": {"donem": donem,
                           "sayilar": {"e-arsiv-alis": 3, "e-arsiv-interaktif": 5, "esmm-alis": 2},
                           "faturalar": {"e-arsiv-interaktif": [["X", "AAA2026000000001", 1.0]]},
                           "tevkifat": {"e-fatura-alis": 2}, "tevkifat_kdv": {"e-fatura-alis": 700},
                           "tevkifat_kdv_tahmini": {"e-fatura-alis": True},
                           "matrah": {"esmm-alis": 3000},
                           "kdv": {"e-arsiv-satis": 1000, "e-fatura-satis": 500, "e-arsiv-alis": 600}},
            "YILDIZ OTO": {"donem": donem, "sayilar": {}, "kdv": {"turmob-satis": 300}},
            "AZ ALIS": {"donem": donem, "kdv": {"e-fatura-satis": 100, "e-fatura-alis": 400}},
            "ESKI AY": {"donem": "01/08/2026-31/08/2026", "kdv": {"e-fatura-satis": 999}},
        }
        g = gostergeler.hesapla(kayitlar, {"BIRLIK TICARET": 200}, donem)
        self.assertEqual(g["tevkifat"], [{"firma": "BIRLIK TIC", "adet": 2, "tutar": 700,
                                          "tahmini": True}])
        self.assertEqual(g["smm"], [{"firma": "BIRLIK TIC", "adet": 2, "tutar": 3000}])
        self.assertEqual(g["fark"], [{"firma": "BIRLIK TIC", "interaktif": 5, "earsiv": 3, "fark": 2}])
        # satis 1500 - alis 600 - devreden 200 = 700; Luca'da kisaltilmis ad listedeki tam adla eslesir
        self.assertEqual(g["kdv"], [
            {"firma": "BIRLIK TIC", "satis": 1500, "alis": 600, "devreden": 200, "odeme": 700},
            {"firma": "YILDIZ OTO", "satis": 300, "alis": 0, "devreden": None, "odeme": 300}])
        t = gostergeler.toplamlar(g)
        self.assertEqual((t["tevkifat"], t["smm"], t["fark"], t["kdv_firma"]), (700, 3000, 2, 2))
        self.assertEqual(gostergeler.tl(1234.5), "1.234,50 TL")


class FirmaTablosuTestleri(unittest.TestCase):
    """Sablon indir / tabloda ekran sec / kaydet: bot ayni dosyayi dogru okumali."""

    def test_sablonu_bot_okur_hepsi_sorgulanir(self):
        from lucabot import firma_tablosu
        with tempfile.TemporaryDirectory() as d:
            yol = firma_tablosu.sablon_olustur(Path(d) / "sablon.xlsx", ["BIRLIK TIC", "KAYA INS"])
            self.assertEqual(firma_listesini_oku(yol), {"BIRLIK TIC": (None, set()),
                                                       "KAYA INS": (None, set())})
            from openpyxl import load_workbook
            self.assertEqual(load_workbook(yol).sheetnames, ["Firmalar", "Açıklama"])
            tablo = firma_tablosu.tabloyu_oku(yol)
            self.assertEqual(len(tablo[0]["ekranlar"]), 10)

    def test_eski_listeye_secim_yazilir_diger_sutunlar_korunur(self):
        from openpyxl import Workbook, load_workbook
        from lucabot import firma_tablosu
        from lucabot.firma_listesi import devreden_kdvleri
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "firmalar.xlsx"
            wb = Workbook()
            wb.active.append(["Kısa Adı", "Kapanış Tarihi", "Telefon", "e-Fatura Alış"])
            wb.active.append(["BIRLIK TIC", "", "0212", "X"])
            wb.active.append(["KAYA INS", "15/03/2026", "0216", ""])
            wb.create_sheet("Notlar")["A1"] = "elle yazilmis not"
            wb.save(yol)
            tablo = firma_tablosu.tabloyu_oku(yol)
            self.assertNotIn("e-fatura-alis", tablo[0]["ekranlar"])
            self.assertEqual(len(tablo[1]["ekranlar"]), 10)
            # arayuzde: BIRLIK'te yalnizca e-Arsiv Alis + Interaktif, KAYA'da GIB 5000 kapali
            tablo[0]["ekranlar"] = {"e-arsiv-alis", "e-arsiv-interaktif"}
            tablo[0]["devreden"] = "5.000"
            tablo[1]["ekranlar"].discard("gib-5000")
            yedek = firma_tablosu.tabloyu_yaz(yol, tablo)
            self.assertTrue(yedek.exists())

            okunan = firma_listesini_oku(yol)
            self.assertEqual(len(okunan["BIRLIK TIC"][1]), 8)
            self.assertNotIn("e-arsiv-alis", okunan["BIRLIK TIC"][1])
            self.assertEqual(okunan["KAYA INS"], (date(2026, 3, 15), {"gib-5000"}))
            self.assertEqual(devreden_kdvleri(yol), {"BIRLIK TIC": 5000.0})
            wb = load_workbook(yol)
            self.assertEqual(wb.sheetnames, ["Sheet", "Notlar"])
            self.assertEqual(wb["Notlar"]["A1"].value, "elle yazilmis not")
            self.assertEqual(wb.active["C2"].value, "0212")


ORNEK_MUSTERILER = [
    {"ad": "AKIN COBAN", "unvan": "AKIN ÇOBAN", "vkn": "1111111111", "acilis": "01/01/2020",
     "kapanis": "31/12/2026"},
    {"ad": "KEREM TICARET", "unvan": "KEREM TİCARET", "vkn": "5555555555", "acilis": "01/01/2019",
     "kapanis": "28/02/2026"},
    {"ad": "DENTAL SAGLIK HIZMETLERI", "unvan": "DENTAL SAĞLIK HİZMETLERİ LTD. ŞTİ.",
     "vkn": "2222222222", "acilis": "15/04/2026", "kapanis": ""},
    {"ad": "YENI FIRMA LTD", "unvan": "YENİ FİRMA LİMİTED", "vkn": "7777777777",
     "acilis": "01/06/2026", "kapanis": ""},
]


class MusteriListesiTestleri(unittest.TestCase):
    """Luca Müşteri Listesi'nin tablodan okunmasi ve firmalar.xlsx ile birlestirilmesi."""

    BASLIK = ["", "Kısa Ad", "Ünvan", "Vergi Dairesi", "VKN", "Açılış Tarihi", "Kapanış Tarihi"]

    def test_tarih_metni_bicimleri(self):
        from lucabot.musteri_listesi import tarih_metni
        self.assertEqual(tarih_metni("05.03.2026"), "05/03/2026")
        self.assertEqual(tarih_metni("2026-03-05 00:00:00"), "05/03/2026")
        self.assertEqual(tarih_metni(date(2026, 3, 5)), "05/03/2026")
        self.assertEqual(tarih_metni("31/02/2026"), "")
        self.assertEqual(tarih_metni(""), "")
        self.assertEqual(tarih_metni(None), "")

    def test_baslikli_tablodan_kayit(self):
        from lucabot.musteri_listesi import kayitlari_cikar
        tablo = [self.BASLIK,
                 ["", "BURAK ALİ", "BURAK ALİ ARSLAN", "ÜMRANİYE VERGİ DAİRESİ", "12345678901",
                  "02.01.2020", ""],
                 ["", "KAYA", "KAYA İNŞAAT", "KADIKÖY VERGİ DAİRESİ", "9876543210",
                  "01/01/2019", "28/02/2026"]]
        kayitlar, baslik = kayitlari_cikar([(0, tablo)])
        self.assertEqual(baslik, self.BASLIK)
        self.assertEqual([(k["ad"], k["vkn"], k["acilis"], k["kapanis"]) for k in kayitlar],
                         [("BURAK ALİ", "12345678901", "02/01/2020", ""),
                          ("KAYA", "9876543210", "01/01/2019", "28/02/2026")])
        self.assertEqual(kayitlar[0]["unvan"], "BURAK ALİ ARSLAN")
        self.assertEqual(kayitlar[0]["vergi_dairesi"], "ÜMRANİYE VERGİ DAİRESİ")

    def test_baslik_ayri_tabloda_durunca_bulunur(self):
        from lucabot.musteri_listesi import kayitlari_cikar
        veri = [["BURAK ALİ", "BURAK ALİ ARSLAN", "ÜMRANİYE", "12345678901", "02.01.2020", "05.05.2026"]]
        kayitlar, baslik = kayitlari_cikar([(0, [self.BASLIK[1:]]), (0, veri)])
        self.assertEqual(kayitlar[0]["kapanis"], "05/05/2026")
        self.assertEqual(kayitlar[0]["acilis"], "02/01/2020")

    def test_veri_satirinda_fazladan_basa_sutun_varsa_baslik_saga_hizalanir(self):
        from lucabot.musteri_listesi import kayit_cikar
        k = kayit_cikar(self.BASLIK[1:], ["", "1", "KAYA", "KAYA İNŞAAT", "KADIKÖY", "9876543210",
                                           "01/01/2019", "28/02/2026"])
        self.assertEqual((k["ad"], k["acilis"], k["kapanis"]), ("KAYA", "01/01/2019", "28/02/2026"))

    def test_baslik_okunamazsa_desenden_okunur_tek_tarih_kapanis_sayilmaz(self):
        from lucabot.musteri_listesi import kayitlari_cikar
        kayitlar, baslik = kayitlari_cikar([(0, [["KAYA", "KAYA İNŞAAT", "KADIKÖY", "9876543210",
                                                   "01/01/2019"]])])
        self.assertIsNone(baslik)
        self.assertEqual((kayitlar[0]["ad"], kayitlar[0]["unvan"], kayitlar[0]["vkn"]),
                         ("KAYA", "KAYA İNŞAAT", "9876543210"))
        self.assertEqual((kayitlar[0]["acilis"], kayitlar[0]["kapanis"]), ("01/01/2019", ""))

    def test_vkn_li_tablo_secilir_ayni_firma_bir_kez(self):
        from lucabot.musteri_listesi import kayitlari_cikar
        menu = [["Yeni", "Filtre", "Şirket Sil"], ["a", "b", "c"]]
        veri = [self.BASLIK, ["", "KAYA", "KAYA İNŞAAT", "KADIKÖY", "9876543210", "", ""],
                ["", "KAYA", "KAYA İNŞAAT", "KADIKÖY", "9876543210", "", ""]]
        kayitlar, _ = kayitlari_cikar([(0, menu), (0, veri)])
        self.assertEqual(len(kayitlar), 1)
        self.assertEqual(kayitlari_cikar([(0, menu)]), ([], None))

    GERCEK_BASLIK = ["", "Kısa Adı", "Uzun Adı", "Vergi Dairesi", "Vergi No", "TC Kimlik No", "Açıklama",
                     "Kuruluş Tarihi", "Kapanış Tarihi"]

    def test_gercek_luca_basligi_ve_vergi_nosuz_firma(self):
        """Gercek ekran: Uzun Adı / Kuruluş Tarihi basliklari; vergi no'su bos firma da listede."""
        from lucabot.musteri_listesi import kayitlari_cikar
        tablo = [self.GERCEK_BASLIK,
                 ["", "ADEM", "ADEM YILMAZ", "ÜMRANİYE VERGİ DAİRESİ", "9660268213", "18719053408", "",
                  "01/04/2021", ""],
                 ["", "AHMET EREN", "AHMET EREN AKSOY", "ÜMRANİYE VERGİ DAİRESİ", "0350869711",
                  "10496564184", "GENÇ GİRİŞİM", "09/08/2024", "31/08/2026"],
                 ["", "BESTHARNES", "BEST HARNES TEKSTİL SANAYİ", "SULTANBEYLİ VERGİ DAİRESİ", "1660852841",
                  "", "", "08/05/2023", ""],
                 ["", "VERGISIZ", "VERGİ NUMARASIZ KİŞİ", "ÜMRANİYE VERGİ DAİRESİ", "", "", "DÖNEM BEKLİYOR",
                  "01/01/2026", ""],
                 ["", "VERGISIZ", "VERGİ NUMARASIZ KİŞİ", "ÜMRANİYE VERGİ DAİRESİ", "", "", "DÖNEM BEKLİYOR",
                  "01/01/2026", ""]]
        kayitlar, baslik = kayitlari_cikar([(0, tablo)])
        self.assertEqual(baslik, self.GERCEK_BASLIK)
        self.assertEqual([k["ad"] for k in kayitlar], ["ADEM", "AHMET EREN", "BESTHARNES", "VERGISIZ"])
        ahmet = kayitlar[1]
        self.assertEqual((ahmet["unvan"], ahmet["vkn"], ahmet["tc"], ahmet["acilis"], ahmet["kapanis"]),
                         ("AHMET EREN AKSOY", "0350869711", "10496564184", "09/08/2024", "31/08/2026"))
        self.assertEqual(kayitlar[0]["acilis"], "01/04/2021")

    def test_toplam_kayit_yazisi(self):
        from lucabot.musteri_listesi import TOPLAM_DESENI
        self.assertEqual(TOPLAM_DESENI.search("Kayıt Sayısı: 105").group(1), "105")
        self.assertEqual(TOPLAM_DESENI.search("Toplam Kayıt Sayısı: 7").group(1), "7")
        self.assertIsNone(TOPLAM_DESENI.search("Silinmiş dönemler dahil dönem sayısı: 105"))

    def test_luca_kaydi_bulma(self):
        from lucabot.firma_tablosu import luca_kaydi_bul
        bul = lambda ad: (luca_kaydi_bul(ad, ORNEK_MUSTERILER) or {}).get("ad")
        self.assertEqual(bul("akin çoban"), "AKIN COBAN")          # unvanla
        self.assertEqual(bul("Kerem Ticaret"), "KEREM TICARET")
        self.assertEqual(bul("DENTAL SAGLIK"), "DENTAL SAGLIK HIZMETLERI")   # kisaltilmis ad
        self.assertIsNone(bul("DENTAL"))                            # 8 harf altinda baslangic: eslesmez
        self.assertEqual(bul("DENTAL SAGLIK HIZ"), "DENTAL SAGLIK HIZMETLERI")
        self.assertIsNone(bul("BAŞKA FİRMA"))

    def test_plan_ve_uygulama(self):
        from openpyxl import Workbook, load_workbook
        from lucabot import firma_tablosu
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "firmalar.xlsx"
            wb = Workbook()
            wb.active.append(["Kısa Adı", "Kapanış Tarihi", "Devreden KDV", "e-Fatura Alış"])
            wb.active.append(["AKIN COBAN", "", 1500, "X"])                 # Luca'da donem sonu: acik
            wb.active.append(["KEREM TICARET", "", "", ""])                  # kapanmis
            wb.active.append(["ESKI DONEM LTD", "10/02/2026", "", ""])       # Luca 2026 listesinde yok
            wb.active.append(["DENTAL SAGLIK HIZ", "20/05/2026", "", ""])    # Luca'da kapanis yok: korunur
            wb.save(yol)
            plan = firma_tablosu.luca_plani(yol, 2026, ORNEK_MUSTERILER)
            self.assertEqual([g["ad"] for g in plan["guncellenecek"]],
                             ["AKIN COBAN", "KEREM TICARET", "DENTAL SAGLIK HIZ"])
            self.assertEqual(plan["guncellenecek"][2]["yeni_ad"], "DENTAL SAGLIK HIZMETLERI")
            self.assertEqual(plan["guncellenecek"][1]["kapanis"], ("", "28/02/2026"))
            self.assertEqual(plan["guncellenecek"][0]["kapanis"], ("", ""))      # 31/12/2026 kapanis degil
            self.assertEqual(plan["guncellenecek"][0]["acilis"], ("", "01/01/2020"))
            self.assertEqual(plan["guncellenecek"][2]["kapanis"], ("20/05/2026", "20/05/2026"))
            self.assertEqual(plan["luca_da_yok"], ["ESKI DONEM LTD"])
            self.assertEqual([r["ad"] for r in plan["yeni"]], ["YENI FIRMA LTD"])

            yedek = firma_tablosu.luca_plani_uygula(yol, plan)   # silmeden
            self.assertTrue(yedek.exists())
            okunan = firma_listesini_oku(yol)
            self.assertEqual(okunan["KEREM TICARET"][0], date(2026, 2, 28))
            self.assertEqual(okunan["DENTAL SAGLIK HIZMETLERI"][0], date(2026, 5, 20))   # Luca'daki ada cevrildi
            self.assertEqual(okunan["ESKI DONEM LTD"][0], date(2026, 2, 10))      # silinmedi, degismedi
            self.assertEqual(len(okunan["YENI FIRMA LTD"][1]), 0)                 # tum ekranlar sorgulanir
            self.assertEqual(okunan["AKIN COBAN"][1], {"e-fatura-alis"})          # ekran secimi korundu
            ws = load_workbook(yol).active
            basliklar = [c.value for c in ws[1]]
            self.assertIn("Açılış Tarihi", basliklar)
            self.assertEqual(ws.cell(row=2, column=3).value, 1500)                # Devreden KDV'ye dokunulmadi
            self.assertEqual(ws.max_row, 6)
            # ikinci kez ayni liste: degisecek bir sey kalmaz (Luca'da olmayan firma hala listede)
            plan2 = firma_tablosu.luca_plani(yol, 2026, ORNEK_MUSTERILER)
            self.assertEqual((plan2["guncellenecek"], plan2["yeni"]), ([], []))
            self.assertEqual(plan2["luca_da_yok"], ["ESKI DONEM LTD"])
            # liste Luca'yi yansitsin: Luca'da olmayan firma cikarilir, digerleri ve ekran secimleri kalir
            firma_tablosu.luca_plani_uygula(yol, plan2, eksikleri_sil=True)
            okunan = firma_listesini_oku(yol)
            self.assertNotIn("ESKI DONEM LTD", okunan)
            self.assertEqual(sorted(okunan), ["AKIN COBAN", "DENTAL SAGLIK HIZMETLERI", "KEREM TICARET",
                                              "YENI FIRMA LTD"])
            self.assertEqual(okunan["AKIN COBAN"][1], {"e-fatura-alis"})


ORNEK_BEYANNAME = """
                     KATMA DEĞER VERGİSİ BEYANNAMESİ                                1015 A
               (Gerçek Usulde Vergilendirilen Mükellefler İçin)                    1
 ÜMRANİYE                  DÖNEM TİPİ                  Yıl                         2026
 Vergi Dairesi Müdürlüğü   Aylık                       Ay                          Ağustos
 Onay Zamanı :              28.09.2026 - 19:47:44
 Vergi Kimlik Numarası (TC Kimlik No)          11111111111
  Soyadı (Unvanı)                               DENEMEOĞLU
  Adı (Unvanın Devamı)                          ÇAĞRI
Toplam Katma Değer Vergisi                                                 28.061,32
Önceki Dönemden Devreden              101 - Önceki Dönemden Devreden       27.972,22
İndirimler Toplamı                                                         62.089,01
 İade Edilmesi Gereken Katma Değer Vergisi                                      0,00
Sonraki Döneme Devreden Katma Değer Vergisi                                34.027,69
"""


class BeyannameTestleri(unittest.TestCase):
    def setUp(self):
        from lucabot import beyanname
        self.bm = beyanname
        self.b = beyanname.cozumle(
            ORNEK_BEYANNAME, "CAGRI_DENE_034252_6170780106_KDV1_45_01082026-31082026_BYN_17.pdf")

    def test_tutarlar_ve_donem(self):
        b = self.b
        self.assertEqual((b.onceki_devreden, b.sonraki_devreden), (27972.22, 34027.69))
        self.assertEqual((b.bas, b.bit), (date(2026, 8, 1), date(2026, 8, 31)))
        self.assertEqual(b.unvan, "DENEMEOĞLU ÇAĞRI")
        self.assertEqual(b.dosya_adi_firma, "CAGRI DENE")
        self.assertEqual(b.vkn, "11111111111")
        # dosya adinda tarih yoksa donem metinden ("Yıl 2026 / Ay Ağustos")
        b2 = self.bm.cozumle(ORNEK_BEYANNAME, "beyanname.pdf")
        self.assertEqual((b2.bas, b2.bit), (date(2026, 8, 1), date(2026, 8, 31)))

    def test_hedef_doneme_gore_dogru_satir(self):
        adlar = ["CAGRI DENEMEOGLU", "BASKA FIRMA"]
        eylul, _, _ = self.bm.devirleri_bul([self.b], adlar, date(2026, 9, 1))
        self.assertEqual(eylul[0]["tutar"], 34027.69)          # agustos beyannamesi: sonraki doneme
        agustos, _, _ = self.bm.devirleri_bul([self.b], adlar, date(2026, 8, 1))
        self.assertEqual(agustos[0]["tutar"], 27972.22)        # kendi beyannamesi: 101 satiri
        _, _, disi = self.bm.devirleri_bul([self.b], adlar, date(2026, 11, 1))
        self.assertEqual(len(disi), 1)

    def test_firma_eslestirme(self):
        bul = self.bm.firma_bul
        self.assertEqual(bul(self.b, ["ÇAĞRI DENEMEOĞLU", "ÇAĞRI AKSU"]), "ÇAĞRI DENEMEOĞLU")
        self.assertEqual(bul(self.b, ["CAGRI DENE", "CAGRI"]), "CAGRI DENE")   # Luca kisaltmasi
        self.assertEqual(bul(self.b, ["DENEMEOĞLU Ç"]), "DENEMEOĞLU Ç")
        self.assertIsNone(bul(self.b, ["ÇAĞRI"]))              # tek kelime her Cagri'ya yapismaz
        self.assertIsNone(bul(self.b, ["ÇAĞRI AKSU"]))

    def test_kodsuz_devreden_satiri_ve_devirsiz_beyanname(self):
        # bazi beyannamelerde satirda "101 -" kodu yok
        kodsuz = ORNEK_BEYANNAME.replace("101 - Önceki Dönemden Devreden       27.972,22",
                                         "                                     859.116,51")
        self.assertEqual(self.bm.cozumle(kodsuz, "x.pdf").onceki_devreden, 859116.51)
        # devir yoksa bolum hic basilmaz: 0
        devirsiz = "\n".join(s for s in ORNEK_BEYANNAME.splitlines() if "Önceki Dönemden" not in s)
        self.assertEqual(self.bm.cozumle(devirsiz, "x.pdf").onceki_devreden, 0.0)
        # bolum var ama tutar okunamadiysa 0 yazilmaz, elle yazilmak uzere None
        bozuk = ORNEK_BEYANNAME.replace("27.972,22", "") + "\nÖNCEKİ DÖNEMDEN DEVREDEN İNDİRİLECEK KDV\n"
        b = self.bm.cozumle(bozuk, "x.pdf")
        self.assertIsNone(b.onceki_devreden)
        sonuc, _, _ = self.bm.devirleri_bul([b], ["CAGRI DENEMEOGLU"], date(2026, 8, 1))
        self.assertIsNone(sonuc[0]["tutar"])

    def test_kdv2_ve_duzeltme(self):
        with self.assertRaises(self.bm.BeyannameDegil):
            self.bm.cozumle("KDV BEYANNAMESİ 2 (Sorumlu Sıfatıyla)", "x.pdf")
        from datetime import datetime
        duzeltme = self.bm.cozumle(ORNEK_BEYANNAME.replace("34.027,69", "30.000,00")
                                   .replace("28.09.2026", "30.09.2026"), "duzeltme.pdf")
        sonuc, _, _ = self.bm.devirleri_bul([self.b, duzeltme], ["CAGRI DENEMEOGLU"], date(2026, 9, 1))
        self.assertEqual(sonuc[0]["tutar"], 30000.0)           # en son onaylanan
        self.assertEqual(duzeltme.onay, datetime(2026, 9, 30, 19, 47, 44))


class SorguBitisiTestleri(unittest.TestCase):
    def test_sona_erdi_yalnizca_sondaysa(self):
        from lucabot.gib_sorgu import sorgu_bitti_mi
        bitmis = ("İşlem Takip\n[82/82] AAC2026000116758 numaralı belge sistemde kayıtlıdır.\n"
                  "Fatura kaydetme işlemi sona erdi.\nOtomatik aşağı kaydır.\nKapat")
        self.assertTrue(sorgu_bitti_mi(bitmis))
        surmekte = ("İşlem Takip\nFatura listesi alma işlemi sona erdi.\n"
                    "[3/82] VEA2026000003479 numaralı belge sistemde kayıtlıdır.\nOtomatik aşağı kaydır.")
        self.assertFalse(sorgu_bitti_mi(surmekte))
        kirmizi = ("Sorgulama Tarihi: 26/09/2026 Hata mesajı: Belirtilen tarih aralığında fatura"
                   " bulunamadı. Bu hata GİB servislerinden alınmıştır.\nOtomatik aşağı kaydır.")
        self.assertFalse(sorgu_bitti_mi(kirmizi))
        self.assertFalse(sorgu_bitti_mi(""))


class DurdurDosyasiTestleri(unittest.TestCase):
    """Konsolsuz calisan arayuz botu sinyalle degil dosyayla durdurur."""

    def setUp(self):
        from lucabot import bekleme
        self.bekleme = bekleme
        self.eski = bekleme.DURDUR_DOSYASI
        self.d = Path(tempfile.mkdtemp())
        bekleme.DURDUR_DOSYASI = self.d / "durdur.istek"

    def tearDown(self):
        self.bekleme.DURDUR_DOSYASI = self.eski

    def test_bekleme_adimi_dosyayi_gorunce_durur(self):
        class Sayfa:
            def wait_for_timeout(self, ms):
                pass

            def is_closed(self):
                return False

        self.bekleme.nabiz(Sayfa(), 1)  # dosya yok: normal
        self.bekleme.DURDUR_DOSYASI.write_text("durdur")
        with self.assertRaises(KeyboardInterrupt):
            self.bekleme.kosulu_bekle(Sayfa(), lambda: False, 5000)  # kosul icindeki hatalar yutulur, bu yutulmaz
        self.assertFalse(self.bekleme.DURDUR_DOSYASI.exists())  # bir kez tuketilir
        self.bekleme.nabiz(Sayfa(), 1)  # tekrar durdurmaz


class YazTestleri(unittest.TestCase):
    def test_konsol_kapaninca_yazma_calismayi_durdurmaz(self):
        """Konsol penceresi kapaninca print "[Errno 22] Invalid argument" verir; gunluge yine yazilir."""
        from unittest import mock
        from lucabot import ortak
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "calisma.log"
            for hata in (OSError(22, "Invalid argument"), ValueError("I/O operation on closed file")):
                with mock.patch("builtins.print", side_effect=hata):
                    ortak.yaz("deneme mesaji", log)  # hata firlatmamali
            self.assertEqual(log.read_text(encoding="utf-8").count("deneme mesaji"), 2)


class GecisAraciTestleri(unittest.TestCase):
    """gecis_rapor_birlestir.py: eski gunluk rapor.json'lari tek surekli rapora birlestirir."""

    def setUp(self):
        import gecis_rapor_birlestir
        self.arac = gecis_rapor_birlestir

    def test_eski_gunler_ve_mevcut_rapor_birlesir(self):
        with tempfile.TemporaryDirectory() as d:
            kok = Path(d) / "indirilenler"
            (kok / "2026-09-24").mkdir(parents=True)
            (kok / "2026-09-25").mkdir(parents=True)
            # eski format: "guncellenme" alani yok (ozellik eklenmeden once yazilmis kayitlar boyle)
            (kok / "2026-09-24" / "rapor.json").write_text(json.dumps({
                "AKIN COBAN": {"firma": "AKIN COBAN", "donem": "01/08/2026-31/08/2026",
                              "durumlar": {"e-arsiv-alis": "tamam", "e-fatura-alis": "fatura yok"},
                              "sayilar": {"e-arsiv-alis": 3, "e-fatura-alis": 0},
                              "iptal": {"e-arsiv-alis": 1}, "tevkifat": {"e-arsiv-alis": 1},
                              "inmeyen": {}, "faturalar": {}, "dosya": 2, "not": "",
                              "son": "24/09/2026 10:00", "matrah": {"e-arsiv-alis": 1000},
                              "kdv": {"e-arsiv-alis": 200}},
                "ESKI FIRMA": {"firma": "ESKI FIRMA", "durumlar": {"e-arsiv-alis": "fatura yok"},
                              "sayilar": {"e-arsiv-alis": 0}, "son": "24/09/2026 10:05"},
            }), encoding="utf-8")
            (kok / "2026-09-25" / "rapor.json").write_text(json.dumps({
                "AKIN COBAN": {"firma": "AKIN COBAN", "donem": "01/08/2026-31/08/2026",
                              "durumlar": {"e-fatura-satis": "tamam"},
                              "sayilar": {"e-fatura-satis": 5}, "son": "25/09/2026 11:00",
                              "matrah": {"e-fatura-satis": 400}, "kdv": {"e-fatura-satis": 80}},
            }), encoding="utf-8")
            # mevcut SUREKLI rapor (yeni koddan, "guncellenme" VAR): AKIN COBAN'in e-arsiv-alis'i
            # bugun tekrar calisip 5 fatura bulmus - en guncel deger bu olmali
            sonuc = yeni_sonuc("AKIN COBAN", "e-arsiv-alis")
            sonuc.update(durum="tamam", fatura_sayisi=5, matrah=1500, kdv=300)
            rapor.guncelle(kok, [sonuc], [], "e-arsiv-alis")

            self.assertEqual(self.arac.main.__module__, "gecis_rapor_birlestir")
            gunler = self.arac._gunluk_klasorler(kok)
            self.assertEqual([g.name for g in gunler], ["2026-09-24", "2026-09-25"])

            birlesik = {}
            for gun in gunler:
                self.arac._kaydi_birlestir(birlesik, self.arac._veriyi_oku(gun / "rapor.json"), gun.name)
            self.arac._kaydi_birlestir(birlesik, self.arac._veriyi_oku(kok / "rapor.json"), None)

            akin = birlesik["AKIN COBAN"]
            # bugunku (surekli rapordan gelen) deger onceki gunlerin verisini gecmeli
            self.assertEqual(akin["sayilar"]["e-arsiv-alis"], 5)
            self.assertEqual(akin["matrah"]["e-arsiv-alis"], 1500)
            # sadece gecmis gunlerde olan ekranlar korunmali
            self.assertEqual(akin["sayilar"]["e-fatura-alis"], 0)
            self.assertEqual(akin["sayilar"]["e-fatura-satis"], 5)
            # eski kayitta "guncellenme" yoktu; firma-geneli "son" alanindan turetilmis olmali
            self.assertEqual(akin["guncellenme"]["e-fatura-alis"], "24/09/2026 10:00")
            self.assertEqual(akin["guncellenme"]["e-fatura-satis"], "25/09/2026 11:00")
            self.assertIn("ESKI FIRMA", birlesik)

    def test_birlestirme_dosyayi_yedekler_ve_eskiye_dokunmaz(self):
        with tempfile.TemporaryDirectory() as d:
            kok = Path(d) / "indirilenler"
            gun = kok / "2026-09-24"
            gun.mkdir(parents=True)
            (gun / "rapor.json").write_text(json.dumps({
                "A": {"firma": "A", "durumlar": {"e-arsiv-alis": "tamam"},
                     "sayilar": {"e-arsiv-alis": 1}, "son": "24/09/2026 10:00"},
            }), encoding="utf-8")
            rapor.guncelle(kok, [yeni_sonuc("B", "e-arsiv-alis")], [], "e-arsiv-alis")
            eski_icerik = (gun / "rapor.json").read_text(encoding="utf-8")

            (Path(d) / "ayarlar.json").write_text(json.dumps({"indirme_klasoru": str(kok)}),
                                                  encoding="utf-8")
            import os
            onceki = os.environ.get("LUCA_BOT_AYAR")
            os.environ["LUCA_BOT_AYAR"] = str(Path(d) / "ayarlar.json")
            try:
                self.assertEqual(self.arac.main(), 0)
            finally:
                if onceki is None:
                    os.environ.pop("LUCA_BOT_AYAR", None)
                else:
                    os.environ["LUCA_BOT_AYAR"] = onceki

            self.assertEqual((gun / "rapor.json").read_text(encoding="utf-8"), eski_icerik)
            yedekler = [p for p in kok.iterdir() if p.name.startswith("rapor-birlestirme-oncesi")]
            self.assertEqual(len(yedekler), 1)
            self.assertTrue((yedekler[0] / "rapor.json").exists())
            birlesik = json.loads((kok / "rapor.json").read_text(encoding="utf-8"))
            self.assertEqual(set(birlesik), {"A", "B"})


if __name__ == "__main__":
    unittest.main()
