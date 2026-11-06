import os
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest

from app.bildirim import CaptchaKoprusu
from app.cekirdek import Uygulama
from app.depo import Depo
from app.kontrol import degerlendir, mukellef_normalize
from app.kurallar import Tatiller, onayli_mi
from app.luca_ekran_okuma import (beyanname_json_kayitlari, musteri_html_filtre, musteri_html_oku, musteri_yillari,
                                  musterileri_birlestir, yukleme_araligi)
from app.luca_toplayici import GercekLucabot, LucaHatasi, LucaToplayici, kimlik_oku
from tests.test_cekirdek import Saat, SahteTelegram

T = Tatiller()

# ================= Beyanname Takip JSON'u (gerçek yanıtın alan yapısı, UYDURMA veriyle) =================

DURUM_AD = {2: "Onaylanmış", 0: "Hatalı", 3: "İptal Edilmiş"}


def bey_kaydi(kisa, unvan, vkn, kod, bas, bit, durum=2, tckn=0):
    r = {"paketOid": "p1", "yuklemeZamani": "28/10/2026 21:03:30", "paketDurum": 3, "paketDurumAciklama": "Kontrol Edildi",
         "beyanId": 1, "beyanDurum": durum, "beyanDurumAciklama": DURUM_AD.get(durum, ""), "tckn": tckn, "vkn": vkn,
         "mesajVar": 0, "beyannameTanimOid": f"{kod}_45", "mukellefAdi": unvan, "onaylanabilir": "F",
         "beyanDonem": f"{bit[4:8]}/{bit[2:4]}", "beyannameKodu": kod, "donemBas": bas, "donemBit": bit, "sirketKisaAd": kisa}
    if bas[2:4] != bit[2:4]:                                                       # üç aylık: 2026/07-09
        r["beyanDonem"] = f"{bit[4:8]}/{bas[2:4]}-{bit[2:4]}"
    return r


def cevap_json(kayitlar, toplam=None):
    n = len(kayitlar) if toplam is None else toplam
    return {"success": f"{n} adet beyanname kaydı listelendi.", "data": kayitlar}


EKIM = ("01102026", "31102026")
EYLUL = ("01092026", "30092026")
Q3 = ("01072026", "30092026")


def test_json_kayitlari_alanlar_ve_donem():
    cevap = cevap_json([
        bey_kaydi("ALFA", "ALFA LTD", "1111111111", "KDV1", *EKIM),
        bey_kaydi("BETA", "BETA AŞ", "2222222222", "KGECICI", *Q3),
        bey_kaydi("GAMA", "GAMA", "3333333333", "MUHSGK", *Q3, durum=0, tckn=30000000001),
        bey_kaydi("DELTA", "DELTA", "4444444444", "KDV1", *EYLUL, durum=3)])
    k, toplam = beyanname_json_kayitlari(cevap)
    assert toplam == 4 and [x["tur"] for x in k] == ["KDV1", "KGECICI", "MUHSGK", "KDV1"]
    assert [x["donem"] for x in k] == ["10/2026", "09/2026", "09/2026", "09/2026"]          # 3 aylıkta dönem BİTİŞİ
    assert [x["durum"] for x in k] == ["Onaylanmış", "Onaylanmış", "Hatalı", "İptal Edilmiş"]
    assert k[0]["kisa_ad"] == "ALFA" and k[0]["tckn"] == "" and k[2]["tckn"] == "30000000001"   # tckn 0 -> boş


def test_json_sgk_alanlari():
    r = bey_kaydi("A", "A", "1111111111", "MUHSGK", *EKIM)
    r["ebildirgeSayisi"], r["muhSgkDurum"] = 2, "2"
    k, _ = beyanname_json_kayitlari(cevap_json([r, bey_kaydi("B", "B", "2222222222", "KDV1", *EKIM)]))
    assert (k[0]["ebildirge"], k[0]["sgk_durum"]) == (2, "2") and (k[1]["ebildirge"], k[1]["sgk_durum"]) == (None, "")


def test_json_durum_kodundan_ve_donem_yedeginden():
    r = bey_kaydi("A", "A", "1111111111", "KDV1", *EKIM)
    r["beyanDurumAciklama"] = ""
    r["donemBit"] = ""                                                        # dönem bitişi yoksa beyanDonem kullanılır
    k, _ = beyanname_json_kayitlari(cevap_json([r]))
    assert k[0]["durum"] == "Onaylanmış" and k[0]["donem"] == "2026/10"
    r["beyanDurum"] = 7
    assert beyanname_json_kayitlari(cevap_json([r]))[0][0]["durum"] == "Bilinmeyen durum (7)"


