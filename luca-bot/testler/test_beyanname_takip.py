# -*- coding: utf-8 -*-
"""Beyanname Takip sekmesi (beyanname_takip_sekmesi.py) testleri.

Saf yardimcilar ekransiz sinanir; sekmenin kendisi icin ekran gerekir (Linux'ta: xvfb-run -a python -m unittest
testler.test_beyanname_takip). Gercek beyanname-takip programi yerine, ayni sozlesmeyi (PORT, /saglik, kontrol.json,
/api/kapat-kontrol) uygulayan kucuk bir sahte baslat.py calisir.
"""

import json
import os
import socket
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

import beyanname_takip_sekmesi as bt  # noqa: E402
from testler.test_arayuz import TK_VAR, ArayuzZemini  # noqa: E402

SAHTE_BASLAT = textwrap.dedent('''
    import json, os, re, sys, threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from pathlib import Path
    KLASOR = Path(__file__).resolve().parent
    PORT = int(re.search(r"PORT=(\\d+)", (KLASOR / "ayarlar.env").read_text()).group(1))
    ANAHTAR = "test-anahtar"
    print("LUCABOT_YOLU=" + os.environ.get("LUCABOT_YOLU", ""), "TARAYICI=" + os.environ.get("BEYANNAME_TARAYICI", ""), flush=True)

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b'{"ok": true}')
        def do_POST(self):
            if self.headers.get("X-Kontrol-Token") == ANAHTAR:
                self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
                threading.Timer(0.2, lambda: os._exit(0)).start()
            else:
                self.send_response(403); self.end_headers()
        def log_message(self, *a):
            pass
    (KLASOR / "kontrol.json").write_text(json.dumps({"port": PORT, "anahtar": ANAHTAR}))
    HTTPServer(("127.0.0.1", PORT), H).serve_forever()
''')


def bos_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def sahte_klasor(port=None):
    d = Path(tempfile.mkdtemp(prefix="bt-test-"))
    (d / "baslat.py").write_text(SAHTE_BASLAT, encoding="utf-8")
    (d / "ayarlar.ornek.env").write_text(f"WEB_SIFRE=\nPORT={port or bos_port()}\n", encoding="utf-8")
    (d / "requirements.txt").write_text("fastapi\nuvicorn\n", encoding="utf-8")
    return d


