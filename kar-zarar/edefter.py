#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""e-Defter gondermeden once Luca'da kontrol: e-Defter kapsaminda UYUMSUZ fisleri bulur (Luca'da hicbir sey degistirilmez).

    python edefter.py --tarih 01/10/2026-31/10/2026
    python edefter.py --tarih 01/10/2026-31/10/2026 --firma-tam "OSMAN ALEM" --tani

Her 1. sinif (genel muhasebe) firma icin Luca'da Muhasebe > Fis Islemleri > Duzenleme > Toplu Belge Turu ve Odeme Yontemi
Duzenleme ekrani acilir; "E-Defter kapsaminda uyumsuz olan fisleri getir" ile listedeki her e-Defter hata kodu (20041, 20042,
20044-20048) icin Listele'ye basilir ve acilan "E-Defter Uyumsuz Fisleri Duzenleme" listesi okunur. Sonuc cikti/edefter.json ve
cikti/edefter.xlsx'e yazilir (onceki firmalar korunur). VARSAYILAN: hicbir sey degistirilmez (Kaydet / Toplu Deger Ata'ya basilmaz).

    python edefter.py --tarih 01/10/2026-31/10/2026 --firma-tam "OSMAN ALEM" --duzelt --tani

--duzelt (YALNIZ acikca istenirse): 20042-20045 kodlarinda fatura OLMAYAN uyumsuz fisler (191/391/6xx/7xx/15x/25x/26x hesabi
olmayan: kasa, banka, cari mahsup) icin Toplu Deger Ata ile Belge Turu = MF ve evrak no = degismez fis no atanir (Aktar'lar),
sonra Kaydet'e basilir (satir satir kaydin bitmesi beklenir); liste yeniden okunup dogrulanir. Fatura fislerine dokunulmaz.
20026 (detaysiz fis, Fis Listesi): fisler secilip alttaki Sil'e basilir.
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
import muavin as mv  # noqa: E402  (1. sinif firma suzgeci ve onbellek yolu)
from karzarar import edefter_kontrol as ek, luca_edefter  # noqa: E402
from lucabot import hesaplar, konsol  # noqa: E402
from lucabot.firma_listesi import firmalari_suz  # noqa: E402
from lucabot.giris import luca_oturumu_ac  # noqa: E402
from lucabot.hesaplar import gorunen_ad, profil_eki as hesap_profil_eki  # noqa: E402
from lucabot.luca_ekran import acik_pencereleri_kapat  # noqa: E402
from lucabot.luca_gezinme import donem_ayarla, firma_sec, firma_secici_bekle  # noqa: E402
from lucabot.ortak import AYAR, DURDUR_DOSYASI, ayarlari_oku, gunluge_yaz, yaz  # noqa: E402
from lucabot.tarayici import profil_klasoru, tarayici_ac, tarayiciyi_kapat  # noqa: E402

CIKTI = kz.CIKTI
ARDISIK_HATA_SINIRI = 6
GUNLUK_FIS_SINIRI = 12     # gunlukte kod basina listelenecek fis (tumu Excel'de)


def arguman_ayristirici():
    p = argparse.ArgumentParser(description="e-Defter oncesi Luca kontrolu: uyumsuz fisleri bul")
    p.add_argument("--tarih", help="Tarih araligi (fis tarihi): 01/10/2026-31/10/2026")
    p.add_argument("--baslangic", help="GG/AA/YYYY")
    p.add_argument("--bitis", help="GG/AA/YYYY")
    p.add_argument("--firma", action="append", help="Sadece bu firma(lar) (parca eslesir, virgulle ayrilir)")
    p.add_argument("--firma-tam", action="append", dest="firma_tam",
                   help="Sadece bu firma(lar), Luca'daki adla TAM eslesen; birden fazla kez verilebilir")
    p.add_argument("--limit", type=int, help="Ilk N firma ile sinirla")
    p.add_argument("--hata-kodu", action="append", dest="hata_kodlari",
                   help="Yalniz bu e-Defter hata kodu (orn. 20041); birden fazla kez verilebilir (varsayilan: listedeki hepsi)")
    p.add_argument("--listeyi-yenile", action="store_true", help="Luca Musteri Listesi'ni yeniden oku")
    p.add_argument("--duzelt", action="store_true",
                   help="DIKKAT: Luca'ya YAZAR. Fatura olmayan uyumsuz fislere MF + evrak no atar ve Kaydet'e basar (yalniz 20042-20045)")
    p.add_argument("--tani", action="store_true", help="Her adimdan sonra ekran goruntusu + sayfa kaydi (tani/) sakla")
    p.add_argument("--hesap", default="hepsi",
                   help="Hangi Luca hesabi: hepsi (once ofis, sonra etkinse isletme), ofis ya da isletme "
                        "(ayarlar.json: ikinci_hesap)")
    p.add_argument("--tum-firmalar", action="store_true", help="1. sinif suzgecini kapat (yalniz deneme icin)")
    p.add_argument("--tarayici", choices=["chrome", "edge", "chromium"])
    p.add_argument("--profil-yerel", action="store_true")
    p.add_argument("--chrome-gunlugu", action="store_true")
    p.add_argument("--bitince-kapat", action="store_true", help="Is bitince ENTER beklemeden tarayiciyi kapat")
    return p


def firma_logu(s, log):
    """Bir firmanin sonucunu gunluge yazar: kod basina sayi ve ilk fisler."""
    for kod, ad, adet in ek.sorunlu_kodlar(s):
        yaz(f"    UYUMSUZ  {kod}  {ad}: {adet} fiş", log)
    for h in s["hatalar"]:
        for f in (h.get("fisler") or [])[:GUNLUK_FIS_SINIRI]:
            yaz(f"      {h['kod']}  {ek.fis_satiri(f)}", log)
        if h.get("fis_sayisi", 0) > GUNLUK_FIS_SINIRI:
            yaz(f"      {h['kod']}  … ve {h['fis_sayisi'] - GUNLUK_FIS_SINIRI} fiş daha (hepsi Excel raporunda)", log)
    for kod, hata in ek.taranamayanlar(s):
        yaz(f"    UYARI: {kod} taranamadı: {hata[:200]}", log)
    for kod, d in ek.duzeltmeler(s):
        yaz(f"    DÜZELTME {kod}: {ek.duzeltme_yazisi(d)}", log)


def birinci_sinif_suz(page, firmalar, bit, ayar_h, args, log, sira):
    """Yalniz 1. sinif (genel muhasebe) firmalar kontrol edilir. Firma adi elle verildiyse ve kayitli sinif listesinde yoksa
    (liste eski olabilir) liste bir kez Luca'dan yeniden cekilip tekrar bakilir; hala yoksa 1. sinif degildir, atlanir."""
    neden = "e-Defter yalnız genel muhasebe (1. sınıf) firmalarında olur"
    birinci = mv.birinci_sinif_firmalari(page, firmalar, bit, ayar_h, log, args.listeyi_yenile, sira, neden=neden)
    if (args.firma or args.firma_tam) and not args.listeyi_yenile and any(f not in birinci for f in firmalar):
        yaz("Firma kayıtlı 1. sınıf listesinde yok: liste eski olabilir, Luca'dan yeniden çekiliyor", log)
        birinci = mv.birinci_sinif_firmalari(page, firmalar, bit, ayar_h, log, True, sira, neden=neden)
    atlanan = [f for f in firmalar if f not in birinci]
    if atlanan and (args.firma or args.firma_tam):
        yaz("1. sınıf olmadığı için atlandı: " + ", ".join(atlanan), log)
    return [f for f in firmalar if f in birinci]


def hesabi_isle(pw, sira, hesap_adi, ayar_h, args, ayarlar, log, tani, bas, bit, donem, gece_modu, kayit_yolu, islenen, coklu):
    """Bir Luca hesabinin (ofis / isletme) 1. sinif firmalarini tarar; {firma: sonuc}."""
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
        if not args.tum_firmalar and firmalar:
            firmalar = birinci_sinif_suz(page, firmalar, bit, ayar_h, args, log, sira)
        if not firmalar:
            yaz("Işlenecek firma yok: seçilen firmalar arasında 1. sınıf (genel muhasebe) firma bulunamadı "
                "(Müşteri Listesi alınamadıysa 'Firma listesini Luca'dan yeniden çek' ya da --tum-firmalar ile deneyin).", log)
            return sonuclar
        ardisik = 0
        for i, firma in enumerate(firmalar, 1):
            if page.is_closed():
                yaz("UYARI: Luca ana penceresi kapandı; kalan firmalar atlandı", log)
                break
            yaz(f"[{i}/{len(firmalar)}] {firma}  " + (f"[{gorunen_ad(hesap_adi)}] " if coklu else "") + "(e-Defter kontrolü)", log)
            try:
                acik_pencereleri_kapat(page)
                firma_sec(page, firma, log)
                if not donem_ayarla(page, firma, bas, bit, log):
                    raise LookupError("firmanın bu döneme uygun çalışma dönemi yok")
                hatalar = luca_edefter.edefter_tara(page, firma, bas, bit, tani, log, tani_hep=args.tani,
                                                    kodlar=set(args.hata_kodlari) if args.hata_kodlari else None,
                                                    duzelt=args.duzelt)
                sonuc = ek.firma_sonucu(firma, donem, hatalar)
                ardisik = 0 if sonuc["durum"] != "hata" else ardisik + 1
                firma_logu(sonuc, log)
                toplam = ek.sorun_sayisi(sonuc)
                yaz(f"  [!!] {firma}: {toplam} uyumsuz fiş ({len(ek.sorunlu_kodlar(sonuc))} hata kodunda) - e-Defter göndermeden önce düzeltin"
                    if sonuc["durum"] == "sorun var" else
                    f"  [OK] {firma}: e-Defter kapsamında uyumsuz fiş yok" if sonuc["durum"] == "tamam" else
                    f"  [??] {firma}: kontrol tamamlanamadı (yukarıdaki UYARI satırlarına bakın)", log)
            except LookupError as e:
                ardisik += 1
                yaz(f"    HATA: {e}", log)
                sonuc = ek.firma_sonucu(firma, donem, [], hata=str(e)[:300])
            except Exception as e:
                if page.is_closed():
                    raise
                ardisik += 1
                yaz(f"    HATA: {type(e).__name__}: {str(e)[:150]}", log)
                gunluge_yaz("    " + traceback.format_exc().replace("\n", "\n    "), log)
                sonuc = ek.firma_sonucu(firma, donem, [], hata=type(e).__name__)
            islenen.add(firma)
            if coklu:
                sonuc["hesap"] = gorunen_ad(hesap_adi)
            sonuclar[firma] = sonuc
            ek.kaydet(kayit_yolu, donem, {firma: sonuc})
            if ardisik >= ARDISIK_HATA_SINIRI:
                yaz(f"UYARI: Art arda {ardisik} hata; kalan firmalar atlandı", log)
                break
    finally:
        tarayiciyi_kapat(ctx)
    return sonuclar


def edefter_kontrol(args, ayarlar, p):
    kz.ayarlari_uygula(args, ayarlar)
    bas, bit = kz.tarih_araligi(args, ayarlar, p)
    bas_m, bit_m = f"{bas:%d/%m/%Y}", f"{bit:%d/%m/%Y}"
    donem = f"{bas_m}-{bit_m}"
    gece_modu = bool(args.bitince_kapat)
    klasor = CIKTI / date.today().isoformat()
    klasor.mkdir(parents=True, exist_ok=True)
    log = klasor / "calisma.log"
    kayit_yolu = CIKTI / ek.DOSYA
    konsol.bolum(f"E-DEFTER ÖN KONTROL  {bas_m} - {bit_m}", log)
    try:
        hesap_listesi = hesaplar.hesaplar(ayarlar, args.hesap)
    except ValueError as e:
        yaz(f"HATA: {e}", log)
        return 1
    coklu = len(hesap_listesi) > 1
    if coklu:
        yaz("Luca hesapları (sırayla): " + " -> ".join(gorunen_ad(ad) for ad, _ in hesap_listesi), log)
    tani = klasor / "tani"
    sonuclar = {}
    islenen = set()          # bir firma iki hesapta da gorunurse ilk hesapta islenir

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        for sira, (hesap_adi, ayar_h) in enumerate(hesap_listesi):
            if coklu:
                konsol.bolum(f"LUCA HESABI {sira + 1}/{len(hesap_listesi)}: {gorunen_ad(hesap_adi).upper()}", log)
            sonuclar.update(hesabi_isle(pw, sira, hesap_adi, ayar_h, args, ayarlar, log, tani, bas, bit, donem, gece_modu,
                                        kayit_yolu, islenen, coklu))
    if kayit_yolu.exists():   # hic firma islenmediyse yazilacak sonuc da yoktur
        try:   # Excel, onceki sorgulari da icerir (json birlesik)
            import json
            tum = json.loads(kayit_yolu.read_text(encoding="utf-8")).get("firmalar") or []
            yaz(f"EXCEL RAPOR: {ek.excel_yaz(CIKTI / 'edefter.xlsx', donem, tum)}", log)
        except Exception as e:
            yaz(f"UYARI: Excel yazılamadı ({type(e).__name__}: {e})", log)
    if not sonuclar:
        yaz("Hiç firma işlenmedi (günlükte yukarıdaki 'Işlenecek firma yok' / TANI satırlarına bakın).", log)
        return 1
    sorun = sum(1 for s in sonuclar.values() if s["durum"] == "sorun var")
    hatali = sum(1 for s in sonuclar.values() if s["durum"] == "hata")
    yaz(f"[OK] {len(sonuclar)} firma: {len(sonuclar) - sorun - hatali} gönderilebilir, {sorun} firmada uyumsuz fiş var, "
        f"{hatali} kontrol tamamlanamadı: {kayit_yolu}", log)
    return 0


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
        return edefter_kontrol(args, ayarlar, p)
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
