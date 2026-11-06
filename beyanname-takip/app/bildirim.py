"""Telegram bildirimi ve captcha köprüsü.

Token ve sohbet no yalnızca ortam değişkenlerinden okunur (TELEGRAM_TOKEN, TELEGRAM_CHAT_ID).
Günlüklere mesaj metni, mükellef adı ya da token yazılmaz.
"""

import json
import logging
import threading
import time
import urllib.error
import urllib.request
import uuid

log = logging.getLogger("bildirim")


def _http(url, veri=None, baslik=None, zaman=35):
    istek = urllib.request.Request(url, data=veri, headers=baslik or {})
    with urllib.request.urlopen(istek, timeout=zaman) as r:
        return json.loads(r.read().decode("utf-8"))


class Telegram:
    def __init__(self, token, chat_id, http=_http):
        self.token = (token or "").strip()
        self.chat_id = str(chat_id or "").strip()
        self.http = http
        self._offset = None

    @property
    def hazir(self):
        return bool(self.token and self.chat_id)

    def _url(self, yontem):
        return f"https://api.telegram.org/bot{self.token}/{yontem}"

    def _cagri(self, yontem, yuk):
        try:
            c = self.http(self._url(yontem), json.dumps(yuk).encode(), {"Content-Type": "application/json"})
            return bool(c.get("ok")), c
        except (urllib.error.URLError, OSError, ValueError) as e:
            # URLError metni token içeren adresi taşıyabilir: yalnızca türü yazılır
            log.warning("Telegram %s başarısız (%s)", yontem, type(e).__name__)
            return False, {}

    def gonder(self, metin):
        if not self.hazir:
            log.warning("Telegram ayarlı değil; mesaj gönderilmedi")
            return False
        ok, _ = self._cagri("sendMessage", {"chat_id": self.chat_id, "text": metin, "parse_mode": "HTML",
                                           "disable_web_page_preview": True})
        return ok

    def foto_gonder(self, png, aciklama=""):
        if not self.hazir:
            return False
        sinir = uuid.uuid4().hex
        parca = []
        for ad, deger in (("chat_id", self.chat_id), ("caption", aciklama)):
            parca.append(f'--{sinir}\r\nContent-Disposition: form-data; name="{ad}"\r\n\r\n{deger}\r\n'.encode())
        parca.append(f'--{sinir}\r\nContent-Disposition: form-data; name="photo"; filename="captcha.png"\r\n'
                     f'Content-Type: image/png\r\n\r\n'.encode() + png + b"\r\n")
        parca.append(f"--{sinir}--\r\n".encode())
        try:
            c = self.http(self._url("sendPhoto"), b"".join(parca),
                          {"Content-Type": f"multipart/form-data; boundary={sinir}"})
            return bool(c.get("ok"))
        except (urllib.error.URLError, OSError, ValueError) as e:
            log.warning("Telegram sendPhoto başarısız (%s)", type(e).__name__)
            return False

    def yeni_mesajlar(self):
        """Yapılandırılan sohbetten gelen yeni metin mesajları (başka sohbetler yok sayılır)."""
        yuk = {"timeout": 0, "allowed_updates": ["message"]}
        if self._offset is not None:
            yuk["offset"] = self._offset
        ok, c = self._cagri("getUpdates", yuk)
        sonuc = []
        for g in (c.get("result") or []) if ok else []:
            self._offset = g["update_id"] + 1
            m = g.get("message") or {}
            if str((m.get("chat") or {}).get("id")) == self.chat_id and m.get("text"):
                sonuc.append(m["text"].strip())
        return sonuc


class CaptchaKoprusu:
    """Captcha resmini Telegram'a (ve web sayfasına) gösterir, cevabı Telegram'dan ya da web'den bekler."""

    def __init__(self, telegram, bekleme_sn=300, aralik_sn=3):
        self.telegram = telegram
        self.bekleme_sn = bekleme_sn
        self.aralik_sn = aralik_sn
        self._olay = threading.Event()
        self._cevap = None
        self.resim = None          # web sayfası için bekleyen resim (png baytları)

    def bekliyor_mu(self):
        return self.resim is not None

    def cevapla(self, kod):
        kod = (kod or "").strip()
        if self.resim is None or not kod:
            return False
        self._cevap = kod
        self._olay.set()
        return True

    def sor(self, png, aciklama="Luca güvenlik kodu: resimdeki kodu bu sohbete yazın"):
        self._cevap = None
        self._olay.clear()
        self.resim = png
        try:
            self.telegram.yeni_mesajlar()           # eski mesajlar cevap sayılmasın
            self.telegram.foto_gonder(png, aciklama)
            bitis = time.monotonic() + self.bekleme_sn
            while time.monotonic() < bitis:
                if self._olay.wait(self.aralik_sn):
                    return self._cevap
                for m in self.telegram.yeni_mesajlar():
                    return m
            return None
        finally:
            self.resim = None
