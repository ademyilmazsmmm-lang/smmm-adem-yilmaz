# -*- coding: utf-8 -*-
"""Luca'dan Muavin Defter dokumunu (Excel) indirir: 191 Indirilecek KDV ve 391 Hesaplanan KDV.

Yol: Muhasebe > Raporlar > Genel Raporlar > Defterler > Tum Yazicilar > Muavin Defter (menu verisinde 'Muavin Defter').
Gercek form (ekran goruntusunden): Baslangic/Bitis Fis Tarihi, Baslangic/Bitis Hesap Kodu, Rapor Turu = "Excel Liste (xlsx)", altta Rapor dugmesi.
Mizan ile ayni mekanik: menuItems/aktar() ile acilir, form etikete gore doldurulur, 'Rapor' Excel indirir
(karzarar.luca_mizan.indir). Muavin formunun alanlari Mizan kadar iyi bilinmedigi icin:

  * alanlar birkac etiket adayiyla denenir (Baslangic/Bitis Fis Tarihi | Tarih Ilk/Son ...);
  * form bulunamayan/doldurulamayan alanlarla ilgili ayrinti gunluge yazilir (FORM ALANLARI: ...);
  * hesap kodu alanlari BOS birakilir: dokum TUM hesaplari icerir (fatura toplami karsi hesap satirlarindan - 320/120/102 -
    okunur); satirlari hesaba gore muavin_karsilastir.muavin_satirlari bolum satirlarindan okur.

Ilk gercek denemede neyin tutmadigi gunlukten ve tani/ klasorunden anlasilsin diye her adim kaydedilir.
"""

from lucabot.bekleme import kosulu_bekle
from lucabot.luca_ekran import acik_pencereleri_kapat
from lucabot.luca_gezinme import menu_yolunu_ac
from lucabot.musteri_listesi import tani_kaydet
from lucabot.ortak import dosya_adi_yap, yaz

from . import luca_mizan
from .luca_hesap_plani import SON_MENU_TANISI, _yuklenmeyi_bekle
from .muavin_karsilastir import muavin_satirlari

MENU_ETIKETI = "||||Muavin Defter"
MENU_ADI = "Muavin Defter"
MENU_YOLU = "Muhasebe > Raporlar > Genel Raporlar > Defterler > Tüm Yazıcılar > Muavin Defter"
RAPOR_TURU_ADAYLARI = ("Excel Liste (xlsx)", "Excel (xlsx)", "Excel", "xlsx")
DUGME_ADAYLARI = ("Rapor", "Raporu Al", "Excel", "Listele")

# (kimlik, etiket) adaylari; ilk bulunan doldurulur. Tarihler zorunludur, hesap alanlari degil.
# Gercek formda tarih kutularinin etiketi kutunun yaninda degil: kimlikle bulunur (p_fis_tarihi_ilk_1 / p_fis_tarihi_son_1).
TARIH_ALANLARI = (("p_fis_tarihi_ilk_1", "Başlangıç Fiş Tarihi"), ("tarih_ilk", "Başlangıç Fiş Tarihi"),
                  ("p_fis_tarihi_son_1", "Bitiş Fiş Tarihi"), ("tarih_son", "Bitiş Fiş Tarihi"))
TARIH_YEDEK_ALANLARI = (("tarih_ilk", "Tarih İlk"), ("tarih_son", "Tarih Son"),
                        ("tarih_ilk", "Başlangıç Tarihi"), ("tarih_son", "Bitiş Tarihi"),
                        ("tarih1", "Başlangıç Tarihi"), ("tarih2", "Bitiş Tarihi"))
# Gorunen etiket + yanindaki kontrol listesi (tani): Luca'nin Muavin formunu ilk kez gormek icin
FORM_TANI_JS = r"""() => {
  const gor = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  const cikti = [];
  const kutular = document.querySelectorAll('select, input:not([type=hidden]):not([type=checkbox]):not([type=button]), textarea');
  for (let i = 0; i < kutular.length && cikti.length < 40; i++) {
    const k = kutular[i];
    if (!gor(k)) continue;
    const hucre = k.closest('td, th, div');
    let etiket = '';
    const onceki = hucre && hucre.previousElementSibling;
    if (onceki) etiket = (onceki.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40);
    let secenek = '';
    if (k.tagName === 'SELECT') {
      const ops = [];
      for (let j = 0; j < k.options.length && j < 5; j++) ops.push(k.options[j].text.trim().slice(0, 24));
      secenek = ' [' + ops.join(' | ') + (k.options.length > 5 ? ' ...' : '') + ']';
    }
    cikti.push((etiket || '?') + ' = ' + (k.id || k.name || k.tagName) + secenek);
  }
  return cikti.join(' ; ');
}"""