def test_json_bozuk_yanit():
    with pytest.raises(ValueError):
        beyanname_json_kayitlari({"success": "hata"})
    assert beyanname_json_kayitlari({"success": "0 adet beyanname kaydı listelendi.", "data": []}) == ([], 0)


def test_onayli_mi_tanimsiz_durum_onayli_sayilmaz():
    assert onayli_mi("Onaylanmış") and onayli_mi("") and not onayli_mi("İptal Edilmiş") and not onayli_mi("Hatalı")
    assert not onayli_mi("Bilinmeyen durum (7)") and not onayli_mi("Gönderildi")


def test_yukleme_araligi():
    assert yukleme_araligi(date(2026, 11, 6), T) == (date(2026, 9, 27), date(2026, 11, 6))   # en eski dönem bitişi 30 Eylül - 3 gün
    assert yukleme_araligi(date(2026, 12, 29), T)[0] > date(2026, 9, 27)                        # geçmiş dönemler pencereden çıkınca ilerler


def mus(ad, vkn, sid):
    return mukellef_normalize({"sirket_id": sid, "ad": ad, "unvan": ad + " LTD", "vkn": vkn, "acilis": "01/01/2020", "kapanis": ""}, "ofis")


def test_eslesme_vkn_kisa_ad_ve_durumlar():
    ml = [mus("ALFA", "1111111111", "1"), mus("BETA", "2222222222", "2"), mus("GAMA", "3333333333", "3"),
          mus("DELTA", "4444444444", "4"), mus("EPSILON", "", "5")]
    kayit = [bey_kaydi("ALFA", "ALFA TİCARET", "1111111111", "KDV1", *EKIM),                    # verildi (VKN)
             bey_kaydi("BETA", "BETA", "2222222222", "KDV1", *EKIM, durum=0),                   # yalnızca hatalı -> onaysız
             bey_kaydi("GAMA", "GAMA", "3333333333", "KDV1", *EKIM, durum=3),                   # iptal + hatalı -> onaysız
             bey_kaydi("GAMA", "GAMA", "3333333333", "KDV1", *EKIM, durum=0),
             bey_kaydi("DELTA", "DELTA", "4444444444", "KDV1", *EKIM, durum=0),                 # hatalı, sonra onaylı -> verildi
             bey_kaydi("DELTA", "DELTA", "4444444444", "KDV1", *EKIM, durum=2),
             bey_kaydi("EPSILON", "BAŞKA UNVAN", "", "KDV1", *EKIM)]                            # VKN yok: kısa ad ile
    kayit, _ = beyanname_json_kayitlari(cevap_json(kayit))
    d = {x.ad: x.durum for x in degerlendir(ml, {}, kayit, date(2026, 11, 26), T) if x.tur == "KDV1" and x.donem == "2026-10"}
    assert d == {"ALFA": "verildi", "BETA": "onaysiz", "GAMA": "onaysiz", "DELTA": "verildi", "EPSILON": "verildi"}


def test_eslesme_tckn_ve_ayni_vkn_tasfiye():
    ml = [mus("SAHIS", "30000000001", "1")]                                  # Luca'da yalnızca TC var (VKN boş -> TC)
    k, _ = beyanname_json_kayitlari(cevap_json([bey_kaydi("SAHIS", "SAHIS", "9999999999", "KDV1", *EKIM, tckn=30000000001)]))
    d = [x.durum for x in degerlendir(ml, {}, k, date(2026, 11, 26), T) if x.tur == "KDV1" and x.donem == "2026-10"]
    assert d == ["verildi"]
    # tasfiye: eski (kapanmış) ve yeni kayıt aynı VKN'yi taşır; beyanname eski kısa adla gelse de yeni kayıt da verilmiş görünür
    ml2 = [mus("ESKI", "7777777777", "1"), mus("YENI-TASFI", "7777777777", "2")]
    k2, _ = beyanname_json_kayitlari(cevap_json([bey_kaydi("ESKI", "TAS.HAL. ESKI", "7777777777", "KDV1", *EKIM)]))
    assert {x.ad: x.durum for x in degerlendir(ml2, {}, k2, date(2026, 11, 26), T) if x.tur == "KDV1" and x.donem == "2026-10"} == {
        "ESKI": "verildi", "YENI-TASFI": "verildi"}


