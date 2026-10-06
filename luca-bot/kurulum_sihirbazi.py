# -*- coding: utf-8 -*-
"""Yeni kullanici kurulum sihirbazi: Luca ve Defter Beyan bilgileri, tercihler, firma listesi.

Luca bilgileri hic girilmemisse program acilinca kendiliginden acilir; sonradan sol paneldeki
"Kurulum Sihirbazi" dugmesiyle de acilir. Mantik lucabot/kurulum.py'dadir (pencere gerektirmez).
"""

import importlib
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from lucabot import kurulum

ADIMLAR = (("hos", "Hoş geldiniz"), ("luca", "Luca girişi"), ("defterbeyan", "Defter Beyan"),
           ("tercihler", "Tercihler"), ("bitis", "Hazır"))
DURUM_SIMGE = {"tamam": "✔", "uyari": "!", "hata": "✖"}


class KurulumSihirbazi:
    def __init__(self, arayuz, ui):
        """arayuz: luca_arayuz.Arayuz; ui: luca_arayuz modulu (renk ve bilesenler icin)."""
        self.a = arayuz
        self.ui = ui
        self.adim = 0
        mevcut = arayuz.ayarlar
        self.v = {
            "uye_no": tk.StringVar(value=str(mevcut.get("uye_no") or "")),
            "kullanici_adi": tk.StringVar(value=str(mevcut.get("kullanici_adi") or "")),
            "parola": tk.StringVar(value=str(mevcut.get("parola") or "")),
            "dogrulama_anahtari": tk.StringVar(value=str(mevcut.get("dogrulama_anahtari") or "")),
            "defterbeyan_kullanici": tk.StringVar(value=str(mevcut.get("defterbeyan_kullanici") or "")),
            "defterbeyan_sifre": tk.StringVar(value=str(mevcut.get("defterbeyan_sifre") or "")),
            "indirme_klasoru": tk.StringVar(value=str(mevcut.get("indirme_klasoru") or "indirilenler")),
            "mail_alici": tk.StringVar(value=str(mevcut.get("mail_alici") or "")),
            "mail_gonder": tk.BooleanVar(value=bool(mevcut.get("mail_gonder", True))),
            "otomatik_tekrar": tk.BooleanVar(value=bool(mevcut.get("otomatik_tekrar", True))),
            "tema": tk.StringVar(value=mevcut.get("tema") or "acik"),
            "liste_cek": tk.BooleanVar(value=True),
        }
        u = ui
        w = self.w = tk.Toplevel(arayuz.kok, bg=u.ZEMIN)
        w.title("Kurulum Sihirbazı — Dijital Stajyer")
        w.transient(arayuz.kok)
        w.geometry("680x560")
        w.minsize(640, 520)
        ust = tk.Frame(w, bg=u.BASLIK_ZEMIN, height=64)
        ust.pack(fill="x")
        ust.pack_propagate(False)
        tk.Label(ust, text="Kurulum Sihirbazı", font=u.SERIF, fg=u.BASLIK_YAZI, bg=u.BASLIK_ZEMIN
                 ).pack(side="left", padx=22)
        self.adim_etiketi = tk.Label(ust, text="", font=u.KUCUK, fg=u.ALTIN, bg=u.BASLIK_ZEMIN)
        self.adim_etiketi.pack(side="right", padx=22)
        alt = tk.Frame(w, bg=u.ZEMIN)
        alt.pack(side="bottom", fill="x", padx=24, pady=(0, 16))
        self.hata_etiketi = tk.Label(w, text="", font=u.KUCUK, fg=u.KIRMIZI, bg=u.ZEMIN, anchor="w",
                                     justify="left", wraplength=620)
        self.hata_etiketi.pack(side="bottom", fill="x", padx=24, pady=(0, 6))
        self.geri_dugmesi = u.dugme(alt, "‹ Geri", self.geri)
        self.geri_dugmesi.pack(side="left")
        self.ileri_dugmesi = u.dugme(alt, "İleri ›", self.ileri, ana=True)
        self.ileri_dugmesi.pack(side="right")
        u.dugme(alt, "Vazgeç", w.destroy).pack(side="right", padx=8)
        self.icerik = tk.Frame(w, bg=u.ZEMIN, padx=28, pady=18)
        self.icerik.pack(fill="both", expand=True)
        self._goster()
        w.grab_set()

    # -- sayfalar --------------------------------------------------------------------------

    def _temizle(self):
        for c in self.icerik.winfo_children():
            c.destroy()
        self.hata_etiketi.configure(text="")

    def _baslik(self, metin, alt=""):
        u = self.ui
        tk.Label(self.icerik, text=metin, font=("Georgia", 14, "bold"), fg=u.BASLIK_FG, bg=u.ZEMIN,
                 anchor="w").pack(fill="x")
        if alt:
            tk.Label(self.icerik, text=alt, font=u.GOVDE, fg=u.SOLUK, bg=u.ZEMIN, anchor="w", justify="left",
                     wraplength=610).pack(fill="x", pady=(4, 12))

    def _alan(self, etiket, anahtar, gizli=False, ipucu=""):
        u = self.ui
        tk.Label(self.icerik, text=etiket, font=u.KUCUK, fg=u.ETIKET, bg=u.ZEMIN, anchor="w"
                 ).pack(fill="x", pady=(8, 3))
        kutu = u.giris_kutusu(self.icerik, self.v[anahtar], gizli=gizli, genislik=44)
        kutu.pack(fill="x", ipady=4)
        if ipucu:
            tk.Label(self.icerik, text=ipucu, font=u.KUCUK, fg=u.SOLUK, bg=u.ZEMIN, anchor="w", justify="left",
                     wraplength=610).pack(fill="x", pady=(3, 0))
        return kutu

    def _hos(self):
        u = self.ui
        self._baslik("Hoş geldiniz", "Birkaç adımda programı bu bilgisayar ve bu Luca kullanıcısı için hazırlayacağız. "
                                     "Bilgiler yalnızca bu bilgisayardaki ayarlar.json dosyasına kaydedilir.")
        self.ortam_alani = tk.Frame(self.icerik, bg=u.ZEMIN)
        self.ortam_alani.pack(fill="x")
        self.kur_bilgisi = tk.Label(self.icerik, text="", font=u.KUCUK, fg=u.SOLUK, bg=u.ZEMIN, anchor="w",
                                    justify="left", wraplength=610)
        satir = tk.Frame(self.icerik, bg=u.ZEMIN)
        satir.pack(fill="x", pady=(10, 4))
        self.kur_dugmesi = u.dugme(satir, "Eksik bileşenleri şimdi kur", self.eksikleri_kur)
        self.kur_dugmesi.pack(side="left")
        tk.Label(satir, text="(kurulum.bat'ın yaptığı iş; internet gerekir)", font=u.KUCUK, fg=u.SOLUK,
                 bg=u.ZEMIN).pack(side="left", padx=10)
        self.kur_bilgisi.pack(fill="x")
        self.kur_logu = tk.Text(self.icerik, height=8, bg=u.KONSOL, fg=u.KONSOL_FG, font=u.KONSOL_YAZI, relief="flat",
                                wrap="word", state="disabled", highlightthickness=1, highlightbackground=u.KENAR)
        self.ortam_yenile()

    def ortam_yenile(self):
        """Ortam durum satirlarini yeniden okuyup cizer (kurulumdan sonra da cagrilir)."""
        u = self.ui
        importlib.invalidate_caches()  # yeni kurulan paketler bulunsun
        self.ortam = kurulum.ortam_kontrol(self.a.kz.klasor)
        for c in self.ortam_alani.winfo_children():
            c.destroy()
        for ad, durum, aciklama in self.ortam:
            satir = tk.Frame(self.ortam_alani, bg=u.ZEMIN)
            satir.pack(fill="x", pady=2)
            renk = {"tamam": u.YESIL_FG, "uyari": u.TURUNCU, "hata": u.KIRMIZI}[durum]
            tk.Label(satir, text=DURUM_SIMGE[durum], font=u.GOVDE_KALIN, fg=renk, bg=u.ZEMIN, width=2).pack(side="left")
            tk.Label(satir, text=ad, font=u.GOVDE_KALIN, fg=u.YAZI, bg=u.ZEMIN, width=30, anchor="w").pack(side="left")
            tk.Label(satir, text=aciklama, font=u.KUCUK, fg=u.SOLUK, bg=u.ZEMIN, anchor="w", justify="left",
                     wraplength=300).pack(side="left", fill="x", expand=True)
        eksik = bool(kurulum.kurulum_komutlari(self._python(), self._kok(), self.ortam))
        self.kur_dugmesi.configure(state="normal" if eksik and not self.kuruluyor() else "disabled")
        if any(d == "hata" for _, d, _ in self.ortam):
            self.kur_bilgisi.configure(text="Kırmızı ✖ satırlar giderilmeden devam edilemez: yukarıdaki düğmeyle kurun.",
                                       fg=u.KIRMIZI)
        elif eksik:
            self.kur_bilgisi.configure(text="Sarı ! satırlar isteğe bağlıdır; kurmak ister misiniz? (Chromium yoksa bilgisayardaki "
                                            "Chrome/Edge denenir.)", fg=u.SOLUK)
        else:
            self.kur_bilgisi.configure(text="Her şey hazır.", fg=u.YESIL_FG)

    # -- kurulum calistirma (kurulum.bat'in isi) ---------------------------------------------

    def _python(self):
        return self.ui.python_komutu()

    def _kok(self):
        return Path(self.ui.KOK)

    def kuruluyor(self):
        return getattr(self, "kur_kuyrugu", None) is not None and getattr(self, "kur_is_parcacigi", None) is not None \
            and self.kur_is_parcacigi.is_alive()

    def eksikleri_kur(self):
        komutlar = kurulum.kurulum_komutlari(self._python(), self._kok(), self.ortam)
        if not komutlar or self.kuruluyor():
            return
        self.kur_logu.pack(fill="both", expand=True, pady=(6, 0))
        self.kur_dugmesi.configure(state="disabled")
        self.ileri_dugmesi.configure(state="disabled")
        self.kur_bilgisi.configure(text="Kuruluyor… pencereyi kapatmayın.", fg=self.ui.TURUNCU)
        self.kur_kuyrugu = queue.Queue()
        self.kur_is_parcacigi = threading.Thread(target=self._kur_calistir, args=(komutlar, self.kur_kuyrugu),
                                                 daemon=True)
        self.kur_is_parcacigi.start()
        self.w.after(150, self._kur_oku)

    def _kur_calistir(self, komutlar, kuyruk):
        bayrak = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0
        ortam = dict(os.environ, PYTHONIOENCODING="utf-8", PIP_DISABLE_PIP_VERSION_CHECK="1")
        basarili = True
        for aciklama, argv in komutlar:
            kuyruk.put(("log", f"\n>>> {aciklama}\n"))
            try:
                with subprocess.Popen(argv, cwd=str(self._kok()), env=ortam, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=bayrak,
                                      text=True, encoding="utf-8", errors="replace") as surec:
                    for satir in surec.stdout:
                        kuyruk.put(("log", satir))
                    kod = surec.wait()
                if kod != 0:
                    basarili = False
                    kuyruk.put(("log", f"[HATA] komut {kod} koduyla bitti\n"))
            except OSError as e:
                basarili = False
                kuyruk.put(("log", f"[HATA] komut başlatılamadı: {e}\n"))
        kuyruk.put(("bitti", basarili))

    def _kur_oku(self):
        try:
            if not self.w.winfo_exists():
                return
        except tk.TclError:
            return
        bitti = None
        try:
            while True:
                tur, veri = self.kur_kuyrugu.get_nowait()
                if tur == "log":
                    self.kur_logu.configure(state="normal")
                    self.kur_logu.insert("end", veri)
                    self.kur_logu.see("end")
                    self.kur_logu.configure(state="disabled")
                else:
                    bitti = veri
        except queue.Empty:
            pass
        if bitti is None:
            self.w.after(150, self._kur_oku)
            return
        self.kur_is_parcacigi = None
        self.ileri_dugmesi.configure(state="normal")
        self.ortam_yenile()
        if not bitti:
            self.kur_bilgisi.configure(text="Kurulum tamamlanamadı: yukarıdaki kayda bakın (internet bağlantısı ya da "
                                            "yetki sorunu olabilir). Gerekirse kurulum.bat'ı yönetici olarak çalıştırın.",
                                       fg=self.ui.KIRMIZI)

    def _luca(self):
        self._baslik("Luca giriş bilgileri", "Program Luca'ya bu bilgilerle kendisi girer.")
        self._alan("Üye No", "uye_no")
        self._alan("Kullanıcı Adı", "kullanici_adi")
        self._alan("Parola", "parola", gizli=True)
        self._alan("Doğrulama anahtarı (isteğe bağlı)", "dogrulama_anahtari", gizli=True,
                   ipucu="Luca'da iki aşamalı doğrulama açıksa, kurulum ekranındaki gizli anahtarı buraya yazarsanız kod "
                         "kendiliğinden üretilir. Boş bırakırsanız her girişte kodu siz yazarsınız.")

    def _defterbeyan(self):
        self._baslik("Defter Beyan (isteğe bağlı)", "İşletme / serbest meslek mükellefleri için Kâr / Zarar sekmesi "
                                                   "Defter Beyan'dan okur. Kullanmayacaksanız boş bırakıp geçin.")
        self._alan("Kullanıcı kodu", "defterbeyan_kullanici")
        self._alan("Şifre", "defterbeyan_sifre", gizli=True,
                   ipucu="Güvenlik kodunu (captcha) her girişte açılan tarayıcıda siz yazarsınız; program onu çözmez.")

    def _tercihler(self):
        u = self.ui
        self._baslik("Tercihler")
        self._alan("İndirme klasörü", "indirme_klasoru",
                   ipucu="Faturalar ve raporlar buraya kaydedilir. Program klasörüne göredir (örn. indirilenler) "
                         "ya da tam yol yazabilirsiniz.")
        tk.Checkbutton(self.icerik, text="Çalışma bitince özet e-postası gönder", variable=self.v["mail_gonder"],
                       font=u.GOVDE, **self.a._kutu_renk()).pack(anchor="w", pady=(12, 0))
        self._alan("E-posta alıcısı (boşsa Outlook hesabınızın kendi adresi)", "mail_alici")
        tk.Checkbutton(self.icerik, text="Hatalı ekranları çalışma sonunda bir kez kendiliğinden tekrar sorgula",
                       variable=self.v["otomatik_tekrar"], font=u.GOVDE, **self.a._kutu_renk()
                       ).pack(anchor="w", pady=(12, 0))
        satir = tk.Frame(self.icerik, bg=u.ZEMIN)
        satir.pack(fill="x", pady=(12, 0))
        tk.Label(satir, text="Görünüm:", font=u.GOVDE, fg=u.YAZI, bg=u.ZEMIN).pack(side="left")
        for ad, deger in (("Açık", "acik"), ("Koyu", "koyu")):
            tk.Radiobutton(satir, text=ad, value=deger, variable=self.v["tema"], font=u.GOVDE,
                           **self.a._kutu_renk()).pack(side="left", padx=(10, 0))

    def _bitis(self):
        u = self.ui
        self._baslik("Hazır", "Ayarlar kaydedilecek. Sonraki adım olarak Luca'dan müşteri (firma) listenizi çekebilirsiniz; "
                              "bu aynı zamanda giriş bilgilerinizi de denemiş olur.")
        tk.Checkbutton(self.icerik, text="Bitirince Luca'dan firma listesini çek", variable=self.v["liste_cek"],
                       font=u.GOVDE_KALIN, **self.a._kutu_renk()).pack(anchor="w", pady=(6, 10))
        ozet = [("Luca kullanıcısı", f"{self.v['kullanici_adi'].get()}  (üye {self.v['uye_no'].get()})"),
                ("Defter Beyan", self.v["defterbeyan_kullanici"].get() or "girilmedi"),
                ("İndirme klasörü", self.v["indirme_klasoru"].get()),
                ("Özet e-postası", ("açık — " + (self.v["mail_alici"].get() or "Outlook hesabınız"))
                 if self.v["mail_gonder"].get() else "kapalı"),
                ("Otomatik ikinci tur", "açık" if self.v["otomatik_tekrar"].get() else "kapalı"),
                ("Görünüm", "Koyu" if self.v["tema"].get() == "koyu" else "Açık")]
        for ad, deger in ozet:
            satir = tk.Frame(self.icerik, bg=u.ZEMIN)
            satir.pack(fill="x", pady=2)
            tk.Label(satir, text=ad, font=u.GOVDE_KALIN, fg=u.ETIKET, bg=u.ZEMIN, width=22, anchor="w").pack(side="left")
            tk.Label(satir, text=deger, font=u.GOVDE, fg=u.YAZI, bg=u.ZEMIN, anchor="w").pack(side="left")

    # -- gezinme ---------------------------------------------------------------------------

    def _goster(self):
        self._temizle()
        anahtar, ad = ADIMLAR[self.adim]
        self.adim_etiketi.configure(text=f"Adım {self.adim + 1} / {len(ADIMLAR)} — {ad}")
        getattr(self, "_" + anahtar)()
        self.geri_dugmesi.configure(state="normal" if self.adim else "disabled")
        self.ileri_dugmesi.configure(text="Bitir" if self.adim == len(ADIMLAR) - 1 else "İleri ›")

    def _degerler(self):
        return {k: v.get() for k, v in self.v.items()}

    def geri(self):
        if self.adim:
            self.adim -= 1
            self._goster()

    def ileri(self):
        anahtar = ADIMLAR[self.adim][0]
        hatalar = kurulum.dogrula(anahtar, self._degerler())
        if anahtar == "hos" and any(d == "hata" for _, d, _ in getattr(self, "ortam", [])):
            hatalar = ["Zorunlu paketler eksik: önce kurulum.bat dosyasını çalıştırıp programı yeniden açın."]
        if hatalar:
            self.hata_etiketi.configure(text="\n".join(hatalar))
            return
        if self.adim == len(ADIMLAR) - 1:
            self.bitir()
            return
        self.adim += 1
        self._goster()

    def bitir(self):
        a = self.a
        d = self._degerler()
        yeni = kurulum.ayarlari_olustur(a.ayarlar, d)
        tema_degisti = yeni["tema"] != self.ui.TEMA
        try:
            a.ayarlar.update(yeni)
            self.ui.ayarlari_kaydet(a.ayarlar)
        except OSError as e:
            messagebox.showerror("Kaydedilemedi", f"ayarlar.json yazılamadı: {e}", parent=self.w)
            return
        a.kz.v_db_kod.set(yeni["defterbeyan_kullanici"])
        a.kz.v_db_sifre.set(yeni["defterbeyan_sifre"])
        a._giris_ozetini_yaz()
        self.w.destroy()
        kok = a.kok
        if tema_degisti:
            a.tema_degistir()  # arayuz yeniden kurulur; sihirbaz penceresi zaten kapali
        if d["liste_cek"]:
            kok.after(500, a.firma_listesi_cek)
