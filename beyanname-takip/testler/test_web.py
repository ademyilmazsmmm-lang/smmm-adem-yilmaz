import pytest
from fastapi.testclient import TestClient

from app.bildirim import CaptchaKoprusu
from app.cekirdek import Uygulama
from app.depo import Depo
from app.toplayici import OrnekToplayici
from app.web import uygulama_olustur
from testler.test_cekirdek import Saat, SahteTelegram

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
        uygulama_olustur(object(), env={"WEB_SIFRE": "abc"})


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
    assert d["telegram"] and d["veri"]["hata"] and set(d["turler"]) == {"KDV1", "MPHB", "GECICI", "KDV2", "POSET", "KONAKLAMA", "KV", "GV"}
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


def test_toplu_onay(istemci):
    ic, c, _ = istemci
    assert ic.post("/api/mukellef/toplu-onay", json={"ids": ["x"]}).status_code == 401
    giris(ic)
    c.topla()
    m = ic.get("/api/mukellefler").json()
    ids = [x["id"] for x in m]
    ic.put("/api/mukellef/ayar", params={"mid": ids[0]}, json={"KDV1": "3aylik", "MPHB": "yok", "GECICI": "yok", "onayli": True})
    assert ic.post("/api/mukellef/toplu-onay", json={"ids": ids}).json() == {"onaylanan": len(ids) - 1}
    m2 = {x["id"]: x["ayar"] for x in ic.get("/api/mukellefler").json()}
    assert all(a["onayli"] for a in m2.values())
    assert m2[ids[0]]["KDV1"] == "3aylik" and m2[ids[0]]["MPHB"] == "yok"        # var olan ayara dokunulmaz
    assert m2[ids[1]]["KDV1"] == "aylik" and m2[ids[1]]["GECICI"] == "3aylik"
    assert ic.post("/api/mukellef/toplu-onay", json={"ids": ids}).json() == {"onaylanan": 0}


def test_sgk_ayari_kaydedilir_ve_dogrulanir(istemci):
    ic, c, _ = istemci
    giris(ic)
    c.topla()
    mid = ic.get("/api/mukellefler").json()[0]["id"]
    assert ic.get("/api/mukellefler").json()[0]["ayar"]["sgk"] == "auto"
    assert ic.put("/api/mukellef/ayar", params={"mid": mid}, json={"sgk": "var", "onayli": True}).status_code == 200
    assert [x["ayar"]["sgk"] for x in ic.get("/api/mukellefler").json() if x["id"] == mid] == ["var"]
    assert ic.put("/api/mukellef/ayar", params={"mid": mid}, json={"sgk": "bozuk"}).status_code == 400


def test_web_sifre_alt_siniri_4():
    from app.web import uygulama_olustur as olustur
    with pytest.raises(RuntimeError):
        olustur(object(), env={"WEB_SIFRE": "123"})
    olustur(object(), env={"WEB_SIFRE": "1234", "ZAMANLAYICI": "0"})


def test_durum_bildirim_kanallarini_gosterir(tmp_path):
    from app.bildirim import Bildirici, Eposta
    tg = Bildirici([Eposta("h", 587, "a@b.c", "p", "a@b.c")])
    c = Uygulama(Depo(tmp_path), OrnekToplayici(), tg, CaptchaKoprusu(tg), saat=Saat("2026-11-26T09:00"))
    ic = TestClient(uygulama_olustur(c, env={"WEB_SIFRE": SIFRE, "WEB_GIZLI": "x" * 32, "ZAMANLAYICI": "0"}))
    giris(ic)
    d = ic.get("/api/durum").json()
    assert d["telegram"] and d["kanallar"] == ["E-posta"]


def test_ag_testi_modulu_hata_turlerini_ayirir():
    import socket
    import urllib.error
    from app.ag_testi import ag_testi

    class Yanit:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def istek(url, zaman):
        if "agiris" in url:
            raise socket.timeout()
        if "luca" in url:
            return Yanit()
        if "google" in url:
            return Yanit()
        raise urllib.error.HTTPError(url, 403, "x", {}, None)
    r = ag_testi(istek=istek)
    assert [(x["sonuc"], x["ok"]) for x in r] == [("HTTP 200", True), ("Zaman aşımı", False), ("HTTP 200", True), ("HTTP 403", False)]
    assert r[1]["adres"] == "https://agiris.luca.com.tr"


