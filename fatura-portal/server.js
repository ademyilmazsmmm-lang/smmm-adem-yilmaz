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
const { Yansi } = require("./yansi");
const ivd = require("./ivd");
const posta = require("./mail");
const sgk = require("./sgk");

const PORT = Number(process.env.PORT) || 3000;
const HOST = process.env.HOST || "127.0.0.1";
const DIR = process.env.DATA_DIR || path.join(__dirname, "data");
const GUVENLI = process.env.GUVENLI === "1"; // internete açık (sunucu) kipi
const PROXY = process.env.TRUST_PROXY === "1"; // önünde HTTPS vekil sunucu (Caddy, Render vb.) var
const ITER = 250000;
const SURUM = "2026-10-31-154";

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
const sifreMin = 4; /* kısa şifre kabul edilir (ofis tercihi); giriş denemesi sınırı ve kasa şifrelemesi aynen sürer */

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
/* İsteğe bağlı GitHub yansısı (kalıcı diski olmayan kurulumlar için): şifreli dosyalar özel bir depoda tutulur, yerel veri yoksa oradan geri yüklenir */
let yansi = null;
if (process.env.GITHUB_DEPO && process.env.GITHUB_TOKEN) {
  yansi = new Yansi({ depo: process.env.GITHUB_DEPO, token: process.env.GITHUB_TOKEN, dal: process.env.GITHUB_DAL, dir: DIR, api: process.env.GITHUB_API, bekleme: process.env.GITHUB_BEKLEME ? Number(process.env.GITHUB_BEKLEME) : undefined });
  depo.yansi = yansi;
  yansi.baslat(() => fs.existsSync(depo.sf) || fs.existsSync(depo.eski), () => depo.yukleSistem());
  for (const sinyal of ["SIGTERM", "SIGINT"]) process.on(sinyal, () => { yansi.kapat(20000).then(() => process.exit(0), () => process.exit(0)); });
}
const mSifreMin = 4; // mükellef hesaplarının en kısa şifresi
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
const aliciTemiz = (arr) => (Array.isArray(arr) ? arr : []).slice(0, 2000).map((a) => ({ id: String(a.id), ad: String(a.ad || "").slice(0, 150), vkn: String(a.vkn || "").slice(0, 11), adres: String(a.adres || "").slice(0, 250), vd: String(a.vd || "").slice(0, 100), eposta: posta.EPOSTA.test(String(a.eposta || "").trim()) ? String(a.eposta).trim().slice(0, 120) : "" }));
/* Mükellef profili: yalnız program içinde (yerel fatura kopyası, iletişim bilgisi) kullanılır; GİB'deki resmî satıcı bilgisini değiştirmez */
const profilTemiz = (p) => {
  p = p && typeof p === "object" ? p : {};
  const k = (x, n) => String(x == null ? "" : x).replace(/[\u0000-\u001f<>]/g, " ").replace(/\s+/g, " ").trim().slice(0, n);
  const mail = k(p.eposta, 120), tel = k(p.tel, 30).replace(/[^\d+()\-\s]/g, "");
  return { vd: k(p.vd, 100), adres: k(p.adres, 250), tel, eposta: /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(mail) ? mail : "", web: k(p.web, 120) };
};
/* Aydınlatma / onay metni sürümü: public/index.html'deki #kabul metni değişirse bu sayı da artırılır (mükelleflerden yeniden onay istenir) */
const KABUL_SURUM = "1";
/* Belgelerim: ofis yükler, mükellef görür/indirir (fatura-fiş yüklemesi bilerek yok) */
const BELGE_TURLERI = ["İmza sirküleri", "Ticaret sicil gazetesi", "Faaliyet belgesi", "Vergi levhası", "Sözleşme", "Kimlik / vekâletname", "Diğer"];
const BELGE_TIPLERI = [["pdf", "application/pdf", (b) => b.slice(0, 4).toString() === "%PDF"], ["jpg", "image/jpeg", (b) => b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff], ["png", "image/png", (b) => b.slice(0, 4).toString("hex") === "89504e47"],
  ["docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", (b) => b[0] === 0x50 && b[1] === 0x4b], ["xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", (b) => b[0] === 0x50 && b[1] === 0x4b],
  ["doc", "application/msword", (b) => b.slice(0, 4).toString("hex") === "d0cf11e0"], ["xls", "application/vnd.ms-excel", (b) => b.slice(0, 4).toString("hex") === "d0cf11e0"]];
