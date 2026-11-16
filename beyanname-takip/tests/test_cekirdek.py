import json
import threading
from datetime import datetime

import pytest

from app.bildirim import CaptchaKoprusu, Telegram
from app.cekirdek import Uygulama
from app.depo import Depo
from app.toplayici import DosyaToplayici, OrnekToplayici


class SahteTelegram:
    hazir = True

    def __init__(self, basarili=True):
        self.mesajlar, self.basarili, self.gelen = [], basarili, []

    def gonder(self, m):
        if self.basarili:
            self.mesajlar.append(m)
        return self.basarili

    def foto_gonder(self, png, aciklama=""):
        self.mesajlar.append(("foto", aciklama))
        return True

    def yeni_mesajlar(self):
        g, self.gelen = self.gelen, []
        return g


class Saat:
    def __init__(self, an):
        self.an = datetime.fromisoformat(an)

    def __call__(self):
        return self.an


def uyg(tmp_path, an, toplayici=None, tg=None):
    saat = Saat(an)
    tg = tg or SahteTelegram()
    return Uygulama(Depo(tmp_path), toplayici or OrnekToplayici(), tg, CaptchaKoprusu(tg), saat=saat), tg, saat


class Bozuk:
    def topla(self, bugun, captcha=None):
        raise RuntimeError("Luca giriş sayfası açılamadı")


def mphb_aylik(u):
    """Varsayılan MUHSGK artık "auto" (SGK dosyası varsa aylık, yoksa 3 aylık); bu testler aylık davranışı sınar."""
    ids = [m["id"] for m in u.depo.oku("mukellefler.json", {}).get("kayitlar", [])]
    u.depo.guncelle("ayarlar.json", lambda d: d.setdefault("mukellef", {}).update({i: {"MPHB": "aylik"} for i in ids}))


def test_ornek_toplayici_eksikleri_bulur(tmp_path):
    u, tg, _ = uyg(tmp_path, "2026-11-26T09:00")
    assert u.topla()["ok"]
    mphb_aylik(u)
    m = u.maddeler()
    eksik = {(x.ad, x.tur) for x in m if x.durum == "eksik" and x.donem == "2026-10"}
    assert ("ALFA TİCARET", "KDV1") in eksik and ("DELTA DANIŞMANLIK", "MPHB") in eksik
    assert ("BETA İNŞAAT", "KDV1") not in eksik


def test_slot_bir_kez_calisir_ve_mesaj_gider(tmp_path):
    u, tg, _ = uyg(tmp_path, "2026-11-26T09:00")
    r = u.slot_calistir("09:00")
    assert r["gonderildi"] and any("çalışıyor" in m for m in tg.mesajlar)
    n = len(tg.mesajlar)
    assert u.slot_calistir("09:00") == "zaten çalıştı" and len(tg.mesajlar) == n


def test_telegram_basarisizsa_slot_isaretlenmez_tekrar_denenir(tmp_path):
    tg = SahteTelegram(basarili=False)
    u, _, _ = uyg(tmp_path, "2026-11-30T21:00", tg=tg)
    assert u.slot_calistir("21:00")["gonderildi"] is False
    tg.basarili = True
    assert u.slot_calistir("21:00")["gonderildi"] and any("SON UYARI" in m for m in tg.mesajlar)


def test_toplama_hatasi_bildirilir_ve_eski_veri_kullanilir(tmp_path):
    u, tg, saat = uyg(tmp_path, "2026-11-30T20:30")
    u.topla()                                                       # önce başarılı veri
    u.toplayici = Bozuk()
    saat.an = datetime.fromisoformat("2026-11-30T21:00")
    u.slot_calistir("21:00")
    metin = "\n".join(tg.mesajlar)
    assert "VERİ ALINAMADI" in metin and "Luca giriş sayfası açılamadı" in metin
    assert "SON UYARI" in metin                                     # eski veriyle de uyarı sürer
    d = u.veri_durumu()
    assert d["hata"] and not d["eski"]


