# -*- coding: utf-8 -*-
"""Luca'da e-Defter gondermeden once kontrol: e-Defter kapsaminda UYUMSUZ fisleri OKUR (hicbir sey degistirmez).

Yol: Muhasebe > Fis Islemleri > Duzenleme > Toplu Belge Turu ve Odeme Yontemi Duzenleme (ayri bir pencere acilir:
parameterBelgeTuruDuzenlemeAction.do). Form (ekran goruntusunden): Fis Tarihi (iki kutu), Evrak No Dolu / Evrak Tarihi Dolu /
Evrak Tarihi Bos Olan / Belge Turu Bos Olan / Odeme Turu Bos Olan onay kutulari, "E-Defter kapsaminda uyumsuz olan fisleri getir"
onay kutusu ve "E-Defter hata" listesi (Hata Kodu: 20041, 20042, 20044-20048), altta Listele dugmesi.
Listele, "E-DEFTER UYUMSUZ FISLERI DUZENLEME" penceresini (listBelgeTuruDuzenlemeAction.do) acar: Sira, Fis No, Degismeyen Fis No,
Fis Tarihi, Hesap Kodu, Borc, Alacak, Aciklama, Evrak No, Evrak Tarihi, BT (belge turu), Odeme Turu, Durum sutunlari; her fisin
ilk satirinda Sira/Fis No dolu, diger satirlari bostur; altta sayfa dugmeleri ("Sayfa No: 1"), Toplu Deger Ata / Kaydet.
BU PROGRAM HICBIR ZAMAN Kaydet / Toplu Deger Ata'ya basmaz: yalniz her hata kodu icin Listele'ye basar ve listeyi okur.

Her adim saglam yazilmistir (menu verisi + ekran menusu, ana sayfa/pencere/cerceve arama, uyari kutusu yakalama) ama gercek
ekran her zaman beklendigi gibi olmayabilir: neyin tutmadigi gunlukten ve tani/ klasorunden anlasilsin diye adimlar kaydedilir.
"""

import re

from lucabot.bekleme import kosulu_bekle
from lucabot.luca_ekran import acik_pencereleri_kapat
from lucabot.luca_gezinme import menu_yolunu_ac
from lucabot.musteri_listesi import tani_kaydet
from lucabot.ortak import sadelestir, yaz

from . import luca_mizan
from .luca_muavin import _baglantiyi_ac, menu_benzerleri

MENU_ANAHTARI = "belge türü ve ödeme yöntemi düzenleme"
MENU_YOLU = "Muhasebe > Fiş İşlemleri > Düzenleme > Toplu Belge Türü ve Ödeme Yöntemi Düzenleme"
HATA_KODU = re.compile(r"Hata\s*Kodu\s*:?\s*(\d+)", re.I)
FIS_SINIRI = 300         # JSON'a yazilacak en cok fis (sayi her zaman tamdir: 'kesildi' degilse)
SAYFA_SINIRI = 60        # bir hata kodu icin en cok okunacak sayfa
KAYIT_SINIRI = 1000      # "Sayfa No/Kayit Sayisi"nda secilecek en buyuk kayit sayisi (varsayilan kucuk: cok sayfa = yavas)
LISTE_BEKLEME_MS = 45000
KAYIT_YOK = re.compile(r"kay[ıi]t.{0,25}(bulunamad|bulunmuyor|yok)|bulunamad[ıi]|listelenecek", re.I)
# Bu onay kutulari her kontrolde KAPALI olur (yalniz e-Defter uyumsuzlugu aranir); e-Defter kutusu ACIK olur.
KAPALI_KUTULAR = ("Evrak No Dolu", "Evrak Tarihi Dolu", "Evrak Tarihi Boş Olan", "Belge Türü Boş Olan", "Ödeme Türü Boş Olan")
ACIK_KUTU = "E-Defter kapsamında uyumsuz olan fişleri getir"

MENU_ICEREN_JS = r"""anahtar => {
  if (typeof menuItems === 'undefined' || typeof aktar !== 'function') return null;
  const ta = document.createElement('textarea');
  const temiz = t => { ta.innerHTML = (t || '').replace(/<[^>]*>/g, ''); return ta.value.replace(/^\|+/, '').trim().toLocaleLowerCase('tr'); };
  const h = anahtar.toLocaleLowerCase('tr'), cikti = [];
  for (let i = 0; i < menuItems.length; i++) {
    const x = menuItems[i];
    if (x && x[1] && temiz(x[0]).includes(h)) cikti.push([x[0], x[1]]);
  }
  return cikti;
}"""

FORM_VAR_JS = r"""() => {
  const g = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  const l = document.querySelectorAll('th, td, label, span, div, b');
  let hata = false, belge = false;
  for (let i = 0; i < l.length; i++) {
    if (!g(l[i])) continue;
    const t = (l[i].textContent || '').trim();
    if (/^E-?\s*Defter\s*kapsam/i.test(t)) hata = true;        // etiket onay kutusuyla ayni hucrede / label icinde olabilir
    if (l[i].children.length) continue;        // onay kutusunun etiketi hep gorunur ("E-Defter hata" satiri kutu isaretlenince acilir)
    if (/^Belge\s*Türü\s*Boş\s*Olan/i.test(t)) belge = true;     // Fiş Listesi'nde de ayni onay kutusu var: bu etiket ayirir
  }
  return hata && belge;
}"""

