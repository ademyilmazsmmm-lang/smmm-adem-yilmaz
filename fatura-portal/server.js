"use strict";
/* Fatura Portalı — bağımlılıksız Node sunucusu.
 * Çalıştır: node server.js   →   http://127.0.0.1:3000
 * Veri: data/kasa.json (uygulama şifresiyle AES-GCM şifreli; GİB şifreleri de içinde). */
const http = require("http");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const gib = require("./gib");
const { Depo, adTemiz, adGecerli } = require("./kasa");

const PORT = Number(process.env.PORT) || 3000;
const HOST = process.env.HOST || "127.0.0.1";
const DIR = process.env.DATA_DIR || path.join(__dirname, "data");
const GUVENLI = process.env.GUVENLI === "1"; // internete açık (sunucu) kipi
const PROXY = process.env.TRUST_PROXY === "1"; // önünde HTTPS vekil sunucu (Caddy, Render vb.) var
const ITER = 250000;
const SURUM = "2026-10-20-58";

const oturumlar = new Map(); // çerez -> { rol, mid, K, M, kullanici, bitis } (anahtarlar yalnız bellekte)
const gibler = new Map(); // mükellef id -> istemci (taslak/sms/imza aynı oturumda)
const gibZaman = new Map();
async function gibBirak(id) {
  clearTimeout(gibZaman.get(id)); gibZaman.delete(id);
  const g = gibler.get(id); gibler.delete(id);
  if (g) await g.cikis().catch(() => {});
}
const gibHepsiniBirak = () => Promise.race([Promise.all([...gibler.keys()].map(gibBirak)), new Promise((ok) => setTimeout(ok, 5000))]);
const denemeler = new Map(); // ip -> { n, bitis }
const istemciIp = (req) => (PROXY && String(req.headers["x-forwarded-for"] || "").split(",")[0].trim()) || req.socket.remoteAddress || "?";
const kilitli = (ip) => { const d = denemeler.get(ip); return d && d.bitis > Date.now() ? Math.ceil((d.bitis - Date.now()) / 1000) : 0; };
function hataSay(ip) {
  const d = denemeler.get(ip) || { n: 0, bitis: 0 };
  d.n++;
  if (d.n >= 5) { d.bitis = Date.now() + Math.min(3600e3, 30e3 * Math.pow(2, d.n - 5)); } // 5. hatadan sonra artan bekleme (en çok 1 saat)
  denemeler.set(ip, d);
}
const sifreMin = GUVENLI ? 12 : 8;

/* Hazır hizmet listesi: etiket açılır listede görünür, ad faturaya yazılır. İstisna/tevkifat bilgisi seçilince fatura tipini de belirler. */
const HAZIR_HIZMET = [
  { id: "ogr10t", etiket: "Öğrenci taşımacılığı %10 tevkifat 5/10", ad: "Öğrenci Taşımacılığı Bedeli", kdv: 10, tev: 5, kod: "614", anah: "öğrenci, ogrenci" },
  { id: "per20t", etiket: "Personel taşımacılığı %20 tevkifat 5/10", ad: "Personel Taşımacılığı Bedeli", kdv: 20, tev: 5, kod: "614", anah: "personel, servis" },
  { id: "ogr10", etiket: "Öğrenci taşımacılığı %10", ad: "Öğrenci Taşımacılığı Bedeli", kdv: 10, tev: 0, kod: "", anah: "" },
  { id: "per20", etiket: "Personel taşımacılığı %20", ad: "Personel Taşımacılığı Bedeli", kdv: 20, tev: 0, kod: "", anah: "" },
  { id: "yuk20t", etiket: "Yük taşımacılığı %20 tevkifatlı", ad: "Yük Taşımacılığı Bedeli", kdv: 20, tev: 2, kod: "624", anah: "yük, yuk, nakliye" },
  { id: "dag20t", etiket: "Dağıtım bedeli %20 tevkifatlı", ad: "Dağıtım Bedeli", kdv: 20, tev: 2, kod: "624", anah: "dağıtım, dagitim" },
  { id: "muh10", etiket: "Muhtelif ürün satışı %10", ad: "Muhtelif Ürün Satışı", kdv: 10, tev: 0, kod: "", anah: "" },
  { id: "muh20", etiket: "Muhtelif ürün satışı %20", ad: "Muhtelif Ürün Satışı", kdv: 20, tev: 0, kod: "", anah: "muhtelif, ürün" },
  { id: "yaz0i", etiket: "Yazılım bedeli %0 istisna (hizmet ihracatı)", ad: "Yazılım Bedeli", kdv: 0, tev: 0, kod: "", istisna: "302", anah: "ihracat" },
  { id: "yaz20", etiket: "Yazılım bedeli %20", ad: "Yazılım Bedeli", kdv: 20, tev: 0, kod: "", anah: "yazılım, yazilim" }
];
const depo = new Depo(DIR, ITER, HAZIR_HIZMET);
const mSifreMin = GUVENLI ? 10 : 8; // mükellef hesaplarının en kısa şifresi
/* Eski cihaz yedeği (v1 tek kasa) biçimi: eskiden alınmış yedekler geri yüklenip çok kullanıcılı yapıya taşınabilsin */
const kasaBicimi = (k) => k && k.v === 1 && k.iter === ITER && ["tuz", "iv", "tag", "veri"].every((a) => typeof k[a] === "string" && k[a].length < 8e6 && /^[A-Za-z0-9+/=]+$/.test(k[a]));

