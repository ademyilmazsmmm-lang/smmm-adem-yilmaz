from datetime import date

from app.kontrol import (degerlendir, gunluk_ozet, mesaj_olustur, mukellef_normalize, uyari_gerekli)
from app.kurallar import Tatiller

T = Tatiller()


def mus(ad, vkn="", acilis="", kapanis="", hesap="ofis"):
    return mukellef_normalize({"ad": ad, "unvan": ad + " LTD", "vkn": vkn, "acilis": acilis, "kapanis": kapanis}, hesap)


def bey(vkn, tur, donem, durum="Onaylanmış", firma="", hesap="ofis"):
    return {"vkn": vkn, "firma": firma, "tur": tur, "donem": donem, "durum": durum, "hesap": hesap}


BUGUN = date(2026, 11, 26)     # KDV (Ekim) son gün 30 Kasım, MUHSGK 26 Kasım, geçici 17 Kasım geçti


def bul(maddeler, ad, tur):
    return [m for m in maddeler if m.ad == ad and m.tur == tur and m.donem == "2026-10" or
            (m.ad == ad and m.tur == tur and tur == "GECICI" and m.donem == "2026-09")]


def test_verildi_eksik_onaysiz_muaf():
    ml = [mus("ALFA", "1111111111"), mus("BETA", "2222222222"), mus("GAMA", "3333333333"), mus("DELTA", "4444444444")]
    b = [bey("1111111111", "KDV1", "10/2026"), bey("2222222222", "KDV1", "10/2026", "Hatalı"),
         bey("3333333333", "MUHSGK", "10/2026")]
    ay = {"muaf": [{"id": "ofis:4444444444", "tur": "KDV1", "donem": "2026-10"}]}
    m = degerlendir(ml, ay, b, BUGUN, T)
    d = {(x.ad, x.tur): x for x in m if x.donem == "2026-10"}
    assert d[("ALFA", "KDV1")].durum == "verildi"
    assert d[("BETA", "KDV1")].durum == "onaysiz"
    assert d[("GAMA", "KDV1")].durum == "eksik"
    assert d[("DELTA", "KDV1")].durum == "muaf"
    assert d[("GAMA", "MPHB")].durum == "verildi"
    assert d[("ALFA", "MPHB")].durum == "eksik"
    assert d[("ALFA", "KDV1")].kalan == 4 and d[("ALFA", "MPHB")].kalan == 0


def test_gecici_ve_pencere():
    m = degerlendir([mus("ALFA", "1111111111")], {}, [], BUGUN, T)
    g = [x for x in m if x.tur == "GECICI"]
    assert [(x.donem, x.son_gun, x.durum) for x in g] == [("2026-09", date(2026, 11, 17), "eksik")]
    assert g[0].kalan == -9


def test_ayar_yok_ve_3aylik():
    ay = {"mukellef": {"ofis:1111111111": {"KDV1": "yok", "MPHB": "3aylik", "GECICI": "yok", "onayli": True}}}
    m = degerlendir([mus("ALFA", "1111111111")], ay, [], date(2026, 12, 28), T)
    assert {x.tur for x in m} == {"MPHB"}                      # KDV ve geçici kapalı
    assert m[0].donem == "2026-12" and m[0].son_gun == date(2027, 1, 26) and m[0].ayar_onayli


def test_acilis_kapanis():
    ml = [mus("YENI", "6666666666", acilis="01/11/2026"), mus("KAPALI", "5555555555", kapanis="30/06/2026"),
          mus("ESKI", "7777777777", acilis="01/01/2020")]
    m = degerlendir(ml, {}, [], BUGUN, T)
    yeni = [x.donem for x in m if x.ad == "YENI" and x.tur == "KDV1"]
    assert yeni == ["2026-11"]                                     # Ekim dönemi açılıştan önce bitti, Kasım beklenir
    assert [x for x in m if x.ad == "KAPALI"] == []
    assert any(x.ad == "ESKI" for x in m)
    # kapanış ayındaki dönem hâlâ beklenir, işaretlenir
    ml2 = [mus("KAPANIS", "8888888888", kapanis="15/10/2026")]
    k = [x for x in degerlendir(ml2, {}, [], BUGUN, T) if x.tur == "KDV1" and x.donem == "2026-10"]
    assert k and k[0].kapanis_donemi


