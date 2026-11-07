"""Beklenen beyannameleri hesaplar, Luca'dan gelen verilenlerle karşılaştırır, uyarı metinlerini üretir."""

import html
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta

from .kurallar import (BEYANNAMELER, donem_baslangici, donem_bitisi, donemler_uret, onayli_mi, sade, tur_coz)

VARSAYILAN_AYAR = {"KDV1": "aylik", "MPHB": "auto", "GECICI": "3aylik", "KDV2": "yok", "POSET": "yok", "KONAKLAMA": "yok", "KV": "auto", "GV": "auto", "sgk": "auto", "onayli": False, "isyeri": ""}

# Hangi kalan günde hangi saatlerde uyarı gider (kalan < 0: süre geçmiş, yalnızca sabah).
SLOTLAR = ("09:00", "13:00", "17:00", "20:30", "21:00", "22:30")
KURAL = {
    7: {"09:00"},
    3: {"09:00"},
    2: {"09:00"},
    1: {"09:00", "17:00"},
    0: {"09:00", "13:00", "17:00", "20:30", "21:00", "22:30"},
}
GECIKME_GUN = 5          # süre geçtikten sonra kaç gün her sabah hatırlatılır


@dataclass
class Madde:
    mid: str
    ad: str
    hesap: str
    isyeri: str
    tur: str
    donem: str            # "2026-10" (dönem bitişi)
    etiket: str
    son_gun: date
    kalan: int
    durum: str            # verildi | onaysiz | eksik | sgk_eksik (MUHSGK var, SGK e-Bildirgesi yok) | muaf
    ayar_onayli: bool
    kapanis_donemi: bool

    def sozluk(self):
        d = asdict(self)
        d["son_gun"] = self.son_gun.isoformat()
        d["tur_ad"] = BEYANNAMELER[self.tur]["ad"]
        return d


def tarih_coz(s):
    """'GG/AA/YYYY' ya da 'YYYY-AA-GG' -> date; boş/bozuksa None."""
    s = str(s or "").strip()
    if not s:
        return None
    try:
        if "-" in s[:5]:
            return date.fromisoformat(s[:10])
        g, a, y = s.replace(".", "/").split("/")[:3]
        return date(int(y), int(a), int(g))
    except (ValueError, TypeError):
        return None


def ayar_al(ayarlar, mid):
    a = dict(VARSAYILAN_AYAR)
    a.update((ayarlar.get("mukellef") or {}).get(mid, {}))
    return a


def ayni_firma(m, r):
    """Beyanname kaydı bu mükellefe mi ait? Sırayla: VKN/TCKN (varsa kesin), Luca kısa adı (Müşteri Listesi'ndeki ad ile
    birebir), unvan. VKN önce gelir: tasfiye halindeki şirketin eski ve yeni kaydı aynı VKN'yi taşır, beyanname ikisinde
    de görünür (eski kaydın kapanışı nedeniyle önemi yoktur)."""
    if r.get("hesap", m["hesap"]) != m["hesap"]:
        return False
    kimlikler = {str(r.get("vkn") or "").strip(), str(r.get("tckn") or "").strip()} - {"", "0"}
    if kimlikler and m.get("vkn"):
        return str(m["vkn"]).strip() in kimlikler
    if sade(r.get("kisa_ad")) and sade(r.get("kisa_ad")) == sade(m.get("ad")):
        return True
    rn = sade(r.get("firma"))
    if not rn:
        return False
    for n in {sade(m.get("ad")), sade(m.get("unvan"))} - {""}:
        if n == rn or (min(len(n), len(rn)) >= 8 and (n.startswith(rn) or rn.startswith(n))):
            return True
    return False


def sgk_tamam(r):
    """MUHSGK kaydında SGK (e-Bildirge) kısmı tamam mı: kayıt onaylı, en az bir e-Bildirge var ve durumu hatalı ("0") ya da
    iptal ("6") değil (rozet: yeşil = 2/3, kırmızı = 0, gri = 6)."""
    try:
        sayi = int(r.get("ebildirge") or 0)
    except (TypeError, ValueError):
        sayi = 0
    return onayli_mi(r.get("durum")) and sayi >= 1 and str(r.get("sgk_durum") or "") not in ("0", "6")


def _ay_no(y, a):
    return y * 12 + a


def _kayit_araligi(r):
    """Kaydın (başlangıç ay no, bitiş ay no); bitiş yoksa None, başlangıç bilinmiyorsa başlangıç None (aylık/3 aylık ayrılamaz)."""
    y, a = donem_bitisi(r)
    if not y:
        return None
    by, ba = donem_baslangici(r)
    return (_ay_no(by, ba) if by else None), _ay_no(y, a)


