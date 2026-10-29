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
      { belgeTuruAciklama: "BILGI ISTEME YAZISI", belgeNo: "2026101566BIY0000077", tarafId: "T1", tarafSecureId: "S1", tebligId: "B1", tebligSecureId: "C1", altKurum: "ÜMRANİYE VERGİ DAİRESİ MÜDÜRLÜĞÜ", kurumAciklama: "VERGİ DAİRESİ", gonderimZamani: "15/10/2026 10:00:00", tebligZamani: "2026-10-15T10:00:00" },
      { belgeTuruAciklama: "TAHAKKUK BILDIRIMI", belgeNo: "2026082866TBY0000012", tarafId: "T1", tarafSecureId: "S1", tebligId: "B1", tebligSecureId: "C1", altKurum: "ÜMRANİYE VERGİ DAİRESİ MÜDÜRLÜĞÜ", kurumAciklama: "VERGİ DAİRESİ", gonderimZamani: "28/08/2026 09:00:00", tebligZamani: "2026-08-28T09:00:00", mukellefOkumaZamani: "2026-08-29T08:00:00" }
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
  async gelen() { const d = [{ unvan: "ÖRNEK TEDARİKÇİ A.Ş.", faturaNo: "ABC2026000000012", duzenlenmeTarihi: "12.10.2026", toplamTutar: 11800, odenecekTutar: 11800, paraBirimi: "TRY" }]; return { kayitlar: kayitlar(d), sekil: sekil(d) }; }
}

module.exports = { istemci: (k, s) => (MOCK ? new SahteIvd(k) : new Ivd(k, s)), sekil, kayitlar };
