/* SGK İşveren Sistemi (uyg.sgk.gov.tr/IsverenSistemi) istemcisi: borç görüntüleme ve borcu yoktur belgesi için.
 *
 * Giriş yarı otomatiktir: güvenlik kodu (captcha) resmi alınır, kullanıcı yazar, sonra mükellefin kayıtlı SGK bilgileriyle giriş yapılır.
 * DİKKAT: Resmî bir API yoktur; sistem klasik form/oturum çerezi ile çalışır. Adresler değişebilir. Art arda hızlı isteklere sunucu tarafında kısa bekleme uygulanır. Yalnız uyg.sgk.gov.tr adresine gidilir. */
"use strict";
const MOCK = process.env.GIB_MOCK === "1";
/* iki ayrı SGK sistemi: İşveren Sistemi (borç, borcu yoktur) ve e-Bildirge (onaylı bildirgeler); ikisinin girişi aynı biçimdedir */
const SISTEMLER = { isveren: { sunucu: "uyg.sgk.gov.tr", kok: "/IsverenSistemi" }, ebildirge: { sunucu: "ebildirge.sgk.gov.tr", kok: "/EBildirgeV2" } };
const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36";

const sade = (h) => String(h || "").replace(/<script[\s\S]*?<\/script>/gi, " ").replace(/<style[\s\S]*?<\/style>/gi, " ").replace(/<[^>]+>/g, " ").replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/\s+/g, " ").trim();
function hataMetni(html) {
  /* 1) bilinen hata kapları (Struts actionError/errorMessage, kırmızı yazı, alert) */
  const aday = [];
  for (const m of html.matchAll(/<(?:ul|div|span)\b[^>]*class\s*=\s*["'][^"']*(?:errorMessage|actionError|fieldError|error|hata|uyari)[^"']*["'][^>]*>([\s\S]*?)<\/(?:ul|div|span)>/gi)) aday.push(sade(m[1]));
  for (const m of html.matchAll(/alert\(\s*["']([^"']{3,200})["']/gi)) aday.push(m[1]);
  for (const m of html.matchAll(/<(?:font|span|p|div|td|li)\b[^>]*(?:color\s*[:=]\s*["']?\s*(?:red|#f00|#ff0000|#c00|#cc0000))[^>]*>([\s\S]*?)<\/(?:font|span|p|div|td|li)>/gi)) aday.push(sade(m[1]));
  const bulunan = aday.map((x) => x.trim()).filter((x) => x && x.length < 240)[0];
  if (bulunan) return bulunan;
  /* 2) bilinen sayfa metinlerini çıkarıp kalan metne bak (başlık/alt bilgi/yükleniyor yazısı hata sayılmaz) */
  let t = sade(html);
  for (const k of ["İşlem Devam Ediyor Lütfen Bekleyiniz!", "T.C. SOSYAL GÜVENLİK KURUMU", "T.C. Sosyal Güvenlik Kurumu", "SGK ANA SAYFA", "İşveren Sistemi Kullanıcı Girişi", "Kullanıcı Adı", "Sistem Şifresi", "İşyeri Şifresi", "Lütfen Güvenlik Anahtarını yanında bulunan kutuya yazıp GİRİŞ tuşuna basınız.", "Giriş Yap", "Türkiye Cumhuriyeti Sosyal Güvenlik Kurumu © 2012", "İletişim", "Loading..."]) t = t.split(k).join(" ");
  t = t.replace(/\s+/g, " ").replace(/^[\s\-]+|[\s\-]+$/g, "").trim();
  return t && t.length > 3 ? t.slice(0, 240) : "";
}
/* sayfadaki bağlantılar ve form adresleri (tanı için; kişisel veri içermez) */
function baglantilar(html) {
  const o = [], gor = new Set();
  const ekle = (metin, href, tur) => { href = String(href || "").trim(); if (!href || /^(javascript:void|#)/i.test(href) && tur === "a") return; const k = tur + "|" + href + "|" + metin; if (gor.has(k)) return; gor.add(k); o.push({ tur, metin: sade(metin).slice(0, 80), href: href.slice(0, 200) }); };
  for (const m of html.matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a>/gi)) { const a = m[1], href = (/href\s*=\s*["']([^"']*)["']/i.exec(a) || [])[1], on = (/onclick\s*=\s*["']([^"']*)["']/i.exec(a) || [])[1]; if (href) ekle(m[2], href, "a"); if (on) ekle(m[2], on, "onclick"); }
  for (const m of html.matchAll(/<form\b[^>]*action\s*=\s*["']([^"']*)["']/gi)) ekle("(form)", m[1], "form");
  for (const m of html.matchAll(/<i?frame\b[^>]*src\s*=\s*["']([^"']*)["']/gi)) ekle("(çerçeve)", m[1], "frame");
  for (const m of html.matchAll(/["'](\/(?:IsverenSistemi|EBildirgeV2)\/[A-Za-z0-9_\/.\-]+\.(?:action|jsp|do|html)[^"']*)["']/g)) ekle("(betik)", m[1], "betik");
  return o.slice(0, 250);
}

/* Giriş sonrası SGK önce "Uygulama Çalıştırılıyor / UYGULAMA BAŞLATILDI" başlatıcı sayfasını verir; uygulama ayrı bir pencerede (window.open) açılır.
 * Burada o pencerenin adresi bulunur ve aynı oturumla açılır. */
const basliyorMu = (h) => /UYGULAMA BAŞLATILDI|Uygulama Çalıştırılıyor/i.test(h);
const anaSayfaMi = (h) => /<frameset/i.test(h) || /İŞVEREN TESCİL|E-BORCU YOKTUR|Onaylanmış Belgeler|Aylık Prim Hizmet Belgesi|ÇIKIŞ|Çıkış/.test(h);
function devamAdresleri(html, taban) {
  const aday = [], ekle = (x) => { x = String(x || "").trim(); if (!x || /^(javascript:|#|mailto:)/i.test(x)) return; try { const u = new URL(x, taban).href; if (!aday.includes(u)) aday.push(u); } catch (e) { /* geçersiz */ } };
  for (const m of html.matchAll(/window\.open\(\s*["']([^"']+)["']/gi)) ekle(m[1]);
  for (const m of html.matchAll(/<meta[^>]+http-equiv\s*=\s*["']?refresh["']?[^>]*content\s*=\s*["'][^"']*url\s*=\s*([^"'>\s]+)/gi)) ekle(m[1]);
  for (const m of html.matchAll(/(?:location(?:\.href)?\s*=|location\.(?:replace|assign)\()\s*["']([^"']+)["']/gi)) ekle(m[1]);
  for (const m of html.matchAll(/<i?frame\b[^>]*src\s*=\s*["']([^"']+)["']/gi)) ekle(m[1]);
  for (const m of html.matchAll(/<a\b[^>]*href\s*=\s*["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi)) if (/ana\s*sayfa|devam|başlat/i.test(sade(m[2]))) ekle(m[1]);
  for (const m of html.matchAll(/["'](\/(?:IsverenSistemi|EBildirgeV2)\/[A-Za-z0-9_\/.\-]+\.(?:action|jsp|do|html)[^"']*)["']/g)) ekle(m[1]);
  return aday.filter((u) => !/\/login\/|kullaniciIlkKontrollerGiris/.test(u));
}

/* sayfadaki formlar (alan adları, seçenekler) ve tablo başlıkları: adres/alan keşfi için; değerler maskelenir */
function formlar(html) {
  const o = [];
  for (const f of html.matchAll(/<form\b([^>]*)>([\s\S]*?)<\/form>/gi)) {
    const a = f[1], eylem = (/action\s*=\s*["']([^"']*)["']/i.exec(a) || [])[1] || "", yontem = ((/method\s*=\s*["']?(\w+)/i.exec(a) || [])[1] || "get").toLowerCase(), alanlar = [];
    for (const i of f[2].matchAll(/<input\b([^>]*)>/gi)) { const n = (/name\s*=\s*["']([^"']*)["']/i.exec(i[1]) || [])[1], t = ((/type\s*=\s*["']?(\w+)/i.exec(i[1]) || [])[1] || "text").toLowerCase(); if (n) alanlar.push(n + ":" + t + (t === "hidden" ? "=" + String((/value\s*=\s*["']([^"']*)["']/i.exec(i[1]) || [])[1] || "").slice(0, 20) : "")); }
    for (const sl of f[2].matchAll(/<select\b([^>]*)>([\s\S]*?)<\/select>/gi)) { const n = (/name\s*=\s*["']([^"']*)["']/i.exec(sl[1]) || [])[1]; const ops = [...sl[2].matchAll(/<option\b[^>]*value\s*=\s*["']([^"']*)["']/gi)].map((x) => x[1]); if (n) alanlar.push(n + ":select[" + ops.slice(0, 6).join("|") + (ops.length > 6 ? "|…" + ops.length : "") + "]"); }
    for (const b of f[2].matchAll(/<(?:button|input)\b[^>]*(?:type\s*=\s*["']?(?:submit|button)["']?)[^>]*>/gi)) { const n = (/(?:name|value|onclick)\s*=\s*["']([^"']{1,80})["']/i.exec(b[0]) || [])[1]; if (n) alanlar.push("düğme:" + n); }
    o.push({ eylem, yontem, alanlar: alanlar.slice(0, 30) });
  }
  return o.slice(0, 6);
}
const tablolar = (html) => [...html.matchAll(/<table\b[\s\S]*?<\/table>/gi)].map((t) => [...t[0].matchAll(/<th\b[^>]*>([\s\S]*?)<\/th>/gi)].map((x) => sade(x[1]).slice(0, 30)).filter(Boolean)).filter((b) => b.length > 1).slice(0, 4);

class Sgk {
  constructor(k, sistem) { this.k = k || {}; this.s = SISTEMLER[sistem] || SISTEMLER.isveren; this.taban = "https://" + this.s.sunucu; this.cerez = new Map(); /* alan adı -> çerezler */ this.girdi = false; this.ana = ""; }
  cerezTopla(r, host) { let j = this.cerez.get(host); if (!j) { j = new Map(); this.cerez.set(host, j); } for (const sc of (typeof r.headers.getSetCookie === "function" ? r.headers.getSetCookie() : [])) { const kv = sc.split(";")[0].trim(), i = kv.indexOf("="); if (i > 0) j.set(kv.slice(0, i), kv.slice(i + 1)); } }
  async git(yontem, yol, govde) {
    let url = /^https?:/i.test(yol) ? yol : this.taban + yol;
    for (let n = 0; n < 6; n++) {
      let u; try { u = new URL(url); } catch (e) { throw new Error("SGK adresi geçersiz."); }
      if (u.protocol === "http:") u.protocol = "https:"; // SGK yönlendirmeleri bazen http gösterir
      if (u.protocol !== "https:" || !/(^|\.)sgk\.gov\.tr$/i.test(u.hostname)) throw new Error("SGK yönlendirmesi beklenmeyen bir adrese gitti (" + String(u.hostname).slice(0, 60) + "); durduruldu.");
      url = u.href;
      const h = { "user-agent": UA, accept: "text/html,application/xhtml+xml,image/*,*/*;q=0.8", "accept-language": "tr-TR,tr;q=0.9" };
      const kavanoz = this.cerez.get(u.hostname); if (kavanoz && kavanoz.size) h.cookie = [...kavanoz].map(([a, d]) => a + "=" + d).join("; ");
      if (govde) { h["content-type"] = "application/x-www-form-urlencoded"; h.referer = this.taban + this.s.kok; h.origin = this.taban; }
      let r;
      try { r = await fetch(url, { method: yontem, headers: h, body: govde ? new URLSearchParams(govde) : undefined, redirect: "manual", signal: AbortSignal.timeout(25000) }); }
      catch (e) { throw new Error(e && (e.name === "TimeoutError" || e.name === "AbortError") ? "SGK 25 saniyede yanıt vermedi (zaman aşımı)." : "SGK'ya ulaşılamadı: " + e.message); }
      this.cerezTopla(r, u.hostname);
      if ([301, 302, 303, 307, 308].includes(r.status)) { url = new URL(r.headers.get("location") || "/", url).href; yontem = "GET"; govde = null; continue; }
      return { durum: r.status, url, tur: r.headers.get("content-type") || "", veri: Buffer.from(await r.arrayBuffer()) };
    }
    throw new Error("SGK çok fazla yönlendirme yaptı.");
  }
  async captcha() {
    this.cerez.clear(); this.girdi = false;
    await this.git("GET", this.s.kok);
    const r = await this.git("GET", this.s.kok + "/PG?" + Date.now());
    if (!/^image\//i.test(r.tur) || !r.veri.length) throw new Error("SGK güvenlik kodu resmini vermedi.");
    return { resim: "data:" + r.tur.split(";")[0] + ";base64," + r.veri.toString("base64") };
  }
  async giris(dk) {
    const k = this.k;
    const r = await this.git("POST", this.s.kok + "/login/kullaniciIlkKontrollerGiris.action", { username: k.kullanici, isyeri_kod: k.isyeriKod, password: k.sistemSifre, isyeri_sifre: k.isyeriSifre, isyeri_guvenlik: String(dk || "").trim() });
    let html = r.veri.toString("utf8"), url = r.url;
    if (/kullaniciIlkKontrollerGiris/.test(html)) {
      const m = hataMetni(html);
      const e = new Error("SGK girişi kabul edilmedi" + (m ? ": " + m : ": SGK aynı giriş formunu yeniden gösterdi, ayrı bir hata metni vermedi. Güvenlik kodu (resimdeki gibi, büyük/küçük harf aynen), kullanıcı adı, işyeri kodu ve iki şifreyi kontrol edin") + ".");
      e.giris = true; throw e;
    }
    /* başlatıcı sayfa(lar)dan gerçek uygulama penceresine geç */
    this.zincir = [url]; this.sayfalar = [{ url, html }]; const denenen = new Set([url]);
    for (let n = 0; n < 4 && !anaSayfaMi(html) && (basliyorMu(html) || n === 0); n++) {
      const sonraki = devamAdresleri(html, url).find((u) => !denenen.has(u)); if (!sonraki) break;
      denenen.add(sonraki);
      try { const r2 = await this.git("GET", sonraki); html = r2.veri.toString("utf8"); url = r2.url; this.zincir.push(url); this.sayfalar.push({ url, html }); }
      catch (e) { if (n === 0) throw e; break; }
    }
    if (/kullaniciIlkKontrollerGiris/.test(html)) { const e = new Error("SGK oturumu açılamadı: uygulama penceresi giriş sayfasına döndü."); e.giris = true; throw e; }
    this.girdi = true; this.ana = html; this.anaUrl = url;
  }
  /* giriş sonrası ana sayfadaki bağlantılar (adres keşfi için tanı) */
  async tani(derin) {
    if (!this.girdi) throw this.oturumHata();
    const liste = baglantilar(this.ana);
    const ilk = this.sayfalar && this.sayfalar.length > 1 ? baglantilar(this.sayfalar[0].html).map((x) => Object.assign({ not: "başlatıcı sayfa" }, x)) : [];
    const cerceveler = liste.filter((x) => x.tur === "frame").slice(0, 4), ek = [], tum = liste.slice();
    for (const c of cerceveler) { try { const r = await this.git("GET", new URL(c.href, this.anaUrl).href); const b = baglantilar(r.veri.toString("utf8")); ek.push({ kaynak: c.href, baglantilar: b }); tum.push(...b); } catch (e) { ek.push({ kaynak: c.href, hata: e.message }); } }
    const sonuc = { baslik: (/<title>([\s\S]*?)<\/title>/i.exec(this.ana) || [])[1] || "", baglantilar: liste, baslatici: ilk, zincir: this.zincir || [], cerceveler: ek, adres: this.anaUrl };
    if (derin) { /* menü sayfalarını gez (yalnız okuma: GET); çıkış bağlantıları atlanır */
      const adaylar = [], gor = new Set();
      for (const x of tum) { if (x.tur !== "a" || !/\.(?:action|jsp|do)/i.test(x.href) || /çıkış|cikis|logout|exit/i.test(x.metin + x.href)) continue; const u = new URL(x.href, this.anaUrl).href; if (gor.has(u)) continue; gor.add(u); adaylar.push({ metin: x.metin, u }); }
      sonuc.sayfalar = [];
      for (const a of adaylar.slice(0, 12)) { try { const r = await this.git("GET", a.u); const h = r.veri.toString("utf8"); sonuc.sayfalar.push({ metin: a.metin, adres: a.u.replace(this.taban, ""), formlar: formlar(h), tablolar: tablolar(h), baglantilar: baglantilar(h).slice(0, 15) }); } catch (e) { sonuc.sayfalar.push({ metin: a.metin, adres: a.u.replace(this.taban, ""), hata: e.message }); } }
    }
    return sonuc;
  }
  oturumHata() { const e = new Error("SGK oturumu kapandı; güvenlik koduyla yeniden bağlanın."); e.oturum = true; return e; }
  async cikis() {
    if (this.girdi) { const c = baglantilar(this.ana).find((x) => /çıkış|cikis|logout/i.test(x.metin + x.href) && x.tur === "a"); if (c) { try { await this.git("GET", new URL(c.href, this.anaUrl).href); } catch (e) { /* önemli değil */ } } }
    this.girdi = false; this.cerez.clear(); this.ana = "";
  }
}

/* deneme kipi: gerçek SGK'ya gitmez. Güvenlik kodu "SGK123" */
class SahteSgk {
  constructor(k, sistem) { this.k = k || {}; this.sistem = sistem || "isveren"; this.girdi = false; this.cid = false; }
  async captcha() { this.cid = true; const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="50"><rect width="160" height="50" fill="#e8e0d8"/><text x="14" y="36" font-size="30" font-family="monospace" fill="#a33">SGK123</text></svg>'; return { resim: "data:image/svg+xml;base64," + Buffer.from(svg).toString("base64") }; }
  async giris(dk) { if (!this.cid) throw new Error("Önce güvenlik kodu resmini isteyin."); this.cid = false; if (String(dk || "").trim() !== "SGK123") { const e = new Error("SGK girişi başarısız: Güvenlik kodu hatalı."); e.giris = true; throw e; } this.girdi = true; }
  async tani(derin) { if (!this.girdi) { const e = new Error("SGK oturumu kapandı; güvenlik koduyla yeniden bağlanın."); e.oturum = true; throw e; } return { baslik: "T.C. Sosyal Güvenlik Kurumu", adres: "https://" + (SISTEMLER[this.sistem] || SISTEMLER.isveren).sunucu + (SISTEMLER[this.sistem] || SISTEMLER.isveren).kok, zincir: [], baslatici: [], baglantilar: [{ tur: "a", metin: "DÖNEM BORÇ GÖRÜNTÜLEME", href: "/IsverenSistemi/ornek/donemBorc.action" }, { tur: "a", metin: "İHALELERE KATILMAK İÇİN", href: "/IsverenSistemi/ornek/ihale.action" }, { tur: "a", metin: "ÇIKIŞ", href: "/IsverenSistemi/cikis.action" }], cerceveler: [], sayfalar: derin ? [{ metin: "Onaylanmış Belgeler", adres: "/EBildirgeV2/ornek/onayli.action", formlar: [{ eylem: "/EBildirgeV2/ornek/liste.action", yontem: "post", alanlar: ["bas_donem:select[2026/09|2026/08]", "bit_donem:select[2026/09|2026/08]", "düğme:Bilgileri Getir"] }], tablolar: [["Tahakkuk Yıl/Ay", "Hizmet Yıl/Ay", "Belge Türü", "Toplam Çalışan Sayısı"]], baglantilar: [] }] : undefined }; }
  async cikis() { this.girdi = false; }
}

module.exports = { istemci: (k, sistem) => (MOCK ? new SahteSgk(k, sistem) : new Sgk(k, sistem)), baglantilar, hataMetni, devamAdresleri, basliyorMu, anaSayfaMi };