/* GİB şifreleri kasa içinde şifreli durur ve istemciye asla gönderilmez (yalnız "var mı" bilgisi). */
const RESIM = /^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/;
const markaTemiz = (m) => {
  m = m || {};
  const r = (x) => (typeof x === "string" && x.length <= 450000 && RESIM.test(x) ? x : "");
  return { logo: r(m.logo), imza: r(m.imza) }; // ad, unvan ve web sabittir (istemcide)
};
const hizmetTemiz = (arr) => (Array.isArray(arr) ? arr : []).slice(0, 100).map((h, i) => ({
  id: String(h.id || "h" + i).slice(0, 40), etiket: String(h.etiket || "").slice(0, 120), ad: String(h.ad || "").slice(0, 150), kdv: Number(h.kdv) >= 0 ? Number(h.kdv) : 20,
  tev: Math.min(9, Math.max(0, parseInt(h.tev, 10) || 0)), kod: String(h.kod || "").slice(0, 10), istisna: String(h.istisna || "").slice(0, 4), anah: String(h.anah || "").slice(0, 200) }));
const aliciTemiz = (arr) => (Array.isArray(arr) ? arr : []).slice(0, 2000).map((a) => ({ id: String(a.id), ad: String(a.ad || "").slice(0, 150), vkn: String(a.vkn || "").slice(0, 11), adres: String(a.adres || "").slice(0, 250), vd: String(a.vd || "").slice(0, 100) }));
function temizMukellef(o, id) {
  const v = depo.mukellef(o, id).veri;
  return { id, ad: v.ad, vkn: v.vkn, kullanici: v.kullanici, sifreVar: !!v.gibSifre, aliciler: v.aliciler || [], hizmetler: v.hizmetler || [], markaVar: { logo: !!(v.marka && v.marka.logo), imza: !!(v.marka && v.marka.imza) }, // resimler büyük: ayrı uçtan (/api/marka) istenir
    hesapKullanici: o.rol === "ofis" ? depo.hesapKullanicisi(id) : undefined, sonGiris: v.sonGiris || null };
}
const temiz = (o) => ({ rol: o.rol, kullanici: o.kullanici, mukellefler: depo.mukellefIdleri(o).map((id) => temizMukellef(o, id)) });
/* İstemciden gelen güncelleme: ofis tüm mükellefleri, mükellef yalnız kendisini düzenler. Mükellef ekleme/silme ayrı uçlardadır. */
function birlestir(o, g) {
  for (const m of g.mukellefler) {
    const id = String(m.id); if (!depo.yetkili(o, id)) continue;
    const e = depo.mukellef(o, id), v = e.veri, eskiK = v.kullanici, eskiS = v.gibSifre;
    v.ad = String(m.ad || "").slice(0, 150); v.vkn = String(m.vkn || "").slice(0, 11); v.kullanici = String(m.kullanici || "").slice(0, 60);
    if (m.gibSifre) v.gibSifre = String(m.gibSifre);
    v.aliciler = aliciTemiz(m.aliciler); v.hizmetler = hizmetTemiz(m.hizmetler); if (m.marka) v.marka = markaTemiz(m.marka);
    depo.kaydet(id);
    if (v.kullanici !== eskiK || v.gibSifre !== eskiS) gibBirak(id);
  }
}
/* Mükellef etkinlik günlüğü (ofis görür): son 300 işlem */
function gunluk(o, mid, eylem, belge) {
  try { const v = depo.mukellef(o, mid).veri; (v.gunluk = v.gunluk || []).push({ zaman: new Date().toISOString(), kim: o.kullanici, rol: o.rol, eylem, belge: belge || "" }); if (v.gunluk.length > 300) v.gunluk.shift(); depo.kaydet(mid); } catch (e) { /* günlük zorunlu değil */ }
}

