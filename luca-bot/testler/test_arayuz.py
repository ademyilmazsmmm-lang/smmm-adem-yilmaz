# -*- coding: utf-8 -*-
"""Arayuz (luca_arayuz.py) testleri: gercek bot yerine ciktisini taklit eden bir betik calisir.

Ekran gerekir (Linux'ta: xvfb-run -a python -m unittest testler.test_arayuz);
tkinter ya da ekran yoksa testler atlanir.
"""

import json
import os
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

try:
    import tkinter as tk
    _kok = tk.Tk()
    _kok.destroy()
    TK_VAR = True
except Exception:  # tkinter yok ya da ekran yok
    TK_VAR = False

SAHTE_BOT = textwrap.dedent('''
    import sys, time
    print("ARGS " + " ".join(sys.argv[1:]), flush=True)
    print("Luca'da 2 firma bulundu", flush=True)
    try:
        for i, ad in enumerate(["BIRLIK TIC", "YILDIZ OTO"], 1):
            print(f"[{i}/2] {ad}  | tahmini kalan: {3 - i} dk", flush=True)
            print("  [OK] e-Arşiv Alış Faturaları: tamam (3 fatura)", flush=True)
            print("    UYARI: ornek uyari", flush=True)
            time.sleep(float(sys.argv[-1]) if sys.argv[-1].replace(".", "").isdigit() else 0.2)
    except KeyboardInterrupt:
        print("Durduruldu. O ana kadarki sonuclar kaydedildi", flush=True)
        sys.exit(130)
    print("son satir (yeni satir yok)", end="", flush=True)
''')


