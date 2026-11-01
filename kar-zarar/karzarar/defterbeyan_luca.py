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
from lucabot.luca_ekran import (acik_pencere, acik_pencereleri_kapat, cerceveler, diyalog_bekle, dugmeye_bas, gorunur_mu,
                                hata_kaydet, metinle_bul, pencerede_tikla, tarih_araligi_yaz, tarih_kutulari)
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

KAYIT_YOK_METINLERI = ("kayıt bulunamadı", "kayıt bulunamamıştır", "kayıt yok", "listelenecek kayıt")


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
    sayfa_durulsun(sayfa, azami_ms=1500)
    if not gorunur_mu(sayfa, ["Listele", "Evrak No"], sure=8000):
        raise LookupError(f"{ad} sekmesi açılmadı")


# --- liste ----------------------------------------------------------------------------------------

def tabloyu_oku(sayfa):
    """{'basliklar': [...], 'satirlar': [[...]]} ya da (liste henuz yok/okunamadi) None."""
    for fr in cerceveler(sayfa):
        try:
            t = fr.evaluate(TABLO_JS)
        except Exception:
            continue
        if t:
            return t
    return None


def _kayit_yok_yazisi(sayfa):
    return any(gorunur_mu(sayfa, m, sure=0) for m in KAYIT_YOK_METINLERI)


def durum_sec(sayfa, hedef):
    """Durum kutusunu (Tumu / Gonderilmemisler / Gonderilmisler) ayarlar."""
    istenen = _k(hedef)
    for fr in cerceveler(sayfa):
        try:
            kutular = fr.locator("select")
            for i in range(kutular.count()):
                kutu = kutular.nth(i)
                secenekler = kutu.locator("option").all_inner_texts()
                eslesen = next((o for o in secenekler if _k(o) == istenen), None)
                if eslesen is not None and any("gonderilmemis" in _k(o) for o in secenekler):
                    kutu.select_option(label=eslesen, timeout=5000)
                    return True
        except Exception:
            continue
    # ozel (select olmayan) acilir liste: gorunen deger tiklanip secenek secilir
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


def evrak_tarihi_kutulari(sayfa):
    """'Evrak Tarihi' yazisindan sonraki ilk iki kutu (Gonderilme Tarihi kutulari bos ve ayri); olmazsa genel arama."""
    for fr in cerceveler(sayfa):
        try:
            sec = ("xpath=(//*[normalize-space(text())='Evrak Tarihi']"
                   "/following::input[not(@type) or @type='text'])")
            kutu = fr.locator(sec)
            if kutu.count() >= 2 and kutu.nth(0).is_visible() and kutu.nth(1).is_visible():
                return [kutu.nth(0), kutu.nth(1)]
        except Exception:
            continue
    return tarih_kutulari(sayfa)[:2]


def listele(sayfa, bas, bit, durum, sure=30000):
    """Evrak Tarihi araligi + Durum ile Listele'ye basar; okunan tabloyu dondurur (kayit yoksa satirlar bos)."""
    if not gorunur_mu(sayfa, "Listele", sure=1200):
        dugmeye_bas(sayfa, "Arama")  # liste varken suzgec formu 'Arama' ile yeniden acilir
        if not gorunur_mu(sayfa, "Listele", sure=5000):
            raise LookupError("Listele düğmesi bulunamadı")
    kutular = evrak_tarihi_kutulari(sayfa)
    if len(kutular) < 2:
        raise LookupError("Evrak Tarihi kutuları bulunamadı")
    tarih_araligi_yaz(kutular, bas, bit)  # Gonderilme Tarihi kutulari bos kalir
    durum_sec(sayfa, durum)
    if not dugmeye_bas(sayfa, "Listele"):
        raise LookupError("Listele düğmesine basılamadı")

    def hazir():
        # form kapanmadan okunan tablo ESKI listedir; Listele gizlenince yeni liste (ya da kayit yok uyarisi) gelmistir
        if gorunur_mu(sayfa, "Listele", sure=0):
            return None
        t = tabloyu_oku(sayfa)
        if t is not None:
            return t
        if _kayit_yok_yazisi(sayfa):
            acik_pencereleri_kapat(sayfa)
            return {"basliklar": [], "satirlar": []}
        return None

    t = kosulu_bekle(sayfa, hazir, sure, aralik_ms=500)
    if t is None:
        acik_pencereleri_kapat(sayfa)
        t = tabloyu_oku(sayfa) if not gorunur_mu(sayfa, "Listele", sure=0) else None
    if t is None:
        raise LookupError(f"Liste okunamadı ({durum})")
    return t


def hepsini_sec(sayfa):
    """Listedeki tum kayitlari isaretler; isaretli satir sayisini dondurur."""
    for fr in cerceveler(sayfa):
        try:
            sayi = fr.evaluate(HEPSINI_SEC_JS)
        except Exception:
            continue
        if sayi:
            return int(sayi)
    return 0


# --- kontrol --------------------------------------------------------------------------------------

def kontrol_tur(sayfa, tur, bas, bit, log=None):
    """Bir sekmede (gelir/gider) donemin gonderilmemis ve gonderilmis kayitlarini sayar; ozet sozluk dondurur."""
    sekme_ac(sayfa, tur)
    bekleyen = listele(sayfa, bas, bit, GONDERILMEMIS)
    adet, tutar, kayitlar, sabit = db_sonuc.kayitlari_ozetle(bekleyen["basliklar"], bekleyen["satirlar"])
    gonderilmis = listele(sayfa, bas, bit, GONDERILMIS)
    return {"gonderilmemis": adet, "tutar_gonderilmemis": tutar, "kayitlar": kayitlar, "sabit_kiymet": sabit,
            "gonderilmis": len(gonderilmis["satirlar"])}


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


