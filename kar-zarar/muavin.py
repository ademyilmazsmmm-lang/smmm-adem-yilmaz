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
from lucabot import hesaplar, konsol  # noqa: E402
from lucabot.firma_listesi import firmalari_suz  # noqa: E402
from lucabot.firma_tablosu import luca_kaydi_bul  # noqa: E402
from lucabot.giris import luca_oturumu_ac  # noqa: E402
from lucabot.luca_ekran import acik_pencereleri_kapat  # noqa: E402
from lucabot.luca_gezinme import donem_ayarla, firma_sec, firma_secici_bekle  # noqa: E402
from lucabot.ortak import AYAR, DURDUR_DOSYASI, ayarlari_oku, gunluge_yaz, yaz  # noqa: E402
from lucabot.hesaplar import gorunen_ad, profil_eki as hesap_profil_eki  # noqa: E402
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
    p.add_argument("--hesap", default="hepsi",
                   help="Hangi Luca hesabi: hepsi (once ofis, sonra etkinse isletme), ofis ya da isletme "
                        "(ayarlar.json: ikinci_hesap)")
    p.add_argument("--sinif", choices=["1", "2", "hepsi", "otomatik"], default="hepsi",
                   help="Hangi sinif: 1 (muavin 191/391), 2 (isletme defteri dokumu), hepsi. --tum-firmalar ile secilen "
                        "firmalarin hepsi bu sinifta sayilir (hepsi -> 1; otomatik -> ekrandan belirlenir)")
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


def onbellek_yolu(sira=0):
    """Musteri listesi onbellegi: her Luca hesabinin firmalari/siniflari farklidir (ikinci hesap ayri dosya)."""
    yol = CIKTI / kz.ONBELLEK
    return yol if not sira else yol.with_name(f"{yol.stem}-hesap{sira + 1}{yol.suffix}")


def eslesme_tanisi(adaylar, kayitlar, log):
    """Hic firma sinif listesiyle eslesmediyse: iki taraftan ad ornekleri (adlarin bicimi tutmuyor olabilir)."""
    ornek = lambda liste: ", ".join(f"'{x}'" for x in liste[:3])
    kayit_adlari = [str(k.get("ad") or k.get("unvan") or "") for k in kayitlar if isinstance(k, dict)]
    yaz(f"    TANI: eşleşme yok. Firma adı örnekleri: {ornek(list(adaylar))} | Müşteri listesi adı örnekleri: {ornek(kayit_adlari)}. "
        "Liste eski/başka hesaptan kalmış olabilir: sekmede 'Firma listesini Luca'dan yeniden çek'i işaretleyip tekrar çalıştırın.", log)


def birinci_sinif_firmalari(page, adaylar, bit, ayarlar, log, yenile=False, sira=0):
    """Luca'daki firmalardan Musteri Listesi'nde 1. sinif (genel muhasebe) olanlar; liste alinamazsa hepsi."""
    sinif = ayarlar.get("luca_sinifi", kz.LUCA_SINIFI)
    if not sinif:
        return list(adaylar)
    yol = onbellek_yolu(sira)
    onbellek = {} if yenile else kz.onbellek_oku(yol, bit.year)
    kayitlar = kz._musteri_listesi(page, bit.year, CIKTI / "tani-liste", sinif, log, onbellek, yol)
    acik_pencereleri_kapat(page)
    if not kayitlar:
        yaz(f"UYARI: {sinif} firma listesi alınamadı; bu firmaların sınıfı ekran açılarak otomatik belirlenecek", log)
        return []
    uygun = [f for f in adaylar if luca_kaydi_bul(f, kayitlar)]
    if adaylar and not uygun:
        eslesme_tanisi(adaylar, kayitlar, log)
    yaz(f"{sinif}: {len(uygun)} firma; {len(adaylar) - len(uygun)} firma bu listede olmadığı için atlandı "
        "(muavin yalnız genel muhasebe firmalarında olur)", log)
    return uygun


