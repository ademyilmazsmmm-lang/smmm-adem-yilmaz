# -*- coding: utf-8 -*-
"""Kar/zarar projesi icin sahte portallar: Luca'ya Hesap Plani Listesi, ayrica sahte Defter Beyan.

luca-bot/testler/sahte_luca.py'yi (Luca taklidi) genisletir; luca-bot'a dokunmaz:
  * Muhasebe > Hesap Planı İşlemleri > Hesap Planı Listesi (Filtre > Hesap Arama > Ara)
  * Defter Beyan: /auth/login, /mmislemleri/mukellefyonetimi, /muhasebe/hesapozeti
"""

import json
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sahte_luca  # noqa: E402
from sahte_luca import KILIT, ORTAK_STIL  # noqa: E402,F401

# Defter Beyan taklidi: VKN -> (unvan, defter turu, hasilat, mal alisi, giderler) aylik
DB_MUKELLEFLER = {
    "1111111111": ("ALFA İŞLETME", "İŞLETME", 500000, 100000, 300000),
    "2222222222": ("DENTAL SAĞLIK HİZMETLERİ", "BİLANÇO", 0, 0, 0),
    "4444444444": ("FATURASIZ ANONİM ŞİRKETİ", "İŞLETME", 100000, 20000, 30000),
    "5555555555": ("KEREM TİCARET", "İŞLETME", 200000, 0, 250000),
    "7777777777": ("YENİ FİRMA LİMİTED", "İŞLETME", 100000, 20000, 30000),
    "8888888888": ("KAPANMIŞ FİRMA", "İŞLETME", 1, 1, 1),   # defter donemi 2025'te bitmis
    "9999999999": ("SERBEST KİŞİ", "SMK", 90000, 0, 40000),  # serbest meslek: ozette Kar/Zarar satiri yok
}
DB_KAPANIS = {"8888888888": "31.12.2025"}
DB_DURUM = {"giris": False, "vkn": None}
# Luca hesap plani taklidi: firma -> aylik (6'li gelir, 150-153 mal alisi, 7'li gider)
HESAP_PLANI_VERI = {"DENTAL SAGLIK": (100000, 20000, 30000), "MERT INSAAT": (10000, 5000, 20000)}
HESAP_PLANI_VARSAYILAN = (50000, 10000, 20000)


def tr_sayi(x):
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def ay_sayisi(bas, bit):
    """GG/AA/YYYY ya da GG.AA.YYYY aralikinda kac ay oldugu."""
    b = [int(p) for p in bas.replace(".", "/").split("/")]
    t = [int(p) for p in bit.replace(".", "/").split("/")]
    return max(1, (t[2] - b[2]) * 12 + t[1] - b[1] + 1)


def hesap_plani_satirlari(firma, bas, bit):
    gelir, stok, gider = HESAP_PLANI_VERI.get(firma, HESAP_PLANI_VARSAYILAN)
    m = ay_sayisi(bas, bit)
    gelir, stok, gider = gelir * m, stok * m, gider * m
    # (kod, ad, tip, borc, alacak); sinif ve ana hesap satirlari toplamlari tasir
    return [
        ("1", "DÖNEN VARLIKLAR", "Ana", stok, 0), ("15", "STOKLAR", "Ana", stok, 0),
        ("153", "TİCARİ MALLAR", "Ana", stok, 0), ("153.01", "ALINAN MALLAR", "Alt", stok, 0),
        ("6", "GELİR TABLOSU HESAPLARI", "Ana", 0, gelir), ("60", "BRÜT SATIŞLAR", "Ana", 0, gelir),
        ("600", "YURTİÇİ SATIŞLAR", "Ana", 0, gelir), ("600.01", "SATIŞLAR", "Alt", 0, gelir),
        ("7", "MALİYET HESAPLARI", "Ana", gider, 0), ("770", "GENEL YÖNETİM GİDERLERİ", "Ana", gider, 0),
        ("770.01", "GİDERLER", "Alt", gider, 0),
    ]


def db_ozet(vkn, bas, bit):
    _, _, hasilat, alis, gider = DB_MUKELLEFLER[vkn]
    m = ay_sayisi(bas, bit)
    hasilat, alis, gider = hasilat * m, alis * m, gider * m
    fark = hasilat - alis - gider
    return hasilat, alis, gider, max(fark, 0), max(-fark, 0)


# Gercek Luca'daki Hesap Planı Listesi gibi sunucuda cizilir: form GET ile yeniden yuklenir, 150'serlik sayfalar,
# Hesap Arama penceresi (#secimDiv: kebirDeger, tarih1, tarih2, Ara = gonder('', 'search')), varsayilan 1. sinif.
SAYFA_BOYU = 150
MESGUL_MS = 6500   # gercek Luca'da buyuk firmalarda: sayfa yuklenirken yapilan islem uyariyla yok sayilir
SINIF_ADLARI = {"1": "1 Dönen Varlıklar", "2": "2 Duran Varlıklar", "6": "6 Gelir Tablosu Hesapları",
                "7": "7 Maliyet Hesapları", "": "Tümü"}


