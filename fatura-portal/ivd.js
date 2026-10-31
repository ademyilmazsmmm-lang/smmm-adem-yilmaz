/* Dijital Vergi Dairesi (dijital.gib.gov.tr) istemcisi: borç durumu, e-Tebligat, gelen (alıcı) e-Arşiv faturaları.
 *
 * Giriş yarı otomatiktir: portalın "Doğrulama Kodu" resmi alınır (captcha), kullanıcı kodu yazar, sonra kayıtlı kullanıcı kodu/şifre ile giriş yapılır.
 * DİKKAT: GİB'in resmî bir API'si yoktur; adresler portalın herkese açık arayüz kodundan okunmuştur ve değişebilir. Bu yüzden her yanıtın
 * "şekli" (anahtarlar ve türler, değerler maskeli) tanı için ayrıca üretilir. Giriş başarısızsa sunucu tarafında bekleme uygulanır (kod kilitlenmesin). */
"use strict";
const crypto = require("crypto");
const sgkYardim = require("./sgk.js");

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
  const duz = (o) => { const r = {}; for (const [k, v] of Object.entries(o || {})) { if (v === null || v === undefined || v === "") continue; if (Array.isArray(v)) { if (v.length && typeof v[0] !== "object") r[k] = v.join(", ").slice(0, 200); } else if (typeof v === "object") { for (const [k2, v2] of Object.entries(v)) if (v2 !== null && v2 !== undefined && v2 !== "" && typeof v2 !== "object") r[k + "." + k2] = v2; } else r[k] = v; } return r; };
  const gez = (v, d) => {
    if (d > 4 || v === null || v === undefined) return;
    if (Array.isArray(v)) { if (v.length && typeof v[0] === "object") v.slice(0, 500).forEach((x) => out.push(duz(x))); else v.slice(0, 500).forEach((x) => out.push({ değer: x })); return; }
    if (typeof v === "object") { let dizi = false; for (const x of Object.values(v)) if (Array.isArray(x) && x.length) { dizi = true; gez(x, d + 1); } if (!dizi) { const f = duz(v); if (Object.keys(f).length) out.push(f); } }
  };
  gez(veri, 0);
  return out.slice(0, 500);
}

