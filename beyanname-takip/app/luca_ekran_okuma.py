"""Luca ekranlarından okunan verinin işlenmesi (tarayıcısız, test edilebilir saf fonksiyonlar).

Tarayıcıyı süren kısım luca_toplayici.py'dedir; bu dosya yalnızca "ne sorgulanacak" ve
"ekrandan okunan tablo nasıl yorumlanır" sorularına cevap verir.
"""

import re
from datetime import date, timedelta
from html.parser import HTMLParser

from .kurallar import BEYANNAMELER, donemler_uret, onayli_mi, sade


# Luca "GİB Beyanname Takip" ekranının listesi (beyan_listele.jq) JSON döner:
#   {"success": "243 adet beyanname kaydı listelendi.", "data": [{beyannameKodu, beyanDonem, donemBas/donemBit (GGAAYYYY),
#    beyanDurum (0 Hatalı, 2 Onaylanmış, 3 İptal Edilmiş), beyanDurumAciklama, vkn, tckn, mukellefAdi, sirketKisaAd,
#    yuklemeZamani, ...}]}
# sirketKisaAd, Müşteri Listesi'ndeki "Kısa Adı" ile birebir aynıdır.
_DURUM_KODLARI = {"2": "Onaylanmış", "0": "Hatalı", "3": "İptal Edilmiş"}


def beyanname_json_kayitlari(cevap):
    """beyan_listele.jq yanıtından (kayıtlar, sayfanın yazdığı toplam ya da None).

    Her kayıt: firma (unvan), kisa_ad, vkn, tckn, tur (beyannameKodu: KDV1, MUHSGK, KGECICI, ...), donem ("AA/YYYY" =
    dönemin BİTTİĞİ ay), donem_bas (dönemin başladığı ay; aylık ile 3 aylık kaydı ayırır), durum (metin), yukleme. Dönem, 3 aylık beyannamelerde de dönem bitişinden okunur (donemBit)."""
    veri = (cevap or {}).get("data")
    if not isinstance(veri, list):
        raise ValueError("yanıtta 'data' listesi yok")
    m = re.search(r"(\d+)\s+adet", str((cevap or {}).get("success") or ""))
    kayitlar = []
    for r in veri:
        bit = re.sub(r"\D", "", str(r.get("donemBit") or ""))
        bas = re.sub(r"\D", "", str(r.get("donemBas") or ""))
        donem = f"{bit[2:4]}/{bit[4:8]}" if len(bit) == 8 else str(r.get("beyanDonem") or "")
        donem_bas = f"{bas[2:4]}/{bas[4:8]}" if len(bas) == 8 else ""            # aylık ile 3 aylığı ayırmak için
        durum = (r.get("beyanDurumAciklama") or "").strip() or _DURUM_KODLARI.get(str(r.get("beyanDurum")), f"Bilinmeyen durum ({r.get('beyanDurum')})")
        tckn = str(r.get("tckn") or "").strip()
        kayitlar.append({"firma": (r.get("mukellefAdi") or "").strip(), "kisa_ad": (r.get("sirketKisaAd") or "").strip(),
                         "vkn": str(r.get("vkn") or "").strip(), "tckn": "" if tckn in ("", "0") else tckn,
                         "tur": (r.get("beyannameKodu") or "").strip(), "donem": donem, "donem_bas": donem_bas, "durum": durum,
                         "yukleme": r.get("yuklemeZamani") or "",
                         # SGK (e-Bildirge) kısmı: ekrandaki "E-Bil." sütunu. Yalnızca MUHSGK kayıtlarında gelir; anlamları henüz
                         # kurala bağlanmadı (muhSgkDurum görülen değerler: "2", "3", "0", "6")
                         "ebildirge": r.get("ebildirgeSayisi"), "sgk_durum": str(r.get("muhSgkDurum") or "")})
    return kayitlar, (int(m.group(1)) if m else None)


def onayli_kayitlar(kayitlar):
    """Yalnızca onaylanmış beyannameler: hatalı, iptal edilmiş ve tanınmayan durumlu kayıtlar HİÇ okunmaz (yok sayılır). Bir dönemin
    yalnızca böyle kayıtları varsa o dönem "verilmemiş" (eksik) sayılır."""
    return [k for k in kayitlar if onayli_mi(k.get("durum"))]


