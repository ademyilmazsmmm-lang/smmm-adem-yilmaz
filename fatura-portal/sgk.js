/* SGK İşveren Sistemi (uyg.sgk.gov.tr/IsverenSistemi) istemcisi: borç görüntüleme ve borcu yoktur belgesi için.
 *
 * Giriş yarı otomatiktir: güvenlik kodu (captcha) resmi alınır, kullanıcı yazar, sonra mükellefin kayıtlı SGK bilgileriyle giriş yapılır.
 * DİKKAT: Resmî bir API yoktur; sistem klasik form/oturum çerezi ile çalışır. Adresler değişebilir. Art arda hızlı isteklere sunucu tarafında kısa bekleme uygulanır. Yalnız uyg.sgk.gov.tr adresine gidilir. */
"use strict";
const MOCK = process.env.GIB_MOCK === "1";
/* iki ayrı SGK sistemi: İşveren Sistemi (borç, borcu yoktur) ve e-Bildirge (onaylı bildirgeler); ikisinin girişi aynı biçimdedir */
const SISTEMLER = { isveren: { sunucu: "uyg.sgk.gov.tr", kok: "/IsverenSistemi" }, ebildirge: { sunucu: "ebildirge.sgk.gov.tr", kok: "/EBildirgeV2" } };
const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36";