MUAVIN_FORM = r"(Başlangıç|Bitiş)\s*(Fiş\s*)?(Tarihi|Hesap)|Tarih\s*(İlk|Son)"   # formu taniyan gorunen etiketler


def _form_hazir(page, desen=MUAVIN_FORM):
    for fr in page.frames:
        try:
            if fr.evaluate(r"""desen => {
                const g = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
                const d = new RegExp('^(?:' + desen + ')', 'i');
                const l = document.querySelectorAll('th, td, label, span, div, b');
                for (let i = 0; i < l.length; i++)
                  if (!l[i].children.length && g(l[i]) && d.test((l[i].textContent || '').trim())) return true;
                return false;
            }""", desen):
                return True
        except Exception:
            continue
    return False


# Luca menusunde "Muavin Defter" IKI kez gecer: Nokta Vurusulu Yazicilar (Rapor Turu: IBM/EPSON, Excel YOK) ve Tum Yazicilar
# (Rapor Turu: Excel Liste (xlsx)). Excel yalniz ikincisinde var: ayni adli tum menu baglantilari sirayla acilip Rapor Turu'nde
# Excel secenegi olan form kullanilir.
MENU_BAGLANTILARI_JS = r"""ad => {
  if (typeof menuItems === 'undefined' || typeof aktar !== 'function') return null;
  const ta = document.createElement('textarea');
  const temiz = t => { ta.innerHTML = (t || '').replace(/<[^>]*>/g, ''); return ta.value.replace(/^\|+/, '').trim().toLocaleLowerCase('tr'); };
  const h = ad.toLocaleLowerCase('tr'), cikti = [];
  for (let i = 0; i < menuItems.length; i++) {
    const x = menuItems[i];
    if (x && x[1] && temiz(x[0]) === h) cikti.push([x[0], x[1]]);
  }
  return cikti;
}"""
ESKI_ISARETLE_JS = "() => { window.__lbEski = true; return true; }"   # icerik cercevesi aktar() ile degisince isaret kaybolur
MENU_AC_JS = r"""l => { if (typeof aktar !== 'function') return false;
  try { aktar(l); return true; } catch (e) { return false; } }"""
YENI_FORM_VE_EXCEL_JS = r"""desen => {
  if (window.__lbEski) return null;                       // eski (degismemis) sayfa
  const g = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  const d = new RegExp('^(?:' + desen + ')', 'i');
  const l = document.querySelectorAll('th, td, label, span, div, b');
  let form = false;
  for (let i = 0; i < l.length && !form; i++) if (!l[i].children.length && g(l[i]) && d.test((l[i].textContent || '').trim())) form = true;
  if (!form) return null;
  const secimler = document.querySelectorAll('select');
  for (let i = 0; i < secimler.length; i++) {
    const s = secimler[i];
    if (!g(s)) continue;
    const ops = Array.from(s.options).map(o => (o.text || '').trim());
    if (ops.some(t => /xlsx|excel/i.test(t))) return {excel: true, secenekler: ops};
  }
  const tum = Array.from(document.querySelectorAll('select')).filter(g).map(s => Array.from(s.options).map(o => (o.text || '').trim()).slice(0, 4).join('/'));
  return {excel: false, secenekler: tum};
}"""


def menu_baglantilari(page, ad=MENU_ADI):
    """Menu verisindeki ayni adli tum girisler: [(etiket, baglanti)] (menu cercevesi yoksa [])."""
    for fr in page.frames:
        try:
            m = fr.evaluate(MENU_BAGLANTILARI_JS, ad)
        except Exception:
            continue
        if m is not None:
            return [tuple(x) for x in m]
    return []


MENU_BENZER_JS = r"""anahtarlar => {
  if (typeof menuItems === 'undefined') return null;
  const ta = document.createElement('textarea');
  const temiz = t => { ta.innerHTML = (t || '').replace(/<[^>]*>/g, ''); return ta.value.replace(/^\|+/, '').trim(); };
  const cikti = [];
  for (let i = 0; i < menuItems.length && cikti.length < 12; i++) {
    const x = menuItems[i];
    if (!x || !x[1]) continue;
    const t = temiz(x[0]), k = t.toLocaleLowerCase('tr');
    if (anahtarlar.some(a => k.includes(a))) cikti.push(t + ' -> ' + x[1]);
  }
  return cikti;
}"""


