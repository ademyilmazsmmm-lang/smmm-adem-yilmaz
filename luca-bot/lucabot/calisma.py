# -*- coding: utf-8 -*-
"""Tum firmalari sirayla isleyen ana dongu.

Dayaniklilik kurallari:
  * Bir EKRANDA hata olursa ekran goruntusu kaydedilir, hata o ekranin
    sonucuna yazilir ve firmanin sonraki ekranina gecilir.
  * Firma secilemezse ya da ayni firmada ust uste 2 ekran hata verirse o
    firma birakilip siradakine gecilir.
  * Tarayici cokerse (sayfa kapanirsa) once acik kalan Luca sekmesine
    gecilir, o da yoksa tarayici yeniden acilir ve firma, kalan ekranlariyla
    birlikte en fazla COKME_DENEMESI kez yeniden denenir.
  * Ust uste 2 firma basarisiz olursa Luca oturumu yenilenir; hata_siniri
    kadar firma ust uste basarisiz olursa calisma durdurulur.
  * Ctrl+C ile durdurulursa o ana kadarki durum ve rapor kaydedilir.
  * Her firmadan sonra ozet.csv, rapor.json ve rapor.xlsx guncellenir; gece
    yarida kalan calisma ayni gun kaldigi yerden surdurulebilir.
"""

import traceback
from dataclasses import dataclass, field

from . import konsol, rapor
from .bekleme import sayfa_canli
from .ekran_isleyici import FirmaSecilemedi, firma_isle
from .giris import giris_bilgileri, luca_oturumu_ac, oturumu_yenile
from .luca_ekran import hata_kaydet, sayfayi_toparla
from .ortak import gunluge_yaz, yaz, yeni_sonuc
from .sabitler import BELGE_TIPLERI, COKME_DENEMESI
from .tarayici import sayfayi_kurtar, tarayiciyi_yeniden_baslat

EKRAN_HATA_SINIRI = 2  # ayni firmada ust uste bu kadar ekran hata verirse firma birakilir


class TarayiciGitti(Exception):
    """Tarayici kapandi ve yeniden acilamadi; calisma devam edemez."""


@dataclass
class CalismaOzeti:
    firma: int = 0
    ekran: int = 0
    basarili: int = 0
    bos: int = 0
    atlanan: int = 0
    sorunlu: int = 0
    fatura: int = 0
    tevkifat: int = 0
    iptal: int = 0
    sure: float = 0
    sorunlu_liste: list = field(default_factory=list)
    durduruldu: str = ""  # bos degilse calisma neden yarida kaldi


def ozetle(sonuclar, sure=0):
    """Ekran sonuclarindan son ozet. Ortusen ekranlarda fatura sayisi cifte sayilmaz."""
    oz = CalismaOzeti(sure=sure, ekran=len(sonuclar))
    # ortusen gruplarindan (bkz. rapor.ORTUSEN_GRUPLARI) yalnizca en yuksek sayi
    # alinir, geri kalan ekranlar ayri belgeler oldugu icin toplanir
    grup_basi, tevkifat, iptal = {}, {}, {}

    def en_yuksek(sozluk, anahtar, deger):
        sozluk[anahtar] = max(sozluk.get(anahtar, 0), deger or 0)

    for s in sonuclar:
        anahtar = (s["firma"], rapor.ortusen_grubu(s.get("belge_tipi", "")))
        en_yuksek(grup_basi, anahtar, s.get("fatura_sayisi"))
        if s.get("belge_tipi") in rapor.TEVKIFAT_EKRANLARI:
            en_yuksek(tevkifat, anahtar, s.get("tevkifat"))
        en_yuksek(iptal, anahtar, s.get("iptal_itiraz"))
        durum = s.get("durum", "")
        if durum.startswith("tamam"):
            oz.basarili += 1
        elif durum == "fatura yok":
            oz.bos += 1
        elif durum.startswith("atlandi") or durum == "donem disi":
            oz.atlanan += 1
        else:
            oz.sorunlu += 1
            ad = BELGE_TIPLERI.get(s.get("belge_tipi"), s.get("belge_tipi", ""))
            oz.sorunlu_liste.append(f"{s['firma']} / {ad}: {durum}"
                                    + (f" - {s['not']}" if s.get("not") else ""))
    oz.firma = len({f for f, _ in grup_basi})
    oz.fatura = sum(grup_basi.values())
    oz.tevkifat = sum(tevkifat.values())
    oz.iptal = sum(iptal.values())
    return oz