/* ---------- http ---------- */
function oku(req, sinir) {
  return new Promise((ok, no) => {
    let b = ""; req.on("data", (c) => { b += c; if (b.length > (sinir || 1e6)) { no(new Error("büyük")); req.destroy(); } });
    req.on("end", () => { try { ok(b ? JSON.parse(b) : {}); } catch (e) { no(new Error("Geçersiz JSON")); } });
  });
}
const GUV = {
  "x-content-type-options": "nosniff", "x-frame-options": "DENY", "referrer-policy": "no-referrer", "cross-origin-opener-policy": "same-origin",
  "content-security-policy": "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://earsivportal.efatura.gov.tr; manifest-src 'self'; worker-src 'self'; font-src 'self' data:; connect-src 'self'; frame-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
  "permissions-policy": "camera=(), microphone=(), geolocation=()"
};
const cevap = (res, kod, nesne, baslik) => { res.writeHead(kod, Object.assign({ "content-type": "application/json; charset=utf-8", "cache-control": "no-store" }, GUV, baslik)); res.end(JSON.stringify(nesne)); };
const cerez = (req) => { const m = /(?:^|;\s*)oturum=([a-f0-9]+)/.exec(req.headers.cookie || ""); return m && m[1]; };
function oturumBul(req) {
  const c = cerez(req), o = c && oturumlar.get(c);
  if (!o) return null;
  if (o.bitis <= Date.now()) { oturumKapat(c); return null; }
  return o;
}
function oturumAc(req, o) {
  const c = crypto.randomBytes(24).toString("hex"); o.bitis = Date.now() + 8 * 3600e3; oturumlar.set(c, o);
  const https = GUVENLI || (PROXY && req.headers["x-forwarded-proto"] === "https");
  return { "set-cookie": `oturum=${c}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800${https ? "; Secure" : ""}` };
}
function oturumKapat(c) { oturumlar.delete(c); depo.temizle(oturumlar.values()); }
setInterval(() => { for (const [c, o] of oturumlar) if (o.bitis <= Date.now()) oturumlar.delete(c); depo.temizle(oturumlar.values()); }, 60e3).unref();
const hataBilgi = (e) => (e && e.message) || "Bilinmeyen hata";
const HATA403 = /yetkiniz yok/;

