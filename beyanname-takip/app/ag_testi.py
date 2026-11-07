"""Sunucunun dış ağ erişimini sınar: Luca'ya ulaşılabiliyor mu, yoksa tüm yurt dışı çıkışı mı yavaş/kapalı?

Tarayıcı kullanılmaz (CPU yavaşlığı sonucu bozmasın). Yalnızca herkese açık ana sayfalara GET atılır; çerez/şifre yok.
"""

import socket
import time
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _istek(url, zaman):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=zaman)


def ag_testi(luca_adresi="https://www.luca.com.tr", zaman=15, istek=_istek, saat=time.monotonic):
    """[{ad, adres, sonuc, ok, sn}] döner. Sonuç HTTP kodu ya da hata türüdür."""
    hedefler = [("Luca ön sayfa (www)", luca_adresi),
                ("Luca GİRİŞ sunucusu (agiris)", "https://agiris.luca.com.tr"),
                ("Karşılaştırma: Google (yurt dışı)", "https://www.google.com"),
                ("Karşılaştırma: gib.gov.tr (Türkiye)", "https://www.gib.gov.tr")]
    sonuc = []
    for ad, adres in hedefler:
        t0 = saat()
        try:
            with istek(adres, zaman) as r:
                durum, ok = f"HTTP {r.status}", True
        except urllib.error.HTTPError as e:         # sunucu cevap verdi (403 gibi): ağ açık, ama engellemiş olabilir
            durum, ok = f"HTTP {e.code}", e.code < 400
        except (socket.timeout, TimeoutError):
            durum, ok = "Zaman aşımı", False
        except (urllib.error.URLError, OSError) as e:
            durum, ok = type(e.reason).__name__ if isinstance(e, urllib.error.URLError) and e.reason else type(e).__name__, False
        sonuc.append({"ad": ad, "adres": adres, "sonuc": durum, "ok": ok, "sn": round(saat() - t0, 1)})
    return sonuc