def sgk_isyerleri_say(satirlar):
    """"E-Bildirge Giriş Dosyası Tanımlama" listesinden {Luca şirket kimliği: SGK işyeri sayısı}. Satırlar köprünün tarayıcıdan
    çıkardığı {sirket_id, isyeri_id, etiket, dolu} kayıtlarıdır (dolu: kullanıcı adı girilmiş). Şifre alanları HİÇ okunmaz."""
    sonuc = {}
    for r in satirlar or []:
        sid = str(r.get("sirket_id") or "").strip()
        if sid and r.get("dolu"):
            sonuc[sid] = sonuc.get(sid, 0) + 1
    return sonuc


def gib_getir_araligi(bugun, gun=15):
    """"GİB'den Getir" penceresine yazılacak yükleme tarihi aralığı: son `gun` gün (en çok 31; pencere en fazla 31 günlük
    aralık kabul eder) ve iki tarih AYNI YIL içinde olmalıdır: yıl başından öncesi kırpılır."""
    gun = max(1, min(int(gun), 31))
    bas = bugun - timedelta(days=gun - 1)
    return max(bas, date(bugun.year, 1, 1)), bugun


def gib_araligi_dogrula(bas, bit, bugun):
    """Elle seçilen "GİB'den Getir" aralığını doğrular (GİB Beyanname Sorgula penceresinin kuralları): iki tarih de dolu, başlangıç
    bitişten sonra olamaz, bitiş bugünden ileri olamaz, aynı takvim yılı içinde ve en çok 31 gün. Hata: ValueError (Türkçe)."""
    if not bas or not bit:
        raise ValueError("GİB aralığı için başlangıç ve bitiş tarihlerinin ikisi de gerekli")
    if bas > bit:
        raise ValueError("Başlangıç tarihi bitiş tarihinden sonra olamaz")
    if bit > bugun:
        raise ValueError("Bitiş tarihi bugünden ileri olamaz")
    if bas.year != bit.year:
        raise ValueError("GİB sorgusu aynı takvim yılı içinde olmalı (yıl sınırını aşan aralığı iki ayrı sorguyla yapın)")
    if (bit - bas).days + 1 > 31:
        raise ValueError("GİB sorgusu en çok 31 günlük olabilir")
    return bas, bit


def yukleme_araligi(bugun, tatil, once=10, sonra=35, pay=3):
    """Beyanname Takip'te sorgulanacak paket yükleme tarihi aralığı: son günü [bugün-once, bugün+sonra] aralığında olan en eski
    dönemin bitişinden (bir beyanname dönem bitmeden verilemez) bugüne. Dönem/tür/durum filtresi kullanılmaz: tümü gelir."""
    en_eski = bugun
    for tur, spec in BEYANNAMELER.items():
        for periyot in spec["periyotlar"]:
            if periyot == "auto":                  # gerçek periyotlar (aylık/3 aylık) zaten ayrıca taranır
                continue
            for d in donemler_uret(tur, periyot, bugun - timedelta(days=once), bugun + timedelta(days=sonra), tatil):
                en_eski = min(en_eski, d.bit)
    return en_eski - timedelta(days=pay), bugun


def musteri_anahtari(k):
    """Firmanın kimliği: Luca şirket kimliği; yoksa VKN + kısa ad."""
    return (str(k.get("sirket_id") or "").strip()
            or f"{(k.get('vkn') or '').strip()}|{sade(k.get('ad') or k.get('unvan'))}")


def musteri_yillari(bugun, ayar=None):
    """Müşteri listesinin hangi yıl(lar)la filtreleneceği. LUCA_MUSTERI_YILI: 'otomatik' (varsayılan: yalnızca bu yıl),
    'yok' (filtresiz) ya da '2027,2026' (açık liste).

    DİKKAT: Ocak'ta henüz yeni yılın dönemi açılmamış bir firmanın Aralık dönemi beyannameleri (KDV 28 Ocak, MUHSGK
    26 Ocak) ve 4. dönem geçici vergisi (17 Şubat) takip dışı kalır; gerekirse Ocak-Mart için '2027,2026' yazın."""
    a = (ayar or "otomatik").strip().lower()
    if a in ("yok", "0", "hayir", "hayır"):
        return []
    if a in ("", "otomatik"):
        return [bugun.year]
    return [int(x) for x in a.split(",") if x.strip().isdigit()]


