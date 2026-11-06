"""Luca ekranlarından okunan verinin işlenmesi (tarayıcısız, test edilebilir saf fonksiyonlar).

Tarayıcıyı süren kısım luca_toplayici.py'dedir; bu dosya yalnızca "ne sorgulanacak" ve
"ekrandan okunan tablo nasıl yorumlanır" sorularına cevap verir.
"""

from datetime import timedelta

from .kurallar import BEYANNAMELER, donemler_uret, sade, tur_coz


def sorgu_plani(bugun, tatil, once=10, sonra=35, ucaylik_ay="bit"):
    """Son günü [bugün-once, bugün+sonra] aralığında olan dönemler için Luca'da yapılacak sorgular.

    Dönen her kayıt: tur, yil/ay (dönemin BİTTİĞİ yıl/ay: karşılaştırmada bu kullanılır) ve sorgu_yil/sorgu_ay
    (Luca filtresine yazılacak yıl/ay). Aylık dönemde ikisi aynıdır; 3 aylık dönemde Luca'nın "Beyanname Dönemi"
    ayını dönem başı mı sonu mu tuttuğu gerçek ekranda doğrulanmadı: ucaylik_ay="bit" (varsayılan) ya da "bas".
    """
    gorulen, plan = set(), []
    for tur, spec in BEYANNAMELER.items():
        for periyot in spec["periyotlar"]:
            for d in donemler_uret(tur, periyot, bugun - timedelta(days=once), bugun + timedelta(days=sonra), tatil):
                if ucaylik_ay == "bas" and periyot == "3aylik":
                    sy, sa = d.bas.year, d.bas.month
                else:
                    sy, sa = d.yil, d.ay
                anahtar = (tur, d.yil, d.ay, sy, sa)
                if anahtar not in gorulen:
                    gorulen.add(anahtar)
                    plan.append({"tur": tur, "yil": d.yil, "ay": d.ay, "sorgu_yil": sy, "sorgu_ay": sa})
    return sorted(plan, key=lambda p: (p["sorgu_yil"], p["sorgu_ay"], p["tur"]))


def secenek_esle(secenekler, tur):
    """Filtredeki 'Beyanname' listesinden bu türe karşılık gelen seçenekler (GGECICI ve KGECICI ikisi de GECICI)."""
    return [s.strip() for s in secenekler if s.strip() and tur_coz(s) == tur]


def durum_sec(secenekler):
    """'Beyanname Durum' listesinden onaylanmış beyannameleri getiren seçenek; yoksa None."""
    aday = [s.strip() for s in secenekler if s.strip()]
    for s in aday:
        if sade(s) == "ONAYLANMIS":
            return s
    for s in aday:
        d = sade(s)
        if "ONAY" in d and not any(k in d for k in ("ONAYLANMAMIS", "BEKL", "HATA")):
            return s
    return None


def _ara_baslik(satirlar):
    """(baslik satırı no, firma sütunu, vkn sütunu) ya da None."""
    for i, satir in enumerate(satirlar):
        hucre = [sade(h) for h in satir]
        firma = next((j for j, h in enumerate(hucre) if h == "MUKELLEF ADI" or h == "MUKELLEF UNVANI"
                      or h == "MUKELLEF" or h == "UNVAN"), None)
        if firma is None:
            firma = next((j for j, h in enumerate(hucre) if "MUKELLEF" in h and "ADI" in h), None)
        if firma is not None:
            vkn = next((j for j, h in enumerate(hucre) if "VKN" in h or "VERGI KIMLIK" in h or h == "VERGI NO"), None)
            return i, firma, vkn
    return None


def beyanname_satirlari(tablolar):
    """Listele'den sonra ekrandaki tablolardan firma satırları: [{"firma", "vkn"}].

    tablolar: her biri hücre metinlerinin satır listesi olan tablolar. Başlık ve veri aynı tabloda ya da
    (ızgara bileşenlerinde sık görüldüğü gibi) ayrı tablolarda olabilir; veri satırlarının başında sıra no ya da
    onay kutusu gibi ek sütunlar varsa başlık o kadar sağa hizalanır. Başlık hiç bulunamazsa None döner.
    """
    for t_no, satirlar in enumerate(tablolar):
        b = _ara_baslik(satirlar)
        if b is None:
            continue
        i, firma_j, vkn_j = b
        baslik = satirlar[i]
        veri = satirlar[i + 1:]
        if not veri:
            # başlık ayrı tabloda: başlığın genişliğine uyan (her satırı en az o kadar hücreli) en çok satırlı tablo veridir;
            # menü gibi dar tablolar böylece veri sanılmaz
            digerleri = [x for k, x in enumerate(tablolar) if k != t_no and x and all(len(r) >= len(baslik) for r in x)]
            veri = max(digerleri, key=len) if digerleri else []
        sonuc = []
        for satir in veri:
            kayma = max(0, len(satir) - len(baslik))
            if firma_j + kayma >= len(satir):
                continue
            ad = satir[firma_j + kayma].strip()
            if not ad or sade(ad) in ("MUKELLEF ADI", "TOPLAM") or sade(satir[0]).startswith("TOPLAM"):
                continue
            vkn = ""
            if vkn_j is not None and vkn_j + kayma < len(satir):
                vkn = "".join(ch for ch in satir[vkn_j + kayma] if ch.isdigit())
            sonuc.append({"firma": ad, "vkn": vkn if len(vkn) in (10, 11) else ""})
        return sonuc
    return None


def musterileri_birlestir(listeler):
    """Yıl listelerini (en yeniden eskiye) tek listede toplar; aynı firma (VKN ya da ad) yalnızca bir kez, yeni yıl kazanır."""
    gorulen, sonuc = set(), []
    for liste in listeler:
        for k in liste:
            anahtar = (k.get("vkn") or "").strip() or sade(k.get("ad") or k.get("unvan"))
            if anahtar and anahtar not in gorulen:
                gorulen.add(anahtar)
                sonuc.append(k)
    return sonuc
