/* Dijital Vergi Dairesi (eski İnteraktif Vergi Dairesi) istemcisi: borç durumu, mesajlar/tebligat benzeri bildirimler, ceza ihbarnameleri.
 *
 * DİKKAT: GİB'in resmî bir API'si yoktur. Giriş ve komut adları açık kaynak kütüphanelerden (mlevent/ivd, ibrcan/ivd) alınmıştır ve
 * GİB tarafından bir gün değiştirilebilir. Bu dosya gerçek hesapla henüz doğrulanmamıştır; bu yüzden her yanıtın "şekli" (anahtarlar ve türler,
 * değerler maskeli) tanı için ayrıca üretilir. Giriş başarısız olursa kullanıcı kodunu kilitlememek için sunucu tarafında bekleme uygulanır. */
"use strict";
const crypto = require("crypto");

const MOCK = process.env.GIB_MOCK === "1";
const BASE = "https://ivd.gib.gov.tr";

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
  constructor(kullanici, sifre) { this.k = kullanici; this.s = sifre; this.token = null; this.cerez = new Map(); }
  cerezTopla(r) {
    const liste = typeof r.headers.getSetCookie === "function" ? r.headers.getSetCookie() : [];
    for (const sc of liste) { const kv = sc.split(";")[0].trim(), i = kv.indexOf("="); if (i > 0) this.cerez.set(kv.slice(0, i), kv.slice(i + 1)); }
  }
  async post(yol, alanlar) {
    const baslik = { "content-type": "application/x-www-form-urlencoded;charset=UTF-8", "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36" };
    if (this.cerez.size) baslik.cookie = [...this.cerez].map(([a, d]) => a + "=" + d).join("; ");
    let r;
    try { r = await fetch(BASE + yol, { method: "POST", headers: baslik, body: new URLSearchParams(alanlar), signal: AbortSignal.timeout(25000) }); }
    catch (e) { throw new Error(e && (e.name === "TimeoutError" || e.name === "AbortError") ? "Dijital Vergi Dairesi 25 saniyede yanıt vermedi (zaman aşımı)." : "Dijital Vergi Dairesi'ne ulaşılamadı: " + e.message); }
    this.cerezTopla(r);
    const t = await r.text();
    try { return JSON.parse(t); } catch (e) { throw new Error("Dijital Vergi Dairesi beklenmeyen yanıt verdi (HTTP " + r.status + ", " + (/^\s*</.test(t) ? "HTML sayfa" : "JSON değil") + ")."); }
  }
  async giris() {
    const y = await this.post("/tvd_server/assos-login", { assoscmd: "multilogin", rtype: "json", userid: this.k, sifre: this.s, parola: "maliye", controlCaptcha: "false", dk: "", imageID: "" });
    if (!y || !y.token) {
      const m = (y && y.messages && y.messages[0] && (y.messages[0].text || y.messages[0])) || (y && (y.error || y.hata)) || "";
      const e = new Error("Dijital Vergi Dairesi girişi başarısız" + (m ? ": " + String(m).slice(0, 200) : " (yanıt kullanıcı kodu/şifre kabul etmedi ya da ek doğrulama istiyor olabilir)") + ".");
      e.giris = true; e.anahtarlar = y && typeof y === "object" ? Object.keys(y).slice(0, 15) : []; throw e;
    }
    this.token = y.token;
  }
  async cikis() {
    const t = this.token; this.token = null; if (!t) { this.cerez.clear(); return; }
    try { await this.dispatchHam("kullaniciBilgileriService_logout", "PG_MAIN_DYNAMIC", "cbf1b5447b6cc-44", {}, t); } catch (e) { /* önemli değil */ }
    this.cerez.clear();
  }
  async dispatchHam(cmd, sayfa, callid, jp, token) {
    return this.post("/tvd_server/dispatch", { cmd, callid, pageName: sayfa, token: token || this.token, jp: JSON.stringify(jp || {}) });
  }
  async dispatch(cmd, sayfa, callid, jp) {
    if (!this.token) await this.giris();
    const y = await this.dispatchHam(cmd, sayfa, callid || crypto.randomUUID(), jp);
    const hata = y && (y.error || (y.data && y.data.hata));
    if (hata) {
      /* GİB hatayı { error: "1", messages: [{ text }] } biçiminde verir; asıl metin messages içindedir */
      const msj = (y.messages || []).map((m) => (m && (m.text || m.message)) || (typeof m === "string" ? m : "")).filter(Boolean).join(" | ");
      const ham = JSON.stringify(Object.assign({}, y, { token: undefined })).replace(/\s+/g, " ").slice(0, 300);
      console.log("Dijital Vergi Dairesi komut hatası (" + cmd + "): " + ham);
      throw new Error("Dijital Vergi Dairesi hatası (" + cmd + "): " + (msj || (typeof hata === "string" && hata.length > 2 ? hata : "ayrıntı yok")) + (msj ? "" : " [yanıt: " + ham.slice(0, 160) + "]"));
    }
    return y.data !== undefined ? y.data : y;
  }
  /* sorgular; her biri { kayitlar, sekil } döndürür */
  async borc() { const d = await this.dispatch("tvdBorcIslemleri_borcGetirYeni", "P_DASHBOARD", "e95931c2f24ce-145", {}); return { kayitlar: kayitlar(d), sekil: sekil(d) }; }
  /* oturumun GERÇEKTEN o kullanıcıya ait olup olmadığını sınar: kendi sicil/kimlik bilgisini ister (token almak giriş yapıldığını kanıtlamaz, misafir oturumu da token verir) */
  async dene() { const d = await this.dispatch("sicilIslemleri_evdoYsicilTckimliknoVknCevrimiMernisAdsoyad", "RG_SICIL", "151218977cdcc-29", {}); const k = kayitlar(d); return { kayitlar: k.map((r) => { const o = {}; for (const [a, v] of Object.entries(r)) o[a] = /tc|vkn|kimlik|no$/i.test(a) && typeof v !== "object" ? String(v).replace(/\d(?=\d{3})/g, "*") : v; return o; }), sekil: sekil(d), bilgi: "Giriş doğrulandı: oturum kullanıcı bilgisini döndürdü (kimlik numaraları maskelendi)." }; }
  async mesajlar() { const d = await this.dispatch("kullaniciMesajlariService_kullaniciMesajlariGetir", "PG_MAIN_DYNAMIC", "e61d39920010c-61", {}); return { kayitlar: kayitlar(d), sekil: sekil(d) }; }
  async cezaIhbar() { const d = await this.dispatch("cezaIhbarnameleriService_cezaIhbarnameleriGetir", "P_CEZA_IHBARNAMELERI", "0861bf80b5f42-37", {}); return { kayitlar: kayitlar(d), sekil: sekil(d) }; }
}

