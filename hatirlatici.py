"""
Hatırlatma panelinden (PythonAnywhere) zamanı gelmiş hatırlatmaları çekip e-posta olarak yollar,
ardından panele "gönderildi" bilgisini yazar (aynı hatırlatma tekrar gitmez).
GitHub Actions her 10 dakikada bir çalıştırır.

Panele ulaşılamazsa her sabah 08:00-08:09 arasındaki çalışmada tek bir uyarı maili atar
(10 dakikada bir mail yağmasın diye diğer çalışmalar sessiz geçer).

Gerekli ortam değişkenleri:
  PANEL_URL   https://KULLANICI.pythonanywhere.com/h/ANAHTAR   (sonunda / olmadan)
  SMTP_HOST, SMTP_USER, SMTP_PASS, MAIL_TO
İsteğe bağlı: SMTP_PORT (587), MAIL_FROM (SMTP_USER)

Kullanım:
  python hatirlatici.py                              # mail atar, panele işler
  python hatirlatici.py --dry-run                    # mail atmaz, panele yazmaz
  python hatirlatici.py --simdi 2026-12-28T09:30 --dry-run
"""

import argparse
import json
import os
import smtplib
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

TR = timezone(timedelta(hours=3))


def istek(url, yol, simdi=None, veri=None):
    adres = url.rstrip("/") + yol + (f"?simdi={simdi}" if simdi else "")
    basliklar = {"User-Agent": "hatirlatici/2.0"}
    govde = None
    if veri is not None:
        govde = json.dumps(veri).encode()
        basliklar["Content-Type"] = "application/json"
    with urllib.request.urlopen(urllib.request.Request(adres, data=govde, headers=basliklar), timeout=30) as r:
        return json.load(r)


def mesaj(konu, govde, gonderen, alici):
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = gonderen, alici, konu
    msg.set_content(govde)
    return msg


def tr_tarih(iso):
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y")


def smtp_gonder(msg):
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT") or 587), timeout=30) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.send_message(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--simdi", help="YYYY-AA-GGTSS:DD (test için)")
    args = ap.parse_args()

    alici, panel = os.environ.get("MAIL_TO"), os.environ.get("PANEL_URL")
    if not alici or not panel:
        sys.exit("PANEL_URL ve MAIL_TO ortam değişkenleri tanımlı olmalı.")
    gonderen = os.environ.get("MAIL_FROM") or os.environ.get("SMTP_USER", "hatirlatici@localhost")

    try:
        veri = istek(panel, "/api/bekleyen", args.simdi)
        liste = veri["hatirlatmalar"]
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        su = datetime.now(TR)
        print(f"Panele ulaşılamadı ({type(e).__name__}).")  # adres anahtar içerir, yazılmaz
        if not (su.hour == 8 and su.minute < 10) and not args.dry_run:
            return
        msg = mesaj(
            "Hatırlatma paneline ulaşılamadı",
            "Hatırlatmalar kontrol edilemiyor, mailler gelmeyebilir.\n\n"
            "Olası neden: PythonAnywhere'de panelin süresi doldu. pythonanywhere.com → Web sekmesi → "
            "\"Run until ... from today\" düğmesine bas.\n\n"
            f"Hata türü: {type(e).__name__}\n",
            gonderen, alici,
        )
        if args.dry_run:
            print(msg["Subject"]); print(msg.get_content())
        else:
            smtp_gonder(msg)
        return

    if not liste:
        print(f"{veri.get('simdi')}: gönderilecek hatırlatma yok.")
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

    smtp_gonder(msg)
    print("Mail gönderildi:", msg["Subject"])
    istek(panel, "/api/gonderildi",
          veri={"ogeler": [{"id": k["id"], "olay": k["olay"], "fark": k["fark"]} for k in liste]})
    print("Panele işlendi.")


if __name__ == "__main__":
    main()
