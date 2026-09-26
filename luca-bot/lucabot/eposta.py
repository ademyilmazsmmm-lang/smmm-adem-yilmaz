# -*- coding: utf-8 -*-
"""Calisma bitince ozet e-postasi gonderir (rapor.xlsx ekli).

Gece calismasinda sabah butun gunlugu okumak yerine tek bir e-postaya
bakmak yeterli olsun diye: tevkifatli faturalar (KDV2), e-SMM alislari ve
iptal/itiraz kayitlari firma firma listelenir.

Ayarlar (ayarlar.json):
    mail_yontemi         : "outlook" (varsayilan) / "smtp"
    mail_otomatik_gonder : true/false
        - outlook yonteminde: true (ya da hic yazilmamissa) doğrudan gonderilir, false ise
          Outlook'ta taslak olarak acilir (siz kontrol edip gonderirsiniz)
        - smtp yonteminde: false ise e-posta hic denenmez
    mail_alici           : "a@b.com"   - birden fazla icin virgulle ayirin; bos birakilirsa
                                         Outlook'taki kendi hesabiniza gonderilir
    mail_sadece_uyari    : true/false  - true ise uyari yoksa e-posta gitmez
    smtp.sunucu/port/ssl/kullanici/sifre/gonderen  - sadece mail_yontemi=smtp icin
"""

import smtplib
import ssl as ssl_modulu
import time
from email.message import EmailMessage
from pathlib import Path

from .rapor import TEVKIFAT_EKRANLARI  # tevkifat uyarisi sadece alis ekranlarindan

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

    satirlar.append("Ayrintilar ekteki rapor.xlsx dosyasinda: 'Özet' sayfasi genel tabloyu,"
                    " 'Hatalar ve Uyarılar' sayfasi ne yapilmasi gerektigini gosterir.")
    metin = "\n".join(satirlar)
    # WhatsApp/Markdown alismasindan kalan '*' isaretleri duz metin mailde
    # oldugu gibi gorunur; hicbir yerde kullanilmasa da guvenlik icin temizlenir
    metin = metin.replace("**", "").replace("*", "")
    return metin, bool(tevkifatli or esmm)


def _outlook_ile_gonder(alicilar, konu, govde, ek_yolu, gonder_mi, bildir):
    """Masaustunde kurulu Outlook uzerinden gonderir (win32com).

    Sifre gerekmez: Outlook'ta o an oturum acmis hesap kullanilir, mail sizin
    adresinizden gider ve Gonderilmis Ogeler klasorune duser - elle
    gonderdiginiz bir mailden farki yoktur. gonder_mi False ise mail
    gonderilmez, Outlook'ta taslak olarak acilir; siz kontrol edip
    gonderirsiniz (Outlook kapaliysa Dispatch onu kendisi acar).
    """
    try:
        import win32com.client
    except ImportError:
        bildir("E-posta gonderilemedi: pywin32 kurulu degil (kurulum.bat calistirin)")
        return False

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        ad_alani = None
        try:
            # Outlook kapaliysa Dispatch onu arka planda baslatir, ama MAPI
            # oturumu hazir olmadan CreateItem/Send cagrilirsa hata verebilir.
            # Logon hem Outlook'u acar (kapaliysa) hem oturum hazir olana
            # kadar bekler; zaten acik/oturum acilmissa sessizce gecer.
            ad_alani = outlook.GetNamespace("MAPI")
            ad_alani.Logon("", "", False, False)
        except Exception:
            pass
        if not alicilar:
            # mail_alici bos: Outlook'ta oturum acmis hesabin kendi adresine gonderilir
            kendi = _outlook_kendi_adresi(outlook)
            if not kendi:
                bildir("E-posta gonderilmedi: mail_alici bos ve Outlook hesabinin adresi"
                       " okunamadi (ayarlar.json'a \"mail_alici\" yazin)")
                return False
            alicilar = [kendi]
            bildir(f"mail_alici bos; ozet Outlook hesabinizin kendi adresine gonderiliyor: {kendi}")
        mail = outlook.CreateItem(0)  # 0 = olMailItem
        mail.To = "; ".join(alicilar)
        mail.Subject = konu
        mail.Body = govde
        if ek_yolu and Path(ek_yolu).exists():
            mail.Attachments.Add(str(Path(ek_yolu).resolve()))
        if gonder_mi:
            onceki = _giden_kutusu_sayisi(ad_alani)
            mail.Send()
            if _giden_kutusu_bosalsin(ad_alani, onceki):
                bildir(f"Ozet e-postasi Outlook ile gonderildi: {', '.join(alicilar)}")
            else:
                bildir(f"UYARI: ozet e-postasi Outlook'un Giden Kutusu'nda bekliyor"
                       f" ({', '.join(alicilar)}); Outlook'u acinca gidecek")
        else:
            mail.Display()
            bildir(f"Ozet e-postasi Outlook'ta taslak olarak acildi: {', '.join(alicilar)}"
                   " (gondermek icin Outlook'ta kontrol edip Gonder'e basin)")
        return True
    except Exception as e:
        bildir(f"E-posta gonderilemedi (Outlook: {type(e).__name__}: {e})")
        return False


