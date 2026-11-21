# -*- coding: utf-8 -*-
"""Luca Bot arayuzunun "e-Defter" sekmesi: e-Defter gondermeden once Luca'da uyumsuz fisleri bulur.

Repodaki kar-zarar/edefter.py programini arka planda calistirir. Her 1. sinif (genel muhasebe) firma icin Luca'da
Muhasebe > Fis Islemleri > Duzenleme > Toplu Belge Turu ve Odeme Yontemi Duzenleme ekraninda "E-Defter kapsaminda uyumsuz olan
fisleri getir" ile her e-Defter hata kodu (20041, 20042, 20044-20048) taranir; uyumsuz fisler (fis no, tarih, evrak no, belge turu,
odeme turu) listelenir. Luca'da hicbir sey degistirilmez (Kaydet'e basilmaz). Sonuc kar-zarar/cikti/edefter.json'dan okunur.
Kar/Zarar, Defter Beyan, Muavin ve Fatura indirme ile ayni anda calismaz.
"""

import json
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox

from kar_zarar_sekmesi import KarZararSekmesi, ayar_hazirla
from lucabot.ortak import tarih_cozumle
from tablo_gorunumu import SiralaFiltreTablosu

DOSYA = "edefter.json"
EXCEL = "edefter.xlsx"
KOD_SUTUNLARI = ("20021", "20025", "20026", "20041", "20042", "20044", "20045", "20046", "20047", "20048")
DURUM_YAZISI = {"tamam": "Gönderilebilir (uyumsuz fiş yok)", "sorun var": "UYUMSUZ FİŞ VAR", "hata": "Kontrol tamamlanamadı"}
DURUM_ETIKET = {"tamam": "tamam", "sorun var": "var", "hata": "hata"}
KISA_AD = {
    "20021": "e-Defter başlangıç tarihinden önce numaralandırılmamış fiş",
    "20025": "Dengesiz veya pasif fiş",
    "20026": "Detaysız fiş",
    "20041": "Belge türü tanımı yok",
    "20042": "Belge tür, evrak no ve tarih uyumsuz",
    "20043": "Evrak no ve tarih var ama belge türü boş",
    "20044": "Birden fazla belge",
    "20045": "Birden fazla belge türü",
    "20046": "Bir fişte çok fazla fatura (50/100 sınırı)",
    "20047": "Birden fazla ödeme yöntemi",
    "20048": "Belge türü fatura olan birden fazla belge",
}


def kod_adi(h):
    return KISA_AD.get(str(h.get("kod"))) or h.get("ad") or f"Hata kodu {h.get('kod')}"


def sorun_sayisi(s):
    """Firmanin toplam uyumsuz fis sayisi (ayni fis birden cok kodda gecebilir: kod basina sayilir)."""
    return sum(h.get("fis_sayisi", 0) for h in s.get("hatalar") or [])


def taranamayanlar(s):
    return [(h["kod"], h["hata"]) for h in s.get("hatalar") or [] if h.get("hata")]


def fis_satiri(f):
    """'   01023  01/07/2026  evrak 89582  BT MF  ödeme -  3 satır' (Luca'da Fiş No ile aranır)."""
    evrak = ", ".join(f.get("evrak") or []) or "-"
    tur = {True: "  (fatura fişi)", False: "  (diğer fiş)"}.get(f.get("fatura_fisi"), "")
    satir = (f"{f.get('fis_no') or '?':>8}  {f.get('tarih') or '-':10}  evrak {evrak[:24]:24}  BT {f.get('bt') or '-':4}  "
             f"ödeme {f.get('odeme') or '-':6}  {f.get('satir', 0)} satır{tur}")
    return satir + (f"  [{'; '.join(f['durum'])[:70]}]" if f.get("durum") else "")      # Luca'nın satır açıklaması


