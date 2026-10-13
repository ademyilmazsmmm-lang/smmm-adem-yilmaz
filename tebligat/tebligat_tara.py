"""
Dijital Vergi Dairesi (dijital.gib.gov.tr) için bu bilgisayarda çalışan yardımcı program.
Tarayıcıyı açar; girişi ve doğrulama kodunu SİZ yaparsınız. Program yalnızca ekrandakileri
okur: hiçbir yere tıklamaz, hiçbir alana yazmaz, hiçbir şey göndermez.

Şu an tek modu "keşif": siz ekranı hazırlayıp Enter'a bastıkça sayfanın yapısını (düğme,
bağlantı, başlık, tablo sütunu adları) cikti/ klasörüne kaydeder. Rakamlar # ile, tablo ve
liste içerikleri x ile gizlenir; kutulara yazılan değerler (şifre dahil) ve bağlantılardaki
sorgu parametreleri hiç kaydedilmez. Tebligat tarama bu dosyalara bakılarak yazılacak.

DİKKAT: Bu depo herkese açıktır. cikti/ klasörü git'e girmez, ama dosyaları birine göndermeden
önce açıp firma ya da kişi adı kalmış mı bakın. Şifre, oturum ve içerik hiçbir yere gönderilmez.

Kullanım:
  python tebligat_tara.py                     # keşif modu; önce Chrome, yoksa Edge ile
  python tebligat_tara.py --tarayici msedge   # tarayıcıyı elle seç (chrome | msedge)
  python tebligat_tara.py --adres file:///deneme.html --gorunmez --tarayici-yolu /yol/chrome   # deneme için
"""

import argparse
import os
import re
import sys
from datetime import datetime
from urllib.parse import urlsplit

ADRES = "https://dijital.gib.gov.tr/"
CIKTI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cikti")

VERI_ROLLERI = {"cell", "gridcell", "row", "rowheader", "option"}    # içerik veri sayılır: yalnızca biçimi kalır
GIRDI_ROLLERI = {"textbox", "searchbox", "combobox", "spinbutton"}   # yazılan değer asla kaydedilmez
BENZER_ESIK = 3        # art arda aynı türden öğelerden bu kadarı gösterilir, kalanı "(+N benzer)" olur
LISTE_ESIGI = 10       # aynı türden bu kadar ya da daha çok kardeş varsa menü değil veri listesi sayılır
SATIR_SINIRI = 600     # bir ekranın dökümü en fazla bu kadar satır
METIN_SINIRI = 120

SATIR = re.compile(r'^(\s*)- (/?[\w-]+)(?: ("(?:[^"\\]|\\.)*"))?(.*)$')
BUYUK_KELIME = r"[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ0-9.&'’-]+"
ISIM = re.compile(rf"{BUYUK_KELIME}(?:\s+{BUYUK_KELIME}){{2,}}")    # art arda 3+ BÜYÜK HARFLİ kelime: firma adı olabilir


# ---------- gizleme ----------

def rakamsiz(metin):
    return re.sub(r"\d", "#", ISIM.sub("[AD]", metin))


def sekil(metin):
    """Harfleri x/X, rakamları 9 yapar; boşluk ve noktalama kalır (içerik gizlenir, biçim görülür)."""
    sonuc = []
    for k in metin:
        if k.isdigit():
            sonuc.append("9")
        elif k.isalpha():
            sonuc.append("X" if k.isupper() else "x")
        else:
            sonuc.append(k)
    return "".join(sonuc)


def yol_gizle(adres):
    """Adresin yalnızca yolunu (ve # rotasını) tutar; sorgu parametreleri atılır, uzun kimlikler gizlenir."""
    parca = urlsplit(adres)
    yol = parca.path + ("#" + parca.fragment.split("?")[0] if parca.fragment else "")
    yol = re.sub(r"[0-9a-fA-F-]{8,}", "{id}", yol)
    return rakamsiz(yol)


# ---------- ekran yapısı ----------

def satir_coz(satir):
    """ARIA anlık görüntüsünün bir satırını (rol, ad, özellik, metin) olarak ayırır."""
    m = SATIR.match(satir)
    if not m:
        return None
    girinti, rol, ad, kalan = m.groups()
    oz = re.match(r"((?:\s*\[[^\]]*\])*)", kalan).group(1)
    sonrasi = kalan[len(oz):]
    metin = sonrasi[1:].strip() if sonrasi.startswith(":") else ""
    if len(metin) >= 2 and metin[0] == metin[-1] == '"':
        metin = metin[1:-1]
    return {"girinti": len(girinti), "rol": rol, "ad": ad[1:-1] if ad else "",
            "oz": oz.strip(), "metin": metin, "cocuk": []}


