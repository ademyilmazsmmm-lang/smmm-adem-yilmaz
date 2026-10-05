# -*- coding: utf-8 -*-
"""Genel muhasebe firmalarinda Luca'daki Mizan'dan (Excel indirerek) kar/zarar tahmini.

Yol: Muhasebe > Raporlar > Genel Raporlar > Mizan (menu verisinde '|||Mizan', raporMizanHazirla.do).
Form: Baslangic/Bitis Fis Tarihi, Hesap Tipi = Ana Hesap, Bakiye Goster, Bakiyesiz Hesaplari Gosterme,
Rapor Turu = Excel Liste (xlsx); 'Rapor' dugmesi dosyayi indirir (Kumulatif Rapor degil).

Indirilen Excel: ust bilgi (MIZAN, firma, Donem, Tarih Araligi), sonra 'HESAP KODU | HESAP ADI | BORC | ALACAK | BAKIYE | B/A'
satirlari (sinif, 2 haneli ve 3 haneli ana hesaplar). Hesaplama Hesap Plani ile aynidir
(luca_hesap_plani.kar_zarar): Gelir = 6'li alacak - borc, Mal alisi = 150-153 borc - alacak, Gider = 7'li borc - alacak.
"""

import re
from pathlib import Path

from lucabot.bekleme import kosulu_bekle, sayfa_durulsun
from lucabot.luca_ekran import acik_pencereleri_kapat, bul
from lucabot.musteri_listesi import tani_kaydet
from lucabot.ortak import dosya_adi_yap, sadelestir, yaz

from lucabot.luca_gezinme import menu_yolunu_ac

from .luca_hesap_plani import SON_MENU_TANISI, _yuklenmeyi_bekle, kar_zarar, menuden_dogrudan_ac

MENU_ETIKETI = "|||Mizan"
MENU_ADI, MENU_LINKI = "Mizan", "raporMizanHazirla"
MENU_YOLU = "Muhasebe > Raporlar > Genel Raporlar > Mizan"
KOD_DESENI = re.compile(r"^\d+(\.\d+)*$")
TARIH_ARALIGI = re.compile(r"(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})")

# Form alanlari (gercek Luca "yeni-rapor-paremetreleri" formu): (kutu kimligi, etiket, deger metni, secenek degeri). Once kimlikle,
# bulunamazsa etiketin yanindaki hucredeki kutuyla doldurulur. Ayni etiketler gizli "eski-rapor-paremetreleri" formunda da gecer
# (TARIH_ILK gibi buyuk harfli kimlikler): gorunur olan alinir. Hesap Tipi (onay kutulu coklu secim) varsayilan "Tümü" birakilir:
# tum hesaplar gelir, hesaplama kodlari tam eslesen satirdan (6, 7, 150-153) okudugu icin Ana Hesap sinirlamasina gerek yoktur.
def form_alanlari(bas, bit):
    return [("tarih_ilk", "Başlangıç Fiş Tarihi", f"{bas:%d/%m/%Y}", None),
            ("tarih_son", "Bitiş Fiş Tarihi", f"{bit:%d/%m/%Y}", None),
            ("bakiye_goster", "Bakiye Göster", "Bakiye Göster", "2"),
            ("bakiye_tipi", "Bakiyesiz ve Çalışmayan Hesaplar", "Bakiyesiz Hesapları Gösterme", "2"),
            # "Göster" iken Excel'e doviz sutunlari eklenir; sutunlar basliktan bulunur ama gereksiz sutun gelmesin
            ("hesap_plani_dovizi_goster", "Hesap Planı Dövizi Göster", "Gösterme", "0"),
            ("report_type", "Rapor Türü", "Excel Liste (xlsx)", "LIST")]


