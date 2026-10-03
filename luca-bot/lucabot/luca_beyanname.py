# -*- coding: utf-8 -*-
"""Luca'daki "Beyanname Kontrol" ekranindan KDV1 beyanname PDF'lerini toplu alma.

Ekran butun mukellefleri tek listede gosterir (Mükellef Adı, Dönem, TCKN, VKN,
KDV1 ...); KDV1 sutunundaki "Onaylanmış Beyanname (PDF)" baglantisi beyannameyi
acar. Bot her baglantiya tiklar, acilan/inen PDF'i yakalar ve
`<kisa ad>_<vkn>_KDV1_<donem>_<n>.pdf` adiyla kaydeder; devreden KDV'yi okumak
beyanname.py'nin isidir (arayuzdeki "Beyannameden Devir Al" ile ayni yol).

Ekranin menudeki yeri gercek Luca'da henuz bilinmiyor: ayarlar.json'daki
"beyanname_menusu" ("Denetim/Analiz > Beyanname Kontrol" gibi) varsa o izlenir,
yoksa ust menuler sirayla taranir.
"""

import re
import tempfile
from pathlib import Path

from .bekleme import kosulu_bekle, nabiz, sayfa_durulsun
from .luca_ekran import (acik_pencereleri_kapat, gorunur_mu, menu_metinleri,
                         metinle_bul)
from .luca_gezinme import menu_ogesini_ac
from .musteri_listesi import tani_kaydet
from .ortak import dosya_adi_yap, yaz

EKRAN_ADI = "Beyanname Kontrol"
UST_MENULER = ["Denetim/Analiz", "Muhasebe", "Müşteri", "Yönetici", "Personel", "Kişisel"]
ARA_MENULER = ["Beyanname", "Beyannameler", "Beyanname İşlemleri", "Kontrol", "Raporlar", "Denetim"]
HIZLI_ERISIM_JS = """ad => {
  for (const s of document.querySelectorAll('select')) {
    const o = [...s.options].find(o => o.text.trim().toLowerCase().includes(ad.toLowerCase()));
    if (o) { s.setAttribute('data-lucabot-hizli', o.text); return o.text; }
  }
  return '';
}"""

# "Onaylanmış Beyanname (PDF)" baglantilari: yaprak ogeler isaretlenir, satirdaki
# mukellef bilgisiyle dondurulur. KDV1 basligi bulunursa yalniz o sutundakiler alinir.
BAGLANTILAR_JS = r"""() => {
  const duz = e => (e.textContent || '').replace(/\s+/g, ' ').trim();
  // satir sonu / <br> ile bolunmus yazi da taninsin: tum bosluklar atilarak karsilastirilir
  const bitisik = e => (e.innerText || e.textContent || '').replace(/\s+/g, '');
  const desen = /^onaylanm[ıi]şbeyanname\(pdf\)$/i;
  document.querySelectorAll('[data-lucabot-bey]').forEach(e => e.removeAttribute('data-lucabot-bey'));
  const adaylar = [...document.querySelectorAll('a, span, div, td, font, u, b')]
    .filter(e => desen.test(bitisik(e)) && ![...e.children].some(c => desen.test(bitisik(c))));
  let kdvSutunu = null;
  for (const e of document.querySelectorAll('th, td, div, span')) {
    if (duz(e) === 'KDV1' && !e.children.length) {
      const hucre = e.closest('th, td') || e;
      const satir = hucre.parentElement;
      kdvSutunu = [...satir.children].indexOf(hucre);
      break;
    }
  }
  const sonuc = [];
  adaylar.forEach(e => {
    const hucre = e.closest('td, [role=gridcell]');
    const satir = e.closest('tr, [role=row]');
    const cocuklar = satir ? [...satir.children] : [];
    const sutun = hucre ? cocuklar.indexOf(hucre) : -1;
    const metinler = cocuklar.map(duz);
    sonuc.push({sutun, ad: metinler[0] || '',
      vkn: metinler.find(m => /^\d{10}$/.test(m)) || '',
      tc: metinler.find(m => /^\d{11}$/.test(m)) || '',
      donem: metinler.find(m => /^\d{4}\/\d{2}$/.test(m)) || '', e});
  });
  const secilen = kdvSutunu === null ? sonuc : sonuc.filter(s => s.sutun === kdvSutunu);
  const kullan = secilen.length ? secilen : sonuc;
  return kullan.map((s, i) => {
    s.e.setAttribute('data-lucabot-bey', String(i));
    return {i, ad: s.ad, vkn: s.vkn, tc: s.tc, donem: s.donem};
  });
}"""


