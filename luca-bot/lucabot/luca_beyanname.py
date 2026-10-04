# -*- coding: utf-8 -*-
"""Luca'daki "GİB Beyanname Takip" ekranindan KDV1 beyanname PDF'lerini toplu alma.

Yol: Muhasebe > Beyannameler > GİB Beyanname Takip. Filtre penceresi
("BEYANNAME ARAMA") donem, beyanname durumu (Onaylanmış) ve beyanname turu
(KDV1) ile suzer; "Beyannameleri Listele" listeyi getirir. Basliktaki kutu
hepsini secer, Toplu İşlemler > "onaylanmış beyannamelerin beyanname ve
tahakkuk dosyalarını indirmek için buraya" baglantisi hepsini tek ZIP olarak
indirir. ZIP'ten tahakkuk dosyalari atilir, kalan beyanname PDF'leri klasore
yazilir; devreden KDV'yi okumak beyanname.py'nin isidir ("Beyannameden Devir Al"
ile ayni yol).
"""

import io
import re
import tempfile
import zipfile
from datetime import date, timedelta
from pathlib import Path

from .bekleme import kosulu_bekle, sayfa_durulsun
from .beyanname import AYLAR
from .luca_ekran import (acik_pencereleri_kapat, cerceveler, dugmeye_bas, gorunur_mu,
                         menu_metinleri, metinle_bul)
from .luca_gezinme import firma_sec, firma_secici, menu_ogesini_ac
from .musteri_listesi import tani_kaydet
from .ortak import dosya_adi_yap, sadelestir, yaz

MENU_YOLU = "Muhasebe > Beyannameler > GİB Beyanname Takip"
EKRAN_ADI = "GİB Beyanname Takip"
ARAMA_PENCERESI = "BEYANNAME ARAMA"
LISTELE_DUGMESI = "Beyannameleri Listele"
TOPLU_ISLEMLER = "Toplu İşlemler"
LISTELENDI_DESENI = re.compile(r"(\d+)\s+adet\s+beyanname\s+kayd[ıi]\s+listelendi", re.I)
TAHAKKUK_DESENI = re.compile(r"_THK_|tahakkuk", re.I)

# Filtre penceresindeki alanlar: etiketi satirdaki ilk metin olan satirin kutulari
# data-lucabot-alan="<etiket>#<sira>" ile isaretlenir
ALANLAR_JS = r"""etiketler => {
  document.querySelectorAll('[data-lucabot-alan]').forEach(e => e.removeAttribute('data-lucabot-alan'));
  const gorunur = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const duz = e => (e.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const bulunan = {};
  // yalniz arama penceresine bakilir: liste basliginda da "Beyanname Durum" yaziyor
  const baslik = [...document.querySelectorAll('td, th, div, span, b')]
    .find(e => gorunur(e) && !e.children.length && duz(e) === 'beyanname arama');
  if (!baslik) return bulunan;
  let kap = baslik.parentElement;
  while (kap && !kap.querySelector('select') && kap.parentElement) kap = kap.parentElement;
  for (const etiket of etiketler) {
    const aranan = etiket.toLowerCase();
    const el = [...kap.querySelectorAll('td, th, label, span, div, b')]
      .find(e => gorunur(e) && !e.children.length && duz(e) === aranan);
    if (!el) continue;
    let satir = el.closest('tr') || el.parentElement;
    let kutular = [...satir.querySelectorAll('select, input[type=text], input:not([type])')].filter(gorunur);
    if (!kutular.length && satir.parentElement) {
      satir = satir.parentElement;
      kutular = [...satir.querySelectorAll('select, input[type=text], input:not([type])')].filter(gorunur);
    }
    kutular.forEach((k, i) => k.setAttribute('data-lucabot-alan', etiket + '#' + i));
    bulunan[etiket] = kutular.length;
  }
  return bulunan;
}"""


# --- ekrani acma -------------------------------------------------------------------

def _ekran_sayfasi(page, onceki):
    """Ekran listesi gelmis sayfa ya da None.

    Luca bu ekrani ana sayfanin icinde degil AYRI PENCERE (popup) olarak aciyor;
    yalniz ana sayfaya bakilirsa ekran acildigi halde "acilmadi" sanilip menu
    tekrar tekrar tiklaniyor (her seferinde yeni pencere) ve is orada takiliyordu.
    """
    for p in [page] + [x for x in page.context.pages if x is not page and x not in onceki]:
        try:
            if gorunur_mu(p, "Mükellef Adı", sure=0) and gorunur_mu(p, "Filtre", sure=0):
                return p
        except Exception:
            continue
    return None


def _yol_parcalari(yol):
    return [p.strip() for p in (yol or MENU_YOLU).split(">") if p.strip()]


