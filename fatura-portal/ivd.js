/* Dijital Vergi Dairesi (dijital.gib.gov.tr) istemcisi: borç durumu, e-Tebligat, gelen (alıcı) e-Arşiv faturaları.
 *
 * Giriş yarı otomatiktir: portalın "Doğrulama Kodu" resmi alınır (captcha), kullanıcı kodu yazar, sonra kayıtlı kullanıcı kodu/şifre ile giriş yapılır.
 * DİKKAT: GİB'in resmî bir API'si yoktur; adresler portalın herkese açık arayüz kodundan okunmuştur ve değişebilir. Bu yüzden her yanıtın
 * "şekli" (anahtarlar ve türler, değerler maskeli) tanı için ayrıca üretilir. Giriş başarısızsa sunucu tarafında bekleme uygulanır (kod kilitlenmesin). */
"use strict";
const crypto = require("crypto");

const MOCK = process.env.GIB_MOCK === "1";
const GW = "https://dijital.gib.gov.tr/apigateway";

/* değerleri maskeleyip yalnız yapıyı gösterir (paylaşılabilir tanı): metin -> <metin n>, sayı -> <sayı>, tarih benzeri -> <tarih> */
function sekil(v, d = 0) {
  if (v === null || v === undefined) return null;
  if (Array.isArray(v)) return d > 4 ? "[...]" : v.length ? ["(" + v.length + " öğe)", sekil(v[0], d + 1)] : [];
  if (typeof v === "object") { if (d > 4) return "{...}"; const o = {}; for (const k of Object.keys(v).slice(0, 40)) o[k] = sekil(v[k], d + 1); return o; }
  if (typeof v === "number") return "<sayı>";
  if (typeof v === "boolean") return "<doğru/yanlış>";
  const t = String(v);
  if (/^\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|^\d{4}-\d{2}-\d{2}/.test(t)) return "<tarih>";
  if (/^-?[\d.,]+$/.test(t)) return "<sayı-metin>";
  return "<metin " + t.length + ">";
}
/* yanıttaki nesne dizilerini düz kayıtlara çevirir (arayüz, anahtarları bilmeden gösterebilsin) */
function kayitlar(veri) {
  const out = [];
  const duz = (o) => { const r = {}; for (const [k, v] of Object.entries(o || {})) { if (v === null || v === undefined || v === "") continue; if (typeof v === "object") { r[k] = JSON.stringify(v).slice(0, 200); } else r[k] = v; } return r; };
  const gez = (v, d) => {
    if (d > 4 || v === null || v === undefined) return;
    if (Array.isArray(v)) { if (v.length && typeof v[0] === "object") v.slice(0, 500).forEach((x) => out.push(duz(x))); else v.slice(0, 500).forEach((x) => out.push({ değer: x })); return; }
    if (typeof v === "object") { let dizi = false; for (const x of Object.values(v)) if (Array.isArray(x) && x.length) { dizi = true; gez(x, d + 1); } if (!dizi) { const f = duz(v); if (Object.keys(f).length) out.push(f); } }
  };
  gez(veri, 0);
  return out.slice(0, 500);
}