def _donem_kayitlari(kayitlar, d):
    """Firmanın bu türdeki kayıtlarından (kayit, bas, bit) d dönemini karşılayanlar: ("tam" | "kapsam" | "", liste).

    * tam: aynı aralıktaki kayıt (aylık beklenene aylık, 3 aylık beklenene 3 aylık). Başlangıç bilinmiyorsa yalnızca bitişe bakılır.
    * kapsam (aylık beklenen ay): 3 aylık kayıt o ayı kapsıyor VE kapsadığı dönemde sonraki bir ay için aylık kayıt var; yani firma
      ay ortasında aylığa geçmiş, geçmeden önceki ay 3 aylık beyanda verilmiştir (örn. Temmuz 3 aylıkta, Ağustos-Eylül aylık).
    * kapsam (3 aylık beklenen dönem): üç ayın her biri için aylık kayıt var.
    Eylül'deki 3 aylık kayıt, Eylül AYLIK beklentisini tek başına karşılamaz."""
    d_bas, d_bit = _ay_no(d.bas.year, d.bas.month), _ay_no(d.bit.year, d.bit.month)
    uz = d_bit - d_bas + 1
    tam = [r for r, b, e in kayitlar if e == d_bit and (b is None or b == d_bas)]
    if tam:
        return "tam", tam
    aylik = [(r, e) for r, b, e in kayitlar if b is not None and b == e]
    if uz == 1:
        kap = [r for r, b, e in kayitlar if b is not None and e - b >= 2 and b <= d_bit < e and any(d_bit < x <= e for _, x in aylik)]
        return ("kapsam", kap) if kap else ("", [])
    ay_kayit = {x: r for r, x in aylik if d_bas <= x <= d_bit}
    if len(ay_kayit) == uz:
        return "kapsam", list(ay_kayit.values())
    return "", []


def degerlendir(mukellefler, ayarlar, beyannameler, bugun, tatil, once=10, sonra=35):
    """Pencere içindeki (bugün-once .. bugün+sonra) tüm beklenen beyannameler ve durumları."""
    bas, bit = bugun - timedelta(days=once), bugun + timedelta(days=sonra)
    tur_kayitlari = defaultdict(list)
    for b in beyannameler:
        tur = tur_coz(b.get("tur"))
        if tur and _kayit_araligi(b):
            tur_kayitlari[tur].append(b)
    muaf = {(x.get("id"), x.get("tur"), x.get("donem")) for x in (ayarlar.get("muaf") or [])}
    mphb_kayitlari = tur_kayitlari.get("MPHB", [])
    sonuc = []
    for m in mukellefler:
        ay = ayar_al(ayarlar, m["id"])
        # SGK: ayar "var" ise her MUHSGK'da e-Bildirge beklenir; "auto"da firmanın SGK dosyası (işyeri tanımı) varsa, liste okunamadıysa
        # e-Bildirgeli bir MUHSGK geçmişi varsa (çalışanı var) beklenir; "yok"ta beklenmez. Çalışanı olan firmada e-Bildirge yoksa prim hizmet bildirgesi verilmemiştir.
        sgk_ayar = ay.get("sgk", "auto")
        onbellek = {}

        def sgk_beklenir(m=m, sgk_ayar=sgk_ayar, onbellek=onbellek):
            if "v" not in onbellek:
                if sgk_ayar == "var":
                    onbellek["v"] = True
                elif sgk_ayar == "yok":
                    onbellek["v"] = False
                elif m.get("sgk_isyeri") is not None:
                    onbellek["v"] = m["sgk_isyeri"] > 0                      # SGK dosya listesi okunabildi: kesin bilgi
                else:                                                        # liste okunamadıysa geçmiş e-Bildirge kaydı
                    onbellek["v"] = any(sgk_tamam(r) for r in mphb_kayitlari if ayni_firma(m, r))
            return onbellek["v"]
        acilis, kapanis = tarih_coz(m.get("acilis")), tarih_coz(m.get("kapanis"))
        for tur in BEYANNAMELER:
            periyot = ay.get(tur, "yok")
            if periyot in (None, "", "yok"):
                continue
            if periyot == "auto":
                if tur == "MPHB":                      # SGK dosyası (çalışanı) olan aylık, olmayan 3 aylık verir
                    periyot = "aylik" if sgk_beklenir() else "3aylik"
                elif tur == "KV":                      # yıllık: tüzel kişi (TC kimlik numarası yok) Kurumlar vergisi verir
                    periyot = "yillik" if not m.get("tc") else "yok"
                elif tur == "GV":                      # yıllık: şahıs (TC kimlik numarası var) Gelir vergisi verir
                    periyot = "yillik" if m.get("tc") else "yok"
                if periyot == "yok":
                    continue
            firma_kayitlari = None
            for d in donemler_uret(tur, periyot, bas, bit, tatil):
                if (acilis and d.bit < acilis) or (kapanis and d.bas > kapanis):
                    continue
                if firma_kayitlari is None:
                    firma_kayitlari = [(r,) + _kayit_araligi(r) for r in tur_kayitlari.get(tur, []) if ayni_firma(m, r)]
                tip, kayitlar = _donem_kayitlari(firma_kayitlari, d)
                onayli = [r for r in kayitlar if onayli_mi(r.get("durum"))]
                if onayli:
                    durum = "verildi"
                    # SGK (e-Bildirge) kontrolü yalnızca aynı aralıktaki kayıtta: 3 aylık beyanın kapsadığı önceki ay SGK'sızdır
                    if tur == "MPHB" and tip == "tam" and sgk_beklenir() and not any(sgk_tamam(r) for r in onayli):
                        durum = "sgk_eksik"
                elif kayitlar:
                    durum = "onaysiz"
                else:
                    durum = "eksik"
                if durum in ("eksik", "sgk_eksik") and (m["id"], tur, d.anahtar) in muaf:
                    durum = "muaf"
                sonuc.append(Madde(
                    mid=m["id"], ad=m.get("ad") or m.get("unvan") or m["id"], hesap=m["hesap"],
                    isyeri=ay.get("isyeri", ""), tur=tur, donem=d.anahtar, etiket=d.etiket,
                    son_gun=d.son_gun, kalan=(d.son_gun - bugun).days, durum=durum,
                    ayar_onayli=bool(ay.get("onayli")),
                    kapanis_donemi=bool(kapanis and d.bas <= kapanis <= d.bit)))
    sonuc.sort(key=lambda x: (x.son_gun, x.tur, x.ad))
    return sonuc


