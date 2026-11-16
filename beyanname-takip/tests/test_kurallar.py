from datetime import date

from app.kurallar import (Tatiller, donem_bitisi, donemler_uret, onayli_mi, son_gun_hesapla, tur_coz)

T = Tatiller()


def test_son_gunler_hafta_sonuna_kayar():
    assert son_gun_hesapla("KDV1", 2026, 10, T) == date(2026, 11, 30)    # 28 Kasım Cumartesi -> Pazartesi
    assert son_gun_hesapla("MPHB", 2026, 10, T) == date(2026, 11, 26)    # Perşembe
    assert son_gun_hesapla("GECICI", 2026, 9, T) == date(2026, 11, 17)   # 3. dönem, Salı
    assert son_gun_hesapla("GECICI", 2026, 12, T) == date(2027, 2, 17)   # 4. dönem, yıl atlar
    assert son_gun_hesapla("MPHB", 2026, 12, T) == date(2027, 1, 26)


def test_bayram_kaymasi():
    # Kurban Bayramı 27-30 Mayıs 2026 (+31 Pazar) -> KDV (Nisan dönemi) 28 Mayıs yerine 1 Haziran
    assert son_gun_hesapla("KDV1", 2026, 4, T) == date(2026, 6, 1)


def test_bayram_verisi_uyarisi():
    assert T.bayram_verisi_var_mi(2026) and not T.bayram_verisi_var_mi(2031)


def test_donemler_uret_pencere():
    d = donemler_uret("KDV1", "aylik", date(2026, 11, 20), date(2026, 12, 31), T)
    assert [(x.anahtar, x.son_gun) for x in d] == [("2026-10", date(2026, 11, 30)), ("2026-11", date(2026, 12, 28))]
    q = donemler_uret("GECICI", "3aylik", date(2026, 11, 1), date(2026, 11, 30), T)
    assert len(q) == 1 and q[0].etiket == "Temmuz–Eylül 2026" and q[0].bas == date(2026, 7, 1)
    assert donemler_uret("GECICI", "aylik", date(2026, 1, 1), date(2026, 12, 31), T) == []   # geçersiz periyot


def test_tur_coz():
    assert tur_coz("KDV1") == tur_coz("KDV Beyannamesi") == "KDV1"
    assert tur_coz("KDV2") == tur_coz("KDV 2") == "KDV2" and tur_coz("KDV3") is None and tur_coz("KDV 9015") is None
    assert tur_coz("POSET") == tur_coz("Poşet Beyannamesi") == "POSET"
    assert tur_coz("MUHSGK") == tur_coz("Muhtasar ve Prim Hizmet Beyannamesi") == tur_coz("MUHTASAR") == "MPHB"
    assert tur_coz("GGECICI") == tur_coz("KGECICI") == tur_coz("Gelir Geçici Vergi Beyannamesi") == "GECICI"
    assert tur_coz("") is None
    assert tur_coz("KURUMLAR") == tur_coz("Kurumlar Vergisi Beyannamesi") == "KV" and tur_coz("GELIR") == tur_coz("GV") == "GV"
    assert tur_coz("KGECICI") == tur_coz("GGECICI") == "GECICI"           # geçiciler Kurumlar/Gelir ile karışmaz
    assert tur_coz("Konaklama Vergisi Beyannamesi") == "KONAKLAMA"


def test_donem_bitisi():
    assert donem_bitisi({"donem": "09/2026"}) == (2026, 9)
    assert donem_bitisi({"donem": "01/2026-03/2026"}) == (2026, 3)
    assert donem_bitisi({"donem_bit": "30.09.2026"}) == (2026, 9)
    assert donem_bitisi({"donem_bit": "2026-09-30"}) == (2026, 9)
    assert donem_bitisi({"donem": "2026/09"}) == (2026, 9)
    assert donem_bitisi({"donem": "saçma"}) == (None, None)


def test_onayli_mi():
    assert onayli_mi("Onaylanmış") and onayli_mi("") and onayli_mi("Onaylandı")
    assert not onayli_mi("Onaylanmamış") and not onayli_mi("Hatalı") and not onayli_mi("Onay Bekliyor")
    assert not onayli_mi("İptal") and not onayli_mi("Red")
