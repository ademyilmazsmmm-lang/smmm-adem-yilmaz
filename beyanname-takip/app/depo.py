"""Basit JSON dosya deposu (DATA_DIR). Yazma atomiktir; okuma-değiştirme-yazma tek kilit altındadır."""

import json
import os
import threading
from pathlib import Path


class Depo:
    def __init__(self, dizin):
        self.dizin = Path(dizin)
        self.dizin.mkdir(parents=True, exist_ok=True)
        self.kilit = threading.RLock()

    def oku(self, ad, varsayilan=None):
        with self.kilit:
            try:
                return json.loads((self.dizin / ad).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return {} if varsayilan is None else varsayilan

    def yaz(self, ad, veri):
        with self.kilit:
            yol = self.dizin / ad
            gecici = yol.with_name(yol.name + ".tmp")
            gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(gecici, yol)

    def guncelle(self, ad, degistir, varsayilan=None):
        """degistir(veri) -> yeni veri (ya da None: veri yerinde değiştirildi). Sonucu döndürür."""
        with self.kilit:
            veri = self.oku(ad, varsayilan)
            yeni = degistir(veri)
            if yeni is not None:
                veri = yeni
            self.yaz(ad, veri)
            return veri
