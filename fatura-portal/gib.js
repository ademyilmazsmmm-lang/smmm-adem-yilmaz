"use strict";
/* GİB e-Arşiv Portal istemcisi.
 * Resmi bir API yok; portalın kendi sayfalarının kullandığı uçlar kullanılır (earsiv-services/assos-login ve dispatch).
 * GIB_MOCK=1 ile gerçek portala bağlanmadan, bellekte çalışan sahte bir GİB kullanılır.
 * Alan adları "DOĞRULANACAK" ile işaretlenen yerler gerçek portalda ilk denemede kontrol edilmelidir. */
const crypto = require("crypto");

const MOCK = process.env.GIB_MOCK === "1";
const BASE = process.env.GIB_TEST === "1" ? "https://earsivportaltest.efatura.gov.tr" : "https://earsivportal.efatura.gov.tr";

/* ---------- hesap (kuruş cinsinden tam sayı) ---------- */
function hesapla(g) {
  const tutar = Number(g.tutar), oran = Number(g.kdvOrani), tev = Number(g.tevkifat) || 0;
  if (!(tutar > 0) || !(oran >= 0) || tev < 0 || tev > 10) throw new Error("Tutar, KDV oranı veya tevkifat geçersiz.");
  let m, kdv;
  if (g.kdvDahil) { const tot = Math.round(tutar * 100); m = Math.round(tot / (1 + oran / 100)); kdv = tot - m; }
  else { m = Math.round(tutar * 100); kdv = Math.round(m * oran / 100); }
  const tevKdv = Math.round(kdv * tev / 10);
  return { matrah: m, kdv, tevKdv, kalanKdv: kdv - tevKdv, toplam: m + kdv, odenecek: m + kdv - tevKdv };
}
const tl = (k) => (k / 100).toFixed(2); // "1234.50" — portal noktalı ondalık bekler

/* ---------- portal gövdesi ---------- */
function faturaGovdesi(g, h, uuid, varyant) {
  varyant = varyant || 0;
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  const t = /^(\d{4})-(\d{2})-(\d{2})$/.exec(g.tarih || "");
  const tarih = t ? `${t[3]}/${t[2]}/${t[1]}` : `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
  const saat = `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  const sahis = /^\d{11}$/.test(g.aliciVkn);
  const parca = g.aliciUnvan.trim().split(/\s+/);
  const soyad = sahis && parca.length > 1 ? parca.pop() : "";
  const tevkifatli = Number(g.tevkifat) > 0;
  return {
    faturaUuid: uuid, belgeNumarasi: "", hangiTip: "5000/30000", faturaTarihi: tarih, saat, paraBirimi: "TRY", dovzTLkur: "0",
    faturaTipi: tevkifatli ? "TEVKIFAT" : "SATIS", /* DOĞRULANACAK: tevkifat için tip değeri */
    vknTckn: g.aliciVkn, aliciUnvan: sahis ? "" : g.aliciUnvan.trim(), aliciAdi: sahis ? parca.join(" ") : "", aliciSoyadi: sahis ? soyad : "",
    binaAdi: "", binaNo: "", kapiNo: "", kasabaKoy: "", vergiDairesi: "", ulke: "Türkiye", bulvarcaddesokak: g.aliciAdres || "",
    irsaliyeNumarasi: "", mahalleSemtIlce: "", sehir: " ", postaKodu: "", tel: "", fax: "", eposta: "", websitesi: "",
    iadeTable: [], ozelMatrahTutari: "0", ozelMatrahOrani: 0, ozelMatrahVergiTutari: "0", vergiCesidi: " ",
    malHizmetTable: [{
      malHizmet: h.ad, miktar: 1, birim: "C62", birimFiyat: tl(g._h.matrah), fiyat: tl(g._h.matrah),
      iskontoArttm: "İskonto", iskontoOrani: 0, iskontoTutari: "0", iskontoNedeni: "",
      malHizmetTutari: tl(g._h.matrah), kdvOrani: Number(g.kdvOrani), vergiOrani: 0, kdvTutari: tl(g._h.kdv), vergininKdvTutari: "0",
      ...(tevkifatli ? Object.assign({ tevkifatKodu: String(g.tevkifatKodu || "") }, varyant >= 1 ? { tevkifatOrani: Number(g.tevkifat) * 10, tevkifatTutari: tl(g._h.tevKdv) } : {}) : {}) /* kod kalem bazında; oranı portal koddan türetir (mlevent/fatura örneği) */
    }],
    tip: "İskonto", matrah: tl(g._h.matrah), malhizmetToplamTutari: tl(g._h.matrah), toplamIskonto: "0",
    hesaplanankdv: tl(g._h.kdv), vergilerToplami: tl(g._h.kdv), vergilerDahilToplamTutar: tl(g._h.toplam),
    toplamMasraflar: "0", odenecekTutar: tl(g._h.odenecek), not: g.not || "",
    siparisNumarasi: "", siparisTarihi: "", fisNo: "", fisTarihi: "", fisSaati: " ", fisTipi: " ", zRaporNo: "", okcSeriNo: ""
  };
}

