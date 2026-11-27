#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Indirilmis Muavin / Isletme Defteri Excel'lerinde arama (Luca'ya GIRMEZ; yalniz diskteki dosyalari okur).

Kullanim: bir mukellefin fisleri / faturalari yanlis firmaya islenmis olabilir; Muavin programi her firma icin
cikti/<tarih>/muavin/dosyalar/ altina Excel indirir. Bu program o Excel'lerin hepsinde arar ve hangi firmanin
dosyasinda bulundugunu soyler.

    # 1) Bir mukellefin indirilmis faturalarinin numaralari baska firmanin muavininde var mi?
    python muavin_ara.py --firma-faturalari "ORNEK FIRMA" --tarih 01/10/2026-31/10/2026

    # 2) Elindeki fatura numarasi / tutar / metin ile ara
    python muavin_ara.py --no ABC2026000000123 --no XYZ2026000000045
    python muavin_ara.py --tutar 1.234,56 --metin "kira"

Her arama olcutu DOSYA bazinda "ve" degil "veya"dir (en az biri tutan satir listelenir); sonuc firma bazinda ozetlenir.
Cikti: cikti/muavin-arama.xlsx (+ ekranda ozet). Muavin programi yalniz donemde faturasi indirilmis firmalar icin
dosya indirir; aradiginiz firmanin dosyasi yoksa once o firma icin Muavin'i calistirin (--tum-firmalar secenegiyle).
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

from karzarar import muavin_karsilastir as mk  # noqa: E402
from lucabot.ortak import ayarlari_oku, tarih_cozumle  # noqa: E402

CIKTI = KOK / "cikti"
TOLERANS = 0.01
ONEKLER = (("isletme_defteri_", mk.isletme_defteri_satirlari), ("muavin_", mk.muavin_satirlari))


def dosya_firmasi(yol):
    """muavin_ORNEK FIRMA.xlsx -> 'ORNEK FIRMA' (dosya adi Luca'daki adin ASCII'lestirilmis halidir)."""
    ad = Path(yol).stem
    for onek, _ in ONEKLER:
        if ad.startswith(onek):
            return ad[len(onek):]
    return ad


def dosyalari_bul(klasor):
    """Klasor altindaki tum muavin_*.xlsx / isletme_defteri_*.xlsx; ayni firma icin en yeni dosya (tarih klasoruyle)."""
    en_yeni = {}
    for yol in Path(klasor).rglob("*.xlsx"):
        if yol.name.startswith("~$") or not any(yol.name.startswith(o) for o, _ in ONEKLER):
            continue
        anahtar = (dosya_firmasi(yol), yol.name.startswith("isletme_defteri_"))
        if anahtar not in en_yeni or yol.stat().st_mtime > en_yeni[anahtar].stat().st_mtime:
            en_yeni[anahtar] = yol
    return sorted(en_yeni.values(), key=lambda y: (dosya_firmasi(y), y.name))


def satirlari_oku(yol):
    for onek, oku in ONEKLER:
        if Path(yol).name.startswith(onek):
            return oku(yol)
    return []


def _norm(m):
    return re.sub(r"\s+", " ", str(m or "").replace("İ", "i").replace("I", "ı").lower().replace("ı", "i")).strip()


def ara(dosyalar, nolar=(), tutarlar=(), metinler=(), log=print):
    """Her dosyada olcutlere uyan satirlar: [{firma, dosya, hesap, tarih, fis, belge, aciklama, borc, alacak, neden}]."""
    nolar = {n.strip().upper() for n in nolar if n and n.strip()}
    metinler = [_norm(m) for m in metinler if m and str(m).strip()]
    sonuc = []
    for yol in dosyalar:
        try:
            satirlar = satirlari_oku(yol)
        except Exception as e:                                       # bozuk / okunamayan dosya aramayi durdurmaz
            log(f"  Okunamadı: {Path(yol).name} ({type(e).__name__})")
            continue
        for s in satirlar:
            nedenler = []
            bulunan = nolar & {n.upper() for n in s.get("nolar", [])}
            if bulunan:
                nedenler.append("fatura no: " + ", ".join(sorted(bulunan)))
            tutar_alanlari = (s.get("borc") or 0, s.get("alacak") or 0, s.get("toplam") or 0)
            for t in tutarlar:
                if any(a and abs(abs(a) - abs(t)) <= TOLERANS for a in tutar_alanlari):
                    nedenler.append(f"tutar: {mk.tl(t)}")
            metin = _norm(s.get("metin", ""))
            for m in metinler:
                if m in metin:
                    nedenler.append(f"metin: {m}")
            if nedenler:
                sonuc.append({"firma": dosya_firmasi(yol), "dosya": Path(yol).name, "hesap": s.get("hesap", ""),
                              "tarih": s.get("tarih"), "fis": s.get("fis", ""), "belge": s.get("belge", ""),
                              "aciklama": s.get("aciklama", ""), "borc": s.get("borc", 0.0), "alacak": s.get("alacak", 0.0),
                              "neden": "; ".join(nedenler)})
    return sonuc


def firma_ozeti(sonuc, toplam_no=None):
    """Firma bazinda: kac farkli olcut (fatura no) bulundu, kac satir. En cok bulunan ustte."""
    ozet = {}
    for s in sonuc:
        o = ozet.setdefault(s["firma"], {"firma": s["firma"], "satir": 0, "nolar": set()})
        o["satir"] += 1
        for parca in s["neden"].split("; "):
            if parca.startswith("fatura no: "):
                o["nolar"].update(x.strip() for x in parca[len("fatura no: "):].split(","))
    liste = sorted(ozet.values(), key=lambda o: (-len(o["nolar"]), -o["satir"], o["firma"]))
    for o in liste:
        o["no_sayisi"] = len(o["nolar"])
        o["toplam_no"] = toplam_no
    return liste


