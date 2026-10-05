# -*- coding: utf-8 -*-
"""Genel muhasebe firmalarinda Luca'daki Hesap Plani Listesi'nden kar/zarar tahmini.

Yol: Muhasebe > Hesap Planı İşlemleri > Hesap Planı Listesi. Alttaki Filtre
"Hesap Arama" penceresini acar; Başlangıç/Bitiş Tarih donemi belirler. Listede
her hesabin Borç/Alacak toplamlari ve bakiyeleri vardir (sinif satirlari dahil:
"6", "7" ...). Hesaplama:

  Gelir     = 6'li hesaplarin alacak - borc farki (satislar ve gelirler, indirimler dusulmus)
  Mal alisi = 150-153 hesaplarin borc - alacak farki
  Gider     = 7'li hesaplarin borc - alacak farki
  Kar       = Gelir - Mal alisi - Gider      (eksi ise zarar)
"""

import re

from lucabot.bekleme import kosulu_bekle, sayfa_durulsun
from lucabot.fatura_analiz import tutar_cozumle
from lucabot.luca_ekran import acik_pencereleri_kapat, dugmeye_bas, gorunur_mu
from lucabot.luca_form import alan, alanlari_isaretle, metin_yaz
from lucabot.luca_gezinme import menu_yolunu_ac
from lucabot.musteri_listesi import TABLOLAR_JS, tablolari_al, tani_kaydet
from lucabot.ortak import sadelestir, yaz

MENU_YOLU = "Muhasebe > Hesap Planı İşlemleri > Hesap Planı Listesi"
ARAMA_PENCERESI = "Hesap Arama"
KOD_DESENI = re.compile(r"^\d+(\.\d+)*$")
SAYI_DESENI = re.compile(r"^-?\d{1,3}(\.\d{3})*,\d{2}$|^-?\d+,\d{2}$")
STOK_HESAPLARI = ("150", "151", "152", "153")


# --- listeyi satirlara cevirme (tarayicisiz, test edilebilir) --------------------------

def hesap_satirlari(tablolar):
    """tablolar: [(cerceve no, satirlar)] -> [{kod, ad, borc, alacak}] (en cok hesap satiri olan tablodan)."""
    en_iyi, en_cok = None, 0
    for _, satirlar in tablolar:
        adet = sum(1 for s in satirlar if _kod(s))
        if adet > en_cok:
            en_iyi, en_cok = satirlar, adet
    if en_iyi is None:
        return []
    baslik = next((s for s in en_iyi[:6] if sadelestir(" ".join(s)).startswith("HESAP KODU")), None)
    sutunlar = {}
    if baslik:
        for i, h in enumerate(baslik):
            sutunlar.setdefault(sadelestir(h), i)
    sonuc = []
    for s in en_iyi:
        kod = _kod(s)
        if not kod:
            continue
        i = next(j for j, h in enumerate(s[:3]) if h.strip() == kod)
        sayilar = [h for h in s[i + 1:] if SAYI_DESENI.match(h.strip())]
        kayma = max(0, len(s) - len(baslik)) if baslik else 0  # satir basinda fazladan kutu/ikon hucresi
        if ("BORC" in sutunlar and "ALACAK" in sutunlar
                and max(sutunlar["BORC"], sutunlar["ALACAK"]) + kayma < len(s)
                and SAYI_DESENI.match(s[sutunlar["BORC"] + kayma].strip())):
            borc, alacak = s[sutunlar["BORC"] + kayma], s[sutunlar["ALACAK"] + kayma]
        elif len(sayilar) >= 2:  # baslik okunamadi: ilk iki sayi Borç ve Alacak
            borc, alacak = sayilar[0], sayilar[1]
        else:
            continue
        ad = next((h for h in s[i + 1:] if h.strip() and not SAYI_DESENI.match(h.strip())), "")
        sonuc.append({"kod": kod, "ad": ad, "borc": tutar_cozumle(borc), "alacak": tutar_cozumle(alacak)})
    return sonuc


def _kod(hucreler):
    """Satir hesap satiri ise hesap kodu (ilk uc hucreden biri) ve satirda en az iki tutar var."""
    kod = next((h.strip() for h in hucreler[:3] if KOD_DESENI.match(h.strip())), "")
    if not kod:
        return ""
    return kod if sum(1 for h in hucreler if SAYI_DESENI.match(h.strip())) >= 2 else ""