def test_ucaylik_muhsgk_ve_gecici_donem_bitisiyle_eslesir():
    ml = [mus("ALFA", "1111111111", "1")]
    ayar = {"mukellef": {"ofis:1": {"KDV1": "yok", "MPHB": "3aylik", "GECICI": "3aylik", "onayli": True}}}
    k, _ = beyanname_json_kayitlari(cevap_json([bey_kaydi("ALFA", "ALFA", "1111111111", "KGECICI", *Q3),
                                                bey_kaydi("ALFA", "ALFA", "1111111111", "MUHSGK", *Q3)]))
    d = {x.tur: x.durum for x in degerlendir(ml, ayar, k, date(2026, 10, 20), T)}   # 26 Ekim MUHSGK, geçici 17 Kasım
    assert d == {"MPHB": "verildi", "GECICI": "verildi"}


# ================= orkestrasyon (sahte köprü) =================

class SahteKopru:
    def __init__(self, cevap=None, musteriler=None, **kw):
        self.cagrilar, self.kapandi, self.kw = [], False, kw
        self.cevap = cevap if cevap is not None else cevap_json([])
        self.musteriler = musteriler if musteriler is not None else [
            {"sirket_id": "101", "ad": "ALFA", "unvan": "ALFA LTD", "vkn": "1111111111", "acilis": "01/01/2020", "kapanis": ""},
            {"sirket_id": "102", "ad": "BETA", "unvan": "BETA AŞ", "vkn": "2222222222", "acilis": "01/01/2020", "kapanis": ""}]
        self.aralik = None

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

    def gib_getir(self, ekran):
        self.cagrilar.append("gib-getir")
        if self.kw.get("gib_hatasi"):
            raise LucaHatasi("180 sn içinde bitmedi")

    def beyanname_listele(self, ekran, bas, bit):
        self.cagrilar.append("listele")
        self.aralik = (bas, bit)
        return self.cevap

    def kapat(self):
        self.kapandi = True


def toplayici(kopru, env=None):
    e = {"LUCA_UYE_NO": "1", "LUCA_KULLANICI": "u", "LUCA_PAROLA": "p"}
    e.update(env or {})
    return LucaToplayici("/tmp/x", env=e, kopru_fabrikasi=lambda h, k, c: kopru, tatil=T)


def test_akis_sirasi_ve_kayitlar():
    cevap = cevap_json([bey_kaydi("ALFA", "ALFA LTD", "1111111111", "KDV1", *EKIM),
                        bey_kaydi("BETA", "BETA AŞ", "2222222222", "MUHSGK", *EKIM)])
    k = SahteKopru(cevap)
    r = toplayici(k).topla(date(2026, 11, 26))
    assert k.cagrilar == ["giris", "musteri:2026", "ekran:2026", "gib-getir", "listele"]
    assert k.aralik == (date(2026, 9, 27), date(2026, 11, 26)) and k.kapandi
    assert [(b["firma"], b["tur"], b["donem"], b["durum"], b["hesap"]) for b in r["beyannameler"]] == [
        ("ALFA LTD", "KDV1", "10/2026", "Onaylanmış", "ofis"), ("BETA AŞ", "MUHSGK", "10/2026", "Onaylanmış", "ofis")]
    assert r["hesaplar"]["ofis"] == {"mukellef": 2, "beyanname": 2} and r["uyarilar"] == []


def test_gib_getir_calismazsa_uyari_ile_devam_eder():
    k = SahteKopru(gib_hatasi=True)
    r = toplayici(k).topla(date(2026, 11, 26))
    assert "listele" in k.cagrilar
    assert len(r["uyarilar"]) == 1 and "güncel olmayabilir" in r["uyarilar"][0] and "180 sn" in r["uyarilar"][0]


def test_gib_getir_kapatilabilir():
    k = SahteKopru()
    toplayici(k, {"LUCA_GIB_GETIR": "0"}).topla(date(2026, 11, 26))
    assert "gib-getir" not in k.cagrilar and "listele" in k.cagrilar


def test_yanit_sayisi_uyusmazligi_durdurur():
    cevap = cevap_json([bey_kaydi("ALFA", "ALFA", "1111111111", "KDV1", *EKIM)], toplam=250)
    with pytest.raises(LucaHatasi, match="250"):
        toplayici(SahteKopru(cevap)).topla(date(2026, 11, 26))


def test_bozuk_yanit_durdurur_ve_tarayici_kapanir():
    k = SahteKopru({"hata": "oturum düştü"})
    with pytest.raises(LucaHatasi, match="okunamadı"):
        toplayici(k).topla(date(2026, 11, 26))
    assert k.kapandi


def test_sifir_kayit_gecerlidir():
    assert toplayici(SahteKopru(cevap_json([]))).topla(date(2026, 11, 26))["beyannameler"] == []


