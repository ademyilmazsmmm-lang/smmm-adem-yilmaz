/* Bağımlılıksız basit PDF metin çıkarıcı (yalnız Node çekirdeği: zlib).
 * Amaç: GİB tahakkuk fişi gibi metin tabanlı PDF'lerden "devreden KDV" gibi satırları okumak. Taranmış (resim) PDF'lerde çalışmaz.
 * Desteklenenler: klasik ve nesne akışlı (ObjStm) PDF, Flate sıkıştırma, ToUnicode eşlemeli Type0/Identity-H yazı tipleri, basit yazı tipleri. */
const zlib = require("zlib");

function ac(buf) { try { return zlib.inflateSync(buf); } catch (e) { try { return zlib.inflateRawSync(buf); } catch (e2) { return null; } } }
const l1 = (b) => b.toString("latin1");

/* nesne tablosu: no -> { dict: "<<...>>" metni (akıştan önce), akis: Buffer|null } */
function nesneler(buf) {
  const s = l1(buf), tablo = new Map(), re = /(\d+)\s+(\d+)\s+obj\b/g; let m;
  const yer = [];
  while ((m = re.exec(s))) yer.push({ no: +m[1], bas: m.index + m[0].length });
  for (let i = 0; i < yer.length; i++) {
    const bit = s.indexOf("endobj", yer[i].bas); const ic = s.slice(yer[i].bas, bit < 0 ? s.length : bit);
    const si = ic.search(/stream\r?\n/);
    let dict = ic, akis = null;
    if (si >= 0) {
      dict = ic.slice(0, si); const basAkis = yer[i].bas + si + ic.slice(si).match(/stream\r?\n/)[0].length;
      let son = s.indexOf("endstream", basAkis); if (son < 0) son = bit < 0 ? s.length : bit;
      let ham = buf.subarray(basAkis, son); /* sondaki satır sonu */
      if (ham[ham.length - 1] === 10) ham = ham.subarray(0, ham.length - (ham[ham.length - 2] === 13 ? 2 : 1)); else if (ham[ham.length - 1] === 13) ham = ham.subarray(0, ham.length - 1);
      akis = ham;
    }
    tablo.set(yer[i].no, { dict, akis });
  }
  /* nesne akışları (ObjStm) */
  for (const [no, o] of [...tablo]) {
    if (!o.akis || !/\/Type\s*\/ObjStm/.test(o.dict)) continue;
    const d = /\/FlateDecode/.test(o.dict) ? ac(o.akis) : o.akis; if (!d) continue;
    const n = +((/\/N\s+(\d+)/.exec(o.dict) || [])[1] || 0), first = +((/\/First\s+(\d+)/.exec(o.dict) || [])[1] || 0), t = l1(d), p = t.slice(0, first).trim().split(/\s+/).map(Number);
    for (let k = 0; k < n; k++) { const onNo = p[k * 2], off = p[k * 2 + 1], son = k + 1 < n ? p[(k + 1) * 2 + 1] : t.length - first; if (!Number.isFinite(onNo)) continue; tablo.set(onNo, { dict: t.slice(first + off, first + son), akis: null }); }
  }
  return tablo;
}
function a85(buf) {
  const t = l1(buf).replace(/\s+/g, "").replace(/^<~/, "").replace(/~>.*$/s, ""), out = []; let grup = [], i = 0;
  while (i < t.length) { const c = t[i]; if (c === "z" && grup.length === 0) { out.push(0, 0, 0, 0); i++; continue; } grup.push(t.charCodeAt(i) - 33); i++; if (grup.length === 5) { let v = 0; for (const g of grup) v = v * 85 + g; out.push((v >>> 24) & 255, (v >>> 16) & 255, (v >>> 8) & 255, v & 255); grup = []; } }
  if (grup.length > 1) { const n = grup.length; while (grup.length < 5) grup.push(84); let v = 0; for (const g of grup) v = v * 85 + g; const b4 = [(v >>> 24) & 255, (v >>> 16) & 255, (v >>> 8) & 255, v & 255]; out.push(...b4.slice(0, n - 1)); }
  return Buffer.from(out);
}
/* /Filter zinciri (ASCII85, ASCIIHex, Flate); desteklenmeyen filtrede null */
function akisVeri(o) {
  if (!o || !o.akis) return null; const fm = /\/Filter\s*(\[[^\]]*\]|\/[A-Za-z0-9]+)/.exec(o.dict); if (!fm) return o.akis;
  const liste = [...fm[1].matchAll(/\/([A-Za-z0-9]+)/g)].map((x) => x[1]); let v = o.akis;
  for (const f of liste) { if (f === "FlateDecode" || f === "Fl") v = ac(v); else if (f === "ASCII85Decode" || f === "A85") v = a85(v); else if (f === "ASCIIHexDecode" || f === "AHx") v = Buffer.from(l1(v).replace(/[^0-9A-Fa-f]/g, ""), "hex"); else return null; if (!v) return null; }
  return v;
}
const ref = (dict, anahtar) => { const m = new RegExp("/" + anahtar + "\\s+(\\d+)\\s+\\d+\\s+R").exec(dict); return m ? +m[1] : 0; };

