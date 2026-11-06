import os
from datetime import date

import pytest

from app.cekirdek import Uygulama
from app.depo import Depo
from app.kurallar import Tatiller
from app.luca_ekran_okuma import (beyanname_satirlari, durum_sec, musteri_html_filtre, musteri_html_oku, musteri_yillari,
                                  musterileri_birlestir, secenek_esle, sorgu_plani)
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


def test_musterileri_birlestir_oncelik_ve_ayni_vkn():
    yeni = [{"ad": "ALFA", "vkn": "1", "kapanis": ""}, {"ad": "BETA", "vkn": ""}]
    eski = [{"ad": "ALFA", "vkn": "1", "kapanis": "01/01/2026"}, {"ad": "beta", "vkn": ""}, {"ad": "GAMA", "vkn": "3"}]
    s = musterileri_birlestir([yeni, eski])
    assert [m["ad"] for m in s] == ["ALFA", "BETA", "GAMA"] and s[0]["kapanis"] == ""
    # tasfiye: aynı VKN'yi taşıyan eski (kapanmış) ve yeni kayıt iki ayrı mükelleftir
    tasfiye = [{"sirket_id": "1", "ad": "FIRMA", "vkn": "7"}, {"sirket_id": "2", "ad": "FIRMA-TASFİ", "vkn": "7"}]
    assert len(musterileri_birlestir([tasfiye])) == 2
    assert len(musterileri_birlestir([[{"ad": "A", "vkn": "7"}, {"ad": "B", "vkn": "7"}]])) == 2   # kimliksiz: VKN + ad


# ---------- orkestrasyon (sahte köprü) ----------

class SahteKopru:
    def __init__(self, satirlar=None, secenekler=None, musteriler=None, **kw):
        self.cagrilar, self.kapandi = [], False
        self.satirlar = satirlar or {}
        self.secenekler = secenekler or {"Beyanname": ["KDV1", "MUHSGK", "GGECICI", "KGECICI"],
                                         "Beyanname Durum": ["Onaylanmamış", "Onaylanmış"]}
        self.musteriler = musteriler if musteriler is not None else [
            {"sirket_id": "101", "ad": "ALFA", "unvan": "ALFA LTD", "vkn": "1111111111", "acilis": "01/01/2020", "kapanis": ""},
            {"sirket_id": "102", "ad": "BETA", "unvan": "BETA AŞ", "vkn": "2222222222", "acilis": "01/01/2020", "kapanis": ""}]
        self.kw = kw

    def oturum_ac(self):
        self.cagrilar.append("giris")
        if self.kw.get("giris_hatasi"):
            raise LucaHatasi("Luca girişi yapılamadı")
        return "sayfa"

    def tani_calistir(self, page, bugun):
        self.cagrilar.append("tani")

    def musteri_listesi(self, page, yil=None, ac=True):
        self.cagrilar.append(("musteri" if yil is None else f"musteri:{yil}") + ("" if ac else ":ac-yok"))
        liste = self.musteriler if yil is None else self.kw.get("yil_listeleri", {}).get(yil, self.musteriler)
        return [dict(m) for m in liste]

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
        toplayici(SahteKopru(musteriler=[])).topla(date(2026, 11, 26))


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
    kopruler = {"ofis": SahteKopru(), "isletme": SahteKopru(musteriler=[{"sirket_id": "900", "ad": "ISL", "unvan": "ISL LTD", "vkn": "9999999999"}])}
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
        "gz": ["firma_secici_bekle"], "ml": ["musteri_listesini_ac", "yili_filtrele", "tablolari_al", "tani_kaydet"],
        "tarayici": ["tarayici_ac", "tarayiciyi_kapat"], "bekleme": ["sayfa_durulsun", "kosulu_bekle"],
    }
    eksik = [f"{mod}.{ad}" for mod, adlar in gereken.items() for ad in adlar if not hasattr(getattr(g.m, mod), ad)]
    assert not eksik, eksik
    assert g.m.ortak.AYAR["tarayici"] == "chromium" and g.m.ortak.AYAR["tarayici_sandbox"] is False


# ---------- tanı ----------

def test_tani_veri_kaydetmez_ve_tarayiciyi_kapatir():
    k = SahteKopru()
    r = toplayici(k).tani(date(2026, 11, 26))
    assert r == {"hesaplar": ["ofis"]} and "tani" in k.cagrilar and k.kapandi
    assert not any(c.startswith(("sorgu", "musteri")) for c in k.cagrilar)


