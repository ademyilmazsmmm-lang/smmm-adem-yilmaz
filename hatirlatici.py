"""
hatirlatmalar.json içindeki kayıtlara göre, bugün gönderilmesi gereken
hatırlatma e-postalarını SMTP ile yollar.

Kayıt türleri:
  tek    -> {"tarih": "YYYY-AA-GG"}
  aylik  -> {"gun": 1-31}          (kısa aylarda ayın son gününe kayar)
  yillik -> {"ay": 1-12, "gun": 1-31}
Her kayıtta "kac_gun_once": [3, 0] -> olaydan 3 gün önce ve olay günü mail atar.

Gerekli ortam değişkenleri: SMTP_HOST, SMTP_USER, SMTP_PASS
İsteğe bağlı: SMTP_PORT (587), MAIL_FROM (SMTP_USER), MAIL_TO (virgülle ayrılmış;
yoksa JSON'daki "alicilar" kullanılır)

Kullanım:
  python hatirlatici.py                 # bugünü işler
  python hatirlatici.py --dry-run       # mail atmadan ne gideceğini yazdırır
  python hatirlatici.py --bugun 2026-12-28 --dry-run
"""

import argparse
import calendar
import json
import os
import smtplib
import sys
from datetime import date, datetime, timedelta
from email.message import EmailMessage

DOSYA = "hatirlatmalar.json"


def olay_tarihi(kayit, yil, ay=None):
    """Kaydın verilen yıl/aydaki olay tarihini döndürür (yoksa None)."""
    tur = kayit["tur"]
    if tur == "tek":
        return datetime.strptime(kayit["tarih"], "%Y-%m-%d").date()
    if tur == "aylik":
        son = calendar.monthrange(yil, ay)[1]
        return date(yil, ay, min(kayit["gun"], son))
    if tur == "yillik":
        son = calendar.monthrange(yil, kayit["ay"])[1]
        return date(yil, kayit["ay"], min(kayit["gun"], son))
    raise ValueError(f"Bilinmeyen tür: {tur}")


def bugunku_hatirlatmalar(kayitlar, bugun):
    sonuc = []
    for k in kayitlar:
        for fark in k.get("kac_gun_once", [0]):
            hedef = bugun + timedelta(days=fark)  # olay bugün+fark gününde mi?
            if olay_tarihi(k, hedef.year, hedef.month) == hedef:
                sonuc.append((k, hedef, fark))
    return sonuc


def mesaj_olustur(liste, gonderen, alicilar):
    msg = EmailMessage()
    msg["From"] = gonderen
    msg["To"] = ", ".join(alicilar)
    msg["Subject"] = (
        liste[0][0]["baslik"] if len(liste) == 1
        else f"{len(liste)} hatırlatma"
    )
    satirlar = []
    for k, hedef, fark in liste:
        zaman = "BUGÜN" if fark == 0 else f"{fark} gün kaldı"
        satir = f"- {k['baslik']} ({hedef.strftime('%d.%m.%Y')}) - {zaman}"
        if k.get("not"):
            satir += f"\n  {k['not']}"
        satirlar.append(satir)
    msg.set_content("Merhaba,\n\nHatırlatmalar:\n\n" + "\n".join(satirlar) + "\n")
    return msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--bugun", help="YYYY-AA-GG (test için)")
    args = ap.parse_args()

    with open(DOSYA, encoding="utf-8") as f:
        veri = json.load(f)

    bugun = datetime.strptime(args.bugun, "%Y-%m-%d").date() if args.bugun else date.today()
    liste = bugunku_hatirlatmalar(veri["hatirlatmalar"], bugun)
    if not liste:
        print(f"{bugun}: gönderilecek hatırlatma yok.")
        return

    env_alici = os.environ.get("MAIL_TO", "")
    alicilar = [a.strip() for a in env_alici.split(",") if a.strip()] or veri.get("alicilar", [])
    gonderen = os.environ.get("MAIL_FROM") or os.environ.get("SMTP_USER", "hatirlatici@localhost")
    if not alicilar:
        sys.exit("Alıcı yok: MAIL_TO ortam değişkenini veya JSON'daki 'alicilar' alanını doldurun.")

    msg = mesaj_olustur(liste, gonderen, alicilar)
    if args.dry_run:
        print(msg)
        return

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.send_message(msg)
    print(f"{len(liste)} hatırlatma {', '.join(alicilar)} adresine gönderildi.")


if __name__ == "__main__":
    main()
