# -*- coding: utf-8 -*-
"""Fatura Indirme: ofis + isletme (ikinci Luca hesabi) sirayla taranir; her hesap kendi giris bilgisi ve tarayici profiliyle.

Sahte Luca'nin giris formu yok: luca_oturumu_ac sarmalanir (hangi hesabin bilgisiyle cagrildigi kaydedilir), giris sahte Luca'nin
urun sayfasindan kendiliginden yapilir. Ekran gerekir (Linux'ta: xvfb-run -a python -m unittest testler.test_iki_hesap).
"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sahte_luca  # noqa: E402


def _calistir(klasor, adres, ayar_ek, argumanlar):
    """luca_bot.main()'i bu surecte calistirir; (cikis kodu, stdout, giris cagrilari [(kullanici, parola)])."""
    import luca_bot
    from lucabot import ortak
    ayar = {"giris_adresi": adres, "tarayici": "chromium", "tarayici_yolu": os.environ.get("LUCA_TEST_CHROMIUM", ""),
            "tarayici_sandbox": os.name == "nt", "indirme_klasoru": str(klasor / "indirilenler"), "profil_yerel": True,
            "sorgu_azami_dakika": 2, "durgunluk_dakika": 1, "indirme_bekleme_saniye": 15, "azami_fatura": 0,
            "mail_gonder": False, "otomatik_tekrar": False}
    ayar.update(ayar_ek)
    (klasor / "ayarlar.json").write_text(json.dumps(ayar), encoding="utf-8")
    cagrilar = []
    asil = luca_bot.luca_oturumu_ac

    def sarmal(ctx, page, ayarlar, gece_modu, tani, log):
        cagrilar.append((ayarlar.get("kullanici_adi"), ayarlar.get("parola"), ayarlar.get("hesap_adi")))
        bilgisiz = {k: v for k, v in ayarlar.items() if k not in ("uye_no", "kullanici_adi", "parola", "dogrulama_anahtari")}
        return asil(ctx, page, bilgisiz, gece_modu, tani, log)   # sahte Luca'da elle giris yolu: urun kutusuna tiklanir

    ortam = {"LUCA_BOT_AYAR": str(klasor / "ayarlar.json"), "LOCALAPPDATA": str(klasor / "yerel"), "LUCA_TEST_LISANS_ATLA": "1"}
    eski = {k: os.environ.get(k) for k in ortam}
    os.environ.update(ortam)
    luca_bot.luca_oturumu_ac = sarmal
    eski_argv = sys.argv
    sys.argv = ["luca_bot.py", "--eski-ekranlar", "--baslangic", "01/08/2026", "--bitis", "10/08/2026", "--bitince-kapat", "--belge-tipi", "e-arsiv-alis",
                *argumanlar]
    cikti = io.StringIO()
    try:
        with redirect_stdout(cikti):
            kod = luca_bot.main()
    finally:
        sys.argv = eski_argv
        luca_bot.luca_oturumu_ac = asil
        for k, v in eski.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    return kod, cikti.getvalue(), cagrilar


IKI = {"uye_no": "1", "kullanici_adi": "ofis-kul", "parola": "p1",
       "ikinci_hesap": {"etkin": True, "ad": "isletme", "uye_no": "2", "kullanici_adi": "isl-kul", "parola": "p2"}}


class IkiHesap(unittest.TestCase):
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
        self.klasor = Path(tempfile.mkdtemp(prefix="iki-hesap-"))

    def test_hepsi_once_ofis_sonra_isletme_taranir(self):
        kod, cikti, cagrilar = _calistir(self.klasor, self.adres, IKI, ["--firma", "AKIN", "--bastan"])
        self.assertEqual(kod, 0, cikti[-1500:])
        self.assertEqual(cagrilar, [("ofis-kul", "p1", "ofis"), ("isl-kul", "p2", "isletme")])
        self.assertIn("LUCA HESABI 1/2: OFIS", cikti)
        self.assertIn("LUCA HESABI 2/2: ISLETME", cikti)
        self.assertEqual(cikti.count("Islenecek firma sayisi"), 2)
        profiller = {p.name for p in (self.klasor / "yerel" / "luca-bot").iterdir()}     # tarayici kanali eki (-chromium) olabilir
        self.assertTrue(any(p.startswith("tarayici-profili") and "hesap2" not in p for p in profiller), profiller)   # ofis: eski profil
        self.assertTrue(any(p.startswith("tarayici-profili-hesap2") for p in profiller), profiller)                 # isletme: ayri profil
        self.assertIn("birlesik ozet", cikti)
        rapor = json.loads((self.klasor / "indirilenler" / "rapor.json").read_text(encoding="utf-8"))
        self.assertEqual(list(rapor), ["AKIN COBAN"])                                                     # firma adina gore birlesik rapor
        self.assertEqual(rapor["AKIN COBAN"]["durumlar"], {"e-arsiv-alis": "tamam"})

    def test_ic_ice_menu_gib_e_belge_grubu(self):
        """Luca (Kasim 2026) maddeleri alt gruplara tasidi: Akıllı Entegrasyon Noktası > GİB e-Belge > e-Arşiv Alış Faturaları."""
        sahte_luca.SAYAC["ara_menu"] = True
        kod, cikti, cagrilar = _calistir(self.klasor, self.adres, {}, ["--firma", "AKIN", "--bastan"])
        self.assertEqual(kod, 0, cikti[-1500:])
        rapor = json.loads((self.klasor / "indirilenler" / "rapor.json").read_text(encoding="utf-8"))
        self.assertEqual(rapor["AKIN COBAN"]["durumlar"], {"e-arsiv-alis": "tamam"}, cikti[-1200:])

    def test_yalniz_isletme(self):
        kod, cikti, cagrilar = _calistir(self.klasor, self.adres, IKI, ["--firma", "AKIN", "--hesap", "isletme"])
        self.assertEqual(kod, 0, cikti[-1500:])
        self.assertEqual(cagrilar, [("isl-kul", "p2", "isletme")])
        self.assertNotIn("LUCA HESABI", cikti)          # tek hesap: eski cikti bicimi

    def test_ikinci_hesap_kapaliysa_yalniz_ofis_ve_isletme_istenirse_hata(self):
        kapali = dict(IKI, ikinci_hesap=dict(IKI["ikinci_hesap"], etkin=False))
        kod, cikti, cagrilar = _calistir(self.klasor, self.adres, kapali, ["--firma", "AKIN"])
        self.assertEqual((kod, [c[0] for c in cagrilar]), (0, ["ofis-kul"]))
        kod, cikti, cagrilar = _calistir(self.klasor, self.adres, kapali, ["--firma", "AKIN", "--hesap", "isletme"])
        self.assertEqual((kod, cagrilar), (1, []))
        self.assertIn("ikinci Luca hesabı kapalı", cikti)

    def test_firma_yalniz_bir_hesapta_olabilir(self):
        """--firma yalniz ofiste bulunuyorsa isletmede 'firma yok' hata sayilmaz; hicbirinde yoksa hata."""
        kod, cikti, cagrilar = _calistir(self.klasor, self.adres, IKI, ["--firma", "YOKFIRMA", "--bastan"])
        self.assertEqual(kod, 1, cikti[-800:])           # ikisinde de eslesme yok: hata
        self.assertEqual(len(cagrilar), 2)


if __name__ == "__main__":
    unittest.main()
