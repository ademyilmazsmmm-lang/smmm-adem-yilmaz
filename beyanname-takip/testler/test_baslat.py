import io
import json
from pathlib import Path

import pytest

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
import baslat


def test_ayar_oku_ozel_karakterli_parola_ve_yorumlar():
    m = "﻿# yorum\n\nWEB_SIFRE=abcd\nLUCA_OFIS_PAROLA=p&s%1!^=x y\nMAIL_ALICI=\"a@b.c\"\nBOS=\n"
    assert baslat.ayar_oku(m) == {"WEB_SIFRE": "abcd", "LUCA_OFIS_PAROLA": "p&s%1!^=x y", "MAIL_ALICI": "a@b.c", "BOS": ""}
    for kotu in ("sifre=1", "WEB SIFRE=1", "yalnizca metin"):
        with pytest.raises(ValueError):
            baslat.ayar_oku(kotu)


def test_ortami_hazirla_varsayilanlar_ve_lucabot_yolu(tmp_path, monkeypatch):
    luca = tmp_path / "luca-bot" / "lucabot"
    luca.mkdir(parents=True)
    (luca / "__init__.py").write_text("")
    monkeypatch.setattr(baslat, "KOK", tmp_path / "beyanname-takip")                  # luca-bot yan yana
    (tmp_path / "beyanname-takip").mkdir()
    env = {}
    baslat.ortami_hazirla({"WEB_SIFRE": "1234", "TELEGRAM_TOKEN": ""}, env)
    assert env["TOPLAYICI"] == "luca" and env["BEYANNAME_YEREL"] == "1" and env["DATA_DIR"].endswith("veri")
    assert env["LUCABOT_YOLU"] == str(tmp_path / "luca-bot")                          # Dijital Stajyer'in lucabot'u
    assert "TELEGRAM_TOKEN" not in env
    env2 = {"LUCABOT_YOLU": "/baska"}
    baslat.ortami_hazirla({"WEB_SIFRE": "1"}, env2)
    assert env2["LUCABOT_YOLU"] == "/baska"                                           # sekmenin verdigi yol ezilmez
    with pytest.raises(ValueError):
        baslat.ortami_hazirla({}, {})


def test_luca_bot_klasoru_bulunamazsa_none(tmp_path, monkeypatch):
    monkeypatch.setattr(baslat, "KOK", tmp_path / "x")
    assert baslat.luca_bot_klasoru() is None


def test_gunluge_yonlendir_konsol_yoksa_dosyaya_yazar(tmp_path):
    o, e = io.StringIO(), io.StringIO()
    assert baslat.gunluge_yonlendir(o, e, tmp_path / "l.log") == (o, e)
    so, se = baslat.gunluge_yonlendir(None, None, tmp_path / "l.log")
    so.write("merhaba\n")
    se.write("hata\n")
    so.flush()
    assert (tmp_path / "l.log").read_text(encoding="utf-8") == "merhaba\nhata\n"


def test_kontrol_yaz_anahtar_uretir_ve_dosyaya_yazar(tmp_path):
    env = {}
    dosya = baslat.kontrol_yaz(8765, tmp_path / "kontrol.json", env)
    veri = json.loads(Path(dosya).read_text(encoding="ascii"))
    assert veri["port"] == 8765 and len(veri["anahtar"]) == 32
    assert env["BEYANNAME_KONTROL_TOKEN"] == veri["anahtar"]                           # uygulama bu anahtarı ortamdan okur
    env2 = {}
    baslat.kontrol_yaz(8765, tmp_path / "k2.json", env2)
    assert env2["BEYANNAME_KONTROL_TOKEN"] != veri["anahtar"]                          # her açılışta farklı