class Calisma:
    def __init__(self, pw, ctx, page, profil, ayarlar, secim, belge_tipleri, araliklar,
                 klasor, log, azami_deneme=3, hata_siniri=5, bugun_tamam=None):
        self.pw = pw
        self.ctx = ctx
        self.page = page
        self.profil = profil
        self.ayarlar = ayarlar
        self.firmalar = secim.firmalar
        self.atlanan_ekranlar = secim.atlanan_ekranlar
        self.belge_tipleri = belge_tipleri
        self.araliklar = araliklar
        self.klasor = klasor
        self.log = log
        self.azami_deneme = azami_deneme
        self.hata_siniri = hata_siniri
        self.bugun_tamam = bugun_tamam or {}

        # (firma, belge tipi) -> sonuc. Ayni ekran yeniden denenirse son sonuc gecerli olur.
        self._sonuclar = {}
        self.ardisik_hata = 0
        self.ilerleme = konsol.Ilerleme(len(self.firmalar))

    @property
    def sonuclar(self):
        return list(self._sonuclar.values())

    # --- kayit -----------------------------------------------------------

    def _sonuc_ekle(self, sonuc):
        self._sonuclar[(sonuc["firma"], sonuc["belge_tipi"])] = sonuc

    def durumu_kaydet(self, kalanlar):
        """ozet.csv + rapor.json/xlsx; yazilamazsa calisma durmaz."""
        try:
            rapor.ozet_csv_yaz(self.klasor / "ozet.csv", self.klasor / "kalan-firmalar.txt",
                               self.sonuclar, kalanlar, self.belge_tipleri[0])
        except Exception as e:
            yaz(f"    UYARI: ozet.csv yazilamadi ({type(e).__name__}: {e})", self.log)
        try:
            rapor.guncelle(self.klasor, self.sonuclar, kalanlar, self.belge_tipleri[0])
        except PermissionError:
            yaz("    UYARI: rapor.xlsx yazilamadi - dosya Excel'de acik olabilir, kapatin"
                " (bir sonraki firmada tekrar denenecek)", self.log)
        except Exception as e:
            yaz(f"    UYARI: rapor guncellenemedi ({type(e).__name__}: {e})", self.log)

    def _hatayi_yaz(self, firma, tip, e):
        """Hatayi ekranin sonucuna yazar, ekran goruntusu ve ayrintili iz kaydeder."""
        yaz(f"    HATA ({BELGE_TIPLERI.get(tip, tip)}): {type(e).__name__}: {e}", self.log)
        gunluge_yaz("    " + traceback.format_exc().replace("\n", "\n    "), self.log)
        sonuc = yeni_sonuc(firma, tip)
        sonuc["durum"] = f"hata: {type(e).__name__}"
        sonuc["not"] = str(e).splitlines()[0][:160] if str(e) else type(e).__name__
        if sayfa_canli(self.page):
            sonuc["ekran_goruntusu"] = hata_kaydet(self.page, self.klasor / "hatalar",
                                                   f"{firma} - {tip}")
        self._sonuc_ekle(sonuc)
        konsol.ekran_sonucu(sonuc, self.log)

    # --- tarayici --------------------------------------------------------

    def _sayfa_hazirla(self):
        """Sayfa olduyse once acik sekmeye gecer, o da yoksa tarayiciyi yeniden acar."""
        if sayfa_canli(self.page):
            return
        yeni = sayfayi_kurtar(self.ctx, self.log)
        if sayfa_canli(yeni):
            self.page = yeni
            return
        yeni_ctx, yeni = tarayiciyi_yeniden_baslat(self.pw, self.profil, self.ctx, self.log)
        if yeni_ctx is not None:
            self.ctx = yeni_ctx
        if yeni_ctx is not None and not sayfa_canli(yeni) and giris_bilgileri(self.ayarlar):
            # profilde oturum kalmamis: ayarlar.json'daki bilgilerle yeniden giris yapilir
            yaz("Luca'ya otomatik olarak yeniden giris yapiliyor...", self.log)
            try:
                sayfa = yeni_ctx.pages[0] if yeni_ctx.pages else yeni_ctx.new_page()
                yeni = luca_oturumu_ac(yeni_ctx, sayfa, self.ayarlar, True,
                                       self.klasor / "tani", self.log)
            except Exception as e:
                yaz(f"Yeniden giris yapilamadi ({type(e).__name__}: {e})", self.log)
                yeni = None
        if yeni_ctx is None or not sayfa_canli(yeni):
            raise TarayiciGitti()
        self.page = yeni

    # --- firma -----------------------------------------------------------

    def _islenecek_ekranlar(self, firma):
        atlanacak = self.atlanan_ekranlar.get(firma, set())
        tamamlanmis = self.bugun_tamam.get(firma, set())
        ekranlar = []
        for tip in self.belge_tipleri:
            if tip in atlanacak:  # firmalar.xlsx'te X isaretli ekran
                yaz(f"  -- {BELGE_TIPLERI[tip]}: listede atlanmis", self.log)
            elif tip in tamamlanmis:  # yarida kalan calismadan zaten tamamlanmis
                yaz(f"  -- {BELGE_TIPLERI[tip]}: bugun tamamlanmis, atlaniyor", self.log)
            else:
                ekranlar.append(tip)
        return ekranlar

    def _ekranlari_isle(self, firma, ekranlar, biten):
        """Firmanin ekranlarini sirayla isler; en az bir ekran sonuc verdiyse True.

        Tarayici kapanirsa (sayfa oldu) hatayi yukari firlatir: cagiran
        tarayiciyi toparlayip kalan ekranlari yeniden dener.
        """
        secildi = False
        ust_uste_hata = 0
        sonuc_veren = 0
        for tip in ekranlar:
            if tip in biten:  # cokmeden once bu turda tamamlanmisti
                continue
            if len(self.belge_tipleri) > 1:
                yaz(f"  -- {BELGE_TIPLERI[tip]}", self.log)
            if secildi:
                sayfayi_toparla(self.page)  # onceki ekrandan kalan diyaloglar
            try:
                sonuc = firma_isle(self.page, firma, tip, self.araliklar, self.klasor, self.log,
                                   self.azami_deneme, firma_secili=secildi)
            except Exception as e:
                if not sayfa_canli(self.page):
                    raise  # tarayici coktu: cagiran toparlayip tekrar dener
                self._hatayi_yaz(firma, tip, e)
                biten.add(tip)
                sayfayi_toparla(self.page)
                secildi = False  # ekranin durumu belirsiz: sonraki ekranda firma yeniden secilir
                ust_uste_hata += 1
                if isinstance(e, FirmaSecilemedi) or ust_uste_hata >= EKRAN_HATA_SINIRI:
                    yaz("    Bu firmanin kalan ekranlari atlandi", self.log)
                    break
                continue
            secildi = True
            ust_uste_hata = 0
            sonuc_veren += 1
            biten.add(tip)
            self._sonuc_ekle(sonuc)
            konsol.ekran_sonucu(sonuc, self.log)
            if sonuc["durum"].startswith(("atlandi", "donem disi")):
                # donemi tutmayan ya da sinir ustu firma: kalan ekranlar taranmaz
                yaz("    Bu firmanin kalan ekranlari atlandi", self.log)
                break
        return sonuc_veren > 0 or not ekranlar

    def _firmayi_isle(self, firma):
        """Firmayi isler; tarayici cokerse toparlayip yeniden dener. Basariliysa True."""
        ekranlar = self._islenecek_ekranlar(firma)
        biten = set()
        for tur in range(COKME_DENEMESI + 1):
            if tur:
                self._sayfa_hazirla()  # TarayiciGitti firlatabilir
                yaz(f"    {firma} yeniden deneniyor ({tur}/{COKME_DENEMESI})", self.log)
            try:
                return self._ekranlari_isle(firma, ekranlar, biten)
            except Exception as e:
                yaz(f"    Tarayici kapandi ({type(e).__name__}); toparlanacak", self.log)
                if tur == COKME_DENEMESI:
                    kalan = next((t for t in ekranlar if t not in biten), ekranlar[0] if ekranlar else "")
                    self._hatayi_yaz(firma, kalan, e)
                    return False
        return False

    # --- ana dongu -------------------------------------------------------

    def calistir(self):
        """Butun firmalari isler; CalismaOzeti dondurur."""
        firmalar = self.firmalar
        # bastan yazilir ki yarida kalsa da dosya olsun
        self.durumu_kaydet(firmalar)
        durduruldu = ""
        i = 0
        try:
            for i, firma in enumerate(firmalar, 1):
                self.ilerleme.firma_basladi(i, firma, self.log)
                self._sayfa_hazirla()
                if self._firmayi_isle(firma):
                    self.ardisik_hata = 0
                else:
                    self.ardisik_hata += 1
                self.ilerleme.firma_bitti()
                # her firmadan sonra: gece yarida kalirsa sabah nerede kalindigi gorulur
                self.durumu_kaydet(firmalar[i:])

                # pes etmeden once oturumu yenilemeyi dene: ust uste hatalarin
                # sebebi genelde firma degil, dusmus Luca oturumu oluyor
                if 2 <= self.ardisik_hata < self.hata_siniri and sayfa_canli(self.page):
                    yeni = oturumu_yenile(self.page, self.ctx, self.ayarlar, self.log)
                    if yeni is not None:
                        self.page = yeni
                        self.ardisik_hata = 0

                if self.ardisik_hata >= self.hata_siniri:
                    durduruldu = (f"ust uste {self.hata_siniri} firma basarisiz oldu;"
                                  " Luca oturumu bozulmus olabilir")
                    yaz(f"\n{durduruldu}. Islem durduruldu. Tarayicidan Luca'ya tekrar girip"
                        " yeniden calistirin (tamamlanan ekranlar tekrar acilmaz).", self.log)
                    break
        except TarayiciGitti:
            durduruldu = "tarayici kapandi ve yeniden acilamadi"
            kalanlar = firmalar[max(i - 1, 0):]
            self.durumu_kaydet(kalanlar)
            yaz("\nTarayici kapandi ve yeniden acilamadi (Luca oturumu dustu).", self.log)
            yaz(f"Kalan {len(kalanlar)} firma 'bekliyor' olarak birakildi.", self.log)
            yaz("Tarayiciyi acip Luca'ya girin ve programi yeniden calistirin.", self.log)
        except KeyboardInterrupt:
            durduruldu = "kullanici durdurdu (Ctrl+C)"
            kalanlar = firmalar[max(i - 1, 0):]
            self.durumu_kaydet(kalanlar)
            yaz(f"\nDurduruldu. O ana kadarki sonuclar kaydedildi; kalan {len(kalanlar)} firma"
                " 'bekliyor'. Yeniden calistirinca [D]evam secerseniz kaldigi yerden surer.", self.log)

        ozet = ozetle(self.sonuclar, self.ilerleme.gecen())
        ozet.durduruldu = durduruldu
        return ozet
