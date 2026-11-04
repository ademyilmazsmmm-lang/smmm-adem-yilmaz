# -*- coding: utf-8 -*-
"""Luca > Isletme Defteri > "Defter Beyan Sistemi" sayfasi (luca2.do?tur=defter_beyan).

Elle yapilan isin otomasyonu (her firma icin, Gelirler ve Giderler sekmesinde ayri ayri):

    Evrak Tarihi araligi + Durum (Tumu / Gonderilmemisler / Gonderilmisler) > Listele
    > listeyi oku (kontrol)
    > baslik kutusuyla hepsini sec > Islemler > "Defter Beyan Sistemine Gonder"
    > SORGULAMA UYARI: Tamam > Giris Bilgileri (API Key/Secret Luca'da kayitli): Tamam
    > DEFTER BEYAN ENTEGRASYON penceresinin yazisi (sonuc) > Tamam

Liste uzun olunca sayfalanmaz, hepsi tek listede gelir. Tum ekran ogeleri YAZIYA gore bulunur (Luca'nin
yardimci islevleri); beklenmeyen bir durumda ekran goruntusu ve sayfa kaydi tani klasorune yazilir.
API Key/Secret programa girilmez: Luca'da kayitli olanlarla "Tamam" denir; bos ise gonderme durdurulur.
"""

import random
import re
import time
from urllib.parse import urlparse

from lucabot.bekleme import kosulu_bekle, sayfa_durulsun
from lucabot.luca_ekran import acik_pencere, acik_pencereleri_kapat, hata_kaydet, kutuya_yaz
from lucabot.luca_ekran import diyalog_bekle as _ekran_diyalog_bekle
from lucabot.luca_ekran import pencerede_tikla as _ekran_pencerede_tikla
from lucabot.ortak import yaz

from . import db_sonuc
from .db_sonuc import _k

DB_YOLU = "/Luca/luca2.do?tur=defter_beyan"
SEKMELER = {"gelir": "Gelirler", "gider": "Giderler"}
GONDERILMEMIS, GONDERILMIS, TUMU = "Gönderilmemişler", "Gönderilmişler", "Tümü"

# Listede "Evrak No" / "Evrak Tarihi" basliklarini tasiyan EN ICTEKI tabloyu okur. Baslik ve govde ayri
# tablolarda (sabit baslikli grid) olabilir: govde satirlari baslik tablosundan sonra gelen tablolardan alinir.
TABLO_JS = """() => {
  const norm = s => (s || '').replace(/\\s+/g, ' ').trim();
  const hucre = r => [...r.children].filter(c => /^(TD|TH)$/.test(c.tagName));
  const satirlari = t => [...t.querySelectorAll('tr')].filter(r => r.closest('table') === t);
  const adaylar = [...document.querySelectorAll('table')].filter(t => {
    if (!(t.offsetParent || t.getClientRects().length)) return false;   // gizli (eski) liste sayilmaz
    const m = norm(t.innerText); return /Evrak No/i.test(m) && /Evrak Tarihi/i.test(m);
  });
  const t = adaylar.find(a => !adaylar.some(o => o !== a && a.contains(o)));
  if (!t) return null;
  const sat = satirlari(t);
  const bi = sat.findIndex(r => /Evrak No/i.test(norm(r.innerText)));
  if (bi < 0) return null;
  const basliklar = hucre(sat[bi]).map(c => norm(c.innerText));
  const oku = rows => rows.map(r => hucre(r).map(c => norm(c.innerText)))
                          .filter(h => h.length >= 3 && h.some(x => x));
  let veri = oku(sat.slice(bi + 1));
  if (!veri.length) {   // govde ayri tabloda
    const hepsi = [...document.querySelectorAll('table')];
    for (const o of hepsi.slice(hepsi.indexOf(t) + 1)) {
      if (o.contains(t) || t.contains(o)) continue;
      const v = oku(satirlari(o));
      if (v.length && v[0].length >= basliklar.length - 2) { veri = v; break; }
    }
  }
  return {basliklar: basliklar, satirlar: veri};
}"""

# Basliktaki "hepsini sec" kutusu; yoksa tek tek satir kutulari. Isaretli satir sayisini dondurur.
HEPSINI_SEC_JS = """() => {
  const norm = s => (s || '').replace(/\\s+/g, ' ').trim();
  const kutular = () => [...document.querySelectorAll('input[type=checkbox]')];
  const bas = kutular().find(k => { const r = k.closest('tr'); return r && /Evrak No/i.test(norm(r.innerText)); });
  if (bas && !bas.checked) bas.click();
  let isaretli = kutular().filter(k => k.checked && k !== bas).length;
  if (!isaretli) {                       // baslik kutusu calismadiysa satirlari tek tek isaretle
    for (const k of kutular()) { if (k !== bas && !k.checked && !k.disabled) k.click(); }
    isaretli = kutular().filter(k => k.checked && k !== bas).length;
  }
  return isaretli;
}"""

# Luca'nin listesi bir jqx grid'idir (jqx-all.js): <table> degil, yalniz ekrandaki satirlari cizer (sanal kaydirma). Bu yuzden
# satirlar DOM'dan degil grid'in kendi arayuzunden (getrows / getcelltext / selectallrows) okunur ve secilir.
GRID_OKU_JS = """() => {
  const jq = window.jQuery || window.$;
  if (!jq || !jq.fn || !jq.fn.jqxGrid) return null;
  const gorunur = e => !!(e.offsetParent || e.getClientRects().length);
  for (const el of document.querySelectorAll('.jqx-grid')) {
    if (!gorunur(el)) continue;
    const g = jq(el);
    let kl;
    try { kl = g.jqxGrid('columns'); } catch (e) { continue; }
    const kolonlar = ((kl && kl.records) || (Array.isArray(kl) ? kl : [])).filter(c => c && !c.hidden);
    const basliklar = kolonlar.map(c => String(c.text || '').replace(/\\s+/g, ' ').trim());
    if (!basliklar.some(b => /evrak no/i.test(b))) continue;
    let satirlar = [];
    try {
      const bilgi = g.jqxGrid('getdatainformation');
      const n = bilgi && bilgi.rowscount != null ? bilgi.rowscount : 0;
      for (let i = 0; i < n; i++) {
        satirlar.push(kolonlar.map(c => {
          if (!c.datafield) return '';
          let v = '';
          try { v = g.jqxGrid('getcelltext', i, c.datafield); } catch (e) {}
          return v == null ? '' : String(v).replace(/\\s+/g, ' ').trim();
        }));
      }
    } catch (e) { return null; }
    return {basliklar: basliklar, satirlar: satirlar};
  }
  return null;
}"""

