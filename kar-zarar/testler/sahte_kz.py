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
 var menuItems = [["Muhasebe", ""], ["|||Mizan", "raporMizanHazirla.do?c_musteri_id=1"],
                  ["||||Muavin Defter", "raporMuavinDefterNoktaVurusluHazirla.do?c_musteri_id=1"],   // Nokta Vurusulu: Excel YOK (once gelir)
                  ["|||||Muavin Defter", "raporMuavinDefterHazirla.do?c_musteri_id=1"],
                  ["||||İşletme Defteri Dökümü", "raporIsletmeDefteriHazirla.do?c_musteri_id=1"],
                  ["||||Toplu Belge Türü ve Ödeme Yöntemi Düzenleme", "parameterBelgeTuruDuzenlemeAction.do?tip=jsp&c_musteri_id=1"],
                  ["||||Fiş Listesi", "listFisAction.do?c_musteri_id=1"]];
 function aktar(link) {
   if (link.indexOf('listFisAction') >= 0) { sekmeAc('/fis-listesi?firma=' + encodeURIComponent(seciliFirma) + '&t=' + Date.now()); return; }
   if (link.indexOf('BelgeTuruDuzenleme') >= 0) {   // gercek Luca: form ayri bir tarayici penceresinde acilir
     window.open('/edefter-form?firma=' + encodeURIComponent(seciliFirma) + '&t=' + Date.now(), '_blank', 'popup,width=1100,height=800');
     return;
   }
   sekmeAc((link.indexOf('Nokta') >= 0 ? '/muavin-nokta' : link.indexOf('Muavin') >= 0 ? '/muavin' : link.indexOf('Isletme') >= 0 ? '/isletme' : '/mizan') + '?firma=' + encodeURIComponent(seciliFirma) + '&t=' + Date.now());
 }
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


# --- Luca > Muhasebe > Raporlar > Genel Raporlar > Defterler > Muavin Defter (varsayimsal form; gercegiyle birebir olmayabilir) ---
# MUAVIN_VERI[(firma, hesap)] = [(tarih, fis no, aciklama, borc, alacak)]; testler doldurur. MUAVIN_AYAR: hesap_alani=False ise form
# hesap kodu alani icermez (dokum tum hesaplari getirir); excel_adi: Rapor Turu seceneginin adi.
MUAVIN_VERI = {}
MUAVIN_AYAR = {"hesap_alani": True, "excel_adi": "Excel (xlsx)", "istekler": []}
MUAVIN_SAYFASI = """<!doctype html><html><head><meta charset="utf-8"><title>Muavin Defter</title>
""" + ORTAK_STIL + """</head><body>
<div class="yeni-rapor-paremetreleri"><table class="form_table">
<tr><th>Başlangıç Fiş Tarihi</th><td><input type="text" id="p_fis_tarihi_ilk_1"></td><th>Bitiş Fiş Tarihi</th><td><input type="text" id="p_fis_tarihi_son_1"></td></tr>
__HESAP__
<tr><th>Rapor Türü</th><td colspan="3"><select id="report_type"><option value="PDF">PDF</option><option value="LIST">__EXCEL__</option></select></td></tr>
</table></div>
<div><button type="button" class="green bold" onclick="gonder()">Rapor</button></div>
<script>
 function gonder() {
   const v = id => { const e = document.getElementById(id); return encodeURIComponent(e ? e.value : ''); };
   if (document.getElementById('report_type').value !== 'LIST') return;
   const w = window.open('/muavin.xlsx?firma=__FIRMA__&bas=' + v('p_fis_tarihi_ilk_1') + '&bit=' + v('p_fis_tarihi_son_1')
                         + '&h1=' + v('hesap_ilk') + '&h2=' + v('hesap_son'), '_blank');
   setTimeout(() => { try { w.close(); } catch (e) {} }, 500);
 }
</script></body></html>"""
MUAVIN_NOKTA_SAYFASI = """<!doctype html><html><head><meta charset="utf-8"><title>Muavin Defter (Nokta Vuruşlu)</title>
""" + ORTAK_STIL + """</head><body>
<div class="yeni-rapor-paremetreleri"><table class="form_table">
<tr><th>Başlangıç Fiş Tarihi</th><td><input type="text" id="p_fis_tarihi_ilk_1"></td><th>Bitiş Fiş Tarihi</th><td><input type="text" id="p_fis_tarihi_son_1"></td></tr>
<tr><th>Rapor Türü</th><td colspan="3"><select id="p_printer_type_0"><option>IBM Tabanlı Yazıcı</option><option>EPSON Tabanlı Yazıcı</option></select></td></tr>
</table></div><div><button type="button" class="green bold">Rapor</button></div></body></html>"""
MUAVIN_HESAP_SATIRI = ('<tr><th>Başlangıç Hesap Kodu</th><td><input type="text" id="hesap_ilk"></td>'
                       '<th>Bitiş Hesap Kodu</th><td><input type="text" id="hesap_son"></td></tr>')
MUAVIN_ADLARI = {"191": "İNDİRİLECEK KDV", "391": "HESAPLANAN KDV", "320": "SATICILAR", "120": "ALICILAR", "770": "GENEL YÖNETİM GİDERLERİ", "600": "YURTİÇİ SATIŞLAR"}


