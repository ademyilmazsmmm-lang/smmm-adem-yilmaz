import os
from datetime import date

import pytest

from app.cekirdek import Uygulama
from app.depo import Depo
from app.kurallar import Tatiller
from app.luca_ekran_okuma import (beyanname_satirlari, durum_sec, musterileri_birlestir, secenek_esle, sorgu_plani)
from app.luca_toplayici import GercekLucabot, LucaHatasi, LucaToplayici, kimlik_oku
from tests.test_cekirdek import Saat, SahteTelegram
from app.bildirim import CaptchaKoprusu

T = Tatiller()


# ---------- saf fonksiyonlar ----------

def test_sorgu_plani_kasim():
    p = sorgu_plani(date(2026, 11, 26), T)
    assert [(x["tur"], x["yil"], x["ay"]) for x in p] == [
        ("GECICI", 2026, 9), ("KDV1", 2026, 10), ("MPHB", 2026, 10), ("KDV1", 2026, 11), ("MPHB", 2026, 11)]
    assert all(x["sorgu_ay"] == x["ay"] for x in p)


def test_sorgu_plani_ucaylik_bas_modu_ve_yil_atlama():
    p = sorgu_plani(date(2026, 11, 26), T, ucaylik_ay="bas")
    g = next(x for x in p if x["tur"] == "GECICI")
    assert (g["yil"], g["ay"], g["sorgu_yil"], g["sorgu_ay"]) == (2026, 9, 2026, 7)     # kıyas dönem sonu 9, sorgu ayı 7
    ocak = sorgu_plani(date(2027, 1, 20), T)                                              # 4. dönem geçici + aralık KDV/MUHSGK
    assert [(x["tur"], x["yil"], x["ay"]) for x in ocak] == [("GECICI", 2026, 12), ("KDV1", 2026, 12), ("MPHB", 2026, 12)]
    ocak_bas = sorgu_plani(date(2027, 1, 20), T, ucaylik_ay="bas")
    assert (ocak_bas[0]["sorgu_yil"], ocak_bas[0]["sorgu_ay"]) == (2026, 10)


def test_secenek_esle_ve_durum_sec():
    s = ["Seçiniz", "KDV1", "KDV2", "MUHSGK", "GGECICI", "KGECICI", "Kurumlar"]
    assert secenek_esle(s, "KDV1") == ["KDV1"] and secenek_esle(s, "MPHB") == ["MUHSGK"]
    assert secenek_esle(s, "GECICI") == ["GGECICI", "KGECICI"]
    assert durum_sec(["Seçiniz", "Onaylanmamış", "Onaylanmış", "Hatalı"]) == "Onaylanmış"
    assert durum_sec(["Onaylandı", "Hatalı"]) == "Onaylandı"
    assert durum_sec(["Hatalı", "Onay Bekliyor"]) is None


BASLIK = ["", "Sıra", "Mükellef Adı", "VKN", "Beyanname", "Dönem", "Durum"]


def test_tablo_ayni_tabloda_baslik_ve_kayma():
    tablo = [BASLIK[1:], ["", "1", "ALFA LTD", "111-111-1111", "KDV1", "10/2026", "Onaylanmış"],
             ["", "2", "BETA AŞ", "22222222222", "KDV1", "10/2026", "Onaylanmış"],
             ["", "", "Toplam", "", "", "", ""]]
    # başlık 6 hücre, veri 7 (baştaki onay kutusu): 1 sütun kayma
    assert beyanname_satirlari([tablo]) == [{"firma": "ALFA LTD", "vkn": "1111111111"},
                                            {"firma": "BETA AŞ", "vkn": "22222222222"}]


def test_tablo_baslik_ayri_tabloda_ve_vknsiz():
    baslik = [["Mükellef Adı", "Beyanname", "Dönem"]]
    veri = [["ALFA LTD", "KDV1", "10/2026"], ["BETA AŞ", "KDV1", "10/2026"]]
    assert beyanname_satirlari([[["Menü"], ["Çıkış"]], baslik, veri]) == [
        {"firma": "ALFA LTD", "vkn": ""}, {"firma": "BETA AŞ", "vkn": ""}]


