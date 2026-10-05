# -*- coding: utf-8 -*-
"""kar_zarar.py'yi bastan sona sahte Luca + sahte Defter Beyan uzerinde calistirir.

    python testler/uctan_uca.py      # Linux'ta: xvfb-run -a python ...

Beklenen dagilim (01/07/2026 - 31/08/2026): ALFA ISLETME ve FATURASIZ AS Defter Beyan'dan
(isletme), DENTAL SAGLIK (bilanco), MERT INSAAT (Defter Beyan'da yok) ve ESKI DONEM LTD
(Luca musteri listesinde yok) Luca hesap planindan; KEREM TICARET donemden once kapanmis.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sahte_kz  # noqa: E402


def main():
    klasor = Path(tempfile.mkdtemp(prefix="karzarar-test-"))
    sunucu, adres = sahte_kz.baslat()
    ayar = {
        "giris_adresi": adres, "defterbeyan_adresi": adres,
        "tarayici": "chromium", "tarayici_yolu": os.environ.get("LUCA_TEST_CHROMIUM", ""),
        "tarayici_sandbox": os.name == "nt",  # Linux test kapsayicisinda root ile sandbox acilmiyor
        "profil_yerel": True,
    }
    ayar_yolu = klasor / "ayarlar.json"
    ayar_yolu.write_text(json.dumps(ayar), encoding="utf-8")
    ortam = dict(os.environ, LUCA_BOT_AYAR=str(ayar_yolu), LOCALAPPDATA=str(klasor / "yerel"),
                 KARZARAR_CIKTI=str(klasor / "cikti"), PYTHONIOENCODING="utf-8")
    komut = [sys.executable, str(KOK / "kar_zarar.py"), "--baslangic", "01/07/2026", "--bitis", "31/08/2026",
             "--bitince-kapat"] + os.environ.get("KZ_EK_ARGUMAN", "").split()
    print("Calistiriliyor:", " ".join(komut))
    sonuc = subprocess.run(komut, env=ortam, cwd=str(KOK))
    sunucu.shutdown()

    hatalar = []
    if sonuc.returncode != 0:
        hatalar.append(f"cikis kodu {sonuc.returncode}")
    try:
        veri = json.loads((klasor / "cikti" / "kar-zarar.json").read_text(encoding="utf-8"))
    except OSError:
        veri = {"donem": "", "firmalar": []}
        hatalar.append("kar-zarar.json yok")
    bulunan = {f["firma"]: (f["kar"], f["kaynak"]) for f in veri["firmalar"]}
    beklenen = {"ALFA ISLETME": (200000.0, "Defter Beyan"), "FATURASIZ AS": (100000.0, "Defter Beyan"),
                "SERBEST KISI": (100000.0, "Defter Beyan"),   # SMK: ozette Kar satiri yok, gelir - gider
                "DENTAL SAGLIK": (100000.0, "Luca (Mizan)"), "MERT INSAAT": (-30000.0, "Luca (Mizan)")}   # ESKI DONEM LTD'nin 2026 donemi yok: 1.Sinif/2026 listesinde olmadigi icin sorgulanmaz
    if bulunan != beklenen:
        hatalar.append(f"sonuclar: {bulunan}")
    if veri["donem"] != "01/07/2026-31/08/2026":
        hatalar.append(f"donem: {veri['donem']}")
    if hatalar:
        print("\nBASARISIZ:\n  - " + "\n  - ".join(hatalar))
        return 1
    print("\nUCTAN UCA TEST BASARILI")
    return 0


if __name__ == "__main__":
    sys.exit(main())
