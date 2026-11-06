"""Web arayüzü ve API (FastAPI). Tek işçi (worker) ile çalıştırın: zamanlayıcı bu süreçte döner.

Ortam değişkenleri:
  WEB_SIFRE         (zorunlu) arayüz giriş şifresi, en az 10 karakter
  WEB_GIZLI         oturum imzası için rastgele metin (yoksa her açılışta üretilir; oturumlar açılışta düşer)
  DATA_DIR          veri klasörü (varsayılan ./veri); Render'da kalıcı disk
  TOPLAYICI         ornek | dosya | luca
  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
  ZAMANLAYICI       0 yazılırsa zamanlayıcı başlamaz
"""

import hashlib
import hmac
import os
import secrets
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .bildirim import CaptchaKoprusu, Telegram
from .cekirdek import Uygulama, simdi_tr
from .depo import Depo
from .kontrol import VARSAYILAN_AYAR, ayar_al
from .kurallar import BEYANNAMELER
from .toplayici import sec
from .zamanlayici import Zamanlayici

STATIK = Path(__file__).parent / "static"
OTURUM_SN = 12 * 3600


def uygulama_kur(env=os.environ):
    depo = Depo(env.get("DATA_DIR", "veri"))
    tg = Telegram(env.get("TELEGRAM_TOKEN"), env.get("TELEGRAM_CHAT_ID"))
    return Uygulama(depo, sec(env.get("TOPLAYICI", "ornek"), depo.dizin), tg, CaptchaKoprusu(tg))