def ikinci_sinif_firmalari(page, adaylar, bit, ayarlar, log, yenile=False, sira=0):
    """Luca'daki firmalardan Musteri Listesi'nde 2. sinif (isletme / serbest meslek defteri) olanlar."""
    yol = onbellek_yolu(sira)
    onbellek = {} if yenile else kz.onbellek_oku(yol, bit.year)
    siniflar = ayarlar.get("musteri_sinifi", IKINCI_SINIF)
    kayitlar = []
    for sinif in ([siniflar] if isinstance(siniflar, str) else siniflar):
        kayitlar += kz._musteri_listesi(page, bit.year, CIKTI / "tani-liste", sinif, log, onbellek, yol) or []
    acik_pencereleri_kapat(page)
    if not kayitlar:
        yaz("UYARI: 2. sınıf firma listesi alınamadı (Müşteri Listesi okunamadı)", log)
        return []
    uygun = [f for f in adaylar if luca_kaydi_bul(f, kayitlar)]
    if adaylar and not uygun:
        eslesme_tanisi(adaylar, kayitlar, log)
    yaz(f"2. sınıf: {len(uygun)} firma (işletme defteri dökümüne bakılacak)", log)
    return uygun


def firma_siniflari(page, firmalar, bit, ayarlar, log, secim, yenile=False, sira=0):
    """{firma: 0, 1 ya da 2}: 1 = genel muhasebe (muavin 191/391), 2 = isletme/serbest meslek defteri (gider/gelir dokumu),
    0 = sinif listelerinde adi eslesmeyen firma (faturasi Fatura Indirme'de var): ekran acilarak otomatik belirlenir
    (once Muavin Defter, yoksa Isletme Defteri Dokumu). secim '1'/'2' ise yalniz o sinifa eslesenler."""
    siniflar = {}
    if secim in ("1", "hepsi"):
        for f in birinci_sinif_firmalari(page, firmalar, bit, ayarlar, log, yenile, sira):
            siniflar[f] = 1
    if secim in ("2", "hepsi"):
        for f in ikinci_sinif_firmalari(page, [f for f in firmalar if f not in siniflar], bit, ayarlar, log, yenile, sira):
            siniflar[f] = 2
    if secim == "hepsi":
        bilinmeyen = [f for f in firmalar if f not in siniflar]
        if bilinmeyen:
            yaz(f"{len(bilinmeyen)} firmanın sınıfı listelerde eşleşmedi: ekran açılarak otomatik belirlenecek (önce Muavin Defter, "
                "yoksa İşletme Defteri Dökümü)", log)
        return {f: siniflar.get(f, 0) for f in firmalar}
    return {f: siniflar[f] for f in firmalar if f in siniflar}


def otomatik_cek(birinci, ikinci, log=None):
    """Sinifi bilinmeyen firma: birinci() (Muavin Defter) denenir, ekran/form yoksa ikinci() (Isletme Defteri Dokumu).
    (satirlar, sinif) dondurur; ikisi de basarisizsa iki nedeni de tasiyan LookupError."""
    try:
        return birinci(), 1
    except LookupError as e1:
        yaz(f"    Muavin Defter açılamadı ({str(e1)[:100]}); İşletme Defteri Dökümü deneniyor", log)
        try:
            return ikinci(), 2
        except LookupError as e2:
            raise LookupError(f"Muavin Defter ({str(e1)[:110]}) ve İşletme Defteri Dökümü ({str(e2)[:110]}) açılamadı")


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


