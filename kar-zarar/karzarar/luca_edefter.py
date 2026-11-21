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
  for (let i = 0; i < l.length; i++)
    if (!l[i].children.length && g(l[i]) && /^E-?\s*Defter\s*hata/i.test((l[i].textContent || '').trim())) return true;
  return false;
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
  const sonuc = {tarihler: null, kutular: {}, secenekler: [], secili: -1};
  const tr = satir(/^Fiş\s*Tarihi/i);
  if (tr && arg.bas) {
    const kutular = Array.from(tr.querySelectorAll('input')).filter(k => g(k) && !/^(checkbox|button|hidden|image|radio|submit)$/i.test(k.type || ''));
    if (kutular.length >= 2) sonuc.tarihler = [yaz(kutular[0], arg.bas), yaz(kutular[1], arg.bit)];
    else if (kutular.length === 1) sonuc.tarihler = [yaz(kutular[0], arg.bas)];
  }
  const kutuAyarla = (ad, istenen) => {
    const r = satir(ad);
    const cb = r && r.querySelector('input[type=checkbox]');
    if (!cb) { sonuc.kutular[ad] = null; return; }
    if (!cb.disabled && cb.checked !== istenen) cb.click();
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
  return sonuc;
}"""

LISTE_VAR_JS = r"""() => {
  const g = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  const duz = t => (t || '').toLocaleLowerCase('tr').replace(/[\s.\-()*:\/]/g, '');
  const c = document.querySelectorAll('th, td');
  for (let i = 0; i < c.length; i++) if (g(c[i]) && !c[i].children.length && duz(c[i].textContent) === 'değişmeyenfişno') return true;
  return false;
}"""

# Listeyi okur: {basliklar, satirlar, sayfa}; baslik hucresi 'Degismeyen Fis No' olan tablo
LISTE_OKU_JS = r"""() => {
  const g = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  const duz = t => (t || '').toLocaleLowerCase('tr').replace(/[\s.\-()*:\/]/g, '');
  const sade = t => (t || '').replace(/\s+/g, ' ').trim();
  let bas = null;
  for (const c of document.querySelectorAll('th, td')) if (g(c) && !c.children.length && duz(c.textContent) === 'değişmeyenfişno') { bas = c; break; }
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


def _bul(ctx, js):
    """js'in true dondurdugu (sayfa, cerceve) ya da None; acilan pencereler de taranir."""
    for pg in acik_sayfalar(ctx):
        try:
            cerceveler = list(pg.frames)
        except Exception:
            continue
        for fr in cerceveler:
            try:
                if fr.evaluate(js):
                    return pg, fr
            except Exception:
                continue
    return None


def form_bul(ctx):
    return _bul(ctx, FORM_VAR_JS)


def liste_bul(ctx):
    return _bul(ctx, LISTE_VAR_JS)


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


def formu_doldur(fr, bas, bit, kod=""):
    """Fis tarihini yazar, onay kutularini ayarlar, kod verilirse E-Defter hata listesinden onu secer.
    {tarihler, kutular, secenekler, secili}; tarihler yazildigi gibi geri okunamazsa LookupError."""
    r = fr.evaluate(FORM_JS, {"bas": f"{bas:%d/%m/%Y}", "bit": f"{bit:%d/%m/%Y}", "kod": str(kod or ""),
                              "kapali": list(KAPALI_KUTULAR), "acik": ACIK_KUTU})
    beklenen = [f"{bas:%d/%m/%Y}", f"{bit:%d/%m/%Y}"]
    if not r.get("tarihler") or r["tarihler"] != beklenen:
        raise LookupError(f"Fiş Tarihi kutuları doldurulamadı (okunan: {r.get('tarihler')}, beklenen: {beklenen})")
    if kod:
        secili = r["secenekler"][r["secili"]] if 0 <= r.get("secili", -1) < len(r["secenekler"]) else ""
        m = HATA_KODU.search(secili)
        if not m or m.group(1) != str(kod):
            raise LookupError(f"E-Defter hata listesinde {kod} seçilemedi (seçili: {secili[:80]!r})")
    if r["kutular"].get(ACIK_KUTU) is False:
        raise LookupError("'E-Defter kapsamında uyumsuz olan fişleri getir' kutusu işaretlenemedi")
    return r


def hata_secenekleri(fr):
    """[(kod, metin)]: E-Defter hata listesindeki secenekler; kodu olmayanlar (orn. bos) alinmaz."""
    r = fr.evaluate(FORM_JS, {"bas": "", "bit": "", "kod": "", "kapali": [], "acik": "__yok__"})
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
                                               "hesap": al(s, "hesap").split(" ")[0], "aciklama": al(s, "aciklama")[:90]})
        if akim is None:
            continue
        akim["satir"] += 1
        akim["tutar"] = round(akim["tutar"] + tutar(al(s, "borc")), 2)
        for ad, alan in (("evrak_no", "evrak"),):
            v = al(s, ad)
            if v and v not in akim[alan] and len(akim[alan]) < 3:
                akim[alan].append(v)
        for ad in ("bt", "odeme"):
            if not akim[ad] and al(s, ad):
                akim[ad] = al(s, ad)
    return fisler