def _toplam(satirlar, kod):
    """Hesap grubunun (borc, alacak) toplami.

    Once tam kodlu satir; yoksa bir alt duzeydeki satirlar (sinif icin 2 haneli, sonra 3 haneli
    ana hesaplar; ana hesap icin 'kod.xx' alt hesaplar). Bulunamazsa (0, 0): calismayan hesap.
    """
    tam = [s for s in satirlar if s["kod"] == kod]
    if tam:
        return tam[0]["borc"], tam[0]["alacak"]
    if len(kod) == 1:
        for uzunluk in (2, 3):
            alt = [s for s in satirlar if s["kod"].startswith(kod) and len(s["kod"]) == uzunluk]
            if alt:
                return sum(s["borc"] for s in alt), sum(s["alacak"] for s in alt)
    alt = [s for s in satirlar if s["kod"].startswith(kod + ".")]
    if alt:
        # ust duzey toplamlari ayri satirsa iki kat sayilmasin: yalniz en kisa kodlu alt satirlar
        en_kisa = min(len(s["kod"]) for s in alt)
        alt = [s for s in alt if len(s["kod"]) == en_kisa]
        return sum(s["borc"] for s in alt), sum(s["alacak"] for s in alt)
    return 0.0, 0.0


def kar_zarar(satirlar):
    """Hesap satirlarindan {satis, mal_alis, gider, kar, ayrinti}."""
    b6, a6 = _toplam(satirlar, "6")
    b7, a7 = _toplam(satirlar, "7")
    stok = [_toplam(satirlar, k) for k in STOK_HESAPLARI]
    gelir = a6 - b6
    mal_alis = sum(b - a for b, a in stok)
    gider = b7 - a7
    return {"satis": round(gelir, 2), "mal_alis": round(mal_alis, 2), "gider": round(gider, 2),
            "kar": round(gelir - mal_alis - gider, 2), "toplam_gider": round(mal_alis + gider, 2),
            "ayrinti": {"6": [b6, a6], "7": [b7, a7], **{k: list(t) for k, t in zip(STOK_HESAPLARI, stok)}}}


# --- ekran -------------------------------------------------------------------------

# Hesap Planı Listesi hazir mi: baslik hucreleri (Hesap Kodu / Hesap Adı) GORUNUR olmali. Ayni yazi gizli
# "Hesap Arama" penceresinde de gectigi icin yalniz ilk eslesmeye bakmak ekrani yanlislikla "hazir degil" sayiyordu.
EKRAN_HAZIR_JS = """() => {
  const gorunur = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const var_mi = m => [...document.querySelectorAll('td, th')].some(e => gorunur(e) && (e.innerText || '').trim() === m);
  return var_mi('Hesap Kodu') && var_mi('Hesap Adı');
}"""

# Liste 150'serlik sayfalara bolunur: [sayfa no, bu sayfadaki kayit sayisi]; 150 ise sonraki() ile devam edilir
SAYFA_DURUMU_JS = """() => {
  const a = document.getElementById('sayfaNo'), b = document.getElementById('sayfaBasinaKayitSayisi');
  return (a && b && typeof sonraki === 'function') ? [Number(a.value), Number(b.value)] : null;
}"""


def _ekran_hazir(page):
    for fr in page.frames:
        try:
            if fr.evaluate(EKRAN_HAZIR_JS):
                return True
        except Exception:
            continue
    return False


def _sayfa_durumu(page):
    for fr in page.frames:
        try:
            d = fr.evaluate(SAYFA_DURUMU_JS)
            if d:
                return fr, d
        except Exception:
            continue
    return None, None


def _sonraki_sayfa(page, fr, sayfa_no):
    """sonraki() ile bir sonraki sayfaya gecer; sayfa numarasi artana kadar bekler."""
    for _ in range(5):  # Luca mesgulse sonraki() yok sayilir
        try:
            fr.evaluate("() => sonraki()")
        except Exception:
            pass  # sayfa yeniden yuklenirken baglam kopabilir
        if kosulu_bekle(page, lambda: (_sayfa_durumu(page)[1] or [0])[0] == sayfa_no + 1, 15000, aralik_ms=500):
            return True
        _yuklenmeyi_bekle(page, 20000)
    return False