def menu_var_mi(page, yol=None):
    """Secili firmada yolun ikinci basamagi ('Beyannameler') gorunuyor mu.

    Isletme defteri / serbest meslek (SMK) firmalarinda Muhasebe menusunde
    Beyannameler yok; yalniz genel muhasebe firmalarinda var.
    """
    parcalar = _yol_parcalari(yol)
    if len(parcalar) < 2:
        return True
    acik_pencereleri_kapat(page)
    menu_ogesini_ac(page, parcalar[0], sure=4000, dogrula=lambda: gorunur_mu(page, parcalar[1], sure=1200))
    var = gorunur_mu(page, parcalar[1], sure=1500)
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    return var


def menusu_olan_firmayi_sec(page, yol=None, tercih=None, log=None, azami=15):
    """Beyanname menusu olan (genel muhasebe) bir firmaya gecer.

    Ekran firmadan bagimsiz (tum musterileri listeler) ama menude yalniz genel muhasebe
    firmalarinda gorunur. Dondurur: gecilen firma adi; secili firma yeterliyse None.
    tercih: once denenecek firma (ayarlar.json "beyanname_firmasi" ya da onceki basarili calisma).
    """
    firmalar = firma_secici(page)[2]
    tercih = tercih if tercih in firmalar else None  # listede olmayan (eski) tercih yok sayilir
    if not tercih and menu_var_mi(page, yol):
        return None
    yaz("    Beyanname menüsü için genel muhasebe firması aranıyor…", log)
    adaylar = ([tercih] if tercih else []) + [f for f in firmalar if f != tercih]
    denenen = 0
    for f in adaylar[:azami]:
        denenen += 1
        try:
            firma_sec(page, f, log)
        except LookupError:
            continue
        if menu_var_mi(page, yol):
            yaz(f"    '{f}' firmasından devam ediliyor", log)
            return f
    raise LookupError(f"Denenen {denenen} firmanın hiçbirinde '{_yol_parcalari(yol)[1]}' menüsü yok"
                      " (genel muhasebe firması gerekir; ayarlar.json'a \"beyanname_firmasi\" yazılabilir)")


def ekrani_ac(page, yol=None, log=None):
    """'Muhasebe > Beyannameler > GİB Beyanname Takip' yolunu izler; ekranin acildigi sayfayi dondurur.

    Ekran ana sayfada ya da yeni pencerede acilabilir; hangisinde ise o Page doner.
    """
    acik_pencereleri_kapat(page)
    parcalar = _yol_parcalari(yol)
    onceki = list(page.context.pages)
    for _ in range(3):
        for sonraki, parca in zip(parcalar[1:], parcalar[:-1]):
            menu_ogesini_ac(page, parca, sure=6000, dogrula=lambda m=sonraki: gorunur_mu(page, m, sure=1200))
        try:
            _, madde = metinle_bul(page, parcalar[-1], sure=5000)
            madde.click(timeout=8000)
        except Exception:
            sayfa_durulsun(page, azami_ms=1000)
            continue
        ekran = kosulu_bekle(page, lambda: _ekran_sayfasi(page, onceki), 20000, aralik_ms=500)
        if ekran:
            if ekran is not page:
                yaz("    Ekran ayrı pencerede açıldı", log)
                try:
                    ekran.bring_to_front()
                except Exception:
                    pass
            return ekran
    raise LookupError(f"'{' > '.join(parcalar)}' menusu acilamadi")


# --- filtre ------------------------------------------------------------------------

def _secenek_sec(secici, metin):
    """Select'te sadelestirilmis metni tutan secenegi secer; bulunamazsa False."""
    hedef = sadelestir(metin)
    secenekler = secici.locator("option").all_inner_texts()
    for i, s in enumerate(secenekler):
        if sadelestir(s) == hedef:
            secici.select_option(index=i, timeout=8000)
            return True
    return False


def donem_filtresi(hedef_bas):
    """Devir icin bakilacak beyanname donemi: kontrol edilen donemin bir onceki ayi."""
    onceki = (hedef_bas - timedelta(days=1)).replace(day=1)
    return onceki.month, onceki.year