def hesabi_isle(pw, sira, hesap_adi, ayar_h, args, ayarlar, log, tani, indirme, fatura_klasoru, bas, bit, donem, gece_modu,
                kayit_yolu, islenen, coklu):
    """Bir Luca hesabinin (ofis / isletme) firmalarini isler; {firma: sonuc}. Hesap kendi tarayici profili ve girisiyle acilir."""
    sonuclar = {}
    ctx = tarayici_ac(pw, profil_klasoru(log, hesap_profil_eki(sira)), log, AYAR["chrome_gunlugu"])
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page = luca_oturumu_ac(ctx, page, ayar_h, gece_modu, tani, log)
    if page is None:
        tarayiciyi_kapat(ctx)
        return sonuclar
    try:
        _, _, luca_firmalari = firma_secici_bekle(page)
        secim = firmalari_suz(luca_firmalari, ayar_h, args.firma, args.limit, bit, log, tam_adlar=args.firma_tam)
        if not secim.firmalar:
            yaz(f"Işlenecek firma yok: {secim.bos_sebep}.", log)
            return sonuclar
        firmalar = [f for f in secim.firmalar if f not in islenen]
        if args.tum_firmalar:
            siniflar = {f: {"2": 2, "otomatik": 0}.get(args.sinif, 1) for f in firmalar}
            faturalar = {f: mk.faturalari_oku(fatura_klasoru, f, bas, bit) for f in firmalar}
        else:
            faturalar = faturasi_indirilmis_firmalar(firmalar, fatura_klasoru, bas, bit, log)   # firmalar Fatura Indirme'de var
            firmalar = [f for f in firmalar if f in faturalar]
            siniflar = firma_siniflari(page, firmalar, bit, ayar_h, log, args.sinif, args.listeyi_yenile, sira) if firmalar else {}
            firmalar = [f for f in firmalar if f in siniflar]
        if not firmalar:
            yaz("Işlenecek firma yok: seçilen dönemde faturası indirilmiş (1. / 2. sınıf) firma bulunamadı.", log)
            return sonuclar
        ardisik = 0
        for i, firma in enumerate(firmalar, 1):
            if page.is_closed():
                yaz("UYARI: Luca ana penceresi kapandı; kalan firmalar atlandı", log)
                break
            sinif = siniflar[firma]
            yaz(f"[{i}/{len(firmalar)}] {firma}  " + (f"[{gorunen_ad(hesap_adi)}] " if coklu else "") +
                ("(Luca muavin 191/391)" if sinif == 1 else "(Luca işletme defteri dökümü: gider/gelir)" if sinif == 2
                 else "(sınıf otomatik: Muavin Defter / İşletme Defteri Dökümü)"), log)
            try:
                acik_pencereleri_kapat(page)
                firma_sec(page, firma, log)
                if not donem_ayarla(page, firma, bas, bit, log):
                    raise LookupError("firmanın bu döneme uygun çalışma dönemi yok")
                muavin_fn = lambda: luca_muavin.muavin_cek(page, firma, bas, bit, indirme / "dosyalar", tani, log,
                                                           tani_hep=args.tani)
                isletme_fn = lambda: luca_isletme.isletme_cek(page, firma, bas, bit, indirme / "dosyalar", tani, log,
                                                              tani_hep=args.tani)
                if sinif == 1:
                    satirlar = muavin_fn()
                elif sinif == 2:
                    satirlar = isletme_fn()
                else:
                    satirlar, sinif = otomatik_cek(muavin_fn, isletme_fn, log)
                    yaz(f"    Sınıf belirlendi: {'1. sınıf (muavin)' if sinif == 1 else '2. sınıf (işletme defteri)'}", log)
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
            islenen.add(firma)
            if coklu:
                sonuc["hesap"] = gorunen_ad(hesap_adi)
            sonuclar[firma] = sonuc
            mk.kaydet(kayit_yolu, donem, {firma: sonuc})
            if ardisik >= ARDISIK_HATA_SINIRI:
                yaz(f"UYARI: Art arda {ardisik} hata; kalan firmalar atlandı", log)
                break
    finally:
        tarayiciyi_kapat(ctx)
    return sonuclar



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
    try:
        hesap_listesi = hesaplar.hesaplar(ayarlar, args.hesap)
    except ValueError as e:
        yaz(f"HATA: {e}", log)
        return 1
    coklu = len(hesap_listesi) > 1
    if coklu:
        yaz("Luca hesapları (sırayla): " + " -> ".join(gorunen_ad(ad) for ad, _ in hesap_listesi), log)
    tani = klasor / "tani"
    indirme = klasor / "muavin"
    sonuclar = {}
    islenen = set()          # bir firma iki hesapta da gorunurse ilk hesapta islenir

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        for sira, (hesap_adi, ayar_h) in enumerate(hesap_listesi):
            if coklu:
                konsol.bolum(f"LUCA HESABI {sira + 1}/{len(hesap_listesi)}: {gorunen_ad(hesap_adi).upper()}", log)
            sonuc_hesap = hesabi_isle(pw, sira, hesap_adi, ayar_h, args, ayarlar, log, tani, indirme, fatura_klasoru, bas, bit,
                                      donem, gece_modu, kayit_yolu, islenen, coklu)
            sonuclar.update(sonuc_hesap)
    if kayit_yolu.exists():   # hic firma islenmediyse yazilacak sonuc da yoktur
        try:   # Excel, onceki sorgulari da icerir (json birlesik)
            import json
            tum = json.loads(kayit_yolu.read_text(encoding="utf-8")).get("firmalar") or []
            yaz(f"EXCEL RAPOR: {mk.excel_yaz(CIKTI / 'muavin.xlsx', donem, tum)}", log)
        except Exception as e:
            yaz(f"UYARI: Excel yazılamadı ({type(e).__name__}: {e})", log)
    fark = sum(1 for s in sonuclar.values() if s["durum"] == "fark var")
    hatali = sum(1 for s in sonuclar.values() if s["durum"] == "hata")
    if not sonuclar:
        yaz("Hiç firma işlenmedi (günlükte yukarıdaki 'Işlenecek firma yok' / TANI satırlarına bakın).", log)
        return 1
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