def hesap_plani_sayfasi(firma, q):
    bas, bit = q.get("tarih1") or "01/01/2026", q.get("tarih2") or "31/12/2026"
    sinif = q.get("kebirDeger", "1")
    sayfa = int(q.get("sayfaNo") or 1)
    satirlar = hesap_plani_satirlari(firma, bas, bit)
    # 2. sinif: sayfalamayi denemek icin cok sayida hesap (kodlar siralamada 153.01 ile 6 arasina duser)
    satirlar += [(f"2{i:02d}", f"DURAN VARLIK {i}", "Ana", 0, 0) for i in range(200)]
    satirlar.sort(key=lambda r: [int(x) if x.isdigit() else x for x in r[0].replace(".", " . ").split()])
    if sinif:
        satirlar = [r for r in satirlar if r[0].startswith(sinif)]
    sayfadakiler = satirlar[(sayfa - 1) * SAYFA_BOYU: sayfa * SAYFA_BOYU]
    tr = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in (
        k, ad, tip, tr_sayi(b), tr_sayi(a), tr_sayi(max(b - a, 0)), tr_sayi(max(a - b, 0)), "B" if b >= a else "A", ""))
        + "</tr>" for k, ad, tip, b, a in sayfadakiler)
    secenekler = "".join(f'<option value="{k}"{" selected" if k == sinif else ""}>{v}</option>'
                         for k, v in (("", "Tümü"), ("1", SINIF_ADLARI["1"]), ("2", SINIF_ADLARI["2"]),
                                      ("6", SINIF_ADLARI["6"]), ("7", SINIF_ADLARI["7"])))
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Hesap Planı Listesi</title>
""" + ORTAK_STIL + f"""</head><body>
<form name="hesapPlaniSearchForm" method="get" action="/hesap-plani">
<input type="hidden" name="firma" value="{firma}">
<input type="hidden" id="sayfaNo" name="sayfaNo" value="{sayfa}">
<input type="hidden" id="sayfaBasinaKayitSayisi" name="sayfaBasinaKayitSayisi" value="{len(sayfadakiler)}">
<div id="secimDiv" class="luca-open-window gizli"><div class="header">Hesap Arama</div>
 <table><tr><th>Hesap Sınıfı</th><td><select name="kebirDeger" id="kebirDeger">{secenekler}</select></td></tr>
  <tr><th>Hesap Kodu</th><td><input type="text" name="hesapKodu" id="hesapKodu"></td></tr>
  <tr><th>Başlangıç Tarih</th><td><input type="text" name="tarih1" id="tarih1" value="{bas}"></td></tr>
  <tr><th>Bitiş Tarih</th><td><input type="text" name="tarih2" id="tarih2" value="{bit}"></td></tr>
  <tr><th>Çalışmayan Hesaplar</th><td><select name="calismayanHesap" id="calismayanHesap">
   <option value="0">Tümünü Göster</option><option value="1"{" selected" if q.get("calismayanHesap") == "1" else ""}>Çalışmayan Hesapları Gösterme</option></select></td></tr></table>
 <button type="button" onclick="gonder('','search')">Ara</button></div>
</form>
<table class="ana"><tr><th>HESAP PLANI LİSTESİ</th></tr></table>
<table id="liste"><thead><tr><th>Hesap Kodu</th><th>Hesap Adı</th><th>Tipi</th><th>Borç</th><th>Alacak</th>
<th>Borç Bakiyesi</th><th>Alacak Bakiyesi</th><th>B/A</th><th>Birim</th></tr></thead><tbody>{tr}</tbody></table>
<div><button>Yenile</button> <button>Yeni Hesap</button> <button>Hesap Düzenle</button>
<button type="button" id="filtre" onclick="document.getElementById('secimDiv').classList.remove('gizli')">Filtre</button>
<button>Cari Hesap Tanımları</button> <button>Kullanım</button> <button>Rapor</button></div>
<div id="uyari" style="display:none;position:fixed;right:10px;bottom:10px;background:#ffd;border:1px solid #888;padding:6px">
 Lütfen işleminiz sürerken işleminizi tekrarlamayın.</div>
<script>
 const T0 = Date.now();
 const mesgul = () => {{ if (Date.now() - T0 < {MESGUL_MS}) {{
   const u = document.getElementById('uyari'); u.style.display = 'block'; setTimeout(() => u.style.display = 'none', 2500);
   return true; }} return false; }};
 for (const k of ['tarih1', 'tarih2']) {{
   const e = document.getElementById(k);
   e.addEventListener('input', () => {{ if (Date.now() - T0 < {MESGUL_MS}) setTimeout(() => {{ e.value = ''; mesgul(); }}, 50); }});
 }}
 function gonder(kod, hedef) {{ if (mesgul()) return; document.forms[0].submit(); }}
 function sonraki() {{
   if (mesgul()) return;
   const no = Number(document.getElementById('sayfaNo').value);
   if (Number(document.getElementById('sayfaBasinaKayitSayisi').value) != {SAYFA_BOYU}) return;
   document.getElementById('sayfaNo').value = no + 1; document.forms[0].submit();
 }}
</script></body></html>"""


DB_BASLIK = """<div style="background:#146;color:#fff;padding:6px">ADEM YILMAZ adına işlem yapmaktasınız.
<span style="float:right;background:#a22;padding:2px 8px">__ROZET__</span><br>
( Başlangıç Tarihi: __DB_BAS__ - Bitiş Tarihi: __DB_BIT__ )</div>"""

DB_GIRIS = """<!doctype html><html><head><meta charset="utf-8"><title>Defter Beyan</title></head><body>
<h2>DEFTER BEYAN SİSTEMİ</h2>
<label>İnternet Vergi Dairesi Kullanıcı Kodu</label><input type="text" id="k"><br>
<label>İnternet Vergi Dairesi Şifresi</label><input type="password" id="s"><br>
<label>Güvenlik Kodu</label><input type="text" id="g"><br>
<button id="gir">GİRİŞ YAP</button>
<script>
 document.getElementById('gir').onclick = async () => {
   await fetch('/db/giris?kod=' + document.getElementById('g').value, {method: 'POST'});
   location.href = '/mmislemleri/mukellefyonetimi';
 };
 // insan guvenlik kodunu birkac sn sonra yazip giris yapar
 setTimeout(() => { document.getElementById('g').value = '50552'; document.getElementById('gir').click(); }, 1800);