/* ToUnicode CMap -> { bayt: 1|2, esle: Map(kod -> metin) } */
function cmap(veri) {
  const t = l1(veri), esle = new Map(); let bayt = 1;
  const cs = /begincodespacerange\s*<([0-9A-Fa-f]+)>/.exec(t); if (cs) bayt = Math.max(1, Math.min(2, cs[1].length / 2));
  const uni = (h) => { let r = ""; for (let i = 0; i + 3 < h.length + 1; i += 4) r += String.fromCharCode(parseInt(h.slice(i, i + 4), 16)); return r; };
  for (const b of t.matchAll(/beginbfchar([\s\S]*?)endbfchar/g)) for (const m of b[1].matchAll(/<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>/g)) esle.set(parseInt(m[1], 16), uni(m[2]));
  for (const b of t.matchAll(/beginbfrange([\s\S]*?)endbfrange/g)) {
    for (const m of b[1].matchAll(/<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(<[0-9A-Fa-f]+>|\[[^\]]*\])/g)) {
      const lo = parseInt(m[1], 16), hi = parseInt(m[2], 16);
      if (m[3][0] === "[") { const l = [...m[3].matchAll(/<([0-9A-Fa-f]+)>/g)].map((x) => uni(x[1])); for (let c = lo; c <= hi && c - lo < l.length; c++) esle.set(c, l[c - lo]); }
      else { const h = m[3].slice(1, -1), bas = parseInt(h, 16); for (let c = lo; c <= hi && c - lo < 70000; c++) { const v = (bas + (c - lo)).toString(16).padStart(h.length, "0"); esle.set(c, uni(v)); } }
    }
  }
  return { bayt, esle };
}