def filtrele(page, ay, yil, log=None):
    """Filtre penceresini doldurup 'Beyannameleri Listele'ye basar; ekrandaki cerceve ya da None."""
    dugmeye_bas(page, "Filtre", sure=8000)
    if not gorunur_mu(page, ARAMA_PENCERESI, sure=8000):
        dugmeye_bas(page, "Filtre", sure=4000)
        if not gorunur_mu(page, ARAMA_PENCERESI, sure=8000):
            raise LookupError(f"'{ARAMA_PENCERESI}' penceresi acilmadi")
    etiketler = ["Paket Yükleme Tarihi", "Beyanname Dönemi", "Beyanname Durum", "Beyanname"]
    cerceve = None
    for fr in cerceveler(page):
        try:
            bulunan = fr.evaluate(ALANLAR_JS, etiketler)
        except Exception:
            continue
        if bulunan.get("Beyanname Dönemi"):
            cerceve = fr
            break
    if cerceve is None:
        raise LookupError("Filtre penceresindeki alanlar bulunamadi")

    def alan(ad, sira=0):
        return cerceve.locator(f'[data-lucabot-alan="{ad}#{sira}"]')

    # sirayla: bos kalan zorunlu alan yanlis beyanname indirmesin
    zorunlu = [("Beyanname Dönemi", 0, AYLAR[ay - 1]), ("Beyanname Dönemi", 1, str(yil)),
               ("Beyanname Durum", 0, "Onaylanmış"), ("Beyanname", 0, "KDV1")]
    for ad, sira, deger in zorunlu:
        if not _secenek_sec(alan(ad, sira), deger):
            raise LookupError(f"'{ad}' listesinde '{deger}' secenegi bulunamadi")
    # yukleme tarihi: dönem ayinin basindan bugune (beyannameler ertesi ay yuklenir)
    bas, bit = date(yil, ay, 1), date.today()
    for sira, d in enumerate((bas, bit)):
        try:
            kutu = alan("Paket Yükleme Tarihi", sira)
            kutu.fill(f"{d:%d/%m/%Y}", timeout=5000)
            kutu.press("Tab")
        except Exception:
            yaz("    Paket yükleme tarihi yazilamadi (varsayilan aralik kalir)", log)
    if not dugmeye_bas(page, LISTELE_DUGMESI, sure=8000):
        raise LookupError(f"'{LISTELE_DUGMESI}' dugmesine basilamadi")
    return cerceve


def listelenen_sayi(page, sure_ms=90000):
    """'N adet beyanname kaydı listelendi.' bildirimindeki N; gelmezse None."""
    def oku():
        for fr in cerceveler(page):
            try:
                m = LISTELENDI_DESENI.search(fr.locator("body").inner_text(timeout=2000))
            except Exception:
                continue
            if m:
                return int(m.group(1))
        return None
    sonuc = kosulu_bekle(page, lambda: oku() is not None, sure_ms, aralik_ms=700)
    return oku() if sonuc else None


# --- indirme -----------------------------------------------------------------------

class DosyaYakalayici:
    """Tiklamadan sonra inen (ya da sekmede acilan) ZIP/PDF baytlarini toplar."""

    def __init__(self, page):
        self.page = page
        self.ctx = page.context
        self.alinan = []
        self._onceki = list(self.ctx.pages)
        self.ctx.on("response", self._yanit)
        self.ctx.on("page", self._sayfa)
        for p in self._onceki:
            p.on("download", self._indirme)

    def kapat(self):
        for olay, fn in (("response", self._yanit), ("page", self._sayfa)):
            try:
                self.ctx.remove_listener(olay, fn)
            except Exception:
                pass
        for p in self._onceki:
            try:
                p.remove_listener("download", self._indirme)
            except Exception:
                pass
        for p in list(self.ctx.pages):  # indirme icin acilan bos sekmeler kapanir
            if p not in self._onceki:
                try:
                    p.close()
                except Exception:
                    pass

    def _sayfa(self, p):
        p.on("download", self._indirme)

    def _indirme(self, d):
        try:
            gecici = Path(tempfile.mkdtemp()) / "indirme.bin"
            d.save_as(str(gecici))
            self.alinan.append(gecici.read_bytes())
        except Exception:
            pass

    def _yanit(self, r):
        try:
            basliklar = {k.lower(): v for k, v in (r.headers or {}).items()}
            tur = basliklar.get("content-type", "").lower()
            ek = basliklar.get("content-disposition", "").lower()
            if not any(k in tur or k in ek for k in ("pdf", "zip")):
                return
            veri = b""
            try:
                veri = r.body()
            except Exception:
                pass
            if veri[:4] not in (b"%PDF", b"PK\x03\x04"):  # yeni sekmenin ilk yanitinda govde bazen yanlis gelir
                veri = self.ctx.request.get(r.url).body()
            if veri[:4] in (b"%PDF", b"PK\x03\x04"):
                self.alinan.append(veri)
        except Exception:
            pass

    def bekle(self, sure_ms):
        kosulu_bekle(self.page, lambda: bool(self.alinan), sure_ms, aralik_ms=400)
        return self.alinan[0] if self.alinan else None