def excel_yaz(yol, sonuc, ozet):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Firma özeti"
    ws.append(["Firma (dosya adı)", "Bulunan fatura no sayısı", "Aranan fatura no sayısı", "Eşleşen satır"])
    for o in ozet:
        ws.append([o["firma"], o["no_sayisi"], o["toplam_no"] if o["toplam_no"] is not None else "", o["satir"]])
    ws2 = wb.create_sheet("Satırlar")
    ws2.append(["Firma (dosya adı)", "Hesap", "Tarih", "Fiş", "Belge/Evrak", "Açıklama", "Borç", "Alacak", "Neden"])
    for s in sonuc:
        ws2.append([s["firma"], s["hesap"], s["tarih"].strftime("%d.%m.%Y") if s["tarih"] else "", s["fis"],
                    s["belge"], s["aciklama"], s["borc"], s["alacak"], s["neden"]])
    for sayfa in (ws, ws2):
        for h in sayfa[1]:
            h.font = Font(bold=True)
        for sutun in sayfa.columns:
            sayfa.column_dimensions[sutun[0].column_letter].width = min(48, max(12, max(len(str(h.value or "")) for h in sutun) + 2))
    Path(yol).parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(yol))
    return yol


def firma_fatura_nolari(fatura_klasoru, firma, bas, bit):
    f = mk.faturalari_oku(fatura_klasoru, firma, bas, bit)
    return sorted({x["no"] for yon in f.values() for x in yon})


def parser():
    p = argparse.ArgumentParser(description="Indirilmis Muavin / Isletme Defteri Excel'lerinde ara (Luca'ya girmez)")
    p.add_argument("--klasor", help="Excel'lerin aranacagi klasor (alt klasorler dahil); varsayilan: cikti/")
    p.add_argument("--no", action="append", default=[], help="Aranacak fatura numarasi (birden cok kez verilebilir)")
    p.add_argument("--tutar", action="append", default=[], help="Aranacak tutar (borc/alacak/toplam), ornek 1.234,56")
    p.add_argument("--metin", action="append", default=[], help="Aciklama/belge metninde gecen sozcuk")
    p.add_argument("--firma-faturalari", dest="firma",
                   help="Bu firmanin indirilmis faturalarinin numaralarini (rapor.json) diger firmalarin dosyalarinda ara")
    p.add_argument("--tarih", help="--firma-faturalari icin donem: GG/AA/YYYY-GG/AA/YYYY")
    p.add_argument("--fatura-klasoru", dest="fatura_klasoru", help="rapor.json'un bulundugu indirilenler klasoru")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    klasor = Path(args.klasor) if args.klasor else CIKTI
    nolar = list(args.no)
    toplam_no = None
    if args.firma:
        if not args.tarih or "-" not in args.tarih:
            print("HATA: --firma-faturalari ile --tarih GG/AA/YYYY-GG/AA/YYYY verilmelidir.")
            return 2
        bas, bit = (tarih_cozumle(x.strip()) for x in args.tarih.split("-", 1))
        ayarlar = ayarlari_oku()
        fk = next((Path(a) for a in (args.fatura_klasoru, ayarlar.get("fatura_klasoru"), str(KOK.parent / "luca-bot" / "indirilenler"))
                   if a and (Path(a) / "rapor.json").exists()), None)
        if fk is None:
            print("HATA: rapor.json bulunamadı; --fatura-klasoru verin.")
            return 2
        bulunan = firma_fatura_nolari(fk, args.firma, bas, bit)
        if not bulunan:
            print("HATA: bu firma için seçilen dönemde indirilmiş fatura bulunamadı (rapor.json).")
            return 2
        nolar += bulunan
        toplam_no = len(set(n.upper() for n in nolar))
        print(f"{len(bulunan)} fatura numarası aranacak.")
    try:
        tutarlar = [mk._sayi(t) for t in args.tutar]
    except Exception:
        print("HATA: tutar okunamadı.")
        return 2
    if not (nolar or tutarlar or args.metin):
        print("HATA: en az bir ölçüt verin: --no, --tutar, --metin ya da --firma-faturalari.")
        return 2
    dosyalar = dosyalari_bul(klasor)
    if not dosyalar:
        print(f"HATA: {klasor} altında Muavin / İşletme Defteri Excel'i bulunamadı. Önce Muavin Kontrol'ü çalıştırın.")
        return 1
    print(f"{len(dosyalar)} dosyada aranıyor...")
    sonuc = ara(dosyalar, nolar, tutarlar, args.metin)
    ozet = firma_ozeti(sonuc, toplam_no)
    if not sonuc:
        print("Hiçbir dosyada eşleşme yok. (Aradığınız firmanın Excel'i indirilmemiş olabilir.)")
        return 0
    print("\nFirma özeti (en çok eşleşen üstte):")
    for o in ozet:
        ek = f" / {o['toplam_no']}" if o["toplam_no"] else ""
        print(f"  {o['firma']}: {o['no_sayisi']}{ek} fatura no, {o['satir']} satır")
    yol = excel_yaz(CIKTI / f"muavin-arama-{date.today().isoformat()}.xlsx", sonuc, ozet)
    print(f"\nEXCEL: {yol}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
