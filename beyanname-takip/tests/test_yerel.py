import pytest

from yerel.baslat import ayar_oku, ortami_hazirla


def test_ayar_oku_ozel_karakterli_parola_ve_yorumlar():
    m = "﻿# yorum\n\nWEB_SIFRE=abcd\nLUCA_OFIS_PAROLA=p&s%1!^=x y\nMAIL_ALICI=\"a@b.c\"\nBOS=\n"
    a = ayar_oku(m)
    assert a == {"WEB_SIFRE": "abcd", "LUCA_OFIS_PAROLA": "p&s%1!^=x y", "MAIL_ALICI": "a@b.c", "BOS": ""}


def test_ayar_oku_bozuk_satir():
    for kotu in ("sifre=1", "WEB SIFRE=1", "yalnizca metin"):
        with pytest.raises(ValueError):
            ayar_oku(kotu)


def test_ortami_hazirla_varsayilanlar_ve_zorunlu():
    env = {}
    ortami_hazirla({"WEB_SIFRE": "1234", "TELEGRAM_TOKEN": ""}, env)
    assert env["TOPLAYICI"] == "luca" and env["DATA_DIR"].endswith("veri") and env["LUCABOT_YOLU"].endswith("luca-bot")
    assert "TELEGRAM_TOKEN" not in env                         # boş değerler ortama yazılmaz
    with pytest.raises(ValueError):
        ortami_hazirla({}, {})


def test_gunluge_yonlendir_konsol_yoksa_dosyaya_yazar(tmp_path):
    import io
    from yerel.baslat import gunluge_yonlendir
    o, e = io.StringIO(), io.StringIO()
    assert gunluge_yonlendir(o, e, tmp_path / "l.log") == (o, e)                  # konsol varsa dokunulmaz
    so, se = gunluge_yonlendir(None, None, tmp_path / "l.log")                     # pythonw: stdout/stderr yok
    so.write("merhaba\n")
    se.write("hata\n")
    so.flush()
    assert (tmp_path / "l.log").read_text(encoding="utf-8") == "merhaba\nhata\n"
    (tmp_path / "b.log").write_bytes(b"x" * 5_000_001)                             # 5 MB'ı aşarsa baştan
    so2, _ = gunluge_yonlendir(None, io.StringIO(), tmp_path / "b.log")
    so2.write("yeni\n")
    so2.flush()
    assert (tmp_path / "b.log").read_text(encoding="utf-8") == "yeni\n"


def test_ortami_hazirla_yerel_isareti_ve_hata_goster_konsolda_yazar(capsys):
    from yerel.baslat import ortami_hazirla, hata_goster
    env = {}
    ortami_hazirla({"WEB_SIFRE": "1234"}, env)
    assert env["BEYANNAME_YEREL"] == "1"
    hata_goster("bir sorun")
    assert "HATA: bir sorun" in capsys.readouterr().out


def test_windows_betikleri_crlf_ve_beklenen_komutlar():
    from pathlib import Path
    yerel = Path(__file__).resolve().parent.parent / "yerel"
    for ad in ("baslat.bat", "kur.bat", "Beyanname Takip.vbs", "Masaustune kisayol koy.vbs", "Luca Giris.vbs"):
        veri = (yerel / ad).read_bytes()
        assert b"\r\n" in veri and b"\n" not in veri.replace(b"\r\n", b""), ad            # tüm satır sonları CRLF
        assert all(b < 128 for b in veri), ad                                            # ASCII: kod sayfası sorunu çıkmaz
    vbs = (yerel / "Beyanname Takip.vbs").read_text()
    assert "pythonw.exe" in vbs and "/saglik" in vbs and "kur.bat" in vbs and ", 0, False" in vbs     # gizli pencere, sağlık kontrolü, ilk kurulum
    assert "call kur.bat" in (yerel / "baslat.bat").read_text()


# ================= Luca'ya hızlı giriş =================

def test_hesap_sec():
    from yerel.luca_giris import hesap_sec
    env = {"LUCA_HESAPLAR": "ofis, isletme"}
    assert hesap_sec(env, []) == ("ofis", ["ofis", "isletme"])                       # argüman yoksa ilk hesap
    assert hesap_sec(env, ["isletme"])[0] == "isletme"
    assert hesap_sec(env, [" OFIS "])[0] == "ofis"                                   # büyük/küçük harf ve boşluk önemsiz
    assert hesap_sec(env, [""])[0] == "ofis"                                         # boş argüman = verilmemiş
    assert hesap_sec({}, [])[0] == "ofis"                                            # LUCA_HESAPLAR yoksa varsayılan
    with pytest.raises(ValueError, match="tanımlı değil.*ofis, isletme"):
        hesap_sec(env, ["baska"])


def test_acik_bekle_tarayici_kapanana_kadar_bekler():
    from yerel.luca_giris import acik_bekle

    class Sayfa:
        def __init__(self, omur):
            self.omur = omur

    class Ctx:
        def __init__(self, sayfalar):
            self.pages = sayfalar
            self.kapanis = None

        def on(self, olay, f):
            self.kapanis = f

    s1, s2 = Sayfa(3), Sayfa(5)
    ctx = Ctx([s1, s2])
    sayac = {"nabiz": 0, "uyku": 0}

    def canli(p):
        return p.omur > 0

    def nabiz(page, ms):
        sayac["nabiz"] += 1
        for p in ctx.pages:
            p.omur -= 1                                                              # her nabızda sayfalar biraz "ölür"
    def uyku(saniye):                                                                # ana sayfa ölünce nabız yerine uyku çağrılır
        sayac["uyku"] += 1
        assert sayac["uyku"] < 100, "acik_bekle sonsuz dongude"
        for p in ctx.pages:
            p.omur -= 1
    assert acik_bekle(ctx, s1, nabiz, canli, uyku=uyku)
    assert all(p.omur <= 0 for p in ctx.pages)                                       # tüm sayfalar kapanınca biter
    assert sayac["nabiz"] >= 3 and sayac["uyku"] >= 2                                # s1 ölünce uykuya geçildi, s2 bitene kadar beklendi
    ctx2 = Ctx([Sayfa(10**6)])                                                       # tarayıcı 'close' olayı verirse hemen biter
    adim = {"n": 0}

    def nabiz2(page, ms):
        adim["n"] += 1
        assert adim["n"] < 100, "sonsuz dongu"
        if adim["n"] == 2:
            ctx2.kapanis(None)
    assert acik_bekle(ctx2, ctx2.pages[0], nabiz2, canli) and adim["n"] == 2


def test_kisayol_betikleri_hizli_giris_icerir():
    from pathlib import Path
    yerel = Path(__file__).resolve().parent.parent / "yerel"
    giris = (yerel / "Luca Giris.vbs").read_text()
    assert "luca_giris.py" in giris and "WScript.Arguments(0)" in giris and ", 0, False" in giris    # gizli, hesap argümanı
    kisayol = (yerel / "Masaustune kisayol koy.vbs").read_text()
    assert "LUCA_HESAPLAR" in kisayol and "Luca Giris.vbs" in kisayol and "Beyanname Takip.vbs" in kisayol
    assert "ChrW(304)" in kisayol                                                    # "İşletme" kısayol adı
    assert (yerel / "luca_giris.py").exists()
