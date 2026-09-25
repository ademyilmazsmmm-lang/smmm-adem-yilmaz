# -*- coding: utf-8 -*-
"""Luca'yi taklit eden kucuk yerel site (yalnizca gelistirme/test icin).

Gercek Luca'ya baglanmadan botun ekran akisini (firma secimi, donem, menu,
GIB'den Getir, Islem Takip, Belge Ara, Belge Sec, Secilenleri Indir, Excel,
Iptal/Itiraz, Interaktif V.D.) uctan uca calistirmak icin kullanilir.
Gercek Luca'nin davranislari (cerceve icinde ekran, .luca-open-window
pencereleri, arkayi kilitleyen perde, gecikmeli acilan diyaloglar, fatura
yoksa acilista cikan uyari) bilerek taklit edilir.

    python testler/sahte_luca.py          # http://127.0.0.1:8765 adresinde acar
"""

import io
import json
import sys
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

FIRMALAR = ["AKIN COBAN", "DENTAL SAGLIK", "ESKI DONEM LTD", "FATURASIZ AS",
            "KEREM TICARET", "MERT INSAAT"]
# Bu firma Luca'da en son 2025 doneminde birakilmis gibi acilir
ESKI_DONEMLI = "ESKI DONEM LTD"
# Bu firmada hic fatura yok
FATURASIZ = "FATURASIZ AS"

AEN_EKRANLARI = {
    "e-Arşiv Alış Faturaları": "e-arsiv-alis",
    "e-Arşiv Satış Faturaları": "e-arsiv-satis",
    "e-Fatura Alış Faturaları": "e-fatura-alis",
    "e-Fatura Satış Faturaları": "e-fatura-satis",
    "GİB 5000/30000": "gib-5000",
    "TÜRMOB Ent. Alış Faturaları": "turmob-alis",
    "TÜRMOB Ent. Satış Faturaları": "turmob-satis",
    "GİB e-SMM Alış": "esmm-alis",
    "GİB e-SMM Satış": "esmm-satis",
}

# sunucu tarafi durum: (firma, tip) -> {"sorgulandi": bool, "iptal": bool}
DURUM = {}
KILIT = threading.Lock()


def faturalar(firma, tip):
    """Her firma/ekran icin sabit fatura listesi."""
    if firma == FATURASIZ:
        return []
    on_ek = "".join(c for c in firma if c.isalpha())[:3].upper()
    liste = [
        {"no": f"{on_ek}2026000000001", "unvan": "TURKCELL ILETISIM", "tarih": "05/08/2026",
         "tip": "SATIS", "matrah": 1000.0, "kdv": 200.0},
        {"no": f"{on_ek}2026000000002", "unvan": "VODAFONE TELEKOM", "tarih": "12/08/2026",
         "tip": "SATIS", "matrah": 500.0, "kdv": 100.0},
        {"no": f"{on_ek}2026000000003", "unvan": "TRUGO SARJ", "tarih": "20/08/2026",
         "tip": "TEVKIFAT", "matrah": 2000.0, "kdv": 400.0},
    ]
    if tip == "e-arsiv-interaktif":  # GIB tarafinda Luca'ya inmemis bir fatura daha var
        liste.append({"no": f"{on_ek}2026000000004", "unvan": "SHELL PETROL", "tarih": "28/08/2026",
                      "tip": "SATIS", "matrah": 300.0, "kdv": 60.0})
    durum = DURUM.get((firma, tip), {})
    for i, f in enumerate(liste):
        f["durum"] = "İPTAL" if (durum.get("iptal") and i == 1) else "ONAYLANDI"
    return liste


def gorunen_faturalar(firma, tip):
    return faturalar(firma, tip) if DURUM.get((firma, tip), {}).get("sorgulandi") else []


def excel_bayt(firma, tip):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["Fatura No", "Gönderici Unvan", "Fatura Tarihi", "Fatura Tipi",
               "Mal Hizmet Toplam Tutarı", "Hesaplanan KDV", "Ödenecek Tutar", "Durum"])
    for f in gorunen_faturalar(firma, tip):
        ws.append([f["no"], f["unvan"], f["tarih"], f["tip"], f["matrah"], f["kdv"],
                   f["matrah"] + f["kdv"], f["durum"]])
    tampon = io.BytesIO()
    wb.save(tampon)
    return tampon.getvalue()


def zip_bayt(firma, tip):
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as z:
        for f in gorunen_faturalar(firma, tip):
            ek = "<cac:WithholdingTaxTotal>9015</cac:WithholdingTaxTotal>" if f["tip"] == "TEVKIFAT" else ""
            z.writestr(f"{f['no']}.xml", f"<Invoice><cbc:ID>{f['no']}</cbc:ID>{ek}</Invoice>")
    return tampon.getvalue()


