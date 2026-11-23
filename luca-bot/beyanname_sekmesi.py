# -*- coding: utf-8 -*-
"""Luca Bot arayuzunun "Beyanname Takip" sekmesi.

Repodaki ayri beyanname-takip/ programini (Luca'daki mukellef listesini ve verilmis beyannameleri karsilastirip son gune
yaklasirken verilmemisleri Telegram/e-posta ile bildiren web uygulamasi) buradan yonetir:
  * ayarlar (sayfa sifresi, e-posta/Telegram, GIB gun sayisi) yerel/ayarlar.env'ye yazilir; Luca girisi Dijital Stajyer'den alinabilir
  * Baslat / Durdur: program arka planda calisir, bu pencere kapansa da devam eder (uyarilar surer)
  * saglik, son veri durumu ve beyanname tablosu programin kendi API'sinden okunur; gunlugun sonu gosterilir
Tam ozellikler (mukellef ayarlari, captcha, tani, onizleme) icin "Tarayicida Ac".
Dikkat: program zamanlanmis saatlerde Luca'ya kendi tarayicisiyla girer; ayni kullanici baska bir Luca calismasiyla cakisabilir.
"""

import threading
import time
import webbrowser
from datetime import date, datetime
from tkinter import messagebox, ttk
import tkinter as tk

from lucabot import beyanname_takip as bt
from tablo_gorunumu import SiralaFiltreTablosu

DURUM_YAZISI = {"verildi": "Verildi", "eksik": "EKSİK", "onaysiz": "Eksik (ayar onaysız)", "sgk_eksik": "SGK e-Bildirge eksik",
                "muaf": "Muaf"}
DURUM_ETIKET = {"verildi": "tamam", "eksik": "eksik", "onaysiz": "uyari", "sgk_eksik": "uyari", "muaf": "soluk"}
SAGLIK_ARALIK = 3.0       # sn
VERI_ARALIK = 60.0        # sn
GUNLUK_ARALIK = 2.0       # sn


def kalan_yazisi(kalan):
    if kalan is None:
        return ""
    if kalan < 0:
        return f"{-kalan} gün geçti"
    return "BUGÜN" if kalan == 0 else f"{kalan} gün"


def gun_yazisi(iso):
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(iso or "")


def hesap_adi(hesap):
    """Madde hesabi ('ofis' / 'isletme') -> gorunen ad ('Adem Yılmaz' / 'Ali Karaahmet'); bos hesap 'ofis' sayilir (programin varsayilani)."""
    from lucabot import hesaplar
    return hesaplar.gorunen_ad(hesap or "ofis")


def satir_uret(m):
    """Program maddesi -> tablo satiri (Mukellef, Luca hesabi, Beyanname, Donem, Son gun, Kalan, Durum, Not)."""
    durum = m.get("durum") or ""
    notlar = []
    if m.get("kapanis_donemi"):
        notlar.append("kapanış dönemi: süre farklı olabilir")
    if durum == "onaysiz":
        notlar.append("mükellef ayarı onaylanmamış")
    return (m.get("ad", ""), hesap_adi(m.get("hesap")), m.get("tur_ad") or m.get("tur", ""), m.get("etiket") or m.get("donem", ""),
            gun_yazisi(m.get("son_gun")), kalan_yazisi(m.get("kalan")), DURUM_YAZISI.get(durum, durum), "; ".join(notlar))