class EdefterSekmesi(KarZararSekmesi):
    """Kar/Zarar sekmesinin surec, log ve ilerleme mekanizmasini kullanir; panel ve sonuc tablosu kendine ozgudur."""

    # -- kurulum ---------------------------------------------------------------

    def _degiskenler(self):
        bas, bit = self.ui.gecen_ay()      # e-Defter aylik gonderilir: varsayilan gecen ay
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

        u.bolum_basligi(p, "Fiş tarihi aralığı (e-Defter ayı)").pack(fill="x")
        t = tk.Frame(p, bg=u.ZEMIN)
        t.pack(fill="x", pady=(6, 0))
        for i, (ad, v) in enumerate((("Başlangıç", self.v_bas), ("Bitiş", self.v_bit))):
            k = tk.Frame(t, bg=u.ZEMIN)
            k.grid(row=0, column=i, sticky="ew", padx=(0, 8) if i == 0 else 0)
            tk.Label(k, text=ad, font=u.KUCUK, fg=u.ETIKET, bg=u.ZEMIN, anchor="w").pack(fill="x")
            u.giris_kutusu(k, v, genislik=12).pack(fill="x", ipady=4)
        t.columnconfigure(0, weight=1)
        t.columnconfigure(1, weight=1)

        tk.Label(p, text="Sadece bu firma (boş = tüm 1. sınıf firmalar)", font=u.KUCUK, fg=u.ETIKET, bg=u.ZEMIN,
                 anchor="w").pack(fill="x", pady=(14, 3))
        u.giris_kutusu(p, self.v_firma).pack(fill="x", ipady=4)
        self._hesap_secici(p)

        tk.Label(p, text="e-Defter göndermeden önce Luca'nın kendi kontrolü çalıştırılır (Fiş İşlemleri > Düzenleme > Toplu "
                 "Belge Türü ve Ödeme Yöntemi Düzenleme > \"E-Defter kapsamında uyumsuz olan fişleri getir\"); her hata "
                 "kodu için uyumsuz fişler listelenir.\n\n"
                 "20041 belge türü tanımı yok · 20042 belge tür/evrak no/tarih uyumsuz · 20043 evrak no ve tarih var, belge türü boş · "
                 "20044 birden fazla belge · 20045 birden fazla belge türü · 20046 bir fişte çok fatura · 20047 birden fazla "
                 "ödeme yöntemi · 20048 fatura türünde birden fazla belge (listede hangileri varsa onlar taranır).\n\nLuca'da hiçbir şey değiştirilmez; yalnız okunur "
                 "(düzeltmeyi siz Luca'da yaparsınız).",
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
        u.dugme(alt, "Uyumsuz fişler", self.ayrinti, ana=True).pack(side="left")
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
        sutunlar = ("Firma", "Dönem", "Durum", "Uyumsuz fiş") + KOD_SUTUNLARI + ("Not",)
        genislik = (170, 140, 200, 85) + (62,) * len(KOD_SUTUNLARI) + (260,)
        self.tablo = SiralaFiltreTablosu(p, u, sutunlar, genislik, yazi={0, 1, 2, len(sutunlar) - 1}, secim="extended",
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
            sayilar = {h["kod"]: h for h in s.get("hatalar") or []}

            def hucre(kod):
                h = sayilar.get(kod)
                if h is None:
                    return ""
                return "?" if h.get("hata") else (h.get("fis_sayisi") or "")
            if s.get("hata"):
                not_ = s["hata"]
            else:
                parca = [f"{k}: {h[:60]}" for k, h in taranamayanlar(s)]
                diger = [h["kod"] for h in s.get("hatalar") or [] if h.get("fis_sayisi") and h["kod"] not in KOD_SUTUNLARI]
                if diger:
                    parca.append("diğer kodlar: " + ", ".join(diger))
                not_ = "; ".join(parca)
            satirlar.append((s["firma"], s.get("donem") or self.donem_metni, DURUM_YAZISI.get(durum, durum),
                             sorun_sayisi(s) or "", *[hucre(k) for k in KOD_SUTUNLARI], not_))
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
        sorunlu = [s for s in gorunen if s.get("durum") == "sorun var"]
        hata = sum(1 for s in gorunen if s.get("durum") == "hata")
        temiz = sum(1 for s in gorunen if s.get("durum") == "tamam")
        if sorunlu:
            metin = (f"{len(sorunlu)} firmada {sum(sorun_sayisi(s) for s in sorunlu)} uyumsuz fiş var; "
                     f"{temiz} firma e-Defter'e gönderilebilir")
        else:
            metin = f"Uyumsuz fiş yok: {temiz} firma e-Defter'e gönderilebilir"
        if hata:
            metin += f" · {hata} firmada kontrol tamamlanamadı"
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
        pencere.title("e-Defter uyumsuz fişleri" + (f" — {firmalar[0]['firma']}" if len(firmalar) == 1 else ""))
        pencere.configure(bg=u.ZEMIN)
        pencere.geometry("1000x560")
        alt = tk.Frame(pencere, bg=u.ZEMIN)
        alt.pack(side="bottom", fill="x", padx=10, pady=8)
        metin = tk.Text(pencere, bg=u.KONSOL, fg=u.KONSOL_FG, font=u.KONSOL_YAZI, wrap="none", padx=12, pady=10)
        metin.pack(fill="both", expand=True)
        metin.tag_configure("baslik", foreground=u.ALTIN_FG)
        metin.tag_configure("hata", foreground=u.UYARI_FG)
        metin.insert("end", "Sütunlar: Fiş No - Fiş Tarihi - Evrak No - BT (belge türü) - Ödeme türü - Satır sayısı - (fiş türü) - [Luca'nın açıklaması]  "
                            "(Luca'da Fiş No ile aranır)\n\n", "baslik")
        for s in firmalar:
            metin.insert("end", f"{s['firma']}   {s.get('donem', '')}   [{DURUM_YAZISI.get(s.get('durum'), s.get('durum'))}]\n", "baslik")
            if s.get("hata"):
                metin.insert("end", f"  Hata: {s['hata']}\n\n", "hata")
                continue
            if not sorun_sayisi(s):
                metin.insert("end", "  e-Defter kapsamında uyumsuz fiş yok.\n")
            for h in s.get("hatalar") or []:
                if h.get("hata"):
                    metin.insert("end", f"  {h['kod']} {kod_adi(h)}: TARANAMADI — {h['hata'][:200]}\n", "hata")
                elif h.get("fis_sayisi"):
                    ayrim = (f" — {h['fatura_fisi']} fatura fişi (191/391 var: elle kontrol), {h['diger_fis']} diğer fiş (MF + evrak no atanabilir)"
                             if h.get("fatura_fisi") or h.get("diger_fis") else "")
                    metin.insert("end", f"  {h['kod']} {kod_adi(h)}: {h['fis_sayisi']} fiş" +
                                 (" (en az; sayfa sınırı)" if h.get("kesildi") else "") + ayrim + "\n", "baslik")
                    for f in h.get("fisler") or []:
                        metin.insert("end", "    " + fis_satiri(f) + "\n")
                    if h["fis_sayisi"] > len(h.get("fisler") or []):
                        metin.insert("end", f"    … {h['fis_sayisi'] - len(h.get('fisler') or [])} fiş daha (Luca'da listeleyin)\n")
            metin.insert("end", "\n")
        toplam = sum(sorun_sayisi(s) for s in firmalar)
        metin.insert("end", f"Toplam: {toplam} uyumsuz fiş ({len(firmalar)} firma)\n", "baslik")
        metin.configure(state="disabled")

        def kopyala():
            pencere.clipboard_clear()
            pencere.clipboard_append(metin.get("1.0", "end-1c"))
        u.dugme(alt, "Panoya kopyala", kopyala).pack(side="left")

    def excele_indir(self):
        """Program her calismada cikti/edefter.xlsx'i yazar (onceki firmalarla birlikte); secilen yere kopyalanir."""
        kaynak = self.cikti_klasoru() / EXCEL
        if not self.ham or not kaynak.exists():
            messagebox.showinfo("Sonuç yok", "Önce çalıştırın (Excel her çalışmanın sonunda hazırlanır).", parent=self.a.kok)
            return
        yol = filedialog.asksaveasfilename(
            title="Excel olarak kaydet", parent=self.a.kok, defaultextension=".xlsx",
            initialfile=f"e-defter-kontrol-{self.donem_metni.replace('/', '.')}.xlsx", filetypes=[("Excel", "*.xlsx")])
        if not yol:
            return
        try:
            shutil.copyfile(kaynak, yol)
        except PermissionError:
            messagebox.showerror("Kaydedilemedi", "Dosya Excel'de açık; kapatıp tekrar deneyin.", parent=self.a.kok)
            return
        self.ui.dosya_ac(yol)

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
        komut = [self.ui.python_komutu(), "-u", str(self.klasor / "edefter.py"), "--bitince-kapat",
                 "--tarih", f"{bas}-{bit}"] + self._hesap_arg()
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
        if self.a.surec or self.a.kz.calisiyor() or self.a.db.calisiyor() or self.a.mv.calisiyor():
            messagebox.showinfo("Başka çalışma sürüyor", "Fatura indirme / Kâr-Zarar / Defter Beyan / Muavin çalışıyor; bitince "
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
            self.ilerleme_etiketi.configure(text="Luca'da e-Defter uyumsuz fişleri taranıyor…")

    def _bitti(self, kod):
        durduruldu = self.durdurma_istendi
        super()._bitti(kod)
        if kod == 0 and not durduruldu:
            self.ilerleme_etiketi.configure(text=f"Tamamlandı: {len(self.ham)} firma. {self.ozet_etiketi.cget('text')}")
