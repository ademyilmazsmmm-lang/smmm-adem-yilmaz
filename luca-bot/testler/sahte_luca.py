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
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

FIRMALAR = ["AKIN COBAN", "DENTAL SAGLIK", "ESKI DONEM LTD", "FATURASIZ AS",
            "KEREM TICARET", "MERT INSAAT"]
# Bu firma Luca'da en son 2025 doneminde birakilmis gibi acilir
ESKI_DONEMLI = "ESKI DONEM LTD"
# Bu firmalar isletme/SMK: Muhasebe menusunde Beyannameler yok (yalniz genel muhasebe firmalarinda var)
ISLETME_FIRMALARI = {"AKIN COBAN", "DENTAL SAGLIK"}
# Bu firmada hic fatura yok
FATURASIZ = "FATURASIZ AS"

# Yönetici > Müşteri İşlemleri > Müşteri Listesi: (kisa ad, unvan, VKN, acilis, kapanis, yillar)
MUSTERILER = [
    ("AKIN COBAN", "AKIN ÇOBAN", "1111111111", "01/01/2020", "31/12/2026", (2025, 2026)),
    ("DENTAL SAGLIK", "DENTAL SAĞLIK HİZMETLERİ LTD. ŞTİ.", "2222222222", "15/04/2026", "", (2026,)),
    ("ESKI DONEM LTD", "ESKİ DÖNEM LİMİTED ŞİRKETİ", "3333333333", "01/01/2015", "", (2025,)),
    ("FATURASIZ AS", "FATURASIZ ANONİM ŞİRKETİ", "4444444444", "01/01/2018", "", (2025, 2026)),
    ("KEREM TICARET", "KEREM TİCARET", "5555555555", "01/01/2019", "28/02/2026", (2025, 2026)),
    ("MERT INSAAT", "MERT İNŞAAT SANAYİ", "6666666666", "01/01/2021", "", (2025, 2026)),
    ("YENI FIRMA LTD", "YENİ FİRMA LİMİTED ŞİRKETİ", "7777777777", "01/06/2026", "", (2026,)),
    # gercek Luca'da vergi no'su ve TC'si bos firma da listede
    ("NUMARASIZ KISI", "NUMARASIZ KİŞİ", "", "01/02/2026", "", (2026,)),
]

# Muhasebe > Beyannameler > GİB Beyanname Takip: (kisa ad, uzun ad, TCKN, VKN, ay, durum)
BEYANNAMELER = [
    ("AKIN COBAN", "AKIN ÇOBAN", "56221452838", "2581374902", 8, "Onaylanmış"),
    ("KEREM TICARET", "KEREM TİCARET", "12345678901", "5555555555", 8, "Onaylanmış"),
    ("MERT INSAAT", "MERT İNŞAAT SANAYİ", "", "6666666666", 8, "Onaylanmış"),
    ("MERT INSAAT", "MERT İNŞAAT SANAYİ", "", "6666666666", 8, "Hatalı"),       # durum suzgecinde elenir
    ("YENI FIRMA LTD", "YENİ FİRMA LİMİTED", "", "7777777777", 7, "Onaylanmış"),  # donem suzgecinde elenir
]
AYLAR_TR = ["OCAK", "ŞUBAT", "MART", "NİSAN", "MAYIS", "HAZİRAN", "TEMMUZ", "AĞUSTOS", "EYLÜL", "EKİM",
            "KASIM", "ARALIK"]

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
# urun seciminde uygulama penceresinin kac kez acildigi (cift tiklama testi icin)
SAYAC = {"sso": 0, "ilk_bos": False, "gib_hatasi": 0, "excel": 0, "excel_gecikme": 0,
        "zip_basarisiz": 0}

# gercek Luca'da goruldu (26/09/2026); gecici, ayni sorgu tekrarlaninca geciyor
GIB_HATA_METNI = ("GİB e-Arşiv Sistemi Hata Mesajı:Doğrulama hatası Internet vergi dairesinden"
                  " kimlik doğrulanamadı.")

