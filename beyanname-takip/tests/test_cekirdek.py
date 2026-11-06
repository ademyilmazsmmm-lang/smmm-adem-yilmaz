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


def test_ornek_toplayici_eksikleri_bulur(tmp_path):
    u, tg, _ = uyg(tmp_path, "2026-11-26T09:00")
    assert u.topla()["ok"]
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