def test_hata_olsa_da_tarayici_kapanir():
    k = SahteKopru(giris_hatasi=True)
    with pytest.raises(LucaHatasi):
        toplayici(k).topla(date(2026, 11, 26))
    assert k.kapandi


def test_bos_musteri_listesi_durdurur():
    with pytest.raises(LucaHatasi, match="boş"):
        toplayici(SahteKopru(musteriler=[])).topla(date(2026, 11, 26))


def test_tani_modu_veri_kaydetmez():
    k = SahteKopru()
    with pytest.raises(LucaHatasi, match="Tanı modu"):
        toplayici(k, {"LUCA_TANI": "1"}).topla(date(2026, 11, 26))
    assert "tani" in k.cagrilar and k.kapandi and "listele" not in k.cagrilar


def test_kimlik_okuma():
    assert kimlik_oku({"LUCA_UYE_NO": "1", "LUCA_KULLANICI": "u", "LUCA_PAROLA": "p"}, "ofis", True)["parola"] == "p"
    env = {"LUCA_OFIS_UYE_NO": "1", "LUCA_OFIS_KULLANICI": "u", "LUCA_OFIS_PAROLA": "p1",
           "LUCA_ISLETME_UYE_NO": "2", "LUCA_ISLETME_KULLANICI": "v", "LUCA_ISLETME_PAROLA": "p2", "LUCA_PAROLA": "genel"}
    assert kimlik_oku(env, "ofis", False)["parola"] == "p1" and kimlik_oku(env, "isletme", False)["parola"] == "p2"
    with pytest.raises(LucaHatasi, match="parola") as e:
        kimlik_oku({"LUCA_UYE_NO": "1", "LUCA_KULLANICI": "u"}, "ofis", True)
    assert "genel" not in str(e.value)


def test_iki_hesap_ayri_islenir():
    kopruler = {"ofis": SahteKopru(), "isletme": SahteKopru(
        musteriler=[{"sirket_id": "900", "ad": "ISL", "unvan": "ISL LTD", "vkn": "9999999999"}])}
    env = {"LUCA_HESAPLAR": "ofis,isletme", **{f"LUCA_{h.upper()}_{a}": "x" for h in kopruler for a in ("UYE_NO", "KULLANICI", "PAROLA")}}
    t = LucaToplayici("/tmp/x", env=env, kopru_fabrikasi=lambda h, k, c: kopruler[h], tatil=T)
    r = t.topla(date(2026, 11, 26))
    assert {m["hesap"] for m in r["mukellefler"]} == {"ofis", "isletme"} and all(k.kapandi for k in kopruler.values())


def test_cekirdekle_butunlesme_ve_eslesmeyen_uyarisi(tmp_path):
    cevap = cevap_json([bey_kaydi("ALFA", "ALFA LTD", "1111111111", "KDV1", *EKIM),
                        bey_kaydi("YABANCI", "TANINMAYAN FIRMA", "8888888888", "KDV1", *EKIM),
                        bey_kaydi("BETA", "BETA AŞ", "2222222222", "MUHSGK", *EKIM, durum=0)])      # BETA'nın MUHSGK'sı hatalı
    tg = SahteTelegram()
    u = Uygulama(Depo(tmp_path), toplayici(SahteKopru(cevap)), tg, CaptchaKoprusu(tg), saat=Saat("2026-11-26T09:00"))
    r = u.topla()
    assert r["ok"] and any("hiçbir mükellefle eşleşmedi" in x and "TANINMAYAN FIRMA" in x for x in r["uyarilar"])
    d = {(x.ad, x.tur): x.durum for x in u.maddeler() if x.donem == "2026-10"}
    assert d[("ALFA", "KDV1")] == "verildi" and d[("BETA", "KDV1")] == "eksik" and d[("BETA", "MPHB")] == "onaysiz"
    u.slot_calistir("09:00")
    assert any("eşleşmedi" in m for m in tg.mesajlar)


# ================= Müşteri Listesi HTML'i (gerçek sayfanın yapısında, UYDURMA veriyle) =================

def test_musterileri_birlestir_oncelik_ve_ayni_vkn():
    yeni = [{"ad": "ALFA", "vkn": "1", "kapanis": ""}, {"ad": "BETA", "vkn": ""}]
    eski = [{"ad": "ALFA", "vkn": "1", "kapanis": "01/01/2026"}, {"ad": "beta", "vkn": ""}, {"ad": "GAMA", "vkn": "3"}]
    s = musterileri_birlestir([yeni, eski])
    assert [m["ad"] for m in s] == ["ALFA", "BETA", "GAMA"] and s[0]["kapanis"] == ""
    tasfiye = [{"sirket_id": "1", "ad": "FIRMA", "vkn": "7"}, {"sirket_id": "2", "ad": "FIRMA-TASFİ", "vkn": "7"}]
    assert len(musterileri_birlestir([tasfiye])) == 2
    assert len(musterileri_birlestir([[{"ad": "A", "vkn": "7"}, {"ad": "B", "vkn": "7"}]])) == 2


