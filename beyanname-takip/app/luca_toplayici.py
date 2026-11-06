"""Luca'ya tarayıcıyla girip mükellef listesini ve onaylanmış beyannameleri okuyan toplayıcı (TOPLAYICI=luca).

AKIŞ (hepsi Luca içinde; GİB/e-Beyanname'ye hiç bağlanılmaz):
  1. Luca girişi (üye no, kullanıcı, parola, doğrulama anahtarı → kod otomatik üretilir).
  2. Yönetici > Müşteri İşlemleri > Müşteri Listesi: tüm mükellefler (Kısa/Uzun Ad, VKN, TC, Kuruluş ve Kapanış
     Tarihi, Luca şirket kimliği). Sayfa HTML'inden okunur; sayfanın yazdığı "Kayıt Sayısı" ile doğrulanır.
  3. Muhasebe > Beyannameler > GİB Beyanname Takip: son günü yaklaşan her dönem ve beyanname türü için
     filtre (dönem, "Onaylanmış", tür) + "Beyannameleri Listele" → ekrandaki "Mükellef Adı" sütunu.
  4. Okunan firmalar "o dönem o beyannameyi vermiş" kaydı olur; karşılaştırmayı cekirdek yapar.

DURUM: Orkestrasyon (sorgu planı, tablo yorumlama, hata yönetimi) birim testlerle doğrulandı. Tarayıcıyı süren
GercekLucabot sınıfı, Dijital Stajyer'in lucabot paketindeki fonksiyonlara göre yazıldı ama GERÇEK LUCA'DA HİÇ
ÇALIŞTIRILMADI: ekran okuma ayrıntıları (3 aylık dönemin filtredeki karşılığı, tablo yapısı, sayfalama, tür adları)
ilk gerçek çalıştırmada doğrulanmalıdır. Bunun için LUCA_TANI=1 (aşağıda) kullanılır.

LİSANS: lucabot lisanslı bir pakettir ve bu depo herkese açıktır; lucabot BU DEPOYA KONMAZ. LUCABOT_YOLU
ortam değişkeni, içinde `lucabot/` klasörü olan dizini gösterir (özel depodan derlenen imajda /opt/luca-bot gibi).

Ortam değişkenleri (hesap başına; birden çok Luca hesabı için LUCA_HESAPLAR=ofis,isletme ve her biri için
LUCA_OFIS_UYE_NO gibi ön ekli adlar kullanılır; tek hesapta ön eksiz LUCA_UYE_NO yeter):
  LUCA_UYE_NO, LUCA_KULLANICI, LUCA_PAROLA, LUCA_DOGRULAMA_ANAHTARI (kimlik doğrulayıcı gizli anahtarı)
  LUCABOT_YOLU     lucabot paketinin bulunduğu dizin
  LUCA_TANI=1      tanı modu: giriş + ekranlar açılır, filtre seçenekleri ve ekran görüntüleri DATA_DIR/tani'ya
                   yazılır, veri KAYDEDİLMEZ. Env değişkenine gerek yok: web sayfasındaki "Tanı" sekmesi aynısını yapar.
  LUCA_UCAYLIK_DONEM=bit|bas   3 aylık dönemlerin Luca filtresindeki ayı (varsayılan bit)
Tarayıcı Xvfb altında (ekranlı kipte) çalışır: Dockerfile.luca'ya bakın.
"""

import contextlib
import io
import os
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from .kurallar import Tatiller
from .luca_ekran_okuma import (beyanname_satirlari, durum_sec, musteri_html_oku, musterileri_birlestir, secenek_esle,
                               sorgu_plani)


class LucaHatasi(RuntimeError):
    """Luca'dan veri alınamadı (mesaj kullanıcıya Telegram'da gösterilir; parola/anahtar içermez)."""


class TaniTamam(LucaHatasi):
    """Tanı çalışması bitti (hata değil); veri kaydedilmez."""


