"use strict";
/* Fatura Portalı — bağımlılıksız Node sunucusu.
 * Çalıştır: node server.js   →   http://127.0.0.1:3000
 * Veri: data/kasa.json (uygulama şifresiyle AES-GCM şifreli; GİB şifreleri de içinde). */
const http = require("http");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const gib = require("./gib");

const PORT = Number(process.env.PORT) || 3000;
const HOST = process.env.HOST || "127.0.0.1";
const DIR = path.join(__dirname, "data");
const KASA = path.join(DIR, "kasa.json");
const ITER = 250000;
const SURUM = "2026-10-18-12";

let key = null, tuz = null, veri = null; // yalnızca giriş yapılınca bellekte
const oturumlar = new Map(); // çerez -> bitiş zamanı
const gibler = new Map(); // mükellef id -> istemci (taslak/sms/imza aynı oturumda)
let basarisiz = 0, kilitBitis = 0;

const varsayilan = () => ({
  mukellefler: [],
  hizmetler: [
    { id: "servis", ad: "Servis Taşımacılık Bedeli", kdv: 20, tev: 5, kod: "614", anah: "servis, personel taşı" },
    { id: "yuk", ad: "Yük Taşımacılığı Bedeli", kdv: 20, tev: 2, kod: "624", anah: "yük, yuk, nakliye" }
  ]
});

const kasaVar = () => fs.existsSync(KASA);
const anahtar = (sifre, t, iter) => new Promise((ok, no) => crypto.pbkdf2(sifre, t, iter, 32, "sha256", (e, k) => (e ? no(e) : ok(k))));
function yaz() {
  const iv = crypto.randomBytes(12), c = crypto.createCipheriv("aes-256-gcm", key, iv);
  const ct = Buffer.concat([c.update(JSON.stringify(veri), "utf8"), c.final()]);
  fs.mkdirSync(DIR, { recursive: true });
  const gecici = KASA + ".tmp";
  fs.writeFileSync(gecici, JSON.stringify({ v: 1, iter: ITER, tuz: tuz.toString("base64"), iv: iv.toString("base64"), tag: c.getAuthTag().toString("base64"), veri: ct.toString("base64") }));
  fs.renameSync(gecici, KASA);
}
async function ac(sifre) {
  const k = JSON.parse(fs.readFileSync(KASA, "utf8")), t = Buffer.from(k.tuz, "base64");
  const kk = await anahtar(sifre, t, k.iter);
  const d = crypto.createDecipheriv("aes-256-gcm", kk, Buffer.from(k.iv, "base64"));
  d.setAuthTag(Buffer.from(k.tag, "base64"));
  const p = Buffer.concat([d.update(Buffer.from(k.veri, "base64")), d.final()]); // yanlış şifrede fırlatır
  key = kk; tuz = t; veri = JSON.parse(p.toString("utf8"));
}

/* GİB şifreleri veri içinde düz durur ama kasa dosyası şifrelidir; istemciye asla gönderilmez. */
const temiz = () => ({
  hizmetler: veri.hizmetler,
  mukellefler: veri.mukellefler.map((m) => ({ id: m.id, ad: m.ad, vkn: m.vkn, kullanici: m.kullanici, sifreVar: !!m.gibSifre, aliciler: m.aliciler || [] }))
});
function birlestir(g) {
  const eski = new Map(veri.mukellefler.map((m) => [m.id, m]));
  veri.hizmetler = g.hizmetler;
  veri.mukellefler = g.mukellefler.map((m) => ({
    id: String(m.id), ad: String(m.ad || ""), vkn: String(m.vkn || ""), kullanici: String(m.kullanici || ""),
    gibSifre: m.gibSifre ? String(m.gibSifre) : (eski.get(m.id) || {}).gibSifre || "",
    aliciler: (m.aliciler || []).map((a) => ({ id: String(a.id), ad: String(a.ad || ""), vkn: String(a.vkn || ""), adres: String(a.adres || "") }))
  }));
  gibler.clear();
  yaz();
}

/* ---------- http ---------- */
function oku(req) {
  return new Promise((ok, no) => {
    let b = ""; req.on("data", (c) => { b += c; if (b.length > 1e6) { no(new Error("büyük")); req.destroy(); } });
    req.on("end", () => { try { ok(b ? JSON.parse(b) : {}); } catch (e) { no(new Error("Geçersiz JSON")); } });
  });
}
const cevap = (res, kod, nesne, baslik) => { res.writeHead(kod, Object.assign({ "content-type": "application/json; charset=utf-8", "cache-control": "no-store" }, baslik)); res.end(JSON.stringify(nesne)); };
const cerez = (req) => { const m = /(?:^|;\s*)oturum=([a-f0-9]+)/.exec(req.headers.cookie || ""); return m && m[1]; };
const girisli = (req) => { const c = cerez(req), b = oturumlar.get(c); return !!(key && b && b > Date.now()); };
function oturumAc(res) {
  const c = crypto.randomBytes(24).toString("hex"); oturumlar.set(c, Date.now() + 8 * 3600e3);
  return { "set-cookie": `oturum=${c}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800` };
}
const hataBilgi = (e) => (e && e.message) || "Bilinmeyen hata";

