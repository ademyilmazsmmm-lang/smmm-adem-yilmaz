# -*- coding: utf-8 -*-
"""FATURA SORGULAMA: GIB'den Getir, Islem Takip, Belge Ara, Interaktif V.D., iptal/itiraz.

Buradaki fonksiyonlar Luca'ya sorgu yaptirip sonucunu bekler. Beklemeler
sabit sure degil, Luca'nin kendi isaretlerine baglidir: Islem Takip
penceresindeki "sona erdi" yazisi, pencerenin kapanmasi, bilgi penceresi,
ekranin altindaki "Toplam Kayit Sayisi" gibi.
"""

import time

from .bekleme import (degisiklik_baslat, degisip_durulsun, geri_cekil, kosulu_bekle,
                      nabiz, sayfa_durulsun)
from .luca_ekran import (TANI, acik_pencere, acik_pencereleri_kapat, bildirim_yazisi,
                         eski_kutulari_isaretle, getir_dugmesi,
                         yeni_tarih_kutulari,
                         bilgi_penceresini_kapat, cerceveler, diyalog_bekle,
                         dugmeye_bas, ekranda_gib_hatasi,
                         fatura_yok_penceresini_kapat, menu_metinleri,
                         pencere_acik_mi, pencerede_tikla, radyo_sec,
                         tarih_araligi_yaz, tarih_kutulari, varsa_tikla)
from .ortak import AYAR, gunluge_yaz, sadelestir, yaz
from .sabitler import (BELGE_ARA_CAPALARI, BELGE_ARA_ONAY, DIYALOG_ONAY,
                       GIB_GETIR, GIB_HATA_ISARETLERI, INDIRILEMEDI,
                       INTERAKTIF_CAPASI, INTERAKTIF_LISTELE,
                       INTERAKTIF_SERVIS, INTERAKTIF_SORGU, INTERAKTIF_TEKRAR,
                       IPTAL_CAPASI, IPTAL_DUGME_ADAYLARI, IPTAL_ONAY,
                       ISLEM_BITTI, ISLEM_ISARETLERI, KAYIT_SAYISI_DESENI,
                       GIB_HATASI, TAKILDI, TAMAMLANMADI, YETKI_ISARETLERI,
                       YETKI_YOK)
from .sure_olcer import olc, olculur, satiri_temizle, satiri_yaz

# Islem Takip penceresine ne siklikla bakilir (her bakis butun cerceveleri tarar)
TAKIP_ARALIGI_MS = 500
# sorgudan once ekranda kalmis Islem Takip yazisi en fazla bu kadar "eski" sayilir
ESKI_GUNLUK_SANIYE = 3
# "sona erdi" gunlugun sonunda degilse bu kadar sure yeni satir gelmezse bitmis sayilir
BITTI_SUKUNET_SANIYE = 5


def gib_hatasi(metin):
    duz = sadelestir(metin or "")
    return any(isaret in duz for isaret in GIB_HATA_ISARETLERI)


def hata_satiri(metin):
    """Islem Takip yazisindaki hata satiri (gunluge kisaca yazmak icin)."""
    for satir in (metin or "").splitlines():
        if any(i in sadelestir(satir) for i in GIB_HATA_ISARETLERI + ["HATA"]):
            return " ".join(satir.split())[:140]
    return ""


def yetki_hatasi(metin):
    duz = sadelestir(metin or "")
    return any(isaret in duz for isaret in YETKI_ISARETLERI)


def _acik_sayfalar(page):
    """Islem Takip penceresi ayri bir sekmede acilabildigi icin tum sayfalar."""
    sayfalar = [page]
    try:
        sayfalar += [p for p in page.context.pages if p is not page and not p.is_closed()]
    except Exception:
        pass
    return sayfalar