def test_tani_giris_hatasini_gizlemez():
    k = SahteKopru(giris_hatasi=True)
    with pytest.raises(LucaHatasi, match="giriş"):
        toplayici(k).tani(date(2026, 11, 26))
    assert k.kapandi


def test_cekirdek_tani_sonucunu_kaydeder(tmp_path):
    k = SahteKopru()
    tg = SahteTelegram()
    u = Uygulama(Depo(tmp_path), toplayici(k), tg, CaptchaKoprusu(tg), saat=Saat("2026-11-26T09:00"))
    assert u.tani()["ok"] and u.depo.oku("durum.json")["son_tani"]["ok"] and not u.tani_suruyor
    assert not u.depo.oku("mukellefler.json")                       # veri kaydedilmedi
    k2 = SahteKopru(giris_hatasi=True)
    u2 = Uygulama(Depo(tmp_path / "b"), toplayici(k2), tg, CaptchaKoprusu(tg), saat=Saat("2026-11-26T09:00"))
    r = u2.tani()
    assert not r["ok"] and "giriş" in r["mesaj"].lower() and not u2.tani_suruyor


def test_tani_luca_disi_toplayicida_calismaz(tmp_path):
    from app.toplayici import OrnekToplayici
    tg = SahteTelegram()
    u = Uygulama(Depo(tmp_path), OrnekToplayici(), tg, CaptchaKoprusu(tg), saat=Saat("2026-11-26T09:00"))
    assert not u.tani()["ok"]


# ---------- Müşteri Listesi HTML'i (gerçek sayfanın yapısında, UYDURMA veriyle) ----------

def musteri_sayfasi(satirlar, toplam=None):
    """Luca listSirketAction.do sayfasının satır/hücre yapısını taklit eder (sınıf adları gerçek sayfadan)."""
    govde = ""
    for i, (sid, kisa, uzun, vd, vn, tc, acik, kur, kap) in enumerate(satirlar):
        govde += f"""
     <tr style="cursor:pointer;" class="satir form_Metin_0{1 + i % 2}"
        ondblclick="gonder('guncelle')"
        onclick="sec(this, '{sid}',
                           '{kisa}',
                           '468234458',
                           '110568073',
                           '');">
      <td class="check-td checks"><input type="checkbox" do-not-set-null="true" name='sirket_id' array='true' class="check" value="{sid}"></td>
      <td class="kisa-ad-td">
            {kisa}
      </td>
      <td class="uzun-ad-td">
            {uzun}
      </td>
      <td class="vergi-dairesi-td">
            {vd}
      </td>
      <td class="vergi-no-td">
            {vn}
      </td>
      <td class="tc-kimlik-no-td">
            {tc}
      </td>
      <td class="aciklama-td">
            {acik}
      </td>
       <td class="kurulus-tarihi-td">
            {kur}
      </td>
       <td class="kapanis-tarihi-td">
            {kap}
      </td>
    </tr>"""
    toplam = len(satirlar) if toplam is None else toplam
    return f"""<html><head><script>var __SESSION = {{"SIRKET_ID": "999"}}</script></head><body>
    <table class="table-header"><tr><td class='checks'><input type="checkbox"></td><td>Kısa Adı</td><td>Uzun Adı</td><td>Vergi Dairesi</td></tr></table>
    <DIV id="scroll"><table class='data-table'>{govde}</table></DIV>
    <script type="text/javascript">lucaNotYaz("Kayıt Sayısı: {toplam}", "info");</script></body></html>"""


SATIRLAR = [
    ("1001", "ALFA", "ALFA TİCARET LTD. ŞTİ.", "ÜMRANİYE VERGİ DAİRESİ", "1111111111", "", "", "01/01/2020", ""),
    ("1002", "BETA ŞAHIS", "BETA ŞAHIS", "ÜSKÜDAR VERGİ DAİRESİ", "2222222222", "30000000001", "GENÇ GİRİŞİM", "12/08/2024", "31/08/2026"),
    ("1003", "GAMA", "GAMA   LTD  &amp; ORTAKLARI", "KARTAL VERGİ DAİRESİ", "", "30000000002", "", "01/01/2021", "31/12/2021"),
    ("1004", "TASFİYE-ESKİ", "ESKİ LTD", "SARIYER VERGİ DAİRESİ", "7777777777", "", "", "22/04/2022", "04/05/2026"),
    ("1005", "TASFİYE-YENİ", "TAS.HAL.ESKİ LTD", "SARIYER VERGİ DAİRESİ", "7777777777", "", "", "04/05/2026", ""),
]