def musteri_sayfasi(satirlar, toplam=None):
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
    assert g["vkn"] == "" and g["unvan"] == "GAMA LTD & ORTAKLARI"
    assert [k["sirket_id"] for k in kayitlar] == ["1001", "1002", "1003", "1004", "1005"]


def test_musteri_html_sayi_uyusmazligi_ve_bos():
    kayitlar, toplam = musteri_html_oku(musteri_sayfasi(SATIRLAR, toplam=7))
    assert toplam == 7 and len(kayitlar) == 5
    assert musteri_html_oku("<html><body>başka sayfa</body></html>") == ([], None) and musteri_html_oku("") == ([], None)


def test_musteri_html_den_mukellef_ve_ayni_vkn_iki_firma():
    kayitlar, _ = musteri_html_oku(musteri_sayfasi(SATIRLAR))
    m = [mukellef_normalize(k, "ofis") for k in kayitlar]
    assert len({x["id"] for x in m}) == 5
    assert m[0]["id"] == "ofis:1001" and m[0]["acilis"] == "2020-01-01" and m[1]["kapanis"] == "2026-08-31"
    assert m[2]["vkn"] == "30000000002"


def test_musteri_yillari():
    assert musteri_yillari(date(2026, 11, 6)) == [2026] and musteri_yillari(date(2027, 1, 14)) == [2027]
    assert musteri_yillari(date(2026, 11, 6), "yok") == [] and musteri_yillari(date(2026, 11, 6), "2026, 2025") == [2026, 2025]


def test_musteri_html_filtre_durumu():
    filtresiz = musteri_sayfasi(SATIRLAR)
    assert musteri_html_filtre(filtresiz) == {"yil": None, "durum": None, "sinif": None}
    filtreli = filtresiz.replace("</body>", '<script>byId("YIL").value = "2026";\n byId("DURUM").value = "";\n byId("SINIF").value = "";</script></body>')
    assert musteri_html_filtre(filtreli) == {"yil": "2026", "durum": "", "sinif": ""}


def test_yil_filtresi_varsayilan_ve_acik_liste():
    firmalar = [{"sirket_id": "1", "ad": "AKTIF", "unvan": "AKTIF", "vkn": "1", "acilis": "01/01/2020", "kapanis": ""},
                {"sirket_id": "2", "ad": "DONEMSIZ", "unvan": "DONEMSIZ", "vkn": "2", "acilis": "01/01/2020", "kapanis": ""}]
    k = SahteKopru(musteriler=firmalar, yil_listeleri={2026: [firmalar[0]]})
    r = toplayici(k).topla(date(2026, 11, 26))
    assert [c for c in k.cagrilar if c.startswith("musteri")] == ["musteri:2026"]
    assert [m["ad"] for m in r["mukellefler"]] == ["AKTIF"] and r["uyarilar"] == []
    a = {"sirket_id": "1", "ad": "A", "unvan": "A", "vkn": "1", "acilis": "01/01/2020", "kapanis": ""}
    b = {"sirket_id": "2", "ad": "B", "unvan": "B", "vkn": "2", "acilis": "01/01/2020", "kapanis": ""}
    k2 = SahteKopru(musteriler=[a, b], yil_listeleri={2027: [a], 2026: [a, b]})
    r2 = toplayici(k2, {"LUCA_MUSTERI_YILI": "2027,2026"}).topla(date(2027, 1, 14))
    assert {m["ad"] for m in r2["mukellefler"]} == {"A", "B"}
    assert [c for c in k2.cagrilar if c.startswith("musteri")] == ["musteri:2027", "musteri:2026:ac-yok"]
    k3 = SahteKopru()
    toplayici(k3, {"LUCA_MUSTERI_YILI": "yok"}).topla(date(2026, 11, 26))
    assert [c for c in k3.cagrilar if c.startswith("musteri")] == ["musteri"]
    with pytest.raises(LucaHatasi, match="boş"):
        toplayici(SahteKopru(yil_listeleri={2026: []})).topla(date(2026, 11, 26))


# ================= gerçek köprü (tarayıcı çağrıları sahte) =================