# --- Luca > Isletme Defteri > Raporlar > Genel Raporlar > Isletme Defteri Dokumu (ekran goruntusundeki form: Tarih Ilk/Son, Rapor Turu) ---
# ISLETME_VERI[firma] = {"gider": [(kayit no, evrak no, tarih, aciklama, kdv, toplam)], "gelir": [...]}
ISLETME_VERI = {}
ISLETME_AYAR = {"istekler": []}
ISLETME_SAYFASI = """<!doctype html><html><head><meta charset="utf-8"><title>İşletme Defteri Dökümü</title>
""" + ORTAK_STIL + """</head><body>
<div class="yeni-rapor-paremetreleri"><table class="form_table">
<tr><th>Tarih İlk</th><td><input type="text" id="tarih_ilk"></td><th>Tarih Son</th><td><input type="text" id="tarih_son"></td></tr>
<tr><th>Kağıt/Printer</th><td colspan="3"><select id="kagit"><option>A4</option></select></td></tr>
<tr><th>Rapor Türü</th><td colspan="3"><select id="report_type"><option value="PDF">PDF</option><option value="LIST">Excel (xlsx)</option></select></td></tr>
</table></div>
<div><button type="button" class="green bold" onclick="gonder()">Rapor</button></div>
<script>
 function gonder() {
   const v = id => encodeURIComponent(document.getElementById(id).value);
   if (document.getElementById('report_type').value !== 'LIST') return;
   const w = window.open('/isletme.xlsx?firma=__FIRMA__&bas=' + v('tarih_ilk') + '&bit=' + v('tarih_son'), '_blank');
   setTimeout(() => { try { w.close(); } catch (e) {} }, 500);
 }
</script></body></html>"""


def isletme_xlsx(firma):
    """Gercek dokumun yapisi: B 'Kayit No', C 'Evrak No', F 'Tarih', G 'Aciklama'; tutar basliklari bir ust satirda."""
    import io
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "isletme_defteri"
    ws.append([None, "İŞLETME HESABI DEFTERİ"])
    ws.append([])
    ws.append([None, "İşyerinin Unvanı", None, ":", firma])
    ws.append([])
    veri = ISLETME_VERI.get(firma, {})
    for bolum, baslik, kalem, kdv_adi in (("gider", "GİDERLER", "Alınan Emtia", "İndirilecek K.D.V."),
                                          ("gelir", "GELİRLER", "Satılan Emtia", "Hesaplanan K.D.V.")):
        ws.append([None, baslik])
        ws.append([])
        ws.append([None, None, None, None, None, None, None, bolum.capitalize(), kalem, kdv_adi, None, "Toplam"])
        ws.append([None, "Kayıt No", "Evrak No", None, None, "Tarih", "Açıklama"])
        for kayit, evrak, tarih, aciklama, kdv, toplam in veri.get(bolum, []):
            ws.append([None, kayit, evrak, None, None, tarih, aciklama, 0.0, toplam - kdv, kdv, None, toplam])
        ws.append([None, "Toplam :"])
        ws.append([])
    cikti = io.BytesIO()
    wb.save(cikti)
    return cikti.getvalue()


def muavin_xlsx(firma, bas, bit, h1, h2):
    """Gercek dokumun yapisi: 'HESAP ADI | TL' bolum satiri, TARIH/TIP/FIS NO/ACIKLAMA/BORC/ALACAK/BAKIYE/B/A basligi,
    datetime tarihler, 'Nakli Yekun Haric' / 'Genel Toplam' satirlari. Hesap araligi bos ise TUM hesaplar gelir."""
    import io
    from datetime import datetime
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "-"
    ws.append(["MUAVİN DEFTER"])
    ws.append([firma])
    ws.append(["Dönem :", "01/01/2026-31/12/2026"])
    ws.append(["Tarih Aralığı :", f"{bas}-{bit}"])
    hesaplar = sorted(h for (f, h) in MUAVIN_VERI if f == firma and (not h1 or h >= h1) and (not h2 or h <= h2))
    for h in hesaplar:
        ws.append([f"{h} {MUAVIN_ADLARI.get(h[:3], 'HESAP')}", None, None, None, "TL"])
        ws.append(["TARİH", "TİP", "FİŞ NO", "AÇIKLAMA", "BORÇ", "ALACAK", "BAKİYE", "B/A"])
        for tarih, fis, aciklama, borc, alacak in MUAVIN_VERI[(firma, h)]:
            ws.append([datetime.strptime(tarih, "%d/%m/%Y"), "Mahsup", fis, aciklama, borc, alacak, 0.0, 0.0])
        ws.append(["Nakli Yekün Hariç :", None, None, None, 0.0, 0.0, 0.0, 0.0])
        ws.append(["Genel Toplam :", None, None, None, 0.0, 0.0, 0.0, 0.0])
        ws.append([])
    cikti = io.BytesIO()
    wb.save(cikti)
    return cikti.getvalue()


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
DB_AYAR = {"secim_calismaz": False, "cari_yok": False, "tarih_bozuk": False, "filtre_yok": False, "jqx": False, "sabit_hatasi": False, "satir_hatasi": False, "gonderim_hatasi": False, "api_bos": False, "yavas": 0.0}
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
        if not DB_AYAR["filtre_yok"] and not (gun(bas) <= gun(k[1]) <= gun(bit)):
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
<div id="cariPen" class="luca-open-window gizli"><b>SORGULAMA UYARI</b><p>Sadece seçili kayıtlar sorgulanacaktır.<br>
 Eksik bilgili kayıtları seçmek için <a href="#" id="buraya">buraya</a> tıklayınız.<br><br>Devam etmek istiyor musunuz?</p>
 <button id="cTamam">Tamam</button> <button id="cKapat">Kapat</button></div>