def test_ag_testi_endpoint_giris_ister(istemci, monkeypatch):
    ic, _, _ = istemci
    assert ic.post("/api/ag-testi").status_code == 401
    giris(ic)
    monkeypatch.setattr("app.web.ag_testi", lambda adres: [{"ad": "x", "adres": adres, "sonuc": "HTTP 200", "ok": True, "sn": 0.1}])
    assert ic.post("/api/ag-testi").json()[0]["sonuc"] == "HTTP 200"


def test_ayar_yeni_turler_ve_mphb_auto(istemci):
    ic, c, _ = istemci
    giris(ic)
    c.topla()
    mid = ic.get("/api/mukellefler").json()[0]["id"]
    a = ic.get("/api/mukellefler").json()[0]["ayar"]
    assert a["MPHB"] == "auto" and a["KDV2"] == "yok" and a["POSET"] == "yok"
    assert ic.put("/api/mukellef/ayar", params={"mid": mid}, json={"KDV2": "aylik", "POSET": "3aylik", "MPHB": "auto"}).status_code == 200
    assert ic.put("/api/mukellef/ayar", params={"mid": mid}, json={"KDV2": "3aylik"}).status_code == 400          # KDV2 yalnızca aylık
    assert ic.put("/api/mukellef/ayar", params={"mid": mid}, json={"KDV1": "auto"}).status_code == 400            # auto yalnızca MUHSGK'da
    assert ic.get("/api/durum").json()["turler"]["MPHB"]["periyotlar"] == ["auto", "aylik", "3aylik"]


def test_onizleme_gondermeden_mesaj_uretir_ve_slotu_isaretlemez(istemci):
    ic, c, tg = istemci
    assert ic.get("/api/onizleme").status_code == 401
    giris(ic)
    c.topla()
    n = len(tg.mesajlar)
    r = ic.get("/api/onizleme", params={"slot": "21:00", "tarih": "2026-11-30"}).json()
    assert r["slot"] == "21:00" and r["tarih"] == "2026-11-30" and r["mesajlar"]                  # son gün akşamı: eksik uyarısı var
    assert len(tg.mesajlar) == n and c.depo.oku("gonderim.json", {}) == {}                        # gönderilmedi, slot işaretlenmedi
    assert ic.get("/api/onizleme", params={"slot": "03:00"}).status_code == 400
    assert ic.get("/api/onizleme", params={"tarih": "yanlis"}).status_code == 400
    g = ic.post("/api/onizleme/gonder", params={"slot": "21:00", "tarih": "2026-11-30"}).json()
    assert g["gonderildi"] and g["mesaj"] == len(r["mesajlar"]) and "ÖNİZLEME" in tg.mesajlar[-1]
    assert c.depo.oku("gonderim.json", {}) == {}
    assert ic.post("/api/onizleme/gonder", params={"slot": "13:00", "tarih": "2026-11-20"}).json()["gonderildi"] is False   # uyarı gerekmiyor


def test_rapor_ucu_giris_ister_ve_gun_dogrular(istemci):
    ic, c, _ = istemci
    assert ic.post("/api/rapor").status_code == 401
    giris(ic)
    assert ic.post("/api/rapor", params={"gun": 0}).status_code == 400
    assert ic.post("/api/rapor", params={"gun": 99}).status_code == 400
    d = ic.get("/api/durum").json()
    assert d["rapor_suruyor"] is False and d["son_rapor"] is None
    c.rapor_suruyor = True
    assert ic.post("/api/rapor").status_code == 409


def test_kontrol_ve_rapor_gib_araligi_dogrular_ve_iletir(istemci):
    from datetime import date
    import time
    ic, c, _ = istemci
    giris(ic)
    alinan = []
    c.topla = lambda aralik=None: alinan.append(aralik)
    for kotu, mesaj in (({"gib_bas": "2020-03-01"}, "ikisi de gerekli"), ({"gib_bas": "2020-03-31", "gib_bit": "2020-03-01"}, "sonra olamaz"),
                        ({"gib_bas": "2020-01-01", "gib_bit": "2020-03-01"}, "31 günlük"), ({"gib_bas": "x", "gib_bit": "y"}, "YYYY-AA-GG"),
                        ({"gib_bas": "2999-01-01", "gib_bit": "2999-01-02"}, "ileri olamaz")):
        r = ic.post("/api/kontrol", params=kotu)
        assert r.status_code == 400 and mesaj in r.json()["detail"], kotu
        assert ic.post("/api/rapor", params=kotu).status_code == 400
    assert ic.post("/api/kontrol", params={"gib_bas": "2020-03-01", "gib_bit": "2020-03-31"}).json() == {"ok": True}
    assert ic.post("/api/kontrol").json() == {"ok": True}
    for _ in range(100):
        if len(alinan) >= 2:
            break
        time.sleep(0.02)
    assert sorted(alinan, key=str) == sorted([(date(2020, 3, 1), date(2020, 3, 31)), None], key=str)


