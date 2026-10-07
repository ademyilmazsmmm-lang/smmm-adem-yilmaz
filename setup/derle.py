# -*- coding: utf-8 -*-
"""Dijital Stajyer kurulum paketini (setup.exe) uretir. Linux, macOS ve Windows'ta calisir; NSIS (makensis) gerekir.

    python setup/derle.py --lisans lisans.json [--cikti setup/cikti]

Adimlar:
  1. git'te izlenen luca-bot/ ve kar-zarar/ dosyalarindan (testler, gelistirici araclari ve kisisel veriler
     haric) bir gecici "sahne" klasoru kurar;
  2. --lisans ile verilen imzali lisansi dogrular (bugun gecerli olmali) ve paketin icine koyar;
  3. NSIS icin dosyalar.nsh (kurulacak dosyalar) ve silme.nsh (kaldirilacak dosyalar) uretir;
  4. makensis ile DijitalStajyer-Kurulum-<surum>.exe olusturur ve SHA-256 degerini yazar.

Lisansi uretmek icin: python luca-bot/lisans_araci.py uret --anahtar <ozel anahtar> --sahip "..." --bitis 2026-12-31
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

DEPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEPO / "luca-bot"))
from lucabot import SURUM, lisans  # noqa: E402

# pakete GIRMEYENLER (gelistirici araclari, testler, kisisel/uretilen veriler)
HARIC_YOL = ("/testler/", "/birlestirme/", "/__pycache__/")
HARIC_AD = {"lisans_araci.py", ".gitignore", ".gitattributes", "BIRLESTIRME.md", "kapali-firmalar.md",
            "giris-gunlugu.log", "luca_bot_sabahki.py", "sabahki-surum-testi.bat", "gecis_rapor_birlestir.py",
            "gecis-rapor-birlestir.bat", "ayarlar.json", "lisans.json", "lisans-durum.json", "python-yolu.txt"}


def izlenen_dosyalar():
    cikti = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "luca-bot", "kar-zarar"], cwd=DEPO)
    for yol in cikti.decode("utf-8").split("\0"):
        if not yol:
            continue
        p = Path(yol)
        if p.name in HARIC_AD or any(h in "/" + yol for h in HARIC_YOL):
            continue
        yield p


def nsis_yolu(p):
    return str(p).replace("/", "\\")


def sahne_kur(sahne):
    dosyalar = []
    for p in izlenen_dosyalar():
        hedef = sahne / p
        hedef.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DEPO / p, hedef)
        dosyalar.append(p)
    shutil.copyfile(Path(__file__).parent / "BASLARKEN.txt", sahne / "luca-bot" / "BASLARKEN.txt")
    dosyalar.append(Path("luca-bot/BASLARKEN.txt"))
    return dosyalar


def nsh_yaz(sahne, dosyalar, hedef_klasor):
    klasorler = {}
    for p in dosyalar:
        klasorler.setdefault(p.parent, []).append(p)
    kur, sil = [], []
    for klasor in sorted(klasorler):
        kur.append(f'SetOutPath "$INSTDIR\\{nsis_yolu(klasor)}"')
        for p in sorted(klasorler[klasor]):
            kur.append(f'File "{sahne / p}"')
            sil.append(f'Delete "$INSTDIR\\{nsis_yolu(p)}"')
    # calisirken olusan __pycache__ klasorleri ve (bos kalirsa) kendi klasorleri kaldirilir; kullanici verisine dokunulmaz
    for klasor in sorted(klasorler, key=lambda k: -len(k.parts)):
        sil.append(f'RMDir /r "$INSTDIR\\{nsis_yolu(klasor / "__pycache__")}"')
        sil.append(f'RMDir "$INSTDIR\\{nsis_yolu(klasor)}"')
    (hedef_klasor / "dosyalar.nsh").write_text("\n".join(kur) + "\n", encoding="utf-8-sig")
    (hedef_klasor / "silme.nsh").write_text("\n".join(sil) + "\n", encoding="utf-8-sig")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lisans", required=True, help="paketle gidecek imzali lisans.json")
    p.add_argument("--cikti", default=str(Path(__file__).parent / "cikti"))
    p.add_argument("--makensis", default=shutil.which("makensis") or "makensis")
    args = p.parse_args()

    d = lisans.durum(dosya=args.lisans, kaydet=False)
    if not d["gecerli"]:
        raise SystemExit(f"Lisans paketlenemez: {d['mesaj']}")
    print(f"Lisans: {lisans.ozet(d)}")

    cikti = Path(args.cikti)
    cikti.mkdir(parents=True, exist_ok=True)
    exe = cikti / f"DijitalStajyer-Kurulum-{SURUM}.exe"
    with tempfile.TemporaryDirectory(prefix="dijital-stajyer-") as gecici:
        gecici = Path(gecici)
        sahne = gecici / "sahne"
        dosyalar = sahne_kur(sahne)
        nsh_yaz(sahne, dosyalar, gecici)
        lisans_kopya = gecici / "lisans.json"
        shutil.copyfile(args.lisans, lisans_kopya)
        metin = gecici / "kosullar.txt"  # NSIS lisans sayfasi icin UTF-16 (BOM'lu)
        metin.write_text((Path(__file__).parent / "LISANS-KOSULLARI.txt").read_text(encoding="utf-8"),
                         encoding="utf-16")
        shutil.copyfile(DEPO / "luca-bot" / "varliklar" / "logo.ico", gecici / "simge.ico")
        shutil.copyfile(Path(__file__).parent / "dijital-stajyer.nsi", gecici / "dijital-stajyer.nsi")
        komut = [args.makensis, "-V2", f"-DSURUM={SURUM}", f"-DYIL={date.today().year}",
                 f"-DCIKTI_EXE={exe}", f"-DSIMGE={gecici / 'simge.ico'}", f"-DLISANS_METNI={metin}",
                 f"-DLISANS_DOSYASI={lisans_kopya}", str(gecici / "dijital-stajyer.nsi")]
        print(f"{len(dosyalar)} dosya paketleniyor...")
        sonuc = subprocess.run(komut, cwd=gecici)
        if sonuc.returncode != 0:
            raise SystemExit("makensis basarisiz oldu.")
    sha = hashlib.sha256(exe.read_bytes()).hexdigest()
    (cikti / f"{exe.name}.sha256").write_text(f"{sha} *{exe.name}\n", encoding="ascii")
    print(f"\nHazir: {exe}  ({exe.stat().st_size / 1e6:.1f} MB)\nSHA-256: {sha}")


if __name__ == "__main__":
    main()
