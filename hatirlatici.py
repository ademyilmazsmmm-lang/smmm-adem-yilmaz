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
  python hatirlatici.py --veri veri --yedek            # hatırlatma + yapılacaklar yedeğini mail eki olarak yollar
"""

import argparse
import calendar
import json
import os
import re
import smtplib
import sys
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr

TR = timezone(timedelta(hours=3))      # Türkiye yıl boyu UTC+3
TOLERANS = timedelta(minutes=5)        # kayıt anından hemen önceki saat dilimi de geçerli sayılır
GERI_DONUS = timedelta(hours=48)       # uzun kesintiden sonra en fazla 2 günlük gecikmiş mail gider


# ---------- tarih mantığı ----------

def simdi_tr():
    return datetime.now(TR).replace(tzinfo=None, second=0, microsecond=0)


def gun_sec(y, a, g):
    return date(y, a, min(g, calendar.monthrange(y, a)[1]))


TATIL_DOSYASI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hatirlatma-tatiller.json")
_tatil = None


def tatil_mi(d):
    """Hafta sonu ya da resmî tatil mi? (Bayram listesi yoksa yalnızca hafta sonu ve sabit tatiller sayılır.)"""
    global _tatil
    if _tatil is None:
        try:
            with open(TATIL_DOSYASI, encoding="utf-8") as f:
                v = json.load(f)
        except (OSError, ValueError):
            v = {}
        _tatil = ({str(x) for x in v.get("sabit", [])},
                  {str(x) for y in v.get("yillar", {}).values() for x in y})
    return d.weekday() >= 5 or d.strftime("%m-%d") in _tatil[0] or d.isoformat() in _tatil[1]


def is_gunu_kaydir(d):
    while tatil_mi(d):
        d += timedelta(days=1)
    return d


def takvim_tarihi(k, y, a):
    """tur=takvim: ayın `gun`'ü ('son' = ayın son günü); tatile/hafta sonuna denk gelirse ilk iş günü."""
    g = calendar.monthrange(y, a)[1] if k.get("gun") == "son" else int(k["gun"])
    d = gun_sec(y, a, g)
    return is_gunu_kaydir(d) if k.get("kaydir", True) else d


def olay_mi(k, hedef):
    """Hatırlatmanın olay günü `hedef` mi? Tekrarlı kayıtlarda `tarih` başlangıçtır (yoksa sınır yok)."""
    bas = date.fromisoformat(k["tarih"]) if k.get("tarih") else None
    if bas and hedef < bas:
        return False
    tur = k["tur"]
    if tur == "takvim":
        # kayma en fazla birkaç gün sürer: hedefin ayına ve bir önceki aya bakmak yeter
        for y, a in ((hedef.year, hedef.month), (hedef.year - (hedef.month == 1), (hedef.month - 2) % 12 + 1)):
            if a in k["aylar"] and takvim_tarihi(k, y, a) == hedef:
                return True
        return False
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
                sonuc.append({"id": k["id"], "metin": k["metin"], "olay": hedef.isoformat(), "fark": fark,
                              "etiket": k.get("etiket", "Tarih"), "alici": k.get("alici")})
    return sonuc


def gorev_hatirlatmalari(yap):
    """Son tarihi olan, tamamlanmamış yapılacaklar da hatırlatma gibi mail atar (yapılacaklar.json)."""
    sonuc = []
    for g in yap.get("ogeler", []):
        if g.get("tamam") or not g.get("son") or g["id"] < 0:
            continue
        firma = g.get("firma")
        sonuc.append({
            "id": f"g{g['id']}", "tur": "tek", "tarih": g["son"],
            "gunler": g.get("gunler") or [3, 0], "saat": g.get("saat") or "09:00",
            "metin": f"{firma}: {g['metin']}" if firma else g["metin"],
            "olusturma": g["olusturma"], "etiket": g.get("etiket") or "Son gün",
        })
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

IMZA = "\n\nSaygılarımla\nAdem Yılmaz\nhttps://smmmyilmaz.com\n"
EPOSTA = re.compile(r"^[^@\s,;<>\"]+@[^@\s,;<>\"]+\.[^@\s,;<>\"]+$")


