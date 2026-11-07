# -*- coding: utf-8 -*-
"""Luca Bot arayuzunun "Beyanname Takip" sekmesi.

Repodaki ayri beyanname-takip/ programini (baslat.py) arka planda calistirir ve tarayicida acar. KDV, MUHSGK, gecici vergi ve
diger beyannamelerin son gunlerini Luca'dan (GIB Beyanname Takip ekrani) okuyarak izler, verilmemis olanlari e-postayla bildirir;
GIB'e dogrudan baglanmaz. Luca baglantisi icin bu programin kendi lucabot paketini kullanir (LUCABOT_YOLU).

Program kendi web sayfasini acar (varsayilan http://127.0.0.1:8765); bu sekme baslatma, kapatma ve ilk kurulum icindir:
  * "Ayar dosyasini olustur"  -> beyanname-takip/ayarlar.env (Luca hesaplari, e-posta, web sifresi)
  * "Gerekli paketleri kur"   -> fastapi + uvicorn (bu programin Python ortamina)
  * "Baslat ve ac" / "Kapat"  -> kapatma, baslaticinin urettigi yerel anahtarla yapilir (surec numarasi oldurulmez)
"""

import importlib
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import messagebox

KOK = Path(__file__).resolve().parent
# luca-bot ile yan yana (repo koku) ya da icinde durabilir
ADAYLAR = (KOK.parent / "beyanname-takip", KOK / "beyanname-takip")
VARSAYILAN_PORT = 8765
ACILIS_BEKLEME_SN = 45
YENILEME_MS = 2000
PAKETLER = ("fastapi", "uvicorn")
PENCERESIZ = 0x08000000 | 0x00000200   # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP (yalniz Windows'ta anlamli)


# -- saf yardimcilar (ekrandan bagimsiz, test edilir) -----------------------------------------------

def klasor_bul():
    """beyanname-takip klasoru (baslat.py iceren); yoksa None."""
    for yol in ADAYLAR:
        if (yol / "baslat.py").exists():
            return yol
    return None


def port_oku(klasor):
    """ayarlar.env icindeki PORT (1024-65535); yoksa ya da gecersizse varsayilan."""
    try:
        metin = (Path(klasor) / "ayarlar.env").read_text(encoding="utf-8-sig")
    except OSError:
        return VARSAYILAN_PORT
    m = re.search(r"^\s*PORT\s*=\s*(\d{1,5})\s*$", metin, re.M)
    port = int(m.group(1)) if m else VARSAYILAN_PORT
    return port if 1024 <= port <= 65535 else VARSAYILAN_PORT


def port_acik_mi(port, zaman=0.25):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=zaman):
            return True
    except OSError:
        return False


def paketler_kurulu_mu():
    importlib.invalidate_caches()
    return all(importlib.util.find_spec(p) is not None for p in PAKETLER)


def konsolsuz_python():
    """Pencere acmayan yorumlayici: Windows'ta pythonw.exe (varsa), degilse bu program neyle calisiyorsa o."""
    exe = Path(sys.executable)
    if os.name == "nt":
        w = exe.with_name("pythonw.exe")
        if w.exists():
            return str(w)
    return str(exe)


def konsollu_python():
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and exe.with_name("python.exe").exists():
        return str(exe.with_name("python.exe"))
    return str(exe)


def ayar_olustur(klasor):
    """ayarlar.ornek.env -> ayarlar.env (yoksa). Dosya zaten varsa dokunmaz. Doner: (yol, yeni_olustu_mu)."""
    klasor = Path(klasor)
    hedef = klasor / "ayarlar.env"
    if hedef.exists():
        return hedef, False
    sablon = klasor / "ayarlar.ornek.env"
    hedef.write_text(sablon.read_text(encoding="utf-8") if sablon.exists() else "WEB_SIFRE=\n", encoding="utf-8")
    return hedef, True