def test_hic_veri_yoksa_sabah_ozeti_calisiyor_demez(tmp_path):
    u, tg, _ = uyg(tmp_path, "2026-11-26T09:00", toplayici=Bozuk())
    u.slot_calistir("09:00")
    assert tg.mesajlar and "VERİ ALINAMADI" in tg.mesajlar[0]
    assert not any("çalışıyor" in m for m in tg.mesajlar)


def test_zamanlayici_kacan_slotlardan_sadece_sonuncusu(tmp_path):
    u, tg, saat = uyg(tmp_path, "2026-11-30T21:20")                 # 20:30 ve 21:00 kaçtı
    u.zamanlayici_adimi()
    g = u.depo.oku("gonderim.json")
    assert g["2026-11-30|20:30"] == "atlandı" and not g["2026-11-30|21:00"].startswith("atl")
    assert any("gecikmeli" in m for m in tg.mesajlar)
    n = len(tg.mesajlar)
    u.zamanlayici_adimi()
    assert len(tg.mesajlar) == n


def test_basarisiz_gonderim_5_dakikada_bir_denenir(tmp_path):
    tg = SahteTelegram(basarili=False)
    sayac = {"n": 0}

    class Sayan(OrnekToplayici):
        def topla(self, bugun, captcha=None):
            sayac["n"] += 1
            return super().topla(bugun, captcha)
    u, _, saat = uyg(tmp_path, "2026-11-30T21:00", toplayici=Sayan(), tg=tg)
    u.zamanlayici_adimi()
    saat.an = datetime.fromisoformat("2026-11-30T21:02")
    u.zamanlayici_adimi()
    assert sayac["n"] == 1                                          # 2 dk sonra yeniden Luca'ya gidilmez
    tg.basarili = True
    saat.an = datetime.fromisoformat("2026-11-30T21:06")
    u.zamanlayici_adimi()
    assert sayac["n"] == 2 and any("SON UYARI" in m for m in tg.mesajlar)


def test_zamanlayici_tolerans_disinda_calismaz(tmp_path):
    u, tg, _ = uyg(tmp_path, "2026-11-30T15:00")                    # 13:00'ten 2 saat sonra
    u.zamanlayici_adimi()
    assert tg.mesajlar == [] and u.depo.oku("gonderim.json") == {}


def test_bayram_verisi_olmayan_yil_uyarisi(tmp_path):
    u, tg, _ = uyg(tmp_path, "2032-01-14T09:00")
    u.slot_calistir("09:00")
    assert any("bayram tatilleri" in m for m in tg.mesajlar)


def test_dosya_toplayici_json_ve_csv(tmp_path):
    g = tmp_path / "girdi"
    (g / "ofis").mkdir(parents=True)
    (g / "isletme").mkdir()
    firmalar = {"yil": 2026, "firmalar": [{"ad": "ALFA", "unvan": "ALFA LTD", "vkn": "1111111111", "acilis": "01/01/2020", "kapanis": ""}]}
    for h in ("ofis", "isletme"):
        (g / h / "luca-musteri-listesi.json").write_text(json.dumps(firmalar), encoding="utf-8")
    (g / "ofis" / "luca-beyannameler.json").write_text(json.dumps(
        {"beyannameler": [{"vkn": "1111111111", "tur": "KDV1", "donem": "10/2026", "durum": "Onaylanmış"}]}), encoding="utf-8")
    (g / "isletme" / "luca-beyannameler.csv").write_text(
        "Vergi No;Unvan;Beyanname Türü;Dönem;Durum\n1111111111;ALFA LTD;MUHSGK;10/2026;Onaylanmış\n", encoding="utf-8-sig")
    u, tg, _ = uyg(tmp_path, "2026-11-26T09:00", toplayici=DosyaToplayici(g))
    r = u.topla()
    assert r["ok"] and r["mukellef"] == 2 and r["beyanname"] == 2
    mphb_aylik(u)
    d = {(x.hesap, x.tur): x.durum for x in u.maddeler() if x.donem == "2026-10" and x.tur in ("KDV1", "MPHB")}
    assert d == {("ofis", "KDV1"): "verildi", ("ofis", "MPHB"): "eksik",
                 ("isletme", "KDV1"): "eksik", ("isletme", "MPHB"): "verildi"}