def musterileri_birlestir(listeler):
    """Birden çok listeyi (öncelik sırasıyla) tek listede toplar; aynı firma yalnızca bir kez, öndeki liste kazanır.

    Firma anahtarı Luca'nın şirket kimliğidir (yoksa VKN + kısa ad). Yalnızca VKN KULLANILMAZ: tasfiye halindeki
    şirketlerde eski (kapanmış) ve yeni kayıt aynı VKN'yi taşır ve ikisi de ayrı mükelleftir.
    """
    gorulen, sonuc = set(), []
    for liste in listeler:
        for k in liste:
            anahtar = musteri_anahtari(k)
            if anahtar.strip("|") and anahtar not in gorulen:
                gorulen.add(anahtar)
                sonuc.append(k)
    return sonuc


_HUCRE = {"kisa-ad-td": "ad", "uzun-ad-td": "unvan", "vergi-dairesi-td": "vergi_dairesi", "vergi-no-td": "vkn",
          "tc-kimlik-no-td": "tc", "aciklama-td": "aciklama", "kurulus-tarihi-td": "acilis", "kapanis-tarihi-td": "kapanis"}


class _MusteriHtml(HTMLParser):
    """Luca 'Müşteri Listesi' (listSirketAction.do) sayfasındaki satırları sınıf adlarından okur."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.kayitlar, self._satir, self._alan = [], None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        sinif = (a.get("class") or "").split()
        if tag == "tr" and "satir" in sinif:
            self._satir = {"sirket_id": "", **{v: "" for v in _HUCRE.values()}}
            m = re.search(r"sec\(\s*this\s*,\s*'([^']*)'", a.get("onclick") or "")
            if m:
                self._satir["sirket_id"] = m.group(1).strip()
        elif self._satir is not None:
            if tag == "input" and a.get("name") == "sirket_id" and a.get("value") and not self._satir["sirket_id"]:
                self._satir["sirket_id"] = a["value"].strip()
            if tag == "td":
                self._alan = next((_HUCRE[c] for c in sinif if c in _HUCRE), None)

    def handle_endtag(self, tag):
        if tag == "td":
            self._alan = None
        elif tag == "tr" and self._satir is not None:
            self.kayitlar.append(self._satir)
            self._satir = None

    def handle_data(self, data):
        if self._satir is not None and self._alan:
            self._satir[self._alan] += data


def musteri_html_filtre(html):
    """Sayfanın sonunda yazdığı uygulanmış filtre: {'yil','durum','sinif'} (yazılmamışsa None). Filtresiz sayfada hepsi None."""
    sonuc = {}
    for ad, anahtar in (("YIL", "yil"), ("DURUM", "durum"), ("SINIF", "sinif")):
        m = re.search(r'byId\("%s"\)\.value\s*=\s*"([^"]*)"' % ad, html or "")
        sonuc[anahtar] = m.group(1) if m else None
    return sonuc


def musteri_html_oku(html):
    """Müşteri Listesi sayfasının HTML'inden (kayıtlar, sayfanın yazdığı 'Kayıt Sayısı' ya da None).

    Kayıtlar: sirket_id, ad (Kısa Adı), unvan (Uzun Adı), vergi_dairesi, vkn, tc, aciklama, acilis (Kuruluş Tarihi),
    kapanis (Kapanış Tarihi; tarihler GG/AA/YYYY). Boşluklar temizlenir; ad ve sirket_id'si boş satırlar atılır.
    """
    p = _MusteriHtml()
    p.feed(html or "")
    p.close()
    kayitlar = []
    for k in p.kayitlar:
        k = {a: re.sub(r"\s+", " ", v).strip() for a, v in k.items()}
        if k["ad"] or k["sirket_id"]:
            kayitlar.append(k)
    m = re.search(r"Kay[ıi]t\s+Say[ıi]s[ıi]\s*:\s*(\d+)", html or "")
    return kayitlar, (int(m.group(1)) if m else None)
