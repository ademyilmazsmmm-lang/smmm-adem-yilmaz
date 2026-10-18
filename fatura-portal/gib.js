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
function faturaGovdesi(g, h, uuid) {
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
    faturaUuid: uuid, belgeNumarasi: "", faturaTarihi: tarih, saat, paraBirimi: "TRY", dovzTLkur: "0",
    faturaTipi: tevkifatli ? "TEVKIFAT" : "SATIS", /* DOĞRULANACAK: tevkifat için tip değeri */
    vknTckn: g.aliciVkn, aliciUnvan: sahis ? "" : g.aliciUnvan.trim(), aliciAdi: sahis ? parca.join(" ") : "", aliciSoyadi: sahis ? soyad : "",
    binaAdi: "", binaNo: "", kapiNo: "", kasabaKoy: "", vergiDairesi: "", ulke: "Türkiye", bulvarcaddesokak: g.aliciAdres || "",
    irsaliyeNumarasi: "", mahalleSemtIlce: "", sehir: " ", postaKodu: "", tel: "", fax: "", eposta: "", websitesi: "",
    iadeTable: [], ozelMatrahTutari: "0", ozelMatrahOrani: 0, ozelMatrahVergiTutari: "0", vergiCesidi: " ",
    malhizmetTable: [{
      malHizmet: h.ad, miktar: 1, birim: "C62", birimFiyat: tl(g._h.matrah), fiyat: tl(g._h.matrah),
      iskontoArttm: "İskonto", iskontoOrani: 0, iskontoTutari: "0", iskontoNedeni: "",
      malHizmetTutari: tl(g._h.matrah), kdvOrani: Number(g.kdvOrani), vergiOrani: 0, kdvTutari: tl(g._h.kdv), vergininKdvTutari: "0",
      ...(tevkifatli ? { tevkifatKodu: String(g.tevkifatKodu || "") } : {}) /* kod kalem bazında; oranı portal koddan türetir (mlevent/fatura örneği) */
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
  async taslak(govde) {
    const y = await this.dispatch("EARSIV_PORTAL_FATURA_OLUSTUR", "RG_BASITFATURA", govde);
    return { uuid: govde.faturaUuid, mesaj: y.data };
  }
  async smsGonder() {
    const tel = await this.dispatch("EARSIV_PORTAL_TELEFONNO_SORGULA", "RG_BASITTASLAKLAR", {});
    const y = await this.dispatch("EARSIV_PORTAL_SMSSIFRE_GONDER", "RG_SMSONAY", { CEPTEL: tel.data && tel.data.telefon || "", KCEPTEL: false, TIP: "" });
    return { oid: y.data && y.data.oid };
  }
  async imzala(uuid, kod, oid, tarih) {
    const bugun = new Date(), p = (n) => String(n).padStart(2, "0");
    const f = (d) => `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
    const fd = /^\d{4}-\d{2}-\d{2}$/.test(tarih || "") ? new Date(tarih + "T00:00:00") : bugun;
    const bas = new Date(Math.min(bugun - 7 * 864e5, fd - 864e5)), bit = new Date(Math.max(+bugun, +fd) + 864e5);
    const liste = await this.dispatch("EARSIV_PORTAL_TASLAKLARI_GETIR", "RG_TASLAKLAR", { baslangic: f(bas), bitis: f(bit), hangiTip: "5000/30000", table: [] });
    const fatura = (liste.data || []).filter((x) => x.ettn === uuid)[0];
    if (!fatura) throw new Error("Taslak GİB'de bulunamadı (son 7 gün).");
    const y = await this.dispatch("EARSIV_PORTAL_SMSSIFRE_DOGRULA", "RG_SMSONAY", { SIFRE: kod, OID: oid, OPR: 1, DATA: [fatura] });
    return { mesaj: y.data };
  }
}

/* Fatura görünümü (HTML). Taslak için onay="Onaylanmadı", kesilmiş için "Onaylandı". DOĞRULANACAK: komut/alan adları */
Gib.prototype.faturaHtml = async function (uuid, onay) {
  const y = await this.dispatch("EARSIV_PORTAL_FATURA_GOSTER", "RG_TASLAKLAR", { ettn: uuid, onayDurumu: onay === "Onaylandı" ? "Onaylandı" : "Onaylanmadı" });
  if (typeof y.data !== "string" || !y.data) throw new Error("GİB fatura görünümü döndürmedi.");
  return y.data;
};

/* ---------- sahte GİB (deneme) ---------- */
class SahteGib {
  constructor(kullanici) { this.k = kullanici; SahteGib.t = SahteGib.t || new Map(); }
  async taslak(govde) { SahteGib.t.set(govde.faturaUuid, govde); return { uuid: govde.faturaUuid, mesaj: "SAHTE: taslak oluşturuldu (" + govde.faturaTipi + ", ödenecek " + govde.odenecekTutar + ")" }; }
  async smsGonder() { return { oid: "SAHTE-OID" }; }
  async imzala(uuid, kod) {
    if (!SahteGib.t.has(uuid)) throw new Error("Taslak bulunamadı.");
    if (String(kod).trim() !== "123456") throw new Error("SMS kodu hatalı (sahte GİB için 123456).");
    SahteGib.o = SahteGib.o || new Map(); SahteGib.o.set(uuid, SahteGib.t.get(uuid)); SahteGib.t.delete(uuid); return { mesaj: "SAHTE: fatura onaylandı." };
  }
  async faturaHtml(uuid) {
    const g = (SahteGib.t && SahteGib.t.get(uuid)) || (SahteGib.o && SahteGib.o.get(uuid));
    if (!g) throw new Error("Fatura bulunamadı.");
    const k = g.malhizmetTable[0];
    return `<html><head><meta charset="utf-8"><title>Fatura ${g.faturaTarihi}</title></head><body style="font-family:sans-serif"><h2>SAHTE e-Arşiv Fatura (${g.faturaTipi})</h2><p>Tarih: ${g.faturaTarihi}<br>Alıcı: ${g.aliciUnvan || g.aliciAdi + " " + g.aliciSoyadi} (${g.vknTckn})</p><table border="1" cellpadding="6"><tr><td>${k.malHizmet}</td><td>${g.matrah}</td></tr><tr><td>KDV</td><td>${g.hesaplanankdv}</td></tr><tr><td><b>Ödenecek</b></td><td><b>${g.odenecekTutar}</b></td></tr></table></body></html>`;
  }
}

module.exports = { hesapla, faturaGovdesi, istemci: (k, s) => (MOCK ? new SahteGib(k) : new Gib(k, s)), MOCK };