def test_dosya_toplayici_eksik_dosya_hata_verir(tmp_path):
    (tmp_path / "girdi" / "ofis").mkdir(parents=True)
    u, _, _ = uyg(tmp_path, "2026-11-26T09:00", toplayici=DosyaToplayici(tmp_path / "girdi"))
    r = u.topla()
    assert not r["ok"] and "luca-musteri-listesi" in r["hata"]


# ---- Telegram ve captcha ----

def test_telegram_gonder_ve_token_gizli(tmp_path):
    cagrilar = []

    def http(url, veri=None, baslik=None, zaman=35):
        cagrilar.append((url, json.loads(veri)))
        return {"ok": True}
    t = Telegram("TOKEN123", "42", http=http)
    assert t.gonder("<b>merhaba</b>")
    assert cagrilar[0][0].endswith("/botTOKEN123/sendMessage") and cagrilar[0][1]["parse_mode"] == "HTML"
    import urllib.error

    def hatali(url, veri=None, baslik=None, zaman=35):
        raise urllib.error.URLError("https://api.telegram.org/botTOKEN123/sendMessage bağlantı yok")
    import logging
    kayit = []
    h = logging.Handler()
    h.emit = lambda r: kayit.append(r.getMessage())
    logging.getLogger("bildirim").addHandler(h)
    assert Telegram("TOKEN123", "42", http=hatali).gonder("x") is False
    assert kayit and all("TOKEN123" not in k for k in kayit)


def test_telegram_ayarsizsa_gonderilmez():
    assert Telegram("", "").gonder("x") is False


def test_telegram_yalniz_kendi_sohbetinden_mesaj_alir():
    def http(url, veri=None, baslik=None, zaman=35):
        return {"ok": True, "result": [
            {"update_id": 1, "message": {"chat": {"id": 99}, "text": "yabancı"}},
            {"update_id": 2, "message": {"chat": {"id": 42}, "text": " AB12 "}}]}
    t = Telegram("T", "42", http=http)
    assert t.yeni_mesajlar() == ["AB12"] and t._offset == 3


def test_captcha_telegramdan_cevap():
    tg = SahteTelegram()
    k = CaptchaKoprusu(tg, bekleme_sn=5, aralik_sn=0.01)
    threading.Timer(0.1, lambda: tg.gelen.append("K7P2")).start()
    assert k.sor(b"\x89PNG") == "K7P2"
    assert ("foto", "Luca güvenlik kodu: resimdeki kodu bu sohbete yazın") in tg.mesajlar
    assert not k.bekliyor_mu()


def test_captcha_webden_cevap_ve_zaman_asimi():
    tg = SahteTelegram()
    k = CaptchaKoprusu(tg, bekleme_sn=5, aralik_sn=0.01)
    threading.Timer(0.1, lambda: k.cevapla("WEB1")).start()
    assert k.sor(b"x") == "WEB1"
    assert not k.cevapla("fazla")                                   # bekleyen yokken cevap kabul edilmez
    assert CaptchaKoprusu(SahteTelegram(), bekleme_sn=0.05, aralik_sn=0.01).sor(b"x") is None


# ---- E-posta ve birleşik bildirici ----

class SahteSMTP:
    gonderilen, girisler, hata = [], [], None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, k, p):
        SahteSMTP.girisler.append((k, p))

    def send_message(self, ileti):
        if SahteSMTP.hata:
            raise SahteSMTP.hata
        SahteSMTP.gonderilen.append(ileti)


def eposta(**kw):
    from app.bildirim import Eposta
    SahteSMTP.gonderilen, SahteSMTP.girisler, SahteSMTP.hata = [], [], None
    return Eposta("smtp.test", 587, "ben@test.com", "uygulama-sifresi", kw.pop("alici", "ben@test.com, ofis@test.com"),
                  smtp_fabrikasi=SahteSMTP, **kw)