# Luca menusu apymenu ile JS'ten cizilir: menu cercevesinde menuItems listesi ve aktar(link) islevi vardir.
# Menu gorunmese de ayni baglanti aktar() ile icerik cercevesinde acilir ("||" = Muhasebe > Hesap Planı İşlemleri altı).
MENU_ETIKETI = "||Hesap Planı Listesi"
MENUDEN_AC_JS = """arg => {
  if (typeof menuItems === 'undefined') return {durum: 'menuItems yok'};
  if (typeof aktar !== 'function') return {durum: 'aktar() yok'};
  const temiz = t => (t || '').replace(/<[^>]*>/g, '').replace(/^\\|+/, '').replace(/&[a-z]+;/g, '').trim().toLocaleLowerCase('tr');
  // 1) tam etiket ("||Hesap Planı Listesi"); 2) menu adi (+ baglanti parcasi); 3) yalniz baglanti parcasi
  let m = menuItems.find(x => x && x[0] === arg.etiket && x[1]);
  if (!m && arg.ad) m = menuItems.find(x => x && x[1] && temiz(x[0]) === arg.ad.toLocaleLowerCase('tr')
                                        && (!arg.link || x[1].indexOf(arg.link) >= 0));
  if (!m && arg.link) m = menuItems.find(x => x && x[1] && x[1].indexOf(arg.link) >= 0);
  if (!m) {
    const anahtar = (arg.ad || arg.etiket || '').replace(/^\\|+/, '').toLocaleLowerCase('tr');
    return {durum: 'menüde bulunamadı', adet: menuItems.length,
            benzer: menuItems.filter(x => x && x[0] && temiz(x[0]).includes(anahtar)).slice(0, 6).map(x => x[0] + ' -> ' + x[1])};
  }
  try { aktar(m[1]); } catch (e) { return {durum: 'aktar() hata: ' + e.message, link: m[1]}; }
  return {durum: 'ok', link: m[1]};
}"""
SON_MENU_TANISI = {"metin": ""}  # menuden_dogrudan_ac basarisiz olursa nedeni (hata mesajlarinda gosterilir)


def menuden_dogrudan_ac(page, etiket=MENU_ETIKETI, ad=None, link=None):
    """Menu verisindeki baglantiyi aktar() ile acar. Menu cercevesi/baglanti bulunamazsa False (neden SON_MENU_TANISI'nda)."""
    nedenler = []
    for fr in page.frames:
        try:
            sonuc = fr.evaluate(MENUDEN_AC_JS, {"etiket": etiket, "ad": ad, "link": link})
        except Exception:
            continue
        if sonuc and sonuc.get("durum") == "ok":
            SON_MENU_TANISI["metin"] = ""
            return True
        if sonuc and sonuc.get("durum") != "menuItems yok":
            nedenler.append(str(sonuc))
    SON_MENU_TANISI["metin"] = "; ".join(nedenler) or "hiçbir çerçevede menuItems yok"
    return False


# Luca bir istek surerken yapilan ikinci islemi "Lütfen işleminiz sürerken işleminizi tekrarlamayın." diyerek YOK SAYAR.
# Buyuk firmalarda Hesap Plani Listesi'nin yuklenmesi 20 sn'yi asar; bu yuzden ekran acilirken menuyu ikinci kez
# tiklamak, yuklenirken Filtre/Ara/tarih islemleri yapmak yerine yuklemenin bitmesi beklenir.
MESGUL_METNI = "tekrarlamayın"
EKRAN_ACMA_BEKLEME_MS = 120000


def _mesgul_mu(page):
    return gorunur_mu(page, MESGUL_METNI, sure=0)


def _yuklenmeyi_bekle(page, azami_ms=60000):
    """Sayfa ve uyari bitene kadar bekler (istek surerken yapilan islem yok sayilir)."""
    sayfa_durulsun(page, azami_ms=5000, sessizlik_ms=1000)
    kosulu_bekle(page, lambda: not _mesgul_mu(page), azami_ms, aralik_ms=500)


def ekrani_ac(page, yol=None):
    acik_pencereleri_kapat(page)
    if yol is None and menuden_dogrudan_ac(page):
        # istek gitti: ikinci kez tiklamadan yuklemenin bitmesini bekle
        if kosulu_bekle(page, lambda: _ekran_hazir(page), EKRAN_ACMA_BEKLEME_MS, aralik_ms=500):
            _yuklenmeyi_bekle(page)
            return True
    return menu_yolunu_ac(page, yol or MENU_YOLU, lambda: _ekran_hazir(page))


