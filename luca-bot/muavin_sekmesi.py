# -*- coding: utf-8 -*-
"""Luca Bot arayuzunun "Muavin" sekmesi: indirilen faturalar Luca muavininde / isletme defterinde var mi?

Repodaki kar-zarar/muavin.py programini arka planda calistirir. 1. sinif (genel muhasebe) firmalar icin Luca'da Muavin
Defter (tum hesaplar), 2. sinif (isletme / serbest meslek defteri) firmalar icin Isletme Defteri Dokumu Excel olarak
indirilir. Fatura Indirme sekmesinin indirdigi alis (191 / gider) ve satis (391 / gelir) faturalari icin FATURA NO ve
GENEL TOPLAM (KDV dahil) tutar kontrol edilir; ikisi de uyuyorsa sorun yoktur. Sorunlu faturalar tarih, fatura no,
unvan/isim, KDV ve KDV dahil tutarla listelenir: "eksik" (numara muavinde/defterde yok) ve "tutar uyusmuyor".
Sonuc kar-zarar/cikti/muavin.json'dan okunur. Kar/Zarar, Defter Beyan ve Fatura indirme ile ayni anda calismaz.
"""

import json
from tkinter import filedialog, messagebox
import tkinter as tk

from kar_zarar_sekmesi import KarZararSekmesi, ayar_hazirla
from lucabot.gostergeler import tl
from lucabot.ortak import indirme_koku, tarih_cozumle
from tablo_gorunumu import SiralaFiltreTablosu

DOSYA = "muavin.json"
YON_ADI = {"alis": "Alış", "satis": "Satış"}
HESAP = {"alis": "191", "satis": "391"}
DURUM_YAZISI = {"tamam": "Fatura no ve toplam uyuşuyor", "fark var": "SORUNLU FATURA VAR", "hata": "Hata"}
KAYNAK_ADI = {"muavin": "Muavin (191/391)", "isletme": "İşletme defteri"}
DURUM_ETIKET = {"tamam": "tamam", "fark var": "var", "hata": "hata"}


def eksikler(s):
    """Bir firmanin muavinde / defterde numarasi olmayan faturalari: [(yon, fatura sozlugu)] (once alis, sonra satis)."""
    return [(y, f) for y in ("alis", "satis") for f in ((s.get("yon") or {}).get(y) or {}).get("eksik", [])]


def tutar_farklari(s):
    """Numarasi bulunup genel toplam tutari uyusmayan faturalar: [(yon, fatura sozlugu)]."""
    return [(y, f) for y in ("alis", "satis") for f in ((s.get("yon") or {}).get(y) or {}).get("tutar_farki", [])]


def sorunlar(s):
    return eksikler(s) + tutar_farklari(s)


def eksik_satiri(yon, f):
    """'Alış  06/10/2026  ABC2026000000002  UNVAN  KDV 100,00 TL  KDV dahil 600,00 TL' (tarih - fatura no - ünvan - KDV - tutar);
    tutar farkinda sonuna kayittaki tutar eklenir."""
    kdv = "?" if f.get("kdv") is None else tl(f["kdv"])
    satir = (f"{YON_ADI[yon]:5} {f.get('tarih') or '-':10}  {f['no']:18}  {(f.get('unvan') or '-')[:38]:38}  "
             f"KDV {kdv:>14}  KDV dahil {tl(f.get('toplam') or 0.0):>16}")
    if f.get("kayit") is not None:
        satir += f"   (kayıtta: {', '.join(tl(t) for t in f['kayit']) or 'tutar yok'}; fiş {f.get('fis') or '?'})"
    return satir


def eksik_toplami(firmalar):
    """(sorunlu fatura adedi, sorunlu faturalarin KDV dahil tutar toplami)."""
    liste = [f for s in firmalar for _, f in sorunlar(s)]
    return len(liste), round(sum(f.get("toplam") or 0.0 for f in liste), 2)