function istemci(m) {
  if (!gibler.has(m.id)) gibler.set(m.id, gib.istemci(m.kullanici, m.gibSifre));
  /* GİB aynı kullanıcı koduyla tek oturuma izin verir: kullanılmayınca 10 dk sonra oturum bırakılır (portala girmek isteyince çakışmasın) */
  clearTimeout(gibZaman.get(m.id));
  gibZaman.set(m.id, setTimeout(() => gibBirak(m.id), 10 * 60e3).unref());
  return gibler.get(m.id);
}
const bekleyen = new Map(); // taslak kimliği -> geçmiş kaydı taslağı (onaylanınca kalıcı olur)
const TIPLER = ["SATIS", "TEVKIFAT", "IADE", "ISTISNA"]; // Özel Matrah: portal isteği alınınca eklenecek
const ISTISNA_AD = { 301: "Mal ihracatı", 302: "Hizmet ihracatı", 303: "Dış ticaret/ihracat kapsamı teslimler", 304: "Yolcu beraberi eşya", 308: "Transit ve gümrük antrepo taşımacılığı", 311: "Uluslararası taşımacılık", 201: "Diplomatik istisna", 350: "Diğer" };
const PARALAR = ["TRY", "USD", "EUR", "GBP"];
/* İstemciden gelen fatura modelini temizler/doğrular. tam=false ise (yalnız hesap önizlemesi) alıcı/tarih zorunlu değildir. */
function modelTemiz(g, tam) {
  const T = gib.temizMetin;
  const yerel = gib.trBugunStr(); // Türkiye tarihi (sunucu UTC olabilir)
  const tip = String(g.tip || "SATIS");
  if (!TIPLER.includes(tip)) throw new Error("Bu fatura tipi henüz desteklenmiyor (Satış, Tevkifat, İade, İstisna).");
  const para = String(g.para || "TRY");
  if (!PARALAR.includes(para)) throw new Error("Para birimi desteklenmiyor.");
  const kur = Number(g.kur);
  if (para !== "TRY" && !(kur > 0)) throw new Error("Döviz kuru (TL karşılığı) girin.");
  const alici = { unvan: T(g.aliciUnvan, 150), vkn: String(g.aliciVkn || ""), adres: T(g.aliciAdres, 250), vd: T(g.vergiDairesi, 100) };
  let tarih = String(g.tarih || "");
  if (tam) {
    if (!alici.unvan || !/^\d{10,11}$/.test(alici.vkn)) throw new Error("Alıcı unvanı ve 10/11 haneli VKN/TCKN gerekli.");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(tarih)) tarih = yerel;
    if (tarih > yerel) throw new Error("Fatura tarihi bugünden ileri olamaz.");
  }
  let iade = null;
  if (tip === "IADE") {
    const no = T(g.iadeNo, 30), it = String(g.iadeTarih || "");
    if (tam) {
      if (!no) throw new Error("İade edilen faturanın numarasını yazın (örn. GIB2026000000023).");
      if (!/^\d{4}-\d{2}-\d{2}$/.test(it)) throw new Error("İade edilen faturanın düzenlenme tarihini seçin.");
      if (it > tarih) throw new Error("İade edilen faturanın tarihi, iade faturasının tarihinden sonra olamaz.");
    }
    iade = { no, tarih: it };
  }
  if (!Array.isArray(g.kalemler) || !g.kalemler.length || g.kalemler.length > 30) throw new Error("1–30 mal/hizmet satırı gerekli.");
  const kalemler = g.kalemler.map((k, i) => {
    const q = { ad: T(k.ad, 150), aciklama: T(k.aciklama, 150), miktar: Number(k.miktar), birim: /^[A-Z0-9]{2,4}$/.test(String(k.birim)) ? String(k.birim) : "C62",
      fiyat: Number(k.fiyat), kdv: Number(k.kdv), tev: tip === "TEVKIFAT" ? Math.min(9, Math.max(0, parseInt(k.tev, 10) || 0)) : 0, kod: T(k.kod, 10), istisna: tip === "ISTISNA" ? String(k.istisna || "") : "" };
    if (tip === "ISTISNA") { q.kdv = 0; if (tam && !ISTISNA_AD[q.istisna]) throw new Error((i + 1) + ". satırda KDV istisna sebebini seçin."); }
    if (tam && !q.ad) throw new Error((i + 1) + ". satırda mal/hizmet adı boş.");
    if (tip === "TEVKIFAT" && tam && (!(q.tev > 0) || !q.kod)) throw new Error((i + 1) + ". satırda tevkifat oranı ve kodu gerekli (tevkifatsız kesmek için fatura tipini “Satış” yapın).");
    return q;
  });
  const m = { alici, tip, para, kur: para === "TRY" ? 0 : kur, kdvDahil: !!g.kdvDahil, tarih, iade, kalemler, notEk: T(g.notEk, 300), notIrsaliye: g.notIrsaliye !== false };
  m._h = gib.hesaplaFatura(m);
  if (tam && !(m._h.toplam.odenecek > 0)) throw new Error("Ödenecek tutar sıfırdan büyük olmalı.");
  m.not = gib.notUret(m, m._h.toplam);
  if (tip === "ISTISNA") { const sb = [...new Set(kalemler.map((k) => k.istisna).filter(Boolean))].map((c) => c + " - " + (ISTISNA_AD[c] || "")); if (sb.length) m.not = ("KDV istisnası: " + sb.join("; ") + "\n" + m.not).trim(); }
  return m;
}

/* Giriş denemesi kısıtı: IP + kullanıcı adı başına (5. hatadan sonra artan bekleme) */
const kisitBekle = (ip, ad) => Math.max(kilitli(ip), ad ? kilitli("u:" + ad) : 0);
const kisitHata = (ip, ad) => { hataSay(ip); if (ad) hataSay("u:" + ad); };
const kisitTemizle = (ip, ad) => { denemeler.delete(ip); if (ad) denemeler.delete("u:" + ad); };
const SIFRE_HATA = "Kullanıcı adı ya da şifre yanlış.";
function sifreKontrol(sifre, min) { if (!sifre || String(sifre).length < min) throw new Error("Şifre en az " + min + " karakter olmalı."); }
const ofisGerek = (o) => { if (!o || o.rol !== "ofis") throw new Error("Bu işlem için yetkiniz yok (yalnız ofis hesabı)."); };
async function oturumBaslat(req, res, o, ip, ad) {
  kisitTemizle(ip, ad);
  if (o.rol === "mukellef") { const e = depo.mukellef(o, o.mid); e.veri.sonGiris = new Date().toISOString(); depo.kaydet(o.mid); }
  return cevap(res, 200, { ok: true }, oturumAc(req, o));
}

