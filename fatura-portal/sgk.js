/* SGK İşveren Sistemi (uyg.sgk.gov.tr/IsverenSistemi) istemcisi: borç görüntüleme ve borcu yoktur belgesi için.
 *
 * Giriş yarı otomatiktir: güvenlik kodu (captcha) resmi alınır, kullanıcı yazar, sonra mükellefin kayıtlı SGK bilgileriyle giriş yapılır.
 * DİKKAT: Resmî bir API yoktur; sistem klasik form/oturum çerezi ile çalışır. Adresler değişebilir. Yanlış şifreyle art arda denemede SGK
 * şifreyi kilitleyebilir; bu yüzden sunucu tarafında bekleme uygulanır. Yalnız uyg.sgk.gov.tr adresine gidilir. */
"use strict";
const MOCK = process.env.GIB_MOCK === "1";
const SUNUCU = "uyg.sgk.gov.tr", TABAN = "https://" + SUNUCU, GIRIS = "/IsverenSistemi";
const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36";

const sade = (h) => String(h || "").replace(/<script[\s\S]*?<\/script>/gi, " ").replace(/<style[\s\S]*?<\/style>/gi, " ").replace(/<[^>]+>/g, " ").replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/\s+/g, " ").trim();
function hataMetni(html) {
  const m = []; const t = sade(html);
  for (const s of t.split(/(?<=[.!?])\s+/)) if (/hatal|yanlış|geçersiz|güvenlik|bloke|kilit|bulunamad|süresi|izin|yetki/i.test(s) && s.length < 220) m.push(s);
  return (m.slice(0, 2).join(" ") || "").slice(0, 240);
}
/* sayfadaki bağlantılar ve form adresleri (tanı için; kişisel veri içermez) */
function baglantilar(html) {
  const o = [], gor = new Set();
  const ekle = (metin, href, tur) => { href = String(href || "").trim(); if (!href || /^(javascript:void|#)/i.test(href) && tur === "a") return; const k = tur + "|" + href + "|" + metin; if (gor.has(k)) return; gor.add(k); o.push({ tur, metin: sade(metin).slice(0, 80), href: href.slice(0, 200) }); };
  for (const m of html.matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a>/gi)) { const a = m[1], href = (/href\s*=\s*["']([^"']*)["']/i.exec(a) || [])[1], on = (/onclick\s*=\s*["']([^"']*)["']/i.exec(a) || [])[1]; if (href) ekle(m[2], href, "a"); if (on) ekle(m[2], on, "onclick"); }
  for (const m of html.matchAll(/<form\b[^>]*action\s*=\s*["']([^"']*)["']/gi)) ekle("(form)", m[1], "form");
  for (const m of html.matchAll(/<i?frame\b[^>]*src\s*=\s*["']([^"']*)["']/gi)) ekle("(çerçeve)", m[1], "frame");
  for (const m of html.matchAll(/["'](\/IsverenSistemi\/[A-Za-z0-9_\/.\-]+\.(?:action|jsp|do|html)[^"']*)["']/g)) ekle("(betik)", m[1], "betik");
  return o.slice(0, 250);
}

class Sgk {
  constructor(k) { this.k = k || {}; this.cerez = new Map(); this.girdi = false; this.ana = ""; }
  cerezTopla(r) { for (const sc of (typeof r.headers.getSetCookie === "function" ? r.headers.getSetCookie() : [])) { const kv = sc.split(";")[0].trim(), i = kv.indexOf("="); if (i > 0) this.cerez.set(kv.slice(0, i), kv.slice(i + 1)); } }
  async git(yontem, yol, govde) {
    let url = /^https?:/i.test(yol) ? yol : TABAN + yol;
    for (let n = 0; n < 6; n++) {
      let u; try { u = new URL(url); } catch (e) { throw new Error("SGK adresi geçersiz."); }
      if (u.protocol !== "https:" || u.hostname !== SUNUCU) throw new Error("SGK yönlendirmesi beklenmeyen bir adrese gitti; durduruldu.");
      const h = { "user-agent": UA, accept: "text/html,application/xhtml+xml,image/*,*/*;q=0.8", "accept-language": "tr-TR,tr;q=0.9" };
      if (this.cerez.size) h.cookie = [...this.cerez].map(([a, d]) => a + "=" + d).join("; ");
      if (govde) { h["content-type"] = "application/x-www-form-urlencoded"; h.referer = TABAN + GIRIS; h.origin = TABAN; }
      let r;
      try { r = await fetch(url, { method: yontem, headers: h, body: govde ? new URLSearchParams(govde) : undefined, redirect: "manual", signal: AbortSignal.timeout(25000) }); }
      catch (e) { throw new Error(e && (e.name === "TimeoutError" || e.name === "AbortError") ? "SGK 25 saniyede yanıt vermedi (zaman aşımı)." : "SGK'ya ulaşılamadı: " + e.message); }
      this.cerezTopla(r);
      if ([301, 302, 303, 307, 308].includes(r.status)) { url = new URL(r.headers.get("location") || "/", url).href; yontem = "GET"; govde = null; continue; }
      return { durum: r.status, url, tur: r.headers.get("content-type") || "", veri: Buffer.from(await r.arrayBuffer()) };
    }
    throw new Error("SGK çok fazla yönlendirme yaptı.");
  }
  async captcha() {
    this.cerez.clear(); this.girdi = false;
    await this.git("GET", GIRIS);
    const r = await this.git("GET", GIRIS + "/PG?" + Date.now());
    if (!/^image\//i.test(r.tur) || !r.veri.length) throw new Error("SGK güvenlik kodu resmini vermedi.");
    return { resim: "data:" + r.tur.split(";")[0] + ";base64," + r.veri.toString("base64") };
  }
  async giris(dk) {
    const k = this.k;
    const r = await this.git("POST", GIRIS + "/login/kullaniciIlkKontrollerGiris.action", { username: k.kullanici, isyeri_kod: k.isyeriKod, password: k.sistemSifre, isyeri_sifre: k.isyeriSifre, isyeri_guvenlik: String(dk || "").trim() });
    const html = r.veri.toString("utf8");
    const formVar = /kullaniciIlkKontrollerGiris/.test(html), cikisVar = /ÇIKIŞ|Çıkış|çıkış|cikis|logout/i.test(html);
    if (formVar || !cikisVar) { const m = hataMetni(html); const e = new Error("SGK girişi başarısız" + (m ? ": " + m : " (kullanıcı adı, şifreler ya da güvenlik kodu kabul edilmedi)") + "."); e.giris = true; throw e; }
    this.girdi = true; this.ana = html; this.anaUrl = r.url;
  }
  /* giriş sonrası ana sayfadaki bağlantılar (adres keşfi için tanı) */
  async tani() {
    if (!this.girdi) throw this.oturumHata();
    const liste = baglantilar(this.ana);
    const cerceveler = liste.filter((x) => x.tur === "frame").slice(0, 3), ek = [];
    for (const c of cerceveler) { try { const r = await this.git("GET", new URL(c.href, this.anaUrl).href); ek.push({ kaynak: c.href, baglantilar: baglantilar(r.veri.toString("utf8")) }); } catch (e) { ek.push({ kaynak: c.href, hata: e.message }); } }
    return { baslik: (/<title>([\s\S]*?)<\/title>/i.exec(this.ana) || [])[1] || "", baglantilar: liste, cerceveler: ek, adres: this.anaUrl };
  }
  oturumHata() { const e = new Error("SGK oturumu kapandı; güvenlik koduyla yeniden bağlanın."); e.oturum = true; return e; }
  async cikis() {
    if (this.girdi) { const c = baglantilar(this.ana).find((x) => /çıkış|cikis|logout/i.test(x.metin + x.href) && x.tur === "a"); if (c) { try { await this.git("GET", new URL(c.href, this.anaUrl).href); } catch (e) { /* önemli değil */ } } }
    this.girdi = false; this.cerez.clear(); this.ana = "";
  }
}

/* deneme kipi: gerçek SGK'ya gitmez. Güvenlik kodu "SGK123" */
class SahteSgk {
  constructor(k) { this.k = k || {}; this.girdi = false; this.cid = false; }
  async captcha() { this.cid = true; const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="50"><rect width="160" height="50" fill="#e8e0d8"/><text x="14" y="36" font-size="30" font-family="monospace" fill="#a33">SGK123</text></svg>'; return { resim: "data:image/svg+xml;base64," + Buffer.from(svg).toString("base64") }; }
  async giris(dk) { if (!this.cid) throw new Error("Önce güvenlik kodu resmini isteyin."); this.cid = false; if (String(dk || "").trim() !== "SGK123") { const e = new Error("SGK girişi başarısız: Güvenlik kodu hatalı."); e.giris = true; throw e; } this.girdi = true; }
  async tani() { if (!this.girdi) { const e = new Error("SGK oturumu kapandı; güvenlik koduyla yeniden bağlanın."); e.oturum = true; throw e; } return { baslik: "T.C. Sosyal Güvenlik Kurumu", adres: TABAN + GIRIS, baglantilar: [{ tur: "a", metin: "DÖNEM BORÇ GÖRÜNTÜLEME", href: "/IsverenSistemi/ornek/donemBorc.action" }, { tur: "a", metin: "İHALELERE KATILMAK İÇİN", href: "/IsverenSistemi/ornek/ihale.action" }, { tur: "a", metin: "ÇIKIŞ", href: "/IsverenSistemi/cikis.action" }], cerceveler: [] }; }
  async cikis() { this.girdi = false; }
}

module.exports = { istemci: (k) => (MOCK ? new SahteSgk(k) : new Sgk(k)), baglantilar, hataMetni };
