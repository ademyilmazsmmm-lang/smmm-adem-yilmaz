#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Indirilen gelen/giden faturalardan Luca muavininde (191 / 391) numarasi OLMAYANLARI bulur; fatura no + tutarla bildirir.
2. sinif (isletme / serbest meslek defteri) firmalarda muavin yoktur: Isletme Defteri Dokumu'nun Giderler/Gelirler tablosuna bakilir.

    python muavin.py --tarih 01/10/2026-31/10/2026 --fatura-klasoru "C:\\...\\luca-bot\\indirilenler"
    python muavin.py --tarih 01/10/2026-31/10/2026 --firma-tam "OSMAN ALEM" --tani

1. sinif (genel muhasebe) her firma icin Luca'da Muavin Defter acilir, 191 ve 391 hesaplari Excel olarak indirilir
(2. sinif firmalarda Isletme Defteri > Raporlar > Genel Raporlar > Isletme Defteri Dokumu Excel'i indirilir);
fatura-klasoru/rapor.json'daki indirilmis alis (191) ve satis (391) faturalarinin NUMARASI muavin satirlarinda aranir;
bulunmayan fatura "eksik"tir; numarasi bulunup genel toplami uyusmayan fatura "tutar uyusmuyor"dur (tarih, no, unvan, KDV, tutar). Sonuc cikti/muavin.json ve cikti/muavin.xlsx'e yazilir
(onceki firmalar korunur). Fatura indirme sekmesi
(luca-bot) once calistirilmis olmalidir; bu program fatura indirmez, Luca'ya yalniz okuma yapar (hicbir sey degistirmez).
"""

import argparse
import signal
import sys
import traceback
from datetime import date
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

import kar_zarar as kz  # noqa: E402  (ortak: giris, musteri listesi onbellegi, ayarlar, tarih cozumleme)
from karzarar import luca_isletme, luca_muavin, muavin_karsilastir as mk  # noqa: E402
from lucabot import konsol  # noqa: E402
from lucabot.firma_listesi import firmalari_suz  # noqa: E402
from lucabot.firma_tablosu import luca_kaydi_bul  # noqa: E402
from lucabot.giris import luca_oturumu_ac  # noqa: E402
from lucabot.luca_ekran import acik_pencereleri_kapat  # noqa: E402
from lucabot.luca_gezinme import donem_ayarla, firma_sec, firma_secici_bekle  # noqa: E402
from lucabot.ortak import AYAR, DURDUR_DOSYASI, ayarlari_oku, gunluge_yaz, yaz  # noqa: E402
from lucabot.tarayici import profil_klasoru, tarayici_ac, tarayiciyi_kapat  # noqa: E402

CIKTI = kz.CIKTI
ARDISIK_HATA_SINIRI = 5
IKINCI_SINIF = ["İşletme Defteri", "Serbest Meslek Defteri"]
EKSIK_GUNLUK_SINIRI = 60      # gunlukte firma basina listelenecek eksik fatura (tumu Excel'de)


def arguman_ayristirici():
    p = argparse.ArgumentParser(description="Luca muavin (191/391) ile indirilen faturalari karsilastir")
    p.add_argument("--tarih", help="Tarih araligi: 01/10/2026-31/10/2026")
    p.add_argument("--baslangic", help="GG/AA/YYYY")
    p.add_argument("--bitis", help="GG/AA/YYYY")
    p.add_argument("--fatura-klasoru", dest="fatura_klasoru",
                   help="Fatura indirme programinin indirilenler klasoru (rapor.json burada); verilmezse ayarlar.json'daki "
                        "fatura_klasoru, o da yoksa ../luca-bot/indirilenler")
    p.add_argument("--firma", action="append", help="Sadece bu firma(lar) (parca eslesir, virgulle ayrilir)")
    p.add_argument("--firma-tam", action="append", dest="firma_tam",
                   help="Sadece bu firma(lar), Luca'daki adla TAM eslesen; birden fazla kez verilebilir")
    p.add_argument("--limit", type=int, help="Ilk N firma ile sinirla")
    p.add_argument("--listeyi-yenile", action="store_true", help="Luca Musteri Listesi'ni yeniden oku")
    p.add_argument("--tani", action="store_true", help="Her adimdan sonra ekran goruntusu + sayfa kaydi (tani/) sakla")
    p.add_argument("--sinif", choices=["1", "2", "hepsi"], default="hepsi",
                   help="Hangi sinif: 1 (muavin 191/391), 2 (isletme defteri dokumu), hepsi. --tum-firmalar ile secilen "
                        "firmalarin hepsi bu sinifta sayilir (hepsi -> 1)")
    p.add_argument("--tum-firmalar", action="store_true",
                   help="Sinif suzgecini ve 'faturasi indirilmis firma' suzgecini kapat (yalniz deneme icin)")
    p.add_argument("--tarayici", choices=["chrome", "edge", "chromium"])
    p.add_argument("--profil-yerel", action="store_true")
    p.add_argument("--chrome-gunlugu", action="store_true")
    p.add_argument("--bitince-kapat", action="store_true", help="Is bitince ENTER beklemeden tarayiciyi kapat")
    return p


def fatura_klasorunu_bul(args, ayarlar):
    adaylar = [args.fatura_klasoru, ayarlar.get("fatura_klasoru"), str(KOK.parent / "luca-bot" / "indirilenler")]
    for a in adaylar:
        if a and (Path(a) / "rapor.json").exists():
            return Path(a)
    return Path(adaylar[0] or adaylar[1] or adaylar[2])


def birinci_sinif_firmalari(page, adaylar, bit, ayarlar, log, yenile=False):
    """Luca'daki firmalardan Musteri Listesi'nde 1. sinif (genel muhasebe) olanlar; liste alinamazsa hepsi."""
    sinif = ayarlar.get("luca_sinifi", kz.LUCA_SINIFI)
    if not sinif:
        return list(adaylar)
    onbellek_yolu = CIKTI / kz.ONBELLEK
    onbellek = {} if yenile else kz.onbellek_oku(onbellek_yolu, bit.year)
    kayitlar = kz._musteri_listesi(page, bit.year, CIKTI / "tani-liste", sinif, log, onbellek, onbellek_yolu)
    acik_pencereleri_kapat(page)
    if not kayitlar:
        yaz(f"UYARI: {sinif} firma listesi alınamadı; muhasebe modülü olmayan firmalar hata verip atlanabilir", log)
        return list(adaylar)
    uygun = [f for f in adaylar if luca_kaydi_bul(f, kayitlar)]
    yaz(f"{sinif}: {len(uygun)} firma; {len(adaylar) - len(uygun)} firma bu listede olmadığı için atlandı "
        "(muavin yalnız genel muhasebe firmalarında olur)", log)
    return uygun


def ikinci_sinif_firmalari(page, adaylar, bit, ayarlar, log, yenile=False):
    """Luca'daki firmalardan Musteri Listesi'nde 2. sinif (isletme / serbest meslek defteri) olanlar."""
    onbellek_yolu = CIKTI / kz.ONBELLEK
    onbellek = {} if yenile else kz.onbellek_oku(onbellek_yolu, bit.year)
    siniflar = ayarlar.get("musteri_sinifi", IKINCI_SINIF)
    kayitlar = []
    for sinif in ([siniflar] if isinstance(siniflar, str) else siniflar):
        kayitlar += kz._musteri_listesi(page, bit.year, CIKTI / "tani-liste", sinif, log, onbellek, onbellek_yolu) or []
    acik_pencereleri_kapat(page)
    if not kayitlar:
        yaz("UYARI: 2. sınıf firma listesi alınamadı (Müşteri Listesi okunamadı)", log)
        return []
    uygun = [f for f in adaylar if luca_kaydi_bul(f, kayitlar)]
    yaz(f"2. sınıf: {len(uygun)} firma (işletme defteri dökümüne bakılacak)", log)
    return uygun


def firma_siniflari(page, firmalar, bit, ayarlar, log, secim, yenile=False):
    """{firma: 1 ya da 2}: 1 = genel muhasebe (muavin 191/391), 2 = isletme/serbest meslek defteri (gider/gelir dokumu).
    Iki listede de olmayan firmalar atlanir; secim '1'/'2' ise yalniz o sinif."""
    siniflar = {}
    if secim in ("1", "hepsi"):
        for f in birinci_sinif_firmalari(page, firmalar, bit, ayarlar, log, yenile):
            siniflar[f] = 1
    if secim in ("2", "hepsi"):
        for f in ikinci_sinif_firmalari(page, [f for f in firmalar if f not in siniflar], bit, ayarlar, log, yenile):
            siniflar[f] = 2
    return {f: siniflar[f] for f in firmalar if f in siniflar}


def faturasi_indirilmis_firmalar(firmalar, fatura_klasoru, bas, bit, log):
    """rapor.json'da bu donemde alis/satis faturasi olan firmalar: {firma: {"alis": [...], "satis": [...]}}."""
    var = {}
    for f in firmalar:
        faturalar = mk.faturalari_oku(fatura_klasoru, f, bas, bit)
        if faturalar["alis"] or faturalar["satis"]:
            var[f] = faturalar
    atlanan = len(firmalar) - len(var)
    yaz(f"{len(var)} firmada dönemde indirilmiş fatura var" + (f"; {atlanan} firmada yok (atlandı)" if atlanan else ""), log)
    return var


def muavin_cek(args, ayarlar, p):
    kz.ayarlari_uygula(args, ayarlar)
    bas, bit = kz.tarih_araligi(args, ayarlar, p)
    bas_m, bit_m = f"{bas:%d/%m/%Y}", f"{bit:%d/%m/%Y}"
    donem = f"{bas_m}-{bit_m}"
    gece_modu = bool(args.bitince_kapat)
    klasor = CIKTI / date.today().isoformat()
    klasor.mkdir(parents=True, exist_ok=True)
    log = klasor / "calisma.log"
    kayit_yolu = CIKTI / mk.DOSYA
    fatura_klasoru = fatura_klasorunu_bul(args, ayarlar)
    konsol.bolum(f"MUAVIN KARSILASTIRMA  {bas_m} - {bit_m}", log)
    if not (fatura_klasoru / "rapor.json").exists():
        yaz(f"HATA: Fatura raporu bulunamadı ({fatura_klasoru / 'rapor.json'}). Önce Fatura İndirme sekmesinden "
            "faturaları indirin ya da --fatura-klasoru verin.", log)
        return 1
    yaz(f"Fatura klasörü: {fatura_klasoru}", log)
    profil = profil_klasoru(log)
    tani = klasor / "tani"
    indirme = klasor / "muavin"
    sonuclar = {}

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = tarayici_ac(pw, profil, log, AYAR["chrome_gunlugu"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page = luca_oturumu_ac(ctx, page, ayarlar, gece_modu, tani, log)
        if page is None:
            tarayiciyi_kapat(ctx)
            return 1
        try:
            _, _, luca_firmalari = firma_secici_bekle(page)
            secim = firmalari_suz(luca_firmalari, ayarlar, args.firma, args.limit, bit, log, tam_adlar=args.firma_tam)
            if not secim.firmalar:
                yaz(f"Işlenecek firma yok: {secim.bos_sebep}.", log)
                return 1
            firmalar = list(secim.firmalar)
            if args.tum_firmalar:
                siniflar = {f: 2 if args.sinif == "2" else 1 for f in firmalar}
                faturalar = {f: mk.faturalari_oku(fatura_klasoru, f, bas, bit) for f in firmalar}
            else:
                siniflar = firma_siniflari(page, firmalar, bit, ayarlar, log, args.sinif, args.listeyi_yenile)
                firmalar = [f for f in firmalar if f in siniflar]
                faturalar = faturasi_indirilmis_firmalar(firmalar, fatura_klasoru, bas, bit, log)
                firmalar = [f for f in firmalar if f in faturalar]
            if not firmalar:
                yaz("Işlenecek firma yok: seçilen dönemde faturası indirilmiş (1. / 2. sınıf) firma bulunamadı.", log)
                return 1
            ardisik = 0
            for i, firma in enumerate(firmalar, 1):
                if page.is_closed():
                    yaz("UYARI: Luca ana penceresi kapandı; kalan firmalar atlandı", log)
                    break
                sinif = siniflar[firma]
                yaz(f"[{i}/{len(firmalar)}] {firma}  " + ("(Luca muavin 191/391)" if sinif == 1 else
                                                          "(Luca işletme defteri dökümü: gider/gelir)"), log)
                try:
                    acik_pencereleri_kapat(page)
                    firma_sec(page, firma, log)
                    if not donem_ayarla(page, firma, bas, bit, log):
                        raise LookupError("firmanın bu döneme uygun çalışma dönemi yok")
                    if sinif == 1:
                        satirlar = luca_muavin.muavin_cek(page, firma, bas, bit, indirme / "dosyalar", tani, log,
                                                          tani_hep=args.tani)
                    else:
                        satirlar = luca_isletme.isletme_cek(page, firma, bas, bit, indirme / "dosyalar", tani, log,
                                                            tani_hep=args.tani)
                    sonuc = mk.firma_sonucu(firma, donem, faturalar[firma], satirlar, kaynak="muavin" if sinif == 1 else "isletme")
                    ardisik = 0
                    a, t = sonuc["yon"]["alis"], sonuc["yon"]["satis"]
                    yer = "muavinde" if sinif == 1 else "defterde"
                    yaz(f"    Alış {a['fatura']} fatura ({a['eslesen']} tamam, {len(a['eksik'])} {yer} yok, "
                        f"{len(a['tutar_farki'])} tutar uyuşmuyor) | Satış {t['fatura']} fatura ({t['eslesen']} tamam, "
                        f"{len(t['eksik'])} {yer} yok, {len(t['tutar_farki'])} tutar uyuşmuyor)", log)
                    sorunlar = [("EKSİK", y, f) for y, d in (("alis", a), ("satis", t)) for f in d["eksik"]] + \
                               [("TUTAR", y, f) for y, d in (("alis", a), ("satis", t)) for f in d["tutar_farki"]]
                    for etiket, y, f in sorunlar[:EKSIK_GUNLUK_SINIRI]:
                        yaz(f"    {etiket}  {mk.eksik_satiri(y, f)}", log)
                    if len(sorunlar) > EKSIK_GUNLUK_SINIRI:
                        yaz(f"    … ve {len(sorunlar) - EKSIK_GUNLUK_SINIRI} fatura daha (hepsi Excel raporunda)", log)
                    yaz(f"  [!!] {firma}: {len(sorunlar)} faturada sorun (fatura no / genel toplam {yer} uyuşmuyor)"
                        if sorunlar else f"  [OK] {firma}: tüm faturalar {yer} var, fatura no ve genel toplam uyuşuyor", log)
                except LookupError as e:
                    ardisik += 1
                    yaz(f"    HATA: {e}", log)
                    sonuc = mk.firma_sonucu(firma, donem, {}, [], hata=str(e)[:300], kaynak="muavin" if sinif == 1 else "isletme")
                except Exception as e:
                    if page.is_closed():
                        raise
                    ardisik += 1
                    yaz(f"    HATA: {type(e).__name__}: {str(e)[:150]}", log)
                    gunluge_yaz("    " + traceback.format_exc().replace("\n", "\n    "), log)
                    sonuc = mk.firma_sonucu(firma, donem, {}, [], hata=type(e).__name__, kaynak="muavin" if sinif == 1 else "isletme")
                sonuclar[firma] = sonuc
                mk.kaydet(kayit_yolu, donem, {firma: sonuc})
                if ardisik >= ARDISIK_HATA_SINIRI:
                    yaz(f"UYARI: Art arda {ardisik} hata; kalan firmalar atlandı", log)
                    break
        finally:
            tarayiciyi_kapat(ctx)
    try:   # Excel, onceki sorgulari da icerir (json birlesik)
        import json
        tum = json.loads(kayit_yolu.read_text(encoding="utf-8")).get("firmalar") or []
        yaz(f"EXCEL RAPOR: {mk.excel_yaz(CIKTI / 'muavin.xlsx', donem, tum)}", log)
    except Exception as e:
        yaz(f"UYARI: Excel yazılamadı ({type(e).__name__}: {e})", log)
    fark = sum(1 for s in sonuclar.values() if s["durum"] == "fark var")
    hatali = sum(1 for s in sonuclar.values() if s["durum"] == "hata")
    yaz(f"[OK] {len(sonuclar)} firma: {len(sonuclar) - fark - hatali} uyumlu, {fark} firmada sorunlu fatura var, {hatali} hata: "
        f"{kayit_yolu}", log)
    return 0 if sonuclar else 1


def _durdurma_sinyali(*_):
    raise KeyboardInterrupt


def main():
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _durdurma_sinyali)
    p = arguman_ayristirici()
    args = p.parse_args()
    ayarlar = ayarlari_oku()
    try:
        DURDUR_DOSYASI.unlink()
    except OSError:
        pass
    try:
        return muavin_cek(args, ayarlar, p)
    except KeyboardInterrupt:
        print("\nKullanici tarafindan durduruldu (o ana kadarki sonuclar kaydedildi).")
        return 130
    except SystemExit:
        raise
    except Exception as e:
        CIKTI.mkdir(parents=True, exist_ok=True)
        gunluge_yaz("BEKLENMEYEN HATA\n" + traceback.format_exc(), CIKTI / "hata.log")
        print(f"\nBEKLENMEYEN HATA: {type(e).__name__}: {e}\nAyrinti: {CIKTI / 'hata.log'}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