def agac_kur(yaml_metni):
    kok = {"girinti": -1, "cocuk": []}
    yigin = [kok]
    for satir in yaml_metni.splitlines():
        dugum = satir_coz(satir)
        if dugum is None:
            continue
        while yigin[-1]["girinti"] >= dugum["girinti"]:
            yigin.pop()
        yigin[-1]["cocuk"].append(dugum)
        yigin.append(dugum)
    return kok


def gizle(d, veri):
    """Düğümün ad ve metnini gizleyerek döndürür. veri: veri kabından ya da veri listesinden geliyor mu."""
    rol, ad, metin = d["rol"], d["ad"], d["metin"]
    if rol == "/url":
        adres = metin.split("?")[0]
        return "", (sekil(adres) if veri else rakamsiz(adres))[:METIN_SINIRI]
    if rol in GIRDI_ROLLERI:
        return rakamsiz(ad)[:METIN_SINIRI], ""
    if veri and rol not in ("button", "columnheader"):      # düğme ve sütun başlığı etikettir, veri değil
        return sekil(ad)[:METIN_SINIRI], sekil(metin)[:METIN_SINIRI]
    return rakamsiz(ad)[:METIN_SINIRI], rakamsiz(metin)[:METIN_SINIRI]


def yaz(dugumler, derinlik, veri, satirlar):
    """Düğümleri ağaç sırasıyla yazar; art arda gelen aynı türden uzun dizileri özetler."""
    i = 0
    while i < len(dugumler):
        rol = dugumler[i]["rol"]
        j = i
        while j < len(dugumler) and dugumler[j]["rol"] == rol:
            j += 1
        adet = j - i
        veri_dizisi = rol in VERI_ROLLERI or (adet >= LISTE_ESIGI and rol != "columnheader")
        ozetle = veri_dizisi and rol not in ("cell", "gridcell")    # bir satırın hücreleri tablonun yapısıdır: hepsi görünsün
        gosterilecek = BENZER_ESIK if ozetle else adet
        for d in dugumler[i:i + gosterilecek]:
            ic_veri = veri or veri_dizisi
            ad, metin = gizle(d, ic_veri)
            satir = "  " * derinlik + "- " + d["rol"]
            if ad:
                satir += f' "{ad}"'
            if d["oz"]:
                satir += " " + d["oz"]
            if metin:
                satir += f": {metin}"
            elif d["cocuk"]:
                satir += ":"
            satirlar.append(satir)
            yaz(d["cocuk"], derinlik + 1, ic_veri, satirlar)
        if ozetle and adet > gosterilecek:
            satirlar.append("  " * derinlik + f"- ... (+{adet - gosterilecek} benzer: {rol})")
        i = j


def sayfa_ozeti(sayfa):
    yaml_metni = sayfa.locator("body").aria_snapshot()
    satirlar = []
    yaz(agac_kur(yaml_metni)["cocuk"], 0, False, satirlar)
    if len(satirlar) > SATIR_SINIRI:
        eksik = len(satirlar) - SATIR_SINIRI
        satirlar = satirlar[:SATIR_SINIRI] + [f"... ({eksik} satır daha, kısaltıldı)"]
    return satirlar


# ---------- tarayıcı ----------

def ag_kaydet(liste, yanit):
    """Sayfanın arka planda yaptığı veri isteklerini (yalnızca yöntem, durum, yol) not eder."""
    istek = yanit.request
    if istek.resource_type in ("xhr", "fetch"):
        satir = f"{istek.method} {yanit.status} {yol_gizle(yanit.url)}"
        if satir not in liste:
            liste.append(satir)


def tarayici_ac(p, args):
    secenekler = {"headless": args.gorunmez}
    if not args.gorunmez:
        secenekler["args"] = ["--start-maximized"]
    if args.tarayici_yolu:
        return p.chromium.launch(executable_path=args.tarayici_yolu, **secenekler)
    hata = None
    for kanal in ([args.tarayici] if args.tarayici else ["chrome", "msedge"]):
        try:
            return p.chromium.launch(channel=kanal, **secenekler)
        except Exception as e:      # o tarayıcı kurulu değil
            hata = e
    sys.exit(f"Chrome ya da Edge açılamadı. Chrome'un kurulu olduğundan emin olun.\n{hata}")


