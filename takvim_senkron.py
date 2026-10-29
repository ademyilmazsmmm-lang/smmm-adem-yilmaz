"""
Gizli veri deposundaki hatırlatmaları (hatirlatmalar.json, yapilacaklar.json) Google Takvim'deki
ayrı bir takvime TEK YÖNLÜ eşitler; zamanı gelince telefona takvim bildirimi düşer. Mail programıyla
aynı slot mantığını kullanır: her "kaç gün önce" günü için o gün ve saatte bir takvim etkinliği açılır
(bildirimi takvimin kendi "etkinlik saatinde" ayarı verir). Tamamlanan, silinen ya da değişen
hatırlatmalar takvimde de kalkar/güncellenir. Eşitleme her çalışmada baştan hesaplanır, durum tutmaz.

DİKKAT: Bu depo herkese açıktır ve Actions günlükleri herkese görünür. Bu yüzden ekrana hatırlatma
metni ya da firma adı YAZILMAZ; yalnızca sayılar ve Google'ın hata kodu yazılır.

Gerekli ortam değişkenleri: GOOGLE_SA_JSON (hizmet hesabı anahtarının içeriği), TAKVIM_ID
Bağımlılık yok: RS256 imzası için sistemdeki `openssl` kullanılır.

Kullanım:
  python takvim_senkron.py --veri veri                      # takvimi eşitler
  python takvim_senkron.py --veri veri --dry-run            # Google'a bağlanmaz; üretilecek etkinlikleri yazdırır
  python takvim_senkron.py --veri veri --simdi 2026-12-28T09:30 --dry-run
"""

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta
from urllib import error, parse, request

import hatirlatici as h

PENCERE = 45                  # bugünden itibaren kaç gün ilerisi takvimde tutulur
SURE = timedelta(minutes=30)  # etkinlik süresi
ZONE = "Europe/Istanbul"
KAPSAM = "https://www.googleapis.com/auth/calendar"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/calendar/v3/calendars/"
TR_OFSET = "+03:00"
ISARET = "hatirlatma"         # bu program tarafından açılan etkinliklerin gizli işareti
TUR_ADIM = 100                # bir çalışmada en fazla bu kadar ekleme/güncelleme/silme (kota koruması)


# ---------- istenen etkinlikler ----------

def etkinlik_kimligi(kid, olay, fark):
    """Google'ın izin verdiği karakterlerden (0-9, a-v) oluşan sabit kimlik: aynı slot hep aynı etkinlik olur."""
    return "hat" + hashlib.sha1(f"{kid}|{olay}|{fark}".encode()).hexdigest()[:32]


def zaman_yazisi(fark):
    if fark == 0:
        return "BUGÜN"
    return f"{fark} gün kaldı" if fark > 0 else f"{-fark} gün önce"