async function api(req, res, yol) {
  if (req.method !== "GET" && !/application\/json/.test(req.headers["content-type"] || "")) return cevap(res, 415, { hata: "JSON bekleniyor." });
  const o = oturumBul(req);
  if (yol === "/api/durum") return cevap(res, 200, { kurulu: depo.kurulu, eski: depo.eskiVar, giris: !!o, rol: o && o.rol, kullanici: o && o.kullanici, sahte: gib.MOCK, surum: SURUM, sifreMin, mSifreMin });
  if (yol === "/api/kurulum" && req.method === "POST") {
    if (depo.kurulu || depo.eskiVar) return cevap(res, 409, { hata: "Zaten kurulu." });
    const { kullanici, sifre } = await oku(req), ad = adTemiz(kullanici);
    if (!adGecerli(ad)) return cevap(res, 400, { hata: "Kullanıcı adı 3-32 karakter olmalı (harf, rakam, nokta, tire, alt çizgi)." });
    try { sifreKontrol(sifre, sifreMin); } catch (e) { return cevap(res, 400, { hata: e.message }); }
    return oturumBaslat(req, res, await depo.ofisOlustur(ad, String(sifre)), istemciIp(req), ad);
  }
  if (yol === "/api/geriyukle" && req.method === "POST") {
    if (depo.kurulu) return cevap(res, 409, { hata: "Sunucuda kayıt zaten var." });
    const ip = istemciIp(req), g = await oku(req, 40e6), ad = adTemiz(g.kullanici), bek = kisitBekle(ip, ad);
    if (bek) return cevap(res, 429, { hata: "Çok fazla yanlış deneme; " + bek + " saniye sonra tekrar deneyin." });
    try {
      let ofis;
      if (g.paket) ofis = await depo.paketYukle(g.paket, ad, String(g.sifre || ""));
      else if (g.kasa) { // eski (v1) cihaz yedeği: yazılır, sonra çok kullanıcılı yapıya taşınır
        if (!kasaBicimi(g.kasa)) throw new Error("Yedek biçimi geçersiz.");
        const yazildi = !depo.eskiVar; if (yazildi) depo.yazDosya(depo.eski, g.kasa);
        try { ofis = await depo.eskiyiTasi(ad, String(g.sifre || "")); } catch (e) { if (yazildi) try { fs.unlinkSync(depo.eski); } catch (x) { /* yok */ } throw e; }
      } else throw new Error("Yedek biçimi geçersiz.");
      return oturumBaslat(req, res, ofis, ip, ad);
    } catch (e) { if (/biçimi|3-32/.test(e.message)) return cevap(res, 400, { hata: e.message }); kisitHata(ip, ad); return cevap(res, 401, { hata: "Şifre yanlış ya da yedek bozuk." }); }
  }
  if (yol === "/api/giris" && req.method === "POST") {
    const ip = istemciIp(req), { kullanici, sifre } = await oku(req), ad = adTemiz(kullanici), bek = kisitBekle(ip, ad);
    if (bek) return cevap(res, 429, { hata: "Çok fazla yanlış deneme; " + bek + " saniye sonra tekrar deneyin." });
    try {
      const yeni = depo.eskiVar ? await depo.eskiyiTasi(ad, String(sifre || "")) : await depo.giris(ad, String(sifre || ""));
      return oturumBaslat(req, res, yeni, ip, ad);
    } catch (e) { if (/3-32/.test(e.message)) return cevap(res, 400, { hata: e.message }); kisitHata(ip, ad); return cevap(res, 401, { hata: SIFRE_HATA }); }
  }
  if (!o) return cevap(res, 401, { hata: "Giriş gerekli." });
  if (yol === "/api/cikis") {
    const ids = depo.mukellefIdleri(o); oturumKapat(cerez(req));
    await Promise.race([Promise.all(ids.map(gibBirak)), new Promise((ok) => setTimeout(ok, 5000))]);
    return cevap(res, 200, { ok: true });
  }
  if (yol === "/api/kasa" && req.method === "GET") { ofisGerek(o); return cevap(res, 200, { paket: depo.paket(o), zaman: new Date().toISOString() }); }
  if (yol === "/api/yedek" && req.method === "GET") {
    ofisGerek(o);
    res.writeHead(200, Object.assign({ "content-type": "application/json", "content-disposition": "attachment; filename=fatura-yedek-" + new Date().toISOString().slice(0, 10) + ".json", "cache-control": "no-store" }, GUV));
    return res.end(JSON.stringify(depo.paket(o)));
  }
  if (yol === "/api/veri" && req.method === "GET") return cevap(res, 200, temiz(o));
  if (yol === "/api/veri" && req.method === "PUT") { const g = await oku(req, 8e6); if (!Array.isArray(g.mukellefler)) return cevap(res, 400, { hata: "Geçersiz veri." }); birlestir(o, g); return cevap(res, 200, temiz(o)); }
  if (yol.startsWith("/api/marka") && req.method === "GET") {
    const mid = o.rol === "mukellef" ? o.mid : decodeURIComponent((req.url.split("mid=")[1] || "").split("&")[0]);
    if (!depo.yetkili(o, mid)) return cevap(res, 403, { hata: "Bu mükellef için yetkiniz yok." });
    const mr = depo.mukellef(o, mid).veri.marka || {}; return cevap(res, 200, { logo: mr.logo || "", imza: mr.imza || "" });
  }
  if (yol === "/api/sifre" && req.method === "POST") {
    const { eski, yeni } = await oku(req); sifreKontrol(yeni, o.rol === "ofis" ? sifreMin : mSifreMin);
    const ip = istemciIp(req), kb = "s:" + o.kullanici; if (kilitli(kb)) return cevap(res, 429, { hata: "Çok fazla yanlış deneme; biraz bekleyin." });
    try { await depo.sifreDegistir(o, String(eski || ""), String(yeni)); denemeler.delete(kb); } catch (e) { hataSay(kb); return cevap(res, 401, { hata: "Mevcut şifre yanlış." }); }
    return cevap(res, 200, { ok: true });
  }
  /* ---- ofis: mükellef ve hesap yönetimi ---- */
  if (yol === "/api/mukellef/ekle" && req.method === "POST") {
    ofisGerek(o); const g = await oku(req);
    if (!String(g.ad || "").trim()) return cevap(res, 400, { hata: "Mükellef unvanını yazın." });
    const hk = String(g.hesapKullanici || "").trim();
    if (hk) { const ad = adTemiz(hk); if (!adGecerli(ad)) return cevap(res, 400, { hata: "Giriş kullanıcı adı 3-32 karakter olmalı (harf, rakam, nokta, tire, alt çizgi)." }); if (!depo.adMusait(ad)) return cevap(res, 400, { hata: "Bu kullanıcı adı kullanılıyor." }); sifreKontrol(g.hesapSifre, mSifreMin); }
    const id = await depo.mukellefEkle(o, g);
    if (hk) await depo.hesapAyarla(o, id, hk, String(g.hesapSifre));
    gunluk(o, id, "Mükellef eklendi");
    return cevap(res, 200, { id, veri: temiz(o) });
  }
  if (yol === "/api/hesap" && req.method === "POST") {
    ofisGerek(o); const g = await oku(req), mid = String(g.mid || "");
    if (g.sifre) sifreKontrol(g.sifre, mSifreMin);
    const ad = await depo.hesapAyarla(o, mid, g.kullanici, g.sifre ? String(g.sifre) : ""); gunluk(o, mid, g.sifre ? "Giriş şifresi belirlendi/sıfırlandı" : "Giriş kullanıcı adı değişti");
    return cevap(res, 200, { kullanici: ad });
  }
  if (yol === "/api/hesap/kaldir" && req.method === "POST") { ofisGerek(o); const g = await oku(req); depo.hesapKaldir(o, String(g.mid || "")); for (const [c, x] of oturumlar) if (x.rol === "mukellef" && x.mid === g.mid) oturumKapat(c); gunluk(o, String(g.mid), "Giriş hesabı kaldırıldı"); return cevap(res, 200, { ok: true }); }
  if (yol === "/api/mukellef/sil" && req.method === "POST") {
    ofisGerek(o); const g = await oku(req), mid = String(g.mid || "");
    await gibBirak(mid); for (const [c, x] of oturumlar) if (x.rol === "mukellef" && x.mid === mid) oturumlar.delete(c);
    for (const [u, k] of bekleyen) if (k.mukellefId === mid) bekleyen.delete(u);
    depo.mukellefSil(o, mid); depo.temizle(oturumlar.values());
    return cevap(res, 200, { veri: temiz(o) });
  }
  if (yol.startsWith("/api/etkinlik") && req.method === "GET") {
    ofisGerek(o); const mid = decodeURIComponent((req.url.split("mid=")[1] || "").split("&")[0]);
    return cevap(res, 200, { gunluk: (depo.mukellef(o, mid).veri.gunluk || []).slice().reverse().slice(0, 100) });
  }
  if (yol === "/api/hesapla" && req.method === "POST") {
    const g = await oku(req), m = modelTemiz(g, false);
    return cevap(res, 200, { satirlar: m._h.satirlar, toplam: m._h.toplam, not: m.not });
  }
  if (yol === "/api/gecmis" && req.method === "GET") {
    const hepsi = []; for (const id of depo.mukellefIdleri(o)) hepsi.push(...(depo.mukellef(o, id).veri.gecmis || []));
    return cevap(res, 200, { kayitlar: hepsi.sort((a, b) => String(a.zaman).localeCompare(String(b.zaman))).reverse().slice(0, 1000) });
  }

  /* ---- mükellef işlemleri (GİB): mükellef hesabı yalnız kendi kasasında çalışır ---- */
  const g = await oku(req), mid = o.rol === "mukellef" ? o.mid : String(g.mukellefId || "");
  if (!mid || !depo.yetkili(o, mid)) return cevap(res, 400, { hata: "Mükellef seçin." });
  const m = depo.mukellef(o, mid).veri;
  if (!m.kullanici || (!m.gibSifre && !gib.MOCK)) return cevap(res, 400, { hata: "Bu mükellef için GİB kullanıcı kodu/şifresi girilmemiş (Ayarlar)." });
  if (yol === "/api/taslak") {
    const x = modelTemiz(g, true), uuid = crypto.randomUUID();
    const r = await istemci(m).taslak((v) => gib.faturaGovdesi(x, uuid, v));
    const satirlar = x.kalemler.map((k, i) => Object.assign({}, k, { matrah: x._h.satirlar[i].matrah, kdvTutar: x._h.satirlar[i].kdv, tevKdv: x._h.satirlar[i].tevKdv }));
    const kayit = {
      id: r.uuid, zaman: new Date().toISOString(), mukellefId: m.id, mukellef: { ad: m.ad, vkn: m.vkn }, belgeNo: (r.satir && r.satir.belgeNumarasi) || "",
      aliciUnvan: x.alici.unvan, aliciVkn: x.alici.vkn, aliciAdres: x.alici.adres, vergiDairesi: x.alici.vd, tarih: x.tarih, tip: x.tip, para: x.para, kur: x.kur,
      kalemler: satirlar, hesap: x._h.toplam, not: x.not, durum: "Taslak", iade: x.iade, olusturan: o.kullanici,
      form: { alici: x.alici, tip: x.tip, para: x.para, kur: x.kur, dahil: x.kdvDahil, iade: x.iade, kalemler: x.kalemler, notEk: x.notEk, notIrsaliye: x.notIrsaliye } // "Tekrarla" için
    };
    bekleyen.set(r.uuid, kayit); gunluk(o, mid, "Taslak oluşturuldu", kayit.belgeNo + " · " + kayit.aliciUnvan);
    return cevap(res, 200, { uuid: r.uuid, mesaj: r.mesaj, hesap: x._h.toplam, kayit });
  }
  if (yol === "/api/sms") return cevap(res, 200, await istemci(m).smsGonder());
  if (yol === "/api/imzala") {
    if (!g.uuid || !/^[A-Za-z0-9]{4,12}$/.test(String(g.kod || "").trim())) return cevap(res, 400, { hata: "SMS kodunu yazın." });
    const r = await istemci(m).imzala(g.uuid, String(g.kod).trim(), g.oid, g.tarih);
    const kayit = bekleyen.get(g.uuid) && bekleyen.get(g.uuid).mukellefId === m.id ? bekleyen.get(g.uuid) : null;
    if (kayit) { kayit.durum = "Onaylandı"; kayit.onayZamani = new Date().toISOString(); m.gecmis.push(kayit); if (m.gecmis.length > 2000) m.gecmis.shift(); bekleyen.delete(g.uuid); depo.kaydet(mid); }
    gunluk(o, mid, "Fatura onaylandı", (kayit && kayit.belgeNo) || g.uuid);
    return cevap(res, 200, { mesaj: r.mesaj, kayit: kayit || null });
  }
  if (yol === "/api/sil" || yol === "/api/iptal") {
    const sil = yol === "/api/sil", neden = gib.temizMetin(g.neden, 200);
    if (!g.uuid || !/^[A-Za-z0-9:_=.-]{8,4000}$/.test(String(g.uuid))) return cevap(res, 400, { hata: "Belge seçilmedi." });
    if (!neden) return cevap(res, 400, { hata: (sil ? "Silme" : "İptal") + " nedenini yazın." });
    const r = await (sil ? istemci(m).sil(g.uuid, neden, g.tarih) : istemci(m).iptal(g.uuid, neden, g.tarih));
    bekleyen.delete(g.uuid);
    const k = (m.gecmis || []).filter((x) => x.id === g.uuid)[0];
    if (k && !sil) { k.durum = "İptal talebi"; k.iptalNedeni = neden; k.iptalZamani = new Date().toISOString(); depo.kaydet(mid); }
    gunluk(o, mid, sil ? "Taslak silindi" : "İptal talebi gönderildi", (k && k.belgeNo) || g.uuid);
    return cevap(res, 200, { mesaj: r.mesaj, durum: r.durum });
  }
  if (yol === "/api/sorgu") {
    if (!/^\d{10,11}$/.test(String(g.vkn || ""))) return cevap(res, 400, { hata: "10 ya da 11 haneli VKN/TCKN girin." });
    return cevap(res, 200, await istemci(m).sorgula(String(g.vkn)));
  }
  if (yol === "/api/liste") {
    const t = (d) => { const q = /^(\d{4})-(\d{2})-(\d{2})$/.exec(d || ""); if (!q) throw new Error("Tarih seçin."); return `${q[3]}/${q[2]}/${q[1]}`; };
    const liste = await istemci(m).listeAralik(t(g.bas), t(g.bit));
    for (const b of liste) { const k = bekleyen.get(b.ettn) || (m.gecmis || []).filter((x) => x.id === b.ettn)[0]; if (k && k.hesap && k.mukellefId === m.id) b.tutar = k.hesap.odenecek; } // tutar GİB listesinde yok; bu programdan açılanlar için bilinir
    return cevap(res, 200, { belgeler: liste });
  }
  if (yol === "/api/fatura-veri") {
    if (!/^[A-Za-z0-9:_=.-]{8,4000}$/.test(String(g.uuid || ""))) return cevap(res, 400, { hata: "Fatura seçilmedi." });
    return cevap(res, 200, await istemci(m).faturaVerisi(g.uuid, g.onay));
  }
  if (yol === "/api/gorunum") {
    if (!/^[A-Za-z0-9:_=.-]{8,4000}$/.test(String(g.uuid || ""))) return cevap(res, 400, { hata: "Fatura seçilmedi." });
    return cevap(res, 200, { html: await istemci(m).faturaHtml(g.uuid, g.onay) });
  }
  cevap(res, 404, { hata: "Bulunamadı." });
}