def uygulama_olustur(cekirdek=None, env=os.environ):
    sifre = env.get("WEB_SIFRE", "")
    if len(sifre) < 10:
        raise RuntimeError("WEB_SIFRE ortam değişkeni en az 10 karakter olmalı (arayüz şifresiz açılmaz).")
    gizli = (env.get("WEB_GIZLI") or secrets.token_hex(32)).encode()
    cekirdek = cekirdek or uygulama_kur(env)
    hatalar = {"sayi": 0, "kilit_bitis": 0.0}

    @asynccontextmanager
    async def omur(app):
        z = None
        if env.get("ZAMANLAYICI", "1") != "0":
            z = Zamanlayici(cekirdek)
            z.start()
        yield
        if z:
            z.durdur()

    app = FastAPI(title="Beyanname Takip", lifespan=omur, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.cekirdek = cekirdek

    def imza(bitis):
        return hmac.new(gizli, str(bitis).encode(), hashlib.sha256).hexdigest()

    def giris_gerekli(request: Request):
        c = request.cookies.get("oturum", "")
        try:
            bitis, im = c.split(".", 1)
            if int(bitis) > time.time() and hmac.compare_digest(im, imza(bitis)):
                return
        except ValueError:
            pass
        raise HTTPException(401, "Giriş gerekli")

    class Giris(BaseModel):
        sifre: str

    @app.get("/saglik")
    def saglik():
        return {"ok": True}

    @app.get("/")
    def ana():
        return FileResponse(STATIK / "index.html", headers={"Cache-Control": "no-store"})

    @app.post("/api/giris")
    def giris(g: Giris, request: Request, yanit: Response):
        if time.time() < hatalar["kilit_bitis"]:
            raise HTTPException(429, "Çok fazla yanlış deneme; biraz bekleyin.")
        if not hmac.compare_digest(g.sifre.encode(), sifre.encode()):
            hatalar["sayi"] += 1
            if hatalar["sayi"] >= 5:
                hatalar["kilit_bitis"] = time.time() + min(900, 30 * 2 ** (hatalar["sayi"] - 5))
            raise HTTPException(401, "Şifre yanlış")
        hatalar["sayi"] = 0
        bitis = int(time.time()) + OTURUM_SN
        yanit.set_cookie("oturum", f"{bitis}.{imza(bitis)}", max_age=OTURUM_SN, httponly=True,
                         samesite="strict", secure=request.url.scheme == "https")
        return {"ok": True}

    @app.post("/api/cikis")
    def cikis(yanit: Response):
        yanit.delete_cookie("oturum")
        return {"ok": True}

    gerekli = [Depends(giris_gerekli)]

    @app.get("/api/durum", dependencies=gerekli)
    def durum():
        d = cekirdek.depo.oku("durum.json", {})
        return {"veri": cekirdek.veri_durumu(), "son_toplama": d.get("son_toplama"),
                "telegram": cekirdek.telegram.hazir, "captcha_bekliyor": cekirdek.captcha.bekliyor_mu(),
                "simdi": simdi_tr().isoformat(),
                "turler": {k: {"ad": v["ad"], "periyotlar": list(v["periyotlar"])} for k, v in BEYANNAMELER.items()}}

    @app.get("/api/maddeler", dependencies=gerekli)
    def maddeler():
        return [m.sozluk() for m in cekirdek.maddeler()]

    @app.get("/api/mukellefler", dependencies=gerekli)
    def mukellefler():
        ayarlar = cekirdek.depo.oku("ayarlar.json", {})
        mus = cekirdek.depo.oku("mukellefler.json", {}).get("kayitlar", [])
        return [dict(m, ayar=ayar_al(ayarlar, m["id"])) for m in sorted(mus, key=lambda x: x["ad"])]

    class AyarGirdi(BaseModel):
        KDV1: str = "aylik"
        MPHB: str = "aylik"
        GECICI: str = "3aylik"
        isyeri: str = ""
        onayli: bool = True

    @app.put("/api/mukellef/ayar", dependencies=gerekli)
    def ayar_yaz(mid: str, a: AyarGirdi):
        for tur in BEYANNAMELER:
            v = getattr(a, tur)
            if v != "yok" and v not in BEYANNAMELER[tur]["periyotlar"]:
                raise HTTPException(400, f"{tur} için geçersiz değer: {v}")

        def isle(d):
            d.setdefault("mukellef", {})[mid] = {**a.model_dump(), "isyeri": a.isyeri[:40]}
        cekirdek.depo.guncelle("ayarlar.json", isle)
        return {"ok": True}

    class MuafGirdi(BaseModel):
        id: str
        tur: str
        donem: str
        aciklama: str = ""

    @app.post("/api/muaf", dependencies=gerekli)
    def muaf_ekle(g: MuafGirdi):
        if g.tur not in BEYANNAMELER:
            raise HTTPException(400, "Geçersiz tür")

        def isle(d):
            l = d.setdefault("muaf", [])
            if not any(x["id"] == g.id and x["tur"] == g.tur and x["donem"] == g.donem for x in l):
                l.append({"id": g.id, "tur": g.tur, "donem": g.donem, "not": g.aciklama[:200],
                          "zaman": simdi_tr().isoformat()})
        cekirdek.depo.guncelle("ayarlar.json", isle)
        return {"ok": True}

    @app.post("/api/muaf/sil", dependencies=gerekli)
    def muaf_sil(g: MuafGirdi):
        def isle(d):
            d["muaf"] = [x for x in d.get("muaf", [])
                         if not (x["id"] == g.id and x["tur"] == g.tur and x["donem"] == g.donem)]
        cekirdek.depo.guncelle("ayarlar.json", isle)
        return {"ok": True}

    @app.post("/api/kontrol", dependencies=gerekli)
    def kontrol():
        """Luca'dan veriyi şimdi çeker (arka planda); sonucu /api/durum'dan izleyin. Telegram'a mesaj atmaz."""
        threading.Thread(target=cekirdek.topla, daemon=True).start()
        return {"ok": True}

    @app.get("/api/tani.zip", dependencies=gerekli)
    def tani_zip():
        """Luca tanı dosyaları (ekran görüntüleri, sayfa kaynağı, filtre seçenekleri). Mükellef adı içerir."""
        import io
        import zipfile
        kok = cekirdek.depo.dizin / "tani"
        tampon = io.BytesIO()
        with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
            for yol in sorted(kok.rglob("*")) if kok.exists() else []:
                if yol.is_file():
                    z.write(yol, yol.relative_to(kok).as_posix())
        return Response(tampon.getvalue(), media_type="application/zip",
                        headers={"Content-Disposition": "attachment; filename=luca-tani.zip", "Cache-Control": "no-store"})

    @app.post("/api/test-bildirim", dependencies=gerekli)
    def test_bildirim():
        return {"gonderildi": cekirdek.telegram.gonder("✅ Beyanname takip: test mesajı")}

    @app.get("/api/captcha.png", dependencies=gerekli)
    def captcha_resim():
        r = cekirdek.captcha.resim
        if r is None:
            raise HTTPException(404, "Bekleyen captcha yok")
        return Response(r, media_type="image/png", headers={"Cache-Control": "no-store"})

    class CaptchaGirdi(BaseModel):
        kod: str

    @app.post("/api/captcha", dependencies=gerekli)
    def captcha_cevap(g: CaptchaGirdi):
        return {"ok": cekirdek.captcha.cevapla(g.kod)}

    return app


def app_fabrikasi():
    return uygulama_olustur()
