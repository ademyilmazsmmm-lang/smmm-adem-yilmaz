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


# --firma-listesi-cek ile cagrilinca Luca'dan musteri listesi cekmis gibi JSON yazar
SAHTE_LISTE_BOTU = textwrap.dedent('''
    import json, os, sys
    from pathlib import Path
    print("ARGS " + " ".join(sys.argv[1:]), flush=True)
    kok = Path(json.loads(Path(os.environ["LUCA_BOT_AYAR"]).read_text(encoding="utf-8"))["indirme_klasoru"])
    firmalar = [
        {"ad": "BIRLIK TICARET", "unvan": "BIRLIK TİCARET", "vkn": "1", "acilis": "01/01/2020", "kapanis": "31/03/2026"},
        {"ad": "YENI FIRMA LTD", "unvan": "YENİ FİRMA", "vkn": "2", "acilis": "01/06/2026", "kapanis": ""},
    ]
    (kok / "luca-musteri-listesi.json").write_text(
        json.dumps({"yil": 2026, "alinma": "x", "firmalar": firmalar}), encoding="utf-8")
    print("[OK] 2026 yilinda 2 firma okundu", flush=True)
''')


# --beyanname-cek ile cagrilinca PDF'leri indirmis gibi dosya + JSON yazar
SAHTE_BEYANNAME_BOTU = textwrap.dedent('''
    import json, os, sys
    from pathlib import Path
    print("ARGS " + " ".join(sys.argv[1:]), flush=True)
    kok = Path(json.loads(Path(os.environ["LUCA_BOT_AYAR"]).read_text(encoding="utf-8"))["indirme_klasoru"])
    (kok / "beyannameler").mkdir()
    yollar = []
    for ad in ("CAGRI DENE_1_KDV1_2026-08_1.pdf", "BIRLIK TICARET_2_KDV1_2026-08_1.pdf"):
        (kok / "beyannameler" / ad).write_bytes(b"%PDF-1.4")
        yollar.append(str(kok / "beyannameler" / ad))
    (kok / "luca-beyannameler.json").write_text(json.dumps({"dosyalar": yollar + [str(kok / "yok.pdf")]}))
    print("[OK] 2 beyanname PDF'i alindi", flush=True)
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
        from lucabot.ortak import DURDUR_DOSYASI
        try:
            DURDUR_DOSYASI.unlink()  # sahte bot dosyayi tuketmez
        except OSError:
            pass
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

    def test_su_an_gostergesi(self):
        self.app.surec = object()  # calisiyor gibi
        try:
            self.app._satir("    GİB'den Getir aciliyor (01/09/2026 - 07/09/2026)")
            self.app._satir("================")  # ayirici cizgiler "su an" yazisi olmaz
            metin, an = self.app.son_islem
            self.assertIn("GİB'den Getir aciliyor", metin)
            self.app.son_islem = (metin, an - self.mod.UZUN_BEKLEME * 3)
            self.app._son_islemi_goster()
            yazi = self.app.son_islem_etiketi.cget("text")
            self.assertTrue(yazi.startswith("Şu an: GİB'den Getir aciliyor"), yazi)
            self.assertEqual(self.app.son_islem_etiketi.cget("fg"), self.mod.KIRMIZI)
        finally:
            self.app.surec = None
        self.app._son_islemi_goster()
        self.assertEqual(self.app.son_islem_etiketi.cget("text"), "")

    def test_durdur_sonuclari_kaydederek_durdurur(self):
        self.bot.write_text(SAHTE_BOT.replace('float(sys.argv[-1]) if sys.argv[-1].replace(".", "").isdigit() else 0.2', "30"),
                            encoding="utf-8")
        self.app.calistir()
        self.assertTrue(self._bekle(lambda: "[1/2]" in self.app.log_metni()))
        self.app.durdur()
        self.assertTrue(self._bekle(lambda: self.app.surec is None))
        self.assertIn("Durduruldu. O ana kadarki sonuclar kaydedildi", self.app.log_metni())
        self.assertEqual(self.app.durum_etiketi.cget("text").strip(), "Durduruldu")

    def test_durdur_dosyasi_yazilir_ve_eskisi_silinir(self):
        from lucabot.ortak import DURDUR_DOSYASI
        self.addCleanup(lambda: DURDUR_DOSYASI.exists() and DURDUR_DOSYASI.unlink())
        DURDUR_DOSYASI.write_text("kalinti")  # onceki calismadan kalmis istek
        self.bot.write_text(SAHTE_BOT.replace('float(sys.argv[-1]) if sys.argv[-1].replace(".", "").isdigit() else 0.2', "30"),
                            encoding="utf-8")
        self.app.calistir()
        self.assertFalse(DURDUR_DOSYASI.exists())  # yeni calisma kalintiyla durmasin
        self.assertTrue(self._bekle(lambda: "[1/2]" in self.app.log_metni()))
        self.app.durdur()
        self.assertTrue(DURDUR_DOSYASI.exists())   # bot bunu gorup duracak
        self.assertTrue(self._bekle(lambda: self.app.surec is None))

    def test_konsolsuz_yeniden_baslatma(self):
        """Konsollu python.exe ile acilan arayuz pythonw ile yeniden baslar (arkada siyah pencere kalmaz)."""
        import types
        from unittest import mock
        self.assertFalse(self.mod.konsolsuz_yeniden_baslat())  # Windows disi: dokunmaz
        d = Path(tempfile.mkdtemp())
        (d / "python.exe").write_text("")
        (d / "pythonw.exe").write_text("")

        def dene(konsol, calisti=True, exe="python.exe"):
            sahte_ctypes = types.SimpleNamespace(windll=types.SimpleNamespace(
                kernel32=types.SimpleNamespace(GetConsoleWindow=lambda: konsol)))
            with mock.patch.dict(sys.modules, {"ctypes": sahte_ctypes}), \
                    mock.patch.object(sys, "platform", "win32"), \
                    mock.patch.object(sys, "executable", str(d / exe)), \
                    mock.patch("subprocess.Popen") as popen, mock.patch("time.sleep"):
                popen.return_value.poll.return_value = None if calisti else 1
                sonuc = self.mod.konsolsuz_yeniden_baslat()
                return sonuc, popen
        sonuc, popen = dene(konsol=123)
        self.assertTrue(sonuc)
        self.assertTrue(popen.call_args[0][0][0].endswith("pythonw.exe"))
        self.assertFalse(dene(konsol=0)[0])                    # zaten konsolsuz: yeniden baslatmaz
        self.assertFalse(dene(konsol=123, calisti=False)[0])   # yeni surec dustuyse bu surecte acilir
        self.assertFalse(dene(konsol=123, exe="pythonw.exe")[0])
        (d / "pythonw.exe").unlink()
        self.assertFalse(dene(konsol=123)[0])                  # pythonw yoksa eski yontem

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

    def test_luca_dan_firma_listesi_cekilir_ve_uygulanir(self):
        from lucabot import firma_tablosu, musteri_listesi
        from lucabot.firma_listesi import firma_listesini_oku
        from tkinter import messagebox
        from datetime import date
        firma_tablosu.sablon_olustur(self.d / "firmalar.xlsx", ["BIRLIK TICARET"])
        self.bot.write_text(SAHTE_LISTE_BOTU, encoding="utf-8")
        sorular = []
        eski, messagebox.askyesno = messagebox.askyesno, lambda *a, **k: sorular.append(a) or True
        try:
            self.app.firma_listesi_cek()
        finally:
            messagebox.askyesno = eski
        self.assertIn("2026", sorular[0][1])
        self.assertEqual(str(self.app.luca_liste_dugmesi.cget("state")), "disabled")
        self.assertTrue(self._bekle(lambda: self.app.surec is None))
        self.assertIn("--firma-listesi-cek --yil 2026", self.app.log_metni())
        self.assertEqual(str(self.app.luca_liste_dugmesi.cget("state")), "normal")
        pencere = self.app.luca_penceresi
        self.assertIsNotNone(pencere)
        self.kok.update()
        self.assertEqual(len(pencere.plan["yeni"]), 1)
        self.assertEqual(len(pencere.agac.get_children()), 2)   # yeni + guncellenecek
        pencere.uygula()
        okunan = firma_listesini_oku(self.d / "firmalar.xlsx")
        self.assertEqual(okunan["BIRLIK TICARET"][0], date(2026, 3, 31))
        self.assertIn("YENI FIRMA LTD", okunan)
        self.assertEqual(self.app.mod, "calisma")

    def test_luca_dan_devir_cekilir_ve_beyannameden_alinir(self):
        from lucabot import firma_tablosu
        from tkinter import messagebox
        firma_tablosu.sablon_olustur(self.d / "firmalar.xlsx", ["BIRLIK TICARET", "CAGRI DENE"])
        self.bot.write_text(SAHTE_BEYANNAME_BOTU, encoding="utf-8")
        fp = self.app.firma_ekran_penceresi()
        alinan = []
        fp.beyannameden_al = lambda yollar=None: alinan.append([Path(y).name for y in yollar])
        eski, messagebox.askyesno = messagebox.askyesno, lambda *a, **k: True
        try:
            self.app.beyanname_cek(fp)
        finally:
            messagebox.askyesno = eski
        self.assertTrue(self._bekle(lambda: self.app.surec is None))
        self.assertIn("--beyanname-cek", self.app.log_metni())
        # yalniz var olan dosyalar iletilir
        self.assertEqual(alinan, [["CAGRI DENE_1_KDV1_2026-08_1.pdf", "BIRLIK TICARET_2_KDV1_2026-08_1.pdf"]])
        self.assertEqual(self.app.mod, "calisma")
        fp.w.destroy()

    @staticmethod
    def _agac(pencere):
        """Pencerenin icindeki ilk Treeview (ic ice cercevelerde aranir)."""
        from tkinter import ttk
        bekleyen = [pencere]
        while bekleyen:
            w = bekleyen.pop(0)
            if isinstance(w, ttk.Treeview):
                return w
            bekleyen += w.winfo_children()

    def _rapora_yaz(self, kayitlar):
        (self.d / "indir" / "rapor.json").write_text(json.dumps(kayitlar), encoding="utf-8")
        self.app.gostergeleri_yenile()

    def test_fark_penceresi_eksik_faturalari_gosterir(self):
        donem = "01/09/2026-30/09/2026"
        self._rapora_yaz({"ALEV SEZEN": {
            "donem": donem, "sayilar": {"e-arsiv-alis": 2, "e-arsiv-interaktif": 3},
            "faturalar": {
                "e-arsiv-alis": [["TURKCELL", "AAA2026000000001", 100.0], ["SHELL", "AAA2026000000002", 50.0]],
                "e-arsiv-interaktif": [["TURKCELL", "AAA2026000000001", 100.0], ["SHELL", "AAA2026000000002", 50.0],
                                       ["VODAFONE", "AAA2026000000007", 1200.5]]}}})
        w = self.app.detay("fark")
        self.kok.update()
        agac = self._agac(w)
        satirlar = [agac.item(i, "values") for i in agac.get_children()]
        self.assertEqual(satirlar[0][0], "ALEV SEZEN")
        self.assertIn("VODAFONE", satirlar[1][0])
        self.assertIn("AAA..007", satirlar[1][0])
        self.assertIn("1.200,50 TL", satirlar[1][0])
        self.assertIn("eksik", satirlar[1][3])
        # sutunlar sigacak genislikte (sayi sutunu kesilmesin)
        self.assertGreaterEqual(int(agac.column("İnteraktif", "width")), 90)
        w.destroy()

    def test_hata_kutusu_ve_tekrar_sorgula(self):
        from tkinter import messagebox
        donem = "01/09/2026-30/09/2026"
        self._rapora_yaz({
            "ALEV SEZEN": {"donem": donem, "durumlar": {"e-arsiv-alis": "tamam"}, "inmeyen": {"e-arsiv-alis": 2}},
            "METIN BALT": {"donem": donem, "durumlar": {"e-arsiv-satis": "hata: LookupError",
                                                       "gib-5000": "tamam"}}})
        self.assertIn("2 ekran", self.app.kutu["hata"].deger.cget("text"))
        w = self.app.detay("hata")
        self.kok.update()
        eski, messagebox.askyesno = messagebox.askyesno, lambda *a, **k: True
        try:
            self.app.tekrar_sorgula(self.app.gostergeler["hata"], w)
        finally:
            messagebox.askyesno = eski
        self.assertTrue(self._bekle(lambda: self.app.surec is None))
        istek = json.loads((self.d / "indir" / "tekrar-listesi.json").read_text(encoding="utf-8"))
        self.assertEqual(istek, {"ALEV SEZEN": ["e-arsiv-alis"], "METIN BALT": ["e-arsiv-satis"]})
        log = self.app.log_metni()
        self.assertIn("--tekrar-listesi", log)
        self.assertIn("--baslangic 01/09/2026 --bitis 30/09/2026", log)
        self.assertNotIn("--belge-tipi", log)

    def test_luca_listesi_cekilemezse_hata_gosterilir(self):
        from tkinter import messagebox
        self.bot.write_text("import sys\nprint('HATA: Filtre penceresi kullanilamadi')\nsys.exit(1)\n",
                            encoding="utf-8")
        eski, messagebox.askyesno = messagebox.askyesno, lambda *a, **k: True
        try:
            self.app.firma_listesi_cek()
        finally:
            messagebox.askyesno = eski
        self.assertTrue(self._bekle(lambda: self.app.surec is None))
        self.assertIsNone(self.app.luca_penceresi)
        self.assertIn("alınamadı", self.app.ilerleme_etiketi.cget("text"))

    def test_beyannameden_devir_alinir(self):
        from lucabot import beyanname, firma_tablosu
        from lucabot.firma_listesi import devreden_kdvleri
        from testler.test_birim import ORNEK_BEYANNAME
        firma_tablosu.sablon_olustur(self.d / "firmalar.xlsx", ["BIRLIK TICARET", "CAGRI DENE"])
        fp = self.app.firma_ekran_penceresi()

        def sahte_oku(yol):
            if "bozuk" in yol:
                raise beyanname.BeyannameDegil("KDV1 beyannamesi değil")
            return beyanname.cozumle(ORNEK_BEYANNAME, yol)

        eski, beyanname.oku = beyanname.oku, sahte_oku
        try:
            once = len(self.kok.winfo_children())
            sonuc = fp.beyannameden_al(["CAGRI_DENE_1_KDV1_01082026-31082026.pdf", "bozuk.pdf"])
        finally:
            beyanname.oku = eski
        self.kok.update()
        self.assertEqual(len(self.kok.winfo_children()), once + 1)  # sonuc penceresi
        self.assertEqual(fp.satirlar[1]["dev"].get(), "34.027,69")   # eylul: agustosun sonraki devri
        self.assertEqual(fp.satirlar[0]["dev"].get(), "")
        self.assertEqual([r[2] for r in sonuc], ["Yazıldı", "Okunamadı"])
        fp.kaydet()
        self.assertEqual(devreden_kdvleri(self.d / "firmalar.xlsx")["CAGRI DENE"], 34027.69)

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
