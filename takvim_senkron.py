"""
Gizli veri deposundaki hatırlatmaları (hatirlatmalar.json, yapilacaklar.json) Google Takvim'deki
ayrı bir takvime TEK YÖNLÜ eşitler; zamanı gelince telefona takvim bildirimi düşer. Mail programıyla
aynı slot mantığını kullanır: her "kaç gün önce" günü için o gün ve saatte bir takvim etkinliği açılır
(bildirimi takvimin kendi "etkinlik saatinde" ayarı verir). Tamamlanan, silinen ya da değişen
hatırlatmalar takvimde de kalkar/güncellenir. Eşitleme her çalışmada baştan hesaplanır, durum tutmaz.

Takvimden silinen etkinlik uygulamada da karşılığını bulur: programın açtığı bir etkinlik takvimde silinirse
(Google'da "iptal" olduğu doğrulanırsa) tek seferlik hatırlatma silinir; tekrarlı hatırlatmada o tarih,
yapılacaklarda görev tamamlandı olur. Hangi etkinliklerin bizim tarafımızdan açıldığını `takvim-durum.json`
(yalnızca etkinlik kimlikleri) tutar; böylece kendi sildiklerimiz kullanıcı silmesi sanılmaz.

Ters yön: takvime elle yazılan (programın açmadığı) etkinlikler hatırlatma olarak uygulamaya alınır
(etkinlik günü ve 1 gün önce, etkinliğin saatinde). Etkinlik değişir/silinirse hatırlatma da güncellenir/silinir.
Tekrarlı etkinlikler alınmaz. Etkinlik, hatırlatma kaydı gerçekten yazıldıktan sonraki çalışmada "alındı"
diye işaretlenir; böylece kayıt bir sebeple yazılamazsa bir sonraki çalışma yeniden dener.

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
ALINDI = "ice"                # takvimden uygulamaya alınmış kullanıcı etkinliklerinin gizli işareti
ALMA_PENCERE = 60             # bugünden itibaren kaç gün ilerisindeki kullanıcı etkinlikleri alınır
ALMA_GUNLER = [1, 0]          # alınan etkinliklere mail: etkinlik günü ve 1 gün önce
ALMA_SAAT = "11:00"           # tüm gün etkinliklerinde varsayılan saat
SILME_SINIRI = 10             # bir çalışmada en fazla bu kadar alınmış hatırlatma, kullanıcı etkinliği silindiği için silinir
KULLANICI_SILME_SINIRI = 50   # bir çalışmada en fazla bu kadar etkinlik silmesi uygulamaya yansıtılır


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


def istenen_etkinlikler(hatirlatmalar, simdi, pencere=PENCERE, kaynak=None):
    """{etkinlik kimliği: gövde}. Mail slotlarıyla aynı kural: her hatırlatma için `gunler` listesindeki her gün
    olay gününden o kadar önce (negatifse sonra) `saat`te bir etkinlik; `gunler`de 0 yoksa olay günü için
    bildirimsiz bir tüm gün etkinliği de eklenir. Tamamlananlar ve geçmiş slotlar atlanır.
    `kaynak` verilirse {etkinlik kimliği: (hatırlatma kimliği, olay günü)} ile doldurulur."""
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
        alinan = bool(k.get("takvim_olay"))       # kullanıcının kendi etkinliği zaten takvimde
        gun = bugun
        while gun <= son:
            for fark in gunler:
                if alinan and fark == 0 and not k.get("takvim_tum_gun"):
                    continue                       # etkinliğin kendisi o saatte bildirim verir
                olay = gun + timedelta(days=fark)
                if olay.isoformat() in bitenler or not h.olay_mi(k, olay):
                    continue
                slot = datetime.combine(gun, saat)
                if olusturma and slot < olusturma - h.TOLERANS:
                    continue
                kid = etkinlik_kimligi(k["id"], olay.isoformat(), fark)
                sonuc[kid] = _gov(k["id"], olay.isoformat(), fark, k, slot, False)
                if kaynak is not None:
                    kaynak[kid] = (str(k["id"]), olay.isoformat())
            gun += timedelta(days=1)
        if 0 not in gunler and not alinan:        # olay günü de takvimde görünsün (bildirimsiz)
            gun = bugun
            while gun <= son:
                if gun.isoformat() not in bitenler and h.olay_mi(k, gun):
                    kid = etkinlik_kimligi(k["id"], gun.isoformat(), "d")
                    sonuc[kid] = _gov(k["id"], gun.isoformat(), 0, k, None, True)
                    if kaynak is not None:
                        kaynak[kid] = (str(k["id"]), gun.isoformat())
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

    ALAN = "nextPageToken,items(id,status,summary,start,updated,recurrence,recurringEventId,extendedProperties)"

    def listele_hepsi(self, zmin, zmax):
        """Takvimdeki tüm etkinlikler (kullanıcınınkiler dahil)."""
        sonuc, sayfa = [], None
        while True:
            q = {"timeMin": zmin, "timeMax": zmax, "maxResults": 2500, "showDeleted": "false", "fields": self.ALAN}
            if sayfa:
                q["pageToken"] = sayfa
            r = self.http("GET", self.taban + "?" + parse.urlencode(q), token=self.token)
            sonuc += r.get("items", [])
            sayfa = r.get("nextPageToken")
            if not sayfa:
                return sonuc

    def getir(self, kid):
        """Tek etkinlik; silinmişse None."""
        try:
            e = self.http("GET", f"{self.taban}/{kid}?" + parse.urlencode({"fields": self.ALAN.split("(", 1)[1][:-1]}), token=self.token)
        except Hata as ex:
            if ex.durum in (404, 410):
                return None
            raise
        return None if e.get("status") == "cancelled" else e

    def silindi_mi(self, kid):
        """Etkinlik Google'da gerçekten silinmiş (iptal) mi? Bulunamazsa (404) silinmiş SAYILMAZ."""
        try:
            e = self.http("GET", f"{self.taban}/{kid}?fields=status", token=self.token)
        except Hata as ex:
            if ex.durum == 410:
                return True
            if ex.durum == 404:
                return False
            raise
        return e.get("status") == "cancelled"

    def isaretle(self, kid):
        """Kullanıcı etkinliğini "alındı" diye işaretler; yeni `updated` değerini döndürür."""
        r = self.http("PATCH", f"{self.taban}/{kid}?fields=updated",
                      veri={"extendedProperties": {"private": {ALINDI: "1"}}}, token=self.token)
        return r.get("updated", "")

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
    """İstenen ile takvimdekini karşılaştırıp farkı uygular.
    Dönüş: (eklenen, güncellenen, silinen, kalan, işlem sonrası takvimde bulunan istenen kimlikler)."""
    silinecek = sorted(i for i in mevcut if i not in istenen)
    eklenecek = sorted((i for i in istenen if i not in mevcut), key=lambda i: istenen[i]["start"].get("dateTime") or istenen[i]["start"]["date"])
    degisecek = [i for i in istenen if i in mevcut and mevcut[i] != istenen[i]["extendedProperties"]["private"]["h"]]
    e = g = s = 0
    var = {i for i in istenen if i in mevcut}
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
        takvim.ekle(i, istenen[i]); e += 1; var.add(i)
    kalan = len(silinecek) + len(degisecek) + len(eklenecek) - (e + g + s)
    return e, g, s, kalan, var


