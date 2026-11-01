# -*- coding: utf-8 -*-
"""Luca > Defter Beyan Sistemi (2. sinif / isletme defteri) kontrol ve gonderme sonuclari.

Tarayici gerektirmeyen mantik: gonderme penceresinin yazisini siniflama, tutar okuma, sonuc dosyasi
(cikti/defter-beyan.json) ve firma bazinda durum.

Sonuc kaydi (firma basina):
    {"firma", "donem", "islem": "kontrol" | "gonder", "zaman",
     "gelir": {"gonderilmemis", "gonderilmis", "tutar_gonderilmemis", "kayitlar": [...],
               "gonderim": {"sonuc", "mesaj", "kalan"}},          # gonderim yalniz islem=gonder'de
     "gider": {...}, "durum", "hata"}
"""

import json
import re
from datetime import datetime
from pathlib import Path

DOSYA = "defter-beyan.json"
TURLER = ("gelir", "gider")

# Gonderme penceresi ("DEFTER BEYAN ENTEGRASYON") siniflari
KAYIT_YOK, HATA, BASARILI, KISMI, BELIRSIZ = "kayit_yok", "hata", "basarili", "kismi", "belirsiz"
_KAYIT_YOK = re.compile(r"g[öo]nderilecek\s+se[çc]ili\s+kay[ıi]t\s+bulunamad", re.I)
_HATA = re.compile(r"hata|ba[şs]ar[ıi]s[ıi]z|g[öo]nderilemedi|reddedil|ge[çc]ersiz|yetki|izin\s+yok", re.I)
_BASARI = re.compile(r"ba[şs]ar[ıi]|g[öo]nderildi|tamamland[ıi]|aktar[ıi]ld[ıi]", re.I)
# Gercek ornek: "Defter Beyan Sistemine gönderim başlıyor. / 1. satır için. / Defter Beyan Sistemine gönderim tamamlandı. (1)"
_GONDERIM_SAYISI = re.compile(r"g[öo]nderim\s+tamamland[ıi]\.?\s*\((\d+)\)", re.I)
_SADECE_BASLANGIC = re.compile(r"g[öo]nderim\s+ba[şs]l[ıi]yor", re.I)

# tamam: gonderilmeyen kayit yok | yalniz sabit kiymet: kalanlarin hepsi sabit kiymet (normalde gonderilmez, es gecilir)
# gonderilmemis var: sabit kiymet DISINDA gonderilmeyen kayit var | hata: islem yapilamadi
DURUMLAR = ("tamam", "yalnız sabit kıymet", "gönderilmemiş var", "hata")


_DUGMELER = {"tamam", "kapat", "evet", "hayir", "iptal", "yenile", "ok", "x"}
_SATIR_BASLIK = re.compile(r"^\s*(\d+)\.\s*sat[ıi]r\s+i[çc]in\.?\s*$", re.I)
_SONEK = re.compile(r"\s*\(\s*[\d.]+\s*\)\s*$")          # "... (8.1)" / "... (14)": Luca'nin ic sayaci
_KIMLIK = re.compile(r"\s+-\s+\d+\s*$")                    # "... - 0" / "... - 10200102"


def gonderim_ayrintisi(metin):
    """Entegrasyon penceresi yazisi -> {'hatalar': [{'satir', 'mesaj'}], 'gonderilen': N | None, 'bitti': bool}.

    Gercek ornek:  '3. satır için.' satirinin altindaki her ek satir o satirin HATASIDIR, ornegin
    'Tutarı 0.00 olan satır girilemez. (8.1)'; hatasiz satirin altinda yazi yoktur.
    Sondaki 'gönderim tamamlandı. (9)' hatasiz giden kayit sayisidir (15 satir - 6 hata = 9)."""
    hatalar, satir, bitti = [], None, False
    satirlar = (metin or "").splitlines()
    for i, ham in enumerate(satirlar):          # pencere basligi ("DEFTER BEYAN ENTEGRASYON") baslangic satirindan onceye duser
        if _SADECE_BASLANGIC.search(ham):
            satirlar = satirlar[i:]
            break
    for ham in satirlar:
        t = ham.strip()
        if not t or _k(t) in _DUGMELER:         # pencere duzeni: Tamam / Kapat gibi dugme yazilari hata degildir
            continue
        m = _SATIR_BASLIK.match(t)
        if m:
            satir = int(m.group(1))
        elif _SADECE_BASLANGIC.search(t):
            continue
        elif _GONDERIM_SAYISI.search(t):
            bitti = True
        else:
            hatalar.append({"satir": satir, "mesaj": _SONEK.sub("", t).strip()})
    return {"hatalar": hatalar, "gonderilen": gonderilen_sayisi(metin), "bitti": bitti}


def hata_ozeti(hatalar):
    """[{'satir','mesaj'}] -> {'Tutarı 0.00 olan satır girilemez.': 2, ...} (kayda ozgu sayilar atilarak gruplanir)."""
    ozet = {}
    for h in hatalar:
        anahtar = _KIMLIK.sub("", h["mesaj"]).strip()
        ozet[anahtar] = ozet.get(anahtar, 0) + 1
    return dict(sorted(ozet.items(), key=lambda kv: -kv[1]))


def gonderim_sinifla(metin):
    """Entegrasyon penceresinin tum yazisi -> kayit_yok / hata / kismi / basarili / belirsiz.

    Satir hatasi (hatalar listesi) varsa: bir kismi gittiyse KISMI, hic gitmediyse HATA. Hata yoksa ve
    'gönderim tamamlandı. (N)' varsa BASARILI."""
    metin = (metin or "").strip()
    if not metin:
        return BELIRSIZ
    if _KAYIT_YOK.search(metin):
        return KAYIT_YOK
    a = gonderim_ayrintisi(metin)
    if a["hatalar"]:
        return KISMI if (a["gonderilen"] or 0) > 0 else HATA
    if a["bitti"]:
        return BASARILI
    govde = "\n".join(s for s in metin.splitlines() if s.strip() and not _SADECE_BASLANGIC.search(s))
    if _HATA.search(govde):
        return HATA
    return BASARILI if _BASARI.search(govde) else BELIRSIZ