def menu_benzerleri(page, anahtarlar=("döküm", "dokum", "muavin", "gelir/gider", "defter")):
    """Tani: menu verisinde bu kelimeleri iceren girisler ('Etiket -> baglanti')."""
    for fr in page.frames:
        try:
            m = fr.evaluate(MENU_BENZER_JS, list(anahtarlar))
        except Exception:
            continue
        if m is not None:
            return m
    return []


def _baglantiyi_ac(page, baglanti):
    for fr in page.frames:        # once TUM cerceveler "eski" isaretlenir: yeni acilan form isaretsiz gelir
        try:
            fr.evaluate(ESKI_ISARETLE_JS)
        except Exception:
            continue
    for fr in page.frames:
        try:
            if fr.evaluate(MENU_AC_JS, baglanti):
                return True
        except Exception:
            continue
    return False


def _yeni_form(page, desen=MUAVIN_FORM):
    """(excel_var_mi, secenekler) - yeni acilan formun Rapor Turu secenekleri; form henuz yuklenmediyse None."""
    for fr in page.frames:
        try:
            r = fr.evaluate(YENI_FORM_VE_EXCEL_JS, desen)
        except Exception:
            continue
        if r:
            return r["excel"], r["secenekler"]
    return None


def ekrani_ac(page, log=None):
    """Muavin Defter formunu (Tum Yazicilar; Rapor Turu'nde Excel olan) acar."""
    acik_pencereleri_kapat(page)
    denenen = []
    for etiket, baglanti in menu_baglantilari(page):
        if not _baglantiyi_ac(page, baglanti):
            continue
        sonuc = {}
        if not kosulu_bekle(page, lambda: sonuc.update(r=_yeni_form(page)) or sonuc["r"] is not None, 120000, aralik_ms=500):
            denenen.append(f"{baglanti}: form açılmadı")
            continue
        excel, secenekler = sonuc["r"]
        _yuklenmeyi_bekle(page)
        if excel:
            yaz(f"    Muavin Defter açıldı (Excel seçenekli form: {baglanti})", log)
            return
        denenen.append(f"{baglanti}: Rapor Türü {secenekler}")
        yaz(f"    Bu Muavin Defter formunda Excel yok (Nokta Vuruşlu Yazıcılar olabilir): {baglanti}; diğer giriş deneniyor", log)
    # menu verisi yok / hicbiri Excel'li degil: ekran menusunden Tum Yazicilar > Muavin Defter
    try:
        menu_yolunu_ac(page, MENU_YOLU, lambda: _form_hazir(page))
        _yuklenmeyi_bekle(page)
        if _yeni_form_var_excel(page):
            return
        denenen.append("ekran menüsü: Excel seçeneği yok")
    except LookupError as e:
        denenen.append(f"ekran menüsü: {e}")
    raise LookupError("Excel seçenekli Muavin Defter formu açılamadı (Tüm Yazıcılar altındaki giriş gerekir). Denenen: "
                      + "; ".join(denenen)[:600] + (f" | menü verisi: {SON_MENU_TANISI['metin']}" if SON_MENU_TANISI["metin"] else ""))


def _yeni_form_var_excel(page):
    r = _yeni_form(page)
    if r is None:                       # __lbEski isaretli degilse (ekran menusu yolu) dogrudan bak
        for fr in page.frames:
            try:
                if fr.evaluate("""() => Array.from(document.querySelectorAll('select')).some(s => Array.from(s.options).some(o => /xlsx|excel/i.test(o.text)))"""):
                    return True
            except Exception:
                continue
        return False
    return r[0]


def form_tanisi(page):
    """Gorunen form kontrolleri (tani); cerceve basina ozet."""
    parca = []
    for fr in page.frames:
        try:
            m = fr.evaluate(FORM_TANI_JS)
        except Exception:
            continue
        if m:
            parca.append(m)
    return " || ".join(parca)[:1500]


