"use strict";
/* GİB e-Arşiv Portal istemcisi.
 * Resmi bir API yok; portalın kendi sayfalarının kullandığı uçlar kullanılır (earsiv-services/assos-login ve dispatch).
 * GIB_MOCK=1 ile gerçek portala bağlanmadan, bellekte çalışan sahte bir GİB kullanılır.
 * Alan adları "DOĞRULANACAK" ile işaretlenen yerler gerçek portalda ilk denemede kontrol edilmelidir. */
const crypto = require("crypto");

const MOCK = process.env.GIB_MOCK === "1";
const BASE = process.env.GIB_TEST === "1" ? "https://earsivportaltest.efatura.gov.tr" : "https://earsivportal.efatura.gov.tr";

/* ---------- hesap (kuruş cinsinden tam sayı) ----------
 * m: { tip: "SATIS"|"TEVKIFAT", kdvDahil, kalemler: [{ miktar, fiyat, kdv, tev }] }
 * Her satır ayrı hesaplanır (portalda da KDV satır bazında yuvarlanır), toplamlar satırların toplamıdır. */
function hesaplaFatura(m) {
  const tev = m.tip === "TEVKIFAT";
  const satirlar = (m.kalemler || []).map((k) => {
    const miktar = Number(k.miktar), fiyat = Number(k.fiyat), oran = Number(k.kdv), t = tev ? Number(k.tev) || 0 : 0;
    if (!(miktar > 0) || !(fiyat >= 0) || !(oran >= 0) || t < 0 || t > 10) throw new Error("Miktar, birim fiyat, KDV oranı veya tevkifat geçersiz.");
    const brut = Math.round(miktar * fiyat * 100);
    let matrah, kdv;
    if (m.kdvDahil) { matrah = Math.round(brut / (1 + oran / 100)); kdv = brut - matrah; }
    else { matrah = brut; kdv = Math.round(matrah * oran / 100); }
    const tevKdv = Math.round(kdv * t / 10);
    return { matrah, kdv, tev: t, tevKdv, toplam: matrah + kdv, oran, miktar };
  });
  if (!satirlar.length) throw new Error("En az bir mal/hizmet satırı gerekli.");
  const top = satirlar.reduce((a, x) => ({ matrah: a.matrah + x.matrah, kdv: a.kdv + x.kdv, tevKdv: a.tevKdv + x.tevKdv, toplam: a.toplam + x.toplam }), { matrah: 0, kdv: 0, tevKdv: 0, toplam: 0 });
  top.odenecek = top.toplam - top.tevKdv;
  return { satirlar, toplam: top };
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
const PARA = { TRY: ["Türk Lirası", "Kuruş"], USD: ["Amerikan Doları", "Sent"], EUR: ["Avro", "Sent"], GBP: ["İngiliz Sterlini", "Peni"] };
/* "Lirası" -> "Lirasıdır", "Kuruş" -> "Kuruştur", "Avro" -> "Avrodur" (ünlü uyumu + sert ünsüz) */
function bildirmeEki(k) {
  const sesli = "aıoueiöü";
  let v = "";
  for (let i = k.length - 1; i >= 0; i--) { const c = k[i].toLocaleLowerCase("tr-TR"); if (sesli.includes(c)) { v = c; break; } }
  const h = "aı".includes(v) ? "ı" : "ei".includes(v) ? "i" : "ou".includes(v) ? "u" : "ü";
  const son = k[k.length - 1].toLocaleLowerCase("tr-TR");
  return k + (!sesli.includes(son) && "çfhkpsşt".includes(son) ? "t" : "d") + h + "r";
}
/* 120.50 TL -> "Yalnız Yüz Yirmi Türk Lirası Elli Kuruştur." */
function tutarYazi(kurus, para) {
  const [ana, kurusAd] = PARA[para] || PARA.TRY;
  const lira = Math.floor(kurus / 100), kr = kurus % 100, parca = [];
  if (lira) parca.push(basHarf(sayiYazi(lira)) + " " + ana);
  if (kr) parca.push(basHarf(sayiYazi(kr)) + " " + kurusAd);
  if (!parca.length) parca.push("Sıfır " + ana);
  const t = parca.join(" "), i = t.lastIndexOf(" ");
  return "Yalnız " + t.slice(0, i + 1) + bildirmeEki(t.slice(i + 1)) + ".";
}
const temizMetin = (v, n) => String(v == null ? "" : v).replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim().slice(0, n);
/* Fatura notu: ek not + ödenecek tutar yazıyla + "İrsaliye yerine geçer." */
function notUret(m, toplam) {
  const k = [];
  if (m.notEk) k.push(temizMetin(m.notEk, 300));
  k.push(tutarYazi(toplam.odenecek, m.para || "TRY")); // her faturada ödenecek tutar yazıyla yer alır
  if (m.notIrsaliye !== false && m.notIrsaliye !== "false") k.push("İrsaliye yerine geçer.");
  return k.join(" ");
}

const tl = (k) => (k / 100).toFixed(2); // "1234.50" — portal noktalı ondalık bekler

/* GİB "sicil/MERNİS sorgusu" cevabı -> {ad, vd, adres}. Alan adları portalın form alanlarına benzer varsayılır; bilinmeyenler `alanlar` ile gösterilir. */
function kimlikEsle(d) {
  d = d && typeof d === "object" ? d : {};
  const v = (...k) => { for (const a of k) { const x = d[a]; if (x != null && String(x).trim()) return String(x).trim(); } return ""; };
  const adSoyad = [v("adi", "ad", "aliciAdi", "isim"), v("soyadi", "soyad", "aliciSoyadi")].filter(Boolean).join(" ");
  const unvan = v("unvan", "aliciUnvan", "ticariUnvan", "kimlikUnvan", "firmaUnvani", "unvanAdSoyad");
  const no = v("binaNo") && "No:" + v("binaNo"), kapi = v("kapiNo") && "Kapı:" + v("kapiNo");
  const adres = [v("bulvarcaddesokak", "adres", "cadde"), v("binaAdi"), no, kapi, v("mahalleSemtIlce", "mahalle"), v("kasabaKoy"), v("sehir", "il")].filter(Boolean).join(" ").replace(/\s+/g, " ").trim();
  return { ad: unvan || adSoyad, vd: v("vergiDairesi", "vdAdi", "vergiDairesiAdi"), adres, alanlar: Object.keys(d) };
}

/* ---------- portal gövdesi ----------
 * Alan adları ve biçim, portalın kendi "Kaydet" isteğinden (EARSIV_PORTAL_FATURA_OLUSTUR) birebir alınmıştır.
 * faturaUuid boş gönderilir; ettn'i GİB verir. Tevkifat: vergiCesidi V9015, kalemde V9015Orani/V9015Tutari. */
const nf = (k) => String(Math.round(k) / 100); // portal "100", "20.1", "0.05" biçimini kullanır
/* m: hazirla() çıktısı { alici:{unvan,vkn,adres,vd}, tip, para, kur, tarih, kalemler:[{ad,aciklama,miktar,birim,fiyat,kdv,tev,kod}], not, _h } */
/* Sunucu saat dilimi (Render'da UTC) ne olursa olsun Türkiye saati: gece 00-03 arası tarih bir gün geri kalmasın. */
function trParcalar() {
  const o = {};
  for (const x of new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Istanbul", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).formatToParts(new Date())) o[x.type] = x.value;
  return o;
}
const trBugunStr = () => { const o = trParcalar(); return `${o.year}-${o.month}-${o.day}`; };
const trBugunTarih = () => { const o = trParcalar(); return new Date(+o.year, +o.month - 1, +o.day); }; // yerel gece yarısı; yerel alıcılar Türkiye tarihini verir
function faturaGovdesi(m, uuid, varyant) {
  varyant = varyant || 0;
  const o = trParcalar();
  const t = /^(\d{4})-(\d{2})-(\d{2})$/.exec(m.tarih || "");
  const tarih = t ? `${t[3]}/${t[2]}/${t[1]}` : `${o.day}/${o.month}/${o.year}`;
  const saat = `${o.hour}:${o.minute}:${o.second}`;
  const a = m.alici, sahis = /^\d{11}$/.test(a.vkn);
  const parca = a.unvan.trim().split(/\s+/);
  const soyad = sahis && parca.length > 1 ? parca.pop() : "";
  const tev = m.tip === "TEVKIFAT", iade = m.tip === "IADE" && m.iade, ist = m.tip === "ISTISNA";
  const dmy = (y) => { const q = /^(\d{4})-(\d{2})-(\d{2})$/.exec(y || ""); return q ? `${q[3]}/${q[2]}/${q[1]}` : ""; };
  const x = m._h;
  const kalemler = m.kalemler.map((k, i) => {
    const s = x.satirlar[i];
    const bf = String(Number((s.matrah / 100 / Number(k.miktar)).toFixed(4))); // KDV hariç birim fiyat
    const satir = {
      malHizmet: temizMetin(k.ad + (k.aciklama ? " - " + k.aciklama : ""), 250), miktar: Number(k.miktar), birim: k.birim || "C62", birimFiyat: bf, fiyat: bf,
      iskontoOrani: 0, iskontoTutari: "0", iskontoNedeni: "", malHizmetTutari: nf(s.matrah),
      kdvOrani: String(Number(k.kdv)), vergiOrani: 0, kdvTutari: nf(s.kdv), vergininKdvTutari: "0", ozelMatrahTutari: "0"
    };
    if (ist) satir.istisnaKodu = String(k.istisna || ""); // portal alan adı doğrulanmadı
    if (tev) Object.assign(satir, { hesaplananotvtevkifatakatkisi: "0", tevkifatKodu: String(k.kod || ""), V9015Orani: Number(k.tev) * 10, V9015Tutari: nf(s.tevKdv) });
    return satir;
  });
  const govde = {
    faturaUuid: varyant === 1 ? uuid : "", belgeNumarasi: "", faturaTarihi: tarih, saat, paraBirimi: m.para || "TRY", dovzTLkur: (m.para || "TRY") === "TRY" ? "0" : String(Number(m.kur)),
    faturaTipi: tev ? "TEVKIFAT" : iade ? "IADE" : ist ? "ISTISNA" : "SATIS", hangiTip: "5000/30000",
    vknTckn: a.vkn, aliciUnvan: sahis ? "" : a.unvan.trim(), aliciAdi: sahis ? parca.join(" ") : "", aliciSoyadi: sahis ? soyad : "",
    binaAdi: "", binaNo: "", kapiNo: "", kasabaKoy: "", vergiDairesi: temizMetin(a.vd, 100), ulke: "Türkiye", bulvarcaddesokak: temizMetin(a.adres, 250),
    irsaliyeNumarasi: "", irsaliyeTarihi: "", mahalleSemtIlce: "", sehir: " ", postaKodu: "", tel: "", fax: "", eposta: "", websitesi: "",
    iadeTable: iade ? [{ faturaNo: temizMetin(m.iade.no, 30), duzenlenmeTarihi: dmy(m.iade.tarih) }] : [], ihracKayitliKarsiBelgeNo: "", yatirimTesvikNumarasi: "", yatirimTesvikTarihi: tarih, kdvOranKontrolMuafiyeti: false,
    vergiCesidi: tev ? "V9015" : " ",
    malHizmetTable: kalemler,
    tip: "İskonto", matrah: nf(x.toplam.matrah), malhizmetToplamTutari: nf(x.toplam.matrah), toplamIskonto: "0", hesaplanankdv: nf(x.toplam.kdv),
    vergilerToplami: nf(x.toplam.kdv), vergilerDahilToplamTutar: nf(x.toplam.toplam), odenecekTutar: nf(x.toplam.odenecek), not: m.not || "",
    siparisNumarasi: "", siparisTarihi: "", fisNo: "", fisTarihi: "", fisSaati: " ", fisTipi: " ", zRaporNo: "", okcSeriNo: ""
  };
  if (tev) Object.assign(govde, { tevkifataTabiIslemTutar: nf(x.toplam.matrah), tevkifataTabiIslemKdv: nf(x.toplam.kdv), hesaplananV9015: nf(x.toplam.tevKdv) });
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
  constructor(kullanici, sifre) { this.k = kullanici; this.s = sifre; this.token = null; this.cerez = new Map(); }
  /* Tarayıcı gibi oturum çerezini (JSESSIONID) saklayıp geri göndeririz; bazı servisler (örn. kimlik sorgusu) oturuma bakıyor. */
  cerezBaslik() { return [...this.cerez.values()].map((c) => c.ad + "=" + c.deger).join("; "); }
  cerezTopla(r) {
    // Portal iki ayrı sunucudan (ea-web, ea-side) aynı adlı JSESSIONID verir; ad+yol+değer ile ayrı tutulur.
    const liste = typeof r.headers.getSetCookie === "function" ? r.headers.getSetCookie() : [];
    for (const sc of liste) {
      const parca = sc.split(";").map((x) => x.trim()), kv = parca[0], i = kv.indexOf("=");
      if (i <= 0) continue;
      const yol = (parca.slice(1).find((x) => /^path=/i.test(x)) || "path=/earsiv-services").slice(5);
      const ad = kv.slice(0, i), deger = kv.slice(i + 1), sunucu = deger.split(".").slice(1).join(".");
      this.cerez.set(ad + "|" + yol + "|" + sunucu, { ad, deger });
    }
  }
  async post(yol, alanlar) {
    const baslik = { "content-type": "application/x-www-form-urlencoded;charset=UTF-8" };
    if (this.cerez.size) baslik.cookie = this.cerezBaslik();
    const r = await fetch(BASE + yol, { method: "POST", headers: baslik, body: new URLSearchParams(alanlar) });
    this.cerezTopla(r);
    const t = await r.text();
    try { return JSON.parse(t); } catch (e) { throw new Error("Portal beklenmeyen yanıt verdi (" + r.status + ")."); }
  }
  async giris() {
    const y = await this.post("/earsiv-services/assos-login", { assoscmd: process.env.GIB_TEST === "1" ? "login" : "anologin", rtype: "json", userid: this.k, sifre: this.s, sifre2: this.s, parola: "1" });
    if (!y.token) {
      const m = y.messages && y.messages[0] && y.messages[0].text || "";
      const acik = /oturum|başka|baska|açık|acik|eşzamanlı|zaten/i.test(m);
      throw new Error("GİB girişi başarısız: " + (m || "kullanıcı kodu/şifre hatalı olabilir.") + (acik ? "\nBu kullanıcı kodu GİB’de başka yerde açık görünüyor: GİB portalında (ya da başka cihazda) çıkış yapın, 1-2 dakika bekleyip tekrar deneyin." : ""));
    }
    this.token = y.token;
  }
  /* GİB oturumunu kapatır (en iyi çaba): aynı kullanıcı kodu başka yerde açılabilsin. Hata verirse sessizce geçilir. */
  async cikis() {
    const t = this.token; this.token = null;
    if (!t) { this.cerez.clear(); return; }
    try { await this.post("/earsiv-services/assos-login", { assoscmd: "logout", rtype: "json", token: t }); } catch (e) { /* önemli değil */ }
    this.cerez.clear();
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
    const bugun = trBugunTarih(), p = (n) => String(n).padStart(2, "0");
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
  /* Alıcı sorgusu: portalın VKN/TCKN girilince yaptığı istek (DevTools'tan: SICIL_VEYA_MERNISTEN_BILGILERI_GETIR, RG_BASITFATURA, {vknTcknn}) */
  async sorgula(vkn) {
    try {
      // Alan adı portalın kendi isteğinde "vknTcknn" (iki n); cevap: { unvan, adi, soyadi, vergiDairesi }
      const y = await this.dispatch("SICIL_VEYA_MERNISTEN_BILGILERI_GETIR", "RG_BASITFATURA", { vknTcknn: vkn });
      return kimlikEsle(y.data);
    } catch (e) {
      // GİB kayıt bulamayınca NullPointerException ile çöküyor: "kayıt yok" olarak ele alınır
      if (/NullPointer/i.test(e.message)) return { ad: "", vd: "", adres: "", alanlar: [], bulunamadi: true };
      throw e;
    }
  }
  /* Belirli tarih aralığındaki belgeler (taslak/onaylı/silinmiş). Tarihler dd/mm/yyyy. */
  async listeHam(bas, bit) {
    const al = (t) => { const [g, a, y] = t.split("/").map(Number); return new Date(y, a - 1, g); };
    const p = (n) => String(n).padStart(2, "0"), f = (d) => `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
    let bs = al(bas); const son = al(bit);
    if (!(bs <= son)) throw new Error("Başlangıç tarihi bitişten sonra olamaz.");
    if (son - bs > 120 * 864e5) bs = new Date(son - 120 * 864e5);
    const hepsi = new Map();
    for (let c = bs; c <= son; c = new Date(+c + 7 * 864e5)) { // portal 7 günlük aralıkla çalışıyor
      const kb = new Date(Math.min(+c + 6 * 864e5, +son));
      const y = await this.dispatch("EARSIV_PORTAL_TASLAKLARI_GETIR", "RG_BASITTASLAKLAR", { baslangic: f(c), bitis: f(kb), hangiTip: "5000/30000" });
      for (const x of Array.isArray(y.data) ? y.data : []) if (x && (x.ettn || x.belgeNumarasi)) hepsi.set(x.ettn || x.belgeNumarasi, x);
    }
    return [...hepsi.values()];
  }
  async listeAralik(bas, bit) {
    const ham = await this.listeHam(bas, bit);
    return ham.map((x) => ({ belgeNo: x.belgeNumarasi || "", alici: x.aliciUnvanAdSoyad || "", vkn: x.aliciVknTckn || "", tarih: x.belgeTarihi || "", durum: x.onayDurumu || "", ettn: x.ettn || "", talep: x.talepDurum === undefined || x.talepDurum === null ? "" : String(x.talepDurum) })).sort((a, b) => String(b.belgeNo).localeCompare(String(a.belgeNo)));
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
        const bas = this.cerez.size ? { cookie: this.cerezBaslik() } : {};
        const r = yontem === "GET" ? await fetch(yol + "?" + q, { headers: bas }) : await fetch(yol, { method: "POST", headers: Object.assign({ "content-type": "application/x-www-form-urlencoded;charset=UTF-8" }, bas), body: q });
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
  /* uuid (ya da liste satır kimliği) ile belge satırını bulur; eski belgeler için belge tarihi çevresinde de arar */
  async belgeBul(uuid, tarih) {
    const kayitlar = await this.liste();
    let fatura = kayitlar.filter((x) => satirId(x) === uuid)[0] || kayitlar.filter((x) => satirId(x).toLowerCase() === String(uuid).toLowerCase())[0];
    if (!fatura && /^\d{4}-\d{2}-\d{2}$/.test(tarih || "")) {
      const p2 = (n) => String(n).padStart(2, "0"), f2 = (d) => `${p2(d.getDate())}/${p2(d.getMonth() + 1)}/${d.getFullYear()}`;
      const d0 = new Date(tarih + "T00:00:00");
      const ham = await this.listeHam(f2(new Date(+d0 - 3 * 864e5)), f2(new Date(Math.min(+trBugunTarih(), +d0 + 3 * 864e5))));
      fatura = ham.filter((x) => String(x.ettn || "").toLowerCase() === String(uuid).toLowerCase())[0];
    }
    if (!fatura) throw new Error("Belge GİB listesinde bulunamadı (" + kayitlar.length + " kayıt). Portalda kontrol edin.");
    return fatura;
  }
  /* İşlemden sonra belgenin durumuna yeniden bakar (GİB listesi gecikmeli güncellenebilir). */
  async durumuOku(uuid, tarih) {
    for (let i = 0; i < 3; i++) {
      try { const f = await this.belgeBul(uuid, tarih); return f.onayDurumu || ""; } catch (e) { if (i === 2) return null; }
      await new Promise((r) => setTimeout(r, 1500));
    }
    return null;
  }
  async imzala(uuid, kod, oid, tarih) {
    const fatura = await this.belgeBul(uuid, tarih);
    if (fatura.onayDurumu && fatura.onayDurumu !== "Onaylanmadı") throw new Error("Bu belge onaylanabilir durumda değil (durum: " + fatura.onayDurumu + ").");
    /* Portalın kendi onay isteğinden (DevTools): cmd 0lhozfib5410mp, pageName RG_SMSONAY, DATA satırına grid alanları eklenir. */
    const satir = Object.assign({ faturaOid: "", toplamTutar: "0", saticiVknTckn: "", saticiUnvanAdSoyad: "", talepDurumColumn: "----------", iptalItiraz: "-99", talepDurum: "-99" }, fatura);
    const y = await this.dispatch("0lhozfib5410mp", "RG_SMSONAY", { SIFRE: kod, OID: oid, OPR: 1, DATA: [satir] });
    const d = y.data || {};
    if (String(d.sonuc) !== "1") throw new Error("GİB onayı kabul etmedi: " + (d.msg || JSON.stringify(y).slice(0, 200)));
    return { mesaj: d.msg || "Fatura onaylandı." };
  }
}

/* Taslak silme ve onaylı fatura iptali. DOĞRULANMADI: portalın gerçek isteği (DevTools) alınana kadar olası biçimler sırayla denenir;
 * hiçbiri belgenin durumunu değiştirmezse hata verilir. Doğru biçim bulununca yalnız bu iki liste güncellenir. */
const SIL_DENEMELERI = (f, neden) => [
  ["EARSIV_PORTAL_FATURA_SIL", "RG_BASITTASLAKLAR", { silinecekler: [f], aciklama: neden }],
  ["EARSIV_PORTAL_FATURA_SIL", "RG_TASLAKLAR", { silinecekler: [f], aciklama: neden }]
];
/* İptal talebi: portalın gerçek isteği (DevTools'tan alındı). Yanıt data = "İptal talebiniz başarıyla oluşturulmuştur."; belge "Onaylandı" kalır, listede talepDurum alanı belirir. */
const IPTAL_DENEMELERI = (f, neden) => [
  ["EARSIV_PORTAL_IPTAL_TALEBI_OLUSTUR", "RG_BASITTASLAKLAR", { ettn: f.ettn, onayDurumu: "Onaylandı", belgeTuru: f.belgeTuru || "FATURA", talepAciklama: neden }]
];
Gib.prototype.belgeIslemi = async function (tur, uuid, neden, tarih) {
  const sil = tur === "sil", beklenen = sil ? "Onaylanmadı" : "Onaylandı";
  const f = await this.belgeBul(uuid, tarih);
  if (f.onayDurumu && f.onayDurumu !== beklenen) throw new Error("Bu belge " + (sil ? "silinebilir" : "iptal edilebilir") + " durumda değil (durum: " + f.onayDurumu + ").");
  const hatalar = [];
  for (const [cmd, sayfa, jp] of (sil ? SIL_DENEMELERI : IPTAL_DENEMELERI)(f, neden)) {
    try {
      const y = await this.dispatch(cmd, sayfa, jp);
      const d = y.data;
      if (!sil && typeof d === "string") { if (/başar/i.test(d)) return { mesaj: d, durum: "iptal talebi oluşturuldu" }; hatalar.push(cmd + ": " + d); continue; }
      if (d && typeof d === "object" && d.sonuc !== undefined && String(d.sonuc) !== "1") { hatalar.push(cmd + "/" + sayfa + ": " + (d.msg || "reddedildi")); continue; }
    } catch (e) { hatalar.push(cmd + "/" + sayfa + ": " + e.message); continue; }
    const durum = await this.durumuOku(uuid, tarih);
    if (durum === null || durum !== beklenen) return { mesaj: sil ? "Taslak silindi." : "İptal talebi GİB’e iletildi.", durum: durum === null ? "(liste okunamadı)" : durum };
    hatalar.push(cmd + "/" + sayfa + ": GİB kabul etti ama belge durumu değişmedi");
  }
  throw new Error("GİB " + (sil ? "silme" : "iptal") + " işlemini yapmadı:\n" + hatalar.join("\n") + "\nGİB portalında işlemi yapıp F12 → Network’te dispatch isteğinin cmd, pageName ve jp alanlarını gönderirseniz doğru biçimi eklerim.");
};
Gib.prototype.sil = function (uuid, neden, tarih) { return this.belgeIslemi("sil", uuid, neden, tarih); };
Gib.prototype.iptal = function (uuid, neden, tarih) { return this.belgeIslemi("iptal", uuid, neden, tarih); };

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
  async cikis() {}
  async taslak(g) { const govde = typeof g === "function" ? g(0) : g; const uuid = crypto.randomUUID(); govde.faturaUuid = uuid; SahteGib.n = (SahteGib.n || 0) + 1; govde._no = "SAHTE" + String(SahteGib.n).padStart(6, "0"); SahteGib.t.set(uuid, govde); return { uuid, satir: { belgeNumarasi: govde._no }, mesaj: "SAHTE: taslak oluşturuldu (" + govde.faturaTipi + ", ödenecek " + govde.odenecekTutar + ")" }; }
  async smsGonder() { return { oid: "SAHTE-OID" }; }
  async sil(uuid) { if (!SahteGib.t.has(uuid)) throw new Error("Taslak bulunamadı."); SahteGib.t.delete(uuid); return { mesaj: "SAHTE: taslak silindi.", durum: "Silinmiş" }; }
  async iptal(uuid) {
    const g = SahteGib.o && SahteGib.o.get(uuid); if (!g) throw new Error("Onaylı fatura bulunamadı.");
    SahteGib.o.delete(uuid); SahteGib.i = SahteGib.i || new Map(); SahteGib.i.set(uuid, g); return { mesaj: "SAHTE: iptal talebi oluşturuldu.", durum: "iptal talebi oluşturuldu" };
  }
  async imzala(uuid, kod) {
    if (!SahteGib.t.has(uuid)) throw new Error("Taslak bulunamadı.");
    if (String(kod).trim() !== "123456") throw new Error("SMS kodu hatalı (sahte GİB için 123456).");
    SahteGib.o = SahteGib.o || new Map(); SahteGib.o.set(uuid, SahteGib.t.get(uuid)); SahteGib.t.delete(uuid); return { mesaj: "SAHTE: fatura onaylandı." };
  }
  async sorgula(vkn) { return kimlikEsle(vkn.length === 11 ? { adi: "ALİ", soyadi: "VELİ", vergiDairesi: "ÜMRANİYE VERGİ DAİRESİ MÜD.", bulvarcaddesokak: "DENEME CD.", binaNo: "5", mahalleSemtIlce: "ÜMRANİYE", sehir: "İSTANBUL" } : { unvan: "DENEME ANONİM ŞİRKETİ", vergiDairesi: "KADIKÖY", bulvarcaddesokak: "TEST SK." }); }
  async listeAralik() {
    const hepsi = [];
    for (const [m, d] of [[SahteGib.t, "Onaylanmadı"], [SahteGib.o, "Onaylandı"], [SahteGib.i, "İptal Edildi"]]) for (const [id, g] of (m || new Map())) hepsi.push({ belgeNo: g._no, alici: g.aliciUnvan || (g.aliciAdi + " " + g.aliciSoyadi), vkn: g.vknTckn, tarih: g.faturaTarihi.replace(/\//g, "-"), durum: d, ettn: id });
    return hepsi;
  }
  async faturaHtml(uuid) {
    const g = (SahteGib.t && SahteGib.t.get(uuid)) || (SahteGib.o && SahteGib.o.get(uuid));
    if (!g) throw new Error("Fatura bulunamadı.");
    const k = g.malHizmetTable[0];
    return `<html><head><meta charset="utf-8"><title>Fatura ${g.faturaTarihi}</title></head><body style="font-family:sans-serif"><div id="qrcode" style="float:right;width:120px"><canvas id="qrc" width="120" height="120"></canvas></div><script>(function(){var c=document.getElementById("qrc").getContext("2d");for(var i=0;i<12;i++)for(var j=0;j<12;j++)if((i*7+j*3)%5<2)c.fillRect(i*10,j*10,10,10)})()</script><h2>SAHTE e-Arşiv Fatura (${g.faturaTipi})</h2><p>Tarih: ${g.faturaTarihi}<br>Alıcı: ${g.aliciUnvan || g.aliciAdi + " " + g.aliciSoyadi} (${g.vknTckn})</p><table border="1" cellpadding="6"><tr><td>${k.malHizmet}</td><td>${g.matrah}</td></tr><tr><td>KDV</td><td>${g.hesaplanankdv}</td></tr><tr><td><b>Ödenecek</b></td><td><b>${g.odenecekTutar}</b></td></tr></table></body></html>`;
  }
}

module.exports = { trBugunStr, zipDosyalari, htmlCikar, hesaplaFatura, notUret, tutarYazi, temizMetin, faturaGovdesi, istemci: (k, s) => (MOCK ? new SahteGib(k) : new Gib(k, s)), MOCK };