/* içerik akışından metin ve konumlu öğeler: yazı tipi değişimi (Tf), Tj/TJ/'/" ve konum matrisleri (cm, Tm, Td, TD, T*) */
const carp = (m, n) => [m[0] * n[0] + m[1] * n[2], m[0] * n[1] + m[1] * n[3], m[2] * n[0] + m[3] * n[2], m[2] * n[1] + m[3] * n[3], m[4] * n[0] + m[5] * n[2] + n[4], m[4] * n[1] + m[5] * n[3] + n[5]];
function icerikMetni(veri, yaziTipi, ogeler) {
  const s = l1(veri); let cikti = "", gecerli = null, boyut = 10, i = 0, TL = 0; const n = s.length;
  let ctm = [1, 0, 0, 1, 0, 0], tm = [1, 0, 0, 1, 0, 0], tlm = [1, 0, 0, 1, 0, 0]; const yigit = [];
  const coz = (bytlar) => {
    if (gecerli && gecerli.cm) { const cm = gecerli.cm; let r = ""; for (let k = 0; k + cm.bayt <= bytlar.length; k += cm.bayt) { let c = 0; for (let j = 0; j < cm.bayt; j++) c = c * 256 + bytlar[k + j]; r += cm.esle.has(c) ? cm.esle.get(c) : ""; } return r; }
    return Buffer.from(bytlar).toString("latin1");
  };
  const goster = (metin) => {
    if (!metin) return; cikti += metin;
    if (ogeler) { const g = carp(tm, ctm), efBoyut = Math.abs(boyut * (Math.hypot(tm[0], tm[1]) || 1) * (Math.hypot(ctm[0], ctm[1]) || 1)); ogeler.push({ x: g[4], y: g[5], s: metin, b: efBoyut }); }
    tm = carp([1, 0, 0, 1, boyut * 0.5 * metin.length * 1, 0], tm); /* aynı satırda sonraki parça için kabaca ilerle */
  };
  const yigin = [];
  const sayilar = (k) => yigin.filter((x) => x.t === "d").slice(-k).map((x) => x.v);
  while (i < n) {
    const c = s[i];
    if (c === "(") {
      let d = 1, j = i + 1, b = []; while (j < n && d > 0) { const x = s[j]; if (x === "\\") { const y = s[j + 1]; const e = { n: 10, r: 13, t: 9, b: 8, f: 12 }[y]; if (e != null) { b.push(e); j += 2; continue; } if (/[0-7]/.test(y)) { let o = y, k = j + 2; while (k < j + 4 && /[0-7]/.test(s[k])) o += s[k++]; b.push(parseInt(o, 8) & 255); j = k; continue; } if (y === "\n") { j += 2; continue; } b.push(y.charCodeAt(0)); j += 2; continue; } if (x === "(") d++; else if (x === ")") { d--; if (d === 0) break; } b.push(x.charCodeAt(0) & 255); j++; }
      yigin.push({ t: "s", v: b }); i = j + 1; continue;
    }
    if (c === "<" && s[i + 1] !== "<") { const j = s.indexOf(">", i); const h = s.slice(i + 1, j).replace(/\s+/g, ""); const b = []; for (let k = 0; k < h.length; k += 2) b.push(parseInt((h.slice(k, k + 2) + "0").slice(0, 2), 16)); yigin.push({ t: "s", v: b }); i = j + 1; continue; }
    if (c === "[") { yigin.push({ t: "[" }); i++; continue; }
    if (c === "]") { const dz = []; while (yigin.length && yigin[yigin.length - 1].t !== "[") dz.unshift(yigin.pop()); yigin.pop(); yigin.push({ t: "a", v: dz }); i++; continue; }
    if (c === "/") { let j = i + 1; while (j < n && !/[\s\/\[\]()<>]/.test(s[j])) j++; yigin.push({ t: "n", v: s.slice(i + 1, j) }); i = j; continue; }
    if (/\s/.test(c)) { i++; continue; }
    let j = i; while (j < n && !/[\s\/\[\]()<>]/.test(s[j])) j++; const w = s.slice(i, j) || s[i]; if (!w) { i++; continue; } i = Math.max(j, i + 1);
    if (/^[+-]?\d*\.?\d+$/.test(w)) { yigin.push({ t: "d", v: parseFloat(w) }); continue; }
    if (w === "q") yigit.push(ctm.slice());
    else if (w === "Q") { if (yigit.length) ctm = yigit.pop(); }
    else if (w === "cm") { const a = sayilar(6); if (a.length === 6) ctm = carp(a, ctm); }
    else if (w === "BT") { tm = [1, 0, 0, 1, 0, 0]; tlm = tm.slice(); }
    else if (w === "Tf") { const ad = yigin.filter((x) => x.t === "n").pop(), sz = sayilar(1); gecerli = ad ? yaziTipi(ad.v) : null; if (sz.length) boyut = sz[0]; }
    else if (w === "TL") { const a = sayilar(1); if (a.length) TL = a[0]; }
    else if (w === "Tm") { const a = sayilar(6); if (a.length === 6) { tm = a.slice(); tlm = a.slice(); } cikti += " "; }
    else if (w === "Td" || w === "TD") { const a = sayilar(2); if (a.length === 2) { tlm = carp([1, 0, 0, 1, a[0], a[1]], tlm); tm = tlm.slice(); if (w === "TD") TL = -a[1]; } cikti += " "; }
    else if (w === "T*") { tlm = carp([1, 0, 0, 1, 0, -TL], tlm); tm = tlm.slice(); cikti += "\n"; }
    else if (w === "Tj" || w === "'" || w === '"') { if (w !== "Tj") { tlm = carp([1, 0, 0, 1, 0, -TL], tlm); tm = tlm.slice(); } const x = yigin.filter((y) => y.t === "s").pop(); if (x) goster(coz(x.v)); if (w !== "Tj") cikti += "\n"; }
    else if (w === "TJ") { const a = yigin.filter((y) => y.t === "a").pop(); if (a) { let ek = ""; for (const e of a.v) { if (e.t === "s") ek += coz(e.v); else if (e.t === "d" && e.v < -250) ek += " "; } goster(ek); } }
    else if (w === "ET") cikti += "\n";
    yigin.length = 0;
  }
  return cikti;
}