# Formu okur ve doldurur. arg: {bas, bit, kod ('' = secimi degistirme), kapali: [...], acik: '...'}
FORM_JS = r"""arg => {
  const g = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  const etiketler = Array.from(document.querySelectorAll('th, td, label, span, div, b')).filter(e => !e.children.length && g(e));
  const duz = t => (t || '').toLocaleLowerCase('tr').replace(/[\s.\-()*:]/g, '');
  const satir = (desen) => {
    for (const e of etiketler) {
      const t = (e.textContent || '').trim();
      if (typeof desen === 'string' ? duz(t) === duz(desen) : desen.test(t)) return e.closest('tr') || e.parentElement;
    }
    return null;
  };
  const yaz = (k, v) => { k.focus(); k.value = v; k.dispatchEvent(new Event('input', {bubbles: true}));
                          k.dispatchEvent(new Event('change', {bubbles: true})); k.blur(); return k.value; };
  const sonuc = {tarihler: null, kutular: {}, secenekler: [], secili: -1, sayfa: null};
  const tr = satir(/^Fiş\s*Tarihi/i);
  if (tr && arg.bas) {
    const kutular = Array.from(tr.querySelectorAll('input')).filter(k => g(k) && !/^(checkbox|button|hidden|image|radio|submit)$/i.test(k.type || ''));
    if (kutular.length >= 2) sonuc.tarihler = [yaz(kutular[0], arg.bas), yaz(kutular[1], arg.bit)];
    else if (kutular.length === 1) sonuc.tarihler = [yaz(kutular[0], arg.bas)];
  }

  // yedek: kutular tek hucrede alt alta olabilir (hucrenin tum metni etikete esit olmaz): kutunun hemen yanindaki yazi okunur
  const yanYazi = cb => {
    if (cb.id) { const l = document.querySelector('label[for="' + cb.id + '"]'); if (l) return l.textContent || ''; }
    const ust = cb.closest('label'); if (ust) return ust.textContent || '';
    let t = '';
    for (let n = cb.nextSibling; n; n = n.nextSibling) {
      if (n.nodeType === 1 && (n.tagName === 'INPUT' || n.tagName === 'BR' || n.tagName === 'SELECT' || n.tagName === 'TABLE')) break;
      t += n.textContent || '';
    }
    return t;
  };
  const metinleBul = ad => {
    const h = duz(ad), kutular = document.querySelectorAll('input[type=checkbox]');
    for (let i = 0; i < kutular.length; i++) if (g(kutular[i]) && duz(yanYazi(kutular[i])) === h) return kutular[i];
    return null;
  };
  // onay kutusu: etiketle ayni hucrede (label icinde) ya da yan hucrede olabilir; en ic eslesen etiketten baslanir
  const kutuBul = (ad) => {
    const h = duz(ad);
    const adaylar = Array.from(document.querySelectorAll('th, td, label, span, div, b')).filter(e => g(e) && duz(e.textContent) === h);
    for (let i = adaylar.length - 1; i >= 0; i--) {
      const e = adaylar[i];
      let cb = e.querySelector('input[type=checkbox]');
      if (!cb && e.tagName === 'LABEL' && e.htmlFor) cb = document.getElementById(e.htmlFor);
      const r = e.closest('tr');
      if (!cb && r) cb = r.querySelector('input[type=checkbox]');
      const kardes = (x) => x && (x.type === 'checkbox' ? x : (x.querySelector ? x.querySelector('input[type=checkbox]') : null));
      if (!cb) cb = kardes(e.previousElementSibling) || kardes(e.nextElementSibling);
      if (cb) return cb;
    }
    return null;
  };
  const kutuAyarla = (ad, istenen) => {
    const cb = kutuBul(ad) || metinleBul(ad);
    if (!cb) { sonuc.kutular[ad] = null; return; }
    if (!cb.disabled && cb.checked !== istenen) {
      cb.click();
      if (cb.checked !== istenen) { cb.checked = istenen; cb.dispatchEvent(new Event('change', {bubbles: true})); }
    }
    sonuc.kutular[ad] = cb.checked;
  };
  for (const ad of arg.kapali) kutuAyarla(ad, false);
  kutuAyarla(arg.acik, true);
  const hr = satir(/^E-?\s*Defter\s*hata/i);
  const s = hr && hr.querySelector('select');
  if (s) {
    sonuc.secenekler = Array.from(s.options).map(o => (o.text || '').replace(/\s+/g, ' ').trim());
    if (arg.kod) {
      let hedef = -1;
      for (let i = 0; i < s.options.length && hedef < 0; i++) if (new RegExp('Hata\\s*Kodu\\s*:?\\s*' + arg.kod + '\\b', 'i').test(s.options[i].text)) hedef = i;
      if (hedef >= 0) { s.selectedIndex = hedef; s.dispatchEvent(new Event('change', {bubbles: true})); }
    }
    sonuc.secili = s.selectedIndex;
  }
  // "Sayfa No/Kayit Sayisi": iki liste (sayfa no, sayfa basina kayit); kayit sayisi izin verilen en buyuk degere cikarilir
  const sr = satir(/^Sayfa\s*No\s*\/\s*Kay[ıi]t/i);
  if (sr) {
    const sel = Array.from(sr.querySelectorAll('select')).filter(g);
    sonuc.sayfa = {listeler: sel.map(x => Array.from(x.options).map(o => (o.text || '').trim()).slice(0, 12)), secili: []};
    if (sel.length >= 2 && arg.kayitSiniri) {
      const k = sel[1];
      let en = -1, deger = -1;
      for (let i = 0; i < k.options.length; i++) {
        const n = parseInt((k.options[i].text || '').replace(/\D/g, ''), 10);
        if (!isNaN(n) && n <= arg.kayitSiniri && n > deger) { deger = n; en = i; }
      }
      if (en >= 0 && k.selectedIndex !== en) { k.selectedIndex = en; k.dispatchEvent(new Event('change', {bubbles: true})); }
    }
    sonuc.sayfa.secili = sel.map(x => (x.options[x.selectedIndex] ? x.options[x.selectedIndex].text.trim() : ''));
  }
  return sonuc;
}"""

LISTE_VAR_JS = r"""capa => {
  const g = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  const duz = t => (t || '').toLocaleLowerCase('tr').replace(/[\s.\-()*:\/]/g, '');
  const c = document.querySelectorAll('th, td');
  for (let i = 0; i < c.length; i++) if (g(c[i]) && !c[i].children.length && duz(c[i].textContent) === capa) return true;
  return false;
}"""

# Listeyi okur: {basliklar, satirlar, sayfa}; baslik hucresi 'Degismeyen Fis No' olan tablo
LISTE_OKU_JS = r"""capa => {
  const g = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  const duz = t => (t || '').toLocaleLowerCase('tr').replace(/[\s.\-()*:\/]/g, '');
  const sade = t => (t || '').replace(/\s+/g, ' ').trim();
  let bas = null;
  for (const c of document.querySelectorAll('th, td')) if (g(c) && !c.children.length && duz(c.textContent) === capa) { bas = c; break; }
  if (!bas) return null;
  const hsatir = bas.closest('tr'), tablo = hsatir.closest('table');
  const basliklar = Array.from(hsatir.children).map(c => sade(c.textContent));
  const hucre = c => { const i = c.querySelector('input[type=text], input:not([type]), textarea'); return sade(i ? i.value : c.textContent); };
  const toplan = (t) => Array.from(t.rows).filter(r => r !== hsatir && r.cells.length === basliklar.length && !r.querySelector('th'))
                             .map(r => Array.from(r.cells).map(hucre));
  let satirlar = toplan(tablo);
  if (!satirlar.length) {   // baslik ayri tabloda olabilir
    for (const t of document.querySelectorAll('table')) { if (t === tablo) continue; const s = toplan(t); if (s.length > satirlar.length) satirlar = s; }
  }
  const m = /Sayfa\s*No\s*:\s*(\d+)/i.exec(document.body.innerText || '');
  return {basliklar, satirlar, sayfa: m ? parseInt(m[1], 10) : null};
}"""