<div id="cariSonuc" class="gizli"><b>CARİ BİLGİ SORGULAMA</b><br><textarea id="cariSonucYazi" readonly style="width:340px;height:90px"></textarea><br><button id="csTamam">Tamam</button></div>
<div id="kayPen" class="luca-open-window gizli"><b>BİLGİ</b><p>Kayıt işlemi tamamlandı.</p><button id="kTamam">Tamam</button></div>
<div id="uyari" class="luca-open-window gizli"><b>SORGULAMA UYARI</b><p>Sadece seçili kayıtlar üzerinde işlem yapılacaktır.
 Gönderilmemiş kayıtları seçmek için <a href="#" id="gburaya">buraya</a> tıklayınız.<br><br>Devam etmek istiyor musunuz?</p>
 <button id="uTamam">Tamam</button> <button id="uKapat">Kapat</button></div>
<div id="giris" class="luca-open-window gizli"><b>Defter Beyan Sistemi - Giriş Bilgileri</b>
 <p>Giriş Yöntem: <select><option>API Key/Secret</option></select><br>
 API Key: <input type="text" id="apiKey" value="__KEY__"><br>API Secret: <input type="text" id="apiSecret" value="__SECRET__"></p>
 <button id="gTamam">Tamam</button> <button id="gKapat">Kapat</button></div>
<div id="ent" class="gizli"><b>DEFTER BEYAN ENTEGRASYON</b>
 <textarea id="entYazi" readonly style="border:1px solid #000;height:120px;width:340px"></textarea>
 <button id="eTamam">Tamam</button></div>