ORTAK_STIL = """
<style>
 body{font-family:Arial,sans-serif;font-size:13px;margin:0}
 .perde{position:fixed;inset:0;background:rgba(0,0,0,.25);z-index:50}
 .luca-open-window{position:fixed;top:80px;left:120px;min-width:380px;background:#fff;
   border:2px solid #1f4e78;padding:12px;z-index:60}
 .gizli{display:none}
 table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:2px 6px}
 .menu a{display:block;padding:3px 8px;cursor:pointer}
</style>"""


ANA_SAYFA = """<!doctype html><html><head><meta charset="utf-8"><title>AKIN COBAN [ 2026 ]</title>
""" + ORTAK_STIL + """</head><body>
<div id="ust" style="padding:6px;background:#eef">
  <select id="firma">__FIRMALAR__</select>
  <select id="donem">
    <option>01/01/2026 - 31/12/2026</option>
    <option>01/01/2025 - 31/12/2025</option>
  </select>
  <span id="onay" class="gizli">Seçim değişti <button id="tamam">Tamam</button></span>
  <span class="menu" style="display:inline-block;vertical-align:top">
    <a id="modul">İşletme Defteri</a>
    <div id="modulMenu" class="gizli">
      <a id="aen">Akıllı Entegrasyon Noktası</a>
      <div id="aenMenu" class="gizli" style="margin-left:14px">__AEN__</div>
      <a data-tip="e-arsiv-interaktif">E-Arşiv Faturaları Sorgulama</a>
      <a>Fiş İşlemleri</a><a>Beyanname İşlemleri</a>
    </div>
  </span>
</div>
<iframe id="ekran" name="ekran" src="about:blank" style="width:100%;height:600px;border:0"></iframe>
<script>
 const firma = document.getElementById('firma'), donem = document.getElementById('donem');
 const onay = document.getElementById('onay');
 let seciliFirma = firma.value;
 const ESKI = '__ESKI__';
 function sonra(ms, f){ setTimeout(f, ms); }
 firma.onchange = () => { onay.classList.remove('gizli'); };
 donem.onchange = () => { onay.classList.remove('gizli'); };
 document.getElementById('tamam').onclick = () => {
   onay.classList.add('gizli');
   sonra(500, () => {
     const yeni = firma.value !== seciliFirma;
     seciliFirma = firma.value;
     if (yeni) donem.selectedIndex = (seciliFirma === ESKI) ? 1 : 0;
     document.title = seciliFirma + ' [ ' + donem.value.slice(-4) + ' ]';
     document.getElementById('ekran').src = 'about:blank';
   });
 };
 document.getElementById('modul').onclick = () =>
   sonra(150, () => document.getElementById('modulMenu').classList.toggle('gizli'));
 const aen = document.getElementById('aen');
 aen.onmouseenter = aen.onclick = () =>
   sonra(150, () => document.getElementById('aenMenu').classList.remove('gizli'));
 document.querySelectorAll('[data-tip]').forEach(a => a.onclick = () => {
   document.getElementById('modulMenu').classList.add('gizli');
   document.getElementById('aenMenu').classList.add('gizli');
   sonra(300, () => {
     document.getElementById('ekran').src = '/ekran?tip=' + a.dataset.tip
       + '&firma=' + encodeURIComponent(seciliFirma) + '&t=' + Date.now();
   });
 });
</script></body></html>"""