def test_tablo_baslik_yoksa_none():
    assert beyanname_satirlari([[["a", "b"], ["c", "d"]]]) is None
    assert beyanname_satirlari([]) is None


def test_musterileri_birlestir_yeni_yil_kazanir():
    yeni = [{"ad": "ALFA", "vkn": "1", "kapanis": ""}, {"ad": "BETA", "vkn": ""}]
    eski = [{"ad": "ALFA", "vkn": "1", "kapanis": "01/01/2026"}, {"ad": "beta", "vkn": ""}, {"ad": "GAMA", "vkn": "3"}]
    s = musterileri_birlestir([yeni, eski])
    assert [m["ad"] for m in s] == ["ALFA", "BETA", "GAMA"] and s[0]["kapanis"] == ""


# ---------- orkestrasyon (sahte köprü) ----------

class SahteKopru:
    def __init__(self, satirlar=None, secenekler=None, musteriler=None, **kw):
        self.cagrilar, self.kapandi = [], False
        self.satirlar = satirlar or {}
        self.secenekler = secenekler or {"Beyanname": ["KDV1", "MUHSGK", "GGECICI", "KGECICI"],
                                         "Beyanname Durum": ["Onaylanmamış", "Onaylanmış"]}
        self.musteriler = musteriler or {2026: [{"ad": "ALFA", "unvan": "ALFA LTD", "vkn": "1111111111", "acilis": "01/01/2020", "kapanis": ""},
                                                {"ad": "BETA", "unvan": "BETA AŞ", "vkn": "2222222222", "acilis": "01/01/2020", "kapanis": ""}]}
        self.kw = kw

    def oturum_ac(self):
        self.cagrilar.append("giris")
        if self.kw.get("giris_hatasi"):
            raise LucaHatasi("Luca girişi yapılamadı")
        return "sayfa"

    def tani_calistir(self, page, bugun):
        self.cagrilar.append("tani")

    def musteri_listesi(self, page, yil):
        self.cagrilar.append(f"musteri:{yil}")
        if yil not in self.musteriler:
            raise LucaHatasi("liste yok")
        return [dict(m) for m in self.musteriler[yil]]

    def beyanname_ekrani_ac(self, page, yil):
        self.cagrilar.append(f"ekran:{yil}")
        return "ekran"

    def filtre_secenekleri(self, ekran):
        return self.secenekler

    def sorgula(self, ekran, ay, yil, tur, durum):
        self.cagrilar.append(f"sorgu:{tur}:{ay:02d}/{yil}")
        satirlar = self.satirlar.get((tur, ay, yil), [])
        n = self.kw.get("n_zorla", len(satirlar))
        tablo = [["Mükellef Adı", "VKN"]] + [[s, ""] for s in satirlar] if satirlar else ([["Mükellef Adı", "VKN"]] if not self.kw.get("baslik_yok") else [["x"]])
        return n, [tablo]

    def kapat(self):
        self.kapandi = True


def toplayici(kopru, env=None):
    e = {"LUCA_UYE_NO": "1", "LUCA_KULLANICI": "u", "LUCA_PAROLA": "p"}
    e.update(env or {})
    return LucaToplayici("/tmp/x", env=e, kopru_fabrikasi=lambda h, k, c: kopru, tatil=T)