# ---------- takvimden uygulamaya (kullanıcının kendi etkinlikleri) ----------

def _ozel(ev):
    return (ev.get("extendedProperties") or {}).get("private") or {}


def olay_ozeti(ev):
    """Etkinlikten (metin, tarih, saat, tüm_gün); anlaşılmazsa None. Saatler Türkiye saatine çevrilir."""
    bas = ev.get("start") or {}
    metin = " ".join(str(ev.get("summary") or "").split())[:300] or "Takvim etkinliği"
    try:
        if bas.get("dateTime"):
            d = datetime.fromisoformat(bas["dateTime"].replace("Z", "+00:00"))
            d = d.astimezone(h.TR).replace(tzinfo=None) if d.tzinfo else d
            return metin, d.date().isoformat(), d.strftime("%H:%M"), False
        if bas.get("date"):
            date.fromisoformat(bas["date"])
            return metin, bas["date"], ALMA_SAAT, True
    except ValueError:
        pass
    return None


def _uygula(r, ozet, guncel):
    """Alınmış hatırlatmayı etkinliğin güncel hâline getirir; değiştiyse True."""
    metin, tarih, saat, tum = ozet
    degisti = (r.get("metin"), r.get("tarih"), r.get("saat")) != (metin, tarih, saat)
    if degisti:
        if r.get("tarih") != tarih:
            r.pop("tamam", None); r.pop("tamamlanma", None)      # tarih kaydıysa yeniden hatırlatılsın
        r["metin"], r["tarih"], r["saat"] = metin, tarih, saat
    r["takvim_tum_gun"] = tum
    r["takvim_guncel"] = guncel
    return degisti


