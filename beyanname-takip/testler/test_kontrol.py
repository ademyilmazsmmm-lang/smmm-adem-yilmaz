from datetime import date

from app.kontrol import (degerlendir, gunluk_ozet, mesaj_olustur, mukellef_normalize, uyari_gerekli)
from app.kurallar import Tatiller

T = Tatiller()


def mus(ad, vkn="", acilis="", kapanis="", hesap="ofis"):
    return mukellef_normalize({"ad": ad, "unvan": ad + " LTD", "vkn": vkn, "acilis": acilis, "kapanis": kapanis}, hesap)


def bey(vkn, tur, donem, durum="Onaylanmış", firma="", hesap="ofis"):
    return {"vkn": vkn, "firma": firma, "tur": tur, "donem": donem, "durum": durum, "hesap": hesap}


BUGUN = date(2026, 11, 26)     # KDV (Ekim) son gün 30 Kasım, MUHSGK 26 Kasım, geçici 17 Kasım geçti


def aylik(*ml, ek=None):
    """Bu testler aylık MUHSGK davranışını sınar; varsayılan artık "auto" (SGK dosyası varsa aylık, yoksa 3 aylık)."""
    ay = {"mukellef": {m["id"]: {"MPHB": "aylik"} for m in ml}}
    ay.update(ek or {})
    return ay


def bul(maddeler, ad, tur):
    return [m for m in maddeler if m.ad == ad and m.tur == tur and m.donem == "2026-10" or
            (m.ad == ad and m.tur == tur and tur == "GECICI" and m.donem == "2026-09")]


def test_verildi_eksik_onaysiz_muaf():
    ml = [mus("ALFA", "1111111111"), mus("BETA", "2222222222"), mus("GAMA", "3333333333"), mus("DELTA", "4444444444")]
    b = [bey("1111111111", "KDV1", "10/2026"), bey("2222222222", "KDV1", "10/2026", "Hatalı"),
         bey("3333333333", "MUHSGK", "10/2026")]
    ay = aylik(*ml, ek={"muaf": [{"id": "ofis:4444444444", "tur": "KDV1", "donem": "2026-10"}]})
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
    ml = [mus("A", "1111111111"), mus("B", "2222222222")]
    m = degerlendir(ml, aylik(*ml), [bey("1111111111", "MUHSGK", "10/2026")], BUGUN, T)
    s = gunluk_ozet(m, "2026-11-26T09:00", BUGUN)
    assert "çalışıyor" in s and "26.11.2026" in s and "1 eksik" in s


def test_uzun_mesaj_bolunur():
    ml = [mus(f"FIRMA {i:03d} " + "X" * 30, f"{i:010d}") for i in range(300)]
    m = degerlendir(ml, {}, [], date(2026, 11, 30), T)
    parcalar = mesaj_olustur(m, "21:00", None)
    assert len(parcalar) > 1 and all(len(p) <= 4096 for p in parcalar)


# ================= MUHSGK "auto", aylık/3 aylık ayrımı, KDV2, Poşet =================

def mus_sgk(ad, vkn, sgk_isyeri):
    return mukellef_normalize({"sirket_id": vkn, "ad": ad, "unvan": ad + " LTD", "vkn": vkn, "acilis": "01/01/2020", "kapanis": "",
                               "sgk_isyeri": sgk_isyeri}, "ofis")


def mphb(vkn, bas, bit, durum="Onaylanmış", ebildirge=1):
    return {"vkn": vkn, "firma": "", "tur": "MUHSGK", "donem": bit, "donem_bas": bas, "durum": durum, "hesap": "ofis",
            "ebildirge": ebildirge, "sgk_durum": "2"}


def mphb_durum(ml, kayitlar, bugun, ayar=None):
    return {(x.ad, x.donem): (x.durum, x.etiket) for x in degerlendir(ml, ayar or {}, kayitlar, bugun, T) if x.tur == "MPHB"}


def test_mphb_auto_sgk_dosyasi_varsa_aylik_yoksa_3_aylik():
    ml = [mus_sgk("VAR", "1111111111", 1), mus_sgk("YOK", "2222222222", 0)]
    d = mphb_durum(ml, [], date(2026, 11, 26))                      # Kasım'da: aylık Ekim (26 Kasım) ve Kasım (28 Aralık); 3 aylık (26 Ocak) yok
    assert sorted(d) == [("VAR", "2026-10"), ("VAR", "2026-11")]
    d = mphb_durum(ml, [], date(2026, 10, 20))                      # Ekim'de: Eylül aylığı ve Temmuz–Eylül 3 aylığı (ikisi de 26 Ekim)
    assert d[("VAR", "2026-09")][1] == "Eylül 2026" and d[("YOK", "2026-09")][1] == "Temmuz–Eylül 2026"