class Ivd {
  constructor(kullanici, sifre) { this.k = kullanici; this.s = sifre; this.token = null; this.cid = null; }
  get girildi() { return !!this.token; }
  async istek(yontem, url, govde, bearer) {
    const baslik = { accept: "application/json, text/plain, */*", "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36", origin: "https://dijital.gib.gov.tr", referer: "https://dijital.gib.gov.tr/portal/" };
    if (govde !== undefined) baslik["content-type"] = "application/json";
    if (bearer && this.token) baslik.authorization = "Bearer " + this.token;
    let r;
    try { r = await fetch(url, { method: yontem, headers: baslik, body: govde !== undefined ? JSON.stringify(govde) : undefined, signal: AbortSignal.timeout(25000) }); }
    catch (e) { throw new Error(e && (e.name === "TimeoutError" || e.name === "AbortError") ? "Dijital Vergi Dairesi 25 saniyede yanıt vermedi (zaman aşımı)." : "Dijital Vergi Dairesi'ne ulaşılamadı: " + e.message); }
    const t = await r.text(); let y = null; try { y = JSON.parse(t); } catch (e) { /* JSON değil */ }
    if (r.status === 401 || r.status === 403) { this.token = null; const e = new Error("Dijital Vergi Dairesi oturumu kapandı; doğrulama koduyla yeniden bağlanın."); e.oturum = true; throw e; }
    if (!r.ok || y === null) {
      const msj = y ? this.mesajMetni(y) : "";
      throw new Error("Dijital Vergi Dairesi " + (msj ? "hatası: " + msj : "beklenmeyen yanıt verdi (HTTP " + r.status + ", " + (/^\s*</.test(t) ? "HTML sayfa" : "JSON değil") + ")") + ".");
    }
    return y;
  }
  mesajMetni(y) {
    const l = (y && (y.messages || y.mesajlar)) || [];
    const m = (Array.isArray(l) ? l : []).map((x) => (x && (x.text || x.message)) || (typeof x === "string" ? x : "")).filter(Boolean).join(" | ");
    return m || (y && (y.errorMessage || y.message || y.error || y.hata)) || "";
  }
  /* doğrulama kodu resmi: { resim (data URI), cid } */
  async captcha() {
    const y = await this.istek("GET", GW + "/captcha/getnewcaptcha");
    if (!y || !y.captchaImgBase64 || !y.cid) throw new Error("Dijital Vergi Dairesi doğrulama kodu resmini vermedi.");
    this.cid = y.cid;
    return { resim: /^data:/.test(y.captchaImgBase64) ? y.captchaImgBase64 : "data:image/png;base64," + y.captchaImgBase64 };
  }
  async giris(dk) {
    if (!this.cid) throw new Error("Önce doğrulama kodu resmini isteyin.");
    const cid = this.cid; this.cid = null; // kod tek kullanımlık
    const y = await this.istek("POST", GW + "/auth/tdvd/login", { userid: this.k, sifre: this.s, dk: String(dk || "").trim(), imageId: cid });
    if (!y || !y.token) {
      const m = this.mesajMetni(y);
      const e = new Error("Dijital Vergi Dairesi girişi başarısız" + (m ? ": " + String(m).slice(0, 200) : " (kod/şifre kabul edilmedi ya da ek doğrulama istendi)") + ".");
      e.giris = true; e.anahtarlar = y && typeof y === "object" ? Object.keys(y).slice(0, 15) : []; throw e;
    }
    this.token = y.token;
  }
  async cikis() {
    const t = this.token; this.token = null; this.cid = null; if (!t) return;
    try { await this.istek("POST", GW + "/auth/tdvd/logout", {}, true); } catch (e) { /* önemli değil */ }
  }
  /* tablo bileşeninin gövdesi */
  tablo(veri, sayfaBoyu, sira) { return { meta: { pagination: { pageNo: 1, pageSize: sayfaBoyu || 100 }, sortFieldName: sira && sira.alan, sortType: sira && sira.yon, filters: [] }, data: veri || {} }; }
  async borc() {
    const ozet = await this.istek("POST", GW + "/payment/api/debtinformation-homepage-summary/false", { meta: { filters: [], pagination: { pageNo: 1, pageSize: 50 } } }, true);
    let liste = null, listeHata = "";
    try { liste = await this.istek("POST", GW + "/payment/api/debtinformation/1", this.tablo({}, 100, { alan: "vdAdi", yon: "ASC" }), true); }
    catch (e) { if (e.oturum) throw e; listeHata = e.message; }
    const k = liste ? kayitlar(liste) : [];
    return { kayitlar: k.length ? k : kayitlar(ozet), ozet: kayitlar(ozet), sekil: { ozet: sekil(ozet), liste: liste ? sekil(liste) : listeHata } };
  }
  async tebligat() {
    let say = null; try { say = await this.istek("GET", GW + "/etebligat/etebligat/tebligat-sayilari", undefined, true); } catch (e) { if (e.oturum) throw e; }
    const liste = await this.istek("POST", GW + "/etebligat/etebligat/tebligat-listele", this.tablo({}, 100, { alan: "tebligTarihi", yon: "DESC" }), true);
    return { kayitlar: kayitlar(liste), say: say ? kayitlar(say)[0] || null : null, sekil: { sayilar: sekil(say), liste: sekil(liste) } };
  }
  /* gelen e-Arşiv: portal en çok 7 günlük aralık kabul eder; bas/bit "GG/AA/YYYY" */
  async gelen(bas, bit) {
    const par = (t) => { const [g, a, y] = t.split("/").map(Number); return Date.UTC(y, a - 1, g); };
    const yaz = (ms) => { const d = new Date(ms); return String(d.getUTCDate()).padStart(2, "0") + "/" + String(d.getUTCMonth() + 1).padStart(2, "0") + "/" + d.getUTCFullYear(); };
    const bs = par(bas), bt = par(bit); if (!(bt >= bs)) throw new Error("Bitiş tarihi başlangıçtan önce olamaz.");
    if ((bt - bs) / 864e5 > 92) throw new Error("En çok 3 aylık aralık sorgulanabilir.");
    const hepsi = []; let ilkSekil = null;
    for (let b = bs; b <= bt; b += 7 * 864e5) {
      const s = Math.min(b + 6 * 864e5, bt);
      const y = await this.istek("POST", GW + "/eislemler/earsiv/alici-list", this.tablo({ duzenlenmeTarihiBas: yaz(b), duzenlenmeTarihiSon: yaz(s) }, 100, { alan: "faturaNo", yon: "DESC" }), true);
      if (!ilkSekil) ilkSekil = sekil(y);
      const dizi = (y && (y.resultListDenormalized || (y.data && y.data.resultListDenormalized))) || null;
      hepsi.push(...(dizi ? kayitlar(dizi) : kayitlar(y)));
    }
    return { kayitlar: hepsi.slice(0, 500), sekil: ilkSekil };
  }
}

