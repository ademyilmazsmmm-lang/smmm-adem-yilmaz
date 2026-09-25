# -*- coding: utf-8 -*-
"""Calisma bitince ozet e-postasi gonderir (rapor.xlsx ekli).

Gece calismasinda sabah butun gunlugu okumak yerine tek bir e-postaya
bakmak yeterli olsun diye: tevkifatli faturalar (KDV2), e-SMM alislari ve
iptal/itiraz kayitlari firma firma listelenir.

Ayarlar (ayarlar.json):
    mail_otomatik_gonder : true/false  - kapaliysa hicbir sey yapilmaz
    mail_alici           : "a@b.com"   - birden fazla icin virgulle ayirin
    mail_sadece_uyari    : true/false  - true ise uyari yoksa e-posta gitmez
    smtp.sunucu/port/ssl/kullanici/sifre/gonderen
"""

import smtplib
import ssl as ssl_modulu
from email.message import EmailMessage
from pathlib import Path

from rapor import TEVKIFAT_EKRANLARI  # tevkifat uyarisi sadece alis ekranlarindan

# e-postada firma firma listelenen basliklar
TEVKIFAT_BASLIGI = "TEVKIFATLI ALIS FATURALARI (KDV2 kontrol)"
ESMM_BASLIGI = "e-SMM ALIS"
IPTAL_BASLIGI = "IPTAL/ITIRAZ"

ESMM_TIPLERI = ("esmm-alis",)


def _ayar(ayarlar, yol, varsayilan=None):
    """Noktali yoldan ayar okur: _ayar(a, "smtp.port", 587)."""
    deger = ayarlar
    for parca in yol.split("."):
        if not isinstance(deger, dict) or parca not in deger:
            return varsayilan
        deger = deger[parca]
    return deger if deger not in ("", None) else varsayilan


def _alicilar(ayarlar):
    ham = _ayar(ayarlar, "mail_alici") or _ayar(ayarlar, "smtp.gonderen") or ""
    return [a.strip() for a in str(ham).replace(";", ",").split(",") if a.strip()]


def _firma_basina(sonuclar, alan):
    """[(firma, belge tipi, deger)] - degeri sifirdan buyuk olan satirlar."""
    satirlar = []
    for s in sonuclar:
        deger = s.get(alan) or 0
        if deger:
            satirlar.append((s.get("firma", "?"), s.get("belge_tipi", ""), deger))
    satirlar.sort(key=lambda r: (-r[2], r[0]))
    return satirlar


def _esmm_alislari(sonuclar):
    satirlar = [(s.get("firma", "?"), s.get("fatura_sayisi") or 0)
                for s in sonuclar
                if s.get("belge_tipi") in ESMM_TIPLERI and (s.get("fatura_sayisi") or 0)]
    satirlar.sort(key=lambda r: (-r[1], r[0]))
    return satirlar


def _bolum(baslik, satirlar, birim="fatura"):
    if not satirlar:
        return []
    metin = [f"{baslik} - {len(satirlar)} firma", "-" * 52]
    for satir in satirlar:
        if len(satir) == 3:
            firma, tip, deger = satir
            metin.append(f"  {firma:<14} {deger:>4} {birim}   ({tip})")
        else:
            firma, deger = satir
            metin.append(f"  {firma:<14} {deger:>4} {birim}")
    metin.append("")
    return metin