@olculur("İşlem Takip penceresini okuma")
def islem_gunlugu(page):
    """Islem Takip penceresinin metni; pencere kapaliysa bos doner.

    Tarih diyalogu da .luca-open-window oldugu icin yalnizca islem gunlugu
    isaretlerini tasiyan pencere kabul edilir.
    """
    isaretler = [i.lower() for i in ISLEM_ISARETLERI] + [ISLEM_BITTI]
    for p in _acik_sayfalar(page):
        for fr in cerceveler(p):
            try:
                loc = fr.locator(".luca-open-window")
                for i in range(loc.count()):
                    pencere = loc.nth(i)
                    if not pencere.is_visible():
                        continue
                    metin = pencere.inner_text() or ""
                    if any(isaret in metin.lower() for isaret in isaretler):
                        return metin
            except Exception:
                continue
    return ""


# Islem Takip penceresinin gunluk disindaki yazilari (son satira bakarken atlanir)
PENCERE_YAZILARI = ("otomatik aşağı kaydır", "kapat", "işlem takip")


def sorgu_bitti_mi(gunluk):
    """Gunlugun SONUNDA "sona erdi" var mi (ortalarda gecen bir "sona erdi" sayilmaz).

    Pencerenin kendi yazilari (Otomatik aşağı kaydır, Kapat) atlanir; "sona
    erdi"den sonra baska bir gunluk satiri geldiyse islem hala suruyordur.
    """
    satirlar = [" ".join(x.split()).strip(" .").lower() for x in (gunluk or "").splitlines()]
    satirlar = [x for x in satirlar if x and x not in PENCERE_YAZILARI]
    return bool(satirlar) and ISLEM_BITTI in satirlar[-1]


def _sorgu_penceresini_birak(page):
    """Hata/takilma sonrasi ekranda kalan butun pencereleri kapatir."""
    varsa_tikla(page, ["Kapat", "Tamam"], sure=3000)
    acik_pencereleri_kapat(page)
    fatura_yok_penceresini_kapat(page)