def kopru_kur(tmp_path, **ek):
    g = GercekLucabot.__new__(GercekLucabot)
    g.log, g.tani_klasoru, g.env = tmp_path / "log.txt", tmp_path, ek.pop("env", {})
    g.m = SimpleNamespace(**ek)
    return g


def test_gercek_toplayici_musteri_listesi_sayfadan_okur_ve_sayiyi_dogrular(tmp_path):
    html = {"v": musteri_sayfasi(SATIRLAR)}
    g = kopru_kur(tmp_path,
                  ml=SimpleNamespace(musteri_listesini_ac=lambda page, log: None, tani_kaydet=lambda *a, **k: None),
                  le=SimpleNamespace(cerceveler=lambda page: [SimpleNamespace(content=lambda: html["v"])]),
                  bekleme=SimpleNamespace(kosulu_bekle=lambda page, f, ms, aralik_ms=0: f()))
    assert len(g.musteri_listesi("sayfa")) == 5
    html["v"] = musteri_sayfasi(SATIRLAR, toplam=9)
    with pytest.raises(LucaHatasi, match="9 kayıt"):
        g.musteri_listesi("sayfa")
    html["v"] = "<html></html>"
    with pytest.raises(LucaHatasi, match="tablosu bulunamadı"):
        g.musteri_listesi("sayfa")


def test_koprude_yil_filtresi_dogrulamasi(tmp_path):
    filtresiz = musteri_sayfasi(SATIRLAR)
    filtreli = musteri_sayfasi(SATIRLAR[:2]).replace("</body>", '<script>byId("YIL").value = "2026";</script></body>')
    durum = {"html": filtresiz, "uygulandi": True}
    g = kopru_kur(tmp_path,
                  ml=SimpleNamespace(yili_filtrele=lambda page, yil, log: durum["uygulandi"], tani_kaydet=lambda *a, **k: None),
                  le=SimpleNamespace(cerceveler=lambda page: [SimpleNamespace(content=lambda: durum["html"])]),
                  bekleme=SimpleNamespace(kosulu_bekle=lambda page, f, ms, aralik_ms=0: f()))
    with pytest.raises(LucaHatasi, match="hâlâ filtresiz"):
        g.musteri_listesi("sayfa", 2026, ac=False)
    durum["html"] = filtreli
    assert len(g.musteri_listesi("sayfa", 2026, ac=False)) == 2
    with pytest.raises(LucaHatasi, match="Yıl=2025"):
        g.musteri_listesi("sayfa", 2025, ac=False)
    durum["uygulandi"] = False
    with pytest.raises(LucaHatasi, match="uygulanamadı"):
        g.musteri_listesi("sayfa", 2026, ac=False)


class SahteEkran:
    """Playwright Page'in kullanılan kısmı: expect_response, on."""

    def __init__(self, yanit=None, hata=None):
        self.yanit, self.hata, self.dinleyiciler = yanit, hata, []

    def on(self, olay, f):
        self.dinleyiciler.append(olay)

    @contextmanager
    def expect_response(self, kosul, timeout=0):
        bilgi = SimpleNamespace(value=None)
        yield bilgi
        if self.hata:
            raise self.hata
        assert kosul(SimpleNamespace(url="https://x.luca.com.tr/Luca/beyan_listele.jq"))
        assert not kosul(SimpleNamespace(url="https://x.luca.com.tr/Luca/paket_sorgula.jq"))
        bilgi.value = self.yanit


def beyanname_kopru(tmp_path, tiklanan, yazilan, secilen=None, basilabilir=True, durum_secilebilir=True):
    secilen = [] if secilen is None else secilen
    kutu = lambda sel: SimpleNamespace(  # noqa: E731
        sel=sel, locator=lambda o: SimpleNamespace(all_inner_texts=lambda: ["Onaylanmış", "Hatalı"]))
    lb = SimpleNamespace(ARAMA_PENCERESI="Arama", ALANLAR_JS="js", LISTELE_DUGMESI="Beyannameleri Listele",
                         _tarih_yaz=lambda k, d: yazilan.append((k.sel, d)),
                         _secenek_sec=lambda k, metin: (secilen.append((k.sel, metin)), durum_secilebilir)[1])
    cerceve = SimpleNamespace(evaluate=lambda js, alanlar: {"Beyanname Dönemi": 1}, locator=kutu)
    le = SimpleNamespace(gorunur_mu=lambda *a, **k: True, cerceveler=lambda page: [cerceve],
                         dugmeye_bas=lambda page, metin, sure=0: (tiklanan.append(metin), basilabilir)[1])
    return kopru_kur(tmp_path, lb=lb, le=le, ml=SimpleNamespace(tani_kaydet=lambda *a, **k: None))