# Gercek Luca'daki gibi: urun kutusuna tiklaninca uygulama AYRI pencerede ve
# gecikmeli aciliyor; giris sekmesi oldugu gibi kaliyor.
URUN_SAYFASI = """<!doctype html><html><head><meta charset="utf-8"><title>LUCA - Ortak Giriş Sayfası</title>
</head><body><div id="kutu" style="cursor:pointer;padding:20px;background:#2aa">LUCA MALİ MÜŞAVİR PAKETİ</div>
<script>document.getElementById('kutu').onclick = () =>
  setTimeout(() => window.open('/Luca/ssoGiris.do', '_blank'), 800);</script></body></html>"""
SSO_SAYFASI = """<!doctype html><html><head><meta charset="utf-8"><title>yukleniyor</title></head>
<body><script>setTimeout(() => location.href = '/Luca/uygulama', 2500);</script></body></html>"""
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
    <a id="muhasebe">Muhasebe</a>
    <div id="muhasebeMenu" class="gizli">
      <a>Hesap Planı İşlemleri</a>
      <a id="beyannameler">Beyannameler</a>
      <div id="beyannameMenu" class="gizli" style="margin-left:14px"><a>KDV</a><a id="gibTakip">GİB Beyanname Takip</a></div>
    </div>
  </span>
  <span class="menu" style="display:inline-block;vertical-align:top">
    <a id="yonetici">Yönetici</a>
    <div id="yoneticiMenu" class="gizli">
      <a id="musteriIslemleri">Müşteri İşlemleri</a>
      <div id="musteriMenu" class="gizli" style="margin-left:14px"><a id="musteriListesi">Müşteri Listesi</a></div>
      <a>Kullanıcı İşlemleri</a>
    </div>
  </span>
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
<div id="sekmeler"></div>
<script>
 const firma = document.getElementById('firma'), donem = document.getElementById('donem');
 const onay = document.getElementById('onay');
 let seciliFirma = firma.value;
 const ESKI = '__ESKI__';
 const ISLETME = __ISLETME__;
 function menuGuncelle(){ document.getElementById('beyannameler').style.display =
   ISLETME.includes(seciliFirma) ? 'none' : ''; }
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
     document.getElementById('sekmeler').innerHTML = '';  // firma degisince sekmeler kapanir
     menuGuncelle();
   });
 };
 document.getElementById('modul').onclick = () =>
   sonra(150, () => document.getElementById('modulMenu').classList.toggle('gizli'));
 function sekmeAc(adres){
   const sekmeler = document.getElementById('sekmeler');
   sekmeler.querySelectorAll('div.sekme').forEach(d => d.style.display = 'none');
   const d = document.createElement('div'); d.className = 'sekme';
   d.innerHTML = '<iframe style="width:100%;height:600px;border:0"></iframe>';
   sekmeler.appendChild(d);
   d.firstChild.src = adres;
 }
 document.getElementById('yonetici').onclick = () =>
   sonra(150, () => document.getElementById('yoneticiMenu').classList.toggle('gizli'));
 const mi = document.getElementById('musteriIslemleri');
 mi.onmouseenter = mi.onclick = () =>
   sonra(150, () => document.getElementById('musteriMenu').classList.remove('gizli'));
 document.getElementById('musteriListesi').onclick = () => {
   document.getElementById('yoneticiMenu').classList.add('gizli');
   sonra(300, () => sekmeAc('/musteri-listesi?t=' + Date.now()));
 };
 document.getElementById('muhasebe').onclick = () =>
   sonra(150, () => document.getElementById('muhasebeMenu').classList.toggle('gizli'));
 menuGuncelle();
 const by = document.getElementById('beyannameler');
 by.onmouseenter = by.onclick = () =>
   sonra(150, () => document.getElementById('beyannameMenu').classList.remove('gizli'));
 document.getElementById('gibTakip').onclick = () => {
   document.getElementById('muhasebeMenu').classList.add('gizli');
   // gercek Luca'da bu ekran ana sayfanin icinde degil ayri pencerede aciliyor
   sonra(300, () => window.open('/gib-beyanname-takip?t=' + Date.now(), '_blank', 'popup,width=1100,height=750'));
 };
 const aen = document.getElementById('aen');
 aen.onmouseenter = aen.onclick = () =>
   sonra(150, () => document.getElementById('aenMenu').classList.remove('gizli'));
 document.querySelectorAll('[data-tip]').forEach(a => a.onclick = () => {
   document.getElementById('modulMenu').classList.add('gizli');
   document.getElementById('aenMenu').classList.add('gizli');
   sonra(300, () => {
     // gercek Luca gibi: her ekran yeni bir sekmede (iframe) acilir, eskiler gizlenip kalir
     const sekmeler = document.getElementById('sekmeler');
     sekmeler.querySelectorAll('div.sekme').forEach(d => d.style.display = 'none');
     const d = document.createElement('div'); d.className = 'sekme';
     d.innerHTML = '<iframe style="width:100%;height:600px;border:0"></iframe>';
     sekmeler.appendChild(d);
     d.firstChild.src = '/ekran?tip=' + a.dataset.tip
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
<!-- gercek Luca'da oldugu gibi: sayfada gizli bir pencere de durur ve ilk sirada -->
<div class="luca-open-window gizli">Her hangi bir fatura bulunamadı <button>Tamam</button></div>
<div id="pencere" class="luca-open-window gizli"></div>
<!-- gercek Luca'da GİB'den Getir'in tarih penceresi .luca-open-window degil -->
<div id="tarihPenceresi" class="tarih-dialog gizli" style="position:fixed;top:120px;left:160px;background:#fff;border:1px solid #888;padding:12px"></div>
<script>
 const TIP = '__TIP__', FIRMA = '__FIRMA__';
 const q = 'tip=' + TIP + '&firma=' + encodeURIComponent(FIRMA);
 const pencere = document.getElementById('pencere'), perde = document.getElementById('perde');
 function sonra(ms, f){ setTimeout(f, ms); }
 function ac(html){ pencere.innerHTML = html; pencere.classList.remove('gizli'); perde.classList.remove('gizli'); }
 function kapat(){ pencere.classList.add('gizli'); perde.classList.add('gizli'); pencere.innerHTML=''; }
 function kapatDugmesi(){ return '<button onclick="kapat()">Kapat</button>'; }
 async function zipIndir(){
   // gercek Luca'da ara sira butona tiklaninca hicbir istek gitmiyor (tepkisiz kaliyor)
   const r = await fetch('/api/zip-durumu'); const j = await r.json();
   if (!j.atla) indir('zip');
 }
 async function yukle(){
   const r = await fetch('/api/liste?' + q); const liste = await r.json();
   const tb = document.querySelector('#liste tbody'); tb.innerHTML = '';
   for (const f of liste) {
     const tr = document.createElement('tr');
     tr.innerHTML = '<td><input type="checkbox"></td><td>'+f.no+'</td><td>'+f.unvan+'</td><td>'
       + f.tarih+'</td><td>'+f.tip+'</td><td>'+f.matrah+'</td><td>'+f.kdv+'</td><td>'+f.durum+'</td>';
     tb.appendChild(tr);
   }
   // gercek Luca gibi: liste bos da olsa kayit sayisi yazar
   document.getElementById('sayac').textContent = '1 / 1 (Toplam Kayıt Sayısı: ' + liste.length + ')';
   bildirim(liste.length ? '' : 'Fatura bulunamadı.');
   return liste.length;
 }
 // gercek Luca'da sorgu sonucu duz bir bildirimle de gosteriliyor: dugmesi yok, birkac sn kalir
 let bildirimZamani = null;
 function bildirim(metin){
   let b = document.getElementById('bildirim');
   if (!metin) { if (b) b.remove(); return; }
   if (!b) { b = document.createElement('div'); b.id = 'bildirim'; b.className = 'luca-open-window';
     b.style.cssText = 'position:fixed;right:20px;bottom:20px;padding:10px;background:#ffe;border:1px solid #cb8;'
       + 'min-width:160px'; document.body.appendChild(b); }
   b.textContent = metin; clearTimeout(bildirimZamani);
   bildirimZamani = setTimeout(() => { const x = document.getElementById('bildirim'); if (x) x.remove(); }, 6000);
 }
 function secili(){ return [...document.querySelectorAll('#liste tbody input:checked')].length; }
 function indir(tur){ document.getElementById('uyari').textContent='';
   location.href = '/indir/' + tur + '?' + q; }
 function islemTakip(url, sonrasi){
   ac('<b>İşlem Takip</b><div id="gunluk"></div><label><input type=checkbox checked>Otomatik aşağı kaydır</label>');
   const g = () => document.getElementById('gunluk');
   const bu = g();  // pencere kapatilirsa (bot erken cikarsa) sorgu yarida kalir
   sonra(500, () => g().innerHTML += '<div>Tarih aralığı sorgulandı</div>');
   // gercek Luca'daki gibi: faturasiz gunler icin sorgu SURERKEN kirmizi satir yazar
   sonra(900, () => { if (g() === bu) g().innerHTML += '<div style="color:red">Sorgulama Tarihi: 01/08/2026'
     + ' Hata mesajı: Belirtilen tarih aralığında fatura bulunamadı. Bu hata GİB servislerinden alınmıştır.</div>'; });
   let hata = false;
   sonra(2000, async () => { if (g() !== bu) return;
     const j = await (await fetch(url, {method:'POST'})).json();
     if (j.hata) { hata = true;  // gercek Luca'daki gibi: hata yazar, pencere kapanmaz, "sona erdi" gelmez
       g().innerHTML += '<div style="color:red">' + j.hata + '</div>' + kapatDugmesi(); return; }
     g().innerHTML += '<div>belge kaydı bulundu</div>'; });
   sonra(3500, () => { if (hata) return;
     g().innerHTML += '<div>İşlem sona erdi.</div>' + kapatDugmesi(); if (sonrasi) sonrasi(); });
 }
 const eylem = {
   getir: () => sonra(400, () => { const t = document.getElementById('tarihPenceresi');
       t.innerHTML = '<span>GİB\\'den fatura getir</span> '
       + 'Başlangıç <input type="text" name="baslangicTarihi" value="01/08/2026"> '
       + 'Bitiş <input type="text" name="bitisTarihi" value="31/08/2026"> '
       + '<button onclick="document.getElementById(\\'tarihPenceresi\\').classList.add(\\'gizli\\');'
       + ' islemTakip(\\'/api/sorgula?\\'+q)">Belgeleri Getir</button>'
       + '<button onclick="document.getElementById(\\'tarihPenceresi\\').classList.add(\\'gizli\\')">Kapat</button>';
       t.classList.remove('gizli'); }),
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
       + '<button onclick="kapat(); zipIndir()">Seçilenleri İndir</button>' + kapatDugmesi()));
   },
   excel: () => {
     if (TIP !== 'e-arsiv-interaktif' && !secili()) {
       document.getElementById('uyari').textContent = 'Lütfen önce faturaları seçiniz'; return; }
     // interaktif ekranda Excel gercek Luca'daki gibi gec geliyor
     if (TIP === 'e-arsiv-interaktif') sonra(1500, () => indir('excel'));
     // gercek Luca'da Excel yeni bir tarayici sekmesinde aciliyor
     else if (TIP === 'e-arsiv-alis') window.open('/excel-sayfa?' + q, '_blank');
     else indir('excel');
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

MUSTERI_SAYFASI = """<!doctype html><html><head><meta charset="utf-8"><title>Müşteri Listesi</title>
""" + ORTAK_STIL + """</head><body>
<h3>Müşteri Listesi</h3>
<table id="liste"><thead><tr><th></th><th>Kısa Adı</th><th>Uzun Adı</th><th>Vergi Dairesi</th><th>Vergi No</th>
<th>TC Kimlik No</th><th>Açıklama</th><th>Kuruluş Tarihi</th><th>Kapanış Tarihi</th></tr></thead><tbody></tbody></table>
<div id="sayac"></div>
<div id="araclar"><button>Yeni</button> <button id="filtre">Filtre</button> <button>Şirket Sil</button>
<button>Mükellef Bilgi</button> <button>Yetki Tablosu</button> <button>Diğer İşlemler</button></div>
<div id="pencere" class="luca-open-window gizli">
  <b>Müşteri Arama</b>
  <p>Yıl <select id="yil"><option></option><option>2025</option><option>2026</option></select></p>
  <p>Sınıf <select><option>Tümü</option><option>A</option></select></p>
  <p>Dönem Durumu <select><option>Tümü</option><option>Açık</option></select></p>
  <button id="ara">Ara</button> <button onclick="document.getElementById('pencere').classList.add('gizli')">Kapat</button>
</div>
<script>
 document.getElementById('filtre').onclick = () =>
   setTimeout(() => document.getElementById('pencere').classList.remove('gizli'), 400);
 document.getElementById('ara').onclick = async () => {
   const yil = document.getElementById('yil').value;
   document.getElementById('pencere').classList.add('gizli');
   const liste = await (await fetch('/api/musteriler?yil=' + yil)).json();
   const tb = document.querySelector('#liste tbody'); tb.innerHTML = '';
   setTimeout(() => {
     for (const m of liste) {
       const tr = document.createElement('tr');
       tr.innerHTML = '<td><input type="checkbox"></td>' + m.map(x => '<td>' + x + '</td>').join('');
       tb.appendChild(tr);
     }
     document.getElementById('sayac').textContent = 'Kayıt Sayısı: ' + liste.length;
   }, 800);
 };
</script></body></html>"""

BEYANNAME_SAYFASI = """<!doctype html><html><head><meta charset="utf-8"><title>GİB Beyanname Takip</title>
""" + ORTAK_STIL + """</head><body>
<h3>GİB Beyanname Takip</h3>
<table id="liste"><thead><tr><th><input type="checkbox" id="hepsi"></th><th>TCKN</th><th>VKN</th><th>Mükellef Adı</th>
<th>Tip</th><th>Beyanname Durum</th><th>Dönem</th></tr></thead><tbody></tbody></table>
<div id="araclar"><button id="filtre">Filtre</button> <button>GİB'den Getir</button>
<button>Sorgula</button> <button id="toplu">Toplu İşlemler</button></div>
<div id="bildirim" class="luca-open-window gizli" style="top:auto;bottom:10px;left:auto;right:10px;min-width:100px"></div>
<div id="arama" class="luca-open-window gizli">
  <b>BEYANNAME ARAMA</b>
  <table>
   <tr><td>Paket Yükleme Tarihi</td><td><input type="text" id="t1" value="01/09/2026"><input type="text" id="t2" value="04/10/2026"></td></tr>
   <tr><td>Beyanname Dönemi</td><td><select id="ay">__AYLAR__</select><select id="yil"><option>2025</option><option selected>2026</option></select></td></tr>
   <tr><td>Paket Durum</td><td><select><option>Tümü</option></select></td></tr>
   <tr><td>Beyanname Durum</td><td><select id="durum"><option>Tümü</option><option>Onaylanmış</option><option>Hatalı</option></select></td></tr>
   <tr><td>Onaylanabilir Durumda mı?</td><td><select><option>Tümü</option></select></td></tr>
   <tr><td>Beyanname</td><td><select id="tur"><option>Tümü</option><option>KDV1</option><option>KDV2</option></select></td></tr>
   <tr><td>TCKN/VKN</td><td><input type="text"></td></tr>
  </table>
  <button id="listele">Beyannameleri Listele</button>
</div>
<div id="toplupencere" class="luca-open-window gizli">
  <b>TOPLU İŞLEMLER</b>
  <ul><li>Seçili olan onaylanmış beyannamelerin beyanname ve tahakkuk dosyalarını indirmek için <a href="#" id="indir">buraya</a> tıklayınız.</li>
  <li>Seçili olan onaylanabilir beyannameleri onaylamak için <a href="#">buraya</a> tıklayınız.</li></ul>
</div>
<script>
 let sorgu = '';
 const g = id => document.getElementById(id);
 g('filtre').onclick = () => setTimeout(() => g('arama').classList.remove('gizli'), 300);
 g('hepsi').onchange = () => document.querySelectorAll('#liste tbody input').forEach(k => k.checked = g('hepsi').checked);
 g('listele').onclick = async () => {
   sorgu = 'ay=' + g('ay').selectedIndex + '&yil=' + g('yil').value + '&durum=' + encodeURIComponent(g('durum').value)
     + '&tur=' + g('tur').value;
   g('arama').classList.add('gizli');
   const liste = await (await fetch('/api/beyannameler?' + sorgu)).json();
   const tb = document.querySelector('#liste tbody'); tb.innerHTML = '';
   setTimeout(() => {
     for (const b of liste) tb.insertAdjacentHTML('beforeend', '<tr><td><input type="checkbox"></td><td>' + b[2]
       + '</td><td>' + b[3] + '</td><td>' + b[1] + '</td><td>KDV1</td><td>' + b[5] + '</td><td>2026/0' + b[4] + '</td></tr>');
     const x = g('bildirim'); x.textContent = liste.length + ' adet beyanname kaydı listelendi.';
     x.classList.remove('gizli');
   }, 700);
 };
 g('toplu').onclick = () => setTimeout(() => g('toplupencere').classList.remove('gizli'), 300);
 g('indir').onclick = e => { e.preventDefault(); g('toplupencere').classList.add('gizli');
   setTimeout(() => { location.href = '/indir/beyannameler?' + sorgu; }, 1200); };
</script></body></html>"""


def beyanname_listesi(ay, yil, durum, tur):
    """Suzgece uyan satirlar (yalniz KDV1 ve 2026 verisi var)."""
    if tur not in ("Tümü", "KDV1") or yil != 2026:
        return []
    return [b for b in BEYANNAMELER if b[4] == ay + 1 and durum in ("Tümü", b[5])]


def beyanname_zip(satirlar):
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as z:
        for ad, _uzun, _tc, vkn, ay, _durum in satirlar:
            on = ad.replace(" ", "_")
            z.writestr(f"{on}_034252_{vkn}_KDV1_45_0{ay}082026-3108{ay}_BYN_17.pdf", b"%PDF-1.4 beyanname " + vkn.encode())
            z.writestr(f"{on}_034252_{vkn}_KDV1_45_0{ay}082026-3108{ay}_THK_17.pdf", b"%PDF-1.4 tahakkuk " + vkn.encode())
    return tampon.getvalue()


AEN_ARAC = """<button data-e="getir" title="Alt+g">GİB'den Getir</button>
<button data-e="yenile">Yenile</button><button data-e="ara">Belge Ara</button>
<button data-e="sec">Belge Seç</button><button data-e="indir">Seçilenleri İndir</button>
<button data-e="excel">Excel</button><button data-e="iptal">GİB'den İptal/İtiraz Sorgula</button>"""

INTERAKTIF_ARAC = """Başlangıç <input type="text" name="ilkTarih" value="01/08/2026">
Bitiş <input type="text" name="sonTarih" value="31/08/2026">
<button data-e="interaktif">İnteraktif V.D'sinden E-Arşiv Faturalarını Sorgula</button>
<button data-e="listele">Mevcut E-Arşiv Faturalarını Listele</button>
<button data-e="iptal">GİB'den İptal/İtiraz Sorgula</button><button data-e="excel">Excel</button>
<div style="color:red">** Uyarı: Lütfen faturalarınızla ekrandaki tutarları kontrol ediniz.</div>"""


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
        if yol == "/urun":
            with KILIT:  # ?ilk_bos=1: ilk acilan uygulama penceresi bos kalir (gercek Luca'daki gibi)
                SAYAC["ilk_bos"] = "ilk_bos=1" in self.path
            return self._yanit(URUN_SAYFASI)
        if yol == "/Luca/ssoGiris.do":
            with KILIT:
                SAYAC["sso"] += 1
                bos = SAYAC["ilk_bos"] and SAYAC["sso"] == 1
            return self._yanit("<!doctype html><html><body></body></html>" if bos else SSO_SAYFASI)
        if yol in ("/", "/Luca/uygulama"):
            secenek = "".join(f"<option>{f}</option>" for f in FIRMALAR)
            aen = "".join(f'<a data-tip="{t}">{ad}</a>' for ad, t in AEN_EKRANLARI.items())
            html = (ANA_SAYFA.replace("__FIRMALAR__", secenek).replace("__AEN__", aen)
                    .replace("__ESKI__", ESKI_DONEMLI)
                    .replace("__ISLETME__", json.dumps(sorted(ISLETME_FIRMALARI))))
            return self._yanit(html)
        if yol == "/gib-beyanname-takip":
            aylar = "".join(f"<option>{a}</option>" for a in AYLAR_TR)
            return self._yanit(BEYANNAME_SAYFASI.replace("__AYLAR__", aylar))
        if yol in ("/api/beyannameler", "/indir/beyannameler"):
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            satirlar = beyanname_listesi(int(q.get("ay", 0)), int(q.get("yil", 0)),
                                         q.get("durum", "Tümü"), q.get("tur", "Tümü"))
            if yol == "/api/beyannameler":
                return self._yanit(json.dumps(satirlar), "application/json")
            time.sleep(1.5)  # Luca toplu dosyayi hazirlarken bekletir
            return self._yanit(beyanname_zip(satirlar), "application/zip",
                               {"Content-Disposition": 'attachment; filename="beyannameler.zip"'})
        if yol == "/musteri-listesi":
            return self._yanit(MUSTERI_SAYFASI)
        if yol == "/api/musteriler":
            yil = int((parse_qs(urlparse(self.path).query).get("yil") or ["0"])[0] or 0)
            liste = [[m[0], m[1], "ÜMRANİYE VERGİ DAİRESİ", m[2], "", "", m[3], m[4]] for m in
                     [mm for mm in MUSTERILER if yil in mm[5]]] if yil else []
            return self._yanit(json.dumps(liste), "application/json")
        if yol == "/ekran":
            baslik = next((ad for ad, t in AEN_EKRANLARI.items() if t == tip), "E-Arşiv Faturaları Sorgulama")
            arac = INTERAKTIF_ARAC if tip == "e-arsiv-interaktif" else AEN_ARAC
            if tip.startswith("turmob"):  # gercek Luca'da bu ekranlarin dugmesi "TÜRMOB'dan Getir"
                arac = arac.replace("GİB'den Getir", "TÜRMOB'dan Getir")
            if firma == "MERT INSAAT" and tip == "esmm-alis":
                arac = "<i>Bu modul firmada tanimli degil</i>"  # ekran bos gelir
            html = (EKRAN.replace("__BASLIK__", baslik).replace("__ARAC__", arac)
                    .replace("__TIP__", tip).replace("__FIRMA__", firma)
                    .replace("__FATURASIZ__", FATURASIZ))
            return self._yanit(html)
        if yol == "/excel-sayfa":  # yeni sekmede acilan ara sayfa, dosyayi kendisi indirir
            hedef = "/indir/excel?" + urlparse(self.path).query
            return self._yanit(f"<html><body>Excel hazirlaniyor...<script>"
                               f"setTimeout(() => location.href = '{hedef}', 300)</script></body></html>")
        if yol == "/api/liste":
            return self._yanit(json.dumps(gorunen_faturalar(firma, tip)), "application/json")
        if yol == "/indir/excel":
            with KILIT:
                SAYAC["excel"] += 1
                gecikme = SAYAC["excel_gecikme"]
            time.sleep(gecikme)  # buyuk listede Luca Excel'i dakikalarca hazirlayabiliyor
            return self._yanit(excel_bayt(firma, tip),
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               {"Content-Disposition": 'attachment; filename="faturalar.xlsx"'})
        if yol == "/api/zip-durumu":
            with KILIT:
                atla = SAYAC["zip_basarisiz"] > 0
                if atla:
                    SAYAC["zip_basarisiz"] -= 1
            return self._yanit(json.dumps({"atla": atla}), "application/json")
        if yol == "/indir/zip":
            return self._yanit(zip_bayt(firma, tip), "application/zip",
                               {"Content-Disposition": 'attachment; filename="belgeler.zip"'})
        self._yanit("yok", durum=404)

    def do_POST(self):
        yol, firma, tip = self._parametre()
        with KILIT:
            if yol == "/api/iptal" and SAYAC["gib_hatasi"] > 0:
                SAYAC["gib_hatasi"] -= 1
                return self._yanit(json.dumps({"hata": GIB_HATA_METNI}), "application/json")
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
        SAYAC.update(sso=0, ilk_bos=False, gib_hatasi=0, excel=0, excel_gecikme=0, zip_basarisiz=0)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    s, adres = baslat(port)
    print(f"Sahte Luca: {adres}  (durdurmak icin Ctrl+C)")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        s.shutdown()