</script></body></html>"""

DB_MUKELLEF_SAYFASI = """<!doctype html><html><head><meta charset="utf-8"><title>Mükellef Yönetimi</title></head><body>
__BASLIK__
<h3>MÜKELLEF YÖNETİMİ</h3>
<p>Toplam __SAYI__ adet mükellefiniz bulunmaktadır.Mükellef Seçiniz:</p>
<label>Vergi Kimlik Numarası</label>
<span class="vcombo" id="kutu" style="display:inline-block;border:1px solid #888;padding:4px;min-width:200px">Vergi Kimlik Numarası</span>
<div id="acilir" style="display:none;border:1px solid #888;width:300px">
 <input id="ara" type="text"><ul id="liste" style="list-style:none;padding:0"></ul></div>
<button id="gecis">Hızlı Geçiş Yap</button>
<script>
 const TUM = __MUKELLEFLER__; let secili = '';
 const ul = document.getElementById('liste'), ara = document.getElementById('ara');
 function ciz(f){ ul.innerHTML = ''; TUM.filter(x => x.includes(f)).forEach(x => {
   const li = document.createElement('li'); li.className = 'vopt';
   li.textContent = x; li.onclick = () => { secili = x.split(' - ')[0]; document.getElementById('kutu').textContent = x;
     document.getElementById('acilir').style.display = 'none'; }; ul.appendChild(li); }); }
 document.getElementById('kutu').onclick = () => { document.getElementById('acilir').style.display = 'block'; ciz(''); ara.focus(); };
 ara.oninput = () => ciz(ara.value);
 document.getElementById('gecis').onclick = async () => { if (!secili) return;
   await fetch('/db/gecis?vkn=' + secili, {method: 'POST'}); location.href = '/muhasebe/hesapozeti'; };
</script></body></html>"""

DB_OZET_SAYFASI = """<!doctype html><html><head><meta charset="utf-8"><title>Hesap Özeti</title></head><body>
__BASLIK__
<a id="geri" href="#">Kendi Hesabıma Geri Dön</a>
<h4>Kazanç Hesaplama</h4>
<label>Başlangıç Tarihi</label><input type="text" id="bas" value="01.01.2026">
<label>Bitiş Tarihi</label><input type="text" id="bit" value="31.12.2026">
<button>Temizle</button><button id="olustur">Oluştur</button>
<div id="sonuc"></div>
<script>
 document.getElementById('geri').onclick = async e => { e.preventDefault();
   await fetch('/db/geri', {method: 'POST'}); location.href = '/mmislemleri/mukellefyonetimi'; };
 document.getElementById('olustur').onclick = async () => {
   const b = document.getElementById('bas').value, t = document.getElementById('bit').value;
   const r = await (await fetch('/api/db-ozet?bas=' + b + '&bit=' + t)).json();
   const g = x => x.replaceAll('.', '/');
   setTimeout(() => { document.getElementById('sonuc').innerHTML = '<h4>Mali Hesap Özeti</h4>'
    + '<div>Başlangıç Tarihi:<br>' + g(b) + '</div><div>Bitiş Tarihi:<br>' + g(t) + '</div>'
    + '<table border=1><tr><th>GİDERLER</th><th>TUTAR</th></tr>'
    + '<tr><td>Dönem Başı Emtia Mevcudu</td><td>0,00</td></tr>'
    + '<tr><td>Dönem İçinde Satın Alınan Emtia</td><td>' + r.alis + '</td></tr>'
    + '<tr><td>Giderler</td><td>' + r.gider + '</td></tr>'
    + '<tr><td>Amortisman Giderleri</td><td>0,00</td></tr>'
    + (r.smk ? '' : '<tr><td>Kar</td><td>' + r.kar + '</td></tr>') + '<tr><td>Genel Toplam</td><td>' + r.toplam + '</td></tr></table>'
    + '<table border=1><tr><th>GELİRLER</th><th>TUTAR</th></tr>'
    + '<tr><td>Dönem Sonu Emtia Mevcudu</td><td></td></tr>'
    + '<tr><td>Dönem İçinde Elde Edilen Hasılat</td><td>' + r.hasilat + '</td></tr>'
    + '<tr><td>Gelir Diğer Gelirler</td><td>0,00</td></tr><tr><td>-</td><td></td></tr>'
    + (r.smk ? '' : '<tr><td>Zarar</td><td>' + r.zarar + '</td></tr>') + '<tr><td>Genel Toplam</td><td>' + r.toplam + '</td></tr></table>'; }, 700);
 };
</script></body></html>"""


# Luca ana sayfasindaki Muhasebe menusune Hesap Planı Listesi eklenir
sahte_luca.ANA_SAYFA = sahte_luca.ANA_SAYFA.replace(
    "      <a>Hesap Planı İşlemleri</a>\n", '      <a id="hesapIslemleri">Hesap Planı İşlemleri</a>\n      <div id="hesapMenu" class="gizli" style="margin-left:14px"><a id="hesapListesi">Hesap Planı Listesi</a></div>\n', 1).replace(
    " const by = document.getElementById('beyannameler');", " const hi = document.getElementById('hesapIslemleri');\n hi.onmouseenter = hi.onclick = () =>\n   sonra(150, () => document.getElementById('hesapMenu').classList.remove('gizli'));\n document.getElementById('hesapListesi').onclick = () => {\n   document.getElementById('muhasebeMenu').classList.add('gizli');\n   sonra(300, () => sekmeAc('/hesap-plani?firma=' + encodeURIComponent(seciliFirma) + '&t=' + Date.now()));\n };\n const by = document.getElementById('beyannameler');", 1)

# Mizan: gercek Luca'daki gibi menuItems/aktar() ile acilir; form etiketleri gercektekiyle ayni, 'Rapor' Excel indirir
MIZAN_MENU_JS = """
 var menuItems = [["Muhasebe", ""], ["|||Mizan", "raporMizanHazirla.do?c_musteri_id=1"]];
 function aktar(link) { sekmeAc('/mizan?firma=' + encodeURIComponent(seciliFirma) + '&t=' + Date.now()); }
