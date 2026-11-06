import pytest
from fastapi.testclient import TestClient

from app.bildirim import CaptchaKoprusu
from app.cekirdek import Uygulama
from app.depo import Depo
from app.toplayici import OrnekToplayici
from app.web import uygulama_olustur
from tests.test_cekirdek import Saat, SahteTelegram

SIFRE = "uzun-bir-sifre-123"


@pytest.fixture
def istemci(tmp_path):
    tg = SahteTelegram()
    c = Uygulama(Depo(tmp_path), OrnekToplayici(), tg, CaptchaKoprusu(tg), saat=Saat("2026-11-26T09:00"))
    app = uygulama_olustur(c, env={"WEB_SIFRE": SIFRE, "WEB_GIZLI": "x" * 32, "ZAMANLAYICI": "0"})
    return TestClient(app), c, tg


def giris(ic):
    assert ic.post("/api/giris", json={"sifre": SIFRE}).status_code == 200


def test_sifresiz_acilmaz():
    with pytest.raises(RuntimeError):
        uygulama_olustur(object(), env={"WEB_SIFRE": "kisa"})


def test_api_giris_olmadan_kapali(istemci):
    ic, _, _ = istemci
    for yol in ("/api/durum", "/api/maddeler", "/api/mukellefler", "/api/captcha.png"):
        assert ic.get(yol).status_code == 401
    assert ic.post("/api/kontrol").status_code == 401
    assert ic.get("/saglik").json() == {"ok": True}
    assert "Beyanname Takip" in ic.get("/").text                    # sayfa kabuğu açık, veri yok


def test_yanlis_sifre_kilitler(istemci):
    ic, _, _ = istemci
    for _ in range(5):
        assert ic.post("/api/giris", json={"sifre": "yanlis"}).status_code == 401
    assert ic.post("/api/giris", json={"sifre": SIFRE}).status_code == 429


def test_sahte_cerez_reddedilir(istemci):
    ic, _, _ = istemci
    ic.cookies.set("oturum", "9999999999.deadbeef")
    assert ic.get("/api/durum").status_code == 401


def test_akis_ayar_muaf_ve_maddeler(istemci):
    ic, c, _ = istemci
    giris(ic)
    c.topla()
    m = ic.get("/api/mukellefler").json()
    assert len(m) == 6 and m[0]["ayar"]["onayli"] is False
    mid = next(x["id"] for x in m if x["ad"] == "DELTA DANIŞMANLIK")
    assert ic.put("/api/mukellef/ayar", params={"mid": mid}, json={"KDV1": "yok", "MPHB": "aylik", "GECICI": "yok", "onayli": True}).status_code == 200
    assert ic.put("/api/mukellef/ayar", params={"mid": mid}, json={"KDV1": "bozuk"}).status_code == 400
    md = [x for x in ic.get("/api/maddeler").json() if x["ad"] == "DELTA DANIŞMANLIK"]
    assert {x["tur"] for x in md} == {"MPHB"} and md[0]["ayar_onayli"]
    ic.post("/api/muaf", json={"id": mid, "tur": "MPHB", "donem": "2026-10", "aciklama": "çalışan yok"})
    assert [x["durum"] for x in ic.get("/api/maddeler").json() if x["ad"] == "DELTA DANIŞMANLIK" and x["donem"] == "2026-10"] == ["muaf"]
    ic.post("/api/muaf/sil", json={"id": mid, "tur": "MPHB", "donem": "2026-10"})
    assert [x["durum"] for x in ic.get("/api/maddeler").json() if x["ad"] == "DELTA DANIŞMANLIK" and x["donem"] == "2026-10"] == ["eksik"]


def test_durum_ve_test_bildirimi(istemci):
    ic, c, tg = istemci
    giris(ic)
    d = ic.get("/api/durum").json()
    assert d["telegram"] and d["veri"]["hata"] and set(d["turler"]) == {"KDV1", "MPHB", "GECICI"}
    assert ic.post("/api/test-bildirim").json() == {"gonderildi": True} and "test mesajı" in tg.mesajlar[-1]


def test_captcha_web_uzerinden(istemci):
    ic, c, _ = istemci
    giris(ic)
    assert ic.get("/api/captcha.png").status_code == 404
    c.captcha.resim = b"\x89PNGxx"
    assert ic.get("/api/captcha.png").content == b"\x89PNGxx"
    assert ic.post("/api/captcha", json={"kod": "ABCD"}).json() == {"ok": True}


def test_tani_dosyalari_ve_yol_guvenligi(istemci):
    ic, c, _ = istemci
    for yol in ("/api/tani/dosyalar", "/api/tani/dosya?yol=x.png", "/api/tani.zip"):
        assert ic.get(yol).status_code == 401
    assert ic.post("/api/tani/calistir").status_code == 401
    giris(ic)
    tani = c.depo.dizin / "tani" / "ofis"
    tani.mkdir(parents=True)
    (tani / "a.png").write_bytes(b"\x89PNGxx")
    (tani / "sayfa.html").write_text("<script>alert(1)</script>", encoding="utf-8")
    (tani / "filtre-secenekleri.json").write_text('{"Beyanname": ["KDV1"]}', encoding="utf-8")
    (c.depo.dizin / "sir.png").write_bytes(b"gizli")                 # tani klasörünün dışında
    liste = ic.get("/api/tani/dosyalar").json()
    assert {x["yol"] for x in liste} == {"ofis/a.png", "ofis/sayfa.html", "ofis/filtre-secenekleri.json"}
    r = ic.get("/api/tani/dosya", params={"yol": "ofis/a.png"})
    assert r.content == b"\x89PNGxx" and r.headers["content-type"] == "image/png"
    h = ic.get("/api/tani/dosya", params={"yol": "ofis/sayfa.html"})
    assert h.headers["content-type"].startswith("text/plain") and h.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in h.headers["content-security-policy"]
    for kotu in ("../sir.png", "ofis/../../sir.png", "/etc/passwd", "ofis", "ofis/yok.png", "ofis/a.exe"):
        assert ic.get("/api/tani/dosya", params={"yol": kotu}).status_code == 404, kotu
    assert ic.get("/api/tani.zip").status_code == 200


def test_tani_calistir_luca_disinda_400(istemci):
    ic, _, _ = istemci
    giris(ic)
    assert ic.post("/api/tani/calistir").status_code == 400          # OrnekToplayici'nin tani() yok
    d = ic.get("/api/durum").json()
    assert d["tani_var"] is False and d["tani_suruyor"] is False