/* deneme kipi: gerçek GİB'e gitmez. Doğrulama kodu her zaman "7K3PQ2". */
class SahteIvd {
  constructor(k) { this.k = k; this.token = null; this.cid = null; }
  get girildi() { return !!this.token; }
  async cikis() { this.token = null; this.cid = null; }
  async captcha() {
    this.cid = "sahte";
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="50"><rect width="160" height="50" fill="#eef"/><text x="14" y="36" font-size="30" font-family="monospace" fill="#223">7K3PQ2</text></svg>';
    return { resim: "data:image/svg+xml;base64," + Buffer.from(svg).toString("base64") };
  }
  async giris(dk) {
    if (!this.cid) throw new Error("Önce doğrulama kodu resmini isteyin.");
    this.cid = null;
    if (String(dk || "").trim().toUpperCase() !== "7K3PQ2") { const e = new Error("Dijital Vergi Dairesi girişi başarısız: Doğrulama kodu hatalı."); e.giris = true; throw e; }
    this.token = "sahte-token";
  }
  async borc() {
    const d = [
      { vdAdi: "Örnek V.D.", vergiTuru: "Muhtasar ve Prim Hizmet", donem: "2026/08", vadeTarihi: "26.09.2026", borcTutari: 12400, gecikmeZammi: 541.6, durum: "Vadesi geçmiş" },
      { vdAdi: "Örnek V.D.", vergiTuru: "KDV", donem: "2026/09", vadeTarihi: "26.10.2026", borcTutari: 35850, gecikmeZammi: 0, durum: "Ödenmedi" }
    ];
    return { kayitlar: kayitlar(d), ozet: [{ toplamBorc: 48250 }], sekil: sekil({ ozet: { toplamBorc: 1 }, liste: d }) };
  }
  async tebligat() { const d = [{ belgeTuru: "Ödeme emri", tebligTarihi: "18.10.2026", durum: "Okunmadı", gonderen: "Vergi Dairesi Müdürlüğü" }, { belgeTuru: "Bilgi isteme yazısı", tebligTarihi: "15.10.2026", durum: "Okunmadı", gonderen: "Vergi Dairesi Müdürlüğü" }, { belgeTuru: "Tahakkuk bildirimi", tebligTarihi: "28.08.2026", durum: "Okundu", gonderen: "Vergi Dairesi Müdürlüğü" }]; return { kayitlar: kayitlar(d), say: { okunmamis: 2 }, sekil: sekil(d) }; }
  async gelen() { const d = [{ unvan: "ÖRNEK TEDARİKÇİ A.Ş.", faturaNo: "ABC2026000000012", duzenlenmeTarihi: "12.10.2026", toplamTutar: 11800, odenecekTutar: 11800, paraBirimi: "TRY" }]; return { kayitlar: kayitlar(d), sekil: sekil(d) }; }
}

module.exports = { istemci: (k, s) => (MOCK ? new SahteIvd(k) : new Ivd(k, s)), sekil, kayitlar };