def kaydet(ctx, sira, ag):
    damga = datetime.now().strftime("%Y%m%d-%H%M%S")
    ad = f"kesif-{damga}-{sira}"
    bolumler = [
        f"# Keşif {sira} - {datetime.now():%d.%m.%Y %H:%M}",
        "# Rakamlar # ile, tablo/liste içerikleri x ile gizlendi; kutu değerleri ve bağlantı sorguları kaydedilmedi.",
        "# Yine de göndermeden önce göz atın: firma ya da kişi adı kalmışsa silin.",
    ]
    ctx.pages[0].wait_for_timeout(500)       # bekleyen ağ olaylarını işle
    sekmeler = [s for s in ctx.pages if s.url != "about:blank"]
    for k, s in enumerate(sekmeler, 1):
        bolumler.append(f"\n=== Sekme {k}: {yol_gizle(s.url)} ===")
        try:
            bolumler.append(f"Başlık: {rakamsiz(s.title())[:METIN_SINIRI]}")
            bolumler.extend(sayfa_ozeti(s))
        except Exception as e:
            bolumler.append(f"(sayfa okunamadı: {type(e).__name__})")
        try:
            s.screenshot(path=os.path.join(CIKTI, f"{ad}-sekme{k}.png"))
        except Exception:
            pass
    bolumler.append("\n=== Arka plan veri istekleri (yöntem, durum, yol) ===")
    bolumler.extend(ag[:80] or ["(yok)"])
    ag.clear()
    yol = os.path.join(CIKTI, ad + ".txt")
    with open(yol, "w", encoding="utf-8") as f:
        f.write("\n".join(bolumler) + "\n")
    return yol


def kesif(args):
    from playwright.sync_api import sync_playwright      # kurulum yapılmadan --help hata vermesin

    os.makedirs(CIKTI, exist_ok=True)
    koruma = os.path.join(CIKTI, ".gitignore")
    if not os.path.exists(koruma):
        with open(koruma, "w", encoding="utf-8") as f:
            f.write("*\n")                               # bu klasördeki hiçbir şey git'e girmesin

    ag = []
    with sync_playwright() as p:
        tarayici = tarayici_ac(p, args)
        ctx = tarayici.new_context(no_viewport=not args.gorunmez)
        ctx.on("response", lambda y: ag_kaydet(ag, y))
        sayfa = ctx.new_page()
        try:
            sayfa.goto(args.adres, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"Adres açılamadı ({type(e).__name__}); pencereden elle gitmeyi deneyebilirsiniz.")

        print("\nAçılan pencerede giriş yapın (doğrulama kodunu siz yazın).")
        print("Önerilen ekranlar, her biri için ekranı hazırlayıp bu pencerede Enter'a basın:")
        print("  1) giriş sonrası ana ekran")
        print("  2) firma seçme / değiştirme ekranı")
        print("  3) bir firma seçiliyken tebligat listesi")
        print("  4) bir tebligat açılmışken")
        print("Bitirince q yazıp Enter'a basın. Hiçbir şeye tıklamam, hiçbir şey yazmam; yalnızca okurum.")

        sira = 0
        while True:
            try:
                cevap = input("\nEnter = bu ekranı kaydet, q = çık: ").strip().lower()
            except EOFError:
                break
            if cevap == "q":
                break
            try:
                sira += 1
                print("Kaydedildi:", os.path.basename(kaydet(ctx, sira, ag)))
            except Exception as e:
                print(f"Kaydedilemedi ({type(e).__name__}). Tarayıcı penceresi kapatılmış olabilir.")
                break
        tarayici.close()
    print(f"\nDosyalar: {CIKTI}")


def main():
    ap = argparse.ArgumentParser(description="Dijital Vergi Dairesi yardımcısı (şimdilik yalnızca keşif modu)")
    ap.add_argument("--adres", default=ADRES, help="açılacak adres")
    ap.add_argument("--tarayici", choices=["chrome", "msedge"], help="varsayılan: önce Chrome, yoksa Edge")
    ap.add_argument("--tarayici-yolu", help="tarayıcı programının tam yolu (deneme için)")
    ap.add_argument("--gorunmez", action="store_true", help="pencere açmadan çalıştır (yalnızca deneme için)")
    kesif(ap.parse_args())


if __name__ == "__main__":
    main()