def test_ucaylik_kayit_eylul_aylik_beklentisini_karsilamaz():
    ml = [mus_sgk("VAR", "1111111111", 1)]
    sadece_3aylik = [mphb("1111111111", "07/2026", "09/2026")]
    assert mphb_durum(ml, sadece_3aylik, date(2026, 10, 20))[("VAR", "2026-09")][0] == "eksik"        # Eylül aylığı verilmedi
    aylik = [mphb("1111111111", "09/2026", "09/2026")]
    assert mphb_durum(ml, aylik, date(2026, 10, 20))[("VAR", "2026-09")][0] == "verildi"


def test_3aylik_beklenen_donem_3aylik_kayitla_ya_da_uc_aylik_kayitla_karsilanir():
    ml = [mus_sgk("YOK", "2222222222", 0)]
    assert mphb_durum(ml, [mphb("2222222222", "07/2026", "09/2026", ebildirge=0)], date(2026, 10, 20))[("YOK", "2026-09")][0] == "verildi"
    uc_aylik = [mphb("2222222222", f"{a:02d}/2026", f"{a:02d}/2026", ebildirge=0) for a in (7, 8, 9)]
    assert mphb_durum(ml, uc_aylik, date(2026, 10, 20))[("YOK", "2026-09")][0] == "verildi"
    eksik_ay = uc_aylik[:2]                                                                           # Eylül aylığı yok
    assert mphb_durum(ml, eksik_ay, date(2026, 10, 20))[("YOK", "2026-09")][0] == "eksik"


def test_ay_ortasinda_aylığa_gecen_firmada_oncesi_3aylik_beyandadir():
    # Çalışan Ağustos'ta başladı: Ağustos ve Eylül aylık, Temmuz 3 aylık beyanda. Temmuz aylığı 3 aylık kayıtla karşılanır.
    from app.kontrol import _donem_kayitlari
    from app.kurallar import Donem
    t = Donem("MPHB", "aylik", 2026, 7, date(2026, 7, 1), date(2026, 7, 31), date(2026, 8, 26))
    k = [(mphb("1", "07/2026", "09/2026"), 2026 * 12 + 7, 2026 * 12 + 9), (mphb("1", "08/2026", "08/2026"), 2026 * 12 + 8, 2026 * 12 + 8),
         (mphb("1", "09/2026", "09/2026"), 2026 * 12 + 9, 2026 * 12 + 9)]
    tip, kayitlar = _donem_kayitlari(k, t)
    assert tip == "kapsam" and len(kayitlar) == 1
    assert _donem_kayitlari(k[:1], t) == ("", [])                       # sonradan aylık kayıt yoksa Temmuz karşılanmış sayılmaz


def test_3aylik_kapsam_kaydinda_sgk_eksik_aranmaz():
    # Temmuz için 3 aylık kayıt (e-Bildirge yok: o ay SGK'sız) "verildi" kalır; SGK kontrolü yalnızca tam eşleşen kayıtta yapılır
    ml = [mus_sgk("VAR", "1111111111", 1)]
    aylik_sgksiz = [mphb("1111111111", "09/2026", "09/2026", ebildirge=0)]
    assert mphb_durum(ml, aylik_sgksiz, date(2026, 10, 20))[("VAR", "2026-09")][0] == "sgk_eksik"      # aylık kayıt = tam eşleşme


def test_kdv2_ve_poset_varsayilan_kapali_firma_bazinda_acilir():
    ml = [mus("ALFA", "1111111111")]
    assert not [x for x in degerlendir(ml, {}, [], date(2026, 11, 26), T) if x.tur in ("KDV2", "POSET")]
    ay = {"mukellef": {ml[0]["id"]: {"KDV2": "aylik", "POSET": "3aylik"}}}
    m = degerlendir(ml, ay, [], date(2026, 10, 20), T)
    assert {x.tur: x.durum for x in m if x.tur in ("KDV2", "POSET")} == {"KDV2": "eksik", "POSET": "eksik"}     # KDV2 Eylül, Poşet Tem–Eyl
    k = [{"vkn": "1111111111", "firma": "", "tur": "KDV2", "donem": "09/2026", "durum": "Onaylanmış", "hesap": "ofis"},
         {"vkn": "1111111111", "firma": "", "tur": "POSET", "donem": "09/2026", "donem_bas": "07/2026", "durum": "Onaylanmış", "hesap": "ofis"}]
    m2 = degerlendir(ml, ay, k, date(2026, 10, 20), T)
    assert {x.tur: x.durum for x in m2 if x.tur in ("KDV2", "POSET")} == {"KDV2": "verildi", "POSET": "verildi"}