SONRAKI_JS = r"""() => {
  const g = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  let yazi = null;
  for (const e of document.querySelectorAll('td, div, span, label, b')) if (g(e) && !e.children.length && /Sayfa\s*No\s*:/i.test(e.textContent || '')) { yazi = e; break; }
  if (!yazi) return 'sayfa kutusu yok';
  let kap = yazi;
  for (let i = 0; i < 4 && kap.parentElement; i++) {
    kap = kap.parentElement;
    const dugmeler = Array.from(kap.querySelectorAll('button, input[type=button], input[type=image], a, img')).filter(g)
                          .filter(b => !(b.tagName === 'IMG' && b.parentElement && b.parentElement.closest('button, a')));   // dugmenin icindeki resim ayri sayilmaz
    const oklar = dugmeler.filter(b => !(b.textContent || b.value || '').trim() || /^[<>‹›«»]+$/.test((b.textContent || b.value || '').trim()));
    const adli = dugmeler.find(b => /sonraki|ileri|next/i.test((b.title || '') + (b.alt || '') + (b.getAttribute('aria-label') || '')));
    const hedef = adli || (oklar.length >= 2 ? oklar[1] : null);
    if (hedef) { hedef.click(); return 'tiklandi'; }
  }
  return 'dugme yok';
}"""

BOS_MESAJ_JS = r"""() => {
  const t = (document.body && document.body.innerText) || '';
  const m = /[^\n]*(kay[ıi]t[^\n]{0,30}(bulunamad|yok)|bulunamad[ıi])[^\n]*/i.exec(t);
  return m ? m[0].trim().slice(0, 160) : '';
}"""


def menu_baglantilari_iceren(page, anahtar=MENU_ANAHTARI):
    """Menu verisinde adinda anahtar gecen girisler: [(etiket, baglanti)] (menu cercevesi yoksa [])."""
    for fr in page.frames:
        try:
            m = fr.evaluate(MENU_ICEREN_JS, anahtar)
        except Exception:
            continue
        if m is not None:
            return [tuple(x) for x in m]
    return []


def acik_sayfalar(ctx):
    return [p for p in list(ctx.pages) if not p.is_closed()]


def ek_sayfalari_kapat(ctx, ana):
    """Ana pencere disindaki (onceki firmadan kalan e-Defter) pencereleri kapatir."""
    for p in acik_sayfalar(ctx):
        if p is not ana:
            try:
                p.close()
            except Exception:
                pass


def _bul(ctx, js, arg=None):
    """js'in true dondurdugu (sayfa, cerceve) ya da None; acilan pencereler de taranir."""
    for pg in acik_sayfalar(ctx):
        try:
            cerceveler = list(pg.frames)
        except Exception:
            continue
        for fr in cerceveler:
            try:
                if fr.evaluate(js, arg):
                    return pg, fr
            except Exception:
                continue
    return None


def form_bul(ctx):
    return _bul(ctx, FORM_VAR_JS)


CAPA_BELGE = "değişmeyenfişno"      # E-Defter Uyumsuz Fisleri listesinin baslik hucresi (duz metin)
CAPA_FIS = "fişno"                  # Fis Listesi tablosunun baslik hucresi


def liste_bul(ctx, capa=CAPA_BELGE):
    return _bul(ctx, LISTE_VAR_JS, capa)


def dinle(pg, mesajlar):
    """Luca'nin uyari kutularini (alert) kaydeder ve kabul eder (Playwright dinleyici yoksa kutuyu kendiliginden kapatir)."""
    if getattr(pg, "_lb_dinleniyor", False):
        return

    def yakala(d):
        try:
            mesajlar.append(d.message)
            d.accept()
        except Exception:
            pass
    try:
        pg.on("dialog", yakala)
        pg._lb_dinleniyor = True
    except Exception:
        pass


def ekrani_ac(page, log=None):
    """Toplu Belge Turu ve Odeme Yontemi Duzenleme formunu acar: (pencere, cerceve). Menu verisi, olmazsa ekran menusu."""
    ctx = page.context
    ek_sayfalari_kapat(ctx, page)
    acik_pencereleri_kapat(page)
    denenen = []
    for etiket, baglanti in menu_baglantilari_iceren(page):
        if not _baglantiyi_ac(page, baglanti):
            continue
        if kosulu_bekle(page, lambda: form_bul(ctx) is not None, 60000, aralik_ms=500):
            yaz(f"    Belge Türü Düzenleme formu açıldı (menü verisi: {baglanti})", log)
            return form_bul(ctx)
        denenen.append(f"{baglanti}: form açılmadı")
    try:
        menu_yolunu_ac(page, MENU_YOLU, lambda: form_bul(ctx) is not None)
        yaz("    Belge Türü Düzenleme formu açıldı (ekran menüsü)", log)
        return form_bul(ctx)
    except LookupError as e:
        denenen.append(f"ekran menüsü: {e}")
    benzer = menu_benzerleri(page, ("belge türü", "belge turu", "düzenleme"))
    raise LookupError("Toplu Belge Türü ve Ödeme Yöntemi Düzenleme ekranı açılamadı (firmada Fiş İşlemleri yok: 2. sınıf firma olabilir). "
                      "Denenen: " + "; ".join(denenen)[:600] + (f" | menüdeki benzer girişler: {benzer}" if benzer else ""))


def formu_doldur(fr, bas, bit, kod="", kayit_siniri=KAYIT_SINIRI):
    """Fis tarihini yazar, onay kutularini ayarlar, kod verilirse E-Defter hata listesinden onu secer.
    {tarihler, kutular, secenekler, secili}; tarihler yazildigi gibi geri okunamazsa LookupError."""
    arg = {"bas": f"{bas:%d/%m/%Y}", "bit": f"{bit:%d/%m/%Y}", "kod": str(kod or ""),
           "kapali": list(KAPALI_KUTULAR), "acik": ACIK_KUTU, "kayitSiniri": kayit_siniri}
    r = _hata_satiri_bekle(fr, arg) if kod else _degerlendir(fr, FORM_JS, arg)
    beklenen = [f"{bas:%d/%m/%Y}", f"{bit:%d/%m/%Y}"]
    if not r.get("tarihler") or r["tarihler"] != beklenen:
        raise LookupError(f"Fiş Tarihi kutuları doldurulamadı (okunan: {r.get('tarihler')}, beklenen: {beklenen})")
    if kod:
        secili = r["secenekler"][r["secili"]] if 0 <= r.get("secili", -1) < len(r["secenekler"]) else ""
        m = HATA_KODU.search(secili)
        if not m or m.group(1) != str(kod):
            raise LookupError(f"E-Defter hata listesinde {kod} seçilemedi (seçili: {secili[:80]!r})")
    if r["kutular"].get(ACIK_KUTU) is not True:     # bulunamadi (None) ya da isaretlenemedi (False): bos liste "uyumsuz yok" sanilmasin
        raise LookupError("'E-Defter kapsamında uyumsuz olan fişleri getir' kutusu "
                          + ("bulunamadı" if r["kutular"].get(ACIK_KUTU) is None else "işaretlenemedi") + f" (kutular: {r['kutular']})")
    return r