def test_isim_eslesmesi_vknsiz_ve_hesap_ayrimi():
    ml = [mus("ALFA TICARET", "", hesap="ofis"), mus("ALFA TICARET", "", hesap="isletme")]
    b = [bey("", "KDV1", "10/2026", firma="Alfa Ticaret Ltd", hesap="ofis")]
    # 'ALFA TICARET LTD' (unvan) kayıttaki firma adıyla birebir eşleşir; ama yalnızca 'ofis' hesabında
    m = degerlendir(ml, {}, b, BUGUN, T)
    d = {(x.hesap, x.tur): x.durum for x in m if x.donem == "2026-10" and x.tur == "KDV1"}
    assert d == {("ofis", "KDV1"): "verildi", ("isletme", "KDV1"): "eksik"}


def test_uyari_zamanlamasi():
    assert uyari_gerekli(0, "21:00") and uyari_gerekli(0, "22:30") and not uyari_gerekli(1, "21:00")
    assert uyari_gerekli(1, "09:00") and uyari_gerekli(1, "17:00") and not uyari_gerekli(1, "13:00")
    assert uyari_gerekli(3, "09:00") and not uyari_gerekli(4, "09:00") and uyari_gerekli(7, "09:00")
    assert uyari_gerekli(-1, "09:00") and uyari_gerekli(-5, "09:00") and not uyari_gerekli(-6, "09:00")
    assert not uyari_gerekli(-1, "21:00")


def test_mesaj_son_gun_ve_html_kacisi():
    ml = [mus("A&B <x>", "1111111111"), mus("TAMAM", "2222222222")]
    b = [bey("2222222222", "KDV1", "10/2026")]
    gun = date(2026, 11, 30)                                       # KDV son günü
    m = degerlendir(ml, {}, b, gun, T)
    metin = "\n".join(mesaj_olustur(m, "21:00", "2026-11-30T20:58"))
    assert "SON UYARI" in metin and "A&amp;B &lt;x&gt;" in metin and "TAMAM" not in metin
    assert "20:58" in metin
    assert mesaj_olustur(m, "13:00", None) != []                   # kalan 0: öğle de uyarılır
    # son güne 2 gün var: öğle uyarısı yok
    m2 = degerlendir(ml, {}, b, date(2026, 11, 28), T)
    assert [x for x in mesaj_olustur(m2, "13:00", None)] == []
    assert mesaj_olustur(m2, "09:00", None) != []


def test_veri_hatasi_her_zaman_mesaj_uretir():
    out = mesaj_olustur([], "21:00", None, veri_hatasi="Luca girişi başarısız")
    assert out and "VERİ ALINAMADI" in out[0] and "Luca girişi başarısız" in out[0]


def test_gunluk_ozet():
    m = degerlendir([mus("A", "1111111111"), mus("B", "2222222222")], {}, [bey("1111111111", "MUHSGK", "10/2026")], BUGUN, T)
    s = gunluk_ozet(m, "2026-11-26T09:00", BUGUN)
    assert "çalışıyor" in s and "26.11.2026" in s and "1 eksik" in s


def test_uzun_mesaj_bolunur():
    ml = [mus(f"FIRMA {i:03d} " + "X" * 30, f"{i:010d}") for i in range(300)]
    m = degerlendir(ml, {}, [], date(2026, 11, 30), T)
    parcalar = mesaj_olustur(m, "21:00", None)
    assert len(parcalar) > 1 and all(len(p) <= 4096 for p in parcalar)