def toplu_indir(page, cerceve, sure_ms=300000, log=None):
    """Hepsini secip Toplu İşlemler'deki ilk 'buraya' baglantisiyla ZIP'i indirir; baytlar ya da None."""
    try:
        cerceve.locator("input[type=checkbox]").first.check(timeout=8000)  # baslik kutusu: hepsi
    except Exception as e:
        raise LookupError(f"Hepsini sec kutusu isaretlenemedi ({type(e).__name__})")
    sayfa_durulsun(page, azami_ms=800)
    if not dugmeye_bas(page, TOPLU_ISLEMLER, sure=8000):
        raise LookupError(f"'{TOPLU_ISLEMLER}' dugmesine basilamadi")
    if not gorunur_mu(page, "buraya", sure=8000):
        raise LookupError("Toplu işlemler penceresi acilmadi")
    yakalayici = DosyaYakalayici(page)
    try:
        for fr in cerceveler(page):
            try:
                bag = fr.get_by_text("buraya", exact=True).first
                if bag.count() and bag.is_visible():
                    bag.click(timeout=8000)  # ilk madde: beyanname ve tahakkuk dosyalarini indir
                    break
            except Exception:
                continue
        else:
            raise LookupError("'buraya' baglantisi bulunamadi")
        yaz("    Toplu indirme istendi; Luca dosyayi hazirlarken bekleniyor…", log)
        return yakalayici.bekle(sure_ms)
    finally:
        yakalayici.kapat()


def arsivden_pdfler(veri, klasor, log=None):
    """ZIP (ya da tek PDF) baytlarindan beyanname PDF'lerini klasore yazar; tahakkuk dosyalari atilir."""
    klasor.mkdir(parents=True, exist_ok=True)
    yollar = []
    if veri[:4] == b"%PDF":
        adlar = {"beyanname.pdf": veri}
    else:
        with zipfile.ZipFile(io.BytesIO(veri)) as z:
            adlar = {Path(i.filename).name: z.read(i) for i in z.infolist()
                     if i.filename.lower().endswith(".pdf") and not i.is_dir()}
    for ad, icerik in sorted(adlar.items()):
        if TAHAKKUK_DESENI.search(ad):
            continue
        yol = klasor / dosya_adi_yap(ad)
        yol.write_bytes(icerik)
        yollar.append(yol)
    return yollar


def ekrandan_al(page, klasor, tani_klasoru, hedef_bas, yol=None, log=None, tercih_firma=None, bilgi=None):
    """Ekrani acar, donemi suzer, ZIP'i indirip PDF'leri klasore cikarir. Dondurur: (yollar, listelenen sayi).

    Secili firmada menu yoksa genel muhasebe firmasina gecilir (bilgi["firma"] o firmayi
    tasir; sonraki calismada tercih_firma olarak verilirse arama atlanir). Ekran yeni
    pencerede acildiysa isi bitince o pencere kapatilir.
    """
    onceki = list(page.context.pages)
    try:
        try:
            firma = menusu_olan_firmayi_sec(page, yol, tercih_firma, log)
            if firma and bilgi is not None:
                bilgi["firma"] = firma
            ekran = ekrani_ac(page, yol, log)
        except LookupError:
            yaz(f"    Gorunen menuler: {menu_metinleri(page)}", log)
            tani_kaydet(page, tani_klasoru, log, "-menu", "beyanname-takip")
            raise
        ay, yil = donem_filtresi(hedef_bas)
        yaz(f"Beyanname dönemi: {AYLAR[ay - 1].title()} {yil} (KDV1, onaylanmış)", log)
        try:
            cerceve = filtrele(ekran, ay, yil, log)
            sayi = listelenen_sayi(ekran)
            tani_kaydet(ekran, tani_klasoru, log, "", "beyanname-takip")
            if not sayi:
                raise LookupError(f"{AYLAR[ay - 1].title()} {yil} için onaylı KDV1 beyannamesi listelenmedi")
            yaz(f"{sayi} beyanname kaydı listelendi", log)
            veri = toplu_indir(ekran, cerceve, log=log)
        except LookupError:
            tani_kaydet(ekran, tani_klasoru, log, "-hata", "beyanname-takip")
            raise
        if veri is None:
            tani_kaydet(ekran, tani_klasoru, log, "-indirme", "beyanname-takip")
            raise LookupError("Toplu indirme dosyası gelmedi")
        yollar = arsivden_pdfler(veri, klasor, log)
        yaz(f"{len(yollar)} beyanname PDF'i çıkarıldı (liste: {sayi} kayıt)", log)
        return yollar, sayi
    finally:
        for p in list(page.context.pages):  # ekran icin acilan pencereler kapanir
            if p not in onceki:
                try:
                    p.close()
                except Exception:
                    pass