/* GİB tarihleri Türkiye saatine göre ister; sunucu UTC olabilir (gece yarısından sonra bir gün geride kalır) */
const trTarih = (gunOnce) => { const d = new Date(Date.now() - (gunOnce || 0) * 864e5); return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Istanbul", year: "numeric", month: "2-digit", day: "2-digit" }).format(d); }; // YYYY-MM-DD
const trTarih8 = (gunOnce) => trTarih(gunOnce).replace(/-/g, "");

const sayiya = (v) => { const n = Number(String(v === null || v === undefined ? "" : v).replace(",", ".")); return Number.isFinite(n) ? n : 0; };
const yuvarla = (n) => Math.round(n * 100) / 100;
/* borç özeti + borç satırları -> arayüzün çizdiği yapı: { ozetKart: { gecmis, gecmemis, toplam: { toplam, asil, gz, adet }, zaman }, kayitlar } */
function borcDuzenle(ozet, liste) {
  const bugun = trTarih();
  const tarih = (t) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(t || "")) || /^(\d{2})[./](\d{2})[./](\d{4})/.exec(String(t || "")); if (!m) return ""; return m[1].length === 4 ? m[1] + "-" + m[2] + "-" + m[3] : m[3] + "-" + m[2] + "-" + m[1]; };
  const satirlar = ((liste && liste.borclar) || []).map((b) => {
    const v = tarih(b.vadeTarihi), gecmis = !!v && v < bugun;
    const r = { vergiTuru: b.vergiTuru || b.vergiAdi || "", donem: b.donem, vadeTarihi: b.vadeTarihi, durum: v ? (gecmis ? "Vadesi geçmiş" : "Vadesi gelmemiş") : "", asilBorc: sayiya(b.asilBorc), gecikmeZammi: sayiya(b.gecikmeZammi), toplam: sayiya(b.toplam), belgeNo: b.belgeNo, vdAdi: b.vdAdi };
    Object.defineProperty(r, "_gecmis", { value: gecmis, enumerable: false });
    return r;
  }).sort((a, b) => (tarih(a.vadeTarihi) || "9").localeCompare(tarih(b.vadeTarihi) || "9"));
  const kart = (adet, toplam, gz, vab) => ({ toplam: yuvarla(toplam), asil: yuvarla(vab), gz: yuvarla(gz), adet });
  const ob = (ozet && ozet.ozetBilgi) || [];
  const bul = (re, ters) => ob.find((x) => { const t = String(x.tipAciklama || "").toLocaleLowerCase("tr-TR"); return re.test(t) && !(ters && ters.test(t)); });
  const gG = bul(/geçmiş/, /geçmemiş/), gM = bul(/geçmemiş/), gT = bul(/toplam/);
  const topla = (x) => x ? { toplam: sayiya(x.toplam), gz: sayiya(x.toplamGzSum), vab: sayiya(x.toplamVabSum) } : null;
  const g1 = topla(gG), g2 = topla(gM), g3 = topla(gT);
  const hesap = (f) => satirlar.filter(f).reduce((a, r) => ({ toplam: a.toplam + r.toplam, gz: a.gz + r.gecikmeZammi, vab: a.vab + r.asilBorc }), { toplam: 0, gz: 0, vab: 0 });
  const h1 = hesap((r) => r._gecmis), h2 = hesap((r) => !r._gecmis);
  const A = g1 || h1, B = g2 || h2;
  const T = g3 || { toplam: A.toplam + B.toplam, gz: A.gz + B.gz, vab: A.vab + B.vab };
  return { ozetKart: { gecmis: kart(satirlar.filter((r) => r._gecmis).length, A.toplam, A.gz, A.vab), gecmemis: kart(satirlar.filter((r) => !r._gecmis).length, B.toplam, B.gz, B.vab), toplam: kart(satirlar.length, T.toplam, T.gz, T.vab), zaman: (ozet && ozet.hesaplamaZamani) || "" }, kayitlar: satirlar.map((r) => Object.assign({}, r, { _gecmis: r._gecmis })) };
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
      if (/hesaplan/i.test(msj)) { const e = new Error(msj); e.hesap = true; throw e; }
      if (/bulunmamaktad[ıi]r|bulunamad[ıi]|kay[ıi]t yok/i.test(msj)) { const e = new Error(msj); e.bos = true; throw e; }
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
  /* portal "borcunuz hesaplanıyor" uyarısı verebilir; kendi arayüzü de birkaç kez yeniden dener */
  async borc() {
    const hesapUyari = (y) => /hesaplan/i.test(this.mesajMetni(y) || "");
    let ozet = null;
    for (let n = 0; n < 6; n++) {
      try { ozet = await this.istek("POST", GW + "/payment/api/debtinformation-homepage-summary/false", { meta: { filters: [], pagination: { pageNo: 1, pageSize: 50 } } }, true); if (!hesapUyari(ozet)) break; }
      catch (e) { if (!e.hesap) throw e; if (n === 5) throw new Error("GİB borç tutarını hâlâ hesaplıyor; bir dakika sonra tekrar Sorgula'ya basın."); }
      await new Promise((r) => setTimeout(r, 3500));
    }
    let liste = null, listeHata = "";
    try { liste = await this.istek("POST", GW + "/payment/api/debtinformation/1", this.tablo({}, 100, { alan: "vdAdi", yon: "ASC" }), true); }
    catch (e) { if (e.oturum) throw e; listeHata = e.message; }
    const o = ozet && (ozet.data || ozet);
    return Object.assign(borcDuzenle(o, liste && (liste.data || liste)), { sekil: { ozet: sekil(ozet), liste: liste ? sekil(liste) : listeHata } });
  }
  async tebligat() {
    let say = null; try { say = await this.istek("GET", GW + "/etebligat/etebligat/tebligat-sayilari", undefined, true); } catch (e) { if (e.oturum) throw e; }
    const liste = await this.istek("POST", GW + "/etebligat/etebligat/tebligat-listele", this.tablo({}, 100, { alan: "tebligTarihi", yon: "DESC" }), true);
    const dizi = liste && liste.data && Array.isArray(liste.data.tebligatDtoList) ? liste.data.tebligatDtoList : null;
    const toplam = liste && liste.data && liste.data.count;
    const sy = say ? kayitlar(say.data || say)[0] || null : null;
    return { kayitlar: dizi ? kayitlar(dizi) : kayitlar(liste), say: sy, toplam, sekil: { sayilar: sekil(say), liste: dizi ? sekil(dizi) : sekil(liste) } };
  }
  /* tebligat belgesi: önce belge/ek listesi, sonra seçilen belgenin dosyası (portalın "Görüntüle" akışı) */
  async belgeListe(p) {
    const y = await this.istek("POST", GW + "/etebligat/etebligat/belge-ek-listele", { tebligId: p.tebligId, tebligSecureId: p.tebligSecureId }, true);
    const d = y && (y.tebligBelge || y.ekler ? y : y.data) || {};
    const hepsi = []; if (d.tebligBelge) hepsi.push(Object.assign({}, d.tebligBelge, { ek: false })); (d.ekler || []).forEach((e) => hepsi.push(Object.assign({}, e, { ek: true })));
    this.belgeler = hepsi.map((b) => ({ id: b.id, secureId: b.secureId, belgeTip: b.belgeTip, uzanti: b.uzanti, adi: b.adi, tarafId: p.tarafId, tarafSecureId: p.tarafSecureId }));
    return { belgeler: hepsi.map((b, n) => ({ n, ad: b.adi || "Belge", uzanti: b.uzanti || "", ek: b.ek })), sekil: sekil(y) };
  }
  async belgeIndir(n) {
    const b = (this.belgeler || [])[n]; if (!b) throw new Error("Belge bulunamadı; tebligatı yeniden açın.");
    const y = await this.istek("POST", GW + "/etebligat/etebligat/belge-getir", { data: { id: b.id, secureId: b.secureId, belgeTip: b.belgeTip, tarafId: b.tarafId, tarafSecureId: b.tarafSecureId, uzanti: b.uzanti, belgeAdi: b.adi } }, true);
    return this.dosyaCek(y, b.adi, b.uzanti);
  }
  /* GİB'in verdiği reportLink'ten dosyayı indirir; yalnız *.gib.gov.tr adreslerine gider, yalnız PDF/resim satır içi açılır */
  async dosyaCek(y, adi, uzanti) {
    const baglanti = y && (y.reportLink || (y.data && y.data.reportLink)); if (!baglanti) throw new Error("GİB belge bağlantısı vermedi.");
    const url = /^https?:\/\//i.test(baglanti) ? baglanti : "https://dijital.gib.gov.tr" + (baglanti.startsWith("/") ? "" : "/") + baglanti;
    let u; try { u = new URL(url); } catch (e) { throw new Error("GİB belge bağlantısı geçersiz."); }
    if (u.protocol !== "https:" || !/(^|\.)gib\.gov\.tr$/i.test(u.hostname)) throw new Error("GİB belge bağlantısı beklenmeyen bir adrese işaret ediyor; açılmadı.");
    let r = await fetch(u, { signal: AbortSignal.timeout(30000), redirect: "follow" });
    if ((r.status === 401 || r.status === 403) && this.token) r = await fetch(u, { headers: { authorization: "Bearer " + this.token }, signal: AbortSignal.timeout(30000), redirect: "follow" });
    if (!r.ok) throw new Error("Belge indirilemedi (HTTP " + r.status + ").");
    const veri = Buffer.from(await r.arrayBuffer()); if (veri.length > 25e6) throw new Error("Belge çok büyük.");
    const ut = (r.headers.get("content-type") || "").toLowerCase(), uz = String(uzanti || "").toLowerCase().replace(/^\./, "");
    const pdf = /pdf/.test(ut) || uz === "pdf" || veri.slice(0, 4).toString() === "%PDF";
    const resim = !pdf && (/^image\/(png|jpe?g|gif)/.test(ut) ? ut.split(";")[0] : { png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", gif: "image/gif" }[uz]);
    const ad = String(adi || "belge").replace(/[\\/:*?"<>|\r\n]+/g, " ").trim(); const adUz = uz && !ad.toLowerCase().endsWith("." + uz) ? ad + "." + uz : ad;
    return { veri, tur: pdf ? "application/pdf" : resim || "application/octet-stream", satir: !!(pdf || resim), ad: adUz };
  }
  /* e-Vergi Levhası: yıla göre liste, onay koduyla Türkçe/İngilizce PDF */
  async levhaListe(yil) {
    const y = await this.istek("POST", GW + "/api/eVergi-levhasi/eVergi-levhasi-listele", this.tablo({ donem: String(yil) }, 50), true);
    const dizi = (y && (Array.isArray(y.data) ? y.data : y.data && Array.isArray(y.data.data) ? y.data.data : [])) || [];
    this.levhalar = dizi.map((d) => ({ vergiDairesi: d.vergiDairesi || "", vergiTuru: d.vergiTuru || "", onayKodu: d.onayKodu || "", onayZamani: d.onayZamani || "" }));
    return { yil: Number(yil), levhalar: this.levhalar.map((d, n) => Object.assign({ n }, d)), sekil: sekil(y) };
  }
  async levhaIndir(n, dil, vkn) {
    const l = (this.levhalar || [])[n]; if (!l || !l.onayKodu) throw new Error("Vergi levhası bulunamadı; listeyi yenileyin.");
    const y = await this.istek("POST", GW + "/api/eVergi-levhasi/eVergi-levhasi-dogrula-pdf-diger", { data: { dogrulanacakTcknVkn: String(vkn || ""), dogrulanacakOnayKodu: l.onayKodu, belgeDili: dil === "en" ? "en" : "tr" } }, true);
    return this.dosyaCek(y, "e-vergi-levhasi-" + l.onayKodu + (dil === "en" ? "-en" : ""), "pdf");
  }
  /* Borç durum yazısı ("borcu yoktur" yazısı): portalda resmî bir talep (dilekçe) olarak verilir, vergi dairesi cevaplayınca PDF görüntülenir */
  async yaziListe() {
    const y = await this.istek("POST", GW + "/api/dilekce/dilekceSorgula", this.tablo({ body: { baslangicTarihi: trTarih8(89), bitisTarihi: trTarih8(0) } }, 50, { alan: "talepZamani", yon: "DESC" }), true);
    const dizi = (y && (y.mukellefiyetGonderilmisDilekcelerListeDTOList || (y.data && y.data.mukellefiyetGonderilmisDilekcelerListeDTOList))) || [];
    this.yazilar = dizi.map((d) => ({ id: d.dilekceId, secureId: d.secureId, ad: d.ad, talep: d.talepZamani, cevap: d.cevapZamani, durum: d.durum, eposta: d.eposta }));
    return { yazilar: this.yazilar.map((d, n) => ({ n, ad: d.ad, talep: d.talep, cevap: d.cevap, durum: d.durum, eposta: d.eposta })), sekil: sekil(y) };
  }
  async yaziIste(p) {
    const y = await this.istek("POST", GW + "/api/dilekce/dilekceKaydet", { eposta: p.eposta, baslangicTarihi: null, bitisTarihi: trTarih8(0), talepNedeni: p.neden, verilecekKurum: p.kurum, digerKurum: p.digerKurum || "", yazininHazirlanacagiTarih: "0" }, true);
    const mesajlar = (y && y.messages) || [], basari = mesajlar.some((m) => m && m.type === "SUCCESS");
    if (!basari) throw new Error("Talep alınmadı" + (this.mesajMetni(y) ? ": " + String(this.mesajMetni(y)).slice(0, 200) : " (GİB başarı yanıtı vermedi)") + ".");
    return { tamam: true, mesaj: mesajlar.filter((m) => m && m.text).map((m) => m.text).join(" ") || "Talebiniz işleme alındı.", sekil: sekil(y) };
  }
  async yaziIndir(n) {
    const d = (this.yazilar || [])[n]; if (!d) throw new Error("Yazı bulunamadı; listeyi yenileyin.");
    if (d.durum !== 1) throw new Error("Bu talep henüz cevaplanmadı; cevaplanınca PDF açılabilir.");
    const y = await this.istek("POST", GW + "/api/dilekce/dilekceGoruntulePdf", { data: { dilekceOid: d.id, secureId: d.secureId } }, true);
    return this.dosyaCek(y, d.ad || "borc-durum-yazisi", "pdf");
  }
  /* gelen e-Arşiv: portal en çok 7 günlük aralık kabul eder ve en erken 2 ay önceki ayın başına bakar; aralık dilimlenip birleştirilir.
   * bas/bit "GG/AA/YYYY" */
  async gelen(bas, bit) {
    const par = (t) => { const [g, a, y] = t.split("/").map(Number); return Date.UTC(y, a - 1, g); };
    const yaz = (ms) => { const d = new Date(ms); return String(d.getUTCDate()).padStart(2, "0") + "/" + String(d.getUTCMonth() + 1).padStart(2, "0") + "/" + d.getUTCFullYear(); };
    let bs = par(bas); const bt = par(bit); if (!(bt >= bs)) throw new Error("Bitiş tarihi başlangıçtan önce olamaz.");
    const simdi = new Date(), enEski = Date.UTC(simdi.getUTCFullYear(), simdi.getUTCMonth() - 2, 1);
    let uyari = ""; if (bs < enEski) { bs = enEski; uyari = "Portal en erken " + yaz(enEski) + " tarihine kadar bakıyor; başlangıç buna çekildi."; }
    if (bt < bs) throw new Error("Seçilen aralık portalın sorgulayabildiği dönemin (son 2–3 ay) dışında.");
    const dilimler = []; for (let b = bs; b <= bt; b += 7 * 864e5) dilimler.push([b, Math.min(b + 6 * 864e5, bt)]);
    const sonuc = new Array(dilimler.length); let ilkSekil = null; const hatalar = [];
    for (let i = 0; i < dilimler.length; i += 4) { // 4'erli paralel; kaydı olmayan dilim hata değil, boş sayılır
      await Promise.all(dilimler.slice(i, i + 4).map(async ([b, e], j) => {
        try {
          const y = await this.istek("POST", GW + "/eislemler/earsiv/alici-list", this.tablo({ duzenlenmeTarihiBas: yaz(b), duzenlenmeTarihiSon: yaz(e) }, 500, { alan: "faturaNo", yon: "DESC" }), true);
          if (!ilkSekil) ilkSekil = sekil(y);
          const dizi = (y && (y.resultListDenormalized || (y.data && y.data.resultListDenormalized))) || null;
          const mj = y && this.mesajMetni(y); if (!dizi && mj && /bulunmamaktad[ıi]r/i.test(mj)) { sonuc[i + j] = []; return; }
          sonuc[i + j] = dizi ? kayitlar(dizi) : [];
        } catch (er) { if (er.bos) { sonuc[i + j] = []; return; } if (er.oturum) throw er; sonuc[i + j] = []; hatalar.push(yaz(b) + ": " + er.message); }
      }));
    }
    if (hatalar.length === dilimler.length) throw new Error(hatalar[0].replace(/^[\d\/]+: /, ""));
    if (hatalar.length) uyari = (uyari ? uyari + " " : "") + hatalar.length + " dilim alınamadı (" + hatalar[0] + ").";
    const hepsi = [].concat(...sonuc).sort((a, b) => String(b.duzenlenmeTarihi || "").localeCompare(String(a.duzenlenmeTarihi || "")));
    return { kayitlar: hepsi.slice(0, 500), sekil: ilkSekil, uyari, aralik: yaz(bs) + " – " + yaz(bt) };
  }
  /* ---- Tahakkuk Bilgilerim: vergi dairesi + ay aralığı; her fiş için tahakkuk PDF'i ----
   * Portalın tarih biçimi kod okumasından kesin anlaşılamadığı için kabul edilen ilk biçim kullanılır ve hatırlanır. bas/bit "YYYY-AA" */
  async tahakkukListe(bas, bit) {
    const ay = (t) => /^\d{4}-(0[1-9]|1[0-2])$/.test(t || "");
    if (!ay(bas) || !ay(bit)) throw new Error("Başlangıç ve bitiş ayını seçin.");
    if (bas > bit) throw new Error("Bitiş ayı başlangıçtan önce olamaz.");
    const vy = await this.istek("POST", GW + "/api/sicil-bilgileri/tahakkuka-gore-vergi-daireleri-list", {}, true);
    const vdler = ((vy && ((vy.data && vy.data.vdArr) || vy.vdArr)) || []).map((d) => ({ kod: d.vdKodu, ad: d.vdAdi })).filter((d) => d.kod);
    if (!vdler.length) throw new Error("Tahakkuk kaydı olan vergi dairesi bulunamadı.");
    const [by, bm] = bas.split("-"), [ey, em] = bit.split("-"), son1 = new Date(Date.UTC(+ey, +em, 0)).getUTCDate();
    /* Portalın ay seçicisinin gönderdiği biçim koddan kesin anlaşılamıyor; yanlış biçimde GİB hata vermeden BOŞ liste dönebiliyor.
     * Bu yüzden boş sonuç "bu biçim olmadı" sayılır ve sıradaki denenir; ilk dolu sonuç veren biçim hatırlanır. */
    const bicimler = [[by + bm, ey + em], [by + bm + "01", ey + em + "01"], [by + bm + "01", ey + em + String(son1).padStart(2, "0")], [by + "-" + bm + "-01", ey + "-" + em + "-" + String(son1).padStart(2, "0")], [bm + "." + by, em + "." + ey], ["01/" + bm + "/" + by, String(son1).padStart(2, "0") + "/" + em + "/" + ey], ["01." + bm + "." + by, String(son1).padStart(2, "0") + "." + em + "." + ey], [by + "-" + bm, ey + "-" + em], [by + "-" + bm + "-01T00:00:00", ey + "-" + em + "-" + String(son1).padStart(2, "0") + "T00:00:00"], [new Date(Date.UTC(+by, +bm - 1, 1) - 3 * 36e5).toISOString(), new Date(Date.UTC(+ey, +em - 1, 1) - 3 * 36e5).toISOString()], [by + "-" + bm + "-01T00:00:00.000Z", ey + "-" + em + "-01T00:00:00.000Z"], [bm + by, em + ey], [bm + "/" + by, em + "/" + ey], [by + "/" + bm, ey + "/" + em]];
    const sirala = this.tahakkukBicim != null ? [bicimler[this.tahakkukBicim]].concat(bicimler.filter((_, i) => i !== this.tahakkukBicim)) : bicimler;
    let son = null, sonHata = null, hepsi = null, bosGeldi = false; const deneme = [];
    for (const b of sirala) {
      const topla = [], yanitlar = [];
      try {
        for (const vd of vdler) {
          const y = await this.istek("POST", GW + "/api/tahakkuklarim/tahakkuk-sorgula", this.tablo({ vdKodu: vd.kod, baslangicTarihi: b[0], bitisTarihi: b[1] }, 200, { alan: "kabulTarihi", yon: "DESC" }), true);
          yanitlar.push(y); const dizi = y && (Array.isArray(y.tahakkukList) ? y.tahakkukList : y.data && Array.isArray(y.data.tahakkukList) ? y.data.tahakkukList : null);
          if (!dizi) throw new Error("Tahakkuk listesi alınamadı (" + (this.mesajMetni(y) || "beklenmeyen yanıt") + ").");
          for (const d of dizi) topla.push(d);
        }
        son = yanitlar[yanitlar.length - 1]; deneme.push(b[0] + ".." + b[1] + " → " + topla.length);
        if (topla.length) { hepsi = topla; this.tahakkukBicim = bicimler.indexOf(b); break; }
        bosGeldi = true; // bu biçimle hiç kayıt gelmedi: ya dönemde tahakkuk yok ya da biçim yanlış
      } catch (e) { if (e.oturum) throw e; deneme.push(b[0] + ".." + b[1] + " → hata: " + String(e.message).slice(0, 80)); if (e.bos) { bosGeldi = true; continue; } sonHata = e; }
    }
    this.sonDeneme = deneme;
    if (hepsi === null) { if (bosGeldi) hepsi = []; else throw sonHata || new Error("Tahakkuk sorgusu kabul edilmedi."); }
    this.tahakkuklar = hepsi;
    const kayit = hepsi.map((d, n) => ({ n, vdAdi: d.vdAdi || "", vergiKodu: d.vergiKodu || "", vergiDonem: d.vergiDonem || "", kabulTarihi: d.kabulTarihi || "", fisNo: d.fisNo || "" }));
    return { kayitlar: kayit, sekil: sekil(son), deneme, vdler: vdler.length };
  }
  async tahakkukIndir(n) {
    const d = (this.tahakkuklar || [])[n]; if (!d) throw new Error("Tahakkuk bulunamadı; listeyi yenileyin.");
    const y = await this.istek("POST", GW + "/api/tahakkuklarim/tahakkuk-goruntule", { data: { secureId: d.secureId, orgoid: d.orgOid, thkFisNo: d.fisNo } }, true);
    return this.dosyaCek(y, "tahakkuk-" + String(d.fisNo || n + 1), "pdf");
  }
  /* ---- e-Yoklama tutanakları (vergi dairesi yoklama fişi): liste + PDF ---- */
  async yoklamaListe() {
    /* Portalın liste bileşeni gövdeyi kendisi kurar; "istek formatı hatalı" gelirse sıradaki biçim denenir, çalışan hatırlanır */
    const govdeler = [() => this.tablo({}, 100, { alan: "vdKoduText", yon: "ASC" }), () => this.tablo({}, 100), () => ({ meta: { pagination: { pageNo: 1, pageSize: 100 }, filters: [] } }), () => this.tablo({}, 100, { alan: "tarih", yon: "DESC" }), () => ({ data: {} }), () => ({})];
    const sira = govdeler.map((_, i) => i); if (this.yoklamaBicim != null) sira.sort((x, z) => (x === this.yoklamaBicim ? -1 : z === this.yoklamaBicim ? 1 : 0));
    let y = null, sonHata = null; const deneme = [];
    for (const i of sira) {
      try { y = await this.istek("POST", GW + "/api/yoklamalar/get-yoklama-list", govdeler[i](), true); this.yoklamaBicim = i; sonHata = null; break; }
      catch (e) { if (e.oturum) throw e; deneme.push(i + ": " + String(e.message).slice(0, 60)); sonHata = e; if (!/format|hatal/i.test(e.message || "")) break; }
    }
    if (sonHata) { sonHata.message += " [denenen biçimler: " + deneme.join(" | ") + "]"; throw sonHata; }
    const dizi = (y && (Array.isArray(y.yoklamaList) ? y.yoklamaList : y.data && Array.isArray(y.data.yoklamaList) ? y.data.yoklamaList : [])) || [];
    this.yoklamalar = dizi.slice(0, 100).map((d) => ({ yoklamaTuru: d.yoklamaTuruText || "", baslama: d.baslamaTarihi || "", tarih: d.tarih || "", vd: d.vdKoduText || "", kod: d.ykodu || "", secureId: d.secureId || "" }));
    return { kayitlar: this.yoklamalar.map((d, n) => ({ n, yoklamaTuru: d.yoklamaTuru, baslama: d.baslama, tarih: d.tarih, vd: d.vd, kod: d.kod })), sekil: sekil(y) };
  }
  async yoklamaIndir(n) {
    const d = (this.yoklamalar || [])[n]; if (!d) throw new Error("Yoklama bulunamadı; listeyi yenileyin.");
    const y = await this.istek("POST", GW + "/api/yoklamalar/get-yoklama-pdf", { data: { yoklamaKodu: d.kod, secureId: d.secureId } }, true);
    return this.dosyaCek(y, "yoklama-" + String(d.kod || n + 1), "pdf");
  }
  /* ---- Sicil Bilgilerim: kimlik/ünvan, merkez ve şubeler (adres, faaliyet/NACE kodları, mükellefiyet açılış-kapanış) ---- */
  /* GİB liste servisleri "istek formatı hatalı" derse sıradaki gövde biçimi denenir (hangisinin işlediği hatırlanmaz; her çağrıda sırayla) */
  async denemeli(yontem, url, govdeler) {
    let son = null; const log = [];
    for (let i = 0; i < govdeler.length; i++) {
      try { return await this.istek(yontem, GW + url, govdeler[i], true); }
      catch (e) { if (e.oturum) throw e; son = e; log.push(i + ": " + String(e.message).slice(0, 70)); if (!/format|hatal/i.test(e.message || "")) break; }
    }
    son.message += (log.length > 1 ? " [denenen biçimler: " + log.join(" | ") + "]" : ""); throw son;
  }
  async sicilBilgi() {
    const al = (y) => (y && y.data && typeof y.data === "object" && !Array.isArray(y.data) ? y.data : y) || {}, m = (v) => (v === undefined || v === null ? "" : String(v)), uyari = [];
    let k = {}; try { k = al(await this.istek("GET", GW + "/api/sicil-bilgileri/kisisel-bilgiler", undefined, true)); } catch (e) { if (e.oturum) throw e; uyari.push("Kimlik bilgileri: " + String(e.message).slice(0, 120)); }
    let tel = ""; try { tel = m(al(await this.istek("GET", GW + "/api/sicil-bilgileri/get-iletisim-bilgileri", undefined, true)).talepOnayGsmNo); } catch (e) { if (e.oturum) throw e; }
    let ly = {}; try { ly = await this.denemeli("POST", "/api/sube-bilgileri/mukellef-sube-listesi", [this.tablo({}, 50, { alan: "isyeriNitelikText", yon: "ASC" }), this.tablo({}, 50), { meta: { pagination: { pageNo: 1, pageSize: 50 }, filters: [] } }, { data: {} }, {}]); }
    catch (e) { if (e.oturum) throw e; uyari.push("İş yeri / şube listesi: " + String(e.message).slice(0, 160)); }
    const dizi = (ly && (Array.isArray(ly.subeBilgiDTO) ? ly.subeBilgiDTO : ly.data && Array.isArray(ly.data.subeBilgiDTO) ? ly.data.subeBilgiDTO : [])) || [], liste = dizi.slice(0, 8), subeler = [];
    const vkn = m(k.vkn) || m((ly && ly.vkn) || "");
    for (const sb of liste) {
      const sube = { ad: m(sb.subeAdi), no: m(sb.subeNumarasi), tur: m(sb.isYeriTuruText), nitelik: m(sb.isyeriNitelikText), vd: m(sb.vdUzunAdi), durum: m(sb.birimFaal), adresler: [], faaliyet: [], vergiler: [], hata: "" };
      const hata = (ad, e) => { sube.hata += (sube.hata ? " · " : "") + ad + ": " + String(e.message).slice(0, 160); };
      try {
        const veri = { vergiNo: vkn, subeNo: sb.subeNumarasi, mukellefiyet: 1, adresBilgi: 1, secureId: sb.secureId };
        const dy = al(await this.denemeli("POST", "/api/sube-bilgileri/get-sube-bilgisi", [{ data: veri }, veri]));
        sube.adresler = (Array.isArray(dy.isyeriAdresList) ? dy.isyeriAdresList : []).map((a) => ({ tip: m(a.adresTipText), adres: m(a.adresAciklama) })).filter((a) => a.adres);
        if (!sube.vd) sube.vd = m(dy.vergiDairesi || dy.vdUzunAdi);
      } catch (e) { if (e.oturum) throw e; hata("adres", e); }
      try {
        const fy = await this.denemeli("POST", "/api/faaliyet-bilgileri/get-faaliyet-bilgileri", [this.tablo({ subeOid: sb.oid }, 100, { alan: "faaliyetKod", yon: "ASC" }), this.tablo({ subeOid: sb.oid }, 100), { data: { subeOid: sb.oid } }]), fl = (fy && (Array.isArray(fy.dataList) ? fy.dataList : fy.data && Array.isArray(fy.data.dataList) ? fy.data.dataList : [])) || [];
        sube.faaliyet = fl.slice(0, 30).map((f) => ({ kod: m(f.faaliyetKod), ad: m(f.faaliyetAd), bas: m(f.basTar || f.baslamaTarihi), bit: m(f.bitTar || f.bitisTarihi) }));
      } catch (e) { if (e.oturum) throw e; hata("faaliyet", e); }
      try {
        const vy = await this.denemeli("POST", "/api/sube-bilgileri/get-vergi-turleri", [this.tablo({ subeNo: sb.subeNumarasi, secureId: sb.secureId }, 100, { alan: "vergiAdi", yon: "ASC" }), this.tablo({ subeNo: sb.subeNumarasi, secureId: sb.secureId }, 100), { data: { subeNo: sb.subeNumarasi, secureId: sb.secureId } }]), vl = (vy && (Array.isArray(vy.dataList) ? vy.dataList : vy.data && Array.isArray(vy.data.dataList) ? vy.data.dataList : [])) || [];
        sube.vergiler = vl.slice(0, 40).map((v) => ({ ad: m(v.vergiAdi), donem: m(v.donem), bas: m(v.baslamaTarihi), bit: m(v.bitisTarihi), terk: m(v.terkNedeni) }));
      } catch (e) { if (e.oturum) throw e; hata("vergi türleri", e); }
      subeler.push(sube);
    }
    /* şube listesi / adres alınamadıysa (ör. kayıtlı adres yok) adres istemeyen uçlardan merkez bilgisi ve faaliyet (NACE) kodları okunur */
    if (!subeler.length) {
      const yedek = { ad: "MERKEZ", no: "", tur: "Merkez", nitelik: "Merkez", vd: "", durum: "", adresler: [], faaliyet: [], vergiler: [], hata: "" };
      try { const my = al(await this.istek("GET", GW + "/api/sube-bilgileri/merkez-bilgisi-getir", undefined, true)); yedek.vd = m(my.vergiDairesi || my.vdUzunAdi || my.vdAdi); yedek.durum = m(my.birimFaal || my.durum); yedek.ad = m(my.subeAdi) || "MERKEZ"; yedek.no = m(my.subeNumarasi || my.subeNo); } catch (e) { if (e.oturum) throw e; yedek.hata += "merkez: " + String(e.message).slice(0, 120); }
      try { const fy = await this.istek("GET", GW + "/api/faaliyet-bilgileri/merkez-faaliyet-bilgisi", undefined, true), fl = (fy && (Array.isArray(fy.faaliyetKodlari) ? fy.faaliyetKodlari : fy.data && Array.isArray(fy.data.faaliyetKodlari) ? fy.data.faaliyetKodlari : [])) || []; yedek.faaliyet = fl.slice(0, 30).map((f) => ({ kod: m(f.faaliyetKod), ad: m(f.faaliyetAd), bas: m(f.basTar || f.baslamaTarihi), bit: m(f.bitTar || f.bitisTarihi) })); } catch (e) { if (e.oturum) throw e; yedek.hata += (yedek.hata ? " · " : "") + "faaliyet: " + String(e.message).slice(0, 120); }
      if (yedek.faaliyet.length || yedek.vd) subeler.push(yedek); else if (!Object.keys(k).length) { const tum = uyari.concat(yedek.hata ? ["yedek okuma: " + yedek.hata] : []).join(" · "); throw new Error((tum || "Sicil bilgisi alınamadı.") + (/Adres bulunamad/i.test(tum) ? " — GİB bu mükellefin sicilinde kayıtlı adres bulamıyor; Dijital VD’deki Sicil Bilgilerim ekranı da aynı hatayı verir olabilir. Başka bir mükellefle deneyin." : "")); }
    }
    return { kisi: { unvan: m(k.adSoyadUnvan), vkn: m(k.vkn), tckn: m(k.tckn), tur: m(k.sirketTuru), mukellefTuru: m(k.mukellefTuru), dogum: m(k.dogumTarihi), ikametgah: m(k.ikametgahAdres), isYeri: m(k.isYeriAdres), ticaretSicil: m(k.ticaretSicilNo), tel }, subeler, toplamSube: dizi.length, uyari: uyari.join(" · "), sekil: sekil({ kisi: k, liste: ly }) };
  }
  /* ---- Z raporu: yeni nesil ÖKC aylık satış raporu bildirimleri (İnternet VD "ÖKC Bildirim Görüntüleme") ---- */
  async zRapor(yil, ay, vknIpucu) {
    yil = String(yil || ""); ay = String(ay || "").padStart(2, "0");
    if (!/^20\d{2}$/.test(yil) || !/^(0[1-9]|1[0-2])$/.test(ay)) throw new Error("Yıl ve ay seçin.");
    let gr; try { gr = await this.sideGiris("okc"); } catch (e) { if (e.oturum) throw e; throw new Error("Z raporu için İnternet Vergi Dairesi bağlantısı kurulamadı: " + String(e.message).slice(0, 120)); }
    const hedef = gr.y.redirectUrl, u = new URL(hedef), token = u.searchParams.get("token") || "", m = (v) => (v === undefined || v === null ? "" : String(v)), sayi = (v) => Number(String(v || "0").replace(",", ".")) || 0, adet = (v) => parseInt(v, 10) || 0;
    await this.gibGit(hedef);
    const hataMetni = (j) => ((j && j.messages) || []).map((x) => x && x.text).filter(Boolean).join(" ").slice(0, 200);
    const cagir = async (cmd, jp) => {
      const r = await this.gibGit(u.origin + "/intvrg_server/dispatch", "cmd=" + cmd + "&callid=" + Date.now().toString(36) + "-1&token=" + encodeURIComponent(token) + "&jp=" + encodeURIComponent(JSON.stringify(jp)), hedef);
      let j; try { j = JSON.parse(r.metin); } catch (e) { throw new Error("İnternet Vergi Dairesi beklenmeyen bir yanıt verdi."); }
      if (j && j.error && String(j.error) !== "0") throw new Error(hataMetni(j) || "İnternet Vergi Dairesi hatası.");
      return j;
    };
    const oz = await cagir("userSessionService_getUserSessionInfo", { token, rfDataInfo: [] }), od = (oz && oz.data && typeof oz.data === "object" ? oz.data : oz) || {};
    const adaylar = [...new Set([m(vknIpucu), m(od.KTCKN), m(od.GMSITCKIMLIKNO), m(od.GMSIVERGINO)].map((x) => x.replace(/\D/g, "")).filter((x) => /^\d{10,11}$/.test(x)))];
    if (!adaylar.length) throw new Error("Mükellefin T.C. / vergi kimlik numarası bulunamadı.");
    let veri = null, sonHata = null;
    for (const vkn of adaylar) {
      try { const j = await cagir("OKCIslemleriService_goruntule", { vkn, donemAy: ay, donemYil: yil, goruntuleTip: "1", okcTip: "2" }); const d = j && j.data; if (d && Array.isArray(d.donemOKCBildirimleri)) { veri = d.donemOKCBildirimleri; if (veri.length) break; } }
      catch (e) { sonHata = e; }
    }
    if (!veri) throw sonHata || new Error("Z raporu bilgisi alınamadı.");
    const satir = (d, a, t, n) => ({ ad: a, tutar: sayi(d[t]), adet: n ? adet(d[n]) : null });
    const bildirimler = veri.map((b) => {
      const d = b.detayBilgi || {}, oran = [0, 1, 8, 10, 18, 20].map((o) => ({ oran: o, tutar: sayi(d["satisKdv" + o]) }));
      return { yontem: m(b.bildirimYontem), tarih: m(b.bildirimTarih), raporNo: m(d.aylikSatisRaporNo), kdvSatis: oran, toplamSatis: oran.reduce((t, x) => t + x.tutar, 0), kdvToplam: sayi(d.kdvToplam),
        belge: [satir(d, "ÖKC fişleri", "okcfistutartutar", "okcfistutaradet"), satir(d, "Faturalar", "faturatutartutar", "faturatutaradet"), satir(d, "Serbest meslek makbuzu", "smmtutartutar", "smmtutaradet"), satir(d, "Müstahsil makbuzu", "muhtasiltutartutar", "muhtasiltutaradet"), satir(d, "Giriş / yolcu bileti", "gybilettutartutar", "gybilettutaradet"), satir(d, "Gider pusulası", "gpusulatutartutar", "gpusulatutaradet")],
        odeme: [satir(d, "Nakit", "nakitodemetutar", "nakitodemeadet"), satir(d, "Banka / kredi kartı", "bkkartodemetutar", "bkkartodemeadet"), satir(d, "Yemek kartı / çeki", "yemekkcodemetutar", "yemekkcodemeadet"), satir(d, "Diğer ödeme", "digerodemetutar", "digerodemeadet")],
        bilgi: [satir(d, "Fatura bilgi fişi", "faturabfistutar", "faturabfisadet"), satir(d, "Yemek kartı / çeki bilgi fişi", "yemekkcbfistutar", "yemekkcbfisadet"), satir(d, "Avans", "avansbfistutar", "avansbfisadet"), satir(d, "Fatura tahsilatı", "faturatahsilatbfistutar", "faturatahsilatbfisadet"), satir(d, "Otopark girişi", "otoparkbfistutar", "otoparkbfisadet"), satir(d, "Cari hesap tahsilatı", "carihesapbfistutar", "carihesapbfisadet"), satir(d, "Diğer bilgi fişi", "digerbfistutar", "digerbfisadet")] };
    });
    return { yil: Number(yil), ay, bildirimler };
  }
  /* ---- Araçlarım (Araç Bilgilerim): mevcut ya da geçmiş araçlar ---- */
  async aracListe(gecmis) {
    const y = await this.istek("POST", GW + "/api/aracBilgilerim/list", this.tablo({ sorgulamaTuru: gecmis ? "2" : "1" }, 100, { alan: "tescilTarihi", yon: "DESC" }), true);
    const dizi = (y && (Array.isArray(y.data) ? y.data : y.data && Array.isArray(y.data.data) ? y.data.data : [])) || [];
    const uyari = ((y && y.messages) || []).filter((m) => m && m.text).map((m) => m.text).join(" ");
    const al = ["plaka", "ozelPlaka", "tescilTarihi", "marka", "model", "tip", "cinsAd", "motorGucu", "silindirHacmi", "koltukSayisi", "tescilDurumu"];
    return { araclar: dizi.slice(0, 100).map((a) => { const r = {}; for (const k of al) if (a && a[k] !== undefined && a[k] !== null && a[k] !== "") r[k] = String(a[k]); return r; }), uyari, sekil: sekil(y) };
  }
  /* ---- POS İşlem Bilgilerim: banka ve ödeme kuruluşu POS tahsilatları (KDV dahil), ay bazında ---- */
  async posListe(yil, ay) {
    if (!/^\d{4}$/.test(String(yil)) || !/^(0?[1-9]|1[0-2])$/.test(String(ay))) throw new Error("Yıl ve ay seçin.");
    const govde = this.tablo({ yil: String(yil), ay: String(ay).padStart(2, "0") }, 200, { alan: "tutar", yon: "DESC" });
    const getir = async (yol) => {
      try { const y = await this.istek("POST", GW + "/mali-bilgiler/pos-islem/" + yol, govde, true); const d = (y && (Array.isArray(y.dataList) ? y.dataList : y.data && Array.isArray(y.data.dataList) ? y.data.dataList : [])) || []; return { satir: d.map((x) => ({ vkn: x.vkn || "", unvan: x.unvan || "", uyeIsyeriNo: x.uyeIsyeriNo || "", tutar: sayiya(x.tutar) })), y }; }
      catch (e) { if (e.oturum) throw e; if (e.bos) return { satir: [], y: null }; throw e; }
    };
    const [b, o] = await Promise.all([getir("banka-bilgileri"), getir("odeme-kurulus-bilgileri")]);
    const top = (l) => yuvarla(l.reduce((t, x) => t + x.tutar, 0));
    return { yil: Number(yil), ay: String(ay).padStart(2, "0"), banka: b.satir, odeme: o.satir, bankaToplam: top(b.satir), odemeToplam: top(o.satir), toplam: yuvarla(top(b.satir) + top(o.satir)), sekil: sekil(b.y || o.y) };
  }
  /* ---- İnteraktif Vergi Dairesi (ivd.gib.gov.tr) sayfaları: Dijital VD'den tek kullanımlık jetonla geçilir (portalın "İnteraktif VD" düğmesi).
   * Haciz sorguları bu sistemdedir (örn. page=P_INTVRG_INTVD_EHACIZ_BANKA_SRG). Yalnız okuma; adres/jeton günlüğe ya da arayüze yazılmaz. */
  async gibGit(url0, govde, ref) {
    const jar = (this.ivdCerez = this.ivdCerez || new Map()), yon = [];
    let url = url0;
    for (let n = 0; n < 6; n++) {
      let u; try { u = new URL(url); } catch (e) { throw new Error("İnteraktif Vergi Dairesi adresi geçersiz."); }
      if (u.protocol !== "https:" || !/(^|\.)gib\.gov\.tr$/i.test(u.hostname)) throw new Error("İnteraktif Vergi Dairesi beklenmeyen bir adrese yönlendirdi (" + String(u.hostname).slice(0, 60) + "); durduruldu.");
      const h = { "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36", accept: "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8", "accept-language": "tr-TR,tr;q=0.9", referer: ref || "https://dijital.gib.gov.tr/" };
      if (govde != null && n === 0) { h["content-type"] = "application/x-www-form-urlencoded; charset=UTF-8"; h["x-requested-with"] = "XMLHttpRequest"; h.origin = u.origin; }
      const c = jar.get(u.hostname); if (c && c.size) h.cookie = [...c].map(([a, d]) => a + "=" + d).join("; ");
      let r; try { r = await fetch(u, { method: govde != null && n === 0 ? "POST" : "GET", body: govde != null && n === 0 ? govde : undefined, headers: h, redirect: "manual", signal: AbortSignal.timeout(25000) }); } catch (e) { throw new Error(e && (e.name === "TimeoutError" || e.name === "AbortError") ? "İnteraktif Vergi Dairesi 25 saniyede yanıt vermedi." : "İnteraktif Vergi Dairesi'ne ulaşılamadı: " + e.message); }
      for (const sc of (typeof r.headers.getSetCookie === "function" ? r.headers.getSetCookie() : [])) { const kv = sc.split(";")[0].trim(), i = kv.indexOf("="); if (i > 0) { let m = jar.get(u.hostname); if (!m) jar.set(u.hostname, (m = new Map())); m.set(kv.slice(0, i), kv.slice(i + 1)); } }
      if ([301, 302, 303, 307, 308].includes(r.status)) { yon.push(r.status + " " + u.pathname + " -> " + (r.headers.get("location") || "").replace(/token=[^&\s]+/gi, "token=<jeton>")); url = new URL(r.headers.get("location") || "/", u).href; continue; }
      return { url: u.href, durum: r.status, tur: r.headers.get("content-type") || "", metin: Buffer.from(await r.arrayBuffer()).toString("utf8"), yon };
    }
    throw new Error("İnteraktif Vergi Dairesi çok fazla yönlendirme yaptı.");
  }
  /* SIDE sunucusuna (intvrg_server/dispatch ya da tvd_server/dispatch) menü tanımlarını sordurur: Z raporu / haciz gibi sayfaların gerçek adlarını ve komutlarını bulmak için (yalnız okuma) */
  /* Z raporu (yeni nesil ÖKC) Dijital VD'de ayrı bir girişle açılır (/tdvd/yeniNesilOkc-login); diğerleri intvrg / interaktif */
  async sideGiris(sistem) {
    const yollar = sistem === "okc" ? ["/auth/tdvd/yeniNesilOkc-login", "/auth/tdvd/intvrg-login"] : sistem === "intvrg" ? ["/auth/tdvd/intvrg-login"] : ["/auth/tdvd/interaktif-login"]; let son = null;
    for (const yol of yollar) { try { const y = await this.istek("GET", GW + yol, undefined, true); if (y && y.redirectUrl) return { y, yol }; son = new Error("bağlantı adresi alınamadı" + (this.mesajMetni(y) ? ": " + this.mesajMetni(y) : "")); } catch (e) { if (e.oturum) throw e; son = e; } }
    throw son || new Error("bağlantı adresi alınamadı");
  }
  async sideKesif(sistem, ara, html) {
    const intvrg = sistem === "intvrg" || sistem === "okc", maske = (t) => String(t || "").replace(/(token|jeton|sid|session[a-z]*)=[^&"'\s;<>]+/gi, "$1=<jeton>").replace(/\b[0-9a-f]{32,}\b/gi, "<jeton>"), gunluk = [];
    let gr; try { gr = await this.sideGiris(sistem); } catch (e) { if (e.oturum) throw e; return "SIDE keşif: " + String(e.message).slice(0, 120) + ".\n\n"; } const y = gr.y, hedef = y.redirectUrl;
    const u = new URL(hedef), token = u.searchParams.get("token") || ""; await this.gibGit(hedef);
    /* sayfa önce userSessionService_getUserSessionInfo ile oturumu başlatır; menü/BF tanımları side-dispatch, iş servisleri server/dispatch adresindedir */
    const uyg = intvrg ? "/intvrg_server/dispatch" : "/tvd_server/dispatch"; 
    /* adresler ve komut adları sayfanın kendi ayarlarından okunur (SideModuleMap / SideDefaults); bulunamazsa bilinen değerler */
    let ayar = String(html || ""); const kok0 = u.origin + new URL(hedef).pathname.replace(/[^/]*$/, "");
    if (!/SideModuleMap/.test(ayar)) { for (const ad of ["js/cs/wt-script-1.jsp", "js/cs/wt-script-2.jsp"]) { try { const r = await this.gibGit(kok0 + ad + "?isAuthorized=true&lang=tr", undefined, hedef); ayar += "\n" + r.metin; } catch (e) { /* yok */ } } }
    const prod = (/prod\s*:\s*\{([\s\S]*?)\}\s*,?\s*\}\s*;/.exec(ayar) || [])[1] || "", yerel0 = /(\w+)\s*:\s*\{\s*side\s*:\s*"([^"]*)"\s*,\s*app\s*:\s*"([^"]*)"[^}]*isLocalModule\s*:\s*true/.exec(prod);
    const yerel = yerel0 || (() => { const x = /"(\w+)"\s*:\s*\{\s*"app"\s*:\s*"([^"]*)"\s*,\s*"side"\s*:\s*"([^"]*)"[^}]*"isLocalModule"\s*:\s*true/.exec(ayar); return x ? [null, x[1], x[3], x[2]] : null; })();
    const mutlak = (yol, taban) => { try { return new URL(String(yol).trim(), taban).pathname; } catch (e) { return ""; } };
    const sayfaYolu = new URL(hedef).pathname, uygA = (yerel && mutlak(yerel[3], u.origin + sayfaYolu)) || uyg, sideA = (yerel && mutlak(yerel[2], u.origin + sayfaYolu)) || (intvrg ? "/intvrg_side/side-dispatch" : "/tvd_side/side-dispatch");
    const oturumKomut = (/\['sn-getUserSessionInfo'\]\s*=\s*'([^']+)'/.exec(ayar) || [])[1] || "userSessionService_getUserSessionInfo", jetonAdi = (/\['param-token-key'\]\s*=\s*'([^']+)'/.exec(ayar) || [])[1] || "token";
    const yollar = [sideA, uygA]; const modller = [...prod.matchAll(/(\w+)\s*:\s*\{\s*side\s*:\s*"([^"]*)"\s*,\s*app\s*:\s*"([^"]*)"/g)].map((x) => x[1] + "(" + x[2].trim() + "," + x[3].trim() + ")").join(" ");
    gunluk.push("adresler: side=" + sideA + " app=" + uygA + " oturum=" + oturumKomut + " jeton=" + jetonAdi + (yerel ? " (sayfa ayarından)" : " (varsayılan)") + (modller ? " modüller: " + modller : ""));
    let oturumOzet = "", userid = "";
    try {
      const r0 = await this.gibGit(u.origin + uygA, "cmd=" + oturumKomut + "&callid=" + Date.now().toString(36) + "&" + jetonAdi + "=" + encodeURIComponent(token) + "&jp=" + encodeURIComponent(JSON.stringify({ token, rfDataInfo: [] })), hedef);
      let j0 = null; try { j0 = JSON.parse(r0.metin); } catch (e) { /* JSON değil */ }
      if (j0 && typeof j0 === "object") { const d0 = j0.data && typeof j0.data === "object" ? j0.data : j0; userid = String(d0.userid || d0.userId || d0.csapUserId || d0.kullaniciKodu || ""); oturumOzet = "HTTP " + r0.durum + " alanlar: " + Object.keys(d0).slice(0, 25).join(",") + (j0.error ? " · hata: " + maske(JSON.stringify(j0.messages || "")).slice(0, 120) : ""); }
      else oturumOzet = "HTTP " + r0.durum + " " + maske(r0.metin.replace(/\s+/g, " ")).slice(0, 160);
    } catch (e) { oturumOzet = String(e.message).slice(0, 120); }
    gunluk.push("oturum başlatma → " + oturumOzet + (userid ? " (userid var)" : " (userid yok)"));
    const kalip = ara || /ÖKC|OKC|Z\s*Rapor|Satış|Haciz|Yoklama/i, bulunan = [];
    const tumu = [], tumTara = (d, derin) => { if (!d || derin > 7 || tumu.length > 120) return; if (Array.isArray(d)) { d.forEach((x) => tumTara(x, derin + 1)); return; } if (typeof d !== "object") return; const m = [d.text, d.title].find((x) => typeof x === "string"); if (m || d.page) tumu.push((d.id || d.defId || "").toString().slice(0, 14) + " | " + String(m || "").slice(0, 60) + " | " + (d.page || "") + (Array.isArray(d.children) && d.children.length ? " | alt:" + d.children.length : "")); Object.values(d).forEach((x) => tumTara(x, derin + 1)); };
    const tara = (d, derin) => { if (!d || derin > 6 || bulunan.length > 60) return; if (Array.isArray(d)) { d.forEach((x) => tara(x, derin + 1)); return; } if (typeof d !== "object") return; const m = [d.text, d.title, d.label, d.name].find((x) => typeof x === "string"); if ((d.page || d.pageName) && m && kalip.test(m + " " + (d.page || d.pageName))) bulunan.push((d.defId || d.id || "") + " | " + m + " | " + (d.page || d.pageName)); Object.values(d).forEach((x) => tara(x, derin + 1)); };
    dis: for (const yol of yollar) for (const cmd of ["SIDE.GET_ALL_MENU_DEFINITIONS3", "SIDE.GET_ALL_MENU_DEFINITIONS2"]) for (const rn of ["", "menuDefRoot", "tdvd"]) {
      const govde = "cmd=" + cmd + "&callid=" + Date.now().toString(36) + "&" + jetonAdi + "=" + encodeURIComponent(token) + "&jp=" + encodeURIComponent(JSON.stringify({ csapUserId: userid, rn, isTest: false, lang: "tr" }));
      try {
        const r = await this.gibGit(u.origin + yol, govde, hedef.replace(/token=[^&]*/, "token=" + token)), ozet = maske(r.metin.replace(/\s+/g, " ")).slice(0, 260);
        let j = null; try { j = JSON.parse(r.metin); } catch (e) { /* JSON değil */ }
        if (j) { tara(j, 0); if (!tumu.length) tumTara(j, 0); gunluk.push(yol + " " + cmd + " rn=" + (rn || "-") + " → HTTP " + r.durum + " JSON " + r.metin.length + " bayt" + (bulunan.length ? "" : " · " + ozet.slice(0, 60))); if (bulunan.length) break dis; } else gunluk.push(yol + " " + cmd + " rn=" + (rn || "-") + " → HTTP " + r.durum + " " + ozet);
      } catch (e) { gunluk.push(yol + " " + cmd + " → " + String(e.message).slice(0, 100)); }
      if (bulunan.length) break dis;
    }
    /* 2. aşama: sayfa tanımı (BF) "<modül>.<sayfa>" adıyla side-dispatch'ten istenir; tanımın içindeki servis (komut) adları sorgunun nasıl yapıldığını gösterir */
    const modAd = (yerel && yerel[1]) || "iv", haciz = intvrg ? [] : ["P_INTVRG_INTVD_EHACIZ_BANKA_SRG", "P_INTVRG_INTVD_EHACIZ_ARAC_SRG"], bf = [];
    const menuSf = [...new Set(tumu.map((x) => x.split(" | ")[2]).filter((x) => x && /^P_/.test(x) && !/YABANCI/.test(x)))].slice(0, 14), okcSf = [...new Set(bulunan.map((x) => x.split(" | ")[2]).filter(Boolean))].slice(0, 4);
    const bfCoz = (metin) => { let j = null; try { j = JSON.parse(metin); } catch (e) { /* düz metin */ } const sc = String((j && j.data && j.data.bfscript) || metin || ""); if (j && j.error) return { hata: maske(JSON.stringify(j.messages || j.error)).slice(0, 200), sc: "" }; return { sc }; };
    const tamYaz = intvrg ? ["E_INTVRG_INNER_MENU", "P_INTVRG_MAIN_SORGULAMALAR"] : [];
    for (const sf of haciz.concat(okcSf, tamYaz, menuSf.filter((x) => !tamYaz.includes(x)))) {
      const ayrinti = haciz.includes(sf) || okcSf.includes(sf), tam = tamYaz.includes(sf); let sonuc = "";
      for (const ek of ["", "&module=" + encodeURIComponent(modAd) + "&pageName=" + encodeURIComponent(sf)]) {
        try {
          const jp = { userid, bfnames: [modAd + "." + sf], loadedList: [], params: {}, resourceBundleLang: "tr" };
          const r = await this.gibGit(u.origin + yollar[0], "cmd=SIDE.GET_EAGER_BF_DEFS&callid=" + Date.now().toString(36) + "&" + jetonAdi + "=" + encodeURIComponent(token) + ek + "&jp=" + encodeURIComponent(JSON.stringify(jp)), hedef), c = bfCoz(r.metin);
          if (c.hata) { sonuc = "hata: " + c.hata; continue; }
          if (!c.sc) { sonuc = "boş (" + r.metin.length + " bayt)"; continue; }
          const tek = (re, n) => [...new Set([...c.sc.matchAll(re)].map((m) => m[1]))].slice(0, n);
          const srv = tek(/CSCaller\.call\(\s*["']([^"']{3,100})["']/g, 12).concat(tek(/["'](?:sn|serviceName)["']\s*[:=]\s*["']([^"']{3,100})["']/g, 8)), sf2 = tek(/\b(P_[A-Z0-9_]{6,70})\b/g, 12), hid = tek(/\b(H[0-9a-f]{12})\b/g, 8), okc = tek(/([^"']{0,40}(?:OKC|ÖKC|ZRAPOR)[^"']{0,40})/gi, 6);
          sonuc = c.sc.length + " bayt · servis: " + (srv.join(", ") || "-") + " · sayfa: " + (sf2.join(", ") || "-") + (hid.length ? " · menü: " + hid.join(", ") : "") + (okc.length ? " · ÖKC: " + okc.join(" | ") : "");
          const adlar2 = tek(/["']([a-z][A-Za-z0-9]{2,40}_[a-zA-Z][A-Za-z0-9]{2,60})["']/g, 30); if (adlar2.length) sonuc += " · tırnaklı adlar: " + adlar2.join(", ");
          if (tam) sonuc += "\n      TAM METİN: " + maske(c.sc.replace(/\s+/g, " ")).slice(0, 5200);
          if (ayrinti) { const k0 = c.sc.indexOf("BFEngine.register(\"" + sf + "\""), onc = c.sc.slice(Math.max(0, (k0 < 0 ? c.sc.length : k0) - 3200), k0 < 0 ? c.sc.length : k0 + 40); sonuc += "\n      SAYFA KODU (kayıt öncesi): " + maske(onc.replace(/\s+/g, " ")); }
          if (ayrinti) { const o = [...c.sc.matchAll(/CSCaller\.call\(/g)].slice(0, 3).map((m) => maske(c.sc.slice(Math.max(0, m.index - 150), m.index + 650).replace(/\s+/g, " "))); if (o.length) sonuc += "\n      örnek çağrılar:\n      " + o.join("\n      ---\n      "); }
          break;
        } catch (e) { sonuc = String(e.message).slice(0, 100); }
      }
      bf.push(modAd + "." + sf + " → " + sonuc);
    }
    const kod = [];
    /* 3. aşama: sayfanın konsolundan öğrenilen servis adları uygulama adresinden doğrudan denenir (yalnız okuma; kişisel sayılar maskelenir) */
    const servisler = [];
    if (intvrg) {
      const maskeK = (t) => maske(String(t || "").replace(/\s+/g, " ")).replace(/\b\d{10,11}\b/g, "<no>");
      for (const [cmd, jp] of [["menuService_getMenuJSON", {}], ["intVrgMenuService_anaMenuYukle", {}], ["OKCIslemleriService_goruntule", {}]]) {
        try {
          const r = await this.gibGit(u.origin + uygA, "cmd=" + cmd + "&callid=" + Date.now().toString(36) + "&" + jetonAdi + "=" + encodeURIComponent(token) + "&jp=" + encodeURIComponent(JSON.stringify(jp)), hedef), t = maskeK(r.metin);
          const okc = [...t.matchAll(/OKC|ÖKC/gi)].slice(0, 4).map((m) => t.slice(Math.max(0, m.index - 150), m.index + 300));
          servisler.push(cmd + " jp=" + JSON.stringify(jp) + " → HTTP " + r.durum + " " + r.metin.length + " bayt\n   " + t.slice(0, 700) + (okc.length ? "\n   ÖKC geçen yerler:\n   " + okc.join("\n   ---\n   ") : ""));
        } catch (e) { servisler.push(cmd + " → " + String(e.message).slice(0, 100)); }
      }
    }
    return "[SIDE keşif] giriş: " + gr.yol + "\n" + (bulunan.length ? "Menüde bulunan sayfalar (kod | ad | sayfa):\n" + [...new Set(bulunan)].join("\n") + "\n\n" : "") + (tumu.length ? "Menü kayıtları (kod | ad | sayfa):\n" + [...new Set(tumu)].join("\n") + "\n\n" : "") + "Denemeler:\n" + gunluk.slice(0, 16).join("\n") + (bf.length ? "\nSayfa tanımı:\n" + bf.join("\n") : "") + (servisler.length ? "\nServis denemeleri:\n" + servisler.join("\n") : "") + "\n\n";
  }
  async interaktifSayfa(sayfa, derin, sistem) {
    const intvrg = sistem === "intvrg" || sistem === "okc"; /* İnternet Vergi Dairesi (intvrg.gib.gov.tr): ÖKC / Z raporu bu sistemdedir */
    if (!(intvrg && !sayfa) && !/^[A-Z0-9_]{5,80}$/.test(String(sayfa))) throw new Error("Geçersiz sayfa.");
    let gr; try { gr = await this.sideGiris(sistem); } catch (e) { if (e.oturum) throw e; throw new Error("İnteraktif Vergi Dairesi " + e.message + "."); }
    const y = gr.y, hedef = y.redirectUrl;
    const r = await this.gibGit(sayfa ? hedef + (hedef.includes("?") ? "&" : "?") + "page=" + sayfa : hedef);
    const maske = (t) => String(t || "").replace(/(token|jeton|sid|session[a-z]*)=[^&"'\s;<>]+/gi, "$1=<jeton>").replace(/\b[0-9a-f]{32,}\b/gi, "<jeton>");
    const { sade, formlar, tablolar, hamMaskeli, formCoz } = sgkYardim, html = r.metin, ham = html.replace(/<style[\s\S]*?<\/style>/gi, "");
    const betikler = [...html.matchAll(/<script\b[^>]*\bsrc\s*=\s*["']([^"']+)["']/gi)].map((m) => maske(m[1])).slice(0, 12), cerceveler = [...html.matchAll(/<i?frame\b[^>]*\bsrc\s*=\s*["']([^"']+)["']/gi)].map((m) => maske(m[1])).slice(0, 6);
    let betikOzet = "";
    if (derin) {
      const satir = [...html.matchAll(/<script\b(?![^>]*\bsrc\s*=)[^>]*>([\s\S]*?)<\/script>/gi)].map((m) => m[1].replace(/\s+/g, " ").trim()).filter((x) => x.length > 20).slice(0, 4);
      if (satir.length) betikOzet += "[sayfadaki betikler]\n" + satir.map((x) => x.slice(0, 1200)).join("\n---\n") + "\n\n";
      /* gömülü betiklerin tamamından: kayıtlı sayfa (BF) adları, servis (komut) adları ve ÖKC / Z raporu / haciz geçen yerler */
      const tumBetik = [...html.matchAll(/<script\b(?![^>]*\bsrc\s*=)[^>]*>([\s\S]*?)<\/script>/gi)].map((m) => m[1]).join("\n"), tek = (re, n) => [...new Set([...tumBetik.matchAll(re)].map((m) => m[1]))].slice(0, n);
      const bfAd = tek(/BFEngine\.register\(\s*["']([^"']+)["']/g, 90), servis = tek(/CSCaller\.call\(\s*["']([^"']{3,100})["']/g, 90).concat(tek(/["'](?:sn|serviceName)["']\s*[:=]\s*["']([^"']{3,100})["']/g, 60)), sfAd = tek(/\b(P_[A-Z0-9_]{6,70})\b/g, 90);
      const okcBag = [...tumBetik.matchAll(/OKC|ÖKC|ZRAPOR|Z_RAPOR|EHACIZ/gi)].slice(0, 6).map((m) => tumBetik.slice(Math.max(0, m.index - 200), m.index + 400).replace(/\s+/g, " "));
      betikOzet += "[gömülü betik özeti: " + tumBetik.length + " bayt]\nsayfa/BF adları: " + (bfAd.join(" | ") || "-") + "\nservisler: " + (servis.join(" | ") || "-") + "\nP_ adları: " + (sfAd.join(" | ") || "-") + (okcBag.length ? "\nÖKC/haciz geçen yerler:\n" + okcBag.join("\n---\n") : "") + "\n\n";
      try { betikOzet += await this.sideKesif(sistem, undefined, html); } catch (e) { betikOzet += "[SIDE keşif] hata: " + String(e.message).slice(0, 160) + "\n\n"; } /* sayfa tek sayfalık uygulama (initSide): arka plan adreslerini bulmak için betiklerden uç/adres kalıpları ve sayfa adının geçtiği yerler çıkarılır (yalnız okuma) */
      const taban = new URL(r.url), parca = [];
      for (const b of [...html.matchAll(/<script\b[^>]*\bsrc\s*=\s*["']([^"']+)["']/gi)].map((m) => m[1]).filter((b) => !/jquery/i.test(b)).slice(0, 8)) {
        try {
          const g = await this.gibGit(new URL(b, taban).href), js = g.metin.slice(0, 900000), ad = b.replace(/\?.*$/, "");
          const uc = [...new Set([...js.matchAll(/["'`]([\w./-]*(?:\.jsp|\.do|\.action|\/rest\/|\/api\/|dispatch|\/service)[\w./?=&%-]*)["'`]/g)].map((m) => m[1]).filter((x) => x.length > 4 && x.length < 120))].slice(0, 40);
          const bag = [...js.matchAll(sayfa ? new RegExp(String(sayfa).replace(/_[A-Z]+$/, "").slice(0, 28), "g") : /Aylık\s*Satış|Satış\s*Rapor|YNOKC|YN_OKC|OKCBildirim|DonemSorgula|Dönem\s*Sorgula|Z\s*Rapor|ZRAPOR/gi)].slice(0, 5).map((m) => js.slice(Math.max(0, m.index - 150), m.index + 350).replace(/\s+/g, " "));
          const ajax = [...js.matchAll(/(?:\$\.ajax|\$\.post|XMLHttpRequest|fetch)\s*\(?[^;]{0,160}/g)].slice(0, 4).map((m) => m[0].replace(/\s+/g, " "));
          const bagla = (kalip, n, boy) => [...js.matchAll(kalip)].slice(0, n).map((m) => js.slice(Math.max(0, m.index - 120), m.index + boy).replace(/\s+/g, " "));
          const yan = /side-common|side-bc|lib_tv|side-user/.test(ad) ? [["çağrı", bagla(/this\.call=function\(cmd,callParams,config\)/g, 1, 3200)], ["initSide", bagla(/function\s+initSide|initSide\s*=/g, 2, 1500)], ["sayfa-adları", [...new Set([...js.matchAll(/P_INTVRG[A-Z0-9_]{4,60}/g)].map((m) => m[0]))].slice(0, 60)], ["cmd", [...new Set([...js.matchAll(/["']?cmd["']?\s*[:=]\s*["']([^"']{3,70})["']/g)].map((m) => m[1]))].slice(0, 50)], ["haciz", bagla(/EHACIZ|e-?haciz/gi, 3, 500)]] : /wt-script-1/.test(ad) ? [["içerik", [js.replace(/\s+/g, " ").slice(0, 3800)]]] : [];
          parca.push("# " + ad + " (" + g.metin.length + " bayt)" + yan.filter((x) => x[1].length).map((x) => "\n[" + x[0] + "] " + x[1].join(" ... ")).join("") + "\nuçlar: " + (uc.join(" | ") || "-") + (ajax.length ? "\najax: " + ajax.join(" || ") : "") + (bag.length ? "\nsayfa adı geçen yer: " + bag.join(" ... ") : ""));
        } catch (e) { parca.push("# " + b + " okunamadı: " + e.message); }
      }
      betikOzet = maske(betikOzet + parca.join("\n\n")).slice(0, 36000);
    }
    return { betikOzet, uyari: "", ciftler: [], borc: null, isyeri: null, dugmeler: [], adres: maske(r.url.replace(/^https:\/\/[^/]+/, "")) + " (HTTP " + r.durum + ")", baslik: sade((/<title>([\s\S]*?)<\/title>/i.exec(html) || [])[1] || ""), metin: sade(html).slice(0, 1500),
      formlar: formCoz(html).map((f) => ({ eylem: maske(f.eylem), yontem: f.yontem, gizli: Object.keys(f.gizli), secimler: f.secimler })), alanlar: formlar(html), tablolar: tablolar(html),
      baglantilar: cerceveler.map((c) => ({ tur: "çerçeve", metin: "", href: c })).concat(betikler.map((b) => ({ tur: "betik", metin: "", href: b }))), yonlendirme: r.yon, satirlar: [], tabloHam: "", ham: maske(hamMaskeli(ham.slice(Math.max(0, ham.search(/<body/i)), undefined), 4500)) };
  }
  /* ---- Onay SMS telefonu (profil → telefon güncelle): mevcut numara, yeni numaraya kod, kodla güncelleme ---- */
  async telefonBilgi() {
    const y = await this.istek("GET", GW + "/api/sms/get-iletisim-bilgileri", undefined, true);
    const t = String((y && (y.telefon || (y.data && y.data.telefon))) || "").replace(/\D/g, "");
    return { telefon: t, sekil: sekil(y) };
  }
  async telefonKodIste(kimlik, tel) {
    if (!/^\d{10,11}$/.test(String(kimlik))) throw new Error("Mükellefin VKN/TCKN bilgisi eksik.");
    if (!/^05\d{9}$/.test(String(tel))) throw new Error("Cep telefonunu 05XX XXX XX XX biçiminde yazın.");
    const y = await this.istek("GET", GW + "/api/sms/send-sms-with-no?tcknVkn=" + kimlik + "&telNo=" + tel + "&islemTuru=7", undefined, true);
    return { tamam: true, mesaj: this.mesajMetni(y) || "Onay kodu yeni numaraya gönderildi.", sekil: sekil(y) };
  }
  async telefonGuncelle(tel, kod) {
    if (!/^05\d{9}$/.test(String(tel))) throw new Error("Cep telefonunu 05XX XXX XX XX biçiminde yazın.");
    if (!/^\d{6}$/.test(String(kod || ""))) throw new Error("6 haneli SMS kodunu yazın.");
    const y = await this.istek("POST", GW + "/auth/login/user/change-phone-number", { smsKod: String(kod), telNo: String(tel) }, true);
    const m = ((y && y.messages) || []).filter((x) => x && x.text);
    if (m.some((x) => x.type === "ERROR")) throw new Error(m.filter((x) => x.type === "ERROR").map((x) => x.text).join(" ").slice(0, 200));
    return { tamam: true, mesaj: m.map((x) => x.text).join(" ") || "Telefon numarası güncellendi.", sekil: sekil(y) };
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
    const liste = { borclar: [
      { vergiTuru: "0032 GELİR GEÇİCİ VERGİ", donem: "2026/04-2026/06", vadeTarihi: "2026-08-17T00:00:00", asilBorc: 26556.75, gecikmeZammi: 2096.28, toplam: 28653.03, belgeNo: "2026081401OFa0000313", vdAdi: "ÖRNEK" },
      { vergiTuru: "0015 KDV", donem: "2026/09", vadeTarihi: "2027-12-26T00:00:00", asilBorc: 35850, gecikmeZammi: 0, toplam: 35850, belgeNo: "2026102601KDV0000001", vdAdi: "ÖRNEK" }
    ] };
    const ozet = { ozetBilgi: [{ tip: "1", tipAciklama: "Vadesi Geçmiş", toplam: "28653.03", toplamGzSum: "2096.28", toplamVabSum: "26556.75" }, { tip: "2", tipAciklama: "Vadesi Geçmemiş", toplam: "35850.00", toplamGzSum: "0.00", toplamVabSum: "35850.00" }, { tip: "3", tipAciklama: "Toplam", toplam: "64503.03", toplamGzSum: "2096.28", toplamVabSum: "62406.75" }], hesaplamaZamani: "2026-10-21T03:40:00" };
    return Object.assign(borcDuzenle(ozet, liste), { sekil: sekil({ ozet, liste }) });
  }
  async tebligat() {
    const d = [
      { belgeTuruAciklama: "ODEME EMRI", belgeNo: "2026091366OEY0001088", tarafId: "T1", tarafSecureId: "S1", tebligId: "B1", tebligSecureId: "C1", altKurum: "ÜMRANİYE VERGİ DAİRESİ MÜDÜRLÜĞÜ", kurumAciklama: "VERGİ DAİRESİ", gonderimZamani: "18/09/2026 16:44:48", tebligZamani: "2026-09-18T16:44:48", gerceklesenOtomatikOkunmaZamani: "2026-09-23T16:46:00" },
      { belgeTuruAciklama: "BILGI ISTEME YAZISI", belgeNo: "2026101577BIY0000077", tarafId: "T1", tarafSecureId: "S1", tebligId: "B1", tebligSecureId: "C1", altKurum: "ÜMRANİYE VERGİ DAİRESİ MÜDÜRLÜĞÜ", kurumAciklama: "VERGİ DAİRESİ", gonderimZamani: "15/10/2026 10:00:00", tebligZamani: "2026-10-15T10:00:00" },
      { belgeTuruAciklama: "TAHAKKUK BILDIRIMI", belgeNo: "2026082866TBY0000012", tarafId: "T1", tarafSecureId: "S1", tebligId: "B1", tebligSecureId: "C1", altKurum: "ÜMRANİYE VERGİ DAİRESİ MÜDÜRLÜĞÜ", kurumAciklama: "VERGİ DAİRESİ", gonderimZamani: "28/08/2026 09:00:00", tebligZamani: "2026-08-28T09:00:00", mukellefOkumaZamani: "2026-08-29T08:00:00" },
      { belgeTuruAciklama: "IHBARNAME", belgeNo: "2026071213AZL0000000", tarafId: "T1", tarafSecureId: "S1", tebligId: "B1", tebligSecureId: "C1", altKurum: "ÜMRANİYE VERGİ DAİRESİ", kurumAciklama: "VERGİ DAİRESİ", gonderimZamani: "12/07/2026 10:00:00", tebligZamani: "2026-07-12T10:00:00" },
      { belgeTuruAciklama: "VDK Belgesi", belgeNo: "29.09.2026/E.21692", tarafId: "T1", tarafSecureId: "S1", tebligId: "B1", tebligSecureId: "C1", altKurum: "İSTANBUL SEKTÖREL-1", kurumAciklama: "VERGİ DENETİM KURULU", gonderimZamani: "29/09/2026 14:00:00", tebligZamani: "2026-09-29T14:00:00" },
      { belgeTuruAciklama: "KEYS-YAZI", belgeNo: "2026081977OER1115704", tarafId: "T1", tarafSecureId: "S1", tebligId: "B1", tebligSecureId: "C1", altKurum: "ÜMRANİYE VERGİ DAİRESİ", kurumAciklama: "GELİR İDARESİ BAŞKANLIĞI", gonderimZamani: "19/08/2026 15:40:00", tebligZamani: "2026-08-19T15:40:00", mukellefOkumaZamani: "2026-08-19T16:00:00" },
      { belgeTuruAciklama: "Trafik İdari Para Cezası Karar Tutanağı", belgeNo: "TA-01510510", tarafId: "T1", tarafSecureId: "S1", tebligId: "B1", tebligSecureId: "C1", altKurum: "Jandarma Genel Komutanlığı", kurumAciklama: "JANDARMA GENEL KOMUTANLIĞI", gonderimZamani: "08/04/2026 09:36:00", tebligZamani: "2026-04-08T09:36:00" }
    ];
    return { kayitlar: kayitlar(d), say: { digerKurumOkunmamisTebligatSayisi: 2, digerKurumOkunmusTebligatSayisi: 1, digerKurumArsivlenmisTebligatSayisi: 0 }, toplam: 3, sekil: sekil(d) };
  }
  async belgeListe() { this.belgeler = [{ adi: "Ödeme emri" }]; return { belgeler: [{ n: 0, ad: "Ödeme emri", uzanti: "pdf", ek: false }, { n: 1, ad: "Ek: hesap dökümü", uzanti: "pdf", ek: true }], sekil: {} }; }
  async belgeIndir(n) {
    if (!(n >= 0 && n < 2)) throw new Error("Belge bulunamadı; tebligatı yeniden açın.");
    const pdf = "%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 120]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n4 0 obj<</Length 44>>stream\nBT /F1 18 Tf 20 60 Td (ORNEK TEBLIGAT) Tj ET\nendstream endobj\n5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R/Size 6>>\n%%EOF";
    return { veri: Buffer.from(pdf), tur: "application/pdf", satir: true, ad: "tebligat.pdf" };
  }
  async yaziListe() { const d = this.yazilar = this.yazilar || [{ ad: "Borç Durum Yazısı", talep: "2026-10-20T10:15:00", cevap: "2026-10-20T11:02:00", durum: 1, eposta: "ornek@ornek.com" }]; return { yazilar: d.map((x, n) => Object.assign({ n }, x)), sekil: {} }; }
  async yaziIste(p) { this.yazilar = this.yazilar || []; this.yazilar.unshift({ ad: "Borç Durum Yazısı", talep: new Date().toISOString().slice(0, 19), cevap: "", durum: 9, eposta: p.eposta }); this.sonIste = p; return { tamam: true, mesaj: "Talebiniz işleme alındı.", sekil: {} }; }
  async yaziIndir(n) {
    const d = (this.yazilar || [])[n]; if (!d) throw new Error("Yazı bulunamadı; listeyi yenileyin."); if (d.durum !== 1) throw new Error("Bu talep henüz cevaplanmadı; cevaplanınca PDF açılabilir.");
    const pdf = "%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 120]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n4 0 obj<</Length 44>>stream\nBT /F1 18 Tf 20 60 Td (ORNEK BORC DURUM YAZISI) Tj ET\nendstream endobj\n5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R/Size 6>>\n%%EOF";
    return { veri: Buffer.from(pdf), tur: "application/pdf", satir: true, ad: "borc-durum-yazisi.pdf" };
  }
  async levhaListe(yil) { this.levhalar = [{ vergiDairesi: "ÖRNEK VERGİ DAİRESİ MÜDÜRLÜĞÜ", vergiTuru: "Gelir Vergisi", onayKodu: "ABC12345", onayZamani: "01.02." + yil + " 10:15" }, { vergiDairesi: "ÖRNEK VERGİ DAİRESİ MÜDÜRLÜĞÜ", vergiTuru: "KDV", onayKodu: "XYZ98765", onayZamani: "01.02." + yil + " 10:16" }]; return { yil: Number(yil), levhalar: this.levhalar.map((d, n) => Object.assign({ n }, d)), sekil: {} }; }
  async levhaIndir(n, dil) {
    if (!(this.levhalar || [])[n]) throw new Error("Vergi levhası bulunamadı; listeyi yenileyin.");
    const pdf = "%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 120]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n4 0 obj<</Length 44>>stream\nBT /F1 18 Tf 20 60 Td (ORNEK VERGI LEVHASI " + (dil === "en" ? "EN" : "TR") + ") Tj ET\nendstream endobj\n5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R/Size 6>>\n%%EOF";
    return { veri: Buffer.from(pdf), tur: "application/pdf", satir: true, ad: "e-vergi-levhasi.pdf" };
  }
  async gelen() { const d = [{ unvan: "ÖRNEK TEDARİKÇİ A.Ş.", faturaNo: "ABC2026000000012", duzenlenmeTarihi: "12.10.2026", toplamTutar: 11800, odenecekTutar: 11800, vergilerTutari: 1800, paraBirimi: "TRY" }]; return { kayitlar: kayitlar(d), sekil: sekil(d) }; }
  async interaktifSayfa(sayfa, derin) { if (sayfa && !/^[A-Z0-9_]{5,80}$/.test(String(sayfa))) throw new Error("Geçersiz sayfa."); return { betikOzet: derin ? "# js/cs/side-common.js (123 bayt)\nuçlar: ornek.jsp" : "", uyari: "", ciftler: [], borc: null, isyeri: null, dugmeler: [], adres: "/tvd_side/index.jsp?token=<jeton> (HTTP 200)", baslik: "Örnek haciz sorgusu", metin: "Örnek içerik: kayıt bulunamadı.", formlar: [], alanlar: [], tablolar: [], baglantilar: [], yonlendirme: [], satirlar: [], tabloHam: "", ham: "<html>örnek</html>" }; }
  ornekPdf(metin) { return { veri: Buffer.from("%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 120]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n4 0 obj<</Length 44>>stream\nBT /F1 16 Tf 20 60 Td (" + metin + ") Tj ET\nendstream endobj\n5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R/Size 6>>\n%%EOF"), tur: "application/pdf", satir: true, ad: String(metin).toLowerCase().replace(/[^a-z0-9]+/g, "-") + ".pdf" }; }
  async tahakkukListe(bas, bit) { if (!bas || !bit) throw new Error("Başlangıç ve bitiş ayını seçin."); this.tahakkuklar = [{ vdAdi: "ÖRNEK VERGİ DAİRESİ", vergiKodu: "0015 - KDV", vergiDonem: "2026-09-01T00:00:00", kabulTarihi: "2026-10-26T10:12:00", fisNo: "2026102601KDV0001" }, { vdAdi: "ÖRNEK VERGİ DAİRESİ", vergiKodu: "0003 - MUHTASAR", vergiDonem: "2026-09-01T00:00:00", kabulTarihi: "2026-10-26T10:05:00", fisNo: "2026102601MUH0002" }]; return { kayitlar: this.tahakkuklar.map((d, n) => Object.assign({ n }, d)), sekil: {} }; }
  async tahakkukIndir(n) { if (!(this.tahakkuklar || [])[n]) throw new Error("Tahakkuk bulunamadı; listeyi yenileyin."); return this.ornekPdf("ORNEK TAHAKKUK " + (n + 1)); }
  async zRapor(yil, ay) { if (!yil || !ay) throw new Error("Yıl ve ay seçin."); const z = (a, t, n) => ({ ad: a, tutar: t, adet: n }); return { yil: Number(yil), ay: String(ay).padStart(2, "0"), bildirimler: [{ yontem: "Özel Entegratör", tarih: "05/10/2026 - 07:31", raporNo: "260900", kdvSatis: [0, 1, 8, 10, 18].map((o) => ({ oran: o, tutar: 0 })).concat([{ oran: 20, tutar: 56830 }]), toplamSatis: 56830, kdvToplam: 9471.67, belge: [z("ÖKC fişleri", 56830, 0), z("Faturalar", 0, 0)], odeme: [z("Nakit", 5288, 0), z("Banka / kredi kartı", 51542, 0), z("Yemek kartı / çeki", 0, 0)], bilgi: [z("Fatura bilgi fişi", 0, 0)] }] }; }
  async sicilBilgi() { return { kisi: { unvan: "ÖRNEK MÜKELLEF", vkn: "1111111111", tckn: "", tur: "GERCEK", mukellefTuru: "Gelir Vergisi", dogum: "01/01/1980", ikametgah: "ATATÜRK MAH. ÖRNEK SK. NO:3 ÜMRANİYE/İSTANBUL", isYeri: "ÖRNEK SANAYİ SİTESİ A BLOK NO:5 ÜMRANİYE/İSTANBUL", ticaretSicil: "", tel: "05320000000" }, subeler: [{ ad: "MERKEZ", no: "0", tur: "Merkez", nitelik: "İş yeri", vd: "ÜMRANİYE VERGİ DAİRESİ", durum: "Faal", adresler: [{ tip: "İş yeri adresi", adres: "ÖRNEK SANAYİ SİTESİ A BLOK NO:5 ÜMRANİYE/İSTANBUL" }], faaliyet: [{ kod: "49.41.01", ad: "Şehirlerarası eşya taşımacılığı", bas: "01/02/2015", bit: "" }], vergiler: [{ ad: "0015 - KDV", donem: "Aylık", bas: "01/02/2015", bit: "", terk: "" }, { ad: "0003 - Gelir Vergisi (Ticari)", donem: "Yıllık", bas: "01/02/2015", bit: "31/12/2019", terk: "İşi bırakma" }], hata: "" }], toplamSube: 1, sekil: {} }; }
  async yoklamaListe() { this.yoklamalar = [{ yoklamaTuru: "Yoklama", baslama: "2026-09-14", tarih: "2026-09-14", vd: "ÖRNEK VERGİ DAİRESİ", kod: "YKL2026000123", secureId: "x" }]; return { kayitlar: this.yoklamalar.map((d, n) => Object.assign({ n }, d)), sekil: {} }; }
  async yoklamaIndir(n) { if (!(this.yoklamalar || [])[n]) throw new Error("Yoklama bulunamadı; listeyi yenileyin."); return this.ornekPdf("ORNEK YOKLAMA FISI"); }
  async aracListe(gecmis) { return { araclar: gecmis ? [{ plaka: "34 ABC 123", marka: "FORD", model: "2012", tip: "TRANSIT", cinsAd: "KAMYONET", tescilDurumu: "Satıldı" }] : [{ plaka: "34 XYZ 789", ozelPlaka: "-", tescilTarihi: "2021-03-04", marka: "RENAULT", model: "2020", tip: "CLIO", cinsAd: "OTOMOBİL", motorGucu: "66", silindirHacmi: "999", koltukSayisi: "5", tescilDurumu: "Tescilli" }], uyari: "", sekil: {} }; }
  async posListe(yil, ay) { if (!yil || !ay) throw new Error("Yıl ve ay seçin."); return { yil: Number(yil), ay: String(ay).padStart(2, "0"), banka: [{ vkn: "1234567890", unvan: "ÖRNEK BANKA A.Ş.", uyeIsyeriNo: "000123", tutar: 85200.5 }], odeme: [{ vkn: "9876543210", unvan: "ÖRNEK ÖDEME KURULUŞU", uyeIsyeriNo: "77", tutar: 12000 }], bankaToplam: 85200.5, odemeToplam: 12000, toplam: 97200.5, sekil: {} }; }
  async telefonBilgi() { return { telefon: this.tel || "05320000000", sekil: {} }; }
  async telefonKodIste(kimlik, tel) { if (!/^05\d{9}$/.test(String(tel))) throw new Error("Cep telefonunu 05XX XXX XX XX biçiminde yazın."); this.bekleyenTel = tel; return { tamam: true, mesaj: "Onay kodu yeni numaraya gönderildi.", sekil: {} }; }
  async telefonGuncelle(tel, kod) { if (String(kod) !== "123456" || this.bekleyenTel !== tel) throw new Error("Dijital Vergi Dairesi hatası: SMS kodu hatalı."); this.tel = tel; return { tamam: true, mesaj: "Telefon numarası güncellendi.", sekil: {} }; }
}

module.exports = { istemci: (k, s) => (MOCK ? new SahteIvd(k) : new Ivd(k, s)), sekil, kayitlar };
