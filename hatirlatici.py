"""
Hatırlatma panelinden (PythonAnywhere) bugünkü hatırlatmaları çekip e-posta olarak yollar.
GitHub Actions her sabah çalıştırır. Panele ulaşılamazsa "panel kapalı" maili atar, böylece
sessizce hatırlatma kaçırılmaz.

Gerekli ortam değişkenleri:
  PANEL_URL   https://KULLANICI.pythonanywhere.com/h/ANAHTAR   (sonunda / olmadan)
  SMTP_HOST, SMTP_USER, SMTP_PASS, MAIL_TO
İsteğe bağlı: SMTP_PORT (587), MAIL_FROM (SMTP_USER)

Kullanım:
  python hatirlatici.py                   # bugünü işler, mail atar
  python hatirlatici.py --dry-run         # mail atmadan yazdırır
  python hatirlatici.py --bugun 2026-12-28 --dry-run
"""

import argparse
import json
import os
import smtplib
import sys
import urllib.error
import urllib.request
from datetime import datetime
from email.message import EmailMessage


def panelden_cek(url, bugun):
    adres = url.rstrip("/") + "/api/bugun" + (f"?bugun={bugun}" if bugun else "")
    istek = urllib.request.Request(adres, headers={"User-Agent": "hatirlatici/1.0"})
    with urllib.request.urlopen(istek, timeout=30) as r:
        return json.load(r)


def mesaj(konu, govde, gonderen, alici):
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = gonderen, alici, konu
    msg.set_content(govde)
    return msg


def tr_tarih(iso):
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--bugun", help="YYYY-AA-GG (test için)")
    args = ap.parse_args()

    alici = os.environ.get("MAIL_TO")
    panel = os.environ.get("PANEL_URL")
    if not alici or not panel:
        sys.exit("PANEL_URL ve MAIL_TO ortam değişkenleri tanımlı olmalı.")
    gonderen = os.environ.get("MAIL_FROM") or os.environ.get("SMTP_USER", "hatirlatici@localhost")

    try:
        veri = panelden_cek(panel, args.bugun)
        liste = veri["hatirlatmalar"]
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        # Adres (anahtarı içerir) hata metnine girmesin diye yalnızca türü yazılır.
        msg = mesaj(
            "Hatırlatma paneline ulaşılamadı",
            "Bugünkü hatırlatmalar kontrol edilemedi.\n\n"
            "Olası neden: PythonAnywhere'de panelin süresi doldu. pythonanywhere.com → Web sekmesi → "
            "\"Run until ... from today\" düğmesine bas.\n\n"
            f"Hata türü: {type(e).__name__}\n",
            gonderen, alici,
        )
        liste = None
    else:
        if not liste:
            print(f"{veri.get('bugun')}: gönderilecek hatırlatma yok.")
            return
        satirlar = [
            f"- {k['metin']} ({tr_tarih(k['olay'])}) - {'BUGÜN' if k['fark'] == 0 else str(k['fark']) + ' gün kaldı'}"
            for k in liste
        ]
        konu = liste[0]["metin"] if len(liste) == 1 else f"{len(liste)} hatırlatma"
        msg = mesaj(konu, "Hatırlatmalar:\n\n" + "\n".join(satirlar) + "\n", gonderen, alici)

    if args.dry_run:
        print(msg["Subject"]); print(msg.get_content())
        return

    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT") or 587), timeout=30) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.send_message(msg)
    print("Mail gönderildi:", msg["Subject"])
    if liste is None:
        sys.exit(1)  # Actions'ta kırmızı görünsün


if __name__ == "__main__":
    main()