def test_koprude_beyanname_listele_durumu_tumu_yapar_tarihleri_yazar_ve_yaniti_yakalar(tmp_path):
    veri = cevap_json([bey_kaydi("ALFA", "ALFA", "1111111111", "KDV1", *EKIM)])
    tiklanan, yazilan, secilen = [], [], []
    g = beyanname_kopru(tmp_path, tiklanan, yazilan, secilen)
    cevap = SimpleNamespace(ok=True, json=lambda: veri)
    assert g.beyanname_listele(SahteEkran(cevap), date(2026, 9, 27), date(2026, 11, 6)) == veri
    assert secilen == [('[data-lucabot-alan="Beyanname Durum#0"]', "Tümü")]          # varsayılan "Onaylanmış" olduğundan şart
    assert yazilan == [('[data-lucabot-alan="Paket Yükleme Tarihi#0"]', date(2026, 9, 27)),
                       ('[data-lucabot-alan="Paket Yükleme Tarihi#1"]', date(2026, 11, 6))]
    assert tiklanan == ["Beyannameleri Listele"]


def test_koprude_beyanname_listele_hatalari(tmp_path):
    g = beyanname_kopru(tmp_path, [], [])
    with pytest.raises(LucaHatasi, match="HTTP 500"):
        g.beyanname_listele(SahteEkran(SimpleNamespace(ok=False, status=500, json=lambda: {})), date(2026, 9, 27), date(2026, 11, 6))

    def bozuk():
        raise ValueError("json değil")
    with pytest.raises(LucaHatasi, match="JSON değil"):
        g.beyanname_listele(SahteEkran(SimpleNamespace(ok=True, json=bozuk)), date(2026, 9, 27), date(2026, 11, 6))
    with pytest.raises(LucaHatasi, match="yanıtı gelmedi"):
        g.beyanname_listele(SahteEkran(hata=TimeoutError("x")), date(2026, 9, 27), date(2026, 11, 6))
    g2 = beyanname_kopru(tmp_path, [], [], basilabilir=False)
    with pytest.raises(LucaHatasi, match="düğmesine basılamadı"):
        g2.beyanname_listele(SahteEkran(), date(2026, 9, 27), date(2026, 11, 6))
    tiklanan, yazilan = [], []
    g3 = beyanname_kopru(tmp_path, tiklanan, yazilan, durum_secilebilir=False)      # "Tümü" yoksa sessizce onaylıyla yetinilmez
    with pytest.raises(LucaHatasi, match="'Tümü' seçeneği yok"):
        g3.beyanname_listele(SahteEkran(), date(2026, 9, 27), date(2026, 11, 6))
    assert tiklanan == [] and yazilan == []


ISLEM_TAKIP = ("İşlem Takip\nBeyannameler GİB'den sorgulanıyor.\n1 adet paket bulundu.\n"
               "[x1] Paket içindeki beyannameler sorgulandı.\n")


def gib_kopru(tmp_path, tiklanan, metinler, basilabilir=True):
    """İşlem Takip penceresinin metni zamanla büyür; son turda bitiş yazısı eklenir."""
    metin = {"v": "Tablo satırları...\n"}
    cerceve = SimpleNamespace(locator=lambda sel: SimpleNamespace(inner_text=lambda timeout=0: metin["v"]))
    le = SimpleNamespace(cerceveler=lambda page: [cerceve],
                         dugmeye_bas=lambda page, ad, sure=0: (tiklanan.append(ad), basilabilir)[1])

    def bekle(page, f, ms, aralik_ms=0):
        for tur, ek in enumerate(metinler):
            metin["v"] += ek
            sonuc = f()
            if sonuc:
                return sonuc
        return None
    return kopru_kur(tmp_path, le=le, bekleme=SimpleNamespace(kosulu_bekle=bekle),
                     ml=SimpleNamespace(tani_kaydet=lambda *a, **k: None), env={})


def test_koprude_gib_getir_islem_takip_bitisini_bekler_ve_pencereyi_kapatir(tmp_path):
    tiklanan = []
    g = gib_kopru(tmp_path, tiklanan, [ISLEM_TAKIP, "", "Ekrandaki listeyi yenilemek için buraya tıklayınız."])
    ekran = SimpleNamespace(on=lambda *a: None)
    g.gib_getir(ekran)
    assert tiklanan == ["GİB'den Getir", "Kapat"]


