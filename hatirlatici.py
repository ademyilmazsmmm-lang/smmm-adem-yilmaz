"""
hatirlatmalar.txt içindeki satırlara göre, bugün gönderilmesi gereken
hatırlatmaları kendine e-posta olarak yollar. Biçim için dosyanın başına bak.

Gerekli ortam değişkenleri: SMTP_HOST, SMTP_USER, SMTP_PASS, MAIL_TO
İsteğe bağlı: SMTP_PORT (587), MAIL_FROM (SMTP_USER)

Kullanım:
  python hatirlatici.py                    # bugünü işler, mail atar
  python hatirlatici.py --dry-run          # mail atmadan yazdırır
  python hatirlatici.py --bugun 2026-12-28 --dry-run
  python hatirlatici.py --liste            # yaklaşan tüm hatırlatmalar
"""

import argparse
import calendar
import os
import re
import smtplib
import sys
from datetime import date, datetime, timedelta
from email.message import EmailMessage

DOSYA = "hatirlatmalar.txt"


def ay_ekle(d, n):
    toplam = d.year * 12 + d.month - 1 + n
    y, a = divmod(toplam, 12)
    a += 1
    return date(y, a, min(d.day, calendar.monthrange(y, a)[1]))


def gun_sec(y, a, g):
    return date(y, a, min(g, calendar.monthrange(y, a)[1]))


def satir_ayristir(satir, no):
    """(zaman, gunler, metin) döndürür; zaman bir fonksiyon: yıl/ay -> date."""
    parcalar = [p.strip() for p in satir.split("|")]
    if len(parcalar) != 3:
        raise ValueError(f"{DOSYA}:{no}: 'ZAMAN | GÜNLER | METİN' biçiminde olmalı: {satir}")
    zaman, gunler, metin = parcalar
    gunler = [int(x) for x in gunler.split(",") if x.strip()] or [0]

    if m := re.fullmatch(r"her-ay\s+(\d{1,2})", zaman):
        g = int(m[1])
        return ("aylik", g), gunler, metin
    if m := re.fullmatch(r"her-yil\s+(\d{1,2})-(\d{1,2})", zaman):
        return ("yillik", int(m[1]), int(m[2])), gunler, metin
    if m := re.fullmatch(r"(\d{4}-\d{2}-\d{2})(?:\s*\+(\d+)(ay|gun))?", zaman):
        d = datetime.strptime(m[1], "%Y-%m-%d").date()
        if m[2]:
            d = ay_ekle(d, int(m[2])) if m[3] == "ay" else d + timedelta(days=int(m[2]))
        return ("tek", d), gunler, metin
    raise ValueError(f"{DOSYA}:{no}: ZAMAN anlaşılamadı: {zaman}")


def oku():
    kayitlar = []
    with open(DOSYA, encoding="utf-8") as f:
        for no, satir in enumerate(f, 1):
            satir = satir.strip()
            if satir and not satir.startswith("#"):
                kayitlar.append(satir_ayristir(satir, no))
    return kayitlar


def olay_mi(zaman, hedef):
    tur = zaman[0]
    if tur == "tek":
        return zaman[1] == hedef
    if tur == "aylik":
        return gun_sec(hedef.year, hedef.month, zaman[1]) == hedef
    return gun_sec(hedef.year, zaman[1], zaman[2]) == hedef


def bugunku(kayitlar, bugun):
    sonuc = []
    for zaman, gunler, metin in kayitlar:
        for fark in gunler:
            hedef = bugun + timedelta(days=fark)
            if olay_mi(zaman, hedef):
                sonuc.append((metin, hedef, fark))
    return sonuc


def liste(kayitlar, bugun, gun=120):
    for i in range(gun + 1):
        for metin, hedef, fark in bugunku(kayitlar, bugun + timedelta(days=i)):
            print(f"mail: {bugun + timedelta(days=i)}  olay: {hedef}  {metin}")


def mesaj(liste_, gonderen, alici):
    msg = EmailMessage()
    msg["From"], msg["To"] = gonderen, alici
    msg["Subject"] = liste_[0][0] if len(liste_) == 1 else f"{len(liste_)} hatırlatma"
    satirlar = [
        f"- {metin} ({hedef.strftime('%d.%m.%Y')}) - {'BUGÜN' if fark == 0 else f'{fark} gün kaldı'}"
        for metin, hedef, fark in liste_
    ]
    msg.set_content("Hatırlatmalar:\n\n" + "\n".join(satirlar) + "\n")
    return msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--liste", action="store_true")
    ap.add_argument("--bugun", help="YYYY-AA-GG (test için)")
    args = ap.parse_args()

    bugun = datetime.strptime(args.bugun, "%Y-%m-%d").date() if args.bugun else date.today()
    kayitlar = oku()
    if args.liste:
        return liste(kayitlar, bugun)

    bugunun = bugunku(kayitlar, bugun)
    if not bugunun:
        print(f"{bugun}: gönderilecek hatırlatma yok.")
        return

    alici = os.environ.get("MAIL_TO")
    if not alici:
        sys.exit("MAIL_TO ortam değişkeni (alıcı adresi) tanımlı değil.")
    gonderen = os.environ.get("MAIL_FROM") or os.environ.get("SMTP_USER", "hatirlatici@localhost")
    msg = mesaj(bugunun, gonderen, alici)
    if args.dry_run:
        print(msg.get_content())
        return

    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT") or 587), timeout=30) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.send_message(msg)
    print(f"{len(bugunun)} hatırlatma {alici} adresine gönderildi.")


if __name__ == "__main__":
    main()