def uyari_gerekli(kalan, slot):
    if kalan < 0:
        return -kalan <= GECIKME_GUN and slot == SLOTLAR[0]
    return slot in KURAL.get(kalan, ())


def _bas(kalan, slot):
    if kalan < 0:
        return "❌ SÜRE GEÇTİ – ceza riski"
    if kalan == 0:
        if slot >= "21:00":
            return "🚨 SON UYARI – bugün son gün"
        if slot >= "20:30":
            return "🚨 SON SAATLER – bugün son gün"
        return "⚠️ BUGÜN SON GÜN"
    if kalan == 1:
        return "⏰ Yarın son gün"
    return f"⏰ Son güne {kalan} gün var"


def _gun_metni(m):
    if m.kalan < 0:
        return f"{-m.kalan} gün geçti"
    return "bugün" if m.kalan == 0 else f"{m.kalan} gün kaldı"


def birli_mi(ad):
    """Firma adı "1" ile başlıyor mu (ofiste ayrı bir grup olarak tutulan firmalar)."""
    return str(ad or "").strip().startswith("1")


def bolumlere_ayir(maddeler):
    """[(başlık, maddeler)]: her hesap ayrı, her hesapta adı "1" ile başlayanlar ayrı. Boş bölümler yer almaz; sıra: ofis, işletme, diğer."""
    sira_hesap = {"ofis": 0, "isletme": 1}
    gruplar = defaultdict(list)
    for m in maddeler:
        gruplar[(m.hesap, birli_mi(m.ad))].append(m)
    sonuc = []
    for (hesap, birli) in sorted(gruplar, key=lambda k: (sira_hesap.get(k[0], 9), k[0], k[1])):
        ad = {"ofis": "OFİS", "isletme": "İŞLETME"}.get(hesap, str(hesap).upper())
        sonuc.append((ad + (" · 1 ile başlayanlar" if birli else ""), gruplar[(hesap, birli)]))
    return sonuc


