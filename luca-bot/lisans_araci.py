# -*- coding: utf-8 -*-
"""Lisans uretme araci (YALNIZ program sahibi icin; musteriye gonderilen pakete konmaz).

    python lisans_araci.py anahtar-uret  [--dosya lisans-ozel-anahtar.txt]
        Yeni Ed25519 anahtar cifti uretir. Ozel anahtar dosyaya yazilir (GIZLI TUTUN, kimseye vermeyin);
        acik anahtar ekrana basilir ve lucabot/lisans.py icindeki ACIK_ANAHTAR olarak girilir.

    python lisans_araci.py uret --anahtar lisans-ozel-anahtar.txt --sahip "Ad Soyad, SMMM"
                                [--baslangic 2026-01-01] [--bitis 2026-12-31] [--cikti lisans.json]
        Imzali lisans dosyasi uretir; musteri bunu programin klasorune koyar ya da Hakkinda'dan yukler.

    python lisans_araci.py kontrol [lisans.json]
        Lisansin gecerliligini ve kalan gunu gosterir.
"""

import argparse
import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lucabot import lisans  # noqa: E402


def _tohum_oku(yol):
    metin = Path(yol).read_text(encoding="ascii").strip()
    tohum = bytes.fromhex(metin)
    if len(tohum) != 32:
        raise SystemExit("Ozel anahtar dosyasi 32 bayt (64 hex karakter) icermeli.")
    return tohum


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    alt = p.add_subparsers(dest="komut", required=True)
    a = alt.add_parser("anahtar-uret")
    a.add_argument("--dosya", default="lisans-ozel-anahtar.txt")
    u = alt.add_parser("uret")
    u.add_argument("--anahtar", required=True)
    u.add_argument("--sahip", required=True)
    u.add_argument("--baslangic", default="2026-01-01")
    u.add_argument("--bitis", default="2026-12-31")
    u.add_argument("--cikti", default="lisans.json")
    k = alt.add_parser("kontrol")
    k.add_argument("dosya", nargs="?", default=str(lisans.LISANS_DOSYASI))
    args = p.parse_args(argv)

    if args.komut == "anahtar-uret":
        yol = Path(args.dosya)
        if yol.exists():
            raise SystemExit(f"{yol} zaten var; uzerine yazilmadi (eski anahtarla verilen lisanslar bozulmasin).")
        tohum = secrets.token_bytes(32)
        yol.write_text(tohum.hex() + "\n", encoding="ascii")
        print(f"Ozel anahtar yazildi: {yol}  (GIZLI TUTUN)")
        print(f"Acik anahtar (lucabot/lisans.py -> ACIK_ANAHTAR): {lisans.acik_anahtar_uret(tohum).hex()}")
    elif args.komut == "uret":
        veri = lisans.lisans_olustur(_tohum_oku(args.anahtar), args.sahip.strip(), args.baslangic, args.bitis)
        Path(args.cikti).write_text(json.dumps(veri, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Yazildi: {args.cikti}  ({args.sahip.strip()}, {args.baslangic} - {args.bitis})")
    else:
        d = lisans.durum(dosya=args.dosya, kaydet=False)
        print(("GECERLI" if d["gecerli"] else "GECERSIZ") + " — " + (d["uyari"] or d["mesaj"] or lisans.ozet(d)))
        if d["kalan_gun"] is not None:
            print(f"Sahip: {d['sahip']}   Bitis: {d['bitis']}   Kalan gun: {d['kalan_gun']}")
        return 0 if d["gecerli"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