"""
sahte_luca.ANA_SAYFA = sahte_luca.ANA_SAYFA.replace("</script></body></html>", MIZAN_MENU_JS + "</script></body></html>", 1)

MIZAN_SAYFASI = """<!doctype html><html><head><meta charset="utf-8"><title>Mizan</title>
""" + ORTAK_STIL + """</head><body>
<div class="eski-rapor-paremetreleri" style="display:none">   <!-- gercek Luca'da ayni etiketli gizli eski form vardir -->
 <table><tr><th>Başlangıç Fiş Tarihi</th><td><input type="text" id="TARIH_ILK"></td><th>Bitiş Fiş Tarihi</th><td><input type="text" id="TARIH_SON"></td></tr></table>
</div>
<div class="yeni-rapor-paremetreleri">
<table class="form_table">
<tr><th>Yıl</th><td><select disabled><option>2026</option></select></td><th>Ay</th><td><select id="ay"><option></option></select></td></tr>
<tr><th>Başlangıç Fiş Tarihi</th><td><table><tr><td><input type="text" id="tarih_ilk"></td><td><img alt="takvim"></td></tr></table></td>
    <th>Bitiş Fiş Tarihi</th><td><table><tr><td><input type="text" id="tarih_son"></td><td><img alt="takvim"></td></tr></table></td></tr>
<tr><th>Hesap Tipi</th><td><div class="multiselect"><select id="hesap_tipi"><option selected>Tümü</option></select></div></td></tr>
<tr><th>Hesap Planı Dövizi Göster</th><td><select id="hesap_plani_dovizi_goster"><option value="1" selected>Göster</option><option value="0">Gösterme</option></select></td></tr>
<tr><th>Bakiye Göster</th><td><select id="bakiye_goster"><option value="1" selected>Borç Bakiye - Alacak Bakiye Göster</option>
    <option value="2">Bakiye Göster</option><option value="0">Gösterme</option></select></td></tr>
<tr><th>Bakiyesiz ve Çalışmayan Hesaplar</th><td><select id="bakiye_tipi"><option value="0">Tümünü Göster</option>
    <option value="1" selected>Çalışmayan Hesapları Gösterme</option><option value="2">Bakiyesiz Hesapları Gösterme</option></select></td></tr>
<tr id="p_rapor_turu_yazdir"><th colspan="1">Rapor Türü</th><td colspan="5"><select id="report_type"><option value="PDF">PDF</option>
    <option value="DOCX">Word (docx)</option><option value="LIST">Excel Liste (xlsx)</option></select></td></tr>
</table></div>
<div><button type="button">Kümülatif Rapor</button> <button type="button" class="green bold" onclick="gonder()"><i aria-hidden="true"></i> Rapor</button></div>
<script>
 // gercek Luca Mizan sayfasi gibi: dizi yontemleri bozuk ("ops.find is not a function")
 Array.prototype.find = undefined; Array.prototype.filter = undefined; Array.prototype.some = undefined;
 function gonder() {
   const v = id => encodeURIComponent(document.getElementById(id).value);
   if (document.getElementById('report_type').value !== 'LIST') return;
   if (document.getElementById('bakiye_goster').value !== '2') return;   // dogru ayarlar yapilmadiysa indirme olmaz
   // gercek Luca: rapor yeni pencerede acilir, pencere kisa sure sonra kendini kapatir (indirme o sirada surerken)
   const w = window.open('/mizan.xlsx?firma=__FIRMA__&bas=' + v('tarih_ilk') + '&bit=' + v('tarih_son'), '_blank');
   setTimeout(() => { try { w.close(); } catch (e) {} }, 500);
   // gercek kullanimda form sayfasinin kendisi de kapanip indirmeyi yarida kesebildi (Chrome kapandi)
   setTimeout(() => { try { window.close(); } catch (e) {} }, 700);
 };