def test_eposta_gonderir_konu_ve_html_duzenler():
    e = eposta()
    assert e.hazir and e.gonder("<b>SON UYARI</b>\nALFA &amp; BETA: KDV eksik")
    ileti = SahteSMTP.gonderilen[0]
    assert ileti["Subject"] == "Beyanname Takip: SON UYARI" and ileti["To"] == "ben@test.com, ofis@test.com"
    assert "ALFA & BETA: KDV eksik" in ileti.get_body(("plain",)).get_content()
    assert "<b>SON UYARI</b>" in ileti.get_body(("html",)).get_content()
    assert SahteSMTP.girisler == [("ben@test.com", "uygulama-sifresi")]


def test_eposta_hata_ve_ayarsizlik_sessiz_dusmez_ama_sizdirmaz():
    import logging
    import smtplib
    kayit = []
    h = logging.Handler()
    h.emit = lambda r: kayit.append(r.getMessage())
    logging.getLogger("bildirim").addHandler(h)
    e = eposta()
    SahteSMTP.hata = smtplib.SMTPAuthenticationError(535, b"kullanici ben@test.com uygulama-sifresi hatali")
    assert e.gonder("x") is False
    assert kayit and all("uygulama-sifresi" not in k and "ben@test.com" not in k for k in kayit)
    from app.bildirim import Eposta
    assert Eposta("", 587, "", "", "").gonder("x") is False and not Eposta("", 587, "", "", "").hazir


def test_eposta_ortamdan_ve_alici_varsayilani():
    from app.bildirim import Eposta
    e = Eposta.ortamdan({"SMTP_KULLANICI": "ben@test.com", "SMTP_PAROLA": "p"})
    assert e.hazir and e.host == "smtp.gmail.com" and e.port == 587 and e.alicilar == ["ben@test.com"]
    assert not Eposta.ortamdan({}).hazir


def test_bildirici_en_az_bir_kanal_ulasirsa_gonderildi_sayar():
    from app.bildirim import Bildirici
    tg = SahteTelegram(basarili=False)
    e = eposta()
    b = Bildirici([tg, e])
    assert b.hazir and b.gonder("<b>merhaba</b>") and len(SahteSMTP.gonderilen) == 1      # Telegram düştü, e-posta gitti
    SahteSMTP.hata = OSError("ağ")
    assert b.gonder("tekrar") is False                                                     # ikisi de düşerse tekrar denenir
    assert Bildirici([]).gonder("x") is False and not Bildirici([]).hazir
    assert b.hazir_kanallar() == ["SahteTelegram", "E-posta"]


def test_eposta_son_hata_turu_tutulur_ve_ayrinti_verilir():
    from app.bildirim import Bildirici
    e = eposta()
    b = Bildirici([e])
    SahteSMTP.hata = OSError("ağ ben@test.com uygulama-sifresi")
    assert b.gonder("x") is False and b.ayrinti() == ["E-posta: OSError"]       # metin/adres/parola sızmaz
    SahteSMTP.hata = None
    assert b.gonder("x") and b.ayrinti() == []


# ---- Gmail API ----

def gmail(http, **kw):
    from app.bildirim import GmailApi
    return GmailApi("cid", "csir", "yenile-anahtari", "ben@test.com", kw.pop("alici", "ben@test.com, ofis@test.com"), http=http, **kw)


def test_gmail_api_token_alir_gonderir_ve_anahtari_onbellekler():
    import base64
    cagrilar = []

    def http(url, veri=None, baslik=None, zaman=35):
        cagrilar.append((url, veri, baslik))
        if "oauth2" in url:
            return {"access_token": "ERISIM", "expires_in": 3600}
        return {"id": "m1"}
    g = gmail(http)
    assert g.hazir and g.gonder("<b>SON UYARI</b>\nALFA: KDV eksik") and g.gonder("ikinci")
    assert [u.split("/")[2] for u, _, _ in cagrilar] == ["oauth2.googleapis.com", "gmail.googleapis.com", "gmail.googleapis.com"]  # token 1 kez
    assert cagrilar[1][2]["Authorization"] == "Bearer ERISIM"
    ham = base64.urlsafe_b64decode(json.loads(cagrilar[1][1])["raw"]).decode()
    assert "Subject: Beyanname Takip: SON UYARI" in ham and "ofis@test.com" in ham