def _degerlendir(fr, js, arg=None, deneme=6):
    """fr.evaluate; form penceresi acilirken sayfa yeniden yuklenirse ("Execution context was destroyed") bekleyip yeniden dener."""
    son = None
    for _ in range(deneme):
        try:
            return fr.evaluate(js, arg)
        except Exception as e:
            m = str(e)
            if not any(k in m for k in ("context was destroyed", "navigation", "Target closed", "detached")):
                raise
            son = e
            try:
                fr.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            fr.page.wait_for_timeout(700)
    raise LookupError(f"Sayfa yüklenirken yenilendi, okunamadı: {str(son)[:120]}")


def _hata_satiri_bekle(fr, arg, deneme=8):
    """'E-Defter hata' satiri onay kutusu isaretlenince gorunur (bazen gecikmeyle): secenekler gelene kadar formu yeniden okur."""
    r = _degerlendir(fr, FORM_JS, arg)
    for _ in range(deneme):
        if r.get("secenekler"):
            break
        fr.page.wait_for_timeout(500)
        r = _degerlendir(fr, FORM_JS, arg)
    return r


def hata_secenekleri(fr):
    """[(kod, metin)]: E-Defter hata listesindeki secenekler; kodu olmayanlar (orn. bos) alinmaz. Once onay kutusu isaretlenir
    (liste ancak o zaman gorunur)."""
    r = _hata_satiri_bekle(fr, {"bas": "", "bit": "", "kod": "", "kapali": [], "acik": ACIK_KUTU, "kayitSiniri": 0})
    sonuc = []
    for metin in r.get("secenekler") or []:
        m = HATA_KODU.search(metin)
        if m:
            sonuc.append((m.group(1), metin))
    return sonuc


def _listele_dugmesi(pg):
    return luca_mizan._rapor_dugmesi(pg, ("Listele",), "E-Defter")


def _bekle_liste(ctx, ana, mesajlar, sure_ms=LISTE_BEKLEME_MS):
    """Listele'den sonra: {'liste': (pg, fr)} ya da {'mesaj': '...'} (uyari kutusu / sayfadaki 'kayit yok'); ikisi de yoksa {}."""
    son = {}

    def hazir():
        r = liste_bul(ctx)
        if r:
            son["liste"] = r
            return True
        if mesajlar:
            son["mesaj"] = mesajlar[-1]
            return True
        try:
            for pg in acik_sayfalar(ctx):
                for fr in pg.frames:
                    m = fr.evaluate(BOS_MESAJ_JS)
                    if m:
                        son["mesaj"] = m
                        return True
        except Exception:
            pass
        return False
    kosulu_bekle(ana, hazir, sure_ms, aralik_ms=400)      # ana pencere hep acik kalir (form/liste pencereleri kapanabilir)
    return son


def _sade(metin):
    return sadelestir(metin).replace(" ", "")


SUTUN_ADLARI = {"sira": "SIRA", "fis_no": "FISNO", "degismeyen": "DEGISMEYENFISNO", "tarih": "FISTARIHI", "hesap": "HESAPKODU",
                "borc": "BORC", "alacak": "ALACAK", "aciklama": "ACIKLAMA", "evrak_no": "EVRAKNO", "evrak_tarihi": "EVRAKTARIHI",
                "bt": "BT", "odeme": "ODEMETURU", "durum": "DURUM"}


def tutar(metin):
    s = re.sub(r"[^0-9,.\-]", "", str(metin or ""))
    if not s or s in ("-", ".", ","):
        return 0.0
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def fisleri_grupla(basliklar, satirlar, fisler=None):
    """Liste satirlarini fislere toplar (fisin ilk satirinda Fis No / Degismeyen Fis No dolu, digerleri bos): sozluk listesi.
    fisler: onceki sayfalardan gelen {anahtar: fis} (sayfa sinirinda bolunen fis birlestirilir)."""
    sade = [_sade(b) for b in basliklar]
    idx = {ad: (sade.index(k) if k in sade else None) for ad, k in SUTUN_ADLARI.items()}
    al = lambda s, ad: (s[idx[ad]] if idx[ad] is not None and idx[ad] < len(s) else "").strip()
    fisler = {} if fisler is None else fisler
    akim = list(fisler.values())[-1] if fisler else None     # onceki sayfanin son fisi: sayfa basinda devam eden satirlar ona aittir
    for s in satirlar:
        fis_no, degismeyen = al(s, "fis_no"), al(s, "degismeyen")
        if fis_no or degismeyen:
            anahtar = (degismeyen, fis_no, al(s, "tarih"))
            akim = fisler.setdefault(anahtar, {"fis_no": fis_no, "tarih": al(s, "tarih"), "degismeyen": degismeyen, "satir": 0,
                                               "evrak": [], "bt": "", "odeme": "", "tutar": 0.0,
                                               "hesap": al(s, "hesap").split(" ")[0], "aciklama": al(s, "aciklama")[:90], "durum": [], "hp": []})
        if akim is None:
            continue
        akim["satir"] += 1
        on_ek = re.match(r"\d{3}", al(s, "hesap"))
        if on_ek and on_ek.group(0) not in akim["hp"] and len(akim["hp"]) < 12:
            akim["hp"].append(on_ek.group(0))                    # fisin hesap ailesi (191, 391, 100 ...): fatura fisi ayrimi icin
        akim["tutar"] = round(akim["tutar"] + tutar(al(s, "borc")), 2)
        for ad, alan in (("evrak_no", "evrak"),):
            v = al(s, ad)
            if v and v not in akim[alan] and len(akim[alan]) < 3:
                akim[alan].append(v)
        for ad in ("bt", "odeme"):
            if not akim[ad] and al(s, ad):
                akim[ad] = al(s, ad)
        d = al(s, "durum")                      # Luca'nin satir aciklamasi: "Evrak No bos olamaz." gibi
        if d and d not in akim["durum"] and len(akim["durum"]) < 3:
            akim["durum"].append(d)
    return fisler


FATURA_HESAPLARI = ("191", "391")       # alis / satis KDV hesaplari: bu fisler fatura (FT) olur, programin dokunmayacagi fisler


def fatura_fisi_mi(f):
    """True: fisin hesaplarinda 191/391 var (fatura fisi: belge turu FT, elle kontrol edilir); False: yok (MF + evrak no atanabilir);
    None: hesap bilgisi okunamadi."""
    hp = f.get("hp")
    if not hp:
        return None
    return any(h in FATURA_HESAPLARI for h in hp)


def _imza(r):
    """Liste sayfasinin kimligi: sayfa numarasi + ilk satirlar (sonraki'ne basinca degismezse son sayfadayizdir)."""
    return (r.get("sayfa"), tuple(tuple(s[:5]) for s in r["satirlar"][:3]))