@olculur("İşlem Takip izleme (diğer)", kapsayici=True)
def islem_takibini_bekle(page, log, azami_saniye=900, durgunluk_saniye=180,
                         pencere_bekleme=12, en_az_saniye=1, eski_gunluk="", eski_bildirim=""):
    """Sorgu bitene kadar bekler; indirilemeyen fatura sayisini dondurur.

    Ozel donusler: TAMAMLANMADI (-1, zaman asimi), YETKI_YOK (-2), TAKILDI (-3).
    Bitis uc sekilde anlasilir: gunlukte "sona erdi" yazmasi, pencerenin
    kendiliginden kapanmasi (hizli biten sorgularda boyle oluyor) veya
    bilgi penceresi cikmasi. Yazi durgunluk_saniye boyunca hic degismezse
    sorgu takilmis sayilir.
    eski_gunluk: sorgu baslatilmadan once ekranda duran Islem Takip yazisi;
    onceki sorgudan kalmissa onun "sona erdi"si bu sorgunun bitisi sayilmaz
    (ESKI_GUNLUK_SANIYE dolana kadar).
    eski_bildirim: sorgudan once ekranda duran sonuc bildirimi ("3 adet fatura bulundu...").
    Duz bildirimler kendiliginden kaybolana kadar ekranda kalabiliyor; ayni yazi hic
    kaybolmadan duruyorsa onceki sorgunun kalintisidir ve bu sorgunun bitisi sayilmaz
    (aksi halde sorgu bitmeden sonraki tarihe geciliyor, faturalar eksik iniyordu).
    """
    eski_kayboldu = not eski_bildirim
    basla = time.time()
    pencere_goruldu = False
    son_gunluk = ""
    son_degisim = time.time()
    son_bildirim = 0

    while True:
        gecen = time.time() - basla
        gunluk = islem_gunlugu(page)

        # Islem Takip acikken bitis onun yazisindan anlasilir; "fatura bulunamadi" /
        # "fatura bulundu" uyari pencerelerine yalnizca o yokken bakilir (her saniye
        # bu iki aramayi yapmak sorgu basina saniyeler tutuyordu)
        if not gunluk and gecen >= en_az_saniye:
            yazi = bildirim_yazisi(page)
            if not yazi:
                eski_kayboldu = True
            elif yazi == eski_bildirim and not eski_kayboldu:
                pass  # sorgudan once kalmis bildirim: bu sorgunun sonucu degil
            else:
                if fatura_yok_penceresini_kapat(page):
                    yaz(f"    Luca: fatura bulunamadi ({int(gecen)} sn)", log)
                    return 0
                bilgi = bilgi_penceresini_kapat(page)  # "... adet fatura bulundu" de bitis
                if bilgi:
                    yaz(f"    Luca: {bilgi} ({int(gecen)} sn)", log)
                    return 0

        if gunluk:
            if not pencere_goruldu:
                pencere_goruldu = True
                yaz("    İşlem Takip penceresi acildi, sorgu suruyor...", log)
            if gunluk != son_gunluk:
                son_gunluk = gunluk
                son_degisim = time.time()

            # onceki sorgunun "sona erdi" yazisi ekranda kalmis olabilir
            eski = eski_gunluk and gunluk == eski_gunluk and gecen < ESKI_GUNLUK_SANIYE
            # "sona erdi" en sondaysa hemen; ortalardaysa (pencerede tanimadigimiz bir
            # yazi kalmis olabilir) gunluk BITTI_SUKUNET_SANIYE boyunca degismediyse
            bitti = sorgu_bitti_mi(gunluk) or (
                ISLEM_BITTI in gunluk.lower() and time.time() - son_degisim >= BITTI_SUKUNET_SANIYE)
            if bitti and gecen >= en_az_saniye and not eski:
                basarisiz = gunluk.lower().count(INDIRILEMEDI)
                # hangi yaziyla bitildigi gunlukte dursun (Luca ekranlari farkli yaziyor)
                gunluge_yaz("    İşlem Takip son satirlar: " + " | ".join(
                    " ".join(x.split()) for x in gunluk.splitlines()[-4:] if x.strip()), log)
                yaz(f"    GİB sorgusu tamamlandi ({int(gecen)} sn)"
                    + (f", {basarisiz} fatura indirilemedi" if basarisiz else ""), log)
                with olc("sorgu bitince Kapat"):
                    varsa_tikla(page, ["Kapat"], sure=4000)
                    kosulu_bekle(page, lambda: not islem_gunlugu(page), 1500, aralik_ms=250)
                return basarisiz

            if yetki_hatasi(gunluk):
                yaz(f"    Bu firmanin bu servise yetkisi yok ({int(gecen)} sn),"
                    " ekran atlaniyor", log)
                _sorgu_penceresini_birak(page)
                return YETKI_YOK

            if gib_hatasi(gunluk):
                yaz(f"    GİB hata verdi ({int(gecen)} sn): {hata_satiri(gunluk)}", log)
                _sorgu_penceresini_birak(page)
                return GIB_HATASI

            if time.time() - son_degisim > durgunluk_saniye:
                sure_metni = (f"{int(durgunluk_saniye // 60)} dk" if durgunluk_saniye >= 60
                              else f"{int(durgunluk_saniye)} sn")
                yaz(f"    Sorgu {sure_metni} boyunca ilerlemedi, takildi sayiliyor", log)
                _sorgu_penceresini_birak(page)
                return TAKILDI

        elif pencere_goruldu:
            # pencere kendiliginden kapandi: sorgu bitmis demektir
            basarisiz = son_gunluk.lower().count(INDIRILEMEDI)
            yaz(f"    GİB sorgusu tamamlandi ({int(gecen)} sn, pencere kapandi)"
                + (f", {basarisiz} fatura indirilemedi" if basarisiz else ""), log)
            return basarisiz

        elif ekranda_gib_hatasi(page):
            yaz(f"    GİB'e ulasilamadi ({int(gecen)} sn)", log)
            varsa_tikla(page, ["Kapat", "Tamam"], sure=3000)
            acik_pencereleri_kapat(page)
            return GIB_HATASI

        elif gecen > pencere_bekleme:
            yaz(f"    İşlem Takip penceresi {int(gecen)} sn icinde gorunmedi, devam ediliyor", log)
            return 0

        if gecen > azami_saniye:
            yaz(f"    UYARI: GİB sorgusu {int(gecen)} sn sonra zaman asimina ugradi", log)
            varsa_tikla(page, ["Kapat"], sure=3000)
            return TAMAMLANMADI

        if gecen - son_bildirim >= 15:
            son_bildirim = gecen
            yaz(f"    ... bekleniyor ({int(gecen)} sn)", log)
        # ilk en_az_saniye icinde sorgu bitmis olsa da kabul edilmez; ayri sayilir
        with olc("GİB yanıtı bekleme" if gecen >= en_az_saniye
                 else f"GİB yanıtı bekleme (ilk {en_az_saniye} sn)"):
            nabiz(page, TAKIP_ARALIGI_MS)