def calistir(klasor):
    """baslat.py'yi pencere acmadan baslatir (cikti program.log'a). Tarayiciyi bu sekme acar (BEYANNAME_TARAYICI=0);
    lucabot olarak bu programin luca-bot klasoru kullanilir (LUCABOT_YOLU)."""
    klasor = Path(klasor)
    env = dict(os.environ, LUCABOT_YOLU=str(KOK), BEYANNAME_TARAYICI="0", PYTHONIOENCODING="utf-8")
    log = open(klasor / "program.log", "a", encoding="utf-8")
    try:
        return subprocess.Popen([konsolsuz_python(), str(klasor / "baslat.py")], cwd=str(klasor), env=env, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT, creationflags=PENCERESIZ if os.name == "nt" else 0)
    finally:
        log.close()                                                            # cocuk kendi kopyasini tutar


def kapat_istegi(klasor, zaman=3):
    """Calisan programa kontrol.json'daki yerel anahtarla 'kapan' der. Doner: (basarili_mi, mesaj)."""
    try:
        k = json.loads((Path(klasor) / "kontrol.json").read_text(encoding="ascii"))
        istek = urllib.request.Request(f"http://127.0.0.1:{int(k['port'])}/api/kapat-kontrol", method="POST", data=b"",
                                       headers={"X-Kontrol-Token": str(k["anahtar"])})
        with urllib.request.urlopen(istek, timeout=zaman) as r:
            return r.status == 200, "Kapatma istegi gonderildi"
    except (OSError, ValueError, KeyError, urllib.error.URLError) as e:
        return False, f"Kapatilamadi ({type(e).__name__}): program bu sekmeden baslatilmamis olabilir; tarayicidaki sayfada Sistem > 'Programi kapat'"


def log_sonu(klasor, satir=12):
    try:
        metin = (Path(klasor) / "program.log").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(metin.splitlines()[-satir:])


# -- sekme --------------------------------------------------------------------------------------------

