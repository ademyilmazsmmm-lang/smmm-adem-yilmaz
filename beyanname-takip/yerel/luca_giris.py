"""Luca'ya hızlı giriş: seçilen hesapla (ofis / isletme) Luca'ya girer, doğrulama kodunu kendisi yazar ve Luca açık kalır.

Kullanım (kısayol bunu çağırır):  pythonw luca_giris.py ofis
Hesap adı yoksa ayarlar.env'deki LUCA_HESAPLAR'ın ilki kullanılır. Giriş bilgileri ayarlar.env'den okunur (Beyanname Takip ile aynı).
Chrome/Edge'i kapattığınızda bu işlem de kendiliğinden biter. Beyanname Takip'in Luca çekimi için kullandığı tarayıcı profilinden AYRI bir
profil kullanılır (veri/profil/hizli-<hesap>), ikisi birbirini kilitlemez. UYARI: Luca aynı kullanıcıyla ikinci oturumu kabul etmeyebilir;
o hesapla bir Luca çekimi sürerken hızlı giriş yapmayın.
"""

import os
import sys
import time
from datetime import date
from pathlib import Path

YEREL = Path(__file__).resolve().parent
KOK = YEREL.parent
sys.path.insert(0, str(YEREL))

import baslat  # noqa: E402


def hesap_sec(env, argumanlar):
    """(hesap, tüm hesaplar). Argüman verilmişse tanımlı bir hesap olmalı; yoksa LUCA_HESAPLAR'ın ilki. Hata: ValueError."""
    hesaplar = [h.strip().lower() for h in (env.get("LUCA_HESAPLAR") or "ofis").split(",") if h.strip()]
    adlar = [a.strip().lower() for a in argumanlar if a and a.strip()]
    if not adlar:
        return hesaplar[0], hesaplar
    if adlar[0] not in hesaplar:
        raise ValueError(f"'{adlar[0]}' hesabı tanımlı değil (ayarlar.env'deki LUCA_HESAPLAR: {', '.join(hesaplar)})")
    return adlar[0], hesaplar


def acik_bekle(ctx, page, nabiz, sayfa_canli, uyku=time.sleep):
    """Tarayıcı siz kapatana kadar bekler (Python bitince Chrome de kapanırdı). Doner: bekleme bitince True."""
    kapandi = {"evet": False}
    try:
        ctx.on("close", lambda _: kapandi.update(evet=True))
    except Exception:  # noqa: BLE001
        pass
    try:
        while not kapandi["evet"] and any(sayfa_canli(p) for p in ctx.pages):
            if sayfa_canli(page):
                nabiz(page, 500)
            else:
                uyku(0.5)
    except KeyboardInterrupt:
        pass
    return True


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    dosya = YEREL / "ayarlar.env"
    if not dosya.exists():
        baslat.hata_goster("ayarlar.env yok. Önce Beyanname Takip kurulumunu yapın (ayarlar-ornek.env -> ayarlar.env).", "Luca Giriş")
        return 1
    try:
        baslat.ortami_hazirla(baslat.ayar_oku(dosya.read_text(encoding="utf-8")), os.environ)
        hesap, hesaplar = hesap_sec(os.environ, argv)
    except ValueError as e:
        baslat.hata_goster(e, "Luca Giriş")
        return 1
    sys.path.insert(0, str(KOK))
    if os.environ.get("LUCABOT_YOLU"):
        sys.path.insert(0, os.environ["LUCABOT_YOLU"])
    try:
        from app.luca_toplayici import LucaHatasi, kimlik_oku
        from lucabot import giris, tarayici
        from lucabot.bekleme import nabiz, sayfa_canli
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        baslat.hata_goster(f"Gerekli paketler bulunamadı ({e}). Beyanname Takip kısayolunu bir kez çalıştırın (ilk kurulum).", "Luca Giriş")
        return 1
    try:
        kimlik = kimlik_oku(os.environ, hesap, tek_hesap=len(hesaplar) == 1)
    except LucaHatasi as e:
        baslat.hata_goster(e, "Luca Giriş")
        return 1
    veri = Path(os.environ["DATA_DIR"])
    profil = veri / "profil" / f"hizli-{hesap}"
    log = veri / f"luca-giris-{hesap}.log"
    tani = veri / "tani" / f"hizli-{hesap}"
    for klasor in (profil, tani):
        klasor.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        try:
            ctx = tarayici.tarayici_ac(pw, profil, log)
        except RuntimeError as e:
            baslat.hata_goster(f"Tarayıcı açılamadı (bu hesap için Luca zaten açık olabilir): {str(e)[:600]}", "Luca Giriş")
            return 1
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        # etkileşimli: kod reddedilirse 3 dakika boyunca elle girmenize izin verilir (gece modu kapalı)
        uygulama = giris.luca_oturumu_ac(ctx, page, dict(kimlik, dogrulama_bekleme_dakika=3), False, tani, log)
        if uygulama is None:
            baslat.hata_goster(f"'{hesap}' hesabıyla giriş tamamlanamadı. Ayrıntı: {log}", "Luca Giriş")
            tarayici.tarayiciyi_kapat(ctx)
            return 1
        acik_bekle(ctx, page, nabiz, sayfa_canli)
        tarayici.tarayiciyi_kapat(ctx)
    return 0


if __name__ == "__main__":
    sys.stdout, sys.stderr = baslat.gunluge_yonlendir(dosya=YEREL / "program.log")
    try:
        kod = main()
    except Exception:  # noqa: BLE001
        import traceback
        baslat.hata_goster(traceback.format_exc()[-1200:], "Luca Giriş")
        kod = 1
    sys.exit(kod)