def liste_oku(ana, liste, log=None, sayfa_siniri=SAYFA_SINIRI, capa=CAPA_BELGE, grupla=None):
    """Acilan e-Defter uyumsuz fis listesini tum sayfalariyla okur: {fis_sayisi, satir_sayisi, fisler, kesildi, sayfa}."""
    pg, fr = liste
    fisler, satir_sayisi, kesildi, sayfa_sayisi = {}, 0, False, 0
    for sayfa_sayisi in range(1, sayfa_siniri + 1):
        r = fr.evaluate(LISTE_OKU_JS, capa)
        if not r or not r["satirlar"]:
            sayfa_sayisi -= 1          # bos sayfa: sayilmaz
            break
        satir_sayisi += len(r["satirlar"])
        (grupla or fisleri_grupla)(r["basliklar"], r["satirlar"], fisler)
        try:
            tiklandi = fr.evaluate(SONRAKI_JS)
        except Exception:
            tiklandi = "hata"
        if tiklandi != "tiklandi":
            break
        imza = _imza(r)

        def degisti():
            x = fr.evaluate(LISTE_OKU_JS, capa)
            return bool(x) and _imza(x) != imza
        if not kosulu_bekle(ana, degisti, 8000, aralik_ms=300):
            break                   # sonraki'ne basildi ama sayfa degismedi: son sayfa
    else:
        kesildi = True
    yaz(f"      {len(fisler)} fiş, {satir_sayisi} satır, {sayfa_sayisi} sayfa okundu" + (" (sayfa sınırı: kalanı okunmadı)" if kesildi else ""), log)
    liste_fis = list(fisler.values())
    for f in liste_fis:
        f["fatura_fisi"] = fatura_fisi_mi(f)
    fatura = sum(1 for f in liste_fis if f["fatura_fisi"] is True)
    diger = sum(1 for f in liste_fis if f["fatura_fisi"] is False)
    if fatura or diger:
        yaz(f"      {fatura} fatura fişi (191/391 var: elle), {diger} diğer fiş (MF + evrak no atanabilir)", log)
    return {"fis_sayisi": len(liste_fis), "satir_sayisi": satir_sayisi, "kesildi": kesildi,
            "fatura_fisi": fatura, "diger_fis": diger, "fisler": liste_fis[:FIS_SINIRI], "sayfa": sayfa_sayisi}


def belge_turu_tara(page, firma, bas, bit, tani_klasoru, log=None, tani_hep=False, kodlar=None):
    """Toplu Belge Turu Duzenleme ekraninda e-Defter hata kodlarini tarar: [{kod, ad, fis_sayisi, satir_sayisi, kesildi, fisler, mesaj, hata}].

    kodlar: yalniz bu hata kodlari (None: listedeki hepsi). Bir kodun taranmasi basarisiz olursa o kodun kaydina 'hata' yazilir,
    digerleri taranmaya devam eder."""
    ctx = page.context
    mesajlar = []
    adim = (lambda ek: tani_kaydet(page, tani_klasoru, log, ek, "edefter")) if tani_hep else (lambda ek: None)
    pg, fr = ekrani_ac(page, log)
    dinle(pg, mesajlar)
    adim("-1-form")
    secenekler = hata_secenekleri(fr)
    if not secenekler:
        tani_kaydet(page, tani_klasoru, log, "-hata", "edefter")
        raise LookupError("E-Defter hata listesi okunamadı (formda 'Hata Kodu' seçeneği yok)")
    istenen = [(k, m) for k, m in secenekler if not kodlar or k in kodlar]
    yaz("    E-Defter hata kodları: " + ", ".join(k for k, _ in istenen), log)
    sonuc = []
    sayfa_yazildi = False
    for kod, metin in istenen:
        ad = re.sub(r"\s*\(?\s*Hata\s*Kodu.*$", "", metin, flags=re.I).strip(" .(")
        kayit = {"kod": kod, "ad": ad, "fis_sayisi": 0, "satir_sayisi": 0, "kesildi": False, "fisler": [], "mesaj": "", "hata": ""}
        try:
            r = form_bul(ctx)
            if r is None:                       # liste formla ayni pencerede acilmis olabilir: form yeniden acilir
                pg, fr = ekrani_ac(page, log)
                dinle(pg, mesajlar)
            else:
                pg, fr = r
            form = formu_doldur(fr, bas, bit, kod)
            if not sayfa_yazildi:
                yaz(f"    Onay kutuları: {form['kutular']}", log)
            if not sayfa_yazildi and form.get("sayfa"):
                sayfa_yazildi = True
                yaz(f"    Sayfa No/Kayıt Sayısı listeleri: {form['sayfa']['listeler']}; seçili: {form['sayfa']['secili']}", log)
            mesajlar.clear()
            _listele_dugmesi(pg).click(timeout=10000)
            son = _bekle_liste(ctx, page, mesajlar)
            if "liste" in son:
                dinle(son["liste"][0], mesajlar)
                adim(f"-{kod}-liste")
                kayit.update(liste_oku(page, son["liste"], log))
                if son["liste"][0] is not pg:
                    try:
                        son["liste"][0].close()
                    except Exception:
                        pass
            elif son.get("mesaj"):
                if KAYIT_YOK.search(son["mesaj"]):
                    kayit["mesaj"] = son["mesaj"][:160]            # kayit yok = sorun yok
                else:
                    raise LookupError(f"Luca mesajı: {son['mesaj'][:160]}")
            else:
                tani_kaydet(page, tani_klasoru, log, f"-{kod}-bos", "edefter")
                raise LookupError("Listele'den sonra ne liste ne mesaj geldi (liste ekranı açılmadı)")
            yaz(f"    {kod}: {kayit['fis_sayisi']} fiş" + (f"  ({kayit['mesaj']})" if kayit["mesaj"] else ""), log)
        except Exception as e:
            if page.is_closed():
                raise
            kayit["hata"] = (str(e) if isinstance(e, LookupError) else f"{type(e).__name__}: {e}")[:300]
            yaz(f"    {kod}: HATA {kayit['hata']}", log)
        sonuc.append(kayit)
    ek_sayfalari_kapat(ctx, page)
    return sonuc


# --- Fis Listesi ekrani: Muhasebe > Fis Islemleri > Fis Listesi (20021 / 20025 / 20026) -------------------------------------
# Ekran goruntusu: Ilk/Son Fis Tarihi (e-Defter kutusu isaretliyken gri), "E-Defter kapsaminda uyumsuz olan fisleri getir"
# onay kutusu, "E-Defter Ay" (Ocak...) ve "E-Defter Hata:" listesi. Tarihleri E-Defter Ay belirler. Sonuc ekraninin yapisi
# henuz gorulmedi: ekranda 'Fis No' baslikli bir tablo, uyari kutusu ya da sayfadaki mesaj aranir; hicbiri gelmezse HATA yazilir
# (sessizce "sorun yok" denmez) ve tani/ klasorune ekran kaydedilir.
FIS_KODLARI = ("20021", "20025", "20026")
BELGE_KODLARI = ("20041", "20042", "20043", "20044", "20045", "20046", "20047", "20048")
FIS_MENU_ADI = "Fiş Listesi"
FIS_MENU_YOLU = "Muhasebe > Fiş İşlemleri > Fiş Listesi"
FIS_LISTELE_ADLARI = ("Liste", "Listele", "Getir", "Ara", "Sorgula", "Filtrele")     # Fis Listesi'nde dugmenin adi "Liste"
FIS_BEKLEME_MS = 25000
AYLAR = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")