# Tum satirlari secer; {'secili': N, 'toplam': M} ya da (jqx grid yoksa) null
GRID_SEC_JS = """() => {
  const jq = window.jQuery || window.$;
  if (!jq || !jq.fn || !jq.fn.jqxGrid) return null;
  const gorunur = e => !!(e.offsetParent || e.getClientRects().length);
  for (const el of document.querySelectorAll('.jqx-grid')) {
    if (!gorunur(el)) continue;
    const g = jq(el);
    try {
      const toplam = g.jqxGrid('getdatainformation').rowscount;
      g.jqxGrid('selectallrows');
      let secili = g.jqxGrid('getselectedrowindexes').length;
      if (secili !== toplam) {   // baslikdaki secim kutusu (jqx-checkbox) ile dene
        const kutu = el.querySelector('[role=columnheader] .jqx-checkbox, [role=columnheader] .jqx-checkbox-default');
        if (kutu) { kutu.click(); secili = g.jqxGrid('getselectedrowindexes').length; }
      }
      return {secili: secili, toplam: toplam};
    } catch (e) { continue; }
  }
  return null;
}"""

KAYIT_YOK_METINLERI = ("kayıt bulunamadı", "kayıt bulunamamıştır", "kayıt yok", "listelenecek kayıt", "no data to display")


# --- ekran ogelerini bulma (bu sayfaya ozgu) ------------------------------------------------------------
# Luca'nin ortak yardimcilari bir metinle eslesen ILK ogeye bakar. Bu sayfada Gelirler/Giderler formlari ayni sayfada
# durup sekmeyle gizlenip gosterilebildigi icin ilk "Listele"/"Evrak Tarihi" gizli formun olabilir ve ekranda gorunen
# oge hic bulunamaz. Burada TUM cerceveler ve TUM eslesmeler taranir, yalnizca GORUNEN ilk oge doner.

def cerceveler(sayfa):
    try:
        return list(sayfa.frames)
    except Exception:
        return []


def gorunur_bul(sayfa, kurucu, sure=15000):
    """kurucu(cerceve) -> locator; tum cerceve ve eslesmelerde ilk GORUNEN ogeyi (cerceve, oge) dondurur."""
    def dene():
        for fr in cerceveler(sayfa):
            try:
                loc = kurucu(fr)
                for i in range(min(loc.count(), 40)):
                    oge = loc.nth(i)
                    if oge.is_visible():
                        return fr, oge
            except Exception:
                continue  # cerceve yeniden yukleniyor
        return None
    sonuc = kosulu_bekle(sayfa, dene, sure, aralik_ms=300)
    if sonuc:
        return sonuc
    raise LookupError("Görünen öğe bulunamadı")