# DIKKAT: Luca'nin Mizan sayfasi Array.prototype'i bozuyor (find/filter/some "is not a function"); bu yuzden bu betikte
# dizi yontemleri yerine duz for dongusu kullanilir.
FORMU_DOLDUR_JS = r"""alanlar => {
  const duz = t => (t || '').toLocaleLowerCase('tr').replace(/[\s.\-()*:]/g, '');
  const gorunur = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  const KUTU = 'select, input:not([type=hidden]):not([type=checkbox]):not([type=button])';
  function bulKutu(kimlik, etiket) {
    const k = document.getElementById(kimlik);
    if (k && gorunur(k)) return k;
    const h = duz(etiket), adaylar = document.querySelectorAll('th, td, label, span, div, b');
    for (let i = 0; i < adaylar.length; i++) {
      const e = adaylar[i];
      if (!gorunur(e) || e.children.length || duz(e.textContent) !== h) continue;
      const yan = (e.closest('td, th') || e).nextElementSibling;
      if (!yan) continue;
      const kutular = yan.querySelectorAll(KUTU);
      for (let j = 0; j < kutular.length; j++) if (gorunur(kutular[j])) return kutular[j];
    }
    return null;
  }
  function secimYap(kutu, metin, deger) {
    const ops = kutu.options, d = duz(metin);
    let hedef = -1;
    for (let i = 0; i < ops.length && hedef < 0; i++) if (deger && ops[i].value === deger) hedef = i;
    for (let i = 0; i < ops.length && hedef < 0; i++) if (duz(ops[i].text) === d) hedef = i;
    for (let i = 0; i < ops.length && hedef < 0; i++) if (duz(ops[i].text).indexOf(d) === 0) hedef = i;
    for (let i = 0; i < ops.length && hedef < 0; i++) if (duz(ops[i].text).indexOf(d) >= 0) hedef = i;
    if (hedef < 0) {
      let liste = '';
      for (let i = 0; i < ops.length; i++) liste += (i ? ' | ' : '') + ops[i].text.replace(/\s+/g, ' ').trim();
      return 'SEÇENEK YOK: ' + liste;
    }
    kutu.selectedIndex = hedef;
    kutu.dispatchEvent(new Event('change', {bubbles: true}));
    return ops[kutu.selectedIndex].text.replace(/\s+/g, ' ').trim();
  }
  const sonuc = {};
  for (let i = 0; i < alanlar.length; i++) {
    const kimlik = alanlar[i][0], etiket = alanlar[i][1], metin = alanlar[i][2], deger = alanlar[i][3];
    const kutu = bulKutu(kimlik, etiket);
    if (!kutu) { sonuc[etiket] = null; continue; }
    if (kutu.tagName === 'SELECT') { sonuc[etiket] = secimYap(kutu, metin, deger); continue; }
    kutu.focus();
    kutu.value = metin;
    kutu.dispatchEvent(new Event('input', {bubbles: true}));
    kutu.dispatchEvent(new Event('change', {bubbles: true}));
    kutu.blur();
    sonuc[etiket] = kutu.value;
  }
  return sonuc;
}"""


# --- Excel'i okuma (tarayicisiz, test edilebilir) ---------------------------------------

def _sayi(h):
    if h is None or h == "":
        return 0.0
    if isinstance(h, (int, float)):
        return float(h)
    from lucabot.fatura_analiz import tutar_cozumle
    return tutar_cozumle(h)