def test_durum_gib_gun_ayardan_gelir(tmp_path):
    from app.bildirim import CaptchaKoprusu as CK
    tg = SahteTelegram()
    c = Uygulama(Depo(tmp_path), OrnekToplayici(), tg, CK(tg), saat=Saat("2026-11-26T09:00"))
    for env_deger, beklenen in (("31", 31), ("", 15), ("99", 31), ("0", 1), ("abc", 15)):
        ic = TestClient(uygulama_olustur(c, env={"WEB_SIFRE": SIFRE, "WEB_GIZLI": "x" * 32, "ZAMANLAYICI": "0", "LUCA_GIB_GUN": env_deger}))
        giris(ic)
        assert ic.get("/api/durum").json()["gib_gun"] == beklenen, env_deger


def test_kapat_yalniz_yerel_calismada(istemci, tmp_path, monkeypatch):
    import time
    import app.web as w
    ic, c, _ = istemci
    assert ic.post("/api/kapat").status_code == 401
    giris(ic)
    assert ic.get("/api/durum").json()["yerel"] is False
    assert ic.post("/api/kapat").status_code == 404                                  # Render/sunucuda yok
    cikis = []
    monkeypatch.setattr(w, "_cik", lambda: cikis.append(1))
    from app.bildirim import CaptchaKoprusu as CK
    c2 = Uygulama(Depo(tmp_path / "y"), OrnekToplayici(), c.telegram, CK(c.telegram), saat=Saat("2026-11-26T09:00"))
    ic2 = TestClient(uygulama_olustur(c2, env={"WEB_SIFRE": SIFRE, "WEB_GIZLI": "x" * 32, "ZAMANLAYICI": "0", "BEYANNAME_YEREL": "1"}))
    giris(ic2)
    assert ic2.get("/api/durum").json()["yerel"] is True
    assert ic2.post("/api/kapat").json() == {"ok": True}
    for _ in range(40):
        if cikis:
            break
        time.sleep(0.05)
    assert cikis == [1]


def test_kapat_kontrol_yalniz_dogru_anahtarla(tmp_path, monkeypatch):
    import time
    import app.web as w
    from app.bildirim import CaptchaKoprusu as CK
    cikis = []
    monkeypatch.setattr(w, "_cik", lambda: cikis.append(1))
    tg = SahteTelegram()
    c = Uygulama(Depo(tmp_path), OrnekToplayici(), tg, CK(tg), saat=Saat("2026-11-26T09:00"))
    anahtarsiz = TestClient(uygulama_olustur(c, env={"WEB_SIFRE": SIFRE, "WEB_GIZLI": "x" * 32, "ZAMANLAYICI": "0"}))
    assert anahtarsiz.post("/api/kapat-kontrol", headers={"X-Kontrol-Token": "x"}).status_code == 403     # anahtar tanımlı değil: kapalı
    assert anahtarsiz.post("/api/kapat-kontrol").status_code == 403
    ic = TestClient(uygulama_olustur(c, env={"WEB_SIFRE": SIFRE, "WEB_GIZLI": "x" * 32, "ZAMANLAYICI": "0", "BEYANNAME_KONTROL_TOKEN": "gizli123"}))
    assert ic.post("/api/kapat-kontrol", headers={"X-Kontrol-Token": "yanlis"}).status_code == 403
    assert ic.post("/api/kapat-kontrol").status_code == 403
    time.sleep(0.9)
    assert cikis == []                                                                                      # yanlış denemeler kapatmaz
    assert ic.post("/api/kapat-kontrol", headers={"X-Kontrol-Token": "gizli123"}).json() == {"ok": True}
    for _ in range(40):
        if cikis:
            break
        time.sleep(0.05)
    assert cikis == [1]