const mukellefBul = (id) => veri.mukellefler.filter((m) => m.id === id)[0];
function istemci(m) {
  if (!gibler.has(m.id)) gibler.set(m.id, gib.istemci(m.kullanici, m.gibSifre));
  return gibler.get(m.id);
}
function hazirla(g) {
  const h = veri.hizmetler.filter((x) => x.id === g.hizmetId)[0];
  if (!h) throw new Error("Hizmet bulunamadı.");
  if (!g.aliciUnvan || !/^\d{10,11}$/.test(String(g.aliciVkn || ""))) throw new Error("Alıcı unvanı ve 10/11 haneli VKN/TCKN gerekli.");
  const bugun = new Date(), yerel = `${bugun.getFullYear()}-${String(bugun.getMonth() + 1).padStart(2, "0")}-${String(bugun.getDate()).padStart(2, "0")}`;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(g.tarih || "")) g.tarih = yerel;
  if (g.tarih > yerel) throw new Error("Fatura tarihi bugünden ileri olamaz.");
  const x = Object.assign({}, g, { tutar: Number(g.tutar), kdvOrani: Number(g.kdvOrani), tevkifat: Number(g.tevkifat) || 0 });
  x._h = gib.hesapla(x);
  return { x, h };
}

async function api(req, res, yol) {
  if (req.method !== "GET" && !/application\/json/.test(req.headers["content-type"] || "")) return cevap(res, 415, { hata: "JSON bekleniyor." });
  if (yol === "/api/durum") return cevap(res, 200, { kurulu: kasaVar(), giris: girisli(req), sahte: gib.MOCK, surum: SURUM });
  if (yol === "/api/kurulum" && req.method === "POST") {
    if (kasaVar()) return cevap(res, 409, { hata: "Zaten kurulu." });
    const { sifre } = await oku(req);
    if (!sifre || sifre.length < 8) return cevap(res, 400, { hata: "Şifre en az 8 karakter olmalı." });
    tuz = crypto.randomBytes(16); key = await anahtar(sifre, tuz, ITER); veri = varsayilan(); yaz();
    return cevap(res, 200, { ok: true }, oturumAc(res));
  }
  if (yol === "/api/giris" && req.method === "POST") {
    if (Date.now() < kilitBitis) return cevap(res, 429, { hata: "Çok fazla yanlış deneme; biraz bekleyin." });
    const { sifre } = await oku(req);
    try { await ac(String(sifre || "")); basarisiz = 0; return cevap(res, 200, { ok: true }, oturumAc(res)); }
    catch (e) { if (++basarisiz >= 5) { kilitBitis = Date.now() + 60e3; basarisiz = 0; } return cevap(res, 401, { hata: "Şifre yanlış." }); }
  }
  if (!girisli(req)) return cevap(res, 401, { hata: "Giriş gerekli." });
  if (yol === "/api/cikis") { oturumlar.delete(cerez(req)); key = null; veri = null; gibler.clear(); return cevap(res, 200, { ok: true }); }
  if (yol === "/api/veri" && req.method === "GET") return cevap(res, 200, temiz());
  if (yol === "/api/veri" && req.method === "PUT") { const g = await oku(req); if (!Array.isArray(g.mukellefler) || !Array.isArray(g.hizmetler)) return cevap(res, 400, { hata: "Geçersiz veri." }); birlestir(g); return cevap(res, 200, temiz()); }
  if (yol === "/api/hesapla" && req.method === "POST") { const g = await oku(req); return cevap(res, 200, gib.hesapla(g)); }

  const g = await oku(req), m = mukellefBul(g.mukellefId);
  if (!m) return cevap(res, 400, { hata: "Mükellef seçin." });
  if (!m.kullanici || (!m.gibSifre && !gib.MOCK)) return cevap(res, 400, { hata: "Bu mükellef için GİB kullanıcı kodu/şifresi girilmemiş (Ayarlar)." });
  if (yol === "/api/taslak") {
    const { x, h } = hazirla(g), uuid = crypto.randomUUID();
    const s = await istemci(m).taslak((v) => gib.faturaGovdesi(x, h, uuid, v));
    return cevap(res, 200, { uuid: s.uuid, mesaj: s.mesaj, hesap: x._h });
  }
  if (yol === "/api/sms") return cevap(res, 200, await istemci(m).smsGonder());
  if (yol === "/api/imzala") {
    if (!g.uuid || !/^[A-Za-z0-9]{4,12}$/.test(String(g.kod || "").trim())) return cevap(res, 400, { hata: "SMS kodunu yazın." });
    return cevap(res, 200, await istemci(m).imzala(g.uuid, String(g.kod).trim(), g.oid, g.tarih));
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
  if (yol.startsWith("/api/")) return api(req, res, yol).catch((e) => { console.error(e.message); cevap(res, 500, { hata: hataBilgi(e) }); });
  if (yol === "/" || yol === "/index.html") { res.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" }); return fs.createReadStream(SAYFA).pipe(res); }
  res.writeHead(404); res.end("Bulunamadı");
}).on("error", (e) => { console.error(e.code === "EADDRINUSE" ? "HATA: " + PORT + " numaralı kapı dolu; eski program hâlâ çalışıyor. Eski siyah pencereyi kapatın ve yeniden başlatın." : e.message); process.exit(1); }).listen(PORT, HOST, () => console.log(`Fatura Portalı ${SURUM}: http://${HOST}:${PORT}` + (gib.MOCK ? "  (SAHTE GİB — gerçek fatura kesilmez)" : "")));