def _filtre_cercevesi(page):
    """Hesap Arama penceresinin (#tarih1 kutusu) bulundugu cerceve; yoksa None. Kutu gorunene kadar bekler."""
    def var():
        return any(_say(fr, "#tarih1") for fr in page.frames)
    if not var():
        return None

    def gorunur():
        for fr in page.frames:
            try:
                if fr.locator("#tarih1").count() and fr.locator("#tarih1").first.is_visible():
                    return fr
            except Exception:
                continue
        return None
    return kosulu_bekle(page, gorunur, 8000, aralik_ms=300)


def _say(fr, secici):
    try:
        return fr.locator(secici).count()
    except Exception:
        return 0


def _tarih_yaz(kutu, metin):
    kutu.fill(metin, timeout=5000)
    kutu.press("Tab")
    kutu.page.wait_for_timeout(250)  # sayfa mesgulse yazilan deger hemen silinebilir
    if kutu.input_value().strip() != metin:  # maske/tarih secici yazimi bozduysa degeri dogrudan ata
        kutu.evaluate("(e, v) => { e.value = v; e.dispatchEvent(new Event('input', {bubbles: true}));"
                      " e.dispatchEvent(new Event('change', {bubbles: true})); }", metin)
        kutu.page.wait_for_timeout(250)
    return kutu.input_value().strip() == metin


def filtrele(page, bas, bit, log=None):
    """Filtre > Hesap Arama: Hesap Sınıfı=Tümü, Çalışmayan Hesapları Gösterme, Başlangıç/Bitiş Tarih; Ara."""
    for _ in range(4):  # Luca mesgulse Filtre tiklamasi yok sayilir
        _yuklenmeyi_bekle(page, 20000)
        dugmeye_bas(page, "Filtre", sure=8000)
        if gorunur_mu(page, ARAMA_PENCERESI, sure=8000):
            break
    else:
        raise LookupError(f"'{ARAMA_PENCERESI}' penceresi acilmadi")
    fr = _filtre_cercevesi(page)
    if fr is not None:  # gercek Luca: alan kimlikleri bilinir (kebirDeger, tarih1, tarih2; Ara = gonder('', 'search'))
        try:  # varsayilan 1 Dönen Varlıklar; kar/zarar icin 6, 7 ve 15x hesaplari da gerekir
            fr.locator("select[name=kebirDeger]").select_option(value="", timeout=4000)
        except Exception:
            yaz("    UYARI: Hesap Sınıfı 'Tümü' seçilemedi (yalnız seçili sınıf okunur)", log)
        try:  # Calismayan Hesaplar = "Çalışmayan Hesapları Gösterme" (hareketsiz hesaplar listeden cikar)
            fr.locator("select[name=calismayanHesap]").select_option(value="1", timeout=4000)
        except Exception:
            yaz("    UYARI: 'Çalışmayan Hesapları Gösterme' seçilemedi", log)
        _yuklenmeyi_bekle(page)
        for deneme in range(6):  # sayfa mesgulken yazilan degerler silinebilir: dogrulayip yeniden dene
            tamam = all(_tarih_yaz(fr.locator(f"#{kimlik}"), f"{d:%d/%m/%Y}") for kimlik, d in (("tarih1", bas), ("tarih2", bit)))
            if tamam:
                break
            yaz("    Tarih alanları yazılamadı (Luca meşgul olabilir); bekleyip yeniden deneniyor", log)
            _yuklenmeyi_bekle(page, 20000)
        else:
            raise LookupError("Hesap Arama tarih alanlarına tarih yazılamadı (Luca meşgul: işlem sürerken tekrarlanamaz)")
        for deneme in range(6):  # Ara: Luca mesgulse komut yok sayilir; liste yenilenene kadar tekrarla
            fr.evaluate("() => { window.__lucabot_eski = 1; }")  # sayfa yenilenince kaybolur
            try:
                fr.evaluate("() => gonder('', 'search')")
            except Exception:
                pass  # sayfa yenilenirken baglam kopabilir
            if kosulu_bekle(page, lambda: not _isaret_var(fr), 12000, aralik_ms=400):
                break
            yaz("    'Ara' yok sayıldı (Luca meşgul); bekleyip yeniden deneniyor", log)
            _yuklenmeyi_bekle(page, 20000)
        else:
            raise LookupError("Ara'dan sonra liste yenilenmedi (Luca meşgul)")
        sayfa_durulsun(page, azami_ms=3000, sessizlik_ms=700)
        return
    cerceve = alanlari_isaretle(page, ARAMA_PENCERESI, ["Başlangıç Tarih", "Bitiş Tarih"],
                                zorunlu="Başlangıç Tarih")
    for etiket, d in (("Başlangıç Tarih", bas), ("Bitiş Tarih", bit)):
        if not metin_yaz(alan(cerceve, etiket), f"{d:%d/%m/%Y}"):
            raise LookupError(f"'{etiket}' alanina {d:%d/%m/%Y} yazilamadi")
    for kurucu in (lambda: cerceve.get_by_role("button", name="Ara", exact=True),
                   lambda: cerceve.get_by_text("Ara", exact=True)):
        try:
            kurucu().first.click(timeout=5000)
            return
        except Exception:
            continue
    raise LookupError("'Ara' dugmesine basilamadi")