def mizan_satirlari(yol):
    """Mizan Excel'inden ({tarih_araligi: (bas, bit) ya da None}, [{kod, ad, borc, alacak}]).

    Baslik satiri 'HESAP KODU' ile baslayan satirdir; ondan onceki 'Tarih Araligi' satiri tarih kontrolu icindir.
    """
    import warnings
    from openpyxl import load_workbook
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = load_workbook(str(yol), data_only=True)
    ws = wb.worksheets[0]
    try:  # Luca dosyalarinda boyut bilgisi eksik olabilir
        ws.reset_dimensions()
    except Exception:
        pass
    aralik, satirlar, baslik = None, [], None
    for ham in ws.iter_rows(values_only=True):
        hucre = list(ham)
        if baslik is None:
            metin = " ".join(str(h) for h in hucre if h is not None)
            if sadelestir(metin).startswith("TARIH ARALIGI"):
                m = TARIH_ARALIGI.search(metin)
                aralik = m.groups() if m else None
            if sadelestir(str(hucre[0] or "")) == "HESAP KODU":
                # sutunlar basliktan bulunur (doviz vb. fazladan sutun gelirse Borc/Alacak kaymasin)
                adlar = [sadelestir(str(h or "")) for h in hucre]
                ilk = lambda ad, varsayilan: adlar.index(ad) if ad in adlar else varsayilan
                baslik = {"ad": ilk("HESAP ADI", 1), "borc": ilk("BORC", 2), "alacak": ilk("ALACAK", 3),
                          "bakiye": adlar.index("BAKIYE") if "BAKIYE" in adlar else None}
            continue
        kod = str(hucre[0]).strip() if hucre and hucre[0] is not None else ""
        if not KOD_DESENI.match(kod):
            continue
        al = lambda i: hucre[i] if i is not None and i < len(hucre) else None
        borc, alacak = _sayi(al(baslik["borc"])), _sayi(al(baslik["alacak"]))
        satir = {"kod": kod, "ad": str(al(baslik["ad"]) or "").strip(), "borc": borc, "alacak": alacak}
        # BAKIYE esas alinir: 'B' (borc) ise borc tarafi, 'A' (alacak) ise alacak tarafi. Borc/Alacak sutunlariyla
        # tutarlilik mizan_kar_zarar'da kontrol edilir.
        if baslik["bakiye"] is not None:
            yon = str(al(baslik["bakiye"] + 1) or "").strip().upper()
            if yon in ("B", "A"):
                tutar = _sayi(al(baslik["bakiye"]))
                satir.update({"ham_borc": borc, "ham_alacak": alacak,
                              "borc": tutar if yon == "B" else 0.0, "alacak": tutar if yon == "A" else 0.0})
            elif not any(h is not None and h != "" for h in (al(baslik["bakiye"]),)):
                satir.update({"ham_borc": borc, "ham_alacak": alacak, "borc": 0.0, "alacak": 0.0})  # bakiyesiz hesap
        satirlar.append(satir)
    return aralik, satirlar


def mizan_kar_zarar(yol, bas, bit):
    """Excel'i okuyup kar/zarar sonucu dondurur; tarih araligi istenenle uyusmazsa ya da satir yoksa LookupError."""
    aralik, satirlar = mizan_satirlari(yol)
    istenen = (f"{bas:%d/%m/%Y}", f"{bit:%d/%m/%Y}")
    if aralik and tuple(aralik) != istenen:
        raise LookupError(f"Mizan farklı tarih aralığı için alınmış: {aralik[0]}-{aralik[1]} (istenen "
                          f"{istenen[0]}-{istenen[1]})")
    if not satirlar:
        raise LookupError("Mizan Excel'inde hesap satırı bulunamadı")
    # Bakiye ile Borc-Alacak farki uyusmali (tarih araligi mizani donem hareketidir); uyusmazsa sutun/sablon sorunu vardir
    uyusmayan = [s["kod"] for s in satirlar if "ham_borc" in s and len(s["kod"]) <= 3
                 and abs((s["ham_borc"] - s["ham_alacak"]) - (s["borc"] - s["alacak"])) > 0.5]
    if uyusmayan:
        raise LookupError(f"Mizan'da Bakiye ile Borç-Alacak uyuşmuyor (hesaplar: {', '.join(uyusmayan[:5])}); sütunlar okunamadı")
    sonuc = kar_zarar(satirlar)
    sonuc["ayrinti"]["hesap_satiri"] = len(satirlar)
    return sonuc


# --- ekran ve indirme ---------------------------------------------------------------------

def _form_hazir(page):
    for fr in page.frames:
        try:
            if fr.evaluate(r"""() => {
                const g = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
                if (g(document.getElementById('tarih_ilk'))) return true;
                const l = document.querySelectorAll('th, td, label, span, div, b');
                for (let i = 0; i < l.length; i++)
                  if (!l[i].children.length && g(l[i]) && /^Bitiş Fiş Tarihi\s*:?$/.test((l[i].textContent || '').trim())) return true;
                return false;
            }"""):
                return True
        except Exception:
            continue
    return False


def ekrani_ac(page):
    acik_pencereleri_kapat(page)
    if menuden_dogrudan_ac(page, MENU_ETIKETI, MENU_ADI, MENU_LINKI):
        if not kosulu_bekle(page, lambda: _form_hazir(page), 120000, aralik_ms=500):
            raise LookupError("Mizan formu açılmadı")
    else:  # menu verisinde bulunamadi: ekrandaki menuyu tiklayarak ac
        neden = SON_MENU_TANISI["metin"]
        try:
            menu_yolunu_ac(page, MENU_YOLU, lambda: _form_hazir(page))
        except LookupError as e:
            raise LookupError(f"Mizan menüsü açılamadı (menü verisi: {neden}; ekran menüsü: {e})")
    _yuklenmeyi_bekle(page)