class MuavinSekmesi(KarZararSekmesi):
    """Kar/Zarar sekmesinin surec, log ve ilerleme mekanizmasini kullanir; panel ve sonuc tablosu kendine ozgudur."""

    # -- kurulum ---------------------------------------------------------------

    def _degiskenler(self):
        bas, bit = self.ui.gecen_ay()      # faturalari indirilen ay
        self.v_bas = tk.StringVar(value=bas)
        self.v_bit = tk.StringVar(value=bit)
        self.v_firma = tk.StringVar()
        self.v_yenile = tk.BooleanVar(value=False)
        self.ham = []
        self.donem_metni = ""

    def _sol_panel(self):
        u = self.ui
        p = tk.Frame(self.govde, bg=u.ZEMIN, width=330, padx=22, pady=16)
        p.pack(side="left", fill="y")
        p.pack_propagate(False)

        u.bolum_basligi(p, "Fatura tarihi aralığı").pack(fill="x")
        t = tk.Frame(p, bg=u.ZEMIN)
        t.pack(fill="x", pady=(6, 0))
        for i, (ad, v) in enumerate((("Başlangıç", self.v_bas), ("Bitiş", self.v_bit))):
            k = tk.Frame(t, bg=u.ZEMIN)
            k.grid(row=0, column=i, sticky="ew", padx=(0, 8) if i == 0 else 0)
            tk.Label(k, text=ad, font=u.KUCUK, fg=u.ETIKET, bg=u.ZEMIN, anchor="w").pack(fill="x")
            u.giris_kutusu(k, v, genislik=12).pack(fill="x", ipady=4)
        t.columnconfigure(0, weight=1)
        t.columnconfigure(1, weight=1)

        tk.Label(p, text="Sadece bu firma (boş = tüm 1. ve 2. sınıf)", font=u.KUCUK, fg=u.ETIKET, bg=u.ZEMIN,
                 anchor="w").pack(fill="x", pady=(14, 3))
        u.giris_kutusu(p, self.v_firma).pack(fill="x", ipady=4)

        tk.Label(p, text="Fatura İndirme sekmesinin indirdiği alış / satış faturalarının numarası ve genel toplam (KDV dahil) "
                 "tutarı kontrol edilir; ikisi de uyuyorsa sorun yoktur.\n\n1. sınıf firmalar: Luca Muavin Defter "
                 "(191 / 391 ve karşı hesaplar).\n2. sınıf firmalar: İşletme Defteri Dökümü (gider / gelir).\n\n"
                 "Önce o dönemin faturalarını Fatura İndirme sekmesinden indirin. Luca'da hiçbir şey değiştirilmez; "
                 "yalnız rapor Excel'i indirilir.",
                 font=u.KUCUK, fg=u.SOLUK, bg=u.ZEMIN, anchor="w", justify="left", wraplength=280).pack(fill="x", pady=(16, 0))
        tk.Checkbutton(p, text="Firma listesini Luca'dan yeniden çek", variable=self.v_yenile, font=u.KUCUK,
                       **self.a._kutu_renk()).pack(anchor="w", pady=(10, 0))

        alt = tk.Frame(p, bg=u.ZEMIN)
        alt.pack(side="bottom", fill="x")
        self.calistir_dugmesi = u.dugme(alt, "Çalıştır", self.calistir, ana=True)
        self.calistir_dugmesi.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.durdur_dugmesi = u.dugme(alt, "Durdur", self.durdur, state="disabled")
        self.durdur_dugmesi.pack(side="left", fill="x", expand=True)

    def _sag_panel(self):
        u = self.ui
        p = tk.Frame(self.govde, bg=u.ZEMIN, padx=22, pady=16)
        p.pack(side="left", fill="both", expand=True)
        self.ilerleme_etiketi = tk.Label(p, text="Hazır.", font=u.GOVDE_KALIN, fg=u.YAZI, bg=u.ZEMIN, anchor="w")
        self.ilerleme_etiketi.pack(fill="x")
        from tkinter import ttk
        self.ilerleme = ttk.Progressbar(p, style="Altin.Horizontal.TProgressbar", maximum=100)
        self.ilerleme.pack(fill="x", pady=(8, 2))
        self.son_islem_etiketi = tk.Label(p, text="", font=u.KUCUK, fg=u.SOLUK, bg=u.ZEMIN, anchor="w")
        self.son_islem_etiketi.pack(fill="x", pady=(0, 6))

        alt = tk.Frame(p, bg=u.ZEMIN)
        alt.pack(side="bottom", fill="x", pady=(10, 0))
        u.dugme(alt, "Sorunlu faturalar", self.ayrinti, ana=True).pack(side="left")
        u.dugme(alt, "Seçilenleri Yeniden Çalıştır", self.secilenleri_calistir).pack(side="left", padx=8)
        u.dugme(alt, "Güncelle", self.guncelle).pack(side="left")
        u.dugme(alt, "Excel olarak indir", self.excele_indir).pack(side="left", padx=8)
        self.durum_yazisi = tk.Label(alt, text="", font=u.KUCUK, fg=u.SOLUK, bg=u.ZEMIN)
        self.durum_yazisi.pack(side="right")

        cerceve = tk.Frame(p, bg=u.KONSOL, highlightthickness=1, highlightbackground=u.KONSOL_KENAR, height=150)
        cerceve.pack(side="bottom", fill="x", pady=(10, 0))
        cerceve.pack_propagate(False)
        self.log = tk.Text(cerceve, bg=u.KONSOL, fg=u.KONSOL_FG, font=u.KONSOL_YAZI, relief="flat", wrap="none",
                           padx=12, pady=8, insertbackground=u.YAZI, state="disabled", highlightthickness=0, bd=0)
        kaydir = tk.Scrollbar(cerceve, command=self.log.yview, bg=u.KONSOL, troughcolor=u.KONSOL,
                              activebackground=u.KENAR, relief="flat", bd=0)
        self.log.configure(yscrollcommand=kaydir.set)
        kaydir.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)
        for etiket, renk in (("ok", u.YESIL_FG), ("uyari", u.UYARI_FG), ("soluk", u.LOG_SOLUK),
                             ("hata", u.KIRMIZI), ("firma", u.LOG_FIRMA), ("bilgi", u.LOG_BILGI)):
            self.log.tag_configure(etiket, foreground=renk)

        self.donem_etiketi = tk.Label(p, text="", font=u.KUCUK, fg=u.SOLUK, bg=u.ZEMIN, anchor="w")
        self.donem_etiketi.pack(fill="x", pady=(2, 0))
        self.ozet_etiketi = tk.Label(p, text="", font=u.GOVDE_KALIN, fg=u.ALTIN_FG, bg=u.ZEMIN, anchor="w",
                                     justify="left", wraplength=720)
        self.ozet_etiketi.pack(side="bottom", fill="x", pady=(6, 0))
        sutunlar = ("Firma", "Dönem", "Kaynak", "Alış fatura", "Alış sorun", "Satış fatura", "Satış sorun", "Sorunlu tutar",
                    "Durum", "Not")
        genislik = (170, 140, 120, 75, 75, 75, 75, 110, 190, 280)
        self.tablo = SiralaFiltreTablosu(p, u, sutunlar, genislik, yazi={0, 1, 2, 8, 9}, secim="extended",
                                         filtreler=("Durum",), degisti=self._toplam_yaz,
                                         etiketler={"tamam": u.YESIL_FG, "var": u.KIRMIZI, "hata": u.UYARI_FG})
        self.tablo.pack(fill="both", expand=True)
        self.agac = self.tablo.agac
        self.agac.bind("<Double-1>", lambda _e: self.ayrinti())

    def liste_bilgisi_yaz(self):
        """(Kar/Zarar sekmesinden kalan cagri) bu sekmede kayitli liste bilgisi etiketi yok."""

    # -- sonuc -------------------------------------------------------------------

    def sonucu_yukle(self):
        try:
            veri = json.loads((self.cikti_klasoru() / DOSYA).read_text(encoding="utf-8"))
            self.donem_metni, self.ham = veri.get("donem", ""), list(veri.get("firmalar") or [])
        except (OSError, ValueError):
            self.donem_metni, self.ham = "", []
        self.sonucu_goster()

    def sonucu_goster(self):
        if self.klasor is None:
            return
        self.satirlar = self.ham
        satirlar, etiketler = [], []
        for s in self.ham:
            durum = s.get("durum") or "hata"
            kaynak = KAYNAK_ADI.get(s.get("kaynak", "muavin"), "")
            if s.get("hata"):
                sayilar, tutar, not_ = ("", "", "", ""), "", s["hata"]
            else:
                a, t = s["yon"]["alis"], s["yon"]["satis"]
                sayilar = (a["fatura"], len(a["eksik"]) + len(a.get("tutar_farki", [])),
                           t["fatura"], len(t["eksik"]) + len(t.get("tutar_farki", [])))
                adet, toplam = eksik_toplami([s])
                tutar = tl(toplam) if adet else ""
                atlanan = a.get("iptal", 0) + t.get("iptal", 0) + a.get("kdvsiz", 0) + t.get("kdvsiz", 0)
                parca = [f"{len(eksikler(s))} numara yok" if eksikler(s) else "",
                         f"{len(tutar_farklari(s))} tutar uyuşmuyor" if tutar_farklari(s) else "",
                         f"{atlanan} fatura sayılmadı (iptal / KDV'siz)" if atlanan else ""]
                not_ = "; ".join(x for x in parca if x)
            satirlar.append((s["firma"], s.get("donem") or self.donem_metni, kaynak, *sayilar[:2], sayilar[2], sayilar[3],
                             tutar, DURUM_YAZISI.get(durum, durum), not_))
            etiketler.append(DURUM_ETIKET.get(durum, "hata"))
        self.tablo.doldur(satirlar, etiketler)
        self.donem_etiketi.configure(
            text=(f"Son sonuç dönemi: {self.donem_metni.replace('-', ' – ')}   ({len(self.ham)} firma)"
                  if self.ham else "Henüz sonuç yok."))
        self._toplam_yaz()

    def _toplam_yaz(self):
        gorunen = [self.ham[i] for i in self.tablo.gorunen_indeksler()]
        if not gorunen:
            self.ozet_etiketi.configure(text="")
            return
        fark = [s for s in gorunen if s.get("durum") == "fark var"]
        hata = sum(1 for s in gorunen if s.get("durum") == "hata")
        adet, toplam = eksik_toplami(gorunen)
        if fark:
            metin = f"{len(fark)} firmada {adet} sorunlu fatura var (toplam {tl(toplam)})"
        else:
            metin = f"Sorunlu fatura yok: fatura no ve genel toplam uyuşuyor ({len(gorunen)} firma)"
        if hata:
            metin += f" · {hata} firmada hata"
        self.ozet_etiketi.configure(text=metin)

    # -- ayrinti / excel ---------------------------------------------------------------

    def _ayrinti_firmalari(self):
        """Tabloda secili firmalar; secim yoksa tabloda gorunen (filtreli) tum firmalar."""
        sira = self.tablo.secili_indeksler() or self.tablo.gorunen_indeksler()
        return [self.ham[i] for i in sira]

    def ayrinti(self):
        firmalar = self._ayrinti_firmalari()
        if not firmalar:
            messagebox.showinfo("Sonuç yok", "Önce çalıştırın.", parent=self.a.kok)
            return
        u = self.ui
        pencere = tk.Toplevel(self.a.kok)
        pencere.title("Sorunlu faturalar (muavinde / işletme defterinde yok ya da tutarı uyuşmuyor)" + (f" — {firmalar[0]['firma']}" if len(firmalar) == 1 else ""))
        pencere.configure(bg=u.ZEMIN)
        pencere.geometry("1000x560")
        alt = tk.Frame(pencere, bg=u.ZEMIN)
        alt.pack(side="bottom", fill="x", padx=10, pady=8)
        metin = tk.Text(pencere, bg=u.KONSOL, fg=u.KONSOL_FG, font=u.KONSOL_YAZI, wrap="none", padx=12, pady=10)
        metin.pack(fill="both", expand=True)
        metin.tag_configure("baslik", foreground=u.ALTIN_FG)
        metin.tag_configure("hata", foreground=u.UYARI_FG)
        metin.insert("end", "Sütunlar: Tarih - Fatura No - Ünvan/İsim - KDV - KDV dahil tutar\n\n", "baslik")
        for s in firmalar:
            metin.insert("end", f"{s['firma']}   {s.get('donem', '')}   [{DURUM_YAZISI.get(s.get('durum'), s.get('durum'))}]   "
                                f"{KAYNAK_ADI.get(s.get('kaynak', 'muavin'), '')}\n", "baslik")
            if s.get("hata"):
                metin.insert("end", f"  Hata: {s['hata']}\n\n", "hata")
                continue
            yer = "muavinde" if s.get("kaynak", "muavin") == "muavin" else "işletme defterinde"
            for yon in ("alis", "satis"):
                d = s["yon"][yon]
                metin.insert("end", f"  {YON_ADI[yon]} ({HESAP[yon]}): {d['fatura']} fatura, {d['eslesen']} tamam, "
                                    f"{len(d['eksik'])} {yer} yok, {len(d.get('tutar_farki', []))} tutar uyuşmuyor\n")
            if not sorunlar(s):
                metin.insert("end", "  Fatura no ve genel toplam uyuşuyor; sorunlu fatura yok.\n")
            for baslik, liste in ((f"İnen fatura listesinde var, {yer} yok:", eksikler(s)),
                                  ("Fatura no var ama genel toplam tutarı uyuşmuyor:", tutar_farklari(s))):
                if liste:
                    metin.insert("end", f"  {baslik}\n", "baslik")
                    for yon, f in liste:
                        metin.insert("end", "    " + eksik_satiri(yon, f) + "\n")
            metin.insert("end", "\n")
        adet, toplam = eksik_toplami(firmalar)
        metin.insert("end", f"Toplam: {adet} sorunlu fatura ({tl(toplam)})\n", "baslik")
        metin.configure(state="disabled")

        def kopyala():
            pencere.clipboard_clear()
            pencere.clipboard_append(metin.get("1.0", "end-1c"))
        u.dugme(alt, "Panoya kopyala", kopyala).pack(side="left")

    def excele_indir(self):
        if not self.ham:
            messagebox.showinfo("Sonuç yok", "Önce çalıştırın.", parent=self.a.kok)
            return
        yol = filedialog.asksaveasfilename(
            title="Excel olarak kaydet", parent=self.a.kok, defaultextension=".xlsx",
            initialfile=f"muavin-eksik-{self.donem_metni.replace('/', '.')}.xlsx", filetypes=[("Excel", "*.xlsx")])
        if not yol:
            return
        try:
            self._excel_yaz_mv(yol)
        except PermissionError:
            messagebox.showerror("Kaydedilemedi", "Dosya Excel'de açık; kapatıp tekrar deneyin.", parent=self.a.kok)
            return
        self.ui.dosya_ac(yol)

    def _excel_yaz_mv(self, yol, firmalar=None):
        firmalar = self.ham if firmalar is None else firmalar
        from openpyxl import Workbook
        from openpyxl.styles import Font
        wb = Workbook()
        ws = wb.active
        ws.title = "Özet"
        ws.append(["Muavin / işletme defteri kontrolü — fatura no ve genel toplam", self.donem_metni.replace("-", " – ")])
        ws["A1"].font = Font(bold=True, size=13)
        ws.append([])
        ws.append(["Firma", "Dönem", "Durum", "Kaynak", "Alış fatura", "Alış eksik", "Alış tutar uyuşmuyor", "Satış fatura",
                   "Satış eksik", "Satış tutar uyuşmuyor", "İptal/KDV'siz (sayılmadı)", "Not"])
        for h in ws[3]:
            h.font = Font(bold=True)
        sayfalar = {}
        for ad, ek in (("Eksik (muavinde yok)", []), ("Tutar uyuşmuyor", ["Kayıttaki tutarlar", "Fiş no"])):
            sh = wb.create_sheet(ad)
            sh.append(["Firma", "Yön", "Tarih", "Fatura No", "Ünvan / İsim", "KDV", "KDV dahil tutar"] + ek)
            for h in sh[1]:
                h.font = Font(bold=True)
            sh.freeze_panes = "A2"
            sayfalar[ad] = sh
        for s in firmalar:
            kaynak = KAYNAK_ADI.get(s.get("kaynak", "muavin"), "")
            if s.get("hata"):
                ws.append([s["firma"], s.get("donem") or self.donem_metni, "HATA", kaynak, None, None, None, None, None, None,
                           None, s["hata"]])
                continue
            a, t = s["yon"]["alis"], s["yon"]["satis"]
            ws.append([s["firma"], s.get("donem") or self.donem_metni, DURUM_YAZISI.get(s.get("durum"), s.get("durum")), kaynak,
                       a["fatura"], len(a["eksik"]), len(a.get("tutar_farki", [])), t["fatura"], len(t["eksik"]),
                       len(t.get("tutar_farki", [])), a.get("iptal", 0) + t.get("iptal", 0) + a.get("kdvsiz", 0) + t.get("kdvsiz", 0), ""])
            for yon, f in eksikler(s):
                sayfalar["Eksik (muavinde yok)"].append([s["firma"], YON_ADI[yon], f.get("tarih", ""), f["no"], f.get("unvan", ""),
                                                         f.get("kdv"), f.get("toplam")])
            for yon, f in tutar_farklari(s):
                sayfalar["Tutar uyuşmuyor"].append([s["firma"], YON_ADI[yon], f.get("tarih", ""), f["no"], f.get("unvan", ""),
                                                    f.get("kdv"), f.get("toplam"), ", ".join(f"{x:.2f}" for x in f.get("kayit", [])),
                                                    f.get("fis", "")])
        for sh in sayfalar.values():
            for satir in sh.iter_rows(min_row=2, min_col=6, max_col=7):
                for h in satir:
                    h.number_format = "#,##0.00"
            for harf, g in zip("ABCDEFGHI", (34, 8, 12, 20, 36, 14, 18, 36, 16)):
                sh.column_dimensions[harf].width = g
        for harf, g in zip("ABCDEFGHIJKL", (34, 24, 30, 22, 11, 11, 14, 11, 11, 14, 14, 50)):
            ws.column_dimensions[harf].width = g
        wb.save(yol)

    # -- calistirma ------------------------------------------------------------------

    def komut(self, tam_firmalar=None):
        bas, bit = self.v_bas.get().strip(), self.v_bit.get().strip()
        try:
            if tarih_cozumle(bit) < tarih_cozumle(bas):
                raise ValueError("Bitiş tarihi başlangıçtan önce olamaz.")
        except ValueError as e:
            if "olamaz" in str(e):
                raise
            raise ValueError("Tarihleri GG/AA/YYYY biçiminde yazın (örnek 01/10/2026).")
        ayar_hazirla(self.klasor, self.a.ayarlar, {})
        komut = [self.ui.python_komutu(), "-u", str(self.klasor / "muavin.py"), "--bitince-kapat",
                 "--tarih", f"{bas}-{bit}", "--fatura-klasoru", str(indirme_koku(self.a.ayarlar))]
        if tam_firmalar:
            for f in tam_firmalar:
                komut += ["--firma-tam", f]
            return komut
        if self.v_firma.get().strip():
            komut += ["--firma", self.v_firma.get().strip()]
        if self.v_yenile.get():
            komut.append("--listeyi-yenile")
        return komut

    def _baska_calisiyor(self):
        if self.a.surec or self.a.kz.calisiyor() or self.a.db.calisiyor():
            messagebox.showinfo("Başka çalışma sürüyor", "Fatura indirme / Kâr-Zarar / Defter Beyan çalışıyor; bitince "
                                "başlatın (ikisi aynı anda Luca'ya girmemeli).", parent=self.a.kok)
            return True
        if self.surec:
            messagebox.showinfo("Çalışıyor", "Önce çalışan işlem bitsin ya da Durdur'a basın.", parent=self.a.kok)
            return True
        return False

    def calistir(self):
        if self._baska_calisiyor() or not self.a._giris_tamam_mi():
            return
        try:
            komut = self.komut()
        except ValueError as e:
            messagebox.showerror("Eksik bilgi", str(e), parent=self.a.kok)
            return
        self._baslat(komut)

    def secilenleri_calistir(self):
        sira = self.tablo.secili_indeksler()
        if not sira:
            messagebox.showinfo("Firma seçin", "Önce tabloda yeniden çalıştırılacak firmaları seçin "
                                "(Ctrl / Shift ile birden çok).", parent=self.a.kok)
            return
        if self._baska_calisiyor() or not self.a._giris_tamam_mi():
            return
        firmalar = sorted({self.ham[i]["firma"] for i in sira})
        try:
            komut = self.komut(firmalar)
        except ValueError as e:
            messagebox.showerror("Eksik bilgi", str(e), parent=self.a.kok)
            return
        self._baslat(komut)

    def _baslat(self, komut):
        super()._baslat(komut)
        if self.surec:
            self.ilerleme_etiketi.configure(text="Luca muavini ile faturalar karşılaştırılıyor…")

    def _bitti(self, kod):
        durduruldu = self.durdurma_istendi
        super()._bitti(kod)
        if kod == 0 and not durduruldu:
            self.ilerleme_etiketi.configure(text=f"Tamamlandı: {len(self.ham)} firma. {self.ozet_etiketi.cget('text')}")