def kimlik_oku(env, hesap, tek_hesap):
    """Hesabın giriş bilgileri: önce ön ekli (LUCA_OFIS_PAROLA), tek hesapta ön eksiz (LUCA_PAROLA)."""
    on = f"LUCA_{hesap.upper()}_"
    sonuc = {}
    for alan, ad in (("uye_no", "UYE_NO"), ("kullanici_adi", "KULLANICI"), ("parola", "PAROLA"),
                     ("dogrulama_anahtari", "DOGRULAMA_ANAHTARI")):
        v = env.get(on + ad) or (env.get("LUCA_" + ad) if tek_hesap else "")
        sonuc[alan] = (v or "").strip()
    eksik = [a for a in ("uye_no", "kullanici_adi", "parola") if not sonuc[a]]
    if eksik:
        raise LucaHatasi(f"'{hesap}' hesabı için giriş bilgisi eksik: {', '.join(eksik)} (ortam değişkenlerini kontrol edin)")
    return sonuc


class LucaToplayici:
    def __init__(self, veri_dizini, env=os.environ, kopru_fabrikasi=None, tatil=None):
        self.veri = Path(veri_dizini)
        self.env = env
        self.tatil = tatil or Tatiller()
        self.kopru_fabrikasi = kopru_fabrikasi or (lambda hesap, kimlik, captcha: GercekLucabot(
            self.veri, hesap, kimlik, captcha, env))
        self.hesaplar = [h.strip() for h in (env.get("LUCA_HESAPLAR") or "ofis").split(",") if h.strip()]

    def tani(self, bugun, captcha=None):
        """Tanı: giriş + ekranları aç, seçenekleri ve ekran görüntülerini DATA_DIR/tani'ya yaz; veri kaydetme."""
        for hesap in self.hesaplar:
            kimlik = kimlik_oku(self.env, hesap, tek_hesap=len(self.hesaplar) == 1)
            kopru = self.kopru_fabrikasi(hesap, kimlik, captcha)
            try:
                self._hesap_topla(kopru, bugun, True)
            except TaniTamam:
                pass
            finally:
                kopru.kapat()
        return {"hesaplar": list(self.hesaplar)}

    def topla(self, bugun, captcha=None):
        tani = self.env.get("LUCA_TANI") == "1"
        sonuc = {"mukellefler": [], "beyannameler": [], "hesaplar": {}, "uyarilar": []}
        for hesap in self.hesaplar:
            kimlik = kimlik_oku(self.env, hesap, tek_hesap=len(self.hesaplar) == 1)
            kopru = self.kopru_fabrikasi(hesap, kimlik, captcha)
            try:
                mus, bey, uyarilar = self._hesap_topla(kopru, bugun, tani)
            finally:
                kopru.kapat()
            for m in mus:
                m["hesap"] = hesap
            for b in bey:
                b["hesap"] = hesap
            sonuc["mukellefler"] += mus
            sonuc["beyannameler"] += bey
            sonuc["uyarilar"] += [f"{hesap}: {u}" for u in uyarilar]
            sonuc["hesaplar"][hesap] = {"mukellef": len(mus), "beyanname": len(bey)}
        return sonuc

    def _hesap_topla(self, kopru, bugun, tani):
        uyarilar = []
        page = kopru.oturum_ac()
        if tani:
            kopru.tani_calistir(page, bugun)
            raise TaniTamam("Tanı modu tamamlandı (veri kaydedilmedi). Sonuçlar web sayfasında 'Tanı' sekmesinde; "
                            "bitince LUCA_TANI'yı kaldırın.")

        # yıl filtresi boşken Luca tüm müşterileri (kapanmışlar dahil) tek sayfada getirir; kapanışlar tarihten anlaşılır
        mus = musterileri_birlestir([kopru.musteri_listesi(page)])
        if not mus:
            raise LucaHatasi("Luca müşteri listesi boş okundu (ekran yapısı değişmiş olabilir; LUCA_TANI=1 ile bakın)")

        plan = sorgu_plani(bugun, self.tatil, ucaylik_ay=self.env.get("LUCA_UCAYLIK_DONEM", "bit"))
        bey, secenekler, ekran_yili = [], None, None
        for p in plan:
            if ekran_yili != p["sorgu_yil"]:
                ekran = kopru.beyanname_ekrani_ac(page, p["sorgu_yil"])
                ekran_yili = p["sorgu_yil"]
                secenekler = kopru.filtre_secenekleri(ekran)
            durum = durum_sec(secenekler.get("Beyanname Durum", []))
            if not durum:
                raise LucaHatasi("'Beyanname Durum' listesinde onaylanmış seçeneği bulunamadı "
                                 f"(seçenekler: {', '.join(secenekler.get('Beyanname Durum', []))})")
            turler = secenek_esle(secenekler.get("Beyanname", []), p["tur"])
            if not turler:
                # eksik seçenek sessizce geçilirse o türün HER mükellefi "eksik" görünür: durdurmak daha güvenli
                raise LucaHatasi(f"Luca'nın 'Beyanname' listesinde {p['tur']} türüne uyan seçenek yok "
                                 f"(seçenekler: {', '.join(secenekler.get('Beyanname', []))})")
            for tur_secenegi in turler:
                n, tablolar = kopru.sorgula(ekran, p["sorgu_ay"], p["sorgu_yil"], tur_secenegi, durum)
                satirlar = beyanname_satirlari(tablolar)
                if satirlar is None:
                    if n == 0:
                        satirlar = []
                    else:
                        raise LucaHatasi(f"{n} kayıt listelendi ama 'Mükellef Adı' sütunu okunamadı "
                                         "(LUCA_TANI=1 ile ekranı inceleyin)")
                if n is not None and n != len(satirlar):
                    uyarilar.append(f"{tur_secenegi} {p['sorgu_ay']:02d}/{p['sorgu_yil']}: ekranda {n} kayıt var, "
                                    f"{len(satirlar)} satır okundu (liste sayfalı olabilir)")
                for s in satirlar:
                    bey.append({"firma": s["firma"], "vkn": s["vkn"], "tur": tur_secenegi,
                                "donem": f"{p['ay']:02d}/{p['yil']}", "durum": durum})
        return mus, bey, uyarilar


