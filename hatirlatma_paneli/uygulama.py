"""
Hatırlatma paneli: şifresiz, gizli bağlantıyla açılan küçük Flask uygulaması.

Adres:  /<ANAHTAR>/        (PythonAnywhere'de /h altına bağlanır -> /h/<ANAHTAR>/)
ANAHTAR, hatirlatma_ayar.py içinde ya da HATIRLATMA_ANAHTAR ortam değişkeninde durur;
kodda ve depoda yoktur. Anahtarı bilmeyen hiçbir sayfaya ve veriye ulaşamaz.
"""

import calendar
import hmac
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone

from flask import Flask, abort, jsonify, make_response, render_template_string, request

KLASOR = os.path.dirname(os.path.abspath(__file__))
DB_YOLU = os.environ.get("HATIRLATMA_DB") or os.path.join(KLASOR, "hatirlatma.db")
TR = timezone(timedelta(hours=3))  # Türkiye yıl boyu UTC+3


def anahtar_oku():
    k = os.environ.get("HATIRLATMA_ANAHTAR")
    if not k:
        try:
            from hatirlatma_ayar import ANAHTAR as k
        except ImportError:
            k = ""
    if len(k) < 24:
        raise RuntimeError("HATIRLATMA_ANAHTAR en az 24 karakter olmalı (bkz. hatirlatma_ayar.ornek.py).")
    return k


ANAHTAR = anahtar_oku()
app = Flask(__name__)


# ---------- tarih yardımcıları ----------

def bugun():
    return datetime.now(TR).date()


def ay_ekle(d, n):
    toplam = d.year * 12 + d.month - 1 + n
    y, a = divmod(toplam, 12)
    a += 1
    return date(y, a, min(d.day, calendar.monthrange(y, a)[1]))


def gun_sec(y, a, g):
    return date(y, a, min(g, calendar.monthrange(y, a)[1]))


def olay_mi(k, hedef):
    if k["tur"] == "tek":
        return date.fromisoformat(k["tarih"]) == hedef
    if k["tur"] == "aylik":
        return gun_sec(hedef.year, hedef.month, k["gun"]) == hedef
    return gun_sec(hedef.year, k["ay"], k["gun"]) == hedef


def sonraki(k, d):
    """d günü veya sonrasındaki ilk olay tarihi (yoksa None)."""
    if k["tur"] == "tek":
        t = date.fromisoformat(k["tarih"])
        return t if t >= d else None
    if k["tur"] == "aylik":
        x = gun_sec(d.year, d.month, k["gun"])
        if x >= d:
            return x
        n = ay_ekle(date(d.year, d.month, 1), 1)
        return gun_sec(n.year, n.month, k["gun"])
    x = gun_sec(d.year, k["ay"], k["gun"])
    return x if x >= d else gun_sec(d.year + 1, k["ay"], k["gun"])


# ---------- veritabanı ----------

def db():
    c = sqlite3.connect(DB_YOLU)
    c.row_factory = sqlite3.Row
    c.execute(
        """CREATE TABLE IF NOT EXISTS hatirlatma (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tur TEXT NOT NULL CHECK (tur IN ('tek','aylik','yillik')),
            tarih TEXT, ay INTEGER, gun INTEGER,
            gunler TEXT NOT NULL DEFAULT '0',
            metin TEXT NOT NULL,
            olusturma TEXT NOT NULL)"""
    )
    return c


def satirlar():
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM hatirlatma")]


def gunler_listesi(k):
    return sorted({int(x) for x in k["gunler"].split(",") if x.strip() != ""}, reverse=True)


# ---------- erişim ----------

def kontrol(anahtar):
    if not hmac.compare_digest(anahtar.encode(), ANAHTAR.encode()):
        abort(404)


@app.after_request
def baslik(resp):
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


# ---------- sayfa ve API ----------

@app.get("/<anahtar>/")
def sayfa(anahtar):
    kontrol(anahtar)
    return render_template_string(SAYFA, bugun=bugun().isoformat())


@app.get("/<anahtar>/liste")
def liste(anahtar):
    kontrol(anahtar)
    b, cikti = bugun(), []
    for k in satirlar():
        s = sonraki(k, b)
        cikti.append({
            "id": k["id"], "metin": k["metin"], "tur": k["tur"],
            "sonraki": s.isoformat() if s else None,
            "tarih": k["tarih"], "gunler": gunler_listesi(k),
        })
    cikti.sort(key=lambda x: (x["sonraki"] is None, x["sonraki"] or "", x["id"]))
    return jsonify(cikti)


