"""
Ortam değişkenlerinden (ZAMAN, GUNLER, METIN) bir satır oluşturup
hatirlatmalar.txt sonuna ekler. Önce hatirlatici.py ile doğrular,
geçersizse hiçbir şey yazmaz. Telefondan (Kestirmeler) çağrılan workflow kullanır.
"""

import os
import sys

import hatirlatici


def temiz(s):
    return " ".join(s.replace("|", "/").split())


zaman, gunler, metin = (temiz(os.environ.get(k, "")) for k in ("ZAMAN", "GUNLER", "METIN"))
satir = f"{zaman} | {gunler or '0'} | {metin}"
try:
    hatirlatici.satir_ayristir(satir, 0)
except (ValueError, KeyError) as e:
    sys.exit(f"Geçersiz satır, eklenmedi: {satir}\n{e}")

with open(hatirlatici.DOSYA, "a", encoding="utf-8") as f:
    f.write(satir + "\n")
print("Eklendi:", satir)