def gibden_getir(page, baslangic, bitis, log):
    """'GİB'den Getir' ile tek bir tarih araligini sorgular; islem_takibini_bekle sonucunu dondurur."""
    satiri_temizle()
    try:
        with olc("GİB'den Getir (diğer)", kapsayici=True):
            return _gibden_getir(page, baslangic, bitis, log)
    finally:
        satiri_yaz(log, f"Aralık {baslangic} - {bitis}")


def _gibden_getir(page, baslangic, bitis, log):
    yaz(f"    GİB'den Getir aciliyor ({baslangic} - {bitis})", log)
    acik_pencereleri_kapat(page, log)  # onceki sorgudan kalan pencere tiklamayi engelliyor
    fatura_yok_penceresini_kapat(page, bekle=False)  # dugmeli uyari kapatilir; duz bildirim beklenmez
    eski_kutulari_isaretle(page)
    getir = getir_dugmesi(page, sure=8000) or GIB_GETIR  # ekrana gore GİB'den / TÜRMOB'dan Getir
    if not dugmeye_bas(page, getir):
        raise LookupError(f"'{getir}' butonuna basilamadi. Gorunen ogeler: {menu_metinleri(page, 20)}")

    # tarih penceresi: yeni beliren tarih kutulari ya da bilinen bir Luca penceresi
    # (hangisi once gelirse); kutular o pencerenin icinde aranir
    yoklama = {"sayi": 0, "en_uzun": 0.0}

    def tarih_penceresi_var():
        basla_yoklama = time.monotonic()
        try:
            return yeni_tarih_kutulari(page) or acik_pencere(page)[1]
        finally:
            yoklama["sayi"] += 1
            yoklama["en_uzun"] = max(yoklama["en_uzun"], time.monotonic() - basla_yoklama)

    basla_pencere = time.monotonic()
    with olc("tarih penceresinin açılması"):
        bulunan = kosulu_bekle(page, tarih_penceresi_var, 5000, aralik_ms=150)
    gecen_pencere = time.monotonic() - basla_pencere
    if gecen_pencere > 2.5:  # yavas: pencere mi gec aciliyor, yoksa yoklamalar mi yavas anlasilsin
        gunluge_yaz(f"    TANI: tarih penceresi {gecen_pencere:.1f} sn'de goruldu "
                    f"({'kutu' if isinstance(bulunan, list) else 'pencere' if bulunan is not None else 'GORULMEDI'}); "
                    f"{yoklama['sayi']} yoklama, en uzunu {yoklama['en_uzun']:.1f} sn; "
                    f"{len(cerceveler(page))} gorunur cerceve", log)
    if isinstance(bulunan, list):
        kutular, pencere = bulunan, acik_pencere(page)[1]
    else:
        if bulunan is None:  # gercek Luca'da neden gorulmedigi anlasilsin diye
            gunluge_yaz(f"    TANI: tarih penceresi 5 sn'de gorulmedi; {_cerceve_ozeti(page)}", log)
        pencere = bulunan
        kutular = tarih_kutulari(page, pencere)
    if len(kutular) < 2:
        yaz(f"    UYARI: tarih kutulari bulunamadi ({len(kutular)} adet"
            + (f", son hata: {TANI['son_kutu_hatasi']}" if TANI["son_kutu_hatasi"] else "")
            + "), Luca varsayilani kullanilacak", log)
    else:
        yaz(f"    Tarih araligi girildi: {tarih_araligi_yaz(kutular, baslangic, bitis)}", log)

    eski_gunluk = islem_gunlugu(page)  # normalde bos: pencereler kapatildi
    eski_bildirim = bildirim_yazisi(page)  # sorgudan once ekranda kalmis sonuc bildirimi
    tiklanan = (pencerede_tikla(page, pencere, DIYALOG_ONAY, sure=5000) if pencere is not None
                else None) or varsa_tikla(page, DIYALOG_ONAY, sure=5000)
    if not tiklanan:
        raise LookupError(f"'Belgeleri Getir' butonu bulunamadi. Gorunen ogeler: {menu_metinleri(page, 20)}")
    yaz(f"    '{tiklanan}' tiklandi, sorgu basladi", log)

    basarisiz = islem_takibini_bekle(page, log, azami_saniye=AYAR["azami_saniye"],
                                     durgunluk_saniye=AYAR["durgunluk_saniye"],
                                     eski_gunluk=eski_gunluk, eski_bildirim=eski_bildirim)
    acik_pencereleri_kapat(page, log)
    return basarisiz