const SAYFA = path.join(__dirname, "public", "index.html");
http.createServer((req, res) => {
  const yol = req.url.split("?")[0];
  if (yol.startsWith("/api/")) return api(req, res, yol).catch((e) => { console.error(e.message); cevap(res, HATA403.test(e.message) ? 403 : 500, { hata: hataBilgi(e) }); });
  const STATIK = { "/manifest.webmanifest": "application/manifest+json", "/sw.js": "text/javascript; charset=utf-8", "/html2canvas.min.js": "text/javascript; charset=utf-8", "/ikon.svg": "image/svg+xml", "/ikon-180.png": "image/png", "/ikon-192.png": "image/png", "/ikon-512.png": "image/png" };
  /* iPhone/iPad: COOP başlığı gönderilmez (ana ekran uygulamasında güvenlik başlığı sorunlarından kaçınmak için). */
  const ios = /iPhone|iPad|iPod/.test(req.headers["user-agent"] || "");
  if (ios) { const yaz = res.writeHead.bind(res); res.writeHead = (k, h) => { if (h && !Array.isArray(h)) delete h["cross-origin-opener-policy"]; return yaz(k, h); }; }
  /* iPhone (iOS 18) tam ekran ana ekran kipinde yazı alanları çalışmadı: varsayılan olarak kısayol Safari'de açılır. Denemek için adresin sonuna ?tam=1 eklenir. */
  const tam = ios && /[?&]tam=1\b/.test(req.url);
  if (yol === "/manifest.webmanifest" && ios) {
    let m = fs.readFileSync(path.join(__dirname, "public", yol), "utf8");
    m = tam ? m.replace('"start_url": "/"', '"start_url": "/?tam=1"') : m.replace('"display": "standalone"', '"display": "browser"');
    res.writeHead(200, Object.assign({ "content-type": STATIK[yol], "cache-control": "no-cache", vary: "User-Agent" }, GUV)); return res.end(m);
  }
  if (yol === "/manifest.webmanifest") { res.writeHead(200, Object.assign({ "content-type": STATIK[yol], "cache-control": "no-cache", vary: "User-Agent" }, GUV)); return fs.createReadStream(path.join(__dirname, "public", yol)).pipe(res); } // iOS'a giden "browser" sürümüyle karışmasın
  if (STATIK[yol]) { res.writeHead(200, Object.assign({ "content-type": STATIK[yol], "cache-control": yol === "/sw.js" ? "no-cache" : "public, max-age=86400" }, GUV)); return fs.createReadStream(path.join(__dirname, "public", yol)).pipe(res); }
  if (yol === "/" || yol === "/index.html") { let h = fs.readFileSync(SAYFA, "utf8");
    if (ios && !tam) h = h.replace(/<meta name="(apple-)?mobile-web-app-capable"[^>]*>\n?/g, "");
    if (tam) h = h.replace('href="/manifest.webmanifest"', 'href="/manifest.webmanifest?tam=1"');
    res.writeHead(200, Object.assign({ "content-type": "text/html; charset=utf-8", "cache-control": "no-store", vary: "User-Agent" }, GUV)); return res.end(h); }
  res.writeHead(404); res.end("Bulunamadı");
}).on("error", (e) => { console.error(e.code === "EADDRINUSE" ? "HATA: " + PORT + " numaralı kapı dolu; eski program hâlâ çalışıyor. Eski siyah pencereyi kapatın ve yeniden başlatın." : e.message); process.exit(1); }).listen(PORT, HOST, () => console.log(`Fatura Portalı ${SURUM}: http://${HOST}:${PORT}` + (gib.MOCK ? "  (SAHTE GİB — gerçek fatura kesilmez)" : "")));