def mesaj_olustur(maddeler, slot, veri_zamani=None, veri_hatasi=None, veri_eski=False, ek_uyari=None, esik=None):
    """Telegram (HTML) metinleri. Uyarı gerekmiyorsa boş liste döner.
    Aynı kalan günü olan eksikler tek başlık altında; mükellef listesi tür+dönem bazında.
    esik verilirse (elle istenen özet) slot kuralı yok sayılır: süresi geçmemiş/yeni geçmiş ve en çok `esik` gün kalan tüm eksikler listelenir."""
    e = html.escape
    if esik is None:
        acik = [m for m in maddeler if m.durum in ("eksik", "onaysiz", "sgk_eksik") and uyari_gerekli(m.kalan, slot)]
    else:
        acik = [m for m in maddeler if m.durum in ("eksik", "onaysiz", "sgk_eksik") and -GECIKME_GUN <= m.kalan <= esik]
    satirlar = []
    if acik:
        grup = defaultdict(list)
        for m in acik:
            grup[m.kalan].append(m)
        for kalan in sorted(grup):
            satirlar.append(f"<b>{e(_bas(kalan, slot))}</b>")
            alt = defaultdict(list)
            for m in grup[kalan]:
                alt[(m.tur, m.etiket, m.son_gun)].append(m)
            for (tur, etiket, son), ms in alt.items():
                satirlar.append(f"\n<b>{e(BEYANNAMELER[tur]['ad'])} – {e(etiket)}</b> "
                                f"(son gün {son:%d.%m.%Y}, {_gun_metni(ms[0])}) – {len(ms)} mükellef")
                for m in sorted(ms, key=lambda x: x.ad):
                    etk = []
                    if m.durum == "onaysiz":
                        etk.append("gönderilmiş ama ONAYLANMAMIŞ")
                    elif m.durum == "sgk_eksik":
                        etk.append("MUHSGK verilmiş ama SGK bildirgesi (E-Bil.) YOK")
                    if not m.ayar_onayli:
                        etk.append("ayar onaysız")
                    if m.kapanis_donemi:
                        etk.append("kapanış dönemi, süre farklı olabilir")
                    if m.isyeri:
                        etk.append(m.isyeri)
                    satirlar.append(" • " + e(m.ad) + (f" <i>({e(', '.join(etk))})</i>" if etk else ""))
            satirlar.append("")
    parcalar = []
    if veri_hatasi:
        parcalar.append("⚠️ <b>LUCA'DAN VERİ ALINAMADI</b> – bu kontrol güncel veriye dayanmıyor, elle bakın.\n"
                        f"Hata: {e(str(veri_hatasi)[:300])}")
    elif veri_eski:
        parcalar.append("⚠️ Veri 24 saatten eski; sonuçlara güvenmeyin.")
    if ek_uyari:
        parcalar.append("⚠️ " + e(ek_uyari))
    if not satirlar and not parcalar:
        return []
    if veri_zamani:
        satirlar.append(f"<i>Luca verisi: {e(str(veri_zamani))} itibarıyla</i>")
    return _parcala("\n".join(parcalar + [""] * bool(parcalar and satirlar) + satirlar).strip())


def gunluk_ozet(maddeler, veri_zamani, bugun):
    """09:00'da her gün giden kısa 'sistem çalışıyor' mesajı (sessizlik = sistem öldü olmasın)."""
    e = html.escape
    yakin = [m for m in maddeler if m.kalan >= 0 and m.durum != "muaf"]
    if not yakin:
        return f"✅ Beyanname takip çalışıyor. Önümüzdeki günlerde son günü olan beyanname yok. (Veri: {e(str(veri_zamani))})"
    ilk = min(m.son_gun for m in yakin)
    ayni = [m for m in yakin if m.son_gun == ilk]
    verilen = sum(m.durum == "verildi" for m in ayni)
    return (f"✅ Beyanname takip çalışıyor. En yakın son gün {ilk:%d.%m.%Y} ({(ilk - bugun).days} gün): "
            f"{len(ayni)} beyannameden {verilen} tanesi verilmiş, {len(ayni) - verilen} eksik. "
            f"(Veri: {e(str(veri_zamani))})")


def _parcala(metin, sinir=3800):
    if len(metin) <= sinir:
        return [metin]
    sonuc, cur = [], ""
    for satir in metin.split("\n"):
        if len(cur) + len(satir) + 1 > sinir:
            sonuc.append(cur)
            cur = ""
        cur += satir + "\n"
    if cur.strip():
        sonuc.append(cur)
    return sonuc


def mukellef_normalize(kayit, hesap):
    """Luca müşteri kaydı (musteri_listesi.py biçimi) -> bu programın mükellef kaydı."""
    ad = (kayit.get("ad") or kayit.get("kisa_ad") or "").strip()
    unvan = (kayit.get("unvan") or "").strip()
    vkn = str(kayit.get("vkn") or kayit.get("tc") or "").strip()
    # Luca şirket kimliği benzersiz ve değişmezdir; aynı VKN'yi taşıyan iki kayıt (tasfiye) ayrı mükelleftir
    anahtar = str(kayit.get("sirket_id") or "").strip() or vkn or sade(ad or unvan)
    ac, ka = tarih_coz(kayit.get("acilis")), tarih_coz(kayit.get("kapanis"))
    return {"id": f"{hesap}:{anahtar}", "hesap": hesap, "sirket_id": str(kayit.get("sirket_id") or ""),
            "aciklama": (kayit.get("aciklama") or "").strip(), "sgk_isyeri": kayit.get("sgk_isyeri"), "tc": str(kayit.get("tc") or "").strip(), "ad": ad or unvan, "unvan": unvan, "vkn": vkn,
            "vergi_dairesi": kayit.get("vergi_dairesi") or "",
            "acilis": ac.isoformat() if ac else "", "kapanis": ka.isoformat() if ka else ""}