def alicilari_ekle(hatirlatmalar, kisiler):
    """Kişi seçilmiş hatırlatmalar için her kişiye AYRI bir kopya üretir (kimse başkasının adresini görmez).
    Kopyanın kimliği '<id>|k<kisi>' olur; böylece gönderim kaydı, geri dönüş ve tekrar gönderimi engelleme aynen çalışır."""
    adres, vergi = {}, []
    for c in (kisiler or {}).get("kisiler", []):
        e = str(c.get("eposta", "")).strip()
        if EPOSTA.match(e):
            adres[c.get("id")] = e
            if c.get("vergi"):
                vergi.append(c.get("id"))
    sonuc = list(hatirlatmalar)
    for k in hatirlatmalar:
        hedefler = list(k.get("kisi") or [])
        if k.get("grup") == "vergi":      # vergi takvimi: "vergi takvimini de alsın" denen herkese
            hedefler += [v for v in vergi if v not in hedefler]
        # kisi_gunler: kişilere yalnızca bu günlerdeki mail gider (örn. [2] = yalnızca 2 gün önceki; son gün yalnızca sahibine)
        gunler = [g for g in k["gunler"] if "kisi_gunler" not in k or g in k["kisi_gunler"]]
        if not gunler:
            continue
        for kid in hedefler:
            if kid in adres:
                sonuc.append({**k, "id": f"{k['id']}|k{kid}", "alici": adres[kid], "gunler": gunler})
    return sonuc


def mesaj(konu, govde, alici=None):
    adres = os.environ.get("MAIL_FROM") or os.environ.get("SMTP_USER", "hatirlatici@localhost")
    # Gelen kutusunda adres yerine görünen ad: sana gelenler "HATIRLATICI", başkalarına gidenler "Adem Yılmaz Hatırlatıcı"
    ad = os.environ.get("MAIL_FROM_ADI", "Adem Yılmaz Hatırlatıcı") if alici else "HATIRLATICI"
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = formataddr((ad, adres)), alici or os.environ["MAIL_TO"], konu
    msg.set_content(govde)
    return msg


def hatirlatma_maili(k):
    """Konu: hatırlatma metninin kendisi (başlık enjeksiyonuna karşı tek satıra indirilir)."""
    konu = " ".join(str(k["metin"]).split()) or "Hatırlatma"
    if k["fark"] == 0:
        zaman = "BUGÜN"
    elif k["fark"] > 0:
        zaman = f"{k['fark']} gün kaldı"
    else:
        zaman = f"{-k['fark']} gün önce"   # tarihten sonra gelen hatırlatma (negatif gün)
    return mesaj(konu, f"{konu}\n\n{k.get('etiket', 'Tarih')}: {tr_tarih(k['olay'])} ({zaman})" + IMZA, k.get("alici"))


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