# ================= Son günler (kullanıcı teyitli) ve yıllık KV/GV =================

def kisi(ad, vkn, tc):
    return mukellef_normalize({"sirket_id": vkn, "ad": ad, "unvan": ad, "vkn": vkn, "tc": tc, "acilis": "01/01/2015", "kapanis": ""}, "ofis")


def test_son_gunler_kullanici_kurallari():
    from app.kurallar import son_gun_hesapla
    # KDV 28, MUHSGK 26, KDV2 25, Konaklama 26, Geçici (Kasım) 17; tatil/hafta sonu -> ilk iş günü
    assert son_gun_hesapla("KDV1", 2026, 10, T) == date(2026, 11, 30)         # 28 Kasım Cumartesi -> Pazartesi
    assert son_gun_hesapla("MPHB", 2026, 10, T) == date(2026, 11, 26)
    assert son_gun_hesapla("KDV2", 2026, 10, T) == date(2026, 11, 25)
    assert son_gun_hesapla("KONAKLAMA", 2026, 10, T) == date(2026, 11, 26)
    assert son_gun_hesapla("GECICI", 2026, 9, T) == date(2026, 11, 17)
    assert son_gun_hesapla("KV", 2025, 12, T) == date(2026, 4, 30)            # Kurumlar: 30 Nisan
    assert son_gun_hesapla("GV", 2025, 12, T) == date(2026, 3, 31)            # Gelir: 31 Mart


def test_yillik_kv_tuzele_gv_sahsa_otomatik():
    ml = [kisi("SIRKET", "1111111111", ""), kisi("SAHIS", "2222222222", "12345678901")]
    m = degerlendir(ml, {}, [], date(2026, 4, 20), T)
    kv = {x.ad: x for x in m if x.tur == "KV"}
    assert list(kv) == ["SIRKET"] and kv["SIRKET"].son_gun == date(2026, 4, 30)
    assert kv["SIRKET"].etiket == "Ocak–Aralık 2025"
    m = degerlendir(ml, {}, [], date(2026, 3, 20), T)
    assert [(x.ad, x.son_gun) for x in m if x.tur == "GV"] == [("SAHIS", date(2026, 3, 31))]


def test_yillik_beyanname_kaydi_karsilar_ve_ayar_zorlanabilir():
    ml = [kisi("SIRKET", "1111111111", "")]
    kayit = [{"vkn": "1111111111", "firma": "", "tur": "KURUMLAR", "donem": "12/2025", "donem_bas": "01/2025", "durum": "Onaylanmış", "hesap": "ofis"}]
    d = {x.tur: x.durum for x in degerlendir(ml, {}, kayit, date(2026, 4, 20), T) if x.tur == "KV"}
    assert d == {"KV": "verildi"}
    ay = {"mukellef": {ml[0]["id"]: {"KV": "yok"}}}
    assert not [x for x in degerlendir(ml, ay, [], date(2026, 4, 20), T) if x.tur == "KV"]
    ay2 = {"mukellef": {ml[0]["id"]: {"GV": "yillik"}}}                       # şirkete elle GV açılabilir
    assert [x for x in degerlendir(ml, ay2, [], date(2026, 3, 20), T) if x.tur == "GV"]


# ================= Bölümler: Ofis / Ofis "1" ile başlayanlar / İşletme =================

def mus_h(ad, vkn, hesap):
    return mukellef_normalize({"sirket_id": vkn, "ad": ad, "unvan": ad, "vkn": vkn, "acilis": "01/01/2015", "kapanis": ""}, hesap)


def test_bolumlere_ayir_hesap_ve_birli_grubu():
    from app.kontrol import bolumlere_ayir, birli_mi
    ml = [mus_h("ALFA", "1111111111", "ofis"), mus_h("1 BETA", "2222222222", "ofis"), mus_h("GAMA", "3333333333", "isletme"),
          mus_h("12 DELTA", "4444444444", "isletme")]
    m = degerlendir(ml, aylik(*ml), [], BUGUN, T)
    b = bolumlere_ayir([x for x in m if x.tur == "KDV1"])
    assert [ad for ad, _ in b] == ["OFİS", "OFİS · 1 ile başlayanlar", "İŞLETME", "İŞLETME · 1 ile başlayanlar"]
    assert {x.ad for x in b[1][1]} == {"1 BETA"} and {x.ad for x in b[3][1]} == {"12 DELTA"}
    assert birli_mi(" 1 X") and not birli_mi("X 1") and not birli_mi("") and not birli_mi(None)
    assert [ad for ad, _ in bolumlere_ayir([x for x in m if x.hesap == "isletme" and x.ad == "GAMA"])] == ["İŞLETME"]   # boş bölüm yok