const TALEP_TURLERI = ["Vergi levhası lazım", "Belge / yazı lazım", "Çalışan giriş-çıkış", "Fatura ile ilgili", "Beyanname sorusu", "Diğer"];
const OFIS_EPOSTA = String(process.env.OFIS_EPOSTA || "").trim();
const ISVEREN_SAYFALAR = new Set(["DonemBorcGoruntuleme", "CariDonemBorc", "Mufredat", "IAIIBYEB", "IAIOTGBYEB", "IAIOTIBYEB", "IAKBYEB", "IATBYEB", "IAHBYEB", "IASBYEB", "IAKGFBYEB", "IAKU", "TesvikPotansiyel"]);
function temizMukellef(o, id) {
  const v = depo.mukellef(o, id).veri;
  return { id, ad: v.ad, vkn: v.vkn, kullanici: v.kullanici, sifreVar: !!v.gibSifre, earsiv: v.earsiv !== false, sgk: { ad: (v.sgk && v.sgk.ad) || "", kullanici: (v.sgk && v.sgk.kullanici) || "", isyeriKod: (v.sgk && v.sgk.isyeriKod) || "", sistemVar: !!(v.sgk && v.sgk.sistemSifre), isyeriVar: !!(v.sgk && v.sgk.isyeriSifre) }, sgkEk: (v.sgkEk || []).map((x) => ({ id: x.id, ad: x.ad || "", kullanici: x.kullanici || "", isyeriKod: x.isyeriKod || "", sistemVar: !!x.sistemSifre, isyeriVar: !!x.isyeriSifre })), profil: v.profil || {}, kabul: o.rol === "ofis" ? (v.kabul || null) : undefined, kabulGerek: o.rol === "mukellef" && !(v.kabul && v.kabul.surum === KABUL_SURUM), aliciler: v.aliciler || [], hizmetler: v.hizmetler || [], markaVar: { logo: !!(v.marka && v.marka.logo), imza: !!(v.marka && v.marka.imza) }, // resimler büyük: ayrı uçtan (/api/marka) istenir
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
    if (m.sgk && typeof m.sgk === "object") { // SGK İşveren Sistemi bilgileri (şifreler yalnız yazıldıysa değişir)
      const e0 = v.sgk || {}, y0 = { ad: String(m.sgk.ad == null ? e0.ad || "" : m.sgk.ad).slice(0, 40), kullanici: String(m.sgk.kullanici == null ? e0.kullanici || "" : m.sgk.kullanici).replace(/\D/g, "").slice(0, 11), isyeriKod: String(m.sgk.isyeriKod == null ? e0.isyeriKod || "" : m.sgk.isyeriKod).replace(/\D/g, "").slice(0, 4), sistemSifre: m.sgk.sistemSifre ? String(m.sgk.sistemSifre).slice(0, 20) : e0.sistemSifre || "", isyeriSifre: m.sgk.isyeriSifre ? String(m.sgk.isyeriSifre).slice(0, 20) : e0.isyeriSifre || "" };
      if (JSON.stringify(y0) !== JSON.stringify(e0)) { v.sgk = y0; sgkBirak(id); }
    }
    if (Array.isArray(m.sgkEk)) { // aynı mükellefin ek SGK işyeri dosyaları (ofis, imalathane vb.); en çok 3; şifreler yalnız yazıldıysa değişir
      const eski = new Map((v.sgkEk || []).map((x) => [x.id, x])), yeni = [];
      for (const x of m.sgkEk.slice(0, 3)) {
        if (!x || typeof x !== "object") continue; const e1 = eski.get(String(x.id)) || {};
        yeni.push({ id: e1.id || crypto.randomBytes(4).toString("hex"), ad: String(x.ad == null ? e1.ad || "" : x.ad).slice(0, 40), kullanici: String(x.kullanici == null ? e1.kullanici || "" : x.kullanici).replace(/\D/g, "").slice(0, 11), isyeriKod: String(x.isyeriKod == null ? e1.isyeriKod || "" : x.isyeriKod).replace(/\D/g, "").slice(0, 4), sistemSifre: x.sistemSifre ? String(x.sistemSifre).slice(0, 20) : e1.sistemSifre || "", isyeriSifre: x.isyeriSifre ? String(x.isyeriSifre).slice(0, 20) : e1.isyeriSifre || "" });
      }
      if (JSON.stringify(yeni) !== JSON.stringify(v.sgkEk || [])) { v.sgkEk = yeni; sgkBirak(id); }
    }
    if (o.rol !== "mukellef" && typeof m.earsiv === "boolean") v.earsiv = m.earsiv; // e-Arşiv kullanmayan mükellef yalnız Vergi Dairesi bölümünü kullanır
    v.aliciler = aliciTemiz(m.aliciler); v.hizmetler = hizmetTemiz(m.hizmetler); if (m.marka) v.marka = markaTemiz(m.marka); if (m.profil) v.profil = profilTemiz(m.profil);
    depo.kaydet(id);
    if (v.kullanici !== eskiK || v.gibSifre !== eskiS) { gibBirak(id); ivdBirak(id); ivdKilit.delete(id); ivdHata.delete(id); }
  }
}
/* Güncel kira artış oranı: web sitesinin ana sayfasında her ay güncellenen kutudan okunur (6 saat önbellek); okunamazsa kart gösterilmez */
let kiraOnbellek = { zaman: 0, oran: null };
function kiraOkuHtml(html) {
  const ay = /class="kira-oran-ay">\s*([^<]+?)\s*</.exec(html), al = (ad) => { const m = new RegExp(ad + "\\s*</span>\\s*<span class=\"kira-oran-value\">\\s*([^<]+?)\\s*<", "i").exec(html); return m ? m[1] : ""; };
  const konut = al("Konut \\(Ev\\) Kirası"), isyeri = al("İşyeri Kirası");
  return ay && konut && isyeri ? { ay: ay[1], konut, isyeri } : null;
}
async function kiraOrani() {
  if (Date.now() - kiraOnbellek.zaman < 6 * 3600e3) return kiraOnbellek.oran;
  kiraOnbellek.zaman = Date.now() - 5 * 3600e3 + 60e3; // hata olursa bir saat sonra yeniden dene
  try {
    const r = await fetch(process.env.KIRA_KAYNAK || "https://smmmyilmaz.com/", { signal: AbortSignal.timeout(8000), headers: { "user-agent": "fatura-portali" } });
    if (r.ok) { const o = kiraOkuHtml(await r.text()); if (o) kiraOnbellek = { zaman: Date.now(), oran: o }; }
  } catch (e) { /* site okunamadı: eski değer kalır */ }
  return kiraOnbellek.oran;
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

/* GİB aynı kullanıcı koduyla tek oturuma izin verir: kullanılmayınca kısa süre sonra oturum bırakılır (mükellef portala girmek isteyince "başka yerde açık" demesin).
 * Normalde 3 dk (GIB_BOSTA_DK ile değişir); SMS kodu beklenirken 8 dk; iş bitince (onay/iptal/silme) 45 sn. */
const GIB_BOSTA = (Number(process.env.GIB_BOSTA_DK) > 0 ? Number(process.env.GIB_BOSTA_DK) : 3) * 60e3;
function gibKisalt(id, ms) { clearTimeout(gibZaman.get(id)); gibZaman.set(id, setTimeout(() => gibBirak(id), ms).unref()); }
function istemci(m, ms) {
  if (!gibler.has(m.id)) gibler.set(m.id, gib.istemci(m.kullanici, m.gibSifre));
  gibKisalt(m.id, ms || GIB_BOSTA);
  return gibler.get(m.id);
}
/* Dijital Vergi Dairesi oturumları (e-Arşiv'den ayrı): her bağlanışta kullanıcı doğrulama kodunu yazar; boşta kısa süre sonra kapatılır.
 * Art arda 3 başarısız girişte kullanıcı kodunu kilitlememek için 10 dk beklenir. */
const ivdler = new Map(), ivdZaman = new Map(), ivdSon = new Map(), ivdKilit = new Map(), ivdHata = new Map();
async function ivdBirak(id) { clearTimeout(ivdZaman.get(id)); ivdZaman.delete(id); const x = ivdler.get(id); ivdler.delete(id); if (x) await x.cikis().catch(() => {}); }
function ivdZamanla(id) { clearTimeout(ivdZaman.get(id)); ivdZaman.set(id, setTimeout(() => ivdBirak(id), 5 * 60e3).unref()); }
function ivdKontrol(m, tur) {
  const kilit = ivdKilit.get(m.id); if (kilit && kilit > Date.now()) throw new Error("Dijital Vergi Dairesi girişi art arda başarısız oldu; kullanıcı kodunun kilitlenmemesi için " + Math.ceil((kilit - Date.now()) / 60e3) + " dakika sonra tekrar deneyin.");
  const an = m.id + ":" + tur, son = ivdSon.get(an) || 0; if (Date.now() - son < 3e3) throw new Error("Çok sık istek: birkaç saniye bekleyin.");
  ivdSon.set(an, Date.now());
}
async function vdSorgu(m, calistir) {
  const x = ivdler.get(m.id);
  if (!x || !x.girildi) { const e = new Error("Önce Dijital Vergi Dairesi'ne bağlanın (doğrulama kodu)."); e.girisGerek = true; throw e; }
  ivdZamanla(m.id);
  try { return await calistir(x); }
  catch (e) { if (e && e.oturum) { await ivdBirak(m.id); e.girisGerek = true; } throw e; }
}
/* SGK İşveren Sistemi oturumları: her bağlanışta kullanıcı güvenlik kodunu yazar; boşta 5 dk sonra kapanır. Yalnız art arda hızlı isteklere 3 sn sınır vardır (kilitleme yok). */
const sgkler = new Map(), sgkZaman = new Map(), sgkSon = new Map();
/* bir mükellefin birden çok SGK işyeri dosyası olabilir: ix 0 = ana kayıt (v.sgk), 1..3 = v.sgkEk[ix-1] */
const sgkIx = (x) => { const n = Number(x); return n >= 1 && n <= 3 ? Math.floor(n) : 0; };
const sgkKayit = (m, ix) => (ix ? (m.sgkEk || [])[ix - 1] : m.sgk) || {};
const sgkAnahtar = (id, sis, ix) => id + ":" + sis + (ix ? ":" + ix : "");
async function sgkBirak(id) { for (const a of [...sgkler.keys()].filter((k) => k.startsWith(id + ":isveren") || k.startsWith(id + ":ebildirge"))) { clearTimeout(sgkZaman.get(a)); sgkZaman.delete(a); const x = sgkler.get(a); sgkler.delete(a); if (x) await x.cikis().catch(() => {}); } }
function sgkZamanla(a) { clearTimeout(sgkZaman.get(a)); sgkZaman.set(a, setTimeout(async () => { sgkZaman.delete(a); const x = sgkler.get(a); sgkler.delete(a); if (x) await x.cikis().catch(() => {}); }, 5 * 60e3).unref()); }
function sgkKontrol(id, tur) {
  const an = id + ":" + tur, son = sgkSon.get(an) || 0; if (Date.now() - son < 3e3) throw new Error("Çok sık istek: birkaç saniye bekleyin."); sgkSon.set(an, Date.now());
}
const yaziSayac = new Map(); // mükellef -> son 24 saatteki borç durum yazısı talepleri
const postaSayac = new Map(); // kullanıcı -> son gönderim zamanları (saatlik sınır)
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
  const alici = { unvan: T(g.aliciUnvan, 150), vkn: String(g.aliciVkn || ""), adres: T(g.aliciAdres, 250), vd: T(g.vergiDairesi, 100), eposta: posta.EPOSTA.test(String(g.aliciEposta || "").trim()) ? String(g.aliciEposta).trim().slice(0, 120) : "" };
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
const personelOlur = (o) => { if (!o || o.rol === "mukellef") throw new Error("Bu işlem için yetkiniz yok (ofis ya da çalışan hesabı)."); }; /* ofis + atanmış mükellefleri için çalışan */
async function oturumBaslat(req, res, o, ip, ad) {
  kisitTemizle(ip, ad);
  if (o.rol === "mukellef") { const e = depo.mukellef(o, o.mid); e.veri.sonGiris = new Date().toISOString(); depo.kaydet(o.mid); }
  return cevap(res, 200, { ok: true }, oturumAc(req, o));
}

async function api(req, res, yol) {
  if (yansi && !yansi.hazir) { /* açılışta GitHub'dan geri yükleme bitmeden hiçbir istek işlenmez (boş başlayıp veriyi ezmemek için) */
    await Promise.race([yansi.hazirSoz, new Promise((r) => setTimeout(r, 25000))]);
    if (!yansi.hazir) return cevap(res, 503, { hata: "Kayıtlı veriler yükleniyor" + (yansi.hata ? " (GitHub deposuna ulaşılamadı: " + yansi.hata + ")" : "") + ". Birkaç saniye sonra yeniden deneyin." });
  }
  if (req.method !== "GET" && !/application\/json/.test(req.headers["content-type"] || "")) return cevap(res, 415, { hata: "JSON bekleniyor." });
  const o = oturumBul(req);
  if (yol === "/api/durum") return cevap(res, 200, { kurulu: depo.kurulu, eski: depo.eskiVar, giris: !!o, rol: o && o.rol, kullanici: o && o.kullanici, sahte: gib.MOCK, surum: SURUM, sifreMin, mSifreMin });
  if (yol === "/api/kabul" && req.method === "POST") {
    if (!o || o.rol !== "mukellef") return cevap(res, 403, { hata: "Bu işlem yalnız mükellef hesabı içindir." });
    const e = depo.mukellef(o, o.mid); e.veri.kabul = { zaman: new Date().toISOString(), surum: KABUL_SURUM }; depo.kaydet(o.mid);
    gunluk(o, o.mid, "Aydınlatma ve onay metni kabul edildi");
    return cevap(res, 200, { ok: true });
  }
  if (yol === "/api/yansi") { ofisGerek(o); return cevap(res, 200, yansi ? yansi.durum : { acik: false }); }
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
    /* çıkışta GİB oturumları da kapatılır; ofis, o sırada kendi hesabıyla girmiş mükellefin (örn. SMS bekleyen) oturumuna dokunmaz */
    const kendi = cerez(req);
    const ids = depo.mukellefIdleri(o).filter((id) => o.rol === "mukellef" || ![...oturumlar].some(([c, x]) => c !== kendi && x.rol === "mukellef" && x.mid === id));
    oturumKapat(kendi);
    await Promise.race([Promise.all(ids.map((id) => Promise.all([gibBirak(id), ivdBirak(id), sgkBirak(id)]))), new Promise((ok) => setTimeout(ok, 5000))]);
    return cevap(res, 200, { ok: true });
  }
  if (yol === "/api/kasa" && req.method === "GET") { ofisGerek(o); return cevap(res, 200, { paket: depo.paket(o), zaman: new Date().toISOString() }); }
  if (yol === "/api/yedek" && req.method === "GET") {
    ofisGerek(o);
    res.writeHead(200, Object.assign({ "content-type": "application/json", "content-disposition": "attachment; filename=fatura-yedek-" + new Date().toISOString().slice(0, 10) + ".json", "cache-control": "no-store" }, GUV));
    return res.end(JSON.stringify(depo.paket(o)));
  }
  if (yol === "/api/yedek/mail" && req.method === "POST") {
    ofisGerek(o);
    if (!posta.hazir()) return cevap(res, 400, { hata: "E-posta gönderimi bu sunucuda henüz kurulmadı." });
    const b = await oku(req), to = String(b.to || "").trim();
    if (!posta.EPOSTA.test(to) || to.length > 120) return cevap(res, 400, { hata: "Geçerli bir e-posta adresi yazın." });
    const sinir = (postaSayac.get(o.kullanici) || []).filter((t) => Date.now() - t < 3600e3); if (sinir.length >= 40) return cevap(res, 429, { hata: "Saatlik e-posta sınırına ulaşıldı (40). Biraz sonra tekrar deneyin." });
    const veri = Buffer.from(JSON.stringify(depo.paket(o))), gun = new Date().toISOString().slice(0, 10);
    if (veri.length > 12e6) return cevap(res, 413, { hata: "Yedek e-posta için çok büyük (" + Math.round(veri.length / 1e6) + " MB); “Tam yedeği indir” ile alın." });
    await posta.gonder({ gonderenAd: "Fatura portalı yedeği", to: [to], cc: [], yanit: "", konu: "Fatura portalı yedeği — " + gun, metin: "Fatura portalının şifreli yedeği ektedir (" + gun + ").\n\nDosya ofis şifrenizle açılır; içinde düz metin parola ya da GİB şifresi yoktur. Yeni bir sunucuya taşımak için kurulum ekranındaki “yedekten geri yükle” seçeneğiyle kullanılır.\nBu dosyayı güvenli bir yerde saklayın.", ek: { ad: "fatura-yedek-" + gun + ".json", tur: "application/json", veri } }, DIR);
    sinir.push(Date.now()); postaSayac.set(o.kullanici, sinir);
    return cevap(res, 200, { tamam: true, to, boyut: veri.length });
  }
  if (yol === "/api/mail/durum" && req.method === "GET") return cevap(res, 200, { hazir: posta.hazir(), saglayici: posta.durum().saglayici, gonderen: o.rol === "ofis" ? posta.durum().gonderen : undefined });
  if (yol === "/api/veri" && req.method === "GET") return cevap(res, 200, temiz(o));
  if (yol === "/api/veri" && req.method === "PUT") { const g = await oku(req, 8e6); if (!Array.isArray(g.mukellefler)) return cevap(res, 400, { hata: "Geçersiz veri." }); birlestir(o, g); return cevap(res, 200, temiz(o)); }
  if (yol === "/api/sgk/form" && req.method === "GET") {
    const q = new URL(req.url, "http://x").searchParams, mid = o.rol === "mukellef" ? o.mid : q.get("mid") || "", an = sgkAnahtar(mid, "isveren", sgkIx(q.get("ix")));
    const duz = (kod, metin) => { res.writeHead(kod, Object.assign({ "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" }, GUV)); res.end(metin); };
    if (!depo.yetkili(o, mid)) return duz(403, "Bu mükellef için yetkiniz yok.");
    const x = sgkler.get(an); if (!x || !x.girdi) return duz(409, "SGK İşveren Sistemi bağlantısı kapalı; güvenlik koduyla yeniden bağlanın.");
    try {
      sgkKontrol(an, "f"); sgkZamanla(an);
      const d = await x.formGonder(Number(q.get("i")));
      gunluk(o, mid, "SGK belgesi açıldı", d.ad);
      res.writeHead(200, Object.assign({}, GUV, { "content-type": d.tur, "content-disposition": "inline; filename*=UTF-8''" + encodeURIComponent(d.ad), "cache-control": "no-store", "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:" }));
      return res.end(d.veri);
    } catch (e) { if (e && e.oturum) { clearTimeout(sgkZaman.get(an)); sgkler.delete(an); } return duz(500, "Belge alınamadı: " + e.message); }
  }
  if (yol === "/api/sgk/belge" && req.method === "GET") {
    const q = new URL(req.url, "http://x").searchParams, mid = o.rol === "mukellef" ? o.mid : q.get("mid") || "";
    const duz = (kod, metin) => { res.writeHead(kod, Object.assign({ "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" }, GUV)); res.end(metin); };
    if (!depo.yetkili(o, mid)) return duz(403, "Bu mükellef için yetkiniz yok.");
    const an = sgkAnahtar(mid, "ebildirge", sgkIx(q.get("ix"))), x = sgkler.get(an); if (!x || !x.girdi) return duz(409, "Önce SGK e-Bildirge'ye bağlanın (SGK sekmesi).");
    try {
      sgkKontrol(an, "b"); sgkZamanla(an);
      const d = await x.bildirgeBelge(Number(q.get("n")), Number(q.get("k")), Number(q.get("j")));
      gunluk(o, mid, "SGK belgesi açıldı", d.ad);
      res.writeHead(200, Object.assign({}, GUV, { "content-type": d.tur, "content-disposition": (d.satir ? "inline" : "attachment") + "; filename*=UTF-8''" + encodeURIComponent(d.ad), "cache-control": "no-store", "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:" }));
      return res.end(d.veri);
    } catch (e) { if (e && e.oturum) { clearTimeout(sgkZaman.get(an)); sgkler.delete(an); } return duz(500, "Belge alınamadı: " + e.message); }
  }
  if ((yol === "/api/vd/belge" || yol === "/api/vd/yazi" || yol === "/api/vd/levha" || yol === "/api/vd/tahakkuk" || yol === "/api/vd/yoklama") && req.method === "GET") {
    const q = new URL(req.url, "http://x").searchParams, mid = o.rol === "mukellef" ? o.mid : q.get("mid") || "";
    const duz = (kod, metin) => { res.writeHead(kod, Object.assign({ "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" }, GUV)); res.end(metin); };
    if (!depo.yetkili(o, mid)) return duz(403, "Bu mükellef için yetkiniz yok.");
    const x = ivdler.get(mid); if (!x || !x.girildi) return duz(409, "Önce Dijital Vergi Dairesi'ne bağlanın (Vergi D. sekmesi).");
    try {
      ivdKontrol({ id: mid }, "b"); ivdZamanla(mid);
      const n = Number(q.get("n")), yazi = yol === "/api/vd/yazi", levha = yol === "/api/vd/levha", thk = yol === "/api/vd/tahakkuk", yok = yol === "/api/vd/yoklama";
      const d = levha ? await x.levhaIndir(n, q.get("dil"), (depo.mukellef(o, mid).veri.vkn || "").replace(/\D/g, "")) : yazi ? await x.yaziIndir(n) : thk ? await x.tahakkukIndir(n) : yok ? await x.yoklamaIndir(n) : await x.belgeIndir(n);
      gunluk(o, mid, levha ? "e-Vergi levhası açıldı" : yazi ? "Borç durum yazısı açıldı" : thk ? "Tahakkuk fişi açıldı" : yok ? "Yoklama fişi açıldı" : "Tebligat belgesi açıldı", d.ad);
      res.writeHead(200, Object.assign({}, GUV, { "content-type": d.tur, "content-disposition": (d.satir ? "inline" : "attachment") + "; filename*=UTF-8''" + encodeURIComponent(d.ad), "cache-control": "no-store", "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:" }));
      return res.end(d.veri);
    } catch (e) { if (e && e.oturum) await ivdBirak(mid); return duz(500, "Belge alınamadı: " + e.message); }
  }
  if (yol.startsWith("/api/marka") && req.method === "GET") {
    const mid = o.rol === "mukellef" ? o.mid : decodeURIComponent((req.url.split("mid=")[1] || "").split("&")[0]);
    if (!depo.yetkili(o, mid)) return cevap(res, 403, { hata: "Bu mükellef için yetkiniz yok." });
    const mr = depo.mukellef(o, mid).veri.marka || {}; return cevap(res, 200, { logo: mr.logo || "", imza: mr.imza || "" });
  }
  if (yol === "/api/sifre" && req.method === "POST") {
    const { eski, yeni } = await oku(req); sifreKontrol(yeni, o.rol === "mukellef" ? mSifreMin : sifreMin);
    const ip = istemciIp(req), kb = "s:" + o.kullanici; if (kilitli(kb)) return cevap(res, 429, { hata: "Çok fazla yanlış deneme; biraz bekleyin." });
    try { await depo.sifreDegistir(o, String(eski || ""), String(yeni)); denemeler.delete(kb); } catch (e) { hataSay(kb); return cevap(res, 401, { hata: "Mevcut şifre yanlış." }); }
    return cevap(res, 200, { ok: true });
  }
  /* ---- ofis: mükellef ve hesap yönetimi ---- */
  if (yol === "/api/personel" && req.method === "GET") { ofisGerek(o); return cevap(res, 200, { personel: depo.personelListe(o) }); }
  if (yol.startsWith("/api/personel/") && req.method === "POST") {
    ofisGerek(o); const g = await oku(req), ne = yol.slice(14);
    if (ne === "ekle") {
      try { sifreKontrol(g.sifre, sifreMin); } catch (e) { return cevap(res, 400, { hata: e.message }); }
      const id = await depo.personelEkle(o, { ad: g.ad, kullanici: g.kullanici, sifre: String(g.sifre) });
      if (Array.isArray(g.mukellefler) && g.mukellefler.length) depo.personelAta(o, id, g.mukellefler);
      gunluk(o, depo.mukellefIdleri(o)[0] || "", "Çalışan hesabı açıldı", ""); return cevap(res, 200, { id, personel: depo.personelListe(o) });
    }
    const pid = String(g.pid || "");
    if (ne === "atama") { depo.personelAta(o, pid, Array.isArray(g.mukellefler) ? g.mukellefler : []); return cevap(res, 200, { personel: depo.personelListe(o) }); }
    if (ne === "sifre") { try { sifreKontrol(g.sifre, sifreMin); } catch (e) { return cevap(res, 400, { hata: e.message }); } await depo.personelSifre(o, pid, String(g.sifre)); for (const [c, x] of oturumlar) if (x.rol === "personel" && x.pid === pid) oturumKapat(c); return cevap(res, 200, { tamam: true }); }
    if (ne === "sil") { depo.personelSil(o, pid); for (const [c, x] of oturumlar) if (x.rol === "personel" && x.pid === pid) oturumKapat(c); return cevap(res, 200, { personel: depo.personelListe(o) }); }
    return cevap(res, 404, { hata: "Bulunamadı." });
  }
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
  if (yol === "/api/mukellef/toplu" && req.method === "POST") {
    /* Excel/CSV'den toplu mükellef: her satır ayrı denenir, sonuç satır satır döner. Şifreler yalnız şifreli kasaya yazılır, günlüğe girmez. */
    ofisGerek(o); const g = await oku(req, 3e6); const satirlar = Array.isArray(g.satirlar) ? g.satirlar.slice(0, 80) : [];
    if (!satirlar.length) return cevap(res, 400, { hata: "Yüklenecek satır yok." });
    const sonuc = [], mevcutVkn = new Set(depo.mukellefIdleri(o).map((id) => String(depo.mukellef(o, id).veri.vkn || "")).filter(Boolean));
    for (let i = 0; i < satirlar.length; i++) {
      const r = satirlar[i] || {}, ad = gib.temizMetin(r.ad, 150), vkn = String(r.vkn || "").replace(/\D/g, "");
      const hata = (mesaj) => sonuc.push({ n: i + 1, ad: ad || "(adsız)", durum: "hata", mesaj });
      if (!ad) { hata("Unvan boş."); continue; }
      if (!/^\d{10,11}$/.test(vkn)) { hata("VKN/TCKN 10 ya da 11 haneli olmalı."); continue; }
      if (mevcutVkn.has(vkn)) { sonuc.push({ n: i + 1, ad, durum: "atlandi", mesaj: "Bu VKN/TCKN ile mükellef zaten kayıtlı." }); continue; }
      const hk = String(r.hesapKullanici || "").trim(), hs = String(r.hesapSifre || "");
      if (hk) { const a2 = adTemiz(hk); if (!adGecerli(a2) || !depo.adMusait(a2)) { hata("Giriş kullanıcı adı geçersiz ya da kullanılıyor."); continue; } if (hs.length < mSifreMin) { hata("Giriş şifresi en az " + mSifreMin + " karakter olmalı."); continue; } }
      try {
        const id = await depo.mukellefEkle(o, { ad, vkn, kullanici: String(r.gibKullanici || "").slice(0, 60), gibSifre: String(r.gibSifre || ""), earsiv: r.earsiv !== false });
        const v = depo.mukellef(o, id).veri, sk = { kullanici: String(r.sgkKullanici || "").replace(/\D/g, "").slice(0, 11), isyeriKod: String(r.sgkIsyeriKod || "").replace(/\D/g, "").slice(0, 4), sistemSifre: String(r.sgkSistemSifre || "").slice(0, 20), isyeriSifre: String(r.sgkIsyeriSifre || "").slice(0, 20) };
        if (sk.kullanici || sk.isyeriKod || sk.sistemSifre || sk.isyeriSifre) v.sgk = sk;
        depo.kaydet(id); mevcutVkn.add(vkn);
        let not = ""; if (hk) { try { await depo.hesapAyarla(o, id, hk, hs); } catch (e) { not = "Giriş hesabı açılamadı: " + e.message; } }
        gunluk(o, id, "Mükellef toplu yüklemeyle eklendi");
        sonuc.push({ n: i + 1, ad, durum: "eklendi", mesaj: not });
      } catch (e) { hata(e.message); }
    }
    return cevap(res, 200, { sonuc, veri: temiz(o) });
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

  if (yol === "/api/kira-orani" && req.method === "GET") return cevap(res, 200, { oran: await kiraOrani() });
  if (yol === "/api/ozet" && req.method === "GET") {
    const mid = o.rol === "mukellef" ? o.mid : new URL(req.url, "http://x").searchParams.get("mid") || "";
    let bekleyenToplam = null; if (o.rol !== "mukellef") { bekleyenToplam = 0; for (const id of depo.mukellefIdleri(o)) bekleyenToplam += (depo.mukellef(o, id).veri.talepler || []).filter((t) => t.durum === "Bekliyor").length; }
    if (!mid) return cevap(res, 200, { son: {}, belge: null, acikTalep: null, bekleyenToplam });
    if (!depo.yetkili(o, mid)) return cevap(res, 400, { hata: "Mükellef seçin." });
    const v = depo.mukellef(o, mid).veri;
    return cevap(res, 200, { son: v.son || {}, belge: depo.belgeListe(o, mid).length, acikTalep: (v.talepler || []).filter((t) => t.durum === "Bekliyor").length, bekleyenToplam });
  }
  if (yol === "/api/belgeler" && req.method === "GET") {
    const mid = o.rol === "mukellef" ? o.mid : new URL(req.url, "http://x").searchParams.get("mid") || "";
    if (!mid || !depo.yetkili(o, mid)) return cevap(res, 400, { hata: "Mükellef seçin." });
    return cevap(res, 200, { belgeler: depo.belgeListe(o, mid), turler: BELGE_TURLERI });
  }
  if (yol === "/api/belge-indir" && req.method === "GET") {
    const q = new URL(req.url, "http://x").searchParams, mid = o.rol === "mukellef" ? o.mid : q.get("mid") || "";
    const duz = (kod, metin) => { res.writeHead(kod, Object.assign({ "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" }, GUV)); res.end(metin); };
    if (!mid || !depo.yetkili(o, mid)) return duz(403, "Bu mükellef için yetkiniz yok.");
    let b; try { b = depo.belgeAl(o, mid, String(q.get("id") || "")); } catch (e) { return duz(404, e.message); }
    gunluk(o, mid, "Belge indirildi", b.tur + " · " + b.ad);
    res.writeHead(200, Object.assign({}, GUV, { "content-type": b.tip, "content-disposition": "attachment; filename*=UTF-8''" + encodeURIComponent(b.ad), "cache-control": "no-store", "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:" }));
    return res.end(Buffer.from(b.veri, "base64"));
  }
  if (yol === "/api/talepler" && req.method === "GET") {
    const hepsi = [];
    for (const id of depo.mukellefIdleri(o)) { const v = depo.mukellef(o, id).veri; for (const t of v.talepler || []) hepsi.push(Object.assign({ mid: id, firma: v.ad }, t)); }
    hepsi.sort((a, b) => (a.durum === "Bekliyor" ? 0 : 1) - (b.durum === "Bekliyor" ? 0 : 1) || String(b.zaman).localeCompare(String(a.zaman)));
    return cevap(res, 200, { talepler: hepsi.slice(0, 300), turler: TALEP_TURLERI });
  }

  /* ---- mükellef işlemleri (GİB): mükellef hesabı yalnız kendi kasasında çalışır ---- */
  const g = await oku(req, yol === "/api/mail" ? 8e6 : yol === "/api/belge" ? 4e6 : undefined), mid = o.rol === "mukellef" ? o.mid : String(g.mukellefId || "");
  if (!mid || !depo.yetkili(o, mid)) return cevap(res, 400, { hata: "Mükellef seçin." });
  const m = depo.mukellef(o, mid).veri;
  if (yol === "/api/belge") {
    personelOlur(o);
    const tur = BELGE_TURLERI.includes(g.tur) ? g.tur : "Diğer", ad = gib.temizMetin(g.ad, 100).replace(/[\\/:*?"<>|]+/g, "_") || "belge";
    const mt = /^data:[^;,]*;base64,([A-Za-z0-9+/=]+)$/.exec(String(g.veri || "")); if (!mt) return cevap(res, 400, { hata: "Dosya okunamadı." });
    const buf = Buffer.from(mt[1], "base64"); if (buf.length < 100) return cevap(res, 400, { hata: "Dosya boş görünüyor." }); if (buf.length > 2.5e6) return cevap(res, 400, { hata: "Dosya en çok 2,5 MB olabilir; küçültüp yeniden deneyin." });
    const uz = (ad.split(".").pop() || "").toLowerCase(), tip = BELGE_TIPLERI.filter((t) => t[0] === uz && t[2](buf))[0];
    if (!tip) return cevap(res, 400, { hata: "Yalnız PDF, JPG, PNG, Word veya Excel dosyası yüklenebilir." });
    const k = depo.belgeEkle(o, mid, { tur, ad, tip: tip[1], boyut: buf.length, veri: mt[1] });
    gunluk(o, mid, "Belge yüklendi", tur + " · " + ad);
    return cevap(res, 200, { belge: { id: k.id, tur: k.tur, ad: k.ad, tip: k.tip, boyut: k.boyut, zaman: k.zaman } });
  }
  if (yol === "/api/belge-sil") { personelOlur(o); const k = depo.belgeSil(o, mid, String(g.id || "")); gunluk(o, mid, "Belge silindi", k.tur + " · " + k.ad); return cevap(res, 200, { tamam: true }); }
  if (yol === "/api/talep") {
    if (o.rol !== "mukellef") return cevap(res, 403, { hata: "Talebi mükellef hesabı gönderir." });
    const metin = gib.temizMetin(g.metin, 600), tur = TALEP_TURLERI.includes(g.tur) ? g.tur : "Diğer";
    if (metin.length < 3) return cevap(res, 400, { hata: "Talebinizi birkaç kelimeyle yazın." });
    const liste = (m.talepler = Array.isArray(m.talepler) ? m.talepler : []);
    if (liste.filter((t) => t.durum === "Bekliyor").length >= 10) return cevap(res, 429, { hata: "Bekleyen 10 talebiniz var; ofis yanıtlayınca yenisini gönderebilirsiniz." });
    const t = { id: crypto.randomBytes(5).toString("hex"), zaman: new Date().toISOString(), tur, metin, durum: "Bekliyor", yanit: "", yanitZaman: "" };
    liste.push(t); if (liste.length > 200) liste.shift(); depo.kaydet(mid);
    gunluk(o, mid, "Ofise talep gönderildi", tur);
    if (OFIS_EPOSTA && posta.hazir()) posta.gonder({ gonderenAd: "Mükellef Portalı", to: [OFIS_EPOSTA], cc: [], konu: "Yeni talep: " + m.ad + " — " + tur, metin: m.ad + " yeni bir talep gönderdi.\n\nTür: " + tur + "\n\n" + metin + "\n\nYanıtlamak için portalda Belge sekmesinden talepleri açın." }, DIR).catch((e) => console.log("Talep bildirimi gönderilemedi: " + e.message));
    return cevap(res, 200, { talep: t });
  }
  if (yol === "/api/talep-durum") {
    personelOlur(o);
    const t = (m.talepler || []).filter((x) => x.id === g.id)[0]; if (!t) return cevap(res, 404, { hata: "Talep bulunamadı." });
    t.durum = g.durum === "Bekliyor" ? "Bekliyor" : "Yapıldı"; t.yanit = gib.temizMetin(g.yanit, 400); t.yanitZaman = new Date().toISOString(); depo.kaydet(mid);
    gunluk(o, mid, "Talep " + t.durum.toLocaleLowerCase("tr-TR"), t.tur);
    return cevap(res, 200, { talep: t });
  }
  /* tahsilat kaydı: yalnız bu programda tutulur (GİB'e gitmez); kısmi tahsilat desteklenir */
  if (yol === "/api/tahsilat") {
    const k = (m.gecmis || []).filter((x) => x.id === g.uuid)[0]; if (!k) return cevap(res, 404, { hata: "Fatura bu programın geçmişinde bulunamadı." });
    if (/^İptal/.test(k.durum || "") || k.tip === "IADE") return cevap(res, 400, { hata: "İptal ve iade faturaları için tahsilat kaydı tutulmaz." });
    const odenecek = (k.hesap && k.hesap.odenecek) || 0; k.tahsilat = Array.isArray(k.tahsilat) ? k.tahsilat : [];
    const alinan = k.tahsilat.reduce((t, x) => t + (x.tutar || 0), 0), kalan = odenecek - alinan, para = (k.para || "TRY") === "TRY" ? "TL" : k.para;
    const tl = (n) => (n / 100).toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (g.islem === "geri") {
      if (!k.tahsilat.length) return cevap(res, 400, { hata: "Silinecek tahsilat kaydı yok." });
      const son = k.tahsilat.pop(); depo.kaydet(mid); gunluk(o, mid, "Tahsilat kaydı geri alındı", (k.belgeNo || g.uuid) + " · " + tl(son.tutar) + " " + para);
      return cevap(res, 200, { kayit: k });
    }
    if (kalan <= 0) return cevap(res, 400, { hata: "Bu faturanın tamamı zaten tahsil edilmiş." });
    const tutar = kalan; // kısmi tahsilat yok: her kayıt faturanın kalan tutarının tamamını kapatır
    const tarih = String(g.tarih || ""); if (!/^\d{4}-\d{2}-\d{2}$/.test(tarih)) return cevap(res, 400, { hata: "Tahsilat tarihini seçin." });
    if (tarih > gib.trBugunStr()) return cevap(res, 400, { hata: "Tahsilat tarihi bugünden ileri olamaz." });
    const YONTEMLER = ["Havale / EFT", "Nakit", "Kredi kartı", "Çek", "Diğer"], yontem = YONTEMLER.includes(g.yontem) ? g.yontem : "Havale / EFT";
    k.tahsilat.push({ tutar, tarih, yontem, not: gib.temizMetin(g.not, 100), zaman: new Date().toISOString(), kim: o.kullanici });
    if (k.tahsilat.length > 50) k.tahsilat.shift();
    depo.kaydet(mid); gunluk(o, mid, "Tahsilat kaydedildi", (k.belgeNo || g.uuid) + " · " + tl(tutar) + " " + para + " · " + yontem);
    return cevap(res, 200, { kayit: k });
  }
  if (m.earsiv === false && !yol.startsWith("/api/vd/") && !yol.startsWith("/api/sgk/") && yol !== "/api/tahsilat" && yol !== "/api/mail") return cevap(res, 400, { hata: "Bu mükellef için e-Arşiv fatura kapalı; yalnız Vergi Dairesi bölümü kullanılabilir." });
  if (yol.startsWith("/api/sgk/")) {
    const ne = yol.slice(9), ix = sgkIx(g.ix), k = sgkKayit(m, ix), sis = g.sistem === "ebildirge" ? "ebildirge" : "isveren", an = sgkAnahtar(m.id, sis, ix);
    const birak = async () => { clearTimeout(sgkZaman.get(an)); sgkZaman.delete(an); const x0 = sgkler.get(an); sgkler.delete(an); if (x0) await x0.cikis().catch(() => {}); };
    try {
      if (ne === "captcha" || ne === "giris") if (!k.kullanici || !k.isyeriKod || !k.sistemSifre || !k.isyeriSifre) return cevap(res, 400, { hata: "Önce Ayarlar'da bu mükellefin SGK İşveren Sistemi bilgilerini (kullanıcı adı, işyeri kodu, sistem şifresi, işyeri şifresi) girin." });
      if (ne === "captcha") { sgkKontrol(an, "c"); await birak(); const x = sgk.istemci(k, sis); sgkler.set(an, x); sgkZamanla(an); return cevap(res, 200, await x.captcha()); }
      if (ne === "giris") {
        sgkKontrol(an, "g"); const x = sgkler.get(an); if (!x) return cevap(res, 409, { hata: "Önce güvenlik kodu resmini isteyin.", girisGerek: true });
        try { await x.giris(g.dk); sgkZamanla(an); gunluk(o, mid, sis === "ebildirge" ? "SGK e-Bildirge bağlantısı" : "SGK İşveren Sistemi bağlantısı", ""); return cevap(res, 200, { tamam: true }); }
        catch (e) { await birak(); throw e; }
      }
      if (ne === "cikis") { if (g.sistem) await birak(); else await sgkBirak(m.id); return cevap(res, 200, { tamam: true }); }
      const x = sgkler.get(an); if (!x || !x.girdi) { const e = new Error("Önce SGK'ya bağlanın (güvenlik kodu)."); e.girisGerek = true; throw e; }
      sgkZamanla(an);
      if (ne === "tani") return cevap(res, 200, await x.tani(g.derin === true));
      if (sis === "isveren" && ne === "tesvik") {
        if (g.islem === "form") { sgkKontrol(an, "tf"); return cevap(res, 200, await x.tesvikFormu()); }
        if (g.islem === "sorgu") {
          sgkKontrol(an, "ts");
          const d = g.alan && typeof g.alan === "object" ? g.alan : {}, tc = String(d.tcKimlikNo || "").replace(/\D/g, "");
          if (tc && !/^\d{11}$/.test(tc)) return cevap(res, 400, { hata: "T.C. kimlik numarası 11 haneli olmalı." });
          const t = await x.tesvikSorgula(d); gunluk(o, mid, "SGK potansiyel teşvik sorgusu", ""); return cevap(res, 200, t);
        }
        return cevap(res, 400, { hata: "Geçersiz işlem." });
      }
      if (sis === "isveren" && ne === "sayfa") { const ad = String(g.ad || ""); if (!ISVEREN_SAYFALAR.has(ad)) return cevap(res, 400, { hata: "Bu sayfa desteklenmiyor." }); const t = await x.isverenSayfa(ad); gunluk(o, mid, "SGK İşveren sayfası görüntülendi", ad);
        if (ad === "DonemBorcGoruntuleme" && t.borcToplam != null) { m.son = m.son || {}; (m.son.sgkBorcIx = m.son.sgkBorcIx || {})[ix] = t.borcToplam; m.son.sgkBorc = { toplam: Object.values(m.son.sgkBorcIx).reduce((a, b) => a + b, 0), zaman: new Date().toISOString() }; depo.kaydet(mid); }
        return cevap(res, 200, t); }
      if (sis === "ebildirge" && ne === "bildirge-donemler") return cevap(res, 200, await x.bildirgeDonemler());
      if (sis === "ebildirge" && ne === "bildirge-liste") { const t = await x.bildirgeListe(String(g.bas || ""), String(g.bit || "")); gunluk(o, mid, "SGK onaylı bildirge listesi görüntülendi", ""); return cevap(res, 200, t); }
    } catch (e) { if (e && e.oturum) { await birak(); e.girisGerek = true; } if (e && e.girisGerek) return cevap(res, 409, { hata: e.message, girisGerek: true }); throw e; }
    return cevap(res, 404, { hata: "Bulunamadı." });
  }
  if (!m.kullanici || (!m.gibSifre && !gib.MOCK)) return cevap(res, 400, { hata: "Bu mükellef için GİB / Dijital Vergi Dairesi kullanıcı kodu ve şifresi girilmemiş (Ayarlar)." });
  if (yol === "/api/taslak") {
    const x = modelTemiz(g, true), uuid = crypto.randomUUID();
    const r = await istemci(m).taslak((v) => gib.faturaGovdesi(x, uuid, v));
    const satirlar = x.kalemler.map((k, i) => Object.assign({}, k, { matrah: x._h.satirlar[i].matrah, kdvTutar: x._h.satirlar[i].kdv, tevKdv: x._h.satirlar[i].tevKdv }));
    const kayit = {
      id: r.uuid, zaman: new Date().toISOString(), mukellefId: m.id, mukellef: { ad: m.ad, vkn: m.vkn }, belgeNo: (r.satir && r.satir.belgeNumarasi) || "",
      aliciUnvan: x.alici.unvan, aliciVkn: x.alici.vkn, aliciAdres: x.alici.adres, vergiDairesi: x.alici.vd, aliciEposta: x.alici.eposta, epostaGonder: !!g.epostaGonder && !!x.alici.eposta, tarih: x.tarih, tip: x.tip, para: x.para, kur: x.kur,
      kalemler: satirlar, hesap: x._h.toplam, not: x.not, durum: "Taslak", iade: x.iade, olusturan: o.kullanici,
      form: { alici: x.alici, tip: x.tip, para: x.para, kur: x.kur, dahil: x.kdvDahil, iade: x.iade, kalemler: x.kalemler, notEk: x.notEk, notIrsaliye: x.notIrsaliye } // "Tekrarla" için
    };
    bekleyen.set(r.uuid, kayit); gunluk(o, mid, "Taslak oluşturuldu", kayit.belgeNo + " · " + kayit.aliciUnvan);
    return cevap(res, 200, { uuid: r.uuid, mesaj: r.mesaj, hesap: x._h.toplam, kayit });
  }
  if (yol === "/api/sms") return cevap(res, 200, await istemci(m, 8 * 60e3).smsGonder());
  if (yol === "/api/imzala") {
    if (!g.uuid || !/^[A-Za-z0-9]{4,12}$/.test(String(g.kod || "").trim())) return cevap(res, 400, { hata: "SMS kodunu yazın." });
    const r = await istemci(m).imzala(g.uuid, String(g.kod).trim(), g.oid, g.tarih);
    const kayit = bekleyen.get(g.uuid) && bekleyen.get(g.uuid).mukellefId === m.id ? bekleyen.get(g.uuid) : null;
    if (kayit) { kayit.durum = "Onaylandı"; kayit.onayZamani = new Date().toISOString(); m.gecmis.push(kayit); if (m.gecmis.length > 2000) m.gecmis.shift(); bekleyen.delete(g.uuid); depo.kaydet(mid); }
    gunluk(o, mid, "Fatura onaylandı", (kayit && kayit.belgeNo) || g.uuid); gibKisalt(m.id, 45e3);
    return cevap(res, 200, { mesaj: r.mesaj, kayit: kayit || null });
  }
  if (yol === "/api/mail") {
    if (!posta.hazir()) return cevap(res, 400, { hata: "E-posta gönderimi bu sunucuda henüz kurulmadı (sunucu ayarlarında MAIL_ANAHTAR ve MAIL_GONDEREN gerekir)." });
    const sinir = (postaSayac.get(o.kullanici) || []).filter((t) => Date.now() - t < 3600e3); if (sinir.length >= 40) return cevap(res, 429, { hata: "Saatlik e-posta sınırına ulaşıldı (40). Biraz sonra tekrar deneyin." });
    let k = (m.gecmis || []).filter((x) => x.id === g.uuid)[0], gibKaydi = false;
    if (!k) { const oz = g.ozet && typeof g.ozet === "object" ? g.ozet : null; if (!oz) return cevap(res, 404, { hata: "Fatura bu programın geçmişinde bulunamadı; e-posta gönderilemedi." }); k = { aliciUnvan: gib.temizMetin(oz.alici, 120), belgeNo: gib.temizMetin(oz.belgeNo, 40), tarih: String(oz.tarih || "").replace(/^(\d{2})[-\/.](\d{2})[-\/.](\d{4})/, "$3-$2-$1").slice(0, 10) }; gibKaydi = true; }
    const to = (Array.isArray(g.to) ? g.to : [g.to]).map((x) => String(x || "").trim()).filter(Boolean).slice(0, 3);
    if (!to.length || !to.every((x) => posta.EPOSTA.test(x) && x.length <= 120)) return cevap(res, 400, { hata: "Geçerli bir e-posta adresi yazın." });
    const b64 = String(g.pdf || ""); if (!/^[A-Za-z0-9+/=]{100,}$/.test(b64) || b64.length > 5.5e6) return cevap(res, 400, { hata: "PDF eki geçersiz ya da çok büyük." });
    const veri = Buffer.from(b64, "base64"); if (veri.slice(0, 4).toString() !== "%PDF") return cevap(res, 400, { hata: "Ek bir PDF değil." });
    const pr = m.profil || {}, para = k.para || "TRY", tutar = k.hesap && typeof k.hesap.odenecek === "number" ? (k.hesap.odenecek / 100).toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " " + (para === "TRY" ? "TL" : para) : "";
    const tarih = String(k.tarih || "").split("-").reverse().join(".");
    const metin = "Sayın " + (k.aliciUnvan || "yetkili") + ",\n\n" + (k.belgeNo ? k.belgeNo + " numaralı " : "") + (tarih ? tarih + " tarihli " : "") + "e-Arşiv faturanız ektedir" + (tutar ? " (toplam: " + tutar + ")" : "") + ".\n\nİyi çalışmalar dileriz.\n" + m.ad + (pr.tel ? "\nTel: " + pr.tel : "") + (pr.eposta ? "\nE-posta: " + pr.eposta : "") + "\n\n— Bu ileti e-Arşiv fatura portalı üzerinden gönderilmiştir.";
    const kopya = pr.eposta && posta.EPOSTA.test(pr.eposta) && !to.includes(pr.eposta) ? [pr.eposta] : [];
    await posta.gonder({ gonderenAd: m.ad, to, cc: kopya, yanit: pr.eposta || "", konu: "Fatura" + (k.belgeNo ? " " + k.belgeNo : "") + " — " + m.ad, metin, ek: { ad: "fatura-" + String(k.belgeNo || "belge").replace(/[^\w.-]+/g, "_") + ".pdf", veri } }, DIR);
    sinir.push(Date.now()); postaSayac.set(o.kullanici, sinir);
    if (!gibKaydi) { (k.epostalar = k.epostalar || []).push({ zaman: new Date().toISOString(), to: to.join(", ") }); if (k.epostalar.length > 20) k.epostalar.shift(); depo.kaydet(mid); }
    gunluk(o, mid, "Fatura e-postayla gönderildi", (k.belgeNo || g.uuid) + " → " + to.join(", "));
    return cevap(res, 200, { tamam: true, to, kopya });
  }
  if (yol === "/api/sil" || yol === "/api/iptal") {
    const sil = yol === "/api/sil", neden = gib.temizMetin(g.neden, 200);
    if (!g.uuid || !/^[A-Za-z0-9:_=.-]{8,4000}$/.test(String(g.uuid))) return cevap(res, 400, { hata: "Belge seçilmedi." });
    if (!neden) return cevap(res, 400, { hata: (sil ? "Silme" : "İptal") + " nedenini yazın." });
    const r = await (sil ? istemci(m).sil(g.uuid, neden, g.tarih) : istemci(m).iptal(g.uuid, neden, g.tarih));
    bekleyen.delete(g.uuid);
    const k = (m.gecmis || []).filter((x) => x.id === g.uuid)[0];
    if (k && !sil) { k.durum = "İptal talebi"; k.iptalNedeni = neden; k.iptalZamani = new Date().toISOString(); depo.kaydet(mid); }
    gunluk(o, mid, sil ? "Taslak silindi" : "İptal talebi gönderildi", (k && k.belgeNo) || g.uuid); gibKisalt(m.id, 45e3);
    return cevap(res, 200, { mesaj: r.mesaj, durum: r.durum });
  }
  if (yol.startsWith("/api/vd/")) {
    const ne = yol.slice(8);
    try {
      if (ne === "captcha") {
        ivdKontrol(m, "c"); await ivdBirak(m.id);
        const x = ivd.istemci(m.kullanici, m.gibSifre); ivdler.set(m.id, x); ivdZamanla(m.id);
        return cevap(res, 200, await x.captcha());
      }
      if (ne === "giris") {
        ivdKontrol(m, "g"); const x = ivdler.get(m.id);
        if (!x) return cevap(res, 409, { hata: "Önce doğrulama kodu resmini isteyin.", girisGerek: true });
        try { await x.giris(g.dk); ivdHata.delete(m.id); ivdZamanla(m.id); gunluk(o, mid, "Dijital Vergi Dairesi bağlantısı", ""); return cevap(res, 200, { tamam: true }); }
        catch (e) { if (e && e.giris) { const n = (ivdHata.get(m.id) || 0) + 1; ivdHata.set(m.id, n); if (n >= 3) { ivdKilit.set(m.id, Date.now() + 10 * 60e3); ivdHata.delete(m.id); } } await ivdBirak(m.id); throw e; }
      }
      if (ne === "cikis") { await ivdBirak(m.id); return cevap(res, 200, { tamam: true }); }
      if (ne === "borc") {
        const r = await vdSorgu(m, (x) => x.borc());
        try { const t = r && r.ozetKart && r.ozetKart.toplam; if (t) { (m.son = m.son || {}).vdBorc = { toplam: Number(t.toplam) || 0, asil: Number(t.asil) || 0, gz: Number(t.gz) || 0, adet: t.adet || 0, zaman: new Date().toISOString() }; depo.kaydet(mid); } } catch (e) { /* özet kaydı isteğe bağlı */ }
        return cevap(res, 200, r);
      }
      if (ne === "tebligat") return cevap(res, 200, await vdSorgu(m, (x) => x.tebligat()));
      if (ne === "belge") {
        const al = (a) => { const v = String(g[a] || ""); if (!/^[\w.\-]{1,128}$/.test(v)) throw new Error("Geçersiz tebligat kimliği."); return v; };
        const p = { tarafId: al("tarafId"), tarafSecureId: al("tarafSecureId"), tebligId: al("tebligId"), tebligSecureId: al("tebligSecureId") };
        return cevap(res, 200, await vdSorgu(m, (x) => x.belgeListe(p)));
      }
      if (ne === "levha") { const yil = Number(g.yil), buYil = Number(gib.trBugunStr().slice(0, 4)); if (!(yil >= buYil - 3 && yil <= buYil)) return cevap(res, 400, { hata: "Yıl seçin." }); return cevap(res, 200, await vdSorgu(m, (x) => x.levhaListe(yil))); }
      if (ne === "yazilar") return cevap(res, 200, await vdSorgu(m, (x) => x.yaziListe()));
      if (ne === "haciz") { const HACIZ = { banka: "P_INTVRG_INTVD_EHACIZ_BANKA_SRG", arac: "P_INTVRG_INTVD_EHACIZ_ARAC_SRG" }; const sayfa = HACIZ[String(g.tur || "")]; if (!sayfa) return cevap(res, 400, { hata: "Bu sorgu henüz desteklenmiyor." }); const r = await vdSorgu(m, (x) => x.interaktifSayfa(sayfa, o.rol === "ofis" && g.derin === true)); gunluk(o, mid, "İnteraktif VD haciz sayfası görüntülendi", String(g.tur)); return cevap(res, 200, r); }
      if (ne === "zrapor") { if (o.rol === "mukellef") return cevap(res, 400, { hata: "Z raporu için çalışma devam ediyor." }); const r = await vdSorgu(m, (x) => x.interaktifSayfa("", g.derin === true, "okc")); gunluk(o, mid, "İnternet VD sayfası görüntülendi", "Z raporu"); return cevap(res, 200, r); }
      if (ne === "yoklama") return cevap(res, 200, await vdSorgu(m, (x) => x.yoklamaListe()));
      if (ne === "sicil") return cevap(res, 200, await vdSorgu(m, (x) => x.sicilBilgi()));
      if (ne === "tahakkuk") return cevap(res, 200, await vdSorgu(m, (x) => x.tahakkukListe(String(g.tbas || ""), String(g.tbit || ""))));
      if (ne === "arac") return cevap(res, 200, await vdSorgu(m, (x) => x.aracListe(g.gecmis === true)));
      if (ne === "pos") return cevap(res, 200, await vdSorgu(m, (x) => x.posListe(String(g.yil || ""), String(g.ay || ""))));
      if (ne === "telefon") {
        /* Dijital VD profilindeki onay (SMS) telefonu: mevcut numara / yeni numaraya kod / kodla güncelleme. Açık onay ister; numara günlüğe yazılmaz. */
        const tel = String(g.tel || "").replace(/\D/g, "").replace(/^(5\d{9})$/, "0$1"), kimlik = String(m.vkn || "").replace(/\D/g, "");
        if (g.islem === "bilgi") return cevap(res, 200, await vdSorgu(m, (x) => x.telefonBilgi()));
        if (g.onay !== true) return cevap(res, 400, { hata: "İşlem için onay gerekli." });
        if (g.islem === "kod") { ivdKontrol(m, "t"); return cevap(res, 200, await vdSorgu(m, (x) => x.telefonKodIste(kimlik, tel))); }
        if (g.islem === "guncelle") { ivdKontrol(m, "t"); const r = await vdSorgu(m, (x) => x.telefonGuncelle(tel, String(g.kod || "").replace(/\D/g, ""))); gunluk(o, mid, "Dijital VD onay telefonu güncellendi", ""); return cevap(res, 200, r); }
        return cevap(res, 400, { hata: "Geçersiz işlem." });
      }
      if (ne === "yazi-iste") {
        /* resmî talep: yalnız açık onayla, mükellef başına günde en çok 3 talep */
        if (g.onay !== true) return cevap(res, 400, { hata: "Talep için onay gerekli." });
        const KURUMLAR = ["Kredi Garanti Fonu", "İlgili Belediye Başkanlığına", "KOSGEB'e", "Tarım ve Orman Bakanlığı'na", "Çevre, Şehircilik ve İklim Değişikliği Bakanlığına", "Emniyet Genel Müdürlüğüne", "Çalışma ve Sosyal Güvenlik Bakanlığına", "Enerji ve Tabii Kaynaklar Bakanlığına", "Diğer Kurum Kuruluşlara"];
        const kurum = String(g.kurum || ""), diger = gib.temizMetin(g.digerKurum, 100), eposta = String(g.eposta || "").trim();
        let neden = String(g.neden || "");
        if (!KURUMLAR.includes(kurum)) return cevap(res, 400, { hata: "Yazının verileceği kurumu seçin." });
        if (kurum === "Kredi Garanti Fonu") neden = "2"; // portal bu kurumda nedeni sabitler
        if (!["1", "2", "3"].includes(neden)) return cevap(res, 400, { hata: "Yazı talep nedenini seçin." });
        if (kurum === "Diğer Kurum Kuruluşlara" && diger.length < 3) return cevap(res, 400, { hata: "Kurum / kuruluş adını yazın." });
        if (!posta.EPOSTA.test(eposta) || eposta.length > 120) return cevap(res, 400, { hata: "Cevabın bildirileceği geçerli bir e-posta adresi yazın." });
        const sin = (yaziSayac.get(m.id) || []).filter((t) => Date.now() - t < 864e5); if (sin.length >= 3) return cevap(res, 429, { hata: "Bir mükellef için günde en çok 3 yazı talebi gönderilebilir." });
        const r = await vdSorgu(m, (x) => x.yaziIste({ eposta, neden, kurum, digerKurum: kurum === "Diğer Kurum Kuruluşlara" ? diger : "" }));
        sin.push(Date.now()); yaziSayac.set(m.id, sin);
        gunluk(o, mid, "Borç durum yazısı talep edildi", kurum + (diger ? " (" + diger + ")" : "") + " · neden " + neden);
        return cevap(res, 200, r);
      }
      if (ne === "gelen") {
        const t = (d) => { const q = /^(\d{4})-(\d{2})-(\d{2})$/.exec(d || ""); if (!q) throw new Error("Tarih seçin."); return `${q[3]}/${q[2]}/${q[1]}`; };
        const bas = t(g.bas), bit = t(g.bit);
        return cevap(res, 200, await vdSorgu(m, (x) => x.gelen(bas, bit)));
      }
    } catch (e) { if (e && e.girisGerek) return cevap(res, 409, { hata: e.message, girisGerek: true }); throw e; }
    return cevap(res, 404, { hata: "Bulunamadı." });
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
    const t0 = Date.now(); let html;
    try { html = await istemci(m).faturaHtml(g.uuid, g.onay); } finally { console.log("fatura görünümü: " + (Date.now() - t0) + " ms"); } // yalnız süre (teşhis); içerik yazılmaz
    return cevap(res, 200, { html });
  }
  cevap(res, 404, { hata: "Bulunamadı." });
}

const SAYFA = path.join(__dirname, "public", "index.html");
http.createServer((req, res) => {
  const yol = req.url.split("?")[0];
  if (yol === "/saglik") { res.writeHead(200, { "content-type": "text/plain", "cache-control": "no-store" }); return res.end("ok"); } /* uyanık tutma / sağlık denetimi: veriye dokunmaz */
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