def test_akis_kayitlari_uretir():
    k = SahteKopru(satirlar={("KDV1", 10, 2026): ["ALFA LTD"], ("MUHSGK", 10, 2026): ["ALFA LTD", "BETA AŞ"],
                             ("GGECICI", 9, 2026): ["BETA AŞ"]})
    r = toplayici(k).topla(date(2026, 11, 26))
    assert k.kapandi and k.cagrilar[0] == "giris"
    d = {(b["firma"], b["tur"], b["donem"], b["durum"]) for b in r["beyannameler"]}
    assert ("ALFA LTD", "KDV1", "10/2026", "Onaylanmış") in d and ("BETA AŞ", "GGECICI", "09/2026", "Onaylanmış") in d
    assert ("BETA AŞ", "KDV1", "10/2026", "Onaylanmış") not in d
    # geçici hem GGECICI hem KGECICI seçeneğiyle sorgulanır
    assert "sorgu:KGECICI:09/2026" in k.cagrilar and "sorgu:GGECICI:09/2026" in k.cagrilar
    assert {m["hesap"] for m in r["mukellefler"]} == {"ofis"} and r["hesaplar"]["ofis"] == {"mukellef": 2, "beyanname": 4}
    assert any("liste yok" in u for u in r["uyarilar"])          # 2025 listesi yoktu: uyarı, hata değil


def test_hata_olsa_da_tarayici_kapanir():
    k = SahteKopru(giris_hatasi=True)
    with pytest.raises(LucaHatasi):
        toplayici(k).topla(date(2026, 11, 26))
    assert k.kapandi


def test_eksik_tur_secenegi_durdurur():
    k = SahteKopru(secenekler={"Beyanname": ["KDV1"], "Beyanname Durum": ["Onaylanmış"]})
    with pytest.raises(LucaHatasi, match="türüne uyan seçenek yok"):
        toplayici(k).topla(date(2026, 11, 26))


def test_onayli_durum_yoksa_durdurur():
    k = SahteKopru(secenekler={"Beyanname": ["KDV1", "MUHSGK", "GGECICI"], "Beyanname Durum": ["Hatalı"]})
    with pytest.raises(LucaHatasi, match="onaylanmış"):
        toplayici(k).topla(date(2026, 11, 26))


def test_bos_musteri_listesi_durdurur():
    with pytest.raises(LucaHatasi, match="boş"):
        toplayici(SahteKopru(musteriler={2026: []})).topla(date(2026, 11, 26))


def test_sayi_uyusmazligi_uyari_olur():
    k = SahteKopru(satirlar={("KDV1", 10, 2026): ["ALFA LTD"]}, n_zorla=7)
    r = toplayici(k).topla(date(2026, 11, 26))
    assert any("7 kayıt var" in u and "sayfalı" in u for u in r["uyarilar"])


def test_kayit_var_ama_sutun_okunamadiysa_durdurur():
    with pytest.raises(LucaHatasi, match="Mükellef Adı"):
        toplayici(SahteKopru(baslik_yok=True, n_zorla=3)).topla(date(2026, 11, 26))


def test_sifir_kayit_gecerlidir():
    r = toplayici(SahteKopru(baslik_yok=True, n_zorla=0)).topla(date(2026, 11, 26))
    assert r["beyannameler"] == []


def test_tani_modu_veri_kaydetmez():
    k = SahteKopru()
    with pytest.raises(LucaHatasi, match="Tanı modu"):
        toplayici(k, {"LUCA_TANI": "1"}).topla(date(2026, 11, 26))
    assert "tani" in k.cagrilar and k.kapandi and not any(c.startswith("sorgu") for c in k.cagrilar)


def test_kimlik_okuma():
    assert kimlik_oku({"LUCA_UYE_NO": "1", "LUCA_KULLANICI": "u", "LUCA_PAROLA": "p"}, "ofis", True)["parola"] == "p"
    env = {"LUCA_OFIS_UYE_NO": "1", "LUCA_OFIS_KULLANICI": "u", "LUCA_OFIS_PAROLA": "p1",
           "LUCA_ISLETME_UYE_NO": "2", "LUCA_ISLETME_KULLANICI": "v", "LUCA_ISLETME_PAROLA": "p2", "LUCA_PAROLA": "genel"}
    assert kimlik_oku(env, "ofis", False)["parola"] == "p1" and kimlik_oku(env, "isletme", False)["parola"] == "p2"
    with pytest.raises(LucaHatasi, match="parola") as e:
        kimlik_oku({"LUCA_UYE_NO": "1", "LUCA_KULLANICI": "u"}, "ofis", True)
    assert "genel" not in str(e.value)                            # hata metni değer içermez