def yedek(veri_klasoru, dry_run):
    """Hatırlatma ve yapılacaklar verisini JSON eki olarak mailler. Günlüğe yalnızca sayılar yazılır."""
    hat = json_oku(os.path.join(veri_klasoru, "hatirlatmalar.json"), {"sonraki_id": 1, "hatirlatmalar": []})
    yap = json_oku(os.path.join(veri_klasoru, "yapilacaklar.json"), {"sonraki_id": 1, "ogeler": []})
    sab = json_oku(os.path.join(veri_klasoru, "sablonlar.json"), None)
    kis = json_oku(os.path.join(veri_klasoru, "kisiler.json"), None)
    bugun = simdi_tr().date()
    acik = sum(1 for g in yap["ogeler"] if not g.get("tamam"))
    bitti = len(yap["ogeler"]) - acik
    govde = (
        "Hatırlatma ve yapılacaklar yedeği ekte.\n\n"
        f"Hatırlatma: {len(hat['hatirlatmalar'])}\n"
        f"Yapılacak: {acik} açık, {bitti} tamamlanmış\n\n"
        "Geri yüklemek için ekteki dosyadaki \"hatirlatmalar\", \"yapilacaklar\" (ve varsa \"sablonlar\", \"kisiler\") bölümlerini,\n"
        "gizli depodaki aynı adlı .json dosyalarına koy.\n"
    )
    msg = mesaj(f"Hatırlatma yedeği ({bugun.strftime('%d.%m.%Y')})", govde)
    icerik = {"hatirlatmalar": hat, "yapilacaklar": yap}
    if sab is not None:
        icerik["sablonlar"] = sab
    if kis is not None:
        icerik["kisiler"] = kis
    ek = json.dumps(icerik, ensure_ascii=False, indent=1).encode("utf-8")
    ek_adi = f"hatirlatma-yedek-{bugun.isoformat()}.json"
    msg.add_attachment(ek, maintype="application", subtype="json", filename=ek_adi)
    if dry_run:
        print(msg["Subject"]); print(govde); print("Ek:", ek_adi, len(ek), "bayt")
        return
    smtp_gonder(msg)
    print(f"Yedek gönderildi: {len(hat['hatirlatmalar'])} hatırlatma, {len(yap['ogeler'])} yapılacak.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--veri", default="veri", help="gizli veri deposunun klasörü")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--simdi", help="YYYY-AA-GGTSS:DD (test için)")
    ap.add_argument("--uyari", action="store_true", help="veriye ulaşılamadı uyarı maili")
    ap.add_argument("--yedek", action="store_true", help="hatırlatma ve yapılacaklar yedeğini mail eki olarak gönder")
    args = ap.parse_args()

    if not os.environ.get("MAIL_TO"):
        sys.exit("MAIL_TO ortam değişkeni tanımlı olmalı.")
    if args.uyari:
        return uyari(args.dry_run)
    if args.yedek:
        return yedek(args.veri, args.dry_run)

    simdi = datetime.fromisoformat(args.simdi) if args.simdi else simdi_tr()
    hat_yolu = os.path.join(args.veri, "hatirlatmalar.json")
    log_yolu = os.path.join(args.veri, "gonderim.json")
    veri = json_oku(hat_yolu, {"hatirlatmalar": []})
    log = json_oku(log_yolu, [])
    gonderilen = {(o["id"], o["olay"], o["fark"]) for o in log}

    yap = json_oku(os.path.join(args.veri, "yapilacaklar.json"), {"ogeler": []})
    kisiler = json_oku(os.path.join(args.veri, "kisiler.json"), {"kisiler": []})
    liste = bekleyenler(alicilari_ekle(veri["hatirlatmalar"], kisiler) + gorev_hatirlatmalari(yap), gonderilen, simdi)
    if not liste:
        print("Gönderilecek hatırlatma yok.")
        return

    # Her hatırlatma kendi konusuyla AYRI bir mail olarak gider. Bir kesintiden sonra aynı hatırlatmanın
    # birden fazla kaçmış slotu birikmişse (örn. "1 gün kaldı" ve "bugün") yalnızca en yakın olanı gönderilir,
    # hepsi gönderildi sayılır.
    gruplar = {}
    for k in liste:
        gruplar.setdefault((k["id"], k["olay"]), []).append(k)
    gonderilecek = sorted((min(g, key=lambda x: x["fark"]) for g in gruplar.values()),
                          key=lambda x: (x["olay"], str(x["id"])))

    if args.dry_run:
        for k in gonderilecek:
            m = hatirlatma_maili(k); print("Kime:", m["To"]); print("Konu:", m["Subject"]); print(m.get_content())
        return

    zaman = simdi.isoformat(timespec="minutes")
    basarili, basarisiz = 0, 0
    for k in gonderilecek:
        try:
            smtp_gonder(hatirlatma_maili(k))
        except Exception as e:  # tek bir mail diğerlerini engellemesin; gönderilmeyen bir sonraki çalışmada denenir
            basarisiz += 1
            print(f"Bir hatırlatma gönderilemedi ({type(e).__name__}).")  # metin yazılmaz: günlük herkese açık
            continue
        basarili += 1
        log += [{"id": s["id"], "olay": s["olay"], "fark": s["fark"], "zaman": zaman} for s in gruplar[(k["id"], k["olay"])]]
    sinir = (simdi.date() - timedelta(days=7)).isoformat()
    log = [o for o in log if o["olay"] >= sinir]  # çok eski kayıtlar dosyayı şişirmesin
    json_yaz(log_yolu, log)
    print(f"{basarili} hatırlatma gönderildi." + (f" {basarisiz} gönderilemedi." if basarisiz else ""))
    if basarisiz:
        sys.exit(1)


if __name__ == "__main__":
    main()