/* "<<" ile başlayan sözlüğü iç içe sözlüklerle birlikte alır */
function denge(t, bas) {
  let d = 0, i = bas; for (; i < t.length - 1; i++) { if (t[i] === "<" && t[i + 1] === "<") { d++; i++; } else if (t[i] === ">" && t[i + 1] === ">") { d--; i++; if (d === 0) return t.slice(bas, i + 1); } }
  return t.slice(bas);
}
function anahtarDeger(dict, anahtar) { /* /Anahtar'ın değeri: sözlük, başvuru (N G R) ya da dizi */
  const m = new RegExp("/" + anahtar + "(?![A-Za-z0-9])\\s*").exec(dict); if (!m) return ""; const k = m.index + m[0].length;
  if (dict.startsWith("<<", k)) return denge(dict, k); const r = /^(\d+)\s+\d+\s+R/.exec(dict.slice(k)); if (r) return r[0]; if (dict[k] === "[") return dict.slice(k, dict.indexOf("]", k) + 1); return "";
}
function pdfMetni(buf, ogelerCikis) {
  const t = nesneler(buf), fontCm = new Map();
  const coz = (v) => { const r = /^(\d+)\s+\d+\s+R$/.exec((v || "").trim()); return r && t.get(+r[1]) ? t.get(+r[1]).dict : v || ""; };
  const cmapAl = (no) => { if (fontCm.has(no)) return fontCm.get(no); const o = t.get(no); let r = null; const tu = o ? ref(o.dict, "ToUnicode") : 0; if (tu) { const v = akisVeri(t.get(tu)); if (v) r = cmap(v); } fontCm.set(no, r); return r; };
  const sayfalar = [...t].filter(([, o]) => /\/Type\s*\/Page(?![A-Za-z])/.test(o.dict));
  let tum = "";
  const kaynakBul = (o, d) => { const r = anahtarDeger(o.dict, "Resources"); if (r) return coz(r); const p = ref(o.dict, "Parent"); return p && d < 6 && t.get(p) ? kaynakBul(t.get(p), d + 1) : ""; };
  for (const [, sf] of sayfalar) {
    const kayDict = kaynakBul(sf, 0), fd = coz(anahtarDeger(kayDict, "Font"));
    const adlar = {}; for (const m of fd.matchAll(/\/([^\s\/<>\[\]()]+)\s+(\d+)\s+\d+\s+R/g)) adlar[m[1]] = +m[2];
    const yaziTipi = (ad) => (adlar[ad] ? { cm: cmapAl(adlar[ad]) } : null);
    const c = anahtarDeger(sf.dict, "Contents"); if (!c) continue;
    const nolar = [...c.matchAll(/(\d+)\s+\d+\s+R/g)].map((x) => +x[1]);
    for (const no of nolar) { const v = akisVeri(t.get(no)); if (v) tum += icerikMetni(v, yaziTipi, ogelerCikis) + "\n"; }
  }
  return tum;
}

/* "12.345,67" -> 12345.67 */
const sayiOku = (x) => { const v = Number(String(x).replace(/\./g, "").replace(",", ".")); return Number.isFinite(v) ? v : null; };