def _isaret_var(fr):
    try:
        return bool(fr.evaluate("() => window.__lucabot_eski === 1"))
    except Exception:
        return False  # baglam koptu: sayfa yenileniyor


def listeyi_oku(page):
    return hesap_satirlari(tablolari_al(page))


def hesap_plani_oku(page, bas, bit, tani_klasoru, log=None, tani_hep=False):
    """Acik firmanin Hesap Planı Listesi'ni donem icin suzer; kar_zarar() sonucunu dondurur.

    tani_hep: tek firma denemesinde her adimdan sonra ekran goruntusu + sayfa kaynagi kaydedilir.
    """
    adim = (lambda ek: tani_kaydet(page, tani_klasoru, log, ek, "hesap-plani")) if tani_hep else (lambda ek: None)
    try:
        ekrani_ac(page)
        adim("-1-ekran-acildi")
        filtrele(page, bas, bit, log)
        adim("-2-filtre-sonrasi")
    except LookupError:
        tani_kaydet(page, tani_klasoru, log, "-hata", "hesap-plani")
        raise
    tum = {}
    # Gercek Luca: liste sunucuda hazir gelir ve tek icerik cercevesindedir (#sayfaNo burada); yalniz o cerceve
    # bir kez okunur. Cerceve bulunamazsa (baska ekran) tum cerceveler taranip liste dolana kadar beklenir.
    kosulu_bekle(page, lambda: _sayfa_durumu(page)[0] is not None, 15000, aralik_ms=500)
    for _ in range(40):  # sayfa sayfa oku (150 kayitlik sayfalar)
        fr, durum = _sayfa_durumu(page)
        satirlar = []
        if fr is not None:
            for _ in range(5):
                try:
                    satirlar = hesap_satirlari([(0, t) for t in fr.evaluate(TABLOLAR_JS) or []])
                except Exception:
                    satirlar = []
                if satirlar:
                    break
                sayfa_durulsun(page, azami_ms=1500, sessizlik_ms=500)
        else:
            kosulu_bekle(page, lambda: len(listeyi_oku(page)) > 0, 30000, aralik_ms=700)
            for _ in range(6):  # liste doldukca sayi artar; iki okuma ayni olunca tamam
                sayfa_durulsun(page, azami_ms=1500, sessizlik_ms=500)
                yeni = listeyi_oku(page)
                if yeni and len(yeni) == len(satirlar):
                    break
                satirlar = yeni
        for h in satirlar:
            tum[h["kod"]] = h
        if not durum or durum[1] < 150 or not _sonraki_sayfa(page, fr, durum[0]):
            break
    satirlar = list(tum.values())
    adim("-3-liste-okundu")
    yaz(f"    Hesap planı: {len(satirlar)} hesap satırı okundu", log)
    if not satirlar:
        if _ekran_hazir(page) and _sayfa_durumu(page)[0] is not None:  # liste ekrani acik ve bos: donemde hareket yok
            yaz("    Dönemde hareketi olan hesap yok; sonuç sıfır", log)
            sonuc = kar_zarar([])
            sonuc["ayrinti"]["not"] = "dönemde hareket yok"
            return sonuc
        tani_kaydet(page, tani_klasoru, log, "-bos", "hesap-plani")
        raise LookupError("Hesap planı satırı okunamadı (liste gelmedi)")
    return kar_zarar(satirlar)