def formu_doldur(page, bas, bit):
    alanlar = form_alanlari(bas, bit)
    etiketler = [a[1] for a in alanlar]
    hatalar = []
    for fr in page.frames:
        try:
            if not fr.evaluate(r"""() => !!document.getElementById('tarih_ilk') || document.body.innerText.includes('Bitiş Fiş Tarihi')"""):
                continue
            sonuc = fr.evaluate(FORMU_DOLDUR_JS, alanlar)
        except Exception as e:
            hatalar.append(f"{type(e).__name__}: {str(e).splitlines()[0][:100]}")
            continue
        if all(sonuc.get(e) is None for e in etiketler):
            hatalar.append("çerçevede alan bulunamadı")
            continue
        # tarihler ve Rapor Turu zorunlu; digerleri (Bakiye/Doviz secimleri) bulunamazsa sutunlar basliktan bulundugu icin sorun degil
        zorunlu = [a[1] for a in alanlar if a[0] in ("tarih_ilk", "tarih_son", "report_type")]
        eksik = {e: sonuc.get(e) for e in zorunlu if sonuc.get(e) is None or str(sonuc.get(e)).startswith("SEÇENEK YOK")}
        # yazilan degerler okunup dogrulanir (Luca tarih kutusu gecersiz degeri silebilir)
        beklenen = {a[1]: a[2] for a in alanlar[:2]}   # ilk iki alan tarih
        for e, d in beklenen.items():
            if sonuc.get(e) != d:
                eksik[e] = f"yazılan değer geri okundu: {sonuc.get(e)!r}"
        if eksik:
            raise LookupError(f"Mizan formundaki alanlar doldurulamadı: {eksik}")
        return sonuc
    raise LookupError("Mizan formu bulunamadı" + (f" ({'; '.join(hatalar)})" if hatalar else ""))


def _rapor_dugmesi(page):
    for kurucu in (lambda f: f.get_by_role("button", name="Rapor", exact=True),
                   lambda f: f.get_by_text("Rapor", exact=True)):
        try:
            return bul(page, kurucu, sure=8000)[1]
        except LookupError:
            continue
    raise LookupError("Mizan formunda 'Rapor' düğmesi bulunamadı")


# Luca raporu yeni pencerede acip pencereyi kisa sure sonra kendisi kapatabilir (gercek kullanimda tum Chrome
# kapandi: "Download.save_as: Target page, context or browser has been closed"). Playwright, indirmeyi baslatan
# sayfa kapaninca henuz bitmemis indirmeyi iptal eder. Bu yuzden indirme surerken HIC BIR pencere (acan pencere
# olsun olmasin) kendini window.close() ile kapatamaz; cagrilar console'a "LB_CLOSE" yazilir (tani) ve indirme
# bitince pencereleri biz kapatiriz. Sayfa zaten yuklu oldugu icin hem init script hem canli cerçevelere uygulanir.
POPUP_KAPANMASINI_ENGELLE_JS = (
    "try { if (!window.__lbClose) { window.__lbClose = window.close; }"
    " window.close = function () { console.log('LB_CLOSE ' + (window === window.top ? 'top' : 'frame') + ' '"
    " + String(location.href).slice(0, 80)); }; } catch (e) {}")
POPUP_KAPANMASINI_GERI_AL_JS = "try { if (window.__lbClose) { window.close = window.__lbClose; } } catch (e) {}"


def _her_cerceveye(ctx, js):
    """Acik tum sayfa ve cerçevelerde js calistirir (hatalar yutulur)."""
    for p in list(ctx.pages):
        try:
            for fr in p.frames:
                try:
                    fr.evaluate("() => { " + js + " }")
                except Exception:
                    pass
        except Exception:
            pass