def test_musteri_html_okuma():
    kayitlar, toplam = musteri_html_oku(musteri_sayfasi(SATIRLAR))
    assert toplam == 5 and len(kayitlar) == 5
    a, b, g = kayitlar[0], kayitlar[1], kayitlar[2]
    assert a == {"sirket_id": "1001", "ad": "ALFA", "unvan": "ALFA TİCARET LTD. ŞTİ.", "vergi_dairesi": "ÜMRANİYE VERGİ DAİRESİ",
                 "vkn": "1111111111", "tc": "", "aciklama": "", "acilis": "01/01/2020", "kapanis": ""}
    assert b["tc"] == "30000000001" and b["aciklama"] == "GENÇ GİRİŞİM" and b["kapanis"] == "31/08/2026"
    assert g["vkn"] == "" and g["unvan"] == "GAMA LTD & ORTAKLARI"          # boşluklar sadeleşir, &amp; çözülür
    assert [k["sirket_id"] for k in kayitlar] == ["1001", "1002", "1003", "1004", "1005"]


def test_musteri_html_sayi_uyusmazligi_ve_bos():
    kayitlar, toplam = musteri_html_oku(musteri_sayfasi(SATIRLAR, toplam=7))
    assert toplam == 7 and len(kayitlar) == 5                                # köprü bunu hata sayar
    assert musteri_html_oku("<html><body>başka sayfa</body></html>") == ([], None)
    assert musteri_html_oku("") == ([], None)


def test_musteri_html_den_mukellef_ve_ayni_vkn_iki_firma(tmp_path):
    from app.kontrol import mukellef_normalize
    kayitlar, _ = musteri_html_oku(musteri_sayfasi(SATIRLAR))
    mus = [mukellef_normalize(k, "ofis") for k in kayitlar]
    assert len({m["id"] for m in mus}) == 5                                  # aynı VKN'li iki tasfiye kaydı ayrı kimlik
    assert mus[0]["id"] == "ofis:1001" and mus[0]["acilis"] == "2020-01-01" and mus[1]["kapanis"] == "2026-08-31"
    assert mus[2]["vkn"] == "30000000002"                                    # VKN yoksa TC kullanılır


def test_gercek_toplayici_musteri_listesi_sayfadan_okur_ve_sayiyi_dogrular(tmp_path):
    """GercekLucabot.musteri_listesi, lucabot'un ekran açma/bekleme çağrıları sahte iken HTML'den doğru okur."""
    from types import SimpleNamespace
    g = GercekLucabot.__new__(GercekLucabot)
    g.log, g.tani_klasoru = tmp_path / "log.txt", tmp_path
    html = {"v": musteri_sayfasi(SATIRLAR)}
    cerceve = SimpleNamespace(content=lambda: html["v"])
    g.m = SimpleNamespace(
        ml=SimpleNamespace(musteri_listesini_ac=lambda page, log: None, tani_kaydet=lambda *a, **k: None),
        le=SimpleNamespace(cerceveler=lambda page: [cerceve]),
        bekleme=SimpleNamespace(kosulu_bekle=lambda page, f, ms, aralik_ms=0: f()))
    assert len(g.musteri_listesi("sayfa")) == 5
    html["v"] = musteri_sayfasi(SATIRLAR, toplam=9)
    with pytest.raises(LucaHatasi, match="9 kayıt"):
        g.musteri_listesi("sayfa")
    html["v"] = "<html></html>"
    with pytest.raises(LucaHatasi, match="tablosu bulunamadı"):
        g.musteri_listesi("sayfa")


# ---------- yıl filtresi ----------

def test_musteri_yillari():
    assert musteri_yillari(date(2026, 11, 6)) == [2026]
    assert musteri_yillari(date(2027, 1, 14)) == [2027]                  # geçmiş yıl okunmaz (Ocak dahil)
    assert musteri_yillari(date(2026, 11, 6), "yok") == [] and musteri_yillari(date(2026, 11, 6), "otomatik") == [2026]
    assert musteri_yillari(date(2026, 11, 6), "2026, 2025") == [2026, 2025]


