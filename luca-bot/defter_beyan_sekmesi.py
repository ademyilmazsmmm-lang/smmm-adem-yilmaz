# -*- coding: utf-8 -*-
"""Luca Bot arayuzunun "Defter Beyan" sekmesi (2. sinif: isletme / serbest meslek defteri firmalari).

Repodaki kar-zarar/defter_beyan.py programini arka planda calistirir. Her firma icin Luca'nin "Defter Beyan Sistemi"
sayfasinda Gelirler ve Giderler listelenir:
  * Yalniz kontrol: donemin Gonderilmemis kayitlari sayilir, hicbir sey gonderilmez.
  * Gonder: gonderilmemis kayitlar secilir -> Cari Bilgi Sorgula -> Kaydet -> Defter Beyan Sistemine Gonder; sonra
    liste yenilenir, gitmeyenler (hata verenler) raporlanir. Gonderilmeyenlerin icindeki SABIT KIYMET ayrica gosterilir;
    kalanlar yalniz sabit kiymet ise firma 'es gecilir' (sabit kiymetler normalde gonderilmez).
Sonuc kar-zarar/cikti/defter-beyan.json'dan okunur. Kar/Zarar ve Fatura indirme ile ayni anda calismaz.
"""

import json
from datetime import datetime
from tkinter import filedialog, messagebox
import tkinter as tk

from kar_zarar_sekmesi import KarZararSekmesi, ayar_hazirla, varsayilan_donem
from lucabot.ortak import TARIH_BICIMI, tarih_cozumle
from lucabot.gostergeler import tl
from tablo_gorunumu import SiralaFiltreTablosu

DOSYA = "defter-beyan.json"
ISLEMLER = (("Yalnız kontrol (hiçbir şey gönderilmez)", "kontrol"),
            ("Gönder (Cari Sorgula → Kaydet → Gönder)", "gonder"))
DURUM_YAZISI = {"tamam": "Gönderilmeyen yok", "yalnız sabit kıymet": "Yalnız sabit kıymet (es geçilir)",
                "gönderilmemiş var": "GÖNDERİLMEYEN VAR", "hata": "Hata"}
DURUM_ETIKET = {"tamam": "tamam", "yalnız sabit kıymet": "sabit", "gönderilmemiş var": "var", "hata": "hata"}
TURLER = (("gelir", "Gelir"), ("gider", "Gider"))


def kalan(t):
    """Bir sekmenin (gelir/gider) gonderilmeyen kayit sayisi, bunlardan sabit kiymet ve kayit listesi; sekme okunamadiysa None."""
    if not t:
        return None, 0, []
    g = t.get("gonderim") or {}
    if g:
        return g.get("kalan") or 0, g.get("kalan_sabit") or 0, g.get("kalan_kayitlar") or []
    return t.get("gonderilmemis") or 0, t.get("sabit_kiymet") or 0, t.get("kayitlar") or []


def hata_ozetleri(sonuc):
    """Sekmelerin satir-hata ozetleri birlestirilir: {'Tutarı 0.00 olan satır girilemez.': 3}."""
    toplam = {}
    for tur, _ in TURLER:
        for mesaj, adet in ((sonuc.get(tur) or {}).get("gonderim", {}).get("hata_ozeti") or {}).items():
            toplam[mesaj] = toplam.get(mesaj, 0) + adet
    return toplam