CERCEVE_OZETI_JS = """() => {
  const gor = e => !!(e.offsetParent || e.getClientRects().length);
  const k = Array.from(document.querySelectorAll('input')).filter(gor);
  const yeni = k.filter(e => !e.hasAttribute('data-lucabot-eski'));
  const p = Array.from(document.querySelectorAll('div,table,form')).filter(e => {
    const s = getComputedStyle(e); return gor(e) && (s.position === 'fixed' || s.position === 'absolute')
      && e.querySelector('input'); }).slice(0, 3).map(e => (e.tagName + '.' + e.className).slice(0, 60));
  return location.pathname.split('/').pop() + ': ' + k.length + ' kutu, ' + yeni.length + ' yeni'
    + (p.length ? ', pencere adaylari ' + p.join(' ; ') : '');
}"""


def _cerceve_ozeti(page):
    """Tani: gorunur cercevelerde kac kutu var, kaci yeni, hangi pencereler acik."""
    parcalar = []
    for fr in cerceveler(page):
        try:
            parcalar.append(fr.evaluate(CERCEVE_OZETI_JS))
        except Exception as e:
            parcalar.append(type(e).__name__)
    return " | ".join(parcalar)[:600]


def listenin_yuklenmesini_bekle(page, baslangic, azami_ms=15000):
    """Yenile/Belge Ara/Listele sonrasi listenin gelmesi: liste degisip ekran durulana kadar."""
    degisip_durulsun(page, baslangic, azami_ms=azami_ms, degisim_ms=3000, sessizlik_ms=500)


@olculur("liste yenileme (diğer)", kapsayici=True)
def listeyi_yenile(page, log, ek=""):
    """Sorgu sonrasi liste kendiliginden tazelenmiyor; tum sorgular bitince bir kez."""
    yaz("    Liste yenileniyor" + (f" ({ek})" if ek else ""), log)
    baslangic = degisiklik_baslat(page)
    if dugmeye_bas(page, "Yenile", sure=5000):
        listenin_yuklenmesini_bekle(page, baslangic)


@olculur("Belge Ara (diğer)", kapsayici=True)
def belge_ara(page, bas, bit, log):
    """Listeyi istenen tarih araligina getirir (indirme ay geneli olsun diye).

    Sorgular 7 gunluk parcalarla yapildigi icin ekranda son parcanin filtresi
    kaliyordu; indirmeden once tum donem yeniden aranir.
    """
    acik_pencereleri_kapat(page, log)
    if not dugmeye_bas(page, "Belge Ara", sure=5000):
        yaz("    UYARI: 'Belge Ara' butonu bulunamadi, liste oldugu gibi kullanilacak", log)
        return False
    _, pencere = diyalog_bekle(page, BELGE_ARA_CAPALARI, azami_ms=3000)
    kutular = tarih_kutulari(page, pencere)
    if len(kutular) < 2:
        yaz("    UYARI: 'Belge Ara' tarih kutulari bulunamadi", log)
        acik_pencereleri_kapat(page, log)
        return False
    tarih_araligi_yaz(kutular, bas, bit)
    onay = pencerede_tikla(page, pencere, BELGE_ARA_ONAY, sure=5000) if pencere is not None else None
    if not onay:  # pencere taninmadi: tarih kutusunda Enter de aramayi baslatiyor
        try:
            kutular[1].press("Enter")
            onay = "Enter"
        except Exception:
            pass
    if onay and onay != "Enter":
        kosulu_bekle(page, lambda: not pencere_acik_mi(pencere), 1500, aralik_ms=200)
    baslangic = degisiklik_baslat(page)  # pencerenin kapanmasi degil, listenin gelmesi beklenir
    if onay and onay != "Enter":
        if pencere_acik_mi(pencere):
            # tiklanan oge baslik olabilir; pencere hala duruyorsa Enter ile aranir
            try:
                kutular[1].press("Enter")
                onay = f"{onay}+Enter"
            except Exception:
                pass
    yaz(f"    Belge Ara: {bas} - {bit}"
        + (f" ('{onay}' tiklandi)" if onay else " (UYARI: onay butonu bulunamadi)"), log)
    listenin_yuklenmesini_bekle(page, baslangic)
    return bool(onay)