def metinle_bul(sayfa, metin, sure=15000):
    """Once dugme, sonra tam metin, en son metni iceren GORUNEN oge (bkz. gorunur_bul)."""
    pay = max(300, sure // 4)
    son = None
    for kurucu, kurucu_sure in (
        (lambda f: f.get_by_role("button", name=metin, exact=True), pay),
        (lambda f: f.get_by_text(metin, exact=True), pay),
        (lambda f: f.get_by_text(metin, exact=False), sure),
    ):
        try:
            return gorunur_bul(sayfa, kurucu, sure=kurucu_sure)
        except LookupError as e:
            son = e
    raise LookupError(f"'{metin}' ekranda görünmüyor") from son


def gorunur_mu(sayfa, metin, sure=1500):
    if not isinstance(metin, str):
        return bool(kosulu_bekle(sayfa, lambda: any(gorunur_mu(sayfa, m, sure=0) for m in metin), sure, aralik_ms=200))
    try:
        gorunur_bul(sayfa, lambda f: f.get_by_text(metin, exact=False), sure=sure)
        return True
    except LookupError:
        return False


def dugmeye_bas(sayfa, metin, sure=8000):
    try:
        _, dugme = metinle_bul(sayfa, metin, sure=sure)
    except LookupError:
        return False
    for zorla in (False, True):
        try:
            dugme.click(timeout=6000, force=zorla)
            return True
        except Exception:
            continue
    return False


def sayfa_ozeti(sayfa, log):
    """Beklenmeyen durumda ekrandaki girdi kutularini ve dugmeleri loga yazar (sayfa yapisini incelemek icin)."""
    js = """() => {
      const g = e => !!(e.offsetParent || e.getClientRects().length);
      const ad = e => `${e.tagName.toLowerCase()}${e.type && e.tagName=='INPUT' ? '['+e.type+']' : ''}#${e.id||''}.${(e.name||'')}` +
                      `="${(e.value||'').slice(0,24)}"${g(e) ? '' : ' (gizli)'}`;
      const girdi = [...document.querySelectorAll('input,select,textarea')].map(ad).slice(0, 40);
      const dugme = [...document.querySelectorAll('button,input[type=button],a')].filter(g)
        .map(e => (e.innerText || e.value || '').trim().slice(0, 24)).filter(Boolean).slice(0, 30);
      return {url: location.pathname.slice(-40), girdi, dugme, baslik: (document.body.innerText || '').slice(0, 160).replace(/\\s+/g, ' ')};
    }"""
    for i, fr in enumerate(cerceveler(sayfa)):
        try:
            o = fr.evaluate(js)
        except Exception:
            continue
        if not o["girdi"] and not o["dugme"]:
            continue
        yaz(f"    [sayfa kaydı] çerçeve {i} {o['url']}: {o['baslik']}", log)
        yaz(f"      kutular: {' | '.join(o['girdi'])}", log)
        yaz(f"      düğmeler: {' | '.join(o['dugme'])}", log)


# --- sayfa ----------------------------------------------------------------------------------------

def sayfayi_ac(ctx, luca_sayfasi, log=None):
    """Luca oturumunda (secili firma sunucuda tutulur) Defter Beyan sayfasini yeni sekmede acar."""
    k = urlparse(luca_sayfasi.url)
    adres = f"{k.scheme}://{k.netloc}{DB_YOLU}&r={random.random()}"
    sayfa = ctx.new_page()
    sayfa.goto(adres, wait_until="domcontentloaded", timeout=60000)
    sayfa_durulsun(sayfa, azami_ms=3000)
    if not (gorunur_mu(sayfa, "Gelirler", sure=15000) and gorunur_mu(sayfa, "Giderler", sure=1000)):
        raise LookupError("Defter Beyan sayfasi açılamadı (Gelirler/Giderler sekmesi görünmüyor; "
                          "firma işletme defteri modülünde olmayabilir)")
    return sayfa


def sekme_ac(sayfa, tur):
    ad = SEKMELER[tur]
    _, oge = metinle_bul(sayfa, ad, sure=8000)
    oge.click()
    try:  # sekme sayfayi yeniden yukleyebilir: eski sayfadaki "Listele"yi gorup yanlis karar verilmesin
        sayfa.wait_for_load_state("domcontentloaded", timeout=8000)
    except Exception:
        pass
    sayfa_durulsun(sayfa, azami_ms=2500)
    if not gorunur_mu(sayfa, ["Listele", "Evrak No"], sure=15000):
        raise LookupError(f"{ad} sekmesi açılmadı")


# --- liste ----------------------------------------------------------------------------------------

def tabloyu_oku(sayfa):
    """{'basliklar': [...], 'satirlar': [[...]]} ya da (liste henuz yok/okunamadi) None."""
    for fr in cerceveler(sayfa):
        for js in (GRID_OKU_JS, TABLO_JS):   # once jqx grid'in kendi arayuzu, sonra duz HTML tablo
            try:
                t = fr.evaluate(js)
            except Exception:
                continue
            if t:
                return t
    return None


def _kayit_yok_yazisi(sayfa):
    return any(gorunur_mu(sayfa, m, sure=0) for m in KAYIT_YOK_METINLERI)


def durum_sec(sayfa, hedef):
    """Durum kutusunu (Tumu / Gonderilmemisler / Gonderilmisler) ayarlar ve secimi dogrular.

    Luca'da kutu ozel bir acilir liste olabilir (asil <select> gizli kalir): once gorunen <select>, sonra ozel listeye
    tiklama, son care gizli <select>'in degerini yazma denenir."""
    istenen = _k(hedef)
    for fr in cerceveler(sayfa):
        try:
            kutular = fr.locator("select")
            for i in range(kutular.count()):
                kutu = kutular.nth(i)
                secenekler = kutu.locator("option").all_inner_texts()
                eslesen = next((o for o in secenekler if _k(o) == istenen), None)
                if eslesen is None or not any("gonderilmemis" in _k(o) for o in secenekler):
                    continue
                secili = lambda: _k(kutu.evaluate("e => (e.selectedOptions[0] || {}).text || ''")) == istenen
                if secili():
                    return True
                if kutu.is_visible():
                    try:
                        kutu.select_option(label=eslesen, timeout=5000)
                        if secili():
                            return True
                    except Exception:
                        pass
                else:   # ozel gosterge: gorunen secili yaziya tiklayip listeden sec
                    simdiki = kutu.evaluate("e => (e.selectedOptions[0] || {}).text || ''").strip()
                    try:
                        _, gosterge = metinle_bul(sayfa, simdiki, sure=1500)
                        gosterge.click(timeout=3000)
                        _, secenek = metinle_bul(sayfa, eslesen, sure=2500)
                        secenek.click(timeout=3000)
                        sayfa_durulsun(sayfa, azami_ms=500)
                        if secili():
                            return True
                    except Exception:
                        pass
                kutu.evaluate("""(e, ad) => { const i = [...e.options].findIndex(o => o.text.trim() === ad);
                    if (i >= 0) { e.selectedIndex = i; e.dispatchEvent(new Event('input', {bubbles: true}));
                    e.dispatchEvent(new Event('change', {bubbles: true})); } }""", eslesen.strip())
                if secili():
                    return True
        except Exception:
            continue
    # <select> yok: gorunen deger tiklanip secenek secilir
    for gorunen in (TUMU, GONDERILMEMIS, GONDERILMIS):
        try:
            _, oge = metinle_bul(sayfa, gorunen, sure=800)
            oge.click()
            _, secenek = metinle_bul(sayfa, hedef, sure=2500)
            secenek.click()
            return True
        except Exception:
            continue
    raise LookupError("Durum kutusu bulunamadı")


# Gorunen, tarih yazilabilir kutulari bulup isaretler. 1) "Evrak Tarihi" yazisindan sonra gelen ilk iki gorunen kutu;
# 2) olmazsa degeri GG/AA/YYYY olan ilk iki gorunen kutu (Gonderilme Tarihi kutulari bos oldugu icin ayri kalir).
KUTU_ISARETLE_JS = """() => {
  const norm = s => (s || '').replace(/[\\s\\u00a0]+/g, ' ').trim().toLowerCase();
  const gorunur = e => !!(e.offsetParent || e.getClientRects().length) && getComputedStyle(e).visibility !== 'hidden';
  document.querySelectorAll('[data-lb-db]').forEach(e => e.removeAttribute('data-lb-db'));
  const yasak = ['hidden', 'checkbox', 'radio', 'button', 'submit', 'image', 'file', 'password'];
  const girdiler = [...document.querySelectorAll('input')].filter(e => gorunur(e) && !yasak.includes((e.type || 'text').toLowerCase()));
  let sec = [];
  const etiketler = [...document.querySelectorAll('body *')].filter(e => gorunur(e) && e.children.length < 3 &&
      norm(e.textContent).startsWith('evrak tarihi') && norm(e.textContent).length <= 16);
  for (const el of etiketler) {
    const sonra = girdiler.filter(g => !el.contains(g) && (el.compareDocumentPosition(g) & Node.DOCUMENT_POSITION_FOLLOWING));
    if (sonra.length >= 2) { sec = sonra.slice(0, 2); break; }
  }
  let yontem = 'etiket';
  if (sec.length < 2) {
    yontem = 'deger';
    sec = girdiler.filter(e => /^\\d{2}[\\/.]\\d{2}[\\/.]\\d{4}$/.test((e.value || '').trim())).slice(0, 2);
  }
  sec.forEach((e, i) => e.setAttribute('data-lb-db', String(i)));
  return sec.length === 2 ? yontem : '';
}"""


def evrak_tarihi_kutulari(sayfa, sure=12000):
    """Evrak Tarihi baslangic/bitis kutulari (gorunen); sayfa yuklenirken kutular gecikebilir, beklenir."""
    def bak():
        for fr in cerceveler(sayfa):
            try:
                if fr.evaluate(KUTU_ISARETLE_JS):
                    return [fr.locator("[data-lb-db='0']").first, fr.locator("[data-lb-db='1']").first]
            except Exception:
                continue
        return None
    return kosulu_bekle(sayfa, bak, sure, aralik_ms=500) or []


def pencerede_tikla(sayfa, pencere, metinler, sure=4000):
    """Butona pencerenin icinden basar; pencere ogesi dugmeyi icermiyorsa gorunen dugmeye sayfadan basilir."""
    m = _ekran_pencerede_tikla(sayfa, pencere, metinler, sure) if pencere is not None else None
    if m:
        return m
    for metin in metinler:
        if dugmeye_bas(sayfa, metin, sure=2500):
            sayfa_durulsun(sayfa, azami_ms=600)
            return metin
    return None


# Luca'nin Evrak Tarihi kutulari jqxDateTimeInput, Durum jqxDropDownList bilesenidir (<input type="textarea"> + gizli <select>).
# Metin yazmak bilesenin kendi degerini bozabildigi icin (2002 gibi) bilesenin API'si kullanilir: setDate / selectIndex.
# Etkin bolum ('.section.db_gelir' / '.section.db_gider'; digeri gizli) icinde calisir.
FORM_AYARLA_JS = """([bas, bit, durum]) => {
  const jq = window.jQuery || window.$;
  if (!jq || !jq.fn || !jq.fn.jqxDateTimeInput || !jq.fn.jqxDropDownList) return null;
  const gorunur = e => !!(e.offsetParent || e.getClientRects().length);
  const bolum = [...document.querySelectorAll('.section')].find(b => /db_g(elir|ider)\\b/.test(b.className) &&
      !/alt_tur/.test(b.className) && gorunur(b));
  if (!bolum) return null;
  const kutu = ad => bolum.querySelector('div.jqx-datetimeinput[name="' + ad + '"]');
  const b = kutu('bas_tarih'), t = kutu('bit_tarih');
  const liste = bolum.querySelector('[role=combobox][id^="durum_"]');
  const sel = bolum.querySelector('select[name="durum"]');
  if (!b || !t || !liste) return null;
  const tarih = s => { const m = /^(\\d{1,2})\\/(\\d{1,2})\\/(\\d{4})$/.exec(s); return new Date(+m[3], +m[2] - 1, +m[1]); };
  jq(b).jqxDateTimeInput('setDate', tarih(bas));
  jq(t).jqxDateTimeInput('setDate', tarih(bit));
  const dl = jq(liste), ogeler = dl.jqxDropDownList('getItems') || [];
  const oge = ogeler.find(o => String(o.label).trim() === durum);
  if (!oge) return {hata: 'durum seçeneği yok: ' + ogeler.map(o => o.label).join('|')};
  dl.jqxDropDownList('selectIndex', oge.index);
  const secili = dl.jqxDropDownList('getSelectedItem');
  if (sel && sel.value !== String(oge.value == null ? '' : oge.value)) {   // gizli select esitlenmediyse esitle
    sel.value = oge.value == null ? '' : oge.value; sel.dispatchEvent(new Event('change', {bubbles: true}));
  }
  return {bas: jq(b).jqxDateTimeInput('getText'), bit: jq(t).jqxDateTimeInput('getText'),
          durum: secili ? String(secili.label).trim() : '', sel: sel ? sel.value : null};
}"""


def formu_ayarla(sayfa, bas, bit, durum):
    """jqx bilesenleriyle Evrak Tarihi + Durum ayarlar. True: ayarlandi ve dogrulandi; False: bilesen yok/dogrulanamadi
    (cagiran metin yazma yoluna doner)."""
    for fr in cerceveler(sayfa):
        try:
            o = fr.evaluate(FORM_AYARLA_JS, [bas, bit, durum])
        except Exception:
            continue
        if not o:
            continue
        if o.get("hata"):
            return False
        sayfa_durulsun(sayfa, azami_ms=400)
        return (o.get("bas") == bas and o.get("bit") == bit and o.get("durum") == durum)
    return False


def _kutu_degeri(kutu):
    try:
        return (kutu.input_value() or "").strip()
    except Exception:
        return ""


def _tarih_yaz_bir(kutu, deger):
    """Kutuya tarihi yazar; kutudan ayrilinca (blur) degeri geri okuyup dogrular. Tarih bilesenleri yazilan degeri
    bozabildigi icin (maske, secici) yontemler sirayla denenir: dogrudan yaz / yalniz rakam yaz / bicimli yaz / JS."""
    rakam = deger.replace("/", "")
    yaz_dizi = getattr(kutu, "press_sequentially", None) or kutu.type

    def tus(metin):
        kutu.click(timeout=4000)
        kutu.press("Control+a")
        kutu.press("Delete")
        yaz_dizi(metin, delay=90)

    denemeler = (
        lambda: kutu.fill(deger, timeout=4000),
        lambda: tus(rakam),
        lambda: tus(deger),
        lambda: kutu.evaluate("(e, v) => { e.removeAttribute('readonly'); e.value = v; "
                              "e.dispatchEvent(new Event('input', {bubbles: true})); }", deger),
    )
    for dene in denemeler:
        try:
            dene()
        except Exception:
            continue
        try:   # sonraki kutuya gecmeden (secici acilmasin) kutudan ayril: degisiklik olayi tetiklenir
            kutu.evaluate("e => { e.dispatchEvent(new Event('change', {bubbles: true})); e.blur(); }")
        except Exception:
            pass
        time.sleep(0.4)
        if _kutu_degeri(kutu) == deger:
            return True
    return False


def tarih_araligi_yaz(kutular, bas, bit):
    """Iki kutuya yazar; ikisinin de gercekten istenen deger oldugunu dogrular (aksi halde LookupError)."""
    for tur in range(2):    # ikinci kutu birincisini bozabilir (aralik kisiti): tum degerler son kez dogrulanir
        for kutu, deger in zip(kutular, (bas, bit)):
            if _kutu_degeri(kutu) != deger and not _tarih_yaz_bir(kutu, deger):
                raise LookupError(f"Evrak Tarihi kutusuna {deger} yazılamadı (görünen: '{_kutu_degeri(kutu)}')")
        if [_kutu_degeri(k) for k in kutular] == [bas, bit]:
            return
    raise LookupError(f"Evrak Tarihi {bas} - {bit} yerine {_kutu_degeri(kutular[0])} - {_kutu_degeri(kutular[1])} göründü")


def _tarih_cozumle(metin):
    m = re.search(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", metin or "")
    return (int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def tarihleri_dogrula(tablo, bas, bit):
    """Listedeki her kaydin Evrak Tarihi secilen aralikta mi? Degilse (tarih kutusu bozulmus olabilir) LookupError:
    aralik disindaki kayitlar yanlislikla gonderilmesin diye islem durur."""
    sutun = next((i for i, b in enumerate(tablo["basliklar"]) if "evrak tarihi" in _k(b)), None)
    if sutun is None:
        return
    alt, ust = _tarih_cozumle(bas), _tarih_cozumle(bit)
    for satir in tablo["satirlar"]:
        t = _tarih_cozumle(satir[sutun]) if sutun < len(satir) else None
        if t and not (alt <= t <= ust):
            raise LookupError(f"Listede {bas}-{bit} dışında kayıt var ({satir[sutun]}); tarih aralığı uygulanmamış, "
                              "güvenlik için durduruldu")


GRID_SAYISI_JS = """() => {
  const jq = window.jQuery || window.$;
  if (!jq || !jq.fn || !jq.fn.jqxGrid) return null;
  for (const el of document.querySelectorAll('.jqx-grid')) {
    if (!(el.offsetParent || el.getClientRects().length)) continue;
    try { return jq(el).jqxGrid('getdatainformation').rowscount; } catch (e) {}
  }
  return null;
}"""


def _satir_sayisi(sayfa):
    """Gorunen listenin satir sayisi (jqx grid ya da duz tablo); liste henuz yoksa None. Ucuz: satirlar okunmaz."""
    for fr in cerceveler(sayfa):
        try:
            n = fr.evaluate(GRID_SAYISI_JS)
        except Exception:
            continue
        if n is not None:
            return int(n)
    t = tabloyu_oku(sayfa)
    return None if t is None else len(t["satirlar"])


def _liste_kararli(sayfa, sure):
    """Liste verisi sonradan (ajax) yuklendigi icin satir sayisi kararli olana kadar bekler; bos liste daha uzun beklenir.
    Hemen okumak 'kayit yok' sanilmasina yol aciyordu (ayni sorgu bir seferinde 35, digerinde 0 donuyordu)."""
    son, ayni, bitis = None, 0, time.time() + sure
    while time.time() < bitis:
        n = _satir_sayisi(sayfa)
        if n is None:
            son, ayni = None, 0
        else:
            ayni = ayni + 1 if n == son else 0
            son = n
            if n == 0 and _kayit_yok_yazisi(sayfa):
                return True
            if ayni >= (3 if n else 6):
                return True
        time.sleep(0.6)
    return False


def listele(sayfa, bas, bit, durum, sure=40000, log=None, tur=None):
    """Evrak Tarihi araligi + Durum ile Listele'ye basar; okunan tabloyu dondurur (kayit yoksa satirlar bos)."""
    if not gorunur_mu(sayfa, "Listele", sure=1200):
        dugmeye_bas(sayfa, "Arama")  # liste varken suzgec formu 'Arama' ile yeniden acilir
        if not gorunur_mu(sayfa, "Listele", sure=5000):
            raise LookupError("Listele düğmesi bulunamadı")
    if not formu_ayarla(sayfa, bas, bit, durum):      # jqx bilesenleri: setDate + selectIndex (dogrulanir)
        kutular = evrak_tarihi_kutulari(sayfa)
        if len(kutular) < 2:
            raise LookupError("Evrak Tarihi kutuları bulunamadı")
        tarih_araligi_yaz(kutular, bas, bit)  # Gonderilme Tarihi kutulari bos kalir
        durum_sec(sayfa, durum)
    from playwright.sync_api import TimeoutError as ZamanAsimi
    yanit = None
    try:
        with sayfa.expect_response(lambda r: "gelir_gider_listesi" in r.url, timeout=20000) as bilgi:
            if not dugmeye_bas(sayfa, "Listele"):
                if not (tur and _js_listele(sayfa, tur)):
                    raise LookupError("Listele düğmesine basılamadı")
        yanit = bilgi.value
    except ZamanAsimi:
        pass   # liste istegi gorulmedi: asagida yine de satir sayisi kararli olana kadar beklenir
    if log is not None:
        if yanit is not None:
            req = yanit.request
            yaz(f"    Liste isteği ({durum}, {bas}-{bit}): {req.method} {req.url.split('/')[-1][:160]}"
                + (f" | {(req.post_data or '')[:200]}" if req.method != "GET" else ""), log)
        else:
            yaz(f"    Liste isteği görülmedi ({durum}); ekrandaki liste okunacak", log)
    if yanit is None:
        time.sleep(1.5)
    if not _liste_kararli(sayfa, sure):
        acik_pencereleri_kapat(sayfa)
    t = tabloyu_oku(sayfa)
    if t is None and _kayit_yok_yazisi(sayfa):
        acik_pencereleri_kapat(sayfa)
        t = {"basliklar": [], "satirlar": []}
    if t is None:
        raise LookupError(f"Liste okunamadı ({durum})")
    tarihleri_dogrula(t, bas, bit)
    return t


def _js_listele(sayfa, tur):
    """Dugmeye basilamazsa Luca'nin kendi islevi (onclick: Luca.defter_beyan.listele('gelir', 0, null))."""
    try:
        sayfa.evaluate(f"Luca.defter_beyan.listele('{tur}', 0, null)")
        return True
    except Exception:
        return False


def hepsini_sec(sayfa):
    """Listedeki tum kayitlari isaretler; isaretli satir sayisini dondurur."""
    for fr in cerceveler(sayfa):
        try:
            g = fr.evaluate(GRID_SEC_JS)
            if g:
                return int(g["secili"]) if g["secili"] == g["toplam"] else 0   # eksik secim: cagiran durdurur
            sayi = fr.evaluate(HEPSINI_SEC_JS)
        except Exception:
            continue
        if sayi:
            return int(sayi)
    return 0


# --- kontrol --------------------------------------------------------------------------------------

def kontrol_tur(sayfa, tur, bas, bit, log=None):
    """Bir sekmede (gelir/gider) donemin GONDERILMEMIS kayitlarini sayar; ozet sozluk dondurur.

    Her zaman yalniz Gonderilmemisler listelenir (Gonderilmis/Tumu sorgulanmaz; sayfa bu durumda kalir)."""
    sekme_ac(sayfa, tur)
    bekleyen = listele(sayfa, bas, bit, GONDERILMEMIS, log=log, tur=tur)
    adet, tutar, kayitlar, sabit = db_sonuc.kayitlari_ozetle(bekleyen["basliklar"], bekleyen["satirlar"])
    return {"gonderilmemis": adet, "tutar_gonderilmemis": tutar, "kayitlar": kayitlar, "sabit_kiymet": sabit}


# --- gonderme -------------------------------------------------------------------------------------

def islem_tikla(sayfa, hedef, js=None):
    """Alttaki 'Islemler' menusunden bir ogeyi secer (menu tiklamayla ya da uzerine gelince aciliyor olabilir)."""
    for eylem in ("click", "hover"):
        try:
            _, menu = metinle_bul(sayfa, "İşlemler", sure=5000)
            getattr(menu, eylem)()
        except Exception:
            continue
        if gorunur_mu(sayfa, hedef, sure=1500):
            _, oge = metinle_bul(sayfa, hedef, sure=3000)
            oge.click()
            return True
    if js:
        try:  # son care: menu ogesinin cagirdigi sayfa islevi (javascript:Luca.defter_beyan.gonder('gider'))
            sayfa.evaluate(js)
            return True
        except Exception:
            pass
    return False


CARI_SAYISI = re.compile(r"(\d+)\s*adet\s+cari\s+sorgulan", re.I)
CARI_YOK = re.compile(r"sorgulanacak\s+kay[ıi]t\s+bulunamad", re.I)


def cari_sorgula(sayfa, log=None):
    """Islemler > Cari Bilgi Sorgula. Luca'nin akisi: SORGULAMA UYARI penceresinde 'buraya' (eksik bilgili kayitlari secer)
    -> Tamam -> '<N> adet cari sorgulandi.' ya da 'Sorgulanacak kayit bulunamadi.' -> Tamam. Sorgulananlar secili kalir.
    Donus: (sorgulanan adet, pencere yazisi)."""
    if not islem_tikla(sayfa, "Cari Bilgi Sorgula"):
        raise LookupError("Işlemler > Cari Bilgi Sorgula bulunamadı; gönderilmedi")
    _, uyari = diyalog_bekle(sayfa, ("SORGULAMA UYARI", "Sadece seçili kayıtlar"), 10000)
    if uyari is None:
        raise LookupError("Cari sorgu onay penceresi (SORGULAMA UYARI) çıkmadı; gönderilmedi")
    if not pencerede_tikla(sayfa, uyari, ["buraya"]):
        raise LookupError("Cari sorgu penceresinde 'buraya' bağlantısı bulunamadı; gönderilmedi")
    sayfa_durulsun(sayfa, azami_ms=1500)
    _, uyari = diyalog_bekle(sayfa, ("SORGULAMA UYARI", "Devam etmek istiyor"), 4000)
    if uyari is not None:
        pencerede_tikla(sayfa, uyari, ["Tamam"])
    # Sonuc penceresi: 'CARİ BİLGİ SORGULAMA' (textarea). Satirlar tek tek dusunce ('<TC> sorgulandi.') yazi buyur; son satir
    # '<N> adet cari sorgulandi.' ya da 'Sorgulanacak kayit bulunamadi.' gelince Tamam'a basilir.
    yazi, bitis = "", time.time() + 240
    while time.time() < bitis:
        yazi = log_yazisi(sayfa, ("adet cari sorgulandı", "Sorgulanacak kayıt bulunamadı"))
        if not yazi:   # metin kutusu degilse: sayfadaki gorunen yazidan ilgili satirlar
            govde = sayfa_yazisi(sayfa)
            if CARI_SAYISI.search(govde) or CARI_YOK.search(govde):
                yazi = "\n".join(l for l in govde.splitlines() if "sorgulan" in _k(l))
        if yazi and (CARI_SAYISI.search(yazi) or CARI_YOK.search(yazi)):
            break
        time.sleep(1)
    else:
        raise LookupError("Cari sorgu sonucu (… adet cari sorgulandı / Sorgulanacak kayıt bulunamadı) görünmedi; gönderilmedi")
    pencerede_tikla(sayfa, None, ["Tamam"])   # pencere ogesi yok: gorunen Tamam'a sayfadan basilir
    kosulu_bekle(sayfa, lambda: not log_yazisi(sayfa, ("adet cari sorgulandı", "Sorgulanacak kayıt bulunamadı")), 8000, aralik_ms=400)
    sayfa_durulsun(sayfa, azami_ms=1500)
    m = CARI_SAYISI.search(yazi)
    adet = int(m.group(1)) if m else 0
    if log:
        yaz("    Cari sorgu: " + (f"{adet} kayıt sorgulandı" if adet else "sorgulanacak kayıt yok")
            + ("" if (m or CARI_YOK.search(yazi)) else f" | {' '.join(yazi.split())[:120]}"), log)
    return adet, yazi


def gonder_tikla(sayfa, tur):
    return islem_tikla(sayfa, "Defter Beyan Sistemine Gönder", f"Luca.defter_beyan.gonder('{tur}')")


def diyalog_bekle(sayfa, capalar, azami_ms=4000):
    """Yazisinda capalardan biri gecen GORUNEN Luca penceresini bekler; (cerceve, pencere) ya da (None, None).

    Ayni baslikli gizli pencereler (ornegin Cari ve Gonder icin iki ayri 'SORGULAMA UYARI') DOM'da kalabildiginden once
    acik (gorunen) pencereye bakilir; bulunamazsa Luca'nin ortak yontemi denenir."""
    if isinstance(capalar, str):
        capalar = (capalar,)

    def bak():
        fr, pencere = acik_pencere(sayfa)
        if pencere is not None:
            yazi = _pencere_yazisi(pencere)
            if any(_k(c) in _k(yazi) for c in capalar):   # Turkce buyuk/kucuk harf (İ/ı) farki olmadan
                return fr, pencere
        return None

    sonuc = kosulu_bekle(sayfa, bak, azami_ms, aralik_ms=250)
    if sonuc:
        return sonuc
    return _ekran_diyalog_bekle(sayfa, capalar, 500)


# Sonuc pencereleri (CARİ BİLGİ SORGULAMA, DEFTER BEYAN ENTEGRASYON) yaziyi bir textarea'da gosterir ve yazi ile bulunan
# "pencere" ogesi cogu zaman yalniz baslik satiridir (textarea icinde degildir). Bu yuzden sonuc, pencere ogesine degil
# sayfadaki GORUNEN metin kutularina bakilarak okunur.
LOG_KUTULARI_JS = """() => [...document.querySelectorAll('textarea')]
  .filter(e => e.offsetParent || e.getClientRects().length).map(e => e.value || '')"""
SAYFA_YAZISI_JS = "() => (document.body ? document.body.innerText : '') || ''"
API_ALANLARI_JS = """() => [...document.querySelectorAll('input')].filter(e => (e.offsetParent || e.getClientRects().length) &&
  ['text', 'password', ''].includes((e.type || '').toLowerCase()) &&
  /api|key|secret|anahtar/i.test((e.id || '') + ' ' + (e.name || '') + ' ' + (e.placeholder || ''))).map(e => (e.value || '').trim())"""


def log_yazisi(sayfa, ipuclari):
    """Gorunen metin kutularindan (tum cerceveler) ipuclarindan birini iceren ilkinin yazisi; yoksa ''."""
    for fr in cerceveler(sayfa):
        try:
            kutular = fr.evaluate(LOG_KUTULARI_JS)
        except Exception:
            continue
        for y in kutular:
            if any(_k(i) in _k(y) for i in ipuclari):
                return y.strip()
    return ""


def sayfa_yazisi(sayfa):
    parca = []
    for fr in cerceveler(sayfa):
        try:
            parca.append(fr.evaluate(SAYFA_YAZISI_JS))
        except Exception:
            continue
    return "\n".join(parca)


def api_alanlari_dolu_mu(sayfa):
    """Giris Bilgileri penceresindeki API Key/Secret kutulari (sayfa genelinde gorunenler) dolu mu; kutu bulunamazsa True."""
    degerler = []
    for fr in cerceveler(sayfa):
        try:
            degerler += fr.evaluate(API_ALANLARI_JS)
        except Exception:
            continue
    return all(degerler) if degerler else True


def pencereyi_gec(sayfa, bekle_sn=8, tuslar=("Tamam", "Evet", "Kapat"), log=None):
    """Bir islemden sonra cikan bilgi/onay penceresi varsa yazisini alip kapatir; yazisini dondurur ('' = pencere yok).

    Cari Bilgi Sorgula ve Kaydet sonrasi cikan pencereleri gecmek icindir; pencere hic cikmayabilir."""
    bitis = time.time() + bekle_sn
    pencere = None
    while time.time() < bitis:
        _, pencere = acik_pencere(sayfa)
        if pencere is not None:
            break
        time.sleep(0.4)
    if pencere is None:
        return ""
    son, ayni = "", 0
    while ayni < 2 and time.time() < bitis + 60:   # yazi degisiyorsa (ilerleme) bekle
        yazi = _pencere_yazisi(pencere)
        ayni = ayni + 1 if yazi == son else 0
        son = yazi
        time.sleep(0.8)
    pencerede_tikla(sayfa, pencere, list(tuslar))
    sayfa_durulsun(sayfa, azami_ms=2000)
    acik_pencereleri_kapat(sayfa)
    if log and son:
        yaz(f"    Pencere: {' '.join(son.split())[:150]}", log)
    return son


def _alanlar_dolu(pencere):
    """Giris Bilgileri penceresindeki API Key / Secret kutulari dolu mu (bos ise gonderme yapilmaz)."""
    try:
        kutular = pencere.locator("input[type=text], input[type=password], input:not([type])")
        degerler = [kutular.nth(i).input_value() for i in range(kutular.count()) if kutular.nth(i).is_visible()]
    except Exception:
        return True  # okunamadi: Luca'nin kendi dogrulamasina birakilir
    return all((d or "").strip() for d in degerler) if degerler else True


PENCERE_YAZISI_JS = """e => { const t = [e.innerText || ''];
  e.querySelectorAll('textarea, input[type=text]').forEach(x => { if (x.value) t.push(x.value); });   // sonuc kutulari
  return t.join('\\n'); }"""


def _pencere_yazisi(pencere):
    """Pencerenin gorunen yazisi + icindeki metin kutularinin (textarea) icerigi: Luca sonuc yazilarini textarea'da gosterir
    ('CARİ BİLGİ SORGULAMA' ve 'DEFTER BEYAN ENTEGRASYON'); inner_text bunlari vermez."""
    try:
        return (pencere.evaluate(PENCERE_YAZISI_JS) or "").strip()
    except Exception:
        try:
            return (pencere.inner_text() or "").strip()
        except Exception:
            return ""


def gonderim_pencereleri(sayfa, log=None, azami_saniye=300):
    """Onay ve giris pencerelerini gecip DEFTER BEYAN ENTEGRASYON penceresinin yazisini dondurur.

    Donus: (mesaj, hata). Hata doluysa gonderme baslamamistir (pencere cikmadi / API bilgileri bos)."""
    _, uyari = diyalog_bekle(sayfa, ("SORGULAMA UYARI", "Sadece seçili kayıtlar"), 10000)
    if uyari is None:
        return "", "Onay penceresi (SORGULAMA UYARI) çıkmadı"
    if not pencerede_tikla(sayfa, uyari, ["Tamam"]):
        return "", "Onay penceresinde Tamam'a basılamadı"
    _, giris = diyalog_bekle(sayfa, ("Giriş Bilgileri", "API Key"), 6000)
    if giris is not None:
        if not (_alanlar_dolu(giris) and api_alanlari_dolu_mu(sayfa)):
            pencerede_tikla(sayfa, giris, ["Kapat"])
            return "", "Defter Beyan API Key/Secret bilgileri Luca'da boş; önce Luca'da girin (gönderilmedi)"
        pencerede_tikla(sayfa, giris, ["Tamam"])
    _, ent = diyalog_bekle(sayfa, ("DEFTER BEYAN ENTEGRASYON", "gönderim başlıyor"), 20000)
    if ent is None:
        return "", "Entegrasyon (sonuç) penceresi çıkmadı"
    son, ayni, bitis, bitti_an = "", 0, time.time() + azami_saniye, None
    ipuclari = ("gönderim başlıyor", "gönderim tamamlandı", "satır için", "Gönderilecek seçili kayıt")
    while time.time() < bitis:
        yazi = log_yazisi(sayfa, ipuclari) or _pencere_yazisi(ent)
        ayni = ayni + 1 if yazi == son else 0
        son = yazi
        if db_sonuc.gonderilen_sayisi(son) is not None or db_sonuc.gonderim_sinifla(son) == db_sonuc.KAYIT_YOK:
            bitti_an = bitti_an or time.time()      # son satir geldi: kisa sure sonra bitir
            if time.time() - bitti_an >= 1.5:
                break
        elif son and ayni >= 4 and time.time() > bitis - azami_saniye + 3:  # yazi ~4 sn degismedi: bitti
            break
        time.sleep(1)
    pencerede_tikla(sayfa, ent, ["Tamam"])
    kosulu_bekle(sayfa, lambda: not log_yazisi(sayfa, ipuclari), 8000, aralik_ms=400)
    sayfa_durulsun(sayfa, azami_ms=1500)
    return son, ""


def gonder_tur(sayfa, tur, bas, bit, log=None):
    """Bir sekmede Gonderilmemisler'i listeleyip hepsini Defter Beyan'a gonderir ve kalani yeniden sayar.

    Donus: {'sonuc', 'mesaj', 'gonderilen', 'kalan'}; 'sonuc' db_sonuc.KAYIT_YOK/HATA/BASARILI/BELIRSIZ."""
    sekme_ac(sayfa, tur)
    t = listele(sayfa, bas, bit, GONDERILMEMIS, log=log, tur=tur)
    n = len(t["satirlar"])
    if n == 0:
        return {"sonuc": db_sonuc.KAYIT_YOK, "mesaj": "Gönderilmemiş kayıt yok", "gonderilen": 0, "kalan": 0}
    # Elle yapilan sira: Cari Bilgi Sorgula ('buraya' ile eksik bilgililer secilir) -> Kaydet -> sonra GONDER icin tum
    # gonderilmemisler secilir. Cari oncesi secim yapilmaz: 'buraya' yalniz eksik bilgili kayitlari sorgulatsin.
    adet, cari = cari_sorgula(sayfa, log)
    if adet > 0:   # sorgulananlar secili kalir: dogrudan Kaydet
        if not dugmeye_bas(sayfa, "Kaydet"):
            raise LookupError("Kaydet düğmesine basılamadı; gönderilmedi")
        pencereyi_gec(sayfa, bekle_sn=8, log=log)
    t = tabloyu_oku(sayfa) or {"satirlar": []}
    if len(t["satirlar"]) != n:
        raise LookupError(f"Cari sorgu/Kaydet sonrası liste {n} yerine {len(t['satirlar'])} kayıt; güvenlik için gönderilmedi")
    secilen = hepsini_sec(sayfa)   # gonderilecekler: tum gonderilmemis kayitlar
    if secilen != n:
        raise LookupError(f"{n} kayıttan {secilen} tanesi seçilebildi; güvenlik için gönderilmedi")
    if not gonder_tikla(sayfa, tur):
        raise LookupError("Işlemler > Defter Beyan Sistemine Gönder bulunamadı")
    mesaj, hata = gonderim_pencereleri(sayfa, log)
    if hata:
        return {"sonuc": db_sonuc.HATA, "mesaj": hata, "gonderilen": 0, "kalan": n}
    sinif = db_sonuc.gonderim_sinifla(mesaj)
    ayrinti = db_sonuc.gonderim_ayrintisi(mesaj)
    bildirilen = ayrinti["gonderilen"]  # pencere: "gönderim tamamlandı. (N)" = hatasiz giden kayit sayisi
    # Elle yapilan kontrol: pencerede Tamam, sonra alttaki Yenile; gonderilenler listeden duser, hatalilar kalir
    dugmeye_bas(sayfa, "Yenile")
    sayfa_durulsun(sayfa, azami_ms=2000)
    kalan_t = listele(sayfa, bas, bit, GONDERILMEMIS, log=log, tur=tur)  # ayni suzgecle yeniden oku (Yenile'nin sonucunu dogrular)
    kalan = len(kalan_t["satirlar"])
    _, kalan_tutar, kalan_kayitlar, kalan_sabit = db_sonuc.kayitlari_ozetle(kalan_t["basliklar"], kalan_t["satirlar"])
    if sinif == db_sonuc.BASARILI and (kalan > 0 or (bildirilen is not None and bildirilen != n)):
        sinif = db_sonuc.KISMI  # pencere "tamamlandi" dese de hepsi gitmemis: kullanici kontrol etsin
    return {"sonuc": sinif, "mesaj": mesaj, "gonderilen": max(n - kalan, 0), "kalan": kalan,
            "bildirilen": bildirilen, "hatalar": ayrinti["hatalar"][:200],
            "hata_ozeti": db_sonuc.hata_ozeti(ayrinti["hatalar"]),
            "kalan_tutar": kalan_tutar, "kalan_kayitlar": kalan_kayitlar, "kalan_sabit": kalan_sabit,
            "cari_mesaj": cari[:300], "cari_sorgulanan": adet}


# --- firma ----------------------------------------------------------------------------------------

def firma_isle(sayfa, firma, bas, bit, islem, log, tani_klasoru=None, tani_hep=False, onay=None):
    """Bir firmanin Defter Beyan sayfasinda kontrol (ve istenirse gonderme) yapar; sonuc kaydini dondurur.

    islem: 'kontrol' | 'gonder'. onay(firma, ozet) -> bool: gonderme oncesi son onay (False ise gonderilmez)."""
    donem = f"{bas}-{bit}"
    sonuc = db_sonuc.bos_sonuc(firma, donem, islem)
    for tur in db_sonuc.TURLER:
        try:
            sonuc[tur] = kontrol_tur(sayfa, tur, bas, bit, log)
            t = sonuc[tur]
            yaz(f"    {SEKMELER[tur]}: {t['gonderilmemis']} gönderilmemiş"
                + (f" ({t['tutar_gonderilmemis']:,.2f} TL)".replace(",", "_").replace(".", ",").replace("_", ".")
                   if t["tutar_gonderilmemis"] is not None else "")
                + ""
                + (f" (bunların {t['sabit_kiymet']} tanesi SABİT KIYMET)" if t.get("sabit_kiymet") else ""), log)
        except Exception as e:
            sonuc[tur] = {}
            sonuc["hata"] = f"{SEKMELER[tur]}: {str(e)[:160]}"
            yaz(f"    HATA ({SEKMELER[tur]}): {str(e)[:160]}", log)
            if tur == db_sonuc.TURLER[0]:
                sayfa_ozeti(sayfa, log)     # ilk hatada sayfanin yapisi loga yazilir (kutular, dugmeler)
            if tani_klasoru:
                hata_kaydet(sayfa, tani_klasoru, f"defter-beyan-{firma}-{tur}-hata")
    if tani_hep and tani_klasoru:
        hata_kaydet(sayfa, tani_klasoru, f"defter-beyan-{firma}-son")
    if islem == "gonder" and not sonuc["hata"]:
        # yalniz sabit kiymetten olusan sekme gonderilmez (sabit kiymetler normalde gonderilmez, es gecilir)
        bekleyen = {tur: sonuc[tur].get("gonderilmemis", 0) - sonuc[tur].get("sabit_kiymet", 0)
                    for tur in db_sonuc.TURLER}
        if sum(bekleyen.values()) == 0:
            yaz("    Gönderilecek kayıt yok" + (" (kalanlar yalnız sabit kıymet)" if any(
                sonuc[t].get("gonderilmemis") for t in db_sonuc.TURLER) else ""), log)
        elif onay is not None and not onay(firma, bekleyen):
            sonuc["hata"] = "Gönderme onaylanmadı"
        else:
            for tur in db_sonuc.TURLER:
                if not bekleyen[tur]:
                    continue
                try:
                    g = gonder_tur(sayfa, tur, bas, bit, log)
                except Exception as e:
                    g = {"sonuc": db_sonuc.HATA, "mesaj": str(e)[:200], "gonderilen": 0, "kalan": bekleyen[tur]}
                    if tani_klasoru:
                        hata_kaydet(sayfa, tani_klasoru, f"defter-beyan-{firma}-{tur}-gonderme-hata")
                sonuc[tur]["gonderim"] = g
                yaz(f"    {SEKMELER[tur]} gönderme: {g['sonuc']} — {g['gonderilen']} gönderildi, {g['kalan']} kaldı"
                    + (f" | {g['mesaj'][:120]}" if g["sonuc"] not in (db_sonuc.BASARILI, db_sonuc.KISMI) else ""), log)
                if g.get("kalan"):
                    yaz(f"        Kalan {g['kalan']} kayıt" + (f", bunların {g['kalan_sabit']} tanesi SABİT KIYMET"
                                                              if g.get("kalan_sabit") else ""), log)
                for hata, adet in (g.get("hata_ozeti") or {}).items():
                    yaz(f"        {adet} kayıt: {hata}", log)
    sonuc["durum"] = db_sonuc.firma_durumu(sonuc)
    return sonuc