def _giden_kutusu_sayisi(ad_alani):
    try:
        return ad_alani.GetDefaultFolder(4).Items.Count  # 4 = olFolderOutbox
    except Exception:
        return None


def _giden_kutusu_bosalsin(ad_alani, onceki, azami_saniye=90):
    """Mail Giden Kutusu'ndan cikana kadar bekler (Outlook kapaliyken de gitsin diye).

    Outlook kapaliyken bot onu arka planda acar; Send() maili yalnizca Giden
    Kutusu'na koyar. Program hemen biterse Outlook da kapanir ve mail orada
    kalabilir. Bu yuzden Gonder/Al tetiklenir ve kutu bosalana kadar beklenir.
    Sayi okunamiyorsa (eski Outlook) gonderildi kabul edilir.
    """
    if ad_alani is None or onceki is None:
        return True
    try:
        ad_alani.SendAndReceive(False)
    except Exception:
        pass
    try:
        import pythoncom
    except ImportError:
        pythoncom = None
    bitis = time.time() + azami_saniye
    while time.time() < bitis:
        sayi = _giden_kutusu_sayisi(ad_alani)
        if sayi is None or sayi <= onceki:
            return True
        if pythoncom is not None:
            pythoncom.PumpWaitingMessages()
        time.sleep(1)
    return False


def _outlook_kendi_adresi(outlook):
    """Outlook'ta acik olan hesabin e-posta adresi; bulunamazsa ""."""
    try:
        hesaplar = outlook.Session.Accounts
        for i in range(1, hesaplar.Count + 1):
            adres = str(hesaplar.Item(i).SmtpAddress or "").strip()
            if "@" in adres:
                return adres
    except Exception:
        pass
    try:
        kullanici = outlook.Session.CurrentUser.AddressEntry
        try:
            adres = str(kullanici.GetExchangeUser().PrimarySmtpAddress or "").strip()
        except Exception:
            adres = str(kullanici.Address or "").strip()
        return adres if "@" in adres else ""
    except Exception:
        return ""


def _smtp_ile_gonder(ayarlar, alicilar, konu, govde, ek_yolu, bildir):
    kullanici = _ayar(ayarlar, "smtp.kullanici")
    sifre = _ayar(ayarlar, "smtp.sifre")
    sunucu = _ayar(ayarlar, "smtp.sunucu")
    if not (kullanici and sifre and sunucu):
        bildir("E-posta gonderilmedi: smtp kullanici/sifre/sunucu eksik")
        return False

    gonderen = _ayar(ayarlar, "smtp.gonderen") or kullanici
    ileti = EmailMessage()
    ileti["From"] = gonderen
    ileti["To"] = ", ".join(alicilar)
    ileti["Subject"] = konu
    ileti.set_content(govde)

    if ek_yolu and Path(ek_yolu).exists():
        ek_yolu = Path(ek_yolu)
        ileti.add_attachment(
            ek_yolu.read_bytes(), maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=ek_yolu.name)

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

    bildir(f"Ozet e-postasi SMTP ile gonderildi: {', '.join(alicilar)}")
    return True


def gonder(ayarlar, klasor, sonuclar, log_yaz=None, donem=""):
    """Ozet e-postasini gonderir. Gonderildiyse (ya da taslak acildiysa) True doner.

    Hicbir hata calismayi durdurmaz; sebep gunluge yazilir.
    """
    def bildir(mesaj):
        if log_yaz:
            log_yaz(mesaj)

    yontem = str(_ayar(ayarlar, "mail_yontemi", "outlook")).strip().lower()
    if yontem not in ("outlook", "smtp"):
        yontem = "outlook"

    # SMTP'de "otomatik gonder" kapaliysa mail hic denenmez. Outlook'ta ise
    # kapali olmasi "hicbir sey yapma" degil "taslak olarak ac" anlamina
    # gelir (asagida _outlook_ile_gonder'e gonder_mi olarak geciliyor).
    if yontem == "smtp" and not _ayar(ayarlar, "mail_otomatik_gonder", False):
        bildir("E-posta gonderilmedi: mail_otomatik_gonder kapali (ayarlar.json)")
        return False

    alicilar = _alicilar(ayarlar)
    if not alicilar and yontem != "outlook":  # Outlook'ta bos alici = kendi hesabiniz
        bildir("E-posta gonderilmedi: mail_alici bos (ayarlar.json)")
        return False

    govde, uyari_var = ozet_metni(sonuclar, donem)
    if _ayar(ayarlar, "mail_sadece_uyari", False) and not uyari_var:
        bildir("Tevkifatli/e-SMM kaydi yok, e-posta gonderilmedi (mail_sadece_uyari)")
        return False

    konu = f"Luca Bot ozeti{' - ' + donem if donem else ''}"
    rapor_yolu = Path(klasor) / "rapor.xlsx"
    ek_yolu = rapor_yolu if rapor_yolu.exists() else None

    if yontem == "outlook":
        # ayar hic yazilmamissa gonderilir; taslak icin acikca false yazilmali
        gonder_mi = bool(_ayar(ayarlar, "mail_otomatik_gonder", True))
        return _outlook_ile_gonder(alicilar, konu, govde, ek_yolu, gonder_mi, bildir)
    return _smtp_ile_gonder(ayarlar, alicilar, konu, govde, ek_yolu, bildir)
