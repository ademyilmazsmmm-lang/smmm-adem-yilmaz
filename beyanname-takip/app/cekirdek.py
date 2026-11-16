"""Uygulama çekirdeği: veri toplama, değerlendirme, zamanlanmış uyarılar."""

import html
import logging
import threading
from datetime import datetime, timedelta, timezone

from .kontrol import (SLOTLAR, ayni_firma, bolumlere_ayir, degerlendir, gunluk_ozet, mesaj_olustur, mukellef_normalize)
from .kurallar import Tatiller

log = logging.getLogger("cekirdek")
TR = timezone(timedelta(hours=3))      # Türkiye yıl boyu UTC+3
GECIKME_TOLERANS = timedelta(minutes=90)  # uygulama geç açılırsa kaçan slot en fazla bu kadar geç çalıştırılır
VERI_ESKI_SAAT = 24
DENEME_ARALIGI = timedelta(minutes=5)     # gönderilemeyen slotun yeniden deneme aralığı


def simdi_tr():
    return datetime.now(TR).replace(tzinfo=None, second=0, microsecond=0)


class Uygulama:
    def __init__(self, depo, toplayici, telegram, captcha, tatil=None, saat=simdi_tr):
        self.depo, self.toplayici, self.telegram, self.captcha = depo, toplayici, telegram, captcha
        self.tatil = tatil or Tatiller()
        self.saat = saat
        self._toplama_kilidi = threading.Lock()
        self.tani_suruyor = False
        self.rapor_suruyor = False
        self._son_deneme = {}          # slot anahtarı -> son deneme zamanı (başarısız gönderimde Luca'yı yormamak için)

    # ---- veri toplama ----
    def topla(self, gib_aralik=None):
        """Luca'dan veriyi alıp kaydeder. Başarısızlık durum.json'a yazılır, istisna fırlatmaz.
        gib_aralik: elle seçilen "GİB'den Getir" aralığı (başlangıç, bitiş); None ise varsayılan (LUCA_GIB_GUN, 15 gün)."""
        if not self._toplama_kilidi.acquire(blocking=False):
            return {"ok": False, "hata": "başka bir toplama sürüyor"}
        simdi = self.saat()
        try:
            ham = (self.toplayici.topla(simdi.date(), self.captcha, gib_aralik=gib_aralik) if gib_aralik
                   else self.toplayici.topla(simdi.date(), self.captcha))
            mus = []
            for m in ham["mukellefler"]:
                hesap = m.get("hesap") or "ofis"
                mus.append(mukellef_normalize(m, hesap))
            if not mus:
                raise ValueError("Luca'dan hiç mükellef gelmedi (liste boş)")
            bey = [dict(b, hesap=b.get("hesap") or "ofis") for b in ham["beyannameler"]]
            uyarilar = list(ham.get("uyarilar", []))
            eslesmeyen = [b for b in bey if not any(ayni_firma(m, b) for m in mus)]
            if eslesmeyen:
                ornek = ", ".join(sorted({b.get("firma", "?") for b in eslesmeyen})[:3])
                uyarilar.append(f"{len(eslesmeyen)} beyanname satırı hiçbir mükellefle eşleşmedi (örn. {ornek}); "
                                "Luca'daki 'Mükellef Adı' ile müşteri listesindeki ad farklı olabilir")
            self.depo.yaz("mukellefler.json", {"zaman": simdi.isoformat(), "kayitlar": mus})
            self.depo.yaz("beyannameler.json", {"zaman": simdi.isoformat(), "kayitlar": bey})
            sonuc = {"ok": True, "zaman": simdi.isoformat(), "mukellef": len(mus), "beyanname": len(bey),
                     "hesaplar": ham.get("hesaplar", {}), "uyarilar": uyarilar}
            if gib_aralik:
                sonuc["gib"] = f"{gib_aralik[0]:%d.%m.%Y} – {gib_aralik[1]:%d.%m.%Y}"
            self.depo.guncelle("durum.json", lambda d: d.update({"son_toplama": sonuc, "son_basarili": sonuc}))
            return sonuc
        except Exception as e:  # noqa: BLE001 - her hata kullanıcıya bildirilmeli
            log.exception("toplama başarısız")
            sonuc = {"ok": False, "zaman": simdi.isoformat(), "hata": f"{type(e).__name__}: {e}"[:300]}
            self.depo.guncelle("durum.json", lambda d: d.update({"son_toplama": sonuc}))
            return sonuc
        finally:
            self._toplama_kilidi.release()

    def tani(self):
        """Luca tanısı (yalnızca TOPLAYICI=luca): ekranları açıp tanı dosyalarını yazar, veri kaydetmez."""
        simdi = self.saat()
        if not hasattr(self.toplayici, "tani"):
            sonuc = {"ok": False, "zaman": simdi.isoformat(), "mesaj": "Tanı yalnızca TOPLAYICI=luca iken çalışır"}
        elif not self._toplama_kilidi.acquire(blocking=False):
            return {"ok": False, "mesaj": "Luca ile başka bir işlem sürüyor"}
        else:
            self.tani_suruyor = True
            try:
                self.toplayici.tani(simdi.date(), self.captcha)
                sonuc = {"ok": True, "zaman": simdi.isoformat(), "mesaj": "Tanı tamamlandı"}
            except Exception as e:  # noqa: BLE001
                log.exception("tanı başarısız")
                sonuc = {"ok": False, "zaman": simdi.isoformat(), "mesaj": f"{type(e).__name__}: {e}"[:300]}
            finally:
                self.tani_suruyor = False
                self._toplama_kilidi.release()
        self.depo.guncelle("durum.json", lambda d: d.update({"son_tani": sonuc}))
        return sonuc

    # ---- değerlendirme ----
    def maddeler(self, bugun=None):
        bugun = bugun or self.saat().date()
        mus = self.depo.oku("mukellefler.json", {}).get("kayitlar", [])
        bey = self.depo.oku("beyannameler.json", {}).get("kayitlar", [])
        return degerlendir(mus, self.depo.oku("ayarlar.json", {}), bey, bugun, self.tatil)

    def veri_durumu(self):
        d = self.depo.oku("durum.json", {})
        son, basarili = d.get("son_toplama"), d.get("son_basarili")
        zaman = basarili["zaman"] if basarili else None
        eski = True
        if zaman:
            eski = (self.saat() - datetime.fromisoformat(zaman)) > timedelta(hours=VERI_ESKI_SAAT)
        return {"zaman": zaman, "eski": eski, "uyarilar": (basarili or {}).get("uyarilar", []),
                "hata": None if (son and son.get("ok")) else (son or {}).get("hata", "hiç veri alınmadı")}

    # ---- zamanlanmış uyarı ----
    def _mesajlar(self, slot, bugun, gecikmeli=False, esik=None):
        """Verilen gün ve slot için gönderilecek mesaj metinleri (depodaki mevcut veriyle; toplama yapmaz, göndermez)."""
        vd = self.veri_durumu()
        maddeler = self.maddeler(bugun)
        ek = []
        for y in {bugun.year, (bugun + timedelta(days=40)).year}:
            if not self.tatil.bayram_verisi_var_mi(y):
                ek.append(f"{y} yılı bayram tatilleri tatiller.json'da yok; son günler yanlış hesaplanabilir.")
        ek += vd["uyarilar"]
        # Veri uyarıları (Luca hatası, eski veri, bayram verisi) bir kez; eksik listeleri Ofis / Ofis "1"liler / İşletme için AYRI e-postalar
        metinler = mesaj_olustur([], slot, vd["zaman"], vd["hata"], vd["eski"], " | ".join(ek) or None, esik=esik)
        for baslik, ms in bolumlere_ayir(maddeler):
            for parca in mesaj_olustur(ms, slot, vd["zaman"], None, False, None, esik=esik):
                metinler.append(f"<b>[{html.escape(baslik)}]</b> " + parca)
        if slot == SLOTLAR[0] and esik is None:
            ozet = gunluk_ozet(maddeler, vd["zaman"], bugun)
            if vd["hata"]:
                ozet = ""        # hata mesajı zaten gidiyor; "çalışıyor" denmez
            if ozet:
                metinler = [ozet] + metinler
        if gecikmeli and metinler:
            metinler[0] = "<i>(gecikmeli gönderim)</i>\n" + metinler[0]
        return metinler

    def rapor_gonder(self, esik=10, gib_aralik=None):
        """Elle istenen özet: Luca'dan taze veriyi çeker, son günü `esik` gün içinde (ya da yeni geçmiş) eksik her şeyi bildirim
        kanallarına gönderir; eksik yoksa "tamam" der. Slot saatlerine ve slot kaydına bağlı değildir (bilgisayarı elle açanlar için)."""
        if not self._toplama_kilidi.acquire(blocking=False):
            return {"ok": False, "mesaj": "Luca ile başka bir işlem sürüyor"}
        self._toplama_kilidi.release()
        self.rapor_suruyor = True
        simdi = self.saat()
        try:
            self.topla(gib_aralik)
            metinler = self._mesajlar("09:00", simdi.date(), esik=esik)
            if not metinler:
                vd = self.veri_durumu()
                metinler = [f"✅ <b>Beyanname takip özeti</b>\nÖnümüzdeki {esik} gün içinde son günü gelen eksik beyanname yok."
                            f"\n<i>Luca verisi: {vd['zaman']} itibarıyla</i>"]
            else:
                metinler[0] = "📋 <b>Elle istenen özet</b>\n" + metinler[0]
            ok = all([self.telegram.gonder(m) for m in metinler])
            sonuc = {"ok": ok, "zaman": simdi.isoformat(), "mesaj": f"{len(metinler)} e-posta gönderildi" if ok else "bildirim gönderilemedi"}
        except Exception as e:  # noqa: BLE001
            log.exception("rapor başarısız")
            sonuc = {"ok": False, "zaman": simdi.isoformat(), "mesaj": f"{type(e).__name__}: {e}"[:300]}
        finally:
            self.rapor_suruyor = False
        self.depo.guncelle("durum.json", lambda d: d.update({"son_rapor": sonuc}))
        return sonuc

    def onizleme(self, slot, tarih=None):
        """Belirtilen gün ve slotta gidecek mesajlar (gönderilmez, 'slot çalıştı' diye işaretlenmez, Luca'ya gidilmez)."""
        return self._mesajlar(slot, tarih or self.saat().date())

    def slot_calistir(self, slot, gecikmeli=False):
        bugun = self.saat().date()
        anahtar = f"{bugun.isoformat()}|{slot}"
        gonderim = self.depo.oku("gonderim.json", {})
        if anahtar in gonderim:
            return "zaten çalıştı"
        self.topla()
        metinler = self._mesajlar(slot, bugun, gecikmeli)
        basarili = all(self.telegram.gonder(m) for m in metinler) if metinler else True
        if basarili:
            def isle(g):
                g[anahtar] = self.saat().isoformat()
                for k in [k for k in g if k < (bugun - timedelta(days=30)).isoformat()]:
                    del g[k]
            self.depo.guncelle("gonderim.json", isle)
        log.info("slot %s: %d mesaj, gönderim %s", slot, len(metinler), "tamam" if basarili else "BAŞARISIZ")
        return {"mesaj": len(metinler), "gonderildi": basarili}

    def zamanlayici_adimi(self):
        """Her dakika çağrılır: zamanı gelmiş (ya da kaçmış ama tolerans içindeki) slotları çalıştırır."""
        simdi = self.saat()
        gonderim = self.depo.oku("gonderim.json", {})
        gunu = simdi.date().isoformat()
        bekleyen = []
        for slot in SLOTLAR:
            h, m = map(int, slot.split(":"))
            an = simdi.replace(hour=h, minute=m)
            if an <= simdi <= an + GECIKME_TOLERANS and f"{gunu}|{slot}" not in gonderim:
                bekleyen.append((slot, an))
        # birden çok slot kaçmışsa (uygulama geç açıldı) yalnızca sonuncusu çalışır, öncekiler atlandı sayılır
        for slot, _ in bekleyen[:-1]:
            self.depo.guncelle("gonderim.json", lambda g, s=slot: g.update({f"{gunu}|{s}": "atlandı"}))
        if bekleyen:
            slot, an = bekleyen[-1]
            anahtar = f"{gunu}|{slot}"
            if simdi - self._son_deneme.get(anahtar, datetime.min) < DENEME_ARALIGI:
                return
            self._son_deneme[anahtar] = simdi
            self.slot_calistir(slot, gecikmeli=(simdi - an) > timedelta(minutes=10))
