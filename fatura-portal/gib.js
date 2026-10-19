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
/* ---------- tutar yazıyla / fatura notu ---------- */
const BIRLER = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"];
const ONLAR = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"];
function ucBasamak(n) {
  const y = Math.floor(n / 100), o = Math.floor((n % 100) / 10), b = n % 10, k = [];
  if (y) { if (y > 1) k.push(BIRLER[y]); k.push("yüz"); }
  if (o) k.push(ONLAR[o]);
  if (b) k.push(BIRLER[b]);
  return k;
}
function sayiYazi(n) {
  if (n === 0) return "sıfır";
  const k = [];
  for (const [d, ad] of [[1e9, "milyar"], [1e6, "milyon"], [1e3, "bin"]]) {
    const q = Math.floor(n / d); n %= d;
    if (q) { if (!(d === 1e3 && q === 1)) k.push(...ucBasamak(q)); k.push(ad); }
  }
  if (n) k.push(...ucBasamak(n));
  return k.join(" ");
}
const basHarf = (m) => m.split(" ").map((w) => w.charAt(0).toLocaleUpperCase("tr-TR") + w.slice(1)).join(" ");
/* 120.50 TL -> "Yalnız Yüz Yirmi Türk Lirası Elli Kuruştur." */
function tutarYazi(kurus) {
  const lira = Math.floor(kurus / 100), kr = kurus % 100;
  let m = "Yalnız ";
  if (lira) m += basHarf(sayiYazi(lira)) + " Türk Lirası";
  if (kr) m += (lira ? " " : "") + basHarf(sayiYazi(kr)) + " Kuruş";
  return m + (kr ? "tur." : lira ? "dır." : "Sıfır Türk Lirasıdır.");
}
const temizMetin = (v, n) => String(v == null ? "" : v).replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim().slice(0, n);
/* Fatura notu: ek not + ödenecek tutar yazıyla + "İrsaliye yerine geçer." */
function notUret(g, h) {
  const k = [];
  if (g.notEk) k.push(temizMetin(g.notEk, 300));
  if (g.notYazi !== false && g.notYazi !== "false") k.push(tutarYazi(h.odenecek));
  if (g.notIrsaliye !== false && g.notIrsaliye !== "false") k.push("İrsaliye yerine geçer.");
  return k.join(" ");
}

const tl = (k) => (k / 100).toFixed(2); // "1234.50" — portal noktalı ondalık bekler

/* ---------- portal gövdesi ----------
 * Alan adları ve biçim, portalın kendi "Kaydet" isteğinden (EARSIV_PORTAL_FATURA_OLUSTUR) birebir alınmıştır.
 * faturaUuid boş gönderilir; ettn'i GİB verir. Tevkifat: vergiCesidi V9015, kalemde V9015Orani/V9015Tutari. */
const nf = (k) => String(Math.round(k) / 100); // portal "100", "20.1", "0.05" biçimini kullanır
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
  const tev = Number(g.tevkifat) > 0;
  const x = g._h;
  const kalem = {
    malHizmet: temizMetin(h.ad + (g.aciklama ? " - " + g.aciklama : ""), 250), miktar: 1, birim: "C62", birimFiyat: nf(x.matrah), fiyat: nf(x.matrah),
    iskontoOrani: 0, iskontoTutari: "0", iskontoNedeni: "", malHizmetTutari: nf(x.matrah),
    kdvOrani: String(Number(g.kdvOrani)), vergiOrani: 0, kdvTutari: nf(x.kdv), vergininKdvTutari: "0", ozelMatrahTutari: "0"
  };
  if (tev) Object.assign(kalem, { hesaplananotvtevkifatakatkisi: "0", tevkifatKodu: String(g.tevkifatKodu || ""), V9015Orani: Number(g.tevkifat) * 10, V9015Tutari: nf(x.tevKdv) });
  const govde = {
    faturaUuid: varyant === 1 ? uuid : "", belgeNumarasi: "", faturaTarihi: tarih, saat, paraBirimi: "TRY", dovzTLkur: "0",
    faturaTipi: tev ? "TEVKIFAT" : "SATIS", hangiTip: "5000/30000",
    vknTckn: g.aliciVkn, aliciUnvan: sahis ? "" : g.aliciUnvan.trim(), aliciAdi: sahis ? parca.join(" ") : "", aliciSoyadi: sahis ? soyad : "",
    binaAdi: "", binaNo: "", kapiNo: "", kasabaKoy: "", vergiDairesi: temizMetin(g.vergiDairesi, 100), ulke: "Türkiye", bulvarcaddesokak: temizMetin(g.aliciAdres, 250),
    irsaliyeNumarasi: "", irsaliyeTarihi: "", mahalleSemtIlce: "", sehir: " ", postaKodu: "", tel: "", fax: "", eposta: "", websitesi: "",
    iadeTable: [], ihracKayitliKarsiBelgeNo: "", yatirimTesvikNumarasi: "", yatirimTesvikTarihi: tarih, kdvOranKontrolMuafiyeti: false,
    vergiCesidi: tev ? "V9015" : " ",
    malHizmetTable: [kalem],
    tip: "İskonto", matrah: nf(x.matrah), malhizmetToplamTutari: nf(x.matrah), toplamIskonto: "0", hesaplanankdv: nf(x.kdv),
    vergilerToplami: nf(x.kdv), vergilerDahilToplamTutar: nf(x.toplam), odenecekTutar: nf(x.odenecek), not: g.not || "",
    siparisNumarasi: "", siparisTarihi: "", fisNo: "", fisTarihi: "", fisSaati: " ", fisTipi: " ", zRaporNo: "", okcSeriNo: ""
  };
  if (tev) Object.assign(govde, { tevkifataTabiIslemTutar: nf(x.matrah), tevkifataTabiIslemKdv: nf(x.kdv), hesaplananV9015: nf(x.tevKdv) });
  return govde;
}