/* deneme kipi: gerçek GİB'e gitmez */
class SahteIvd {
  constructor(k) { this.k = k; }
  async cikis() {}
  async borc() {
    const d = { borcListesi: [
      { vergiTuru: "Muhtasar ve Prim Hizmet", donem: "2026/08", vadeTarihi: "26.09.2026", borcTutari: 12400, gecikmeZammi: 541.6, durum: "Vadesi geçmiş" },
      { vergiTuru: "KDV", donem: "2026/09", vadeTarihi: "26.10.2026", borcTutari: 35850, gecikmeZammi: 0, durum: "Ödenmedi" }
    ], toplamBorc: 48250 };
    return { kayitlar: kayitlar(d.borcListesi), sekil: sekil(d), ozet: d.toplamBorc };
  }
  async mesajlar() { const d = [{ konu: "Ödeme emri", tarih: "18.10.2026", durum: "Okunmadı", gonderen: "Vergi Dairesi Müdürlüğü" }, { konu: "Bilgi isteme yazısı", tarih: "15.10.2026", durum: "Okunmadı", gonderen: "Vergi Dairesi Müdürlüğü" }, { konu: "Tahakkuk bildirimi", tarih: "28.08.2026", durum: "Okundu", gonderen: "Vergi Dairesi Müdürlüğü" }]; return { kayitlar: kayitlar(d), sekil: sekil(d) }; }
  async cezaIhbar() { return { kayitlar: [], sekil: [] }; }
  async dene() { const d = [{ adSoyad: "ÖRNEK KİŞİ", tckn: "1234567890" }]; return { kayitlar: kayitlar(d), sekil: sekil(d), bilgi: "Giriş doğrulandı (deneme kipi)." }; }
}

module.exports = { istemci: (k, s) => (MOCK ? new SahteIvd(k) : new Ivd(k, s)), sekil, kayitlar };
