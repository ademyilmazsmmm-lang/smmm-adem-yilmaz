# -*- coding: utf-8 -*-
"""Arayuzdeki tablolar icin ortak bilesen: arama kutusu, sutun filtreleri ve basliga tiklayinca siralama.

Satirlar gosterim metni (ya da sayi) olarak verilir; siralama "1.234,56 TL" gibi Turk bicimli tutarlari
sayi, tarihleri tarih, digerlerini Turkce harf farkini yok sayarak metin olarak karsilastirir.
Satirin kimligi (iid) listedeki sirasidir; filtre/siralama sonrasinda da ayni kalir, boylece
`secili_indeksler()` her zaman verilen listedeki konumu dondurur.
"""

import re
import tkinter as tk
from datetime import datetime
from tkinter import ttk

from lucabot.ortak import sadelestir

TUMU = "Tümü"
BOS = ("", "—", None)
TUTAR = re.compile(r"^-?[\d.]+(,\d+)?$")
TARIH = re.compile(r"^\d{2}/\d{2}/\d{4}")


def siralama_anahtari(deger):
    """(grup, sayi, metin): bos degerler hep sonda, sayilar sayisal, kalani metin olarak siralanir."""
    if deger in BOS:
        return (3, 0.0, "")
    if isinstance(deger, bool):
        return (1, float(deger), "")
    if isinstance(deger, (int, float)):
        return (0, float(deger), "")
    metin = str(deger).strip()
    sade = re.sub(r"\s*(TL|kâr|zarar|\*)\s*", "", metin).strip()
    if TUTAR.match(sade):
        try:
            return (0, float(sade.replace(".", "").replace(",", ".")), "")
        except ValueError:
            pass
    if TARIH.match(metin):
        try:
            return (1, datetime.strptime(metin[:10], "%d/%m/%Y").toordinal(), metin)
        except ValueError:
            pass
    return (2, 0.0, sadelestir(metin))