<script>
 const g = id => document.getElementById(id);
 g('durumGos').onclick = () => g('durumListe').classList.toggle('gizli');
 document.querySelectorAll('#durumListe .d').forEach(d => d.onclick = () => { g('durum').value = d.textContent;
   g('durumYazi').textContent = d.textContent; g('durumListe').classList.add('gizli'); });
 let tur = 'gelir', kayitlar = [];
 const SECIMYOK = __SECIMYOK__, JQX = __JQX__, CARIYOK = __CARIYOK__, TARIHBOZUK = __TARIHBOZUK__;
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
     selectallrows: () => { if (SECIMYOK) return; secilen = new Set(kayitlar.map((_, i) => i)); jqxCiz(); },
     getselectedrowindexes: () => [...secilen],
   };
   const iki = n => String(n).padStart(2, '0');
   window.jQuery = el => ({jqxGrid: (m, ...a) => yontem[m](...a),
     jqxDateTimeInput: (m, d) => { const k = el.querySelector('input');   // bilesen API'si: yazi degil tarih nesnesi alir
       if (m === 'setDate') k.value = iki(d.getDate()) + '/' + iki(d.getMonth() + 1) + '/' + d.getFullYear(); return k.value; },
     jqxDropDownList: (m, i) => { const sec = g('durum');
       if (m === 'getItems') return [...sec.options].map((o, j) => ({label: o.text, value: o.text, index: j}));
       if (m === 'selectIndex') { g('durumYazi').textContent = sec.options[i].text; return; }   // gizli select ESITLENMEZ (gercek gibi olabilir)
       if (m === 'getSelectedItem') { const t = g('durumYazi').textContent; return {label: t, value: t}; } }});
   window.jQuery.fn = {jqxGrid: true, jqxDateTimeInput: true, jqxDropDownList: true};
   // gercek Luca formu: .section.db_gelir > jqxDateTimeInput (div[name] > input[type=textarea]) + jqxDropDownList (gizli select + combobox)
   const bolum = document.createElement('div'); bolum.className = 'section db_gelir'; bolum.id = 'bolum';
   g('form').before(bolum); bolum.appendChild(g('form'));
   for (const [id, ad] of [['b1', 'bas_tarih'], ['b2', 'bit_tarih']]) { const w = document.createElement('div');
     w.className = 'jqx-datetimeinput'; w.setAttribute('name', ad); const el = g(id); el.replaceWith(w); w.appendChild(el); el.setAttribute('type', 'textarea'); }
   g('durum').setAttribute('name', 'durum'); g('durumGos').setAttribute('role', 'combobox'); g('durumGos').id = 'durum_gelir';
   document.body.insertAdjacentHTML('afterbegin', '<div class="section db_gider" style="display:none"><div class="jqx-datetimeinput" name="bas_tarih"><input type="textarea" value="01/01/2000"></div>' +
     '<div class="jqx-datetimeinput" name="bit_tarih"><input type="textarea" value="01/01/2000"></div><select name="durum"></select><div role="combobox" id="durum_gider"></div><button class="listele">Listele</button></div>');
   g('jqxHepsi').onclick = () => yontem.selectallrows();
 }
 function jqxCiz() {   // yalniz ilk 5 satir DOM'da (sanal kaydirma)
   g('jgGovde').innerHTML = kayitlar.slice(0, 5).map((k, i) => '<div role="row"><div role="gridcell">' +
     (secilen.has(i) ? '&#9745;' : '&#9744;') + '</div>' + KOLONLAR.slice(1).map(c =>
     '<div role="gridcell">' + hucre(i, c[1]) + '</div>').join('') + '</div>').join(''); }
 function sekme(t) { tur = t; g('baslik').textContent = (t == 'gelir' ? 'Gelir' : 'Gider') + ' Listesi';
   g('form').classList.remove('gizli'); g('liste').classList.add('gizli'); g('arac').classList.add('gizli'); }
 g('gelir').onclick = () => sekme('gelir'); g('gider').onclick = () => sekme('gider');
 document.addEventListener('click', e => { if (e.target.id === 'gider' || e.target.id === 'gelir') { const b = document.getElementById('bolum'); if (b) b.className = 'section db_' + e.target.id; } });
 g('listele').onclick = async () => {
   const q = 'tur=' + tur + '&bas=' + encodeURIComponent(g('b1').value) + '&bit=' + encodeURIComponent(g('b2').value)
     + '&durum=' + encodeURIComponent(g('durum').value);
   kayitlar = await (await fetch('/Luca/defter_beyan_gelir_gider_listesi.jq?' + q)).json();
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
 g('cari').onclick = () => { g('islemMenu').classList.add('gizli');
   setTimeout(() => g('cariPen').classList.remove('gizli'), 300); };
 g('buraya').onclick = e => { e.preventDefault();   // eksik bilgili kayitlari (ilk kayit) secer; pencere acik kalir
   if (CARIYOK) return; if (JQX) { secilen = new Set([0]); jqxCiz(); }
   else { const k = g('grid').querySelector('tbody input'); if (k) k.checked = true; } };
 g('cKapat').onclick = () => g('cariPen').classList.add('gizli');
 g('cTamam').onclick = () => { g('cariPen').classList.add('gizli'); olay('cari');
   const n = JQX ? secilen.size : g('grid').querySelectorAll('tbody input:checked').length;
   g('cariSonucYazi').value = n ? '27163387984 sorgulandı.\\n' : '';
   setTimeout(() => g('cariSonuc').classList.remove('gizli'), 400);
   setTimeout(() => g('cariSonucYazi').value += n ? n + ' adet cari sorgulandı.\\n' : 'Sorgulanacak kayıt bulunamadı.\\n', 1500); };
 g('csTamam').onclick = () => g('cariSonuc').classList.add('gizli');
 for (const id of ['b1', 'b2']) g(id).addEventListener('change', () => {   // maskeli tarih bileseni taklidi
   if (!TARIHBOZUK) return; const v = g(id).value;
   if (v.includes('/')) g(id).value = '01/01/2002';
   else if (/^\\d{8}$/.test(v)) g(id).value = v.slice(0, 2) + '/' + v.slice(2, 4) + '/' + v.slice(4); });
 g('kaydet').onclick = () => { olay('kaydet');   // gercek Luca gibi: kayit sonrasi liste yenilenir, secim kalkar
   if (JQX) { secilen = new Set(); jqxCiz(); } else { g('grid').querySelectorAll('tbody input').forEach(k => k.checked = false); g('hepsi').checked = false; }
   setTimeout(() => g('kayPen').classList.remove('gizli'), 300); };
 g('kTamam').onclick = () => g('kayPen').classList.add('gizli');
 g('arama').onclick = () => { g('form').classList.remove('gizli'); g('liste').classList.add('gizli'); };
 g('islemler').onclick = () => g('islemMenu').classList.toggle('gizli');
 g('gonder').onclick = () => { g('islemMenu').classList.add('gizli'); setTimeout(() => g('uyari').classList.remove('gizli'), 200); };
 g('gburaya').onclick = e => { e.preventDefault(); olay('gburaya');   // Luca'nin kendi secimi: tum gonderilmemisler
   if (JQX) { secilen = new Set(kayitlar.map((_, i) => i)); jqxCiz(); }
   else g('grid').querySelectorAll('tbody input').forEach(k => k.checked = true); };
 g('uKapat').onclick = () => g('uyari').classList.add('gizli');
 g('uTamam').onclick = () => { g('uyari').classList.add('gizli'); setTimeout(() => g('giris').classList.remove('gizli'), 250); };
 g('gKapat').onclick = () => g('giris').classList.add('gizli');
 g('gTamam').onclick = async () => {
   olay('gonder');
   g('giris').classList.add('gizli'); g('entYazi').value = ''; g('ent').classList.remove('gizli');
   const sec = JQX ? [...secilen].sort((a, b) => a - b).map(i => kayitlar[i][0]) :
     [...g('grid').querySelectorAll('tbody tr')].filter(r => r.querySelector('input').checked).map(r => r.children[3].textContent);
   const yaz = s => g('entYazi').value += s + '\\n';
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


# --- Luca > Muhasebe > Fis Islemleri > Duzenleme > Toplu Belge Turu ve Odeme Yontemi Duzenleme (e-Defter on kontrolu) ---
# EDEFTER_VERI[(firma, hata kodu)] = [fis]; fis = {"fis_no", "degismeyen", "tarih", "satirlar": [(hesap kodu, hesap adi, borc, alacak,
# aciklama, evrak no, evrak tarihi, bt, odeme)]}. Form ve liste gercek ekran goruntulerindeki gibi ayri pencerelerde acilir.
EDEFTER_VERI = {}
EDEFTER_AYAR = {"form_yenile": False, "edefter_kutu": "isaretli", "sayfa_boyu": 2, "kayit_yok": "bos_liste", "ayni_pencere": False, "belge_bos_varsayilan": False,
                "istekler": [], "kaydet": 0}
EDEFTER_HATALAR = [("20041", "... nolu fiş içinde ... belge türünün tanımı yok.( Hata Kodu: 20041)"),
                   ("20042", "... nolu fiş(ler) içinde ilgili belge tür kodlu satırda evrak no ve tarihi girilmelidir.( Hata Kodu: 20042)"),
                   ("20044", "... nolu fiş(ler)de birden fazla belge mevcut.(Hata Kodu: 20044)"),
                   ("20045", "... nolu fiş(ler)de birden fazla belge tür mevcut.(Hata Kodu: 20045)"),
                   ("20046", "... nolu fiş(ler)de 100 den fazla fatura mevcut.(Hata Kodu: 20046)"),
                   ("20047", "... nolu fiş(ler)de birden fazla ödeme yöntemi mevcut.(Hata Kodu: 20047)"),
                   ("20048", "... nolu fiş(ler)de belge türü fatura olan birden fazla belge mevcut.(Hata Kodu: 20048)")]
EDEFTER_KUTULARI = {   # e-Defter onay kutusunun gorunumu: varsayilan isaretli / isaretsiz / etiketle ayni hucrede (label icinde, isaretsiz)
    "isaretli": '<tr><th>E-Defter kapsamında uyumsuz olan fişleri getir</th><td><input type="checkbox" id="c_edefter" checked></td></tr>',
    "isaretsiz": '<tr><th>E-Defter kapsamında uyumsuz olan fişleri getir</th><td><input type="checkbox" id="c_edefter"></td></tr>',
    "ayni_hucre": '<tr><td colspan="2"><label><input type="checkbox" id="c_edefter"> E-Defter kapsamında uyumsuz olan fişleri getir</label></td></tr>',
    # gercek Luca: kutu isaretsizken "E-Defter hata" satiri gizli, isaretlenince (hemen / gecikmeyle) gorunur
    "gizli": '<tr><th>E-Defter kapsamında uyumsuz olan fişleri getir</th><td><input type="checkbox" id="c_edefter" onclick="hataGoster(this.checked, 0)"></td></tr>',
    "gizli_gecikmeli": '<tr><th>E-Defter kapsamında uyumsuz olan fişleri getir</th><td><input type="checkbox" id="c_edefter" onclick="hataGoster(this.checked, 900)"></td></tr>',
    "yok": ''}
EDEFTER_FORM_SAYFASI = """<!doctype html><html><head><meta charset="utf-8"><title>BELGE TÜRÜ DÜZENLEME - Google Chrome</title>
""" + ORTAK_STIL + """</head><body>
<h3>BELGE TÜRÜ DÜZENLEME</h3>
<table class="form_table">
<tr><th>Fiş Tarihi *</th><td><input type="text" id="tarih_ilk"></td><td><img alt="takvim"></td><td></td>
    <td><input type="text" id="tarih_son"></td><td><img alt="takvim"></td></tr>
<tr><th>Evrak No Dolu</th><td><input type="checkbox" id="c_evrak_no_dolu"></td></tr>
<tr><th>Evrak Tarihi Dolu</th><td><input type="checkbox" id="c_evrak_tarihi_dolu"></td></tr>
<tr><th>Evrak Tarihi Boş Olan</th><td><input type="checkbox" id="c_evrak_tarihi_bos"></td></tr>
<tr><th>Belge Türü Boş Olan</th><td><input type="checkbox" id="c_belge_turu_bos" __BELGE_BOS__></td></tr>
<tr><th>Ödeme Türü Boş Olan</th><td><input type="checkbox" id="c_odeme_turu_bos"></td></tr>
<tr><th>Entegrasyon Fişlerini de (LucaNET ve KOZA) getir</th><td><input type="checkbox" checked disabled></td></tr>
<tr><th>Hesap Kodu</th><td><input type="text" id="hesap_kodu"></td></tr>
__EDEFTER_KUTU__
<tr id="hata_satiri" style="__HATA_STIL__"><th>E-Defter hata:</th><td><select id="edefter_hata">__SECENEKLER__</select></td></tr>
<tr><th>Sayfa No/Kayıt Sayısı</th><td><select id="sayfa_no"><option>1</option></select> / <select id="kayit_sayisi"><option>50</option><option selected>100</option><option>500</option><option>1000</option></select></td></tr>
</table>
<div><button type="button" id="listele" onclick="listele()"><i></i> Listele</button></div>
<script>
 function hataGoster(acik, gecikme) { setTimeout(() => { document.getElementById('hata_satiri').style.display = acik ? '' : 'none'; }, gecikme); }
 function listele() {
   const v = id => encodeURIComponent(document.getElementById(id).value);
   const c = id => document.getElementById(id).checked ? '1' : '0';
   const kod = (/Hata\\s*Kodu:\\s*(\\d+)/.exec(document.getElementById('edefter_hata').selectedOptions[0].text) || [])[1] || '';
   const q = '?firma=__FIRMA__&kod=' + kod + '&bas=' + v('tarih_ilk') + '&bit=' + v('tarih_son') + '&edefter=' + c('c_edefter')
           + '&belge_bos=' + c('c_belge_turu_bos') + '&evrak_dolu=' + c('c_evrak_no_dolu') + '&kayit=' + v('kayit_sayisi');
   const ac = () => { if (__AYNI__) location.href = '/edefter-liste' + q + '&sayfa=1';
                      else window.open('/edefter-liste' + q + '&sayfa=1', '_blank', 'popup,width=1200,height=800'); };
   if (__UYARI__) fetch('/api/edefter-say' + q).then(r => r.json()).then(n => { if (!n) alert('Kayıt bulunamadı.'); else ac(); });
   else ac();
 }
</script></body></html>"""
EDEFTER_LISTE_SAYFASI = """<!doctype html><html><head><meta charset="utf-8"><title>E-DEFTER UYUMSUZ FİŞLERİ DÜZENLEME - Google Chrome</title>
""" + ORTAK_STIL + """</head><body>
<h4>E-DEFTER UYUMSUZ FİŞLERİ DÜZENLEME</h4>
<table id="liste" border="1"><thead><tr><th><input type="checkbox"></th><th>Sıra</th><th>Fiş No</th><th>Değişmeyen Fiş No</th><th>Fiş Tarihi</th>
<th>Hesap Kodu</th><th>Borç</th><th>Alacak</th><th>Açıklama</th><th>Evrak No</th><th>Evrak Tarihi</th><th>BT</th><th>Ödeme Türü</th><th>Durum</th></tr></thead>
<tbody>__SATIRLAR__</tbody></table>
<div id="alt"><button type="button" onclick="git(-1)"><i></i></button><button type="button" onclick="git(1)"><i></i></button>
<b>Sayfa No: __SAYFA__</b>
<button type="button">Toplu Değer Ata</button><button type="button">Toplu Değer Seç</button><button type="button">Filtre</button>
<button type="button" onclick="fetch('/api/edefter-kaydet')"><img alt="kaydet"> Kaydet</button></div>
<script>function git(d) { const u = new URL(location.href); u.searchParams.set('sayfa', Math.max(1, __SAYFA__ + d)); location.href = u.toString(); }</script>
</body></html>"""


def edefter_fisleri(firma, kod, edefter="1"):
    """E-Defter kutusu isaretli degilse Luca uyumsuz fisleri getirmez (liste bos)."""
    return EDEFTER_VERI.get((firma, kod), []) if edefter == "1" else []


def edefter_liste_html(q):
    fisler = edefter_fisleri(q.get("firma", ""), q.get("kod", ""), q.get("edefter", "1"))
    boyut = EDEFTER_AYAR["sayfa_boyu"]
    sayfa = max(1, int(q.get("sayfa") or 1))
    parca = fisler[(sayfa - 1) * boyut: sayfa * boyut]
    satirlar = []
    sira = (sayfa - 1) * boyut
    for f in parca:
        sira += 1
        for i, (hk, ha, borc, alacak, aciklama, evrak, evrak_t, bt, odeme) in enumerate(f["satirlar"]):
            ilk = i == 0
            satirlar.append(
                "<tr><td><input type='checkbox'></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s<br>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                "<td><input type='text' value='%s'></td><td><input type='text' value='%s'></td><td>%s</td><td><input type='text' value='%s'></td><td>%s</td></tr>"
                % (sira if ilk else "", ("<a href='#'>%s</a>" % f["fis_no"]) if ilk else "", f["degismeyen"] if ilk else "",
                   f["tarih"] if ilk else "", hk, ha, tr_sayi(borc), tr_sayi(alacak), aciklama, evrak, evrak_t, bt, odeme,
                   f.get("durum", "") if ilk else ""))
    return EDEFTER_LISTE_SAYFASI.replace("__SATIRLAR__", "".join(satirlar)).replace("__SAYFA__", str(sayfa))



# --- Luca > Muhasebe > Fis Islemleri > Fis Listesi (e-Defter hata kodlari 20021/20025/20026; ekran goruntusundeki form) ---
# FIS_VERI[(firma, kod, ay adi)] = [{"fis_no", "tarih", "aciklama"}]; FIS_AYAR["modlar"][kod] = "grid" (tablo) ya da "mesaj" (uyari kutusu)
FIS_VERI = {}
FIS_KUTULARI = {   # onay kutularinin yapisi: ayri hucre / ucu tek hucrede alt alta (gercek Luca) ; hepsi isaretsiz baslar
    "tek": '<tr><td colspan="4"><input type="checkbox" id="c_edefter" onclick="fisGoster(this.checked)"> E-Defter kapsamında uyumsuz olan fişleri getir</td></tr>'
           '<tr><td colspan="4"><input type="checkbox" id="c_detayli"> Detaylı Arama</td></tr>',
    "tek_hucre": '<tr><td colspan="4"><input type="checkbox" id="c_yevmiye" disabled> Yevmiye numarası ve fiş numarası uyumsuzları listele<br>'
                 '<input type="checkbox" id="c_edefter" onclick="fisGoster(this.checked)"> E-Defter kapsamında uyumsuz olan fişleri getir<br>'
                 '<input type="checkbox" id="c_detayli"> Detaylı Arama</td></tr>'}
FIS_DUGMELERI = {"liste": '<div class="alt"><button type="button" id="mukerrer">Mükerrer Kayıt Denetimi</button> <button type="button" id="listele" onclick="listele()"><i></i> Liste</button></div>',
                 "button": '<div><button type="button" id="listele" onclick="listele()"><i></i> Listele</button></div>',
                 # gercek Luca: yazisiz resimli kutu, adi yalniz title'da
                 "kutu_title": '<div class="alt_cubuk"><div onclick="listele()" title="Listele" style="cursor:pointer;width:40px;height:20px;border:1px solid"><img alt=""></div></div>'}
FIS_AYAR = {"gizli": False, "dugme": "button", "kutu": "tek", "modlar": {"20021": "grid", "20025": "mesaj", "20026": "mesaj"}, "istekler": []}
FIS_HATALARI = ["... nolu fiş(ler)de birden fazla belge mevcut.(Hata Kodu: 20044)",
                "e-Defter başlangıç tarihinden önce numaralandırılmamış fişler mevcut.( Hata Kodu: 20021)",
                "... adet dengesiz veya pasif fişiniz var.( Hata Kodu: 20025)", "... adet detaysız fişiniz var.( Hata Kodu: 20026)",
                "... nolu fiş içinde ... belge türünün tanımı yok.( Hata Kodu: 20041)",
                "... nolu fiş(ler) içinde belge tür, evrak no ve tarih uyumsuzluğu.(Hata Kodu: 20042)",
                "E-Defter XML içinde hataya neden olan karakter sahip fiş listesi"]
FIS_SAYFASI = """<!doctype html><html><head><meta charset="utf-8"><title>FİŞ LİSTESİ</title>
""" + ORTAK_STIL + """</head><body>
<h3>FİŞ LİSTESİ</h3>
<table class="form_table">
<tr><th>İlk Fiş Tarihi</th><td><input type="text" id="ilk_tarih" value="01/01/2026" readonly></td><th>Son Fiş Tarihi</th><td><input type="text" id="son_tarih" value="31/01/2026" readonly></td></tr>
<tr><th>Fiş Açıklama</th><td colspan="3"><input type="text" id="fis_aciklama"></td></tr>
__FIS_KUTU__
<tr id="fis_ay_satiri" style="__GIZLI__"><th>E-Defter Ay</th><td><select id="edefter_ay">__AYLAR__</select></td></tr>
<tr id="fis_hata_satiri" style="__GIZLI__"><th>E-Defter Hata:</th><td><select id="edefter_hata">__HATALAR__</select></td></tr>
<tr><td colspan="4"><input type="checkbox" id="c_mukerrer" style="display:none"></td></tr>
</table>
__FIS_DUGME__
<div id="sonuc"></div>
<script>
 function fisGoster(acik) { if (__GIZLI_AKTIF__) setTimeout(() => { for (const id of ['fis_ay_satiri', 'fis_hata_satiri']) document.getElementById(id).style.display = acik ? '' : 'none'; }, __GECIKME__); }
 function listele() {
   const kod = (/Hata\\s*Kodu:\\s*(\\d+)/.exec(document.getElementById('edefter_hata').selectedOptions[0].text) || [])[1] || '';
   const ay = document.getElementById('edefter_ay').value, ed = document.getElementById('c_edefter').checked ? '1' : '0';
   fetch('/api/fis-listesi?firma=__FIRMA__&kod=' + kod + '&ay=' + encodeURIComponent(ay) + '&edefter=' + ed).then(r => r.json()).then(r => {
     if (r.mod === 'mesaj') { alert(r.mesaj); return; }
     if (r.mod === 'hicbir') return;                // sonuc ekranina hicbir sey gelmez (okunamayan yanit)
     let h = '<table border="1" id="fislistesi"><thead><tr><th>Sıra</th><th>Fiş No</th><th>Fiş Tarihi</th><th>Açıklama</th></tr></thead><tbody>';
     r.satirlar.forEach((s, i) => { h += '<tr><td>' + (i + 1) + '</td><td>' + s.fis_no + '</td><td>' + s.tarih + '</td><td>' + s.aciklama + '</td></tr>'; });
     document.getElementById('sonuc').innerHTML = h + '</tbody></table>';
   });
 }
</script></body></html>"""
AYLAR_TR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


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
            return self._yanit(DB_SAYFASI.replace("__JQX__", "true" if DB_AYAR["jqx"] else "false")
                               .replace("__SECIMYOK__", "true" if DB_AYAR["secim_calismaz"] else "false")
                               .replace("__CARIYOK__", "true" if DB_AYAR["cari_yok"] else "false")
                               .replace("__TARIHBOZUK__", "true" if DB_AYAR["tarih_bozuk"] else "false").replace("__KEY__", "" if bos else "TESTKEY123")
                               .replace("__SECRET__", "" if bos else "TESTSECRET456"))
        if yol == "/api/db-olay":
            with KILIT:
                DB_OLAYLAR.append(parse_qs(urlparse(self.path).query).get("ad", [""])[0])
            return self._yanit("{}", "application/json")
        if yol == "/Luca/defter_beyan_gelir_gider_listesi.jq":
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            import time
            time.sleep(DB_AYAR["yavas"])
            return self._yanit(json.dumps(db_liste(DB_SEC["firma"], q["tur"], q["bas"], q["bit"], q["durum"]),
                                          ensure_ascii=False), "application/json")
        if yol == "/fis-listesi":
            return self._yanit(FIS_SAYFASI.replace("__FIS_KUTU__", FIS_KUTULARI[FIS_AYAR["kutu"]]).replace("__FIS_DUGME__", FIS_DUGMELERI[FIS_AYAR["dugme"]])
                               .replace("__GIZLI__", "display:none" if FIS_AYAR["gizli"] else "").replace("__GIZLI_AKTIF__", "true" if FIS_AYAR["gizli"] else "false")
                               .replace("__GECIKME__", "700" if FIS_AYAR["gizli"] == "gecikmeli" else "0").replace("__FIRMA__", firma)
                               .replace("__AYLAR__", "".join(f"<option>{a}</option>" for a in AYLAR_TR))
                               .replace("__HATALAR__", "".join(f"<option>{h}</option>" for h in FIS_HATALARI)))
        if yol == "/api/fis-listesi":
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query, keep_blank_values=True).items()}
            with KILIT:
                FIS_AYAR["istekler"].append(q)
            veri = FIS_VERI.get((q.get("firma", ""), q.get("kod", ""), q.get("ay", "")), []) if q.get("edefter") == "1" else []
            if FIS_AYAR["modlar"].get(q.get("kod")) == "hicbir":
                return self._yanit(json.dumps({"mod": "hicbir"}), "application/json")
            if FIS_AYAR["modlar"].get(q.get("kod")) == "mesaj":
                mesaj = f"{len(veri)} adet dengesiz veya pasif fişiniz var." if veri else "Kayıt bulunamadı."
                return self._yanit(json.dumps({"mod": "mesaj", "mesaj": mesaj}, ensure_ascii=False), "application/json")
            return self._yanit(json.dumps({"mod": "grid", "satirlar": veri}, ensure_ascii=False), "application/json")
        if yol == "/edefter-form":
            secenekler = "".join(f"<option>{m}</option>" for _, m in EDEFTER_HATALAR)
            return self._yanit(EDEFTER_FORM_SAYFASI.replace("__FIRMA__", firma).replace("__SECENEKLER__", secenekler)
                               .replace("__YENILE__", "true" if EDEFTER_AYAR["form_yenile"] else "false")
                               .replace("__HATA_STIL__", "display:none" if EDEFTER_AYAR["edefter_kutu"].startswith("gizli") else "")
                               .replace("__EDEFTER_KUTU__", EDEFTER_KUTULARI[EDEFTER_AYAR["edefter_kutu"]])
                               .replace("__BELGE_BOS__", "checked" if EDEFTER_AYAR["belge_bos_varsayilan"] else "")
                               .replace("__AYNI__", "true" if EDEFTER_AYAR["ayni_pencere"] else "false")
                               .replace("__UYARI__", "true" if EDEFTER_AYAR["kayit_yok"] == "uyari" else "false"))
        if yol == "/api/edefter-say":
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query, keep_blank_values=True).items()}
            return self._yanit(json.dumps(len(edefter_fisleri(q.get("firma", ""), q.get("kod", ""), q.get("edefter", "1")))), "application/json")
        if yol == "/api/edefter-kaydet":
            with KILIT:
                EDEFTER_AYAR["kaydet"] += 1
            return self._yanit("{}", "application/json")
        if yol == "/edefter-liste":
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query, keep_blank_values=True).items()}
            with KILIT:
                EDEFTER_AYAR["istekler"].append(q)
            return self._yanit(edefter_liste_html(q))
        if yol == "/muavin-nokta":
            with KILIT:
                MUAVIN_AYAR.setdefault("nokta_acildi", 0)
                MUAVIN_AYAR["nokta_acildi"] += 1
            return self._yanit(MUAVIN_NOKTA_SAYFASI)
        if yol == "/muavin":
            sayfa = (MUAVIN_SAYFASI.replace("__FIRMA__", firma).replace("__EXCEL__", MUAVIN_AYAR["excel_adi"])
                     .replace("__HESAP__", MUAVIN_HESAP_SATIRI if MUAVIN_AYAR["hesap_alani"] else ""))
            return self._yanit(sayfa)
        if yol == "/muavin.xlsx":
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query, keep_blank_values=True).items()}
            with KILIT:
                MUAVIN_AYAR["istekler"].append(q)
            return self._yanit(muavin_xlsx(q.get("firma", ""), q.get("bas", ""), q.get("bit", ""), q.get("h1", ""), q.get("h2", "")),
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               {"Content-Disposition": 'attachment; filename="muavin.xlsx"'})
        if yol == "/isletme":
            return self._yanit(ISLETME_SAYFASI.replace("__FIRMA__", firma))
        if yol == "/isletme.xlsx":
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query, keep_blank_values=True).items()}
            with KILIT:
                ISLETME_AYAR["istekler"].append(q)
            return self._yanit(isletme_xlsx(q.get("firma", "")),
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               {"Content-Disposition": 'attachment; filename="isletme_defteri.xlsx"'})
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
    DB_AYAR.update(gonderim_hatasi=False, api_bos=False, satir_hatasi=False, sabit_hatasi=False, jqx=False, cari_yok=False, secim_calismaz=False, tarih_bozuk=False, filtre_yok=False, yavas=0.0)
    DB_OLAYLAR.clear()
    MUAVIN_VERI.clear()
    EDEFTER_VERI.clear()
    FIS_VERI.clear()
    FIS_AYAR.update(gizli=False, dugme="button", kutu="tek", modlar={"20021": "grid", "20025": "mesaj", "20026": "mesaj"}, istekler=[])
    EDEFTER_AYAR.update(form_yenile=False, edefter_kutu="isaretli", sayfa_boyu=2, kayit_yok="bos_liste", ayni_pencere=False, belge_bos_varsayilan=False, istekler=[], kaydet=0)
    ISLETME_VERI.clear()
    ISLETME_AYAR["istekler"] = []
    MUAVIN_AYAR.update(hesap_alani=True, excel_adi="Excel (xlsx)", istekler=[], nokta_acildi=0)