FIS_FORM_VAR_JS = r"""() => {
  const t = (document.body && document.body.innerText) || '';
  // onay kutusu isaretsizken "E-Defter Ay / Hata" satirlari gizlidir: hep gorunen etiketlerle taninir (Belge Turu formunda "Detayli Arama" yok)
  return /E-?\s*Defter\s*kapsam[ıi]nda/i.test(t) && /Detayl[ıi]\s*Arama/i.test(t) && /Fiş\s*A[çc][ıi]klama/i.test(t);
}"""

# Luca'nin bazi sayfalari Array.prototype.find/filter/some'u bozar: yalniz dongu kullanilir
FIS_FORM_JS = r"""arg => {
  const g = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  const duz = t => (t || '').toLocaleLowerCase('tr').replace(/[\s.\-()*:]/g, '');
  const yaprak = [], hepsi = document.querySelectorAll('th, td, label, span, div, b');
  for (let i = 0; i < hepsi.length; i++) if (!hepsi[i].children.length && g(hepsi[i])) yaprak.push(hepsi[i]);
  const etiket = desen => { for (let i = 0; i < yaprak.length; i++) if (desen.test((yaprak[i].textContent || '').trim())) return yaprak[i]; return null; };
  const ILK = 'input:not([type=checkbox]):not([type=hidden]):not([type=image]):not([type=button]), select';
  const yanKutu = desen => {
    const e = etiket(desen);
    if (!e) return null;
    const hucre = e.closest('td, th') || e;
    for (let n = hucre.nextElementSibling; n; n = n.nextElementSibling) {
      const k = (n.matches && n.matches(ILK)) ? n : (n.querySelector ? n.querySelector(ILK) : null);
      if (k && g(k)) return k;
    }
    return null;
  };
  const sonuc = {ay: null, kutu: null, secenekler: [], secili: -1, tarihler: []};
  // onay kutusu: etiketle ayni hucrede / label icinde / yan hucrede
  const h = duz(arg.acik), adaylar = document.querySelectorAll('th, td, label, span, div, b');
  let cb = null;
  for (let i = adaylar.length - 1; i >= 0 && !cb; i--) {
    const e = adaylar[i];
    if (!g(e) || duz(e.textContent) !== h) continue;
    cb = e.querySelector('input[type=checkbox]');
    if (!cb && e.tagName === 'LABEL' && e.htmlFor) cb = document.getElementById(e.htmlFor);
    const r = e.closest('tr');
    if (!cb && r) cb = r.querySelector('input[type=checkbox]');
    const kardes = x => x && (x.type === 'checkbox' ? x : (x.querySelector ? x.querySelector('input[type=checkbox]') : null));
    if (!cb) cb = kardes(e.previousElementSibling) || kardes(e.nextElementSibling);
  }
  if (!cb) {
    const kutular = document.querySelectorAll('input[type=checkbox]');
    for (let i = 0; i < kutular.length && !cb; i++) {
      const k = kutular[i];
      if (!g(k)) continue;
      let t = '';
      if (k.id) { const l = document.querySelector('label[for="' + k.id + '"]'); if (l) t = l.textContent || ''; }
      if (!t && k.closest('label')) t = k.closest('label').textContent || '';
      if (!t) for (let n = k.nextSibling; n; n = n.nextSibling) {
        if (n.nodeType === 1 && (n.tagName === 'INPUT' || n.tagName === 'BR' || n.tagName === 'SELECT' || n.tagName === 'TABLE')) break;
        t += n.textContent || '';
      }
      if (duz(t) === h) cb = k;
    }
  }
  if (cb) {
    if (!cb.disabled && !cb.checked) {
      cb.click();
      if (!cb.checked) { cb.checked = true; cb.dispatchEvent(new Event('change', {bubbles: true})); }
    }
    sonuc.kutu = cb.checked;
  }
  // E-Defter Ay ve Hata satirlari kutu isaretlenince acilir: kutudan SONRA aranir
  const ay = yanKutu(/^E-?\s*Defter\s*Ay\s*:?$/i);
  if (ay && ay.tagName === 'SELECT') {
    for (let i = 0; i < ay.options.length; i++) if (duz(ay.options[i].text) === duz(arg.ay)) { ay.selectedIndex = i; break; }
    ay.dispatchEvent(new Event('change', {bubbles: true}));
    sonuc.ay = ay.options[ay.selectedIndex] ? ay.options[ay.selectedIndex].text.trim() : '';
  }
  const hata = yanKutu(/^E-?\s*Defter\s*hata\s*:?$/i);
  if (hata && hata.tagName === 'SELECT') {
    for (let i = 0; i < hata.options.length; i++) sonuc.secenekler.push((hata.options[i].text || '').replace(/\s+/g, ' ').trim());
    if (arg.kod) {
      const d = new RegExp('Hata\\s*Kodu\\s*:?\\s*' + arg.kod + '\\b', 'i');
      for (let i = 0; i < hata.options.length; i++) if (d.test(hata.options[i].text)) { hata.selectedIndex = i; hata.dispatchEvent(new Event('change', {bubbles: true})); break; }
    }
    sonuc.secili = hata.selectedIndex;
  }
  for (const desen of [/^İlk\s*Fiş\s*Tarihi/i, /^Son\s*Fiş\s*Tarihi/i]) { const k = yanKutu(desen); sonuc.tarihler.push(k ? k.value : null); }
  return sonuc;
}"""


# Fis Listesi'nde Listele dugmesi bir <button> olmayabilir (resim / tiklanabilir kutu / baslik-ipucu): genis arama
FIS_DUGME_JS = r"""adlar => {
  const g = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  const duz = t => (t || '').toLocaleLowerCase('tr').replace(/[\s.\-()*:]/g, '');
  const aranan = adlar.map(duz), adaylar = [], hepsi = document.querySelectorAll('button, input, a, img, span, div, td, li, i');
  let bulunan = null;
  for (let i = 0; i < hepsi.length; i++) {
    const e = hepsi[i];
    if (!g(e) || (e.tagName === 'INPUT' && /^(checkbox|text|hidden|radio|password)$/i.test(e.type || ''))) continue;
    const t = (e.value || e.title || e.alt || e.getAttribute('aria-label') || (e.children.length > 3 ? '' : e.textContent) || '').replace(/\s+/g, ' ').trim();
    if (!t || t.length > 40) continue;
    const tiklanir = /^(BUTTON|A|IMG)$/.test(e.tagName) || (e.tagName === 'INPUT') || e.hasAttribute('onclick') || e.getAttribute('role') === 'button'
                     || getComputedStyle(e).cursor === 'pointer';
    if (!tiklanir) continue;
    if (adaylar.length < 40) adaylar.push(e.tagName + ':' + t + (e.id ? '#' + e.id : ''));
    if (!bulunan && aranan.indexOf(duz(t)) >= 0) bulunan = e;
  }
  if (bulunan) { bulunan.click(); return {tiklandi: bulunan.tagName + ':' + (bulunan.value || bulunan.title || bulunan.alt || bulunan.textContent || '').trim().slice(0, 30), adaylar}; }
  return {tiklandi: null, adaylar};
}"""


