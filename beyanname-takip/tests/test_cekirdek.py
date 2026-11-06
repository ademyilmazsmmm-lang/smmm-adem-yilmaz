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