EKRAN = """<!doctype html><html><head><meta charset="utf-8"><title>__BASLIK__</title>
""" + ORTAK_STIL + """</head><body>
<h3>__BASLIK__</h3>
<div id="arac">__ARAC__</div>
<table id="liste"><thead><tr><th></th><th>Fatura No</th><th>Unvan</th><th>Tarih</th>
<th>Fatura Tipi</th><th>Matrah</th><th>KDV</th><th>Durum</th></tr></thead><tbody></tbody></table>
<div id="sayac"></div>
<div id="uyari"></div>
<div id="perde" class="perde gizli"></div>
<div id="pencere" class="luca-open-window gizli"></div>
<script>
 const TIP = '__TIP__', FIRMA = '__FIRMA__';
 const q = 'tip=' + TIP + '&firma=' + encodeURIComponent(FIRMA);
 const pencere = document.getElementById('pencere'), perde = document.getElementById('perde');
 function sonra(ms, f){ setTimeout(f, ms); }
 function ac(html){ pencere.innerHTML = html; pencere.classList.remove('gizli'); perde.classList.remove('gizli'); }
 function kapat(){ pencere.classList.add('gizli'); perde.classList.add('gizli'); pencere.innerHTML=''; }
 function kapatDugmesi(){ return '<button onclick="kapat()">Kapat</button>'; }
 async function yukle(){
   const r = await fetch('/api/liste?' + q); const liste = await r.json();
   const tb = document.querySelector('#liste tbody'); tb.innerHTML = '';
   for (const f of liste) {
     const tr = document.createElement('tr');
     tr.innerHTML = '<td><input type="checkbox"></td><td>'+f.no+'</td><td>'+f.unvan+'</td><td>'
       + f.tarih+'</td><td>'+f.tip+'</td><td>'+f.matrah+'</td><td>'+f.kdv+'</td><td>'+f.durum+'</td>';
     tb.appendChild(tr);
   }
   document.getElementById('sayac').textContent = liste.length
     ? '1 / 1 (Toplam Kayıt Sayısı: ' + liste.length + ')' : '';
   return liste.length;
 }
 function secili(){ return [...document.querySelectorAll('#liste tbody input:checked')].length; }
 function indir(tur){ document.getElementById('uyari').textContent='';
   location.href = '/indir/' + tur + '?' + q; }
 function islemTakip(url, sonrasi){
   ac('<b>İşlem Takip</b><div id="gunluk"></div><label><input type=checkbox checked>Otomatik aşağı kaydır</label>');
   const g = () => document.getElementById('gunluk');
   sonra(500, () => g().innerHTML += '<div>Tarih aralığı sorgulandı</div>');
   sonra(1200, async () => { await fetch(url, {method:'POST'});
     g().innerHTML += '<div>belge kaydı bulundu</div>'; });
   sonra(3500, () => { g().innerHTML += '<div>İşlem sona erdi.</div>' + kapatDugmesi(); if (sonrasi) sonrasi(); });
 }
 const eylem = {
   getir: () => sonra(400, () => ac('<span>GİB\\'den fatura getir</span> '
       + 'Başlangıç <input type="text" name="baslangicTarihi" value="01/08/2026"> '
       + 'Bitiş <input type="text" name="bitisTarihi" value="31/08/2026"> '
       + '<button onclick="islemTakip(\\'/api/sorgula?\\'+q)">Belgeleri Getir</button>' + kapatDugmesi())),
   yenile: () => sonra(600, yukle),
   ara: () => sonra(400, () => ac('<span>Tarih Aralığı</span> '
       + '<input type="text" name="ilkTarih" value="01/08/2026"> <input type="text" name="sonTarih" value="31/08/2026">'
       + '<label><input type=checkbox>Muhasebeleşmiş</label>'
       + '<button onclick="kapat(); sonra(500, yukle)">Belge Ara</button>' + kapatDugmesi())),
   sec: () => sonra(300, () => ac('<span>Belge Seçiniz</span> <button id="tumu">Tümünü Seç</button>'
       + '<button id="secTamam">Tamam</button>' + kapatDugmesi())),
   indir: () => {
     if (!secili()) { document.getElementById('uyari').textContent = 'Lütfen indirilecek faturaları seçiniz'; return; }
     sonra(400, () => ac('<span>Tüm faturaları seçmek için <a href="#" id="buraya">buraya</a>,'
       + ' onaylanmışlar için <a href="#">buraya</a> tıklayınız</span> '
       + '<button onclick="kapat(); indir(\\'zip\\')">Seçilenleri İndir</button>' + kapatDugmesi()));
   },
   excel: () => {
     if (TIP !== 'e-arsiv-interaktif' && !secili()) {
       document.getElementById('uyari').textContent = 'Lütfen önce faturaları seçiniz'; return; }
     indir('excel');
   },
   iptal: () => sonra(400, () => ac('<span>Raporlanma Tarihi aralığı</span> '
       + '<input type="text" name="rapBas" value="01/08/2026"> <input type="text" name="rapBit" value="31/08/2026"> '
       + '<button onclick="islemTakip(\\'/api/iptal?\\'+q)">İptal/İtiraz Sorgula</button>' + kapatDugmesi())),
   interaktif: () => sonra(400, () => ac('<span>Luca Proxy ile Sorgula / GİB Servis ile Sorgula</span>'
       + '<p><label><input type="radio" name="yol" checked>Luca Proxy ile Sorgula</label></p>'
       + '<p><label><input type="radio" name="yol" id="servis">GİB Servis ile Sorgula</label></p>'
       + '<button id="iSorgu">İnteraktif V.D\\'sinden E-Arşiv Faturalarını Sorgula</button>' + kapatDugmesi())),
   listele: () => sonra(500, yukle),
 };
 document.addEventListener('click', e => {
   const t = e.target;
   if (t.id === 'tumu') document.querySelectorAll('#liste tbody input').forEach(k => k.checked = true);
   if (t.id === 'secTamam') kapat();
   if (t.id === 'buraya') { e.preventDefault(); document.querySelectorAll('#liste tbody input').forEach(k => k.checked = true); }
   if (t.id === 'iSorgu') {
     if (!document.getElementById('servis').checked) return;
     kapat(); sonra(1500, async () => { await fetch('/api/sorgula?' + q, {method:'POST'}); yukle(); });
   }
   if (t.dataset && t.dataset.e) eylem[t.dataset.e]();
 });
 yukle().then(n => { if (!n && FIRMA === '__FATURASIZ__')
   sonra(300, () => ac('<span>Her hangi bir fatura bulunamadı.</span> <button onclick="kapat()">Tamam</button>')); });
</script></body></html>"""