def gonder_tikla(sayfa, tur):
    return islem_tikla(sayfa, "Defter Beyan Sistemine Gönder", f"Luca.defter_beyan.gonder('{tur}')")


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


def _pencere_yazisi(pencere):
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
        if not _alanlar_dolu(giris):
            pencerede_tikla(sayfa, giris, ["Kapat"])
            return "", "Defter Beyan API Key/Secret bilgileri Luca'da boş; önce Luca'da girin (gönderilmedi)"
        pencerede_tikla(sayfa, giris, ["Tamam"])
    _, ent = diyalog_bekle(sayfa, ("DEFTER BEYAN ENTEGRASYON", "gönderim başlıyor"), 20000)
    if ent is None:
        return "", "Entegrasyon (sonuç) penceresi çıkmadı"
    son, ayni, bitis = "", 0, time.time() + azami_saniye
    while time.time() < bitis:
        yazi = _pencere_yazisi(ent)
        ayni = ayni + 1 if yazi == son else 0
        son = yazi
        if son and ayni >= 4 and time.time() > bitis - azami_saniye + 3:  # yazi ~4 sn degismedi: bitti
            break
        time.sleep(1)
    pencerede_tikla(sayfa, ent, ["Tamam"])
    sayfa_durulsun(sayfa, azami_ms=1500)
    return son, ""


def gonder_tur(sayfa, tur, bas, bit, log=None):
    """Bir sekmede Gonderilmemisler'i listeleyip hepsini Defter Beyan'a gonderir ve kalani yeniden sayar.

    Donus: {'sonuc', 'mesaj', 'gonderilen', 'kalan'}; 'sonuc' db_sonuc.KAYIT_YOK/HATA/BASARILI/BELIRSIZ."""
    sekme_ac(sayfa, tur)
    t = listele(sayfa, bas, bit, GONDERILMEMIS)
    n = len(t["satirlar"])
    if n == 0:
        return {"sonuc": db_sonuc.KAYIT_YOK, "mesaj": "Gönderilmemiş kayıt yok", "gonderilen": 0, "kalan": 0}
    secilen = hepsini_sec(sayfa)
    if secilen != n:
        raise LookupError(f"{n} kayıttan {secilen} tanesi seçilebildi; güvenlik için gönderilmedi")
    # Elle yapilan sira: Cari Bilgi Sorgula -> Kaydet -> Gonder (cari bilgileri kayda islenir; liste yenilenip secim bosalabilir)
    cari = ""
    if islem_tikla(sayfa, "Cari Bilgi Sorgula"):
        cari = pencereyi_gec(sayfa, bekle_sn=10, log=log)
    else:
        raise LookupError("Işlemler > Cari Bilgi Sorgula bulunamadı; gönderilmedi")
    if not dugmeye_bas(sayfa, "Kaydet"):
        raise LookupError("Kaydet düğmesine basılamadı; gönderilmedi")
    pencereyi_gec(sayfa, bekle_sn=8, log=log)
    t = tabloyu_oku(sayfa) or {"satirlar": []}
    if len(t["satirlar"]) != n:
        raise LookupError(f"Kaydet sonrası liste {n} yerine {len(t['satirlar'])} kayıt; güvenlik için gönderilmedi")
    secilen = hepsini_sec(sayfa)   # Kaydet listeyi yenilediyse secim kalkmis olabilir
    if secilen != n:
        raise LookupError(f"Kaydet sonrası {n} kayıttan {secilen} tanesi seçilebildi; gönderilmedi")
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
    kalan_t = listele(sayfa, bas, bit, GONDERILMEMIS)  # ayni suzgecle yeniden oku (Yenile'nin sonucunu dogrular)
    kalan = len(kalan_t["satirlar"])
    _, kalan_tutar, kalan_kayitlar, kalan_sabit = db_sonuc.kayitlari_ozetle(kalan_t["basliklar"], kalan_t["satirlar"])
    if sinif == db_sonuc.BASARILI and (kalan > 0 or (bildirilen is not None and bildirilen != n)):
        sinif = db_sonuc.KISMI  # pencere "tamamlandi" dese de hepsi gitmemis: kullanici kontrol etsin
    return {"sonuc": sinif, "mesaj": mesaj, "gonderilen": max(n - kalan, 0), "kalan": kalan,
            "bildirilen": bildirilen, "hatalar": ayrinti["hatalar"][:200],
            "hata_ozeti": db_sonuc.hata_ozeti(ayrinti["hatalar"]),
            "kalan_tutar": kalan_tutar, "kalan_kayitlar": kalan_kayitlar, "kalan_sabit": kalan_sabit,
            "cari_mesaj": cari[:300]}


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
                + f", {t['gonderilmis']} gönderilmiş"
                + (f" (bunların {t['sabit_kiymet']} tanesi SABİT KIYMET)" if t.get("sabit_kiymet") else ""), log)
        except Exception as e:
            sonuc[tur] = {}
            sonuc["hata"] = f"{SEKMELER[tur]}: {str(e)[:160]}"
            yaz(f"    HATA ({SEKMELER[tur]}): {str(e)[:160]}", log)
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