@app.post("/<anahtar>/ekle")
def ekle(anahtar):
    kontrol(anahtar)
    v = request.get_json(silent=True) or {}
    metin = " ".join(str(v.get("metin", "")).split())[:300]
    if not metin:
        return jsonify(hata="Metin boş olamaz."), 400
    try:
        tarih = date.fromisoformat(str(v.get("tarih", "")))
        gunler = sorted({int(x) for x in v.get("gunler", [0])}, reverse=True)
    except (ValueError, TypeError):
        return jsonify(hata="Tarih veya gün değeri geçersiz."), 400
    if not gunler or any(g < 0 or g > 365 for g in gunler):
        return jsonify(hata="Kaç gün önce değeri geçersiz."), 400
    tekrar = v.get("tekrar", "yok")
    if tekrar == "yok":
        tur, ay, gun, t = "tek", None, None, tarih.isoformat()
        if tarih < bugun():
            return jsonify(hata="Geçmiş bir tarih seçilemez."), 400
    elif tekrar == "aylik":
        tur, ay, gun, t = "aylik", None, tarih.day, None
    elif tekrar == "yillik":
        tur, ay, gun, t = "yillik", tarih.month, tarih.day, None
    else:
        return jsonify(hata="Tekrar değeri geçersiz."), 400
    with db() as c:
        c.execute(
            "INSERT INTO hatirlatma (tur,tarih,ay,gun,gunler,metin,olusturma) VALUES (?,?,?,?,?,?,?)",
            (tur, t, ay, gun, ",".join(map(str, gunler)), metin, datetime.now(TR).isoformat(timespec="seconds")),
        )
    return jsonify(tamam=True)


@app.post("/<anahtar>/sil/<int:no>")
def sil(anahtar, no):
    kontrol(anahtar)
    with db() as c:
        c.execute("DELETE FROM hatirlatma WHERE id=?", (no,))
    return jsonify(tamam=True)


@app.get("/<anahtar>/api/bugun")
def api_bugun(anahtar):
    """GitHub Actions her sabah buraya sorar. ?bugun=YYYY-AA-GG test içindir."""
    kontrol(anahtar)
    try:
        b = date.fromisoformat(request.args["bugun"]) if "bugun" in request.args else bugun()
    except ValueError:
        return jsonify(hata="bugun geçersiz"), 400
    cikti = []
    for k in satirlar():
        for fark in gunler_listesi(k):
            hedef = b + timedelta(days=fark)
            if olay_mi(k, hedef):
                cikti.append({"metin": k["metin"], "olay": hedef.isoformat(), "fark": fark})
    return jsonify(bugun=b.isoformat(), hatirlatmalar=cikti)


@app.get("/<anahtar>/yedek.txt")
def yedek(anahtar):
    kontrol(anahtar)
    sat = []
    for k in satirlar():
        if k["tur"] == "tek":
            zaman = k["tarih"]
        elif k["tur"] == "aylik":
            zaman = f"her-ay {k['gun']}"
        else:
            zaman = f"her-yil {k['ay']:02d}-{k['gun']:02d}"
        sat.append(f"{zaman} | {k['gunler']} | {k['metin']}")
    r = make_response("\n".join(sat) + "\n")
    r.mimetype = "text/plain"
    return r


@app.get("/<anahtar>/manifest.json")
def manifest(anahtar):
    kontrol(anahtar)
    return jsonify(name="Hatırlatma", short_name="Hatırlatma", start_url="./", display="standalone",
                   background_color="#f3f5f2", theme_color="#1f6f5c")


@app.get("/<anahtar>/ikon.png")
def ikon(anahtar):
    """Ana ekran simgesi: yeşil zemin üzerinde beyaz çan benzeri şekil (bağımlılıksız PNG)."""
    kontrol(anahtar)
    import struct
    import zlib

    n = 180
    satir = []
    for y in range(n):
        s = bytearray([0])
        for x in range(n):
            c = (31, 111, 92)
            if (x - 90) ** 2 + (y - 80) ** 2 <= 56 ** 2 and y < 130 or 56 <= y <= 132 and 40 <= x <= 140 and y > 100 \
                    or (x - 90) ** 2 + (y - 152) ** 2 <= 11 ** 2 or 128 <= y <= 136 and 30 <= x <= 150:
                c = (255, 255, 255)
            s += bytes(c)
        satir.append(bytes(s))

    def parca(tip, veri):
        return struct.pack(">I", len(veri)) + tip + veri + struct.pack(">I", zlib.crc32(tip + veri))

    png = (b"\x89PNG\r\n\x1a\n" + parca(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0))
           + parca(b"IDAT", zlib.compress(b"".join(satir))) + parca(b"IEND", b""))
    r = make_response(png)
    r.mimetype = "image/png"
    return r


SAYFA = open(os.path.join(KLASOR, "sayfa.html"), encoding="utf-8").read()