def ozet_metni(sonuclar, donem=""):
    """E-posta govdesi: once uyari gerektirenler, sonra genel sayilar."""
    tevkifatli = _firma_basina(
        [s for s in sonuclar if s.get("belge_tipi") in TEVKIFAT_EKRANLARI], "tevkifat")
    esmm = _esmm_alislari(sonuclar)
    iptaller = _firma_basina(sonuclar, "iptal_itiraz")

    firmalar = {s.get("firma") for s in sonuclar}
    inen = sum(1 for s in sonuclar if s.get("durum") == "tamam")
    bos = sum(1 for s in sonuclar if s.get("durum") == "fatura yok")
    sorunlu = len(sonuclar) - inen - bos

    satirlar = []
    if donem:
        satirlar.append(f"Donem: {donem}")
    satirlar += [
        f"{len(firmalar)} firma, {len(sonuclar)} ekran islendi.",
        f"Fatura inen ekran: {inen} | Bos: {bos} | Sorunlu: {sorunlu}",
        "",
    ]
    satirlar += _bolum(TEVKIFAT_BASLIGI, tevkifatli)
    satirlar += _bolum(ESMM_BASLIGI, esmm)
    satirlar += _bolum(IPTAL_BASLIGI, iptaller)

    if not (tevkifatli or esmm or iptaller):
        satirlar.append("Tevkifatli fatura, e-SMM alisi ve iptal/itiraz kaydi yok.")
        satirlar.append("")

    sorunlular = [s for s in sonuclar if s.get("not")]
    if sorunlular:
        satirlar += ["NOTLAR", "-" * 52]
        for s in sorunlular[:20]:
            satirlar.append(f"  {s.get('firma', '?'):<14} {s['not']}")
        if len(sorunlular) > 20:
            satirlar.append(f"  ... (+{len(sorunlular) - 20})")
        satirlar.append("")

    satirlar.append("Ayrintilar ekteki rapor.xlsx dosyasinda.")
    return "\n".join(satirlar), bool(tevkifatli or esmm)


def gonder(ayarlar, klasor, sonuclar, log_yaz=None, donem=""):
    """Ozet e-postasini gonderir. Gonderildiyse True doner.

    Hicbir hata calismayi durdurmaz; sebep gunluge yazilir.
    """
    def bildir(mesaj):
        if log_yaz:
            log_yaz(mesaj)

    if not _ayar(ayarlar, "mail_otomatik_gonder", False):
        bildir("E-posta gonderilmedi: mail_otomatik_gonder kapali (ayarlar.json)")
        return False
    kullanici = _ayar(ayarlar, "smtp.kullanici")
    sifre = _ayar(ayarlar, "smtp.sifre")
    sunucu = _ayar(ayarlar, "smtp.sunucu")
    if not (kullanici and sifre and sunucu):
        bildir("E-posta gonderilmedi: smtp kullanici/sifre/sunucu eksik")
        return False
    alicilar = _alicilar(ayarlar)
    if not alicilar:
        bildir("E-posta gonderilmedi: mail_alici bos")
        return False

    govde, uyari_var = ozet_metni(sonuclar, donem)
    if _ayar(ayarlar, "mail_sadece_uyari", False) and not uyari_var:
        bildir("Tevkifatli/e-SMM kaydi yok, e-posta gonderilmedi (mail_sadece_uyari)")
        return False

    gonderen = _ayar(ayarlar, "smtp.gonderen") or kullanici
    ileti = EmailMessage()
    ileti["From"] = gonderen
    ileti["To"] = ", ".join(alicilar)
    ileti["Subject"] = f"Luca Bot ozeti{' - ' + donem if donem else ''}"
    ileti.set_content(govde)

    rapor_yolu = Path(klasor) / "rapor.xlsx"
    if rapor_yolu.exists():
        ileti.add_attachment(
            rapor_yolu.read_bytes(), maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=rapor_yolu.name)

    port = int(_ayar(ayarlar, "smtp.port", 587))
    try:
        if _ayar(ayarlar, "smtp.ssl", False):
            with smtplib.SMTP_SSL(sunucu, port, timeout=60,
                                  context=ssl_modulu.create_default_context()) as s:
                s.login(kullanici, sifre)
                s.send_message(ileti)
        else:  # Office365/Outlook: 587 + STARTTLS
            with smtplib.SMTP(sunucu, port, timeout=60) as s:
                s.ehlo()
                s.starttls(context=ssl_modulu.create_default_context())
                s.ehlo()
                s.login(kullanici, sifre)
                s.send_message(ileti)
    except smtplib.SMTPAuthenticationError:
        bildir("E-posta gonderilemedi: kullanici adi/sifre kabul edilmedi"
               " (Office365'te uygulama sifresi ve SMTP AUTH gerekebilir)")
        return False
    except Exception as e:
        bildir(f"E-posta gonderilemedi ({type(e).__name__}: {e})")
        return False

    bildir(f"Ozet e-postasi gonderildi: {', '.join(alicilar)}")
    return True