AEN_ARAC = """<button data-e="getir" title="Alt+g">GİB'den Getir</button>
<button data-e="yenile">Yenile</button><button data-e="ara">Belge Ara</button>
<button data-e="sec">Belge Seç</button><button data-e="indir">Seçilenleri İndir</button>
<button data-e="excel">Excel</button><button data-e="iptal">GİB'den İptal/İtiraz Sorgula</button>"""

INTERAKTIF_ARAC = """Başlangıç <input type="text" name="ilkTarih" value="01/08/2026">
Bitiş <input type="text" name="sonTarih" value="31/08/2026">
<button data-e="interaktif">İnteraktif V.D'sinden E-Arşiv Faturalarını Sorgula</button>
<button data-e="listele">Mevcut E-Arşiv Faturalarını Listele</button>
<button data-e="iptal">GİB'den İptal/İtiraz Sorgula</button><button data-e="excel">Excel</button>"""


class Isleyici(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _yanit(self, govde, tur="text/html; charset=utf-8", ek=None, durum=200):
        if isinstance(govde, str):
            govde = govde.encode("utf-8")
        self.send_response(durum)
        self.send_header("Content-Type", tur)
        self.send_header("Content-Length", str(len(govde)))
        for k, v in (ek or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(govde)

    def _parametre(self):
        u = urlparse(self.path)
        p = {k: v[0] for k, v in parse_qs(u.query).items()}
        return u.path, p.get("firma", ""), p.get("tip", "")

    def do_GET(self):
        yol, firma, tip = self._parametre()
        if yol == "/":
            secenek = "".join(f"<option>{f}</option>" for f in FIRMALAR)
            aen = "".join(f'<a data-tip="{t}">{ad}</a>' for ad, t in AEN_EKRANLARI.items())
            html = (ANA_SAYFA.replace("__FIRMALAR__", secenek).replace("__AEN__", aen)
                    .replace("__ESKI__", ESKI_DONEMLI))
            return self._yanit(html)
        if yol == "/ekran":
            baslik = next((ad for ad, t in AEN_EKRANLARI.items() if t == tip), "E-Arşiv Faturaları Sorgulama")
            arac = INTERAKTIF_ARAC if tip == "e-arsiv-interaktif" else AEN_ARAC
            html = (EKRAN.replace("__BASLIK__", baslik).replace("__ARAC__", arac)
                    .replace("__TIP__", tip).replace("__FIRMA__", firma)
                    .replace("__FATURASIZ__", FATURASIZ))
            return self._yanit(html)
        if yol == "/api/liste":
            return self._yanit(json.dumps(gorunen_faturalar(firma, tip)), "application/json")
        if yol == "/indir/excel":
            return self._yanit(excel_bayt(firma, tip),
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               {"Content-Disposition": 'attachment; filename="faturalar.xlsx"'})
        if yol == "/indir/zip":
            return self._yanit(zip_bayt(firma, tip), "application/zip",
                               {"Content-Disposition": 'attachment; filename="belgeler.zip"'})
        self._yanit("yok", durum=404)

    def do_POST(self):
        yol, firma, tip = self._parametre()
        with KILIT:
            d = DURUM.setdefault((firma, tip), {})
            if yol == "/api/sorgula":
                d["sorgulandi"] = True
            elif yol == "/api/iptal":
                d["iptal"] = True
        self._yanit("{}", "application/json")


def baslat(port=0):
    """Sunucuyu arka planda baslatir; (sunucu, adres) doner."""
    sunucu = ThreadingHTTPServer(("127.0.0.1", port), Isleyici)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    return sunucu, f"http://127.0.0.1:{sunucu.server_address[1]}/"


def sifirla():
    with KILIT:
        DURUM.clear()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    s, adres = baslat(port)
    print(f"Sahte Luca: {adres}  (durdurmak icin Ctrl+C)")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        s.shutdown()