def test_gmail_api_hatalari_ayrintili_ama_sizdirmaz():
    import io
    import urllib.error
    import logging
    kayit = []
    h = logging.Handler()
    h.emit = lambda r: kayit.append(r.getMessage())
    logging.getLogger("bildirim").addHandler(h)

    def reddet(url, veri=None, baslik=None, zaman=35):
        raise urllib.error.HTTPError(url, 400, "x", {}, io.BytesIO(b'{"error": "invalid_grant", "error_description": "yenile-anahtari ben@test.com"}'))
    g = gmail(reddet)
    assert g.gonder("x") is False and g.son_hata == "HTTP 400 invalid_grant"
    assert all("yenile-anahtari" not in k and "ben@test.com" not in k for k in kayit)

    def ag(url, veri=None, baslik=None, zaman=35):
        raise OSError("bağlantı")
    g2 = gmail(ag)
    assert g2.gonder("x") is False and g2.son_hata == "OSError"
    from app.bildirim import GmailApi, Bildirici
    assert not GmailApi.ortamdan({}).hazir and GmailApi.ortamdan({"GMAIL_CLIENT_ID": "a", "GMAIL_CLIENT_SECRET": "b", "GMAIL_REFRESH_TOKEN": "c",
                                                                  "MAIL_GONDEREN": "ben@test.com"}).hazir
    assert Bildirici([g2]).ayrinti() == ["E-posta (Gmail API): OSError"]


def test_gmail_api_401de_anahtari_yeniler():
    import io
    import urllib.error
    sira = []

    def http(url, veri=None, baslik=None, zaman=35):
        if "oauth2" in url:
            sira.append("token")
            return {"access_token": "A" + str(len(sira)), "expires_in": 3600}
        if len(sira) == 1:
            sira.append("401")
            raise urllib.error.HTTPError(url, 401, "x", {}, io.BytesIO(b"{}"))
        return {"id": "m"}
    g = gmail(http)
    assert g.gonder("x") is False and g.gonder("x") is True and sira.count("token") == 2


# ---- Resend ----

def test_resend_gonderir_user_agent_ve_alici_ile():
    from app.bildirim import ResendApi
    cagrilar = []

    def http(url, veri=None, baslik=None, zaman=35):
        cagrilar.append((url, json.loads(veri), baslik))
        return {"id": "e1"}
    r = ResendApi("re_ANAHTAR", "ben@test.com", http=http)
    assert r.hazir and r.gonder("<b>SON UYARI</b>\nALFA: KDV eksik")
    url, yuk, baslik = cagrilar[0]
    assert url == "https://api.resend.com/emails" and baslik["Authorization"] == "Bearer re_ANAHTAR" and baslik["User-Agent"]
    assert yuk["from"] == "onboarding@resend.dev" and yuk["to"] == ["ben@test.com"] and yuk["subject"] == "Beyanname Takip: SON UYARI"
    assert "ALFA: KDV eksik" in yuk["text"] and "<b>SON UYARI</b>" in yuk["html"]


def test_resend_hata_ayrintisi_sizdirmaz_ve_ayarsizlik():
    import io
    import urllib.error
    import logging
    from app.bildirim import ResendApi, Bildirici
    kayit = []
    h = logging.Handler()
    h.emit = lambda r: kayit.append(r.getMessage())
    logging.getLogger("bildirim").addHandler(h)

    def reddet(url, veri=None, baslik=None, zaman=35):
        raise urllib.error.HTTPError(url, 403, "x", {}, io.BytesIO(b'{"statusCode":403,"name":"validation_error","message":"re_ANAHTAR ben@test.com"}'))
    r = ResendApi("re_ANAHTAR", "ben@test.com", http=reddet)
    assert r.gonder("x") is False and r.son_hata == "HTTP 403 validation_error"
    assert all("re_ANAHTAR" not in k and "ben@test.com" not in k for k in kayit)
    assert Bildirici([r]).ayrinti() == ["E-posta (Resend): HTTP 403 validation_error"]
    assert not ResendApi.ortamdan({}).hazir and not ResendApi.ortamdan({"RESEND_API_KEY": "k"}).hazir      # alıcı şart
    assert ResendApi.ortamdan({"RESEND_API_KEY": "k", "MAIL_ALICI": "a@b.c"}).hazir