# --- Interaktif V.D. ------------------------------------------------------------

@olculur("kayıt sayısını okuma")
def interaktif_kayit_sayisi(page):
    """Ekran altindaki 'Toplam Kayit Sayisi' degeri; bulunamazsa None."""
    for fr in cerceveler(page):
        try:
            loc = fr.get_by_text("Kayıt Sayısı", exact=False)
            for i in range(min(loc.count(), 3)):
                eslesme = KAYIT_SAYISI_DESENI.search(loc.nth(i).inner_text() or "")
                if eslesme:
                    return int(eslesme.group(1))
        except Exception:
            continue
    return None


@olculur("listenin dolmasını bekleme")
def listeyi_bekle(page, log, azami_saniye=120):
    """Sorgu sonrasi listenin dolmasini bekler (kayit sayisi > 0); sayiyi ya da None dondurur."""
    basla = time.time()
    son_bildirim = 0
    while time.time() - basla < azami_saniye:
        sayi = interaktif_kayit_sayisi(page)
        if sayi:
            yaz(f"    Liste doldu: {sayi} kayit ({int(time.time() - basla)} sn)", log)
            return sayi
        if fatura_yok_penceresini_kapat(page):
            yaz("    Luca: fatura bulunamadi", log)
            return 0
        if sayi == 0 and time.time() - basla > 10:
            yaz("    Liste bos (Toplam Kayit Sayisi: 0)", log)
            return 0
        gecen = time.time() - basla
        if gecen - son_bildirim >= 15:
            son_bildirim = gecen
            yaz(f"    ... liste bekleniyor ({int(gecen)} sn)", log)
        nabiz(page, 1000)
    yaz(f"    Liste {azami_saniye} sn icinde dolmadi", log)
    return None


def interaktif_listele(page, log):
    """'Mevcut E-Arşiv Faturalarını Listele' butonuna basar ve listenin gelmesini bekler."""
    baslangic = degisiklik_baslat(page)
    if dugmeye_bas(page, INTERAKTIF_LISTELE, sure=5000):
        yaz(f"    '{INTERAKTIF_LISTELE}' tiklandi", log)
        listenin_yuklenmesini_bekle(page, baslangic)
        return True
    yaz(f"    UYARI: '{INTERAKTIF_LISTELE}' butonu bulunamadi", log)
    return False


def interaktif_sorgula(page, araliklar, log, listeleme_araligi=None):
    """Interaktif Vergi Dairesi ekraninda e-arsiv faturalarini GIB servisinden ceker.

    Akis: tarih araligi -> "İnteraktif V.D'sinden E-Arşiv Faturalarını Sorgula"
    -> acilan pencerede "GİB Servis ile Sorgula" -> ayni isimli onay butonu.
    Luca ilk sorguda listeyi her zaman doldurmadigi icin iki kez calistirilir.
    Basarili sorgu sayisini dondurur.
    """
    calisan = 0
    for sira, (bas, bit) in enumerate(araliklar):
        # Luca ilk sorguda 9000/9001 hatasi verip bos donuyor; yalnizca ilk
        # aralikta iki kez sorulur, sonrakilerde tek sorgu yetiyor
        tekrar = INTERAKTIF_TEKRAR if sira == 0 else 1
        for tur in range(1, tekrar + 1):
            satiri_temizle()
            with olc("İnteraktif sorgu (diğer)", kapsayici=True):
                devam = _interaktif_turu(page, bas, bit, tur, tekrar, log)
            satiri_yaz(log, f"Aralık {bas} - {bit}")
            if not devam:
                return calisan
            calisan += 1

    # son sorgunun tarih filtresi ekranda kaliyor; listeleme tum donem icin yapilir
    if listeleme_araligi:
        acik_pencereleri_kapat(page, log)
        fatura_yok_penceresini_kapat(page)
        kutular = tarih_kutulari(page)
        if len(kutular) >= 2:
            tarih_araligi_yaz(kutular, *listeleme_araligi)
            yaz(f"    Listeleme araligi: {listeleme_araligi[0]} - {listeleme_araligi[1]}", log)

    # bu ekranda sorgu listeyi kendiliginden doldurmuyor
    interaktif_listele(page, log)
    return calisan