def takvimden_al(takvim, veri, simdi):
    """Programın açmadığı etkinlikleri `veri` (hatirlatmalar.json sözlüğü) içine hatırlatma olarak alır; yerinde değiştirir.
    Dönüş: (alınan, güncellenen, silinen)."""
    hat = veri.setdefault("hatirlatmalar", [])
    bugun = simdi.date()
    zmin = datetime.combine(bugun, datetime.min.time()).isoformat(timespec="seconds") + TR_OFSET
    zmax = datetime.combine(bugun + timedelta(days=ALMA_PENCERE + 1), datetime.min.time()).isoformat(timespec="seconds") + TR_OFSET
    olaylar = {}
    for ev in takvim.listele_hepsi(zmin, zmax):
        if ev.get("status") == "cancelled" or _ozel(ev).get(ISARET) or ev.get("recurrence") or ev.get("recurringEventId"):
            continue                                   # programın kendi etkinlikleri ve tekrarlılar alınmaz
        olaylar[ev["id"]] = ev
    benim = {r["takvim_olay"]: r for r in hat if r.get("takvim_olay")}
    alinan = guncellenen = silinen = 0
    for kid, ev in olaylar.items():
        ozet = olay_ozeti(ev)
        if not ozet:
            continue
        guncel, isaretli = ev.get("updated", ""), _ozel(ev).get(ALINDI) == "1"
        r = benim.get(kid)
        if r is None:
            if isaretli:
                continue                               # uygulamadan silinmiş: yeniden alınmaz
            metin, tarih, saat, tum = ozet
            if (tarih < bugun.isoformat()) if tum else (datetime.fromisoformat(f"{tarih}T{saat}") < simdi):
                continue                               # geçmiş etkinlik
            yeni = veri.get("sonraki_id") or (max([x["id"] for x in hat if isinstance(x.get("id"), int)] + [0]) + 1)
            veri["sonraki_id"] = yeni + 1
            hat.append({"id": yeni, "gunler": list(ALMA_GUNLER), "saat": saat, "metin": metin,
                        "olusturma": simdi.isoformat(timespec="minutes"), "tur": "tek", "tarih": tarih,
                        "takvim_olay": kid, "takvim_guncel": guncel, "takvim_tum_gun": tum})
            alinan += 1
            continue
        if guncel != r.get("takvim_guncel") and _uygula(r, ozet, guncel):
            guncellenen += 1
        if not isaretli:                               # kayıt yazılmış (ikinci çalışma): artık işaretle
            r["takvim_guncel"] = takvim.isaretle(kid)
    kontrol = 0
    for kid, r in benim.items():
        if kid in olaylar or r.get("tarih", "") < bugun.isoformat() or kontrol >= 20:
            continue
        kontrol += 1
        ev = takvim.getir(kid)                         # pencere dışına taşınmış olabilir
        if ev is None:
            if silinen < SILME_SINIRI:
                hat.remove(r); silinen += 1
        else:
            ozet = olay_ozeti(ev)
            if ozet and ev.get("updated", "") != r.get("takvim_guncel") and _uygula(r, ozet, ev.get("updated", "")):
                guncellenen += 1
    return alinan, guncellenen, silinen


# ---------- takvimden silinenler uygulamaya ----------

def silinenleri_isle(takvim, kayip, kaynak, veri, yap, simdi):
    """Takvimde kullanıcı tarafından silinmiş etkinliklerin hatırlatmalarını işler (veri/yap yerinde değişir).
    Önce her etkinliğin Google'da gerçekten iptal olduğu doğrulanır. Dönüş: işlenen hatırlatma/tarih sayısı."""
    birimler = []
    for kid in sorted(kayip)[:KULLANICI_SILME_SINIRI * 2]:
        if kid in kaynak and takvim.silindi_mi(kid) and kaynak[kid] not in birimler:
            birimler.append(kaynak[kid])
    birimler = birimler[:KULLANICI_SILME_SINIRI]
    damga = simdi.strftime("%d.%m.%Y %H:%M") + " (takvimden)"
    islenen = 0
    for rid, olay in birimler:
        if rid.startswith("g"):
            for o in yap.get("ogeler", []):
                if str(o.get("id")) == rid[1:] and not o.get("tamam"):
                    o["tamam"] = True; o["tamamlanma"] = damga; islenen += 1
            continue
        for k in list(veri.get("hatirlatmalar", [])):
            if str(k.get("id")) != rid:
                continue
            if k.get("tur") == "tek":
                veri["hatirlatmalar"].remove(k); islenen += 1
            else:
                l = k.get("tamamlanan") or []
                if olay not in l:
                    k["tamamlanan"] = (l + [olay])[-36:]; islenen += 1
    return islenen