</script></body></html>"""


def mizan_xlsx(firma, bas, bit):
    import io
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "MİZAN"
    ws.append(["MİZAN"])
    ws.append([firma])
    ws.append(["Dönem :", "01/01/2026-31/12/2026"])
    ws.append(["Tarih Aralığı :", f"{bas}-{bit}"])
    ws.append([])
    ws.append(["HESAP KODU", "HESAP ADI", "BORÇ", "ALACAK", "BAKİYE", " "])
    for kod, ad, tip, b, a in hesap_plani_satirlari(firma, bas, bit):
        # Hesap Tipi = Tumu: ana ve alt hesaplar birlikte gelir
        ws.append([kod, ad, b or None, a or None, abs(b - a), "B" if b >= a else "A"])
    cikti = io.BytesIO()
    wb.save(cikti)
    return cikti.getvalue()


# --- Luca > Isletme Defteri > "Defter Beyan Sistemi" sayfasi (luca2.do?tur=defter_beyan) -----------------------
# Ekran goruntulerinden: Gelirler / Giderler / Gelir Alt Tur Tanimlari / Muhtasar; Evrak Tarihi + Durum + Gonderilme
# Tarihi + Listele; liste (baslik kutusu, #, Seri No, Evrak No, Evrak Tarihi, ... ) ve alttaki arac cubugu
# (Kaydet, Arama, Yenile, Islemler > Defter Beyan Sistemine Gonder, ...). Gonder: SORGULAMA UYARI > Giris Bilgileri >
# DEFTER BEYAN ENTEGRASYON penceresi ("gonderim tamamlandi. (N)").
DB_SEC = {"firma": sahte_luca.FIRMALAR[0]}      # secili firma (gercek Luca'da sunucu oturumunda)
DB_GONDERILDI = set()                            # (firma, tur, evrak no)
DB_OLAYLAR = []                                  # sunucu tarafi islem sirasi: cari, kaydet, gonder
DB_AYAR = {"jqx": False, "sabit_hatasi": False, "satir_hatasi": False, "gonderim_hatasi": False, "api_bos": False, "yavas": 0.0}
DB_TARIHLER = ("03/10/2026", "15/10/2026", "28/10/2026", "05/11/2026")


def db_kayitlari(firma, tur):
    """[(evrak no, tarih, kategori, belge turu, aciklama, tutar)]: firmaya gore degisen sabit veri."""
    taban = {"ALFA ISLETME": {"gelir": 1, "gider": 3}, "FATURASIZ AS": {"gelir": 0, "gider": 0},
             "KEREM TICARET": {"gelir": 2, "gider": 1}, "SERBEST KISI": {"gelir": 1, "gider": 1}}.get(firma, {})
    adet = taban.get(tur, 0)
    kategori, belge = (("Serbest Meslek Fişleri", "Meslek Gideri") if tur == "gider" else ("Satışlar", "Fatura"))
    sonuc = []
    for i in range(adet):
        sabit = tur == "gider" and adet >= 3 and i == adet - 1      # ALFA: gider listesinin son kaydi sabit kiymet
        sonuc.append((f"{'GDR' if tur == 'gider' else 'GLR'}{firma[:2]}{i + 1:04d}", DB_TARIHLER[i % 4],
                      "Sabit Kıymet" if sabit else kategori, "Amortisman" if sabit else belge,
                      f"{firma} kayıt {i + 1}", 1000.0 * (i + 1) + 250.5))
    return sonuc


def db_liste(firma, tur, bas, bit, durum):
    def gun(t):
        g, a, y = (int(x) for x in t.split("/"))
        return (y, a, g)
    sonuc = []
    for k in db_kayitlari(firma, tur):
        gonderildi = (firma, tur, k[0]) in DB_GONDERILDI
        if not (gun(bas) <= gun(k[1]) <= gun(bit)):
            continue
        if durum == "Gönderilmemişler" and gonderildi or durum == "Gönderilmişler" and not gonderildi:
            continue
        sonuc.append(k)
    return sonuc


DB_SAYFASI = """<!doctype html><html><head><meta charset="utf-8"><title>Defter Beyan</title>
""" + ORTAK_STIL + """
<style>#menu{background:#777;color:#fff;padding:6px}#menu a{margin-right:16px;cursor:pointer;color:#fff}
.alt{position:fixed;bottom:0;left:0;right:0;background:#9bb;padding:4px}.alt button{margin-right:8px}
#islemMenu{position:fixed;bottom:30px;left:120px;background:#fff;border:1px solid #888}
#islemMenu a{display:block;padding:6px 10px;cursor:pointer}</style></head><body>
<div class="gizli" id="tuzak">Evrak Tarihi <input type="text" value="01/01/2000"> <input type="text" value="02/01/2000">
 <button>Listele</button></div>
<div id="menu"><a id="gelir">Gelirler</a><a id="gider">Giderler</a><a>Gelir Alt Tür Tanımları</a><a>Muhtasar</a></div>
<div id="form"><h4 id="baslik">Gelir Listesi</h4>
 <table style="border:0"><tr><td style="border:0">Evrak Tarihi</td>
 <td style="border:0"><input type="text" id="b1" value="01/10/2026"> <input type="text" id="b2" value="31/10/2026"></td></tr>
 <tr><td style="border:0">Durum</td><td style="border:0"><select id="durum" style="display:none"><option>Tümü</option>
 <option>Gönderilmemişler</option><option>Gönderilmişler</option></select>
 <div id="durumGos" style="border:1px solid #888;width:200px;cursor:pointer"><span id="durumYazi">Tümü</span> <span>▾</span></div>
 <div id="durumListe" class="gizli" style="border:1px solid #888;width:200px"><div class="d">Tümü</div>
 <div class="d">Gönderilmemişler</div><div class="d">Gönderilmişler</div></div></td></tr>
 <tr><td style="border:0">Gönderilme Tarihi</td><td style="border:0"><input type="text" id="g1"> <input type="text" id="g2"></td></tr>
 <tr><td style="border:0"></td><td style="border:0"><button id="listele">Listele</button></td></tr></table></div>
<div id="liste" class="gizli">
 <table id="grid"><thead><tr><th><input type="checkbox" id="hepsi"></th><th>#</th><th>Seri No</th><th>Evrak No</th>
 <th>Evrak Tarihi</th><th>Kategori</th><th>Belge Türü</th><th>Fiş Açıklama</th><th>Tutar</th></tr></thead><tbody></tbody></table></div>
<div class="alt gizli" id="arac"><button id="kaydet">Kaydet</button><button id="arama">Arama</button><button>Yenile</button>
 <button id="islemler">İşlemler ▲</button><button>Sütunlar</button><button>KDV Hariç</button><button>KDV Dahil</button>
 <button>GİB DBS Portalı</button></div>
<div id="islemMenu" class="gizli"><a>Defter Beyan Sisteminden Sil</a><a id="gonder">Defter Beyan Sistemine Gönder</a>
 <a id="cari">Cari Bilgi Sorgula</a><a>Toplu Değer Ata</a></div>
<div id="cariPen" class="luca-open-window gizli"><b>CARİ BİLGİ SORGULA</b><p>Cari bilgi sorgulama tamamlandı.</p>
 <button id="cTamam">Tamam</button></div>
<div id="kayPen" class="luca-open-window gizli"><b>BİLGİ</b><p>Kayıt işlemi tamamlandı.</p><button id="kTamam">Tamam</button></div>
<div id="uyari" class="luca-open-window gizli"><b>SORGULAMA UYARI</b><p>Sadece seçili kayıtlar üzerinde işlem yapılacaktır.
 Gönderilmemiş kayıtları seçmek için <a href="#">buraya</a> tıklayınız.<br><br>Devam etmek istiyor musunuz?</p>
 <button id="uTamam">Tamam</button> <button id="uKapat">Kapat</button></div>
<div id="giris" class="luca-open-window gizli"><b>Defter Beyan Sistemi - Giriş Bilgileri</b>
 <p>Giriş Yöntem: <select><option>API Key/Secret</option></select><br>
 API Key: <input type="text" id="apiKey" value="__KEY__"><br>API Secret: <input type="text" id="apiSecret" value="__SECRET__"></p>
 <button id="gTamam">Tamam</button> <button id="gKapat">Kapat</button></div>
<div id="ent" class="luca-open-window gizli"><b>DEFTER BEYAN ENTEGRASYON</b>
 <div id="entYazi" style="border:1px solid #000;height:120px;width:340px;white-space:pre"></div>
 <button id="eTamam">Tamam</button></div>
<script>
 const g = id => document.getElementById(id);
 g('durumGos').onclick = () => g('durumListe').classList.toggle('gizli');
 document.querySelectorAll('#durumListe .d').forEach(d => d.onclick = () => { g('durum').value = d.textContent;
   g('durumYazi').textContent = d.textContent; g('durumListe').classList.add('gizli'); });
 let tur = 'gelir', kayitlar = [];
 const JQX = __JQX__;
 // jqx grid taklidi: <table> yok, yalniz ilk 5 satir cizilir (sanal kaydirma); satirlar grid arayuzunden okunur/secilir
 let secilen = new Set();
 const KOLONLAR = [['', ''], ['#', 'no'], ['Seri No', 'seri'], ['Evrak No', 'evrak'], ['Evrak Tarihi', 'tarih'],
   ['Kategori', 'kategori'], ['Belge Türü', 'belge'], ['Fiş Açıklama', 'aciklama'], ['Tutar', 'tutar']];
 function hucre(i, df) { const k = kayitlar[i]; if (!k) return '';
   return {no: String(i + 1), seri: '', evrak: k[0], tarih: k[1], kategori: k[2], belge: k[3], aciklama: k[4],
           tutar: k[5].toLocaleString('tr-TR', {minimumFractionDigits: 2})}[df] || ''; }
 if (JQX) {
   g('grid').remove();
   g('liste').insertAdjacentHTML('afterbegin', '<div id="jg" class="jqx-grid"><div role="row"><div role="columnheader">' +
     '<div class="jqx-checkbox" id="jqxHepsi">&#9744;</div></div>' + KOLONLAR.slice(1).map(c =>
     '<div role="columnheader">' + c[0] + '</div>').join('') + '</div><div id="jgGovde"></div></div>');
   const yontem = {
     columns: () => ({records: KOLONLAR.map(c => ({text: c[0], datafield: c[1], hidden: false}))}),
     getdatainformation: () => ({rowscount: kayitlar.length}),
     getcelltext: (i, df) => hucre(i, df),
     selectallrows: () => { secilen = new Set(kayitlar.map((_, i) => i)); jqxCiz(); },
     getselectedrowindexes: () => [...secilen],
   };
   window.jQuery = el => ({jqxGrid: (m, ...a) => yontem[m](...a)});
   window.jQuery.fn = {jqxGrid: true};
   g('jqxHepsi').onclick = () => yontem.selectallrows();
 }
 function jqxCiz() {   // yalniz ilk 5 satir DOM'da (sanal kaydirma)
   g('jgGovde').innerHTML = kayitlar.slice(0, 5).map((k, i) => '<div role="row"><div role="gridcell">' +
     (secilen.has(i) ? '&#9745;' : '&#9744;') + '</div>' + KOLONLAR.slice(1).map(c =>
     '<div role="gridcell">' + hucre(i, c[1]) + '</div>').join('') + '</div>').join(''); }
 function sekme(t) { tur = t; g('baslik').textContent = (t == 'gelir' ? 'Gelir' : 'Gider') + ' Listesi';
   g('form').classList.remove('gizli'); g('liste').classList.add('gizli'); g('arac').classList.add('gizli'); }
 g('gelir').onclick = () => sekme('gelir'); g('gider').onclick = () => sekme('gider');
 g('listele').onclick = async () => {
   const q = 'tur=' + tur + '&bas=' + encodeURIComponent(g('b1').value) + '&bit=' + encodeURIComponent(g('b2').value)
     + '&durum=' + encodeURIComponent(g('durum').value);
   kayitlar = await (await fetch('/api/db-liste?' + q)).json();
   setTimeout(() => { const tb = JQX ? {insertAdjacentHTML() {}, set innerHTML(v) {}} : g('grid').querySelector('tbody'); tb.innerHTML = '';
     if (JQX) { secilen = new Set(); jqxCiz(); }
     kayitlar.forEach((k, i) => tb.insertAdjacentHTML('beforeend', '<tr><td><input type="checkbox"></td><td>' + (i + 1)
       + '</td><td></td><td>' + k[0] + '</td><td>' + k[1] + '</td><td>' + k[2] + '</td><td>' + k[3] + '</td><td>' + k[4]
       + '</td><td>' + k[5].toLocaleString('tr-TR', {minimumFractionDigits: 2}) + '</td></tr>'));
     if (!JQX) g('hepsi').checked = false; g('form').classList.add('gizli'); g('liste').classList.remove('gizli');
     g('arac').classList.remove('gizli');
     if (!kayitlar.length) { const u = document.createElement('div'); u.textContent = 'Kayıt bulunamadı'; } }, 400); };
 if (!JQX) g('hepsi').onchange = () => g('grid').querySelectorAll('tbody input').forEach(k => k.checked = g('hepsi').checked);
 const olay = ad => fetch('/api/db-olay?ad=' + ad);
 g('cari').onclick = () => { g('islemMenu').classList.add('gizli'); olay('cari');
   setTimeout(() => g('cariPen').classList.remove('gizli'), 300); };
 g('cTamam').onclick = () => g('cariPen').classList.add('gizli');
 g('kaydet').onclick = () => { olay('kaydet');   // gercek Luca gibi: kayit sonrasi liste yenilenir, secim kalkar
   if (JQX) { secilen = new Set(); jqxCiz(); } else { g('grid').querySelectorAll('tbody input').forEach(k => k.checked = false); g('hepsi').checked = false; }
   setTimeout(() => g('kayPen').classList.remove('gizli'), 300); };
 g('kTamam').onclick = () => g('kayPen').classList.add('gizli');
 g('arama').onclick = () => { g('form').classList.remove('gizli'); g('liste').classList.add('gizli'); };
 g('islemler').onclick = () => g('islemMenu').classList.toggle('gizli');
 g('gonder').onclick = () => { g('islemMenu').classList.add('gizli'); setTimeout(() => g('uyari').classList.remove('gizli'), 200); };
 g('uKapat').onclick = () => g('uyari').classList.add('gizli');
 g('uTamam').onclick = () => { g('uyari').classList.add('gizli'); setTimeout(() => g('giris').classList.remove('gizli'), 250); };
 g('gKapat').onclick = () => g('giris').classList.add('gizli');
 g('gTamam').onclick = async () => {
   olay('gonder');
   g('giris').classList.add('gizli'); g('entYazi').textContent = ''; g('ent').classList.remove('gizli');
   const sec = JQX ? [...secilen].sort((a, b) => a - b).map(i => kayitlar[i][0]) :
     [...g('grid').querySelectorAll('tbody tr')].filter(r => r.querySelector('input').checked).map(r => r.children[3].textContent);
   const yaz = s => g('entYazi').textContent += s + '\\n';
   yaz('Defter Beyan Sistemine gönderim başlıyor.');
   if (!sec.length) { setTimeout(() => yaz('Gönderilecek seçili kayıt bulunamadı.'), 300); return; }
   const s = await (await fetch('/api/db-gonder?tur=' + tur, {method: 'POST', body: JSON.stringify(sec)})).json();
   sec.forEach((_, i) => setTimeout(() => { yaz((i + 1) + '. satır için.');
     if ((s.hatali || {})[sec[i]]) yaz(s.hatali[sec[i]] + ' (' + (i + 1) + '.1)'); }, 300 * (i + 1)));
   setTimeout(() => yaz(s.hata ? 'Hata: ' + s.hata : 'Defter Beyan Sistemine gönderim tamamlandı. (' + s.gonderilen + ')'),
     300 * (sec.length + 1));
 };
 g('eTamam').onclick = () => g('ent').classList.add('gizli');
 window.Luca = {defter_beyan: {gonder: t => g('gonder').click()}};
</script></body></html>"""


class Isleyici(sahte_luca.Isleyici):
    """Once kar/zarar rotalari, bulunamazsa Luca taklidi."""

    def _yanit(self, *a, **k):
        self._yanit_verildi = True
        return super()._yanit(*a, **k)

    def do_GET(self):
        self._yanit_verildi = False
        yol, firma, tip = self._parametre()
        self._kz_get(yol, firma)
        if not self._yanit_verildi:
            super().do_GET()

    def _kz_get(self, yol, firma):
        if yol == "/api/firma-sec":
            with KILIT:
                DB_SEC["firma"] = parse_qs(urlparse(self.path).query).get("firma", [DB_SEC["firma"]])[0]
            return self._yanit("{}", "application/json")
        if yol == "/Luca/luca2.do":
            bos = DB_AYAR["api_bos"]
            return self._yanit(DB_SAYFASI.replace("__JQX__", "true" if DB_AYAR["jqx"] else "false").replace("__KEY__", "" if bos else "TESTKEY123")
                               .replace("__SECRET__", "" if bos else "TESTSECRET456"))
        if yol == "/api/db-olay":
            with KILIT:
                DB_OLAYLAR.append(parse_qs(urlparse(self.path).query).get("ad", [""])[0])
            return self._yanit("{}", "application/json")
        if yol == "/api/db-liste":
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            import time
            time.sleep(DB_AYAR["yavas"])
            return self._yanit(json.dumps(db_liste(DB_SEC["firma"], q["tur"], q["bas"], q["bit"], q["durum"]),
                                          ensure_ascii=False), "application/json")
        if yol == "/mizan":
            return self._yanit(MIZAN_SAYFASI.replace("__FIRMA__", firma))
        if yol == "/mizan.xlsx":
            import time
            time.sleep(1.5)   # rapor hazirlanirken pencere kapanir
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            return self._yanit(mizan_xlsx(q.get("firma", ""), q.get("bas", ""), q.get("bit", "")),
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               {"Content-Disposition": 'attachment; filename="mizan.xlsx"'})
        if yol == "/hesap-plani":
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query, keep_blank_values=True).items()}
            return self._yanit(hesap_plani_sayfasi(firma, q))
        if yol == "/api/hesap-plani":
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            satirlar = [[k, ad, tip, tr_sayi(b), tr_sayi(a), tr_sayi(max(b - a, 0)), tr_sayi(max(a - b, 0)),
                         "B" if b >= a else "A", ""]
                        for k, ad, tip, b, a in hesap_plani_satirlari(q.get("firma", ""), q.get("bas", ""), q.get("bit", ""))]
            return self._yanit(json.dumps(satirlar), "application/json")
        if yol == "/auth/login":
            return self._yanit(DB_GIRIS)
        if yol in ("/mmislemleri/mukellefyonetimi", "/muhasebe/hesapozeti"):
            if not DB_DURUM["giris"]:
                return self._yanit(DB_GIRIS)
            vkn = DB_DURUM["vkn"]
            rozet = f"{vkn} - {DB_MUKELLEFLER[vkn][1]}" if vkn else "9000000001 - SMK"
            baslik = (DB_BASLIK.replace("__ROZET__", rozet)
                      .replace("__DB_BAS__", "01.01.2025" if vkn in DB_KAPANIS else "01.01.2026")
                      .replace("__DB_BIT__", DB_KAPANIS.get(vkn, "Devam Ediyor")))
            if yol == "/muhasebe/hesapozeti":
                return self._yanit(DB_OZET_SAYFASI.replace("__BASLIK__", baslik))
            liste = json.dumps([f"{v} - {d[0]}" for v, d in sorted(DB_MUKELLEFLER.items())], ensure_ascii=False)
            return self._yanit(DB_MUKELLEF_SAYFASI.replace("__BASLIK__", baslik)
                               .replace("__SAYI__", str(len(DB_MUKELLEFLER))).replace("__MUKELLEFLER__", liste))
        if yol == "/api/db-ozet":
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            h, a, g, kar, zarar = db_ozet(DB_DURUM["vkn"], q["bas"], q["bit"])
            return self._yanit(json.dumps({"hasilat": tr_sayi(h), "alis": tr_sayi(a), "gider": tr_sayi(g),
                                           "kar": tr_sayi(kar), "zarar": tr_sayi(zarar),
                                           "toplam": tr_sayi(h),
                                           "smk": DB_MUKELLEFLER[DB_DURUM["vkn"]][1] == "SMK"}), "application/json")

    def do_POST(self):
        self._yanit_verildi = False
        yol, firma, tip = self._parametre()
        if yol == "/api/db-gonder":
            tur = parse_qs(urlparse(self.path).query).get("tur", ["gelir"])[0]
            n = int(self.headers.get("Content-Length") or 0)
            evraklar = json.loads(self.rfile.read(n) or b"[]")
            with KILIT:
                if DB_AYAR["gonderim_hatasi"]:
                    return self._yanit(json.dumps({"hata": "Defter Beyan Sistemi yanıt vermedi", "gonderilen": 0}),
                                       "application/json")
                hatali = {}      # evrak -> hata yazisi; bunlar Defter Beyan'a gitmez, Gonderilmemisler'de kalir
                if DB_AYAR["satir_hatasi"] and evraklar:
                    hatali[evraklar[0]] = "Tutarı 0.00 olan satır girilemez."
                for e in evraklar:
                    k = next((x for x in db_kayitlari(DB_SEC["firma"], tur) if x[0] == e), None)
                    if k and "Sabit" in k[2] and DB_AYAR["sabit_hatasi"]:
                        hatali[e] = "Sabit kıymet adı boş olamaz. - 0"
                gidecek = [e for e in evraklar if e not in hatali]
                for e in gidecek:
                    DB_GONDERILDI.add((DB_SEC["firma"], tur, e))
            return self._yanit(json.dumps({"gonderilen": len(gidecek), "hatali": hatali, "hata": ""}), "application/json")
        if yol.startswith("/db/"):
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            with KILIT:
                if yol == "/db/giris":
                    DB_DURUM["giris"] = q.get("kod") == "50552"
                elif yol == "/db/gecis":
                    DB_DURUM["vkn"] = q.get("vkn")
                elif yol == "/db/geri":
                    DB_DURUM["vkn"] = None
            self._yanit("{}", "application/json")
        if not self._yanit_verildi:
            super().do_POST()


def baslat(port=0):
    sunucu = ThreadingHTTPServer(("127.0.0.1", port), Isleyici)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    return sunucu, f"http://127.0.0.1:{sunucu.server_address[1]}/"


def sifirla():
    sahte_luca.sifirla()
    DB_DURUM.update(giris=False, vkn=None)
    DB_SEC["firma"] = sahte_luca.FIRMALAR[0]
    DB_GONDERILDI.clear()
    DB_AYAR.update(gonderim_hatasi=False, api_bos=False, satir_hatasi=False, sabit_hatasi=False, jqx=False, yavas=0.0)
    DB_OLAYLAR.clear()
