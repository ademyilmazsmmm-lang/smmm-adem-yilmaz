"""Luca'ya tarayıcıyla girip mükellef listesini ve onaylanmış beyannameleri okuyan toplayıcı (TOPLAYICI=luca).

AKIŞ (hepsi Luca içinde; GİB/e-Beyanname'ye hiç bağlanılmaz):
  1. Luca girişi (üye no, kullanıcı, parola, doğrulama anahtarı → kod otomatik üretilir).
  2. Yönetici > Müşteri İşlemleri > Müşteri Listesi: tüm mükellefler (Kısa/Uzun Ad, VKN, TC, Kuruluş ve Kapanış
     Tarihi, Luca şirket kimliği). Sayfa HTML'inden okunur; sayfanın yazdığı "Kayıt Sayısı" ile doğrulanır.
  3. Muhasebe > Beyannameler > GİB Beyanname Takip: önce "GİB'den Getir" (Luca beyannameleri kendiliğinden çekmez; arama
     ekranı yalnızca daha önce GİB'den getirilmiş kayıtları bulur; bitince İşlem Takip penceresinde yazı çıkar), sonra "Beyanname Durum = Tümü" ve "Paket Yükleme
     Tarihi" aralığıyla "Beyannameleri Listele" (varsayılan durum "Onaylanmış"tır: Tümü seçilmezse hatalılar görünmez). Ekranın kendi isteğinin yanıtı (beyan_listele.jq,
     JSON) okunur: tür (beyannameKodu), dönem, durum (Onaylanmış/Hatalı/İptal Edilmiş), VKN, kısa ad. Tablo okunmaz.
  4. Karşılaştırmayı cekirdek yapar (onaylı kayıt = verildi; yalnızca hatalı/iptal = "gönderilmiş ama onaysız").

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
  LUCA_MUSTERI_YILI=otomatik|yok|2027,2026   müşteri listesi yıl filtresi (otomatik: yalnızca bu yıl)
  LUCA_GIB_GETIR=1|0   okumadan önce "GİB'den Getir"e bas (varsayılan 1); LUCA_GIB_GETIR_SN: en çok bekleme (180)
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
from .luca_ekran_okuma import (beyanname_json_kayitlari, musteri_html_filtre, musteri_html_oku, musteri_yillari,
                               musterileri_birlestir, yukleme_araligi)


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

        # Ekranı aç, Yıl'ı seç, Ara'ya bas, sonra oku: yalnızca o yılın dönemi açılmış firmalar gelir (kapanış tarihi
        # girilmemiş eski firmalar böylece listeye girmez). Geçen yıl okunmaz. LUCA_MUSTERI_YILI=yok: filtresiz.
        yillar = musteri_yillari(bugun, self.env.get("LUCA_MUSTERI_YILI"))
        if yillar:
            mus = musterileri_birlestir([kopru.musteri_listesi(page, y, ac=(i == 0)) for i, y in enumerate(yillar)])
        else:
            mus = musterileri_birlestir([kopru.musteri_listesi(page)])
        if not mus:
            raise LucaHatasi("Luca müşteri listesi boş okundu (ekran yapısı değişmiş olabilir; LUCA_TANI=1 ile bakın)")

        ekran = kopru.beyanname_ekrani_ac(page, bugun.year)
        if self.env.get("LUCA_GIB_GETIR", "1") != "0":
            # Luca beyannameleri kendiliğinden GİB'den çekmez: "GİB'den Getir" düğmesi çeker. Düğme çalışmazsa eski veriyle
            # devam edilir (yanlış "eksik" alarmı olabilir, kaçan alarm olmaz) ve bu uyarı mesajlarda görünür.
            try:
                kopru.gib_getir(ekran)
            except LucaHatasi as e:
                uyarilar.append(f"GİB'den Getir çalışmadı, Luca verisi güncel olmayabilir: {e}")
        bas, bit = yukleme_araligi(bugun, self.tatil)
        # Dönem/tür/durum filtresi YOK: yalnızca paket yükleme tarihi aralığı; tüm beyannameler (onaylı, hatalı, iptal) gelir
        cevap = kopru.beyanname_listele(ekran, bas, bit)
        try:
            bey, toplam = beyanname_json_kayitlari(cevap)
        except (ValueError, AttributeError, TypeError) as e:
            raise LucaHatasi(f"Beyanname listesi yanıtı okunamadı ({e}); Tanı sekmesine bakın") from e
        if toplam is not None and toplam != len(bey):
            raise LucaHatasi(f"Luca {toplam} beyanname kaydı yazıyor ama yanıtta {len(bey)} kayıt var (liste kesilmiş olabilir)")
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

    def _musteri_html(self, page, yil=None):
        """Müşteri Listesi tablosunu içeren HTML. yil verilmişse yalnızca o yıl filtresi UYGULANMIŞ sayfa kabul edilir
        (sayfa uygulanan filtreyi sonunda kendisi yazar); böylece filtre öncesi eski sayfa yanlışlıkla okunmaz."""
        for fr in self.m.le.cerceveler(page):
            try:
                html = fr.content()
            except Exception:  # noqa: BLE001
                continue
            if "kisa-ad-td" in html and "sirket_id" in html:
                if yil is None or musteri_html_filtre(html)["yil"] == str(yil):
                    return html
        return None

    def musteri_listesi(self, page, yil=None, ac=True):
        """Yönetici > Müşteri İşlemleri > Müşteri Listesi: ekranı açar (ac=True), varsa Yıl'ı seçip Ara'ya basar, sayfa
        HTML'inden okur ve 'Kayıt Sayısı' ile doğrular. Aynı oturumda ikinci yıl için ac=False (ekran açık kalır)."""
        with self._sessiz():
            if ac:
                try:
                    self.m.ml.musteri_listesini_ac(page, self.log)
                except LookupError as e:
                    self.m.ml.tani_kaydet(page, self.tani_klasoru, self.log, "-menu")
                    raise LucaHatasi(f"Müşteri Listesi ekranı açılamadı: {e}") from e
            if yil is not None and not self.m.ml.yili_filtrele(page, yil, self.log):
                self.m.ml.tani_kaydet(page, self.tani_klasoru, self.log, f"-yil{yil}")
                raise LucaHatasi(f"Müşteri Listesi'nde Yıl={yil} filtresi uygulanamadı (Tanı sekmesine bakın)")
            html = self.m.bekleme.kosulu_bekle(page, lambda: self._musteri_html(page, yil), 30000, aralik_ms=700)
            self.m.ml.tani_kaydet(page, self.tani_klasoru, self.log, "" if yil is None else f"-yil{yil}")
            sayfa_var = html or self._musteri_html(page)
        if not html:
            if sayfa_var and yil is not None:
                raise LucaHatasi(f"Yıl={yil} filtresi uygulanamadı: sayfa hâlâ filtresiz görünüyor")
            raise LucaHatasi("Müşteri Listesi tablosu bulunamadı (sayfa yapısı değişmiş olabilir; Tanı sekmesine bakın)")
        kayitlar, toplam = musteri_html_oku(html)
        if toplam is not None and toplam != len(kayitlar):
            raise LucaHatasi(f"Müşteri Listesi sayfası {toplam} kayıt yazıyor ama {len(kayitlar)} satır okundu")
        if not kayitlar:
            raise LucaHatasi("Müşteri Listesi boş okundu" + ("" if yil is None else f" (Yıl={yil})"))
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

    GIB_BITIS = "Ekrandaki listeyi yenilemek"      # "İşlem Takip" penceresinde GİB'den çekme bittiğinde çıkan bağlantının yazısı

    def _islem_takip_metni(self, ekran, isaret):
        """Çerçevelerin metninde işaret varsa 'İşlem Takip' penceresinin metni (son 800 karakter); yoksa None."""
        for fr in self.m.le.cerceveler(ekran):
            try:
                t = fr.locator("body").inner_text(timeout=1500)
            except Exception:  # noqa: BLE001
                continue
            if isaret in t:
                i = t.find("İşlem Takip")
                return (t[i:] if i >= 0 else t)[-800:] or isaret
        return None

    def gib_getir(self, ekran):
        """Ekrandaki "GİB'den Getir": Luca GİB'e sorar ve "İşlem Takip" penceresinde ilerlemeyi yazar; bitince
        "Ekrandaki listeyi yenilemek için buraya tıklayınız" çıkar (liste kendiliğinden yenilenmez). O yazıyı bekler, pencereyi
        kapatır; listeyi sonra beyanname_listele kendisi çeker. Düğme bulunamaz ya da süre dolarsa LucaHatasi."""
        le = self.m.le
        sure = int(self.env.get("LUCA_GIB_GETIR_SN", "180")) * 1000
        with self._sessiz():
            if not getattr(ekran, "_gib_diyalog", False):
                try:
                    ekran.on("dialog", lambda d: d.accept())        # Luca'nın onay (confirm) soruları kabul edilir
                    ekran._gib_diyalog = True
                except Exception:  # noqa: BLE001
                    pass
            if not any(le.dugmeye_bas(ekran, ad, sure=6000) for ad in ("GİB'den Getir", "GİB’den Getir", "Getir")):
                raise LucaHatasi("'GİB'den Getir' düğmesine basılamadı")
            bitti = self.m.bekleme.kosulu_bekle(ekran, lambda: self._islem_takip_metni(ekran, self.GIB_BITIS), sure, aralik_ms=1000)
            if not bitti:
                self.m.ml.tani_kaydet(ekran, self.tani_klasoru, self.log, "-gibgetir", "beyanname-takip")
                raise LucaHatasi(f"{sure // 1000} sn içinde bitmedi (GİB girişi/yetkisi ya da bir onay penceresi sorunu olabilir; "
                                 "Tanı ekran görüntüsüne bakın)")
            try:
                le.dugmeye_bas(ekran, "Kapat", sure=3000)           # "İşlem Takip" penceresi, filtre penceresini engellemesin
            except Exception:  # noqa: BLE001
                pass

    def beyanname_listele(self, ekran, bas, bit):
        """Filtre penceresinde 'Beyanname Durum'u Tümü yapıp 'Paket Yükleme Tarihi' aralığını yazar ve listeler; ekranın kendi
        isteğinin yanıtını (beyan_listele.jq, JSON) yakalar. Dönen: {"success": "N adet ...", "data": [...]}."""
        lb, le, ml = self.m.lb, self.m.le, self.m.ml
        with self._sessiz():
            cerceve = self._filtre_penceresi(ekran)
            alan = lambda ad, sira=0: cerceve.locator(f'[data-lucabot-alan="{ad}#{sira}"]')  # noqa: E731
            # "Beyanname Durum" pencerede varsayılan olarak "Onaylanmış" gelir: açıkça "Tümü" seçilmezse hatalı ve iptal edilmiş
            # beyannameler hiç gelmez ve "gönderildi ama onaylanmadı" tespiti sessizce çalışmaz. Dönem/Paket Durum/tür "Tümü" kalır.
            durum_kutusu = alan("Beyanname Durum", 0)
            if not lb._secenek_sec(durum_kutusu, "Tümü"):
                mevcut = ", ".join(t.strip() for t in durum_kutusu.locator("option").all_inner_texts())
                raise LucaHatasi(f"'Beyanname Durum' listesinde 'Tümü' seçeneği yok (seçenekler: {mevcut})")
            for sira, d in enumerate((bas, bit)):
                lb._tarih_yaz(alan("Paket Yükleme Tarihi", sira), d)
            try:
                with ekran.expect_response(lambda r: "beyan_listele.jq" in r.url, timeout=90000) as bilgi:
                    if not le.dugmeye_bas(ekran, lb.LISTELE_DUGMESI, sure=8000):
                        raise LucaHatasi(f"'{lb.LISTELE_DUGMESI}' düğmesine basılamadı")
            except LucaHatasi:
                raise
            except Exception as e:  # noqa: BLE001
                ml.tani_kaydet(ekran, self.tani_klasoru, self.log, "-liste", "beyanname-takip")
                raise LucaHatasi(f"Beyanname listesi yanıtı gelmedi ({type(e).__name__})") from e
            cevap = bilgi.value
            if not getattr(cevap, "ok", True):
                raise LucaHatasi(f"Beyanname listesi isteği başarısız (HTTP {getattr(cevap, 'status', '?')})")
            try:
                veri = cevap.json()
            except Exception as e:  # noqa: BLE001
                raise LucaHatasi("Beyanname listesi yanıtı JSON değil") from e
            ml.tani_kaydet(ekran, self.tani_klasoru, self.log, "-liste", "beyanname-takip")
        return veri

    def tani_calistir(self, page, bugun):
        """Tanı modu: müşteri listesini açar, beyanname ekranında son 30 günün listesini alır, ham yanıtı ve ekranları kaydeder."""
        import json
        from datetime import timedelta
        self.musteri_listesi(page, bugun.year)
        ekran = self.beyanname_ekrani_ac(page, bugun.year)
        veri = self.beyanname_listele(ekran, bugun - timedelta(days=30), bugun)
        (self.tani_klasoru / "beyan_listele.json").write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")

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
