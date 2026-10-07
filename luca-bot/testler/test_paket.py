# -*- coding: utf-8 -*-
"""Kurulum paketi (setup/derle.py) icerigi: ne girer, ne girmez, NSIS dosya listeleri."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

DEPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(DEPO / "setup"))
sys.path.insert(0, str(DEPO / "luca-bot"))
import derle  # noqa: E402


class PaketTest(unittest.TestCase):
    def test_pakete_girenler_ve_girmeyenler(self):
        dosyalar = {p.as_posix() for p in derle.izlenen_dosyalar()}
        for gerekli in ("luca-bot/luca_arayuz.py", "luca-bot/luca_bot.py", "luca-bot/lucabot/lisans.py",
                        "luca-bot/varliklar/logo.ico", "luca-bot/requirements.txt", "luca-bot/kurulum_sihirbazi.py",
                        "kar-zarar/kar_zarar.py", "kar-zarar/karzarar/hesaplama.py"):
            self.assertIn(gerekli, dosyalar)
        for istenmeyen in dosyalar:
            self.assertNotIn("/testler/", "/" + istenmeyen)
            self.assertNotIn("__pycache__", istenmeyen)
            self.assertNotIn(Path(istenmeyen).name, derle.HARIC_AD)
        self.assertNotIn("luca-bot/lisans_araci.py", dosyalar)  # lisans uretme araci musteriye gitmez
        self.assertFalse(any(p.endswith("ayarlar.json") for p in dosyalar))  # parolalar pakete girmesin

    def test_nsis_listeleri(self):
        gecici = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, gecici, True)
        sahne = gecici / "sahne"
        dosyalar = derle.sahne_kur(sahne)
        derle.nsh_yaz(sahne, dosyalar, gecici)
        kur = (gecici / "dosyalar.nsh").read_text(encoding="utf-8-sig")
        sil = (gecici / "silme.nsh").read_text(encoding="utf-8-sig")
        self.assertIn('SetOutPath "$INSTDIR\\luca-bot\\lucabot"', kur)
        self.assertIn('Delete "$INSTDIR\\luca-bot\\lucabot\\lisans.py"', sil)
        self.assertIn('Delete "$INSTDIR\\luca-bot\\BASLARKEN.txt"', sil)
        self.assertIn('RMDir /r "$INSTDIR\\luca-bot\\lucabot\\__pycache__"', sil)
        self.assertEqual(kur.count("File "), len(dosyalar))
        self.assertNotIn("ayarlar.json", sil)  # kaldirirken kullanici verisi silinmez
        self.assertNotIn("indirilenler", sil)

    def test_suresi_dolmus_lisans_paketlenmez(self):
        from lucabot import lisans
        gecici = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, gecici, True)
        sahte = gecici / "lisans.json"
        sahte.write_text(json.dumps(lisans.lisans_olustur(bytes(32), "X", "2020-01-01", "2020-12-31")),
                         encoding="utf-8")
        sys.argv = ["derle", "--lisans", str(sahte), "--cikti", str(gecici / "c")]
        with self.assertRaises(SystemExit) as c:
            derle.main()
        self.assertIn("paketlenemez", str(c.exception))


if __name__ == "__main__":
    unittest.main()