def gonderilen_sayisi(metin):
    """'... gönderim tamamlandı. (3)' -> 3; bu kalip yoksa None."""
    m = _GONDERIM_SAYISI.search(metin or "")
    return int(m.group(1)) if m else None


def tutar_oku(metin):
    """'1.234,56' / '1234,56' / '1234.56' / '₺ 1.234,56' -> float; okunamazsa None."""
    s = re.sub(r"[^\d,.\-]", "", str(metin or ""))
    if not s or not re.search(r"\d", s):
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _k(metin):
    """Baslik karsilastirma anahtari: kucuk harf, Turkce harfler sade."""
    m = (metin or "").replace("İ", "i").replace("I", "ı").lower()
    return m.translate(str.maketrans("ışğüöç", "isguoc")).strip()


def tutar_sutunu(basliklar):
    """Satirlardaki toplanacak tutar sutununun indeksi (baslikta 'tutar' gecen, KDV ve oran sutunlari haric)."""
    for i, b in enumerate(basliklar):
        k = _k(b)
        if "tutar" in k and "oran" not in k and ("kdv" not in k or k.find("kdv") > k.find("tutar")):
            return i  # 'KDV Tutari' degil; 'Tutar', 'Tutar (KDV Dahil)' olur
    return None


def sabit_kiymet_mi(satir):
    """Satirin herhangi bir hucresinde 'sabit kiymet' geciyorsa (kategori / belge turu / aciklama) True."""
    return any("sabit kiymet" in _k(h) for h in satir)


def kayitlari_ozetle(basliklar, satirlar, sinir=500):
    """Okunan tablo -> (adet, tutar toplami ya da None, kayit listesi [en fazla `sinir`], sabit kiymet adedi)."""
    ti = tutar_sutunu(basliklar)

    def al(satir, aranan):
        for i, b in enumerate(basliklar):
            if aranan in _k(b):
                return satir[i] if i < len(satir) else ""
        return ""

    toplam, kayitlar, sabit = 0.0, [], 0
    tutar_var = False
    for s in satirlar:
        sabit += sabit_kiymet_mi(s)
        t = tutar_oku(s[ti]) if ti is not None and ti < len(s) else None
        if t is not None:
            toplam += t
            tutar_var = True
        if len(kayitlar) < sinir:
            kayitlar.append({"evrak_no": al(s, "evrak no"), "tarih": al(s, "evrak tarihi"),
                             "kategori": al(s, "kategori"), "belge_turu": al(s, "belge"),
                             "aciklama": al(s, "aciklama"), "tutar": t,
                             "sabit_kiymet": sabit_kiymet_mi(s)})
    return len(satirlar), (round(toplam, 2) if tutar_var else None), kayitlar, sabit


def tur_durumu(t):
    """Bir sekmenin (gelir/gider) durumu: tamam / yalniz sabit kiymet / gonderilmemis var / hata."""
    g = t.get("gonderim") or {}
    if g.get("sonuc") == HATA and not g.get("hatalar") and g.get("kalan"):
        return "hata"  # satir hatasi degil, genel hata (API bilgisi bos, pencere cikmadi, ...)
    if g:
        bekleyen, sabit = g.get("kalan") or 0, g.get("kalan_sabit") or 0
    else:
        bekleyen, sabit = t.get("gonderilmemis") or 0, t.get("sabit_kiymet") or 0
    if bekleyen - sabit > 0:
        return "gönderilmemiş var"
    return "yalnız sabit kıymet" if bekleyen > 0 else "tamam"


def firma_durumu(sonuc):
    """Firma kaydinin genel durumu (en kotu sekme): hata > gönderilmemiş var > yalnız sabit kıymet > tamam."""
    if sonuc.get("hata"):
        return "hata"
    sira = {"tamam": 0, "yalnız sabit kıymet": 1, "gönderilmemiş var": 2, "hata": 3}
    durumlar = [tur_durumu(sonuc.get(tur) or {}) for tur in TURLER]
    return max(durumlar, key=sira.get)


# --- sonuc dosyasi --------------------------------------------------------------------------------

def oku(yol):
    """(donem metni, [firma kayitlari]); dosya yoksa ('', [])."""
    try:
        veri = json.loads(Path(yol).read_text(encoding="utf-8"))
        return veri.get("donem", ""), list(veri.get("firmalar") or [])
    except (OSError, ValueError, AttributeError):
        return "", []


def kaydet(yol, donem, sonuclar):
    """sonuclar: {firma: kayit}. Dosyadaki oncekiler korunur; ayni firma yeni kayitla degisir."""
    yol = Path(yol)
    _, eski = oku(yol)
    birlesik = {k["firma"]: k for k in eski if k.get("firma")}
    birlesik.update(sonuclar)
    gecici = yol.with_suffix(".json.tmp")
    gecici.parent.mkdir(parents=True, exist_ok=True)
    gecici.write_text(json.dumps({"donem": donem, "guncelleme": datetime.now().isoformat(timespec="seconds"),
                                  "firmalar": [birlesik[k] for k in sorted(birlesik)]},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    gecici.replace(yol)


def bos_sonuc(firma, donem, islem):
    return {"firma": firma, "donem": donem, "islem": islem, "zaman": datetime.now().isoformat(timespec="seconds"),
            "gelir": {}, "gider": {}, "durum": "", "hata": ""}