/* ---------- gerçek istemci ---------- */
class Gib {
  constructor(kullanici, sifre) { this.k = kullanici; this.s = sifre; this.token = null; }
  async post(yol, alanlar) {
    const r = await fetch(BASE + yol, { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded;charset=UTF-8" }, body: new URLSearchParams(alanlar) });
    const t = await r.text();
    try { return JSON.parse(t); } catch (e) { throw new Error("Portal beklenmeyen yanıt verdi (" + r.status + ")."); }
  }
  async giris() {
    const y = await this.post("/earsiv-services/assos-login", { assoscmd: process.env.GIB_TEST === "1" ? "login" : "anologin", rtype: "json", userid: this.k, sifre: this.s, sifre2: this.s, parola: "1" });
    if (!y.token) throw new Error("GİB girişi başarısız: " + (y.messages && y.messages[0] && y.messages[0].text || "kullanıcı kodu/şifre hatalı olabilir."));
    this.token = y.token;
  }
  async dispatch(cmd, sayfa, jp) {
    if (!this.token) await this.giris();
    const y = await this.post("/earsiv-services/dispatch", { cmd, callid: crypto.randomUUID(), pageName: sayfa, token: this.token, jp: JSON.stringify(jp) });
    if (y.error === "1") throw new Error("GİB hatası: " + (y.messages && y.messages[0] && y.messages[0].text || JSON.stringify(y).slice(0, 200)));
    return y;
  }
  async liste(ileri) {
    const bugun = new Date(), p = (n) => String(n).padStart(2, "0");
    const f = (d) => `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
    const y = await this.dispatch("EARSIV_PORTAL_TASLAKLARI_GETIR", "RG_TASLAKLAR", { baslangic: f(new Date(bugun - 31 * 864e5)), bitis: f(new Date(+bugun + (ileri || 0) * 864e5)), hangiTip: "5000/30000", table: [] });
    return Array.isArray(y.data) ? y.data : [];
  }
  /* GİB taslağa kendi ettn'ini verir; yeni çıkan kaydı önce/sonra listesinden buluruz.
   * Liste oluşturma sonrası gecikmeli güncellenebilir: birkaç kez beklenip yeniden bakılır. */
  async taslak(govdeVeyaYapici) {
    const once = new Set((await this.liste()).map((x) => String(x.ettn).toLowerCase()));
    const yapici = typeof govdeVeyaYapici === "function" ? govdeVeyaYapici : () => govdeVeyaYapici;
    const varyantlar = typeof govdeVeyaYapici === "function" ? [0, 1] : [0];
    const redler = [];
    let y, govde;
    for (const v of varyantlar) {
      govde = yapici(v);
      y = await this.dispatch("EARSIV_PORTAL_FATURA_OLUSTUR", "RG_BASITFATURA", govde);
      if (!(typeof y.data === "string" && /sorun|hata|ge[cç]ersiz|zorunlu|yanl[ıi]ş/i.test(y.data))) { redler.length = 0; break; }
      redler.push("varyant " + v + ": " + y.data);
    }
    if (redler.length) throw new Error("GİB taslağı kabul etmedi (taslak OLUŞMADI) — " + redler.join(" | "));
    let yeni = [], say = 0;
    for (let i = 0; i < 4 && !yeni.length; i++) {
      if (i) await new Promise((r) => setTimeout(r, 1500));
      for (const ileri of [0, 1]) {
        try { const l = await this.liste(ileri); say = Math.max(say, l.length); yeni = l.filter((x) => !once.has(String(x.ettn).toLowerCase())); } catch (e) { /* ileri tarihli aralık reddedilebilir */ }
        if (yeni.length) break;
      }
    }
    let k = yeni.length === 1 ? yeni[0] : null;
    if (!k) { const e = yeni.filter((x) => String(x.aliciVknTckn) === String(govde.vknTckn)); if (e.length === 1) k = e[0]; }
    if (!k) throw new Error("GİB taslak yanıtı: " + JSON.stringify(y).slice(0, 300) + " — ama listede yeni kayıt görünmüyor (önce " + once.size + ", sonra " + say + " kayıt). Portalda Taslak Faturalar'ı kontrol edin; faturayı onaylamayın.");
    return { uuid: k.ettn, mesaj: y.data };
  }
  async smsGonder() {
    const tel = await this.dispatch("EARSIV_PORTAL_TELEFONNO_SORGULA", "RG_BASITTASLAKLAR", {});
    const y = await this.dispatch("EARSIV_PORTAL_SMSSIFRE_GONDER", "RG_SMSONAY", { CEPTEL: tel.data && tel.data.telefon || "", KCEPTEL: false, TIP: "" });
    return { oid: y.data && y.data.oid };
  }
  async imzala(uuid, kod, oid) {
    const kayitlar = await this.liste();
    const kucuk = String(uuid).toLowerCase();
    const fatura = kayitlar.filter((x) => String(x.ettn || "").toLowerCase() === kucuk)[0];
    if (!fatura) throw new Error("Taslak GİB listesinde bulunamadı (" + kayitlar.length + " kayıt). Portalda Taslak Faturalar'ı kontrol edin.");
    const y = await this.dispatch("EARSIV_PORTAL_SMSSIFRE_DOGRULA", "RG_SMSONAY", { SIFRE: kod, OID: oid, OPR: 1, DATA: [fatura] });
    return { mesaj: y.data };
  }
}

/* Fatura görünümü (HTML). Taslak için onay="Onaylanmadı", kesilmiş için "Onaylandı". DOĞRULANACAK: komut/alan adları */
Gib.prototype.faturaHtml = async function (uuid, onay) {
  const od = onay === "Onaylandı" ? "Onaylandı" : "Onaylanmadı";
  const denemeler = [
    ["RG_TASLAKLAR", { ettn: uuid, onayDurumu: od }],
    ["RG_BASITTASLAKLAR", { ettn: uuid, onayDurumu: od }],
    ["RG_TASLAKLAR", { ettn: uuid, belgeTip: "FATURA", onayDurumu: od }],
    ["RG_BASITTASLAKLAR", { ettn: uuid, belgeTip: "FATURA", onayDurumu: od }]
  ];
  const hatalar = [];
  for (const [sayfa, jp] of denemeler) {
    try {
      const y = await this.dispatch("EARSIV_PORTAL_FATURA_GOSTER", sayfa, jp);
      if (typeof y.data === "string" && y.data) return y.data;
      hatalar.push(sayfa + ": boş yanıt");
    } catch (e) { hatalar.push(sayfa + ": " + e.message); }
  }
  throw new Error(hatalar[hatalar.length - 1] + " (" + denemeler.length + " varyant denendi)");
};

/* ---------- sahte GİB (deneme) ---------- */
class SahteGib {
  constructor(kullanici) { this.k = kullanici; SahteGib.t = SahteGib.t || new Map(); }
  async taslak(g) { const govde = typeof g === "function" ? g(0) : g; SahteGib.t.set(govde.faturaUuid, govde); return { uuid: govde.faturaUuid, mesaj: "SAHTE: taslak oluşturuldu (" + govde.faturaTipi + ", ödenecek " + govde.odenecekTutar + ")" }; }
  async smsGonder() { return { oid: "SAHTE-OID" }; }
  async imzala(uuid, kod) {
    if (!SahteGib.t.has(uuid)) throw new Error("Taslak bulunamadı.");
    if (String(kod).trim() !== "123456") throw new Error("SMS kodu hatalı (sahte GİB için 123456).");
    SahteGib.o = SahteGib.o || new Map(); SahteGib.o.set(uuid, SahteGib.t.get(uuid)); SahteGib.t.delete(uuid); return { mesaj: "SAHTE: fatura onaylandı." };
  }
  async faturaHtml(uuid) {
    const g = (SahteGib.t && SahteGib.t.get(uuid)) || (SahteGib.o && SahteGib.o.get(uuid));
    if (!g) throw new Error("Fatura bulunamadı.");
    const k = g.malHizmetTable[0];
    return `<html><head><meta charset="utf-8"><title>Fatura ${g.faturaTarihi}</title></head><body style="font-family:sans-serif"><h2>SAHTE e-Arşiv Fatura (${g.faturaTipi})</h2><p>Tarih: ${g.faturaTarihi}<br>Alıcı: ${g.aliciUnvan || g.aliciAdi + " " + g.aliciSoyadi} (${g.vknTckn})</p><table border="1" cellpadding="6"><tr><td>${k.malHizmet}</td><td>${g.matrah}</td></tr><tr><td>KDV</td><td>${g.hesaplanankdv}</td></tr><tr><td><b>Ödenecek</b></td><td><b>${g.odenecekTutar}</b></td></tr></table></body></html>`;
  }
}

module.exports = { hesapla, faturaGovdesi, istemci: (k, s) => (MOCK ? new SahteGib(k) : new Gib(k, s)), MOCK };