def test_iki_hesap_ayri_islenir():
    kopruler = {"ofis": SahteKopru(), "isletme": SahteKopru(musteriler={2026: [{"ad": "ISL", "unvan": "ISL LTD", "vkn": "9999999999"}]})}
    env = {"LUCA_HESAPLAR": "ofis,isletme", **{f"LUCA_{h.upper()}_{a}": "x" for h in kopruler for a in ("UYE_NO", "KULLANICI", "PAROLA")}}
    t = LucaToplayici("/tmp/x", env=env, kopru_fabrikasi=lambda h, k, c: kopruler[h], tatil=T)
    r = t.topla(date(2026, 11, 26))
    assert {m["hesap"] for m in r["mukellefler"]} == {"ofis", "isletme"} and all(k.kapandi for k in kopruler.values())


def test_cekirdekle_butunlesme_ve_eslesmeyen_uyarisi(tmp_path):
    k = SahteKopru(satirlar={("KDV1", 10, 2026): ["ALFA LTD", "BILINMEYEN FIRMA"], ("MUHSGK", 10, 2026): ["ALFA LTD"]})
    tg = SahteTelegram()
    u = Uygulama(Depo(tmp_path), toplayici(k), tg, CaptchaKoprusu(tg), saat=Saat("2026-11-26T09:00"))
    r = u.topla()
    assert r["ok"] and any("hiçbir mükellefle eşleşmedi" in x and "BILINMEYEN FIRMA" in x for x in r["uyarilar"])
    d = {(x.ad, x.tur): x.durum for x in u.maddeler() if x.donem == "2026-10"}
    assert d[("ALFA", "KDV1")] == "verildi" and d[("BETA", "KDV1")] == "eksik" and d[("BETA", "MPHB")] == "eksik"
    u.slot_calistir("09:00")
    assert any("eşleşmedi" in m for m in tg.mesajlar)


# ---------- gerçek köprü: yalnızca içe aktarma/uyum ----------

def test_lucabot_yoksa_anlasilir_hata(tmp_path, monkeypatch):
    monkeypatch.delitem(__import__("sys").modules, "lucabot", raising=False)
    with pytest.raises(LucaHatasi, match="LUCABOT_YOLU"):
        GercekLucabot(tmp_path, "ofis", {}, None, env={})


@pytest.mark.skipif(not os.environ.get("LUCABOT_YOLU"), reason="lucabot paketi yok (LUCABOT_YOLU tanımlı değil)")
def test_gercek_lucabot_arayuzu_uyumlu(tmp_path):
    """Dijital Stajyer'in lucabot paketinde köprünün çağırdığı ad ve alanlar var mı?"""
    g = GercekLucabot(tmp_path, "ofis", {"uye_no": "1"}, None, env=os.environ)
    gereken = {
        "giris": ["luca_oturumu_ac"],
        "lb": ["menusu_olan_firmayi_sec", "ekrani_ac", "ARAMA_PENCERESI", "ALANLAR_JS", "_secenek_sec", "_tarih_yaz",
               "bildirim_sayisi", "listelenen_sayi", "LISTELE_DUGMESI", "AYLAR"],
        "le": ["gorunur_mu", "dugmeye_bas", "cerceveler", "acik_pencereleri_kapat"],
        "gz": ["firma_secici_bekle"], "ml": ["listeyi_oku", "tablolari_al", "tani_kaydet"],
        "tarayici": ["tarayici_ac", "tarayiciyi_kapat"], "bekleme": ["sayfa_durulsun"],
    }
    eksik = [f"{mod}.{ad}" for mod, adlar in gereken.items() for ad in adlar if not hasattr(getattr(g.m, mod), ad)]
    assert not eksik, eksik
    assert g.m.ortak.AYAR["tarayici"] == "chromium" and g.m.ortak.AYAR["tarayici_sandbox"] is False