class SafYardimcilar(unittest.TestCase):
    def test_port_oku(self):
        d = Path(tempfile.mkdtemp())
        self.assertEqual(bt.port_oku(d), bt.VARSAYILAN_PORT)                          # dosya yok
        (d / "ayarlar.env").write_text("A=1\n PORT = 9123 \nB=2\n", encoding="utf-8")
        self.assertEqual(bt.port_oku(d), 9123)
        for kotu in ("PORT=80", "PORT=99999", "PORT=abc", "# PORT=9000"):              # ayricalikli portlar, sinir disi, bozuk, yorum
            (d / "ayarlar.env").write_text(kotu + "\n", encoding="utf-8")
            self.assertEqual(bt.port_oku(d), bt.VARSAYILAN_PORT, kotu)

    def test_port_acik_mi(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        self.assertTrue(bt.port_acik_mi(port))
        s.close()
        self.assertFalse(bt.port_acik_mi(port))

    def test_ayar_olustur_sablondan_kopyalar_ve_ezmez(self):
        d = sahte_klasor(9555)
        yol, yeni = bt.ayar_olustur(d)
        self.assertTrue(yeni)
        self.assertIn("PORT=9555", yol.read_text(encoding="utf-8"))
        yol.write_text("WEB_SIFRE=benimsifrem\n", encoding="utf-8")
        yol2, yeni2 = bt.ayar_olustur(d)
        self.assertFalse(yeni2)                                                       # var olan ayara dokunulmaz
        self.assertEqual(yol2.read_text(encoding="utf-8"), "WEB_SIFRE=benimsifrem\n")

    def test_kapat_istegi_yalniz_dogru_anahtarla(self):
        durum = {"anahtar": None}

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                durum["anahtar"] = self.headers.get("X-Kontrol-Token")
                self.send_response(200 if durum["anahtar"] == "dogru" else 403)
                self.end_headers()

            def log_message(self, *a):
                pass
        sunucu = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=sunucu.serve_forever, daemon=True).start()
        self.addCleanup(sunucu.shutdown)
        d = Path(tempfile.mkdtemp())
        (d / "kontrol.json").write_text(json.dumps({"port": sunucu.server_address[1], "anahtar": "dogru"}), encoding="ascii")
        ok, _ = bt.kapat_istegi(d)
        self.assertTrue(ok)
        self.assertEqual(durum["anahtar"], "dogru")
        (d / "kontrol.json").write_text(json.dumps({"port": sunucu.server_address[1], "anahtar": "yanlis"}), encoding="ascii")
        self.assertFalse(bt.kapat_istegi(d)[0])                                       # 403
        (d / "kontrol.json").unlink()
        ok, mesaj = bt.kapat_istegi(d)                                                # dosya yok: program bu sekmeden baslamamis
        self.assertFalse(ok)
        self.assertIn("Sistem", mesaj)

    def test_calistir_pencere_acmaz_ve_lucabotu_bu_programdan_alir(self):
        d = sahte_klasor()
        with mock.patch.object(bt.subprocess, "Popen") as popen:
            bt.calistir(d)
        args, kw = popen.call_args
        self.assertEqual(args[0][1], str(d / "baslat.py"))
        self.assertEqual(kw["cwd"], str(d))
        self.assertEqual(kw["env"]["LUCABOT_YOLU"], str(bt.KOK))                      # Dijital Stajyer'in lucabot'u
        self.assertEqual(kw["env"]["BEYANNAME_TARAYICI"], "0")                        # tarayiciyi sekme acar
        self.assertEqual(kw["stdin"], bt.subprocess.DEVNULL)
        self.assertEqual(Path(kw["cwd"], "program.log").exists(), True)

    def test_klasor_bul_ve_log_sonu(self):
        d = sahte_klasor()
        with mock.patch.object(bt, "ADAYLAR", (Path(tempfile.mkdtemp()), d)):
            self.assertEqual(bt.klasor_bul(), d)
        with mock.patch.object(bt, "ADAYLAR", (Path(tempfile.mkdtemp()),)):
            self.assertIsNone(bt.klasor_bul())
        (d / "program.log").write_text("\n".join(f"satir {i}" for i in range(30)), encoding="utf-8")
        self.assertEqual(bt.log_sonu(d, 3), "satir 27\nsatir 28\nsatir 29")
        self.assertEqual(bt.log_sonu(Path(tempfile.mkdtemp())), "")


