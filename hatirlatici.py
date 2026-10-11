"""
Gizli veri deposundaki (hatirlatma) hatirlatmalar.json dosyasından zamanı gelmiş hatırlatmaları
bulup e-posta olarak yollar, gönderilenleri gonderim.json dosyasına işler (aynı hatırlatma
tekrar gitmez). GitHub Actions her 10 dakikada bir çalıştırır.

DİKKAT: Bu depo herkese açıktır ve Actions günlükleri herkese görünür. Bu yüzden ekrana
hatırlatma metni, firma adı ya da adres YAZILMAZ; yalnızca sayılar yazılır.

Gerekli ortam değişkenleri: SMTP_HOST, SMTP_USER, SMTP_PASS, MAIL_TO
İsteğe bağlı: SMTP_PORT (587), MAIL_FROM (SMTP_USER)

Kullanım:
  python hatirlatici.py --veri veri                    # mail atar, gonderim.json'u günceller
  python hatirlatici.py --veri veri --dry-run          # mail atmaz, dosyaya yazmaz, içeriği yazdırır
  python hatirlatici.py --veri veri --simdi 2026-12-28T09:30 --dry-run
  python hatirlatici.py --uyari                        # veriye ulaşılamadı uyarısı (08:00-08:09 arası)
"""

import argparse
import calendar
import json
import os
import smtplib
import sys
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage

TR = timezone(timedelta(hours=3))      # Türkiye yıl boyu UTC+3
TOLERANS = timedelta(minutes=5)        # kayıt anından hemen önceki saat dilimi de geçerli sayılır
GERI_DONUS = timedelta(hours=48)       # uzun kesintiden sonra en fazla 2 günlük gecikmiş mail gider


# ---------- tarih mantığı ----------

def simdi_tr():
    return datetime.now(TR).replace(tzinfo=None, second=0, microsecond=0)


def gun_sec(y, a, g):
    return date(y, a, min(g, calendar.monthrange(y, a)[1]))


def olay_mi(k, hedef):
    """Hatırlatmanın olay günü `hedef` mi? Tekrarlı kayıtlarda `tarih` başlangıçtır (yoksa sınır yok)."""
    bas = date.fromisoformat(k["tarih"]) if k.get("tarih") else None
    if bas and hedef < bas:
        return False
    tur = k["tur"]
    if tur == "tek":
        return hedef == bas
    if tur == "haftalik":
        return (hedef - bas).days % 7 == 0
    if tur == "aylik":
        if gun_sec(hedef.year, hedef.month, k["gun"]) != hedef:
            return False
        aralik = int(k.get("aralik", 1))
        if aralik > 1 and bas:
            return ((hedef.year - bas.year) * 12 + hedef.month - bas.month) % aralik == 0
        return True
    return gun_sec(hedef.year, k["ay"], k["gun"]) == hedef  # yillik


def bekleyenler(hatirlatmalar, gonderilen, simdi):
    """Zamanı gelmiş ama gönderilmemiş (hatırlatma, olay günü, kaç gün önce) kayıtları."""
    sonuc = []
    for k in hatirlatmalar:
        saat = datetime.strptime(k["saat"], "%H:%M").time()
        olusturma = datetime.fromisoformat(k["olusturma"])
        for fark in sorted({int(x) for x in k["gunler"]}, reverse=True):
            for geri in range(3):
                gun = simdi.date() - timedelta(days=geri)
                hedef = gun + timedelta(days=fark)
                if not olay_mi(k, hedef):
                    continue
                slot = datetime.combine(gun, saat)
                if slot > simdi or slot < simdi - GERI_DONUS or slot < olusturma - TOLERANS:
                    continue
                if (k["id"], hedef.isoformat(), fark) in gonderilen:
                    continue
                sonuc.append({"id": k["id"], "metin": k["metin"], "olay": hedef.isoformat(), "fark": fark})
    return sonuc


# ---------- dosyalar ----------

def json_oku(yol, varsayilan):
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return varsayilan


def json_yaz(yol, veri):
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=1)
        f.write("\n")


# ---------- mail ----------

def mesaj(konu, govde):
    gonderen = os.environ.get("MAIL_FROM") or os.environ.get("SMTP_USER", "hatirlatici@localhost")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = gonderen, os.environ["MAIL_TO"], konu
    msg.set_content(govde)
    return msg


def smtp_gonder(msg):
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT") or 587), timeout=30) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.send_message(msg)


def tr_tarih(iso):
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y")


def uyari(dry_run):
    su = datetime.now(TR)
    if not (su.hour == 8 and su.minute < 10) and not dry_run:
        print("Veriye ulaşılamadı; uyarı maili yalnızca 08:00-08:09 arası gönderilir.")
        return
    msg = mesaj(
        "Hatırlatma verisine ulaşılamıyor",
        "Gizli depodaki hatırlatmalar okunamıyor, mailler gelmeyebilir.\n\n"
        "Olası neden: GitHub anahtarının (HATIRLATMA_TOKEN) süresi doldu ya da iptal edildi.\n"
        "Çözüm: github.com → Settings → Developer settings → Fine-grained tokens bölümünden yeni anahtar üret, "
        "ana depodaki HATIRLATMA_TOKEN secret'ını güncelle, hatırlatma sayfasında da yeni anahtarı yapıştır.\n",
    )
    if dry_run:
        print(msg["Subject"]); print(msg.get_content())
    else:
        smtp_gonder(msg)
        print("Uyarı maili gönderildi.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--veri", default="veri", help="gizli veri deposunun klasörü")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--simdi", help="YYYY-AA-GGTSS:DD (test için)")
    ap.add_argument("--uyari", action="store_true", help="veriye ulaşılamadı uyarı maili")
    args = ap.parse_args()

    if not os.environ.get("MAIL_TO"):
        sys.exit("MAIL_TO ortam değişkeni tanımlı olmalı.")
    if args.uyari:
        return uyari(args.dry_run)

    simdi = datetime.fromisoformat(args.simdi) if args.simdi else simdi_tr()
    hat_yolu = os.path.join(args.veri, "hatirlatmalar.json")
    log_yolu = os.path.join(args.veri, "gonderim.json")
    veri = json_oku(hat_yolu, {"hatirlatmalar": []})
    log = json_oku(log_yolu, [])
    gonderilen = {(o["id"], o["olay"], o["fark"]) for o in log}

    liste = bekleyenler(veri["hatirlatmalar"], gonderilen, simdi)
    if not liste:
        print("Gönderilecek hatırlatma yok.")
        return

    satirlar = [
        f"- {k['metin']} ({tr_tarih(k['olay'])}) - {'BUGÜN' if k['fark'] == 0 else str(k['fark']) + ' gün kaldı'}"
        for k in liste
    ]
    konu = liste[0]["metin"] if len(liste) == 1 else f"{len(liste)} hatırlatma"
    msg = mesaj(konu, "Hatırlatmalar:\n\n" + "\n".join(satirlar) + "\n")

    if args.dry_run:
        print(msg["Subject"]); print(msg.get_content())
        return

    smtp_gonder(msg)
    zaman = simdi.isoformat(timespec="minutes")
    log += [{"id": k["id"], "olay": k["olay"], "fark": k["fark"], "zaman": zaman} for k in liste]
    sinir = (simdi.date() - timedelta(days=7)).isoformat()
    log = [o for o in log if o["olay"] >= sinir]  # çok eski kayıtlar dosyayı şişirmesin
    json_yaz(log_yolu, log)
    print(f"{len(liste)} hatırlatma gönderildi.")  # metin yazılmaz: günlük herkese açık


if __name__ == "__main__":
    main()