def test_rapor_gonder_elle_istenen_ozet_slota_bagli_degil(tmp_path):
    u, tg, _ = uyg(tmp_path, "2026-11-26T14:00")                    # slot saati değil (13:00 ile 17:00 arası)
    r = u.rapor_gonder(10)
    assert r["ok"] and tg.mesajlar and "Elle istenen özet" in tg.mesajlar[0]
    assert any("mükellef" in m for m in tg.mesajlar)               # eksikler listelenir
    assert u.depo.oku("gonderim.json", {}) == {}                    # zamanlayıcı slotu işaretlenmez
    assert u.depo.oku("durum.json", {})["son_rapor"]["ok"] is True and u.rapor_suruyor is False


def test_rapor_gonder_eksik_yoksa_tamam_der_ve_hatayi_bildirir(tmp_path):
    u, tg, _ = uyg(tmp_path, "2026-12-20T09:00")                    # en yakın son gün 28 Aralık: esik 3 içinde değil
    r = u.rapor_gonder(3)
    assert r["ok"] and "eksik beyanname yok" in tg.mesajlar[-1]
    tg2 = SahteTelegram(basarili=False)
    u2, _, _ = uyg(tmp_path / "b", "2026-11-26T14:00", tg=tg2)
    r2 = u2.rapor_gonder(10)
    assert r2["ok"] is False and "gönderilemedi" in r2["mesaj"]
    u3, tg3, _ = uyg(tmp_path / "c", "2026-11-26T14:00", toplayici=Bozuk())
    u3.rapor_gonder(10)
    assert "VERİ ALINAMADI" in "\n".join(tg3.mesajlar)              # Luca verisi yoksa bu da bildirilir


def test_mesajlar_ofis_birli_ve_isletme_ayri_epostalar(tmp_path):
    from app.kontrol import mukellef_normalize

    class Uc:
        def topla(self, bugun, captcha=None):
            mk = [mukellef_normalize({"sirket_id": v, "ad": a, "unvan": a, "vkn": v, "acilis": "01/01/2015", "kapanis": ""}, h)
                  for a, v, h in (("ALFA", "1111111111", "ofis"), ("1 BETA", "2222222222", "ofis"), ("GAMA", "3333333333", "isletme"))]
            return {"mukellefler": mk, "beyannameler": [], "uyarilar": []}
    u, tg, _ = uyg(tmp_path, "2026-11-30T21:00", toplayici=Uc())
    u.slot_calistir("21:00")
    basliklar = [m.split("</b>")[0].replace("<b>", "") for m in tg.mesajlar]
    assert '[OFİS]' in basliklar and "[OFİS · 1 ile başlayanlar]" in basliklar and "[İŞLETME]" in basliklar
    ofis = next(m for m in tg.mesajlar if m.startswith("<b>[OFİS]</b>"))
    assert "ALFA" in ofis and "1 BETA" not in ofis and "GAMA" not in ofis                   # bölümler birbirine karışmaz
    assert "SON UYARI" in ofis


def test_topla_gib_araligini_toplayiciya_iletir_ve_sonucta_gosterir(tmp_path):
    from datetime import date as _d
    alinan = []

    class Kayit(OrnekToplayici):
        def topla(self, bugun, captcha=None, gib_aralik=None):
            alinan.append(gib_aralik)
            return super().topla(bugun, captcha)
    u, _, _ = uyg(tmp_path, "2026-11-26T09:00", toplayici=Kayit())
    assert u.topla()["ok"] and alinan == [None] and "gib" not in u.depo.oku("durum.json", {})["son_toplama"]       # varsayılan: iletilmez
    r = u.topla((_d(2026, 10, 1), _d(2026, 10, 31)))
    assert r["ok"] and alinan[-1] == (_d(2026, 10, 1), _d(2026, 10, 31)) and r["gib"] == "01.10.2026 – 31.10.2026"
    u2, _, _ = uyg(tmp_path / "x", "2026-11-26T09:00", toplayici=OrnekToplayici())
    assert u2.topla()["ok"]                                                  # gib_aralik'i bilmeyen eski toplayıcılar da çalışır