class DefterBeyanSekmesi(KarZararSekmesi):
    """Kar/Zarar sekmesinin surec, log ve ilerleme mekanizmasini kullanir; panel ve sonuc tablosu kendine ozgudur."""

    # -- kurulum ---------------------------------------------------------------

    def _degiskenler(self):
        bas, bit = varsayilan_donem()
        self.v_bas = tk.StringVar(value=bas)
        self.v_bit = tk.StringVar(value=bit)
        self.v_firma = tk.StringVar()
        self.v_islem = tk.StringVar(value=ISLEMLER[0][0])
        self.v_yenile = tk.BooleanVar(value=False)
        self.ham = []
        self.donem_metni = ""

    def _sol_panel(self):
        u = self.ui
        p = tk.Frame(self.govde, bg=u.ZEMIN, width=330, padx=22, pady=16)
        p.pack(side="left", fill="y")
        p.pack_propagate(False)

        u.bolum_basligi(p, "Evrak tarihi aralığı").pack(fill="x")
        t = tk.Frame(p, bg=u.ZEMIN)
        t.pack(fill="x", pady=(6, 0))
        for i, (ad, v) in enumerate((("Başlangıç", self.v_bas), ("Bitiş", self.v_bit))):
            k = tk.Frame(t, bg=u.ZEMIN)
            k.grid(row=0, column=i, sticky="ew", padx=(0, 8) if i == 0 else 0)
            tk.Label(k, text=ad, font=u.KUCUK, fg=u.ETIKET, bg=u.ZEMIN, anchor="w").pack(fill="x")
            u.giris_kutusu(k, v, genislik=12).pack(fill="x", ipady=4)
        t.columnconfigure(0, weight=1)
        t.columnconfigure(1, weight=1)

        tk.Label(p, text="Sadece bu firma (boş = tüm 2. sınıf)", font=u.KUCUK, fg=u.ETIKET, bg=u.ZEMIN,
                 anchor="w").pack(fill="x", pady=(14, 3))
        u.giris_kutusu(p, self.v_firma).pack(fill="x", ipady=4)

        u.bolum_basligi(p, "İşlem").pack(fill="x", pady=(16, 0))
        for yazi, deger in ISLEMLER:
            tk.Radiobutton(p, text=yazi, value=yazi, variable=self.v_islem, font=u.KUCUK, justify="left",
                           **self.a._kutu_renk()).pack(fill="x", pady=(4, 0))
        tk.Label(p, text="2. sınıf = Luca Müşteri Listesi'nde İşletme Defteri / Serbest Meslek Defteri olan firmalar. "
                 "Gönderirken seçili kayıtlar için sırayla Cari Bilgi Sorgula, Kaydet ve Defter Beyan Sistemine Gönder "
                 "uygulanır; API Key/Secret Luca'da kayıtlı olanlar kullanılır (program yazmaz).",
                 font=u.KUCUK, fg=u.SOLUK, bg=u.ZEMIN, anchor="w", justify="left", wraplength=280).pack(fill="x", pady=(10, 0))
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
        self.ilerleme_etiketi = tk.Label(p, text="Hazır. Önce 'Yalnız kontrol' ile bakmanız önerilir.",
                                         font=u.GOVDE_KALIN, fg=u.YAZI, bg=u.ZEMIN, anchor="w")
        self.ilerleme_etiketi.pack(fill="x")
        from tkinter import ttk
        self.ilerleme = ttk.Progressbar(p, style="Altin.Horizontal.TProgressbar", maximum=100)
        self.ilerleme.pack(fill="x", pady=(8, 2))
        self.son_islem_etiketi = tk.Label(p, text="", font=u.KUCUK, fg=u.SOLUK, bg=u.ZEMIN, anchor="w")
        self.son_islem_etiketi.pack(fill="x", pady=(0, 6))

        alt = tk.Frame(p, bg=u.ZEMIN)
        alt.pack(side="bottom", fill="x", pady=(10, 0))
        u.dugme(alt, "Ayrıntı (seçili firma)", self.ayrinti, ana=True).pack(side="left")
        u.dugme(alt, "Seçilenleri Yeniden Çalıştır", self.secilenleri_calistir).pack(side="left", padx=8)
        u.dugme(alt, "Güncelle", self.guncelle).pack(side="left")
        u.dugme(alt, "Excel olarak indir", self.excele_indir).pack(side="left", padx=8)
        self.durum_yazisi = tk.Label(alt, text="", font=u.KUCUK, fg=u.SOLUK, bg=u.ZEMIN)
        self.durum_yazisi.pack(side="right")

        cerceve = tk.Frame(p, bg=u.KONSOL, highlightthickness=1, highlightbackground=u.KONSOL_KENAR, height=130)
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
        sutunlar = ("Firma", "Dönem", "İşlem", "Gelir kalan", "Gider kalan", "Sabit kıymet", "Durum", "Not")
        genislik = (170, 150, 80, 90, 90, 90, 190, 300)
        self.tablo = SiralaFiltreTablosu(p, u, sutunlar, genislik, yazi={0, 1, 2, 6, 7}, secim="extended",
                                         filtreler=("Durum",), degisti=self._toplam_yaz,
                                         etiketler={"tamam": u.YESIL_FG, "sabit": u.SOLUK, "var": u.KIRMIZI,
                                                    "hata": u.UYARI_FG})
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
            sayilar = [kalan(s.get(tur)) for tur, _ in TURLER]
            sutun = lambda x: "—" if x[0] is None else str(x[0])
            sabit = sum(x[1] for x in sayilar if x[0] is not None)
            ozet = hata_ozetleri(s)
            if s.get("hata"):
                not_ = s["hata"]
            elif ozet:
                not_ = "; ".join(f"{adet}× {mesaj}" for mesaj, adet in list(ozet.items())[:3])
            elif durum == "gönderilmemiş var" and s.get("islem") == "kontrol":
                not_ = "Kontrol: gönderilmedi"
            else:
                not_ = ""
            islem = "Gönderme" if s.get("islem") == "gonder" else "Kontrol"
            satirlar.append((s["firma"], s.get("donem") or self.donem_metni, islem, sutun(sayilar[0]), sutun(sayilar[1]),
                             str(sabit) if sabit else "", DURUM_YAZISI.get(durum, durum), not_))
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
        sayi = {}
        for s in gorunen:
            sayi[s.get("durum") or "hata"] = sayi.get(s.get("durum") or "hata", 0) + 1
        parca = [f"{DURUM_YAZISI[d]}: {sayi[d]}" for d in ("tamam", "yalnız sabit kıymet", "gönderilmemiş var", "hata")
                 if sayi.get(d)]
        if len(sayi) == 1 and "tamam" in sayi:
            self.ozet_etiketi.configure(text=f"Gönderilmeyen yok ({len(gorunen)} firma).")
        else:
            self.ozet_etiketi.configure(text=f"{len(gorunen)} firma → " + " · ".join(parca))

    # -- ayrinti / excel ---------------------------------------------------------------

    def _kalan_satirlari(self, s):
        """Bir firmanin gonderilmeyen kayitlari: [(tur, evrak no, tarih, kategori, belge turu, aciklama, tutar, sabit mi)]"""
        sonuc = []
        for tur, ad in TURLER:
            for k in kalan(s.get(tur))[2]:
                sonuc.append((ad, k.get("evrak_no", ""), k.get("tarih", ""), k.get("kategori", ""), k.get("belge_turu", ""),
                              k.get("aciklama", ""), k.get("tutar"), bool(k.get("sabit_kiymet"))))
        return sonuc

    def ayrinti(self):
        sira = self.tablo.secili_indeksler()
        if not sira:
            messagebox.showinfo("Firma seçin", "Tablodan bir firma seçin (çift tıklamak da olur).", parent=self.a.kok)
            return
        s = self.ham[sira[0]]
        u = self.ui
        pencere = tk.Toplevel(self.a.kok)
        pencere.title(f"Defter Beyan — {s['firma']}")
        pencere.configure(bg=u.ZEMIN)
        pencere.geometry("900x520")
        metin = tk.Text(pencere, bg=u.KONSOL, fg=u.KONSOL_FG, font=u.KONSOL_YAZI, wrap="none", padx=12, pady=10)
        metin.pack(fill="both", expand=True)
        metin.tag_configure("sabit", foreground=u.UYARI_FG)
        metin.tag_configure("baslik", foreground=u.ALTIN_FG)
        metin.insert("end", f"{s['firma']}   {s.get('donem', '')}   [{DURUM_YAZISI.get(s.get('durum'), s.get('durum'))}]\n\n",
                     "baslik")
        if s.get("hata"):
            metin.insert("end", f"Hata: {s['hata']}\n\n")
        for tur, ad in TURLER:
            t = s.get(tur) or {}
            g = t.get("gonderim") or {}
            n, sabit, _ = kalan(t)
            if n is None:
                metin.insert("end", f"{ad}: okunamadı\n")
                continue
            satir = f"{ad}: {t.get('gonderilmemis', 0)} gönderilmemişti"
            if g:
                satir += f", {g.get('gonderilen', 0)} gönderildi, {n} kaldı"
            if sabit:
                satir += f"  (kalanların {sabit} tanesi SABİT KIYMET)"
            metin.insert("end", satir + "\n")
            for mesaj, adet in (g.get("hata_ozeti") or {}).items():
                metin.insert("end", f"    {adet} kayıt: {mesaj}\n")
        metin.insert("end", "\nGönderilmeyen kayıtlar:\n", "baslik")
        kalanlar = self._kalan_satirlari(s)
        if not kalanlar:
            metin.insert("end", "  Gönderilmeyen yok.\n")
        for tur, evrak, tarih, kat, belge, acik, tutar, sabit in kalanlar:
            yazi = (f"  {tur:6} {evrak:14} {tarih:11} {kat[:22]:22} {belge[:16]:16} {acik[:30]:30} "
                    f"{tl(tutar) if tutar is not None else '':>16}" + ("   ← SABİT KIYMET" if sabit else "") + "\n")
            metin.insert("end", yazi, "sabit" if sabit else ())
        metin.configure(state="disabled")

    def excele_indir(self):
        if not self.ham:
            messagebox.showinfo("Sonuç yok", "Önce çalıştırın.", parent=self.a.kok)
            return
        yol = filedialog.asksaveasfilename(
            title="Excel olarak kaydet", parent=self.a.kok, defaultextension=".xlsx",
            initialfile=f"defter-beyan-{self.donem_metni.replace('/', '.')}.xlsx", filetypes=[("Excel", "*.xlsx")])
        if not yol:
            return
        try:
            self._excel_yaz_db(yol)
        except PermissionError:
            messagebox.showerror("Kaydedilemedi", "Dosya Excel'de açık; kapatıp tekrar deneyin.", parent=self.a.kok)
            return
        self.ui.dosya_ac(yol)

    def _excel_yaz_db(self, yol):
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        wb = Workbook()
        ws = wb.active
        ws.title = "Özet"
        ws.append(["Defter Beyan — gönderim kontrolü", self.donem_metni.replace("-", " – ")])
        ws["A1"].font = Font(bold=True, size=13)
        ws.append([])
        ws.append(["Firma", "İşlem", "Gelir kalan", "Gider kalan", "Sabit kıymet", "Durum", "Not"])
        for h in ws[3]:
            h.font = Font(bold=True)
        for s in self.ham:
            a, b = kalan(s.get("gelir")), kalan(s.get("gider"))
            ozet = hata_ozetleri(s)
            ws.append([s["firma"], "Gönderme" if s.get("islem") == "gonder" else "Kontrol", a[0], b[0],
                       (a[1] + b[1]) or None, DURUM_YAZISI.get(s.get("durum"), s.get("durum")),
                       s.get("hata") or "; ".join(f"{n}× {m}" for m, n in ozet.items())])
        for harf, g in zip("ABCDEFG", (34, 12, 12, 12, 12, 30, 70)):
            ws.column_dimensions[harf].width = g
        ws2 = wb.create_sheet("Gönderilmeyenler")
        ws2.append(["Firma", "Tür", "Evrak No", "Evrak Tarihi", "Kategori", "Belge Türü", "Açıklama", "Tutar", "Sabit kıymet"])
        for h in ws2[1]:
            h.font = Font(bold=True)
        sari = PatternFill("solid", fgColor="FFF2CC")
        for s in self.ham:
            for tur, evrak, tarih, kat, belge, acik, tutar, sabit in self._kalan_satirlari(s):
                ws2.append([s["firma"], tur, evrak, tarih, kat, belge, acik, tutar, "EVET" if sabit else ""])
                if sabit:
                    for h in ws2[ws2.max_row]:
                        h.fill = sari
        for satir in ws2.iter_rows(min_row=2, min_col=8, max_col=8):
            for h in satir:
                h.number_format = '#,##0.00;[Red]-#,##0.00'
        for harf, g in zip("ABCDEFGHI", (34, 8, 16, 13, 24, 18, 36, 14, 13)):
            ws2.column_dimensions[harf].width = g
        wb.save(yol)

    # -- calistirma ------------------------------------------------------------------

    def _islem(self):
        return dict(ISLEMLER)[self.v_islem.get()]

    def komut(self, tam_firmalar=None):
        bas, bit = self.v_bas.get().strip(), self.v_bit.get().strip()
        try:
            if tarih_cozumle(bit) < tarih_cozumle(bas):
                raise ValueError("Bitiş tarihi başlangıçtan önce olamaz.")
        except ValueError as e:
            if "olamaz" in str(e):
                raise
            raise ValueError("Tarihleri GG/AA/YYYY biçiminde yazın (örnek 01/01/2026).")
        ayar_hazirla(self.klasor, self.a.ayarlar, {})
        komut = [self.ui.python_komutu(), "-u", str(self.klasor / "defter_beyan.py"), "--bitince-kapat",
                 "--tarih", f"{bas}-{bit}", "--islem", self._islem()]
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
        if self.a.surec or self.a.kz.calisiyor():
            messagebox.showinfo("Başka çalışma sürüyor", "Fatura indirme / Kâr-Zarar çalışıyor; bitince başlatın "
                                "(ikisi aynı anda Luca'ya girmemeli).", parent=self.a.kok)
            return True
        if self.surec:
            messagebox.showinfo("Çalışıyor", "Önce çalışan işlem bitsin ya da Durdur'a basın.", parent=self.a.kok)
            return True
        return False

    def _onayla(self, firma_sayisi=None):
        """Gonderme GERI ALINAMAYABILIR: her calismada acik onay istenir. Kontrol icin onay gerekmez."""
        if self._islem() != "gonder":
            return True
        kapsam = (f"{firma_sayisi} seçili firma" if firma_sayisi else
                  (f"'{self.v_firma.get().strip()}' içeren firmalar" if self.v_firma.get().strip() else "TÜM 2. sınıf firmalar"))
        return messagebox.askyesno(
            "Defter Beyan'a GÖNDER",
            f"{kapsam} için {self.v_bas.get().strip()} – {self.v_bit.get().strip()} arasındaki gönderilmemiş gelir ve "
            "giderler Defter Beyan Sistemine GÖNDERİLECEK.\n\nSıra: Cari Bilgi Sorgula → Kaydet → Gönder. Gönderilemeyenler "
            "raporlanır; sabit kıymet olanlar ayrıca belirtilir.\n\nDaha önce 'Yalnız kontrol' ile baktınız mı? "
            "Gönderilenler Luca'daki 'Defter Beyan Sisteminden Sil' ile geri alınabilir.\n\nDevam edilsin mi?",
            icon="warning", default="no", parent=self.a.kok)

    def calistir(self):
        if self._baska_calisiyor() or not self.a._giris_tamam_mi():
            return
        try:
            komut = self.komut()
        except ValueError as e:
            messagebox.showerror("Eksik bilgi", str(e), parent=self.a.kok)
            return
        if self._onayla():
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
        if self._onayla(len(firmalar)):
            self._baslat(komut)

    def _baslat(self, komut):
        super()._baslat(komut)
        if self.surec:
            self.ilerleme_etiketi.configure(text="Defter Beyan " + ("gönderiliyor…" if self._islem() == "gonder"
                                                                    else "kontrol ediliyor…"))

    def _bitti(self, kod):
        super()._bitti(kod)
        if kod == 0 and not self.durdurma_istendi:
            self.ilerleme_etiketi.configure(text=f"Tamamlandı: {len(self.ham)} firma. "
                                                 f"{self.ozet_etiketi.cget('text')}")