def _interaktif_turu(page, bas, bit, tur, tekrar, log):
    """Interaktif V.D. ekraninda tek sorgu; devam edilebilirse True."""
    acik_pencereleri_kapat(page, log)
    fatura_yok_penceresini_kapat(page, bekle=False)

    kutular = tarih_kutulari(page)
    if len(kutular) >= 2:
        tarih_araligi_yaz(kutular, bas, bit)
    else:
        yaz("    UYARI: tarih kutulari bulunamadi, Luca varsayilani kullanilacak", log)
    yaz(f"    Interaktif V.D. sorgusu ({bas} - {bit}) {tur}/{tekrar}", log)

    if not dugmeye_bas(page, INTERAKTIF_SORGU, sure=8000):
        yaz(f"    '{INTERAKTIF_SORGU}' butonuna basilamadi", log)
        return False

    _, pencere = diyalog_bekle(page, INTERAKTIF_CAPASI, azami_ms=4000)
    if pencere is None:
        # pencere yoksa onay butonu da yok; arac cubugu butonuna tekrar
        # basmamak icin burada durulur
        yaz("    UYARI: 'GİB Servis ile Sorgula' penceresi acilmadi", log)
        return False
    if radyo_sec(page, pencere, INTERAKTIF_SERVIS):
        yaz(f"    '{INTERAKTIF_SERVIS}' secildi", log)
    else:
        yaz(f"    UYARI: '{INTERAKTIF_SERVIS}' secenegi isaretlenemedi", log)
    if not pencerede_tikla(page, pencere, [INTERAKTIF_SORGU], sure=5000):
        yaz("    UYARI: pencerede sorgu butonu tiklanamadi", log)
        acik_pencereleri_kapat(page, log)
        return False

    # bu ekranda Islem Takip penceresi acilmiyor; listenin dolmasi beklenir
    listeyi_bekle(page, log, azami_saniye=min(AYAR["azami_saniye"], 120))
    acik_pencereleri_kapat(page, log)
    sayfa_durulsun(page, azami_ms=1500)
    return True


# --- iptal/itiraz -----------------------------------------------------------------

def _iptal_araligi(page, bas, bit, log, interaktif):
    """Tek tarih araligi icin iptal/itiraz sorgusu; islem_takibini_bekle sonucunu
    ya da (buton/pencere bulunamazsa) None dondurur."""
    acik_pencereleri_kapat(page, log)
    fatura_yok_penceresini_kapat(page, bekle=False)
    if not varsa_tikla(page, IPTAL_DUGME_ADAYLARI, sure=4000):
        yaz("    'GİB'den İptal/İtiraz Sorgula' butonu bulunamadi, atlandi", log)
        return None

    _, pencere = diyalog_bekle(page, IPTAL_CAPASI, azami_ms=4000)
    kutular = tarih_kutulari(page, pencere)
    if len(kutular) >= 2:
        yaz(f"    Iptal/itiraz sorgusu ({tarih_araligi_yaz(kutular, bas, bit)})", log)
    else:
        yaz("    UYARI: iptal/itiraz tarih kutulari bulunamadi, Luca varsayilani kullanilacak", log)

    eski_gunluk = islem_gunlugu(page)
    eski_bildirim = bildirim_yazisi(page)
    onay = pencerede_tikla(page, pencere, IPTAL_ONAY) if pencere is not None else None
    if not onay:
        # pencere taninmadiysa tam metinle ara; arac cubugu butonu farkli yazildigi
        # icin tam eslesme yanlislikla ona denk gelmez
        onay = varsa_tikla(page, IPTAL_ONAY, sure=4000)
    if not onay:
        yaz("    UYARI: iptal/itiraz sorgu butonu tiklanamadi", log)
        acik_pencereleri_kapat(page, log)
        return None

    # interaktif V.D. ekraninda Islem Takip penceresi hic acilmiyor; kisa
    # beklenir ama bilgi penceresi kontrolu (3 sn) yine de calissin
    sonuc = islem_takibini_bekle(page, log, azami_saniye=AYAR["azami_saniye"],
                                 durgunluk_saniye=AYAR["durgunluk_saniye"],
                                 pencere_bekleme=4 if interaktif else 12,
                                 eski_gunluk=eski_gunluk, eski_bildirim=eski_bildirim)
    acik_pencereleri_kapat(page, log)
    return sonuc


