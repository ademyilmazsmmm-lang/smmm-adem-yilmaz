#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Luca Bot masaustu arayuzu (SMMM Adem Yilmaz).

luca-arayuz.bat ile acilir. Komut satirina gerek kalmadan:
    - Luca giris bilgileri, firma listesi, tarih araligi ve ekranlar secilir
      (ayarlar.json'a kaydedilir),
    - "Calistir" botu (luca_bot.py) arka planda gece modunda baslatir; ciktisi
      pencerede canli akar, "Durdur" o ana kadarki sonuclari kaydederek durdurur,
    - alttaki kutular (Alis Tevkifat KDV, Alis SMM, Interaktif - e-Arsiv farki,
      KDV odemesi cikabilir) rapor.json'dan hesaplanir; tiklaninca firmalari
      listeler (lucabot.gostergeler).
"""

import codecs
import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import webbrowser
from datetime import date, timedelta
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

from lucabot import firma_tablosu, gostergeler  # noqa: E402
from lucabot.firma_listesi import devreden_kdvleri  # noqa: E402
from lucabot.ortak import (AYAR_DOSYASI, ORNEK_AYAR, TARIH_BICIMI,  # noqa: E402
                           hedef_ay_araligi, indirme_koku, sadelestir, tarih_cozumle)
from lucabot.sabitler import EKRAN_SUTUNLARI, TUM_BELGELER  # noqa: E402

# --- gorunum (smmmyilmaz.com ile ayni: lacivert + altin) -------------------
ZEMIN = "#0B1426"
BASLIK_ZEMIN = "#091122"
PANEL = "#111D35"
KUTU = "#0E1830"
KENAR = "#2A3A5C"
CIZGI = "#1F2C48"
YAZI = "#E8ECF4"
SOLUK = "#9AA6BD"
ETIKET = "#B8C2D6"
ALTIN = "#D4B263"
ALTIN_ACIK = "#E2C47A"
ALTIN_YAZI = "#1A1405"
YESIL = "#13804F"
TURUNCU = "#F0B45A"
KIRMIZI = "#F2918A"
KONSOL = "#070D1A"

GOVDE = ("Segoe UI", 10)
GOVDE_KALIN = ("Segoe UI", 10, "bold")
KUCUK = ("Segoe UI", 9)
BOLUM = ("Segoe UI", 8, "bold")
SERIF = ("Georgia", 16, "bold")
KONSOL_YAZI = ("Consolas", 10)

EKRAN_ADLARI = {tip: ad for ad, tip in EKRAN_SUTUNLARI.items()}
ILERLEME = re.compile(r"^\[(\d+)/(\d+)\]\s+(.+?)(?:\s+\|\s+tahmini kalan:\s*(.+))?$")
AZAMI_SATIR = 4000  # log penceresinde tutulan satir (uzun gecelerde pencere sismesin)


# --- ayarlar ---------------------------------------------------------------

def ayar_yolu():
    ozel = os.environ.get("LUCA_BOT_AYAR")
    return Path(ozel) if ozel else AYAR_DOSYASI


def ayarlari_yukle():
    """ayarlar.json (yoksa ornek). Bozuksa ValueError: uzerine yazip kaybetmeyelim."""
    for yol in (ayar_yolu(), ORNEK_AYAR):
        if yol.exists():
            try:
                return json.loads(yol.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError as e:
                raise ValueError(f"{yol.name} okunamadi (satir {e.lineno}): {e.msg}")
    return {}


def ayarlari_kaydet(ayarlar):
    yol = ayar_yolu()
    gecici = yol.with_suffix(".json.tmp")
    gecici.write_text(json.dumps(ayarlar, ensure_ascii=False, indent=2), encoding="utf-8")
    gecici.replace(yol)


def gecen_ay():
    bu_ay = date.today().replace(day=1)
    bit = bu_ay - timedelta(days=1)
    return bit.replace(day=1).strftime(TARIH_BICIMI), bit.strftime(TARIH_BICIMI)


def dosya_ac(yol):
    yol = str(yol)
    if sys.platform.startswith("win"):
        os.startfile(yol)  # noqa: S606 - kullanicinin kendi dosyasi
    elif sys.platform == "darwin":
        subprocess.Popen(["open", yol])
    else:
        subprocess.Popen(["xdg-open", yol])


def python_komutu():
    """Botu calistiracak python; arayuz pythonw ile acildiysa konsollu python.exe."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and (exe.parent / "python.exe").exists():
        return str(exe.parent / "python.exe")
    return str(exe)


TL_DESENI = re.compile(r"^-?[\d.]+,\d{2} TL( \*)?$")


def liste_excel_yaz(yol, baslik, donem, sutunlar, satirlar, toplam, notlar):
    """Ozet kutusunun firma listesini .xlsx olarak yazar; TL tutarlari sayi olarak."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from lucabot.fatura_analiz import tutar_cozumle

    def hucre(deger):
        if isinstance(deger, str) and TL_DESENI.match(deger):
            return tutar_cozumle(deger.replace(" *", ""))
        return deger

    wb = Workbook()
    ws = wb.active
    ws.title = "Liste"
    ws.append([baslik])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([f"Dönem: {donem.replace('-', ' – ')}" if donem else ""])
    ws.append([])
    ws.append(list(sutunlar))
    for h in ws[4]:
        h.font = Font(bold=True)
    for s in satirlar:
        ws.append([hucre(d) for d in s])
    if satirlar:
        ws.append([hucre(d) for d in toplam])
        for h in ws[ws.max_row]:
            h.font = Font(bold=True)
    for satir in ws.iter_rows(min_row=5):
        for h in satir:
            if isinstance(h.value, float):
                h.number_format = '#,##0.00 "TL"'
    ws.append([])
    for n in notlar:
        ws.append([n])
    ws.column_dimensions["A"].width = 38
    for harf in "BCDEF":
        ws.column_dimensions[harf].width = 18
    wb.save(yol)


# --- kucuk parcalar ----------------------------------------------------------

def bolum_basligi(ebeveyn, metin):
    return tk.Label(ebeveyn, text=metin.upper(), font=BOLUM, fg=ALTIN, bg=ZEMIN, anchor="w")


def giris_kutusu(ebeveyn, degisken, gizli=False, genislik=20):
    return tk.Entry(ebeveyn, textvariable=degisken, show="•" if gizli else "", width=genislik,
                    font=GOVDE, bg=KUTU, fg=YAZI, insertbackground=YAZI, relief="flat",
                    highlightthickness=1, highlightbackground=KENAR, highlightcolor=ALTIN)


def dugme(ebeveyn, metin, komut, ana=False, **kw):
    if ana:
        renk = dict(bg=ALTIN, fg=ALTIN_YAZI, activebackground=ALTIN_ACIK, activeforeground=ALTIN_YAZI,
                    font=("Segoe UI", 11, "bold"))
    else:
        renk = dict(bg=PANEL, fg=YAZI, activebackground="#172443", activeforeground=YAZI, font=GOVDE)
    d = tk.Button(ebeveyn, text=metin, command=komut, relief="flat", cursor="hand2",
                  bd=0, padx=14, pady=7, disabledforeground="#5B6782",
                  highlightthickness=1, highlightbackground=KENAR, **renk, **kw)
    return d


def logo(ebeveyn):
    """smmmyilmaz.com'daki altin 'AY' kutusu."""
    c = tk.Canvas(ebeveyn, width=46, height=46, bg=BASLIK_ZEMIN, highlightthickness=0)
    ust, alt = (0xEA, 0xD2, 0x93), (0xC4, 0x9A, 0x45)
    for y in range(46):
        o = y / 45
        renk = "#%02x%02x%02x" % tuple(int(u + (a - u) * o) for u, a in zip(ust, alt))
        c.create_line(0, y, 46, y, fill=renk)
    c.create_text(23, 24, text="AY", font=("Georgia", 15, "bold"), fill="#121A2E")
    return c


class OzetKutusu(tk.Frame):
    """Alttaki tiklanabilir gosterge kutusu."""

    def __init__(self, ebeveyn, baslik, komut, renk=YAZI):
        super().__init__(ebeveyn, bg=PANEL, highlightthickness=1, highlightbackground=CIZGI,
                         cursor="hand2", padx=12, pady=9)
        self.komut = komut
        self.baslik = tk.Label(self, text=baslik.upper(), font=BOLUM, fg=ETIKET if renk == YAZI else renk,
                               bg=PANEL, anchor="w")
        self.deger = tk.Label(self, text="—", font=("Segoe UI", 15, "bold"), fg=renk, bg=PANEL, anchor="w")
        self.alt = tk.Label(self, text="Firmaları gör ›", font=KUCUK, fg=ALTIN, bg=PANEL, anchor="w")
        for w in (self.baslik, self.deger, self.alt):
            w.pack(fill="x")
        for w in (self, self.baslik, self.deger, self.alt):
            w.bind("<Button-1>", lambda _e: self.komut())
            w.bind("<Enter>", lambda _e: self.configure(highlightbackground=ALTIN))
            w.bind("<Leave>", lambda _e: self.configure(highlightbackground=CIZGI))

    def ayarla(self, deger, alt="Firmaları gör ›"):
        self.deger.configure(text=deger)
        self.alt.configure(text=alt)


class FirmaEkranPenceresi:
    """firmalar.xlsx'i tablo olarak gosterir: her firmada hangi ekran sorgulansin (✓/X), Devreden KDV."""

    GENISLIK = (240, 100) + (80,) * len(TUM_BELGELER)

    def __init__(self, arayuz, yol, firmalar):
        self.arayuz, self.yol, self.firmalar = arayuz, yol, firmalar
        w = self.w = tk.Toplevel(arayuz.kok, bg=ZEMIN, padx=18, pady=14)
        w.title(f"Firma / Ekran Seçimi — {yol.name}")
        w.transient(arayuz.kok)
        w.geometry(f"{sum(self.GENISLIK) + 70}x660")

        ust = tk.Frame(w, bg=ZEMIN)
        ust.pack(fill="x")
        tk.Label(ust, text="Firma / Ekran Seçimi", font=("Georgia", 14, "bold"), fg="#F2F4F8",
                 bg=ZEMIN).pack(side="left")
        self.v_ara = tk.StringVar()
        self.v_ara.trace_add("write", lambda *_: self._suz())
        giris_kutusu(ust, self.v_ara, genislik=24).pack(side="right", ipady=3)
        tk.Label(ust, text="Firma ara:", font=KUCUK, fg=ETIKET, bg=ZEMIN).pack(side="right", padx=6)
        tk.Label(w, text="İşaretli = o ekran bu firmada sorgulanır. Sütun başlığına tıklayınca o ekran"
                         " tüm firmalarda açılır/kapanır, firma adına tıklayınca o firmanın tüm ekranları.",
                 font=KUCUK, fg=SOLUK, bg=ZEMIN, anchor="w", justify="left",
                 wraplength=sum(self.GENISLIK)).pack(fill="x", pady=(4, 8))

        alt = tk.Frame(w, bg=ZEMIN)
        alt.pack(side="bottom", fill="x", pady=(10, 0))
        self.bilgi = tk.Label(alt, text=f"{len(firmalar)} firma", font=KUCUK, fg=SOLUK, bg=ZEMIN)
        self.bilgi.pack(side="left")
        dugme(alt, "Kaydet", self.kaydet, ana=True).pack(side="right")
        dugme(alt, "Vazgeç", w.destroy).pack(side="right", padx=8)

        baslik = tk.Frame(w, bg=KUTU)
        baslik.pack(fill="x")
        basliklar = ["Firma", "Devreden KDV"] + [EKRAN_ADLARI.get(t, t).replace(" ", "\n", 1)
                                                 for t in TUM_BELGELER]
        for i, ad in enumerate(basliklar):
            baslik.grid_columnconfigure(i, minsize=self.GENISLIK[i])
            et = tk.Label(baslik, text=ad, font=BOLUM, fg=ALTIN, bg=KUTU,
                          anchor="w" if i < 2 else "center", justify="center", pady=6)
            et.grid(row=0, column=i, sticky="ew")
            if i >= 2:
                tip = TUM_BELGELER[i - 2]
                et.configure(cursor="hand2")
                et.bind("<Button-1>", lambda _e, t=tip: self._sutunu_cevir(t))

        govde = tk.Frame(w, bg=PANEL)
        govde.pack(fill="both", expand=True)
        self.tuval = tk.Canvas(govde, bg=PANEL, highlightthickness=0)
        kaydir = tk.Scrollbar(govde, command=self.tuval.yview)
        self.tuval.configure(yscrollcommand=kaydir.set)
        kaydir.pack(side="right", fill="y")
        self.tuval.pack(side="left", fill="both", expand=True)
        self.ic = tk.Frame(self.tuval, bg=PANEL)
        self.tuval.create_window((0, 0), window=self.ic, anchor="nw")
        self.ic.bind("<Configure>", lambda _e: self.tuval.configure(scrollregion=self.tuval.bbox("all")))
        for i, g in enumerate(self.GENISLIK):
            self.ic.grid_columnconfigure(i, minsize=g)

        self.satirlar = []
        for r, f in enumerate(firmalar):
            ad = tk.Label(self.ic, text=f["ad"], font=GOVDE, fg=YAZI, bg=PANEL, anchor="w", cursor="hand2")
            ad.bind("<Button-1>", lambda _e, i=r: self._satiri_cevir(i))
            dev = tk.StringVar(value=f["devreden"])
            kutu = giris_kutusu(self.ic, dev, genislik=10)
            secim = {t: tk.BooleanVar(value=t in f["ekranlar"]) for t in TUM_BELGELER}
            isaretler = [tk.Checkbutton(self.ic, variable=secim[t], bg=PANEL, activebackground=PANEL,
                                        fg=YAZI, activeforeground=YAZI, selectcolor=KUTU,
                                        highlightthickness=0, bd=0)
                         for t in TUM_BELGELER]
            self.satirlar.append({"ad": f["ad"], "dev": dev, "secim": secim,
                                  "widgetlar": [ad, kutu] + isaretler})
        self._suz()
        w.bind_all("<MouseWheel>", self._tekerlek)
        w.bind_all("<Button-4>", lambda _e: self.tuval.yview_scroll(-3, "units"))
        w.bind_all("<Button-5>", lambda _e: self.tuval.yview_scroll(3, "units"))
        w.bind("<Destroy>", self._kapandi)

    def _tekerlek(self, e):
        self.tuval.yview_scroll(int(-e.delta / 120) * 3, "units")

    def _kapandi(self, e):
        if e.widget is self.w:
            for olay in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                self.w.unbind_all(olay)

    def gorunen(self):
        ara = sadelestir(self.v_ara.get())
        return [s for s in self.satirlar if ara in sadelestir(s["ad"])]

    def _suz(self):
        for s in self.satirlar:
            for wdg in s["widgetlar"]:
                wdg.grid_forget()
        for r, s in enumerate(self.gorunen()):
            for c, wdg in enumerate(s["widgetlar"]):
                wdg.grid(row=r, column=c, sticky="w" if c < 2 else "", padx=(8 if c == 0 else 2, 2), pady=2)
        self.tuval.yview_moveto(0)

    def _sutunu_cevir(self, tip):
        gorunen = self.gorunen()
        yeni = not all(s["secim"][tip].get() for s in gorunen)
        for s in gorunen:
            s["secim"][tip].set(yeni)

    def _satiri_cevir(self, i):
        secim = self.satirlar[i]["secim"]
        yeni = not all(v.get() for v in secim.values())
        for v in secim.values():
            v.set(yeni)

    def secimler(self):
        return [{"ad": s["ad"], "devreden": s["dev"].get().strip(),
                 "ekranlar": {t for t, v in s["secim"].items() if v.get()}} for s in self.satirlar]

    def kaydet(self):
        try:
            firma_tablosu.tabloyu_yaz(self.yol, self.secimler())
        except PermissionError:
            messagebox.showerror("Kaydedilemedi", f"{self.yol.name} Excel'de açık; kapatıp tekrar deneyin.",
                                 parent=self.w)
            return
        except Exception as e:
            messagebox.showerror("Kaydedilemedi", f"{type(e).__name__}: {e}", parent=self.w)
            return
        self.arayuz.gostergeleri_yenile()
        self.w.destroy()


# --- ana pencere ---------------------------------------------------------------

class Arayuz:
    BOT = KOK / "luca_bot.py"

    def __init__(self, kok):
        self.kok = kok
        self.surec = None
        self.okuyucu = None
        self.kuyruk = queue.Queue()
        self.yarim_satir = ""
        self.durdurma_istendi = False
        self.gostergeler = {"tevkifat": [], "smm": [], "fark": [], "kdv": []}
        try:
            self.ayarlar = ayarlari_yukle()
        except ValueError as e:
            messagebox.showerror("Ayar dosyası bozuk", f"{e}\n\nDosyayı Not Defteri ile düzeltin.")
            raise SystemExit(1)

        kok.title("Luca Bot — SMMM Adem Yılmaz")
        kok.configure(bg=ZEMIN)
        kok.geometry("1140x780")
        kok.minsize(1020, 720)
        self._stiller()
        self._degiskenler()
        self._baslik()
        govde = tk.Frame(kok, bg=ZEMIN)
        govde.pack(fill="both", expand=True)
        self._sol_panel(govde)
        tk.Frame(govde, bg=CIZGI, width=1).pack(side="left", fill="y")
        self._sag_panel(govde)
        self._giris_ozetini_yaz()
        self.gostergeleri_yenile()
        kok.protocol("WM_DELETE_WINDOW", self.kapat)
        self.dongu_id = kok.after(100, self._dongu)

    # -- kurulum ---------------------------------------------------------------

    def _stiller(self):
        s = ttk.Style(self.kok)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure("Altin.Horizontal.TProgressbar", troughcolor="#1B2944", background=ALTIN,
                    bordercolor="#1B2944", lightcolor=ALTIN, darkcolor=ALTIN, thickness=8)
        s.configure("Liste.Treeview", background=PANEL, fieldbackground=PANEL, foreground=YAZI,
                    rowheight=26, font=GOVDE, bordercolor=CIZGI)
        s.configure("Liste.Treeview.Heading", background=KUTU, foreground=ALTIN, font=BOLUM,
                    relief="flat")
        s.map("Liste.Treeview", background=[("selected", "#2A3A5C")])

    def _degiskenler(self):
        a = self.ayarlar
        vars_bas, vars_bit = gecen_ay()
        self.v_bas = tk.StringVar(value=a.get("baslangic_tarihi") or vars_bas)
        self.v_bit = tk.StringVar(value=a.get("bitis_tarihi") or vars_bit)
        self.v_liste = tk.StringVar(value=a.get("firma_listesi") or "")
        self.v_firma = tk.StringVar()
        self.v_devam = tk.BooleanVar(value=True)
        secili = set(a.get("arayuz_ekranlar") or TUM_BELGELER)
        self.v_ekran = {t: tk.BooleanVar(value=t in secili) for t in TUM_BELGELER}
        self.v_hepsi = tk.BooleanVar(value=all(v.get() for v in self.v_ekran.values()))

    def _baslik(self):
        b = tk.Frame(self.kok, bg=BASLIK_ZEMIN, height=74)
        b.pack(fill="x")
        b.pack_propagate(False)
        sol = tk.Frame(b, bg=BASLIK_ZEMIN)
        sol.pack(side="left", padx=22)
        logo(sol).pack(side="left", pady=14)
        yazi = tk.Frame(sol, bg=BASLIK_ZEMIN)
        yazi.pack(side="left", padx=12)
        tk.Label(yazi, text="SMMM Adem Yılmaz", font=SERIF, fg="#F2F4F8", bg=BASLIK_ZEMIN).pack(anchor="w")
        tk.Label(yazi, text="SERBEST MUHASEBECİ MALİ MÜŞAVİR", font=("Segoe UI", 8, "bold"),
                 fg=ALTIN, bg=BASLIK_ZEMIN).pack(anchor="w")
        sag = tk.Frame(b, bg=BASLIK_ZEMIN)
        sag.pack(side="right", padx=22)
        site = tk.Label(sag, text="smmmyilmaz.com", font=KUCUK, fg=ALTIN, bg=BASLIK_ZEMIN, cursor="hand2")
        site.pack(side="right", padx=(12, 0))
        site.bind("<Button-1>", lambda _e: webbrowser.open("https://smmmyilmaz.com"))
        self.durum_etiketi = tk.Label(sag, text="  Hazır  ", font=("Segoe UI", 9, "bold"),
                                      fg="#FFFFFF", bg=YESIL, padx=6, pady=2)
        self.durum_etiketi.pack(side="right", padx=(12, 0))
        tk.Label(sag, text="Luca Bot · e-Fatura / e-Arşiv Otomatik İndirme", font=KUCUK,
                 fg=ETIKET, bg=BASLIK_ZEMIN).pack(side="right")
        tk.Frame(self.kok, bg=CIZGI, height=1).pack(fill="x")

    def _sol_panel(self, govde):
        p = tk.Frame(govde, bg=ZEMIN, width=330, padx=22, pady=16)
        p.pack(side="left", fill="y")
        p.pack_propagate(False)

        bolum_basligi(p, "Luca Girişi").pack(fill="x")
        satir = tk.Frame(p, bg=ZEMIN)
        satir.pack(fill="x", pady=(6, 14))
        self.giris_ozeti = tk.Label(satir, text="", font=GOVDE, fg=YAZI, bg=ZEMIN, anchor="w",
                                    justify="left")
        self.giris_ozeti.pack(side="left", fill="x", expand=True)
        dugme(satir, "Değiştir", self.giris_penceresi).pack(side="right")

        bolum_basligi(p, "Firma Listesi").pack(fill="x")
        self.liste_etiketi = tk.Label(p, text="", font=KUCUK, fg=ETIKET, bg=KUTU, anchor="w",
                                      padx=8, pady=6, highlightthickness=1, highlightbackground=KENAR)
        self.liste_etiketi.pack(fill="x", pady=(6, 6))
        iki = tk.Frame(p, bg=ZEMIN)
        iki.pack(fill="x")
        dugme(iki, "Liste Yükle…", self.liste_sec).pack(side="left", fill="x", expand=True, padx=(0, 6))
        dugme(iki, "Şablon İndir", self.sablon_indir).pack(side="left", fill="x", expand=True)
        dugme(p, "Firma / Ekran Seçimi…", self.firma_ekran_penceresi).pack(fill="x", pady=(6, 0))
        tk.Label(p, text="Sadece bu firma (boş = listedeki hepsi)", font=KUCUK, fg=ETIKET,
                 bg=ZEMIN, anchor="w").pack(fill="x", pady=(10, 3))
        giris_kutusu(p, self.v_firma).pack(fill="x", ipady=4)
        self._liste_etiketini_yaz()

        bolum_basligi(p, "Tarih Aralığı").pack(fill="x", pady=(16, 0))
        t = tk.Frame(p, bg=ZEMIN)
        t.pack(fill="x", pady=(6, 0))
        for i, (ad, v) in enumerate((("Başlangıç", self.v_bas), ("Bitiş", self.v_bit))):
            k = tk.Frame(t, bg=ZEMIN)
            k.grid(row=0, column=i, sticky="ew", padx=(0, 8) if i == 0 else 0)
            tk.Label(k, text=ad, font=KUCUK, fg=ETIKET, bg=ZEMIN, anchor="w").pack(fill="x")
            e = giris_kutusu(k, v, genislik=12)
            e.pack(fill="x", ipady=4)
            e.bind("<FocusOut>", lambda _e: self.gostergeleri_yenile())
        t.columnconfigure(0, weight=1)
        t.columnconfigure(1, weight=1)

        bolum_basligi(p, "Ekranlar").pack(fill="x", pady=(16, 4))
        tk.Checkbutton(p, text="Hepsini Seç", variable=self.v_hepsi, command=self._hepsi_degisti,
                       font=GOVDE_KALIN, **self._kutu_renk()).pack(anchor="w")
        tk.Frame(p, bg=CIZGI, height=1).pack(fill="x", pady=4)
        g = tk.Frame(p, bg=ZEMIN)
        g.pack(fill="x")
        for i, tip in enumerate(TUM_BELGELER):
            tk.Checkbutton(g, text=EKRAN_ADLARI.get(tip, tip), variable=self.v_ekran[tip],
                           command=self._ekran_degisti, font=GOVDE, **self._kutu_renk()
                           ).grid(row=i // 2, column=i % 2, sticky="w")
        tk.Checkbutton(p, text="Bugün bitenleri atla (kaldığı yerden)", variable=self.v_devam,
                       font=KUCUK, **self._kutu_renk()).pack(anchor="w", pady=(12, 0))

        alt = tk.Frame(p, bg=ZEMIN)
        alt.pack(side="bottom", fill="x")
        self.calistir_dugmesi = dugme(alt, "Çalıştır", self.calistir, ana=True)
        self.calistir_dugmesi.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.durdur_dugmesi = dugme(alt, "Durdur", self.durdur, state="disabled")
        self.durdur_dugmesi.pack(side="left", fill="x", expand=True)

    @staticmethod
    def _kutu_renk():
        return dict(bg=ZEMIN, fg=YAZI, selectcolor=KUTU, activebackground=ZEMIN,
                    activeforeground=YAZI, highlightthickness=0, bd=0, anchor="w")

    def _sag_panel(self, govde):
        p = tk.Frame(govde, bg=ZEMIN, padx=22, pady=16)
        p.pack(side="left", fill="both", expand=True)

        ust = tk.Frame(p, bg=ZEMIN)
        ust.pack(fill="x")
        self.ilerleme_etiketi = tk.Label(ust, text="Hazır. Ayarları kontrol edip Çalıştır'a basın.",
                                         font=GOVDE_KALIN, fg=YAZI, bg=ZEMIN, anchor="w")
        self.ilerleme_etiketi.pack(side="left")
        self.kalan_etiketi = tk.Label(ust, text="", font=KUCUK, fg=SOLUK, bg=ZEMIN)
        self.kalan_etiketi.pack(side="right")
        self.ilerleme = ttk.Progressbar(p, style="Altin.Horizontal.TProgressbar", maximum=100)
        self.ilerleme.pack(fill="x", pady=(8, 12))

        # alt kisim once yerlestirilir ki log alani kalan yeri doldursun
        alt = tk.Frame(p, bg=ZEMIN)
        alt.pack(side="bottom", fill="x", pady=(10, 0))
        dugme(alt, "Rapor Dosyasını Aç", self.raporu_ac).pack(side="left")
        dugme(alt, "İndirilenler Klasörü", self.klasoru_ac).pack(side="left", padx=8)
        self.durum_yazisi = tk.Label(alt, text="", font=KUCUK, fg=SOLUK, bg=ZEMIN)
        self.durum_yazisi.pack(side="right")

        kutular = tk.Frame(p, bg=ZEMIN)
        kutular.pack(side="bottom", fill="x", pady=(10, 0))
        self.donem_etiketi = tk.Label(kutular, text="", font=KUCUK, fg=SOLUK, bg=ZEMIN, anchor="w")
        self.donem_etiketi.pack(fill="x", pady=(0, 6))
        sira = tk.Frame(kutular, bg=ZEMIN)
        sira.pack(fill="x")
        self.kutu = {
            "tevkifat": OzetKutusu(sira, "Alış Tevkifat KDV", lambda: self.detay("tevkifat")),
            "smm": OzetKutusu(sira, "Alış SMM", lambda: self.detay("smm")),
            "fark": OzetKutusu(sira, "İnteraktif Farkı", lambda: self.detay("fark"), TURUNCU),
            "kdv": OzetKutusu(sira, "KDV Ödemesi Çıkabilir", lambda: self.detay("kdv"), KIRMIZI),
        }
        for i, k in enumerate(self.kutu.values()):
            k.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            sira.columnconfigure(i, weight=1, uniform="kutu")

        cerceve = tk.Frame(p, bg=KONSOL, highlightthickness=1, highlightbackground="#1B2944")
        cerceve.pack(fill="both", expand=True)
        self.log = tk.Text(cerceve, bg=KONSOL, fg="#CBD2DE", font=KONSOL_YAZI, relief="flat",
                           wrap="none", padx=12, pady=10, insertbackground=YAZI, state="disabled",
                           highlightthickness=0, bd=0)
        kaydir = tk.Scrollbar(cerceve, command=self.log.yview, bg=KONSOL, troughcolor=KONSOL,
                              activebackground=KENAR, relief="flat", bd=0)
        self.log.configure(yscrollcommand=kaydir.set)
        kaydir.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)
        for etiket, renk in (("ok", "#8CE59A"), ("uyari", "#F2D98A"), ("soluk", "#7F8BA3"),
                             ("hata", KIRMIZI), ("firma", ALTIN_ACIK), ("bilgi", "#9AA6BD")):
            self.log.tag_configure(etiket, foreground=renk)

    # -- ayarlar ---------------------------------------------------------------

    def _giris_ozetini_yaz(self):
        a = self.ayarlar
        if a.get("uye_no") and a.get("kullanici_adi") and a.get("parola"):
            self.giris_ozeti.configure(text=f"{a['kullanici_adi']}  (üye {a['uye_no']})", fg=YAZI)
        else:
            self.giris_ozeti.configure(text="Giriş bilgisi girilmedi", fg=TURUNCU)

    def _liste_etiketini_yaz(self):
        yol = self.v_liste.get()
        self.liste_etiketi.configure(text=Path(yol).name if yol else "Seçilmedi (tüm Luca firmaları)")

    def giris_penceresi(self):
        w = tk.Toplevel(self.kok, bg=ZEMIN, padx=24, pady=20)
        w.title("Luca Giriş Bilgileri")
        w.transient(self.kok)
        w.resizable(False, False)
        alanlar = [("Üye No", "uye_no", False), ("Kullanıcı Adı", "kullanici_adi", False),
                   ("Parola", "parola", True),
                   ("Doğrulama Anahtarı (iki aşamalı giriş, isteğe bağlı)", "dogrulama_anahtari", True)]
        degerler = {}
        for ad, anahtar, gizli in alanlar:
            tk.Label(w, text=ad, font=KUCUK, fg=ETIKET, bg=ZEMIN, anchor="w").pack(fill="x", pady=(8, 3))
            degerler[anahtar] = tk.StringVar(value=str(self.ayarlar.get(anahtar) or ""))
            giris_kutusu(w, degerler[anahtar], gizli=gizli, genislik=38).pack(fill="x", ipady=4)
        tk.Label(w, text="Bilgiler bu bilgisayardaki ayarlar.json dosyasına kaydedilir.",
                 font=KUCUK, fg=SOLUK, bg=ZEMIN).pack(anchor="w", pady=(12, 0))

        def kaydet():
            for anahtar, v in degerler.items():
                self.ayarlar[anahtar] = v.get().strip() if anahtar != "parola" else v.get()
            ayarlari_kaydet(self.ayarlar)
            self._giris_ozetini_yaz()
            w.destroy()

        alt = tk.Frame(w, bg=ZEMIN)
        alt.pack(fill="x", pady=(16, 0))
        dugme(alt, "Kaydet", kaydet, ana=True).pack(side="right")
        dugme(alt, "Vazgeç", w.destroy).pack(side="right", padx=8)
        w.grab_set()

    def liste_sec(self):
        yol = filedialog.askopenfilename(title="Firma listesi (firmalar.xlsx)", initialdir=str(KOK),
                                         filetypes=[("Excel", "*.xlsx"), ("Tüm dosyalar", "*.*")])
        if not yol:
            return
        self._listeyi_ayarla(yol)

    def _liste_tam_yolu(self):
        yol = self.v_liste.get().strip()
        if not yol:
            return None
        p = Path(yol)
        return p if p.is_absolute() else KOK / p

    def sablon_indir(self):
        yol = filedialog.asksaveasfilename(
            title="Firma listesi şablonu", initialdir=str(KOK), initialfile="firmalar-sablon.xlsx",
            defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")], parent=self.kok)
        if not yol:
            return
        try:  # daha once islenen firmalar varsa sablon onlarla dolu gelsin
            firmalar = sorted(json.loads(self.rapor_yolu().read_text(encoding="utf-8")))
        except (OSError, ValueError):
            firmalar = []
        try:
            firma_tablosu.sablon_olustur(yol, firmalar)
        except PermissionError:
            messagebox.showerror("Kaydedilemedi", "Dosya Excel'de açık; kapatıp tekrar deneyin.",
                                 parent=self.kok)
            return
        if messagebox.askyesno(
                "Şablon indi",
                f"{Path(yol).name} kaydedildi"
                + (f" ({len(firmalar)} firma, daha önce işlenenler)" if firmalar else "") + ".\n\n"
                "Ekran sütunlarında ✓ = sorgulanır, X = sorgulanmaz.\n"
                "Bu dosya firma listesi olarak seçilsin ve Excel'de açılsın mı?", parent=self.kok):
            self._listeyi_ayarla(yol)
            dosya_ac(yol)

    def _listeyi_ayarla(self, yol):
        p = Path(yol)
        try:
            yol = str(p.relative_to(KOK))
        except ValueError:
            yol = str(p)
        self.v_liste.set(yol)
        self.ayarlar["firma_listesi"] = yol
        ayarlari_kaydet(self.ayarlar)
        self._liste_etiketini_yaz()
        self.gostergeleri_yenile()

    def firma_ekran_penceresi(self):
        yol = self._liste_tam_yolu()
        if not yol or not yol.exists():
            messagebox.showinfo("Firma listesi yok", "Önce 'Liste Yükle' ile firmalar.xlsx'i seçin ya da"
                                " 'Şablon İndir' ile yeni bir liste oluşturun.", parent=self.kok)
            return
        try:
            firmalar = firma_tablosu.tabloyu_oku(yol)
        except Exception as e:
            messagebox.showerror("Okunamadı", f"{yol.name} okunamadı: {e}", parent=self.kok)
            return
        return FirmaEkranPenceresi(self, yol, firmalar)

    def _hepsi_degisti(self):
        for v in self.v_ekran.values():
            v.set(self.v_hepsi.get())

    def _ekran_degisti(self):
        self.v_hepsi.set(all(v.get() for v in self.v_ekran.values()))

    # -- calistirma --------------------------------------------------------------

    def komut(self):
        """luca_bot.py komutu; hata varsa ValueError (kullaniciya gosterilir)."""
        bas, bit = self.v_bas.get().strip(), self.v_bit.get().strip()
        try:
            if tarih_cozumle(bit) < tarih_cozumle(bas):
                raise ValueError("Bitiş tarihi başlangıçtan önce olamaz.")
        except ValueError as e:
            if "olamaz" in str(e):
                raise
            raise ValueError("Tarihleri GG/AA/YYYY biçiminde yazın (örnek 01/09/2026).")
        secili = [t for t in TUM_BELGELER if self.v_ekran[t].get()]
        if not secili:
            raise ValueError("En az bir ekran seçin.")
        komut = [python_komutu(), "-u", str(self.BOT), "--bitince-kapat",
                 "--baslangic", bas, "--bitis", bit]
        if len(secili) == len(TUM_BELGELER):
            komut.append("--hepsi")
        else:
            for t in secili:
                komut += ["--belge-tipi", t]
        if self.v_firma.get().strip():
            komut += ["--firma", self.v_firma.get().strip()]
        if not self.v_devam.get():
            komut.append("--bastan")
        return komut

    def calistir(self):
        if self.surec:
            return
        a = self.ayarlar
        if not (a.get("uye_no") and a.get("kullanici_adi") and a.get("parola")):
            messagebox.showwarning("Giriş bilgisi eksik",
                                   "Program Luca'ya kendisi girer; önce Üye No, Kullanıcı Adı ve"
                                   " Parola'yı girin.", parent=self.kok)
            self.giris_penceresi()
            return
        try:
            komut = self.komut()
        except ValueError as e:
            messagebox.showwarning("Kontrol edin", str(e), parent=self.kok)
            return
        a["baslangic_tarihi"], a["bitis_tarihi"] = self.v_bas.get().strip(), self.v_bit.get().strip()
        a["firma_listesi"] = self.v_liste.get()
        a["arayuz_ekranlar"] = [t for t in TUM_BELGELER if self.v_ekran[t].get()]
        ayarlari_kaydet(a)

        ortam = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        bayrak = 0
        if sys.platform.startswith("win"):
            # ayri surec grubu: "Durdur"daki CTRL_BREAK yalnizca bota gitsin. Konsol
            # paylasilmali (CREATE_NO_WINDOW olmaz), yoksa sinyal ulasmiyor.
            bayrak = subprocess.CREATE_NEW_PROCESS_GROUP
        self._log_temizle()
        self._log_ekle("Başlatılıyor…\n", "bilgi")
        try:
            self.surec = subprocess.Popen(komut, cwd=str(KOK), env=ortam, stdin=subprocess.DEVNULL,
                                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                          bufsize=0, creationflags=bayrak)
        except OSError as e:
            messagebox.showerror("Başlatılamadı", f"Program başlatılamadı: {e}", parent=self.kok)
            return
        self.durdurma_istendi = False
        self.yarim_satir = ""
        self.okuyucu = threading.Thread(target=self._oku, args=(self.surec,), daemon=True)
        self.okuyucu.start()
        self.ilerleme.configure(value=0)
        self.ilerleme_etiketi.configure(text="Luca'ya giriş yapılıyor…")
        self.kalan_etiketi.configure(text="")
        self._durum("Çalışıyor", ALTIN, ALTIN_YAZI)
        self.calistir_dugmesi.configure(state="disabled")
        self.durdur_dugmesi.configure(state="normal", text="Durdur")

    def _oku(self, surec):
        cozucu = codecs.getincrementaldecoder("utf-8")(errors="replace")
        while True:
            parca = surec.stdout.read(4096)
            if not parca:
                break
            self.kuyruk.put(cozucu.decode(parca))
        self.kuyruk.put(cozucu.decode(b"", final=True))

    def durdur(self):
        if not self.surec:
            return
        if self.durdurma_istendi:
            if messagebox.askyesno("Zorla kapat", "Program hâlâ kapanmadı. Zorla kapatılsın mı?\n"
                                   "(Son firmanın sonucu kaydedilmemiş olabilir.)", parent=self.kok):
                self.surec.kill()
            return
        self.durdurma_istendi = True
        try:
            if sys.platform.startswith("win"):
                self.surec.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                self.surec.send_signal(signal.SIGINT)
        except OSError:
            self.surec.kill()  # sinyal gonderilemiyorsa (konsol yok) en azindan kapansin
        self._log_ekle("\nDurduruluyor… o ana kadarki sonuçlar kaydediliyor.\n", "uyari")
        self.durdur_dugmesi.configure(text="Zorla Kapat")

    def _dongu(self):
        metin = ""
        try:
            while True:
                metin += self.kuyruk.get_nowait()
        except queue.Empty:
            pass
        if metin:
            self._metni_isle(metin)
        # surec bittiginde borudaki son satirlar da okunmus olmali
        if (self.surec and self.surec.poll() is not None and not self.okuyucu.is_alive()
                and self.kuyruk.empty()):
            self._bitti(self.surec.returncode)
        self.dongu_id = self.kok.after(150, self._dongu)

    def _metni_isle(self, metin):
        satirlar = (self.yarim_satir + metin.replace("\r\n", "\n")).split("\n")
        self.yarim_satir = satirlar.pop()
        for satir in satirlar:
            self._satir(satir)

    def _satir(self, satir):
        sade = satir.strip()
        m = ILERLEME.match(sade)
        etiket = None
        if m:
            sira, toplam = int(m.group(1)), int(m.group(2))
            self.ilerleme_etiketi.configure(text=f"İşleniyor: {m.group(3)}  ({sira} / {toplam} firma)")
            self.kalan_etiketi.configure(text=f"Tahmini kalan: {m.group(4)}" if m.group(4) else "")
            self.ilerleme.configure(value=(sira - 1) * 100 / max(toplam, 1))
            self.gostergeleri_yenile()  # bir onceki firma rapora yazildi
            etiket = "firma"
        elif "[OK]" in sade:
            etiket = "ok"
        elif "[!!]" in sade or sade.startswith(("DIKKAT", "UYARI")) or "UYARI:" in sade:
            etiket = "uyari"
        elif "[--]" in sade or set(sade) <= set("=-") and sade:
            etiket = "soluk"
        elif "HATA" in sade:
            etiket = "hata"
        elif sade.startswith("Luca'da") or "LUCA GIRIS" in sade:
            self.ilerleme_etiketi.configure(text="Firma listesi okunuyor…")
        self._log_ekle(satir + "\n", etiket)

    def _bitti(self, kod):
        if self.yarim_satir:
            self._satir(self.yarim_satir)
            self.yarim_satir = ""
        self.surec.stdout.close()
        self.surec = None
        self.calistir_dugmesi.configure(state="normal")
        self.durdur_dugmesi.configure(state="disabled", text="Durdur")
        self.gostergeleri_yenile()
        if kod == 0 and not self.durdurma_istendi:
            self.ilerleme.configure(value=100)
            self.ilerleme_etiketi.configure(text="Tamamlandı. Rapor güncellendi.")
            self._durum("Tamamlandı", YESIL, "#FFFFFF")
        elif self.durdurma_istendi or kod in (130, -2):
            self.ilerleme_etiketi.configure(text="Durduruldu. Yeniden Çalıştır'a basınca kaldığı yerden sürer.")
            self._durum("Durduruldu", TURUNCU, ALTIN_YAZI)
        else:
            self.ilerleme_etiketi.configure(text="Hata ile bitti — log'un sonuna bakın.")
            self._durum("Hata", "#B3443A", "#FFFFFF")

    def _durum(self, metin, zemin, yazi):
        self.durum_etiketi.configure(text=f"  {metin}  ", bg=zemin, fg=yazi)

    # -- log ---------------------------------------------------------------------

    def _log_ekle(self, metin, etiket=None):
        alttaydi = self.log.yview()[1] >= 0.999
        self.log.configure(state="normal")
        self.log.insert("end", metin, (etiket,) if etiket else ())
        fazla = int(self.log.index("end-1c").split(".")[0]) - AZAMI_SATIR
        if fazla > 0:
            self.log.delete("1.0", f"{fazla + 1}.0")
        self.log.configure(state="disabled")
        if alttaydi:
            self.log.see("end")

    def _log_temizle(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def log_metni(self):
        return self.log.get("1.0", "end-1c")

    # -- ozet kutulari ------------------------------------------------------------

    def secili_donem(self):
        try:
            bas, bit = hedef_ay_araligi(tarih_cozumle(self.v_bas.get().strip()),
                                        tarih_cozumle(self.v_bit.get().strip()))
        except ValueError:
            return None
        return f"{bas:{TARIH_BICIMI}}-{bit:{TARIH_BICIMI}}"

    def rapor_yolu(self):
        return indirme_koku(self.ayarlar) / "rapor.json"

    def gostergeleri_yenile(self):
        donem = self.secili_donem()
        try:
            kayitlar = json.loads(self.rapor_yolu().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            kayitlar = {}
        try:
            devreden = devreden_kdvleri(self.v_liste.get())
        except Exception:
            devreden = {}
        self.gostergeler = gostergeler.hesapla(kayitlar, devreden, donem)
        t = gostergeler.toplamlar(self.gostergeler)
        tl = gostergeler.tl
        self.kutu["tevkifat"].ayarla(tl(t["tevkifat"]), f"{t['tevkifat_adet']} fatura · Firmaları gör ›")
        self.kutu["smm"].ayarla(tl(t["smm"]), f"{t['smm_adet']} makbuz · Firmaları gör ›")
        self.kutu["fark"].ayarla(f"{t['fark']} fatura")
        self.kutu["kdv"].ayarla(f"{t['kdv_firma']} firma")
        if donem:
            bas, bit = donem.split("-")
            self.donem_etiketi.configure(text=f"Dönem özeti: {bas} – {bit}   (iptal/itiraz edilen"
                                              " faturalar tutarlara dahil değildir)")

    def detay(self, tur):
        tl = gostergeler.tl
        g = self.gostergeler[tur]
        if tur == "tevkifat":
            baslik = "Alış Tevkifat KDV — firmalar"
            sutunlar = ("Firma", "Fatura", "Tevkifat KDV")
            satirlar = [(x["firma"], x["adet"], tl(x["tutar"]) + (" *" if x["tahmini"] else ""))
                        for x in g]
            toplam = ("Toplam", sum(x["adet"] for x in g), tl(sum(x["tutar"] for x in g)))
            notlar = []
            if any(x["tahmini"] for x in g):
                notlar.append("* Excel'de tevkifat tutarı sütunu bulunamadı; faturanın KDV'si"
                              " gösterildi (tevkif edilen kısım orana göre bundan azdır).")
            notlar.append("KDV2 için: iptal/itiraz edilen tevkifatlı faturalar da sayıya dahildir,"
                          " tutara dahil değildir.")
        elif tur == "smm":
            baslik = "Alış SMM — firmalar"
            sutunlar = ("Firma", "Makbuz", "Tutar")
            satirlar = [(x["firma"], x["adet"], tl(x["tutar"])) for x in g]
            toplam = ("Toplam", sum(x["adet"] for x in g), tl(sum(x["tutar"] for x in g)))
            notlar = []
        elif tur == "fark":
            baslik = "İnteraktif V.D. − e-Arşiv Alış farkı"
            sutunlar = ("Firma", "İnteraktif", "e-Arşiv Alış", "Fark")
            satirlar = [(x["firma"], x["interaktif"], x["earsiv"],
                         f"{x['fark']:+d}  ({'e-Arşiv’de eksik' if x['fark'] > 0 else 'e-Arşiv’de fazla'})")
                        for x in g]
            toplam = ("Toplam", sum(x["interaktif"] for x in g), sum(x["earsiv"] for x in g),
                      f"{sum(abs(x['fark']) for x in g)} fatura")
            notlar = ["Hangi faturaların eksik olduğu rapor.xlsx › İndirilen Faturalar sayfasında yazar."]
        else:
            baslik = "KDV ödemesi çıkabilecek firmalar"
            sutunlar = ("Firma", "Satış KDV", "Alış KDV", "Devreden", "Tahmini Ödeme")
            satirlar = [(x["firma"], tl(x["satis"]), tl(x["alis"]),
                         tl(x["devreden"]) if x["devreden"] is not None else "girilmedi",
                         tl(x["odeme"])) for x in g]
            toplam = ("Toplam", "", "", "", tl(sum(x["odeme"] for x in g)))
            notlar = ["Tahmini: Satış KDV − Alış KDV − Devreden KDV (iptaller hariç). Diğer beyan"
                      " kalemleri hesaba girmez; kesin tutar değil, uyarıdır.",
                      "Devreden KDV, firma listesindeki \"Devreden KDV\" sütunundan okunur;"
                      " boşsa 0 sayılır."]
        self._detay_penceresi(baslik, sutunlar, satirlar, toplam, notlar)

    def _detay_penceresi(self, baslik, sutunlar, satirlar, toplam, notlar):
        w = tk.Toplevel(self.kok, bg=ZEMIN, padx=20, pady=16)
        w.title(baslik)
        w.transient(self.kok)
        w.geometry(f"{240 + 140 * len(sutunlar)}x460")
        tk.Label(w, text=baslik, font=("Georgia", 14, "bold"), fg="#F2F4F8", bg=ZEMIN,
                 anchor="w").pack(fill="x")
        donem = self.secili_donem()
        if donem:
            tk.Label(w, text=f"Dönem: {donem.replace('-', ' – ')}", font=KUCUK, fg=SOLUK, bg=ZEMIN,
                     anchor="w").pack(fill="x", pady=(2, 10))
        alt = tk.Frame(w, bg=ZEMIN)
        alt.pack(side="bottom", fill="x", pady=(10, 0))
        for n in notlar:
            tk.Label(w, text=n, font=KUCUK, fg=SOLUK, bg=ZEMIN, anchor="w", justify="left",
                     wraplength=700).pack(side="bottom", fill="x", pady=(4, 0))
        agac = ttk.Treeview(w, columns=sutunlar, show="headings", style="Liste.Treeview")
        for i, s in enumerate(sutunlar):
            agac.heading(s, text=s, anchor="w" if i == 0 else "e")
            agac.column(s, anchor="w" if i == 0 else "e", width=240 if i == 0 else 130,
                        stretch=i == 0)
        agac.tag_configure("toplam", foreground=ALTIN, font=GOVDE_KALIN)
        if not satirlar:
            agac.insert("", "end", values=("Bu dönemde kayıt yok",) + ("",) * (len(sutunlar) - 1))
        for s in satirlar:
            agac.insert("", "end", values=s)
        if satirlar:
            agac.insert("", "end", values=toplam, tags=("toplam",))
        agac.pack(fill="both", expand=True)

        def excele_indir():
            ad = re.sub(r"[^\w-]+", "-", sadelestir(baslik.split("—")[0]).lower()).strip("-")
            yol = filedialog.asksaveasfilename(
                title="Excel olarak kaydet", parent=w, defaultextension=".xlsx",
                initialdir=str(indirme_koku(self.ayarlar)),
                initialfile=f"{ad}-{(donem or '').replace('/', '.')}.xlsx",
                filetypes=[("Excel", "*.xlsx")])
            if not yol:
                return
            try:
                liste_excel_yaz(yol, baslik, donem, sutunlar, satirlar, toplam, notlar)
            except PermissionError:
                messagebox.showerror("Kaydedilemedi", "Dosya Excel'de açık; kapatıp tekrar deneyin.",
                                     parent=w)
                return
            dosya_ac(yol)

        dugme(alt, "Kapat", w.destroy).pack(side="right")
        dugme(alt, "Excel olarak indir", excele_indir, ana=True).pack(side="right", padx=8)

    # -- dosyalar / kapanis -------------------------------------------------------

    def raporu_ac(self):
        yol = indirme_koku(self.ayarlar) / "rapor.xlsx"
        if not yol.exists():
            messagebox.showinfo("Rapor yok", "Henüz rapor oluşmadı; önce bir çalıştırma yapın.",
                                parent=self.kok)
            return
        dosya_ac(yol)

    def klasoru_ac(self):
        dosya_ac(indirme_koku(self.ayarlar))

    def kapat(self):
        if self.surec:
            if not messagebox.askyesno("Çalışma sürüyor", "Program çalışıyor. Durdurup çıkılsın mı?",
                                       parent=self.kok):
                return
            self.durdur()
            try:
                self.surec.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.surec.kill()
        self.kok.after_cancel(self.dongu_id)
        self.kok.destroy()


def main():
    if sys.platform.startswith("win"):
        try:  # yuksek cozunurluklu ekranlarda bulanik yazi olmasin
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    kok = tk.Tk()
    try:
        Arayuz(kok)
        kok.mainloop()
    except SystemExit:
        raise
    except Exception:
        import traceback
        hata = traceback.format_exc()
        (KOK / "arayuz-hata.log").write_text(hata, encoding="utf-8")
        messagebox.showerror("Beklenmeyen hata", f"{hata[-1500:]}\n\nAyrıntı: arayuz-hata.log")
        raise


if __name__ == "__main__":
    main()
