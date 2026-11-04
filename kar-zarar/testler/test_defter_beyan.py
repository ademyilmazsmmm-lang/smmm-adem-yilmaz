# -*- coding: utf-8 -*-
"""Defter Beyan (2. sinif) kontrol/gonderme testleri.

    python -m unittest testler.test_defter_beyan            # yalniz mantik (tarayici yok)
    xvfb-run -a python testler/test_defter_beyan.py         # + sahte Luca uzerinde uctan uca (LUCA_TEST_CHROMIUM)

Uctan uca bolum sahte Luca'nin 'Defter Beyan Sistemi' sayfasini kullanir; gercek Luca ile birebir olmayabilir.
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

# Kullanicinin Luca'dan yapistirdigi GERCEK gonderme penceresi yazisi
GERCEK_LOG = """Defter Beyan Sistemine gönderim başlıyor.
1. satır için.
Sabit kıymet adı boş olamaz. - 0 (1)
2. satır için.
3. satır için.
4. satır için.
5. satır için.
7. satır için.
8. satır için.
9. satır için.
Tutarı 0.00 olan satır girilemez. (8.1)
11. satır için.
Bu belge türü için zorunlu alan. Alan adı: Vergi Dairesi - 10200102 (9)
12. satır için.
13. satır için.
Tutarı 0.00 olan satır girilemez. (11.1)
15. satır için.
18. satır için.
21. satır için.
Sabit kıymet adı boş olamaz. - 0 (14)
22. satır için.
Sabit kıymet adı boş olamaz. - 0 (15)
Defter Beyan Sistemine gönderim tamamlandı. (9)"""


class SonucMantigi(unittest.TestCase):
    def test_gercek_log_kismi_ve_satir_hatalari(self):
        from karzarar import db_sonuc as d
        a = d.gonderim_ayrintisi(GERCEK_LOG)
        self.assertEqual(a["gonderilen"], 9)
        self.assertEqual([h["satir"] for h in a["hatalar"]], [1, 9, 11, 13, 21, 22])
        self.assertEqual(a["hatalar"][1]["mesaj"], "Tutarı 0.00 olan satır girilemez.")
        self.assertEqual(d.gonderim_sinifla(GERCEK_LOG), d.KISMI)
        self.assertEqual(d.hata_ozeti(a["hatalar"]),
                         {"Sabit kıymet adı boş olamaz.": 3, "Tutarı 0.00 olan satır girilemez.": 2,
                          "Bu belge türü için zorunlu alan. Alan adı: Vergi Dairesi": 1})

    def test_pencere_basligi_ve_dugmesi_hata_sayilmaz(self):
        from karzarar import db_sonuc as d
        pencere = "DEFTER BEYAN ENTEGRASYON\n" + GERCEK_LOG + "\n\nTamam"
        a = d.gonderim_ayrintisi(pencere)
        self.assertEqual(len(a["hatalar"]), 6)
        self.assertEqual(d.gonderim_sinifla("DEFTER BEYAN ENTEGRASYON\nDefter Beyan Sistemine gönderim başlıyor.\n"
                                            "1. satır için.\nDefter Beyan Sistemine gönderim tamamlandı. (1)\n\nTamam"),
                         d.BASARILI)

    def test_siniflar(self):
        from karzarar import db_sonuc as d
        self.assertEqual(d.gonderim_sinifla("Defter Beyan Sistemine gönderim başlıyor.\n1. satır için.\n"
                                            "Defter Beyan Sistemine gönderim tamamlandı. (1)"), d.BASARILI)
        self.assertEqual(d.gonderim_sinifla("Defter Beyan Sistemine gönderim başlıyor.\n"
                                            "Gönderilecek seçili kayıt bulunamadı."), d.KAYIT_YOK)
        self.assertEqual(d.gonderim_sinifla("Defter Beyan Sistemine gönderim başlıyor.\n1. satır için.\n"
                                            "Tutarı 0.00 olan satır girilemez. (1.1)\n"
                                            "Defter Beyan Sistemine gönderim tamamlandı. (0)"), d.HATA)
        self.assertEqual(d.gonderim_sinifla(""), d.BELIRSIZ)
        self.assertEqual(d.gonderim_sinifla("Defter Beyan Sistemine gönderim başlıyor."), d.BELIRSIZ)

    def test_tutar_ve_ozet(self):
        from karzarar import db_sonuc as d
        self.assertEqual(d.tutar_oku("1.234,56"), 1234.56)
        self.assertEqual(d.tutar_oku("₺ 2.500"), 2500.0)
        self.assertIsNone(d.tutar_oku(""))
        bas = ["#", "Evrak No", "Evrak Tarihi", "Kategori", "Belge Türü", "Fiş Açıklama", "KDV Tutarı", "Tutar"]
        adet, toplam, kayit, sabit = d.kayitlari_ozetle(bas, [
            ["1", "A1", "03/10/2026", "Satışlar", "Fatura", "x", "10,00", "100,00"],
            ["2", "A2", "04/10/2026", "Sabit Kıymet", "Amortisman", "y", "5,00", "50,50"]])
        self.assertEqual((adet, toplam, kayit[0]["evrak_no"], sabit, kayit[1]["sabit_kiymet"]), (2, 150.5, "A1", 1, True))

    def test_firma_durumu_ve_dosya(self):
        from karzarar import db_sonuc as d
        s = d.bos_sonuc("A", "01/10/2026-31/10/2026", "kontrol")
        s["gelir"] = {"gonderilmemis": 0}
        s["gider"] = {"gonderilmemis": 2}
        self.assertEqual(d.firma_durumu(s), "gönderilmemiş var")
        s["gider"] = {"gonderilmemis": 2, "gonderim": {"sonuc": d.KISMI, "kalan": 1, "kalan_sabit": 0, "hatalar": [1]}}
        self.assertEqual(d.firma_durumu(s), "gönderilmemiş var")
        s["gider"]["gonderim"]["kalan_sabit"] = 1          # kalan tek kayit sabit kiymet: es gecilir
        self.assertEqual(d.firma_durumu(s), "yalnız sabit kıymet")
        s["gider"] = {"gonderilmemis": 2, "gonderim": {"sonuc": d.HATA, "kalan": 2, "hatalar": []}}   # API bilgisi bos vb.
        self.assertEqual(d.firma_durumu(s), "hata")
        s["gider"] = {"gonderilmemis": 2, "gonderim": {"sonuc": d.BASARILI, "kalan": 0}}
        self.assertEqual(d.firma_durumu(s), "tamam")
        with tempfile.TemporaryDirectory() as k:
            yol = Path(k) / "db.json"
            d.kaydet(yol, "01/10/2026-31/10/2026", {"A": s})
            d.kaydet(yol, "01/10/2026-31/10/2026", {"B": dict(s, firma="B")})
            self.assertEqual([f["firma"] for f in d.oku(yol)[1]], ["A", "B"])


def calistir(islem, ek=(), ayar_degisiklik=None, tarih="01/10/2026-31/10/2026"):
    """Sahte Luca'yi baslatip defter_beyan.py'yi calistirir; (cikis kodu, sonuc dosyasi, sahte sunucu durumu, cikti)."""
    import sahte_kz
    sahte_kz.sifirla()
    sahte_kz.DB_AYAR.update(ayar_degisiklik or {})
    klasor = Path(tempfile.mkdtemp(prefix="db-test-"))
    sunucu, adres = sahte_kz.baslat()
    ayar = {"giris_adresi": adres, "defterbeyan_adresi": adres, "tarayici": "chromium",
            "tarayici_yolu": os.environ.get("LUCA_TEST_CHROMIUM", ""), "tarayici_sandbox": os.name == "nt",
            "profil_yerel": True}
    (klasor / "ayarlar.json").write_text(json.dumps(ayar), encoding="utf-8")
    ortam = dict(os.environ, LUCA_BOT_AYAR=str(klasor / "ayarlar.json"), LOCALAPPDATA=str(klasor / "yerel"),
                 KARZARAR_CIKTI=str(klasor / "cikti"), PYTHONIOENCODING="utf-8")
    komut = [sys.executable, str(KOK / "defter_beyan.py"), "--tarih", tarih, "--islem", islem,
             "--bitince-kapat", *ek]
    r = subprocess.run(komut, env=ortam, cwd=str(KOK), capture_output=True, text=True, encoding="utf-8")
    sunucu.shutdown()
    try:
        veri = json.loads((klasor / "cikti" / "defter-beyan.json").read_text(encoding="utf-8"))
    except OSError:
        veri = {"firmalar": []}
    calistir.olaylar = list(sahte_kz.DB_OLAYLAR)
    return r.returncode, {f["firma"]: f for f in veri["firmalar"]}, set(sahte_kz.DB_GONDERILDI), r.stdout + r.stderr


@unittest.skipUnless(os.environ.get("LUCA_TEST_CHROMIUM"), "LUCA_TEST_CHROMIUM yok: uctan uca atlandi")
class UctanUca(unittest.TestCase):
    def test_kontrol_hicbir_sey_gondermez(self):
        kod, sonuc, gonderilen, cikti = calistir("kontrol")
        self.assertEqual(kod, 0, cikti[-1500:])
        self.assertEqual(gonderilen, set())
        a = sonuc["ALFA ISLETME"]
        self.assertEqual((a["gelir"]["gonderilmemis"], a["gider"]["gonderilmemis"], a["gider"]["sabit_kiymet"],
                          a["durum"]), (1, 3, 1, "gönderilmemiş var"))
        self.assertEqual(a["gider"]["tutar_gonderilmemis"], 1250.5 + 2250.5 + 3250.5)
        self.assertEqual(sonuc["FATURASIZ AS"]["durum"], "tamam")

    def test_gonder_ve_yenile_ile_kontrol(self):
        kod, sonuc, gonderilen, cikti = calistir("gonder", ["--firma-tam", "ALFA ISLETME"])
        olaylar = calistir.olaylar
        self.assertEqual(kod, 0, cikti[-1500:])
        self.assertEqual(len([g for g in gonderilen if g[0] == "ALFA ISLETME"]), 4)
        a = sonuc["ALFA ISLETME"]
        self.assertEqual((a["durum"], a["gider"]["gonderim"]["kalan"], a["gider"]["gonderim"]["sonuc"]),
                         ("tamam", 0, "basarili"))
        self.assertEqual(olaylar, ["cari", "kaydet", "gburaya", "gonder", "cari", "kaydet", "gburaya", "gonder"])  # gelir, gider

    def test_satir_hatasi_listede_kalir(self):
        kod, sonuc, gonderilen, cikti = calistir("gonder", ["--firma-tam", "ALFA ISLETME"], {"satir_hatasi": True})
        self.assertEqual(kod, 0, cikti[-1500:])
        g = sonuc["ALFA ISLETME"]["gider"]["gonderim"]
        self.assertEqual((g["sonuc"], g["gonderilen"], g["kalan"]), ("kismi", 2, 1))
        self.assertEqual(g["hata_ozeti"], {"Tutarı 0.00 olan satır girilemez.": 1})
        self.assertEqual(len(g["kalan_kayitlar"]), 1)
        self.assertEqual(sonuc["ALFA ISLETME"]["durum"], "gönderilmemiş var")

    def test_kalan_yalniz_sabit_kiymet_ise_es_gecilir(self):
        kod, sonuc, gonderilen, cikti = calistir("gonder", ["--firma-tam", "ALFA ISLETME"], {"sabit_hatasi": True})
        self.assertEqual(kod, 0, cikti[-1500:])
        g = sonuc["ALFA ISLETME"]["gider"]["gonderim"]
        self.assertEqual((g["kalan"], g["kalan_sabit"], g["sonuc"]), (1, 1, "kismi"))
        self.assertEqual(sonuc["ALFA ISLETME"]["durum"], "yalnız sabit kıymet")
        self.assertIn("SABİT KIYMET", cikti)

    def test_jqx_grid_sanal_kaydirma_tum_satirlar(self):
        """Gercek Luca listesi jqx grid: DOM'da yalniz 5 satir var; satirlar grid arayuzunden okunur ve secilir."""
        kod, sonuc, gonderilen, cikti = calistir("gonder", ["--firma-tam", "ALFA ISLETME"], {"jqx": True})
        self.assertEqual(kod, 0, cikti[-1500:])
        a = sonuc["ALFA ISLETME"]
        self.assertEqual((a["gelir"]["gonderilmemis"], a["gider"]["gonderilmemis"], a["gider"]["sabit_kiymet"]), (1, 3, 1))
        self.assertEqual(len([g for g in gonderilen if g[0] == "ALFA ISLETME"]), 4)
        self.assertEqual((a["durum"], a["gider"]["gonderim"]["kalan"]), ("tamam", 0))

    def test_cari_sorgu_yoksa_kaydet_basilmaz(self):
        kod, sonuc, gonderilen, cikti = calistir("gonder", ["--firma-tam", "ALFA ISLETME"], {"cari_yok": True})
        self.assertEqual(kod, 0, cikti[-1500:])
        self.assertEqual(calistir.olaylar, ["cari", "gburaya", "gonder", "cari", "gburaya", "gonder"])    # sorgulanacak yok: Kaydet basilmaz
        self.assertEqual(sonuc["ALFA ISLETME"]["durum"], "tamam")

    def test_bozulan_tarih_kutusu_duzeltilir(self):
        """Tarih bileseni slash'li degeri 2002'ye bozuyorsa yalniz rakamla yazilir; aralik dogru uygulanir."""
        kod, sonuc, gonderilen, cikti = calistir("kontrol", ["--firma-tam", "ALFA ISLETME"], {"tarih_bozuk": True})
        self.assertEqual(kod, 0, cikti[-1500:])
        a = sonuc["ALFA ISLETME"]
        self.assertEqual((a["gelir"]["gonderilmemis"], a["gider"]["gonderilmemis"]), (1, 3))

    def test_tarih_filtresi_uygulanmazsa_durur(self):
        """Liste aralik disi kayit getirirse (tarih kutusu bozuk) gonderilmez."""
        kod, sonuc, gonderilen, cikti = calistir("gonder", ["--firma-tam", "ALFA ISLETME"], {"filtre_yok": True},
                                                 tarih="01/10/2026-10/10/2026")
        self.assertEqual(gonderilen, set(), cikti[-1500:])
        self.assertIn("dışında kayıt", cikti)
        self.assertEqual(sonuc["ALFA ISLETME"]["durum"], "hata")

    def test_gonder_penceresinde_buraya_ile_secilir(self):
        """Kendi secimimiz Luca'da tutmasa bile (selectallrows etkisiz) 'buraya' ile tum gonderilmemisler gider."""
        kod, sonuc, gonderilen, cikti = calistir("gonder", ["--firma-tam", "ALFA ISLETME"], {"jqx": True, "secim_calismaz": True})
        self.assertEqual(kod, 0, cikti[-1500:])
        self.assertEqual(len([g for g in gonderilen if g[0] == "ALFA ISLETME"]), 4)
        self.assertIn("gburaya", calistir.olaylar)
        self.assertEqual(sonuc["ALFA ISLETME"]["durum"], "tamam")

    def test_api_bilgisi_bos_ise_gonderilmez(self):
        kod, sonuc, gonderilen, cikti = calistir("gonder", ["--firma-tam", "ALFA ISLETME"], {"api_bos": True})
        self.assertEqual(gonderilen, set(), cikti[-1500:])
        self.assertEqual(sonuc["ALFA ISLETME"]["gelir"]["gonderim"]["sonuc"], "hata")


if __name__ == "__main__":
    unittest.main(verbosity=2)