# --- ekrani acma -------------------------------------------------------------------

def _ekran_hazir(page, sure=15000):
    return bool(kosulu_bekle(page, lambda: gorunur_mu(page, "Mükellef Adı", sure=0)
                             or gorunur_mu(page, "Onaylanmış", sure=0), sure, aralik_ms=500))


def _ekrani_tikla(page):
    _, madde = metinle_bul(page, EKRAN_ADI, sure=4000)
    madde.click(timeout=8000)
    return _ekran_hazir(page)


def _hizli_erisimden_ac(page):
    """Ust cubuktaki "Hızlı Erişim" listesinde ekran varsa onu secer."""
    for fr in page.frames:
        try:
            metin = fr.evaluate(HIZLI_ERISIM_JS, EKRAN_ADI)
            if metin:
                fr.locator("[data-lucabot-hizli]").select_option(label=metin, timeout=5000)
                return _ekran_hazir(page, sure=10000)
        except Exception:
            continue
    return False


def _yoldan_ac(page, yol):
    """'Denetim/Analiz > Beyanname Kontrol' gibi yolu sirayla acar."""
    parcalar = [p.strip() for p in yol.split(">") if p.strip()]
    for sonraki, parca in zip(parcalar[1:] + [None], parcalar):
        dogrula = (lambda m=sonraki: gorunur_mu(page, m, sure=1200)) if sonraki else None
        if sonraki is None:
            _, madde = metinle_bul(page, parca, sure=5000)
            madde.click(timeout=8000)
            return _ekran_hazir(page)
        menu_ogesini_ac(page, parca, sure=6000, dogrula=dogrula)
    return False


def ekrani_ac(page, yol=None, log=None):
    """Beyanname Kontrol ekranini acar; ekran listesi gorunene kadar. Bulunamazsa LookupError."""
    acik_pencereleri_kapat(page)
    if yol:
        try:
            if _yoldan_ac(page, yol):
                return True
        except LookupError:
            yaz(f"    '{yol}' menu yolu izlenemedi, ust menuler taranacak", log)
    if _hizli_erisimden_ac(page):
        return True
    gorunur = lambda: gorunur_mu(page, EKRAN_ADI, sure=900)
    for ust in UST_MENULER:
        menu_ogesini_ac(page, ust, sure=3000, dogrula=gorunur)
        if not gorunur():
            for ara in ARA_MENULER:
                if gorunur_mu(page, ara, sure=300):
                    menu_ogesini_ac(page, ara, sure=2000, dogrula=gorunur)
                    if gorunur():
                        break
        if gorunur():
            try:
                if _ekrani_tikla(page):
                    yaz(f"Ekran '{ust}' menusunden acildi", log)
                    return True
            except Exception:
                pass
        acik_pencereleri_kapat(page)
    raise LookupError(f"'{EKRAN_ADI}' menusu bulunamadi")


# --- PDF yakalama ------------------------------------------------------------------

class PdfYakalayici:
    """Tiklamadan sonra acilan sekmeye ya da inen dosyaya bakar; PDF baytlarini toplar."""

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
        for p in list(self.ctx.pages):  # tiklamayla acilan PDF sekmeleri kapanir
            if p not in self._onceki:
                try:
                    p.close()
                except Exception:
                    pass

    def _sayfa(self, p):
        p.on("download", self._indirme)

    def _indirme(self, d):
        try:
            gecici = Path(tempfile.mkdtemp()) / "indirme.pdf"
            d.save_as(str(gecici))
            self.alinan.append(gecici.read_bytes())
        except Exception:
            pass

    def _yanit(self, r):
        try:
            basliklar = {k.lower(): v for k, v in (r.headers or {}).items()}
            tur = basliklar.get("content-type", "").lower()
            ek = basliklar.get("content-disposition", "").lower()
            if "pdf" not in tur and ".pdf" not in ek:
                return
            veri = b""
            try:
                veri = r.body()
            except Exception:
                pass
            if veri[:4] != b"%PDF":  # yeni sekmenin ilk yanitinda govde bazen yanlis gelir: ayni adres yeniden istenir
                veri = self.ctx.request.get(r.url).body()
            if veri[:4] == b"%PDF":
                self.alinan.append(veri)
        except Exception:
            pass

    def bekle(self, sure_ms=25000):
        """Ilk PDF gelene kadar bekler; baytlar ya da None."""
        kosulu_bekle(self.page, lambda: bool(self.alinan), sure_ms, aralik_ms=300)
        return self.alinan[0] if self.alinan else None