def fis_listele_tikla(page, tani_klasoru, kod, log=None):
    """Fis Listesi'nde Listele'ye (ya da esdegerine) basar; bulunamazsa tiklanabilir ogelerin listesiyle LookupError."""
    adaylar = []
    for fr in list(page.frames):
        try:
            r = fr.evaluate(FIS_DUGME_JS, list(FIS_LISTELE_ADLARI))
        except Exception:
            continue
        if r.get("tiklandi"):
            yaz(f"    Fiş Listesi: '{r['tiklandi']}' tıklandı", log)
            return
        adaylar += r.get("adaylar") or []
    tani_kaydet(page, tani_klasoru, log, f"-{kod}-dugme", "edefter-fis")
    raise LookupError("Fiş Listesi formunda 'Listele' / 'Getir' / 'Ara' / 'Sorgula' düğmesi bulunamadı. Tıklanabilir öğeler: "
                      + ", ".join(adaylar[:25]))


def _fis_form_oku(fr, arg, deneme=8):
    """Fis Listesi formunu doldurur; onay kutusu isaretlenince acilan Ay / Hata satirlari gorunene kadar (gecikmeli olabilir) yeniden dener."""
    r = _degerlendir(fr, FIS_FORM_JS, arg)
    for _ in range(deneme):
        if r.get("ay") is not None and r.get("secenekler"):
            break
        fr.page.wait_for_timeout(500)
        r = _degerlendir(fr, FIS_FORM_JS, arg)
    return r


def fis_form_bul(ctx):
    return _bul(ctx, FIS_FORM_VAR_JS)


def fis_listesini_ac(page, log=None):
    """Fis Listesi ekranini acar (ana pencerenin icerik cercevesinde): (pencere, cerceve)."""
    ctx = page.context
    ek_sayfalari_kapat(ctx, page)
    acik_pencereleri_kapat(page)
    denenen = []
    from .luca_muavin import menu_baglantilari
    for etiket, baglanti in menu_baglantilari(page, FIS_MENU_ADI):
        if not _baglantiyi_ac(page, baglanti):
            continue
        if kosulu_bekle(page, lambda: fis_form_bul(ctx) is not None, 45000, aralik_ms=500):
            yaz(f"    Fiş Listesi açıldı (menü verisi: {baglanti})", log)
            return fis_form_bul(ctx)
        denenen.append(f"{baglanti}: form açılmadı")
    try:
        menu_yolunu_ac(page, FIS_MENU_YOLU, lambda: fis_form_bul(ctx) is not None)
        yaz("    Fiş Listesi açıldı (ekran menüsü)", log)
        return fis_form_bul(ctx)
    except LookupError as e:
        denenen.append(f"ekran menüsü: {e}")
    raise LookupError("Fiş Listesi ekranı açılamadı. Denenen: " + "; ".join(denenen)[:600])


def fis_satirlarini_grupla(basliklar, satirlar, fisler=None):
    """Fis Listesi tablosu (bir satir = bir fis): Fis No / Fis Tarihi / Aciklama sutunlarindan fis sozlukleri."""
    sade = [_sade(b) for b in basliklar]

    def ind(*adaylar, tam=False):
        for a in adaylar:
            for i, b in enumerate(sade):
                if b == a or (not tam and a in b):
                    return i
        return None
    i_no, i_tarih, i_ack = ind("FISNO", tam=True), ind("FISTARIHI", "TARIH"), ind("ACIKLAMA")
    fisler = {} if fisler is None else fisler
    al = lambda s, i: (s[i] if i is not None and i < len(s) else "").strip()
    for s in satirlar:
        no = al(s, i_no)
        if not no:
            continue
        tarih = al(s, i_tarih)
        fisler.setdefault((no, tarih), {"fis_no": no, "tarih": tarih, "degismeyen": "", "satir": 1, "evrak": [], "bt": "", "odeme": "",
                                        "tutar": 0.0, "hesap": "", "aciklama": al(s, i_ack)[:90], "durum": []})
    return fisler


def _adet(mesaj):
    """'3 adet dengesiz veya pasif fisiniz var.' -> 3 (sayi yoksa None)."""
    m = re.search(r"(\d+)\s*adet", mesaj or "", re.I)
    return int(m.group(1)) if m else None