def _gov(kid, olay, fark, k, baslangic, tum_gun):
    metin = " ".join(str(k["metin"]).split()) or "Hatırlatma"
    gov = {
        "summary": metin if tum_gun else f"{metin} ({zaman_yazisi(fark)})",
        "description": f"{k.get('etiket', 'Tarih')}: {h.tr_tarih(olay)} ({zaman_yazisi(fark)})\n{h.SAYFA}",
        "reminders": {"useDefault": True},
    }
    if tum_gun:
        gov["start"] = {"date": olay}
        gov["end"] = {"date": (date.fromisoformat(olay) + timedelta(days=1)).isoformat()}
    else:
        bit = baslangic + SURE
        gov["start"] = {"dateTime": baslangic.isoformat(timespec="seconds") + TR_OFSET, "timeZone": ZONE}
        gov["end"] = {"dateTime": bit.isoformat(timespec="seconds") + TR_OFSET, "timeZone": ZONE}
    ozet = hashlib.sha1(json.dumps(gov, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    gov["extendedProperties"] = {"private": {ISARET: "1", "h": ozet}}
    return gov


def istenen_etkinlikler(hatirlatmalar, simdi, pencere=PENCERE):
    """{etkinlik kimliği: gövde}. Mail slotlarıyla aynı kural: her hatırlatma için `gunler` listesindeki her gün
    olay gününden o kadar önce (negatifse sonra) `saat`te bir etkinlik; `gunler`de 0 yoksa olay günü için
    bildirimsiz bir tüm gün etkinliği de eklenir. Tamamlananlar ve geçmiş slotlar atlanır."""
    bugun = simdi.date()
    son = bugun + timedelta(days=pencere)
    sonuc = {}
    for k in hatirlatmalar:
        if k.get("tamam"):
            continue
        bitenler = set(k.get("tamamlanan") or [])
        gunler = sorted({int(x) for x in k.get("gunler") or []}, reverse=True)
        if not gunler:
            continue
        saat = datetime.strptime(k["saat"], "%H:%M").time()
        olusturma = datetime.fromisoformat(k["olusturma"]) if k.get("olusturma") else None
        gun = bugun
        while gun <= son:
            for fark in gunler:
                olay = gun + timedelta(days=fark)
                if olay.isoformat() in bitenler or not h.olay_mi(k, olay):
                    continue
                slot = datetime.combine(gun, saat)
                if olusturma and slot < olusturma - h.TOLERANS:
                    continue
                kid = etkinlik_kimligi(k["id"], olay.isoformat(), fark)
                sonuc[kid] = _gov(k["id"], olay.isoformat(), fark, k, slot, False)
            gun += timedelta(days=1)
        if 0 not in gunler:                       # olay günü de takvimde görünsün (bildirimsiz)
            gun = bugun
            while gun <= son:
                if gun.isoformat() not in bitenler and h.olay_mi(k, gun):
                    sonuc[etkinlik_kimligi(k["id"], gun.isoformat(), "d")] = _gov(k["id"], gun.isoformat(), 0, k, None, True)
                gun += timedelta(days=1)
    return sonuc


# ---------- Google ----------

class Hata(Exception):
    def __init__(self, durum, neden=""):
        super().__init__(f"{durum} {neden}".strip())
        self.durum, self.neden = durum, neden


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def rs256_imzala(ozel_anahtar, veri):
    """openssl ile RS256 (SHA-256 + PKCS#1 v1.5) imzası; anahtar yalnızca kısa süre 0600 dosyada durur."""
    with tempfile.TemporaryDirectory() as t:
        yol = os.path.join(t, "k.pem")
        fd = os.open(yol, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(ozel_anahtar)
        try:
            return subprocess.run(["openssl", "dgst", "-sha256", "-sign", yol], input=veri,
                                  capture_output=True, check=True).stdout
        except (subprocess.CalledProcessError, OSError):
            raise Hata("anahtar", "özel anahtar okunamadı ya da openssl yok")


def jwt_uret(sa, simdi_ts, imzala=rs256_imzala):
    baslik = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    ic = _b64(json.dumps({"iss": sa["client_email"], "scope": KAPSAM, "aud": TOKEN_URL,
                          "iat": simdi_ts, "exp": simdi_ts + 3600}).encode())
    govde = f"{baslik}.{ic}"
    return govde + "." + _b64(imzala(sa["private_key"], govde.encode()))


def istek(yontem, url, veri=None, token=None, form=None):
    """Tek HTTP isteği. Hata gövdesi yazdırılmaz (metin içerebilir); yalnızca durum kodu ve Google'ın hata nedeni."""
    govde, basliklar = None, {}
    if form is not None:
        govde = parse.urlencode(form).encode()
        basliklar["Content-Type"] = "application/x-www-form-urlencoded"
    elif veri is not None:
        govde = json.dumps(veri).encode()
        basliklar["Content-Type"] = "application/json"
    if token:
        basliklar["Authorization"] = "Bearer " + token
    for deneme in range(4):
        try:
            with request.urlopen(request.Request(url, data=govde, method=yontem, headers=basliklar), timeout=30) as r:
                ham = r.read()
            return json.loads(ham) if ham else {}
        except error.HTTPError as e:
            neden = ""
            try:
                j = json.loads(e.read())
                neden = j["error"] if isinstance(j.get("error"), str) else j["error"]["errors"][0]["reason"]
            except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                pass
            gecici = e.code in (429, 500, 502, 503, 504) or (e.code == 403 and "ratelimit" in neden.lower())
            if gecici and deneme < 3:
                time.sleep(2 ** deneme)
                continue
            raise Hata(e.code, neden)
        except (error.URLError, TimeoutError, OSError) as e:
            if deneme < 3:
                time.sleep(2 ** deneme)
                continue
            raise Hata("ag", type(e).__name__)


def erisim_anahtari(sa, http=istek, simdi_ts=None, imzala=rs256_imzala):
    jwt = jwt_uret(sa, int(simdi_ts if simdi_ts is not None else time.time()), imzala)
    return http("POST", TOKEN_URL, form={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                         "assertion": jwt})["access_token"]


class Takvim:
    def __init__(self, takvim_id, token, http=istek):
        self.taban = API + parse.quote(takvim_id, safe="") + "/events"
        self.token, self.http = token, http

    def listele(self, zmin, zmax):
        """Bu programın açtığı etkinlikler: {kimlik: içerik özeti}."""
        sonuc, sayfa = {}, None
        while True:
            q = {"timeMin": zmin, "timeMax": zmax, "maxResults": 2500, "showDeleted": "false",
                 "privateExtendedProperty": f"{ISARET}=1", "fields": "nextPageToken,items(id,extendedProperties)"}
            if sayfa:
                q["pageToken"] = sayfa
            r = self.http("GET", self.taban + "?" + parse.urlencode(q), token=self.token)
            for e in r.get("items", []):
                sonuc[e["id"]] = ((e.get("extendedProperties") or {}).get("private") or {}).get("h", "")
            sayfa = r.get("nextPageToken")
            if not sayfa:
                return sonuc

    def ekle(self, kid, gov):
        try:
            self.http("POST", self.taban, veri={"id": kid, **gov}, token=self.token)
        except Hata as e:
            if e.durum != 409:
                raise
            # daha önce silinmiş (iptal edilmiş) aynı kimlikli etkinlik: yeniden canlandır
            self.http("PUT", f"{self.taban}/{kid}", veri={**gov, "status": "confirmed"}, token=self.token)

    def guncelle(self, kid, gov):
        self.http("PATCH", f"{self.taban}/{kid}", veri=gov, token=self.token)

    def sil(self, kid):
        try:
            self.http("DELETE", f"{self.taban}/{kid}", token=self.token)
        except Hata as e:
            if e.durum not in (404, 410):
                raise


def esitle(takvim, istenen, mevcut, sinir=TUR_ADIM):
    """İstenen ile takvimdekini karşılaştırıp farkı uygular. Dönüş: (eklenen, güncellenen, silinen, kalan)."""
    silinecek = sorted(i for i in mevcut if i not in istenen)
    eklenecek = sorted((i for i in istenen if i not in mevcut), key=lambda i: istenen[i]["start"].get("dateTime") or istenen[i]["start"]["date"])
    degisecek = [i for i in istenen if i in mevcut and mevcut[i] != istenen[i]["extendedProperties"]["private"]["h"]]
    e = g = s = 0
    for i in silinecek:
        if e + g + s >= sinir:
            break
        takvim.sil(i); s += 1
    for i in degisecek:
        if e + g + s >= sinir:
            break
        takvim.guncelle(i, istenen[i]); g += 1
    for i in eklenecek:
        if e + g + s >= sinir:
            break
        takvim.ekle(i, istenen[i]); e += 1
    kalan = len(silinecek) + len(degisecek) + len(eklenecek) - (e + g + s)
    return e, g, s, kalan


# ---------- ana program ----------

def main(argv=None, http=istek, imzala=rs256_imzala):
    ap = argparse.ArgumentParser()
    ap.add_argument("--veri", default="veri", help="gizli veri deposunun klasörü")
    ap.add_argument("--dry-run", action="store_true", help="Google'a bağlanmaz; üretilecek etkinlikleri yazdırır")
    ap.add_argument("--simdi", help="YYYY-AA-GGTSS:DD (test için)")
    args = ap.parse_args(argv)

    simdi = datetime.fromisoformat(args.simdi) if args.simdi else h.simdi_tr()
    veri = h.json_oku(os.path.join(args.veri, "hatirlatmalar.json"), {"hatirlatmalar": []})
    yap = h.json_oku(os.path.join(args.veri, "yapilacaklar.json"), {"ogeler": []})
    istenen = istenen_etkinlikler(veri["hatirlatmalar"] + h.gorev_hatirlatmalari(yap), simdi)

    if args.dry_run:
        for kid, g in sorted(istenen.items(), key=lambda x: x[1]["start"].get("dateTime") or x[1]["start"]["date"]):
            print(g["start"].get("dateTime") or g["start"]["date"], "|", g["summary"])
        print(f"{len(istenen)} etkinlik üretilecek.")
        return 0

    sa_json, takvim_id = os.environ.get("GOOGLE_SA_JSON"), os.environ.get("TAKVIM_ID")
    if not sa_json or not takvim_id:
        print("Google Takvim ayarlı değil (GOOGLE_SA_JSON / TAKVIM_ID tanımlı değil); atlandı.")
        return 0
    try:
        sa = json.loads(sa_json)
        token = erisim_anahtari(sa, http, imzala=imzala)
        takvim = Takvim(takvim_id, token, http)
        zmin = datetime.combine(simdi.date(), datetime.min.time()).isoformat(timespec="seconds") + TR_OFSET
        zmax = datetime.combine(simdi.date() + timedelta(days=PENCERE + 1), datetime.min.time()).isoformat(timespec="seconds") + TR_OFSET
        e, g, s, kalan = esitle(takvim, istenen, takvim.listele(zmin, zmax))
    except (Hata, ValueError, KeyError) as ex:
        ad = f"{ex.durum} {ex.neden}".strip() if isinstance(ex, Hata) else type(ex).__name__
        print(f"Takvim eşitlenemedi ({ad}).")      # ayrıntı yazılmaz: günlük herkese açık
        return 1
    print(f"Takvim eşitlendi: {len(istenen)} etkinlik (eklenen {e}, güncellenen {g}, silinen {s})."
          + (f" {kalan} işlem sonraki çalışmaya kaldı." if kalan else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
