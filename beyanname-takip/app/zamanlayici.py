"""Arka plan zamanlayıcısı: her 30 saniyede bir çekirdeğe 'zamanı geldi mi?' diye sorar."""

import logging
import threading

log = logging.getLogger("zamanlayici")


class Zamanlayici(threading.Thread):
    def __init__(self, uygulama, aralik_sn=30):
        super().__init__(daemon=True, name="zamanlayici")
        self.uygulama, self.aralik_sn = uygulama, aralik_sn
        self._dur = threading.Event()

    def run(self):
        log.info("zamanlayıcı başladı")
        while not self._dur.is_set():
            try:
                self.uygulama.zamanlayici_adimi()
            except Exception:  # noqa: BLE001 - döngü hiçbir hatada ölmemeli
                log.exception("zamanlayıcı adımı başarısız")
            self._dur.wait(self.aralik_sn)

    def durdur(self):
        self._dur.set()