@unittest.skipUnless(TK_VAR, "tkinter ya da ekran yok")
class BeyannameTakipSekmesiTestleri(ArayuzZemini):
    def setUp(self):
        self.port = bos_port()
        self.klasor = sahte_klasor(self.port)
        self.yamalar = [mock.patch.object(bt, "ADAYLAR", (self.klasor,)), mock.patch.object(bt, "paketler_kurulu_mu", return_value=True),
                        mock.patch.object(bt.webbrowser, "open")]
        self.tarayici = None
        for i, y in enumerate(self.yamalar):
            m = y.start()
            self.addCleanup(y.stop)
            if i == 2:
                self.tarayici = m
        for ad in ("askyesno", "showinfo", "showerror", "showwarning"):
            y = mock.patch.object(bt.messagebox, ad, return_value=True)
            setattr(self, "mb_" + ad, y.start())
            self.addCleanup(y.stop)
        super().setUp()
        self.bt = self.app.bt

    def tearDown(self):
        self.bt.iptal()
        if self.bt.surec is not None and self.bt.surec.poll() is None:
            self.bt.surec.kill()
            self.bt.surec.wait()
        super().tearDown()

    def _durum(self):
        self.bt.yenile_simdi()
        return self.bt.durum.cget("text")

    def test_sekme_cubukta_ve_secilebilir(self):
        self.assertEqual(self.app.sekme_dugmeleri["bt"].cget("text"), "Beyanname Takip")
        self.app.sekme_sec("bt")
        self.kok.update()
        self.assertTrue(self.bt.govde.winfo_ismapped())
        self.assertFalse(self.app.fatura_govde.winfo_ismapped())
        self.app.sekme_sec("fatura")                                                  # geri donunce diger sekmeler bozulmaz
        self.kok.update()
        self.assertTrue(self.app.fatura_govde.winfo_ismapped())
        self.assertFalse(self.bt.govde.winfo_ismapped())

    def test_klasor_yoksa_aciklama_gosterir(self):
        with mock.patch.object(bt, "ADAYLAR", ()):
            s = bt.BeyannameTakipSekmesi(self.app, self.kok, self.mod)
        yazilar = [w.cget("text") for w in s.govde.winfo_children() if w.winfo_class() == "Label"]
        self.assertTrue(any("bulunamadı" in y for y in yazilar))

    def test_ayar_yoksa_yonlendirir_ve_ayar_dosyasini_olusturur(self):
        self.assertIn("Ayar dosyası yok", self._durum())
        with mock.patch.object(bt.os, "startfile", create=True) as ac:
            self.bt.ayar_ac()
        self.assertTrue((self.klasor / "ayarlar.env").exists())
        self.assertEqual(ac.call_count, 1)
        self.assertEqual(self.mb_showinfo.call_count, 1)                               # ne yapilacagini soyler
        self.assertIn("Kapalı", self._durum())

    def test_paketler_eksikse_baslatmaz(self):
        with mock.patch.object(bt, "paketler_kurulu_mu", return_value=False):
            self.assertIn("kurulu değil", self._durum())
            self.assertEqual(str(self.bt.d_baslat.cget("state")), "disabled")
            self.assertEqual(str(self.bt.d_paket.cget("state")), "normal")
            self.bt.baslat()
        self.assertIsNone(self.bt.surec)

    def test_baslat_acar_tarayiciyi_acar_ve_kapat_kapatir(self):
        (self.klasor / "ayarlar.env").write_text(f"WEB_SIFRE=1234\nPORT={self.port}\n", encoding="utf-8")
        self.app.sekme_sec("bt")
        self.assertIn("Kapalı", self._durum())
        self.bt.baslat()
        self.assertTrue(self._bekle(lambda: self._durum().startswith("● Çalışıyor"), 20), self.bt.durum.cget("text"))
        self.assertIn(f"127.0.0.1:{self.port}", self.bt.durum.cget("text"))
        self.assertTrue(bt.port_acik_mi(self.port))
        self.tarayici.assert_called_with(f"http://127.0.0.1:{self.port}")             # acilinca tarayici bir kez acildi
        self.assertIsNone(self.bt.bekleme_bitis)
        log = (self.klasor / "program.log").read_text(encoding="utf-8")
        self.assertIn("TARAYICI=0", log)
        self.assertIn(f"LUCABOT_YOLU={bt.KOK}", log)
        self.assertEqual(str(self.bt.d_baslat.cget("state")), "disabled")             # zaten calisiyor: ikinci kopya baslatilmaz
        self.assertEqual(str(self.bt.d_kapat.cget("state")), "normal")
        self.bt.kapat()                                                                # askyesno -> True
        self.assertTrue(self._bekle(lambda: self._durum().startswith("○ Kapalı"), 20), self.bt.durum.cget("text"))
        self.assertFalse(bt.port_acik_mi(self.port))

    def test_zaten_calisiyorsa_yalniz_tarayiciyi_acar(self):
        (self.klasor / "ayarlar.env").write_text(f"PORT={self.port}\n", encoding="utf-8")
        sunucu = socket.socket()
        sunucu.bind(("127.0.0.1", self.port))
        sunucu.listen(1)
        self.addCleanup(sunucu.close)
        with mock.patch.object(bt, "calistir") as calistir:
            self.bt.baslat()
        calistir.assert_not_called()
        self.tarayici.assert_called_with(f"http://127.0.0.1:{self.port}")

    def test_program_acilamazsa_hata_gosterir(self):
        (self.klasor / "baslat.py").write_text("import sys; print('ayarlar.env bozuk'); sys.exit(1)", encoding="utf-8")
        (self.klasor / "ayarlar.env").write_text(f"PORT={self.port}\n", encoding="utf-8")
        self.bt.baslat()
        self.assertTrue(self._bekle(lambda: self._durum() and self.mb_showerror.call_count > 0, 20))
        self.assertIn("ayarlar.env bozuk", self.mb_showerror.call_args[0][1])         # hatanin nedenini log'dan gosterir
        self.assertIsNone(self.bt.bekleme_bitis)


if __name__ == "__main__":
    unittest.main()
