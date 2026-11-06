"""Beklenen beyannameleri hesaplar, Luca'dan gelen verilenlerle karşılaştırır, uyarı metinlerini üretir."""

import html
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta

from .kurallar import (BEYANNAMELER, donem_bitisi, donemler_uret, onayli_mi, sade, tur_coz)

VARSAYILAN_AYAR = {"KDV1": "aylik", "MPHB": "aylik", "GECICI": "3aylik", "onayli": False, "isyeri": ""}

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
    durum: str            # verildi | onaysiz | eksik | muaf
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


def degerlendir(mukellefler, ayarlar, beyannameler, bugun, tatil, once=10, sonra=35):
    """Pencere içindeki (bugün-once .. bugün+sonra) tüm beklenen beyannameler ve durumları."""
    bas, bit = bugun - timedelta(days=once), bugun + timedelta(days=sonra)
    idx = defaultdict(list)
    for b in beyannameler:
        tur = tur_coz(b.get("tur"))
        y, a = donem_bitisi(b)
        if tur and y:
            idx[(tur, y, a)].append(b)
    muaf = {(x.get("id"), x.get("tur"), x.get("donem")) for x in (ayarlar.get("muaf") or [])}
    sonuc = []
    for m in mukellefler:
        ay = ayar_al(ayarlar, m["id"])
        acilis, kapanis = tarih_coz(m.get("acilis")), tarih_coz(m.get("kapanis"))
        for tur in BEYANNAMELER:
            periyot = ay.get(tur, "yok")
            if periyot in (None, "", "yok"):
                continue
            for d in donemler_uret(tur, periyot, bas, bit, tatil):
                if (acilis and d.bit < acilis) or (kapanis and d.bas > kapanis):
                    continue
                kayitlar = [r for r in idx.get((tur, d.yil, d.ay), []) if ayni_firma(m, r)]
                if any(onayli_mi(r.get("durum")) for r in kayitlar):
                    durum = "verildi"
                elif kayitlar:
                    durum = "onaysiz"
                elif (m["id"], tur, d.anahtar) in muaf:
                    durum = "muaf"
                else:
                    durum = "eksik"
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


def mesaj_olustur(maddeler, slot, veri_zamani=None, veri_hatasi=None, veri_eski=False, ek_uyari=None):
    """Telegram (HTML) metinleri. Uyarı gerekmiyorsa boş liste döner.
    Aynı kalan günü olan eksikler tek başlık altında; mükellef listesi tür+dönem bazında."""
    e = html.escape
    acik = [m for m in maddeler if m.durum in ("eksik", "onaysiz") and uyari_gerekli(m.kalan, slot)]
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
            "aciklama": (kayit.get("aciklama") or "").strip(), "ad": ad or unvan, "unvan": unvan, "vkn": vkn,
            "vergi_dairesi": kayit.get("vergi_dairesi") or "",
            "acilis": ac.isoformat() if ac else "", "kapanis": ka.isoformat() if ka else ""}