def test_koprude_gib_getir_bitmezse_hata(tmp_path):
    tiklanan = []
    g = gib_kopru(tmp_path, tiklanan, [ISLEM_TAKIP, "", ""])                       # bitiş yazısı hiç gelmez
    with pytest.raises(LucaHatasi, match="içinde bitmedi"):
        g.gib_getir(SimpleNamespace(on=lambda *a: None))
    assert tiklanan == ["GİB'den Getir"]                                           # Kapat'a basılmaz
    g2 = gib_kopru(tmp_path, [], [], basilabilir=False)
    with pytest.raises(LucaHatasi, match="basılamadı"):
        g2.gib_getir(SimpleNamespace(on=lambda *a: None))


def test_koprude_gib_getir_onay_pencerelerini_kabul_eder(tmp_path):
    dinleyiciler = []
    g = gib_kopru(tmp_path, [], ["Ekrandaki listeyi yenilemek için"])
    g.gib_getir(SimpleNamespace(on=lambda olay, f: dinleyiciler.append(olay)))
    assert dinleyiciler == ["dialog"]


# ================= tanı =================

def test_tani_veri_kaydetmez_ve_tarayiciyi_kapatir():
    k = SahteKopru()
    r = toplayici(k).tani(date(2026, 11, 26))
    assert r == {"hesaplar": ["ofis"]} and "tani" in k.cagrilar and k.kapandi
    assert not any(c.startswith(("musteri", "listele")) for c in k.cagrilar)


def test_tani_giris_hatasini_gizlemez():
    k = SahteKopru(giris_hatasi=True)
    with pytest.raises(LucaHatasi, match="giriş"):
        toplayici(k).tani(date(2026, 11, 26))
    assert k.kapandi


def test_cekirdek_tani_sonucunu_kaydeder(tmp_path):
    tg = SahteTelegram()
    u = Uygulama(Depo(tmp_path), toplayici(SahteKopru()), tg, CaptchaKoprusu(tg), saat=Saat("2026-11-26T09:00"))
    assert u.tani()["ok"] and u.depo.oku("durum.json")["son_tani"]["ok"] and not u.tani_suruyor
    assert not u.depo.oku("mukellefler.json")
    u2 = Uygulama(Depo(tmp_path / "b"), toplayici(SahteKopru(giris_hatasi=True)), tg, CaptchaKoprusu(tg), saat=Saat("2026-11-26T09:00"))
    r = u2.tani()
    assert not r["ok"] and "giriş" in r["mesaj"].lower() and not u2.tani_suruyor


def test_tani_luca_disi_toplayicida_calismaz(tmp_path):
    from app.toplayici import OrnekToplayici
    tg = SahteTelegram()
    u = Uygulama(Depo(tmp_path), OrnekToplayici(), tg, CaptchaKoprusu(tg), saat=Saat("2026-11-26T09:00"))
    assert not u.tani()["ok"]


# ================= gerçek lucabot paketiyle uyum =================

def test_lucabot_yoksa_anlasilir_hata(tmp_path, monkeypatch):
    monkeypatch.delitem(__import__("sys").modules, "lucabot", raising=False)
    with pytest.raises(LucaHatasi, match="LUCABOT_YOLU"):
        GercekLucabot(tmp_path, "ofis", {}, None, env={})


@pytest.mark.skipif(not os.environ.get("LUCABOT_YOLU"), reason="lucabot paketi yok (LUCABOT_YOLU tanımlı değil)")
def test_gercek_lucabot_arayuzu_uyumlu(tmp_path):
    g = GercekLucabot(tmp_path, "ofis", {"uye_no": "1"}, None, env=os.environ)
    gereken = {
        "giris": ["luca_oturumu_ac"],
        "lb": ["menusu_olan_firmayi_sec", "ekrani_ac", "ARAMA_PENCERESI", "ALANLAR_JS", "_tarih_yaz", "_secenek_sec",
               "LISTELE_DUGMESI"],
        "le": ["gorunur_mu", "dugmeye_bas", "cerceveler", "acik_pencereleri_kapat"],
        "gz": ["firma_secici_bekle"], "ml": ["musteri_listesini_ac", "yili_filtrele", "tani_kaydet"],
        "tarayici": ["tarayici_ac", "tarayiciyi_kapat"], "bekleme": ["kosulu_bekle"],
    }
    eksik = [f"{mod}.{ad}" for mod, adlar in gereken.items() for ad in adlar if not hasattr(getattr(g.m, mod), ad)]
    assert not eksik, eksik
    assert g.m.ortak.AYAR["tarayici"] == "chromium" and g.m.ortak.AYAR["tarayici_sandbox"] is False