class BeyannameTakipSekmesi:
    def __init__(self, arayuz, ebeveyn, ui):
        """ui: luca_arayuz modulu (renkler ve kucuk bilesenler); dongusel import olmasin diye verilir."""
        self.a = arayuz
        self.ui = ui
        self.klasor = klasor_bul()
        self.surec = None
        self.bekleme_bitis = None        # baslatildi, acilmasi bekleniyor (zaman damgasi)
        self.paket_kuruluyor = False
        self.paket_mesaji = ""
        self.yenile_id = None
        self.govde = tk.Frame(ebeveyn, bg=ui.ZEMIN)
        if self.klasor is None:
            tk.Label(self.govde, text="beyanname-takip klasörü bulunamadı.\n\nluca-bot klasörünün yanında (aynı üst klasörde) "
                     "`beyanname-takip` klasörü olmalı.", font=ui.GOVDE, fg=ui.TURUNCU, bg=ui.ZEMIN,
                     justify="left").pack(padx=30, pady=30, anchor="w")
            return
        self._arayuz_kur()
        self.yenile()

    # -- gorunum ----------------------------------------------------------------------------------

    def _arayuz_kur(self):
        u = self.ui
        dis = tk.Frame(self.govde, bg=u.ZEMIN, padx=30, pady=24)
        dis.pack(fill="both", expand=True)
        tk.Label(dis, text="Beyanname Takip", font=u.SERIF, fg=u.BASLIK_FG, bg=u.ZEMIN, anchor="w").pack(fill="x")
        tk.Label(dis, text="KDV, MUHSGK, geçici vergi ve diğer beyannamelerin son günlerini Luca'dan (GİB Beyanname Takip ekranı) "
                 "okuyarak izler; verilmemiş olanları e-postayla bildirir. GİB'e doğrudan bağlanmaz. Program tarayıcıda açılır.",
                 font=u.GOVDE, fg=u.SOLUK, bg=u.ZEMIN, justify="left", wraplength=760, anchor="w").pack(fill="x", pady=(4, 14))
        self.durum = tk.Label(dis, text="", font=u.GOVDE_KALIN, bg=u.ZEMIN, anchor="w", justify="left", wraplength=760)
        self.durum.pack(fill="x", pady=(0, 10))
        satir = tk.Frame(dis, bg=u.ZEMIN)
        satir.pack(fill="x")
        self.d_baslat = u.dugme(satir, "Başlat ve aç", self.baslat, ana=True)
        self.d_baslat.pack(side="left")
        self.d_ac = u.dugme(satir, "Tarayıcıda aç", self.tarayicida_ac)
        self.d_ac.pack(side="left", padx=8)
        self.d_kapat = u.dugme(satir, "Kapat", self.kapat)
        self.d_kapat.pack(side="left")
        tk.Frame(dis, bg=u.CIZGI, height=1).pack(fill="x", pady=16)
        satir2 = tk.Frame(dis, bg=u.ZEMIN)
        satir2.pack(fill="x")
        self.d_ayar = u.dugme(satir2, "Ayar dosyasını oluştur / aç", self.ayar_ac)
        self.d_ayar.pack(side="left")
        self.d_paket = u.dugme(satir2, "Gerekli paketleri kur", self.paket_kur)
        self.d_paket.pack(side="left", padx=8)
        self.bilgi = tk.Label(dis, text="", font=u.KUCUK, fg=u.SOLUK, bg=u.ZEMIN, justify="left", wraplength=760, anchor="w")
        self.bilgi.pack(fill="x", pady=(8, 8))
        self.log = tk.Text(dis, height=10, font=u.KONSOL_YAZI, bg=u.KONSOL, fg=u.KONSOL_FG, relief="flat", wrap="word",
                           highlightthickness=1, highlightbackground=u.KONSOL_KENAR, state="disabled")
        self.log.pack(fill="both", expand=True)

    def _durum_yaz(self, metin, renk):
        self.durum.configure(text=metin, fg=renk)

    def yenile(self):
        """Durumu 2 saniyede bir tazeler (port, ayar dosyasi, paketler, acilis beklemesi, log)."""
        u = self.ui
        try:
            port = port_oku(self.klasor)
            acik = port_acik_mi(port)
            paket = paketler_kurulu_mu()
            ayar = (self.klasor / "ayarlar.env").exists()
            if self.bekleme_bitis is not None:
                if acik:
                    self.bekleme_bitis = None
                    self.tarayicida_ac()
                elif self.surec is not None and self.surec.poll() is not None:
                    self.bekleme_bitis = None
                    messagebox.showerror("Beyanname Takip", "Program açılamadı.\n\n" + (log_sonu(self.klasor, 6) or "program.log boş"),
                                         parent=self.a.kok)
                elif time.time() > self.bekleme_bitis:
                    self.bekleme_bitis = None
                    messagebox.showwarning("Beyanname Takip", f"Program {ACILIS_BEKLEME_SN} saniyede açılmadı. "
                                           "Aşağıdaki günlüğe (program.log) bakın.", parent=self.a.kok)
            if self.paket_kuruluyor:
                self._durum_yaz("Gerekli paketler kuruluyor…", u.TURUNCU)
            elif not paket:
                self._durum_yaz("Gerekli paketler (fastapi, uvicorn) kurulu değil: 'Gerekli paketleri kur' düğmesine basın.", u.TURUNCU)
            elif acik:
                self._durum_yaz(f"● Çalışıyor: http://127.0.0.1:{port}", u.YESIL_FG)
            elif self.bekleme_bitis is not None:
                self._durum_yaz("Başlatılıyor…", u.TURUNCU)
            elif not ayar:
                self._durum_yaz("Ayar dosyası yok: 'Ayar dosyasını oluştur / aç' ile Luca hesaplarınızı ve web şifresini girin.", u.TURUNCU)
            else:
                self._durum_yaz("○ Kapalı", u.SOLUK)
            self.d_baslat.configure(state="normal" if paket and not acik and not self.paket_kuruluyor and self.bekleme_bitis is None else "disabled")
            self.d_ac.configure(state="normal" if acik else "disabled")
            self.d_kapat.configure(state="normal" if acik else "disabled")
            self.d_paket.configure(state="disabled" if paket or self.paket_kuruluyor else "normal")
            self.bilgi.configure(text=self.paket_mesaji or f"Ayar dosyası: {self.klasor / 'ayarlar.env'}  ·  Günlük: {self.klasor / 'program.log'}")
            self._log_yaz()
        except tk.TclError:
            return                                                              # pencere kapandi
        # yalnizca sekme gorunurken (ya da baslatma/kurulum surerken) taze tut; baska sekmedeyken bosuna yoklama yapma
        if self.govde.winfo_ismapped() or self.bekleme_bitis is not None or self.paket_kuruluyor:
            self.yenile_id = self.govde.after(YENILEME_MS, self.yenile)
        else:
            self.yenile_id = None

    def _log_yaz(self):
        metin = log_sonu(self.klasor)
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.insert("end", metin)
        self.log.configure(state="disabled")
        self.log.see("end")

    def iptal(self):
        if self.yenile_id:
            try:
                self.govde.after_cancel(self.yenile_id)
            except tk.TclError:
                pass
            self.yenile_id = None

    # -- islemler ---------------------------------------------------------------------------------

    def tarayicida_ac(self):
        webbrowser.open(f"http://127.0.0.1:{port_oku(self.klasor)}")

    def baslat(self):
        if not paketler_kurulu_mu():
            messagebox.showinfo("Beyanname Takip", "Önce 'Gerekli paketleri kur' düğmesine basın.", parent=self.a.kok)
            return
        if not (self.klasor / "ayarlar.env").exists():
            self.ayar_ac()
            return
        if port_acik_mi(port_oku(self.klasor)):
            self.tarayicida_ac()
            return
        self.surec = calistir(self.klasor)
        self.bekleme_bitis = time.time() + ACILIS_BEKLEME_SN
        self.yenile_simdi()

    def kapat(self):
        if not messagebox.askyesno("Beyanname Takip", "Program kapatılsın mı? Luca çekimi sürüyorsa yarıda kesilir.", parent=self.a.kok):
            return
        ok, mesaj = kapat_istegi(self.klasor)
        if not ok:
            messagebox.showinfo("Beyanname Takip", mesaj, parent=self.a.kok)
        self.yenile_simdi()

    def ayar_ac(self):
        yol, yeni = ayar_olustur(self.klasor)
        if yeni:
            messagebox.showinfo("Beyanname Takip", "ayarlar.env oluşturuldu. Açılan dosyada web şifresini, Luca hesaplarınızı "
                                "(üye no, kullanıcı, parola, doğrulama anahtarı) ve e-posta ayarlarını doldurup kaydedin.", parent=self.a.kok)
        try:
            if hasattr(os, "startfile"):
                os.startfile(str(yol))                                          # Windows: varsayilan metin duzenleyici
            else:
                webbrowser.open(yol.as_uri())
        except OSError as e:
            messagebox.showerror("Beyanname Takip", f"Dosya açılamadı: {e}\n\n{yol}", parent=self.a.kok)
        self.yenile_simdi()

    def paket_kur(self):
        if self.paket_kuruluyor:
            return
        self.paket_kuruluyor, self.paket_mesaji = True, "pip çalışıyor…"
        import threading

        def is_():
            try:
                s = subprocess.run([konsollu_python(), "-m", "pip", "install", "-r", str(self.klasor / "requirements.txt")],
                                   capture_output=True, text=True, timeout=600, creationflags=PENCERESIZ if os.name == "nt" else 0)
                mesaj = "Paketler kuruldu." if s.returncode == 0 else "Kurulum başarısız: " + (s.stderr or s.stdout)[-400:]
            except (OSError, subprocess.SubprocessError) as e:
                mesaj = f"Kurulum başarısız: {type(e).__name__}: {e}"
            self.paket_mesaji, self.paket_kuruluyor = mesaj, False
        threading.Thread(target=is_, daemon=True).start()
        self.yenile_simdi()

    def yenile_simdi(self):
        self.iptal()
        self.yenile()
