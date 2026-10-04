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
    "1111111111": ("AKIN ÇOBAN", "İŞLETME", 500000, 100000, 300000),
    "2222222222": ("DENTAL SAĞLIK HİZMETLERİ", "BİLANÇO", 0, 0, 0),
    "4444444444": ("FATURASIZ ANONİM ŞİRKETİ", "İŞLETME", 100000, 20000, 30000),
    "5555555555": ("KEREM TİCARET", "İŞLETME", 200000, 0, 250000),
    "7777777777": ("YENİ FİRMA LİMİTED", "İŞLETME", 100000, 20000, 30000),
}
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


HESAP_PLANI_SAYFASI = """<!doctype html><html><head><meta charset="utf-8"><title>Hesap Planı Listesi</title>
""" + ORTAK_STIL + """</head><body>
<h3>HESAP PLANI LİSTESİ</h3>
<table id="liste"><thead><tr><th>Hesap Kodu</th><th>Hesap Adı</th><th>Tipi</th><th>Borç</th><th>Alacak</th>
<th>Borç Bakiyesi</th><th>Alacak Bakiyesi</th><th>B/A</th><th>Birim</th></tr></thead><tbody></tbody></table>
<div><button>Yenile</button> <button>Yeni Hesap</button> <button>Hesap Düzenle</button> <button id="filtre">Filtre</button>
<button>Cari Hesap Tanımları</button> <button>Kullanım</button> <button>Rapor</button></div>
<div id="pencere" class="luca-open-window gizli"><b>Hesap Arama</b>
 <table>
  <tr><td>Hesap Sınıfı</td><td><select><option>Tümü</option></select></td></tr>
  <tr><td>Hesap Kodu</td><td><input type="text"></td></tr>
  <tr><td>Yıl/Ay</td><td><select><option>2026</option></select><select><option></option></select></td></tr>
  <tr><td>Başlangıç Tarih</td><td><input type="text" id="bas" value="01/01/2026"></td></tr>
  <tr><td>Bitiş Tarih</td><td><input type="text" id="bit" value="31/08/2026"></td></tr>
  <tr><td>Çalışmayan Hesaplar</td><td><select><option>Çalışmayan Hesapları Gösterme</option></select></td></tr>
 </table>
 <button>Temizle</button> <button id="ara">Ara</button></div>
<script>
 const FIRMA = '__FIRMA__';
 document.getElementById('filtre').onclick = () =>
   setTimeout(() => document.getElementById('pencere').classList.remove('gizli'), 300);
 document.getElementById('ara').onclick = async () => {
   const q = 'firma=' + encodeURIComponent(FIRMA) + '&bas=' + encodeURIComponent(document.getElementById('bas').value)
     + '&bit=' + encodeURIComponent(document.getElementById('bit').value);
   document.getElementById('pencere').classList.add('gizli');
   const liste = await (await fetch('/api/hesap-plani?' + q)).json();
   const tb = document.querySelector('#liste tbody'); tb.innerHTML = '';
   setTimeout(() => { for (const r of liste) tb.insertAdjacentHTML('beforeend',
     '<tr>' + r.map(x => '<td>' + x + '</td>').join('') + '</tr>'); }, 700);
 };
</script></body></html>"""

DB_BASLIK = """<div style="background:#146;color:#fff;padding:6px">ADEM YILMAZ adına işlem yapmaktasınız.
<span style="float:right;background:#a22;padding:2px 8px">__ROZET__</span></div>"""

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
<span class="select2-selection" role="combobox" id="kutu" style="display:inline-block;border:1px solid #888;padding:4px;min-width:200px">Vergi Kimlik Numarası</span>
<div id="acilir" style="display:none;border:1px solid #888;width:300px">
 <input class="select2-search__field" id="ara" type="search"><ul id="liste" style="list-style:none;padding:0"></ul></div>
<button id="gecis">Hızlı Geçiş Yap</button>
<script>
 const TUM = __MUKELLEFLER__; let secili = '';
 const ul = document.getElementById('liste'), ara = document.getElementById('ara');
 function ciz(f){ ul.innerHTML = ''; TUM.filter(x => x.includes(f)).forEach(x => {
   const li = document.createElement('li'); li.setAttribute('role', 'option'); li.className = 'select2-results__option';
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
    + '<tr><td>Kar</td><td>' + r.kar + '</td></tr><tr><td>Genel Toplam</td><td>' + r.toplam + '</td></tr></table>'
    + '<table border=1><tr><th>GELİRLER</th><th>TUTAR</th></tr>'
    + '<tr><td>Dönem Sonu Emtia Mevcudu</td><td></td></tr>'
    + '<tr><td>Dönem İçinde Elde Edilen Hasılat</td><td>' + r.hasilat + '</td></tr>'
    + '<tr><td>Gelir Diğer Gelirler</td><td>0,00</td></tr><tr><td>-</td><td></td></tr>'
    + '<tr><td>Zarar</td><td>' + r.zarar + '</td></tr><tr><td>Genel Toplam</td><td>' + r.toplam + '</td></tr></table>'; }, 700);
 };
</script></body></html>"""


# Luca ana sayfasindaki Muhasebe menusune Hesap Planı Listesi eklenir
sahte_luca.ANA_SAYFA = sahte_luca.ANA_SAYFA.replace(
    "      <a>Hesap Planı İşlemleri</a>\n", '      <a id="hesapIslemleri">Hesap Planı İşlemleri</a>\n      <div id="hesapMenu" class="gizli" style="margin-left:14px"><a id="hesapListesi">Hesap Planı Listesi</a></div>\n', 1).replace(
    " const by = document.getElementById('beyannameler');", " const hi = document.getElementById('hesapIslemleri');\n hi.onmouseenter = hi.onclick = () =>\n   sonra(150, () => document.getElementById('hesapMenu').classList.remove('gizli'));\n document.getElementById('hesapListesi').onclick = () => {\n   document.getElementById('muhasebeMenu').classList.add('gizli');\n   sonra(300, () => sekmeAc('/hesap-plani?firma=' + encodeURIComponent(seciliFirma) + '&t=' + Date.now()));\n };\n const by = document.getElementById('beyannameler');", 1)


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
        if yol == "/hesap-plani":
            return self._yanit(HESAP_PLANI_SAYFASI.replace("__FIRMA__", firma))
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
            rozet = f"{vkn} - {DB_MUKELLEFLER[vkn][1]}" if vkn else "9660268213 - SMK"
            baslik = DB_BASLIK.replace("__ROZET__", rozet)
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
                                           "toplam": tr_sayi(h)}), "application/json")

    def do_POST(self):
        self._yanit_verildi = False
        yol, firma, tip = self._parametre()
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