def fis_listesi_tara(page, firma, bas, bit, tani_klasoru, log=None, kodlar=None):
    """Fis Listesi'nde e-Defter hata kodlarini (20021, 20025, 20026) tarar; belge_turu_tara ile ayni kayit bicimi.

    E-Defter Ay secimi donemin her ayi icin yapilir (e-Defter aylik). Sonuc ekraninda 'Fis No' tablosu varsa fisler okunur;
    'N adet ... fisiniz var' uyarisi gelirse sayi alinir; 'kayit yok' ise 0; hicbiri gelmezse kodun kaydina hata yazilir."""
    ctx = page.context
    mesajlar = []
    istenen = [k for k in FIS_KODLARI if not kodlar or k in kodlar]
    aylar, y, m = [], bas.year, bas.month
    while (y, m) <= (bit.year, bit.month):
        aylar.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    pg, fr = fis_listesini_ac(page, log)
    dinle(pg, mesajlar)
    secenekler = {}
    for kod in istenen:
        secenekler[kod] = None
    r0 = _fis_form_oku(fr, {"ay": AYLAR[bas.month - 1], "kod": "", "acik": ACIK_KUTU})
    for metin in r0.get("secenekler") or []:
        m = HATA_KODU.search(metin)
        if m and m.group(1) in secenekler:
            secenekler[m.group(1)] = metin
    yaz(f"    Fiş Listesi: E-Defter Ay={r0.get('ay')}, onay kutusu={r0.get('kutu')}, tarihler={r0.get('tarihler')}; "
        f"hata kodları: {[k for k, v in secenekler.items() if v]}", log)
    sonuc = []
    for kod in istenen:
        metin = secenekler.get(kod)
        ad = re.sub(r"\s*\(?\s*Hata\s*Kodu.*$", "", metin or "", flags=re.I).strip(" .(")
        kayit = {"kod": kod, "ad": ad, "fis_sayisi": 0, "satir_sayisi": 0, "kesildi": False, "fisler": [], "mesaj": "", "hata": ""}
        sonuc.append(kayit)
        if not metin:
            kayit["mesaj"] = "Bu kod Fiş Listesi'ndeki E-Defter hata listesinde yok (bu Luca sürümünde yok sayıldı)"
            yaz(f"    {kod}: listede yok", log)
            continue
        fislerim = {}
        try:
            for (yil, ay) in aylar:
                r = fis_form_bul(ctx)
                if r is None:
                    pg, fr = fis_listesini_ac(page, log)
                    dinle(pg, mesajlar)
                else:
                    pg, fr = r
                form = _fis_form_oku(fr, {"ay": AYLAR[ay - 1], "kod": kod, "acik": ACIK_KUTU})
                if form.get("kutu") is not True:
                    tani_kaydet(page, tani_klasoru, log, f"-{kod}-kutu", "edefter-fis")
                    raise LookupError("'E-Defter kapsamında uyumsuz olan fişleri getir' kutusu "
                                      + ("bulunamadı" if form.get("kutu") is None else "işaretlenemedi"))
                if _sade(form.get("ay") or "") != _sade(AYLAR[ay - 1]):
                    raise LookupError(f"E-Defter Ay seçilemedi (seçili: {form.get('ay')!r}, beklenen: {AYLAR[ay - 1]})")
                secili = form["secenekler"][form["secili"]] if 0 <= form.get("secili", -1) < len(form["secenekler"]) else ""
                if f"Hata Kodu: {kod}" not in secili.replace("  ", " ") and not re.search(rf"Hata\s*Kodu\s*:?\s*{kod}\b", secili):
                    raise LookupError(f"E-Defter Hata listesinde {kod} seçilemedi (seçili: {secili[:80]!r})")
                mesajlar.clear()
                onceki = liste_bul(ctx, CAPA_FIS)          # onceki kodun sonuc tablosu ekranda kalmis olabilir
                onceki_imza = _grid_imza(onceki) if onceki else None
                fis_listele_tikla(pg, tani_klasoru, kod, log)
                son = {}

                def hazir():
                    if mesajlar:                              # uyari kutusu (orn. "Kayit bulunamadi")
                        son["mesaj"] = mesajlar[-1]
                        return True
                    for p2 in acik_sayfalar(ctx):
                        for f2 in p2.frames:
                            mm = f2.evaluate(BOS_MESAJ_JS)
                            if mm and not onceki:
                                son["mesaj"] = mm
                                return True
                    g = liste_bul(ctx, CAPA_FIS)
                    if g and (onceki_imza is None or _grid_imza(g) != onceki_imza):   # eski tablo degil, yenilenen tablo
                        son["grid"] = g
                        return True
                    return False
                kosulu_bekle(page, hazir, FIS_BEKLEME_MS, aralik_ms=400, en_az_ms=700 if onceki else 0)
                if not son and onceki:                        # tablo yenilendi ama icerigi ayni (iki kodda ayni fisler): eski tabloyu kabul et
                    g = liste_bul(ctx, CAPA_FIS)
                    if g:
                        son["grid"] = g
                if "grid" in son:
                    okunan = liste_oku(page, son["grid"], log, capa=CAPA_FIS, grupla=fis_satirlarini_grupla)
                    for f in okunan["fisler"]:
                        fislerim.setdefault((f["fis_no"], f["tarih"]), f)
                    kayit["satir_sayisi"] += okunan["satir_sayisi"]
                    kayit["kesildi"] = kayit["kesildi"] or okunan["kesildi"]
                elif son.get("mesaj"):
                    if KAYIT_YOK.search(son["mesaj"]):
                        kayit["mesaj"] = son["mesaj"][:160]
                    elif _adet(son["mesaj"]) is not None and re.search(r"fi[sş]", son["mesaj"], re.I):
                        kayit["fis_sayisi"] += _adet(son["mesaj"])
                        kayit["mesaj"] = son["mesaj"][:160]
                    else:
                        tani_kaydet(page, tani_klasoru, log, f"-{kod}-mesaj", "edefter-fis")
                        raise LookupError(f"Luca mesajı anlaşılamadı: {son['mesaj'][:160]}")
                else:
                    tani_kaydet(page, tani_klasoru, log, f"-{kod}-bos", "edefter-fis")
                    raise LookupError("Listele'den sonra tablo ya da mesaj gelmedi (Fiş Listesi sonucu okunamadı)")
            if fislerim:
                kayit["fisler"] = list(fislerim.values())[:FIS_SINIRI]
                kayit["fis_sayisi"] += len(fislerim)
            yaz(f"    {kod}: {kayit['fis_sayisi']} fiş" + (f"  ({kayit['mesaj']})" if kayit["mesaj"] else ""), log)
        except Exception as e:
            if page.is_closed():
                raise
            kayit["hata"] = (str(e) if isinstance(e, LookupError) else f"{type(e).__name__}: {e}")[:300]
            yaz(f"    {kod}: HATA {kayit['hata']}", log)
    ek_sayfalari_kapat(ctx, page)
    return sonuc


def _grid_imza(grid):
    try:
        r = grid[1].evaluate(LISTE_OKU_JS, CAPA_FIS)
    except Exception:
        return None
    return _imza(r) if r else None


def _listele_dugmesi_adlari(pg):
    return luca_mizan._rapor_dugmesi(pg, FIS_LISTELE_ADLARI, "Fiş Listesi")


def edefter_tara(page, firma, bas, bit, tani_klasoru, log=None, tani_hep=False, kodlar=None):
    """Acik firmanin e-Defter hata kodlarini iki ekrandan tarar (Belge Turu Duzenleme + Fis Listesi); kayit listesi.

    kodlar: yalniz bu hata kodlari (None: hepsi). Bir ekran acilamazsa o ekranin kodlari 'hata' ile isaretlenir, digeri taranir."""
    sonuc = []
    belge_gerekli = not kodlar or any(k not in FIS_KODLARI for k in kodlar)
    fis_gerekli = not kodlar or any(k in FIS_KODLARI for k in kodlar)
    if belge_gerekli:
        sonuc += belge_turu_tara(page, firma, bas, bit, tani_klasoru, log, tani_hep,
                                 {k for k in kodlar if k not in FIS_KODLARI} if kodlar else None)
    if fis_gerekli:
        try:
            sonuc += fis_listesi_tara(page, firma, bas, bit, tani_klasoru, log, kodlar)
        except LookupError as e:
            yaz(f"    Fiş Listesi taranamadı: {e}", log)
            sonuc += [{"kod": k, "ad": "", "fis_sayisi": 0, "satir_sayisi": 0, "kesildi": False, "fisler": [], "mesaj": "",
                       "hata": str(e)[:300]} for k in FIS_KODLARI if not kodlar or k in kodlar]
    return sonuc