def iptal_itiraz_sorgula(page, araliklar, log, interaktif=False, bilgi=None):
    """Listedeki faturalar icin GIB'den iptal/itiraz durumunu sorgular.

    Luca akisi: arac cubugundan "GİB'den İptal/İtiraz Sorgula" -> acilan
    pencerede tarih araligi -> "İptal/İtiraz Sorgula". Sorgu tum listeye
    uygulandigi icin faturalari onceden isaretlemek gerekmiyor.
    Buradaki tarih, faturanin GIB'e raporlanma tarihidir.
    Basarili sorgu sayisini dondurur. bilgi (sozluk) verilirse GIB kimlik
    hatasi yuzunden sorgulanamayan araliklar bilgi["gib_hatasi"] listesine yazilir.
    """
    calisan = 0
    ust_uste_takildi = 0
    ust_uste_gib = 0
    hatali = []
    for bas, bit in araliklar:
        if ust_uste_takildi >= 2:
            yaz("    Iptal/itiraz sorgusu ust uste takildi, kalan tarih araliklari atlaniyor", log)
            break
        if ust_uste_gib >= 2:
            # hata her aralikta tekrarlaniyorsa gecici degildir (orn. firmanin GIB
            # bilgileri Luca'da hatali); kalan araliklari denemek bos
            yaz("    GİB iki aralikta ust uste kimlik hatasi verdi, kalan iptal/itiraz"
                " araliklari atlaniyor", log)
            hatali.append(f"{bas} sonrasi")
            break
        for tur in (1, 2):  # GIB gecici hata verirse ayni aralik bir kez daha sorulur
            satiri_temizle()
            with olc("İptal/itiraz sorgusu (diğer)", kapsayici=True):
                sonuc = _iptal_araligi(page, bas, bit, log, interaktif)
            satiri_yaz(log, f"İptal aralığı {bas} - {bit}")
            if sonuc is None:  # buton/pencere bulunamadi: bu ekranda devam etmek bos
                return calisan
            if sonuc == GIB_HATASI and tur == 1:
                yaz(f"    GİB hatasi sonrasi ayni aralik tekrar sorgulaniyor ({bas} - {bit})", log)
                geri_cekil(page, 5)
                continue
            break
        calisan += 1
        # Bir defalik takilma tek basina kalanini gecersiz saymaz (bazen sadece
        # ilk parca donuyor), ama ust uste ikinci kez olursa ekran yanit vermiyor demektir
        ust_uste_takildi = ust_uste_takildi + 1 if sonuc == TAKILDI else 0
        if sonuc == GIB_HATASI:
            ust_uste_gib += 1
            hatali.append(f"{bas} - {bit}")
        else:
            ust_uste_gib = 0
    if bilgi is not None and hatali:
        bilgi["gib_hatasi"] = hatali

    if interaktif:
        # bu ekranda Yenile listeyi bosaltiyor; liste yeniden listelenmeli
        yaz("    Liste yeniden listeleniyor (iptal/itiraz sonrasi)", log)
        interaktif_listele(page, log)
    else:
        listeyi_yenile(page, log, "iptal/itiraz sonrasi")
    return calisan