class SiralaFiltreTablosu(tk.Frame):
    def __init__(self, ebeveyn, ui, sutunlar, genislik, yazi=(0,), filtreler=(), varsayilan_filtre=None,
                 secim="browse", yatay=False, arama=True, etiketler=None, degisti=None, sabit=0):
        """sutunlar/genislik: baslik ve piksel; yazi: sola yasli sutun numaralari (digerleri saga);
        filtreler: kutu olarak sunulacak sutun adlari; secim: 'browse' (tek) ya da 'extended' (coklu);
        etiketler: {etiket adi: renk} satir renkleri;
        sabit: yatay kaydirmada yerinde kalacak ilk sutun sayisi (yalniz yatay=True; ayri bir tablo olarak cizilir,
        secim ve dikey kaydirma ikisinde birlikte ilerler)."""
        super().__init__(ebeveyn, bg=ui.ZEMIN)
        self.ui = ui
        self.sutunlar = list(sutunlar)
        self.yazi = set(yazi)
        self.satirlar, self.satir_etiketleri = [], []
        self.siralama = None  # (sutun no, azalan mi)
        self.filtre_adlari = list(filtreler)
        self.filtre_degiskenleri = {}
        self.filtre_kutulari = {}
        self.istenen_filtre = dict(varsayilan_filtre or {})
        self.arama_degiskeni = tk.StringVar()
        self.degisti = degisti  # liste her yenilendiginde (filtre/arama/siralama dahil) cagrilir

        ust = tk.Frame(self, bg=ui.ZEMIN)
        ust.pack(fill="x", pady=(0, 6))
        self.sayac = tk.Label(ust, text="", font=ui.KUCUK, fg=ui.SOLUK, bg=ui.ZEMIN)
        self.sayac.pack(side="right")
        tk.Button(ust, text="Temizle", command=self.temizle, relief="flat", bd=0, cursor="hand2", font=ui.KUCUK,
                  bg=ui.PANEL, fg=ui.YAZI, activebackground=ui.HOVER, activeforeground=ui.YAZI,
                  highlightthickness=1, highlightbackground=ui.KENAR, padx=8).pack(side="right", padx=(0, 10))

        if arama:
            tk.Label(ust, text="Ara:", font=ui.KUCUK, fg=ui.ETIKET, bg=ui.ZEMIN).pack(side="left")
            kutu = ui.giris_kutusu(ust, self.arama_degiskeni, genislik=16)
            kutu.pack(side="left", padx=(6, 12), ipady=3)
            self.arama_degiskeni.trace_add("write", lambda *_: self.goster())
        for ad in self.filtre_adlari:
            tk.Label(ust, text=f"{ad}:", font=ui.KUCUK, fg=ui.ETIKET, bg=ui.ZEMIN).pack(side="left")
            degisken = tk.StringVar(value=self.istenen_filtre.get(ad, TUMU))
            kombo = ttk.Combobox(ust, textvariable=degisken, state="readonly", font=ui.KUCUK, width=18,
                                 values=[TUMU])
            kombo.pack(side="left", padx=(6, 12), ipady=2)
            kombo.bind("<<ComboboxSelected>>", lambda _e: self.goster())
            self.filtre_degiskenleri[ad] = degisken
            self.filtre_kutulari[ad] = kombo
        cerceve = tk.Frame(self, bg=ui.ZEMIN)
        cerceve.pack(fill="both", expand=True)
        self.sabit_sayisi = sabit if (yatay and 0 < sabit < len(self.sutunlar)) else 0
        self.sabit_agac = None
        self._esitleniyor = False
        dikey = self.dikey = ttk.Scrollbar(cerceve, orient="vertical", command=self._dikey_kaydir)
        if self.sabit_sayisi:
            self.sabit_agac = ttk.Treeview(cerceve, columns=self.sutunlar[:self.sabit_sayisi], show="headings",
                                           style="Liste.Treeview", selectmode=secim,
                                           yscrollcommand=self._dikey_ayarla)
        self.agac = ttk.Treeview(cerceve, columns=self.sutunlar[self.sabit_sayisi:], show="headings",
                                 style="Liste.Treeview", selectmode=secim, yscrollcommand=self._dikey_ayarla)
        self.agaclar = [a for a in (self.sabit_agac, self.agac) if a is not None]
        if yatay:
            yatay_k = ttk.Scrollbar(self, orient="horizontal", command=self.agac.xview)
            self.agac.configure(xscrollcommand=yatay_k.set)
        for i, (s, g) in enumerate(zip(self.sutunlar, genislik)):
            yon = "w" if i in self.yazi else "e"
            agac = self._agac_of(i)
            agac.heading(s, text=s, anchor=yon, command=lambda i=i: self.sirala(i))
            agac.column(s, anchor=yon, width=g, minwidth=60, stretch=(not yatay and i == 0))
        for etiket, renk in (etiketler or {}).items():
            for agac in self.agaclar:
                agac.tag_configure(etiket, foreground=renk)
        dikey.pack(side="right", fill="y")
        if self.sabit_agac is not None:
            self.sabit_agac.pack(side="left", fill="y")
            tk.Frame(cerceve, bg=ui.KENAR, width=2).pack(side="left", fill="y")  # sabit sutunu ayiran cizgi
            for agac in self.agaclar:
                agac.bind("<<TreeviewSelect>>", lambda _e, a=agac: self._secimi_esitle(a), add="+")
        self.agac.pack(side="left", fill="both", expand=True)
        if yatay:
            yatay_k.pack(fill="x")

    def _agac_of(self, sutun_no):
        return self.sabit_agac if sutun_no < self.sabit_sayisi else self.agac

    def _dikey_kaydir(self, *arg):
        for agac in self.agaclar:
            agac.yview(*arg)

    def _dikey_ayarla(self, ilk, son):
        """Tablolardan biri kayinca (fare tekerlegi dahil) scrollbar ve diger tablo da ayni yere gelir."""
        self.dikey.set(ilk, son)
        for agac in self.agaclar:
            if abs(agac.yview()[0] - float(ilk)) > 1e-6:
                agac.yview_moveto(ilk)

    def _secimi_esitle(self, kaynak):
        if self._esitleniyor:
            return
        self._esitleniyor = True
        try:
            for agac in self.agaclar:
                if agac is not kaynak and tuple(agac.selection()) != tuple(kaynak.selection()):
                    agac.selection_set(list(kaynak.selection()))
        finally:
            self._esitleniyor = False

    # -- veri ----------------------------------------------------------------------------

    def doldur(self, satirlar, etiketler=None):
        """Tum satirlari degistirir; secili filtre/siralama/arama korunur (filtre kutulari yeni degerlerle dolar)."""
        self.satirlar = [tuple(s) for s in satirlar]
        self.satir_etiketleri = list(etiketler) if etiketler else [""] * len(self.satirlar)
        for ad, kombo in self.filtre_kutulari.items():
            i = self.sutunlar.index(ad)
            degerler = sorted({str(s[i]) for s in self.satirlar if s[i] not in BOS}, key=siralama_anahtari)
            kombo.configure(values=[TUMU] + degerler)
            if self.filtre_degiskenleri[ad].get() not in [TUMU] + degerler:
                self.filtre_degiskenleri[ad].set(TUMU)
        self.goster()

    def filtre_ayarla(self, ad, deger):
        if ad in self.filtre_degiskenleri:
            self.filtre_degiskenleri[ad].set(deger)
            self.goster()

    def temizle(self):
        self.arama_degiskeni.set("")
        for d in self.filtre_degiskenleri.values():
            d.set(TUMU)
        self.siralama = None
        self._basliklari_yaz()
        self.goster()

    def _gorunenler(self):
        aranan = sadelestir(self.arama_degiskeni.get())
        secimler = {self.sutunlar.index(ad): d.get() for ad, d in self.filtre_degiskenleri.items()
                    if d.get() != TUMU}
        sonuc = []
        for n, satir in enumerate(self.satirlar):
            if any(str(satir[i]) != v for i, v in secimler.items()):
                continue
            if aranan and aranan not in sadelestir(" ".join(str(h) for h in satir)):
                continue
            sonuc.append(n)
        if self.siralama is not None:
            sutun, azalan = self.siralama
            bos = [n for n in sonuc if self.satirlar[n][sutun] in BOS]
            dolu = [n for n in sonuc if self.satirlar[n][sutun] not in BOS]
            dolu.sort(key=lambda n: siralama_anahtari(self.satirlar[n][sutun]), reverse=azalan)
            sonuc = dolu + bos  # bos degerler hangi yonde olursa olsun sonda
        return sonuc

    def goster(self):
        secili = set(self.secili_indeksler())
        kaydirma = self.agac.yview()[0]
        self._esitleniyor = True  # asagidaki toplu degisiklikte secim esitleme olaylari tetiklenmesin
        for agac in self.agaclar:
            agac.delete(*agac.get_children())
        gorunen = self._gorunenler()
        b = self.sabit_sayisi
        for n in gorunen:
            etiket = (self.satir_etiketleri[n],) if self.satir_etiketleri[n] else ()
            if self.sabit_agac is not None:
                self.sabit_agac.insert("", "end", iid=str(n), values=self.satirlar[n][:b], tags=etiket)
            self.agac.insert("", "end", iid=str(n), values=self.satirlar[n][b:], tags=etiket)
        yeniden = [str(n) for n in gorunen if n in secili]
        if yeniden:
            for agac in self.agaclar:
                agac.selection_set(yeniden)
        self._esitleniyor = False
        try:
            for agac in self.agaclar:
                agac.yview_moveto(kaydirma)
        except tk.TclError:
            pass
        self.sayac.configure(text=f"{len(gorunen)} / {len(self.satirlar)} kayıt")
        if self.degisti:
            self.degisti()

    # -- siralama ------------------------------------------------------------------------

    def sirala(self, sutun):
        """Ayni basliga ikinci tiklama yonu cevirir; ucuncusu siralamayi kaldirir."""
        if self.siralama is None or self.siralama[0] != sutun:
            self.siralama = (sutun, False)
        elif not self.siralama[1]:
            self.siralama = (sutun, True)
        else:
            self.siralama = None
        self._basliklari_yaz()
        self.goster()

    def _basliklari_yaz(self):
        for i, s in enumerate(self.sutunlar):
            ok = ""
            if self.siralama is not None and self.siralama[0] == i:
                ok = " ▼" if self.siralama[1] else " ▲"
            self._agac_of(i).heading(s, text=s + ok)

    # -- secim ---------------------------------------------------------------------------

    def secili_indeksler(self):
        return [int(i) for i in self.agac.selection()]

    def gorunen_indeksler(self):
        return [int(i) for i in self.agac.get_children()]

    def hepsini_sec(self):
        self.agac.selection_set(self.agac.get_children())
