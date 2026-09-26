#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tek tikla Luca girisi: fatura cekme botuyla ilgisi yok, sadece oturum acar.

ayarlar.json'daki bilgilerle Luca'ya otomatik giris yapar (parola/uye no/
kullanici adi elle yazilmaz), muhasebe ekranini acar ve tarayiciyi acik
birakir - siz normal calismanizi yaparsiniz. Ayni ayarlar.json ofiste de
evde de kullanildigi icin (OneDrive ile birlikte tasindigi surece) her
iki yerde de tek tikla calisir. Chrome'u kapattiginizda bu pencere de
kendiliginden kapanir.

Kullanim: luca-giris.bat dosyasina cift tiklayin (bkz. o dosya).
"""

import sys
from datetime import date

from lucabot.giris import luca_oturumu_ac
from lucabot.ortak import AYAR, KOK, ayarlari_oku, yaz
from lucabot.bekleme import nabiz, sayfa_canli
from lucabot.tarayici import profil_klasoru, tarayici_ac, tarayiciyi_kapat


def main():
    ayarlar = ayarlari_oku()
    # botun ana programindaki ayarlari_uygula()'nin tarayici/giris ile ilgili kismi:
    # burada sorgu/indirme ayarlarina gerek yok, sadece giris ve tarayici secimi
    AYAR["tarayici"] = ayarlar.get("tarayici") or None
    AYAR["tarayici_yolu"] = ayarlar.get("tarayici_yolu") or None
    AYAR["tarayici_sandbox"] = bool(ayarlar.get("tarayici_sandbox", True))
    AYAR["profil_yerel"] = bool(ayarlar.get("profil_yerel", False))
    AYAR["giris_adresi"] = ayarlar.get("giris_adresi") or None

    log = KOK / "giris-gunlugu.log"
    profil = profil_klasoru(log)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = tarayici_ac(pw, profil, log)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        uygulama = luca_oturumu_ac(ctx, page, ayarlar, False, KOK / "tani" / date.today().isoformat(), log)
        if uygulama is None:
            yaz("\nGiris tamamlanamadi; yukaridaki mesaja bakin.", log)
            input(">>> Kapatmak icin ENTER: ")
            tarayiciyi_kapat(ctx)
            return 1

        yaz("\nGiris tamam. Tarayici acik kaliyor, calismanizi yapabilirsiniz.", log)
        yaz("(Bu pencereyi kapatmak icin Chrome'u kapatin, ya da burada Ctrl+C yapin.)", log)

        # Chrome'u siz kapatana kadar bu program acik kalir (aksi halde Python
        # bitince Chrome de kapanirdi); Chrome'u kapatinca bu pencere de kendiliginden kapanir.
        kapandi = {"evet": False}
        try:
            ctx.on("close", lambda _: kapandi.update(evet=True))
        except Exception:
            pass
        try:
            while not kapandi["evet"] and any(sayfa_canli(p) for p in ctx.pages):
                nabiz(page if sayfa_canli(page) else None, 500)
        except KeyboardInterrupt:
            pass
        tarayiciyi_kapat(ctx)
    return 0


if __name__ == "__main__":
    sys.exit(main())