/* ---------- gerçek istemci ---------- */
/* Liste satırının kimliği: ettn doluysa o, değilse satırın içeriği (GİB taslak satırında ettn boş gelebiliyor). */
const satirId = (x) => (x.ettn ? String(x.ettn) : "j:" + Buffer.from(JSON.stringify(x)).toString("base64url"));
const sekil = (x) => Object.keys(x).map((k) => k + "=" + (x[k] === "" || x[k] == null ? "boş" : String(x[k]).length + " krk")).join(", ");

/* Portalın "İndir" çıktısı ZIP içinde HTML (ya da doğrudan HTML) olabilir; bağımlılıksız küçük ZIP okuyucu. */
const zlib = require("zlib");
function zipDosyalari(b) {
  const out = new Map();
  let e = -1;
  for (let i = b.length - 22; i >= Math.max(0, b.length - 70000); i--) if (b.readUInt32LE(i) === 0x06054b50) { e = i; break; }
  if (e < 0) throw new Error("ZIP bitiş kaydı bulunamadı");
  let n = b.readUInt16LE(e + 10), o = b.readUInt32LE(e + 16);
  while (n-- > 0 && b.readUInt32LE(o) === 0x02014b50) {
    const yontem = b.readUInt16LE(o + 10), csize = b.readUInt32LE(o + 20), ad = b.readUInt16LE(o + 28), ek = b.readUInt16LE(o + 30), yo = b.readUInt16LE(o + 32), lh = b.readUInt32LE(o + 42);
    const isim = b.slice(o + 46, o + 46 + ad).toString("utf8");
    const bas = lh + 30 + b.readUInt16LE(lh + 26) + b.readUInt16LE(lh + 28), ham = b.slice(bas, bas + csize);
    out.set(isim, yontem === 8 ? zlib.inflateRawSync(ham) : ham);
    o += 46 + ad + ek + yo;
  }
  return out;
}
function htmlCikar(b) {
  if (b.length > 4 && b[0] === 0x50 && b[1] === 0x4b) {
    const d = zipDosyalari(b);
    for (const [isim, v] of d) if (/\.html?$/i.test(isim)) return v.toString("utf8");
    throw new Error("ZIP içinde HTML yok (dosyalar: " + [...d.keys()].join(", ") + ")");
  }
  const t = b.toString("utf8");
  if (/<html|<!doctype/i.test(t.slice(0, 500))) return t;
  throw new Error("İndirilen dosya HTML değil.");
}

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
  /* Belge listesi: portalın birden çok listeleme komutu var; hepsini deneyip birleştiririz.
   * Hangisinin kaç kayıt döndürdüğü this.tani içinde tutulur (hata mesajında gösterilir). */
  async liste() {
    const bugun = new Date(), p = (n) => String(n).padStart(2, "0");
    const f = (d) => `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
    const gun = (n) => f(new Date(bugun - n * 864e5));
    /* Portalın kendi isteği (DevTools'tan alındı): cmd EARSIV_PORTAL_TASLAKLARI_GETIR, pageName RG_BASITTASLAKLAR,
     * jp = {baslangic, bitis, hangiTip:"5000/30000"} — "table" alanı yok. */
    const denemeler = [
      ["BASIT/31g", "RG_BASITTASLAKLAR", gun(31), gun(0)],
      ["BASIT/7g", "RG_BASITTASLAKLAR", gun(7), gun(0)],
      ["TASLAK/7g", "RG_TASLAKLAR", gun(7), gun(0)]
    ];
    const hepsi = new Map(), tani = [];
    for (const [ad, sayfa, b1, b2] of denemeler) {
      try {
        const y = await this.dispatch("EARSIV_PORTAL_TASLAKLARI_GETIR", sayfa, { baslangic: b1, bitis: b2, hangiTip: "5000/30000" });
        const l = Array.isArray(y.data) ? y.data : [];
        const gercek = l.filter((x) => x && typeof x === "object" && (x.ettn || x.belgeNumarasi || x.aliciVknTckn));
        const uyari = l.filter((x) => x && x.error && !gercek.includes(x))[0];
        tani.push(ad + ":" + gercek.length + (uyari ? "(uyarı: " + String(uyari.error).slice(0, 50) + ")" : ""));
        for (const x of gercek) hepsi.set(satirId(x).toLowerCase(), x);
        if (gercek.length) break;
      } catch (e) { tani.push(ad + ":hata(" + String(e.message).slice(0, 60) + ")"); }
    }
    this.tani = tani.join(", ");
    this.ornek = hepsi.size ? sekil([...hepsi.values()][0]) : "";
    return [...hepsi.values()];
  }
  /* Belirli tarih aralığındaki belgeler (taslak/onaylı/silinmiş). Tarihler dd/mm/yyyy. */
  async listeAralik(bas, bit) {
    const al = (t) => { const [g, a, y] = t.split("/").map(Number); return new Date(y, a - 1, g); };
    const p = (n) => String(n).padStart(2, "0"), f = (d) => `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
    let bs = al(bas); const son = al(bit);
    if (!(bs <= son)) throw new Error("Başlangıç tarihi bitişten sonra olamaz.");
    if (son - bs > 120 * 864e5) bs = new Date(son - 120 * 864e5);
    const hepsi = new Map();
    for (let c = bs; c <= son; c = new Date(+c + 7 * 864e5)) { // portal 7 günlük aralıkla çalışıyor
      const kb = new Date(Math.min(+c + 6 * 864e5, +son));
      const y = await this.dispatch("EARSIV_PORTAL_TASLAKLARI_GETIR", "RG_BASITTASLAKLAR", { baslangic: f(c), bitis: f(kb), hangiTip: "5000/30000" });
      for (const x of Array.isArray(y.data) ? y.data : []) if (x && (x.ettn || x.belgeNumarasi)) hepsi.set(x.ettn || x.belgeNumarasi, { belgeNo: x.belgeNumarasi || "", alici: x.aliciUnvanAdSoyad || "", vkn: x.aliciVknTckn || "", tarih: x.belgeTarihi || "", durum: x.onayDurumu || "", ettn: x.ettn || "" });
    }
    return [...hepsi.values()].sort((a, b) => String(b.belgeNo).localeCompare(String(a.belgeNo)));
  }
  /* GİB taslağa kendi ettn'ini verir; yeni çıkan kaydı önce/sonra listesinden buluruz.
   * Liste oluşturma sonrası gecikmeli güncellenebilir: birkaç kez beklenip yeniden bakılır. */
  async taslak(govdeVeyaYapici) {
    const once = new Set((await this.liste()).map((x) => satirId(x).toLowerCase()));
    const yapici = typeof govdeVeyaYapici === "function" ? govdeVeyaYapici : () => govdeVeyaYapici;
    const varyantlar = typeof govdeVeyaYapici === "function" ? [0, 1] : [0];
    const redler = [];
    let y, govde;
    for (const v of varyantlar) {
      govde = yapici(v);
      y = await this.dispatch("EARSIV_PORTAL_FATURA_OLUSTUR", "RG_BASITFATURA", govde);
      if (!(typeof y.data === "string" && /sorun|hata|ge[cç]ersiz|zorunlu|yanl[ıi]ş|ettn|eksik|uymuyor/i.test(y.data))) { redler.length = 0; break; }
      redler.push("varyant " + v + ": " + y.data);
    }
    if (redler.length) throw new Error("GİB taslağı kabul etmedi (taslak OLUŞMADI) — " + redler.join(" | "));
    let yeni = [], say = 0;
    for (let i = 0; i < 4 && !yeni.length; i++) {
      if (i) await new Promise((r) => setTimeout(r, 2000));
      const l = await this.liste(); say = l.length;
      yeni = l.filter((x) => !once.has(satirId(x).toLowerCase()));
    }
    let k = yeni.length === 1 ? yeni[0] : null;
    if (!k) { const e = yeni.filter((x) => String(x.aliciVknTckn) === String(govde.vknTckn)); if (e.length === 1) k = e[0]; }
    if (!k) throw new Error("GİB taslak yanıtı: " + JSON.stringify(y).slice(0, 300) + " — ama listede yeni kayıt görünmüyor (önce " + once.size + ", sonra " + say + " kayıt). Liste denemeleri: " + this.tani + ". İlk kayıt alanları: " + (this.ornek || "-") + ". Portalda Taslak Faturalar'ı kontrol edin; faturayı onaylamayın.");
    return { uuid: satirId(k), mesaj: y.data, satir: k };
  }
  /* Portalın "İndir" isteği. DOĞRULANACAK: adres biçimi; GET ve POST sırayla denenir, hata ayrıntısı döner. */
  async indir(uuid, onay) {
    if (!this.token) await this.giris();
    const alanlar = { token: this.token, ettn: uuid, belgeTip: "FATURA", onayDurumu: onay === "Onaylandı" ? "Onaylandı" : "Onaylanmadı", cmd: "EARSIV_PORTAL_BELGE_INDIR" };
    const yol = BASE + "/earsiv-services/download";
    const hatalar = [];
    for (const yontem of ["GET", "POST"]) {
      try {
        const q = new URLSearchParams(alanlar).toString();
        const r = yontem === "GET" ? await fetch(yol + "?" + q) : await fetch(yol, { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded;charset=UTF-8" }, body: q });
        const b = Buffer.from(await r.arrayBuffer());
        try { return htmlCikar(b); } catch (e) { hatalar.push(yontem + " " + r.status + ": " + e.message + " [" + b.slice(0, 120).toString("utf8").replace(/\s+/g, " ") + "]"); }
      } catch (e) { hatalar.push(yontem + ": " + e.message); }
    }
    throw new Error(hatalar.join(" ; "));
  }
  async smsGonder() {
    const tel = await this.dispatch("EARSIV_PORTAL_TELEFONNO_SORGULA", "RG_BASITTASLAKLAR", {});
    const y = await this.dispatch("EARSIV_PORTAL_SMSSIFRE_GONDER", "RG_SMSONAY", { CEPTEL: tel.data && tel.data.telefon || "", KCEPTEL: false, TIP: "" });
    return { oid: y.data && y.data.oid };
  }
  async imzala(uuid, kod, oid) {
    const kayitlar = await this.liste();
    const fatura = kayitlar.filter((x) => satirId(x) === uuid)[0] || kayitlar.filter((x) => satirId(x).toLowerCase() === String(uuid).toLowerCase())[0];
    if (!fatura) throw new Error("Taslak GİB listesinde bulunamadı (" + kayitlar.length + " kayıt). Portalda Taslak Faturalar'ı kontrol edin.");
    if (fatura.onayDurumu && fatura.onayDurumu !== "Onaylanmadı") throw new Error("Bu belge onaylanabilir durumda değil (durum: " + fatura.onayDurumu + ").");
    /* Portalın kendi onay isteğinden (DevTools): cmd 0lhozfib5410mp, pageName RG_SMSONAY, DATA satırına grid alanları eklenir. */
    const satir = Object.assign({ faturaOid: "", toplamTutar: "0", saticiVknTckn: "", saticiUnvanAdSoyad: "", talepDurumColumn: "----------", iptalItiraz: "-99", talepDurum: "-99" }, fatura);
    const y = await this.dispatch("0lhozfib5410mp", "RG_SMSONAY", { SIFRE: kod, OID: oid, OPR: 1, DATA: [satir] });
    const d = y.data || {};
    if (String(d.sonuc) !== "1") throw new Error("GİB onayı kabul etmedi: " + (d.msg || JSON.stringify(y).slice(0, 200)));
    return { mesaj: d.msg || "Fatura onaylandı." };
  }
}

/* Fatura görünümü (HTML). Taslak için onay="Onaylanmadı", kesilmiş için "Onaylandı". DOĞRULANACAK: komut/alan adları */
Gib.prototype.faturaHtml = async function (id, onay) {
  let uuid = id;
  if (String(id).startsWith("j:")) { try { uuid = JSON.parse(Buffer.from(String(id).slice(2), "base64url").toString("utf8")).ettn; } catch (e) { uuid = ""; } }
  if (!uuid) throw new Error("Bu taslağın ettn kimliği GİB listesinde boş; görünüm alınamadı.");
  const od = onay === "Onaylandı" ? "Onaylandı" : "Onaylanmadı";
  try { return await this.indir(uuid, od); } catch (e) { var indirHata = "indir: " + e.message; }
  const denemeler = [
    ["RG_TASLAKLAR", { ettn: uuid, onayDurumu: od }],
    ["RG_BASITTASLAKLAR", { ettn: uuid, onayDurumu: od }],
    ["RG_TASLAKLAR", { ettn: uuid, belgeTip: "FATURA", onayDurumu: od }],
    ["RG_BASITTASLAKLAR", { ettn: uuid, belgeTip: "FATURA", onayDurumu: od }]
  ];
  const hatalar = [indirHata];
  for (const [sayfa, jp] of denemeler) {
    try {
      const y = await this.dispatch("EARSIV_PORTAL_FATURA_GOSTER", sayfa, jp);
      if (typeof y.data === "string" && y.data) return y.data;
      hatalar.push(sayfa + ": boş yanıt");
    } catch (e) { hatalar.push(sayfa + ": " + e.message); }
  }
  throw new Error(hatalar.join(" | ").slice(0, 400));
};

/* ---------- sahte GİB (deneme) ---------- */
class SahteGib {
  constructor(kullanici) { this.k = kullanici; SahteGib.t = SahteGib.t || new Map(); }
  async taslak(g) { const govde = typeof g === "function" ? g(0) : g; const uuid = crypto.randomUUID(); govde.faturaUuid = uuid; SahteGib.n = (SahteGib.n || 0) + 1; govde._no = "SAHTE" + String(SahteGib.n).padStart(6, "0"); SahteGib.t.set(uuid, govde); return { uuid, satir: { belgeNumarasi: govde._no }, mesaj: "SAHTE: taslak oluşturuldu (" + govde.faturaTipi + ", ödenecek " + govde.odenecekTutar + ")" }; }
  async smsGonder() { return { oid: "SAHTE-OID" }; }
  async imzala(uuid, kod) {
    if (!SahteGib.t.has(uuid)) throw new Error("Taslak bulunamadı.");
    if (String(kod).trim() !== "123456") throw new Error("SMS kodu hatalı (sahte GİB için 123456).");
    SahteGib.o = SahteGib.o || new Map(); SahteGib.o.set(uuid, SahteGib.t.get(uuid)); SahteGib.t.delete(uuid); return { mesaj: "SAHTE: fatura onaylandı." };
  }
  async listeAralik() {
    const hepsi = [];
    for (const [m, d] of [[SahteGib.t, "Onaylanmadı"], [SahteGib.o, "Onaylandı"]]) for (const [id, g] of (m || new Map())) hepsi.push({ belgeNo: g._no, alici: g.aliciUnvan || (g.aliciAdi + " " + g.aliciSoyadi), vkn: g.vknTckn, tarih: g.faturaTarihi.replace(/\//g, "-"), durum: d, ettn: id });
    return hepsi;
  }
  async faturaHtml(uuid) {
    const g = (SahteGib.t && SahteGib.t.get(uuid)) || (SahteGib.o && SahteGib.o.get(uuid));
    if (!g) throw new Error("Fatura bulunamadı.");
    const k = g.malHizmetTable[0];
    return `<html><head><meta charset="utf-8"><title>Fatura ${g.faturaTarihi}</title></head><body style="font-family:sans-serif"><h2>SAHTE e-Arşiv Fatura (${g.faturaTipi})</h2><p>Tarih: ${g.faturaTarihi}<br>Alıcı: ${g.aliciUnvan || g.aliciAdi + " " + g.aliciSoyadi} (${g.vknTckn})</p><table border="1" cellpadding="6"><tr><td>${k.malHizmet}</td><td>${g.matrah}</td></tr><tr><td>KDV</td><td>${g.hesaplanankdv}</td></tr><tr><td><b>Ödenecek</b></td><td><b>${g.odenecekTutar}</b></td></tr></table></body></html>`;
  }
}

module.exports = { zipDosyalari, htmlCikar, hesapla, notUret, tutarYazi, temizMetin, faturaGovdesi, istemci: (k, s) => (MOCK ? new SahteGib(k) : new Gib(k, s)), MOCK };