def _imza(r):
    """Liste sayfasinin kimligi: sayfa numarasi + ilk satirlar (sonraki'ne basinca degismezse son sayfadayizdir)."""
    return (r.get("sayfa"), tuple(tuple(s[:5]) for s in r["satirlar"][:3]))


def liste_oku(ana, liste, log=None, sayfa_siniri=SAYFA_SINIRI):
    """Acilan e-Defter uyumsuz fis listesini tum sayfalariyla okur: {fis_sayisi, satir_sayisi, fisler, kesildi, sayfa}."""
    pg, fr = liste
    fisler, satir_sayisi, kesildi, sayfa_sayisi = {}, 0, False, 0
    for sayfa_sayisi in range(1, sayfa_siniri + 1):
        r = fr.evaluate(LISTE_OKU_JS)
        if not r or not r["satirlar"]:
            sayfa_sayisi -= 1          # bos sayfa: sayilmaz
            break
        satir_sayisi += len(r["satirlar"])
        fisleri_grupla(r["basliklar"], r["satirlar"], fisler)
        try:
            tiklandi = fr.evaluate(SONRAKI_JS)
        except Exception:
            tiklandi = "hata"
        if tiklandi != "tiklandi":
            break
        imza = _imza(r)

        def degisti():
            x = fr.evaluate(LISTE_OKU_JS)
            return bool(x) and _imza(x) != imza
        if not kosulu_bekle(ana, degisti, 8000, aralik_ms=300):
            break                   # sonraki'ne basildi ama sayfa degismedi: son sayfa
    else:
        kesildi = True
    yaz(f"      {len(fisler)} fiş, {satir_sayisi} satır, {sayfa_sayisi} sayfa okundu" + (" (sayfa sınırı: kalanı okunmadı)" if kesildi else ""), log)
    liste_fis = list(fisler.values())
    return {"fis_sayisi": len(liste_fis), "satir_sayisi": satir_sayisi, "kesildi": kesildi,
            "fisler": liste_fis[:FIS_SINIRI], "sayfa": sayfa_sayisi}


def edefter_tara(page, firma, bas, bit, tani_klasoru, log=None, tani_hep=False, kodlar=None):
    """Acik firmanin e-Defter hata kodlarini tarar: [{kod, ad, fis_sayisi, satir_sayisi, kesildi, fisler, mesaj, hata}].

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
            formu_doldur(fr, bas, bit, kod)
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
        except LookupError as e:
            kayit["hata"] = str(e)[:300]
            yaz(f"    {kod}: HATA {kayit['hata']}", log)
        sonuc.append(kayit)
    ek_sayfalari_kapat(ctx, page)
    return sonuc