# ---------- ana program ----------

def main(argv=None, http=istek, imzala=rs256_imzala):
    ap = argparse.ArgumentParser()
    ap.add_argument("--veri", default="veri", help="gizli veri deposunun klasörü")
    ap.add_argument("--dry-run", action="store_true", help="Google'a bağlanmaz; üretilecek etkinlikleri yazdırır")
    ap.add_argument("--simdi", help="YYYY-AA-GGTSS:DD (test için)")
    args = ap.parse_args(argv)

    simdi = datetime.fromisoformat(args.simdi) if args.simdi else h.simdi_tr()
    hat_yolu = os.path.join(args.veri, "hatirlatmalar.json")
    yap_yolu = os.path.join(args.veri, "yapilacaklar.json")
    durum_yolu = os.path.join(args.veri, "takvim-durum.json")
    veri = h.json_oku(hat_yolu, {"hatirlatmalar": []})
    yap = h.json_oku(yap_yolu, {"ogeler": []})
    durum = h.json_oku(durum_yolu, {"var": []})
    yazilan = {hat_yolu: json.dumps(veri, sort_keys=True), yap_yolu: json.dumps(yap, sort_keys=True)}

    def kaydet():
        """Değişen veri dosyalarını yazar (workflow'un "kaydet" adımı depoya işler)."""
        for yol, nesne in ((hat_yolu, veri), (yap_yolu, yap)):
            if json.dumps(nesne, sort_keys=True) != yazilan[yol]:
                h.json_yaz(yol, nesne); yazilan[yol] = json.dumps(nesne, sort_keys=True)

    if args.dry_run:
        istenen = istenen_etkinlikler(veri["hatirlatmalar"] + h.gorev_hatirlatmalari(yap), simdi)
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
        alinan, guncellenen, silinen = takvimden_al(takvim, veri, simdi)
        kaydet()
        kaynak = {}
        istenen = istenen_etkinlikler(veri["hatirlatmalar"] + h.gorev_hatirlatmalari(yap), simdi, kaynak=kaynak)
        zmin = datetime.combine(simdi.date(), datetime.min.time()).isoformat(timespec="seconds") + TR_OFSET
        zmax = datetime.combine(simdi.date() + timedelta(days=PENCERE + 1), datetime.min.time()).isoformat(timespec="seconds") + TR_OFSET
        mevcut = takvim.listele(zmin, zmax)
        kayip = [i for i in durum.get("var", []) if i in istenen and i not in mevcut]   # daha önce vardı, şimdi yok
        kullanici_silmesi = silinenleri_isle(takvim, kayip, kaynak, veri, yap, simdi) if kayip else 0
        if kullanici_silmesi:
            kaydet()
            istenen = istenen_etkinlikler(veri["hatirlatmalar"] + h.gorev_hatirlatmalari(yap), simdi, kaynak=kaynak)
        e, g, s, kalan, var = esitle(takvim, istenen, mevcut)
        if sorted(var) != durum.get("var"):
            h.json_yaz(durum_yolu, {"var": sorted(var)})
    except (Hata, ValueError, KeyError) as ex:
        ad = f"{ex.durum} {ex.neden}".strip() if isinstance(ex, Hata) else type(ex).__name__
        print(f"Takvim eşitlenemedi ({ad}).")      # ayrıntı yazılmaz: günlük herkese açık
        return 1
    print(f"Takvim eşitlendi: {len(istenen)} etkinlik (eklenen {e}, güncellenen {g}, silinen {s})."
          + (f" {kalan} işlem sonraki çalışmaya kaldı." if kalan else "")
          + (f" Takvimden alınan: {alinan}, güncellenen: {guncellenen}, silinen: {silinen}." if alinan or guncellenen or silinen else "")
          + (f" Takvimde silinen etkinliklere karşılık işlenen hatırlatma: {kullanici_silmesi}." if kullanici_silmesi else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