/* Tahakkuk fişi metninde "devreden KDV" tutarını arar; bulunan adayları bağlamıyla döner */
function devirBul(metin) {
  const t = String(metin || "").replace(/[\u0000-\u001f]+/g, " ").replace(/\s+/g, " "), adaylar = [];
  const sayi = "(-?\\d{1,3}(?:\\.\\d{3})*,\\d{1,2}|-?\\d+,\\d{1,2}|-?\\d{1,3}(?:\\.\\d{3})+|-?\\d+)";
  const g = (w) => w.split("").map((c) => c + "\\s*").join(""), dev = g("devreden"); /* PDF'de harf aralarına boşluk girebilir */
  const desenler = [
    new RegExp(dev + "\\s*(?:" + g("kdv") + "|" + g("katma") + "\\s*" + g("değer") + "\\s*" + g("vergisi") + ")[^0-9-]{0,90}?" + sayi, "gi"),
    new RegExp(g("döneme") + "\\s*" + dev + "[^0-9-]{0,90}?" + sayi, "gi"),
    new RegExp(dev + "[^0-9-]{0,50}?" + sayi, "gi")
  ];
  for (const re of desenler) { let m; while ((m = re.exec(t))) { const v = sayiOku(m[1]); if (v != null && !adaylar.some((a) => a.konum === m.index)) adaylar.push({ tutar: v, konum: m.index, baglam: t.slice(Math.max(0, m.index - 20), m.index + m[0].length + 20) }); } if (adaylar.length) break; }
  return adaylar;
}

/* Tahakkuk fişi tablosu: "TAHAKKUK EDEN | MAHSUP EDİLEN | ÖDENECEK OLAN" başlıklı satırların tutarları. Devreden KDV = mahsup edilen tutarın tahakkuk edeni aşan kısmı.
 * Satır, öğelerin dikey konumuyla kurulur (PDF'deki yazma sırasından bağımsız); her satırdaki son üç tutar sırasıyla tahakkuk, mahsup, ödenecektir. */
const TUTAR = /^-?\d{1,3}(?:\.\d{3})*,\d{2}$/;
function tahakkukTablo(ogeler) {
  const sirali = ogeler.filter((o) => String(o.s).trim()).sort((a, b) => b.y - a.y || a.x - b.x), satirlar = [];
  for (const o of sirali) { const son = satirlar[satirlar.length - 1]; if (son && Math.abs(son.y - o.y) <= Math.max(2, (o.b || 8) * 0.5)) son.oge.push(o); else satirlar.push({ y: o.y, oge: [o] }); }
  for (const r of satirlar) { r.oge.sort((a, b) => a.x - b.x); r.metin = r.oge.map((o) => o.s).join(" "); }
  const mh = sirali.find((o) => /MAHSUP/i.test(o.s)); if (!mh) return null;
  /* başlık hücreleri dikeyde ortalanmış olabilir: MAHSUP'a yakın başlık sözcüklerinin en alt konumu başlığın sonudur */
  const baslik = sirali.filter((o) => Math.abs(o.y - mh.y) <= 32 && /AHAKKUK|EDEN|MAHSUP|ED[İI]LEN|DENECEK|OLAN|ORAN|VADE/i.test(o.s)), alt = Math.min(...baslik.map((o) => o.y));
  const rows = [];
  for (const r of satirlar) {
    if (r.y >= alt - 1) continue; if (/TOPLAM/i.test(r.metin)) break;
    const tut = r.metin.split(/\s+/).filter((w) => TUTAR.test(w)).map(sayiOku); if (tut.length >= 3) { const [thk, mhs, ode] = tut.slice(-3); rows.push({ tahakkuk: thk, mahsup: mhs, odenecek: ode }); }
  }
  if (!rows.length) return null;
  return { satirlar: rows, devir: Math.round(rows.reduce((t, r) => t + Math.max(0, r.mahsup - r.tahakkuk), 0) * 100) / 100 };
}
/* PDF'ten devreden KDV: önce tahakkuk tablosu, olmazsa "devreden KDV" ifadesi */
function fisDevir(buf) {
  const ogeler = [], metin = pdfMetni(buf, ogeler), tablo = tahakkukTablo(ogeler), adaylar = devirBul(metin);
  if (tablo) return { yontem: "tablo", tutar: tablo.devir, satirlar: tablo.satirlar, adaylar, metin };
  if (adaylar.length) return { yontem: "ifade", tutar: adaylar[0].tutar, satirlar: [], adaylar, metin };
  return { yontem: "", tutar: null, satirlar: [], adaylar, metin };
}

module.exports = { fisDevir, tahakkukTablo, pdfMetni, devirBul, _icerikMetni: icerikMetni, _cmap: cmap };