# --- toplu alma --------------------------------------------------------------------

def baglantilari_bul(page):
    """Ekrandaki 'Onaylanmış Beyanname (PDF)' baglantilari: (cerceve, [{i, ad, vkn, tc, donem}])."""
    from .luca_ekran import cerceveler
    en_iyi = (None, [])
    for fr in cerceveler(page):
        try:
            bulunan = fr.evaluate(BAGLANTILAR_JS)
        except Exception:
            continue
        if len(bulunan) > len(en_iyi[1]):
            en_iyi = (fr, bulunan)
    return en_iyi


def dosya_adi(kisa_ad, vkn, donem, sira):
    donem = (donem or "").replace("/", "-")
    return f"{dosya_adi_yap(kisa_ad)}_{vkn or 'x'}_KDV1_{donem or 'x'}_{sira}.pdf"


def hepsini_al(page, klasor, adlar=None, log=None, sure_ms=25000):
    """Her mukellefin onayli KDV1 beyannamesini klasore indirir.

    adlar: {vkn ya da tc: kisa ad} (Luca musteri listesinden); yoksa satirdaki
    Mükellef Adı kullanilir. Dondurur: (kaydedilen yollar, alinamayan satir adlari).
    """
    klasor.mkdir(parents=True, exist_ok=True)
    adlar = adlar or {}
    fr, baglantilar = baglantilari_bul(page)
    yaz(f"{len(baglantilar)} onaylı beyanname bağlantısı bulundu", log)
    kaydedilen, alinamayan, sayac = [], [], {}
    for n, b in enumerate(baglantilar, 1):
        nabiz(page, 50)  # Durdur istegi gelmisse KeyboardInterrupt
        ad = adlar.get(b["vkn"]) or adlar.get(b["tc"]) or b["ad"] or b["vkn"] or f"firma{n}"
        sayac[ad] = sayac.get(ad, 0) + 1
        yakalayici = PdfYakalayici(page)
        veri = None
        try:
            hedef = fr.locator(f'[data-lucabot-bey="{b["i"]}"]').first
            hedef.scroll_into_view_if_needed(timeout=5000)
            hedef.click(timeout=8000)
            veri = yakalayici.bekle(sure_ms)
        except Exception as e:
            yaz(f"    [{n}/{len(baglantilar)}] {ad}: tıklanamadı ({type(e).__name__})", log)
        finally:
            yakalayici.kapat()
        if veri is None:
            alinamayan.append(ad)
            yaz(f"    [{n}/{len(baglantilar)}] {ad}: PDF alınamadı", log)
            sayfa_durulsun(page, azami_ms=500)
            continue
        yol = klasor / dosya_adi(ad, b["vkn"] or b["tc"], b["donem"], sayac[ad])
        yol.write_bytes(veri)
        kaydedilen.append(yol)
        yaz(f"    [{n}/{len(baglantilar)}] {ad}: {yol.name} ({len(veri) // 1024} KB)", log)
    return kaydedilen, alinamayan


def ekrandan_al(page, klasor, tani_klasoru, adlar=None, yol=None, log=None):
    """Ekrani acip butun PDF'leri alir; ekran goruntusu/kaynak tani klasorune kaydedilir."""
    try:
        ekrani_ac(page, yol, log)
    except LookupError:
        yaz(f"    Gorunen menuler: {menu_metinleri(page)}", log)
        tani_kaydet(page, tani_klasoru, log, "-menu", "beyanname-kontrol")
        raise
    sayfa_durulsun(page, azami_ms=1500)
    tani_kaydet(page, tani_klasoru, log, "", "beyanname-kontrol")
    return hepsini_al(page, klasor, adlar, log)


def adlar_haritasi(kayitlar):
    """Luca musteri listesi kayitlarindan {vkn / tc: kisa ad}."""
    harita = {}
    for k in kayitlar:
        for anahtar in (k.get("vkn"), k.get("tc")):
            if anahtar:
                harita[anahtar] = k["ad"]
    return harita