const coz = (t) => String(t == null ? "" : t).replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/&#39;|&#x27;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&#x([0-9a-f]+);/gi, (m, h) => String.fromCodePoint(parseInt(h, 16))).replace(/&#(\d+);/g, (m, d) => String.fromCodePoint(+d)).replace(/&nbsp;/g, " ");
const nitelik = (a, ad) => { const m = new RegExp("\\b" + ad + "\\s*=\\s*(?:\"([^\"]*)\"|'([^']*)'|([^\\s>]+))", "i").exec(a); return m ? coz(m[1] !== undefined ? m[1] : m[2] !== undefined ? m[2] : m[3]) : ""; };
const ADLI = { Uuml: "Ü", uuml: "ü", Ccedil: "Ç", ccedil: "ç", Ouml: "Ö", ouml: "ö", Iuml: "Ï", iuml: "ï", Auml: "Ä", auml: "ä", acirc: "â", Acirc: "Â", icirc: "î", ucirc: "û" };
const adliCoz = (t) => String(t).replace(/&([A-Za-z]+);/g, (m, a) => (ADLI[a] != null ? ADLI[a] : m)).replace(/&#(\d+);/g, (m, d) => String.fromCharCode(Number(d)));
const sade = (h) => adliCoz(String(h || "").replace(/<script[\s\S]*?<\/script>/gi, " ").replace(/<style[\s\S]*?<\/style>/gi, " ").replace(/<[^>]+>/g, " ").replace(/&nbsp;/g, " ").replace(/&amp;/g, "&")).replace(/\s+/g, " ").trim();
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
  const ekle = (metin, href, tur) => { href = coz(href).trim(); if (!href || /^(javascript:void|#)/i.test(href) && tur === "a") return; const k = tur + "|" + href + "|" + metin; if (gor.has(k)) return; gor.add(k); o.push({ tur, metin: sade(metin).slice(0, 80), href: href.slice(0, 200) }); };
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
  for (const m of html.matchAll(/<a\b[^>]*href\s*=\s*["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi)) if (/^\s*ana\s*sayfa\s*$|devam|başlat/i.test(sade(m[2]))) ekle(m[1]);
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

/* formun gerçek alanları (gizli alanlar, seçenek değer/etiketleri) */
function formCoz(html) {
  const o = [];
  for (const f of html.matchAll(/<form\b([^>]*)>([\s\S]*?)<\/form>/gi)) {
    const gizli = {}, secimler = {};
    for (const i of f[2].matchAll(/<input\b([^>]*)>/gi)) { const n = nitelik(i[1], "name"), t = (nitelik(i[1], "type") || "text").toLowerCase(); if (n && t === "hidden") gizli[n] = nitelik(i[1], "value"); }
    for (const sl of f[2].matchAll(/<select\b([^>]*)>([\s\S]*?)<\/select>/gi)) { const n = nitelik(sl[1], "name"); if (n) secimler[n] = [...sl[2].matchAll(/<option\b([^>]*)>([\s\S]*?)<\/option>/gi)].map((x) => ({ deger: nitelik(x[1], "value"), etiket: sade(x[2]).trim() })); }
    o.push({ eylem: nitelik(f[1], "action"), yontem: (nitelik(f[1], "method") || "get").toLowerCase(), gizli, secimler });
  }
  return o;
}
/* tablo satırları: her hücrenin metni ve içindeki bağlantılar/simgeler (belge düğmeleri) */
function tabloSatirlari(html) {
  const satirlar = [], basliklar = []; let hamSatir = "";
  for (const tr of html.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/gi)) {
    const hucreler = [...tr[1].matchAll(/<(td|th)\b[^>]*>([\s\S]*?)<\/\1>/gi)];
    if (hucreler.length < 6) continue;
    const h = hucreler.map((c) => ({ metin: sade(c[2]).trim(), baglantilar: [...c[2].matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a>/gi)].map((a) => ({ href: nitelik(a[1], "href"), onclick: nitelik(a[1], "onclick"), baslik: nitelik(a[1], "title") || nitelik(a[2], "alt") || nitelik(a[2], "title") || sade(a[2]).trim() })) }));
    if (/<th\b/i.test(tr[1]) && !h.some((x) => x.baglantilar.length)) { if (!basliklar.length || h.length > basliklar.length) { basliklar.length = 0; basliklar.push(...h.map((x) => x.metin)); } continue; }
    if (/^\d{4}\/\d{2}$/.test(h[0].metin)) { satirlar.push(h); if (!hamSatir) hamSatir = tr[1]; }
  }
  return { basliklar, satirlar, hamSatir };
}
const hamMaskeli = (h, n) => String(h || "").replace(/[A-Za-z0-9]{24,}/g, (m) => (/\d/.test(m) ? "<kod>" : m)).replace(/\s+/g, " ").slice(0, n || 2500);
/* bir betik işlevinin kaynağı (süslü parantez dengesiyle) ve içinde çağırdığı, aynı betikte tanımlı işlevler */
function islevKaynagi(js, ad) {
  const re = new RegExp("(?:function\\s+" + ad + "\\s*\\(|(?:var\\s+|window\\.)?" + ad + "\\s*=\\s*function\\s*\\()"), m = re.exec(js); if (!m) return "";
  const i = js.indexOf("{", m.index); if (i < 0) return ""; let d = 0, j = i;
  for (; j < js.length && j - i < 6000; j++) { const c = js[j]; if (c === "{") d++; else if (c === "}") { d--; if (d === 0) { j++; break; } } }
  return js.slice(m.index, j);
}
function islevlerZinciri(js, ad) {
  const gor = new Set(), cikti = [], sira = [ad];
  while (sira.length && cikti.length < 5) {
    const a = sira.shift(); if (gor.has(a)) continue; gor.add(a);
    const k = islevKaynagi(js, a); if (!k) continue; cikti.push(k);
    for (const m of k.matchAll(/(?<![\w$.])([A-Za-z_$][\w$]{2,})\s*\(/g)) if (!gor.has(m[1]) && !/^(function|if|for|while|switch|return|catch|alert|confirm|setTimeout|String|Number|parseInt|parseFloat|isNaN)$/.test(m[1])) sira.push(m[1]);
  }
  return cikti.join("\n\n");
}
const betiklerMaskeli = (html) => [...html.matchAll(/<script\b(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi)].map((m) => m[1].trim()).filter(Boolean).join("\n---\n").replace(/[A-Za-z0-9]{24,}/g, "<kod>").slice(0, 1800);

/* e-Bildirge belge düğmeleri: onclick="islem('H','178852-2026-9')" sayfadaki gizli pdfFormId formunu doldurup /tahakkuk/pdfGosterim.action'a gönderir */
function pdfFormu(html) {
  for (const f of html.matchAll(/<form\b([^>]*)>([\s\S]*?)<\/form>/gi)) {
    if (!/pdfGosterim/i.test(f[1]) && nitelik(f[1], "id") !== "pdfFormId") continue;
    const alanlar = {}, idAd = {};
    for (const i of f[2].matchAll(/<input\b([^>]*)>/gi)) { const n = nitelik(i[1], "name"); if (!n) continue; alanlar[n] = nitelik(i[1], "value"); const id = nitelik(i[1], "id"); if (id) idAd[id] = n; }
    return { eylem: nitelik(f[1], "action"), alanlar, idAd };
  }
  return null;
}
function islemTipleri(html) {
  const o = {};
  for (const m of html.matchAll(/case\s*["'](\w+)["']\s*:\s*\$\(\s*["']#tipId["']\s*\)\.val\(\s*["']([^"']*)["']\s*\)\s*;?(\s*\$\(\s*["']#downloadId["']\s*\)\.val\(\s*["']true["']\s*\))?/g)) o[m[1]] = { tip: m[2], indir: !!m[3] };
  return o;
}
const ISLEM = /islem\(\s*['"]([A-Z]+)['"]\s*,\s*['"]([^'"]+)['"]\s*\)/;
const ISLEM_AD = { T: "tahakkuk", H: "hizmet", SH: "s-hizmet" };

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
      if (this.ref) h.referer = this.ref;
      let r;
      try { r = await fetch(url, { method: yontem, headers: h, body: govde ? new URLSearchParams(govde) : undefined, redirect: "manual", signal: AbortSignal.timeout(25000) }); }
      catch (e) { throw new Error(e && (e.name === "TimeoutError" || e.name === "AbortError") ? "SGK 25 saniyede yanıt vermedi (zaman aşımı)." : "SGK'ya ulaşılamadı: " + e.message); }
      this.cerezTopla(r, u.hostname);
      if ([301, 302, 303, 307, 308].includes(r.status)) { const hdf = r.headers.get("location") || "/"; (this.yon = this.yon || []).push(r.status + " " + u.pathname + u.search + " -> " + hdf); url = new URL(hdf, url).href; yontem = "GET"; govde = null; continue; }
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
    this.iz = [];
    for (let n = 0; n < 4 && (basliyorMu(html) || (n === 0 && !anaSayfaMi(html))); n++) {
      const ayni = (u) => { try { return new URL(u).hostname === this.s.sunucu; } catch (e) { return false; } };
      const sonraki = devamAdresleri(html, url).find((u) => !denenen.has(u) && ayni(u));
      const betik = !sonraki && basliyorMu(html) ? await this.betiktenAdres(html, url) : "";
      const form = !sonraki && !betik && formCoz(html).find((f) => f.eylem && !/kullaniciIlkKontrollerGiris/.test(f.eylem));
      this.iz.push("adım " + (n + 1) + ": bağlantı=" + (sonraki || "-") + " betik=" + (betik || "-") + " form=" + (form ? form.eylem : "-"));
      if (!sonraki && !betik && !form) break;
      const hedef = sonraki || betik || new URL(form.eylem, url).href; if (denenen.has(hedef)) break; denenen.add(hedef);
      try { const r2 = form && !sonraki && !betik ? await this.git(form.yontem === "post" ? "POST" : "GET", hedef, form.gizli) : await this.git("GET", hedef); html = r2.veri.toString("utf8"); url = r2.url; this.zincir.push(url); this.sayfalar.push({ url, html }); }
      catch (e) { this.iz.push("hata: " + e.message); if (n === 0) throw e; break; }
    }
    if (/kullaniciIlkKontrollerGiris/.test(html)) { const e = new Error("SGK oturumu açılamadı: uygulama penceresi giriş sayfasına döndü."); e.giris = true; throw e; }
    this.girdi = true; this.ana = html; this.anaUrl = url;
  }
  /* başlatıcı sayfanın harici betiği uygulamayı window.open(window.location.pathname + "/pages/baslangic.jsf") ile açar; tarayıcıda sayfa yolu giriş sonrası sistem köküne çekildiği için adres kök + yol olur */
  async betiktenAdres(html, url) {
    for (const m of [...html.matchAll(/<script\b[^>]*\bsrc\s*=\s*["']([^"']+)["']/gi)].slice(0, 6)) {
      try {
        const r = await this.git("GET", new URL(coz(m[1]), url).href), js = r.veri.toString("utf8");
        const w = /window\.open\(\s*window\.location\.pathname\s*\+\s*["']([^"']+)["']/.exec(js);
        if (w) return new URL(this.s.kok + w[1], url).href;
        const d = /window\.open\(\s*["']([^"']+)["']/.exec(js); if (d) return new URL(d[1], url).href;
      } catch (e) { (this.iz = this.iz || []).push("betik okunamadı: " + e.message); }
    }
    /* betik okunamasa da başlatıcı bilinen kalıpsa (uygulamaBaslat) adres, betiğin kurduğu adrestir */
    if (/uygulamaBaslat\(/.test(html)) { (this.iz = this.iz || []).push("betik okunamadı/bulunamadı; bilinen adres kullanıldı"); return new URL(this.s.kok + "/pages/baslangic.jsf", url).href; }
    return "";
  }
  /* giriş sonrası ana sayfadaki bağlantılar (adres keşfi için tanı) */
  async tani(derin) {
    if (!this.girdi) throw this.oturumHata();
    const liste = baglantilar(this.ana);
    const ilk = this.sayfalar && this.sayfalar.length > 1 ? baglantilar(this.sayfalar[0].html).map((x) => Object.assign({ not: "başlatıcı sayfa" }, x)) : [];
    const cerceveler = liste.filter((x) => x.tur === "frame" && /sgk\.gov\.tr/i.test(new URL(x.href, this.anaUrl).hostname)).slice(0, 4), ek = [], tum = liste.slice();
    for (const c of cerceveler) { try { const r = await this.git("GET", new URL(c.href, this.anaUrl).href); const b = baglantilar(r.veri.toString("utf8")); ek.push({ kaynak: c.href, baglantilar: b }); tum.push(...b); } catch (e) { ek.push({ kaynak: c.href, hata: e.message }); } }
    const sonuc = { baslik: (/<title>([\s\S]*?)<\/title>/i.exec(this.ana) || [])[1] || "", baglantilar: liste, baslatici: ilk, baslaticiBetik: this.sayfalar && this.sayfalar.length > 1 ? betiklerMaskeli(this.sayfalar[0].html) : "", baslaticiHam: basliyorMu((this.sayfalar && this.sayfalar[0] ? this.sayfalar[0].html : this.ana)) ? hamMaskeli((this.sayfalar && this.sayfalar[0] ? this.sayfalar[0].html : this.ana).slice(((this.sayfalar && this.sayfalar[0] ? this.sayfalar[0].html : this.ana).indexOf("<body") + 1) || 0), 3500) : "", zincir: this.zincir || [], iz: this.iz || [], cerceveler: ek, adres: this.anaUrl };
    if (derin) { /* menü sayfalarını gez (yalnız okuma: GET); çıkış bağlantıları atlanır */
      const adaylar = [], gor = new Set();
      for (const x of tum) { if (x.tur !== "a" || !/\.(?:action|jsp|do)/i.test(x.href) || /çıkış|cikis|logout|exit/i.test(x.metin + x.href)) continue; const u = new URL(x.href, this.anaUrl).href; if (gor.has(u)) continue; gor.add(u); adaylar.push({ metin: x.metin, u }); }
      sonuc.sayfalar = [];
      for (const a of adaylar.slice(0, 12)) { try { const r = await this.git("GET", a.u); const h = r.veri.toString("utf8"); sonuc.sayfalar.push({ metin: a.metin, adres: a.u.replace(this.taban, ""), formlar: formlar(h), tablolar: tablolar(h), baglantilar: baglantilar(h).slice(0, 15) }); } catch (e) { sonuc.sayfalar.push({ metin: a.metin, adres: a.u.replace(this.taban, ""), hata: e.message }); } }
    }
    return sonuc;
  }
  /* İşveren Sistemi menü sayfası (yalnız okuma: GET). ad: menüdeki internetLink<ad>.action */
  async isverenSayfa(ad) {
    if (!this.girdi) throw this.oturumHata();
    const jeton = (t) => String(t || "").replace(/(isverenToken|token)=[^"'&\s;]+/gi, "$1=<jeton>");
    this.yon = []; this.ref = null;
    let r = await this.git("GET", this.s.kok + "/internetLink" + ad + ".action"), html = r.veri.toString("utf8"), adimlar = [];
    if (/kullaniciIlkKontrollerGiris/.test(html)) throw this.oturumHata();
    adimlar.push(jeton(r.url.replace(this.taban, "")));
    /* menü sayfası gerçek uygulamayı bir iframe içinde açar: iframe adresini izle (en çok 2 kademe) */
    for (let n = 0; n < 2; n++) {
      const i = html.search(/id\s*=\s*["']contentContainer["']/i), kap = i >= 0 ? html.slice(i) : html;
      const f = /<iframe\b[^>]*\bsrc\s*=\s*["']([^"']+)["']/i.exec(kap); if (!f) break;
      const u = new URL(coz(f[1]), r.url); if (!/(^|\.)sgk\.gov\.tr$/i.test(u.hostname)) break;
      this.ref = r.url; try { r = await this.git("GET", u.href); } finally { this.ref = null; } html = r.veri.toString("utf8"); adimlar.push(jeton(r.url.replace(this.taban, "")));
      if (/kullaniciIlkKontrollerGiris/.test(html)) throw this.oturumHata();
    }
    const i2 = html.search(/id\s*=\s*["']contentContainer["']/i), icerik = i2 >= 0 ? html.slice(i2) : html;
    const satirlar = [];
    const TR = /<tr\b[^>]*>((?:(?!<tr\b)[\s\S])*?)<\/tr>/gi;
    for (const tr of html.matchAll(TR)) {
      const h = [...tr[1].matchAll(/<(td|th)\b[^>]*>([\s\S]*?)<\/\1>/gi)].map((c) => sade(c[2]).trim()); if (h.length < 8 || h.every((x) => !x)) continue;
      const eylem = [...tr[1].matchAll(/(?:onclick|href)\s*=\s*["']([^"']{3,160})["']/gi)].map((m) => coz(m[1])).filter((x) => !/^#$/.test(x)).slice(0, 4);
      satirlar.push({ h: h.map((x) => x.slice(0, 40)), eylem: eylem.map(jeton) }); if (satirlar.length >= 60) break;
    }
    const th = html.search(/<th\b/i), tabloHam = th >= 0 ? jeton(hamMaskeli(html.slice(Math.max(0, th - 200)).replace(/<style[\s\S]*?<\/style>/gi, ""), 4500)) : "";
    const uyari = sade((/id\s*=\s*["']genelUyariCenterTag["'][^>]*>([\s\S]*?)<\/center>/i.exec(html) || [])[1] || "");
    const ciftler = [...icerik.matchAll(/<tr\b[^>]*>\s*<th\b[^>]*>([\s\S]*?)<\/th>\s*<td\b[^>]*>([\s\S]*?)<\/td>\s*<\/tr>/gi)].map((m) => ({ k: sade(m[1]).slice(0, 60), v: sade(m[2]).slice(0, 120) })).filter((x) => x.k).slice(0, 20);
    let borc = null;
    { let bas = null; const sat = [];
      for (const tr of icerik.matchAll(TR)) {
        const ths = [...tr[1].matchAll(/<th\b[^>]*>([\s\S]*?)<\/th>/gi)].map((m) => sade(m[1])), tds = [...tr[1].matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/gi)].map((m) => sade(m[1]));
        if (ths.length >= 8 && !bas) { bas = ths; continue; }
        if (bas && !ths.length && tds.length >= 8 && tds.length <= bas.length + 1) sat.push(tds);
      }
      if (bas && sat.length) borc = { basliklar: bas, satirlar: sat.slice(0, 60) }; }
    const sonuc = sade((/SORGULAMA SONUCU[\s\S]*?<td\b[^>]*>([\s\S]*?)<\/td>/i.exec(icerik) || [])[1] || "");
    const yeriM = /Sicil No\s*:\s*([\d ]+?)\s+Ünvan\s*:\s*(.+?)\s+Adresi/.exec(sade(icerik)), isyeri = yeriM ? { sicil: yeriM[1].trim(), unvan: yeriM[2].trim() } : null;
    const sayiTr = (t) => { const n = Number(String(t || "").replace(/\./g, "").replace(",", ".")); return Number.isFinite(n) ? n : null; };
    let borcToplam = null;
    if (borc) { const tp = borc.satirlar.filter((c) => /^TOPLAM/i.test(c[0]))[0]; if (tp) borcToplam = sayiTr(tp[tp.length - 1]); else if (!borc.satirlar.length) borcToplam = 0; }
    this.sonSayfa = { url: r.url, html, formlar: [] };
    for (const f of html.matchAll(/<form\b([^>]*)>([\s\S]*?)<\/form>/gi)) {
      const eylem = nitelik(f[1], "action"); if (!eylem || /3_4_sent_2|DetayGetir|13_1_sent/.test(eylem)) continue;
      const dugmeler = [...f[2].matchAll(/<input\b[^>]*type\s*=\s*["']submit["'][^>]*>|<button\b[^>]*>/gi)].map((m) => ({ ad: nitelik(m[0], "name"), deger: sade(nitelik(m[0], "value")), onclick: sade(nitelik(m[0], "onclick")).slice(0, 160) })).filter((d) => d.deger || d.ad);
      if (!dugmeler.length) continue;
      const gizli = {}; for (const i of f[2].matchAll(/<input\b([^>]*)>/gi)) { const n = nitelik(i[1], "name"); if (n && (nitelik(i[1], "type") || "text").toLowerCase() === "hidden") gizli[n] = coz(nitelik(i[1], "value")); }
      for (const d of dugmeler) this.sonSayfa.formlar.push({ eylem, gizli, ad: d.ad, deger: d.deger, etiket: d.deger || d.ad, onclick: d.onclick });
    }
    const metinSade = sade(icerik).replace(/^.*?Eski Prim Oran\s*:\s*[\d.,]*\s*/, "").slice(0, 1200);
    return { uyari, sonuc, ciftler, borc, borcToplam, isyeri, dugmeler: this.sonSayfa.formlar.map((f, i) => ({ i, etiket: f.etiket, onclick: hamMaskeli(f.onclick, 160) })), yonlendirme: (this.yon || []).map(jeton), satirlar, tabloHam, adres: adimlar.join(" -> "), baslik: sade((/<title>([\s\S]*?)<\/title>/i.exec(html) || [])[1] || ""), metin: metinSade, hata: "", formlar: formCoz(icerik).map((f) => ({ eylem: jeton(f.eylem), yontem: f.yontem, gizli: Object.keys(f.gizli), secimler: f.secimler })), alanlar: formlar(icerik), tablolar: tablolar(icerik), baglantilar: baglantilar(icerik).slice(0, 25).map((x) => ({ tur: x.tur, metin: x.metin, href: jeton(x.href) })), ham: jeton(hamMaskeli(icerik.replace(/<style[\s\S]*?<\/style>/gi, ""), 4500)) };
  }
  /* menü sayfasını (iframe kademeleriyle) getirir: { r, html, icerik } */
  async isverenGetir(ad) {
    this.yon = []; this.ref = null;
    let r = await this.git("GET", this.s.kok + "/internetLink" + ad + ".action"), html = r.veri.toString("utf8");
    if (/kullaniciIlkKontrollerGiris/.test(html)) throw this.oturumHata();
    for (let n = 0; n < 2; n++) {
      const i = html.search(/id\s*=\s*["']contentContainer["']/i), kap = i >= 0 ? html.slice(i) : html;
      const f = /<iframe\b[^>]*\bsrc\s*=\s*["']([^"']+)["']/i.exec(kap); if (!f) break;
      const u = new URL(coz(f[1]), r.url); if (!/(^|\.)sgk\.gov\.tr$/i.test(u.hostname)) break;
      this.ref = r.url; try { r = await this.git("GET", u.href); } finally { this.ref = null; } html = r.veri.toString("utf8");
      if (/kullaniciIlkKontrollerGiris/.test(html)) throw this.oturumHata();
    }
    const i2 = html.search(/id\s*=\s*["']contentContainer["']/i);
    return { r, html, icerik: i2 >= 0 ? html.slice(i2) : html };
  }
  /* ---- Potansiyel teşvik sorgulama: sayfanın "sorgula" formu okunur (alan adları, seçenekler), kullanıcı doldurur, aynı forma gönderilir ---- */
  async tesvikFormu() {
    if (!this.girdi) throw this.oturumHata();
    const { r, html } = await this.isverenGetir("TesvikPotansiyel"), temiz = html.replace(/<script[\s\S]*?<\/script>/gi, "");
    for (const f of temiz.matchAll(/<form\b([^>]*)>([\s\S]*?)<\/form>/gi)) {
      const eylem = nitelik(f[1], "action"); if (!/sorgula/i.test(eylem)) continue;
      const alanlar = [], gizli = {}, gor = new Map();
      for (const tr of f[2].matchAll(/<tr\b[^>]*>((?:(?!<tr\b)[\s\S])*?)<\/tr>/gi)) {
        const satir = tr[1], th0 = /<th\b[^>]*>([\s\S]*?)<\/th>/i.exec(satir), etiket = th0 ? sade(th0[1]).slice(0, 170) : sade(satir.replace(/<select[\s\S]*?<\/select>/gi, " ").replace(/<input\b[^>]*>/gi, " ").replace(/<button[\s\S]*?<\/button>/gi, " ")).slice(0, 170);
        const girdiler = [...satir.matchAll(/<input\b([^>]*)>/gi)];
        girdiler.forEach((m, i) => {
          const ad = nitelik(m[1], "name"), tur = (nitelik(m[1], "type") || "text").toLowerCase(); if (!ad) return;
          if (tur === "hidden") { gizli[ad] = coz(nitelik(m[1], "value")); return; }
          if (tur === "submit" || tur === "button" || tur === "reset" || tur === "image") return;
          const bit = m.index + m[0].length, son = i + 1 < girdiler.length ? girdiler[i + 1].index : satir.length, yan = sade(satir.slice(bit, Math.min(son, bit + 400)).replace(/<select[\s\S]*?<\/select>/gi, " "));
          if (tur === "radio" || tur === "checkbox") { let a = gor.get(ad); if (!a) { a = { ad, tur, etiket, secenekler: [] }; gor.set(ad, a); alanlar.push(a); } a.secenekler.push({ deger: coz(nitelik(m[1], "value")), etiket: yan.slice(0, 200) || coz(nitelik(m[1], "value")) }); return; }
          if (!gor.has(ad)) { const a = { ad, tur: "text", etiket, deger: coz(nitelik(m[1], "value")) }; gor.set(ad, a); alanlar.push(a); }
        });
        for (const sl of satir.matchAll(/<select\b([^>]*)>([\s\S]*?)<\/select>/gi)) {
          const ad = nitelik(sl[1], "name"); if (!ad || gor.has(ad)) continue;
          const a = { ad, tur: "select", etiket, secenekler: [...sl[2].matchAll(/<option\b([^>]*)>([\s\S]*?)<\/option>/gi)].map((x) => ({ deger: coz(nitelik(x[1], "value")), etiket: sade(x[2]) })) };
          gor.set(ad, a); alanlar.push(a);
        }
      }
      this.sonForm = { eylem, gizli, url: r.url, izinli: new Set(alanlar.map((a) => a.ad)), alanlar };
      const ai = sade(temiz.slice(Math.max(0, temiz.search(/AÇIKLAMALAR/))));
      return { alanlar, aciklama: /AÇIKLAMALAR/.test(temiz) ? ai.slice(0, 2600) : "" };
    }
    throw new Error("Teşvik sorgu formu sayfada bulunamadı.");
  }
  async tesvikSorgula(deger) {
    if (!this.girdi) throw this.oturumHata();
    const f = this.sonForm; if (!f) throw new Error("Önce teşvik formunu açın.");
    const g = Object.assign({}, f.gizli);
    for (const a of f.alanlar) { const v = deger && deger[a.ad]; if (v !== undefined && v !== null && String(v) !== "" && f.izinli.has(a.ad)) g[a.ad] = String(v).slice(0, 80); }
    this.ref = f.url; let r; try { r = await this.git("POST", new URL(f.eylem, f.url).href, g); } finally { this.ref = null; }
    const html = r.veri.toString("utf8"); if (/kullaniciIlkKontrollerGiris/.test(html)) throw this.oturumHata();
    const temiz = html.replace(/<script[\s\S]*?<\/script>/gi, ""), tablolar = []; let akt = null;
    for (const tr of temiz.matchAll(/<tr\b[^>]*>((?:(?!<tr\b)[\s\S])*?)<\/tr>/gi)) {
      if (/<(input|select|textarea)\b/i.test(tr[1])) continue;
      const ths = [...tr[1].matchAll(/<th\b[^>]*>([\s\S]*?)<\/th>/gi)].map((m) => sade(m[1])), tds = [...tr[1].matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/gi)].map((m) => sade(m[1]));
      if (ths.length >= 2 && !tds.length) { akt = { basliklar: ths, satirlar: [] }; tablolar.push(akt); continue; }
      if (akt && tds.length >= 2 && akt.satirlar.length < 60 && tds.some((x) => x)) akt.satirlar.push(tds);
    }
    const i = temiz.search(/id\s*=\s*["']contentContainer["']/i), metin = sade(i >= 0 ? temiz.slice(i) : temiz).replace(/^.*?Eski Prim Oran\s*:\s*[\d.,]*\s*/, "");
    const uyari = sade((/id\s*=\s*["']genelUyariCenterTag["'][^>]*>([\s\S]*?)<\/center>/i.exec(temiz) || [])[1] || "") || hataMetni(html);
    return { tablolar: tablolar.filter((t) => t.satirlar.length), uyari, metin: metin.slice(0, 2200) };
  }
  /* son açılan İşveren sayfasındaki bir düğmeyi (ör. "Pdf Döküm Al") sayfanın kendi formu gibi gönderir */
  async formGonder(i) {
    if (!this.girdi) throw this.oturumHata();
    const sf = this.sonSayfa && this.sonSayfa.formlar[i]; if (!sf) throw new Error("Düğme bulunamadı; sayfayı yeniden açın.");
    const alan = Object.assign({}, sf.gizli); if (sf.ad) alan[sf.ad] = sf.deger; if ("jsp" in alan && !alan.jsp) alan.jsp = this.sonSayfa.html;
    this.ref = this.sonSayfa.url; let r; try { r = await this.git("POST", new URL(sf.eylem, this.sonSayfa.url).href, alan); } finally { this.ref = null; }
    const tur = (r.tur || "").toLowerCase().split(";")[0], pdf = /pdf/.test(tur) || r.veri.slice(0, 4).toString() === "%PDF";
    if (pdf) return { veri: r.veri, tur: "application/pdf", satir: true, ad: "sgk-belge.pdf" };
    const h = r.veri.toString("utf8"), m = sade((/id\s*=\s*["']genelUyariCenterTag["'][^>]*>([\s\S]*?)<\/center>/i.exec(h) || [])[1] || "") || hataMetni(h);
    throw new Error("SGK belge yerine bir sayfa döndürdü" + (m ? ": " + m : " (" + tur + ")") + ".");
  }
  async islemKaynagi(html, sayfaUrl, ad) {
    const satir = [...html.matchAll(/<script\b(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi)].map((m) => m[1]).join("\n");
    let k = islevlerZinciri(satir, ad); if (k) return { dosya: "(sayfa içi)", kaynak: hamMaskeli(k, 4500) };
    for (const m of [...html.matchAll(/<script\b[^>]*\bsrc\s*=\s*["']([^"']+)["']/gi)].slice(0, 8)) {
      try { const r = await this.git("GET", new URL(coz(m[1]), sayfaUrl).href), js = r.veri.toString("utf8"); k = islevlerZinciri(js, ad); if (k) return { dosya: m[1].replace(/\?.*$/, ""), kaynak: hamMaskeli(k, 4500) }; } catch (e) { /* sonraki betik */ }
    }
    return { dosya: "", kaynak: "" };
  }
  /* e-Bildirge > Onaylanmış Belgeler: dönem listesi, sorgu ve belge dosyaları */
  async bildirgeSayfa() {
    if (!this.girdi) throw this.oturumHata();
    const b = baglantilar(this.ana).find((x) => x.tur === "a" && /Onaylanmış Belgeler/i.test(x.metin));
    if (!b) throw new Error("e-Bildirge ana sayfasında “Onaylanmış Belgeler” bağlantısı bulunamadı.");
    const r = await this.git("GET", new URL(b.href, this.anaUrl).href), html = r.veri.toString("utf8");
    if (/kullaniciIlkKontrollerGiris/.test(html)) throw this.oturumHata();
    const f = formCoz(html).find((x) => /DonemSecildi/i.test(x.eylem)) || formCoz(html)[0];
    if (!f || !f.secimler.hizmet_yil_ay_index) throw new Error("Onaylanmış Belgeler sayfasında dönem seçimi bulunamadı.");
    return { f, eylem: new URL(f.eylem, r.url).href };
  }
  async bildirgeDonemler() { const d = await this.bildirgeSayfa(); return { donemler: d.f.secimler.hizmet_yil_ay_index.filter((x) => x.deger !== "-1" && x.etiket).map((x) => ({ deger: x.deger, etiket: x.etiket })) }; }
  async bildirgeListe(bas, bit) {
    const d = await this.bildirgeSayfa(), gecerli = (v) => d.f.secimler.hizmet_yil_ay_index.some((x) => x.deger === String(v) && x.deger !== "-1");
    if (!gecerli(bas) || !gecerli(bit)) throw new Error("Geçerli bir dönem seçin.");
    const alan = Object.assign({}, d.f.gizli, { hizmet_yil_ay_index: String(bas), hizmet_yil_ay_index_bitis: String(bit) });
    const r = await this.git("POST", d.eylem, alan), html = r.veri.toString("utf8");
    if (/kullaniciIlkKontrollerGiris/.test(html)) throw this.oturumHata();
    const t = tabloSatirlari(html); this.bsatirlar = t.satirlar; this.sonSorgu = { bas: String(bas), bit: String(bit) }; this.pdfForm = pdfFormu(html); this.islemHarita = islemTipleri(html);
    const VARSAYILAN = ["Tahakkuk Yıl/Ay", "Hizmet Yıl/Ay", "Belge Türü", "Belge Mahiyeti", "Kanun No", "Toplam Çalışan Sayısı", "Toplam Gün Sayısı", "Toplam Pek Tutar", "Tahakkuk", "Hizmet", "S.Hizmet"];
    if (t.satirlar.length && t.basliklar.length !== t.satirlar[0].length && t.satirlar[0].length === VARSAYILAN.length) t.basliklar = VARSAYILAN;
    return { basliklar: t.basliklar, satirlar: t.satirlar.map((h, n) => ({ n, hucreler: h.map((c, k) => ({ k, metin: c.metin, belgeler: c.baglantilar.map((b2, j) => { const im = ISLEM.exec(b2.onclick || ""); return { j, baslik: im ? (im[1].endsWith("D") ? "İndir" : "Görüntüle") : (b2.baslik || ""), var: !!im || !!(b2.href && !/^javascript:/i.test(b2.href)) || /["'](\/EBildirgeV2\/[^"']+)["']/.test(b2.onclick) }; }) })) })), ham: { satir: hamMaskeli(t.hamSatir, 2500), betik: betiklerMaskeli(html), islem: await this.islemKaynagi(html, r.url, "islem"), formlar: formCoz(html).map((f) => ({ eylem: f.eylem, yontem: f.yontem, gizli: Object.fromEntries(Object.entries(f.gizli).map(([a, b]) => [a, hamMaskeli(b, 30)])) })) }, hamMetin: t.satirlar.length ? "" : sade(html).replace(/İşlem Devam Ediyor Lütfen Bekleyiniz!/g, "").replace(/\s+/g, " ").trim().slice(0, 500), onclickOrnek: t.satirlar.length ? (t.satirlar[0].flatMap((c) => c.baglantilar).map((x) => x.onclick || x.href).filter(Boolean).slice(0, 6)) : [] };
  }
  async bildirgeBelge(n, k, j) {
    const c = ((this.bsatirlar || [])[n] || [])[k], b = c && c.baglantilar[j]; if (!b) throw new Error("Belge bulunamadı; listeyi yenileyin.");
    const im = ISLEM.exec(b.onclick || ""); if (im) return this.pdfAl(im[1], im[2], false);
    let yol = b.href && !/^javascript:/i.test(b.href) ? b.href : ((/["'](\/EBildirgeV2\/[^"']+)["']/.exec(b.onclick) || [])[1] || "");
    if (!yol) throw new Error("Bu belgenin adresi bulunamadı (düğme bir betik çalıştırıyor).");
    const r = await this.git("GET", new URL(coz(yol), this.anaUrl).href), tur = (r.tur || "").toLowerCase().split(";")[0];
    const pdf = /pdf/.test(tur) || r.veri.slice(0, 4).toString() === "%PDF";
    if (/html/.test(tur) && !pdf) throw new Error("SGK belge yerine bir sayfa döndürdü" + (hataMetni(r.veri.toString("utf8")) ? ": " + hataMetni(r.veri.toString("utf8")) : "") + ".");
    return { veri: r.veri, tur: pdf ? "application/pdf" : "application/octet-stream", satir: pdf, ad: "sgk-belge-" + (n + 1) + "-" + (k + 1) + (pdf ? ".pdf" : "") };
  }
  /* sayfanın islem() betiğinin yaptığı işi yapar: gizli formu doldurup pdfGosterim.action'a POST eder (token tek kullanımlık olabilir: gerekirse listeyi yenileyip bir kez daha dener) */
  async pdfAl(kod, ref, tekrar) {
    if (!this.pdfForm || !this.islemHarita || !this.islemHarita[kod]) { if (!tekrar && this.sonSorgu) { await this.bildirgeListe(this.sonSorgu.bas, this.sonSorgu.bit); return this.pdfAl(kod, ref, true); } throw new Error("Belge türü tanınmadı (" + kod + "); listeyi yenileyin."); }
    const f = this.pdfForm, t = this.islemHarita[kod], alan = Object.assign({}, f.alanlar), koy = (id, v) => { if (f.idAd[id]) alan[f.idAd[id]] = v; };
    koy("tipId", t.tip); koy("downloadId", t.indir ? "true" : "false"); koy("bildirgeRefNoId", ref);
    const r = await this.git("POST", new URL(f.eylem, this.anaUrl).href, alan), tur = (r.tur || "").toLowerCase().split(";")[0], pdf = /pdf/.test(tur) || r.veri.slice(0, 4).toString() === "%PDF";
    const ad = "sgk-" + (ISLEM_AD[kod.replace(/D$/, "")] || "belge") + "-" + String(ref).replace(/[^\w-]+/g, "_") + ".pdf";
    if (pdf) return { veri: r.veri, tur: "application/pdf", satir: !t.indir, ad };
    if (!tekrar && this.sonSorgu) { await this.bildirgeListe(this.sonSorgu.bas, this.sonSorgu.bit); return this.pdfAl(kod, ref, true); }
    const h = hataMetni(r.veri.toString("utf8")); throw new Error("SGK belge yerine bir sayfa döndürdü" + (h ? ": " + h : " (" + tur + ")") + ".");
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
  async formGonder(i) { if (!this.girdi) throw this.oturumHata2(); return this.bildirgeBelge(0, 0, 0); }
  async tesvikFormu() { if (!this.girdi) throw this.oturumHata2(); this.mf = true; return { alanlar: [{ ad: "tcKimlikNo", tur: "text", etiket: "T.C.Kimlik Numarası", deger: "" }, { ad: "kazanc", tur: "text", etiket: "Sigortalının Kazanç Bilgisi", deger: "" }, { ad: "egitimDurumu", tur: "select", etiket: "Eğitim Durumu", secenekler: [{ deger: "0", etiket: "SEÇİNİZ" }, { deger: "5", etiket: "Ortaöğretim" }, { deger: "7", etiket: "Üniversite" }] }, { ad: "meslekKod", tur: "text", etiket: "Meslek Kodu", deger: "" }, { ad: "sigortaliBasvuruTarihi", tur: "text", etiket: "Başvuru tarihi", deger: "" }, { ad: "sigortaliDurum", tur: "radio", etiket: "Sigortalının durumu", secenekler: [{ deger: "1", etiket: "Hiçbiri" }, { deger: "2", etiket: "İşsizlik ödeneği alıyor" }] }], aciklama: "Örnek açıklama." }; }
  async tesvikSorgula(d) { if (!this.mf) throw new Error("Önce teşvik formunu açın."); if (!d || !d.tcKimlikNo) return { tablolar: [], uyari: "T.C. Kimlik No boş.", metin: "" }; return { tablolar: [{ basliklar: ["Kanun No", "Teşvik süresi", "Aylık tutar"], satirlar: [["06111", "12 ay", "2.500,00"], ["05510", "5 puan", "1.100,00"]] }], uyari: "", metin: "Örnek sonuç" }; }
  async isverenSayfa(ad) { if (!this.girdi) throw this.oturumHata2(); return { uyari: ad === "IAKU" ? "HATA E-Borcu Yoktur Aktivasyonu Bulunmamaktadır." : "", ciftler: /^IA/.test(ad) ? [{ k: "TC Kimlik No", v: "11111111110" }] : [], borcToplam: ad === "DonemBorcGoruntuleme" ? 14065.45 : null, borc: ad === "DonemBorcGoruntuleme" ? { basliklar: ["Dönem", "Prim", "GZ", "Toplam BORÇ", "Toplam GZ", "TOPLAM"], satirlar: [["2026/08", "11.808,23", "2.257,22", "11.808,23", "2.257,22", "14.065,45"], ["TOPLAM", "11.808,23", "2.257,22", "11.808,23", "2.257,22", "14.065,45"]] } : null, isyeri: { sicil: "2 1234 01 01 1234567 034 12-34 000 000", unvan: "ÖRNEK NAKLİYAT LTD. ŞTİ." }, dugmeler: [{ i: 0, etiket: "Pdf Döküm Al" }], adres: "/IsverenSistemi/internetLink" + ad + ".action", baslik: "Örnek sayfa " + ad, metin: "Örnek içerik", hata: "", formlar: [{ eylem: "/IsverenSistemi/x.action", yontem: "post", gizli: ["token"], secimler: { donem: [{ deger: "1", etiket: "2026/09" }] } }], alanlar: [{ eylem: "/x", yontem: "post", alanlar: ["donem:select[1]"] }], tablolar: [["Dönem", "Borç"]], ham: "<form>…</form>" }; }
  async bildirgeDonemler() { if (!this.girdi) throw this.oturumHata2(); return { donemler: [{ deger: "1", etiket: "2026/09" }, { deger: "2", etiket: "2026/08" }, { deger: "3", etiket: "2026/07" }] }; }
  async bildirgeListe(b, e) { if (!this.girdi) throw this.oturumHata2(); const s = [{ n: 0, hucreler: ["2026/09", "2026/09", "01", "ASIL", "05510", "1", "4", "4.404,00 TL", "", "", ""].map((m, k) => ({ k, metin: m, belgeler: k >= 8 ? [{ j: 0, baslik: "Görüntüle", var: true }, { j: 1, baslik: "İndir", var: true }] : [] })) }]; return { basliklar: ["Tahakkuk Yıl/Ay", "Hizmet Yıl/Ay", "Belge Türü", "Belge Mahiyeti", "Kanun No", "Toplam Çalışan Sayısı", "Toplam Gün Sayısı", "Toplam Pek Tutar", "Tahakkuk", "Hizmet", "S.Hizmet"], satirlar: s, hamMetin: "", onclickOrnek: [] }; }
  async bildirgeBelge(n, k, j) { if (!this.girdi) throw this.oturumHata2(); const pdf = "%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 120]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n4 0 obj<</Length 44>>stream\nBT /F1 16 Tf 20 60 Td (ORNEK SGK BELGESI) Tj ET\nendstream endobj\n5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R/Size 6>>\n%%EOF"; return { veri: Buffer.from(pdf), tur: "application/pdf", satir: true, ad: "sgk-belge.pdf" }; }
  oturumHata2() { const e = new Error("SGK oturumu kapandı; güvenlik koduyla yeniden bağlanın."); e.oturum = true; return e; }
}

module.exports = { sade, formlar, tablolar, hamMaskeli, formCoz, tabloSatirlari, istemci: (k, sistem) => (MOCK ? new SahteSgk(k, sistem) : new Sgk(k, sistem)), baglantilar, hataMetni, devamAdresleri, basliyorMu, anaSayfaMi };
