"""Bildirim kanalları (Telegram, e-posta) ve captcha köprüsü.

Token, sohbet no ve SMTP parolası yalnızca ortam değişkenlerinden okunur (TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, SMTP_*).
Günlüklere mesaj metni, mükellef adı, token ya da parola yazılmaz.
"""

import html
import json
import logging
import re
import smtplib
import ssl
import threading
import time
import urllib.error
import urllib.request
import uuid
from email.message import EmailMessage

log = logging.getLogger("bildirim")


def _http(url, veri=None, baslik=None, zaman=35):
    istek = urllib.request.Request(url, data=veri, headers=baslik or {})
    with urllib.request.urlopen(istek, timeout=zaman) as r:
        return json.loads(r.read().decode("utf-8"))


class Telegram:
    ad = "Telegram"

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


class Eposta:
    """SMTP ile e-posta (örn. Gmail: smtp.gmail.com:587 + "uygulama şifresi"). Mesajlar Telegram'la aynı HTML işaretlemesini taşır."""
    ad = "E-posta"

    def __init__(self, host, port, kullanici, parola, alici, gonderen=None, smtp_fabrikasi=None):
        self.host = (host or "").strip()
        self.port = int(port or 587)
        self.kullanici = (kullanici or "").strip()
        self.parola = parola or ""
        self.alicilar = [a.strip() for a in re.split(r"[,;]", alici or self.kullanici) if a.strip()]
        self.gonderen = (gonderen or self.kullanici).strip()
        self._fabrika = smtp_fabrikasi or self._baglan

    @classmethod
    def ortamdan(cls, env):
        return cls(env.get("SMTP_HOST") or ("smtp.gmail.com" if env.get("SMTP_KULLANICI") else ""), env.get("SMTP_PORT"),
                   env.get("SMTP_KULLANICI"), env.get("SMTP_PAROLA"), env.get("MAIL_ALICI"), env.get("MAIL_GONDEREN"))

    @property
    def hazir(self):
        return bool(self.host and self.kullanici and self.parola and self.alicilar and self.gonderen)

    def _baglan(self):
        if self.port == 465:
            return smtplib.SMTP_SSL(self.host, self.port, timeout=30, context=ssl.create_default_context())
        c = smtplib.SMTP(self.host, self.port, timeout=30)
        c.starttls(context=ssl.create_default_context())
        return c

    def gonder(self, metin):
        if not self.hazir:
            log.warning("E-posta ayarlı değil; mesaj gönderilmedi")
            return False
        duz = html.unescape(re.sub(r"<[^>]+>", "", metin)).strip()
        ilk = next((satir.strip() for satir in duz.splitlines() if satir.strip()), "bildirim")
        ileti = EmailMessage()
        ileti["Subject"] = "Beyanname Takip: " + ilk[:120]
        ileti["From"] = self.gonderen
        ileti["To"] = ", ".join(self.alicilar)
        ileti.set_content(duz)
        ileti.add_alternative(f'<div style="white-space:pre-wrap;font-family:sans-serif">{metin}</div>', subtype="html")
        try:
            with self._fabrika() as c:
                c.login(self.kullanici, self.parola)
                c.send_message(ileti)
            return True
        except (smtplib.SMTPException, OSError) as e:
            log.warning("E-posta gönderilemedi (%s)", type(e).__name__)     # parola/adres/metin yazılmaz
            return False

    def foto_gonder(self, png, aciklama=""):
        return False                # captcha e-postayla çözülmez; web sayfası ya da Telegram kullanılır

    def yeni_mesajlar(self):
        return []


class Bildirici:
    """Birden çok kanalı tek nesne gibi kullanır. Mesaj, hazır olan kanalların en az birine ulaştıysa 'gönderildi' sayılır."""

    def __init__(self, kanallar):
        self.kanallar = list(kanallar)

    @property
    def hazir(self):
        return any(k.hazir for k in self.kanallar)

    def hazir_kanallar(self):
        return [getattr(k, "ad", type(k).__name__) for k in self.kanallar if k.hazir]

    def gonder(self, metin):
        sonuc = [k.gonder(metin) for k in self.kanallar if k.hazir]           # biri düşse diğeri yine denenir
        return any(sonuc)

    def foto_gonder(self, png, aciklama=""):
        return any([k.foto_gonder(png, aciklama) for k in self.kanallar if k.hazir])

    def yeni_mesajlar(self):
        return [m for k in self.kanallar if k.hazir for m in k.yeni_mesajlar()]


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