class BeyannameSekmesi:
    def __init__(self, arayuz, ebeveyn, ui):
        self.a = arayuz
        self.ui = ui
        self.klasor = bt.klasor()
        self.govde = tk.Frame(ebeveyn, bg=ui.ZEMIN)
        self.calisiyor_mu = False
        self.maddeler = []
        self._saglik_sonuc = None
        self._saglik_calisiyor = False
        self._veri_sonuc = None
        self._veri_calisiyor = False
        self._son_saglik = self._son_veri = self._son_gunluk = 0.0
        self._hizli_bitis = 0.0      # 'Simdi cek' sonrasi veri sik yoklanir
        self._islem_calisiyor = False
        self._mesaj = None
        if self.klasor is None:
            tk.Label(self.govde, text="beyanname-takip klasörü bulunamadı.\n\nluca-bot klasörünün yanında (aynı üst klasörde) "
                     "`beyanname-takip` klasörü olmalı.", font=ui.GOVDE, fg=ui.TURUNCU, bg=ui.ZEMIN,
                     justify="left").pack(padx=30, pady=30, anchor="w")
            return
        form = bt.varsayilan_form(self.klasor, self.a.ayarlar)
        self.v = {ad: tk.StringVar(value=form[ad]) for ad in ("WEB_SIFRE", "PORT", "LUCA_GIB_GUN", "MAIL_ALICI", "RESEND_API_KEY",
                                                               "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID")}
        self.v_luca = tk.BooleanVar(value=form["luca_ayarlardan"])
        self.kapsam_secenekleri = bt.kapsam_etiketleri(self.a.ayarlar)           # [(kod, etiket)]
        etiket = dict(self.kapsam_secenekleri).get(form.get("KAPSAM"), self.kapsam_secenekleri[0][1])
        self.v_kapsam = tk.StringVar(value=etiket)
        self._tarama_suruyor = False
        self._iptal = threading.Event()
        self._kalici_veri_metni = ""        # tek seferlik tarama bitip program durunca ozet satiri silinmesin
        self.v_tek_sefer = tk.BooleanVar(value=form.get("TEK_SEFER", True))
        self.v_ozet = tk.BooleanVar(value=form.get("OZET_GONDER", False))
        self.v["MAIL_ALICI_BIR"] = tk.StringVar(value=form.get("MAIL_ALICI_BIR") or "")
        self._sol_panel()
        tk.Frame(self.govde, bg=ui.CIZGI, width=1).pack(side="left", fill="y")
        self._sag_panel()
        self._saglik_iste()

    # -- arayuz ---------------------------------------------------------------

    def _sol_panel(self):
        u = self.ui
        dis = tk.Frame(self.govde, bg=u.ZEMIN, width=330)
        dis.pack(side="left", fill="y")
        dis.pack_propagate(False)
        alt = tk.Frame(dis, bg=u.ZEMIN)
        alt.pack(side="bottom", fill="x", padx=22, pady=(4, 14))
        self.baslat_dugmesi = u.dugme(alt, "Başlat", self.baslat, ana=True)
        self.baslat_dugmesi.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.durdur_dugmesi = u.dugme(alt, "Durdur", self.durdur, state="disabled")
        self.durdur_dugmesi.pack(side="left", fill="x", expand=True)
        p = tk.Frame(dis, bg=u.ZEMIN, padx=22, pady=16)
        p.pack(side="top", fill="both", expand=True)

        def alan(baslik, ad, gizli=False, ilk=False):
            tk.Label(p, text=baslik, font=u.KUCUK, fg=u.ETIKET, bg=u.ZEMIN, anchor="w").pack(fill="x", pady=(0 if ilk else 8, 3))
            u.giris_kutusu(p, self.v[ad], gizli=gizli).pack(fill="x", ipady=4)

        u.bolum_basligi(p, "Web sayfası").pack(fill="x")
        alan("Sayfa şifresi (tarayıcıdaki giriş için)", "WEB_SIFRE")
        alan("Port", "PORT")
        u.bolum_basligi(p, "Luca").pack(fill="x", pady=(14, 0))
        tk.Checkbutton(p, text="Giriş bilgilerini Dijital Stajyer ayarlarından al", variable=self.v_luca, font=u.KUCUK,
                       **self.a._kutu_renk()).pack(anchor="w", pady=(6, 0))
        alan("GİB'den Getir kaç günü kapsasın (1-31)", "LUCA_GIB_GUN")
        tk.Label(p, text="Taranacak Luca hesabı / firmalar", font=u.KUCUK, fg=u.ETIKET, bg=u.ZEMIN, anchor="w").pack(fill="x", pady=(8, 3))
        self.kapsam_kutusu = ttk.Combobox(p, textvariable=self.v_kapsam, values=[e for _, e in self.kapsam_secenekleri], state="readonly",
                                          font=u.KUCUK)
        self.kapsam_kutusu.pack(fill="x", ipady=3)
        tk.Checkbutton(p, text="Başlat = tek tarama; bitince programı durdur", variable=self.v_tek_sefer, font=u.KUCUK,
                       **self.a._kutu_renk()).pack(anchor="w", pady=(6, 0))
        tk.Checkbutton(p, text="Tarama bitince eksik özetini e-posta/Telegram ile gönder", variable=self.v_ozet, font=u.KUCUK,
                       **self.a._kutu_renk()).pack(anchor="w", pady=(2, 0))
        u.bolum_basligi(p, "Bildirim").pack(fill="x", pady=(14, 0))
        alan("E-posta alıcı", "MAIL_ALICI", ilk=True)
        alan("E-posta alıcı: adı \"1\" ile başlayan firmalar (Gürbetçi)", "MAIL_ALICI_BIR")
        alan("Resend API anahtarı (boşsa SMTP ayarları kullanılır)", "RESEND_API_KEY", gizli=True)
        alan("Telegram bot token (isteğe bağlı)", "TELEGRAM_TOKEN", gizli=True)
        alan("Telegram chat id", "TELEGRAM_CHAT_ID")

    def _sag_panel(self):
        u = self.ui
        p = tk.Frame(self.govde, bg=u.ZEMIN, padx=22, pady=16)
        p.pack(side="left", fill="both", expand=True)
        ust = tk.Frame(p, bg=u.ZEMIN)
        ust.pack(fill="x")
        self.durum_etiketi = tk.Label(ust, text="Kontrol ediliyor…", font=u.GOVDE_KALIN, fg=u.YAZI, bg=u.ZEMIN, anchor="w")
        self.durum_etiketi.pack(side="left")
        self.adres_etiketi = tk.Label(ust, text="", font=u.KUCUK, fg=u.SOLUK, bg=u.ZEMIN)
        self.adres_etiketi.pack(side="left", padx=(12, 0))
        self.veri_etiketi = tk.Label(p, text="", font=u.KUCUK, fg=u.SOLUK, bg=u.ZEMIN, anchor="w", justify="left", wraplength=760)
        self.veri_etiketi.pack(fill="x", pady=(2, 4))
        self.uyari_etiketi = tk.Label(p, text="Program zamanlanmış saatlerde Luca'ya kendi tarayıcısıyla girer; aynı kullanıcıyla "
                                      "Fatura İndirme / Kâr-Zarar / Defter Beyan çalışırken Luca oturumu düşebilir. Bu pencereyi "
                                      "kapatsanız da program çalışmaya devam eder (durdurmak için Durdur).",
                                      font=u.KUCUK, fg=u.ALTIN_FG, bg=u.ZEMIN, anchor="w", justify="left", wraplength=760)
        self.uyari_etiketi.pack(fill="x", pady=(0, 6))

        alt = tk.Frame(p, bg=u.ZEMIN)
        alt.pack(side="bottom", fill="x", pady=(8, 0))
        u.dugme(alt, "Tarayıcıda Aç", self.tarayicida_ac, ana=True).pack(side="left")
        u.dugme(alt, "Şimdi Luca'dan Çek", self.simdi_cek).pack(side="left", padx=8)
        u.dugme(alt, "Yenile", self.yenile).pack(side="left")
        u.dugme(alt, "Ayarları Kaydet", self.kaydet).pack(side="left", padx=8)
        u.dugme(alt, "Klasörü Aç", lambda: u.dosya_ac(self.klasor / "yerel")).pack(side="left")
        self.mesaj_etiketi = tk.Label(alt, text="", font=u.KUCUK, fg=u.SOLUK, bg=u.ZEMIN)
        self.mesaj_etiketi.pack(side="right")

        cerceve = tk.Frame(p, bg=u.KONSOL, highlightthickness=1, highlightbackground=u.KONSOL_KENAR, height=130)
        cerceve.pack(side="bottom", fill="x", pady=(8, 0))
        cerceve.pack_propagate(False)
        self.log = tk.Text(cerceve, bg=u.KONSOL, fg=u.KONSOL_FG, font=u.KONSOL_YAZI, relief="flat", wrap="none", padx=12, pady=8,
                           insertbackground=u.YAZI, state="disabled", highlightthickness=0, bd=0)
        kaydir = tk.Scrollbar(cerceve, command=self.log.yview, bg=u.KONSOL, troughcolor=u.KONSOL, activebackground=u.KENAR,
                              relief="flat", bd=0)
        self.log.configure(yscrollcommand=kaydir.set)
        kaydir.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

        sutunlar = ("Mükellef", "Luca hesabı", "Beyanname", "Dönem", "Son gün", "Kalan", "Durum", "Not")
        genislik = (220, 120, 120, 100, 90, 80, 150, 200)
        self.tablo = SiralaFiltreTablosu(p, u, sutunlar, genislik, yazi={0, 1, 2, 3, 4, 5, 6, 7}, secim="extended",
                                         filtreler=("Luca hesabı", "Dönem", "Durum", "Beyanname"),
                                         etiketler={"tamam": u.YESIL_FG, "eksik": u.KIRMIZI, "uyari": u.UYARI_FG, "soluk": u.SOLUK})
        self.tablo.pack(fill="both", expand=True)

    # -- ayar / baslat / durdur ------------------------------------------------

    def _form(self):
        form = {ad: v.get() for ad, v in self.v.items()}
        form["luca_ayarlardan"] = self.v_luca.get()
        form["TEK_SEFER"] = self.v_tek_sefer.get()
        form["OZET_GONDER"] = self.v_ozet.get()
        form["KAPSAM"] = next((k for k, e in self.kapsam_secenekleri if e == self.v_kapsam.get()), self.kapsam_secenekleri[0][0])
        return form

    def _bildir(self, metin, hata=False):
        self._mesaj = (metin, hata)

    def kaydet(self, sessiz=False):
        """Formu yerel/ayarlar.env'ye yazar; basariliysa True."""
        form = self._form()
        hatalar = bt.dogrula(form)
        if hatalar:
            messagebox.showerror("Eksik bilgi", "\n".join(hatalar), parent=self.a.kok)
            return False
        if form["luca_ayarlardan"] and not all(str(self.a.ayarlar.get(a) or "").strip() for a in ("uye_no", "kullanici_adi", "parola")):
            messagebox.showerror("Luca bilgisi yok", "Dijital Stajyer'de Luca giriş bilgileri girilmemiş (Ayarlar). Önce onları girin "
                                 "ya da kutuyu kaldırıp ayarlar.env'yi elle doldurun.", parent=self.a.kok)
            return False
        try:
            bt.env_hazirla(self.klasor, form, self.a.ayarlar)
        except OSError as e:
            messagebox.showerror("Kaydedilemedi", f"Ayarlar yazılamadı: {e}", parent=self.a.kok)
            return False
        if not sessiz:
            self._bildir("Ayarlar kaydedildi" + (" (program çalışıyorsa yeniden başlatın)" if self.calisiyor_mu else ""))
        return True

    def baslat(self):
        if self._islem_calisiyor:
            return
        eksik = bt.eksik_paketler()
        if eksik and not self.calisiyor_mu:
            messagebox.showerror("Paket eksik", "Şu paketler kurulu değil: " + ", ".join(eksik) + "\n\nKurulum sihirbazındaki 'Eksik bileşenleri "
                                 "kur'a basın ya da luca-bot klasöründe `pip install -r requirements.txt` çalıştırın.", parent=self.a.kok)
            return
        tek_sefer = self.v_tek_sefer.get()
        if self.calisiyor_mu:
            if not tek_sefer:
                messagebox.showinfo("Zaten çalışıyor", "Program zaten çalışıyor.", parent=self.a.kok)
                return
            if not messagebox.askyesno("Program zaten çalışıyor", "Program zaten çalışıyor. Yeni ayarların (hesap kapsamı, e-posta) geçerli olması için "
                                       "önce durdurulup yeniden başlatılacak, tarama yapılacak ve bitince program durdurulacak.\n\nDevam edilsin mi?",
                                       parent=self.a.kok):
                return
            self._durdur_sessiz()
        if not self.kaydet(sessiz=True):
            return
        port = int(self.v["PORT"].get())
        if bt.saglikli_mi(port):
            # baska bir program (ya da durdurulamayan eski surec) portta yanit veriyor: izleme ona baglanir, tarama yapilmaz
            self.calisiyor_mu = True
            self._durumu_yaz()
            self._son_veri = 0.0
            self._bildir(f"Program {port} portunda zaten çalışıyor; izleme bağlandı")
            return
        self._islem_calisiyor = True
        self.baslat_dugmesi.configure(state="disabled")
        self._bildir("Başlatılıyor…")
        self._iptal.clear()
        ozet = self.v_ozet.get()
        sifre = self.v["WEB_SIFRE"].get()

        def is_():
            try:
                bt.baslat(self.klasor, self.ui.python_komutu(), port, bt.KOK)
                for _ in range(40):                       # en gec ~20 sn: acilis suresi
                    if bt.saglikli_mi(port, 0.5):
                        self._bildir("Program başladı")
                        break
                    time.sleep(0.5)
                else:
                    self._bildir("Program başlamadı — günlüğe bakın (aşağıda)", hata=True)
                    return
                if tek_sefer:
                    self._tek_tarama(port, sifre, ozet)
            except Exception as e:  # noqa: BLE001
                self._bildir(f"Başlatılamadı: {type(e).__name__}: {e}", hata=True)
            finally:
                self._islem_calisiyor = False
                self._tarama_suruyor = False
                self._son_saglik = 0.0
        threading.Thread(target=is_, daemon=True).start()

    TARAMA_AZAMI_SN = 90 * 60       # tek tarama icin en uzun bekleme (CAPTCHA / yavas Luca dahil)

    def _tek_tarama(self, port, sifre, ozet):
        """Program acildiktan sonra Luca taramasini baslatir (Luca penceresi gorunur acilir, islemler izlenir), bitince sonucu tabloya yazar ve
        programi durdurur. (Arka plan is parcacigindan cagrilir.)"""
        self._tarama_suruyor = True
        onceki = bt.durum_oku(port, sifre)
        onceki_toplama = (onceki.get("son_toplama") or {}).get("zaman")
        onceki_rapor = (onceki.get("son_rapor") or {}).get("zaman")
        if ozet:
            bt.rapor_gonder(port, sifre)               # veriyi cek + eksik ozetini e-posta/Telegram ile gonder
        else:
            bt.simdi_cek(port, sifre)                  # yalniz veriyi cek (mesaj gitmez)
        self._hizli_bitis = time.monotonic() + self.TARAMA_AZAMI_SN
        self._bildir("Luca taranıyor… (açılan Luca penceresinden işlemleri izleyebilirsiniz)")
        bitis = time.monotonic() + self.TARAMA_AZAMI_SN
        sonuc = (False, False, "Tarama beklenen sürede bitmedi (90 dk); program açık bırakıldı")
        while time.monotonic() < bitis and not self._iptal.is_set():
            time.sleep(3.0)
            try:
                durum = bt.durum_oku(port, sifre)
            except (OSError, ValueError):
                continue                                  # program anlik yanit vermedi
            if durum.get("captcha_bekliyor"):
                self._bildir("CAPTCHA bekliyor — Telegram'dan ya da \"Tarayıcıda Aç\" sayfasından cevaplayın")
            bitti, ok, mesaj = bt.tarama_bitti(durum, onceki_toplama, onceki_rapor, ozet)
            if bitti:
                sonuc = (True, ok, mesaj)
                break
        else:
            if self._iptal.is_set():
                return                                    # kullanici Durdur'a bastı: durdurma onun elinde
        bitti, ok, mesaj = sonuc
        try:                                              # program durmadan once son veriyi tabloya al
            veri = bt.veri_oku(port, sifre)
            self._veri_sonuc = ("ok", veri)
            self._tarama_ozeti_hazirla(veri)
        except (OSError, ValueError):
            pass
        if bitti:
            self._iptal.set()
            ok_durdu, durdu_mesaj = bt.durdur(self.klasor)
            self._bildir(("Tarama bitti: " if ok else "Tarama TAMAMLANAMADI: ") + mesaj + (" — program durduruldu" if ok_durdu else f" — {durdu_mesaj}"),
                         hata=not ok)
        else:
            self._bildir(mesaj, hata=True)

    def _tarama_ozeti_hazirla(self, veri):
        """Program durunca da gorunecek ozet satiri (Luca verisi zamani, madde / eksik sayisi)."""
        d, maddeler = veri["durum"], veri["maddeler"]
        v = d.get("veri") or {}
        eksik = [m for m in maddeler if m.get("durum") in ("eksik", "onaysiz", "sgk_eksik")]
        zaman = ""
        if v.get("zaman"):
            try:
                zaman = "Luca verisi: " + datetime.fromisoformat(v["zaman"]).strftime("%d/%m/%Y %H:%M") + "  ·  "
            except ValueError:
                pass
        self._kalici_veri_metni = f"{zaman}{len(maddeler)} madde, {len(eksik)} verilmemiş (son tarama; program durduruldu)"

    def _durdur_sessiz(self):
        """Onay sormadan programi durdurur (yeniden baslatmadan once)."""
        try:
            bt.durdur(self.klasor)
        except Exception:  # noqa: BLE001
            pass
        for _ in range(20):
            if not bt.saglikli_mi(int(self.v["PORT"].get()), 0.5):
                break
            time.sleep(0.5)
        self.calisiyor_mu = False
        self._durumu_yaz()

    def durdur(self):
        if self._islem_calisiyor and not self._tarama_suruyor:
            return
        if not messagebox.askyesno("Durdur", "Beyanname Takip durdurulsun mu?\n\nDurunca uyarı mesajları gitmez (son gün akşamları dahil); "
                                   "yeniden başlatana kadar kontrol yapılmaz.", parent=self.a.kok):
            return
        self._iptal.set()                    # sürüyorsa tek tarama bekleyişi bırakılır
        self._islem_calisiyor = True
        self.durdur_dugmesi.configure(state="disabled")
        self._bildir("Durduruluyor…")

        def is_():
            try:
                ok, mesaj = bt.durdur(self.klasor)
                self._bildir(mesaj, hata=not ok)
            except Exception as e:  # noqa: BLE001
                self._bildir(f"Durdurulamadı: {type(e).__name__}: {e}", hata=True)
            finally:
                self._islem_calisiyor = False
                self._son_saglik = 0.0
        threading.Thread(target=is_, daemon=True).start()

    def tarayicida_ac(self):
        if not self.calisiyor_mu:
            messagebox.showinfo("Çalışmıyor", "Önce Başlat'a basın.", parent=self.a.kok)
            return
        webbrowser.open(bt.adres(self.v["PORT"].get()))

    def yenile(self):
        self._son_saglik = self._son_veri = 0.0

    def simdi_cek(self):
        """Programa Luca'dan veriyi simdi cekmesini soyler (Telegram'a mesaj atmaz); gerekirse CAPTCHA tarayicidaki sayfadan cevaplanir."""
        if not self.calisiyor_mu:
            messagebox.showinfo("Çalışmıyor", "Önce Başlat'a basın.", parent=self.a.kok)
            return
        if not messagebox.askyesno("Şimdi çek", "Program Luca'ya girip mükellef ve beyanname verisini şimdi çekecek (birkaç dakika sürebilir).\n"
                                   "Aynı Luca kullanıcısıyla başka bir çalışma yokken yapın. Devam edilsin mi?", parent=self.a.kok):
            return
        port, sifre = int(self.v["PORT"].get()), self.v["WEB_SIFRE"].get()
        self._bildir("Çekim başlatılıyor…")

        def is_():
            try:
                bt.simdi_cek(port, sifre)
                self._bildir("Çekim başladı; sonuç tabloya otomatik gelir")
                self._hizli_bitis = time.monotonic() + 600
            except Exception as e:  # noqa: BLE001
                self._bildir(f"Çekim başlatılamadı: {type(e).__name__}: {e}", hata=True)
        threading.Thread(target=is_, daemon=True).start()

    def sekme_secildi(self):
        if self.klasor is not None:
            self.yenile()

    # -- arka plan okumalari (arayuz dongusunden) ------------------------------------

    def _saglik_iste(self):
        if self._saglik_calisiyor or self.klasor is None:
            return
        self._saglik_calisiyor = True

        def is_():
            try:
                port = int(self.v["PORT"].get())
            except ValueError:
                port = bt.VARSAYILAN_PORT
            self._saglik_sonuc = bt.saglikli_mi(port)
            self._saglik_calisiyor = False
        threading.Thread(target=is_, daemon=True).start()

    def _veri_iste(self):
        if self._veri_calisiyor or not self.calisiyor_mu:
            return
        self._veri_calisiyor = True
        port, sifre = int(self.v["PORT"].get()), self.v["WEB_SIFRE"].get()

        def is_():
            try:
                self._veri_sonuc = ("ok", bt.veri_oku(port, sifre))
            except Exception as e:  # noqa: BLE001
                self._veri_sonuc = ("hata", f"{type(e).__name__}: {e}")
            self._veri_calisiyor = False
        threading.Thread(target=is_, daemon=True).start()

    def tikla(self):
        """Arayuz dongusu: saglik/veri/gunluk yoklamalarini tetikler ve sonuclari ekrana yazar."""
        if self.klasor is None:
            return
        simdi = time.monotonic()
        if simdi - self._son_saglik >= SAGLIK_ARALIK:
            self._son_saglik = simdi
            self._saglik_iste()
        if self._saglik_sonuc is not None:
            var = self._saglik_sonuc
            self._saglik_sonuc = None
            if var != self.calisiyor_mu or self.durum_etiketi.cget("text") == "Kontrol ediliyor…":
                self.calisiyor_mu = var
                self._durumu_yaz()
                if var:
                    self._son_veri = 0.0
        if self.calisiyor_mu and simdi - self._son_veri >= (4.0 if simdi < self._hizli_bitis else VERI_ARALIK):
            self._son_veri = simdi
            self._veri_iste()
        if self._veri_sonuc is not None:
            tur, deger = self._veri_sonuc
            self._veri_sonuc = None
            self._veriyi_yaz(tur, deger)
        if simdi - self._son_gunluk >= GUNLUK_ARALIK and self.govde.winfo_ismapped():
            self._son_gunluk = simdi
            self._gunlugu_yaz()
        if self._mesaj is not None:
            metin, hata = self._mesaj
            self._mesaj = None
            self.mesaj_etiketi.configure(text=metin, fg=self.ui.KIRMIZI if hata else self.ui.SOLUK)

    def _durumu_yaz(self):
        u = self.ui
        if self.calisiyor_mu:
            self.durum_etiketi.configure(text="● Çalışıyor", fg=u.YESIL_FG)
            self.adres_etiketi.configure(text=bt.adres(self.v["PORT"].get()))
        else:
            self.durum_etiketi.configure(text="○ Çalışmıyor", fg=u.SOLUK)
            self.adres_etiketi.configure(text="")
            self.veri_etiketi.configure(text=self._kalici_veri_metni, fg=self.ui.SOLUK)
        self.baslat_dugmesi.configure(state="disabled" if self.calisiyor_mu else "normal")
        self.durdur_dugmesi.configure(state="normal" if self.calisiyor_mu else "disabled")

    def _veriyi_yaz(self, tur, deger):
        if tur == "hata":
            self.veri_etiketi.configure(text=f"Veri okunamadı: {deger}", fg=self.ui.KIRMIZI)
            return
        d, maddeler = deger["durum"], deger["maddeler"]
        self.maddeler = maddeler
        v = d.get("veri") or {}
        parca = []
        if v.get("zaman"):
            try:
                parca.append("Luca verisi: " + datetime.fromisoformat(v["zaman"]).strftime("%d/%m/%Y %H:%M") + (" (ESKİ)" if v.get("eski") else ""))
            except ValueError:
                parca.append("Luca verisi: " + str(v["zaman"]))
        else:
            parca.append("Luca'dan henüz veri alınmadı")
        if v.get("hata"):
            parca.append(f"Son çekim hatası: {v['hata']}")
        kanallar = d.get("kanallar") or []
        parca.append("Bildirim: " + (", ".join(kanallar) if kanallar else ("Telegram hazır" if d.get("telegram") else "kanal yok — Telegram/e-posta ayarlarını girin")))
        if d.get("captcha_bekliyor"):
            parca.append("CAPTCHA bekliyor — tarayıcıdaki sayfadan cevaplayın")
        eksik = [m for m in maddeler if m.get("durum") in ("eksik", "onaysiz", "sgk_eksik")]
        parca.append(f"{len(maddeler)} madde, {len(eksik)} verilmemiş")
        self.veri_etiketi.configure(text="  ·  ".join(parca), fg=self.ui.TURUNCU if (v.get("hata") or d.get("captcha_bekliyor")) else self.ui.SOLUK)
        sirali = sorted(maddeler, key=lambda m: (m.get("son_gun") or "", m.get("ad") or ""))
        self.tablo.doldur([satir_uret(m) for m in sirali], [DURUM_ETIKET.get(m.get("durum"), "") for m in sirali])

    def _gunlugu_yaz(self):
        metin = bt.log_sonu(self.klasor, 40)
        if metin == getattr(self, "_son_gunluk_metni", None):
            return
        self._son_gunluk_metni = metin
        alttaydi = self.log.yview()[1] >= 0.999
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.insert("end", metin)
        self.log.configure(state="disabled")
        if alttaydi:
            self.log.see("end")

    # -- ana pencere baglantilari ------------------------------------------------

    def calisiyor(self):
        """Ana pencerenin 'calisan is var' kontrolu icin: bu sekmenin programi ayri surectir; pencere kapanmasini engellemez."""
        return False

    def kapat(self):
        """Pencere kapanirken program DURDURULMAZ (uyarilar surmeli); yapilacak bir sey yok."""