@unittest.skipUnless(TK_VAR, "tkinter ya da ekran yok")
class ArayuzTestleri(unittest.TestCase):
    def setUp(self):
        from openpyxl import Workbook
        import luca_arayuz
        self.mod = luca_arayuz
        self.d = Path(tempfile.mkdtemp(prefix="arayuz-test-"))
        wb = Workbook()
        wb.active.append(["Kısa Adı", "Devreden KDV"])
        wb.active.append(["BIRLIK TICARET", 200])
        wb.save(self.d / "firmalar.xlsx")
        (self.d / "indir").mkdir()
        donem = "01/09/2026-30/09/2026"
        (self.d / "indir" / "rapor.json").write_text(json.dumps({
            "BIRLIK TIC": {"donem": donem, "sayilar": {"esmm-alis": 1}, "matrah": {"esmm-alis": 1500},
                           "tevkifat": {"e-fatura-alis": 2}, "tevkifat_kdv": {"e-fatura-alis": 700},
                           "kdv": {"e-fatura-satis": 1000, "e-fatura-alis": 300}},
        }), encoding="utf-8")
        self.ayar = self.d / "ayarlar.json"
        self.ayar.write_text(json.dumps({
            "uye_no": "1", "kullanici_adi": "deneme", "parola": "x", "baska_ayar": 42,
            "indirme_klasoru": str(self.d / "indir"), "firma_listesi": str(self.d / "firmalar.xlsx"),
            "baslangic_tarihi": "01/09/2026", "bitis_tarihi": "30/09/2026"}), encoding="utf-8")
        os.environ["LUCA_BOT_AYAR"] = str(self.ayar)
        self.bot = self.d / "sahte_bot.py"
        self.bot.write_text(SAHTE_BOT, encoding="utf-8")
        self.kok = tk.Tk()
        self.app = luca_arayuz.Arayuz(self.kok)
        self.app.BOT = self.bot

    def tearDown(self):
        if self.app.surec:
            self.app.surec.kill()
            self.app.surec.wait()
            self.app.surec.stdout.close()
        self.kok.after_cancel(self.app.dongu_id)
        self.kok.destroy()
        os.environ.pop("LUCA_BOT_AYAR", None)

    def _bekle(self, kosul, saniye=20):
        son = time.time() + saniye
        while time.time() < son:
            self.kok.update()
            if kosul():
                return True
            time.sleep(0.05)
        return False

    def test_kutular_rapordan_doluyor(self):
        k = self.app.kutu
        self.assertEqual(k["tevkifat"].deger.cget("text"), "700,00 TL")
        self.assertEqual(k["smm"].deger.cget("text"), "1.500,00 TL")
        self.assertEqual(k["fark"].deger.cget("text"), "0 fatura")
        self.assertEqual(k["kdv"].deger.cget("text"), "1 firma")  # 1000 - 300 - 200 devreden
        self.assertEqual(self.app.gostergeler["kdv"][0]["odeme"], 500)

    def test_detay_penceresi_acilir(self):
        once = len(self.kok.winfo_children())
        self.app.detay("kdv")
        self.kok.update()
        self.assertEqual(len(self.kok.winfo_children()), once + 1)

    def test_komut(self):
        komut = self.app.komut()
        self.assertIn("--hepsi", komut)
        self.assertIn("--bitince-kapat", komut)
        self.assertEqual(komut[komut.index("--baslangic") + 1], "01/09/2026")
        self.app.v_ekran["e-arsiv-satis"].set(False)
        self.app.v_devam.set(False)
        self.app.v_firma.set("BIRLIK")
        komut = self.app.komut()
        self.assertNotIn("--hepsi", komut)
        self.assertEqual(komut.count("--belge-tipi"), 9)
        self.assertIn("--bastan", komut)
        self.assertEqual(komut[komut.index("--firma") + 1], "BIRLIK")
        self.app.v_bit.set("31/08/2026")
        with self.assertRaises(ValueError):
            self.app.komut()
        self.app.v_bit.set("30-09")
        with self.assertRaises(ValueError):
            self.app.komut()

    def test_calistir_canli_log_ve_bitis(self):
        self.app.calistir()
        self.assertIsNotNone(self.app.surec)
        self.assertTrue(self._bekle(lambda: self.app.surec is None))
        log = self.app.log_metni()
        self.assertIn("--bitince-kapat", log)
        self.assertIn("[OK] e-Arşiv Alış Faturaları", log)
        self.assertIn("son satir (yeni satir yok)", log)
        self.assertIn("Tamamlandı", self.app.ilerleme_etiketi.cget("text"))
        self.assertEqual(self.app.durum_etiketi.cget("text").strip(), "Tamamlandı")
        self.assertEqual(str(self.app.calistir_dugmesi.cget("state")), "normal")
        # ayarlar kaydedildi, arayuzun bilmedigi anahtarlar korundu
        ayar = json.loads(self.ayar.read_text(encoding="utf-8"))
        self.assertEqual(ayar["baska_ayar"], 42)
        self.assertEqual(len(ayar["arayuz_ekranlar"]), 10)
        # renklendirme: [OK] satiri yesil etiketli
        self.assertTrue(self.app.log.tag_ranges("ok"))
        self.assertTrue(self.app.log.tag_ranges("firma"))

    def test_ilerleme_satiri(self):
        self.app._satir("[13/93] BIRLIK TIC  | tahmini kalan: 2 sa 10 dk")
        self.assertIn("BIRLIK TIC", self.app.ilerleme_etiketi.cget("text"))
        self.assertIn("13 / 93", self.app.ilerleme_etiketi.cget("text"))
        self.assertEqual(self.app.kalan_etiketi.cget("text"), "Tahmini kalan: 2 sa 10 dk")
        self.assertAlmostEqual(float(self.app.ilerleme.cget("value")), 12 * 100 / 93, places=3)

    def test_durdur_sonuclari_kaydederek_durdurur(self):
        self.bot.write_text(SAHTE_BOT.replace('float(sys.argv[-1]) if sys.argv[-1].replace(".", "").isdigit() else 0.2', "30"),
                            encoding="utf-8")
        self.app.calistir()
        self.assertTrue(self._bekle(lambda: "[1/2]" in self.app.log_metni()))
        self.app.durdur()
        self.assertTrue(self._bekle(lambda: self.app.surec is None))
        self.assertIn("Durduruldu. O ana kadarki sonuclar kaydedildi", self.app.log_metni())
        self.assertEqual(self.app.durum_etiketi.cget("text").strip(), "Durduruldu")

    def test_firma_ekran_penceresi_kaydeder(self):
        from lucabot import firma_tablosu
        from lucabot.firma_listesi import firma_listesini_oku
        firma_tablosu.sablon_olustur(self.d / "firmalar.xlsx", ["BIRLIK TICARET", "KAYA INSAAT"])
        fp = self.app.firma_ekran_penceresi()
        self.kok.update()
        self.assertEqual(len(fp.satirlar), 2)
        fp.v_ara.set("kaya")
        self.kok.update()
        self.assertEqual([s["ad"] for s in fp.gorunen()], ["KAYA INSAAT"])
        fp._sutunu_cevir("gib-5000")           # yalnizca gorunen (KAYA) firmada kapanir
        fp.v_ara.set("")
        fp._satiri_cevir(fp.satirlar[0])       # BIRLIK: tum ekranlar kapanir
        fp.satirlar[0]["secim"]["e-arsiv-alis"].set(True)
        fp.satirlar[0]["dev"].set("1.250,50")
        fp.kaydet()
        okunan = firma_listesini_oku(self.d / "firmalar.xlsx")
        self.assertEqual(okunan["KAYA INSAAT"][1], {"gib-5000"})
        self.assertEqual(len(okunan["BIRLIK TICARET"][1]), 9)
        self.assertNotIn("e-arsiv-alis", okunan["BIRLIK TICARET"][1])
        from lucabot.firma_listesi import devreden_kdvleri
        self.assertEqual(devreden_kdvleri(self.d / "firmalar.xlsx"), {"BIRLIK TICARET": 1250.5})
        # kaydedince kutular yenilenir: 1000 - 300 - 1250,50 devreden < 0, odeme cikmaz
        self.assertEqual(self.app.gostergeler["kdv"], [])

    def test_arayuzden_firma_eklenir_ve_silinir(self):
        from lucabot import firma_tablosu
        from lucabot.firma_listesi import devreden_kdvleri, firma_listesini_oku
        firma_tablosu.sablon_olustur(self.d / "firmalar.xlsx", ["BIRLIK TICARET", "KAYA INSAAT"])
        fp = self.app.firma_ekran_penceresi()
        fp.v_yeni.set("  YENI   FIRMA ")
        fp.firma_ekle()
        fp.v_yeni.set("yeni firma")       # ayni firma ikinci kez eklenmez
        uyari = []
        eski = self.mod.messagebox.showinfo
        self.mod.messagebox.showinfo = lambda *a, **k: uyari.append(a)
        eski_soru = self.mod.messagebox.askyesno
        self.mod.messagebox.askyesno = lambda *a, **k: True
        try:
            fp.firma_ekle()
            yeni = fp.satirlar[-1]
            yeni["dev"].set("750")
            yeni["secim"]["turmob-alis"].set(False)
            fp.firma_sil(fp.satirlar[1])  # KAYA
        finally:
            self.mod.messagebox.showinfo = eski
            self.mod.messagebox.askyesno = eski_soru
        self.assertTrue(uyari)
        self.assertEqual(fp.bilgi.cget("text"), "2 firma")
        fp.kaydet()
        okunan = firma_listesini_oku(self.d / "firmalar.xlsx")
        self.assertEqual(set(okunan), {"BIRLIK TICARET", "YENI FIRMA"})
        self.assertEqual(okunan["YENI FIRMA"][1], {"turmob-alis"})
        self.assertEqual(devreden_kdvleri(self.d / "firmalar.xlsx"), {"YENI FIRMA": 750.0})

    def test_liste_yoksa_olusturulur(self):
        self.app.v_liste.set("")
        hedef = self.mod.KOK / "firmalar.xlsx"
        if hedef.exists():
            self.skipTest("program klasorunde gercek firmalar.xlsx var")
        eski = self.mod.messagebox.askyesno
        self.mod.messagebox.askyesno = lambda *a, **k: True
        try:
            fp = self.app.firma_ekran_penceresi()
        finally:
            self.mod.messagebox.askyesno = eski
            self.addCleanup(lambda: hedef.unlink(missing_ok=True))
        # rapor.json'daki firma hazir gelir, sablonun ornek satiri gelmez
        self.assertEqual([s["ad"] for s in fp.satirlar], ["BIRLIK TIC"])
        self.assertEqual(self.app.v_liste.get(), "firmalar.xlsx")
        self.assertEqual(json.loads(self.ayar.read_text(encoding="utf-8"))["firma_listesi"], "firmalar.xlsx")

    def test_liste_excel_olarak_iner(self):
        from openpyxl import load_workbook
        yol = self.d / "liste.xlsx"
        self.mod.liste_excel_yaz(yol, "Alış Tevkifat KDV — firmalar", "01/09/2026-30/09/2026",
                                 ("Firma", "Fatura", "Tevkifat KDV"),
                                 [("A", 2, "1.234,50 TL *"), ("B", 1, "100,00 TL")],
                                 ("Toplam", 3, "1.334,50 TL"), ["not"])
        ws = load_workbook(yol).active
        self.assertEqual(ws["A4"].value, "Firma")
        self.assertEqual(ws["C5"].value, 1234.5)
        self.assertEqual(ws["C7"].value, 1334.5)

    def test_giris_bilgisi_yoksa_calismaz(self):
        self.app.ayarlar["parola"] = ""
        import luca_arayuz
        uyari = []
        eski = luca_arayuz.messagebox.showwarning
        luca_arayuz.messagebox.showwarning = lambda *a, **k: uyari.append(a)
        try:
            self.app.calistir()
        finally:
            luca_arayuz.messagebox.showwarning = eski
        self.assertIsNone(self.app.surec)
        self.assertTrue(uyari)


if __name__ == "__main__":
    unittest.main()