def _doldur(page, alanlar, desen=MUAVIN_FORM):
    """alanlar: [(kimlik, etiket, deger_metni, secenek_degeri)]; alanlarin bulundugu cerceve sonucunu dondurur
    (bulunamayan alanlar None). Form yoksa LookupError."""
    hatalar = []
    bos = None
    for fr in page.frames:
        try:
            if not fr.evaluate(r"""desen => document.body && new RegExp(desen, 'i').test(document.body.innerText)""", desen):
                continue
            sonuc = fr.evaluate(luca_mizan.FORMU_DOLDUR_JS, alanlar)
        except Exception as e:
            hatalar.append(f"{type(e).__name__}")
            continue
        if any(v is not None for v in sonuc.values()):
            return sonuc            # alanlar bu cercevede dolduruldu
        bos = sonuc                 # eski/gizli bir cerceve olabilir: digerlerine de bak
    if bos is not None:
        return bos                  # form var ama bu alanlar yok (bulunamayanlar None)
    raise LookupError("Form bulunamadı" + (f" ({'; '.join(hatalar)})" if hatalar else ""))


def tarih_ve_rapor_turu(page, bas, bit, tarih_alanlari, desen, rapor_turu_adaylari=RAPOR_TURU_ADAYLARI, ad="Muavin"):
    """Tarih araligini yazar (geri okuyup dogrular) ve Excel rapor turunu secer: {etiket: deger}.
    Tarihler ya da Excel rapor turu ayarlanamazsa LookupError."""
    t_ilk, t_son = f"{bas:%d/%m/%Y}", f"{bit:%d/%m/%Y}"
    ilk_mi = lambda k, e: "ilk" in k.lower() or k.endswith("1") or "Başlangıç" in e or "İlk" in e
    alanlar = [(k, e, t_ilk if ilk_mi(k, e) else t_son, None) for k, e in tarih_alanlari]
    sonuc = _doldur(page, alanlar, desen)
    yazilan = {e: sonuc.get(e) for _, e, _, _ in alanlar if sonuc.get(e) is not None}
    beklenen = {e: d for _, e, d, _ in alanlar}
    uyusmayan = {e: v for e, v in yazilan.items() if v != beklenen[e]}   # tarih kutusu gecersiz degeri silebilir
    if not yazilan or uyusmayan:
        raise LookupError(f"{ad} tarih alanları doldurulamadı (bulunan: {yazilan or 'yok'}"
                          f"{'; yazılan değer geri okundu: ' + str(uyusmayan) if uyusmayan else ''})")
    rapor_turu = None
    for aday in rapor_turu_adaylari:
        r = _doldur(page, [("report_type", "Rapor Türü", aday, "LIST")], desen)
        deger = r.get("Rapor Türü")
        if deger is not None and not str(deger).startswith("SEÇENEK YOK"):
            rapor_turu = deger
            break
    if rapor_turu is None:
        raise LookupError(f"{ad} formunda Excel rapor türü seçilemedi (Rapor Türü alanı yok ya da seçenekte Excel yok)")
    yazilan["Rapor Türü"] = rapor_turu
    return yazilan


def formu_doldur(page, bas, bit, log=None):
    """Tarih araligini yazar ve Excel rapor turunu secer; hesap kodu alanlari BOS birakilir (tum hesaplar gelir: genel toplam
    karsi hesap satirlarindan - 320/120/102... - okunur). Tarihler ya da Rapor Turu ayarlanamazsa LookupError."""
    return tarih_ve_rapor_turu(page, bas, bit, TARIH_ALANLARI + TARIH_YEDEK_ALANLARI, MUAVIN_FORM)


def muavin_cek(page, firma, bas, bit, indirme_klasoru, tani_klasoru, log=None, tani_hep=False):
    """Acik firmanin Muavin Defter'ini (tum hesaplar) Excel olarak indirir; muavin_satirlari bicimli satir listesi."""
    adim = (lambda ek: tani_kaydet(page, tani_klasoru, log, ek, "muavin")) if tani_hep else (lambda ek: None)
    try:
        ekrani_ac(page, log)
        adim("-1-form")
        yaz(f"    Muavin formu (tanı): {form_tanisi(page)}", log)
        alanlar = formu_doldur(page, bas, bit, log)
        yaz(f"    Muavin formu: {', '.join(f'{k}={v}' for k, v in alanlar.items())}  (tüm hesaplar)", log)
        adim("-2-form-doldu")
        yol = luca_mizan.indir(page, indirme_klasoru, f"muavin_{dosya_adi_yap(firma)}.xlsx", log=log,
                               dugme_adlari=DUGME_ADAYLARI, rapor_adi="Muavin")
        satirlar = muavin_satirlari(yol)
        yaz(f"    Muavin indirildi: {yol.name} ({len(satirlar)} kayıt)", log)
        return satirlar
    except LookupError:
        tani_kaydet(page, tani_klasoru, log, "-hata", "muavin")
        raise