def indir(page, klasor, ad, sure_ms=120000, log=None):
    """'Rapor' dugmesine basip inen dosyayi klasor/ad olarak kaydeder (pencere/sekme acilsa da yakalanir)."""
    dugme = _rapor_dugmesi(page)
    ctx = page.context
    klasor.mkdir(parents=True, exist_ok=True)
    yol = klasor / ad
    alinan, olaylar = {}, []
    onceki = list(ctx.pages)

    def al(d):
        olaylar.append(f"indirme başladı: {d.suggested_filename}")
        if "yol" in alinan:
            return
        try:  # hemen kaydet (indirme bitene kadar bekler); pencere kapanirsa indirme yarim kalir
            d.save_as(str(yol))
            alinan["yol"] = yol
        except Exception as e:
            olaylar.append(f"kaydedilemedi: {type(e).__name__}: {str(e)[:90]}")

    def konsol(m):
        if m.text.startswith("LB_CLOSE"):
            olaylar.append(f"Luca window.close() çağırdı, engellendi ({m.text[9:]})")

    def yeni_sayfa(p):
        olaylar.append(f"yeni pencere: {p.url[:60]}")
        p.on("download", al)
        p.on("console", konsol)
        p.on("close", lambda *_: olaylar.append("pencere kapandı"))
    try:
        ctx.add_init_script(POPUP_KAPANMASINI_ENGELLE_JS)
    except Exception:
        pass
    _her_cerceveye(ctx, POPUP_KAPANMASINI_ENGELLE_JS)  # zaten acik sayfalar (Mizan formu dahil)
    page.on("download", al)
    ctx.on("page", yeni_sayfa)
    try:
        for p in onceki:
            p.on("console", konsol)
            if p is not page:
                p.on("download", al)
        dugme.click(timeout=8000)
        kosulu_bekle(page, lambda: "yol" in alinan, sure_ms, aralik_ms=300)
    finally:
        for p in list(ctx.pages):
            try:
                p.remove_listener("download", al)
            except Exception:
                pass
        try:
            ctx.remove_listener("page", yeni_sayfa)
        except Exception:
            pass
        try:  # tani: rapor sonrasi pencerelerin durumu (ana pencere kapandi mi?)
            olaylar.append(f"ana pencere {'KAPANDI' if page.is_closed() else 'açık'}; açık pencere sayısı: "
                           f"{len([p for p in ctx.pages if not p.is_closed()])}")
        except Exception:
            olaylar.append("pencere durumu okunamadı (tarayıcı kapanmış olabilir)")
        yaz(f"    İndirme olayları: {'; '.join(olaylar)}", log)
        for p in list(ctx.pages):  # raporun actigi pencereleri biz kapatiriz (ana pencere kapandiysa tarayici kapanmasin diye dokunulmaz)
            if p not in onceki and p is not page and not page.is_closed():
                try:
                    p.close()
                except Exception:
                    pass
        try:  # sonraki acilacak pencereler normal davransin (init script'ler sirayla calisir)
            ctx.add_init_script(POPUP_KAPANMASINI_GERI_AL_JS)
        except Exception:
            pass
        _her_cerceveye(ctx, POPUP_KAPANMASINI_GERI_AL_JS)
        for p in list(ctx.pages):
            try:
                p.remove_listener("console", konsol)
            except Exception:
                pass
    if "yol" not in alinan:
        raise LookupError("Mizan indirilemedi (" + ("; ".join(olaylar) if olaylar else "Rapor'a basıldı ama dosya inmedi") + ")")
    return alinan["yol"]


def mizan_oku(page, firma, bas, bit, indirme_klasoru, tani_klasoru, log=None, tani_hep=False):
    """Acik firmanin Mizan'ini donem icin Excel olarak indirir ve kar_zarar() sonucunu dondurur."""
    adim = (lambda ek: tani_kaydet(page, tani_klasoru, log, ek, "mizan")) if tani_hep else (lambda ek: None)
    try:
        ekrani_ac(page)
        adim("-1-form")
        sonuc = formu_doldur(page, bas, bit)
        yaz(f"    Mizan formu: {', '.join(f'{k}={v}' for k, v in sonuc.items())}", log)
        adim("-2-form-doldu")
        yol = indir(page, indirme_klasoru, f"mizan_{dosya_adi_yap(firma)}.xlsx", log=log)
    except LookupError:
        tani_kaydet(page, tani_klasoru, log, "-hata", "mizan")
        raise
    yaz(f"    Mizan indirildi: {yol.name}", log)
    return mizan_kar_zarar(yol, bas, bit)