def test_musteri_html_filtre_durumu():
    filtresiz = musteri_sayfasi(SATIRLAR)
    assert musteri_html_filtre(filtresiz) == {"yil": None, "durum": None, "sinif": None}
    filtreli = filtresiz.replace("</body>", '<script>byId("YIL").value = "2026";\n byId("DURUM").value = "";\n byId("SINIF").value = "";</script></body>')
    assert musteri_html_filtre(filtreli) == {"yil": "2026", "durum": "", "sinif": ""}


def test_yil_filtresi_varsayilan():
    firmalar = [{"sirket_id": "1", "ad": "AKTIF", "unvan": "AKTIF", "vkn": "1", "acilis": "01/01/2020", "kapanis": ""},
                {"sirket_id": "2", "ad": "DONEMSIZ", "unvan": "DONEMSIZ", "vkn": "2", "acilis": "01/01/2020", "kapanis": ""}]
    k = SahteKopru(musteriler=firmalar, yil_listeleri={2026: [firmalar[0]]})
    r = toplayici(k).topla(date(2026, 11, 26))
    assert [c for c in k.cagrilar if c.startswith("musteri")] == ["musteri:2026"]          # filtresiz okuma yok
    assert [m["ad"] for m in r["mukellefler"]] == ["AKTIF"] and r["uyarilar"] == []


def test_acik_yil_listesi_iki_yil_birlestirir():
    a = {"sirket_id": "1", "ad": "A", "unvan": "A", "vkn": "1", "acilis": "01/01/2020", "kapanis": ""}
    b = {"sirket_id": "2", "ad": "B", "unvan": "B", "vkn": "2", "acilis": "01/01/2020", "kapanis": ""}
    k = SahteKopru(musteriler=[a, b], yil_listeleri={2027: [a], 2026: [a, b]})
    r = toplayici(k, {"LUCA_MUSTERI_YILI": "2027,2026"}).topla(date(2027, 1, 14))        # isteğe bağlı açık liste
    assert {m["ad"] for m in r["mukellefler"]} == {"A", "B"}
    assert [c for c in k.cagrilar if c.startswith("musteri")] == ["musteri:2027", "musteri:2026:ac-yok"]   # ekran bir kez açılır


def test_yil_filtresi_kapali_ve_bos_filtre_sonucu():
    k = SahteKopru()
    r = toplayici(k, {"LUCA_MUSTERI_YILI": "yok"}).topla(date(2026, 11, 26))
    assert [c for c in k.cagrilar if c.startswith("musteri")] == ["musteri"]
    with pytest.raises(LucaHatasi, match="boş"):
        toplayici(SahteKopru(yil_listeleri={2026: []})).topla(date(2026, 11, 26))


def test_koprude_yil_filtresi_dogrulamasi(tmp_path):
    """Filtre uygulanmadan önceki eski sayfa okunmamalı: sayfa uygulanan yılı kendisi yazar."""
    from types import SimpleNamespace
    g = GercekLucabot.__new__(GercekLucabot)
    g.log, g.tani_klasoru = tmp_path / "log.txt", tmp_path
    filtresiz = musteri_sayfasi(SATIRLAR)
    filtreli = musteri_sayfasi(SATIRLAR[:2]).replace("</body>", '<script>byId("YIL").value = "2026";</script></body>')
    durum = {"html": filtresiz, "uygulandi": True}
    g.m = SimpleNamespace(
        ml=SimpleNamespace(yili_filtrele=lambda page, yil, log: durum["uygulandi"], tani_kaydet=lambda *a, **k: None),
        le=SimpleNamespace(cerceveler=lambda page: [SimpleNamespace(content=lambda: durum["html"])]),
        bekleme=SimpleNamespace(kosulu_bekle=lambda page, f, ms, aralik_ms=0: f()))
    with pytest.raises(LucaHatasi, match="hâlâ filtresiz"):                  # filtre sayfaya yansımadı: eski sayfa kabul edilmez
        g.musteri_listesi("sayfa", 2026, ac=False)
    durum["html"] = filtreli
    assert len(g.musteri_listesi("sayfa", 2026, ac=False)) == 2
    with pytest.raises(LucaHatasi, match="Yıl=2025"):                        # istenen yıl ile sayfadaki yıl uyuşmuyor
        g.musteri_listesi("sayfa", 2025, ac=False)
    durum["uygulandi"] = False
    with pytest.raises(LucaHatasi, match="uygulanamadı"):
        g.musteri_listesi("sayfa", 2026, ac=False)