class GercekLucabot:
    """Dijital Stajyer'in lucabot paketini sürer. Gerçek Luca'da DOĞRULANMADI (dosya başındaki nota bakın)."""

    FILTRE_ALANLARI = ["Paket Yükleme Tarihi", "Beyanname Dönemi", "Beyanname Durum", "Beyanname"]

    def __init__(self, veri_dizini, hesap, kimlik, captcha, env=os.environ):
        yol = env.get("LUCABOT_YOLU")
        if yol and yol not in sys.path:
            sys.path.insert(0, yol)
        try:
            from lucabot import giris, luca_beyanname, luca_ekran, luca_gezinme, musteri_listesi, ortak, tarayici
            from lucabot import bekleme
        except ImportError as e:
            raise LucaHatasi("lucabot paketi bulunamadı: LUCABOT_YOLU'nun lucabot/ klasörünü içeren dizini göstermesi "
                             f"gerekir ({e})") from e
        self.m = SimpleNamespace(giris=giris, lb=luca_beyanname, le=luca_ekran, gz=luca_gezinme,
                                 ml=musteri_listesi, ortak=ortak, tarayici=tarayici, bekleme=bekleme)
        # sunucuda Chrome yok ve süreç root: kendi Chromium'u, sandbox kapalı
        ortak.AYAR.update({"tarayici": "chromium", "tarayici_sandbox": False})
        self.hesap, self.kimlik, self.captcha = hesap, kimlik, captcha
        self.tani_klasoru = Path(veri_dizini) / "tani" / hesap
        self.profil = Path(veri_dizini) / "profil" / hesap
        self.tani_klasoru.mkdir(parents=True, exist_ok=True)
        self.log = self.tani_klasoru / "calisma.log"
        if self.log.exists() and self.log.stat().st_size > 5_000_000:
            self.log.unlink()
        self._pw = self._ctx = None
        self._tercih_firma = None

    @contextlib.contextmanager
    def _sessiz(self):
        """lucabot ekrana firma adı yazar; sunucu günlüğüne gitmesin diye çıktı dosyaya yönlendirilir."""
        tampon = io.StringIO()
        with contextlib.redirect_stdout(tampon):
            try:
                yield
            finally:
                try:
                    with open(self.log, "a", encoding="utf-8") as f:
                        f.write(tampon.getvalue())
                except OSError:
                    pass

    def oturum_ac(self):
        with self._sessiz():
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            self._ctx = self.m.tarayici.tarayici_ac(self._pw, self.profil, self.log)
            page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
            ayarlar = dict(self.kimlik, dogrulama_bekleme_dakika=0)
            page = self.m.giris.luca_oturumu_ac(self._ctx, page, ayarlar, True, self.tani_klasoru, self.log)
            if page is None:
                self._giris_hatasi_bildir()
                raise LucaHatasi(
                    "Luca girişi yapılamadı. Parola/doğrulama anahtarını, ya da Luca'nın captcha/SMS isteyip "
                    "istemediğini kontrol edin (Luca'da kimlik doğrulayıcı ile iki aşamalı doğrulama açıksa captcha çıkmaz). "
                    f"Ayrıntı: DATA_DIR/tani/{self.hesap}/")
            self.m.gz.firma_secici_bekle(page)
            return page

    def _giris_hatasi_bildir(self):
        try:
            for p in self._ctx.pages:
                if not p.is_closed():
                    png = p.screenshot()
                    (self.tani_klasoru / "giris-hatasi.png").write_bytes(png)
                    if self.captcha is not None:
                        self.captcha.telegram.foto_gonder(png, f"Luca girişi başarısız ({self.hesap}): ekran görüntüsü")
                    break
        except Exception:  # noqa: BLE001 - tanı çabası asıl hatayı gizlememeli
            pass

    def _musteri_html(self, page):
        """Açık Luca sayfalarının çerçevelerinden Müşteri Listesi tablosunu içeren HTML'i bulur (yoksa None)."""
        for fr in self.m.le.cerceveler(page):
            try:
                html = fr.content()
            except Exception:  # noqa: BLE001
                continue
            if "kisa-ad-td" in html and "sirket_id" in html:
                return html
        return None

    def musteri_listesi(self, page):
        """Yönetici > Müşteri İşlemleri > Müşteri Listesi: tüm müşteriler (yıl filtresi yok), sayfa HTML'inden okunur."""
        with self._sessiz():
            try:
                self.m.ml.musteri_listesini_ac(page, self.log)
            except LookupError as e:
                self.m.ml.tani_kaydet(page, self.tani_klasoru, self.log, "-menu")
                raise LucaHatasi(f"Müşteri Listesi ekranı açılamadı: {e}") from e
            html = self.m.bekleme.kosulu_bekle(page, lambda: self._musteri_html(page), 30000, aralik_ms=700)
            self.m.ml.tani_kaydet(page, self.tani_klasoru, self.log)
        if not html:
            raise LucaHatasi("Müşteri Listesi tablosu bulunamadı (sayfa yapısı değişmiş olabilir; Tanı sekmesine bakın)")
        kayitlar, toplam = musteri_html_oku(html)
        if toplam is not None and toplam != len(kayitlar):
            raise LucaHatasi(f"Müşteri Listesi sayfası {toplam} kayıt yazıyor ama {len(kayitlar)} satır okundu")
        if not kayitlar:
            raise LucaHatasi("Müşteri Listesi boş okundu")
        return kayitlar

    def beyanname_ekrani_ac(self, page, yil):
        with self._sessiz():
            try:
                self.m.le.acik_pencereleri_kapat(page)
                firma = self.m.lb.menusu_olan_firmayi_sec(page, None, self._tercih_firma, self.log, yil=yil)
                if firma:
                    self._tercih_firma = firma
                return self.m.lb.ekrani_ac(page, None, self.log)
            except LookupError as e:
                self.m.ml.tani_kaydet(page, self.tani_klasoru, self.log, "-menu", "beyanname-takip")
                raise LucaHatasi(f"GİB Beyanname Takip ekranı açılamadı: {e}") from e

    def _filtre_penceresi(self, ekran):
        lb, le = self.m.lb, self.m.le
        if not le.gorunur_mu(ekran, lb.ARAMA_PENCERESI, sure=500):
            le.dugmeye_bas(ekran, "Filtre", sure=8000)
            if not le.gorunur_mu(ekran, lb.ARAMA_PENCERESI, sure=8000):
                le.dugmeye_bas(ekran, "Filtre", sure=4000)
                if not le.gorunur_mu(ekran, lb.ARAMA_PENCERESI, sure=8000):
                    raise LucaHatasi(f"'{lb.ARAMA_PENCERESI}' penceresi açılmadı")
        for fr in le.cerceveler(ekran):
            try:
                bulunan = fr.evaluate(lb.ALANLAR_JS, self.FILTRE_ALANLARI)
            except Exception:  # noqa: BLE001
                continue
            if bulunan.get("Beyanname Dönemi"):
                return fr
        raise LucaHatasi("Filtre penceresindeki alanlar bulunamadı")

    def filtre_secenekleri(self, ekran):
        with self._sessiz():
            cerceve = self._filtre_penceresi(ekran)
            alan = lambda ad, sira=0: cerceve.locator(f'[data-lucabot-alan="{ad}#{sira}"]')  # noqa: E731
            return {ad: [t.strip() for t in alan(ad).locator("option").all_inner_texts()]
                    for ad in ("Beyanname", "Beyanname Durum")}

    def sorgula(self, ekran, ay, yil, tur_secenegi, durum_secenegi):
        """Filtreyi doldurup listeler. Dönen: (ekrandaki kayıt sayısı, tablolar[satır listeleri])."""
        lb, le, ml = self.m.lb, self.m.le, self.m.ml
        with self._sessiz():
            cerceve = self._filtre_penceresi(ekran)
            alan = lambda ad, sira=0: cerceve.locator(f'[data-lucabot-alan="{ad}#{sira}"]')  # noqa: E731
            for ad, sira, deger in (("Beyanname Dönemi", 0, lb.AYLAR[ay - 1]), ("Beyanname Dönemi", 1, str(yil)),
                                    ("Beyanname Durum", 0, durum_secenegi), ("Beyanname", 0, tur_secenegi)):
                if not lb._secenek_sec(alan(ad, sira), deger):
                    mevcut = ", ".join(t.strip() for t in alan(ad, sira).locator("option").all_inner_texts())
                    raise LucaHatasi(f"'{ad}' listesinde '{deger}' seçeneği yok (seçenekler: {mevcut})")
            for sira, d in enumerate((date(yil, ay, 1), date.today())):
                lb._tarih_yaz(alan("Paket Yükleme Tarihi", sira), d)
            eski = lb.bildirim_sayisi(ekran)
            if not le.dugmeye_bas(ekran, lb.LISTELE_DUGMESI, sure=8000):
                raise LucaHatasi(f"'{lb.LISTELE_DUGMESI}' düğmesine basılamadı")
            n = lb.listelenen_sayi(ekran, eski=eski)
            if n is None:
                ml.tani_kaydet(ekran, self.tani_klasoru, self.log, "-liste", "beyanname-takip")
                raise LucaHatasi("Liste sayısı bildirimi ('N adet beyanname kaydı listelendi') gelmedi")
            self.m.bekleme.sayfa_durulsun(ekran, azami_ms=1500, sessizlik_ms=500)
            tablolar = [satirlar for _, satirlar in ml.tablolari_al(ekran)]
            ml.tani_kaydet(ekran, self.tani_klasoru, self.log, f"-{tur_secenegi}-{ay:02d}-{yil}", "beyanname-takip")
        return n, tablolar

    def tani_calistir(self, page, bugun):
        """Tanı modu: müşteri listesini açar, beyanname ekranını açar, seçenekleri ve ekranları kaydeder."""
        import json
        self.musteri_listesi(page)
        ekran = self.beyanname_ekrani_ac(page, bugun.year)
        secenekler = self.filtre_secenekleri(ekran)
        (self.tani_klasoru / "filtre-secenekleri.json").write_text(
            json.dumps(secenekler, ensure_ascii=False, indent=1), encoding="utf-8")
        with self._sessiz():
            self.m.ml.tani_kaydet(ekran, self.tani_klasoru, self.log, "-filtre", "beyanname-takip")

    def kapat(self):
        with self._sessiz():
            try:
                if self._ctx is not None:
                    self.m.tarayici.tarayiciyi_kapat(self._ctx)
            finally:
                if self._pw is not None:
                    try:
                        self._pw.stop()
                    except Exception:  # noqa: BLE001
                        pass
