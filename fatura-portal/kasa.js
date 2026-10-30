"use strict";
/* Çok kullanıcılı şifreli depo.
 *
 *   DIR/sistem.json   : ofis hesabı (kullanıcı adı, ana anahtarın şifreyle sarılmış hali) + hesap/mükellef listesi (düz metin: yalnız kimlikler)
 *   DIR/m/<id>.json   : her mükellefin kasası. Veri rastgele bir kasa anahtarıyla (K) AES-256-GCM şifrelenir.
 *                       K iki kez sarılır: mükellefin şifresiyle (wrapSifre) ve ofis ana anahtarıyla (wrapOfis).
 *   Böylece mükellef yalnız kendi kasasını açar; ofis hepsini açar; şifresini unutan mükellef için ofis yeni şifre verir.
 *
 * Anahtarlar yalnızca oturum süresince bellekte durur. Disk şifrelidir; GİB şifreleri düz yazı olarak hiçbir yerde saklanmaz. */
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const b64 = (b) => Buffer.from(b).toString("base64");
const kdf = (sifre, tuz, iter) => new Promise((ok, no) => crypto.pbkdf2(String(sifre), tuz, iter, 32, "sha256", (e, k) => (e ? no(e) : ok(k))));
function sar(anahtar, veri) {
  const iv = crypto.randomBytes(12), c = crypto.createCipheriv("aes-256-gcm", anahtar, iv);
  const ct = Buffer.concat([c.update(veri), c.final()]);
  return { iv: b64(iv), tag: b64(c.getAuthTag()), ct: b64(ct) };
}
function ac(anahtar, o) {
  const d = crypto.createDecipheriv("aes-256-gcm", anahtar, Buffer.from(o.iv, "base64"));
  d.setAuthTag(Buffer.from(o.tag, "base64"));
  return Buffer.concat([d.update(Buffer.from(o.ct, "base64")), d.final()]); // yanlış anahtarda fırlatır
}
const KIMLIK = /^[A-Za-z0-9_-]{1,40}$/;
const B64 = /^[A-Za-z0-9+/=]+$/;
const sarmaGecerli = (o) => o && ["iv", "tag", "ct"].every((a) => typeof o[a] === "string" && o[a].length < 8e6 && B64.test(o[a]));

/* Kullanıcı adı: küçük harf, rakam, . _ - ; 3-32 karakter. Türkçe harfler ASCII'ye çevrilir. */
function adTemiz(s) {
  const t = { "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c" };
  return String(s || "").trim().replace(/[ıİşŞğĞüÜöÖçÇ]/g, (c) => t[c]).toLowerCase();
}
const adGecerli = (s) => /^[a-z0-9._-]{3,32}$/.test(s);

class Depo {
  constructor(dir, iter, varsayilanHizmet) {
    this.dir = dir; this.iter = iter; this.hizmet = varsayilanHizmet || [];
    this.sf = path.join(dir, "sistem.json"); this.md = path.join(dir, "m"); this.eski = path.join(dir, "kasa.json");
    this.acik = new Map(); // mükellef id -> { K, baslik, veri }
    this.sistem = null; this.yukleSistem();
    this.sahte = crypto.randomBytes(16); // bilinmeyen kullanıcıda da aynı süre harcamak için
  }
  yukleSistem() { try { this.sistem = JSON.parse(fs.readFileSync(this.sf, "utf8")); } catch (e) { this.sistem = null; } }
  get kurulu() { return !!this.sistem; }
  get eskiVar() { return !this.sistem && fs.existsSync(this.eski); }

  /* ---- dosya işlemleri ---- */
  yazDosya(yol, nesne) {
    fs.mkdirSync(path.dirname(yol), { recursive: true });
    const metin = JSON.stringify(nesne), g = yol + ".tmp"; fs.writeFileSync(g, metin); fs.renameSync(g, yol);
    const rel = path.relative(this.dir, yol);
    if (this.yansi && (rel === "sistem.json" || rel.startsWith("m" + path.sep))) this.yansi.yaz(rel, metin); // GitHub yansısı (varsa); eski tek-kasa dosyası gönderilmez
  }
  sistemYaz() { this.yazDosya(this.sf, this.sistem); }
  vaultYol(id) { if (!KIMLIK.test(id)) throw new Error("Geçersiz mükellef."); return path.join(this.md, id + ".json"); }
  vaultOku(id) { return JSON.parse(fs.readFileSync(this.vaultYol(id), "utf8")); }
  kaydet(id) {
    const e = this.acik.get(id); if (!e) throw new Error("Kasa açık değil.");
    this.yazDosya(this.vaultYol(id), Object.assign({ v: 2, id }, e.baslik, { veri: sar(e.K, Buffer.from(JSON.stringify(e.veri), "utf8")) }));
  }

  /* ---- kurulum ---- */
  async ofisOlustur(kullanici, sifre) {
    const M = crypto.randomBytes(32), tuz = crypto.randomBytes(16), KEK = await kdf(sifre, tuz, this.iter);
    this.sistem = { v: 2, olusturma: new Date().toISOString(), ofis: { kullanici, tuz: b64(tuz), iter: this.iter, wrap: sar(KEK, M) }, hesaplar: [], mukellefler: [] };
    this.sistemYaz();
    return { rol: "ofis", M, kullanici };
  }

  /* ---- giriş ---- */
  async ofisAc(kullanici, sifre) {
    const o = this.sistem.ofis, KEK = await kdf(sifre, Buffer.from(o.tuz, "base64"), o.iter);
    return { rol: "ofis", M: ac(KEK, o.wrap), kullanici: o.kullanici };
  }
  async giris(kullanici, sifre) {
    if (!this.sistem) throw new Error("Kurulu değil.");
    const ad = adTemiz(kullanici);
    if (ad === this.sistem.ofis.kullanici) return this.ofisAc(ad, sifre);
    const h = this.sistem.hesaplar.filter((x) => x.kullanici === ad)[0];
    if (!h) { await kdf(sifre, this.sahte, this.iter); throw new Error("Giriş başarısız."); }
    const v = this.vaultOku(h.id);
    if (!v.wrapSifre) throw new Error("Giriş başarısız.");
    const KEK = await kdf(sifre, Buffer.from(v.tuz, "base64"), v.iter), K = ac(KEK, v.wrapSifre);
    const baslik = { tuz: v.tuz, iter: v.iter, wrapSifre: v.wrapSifre, wrapOfis: v.wrapOfis };
    const veri = JSON.parse(ac(K, v.veri).toString("utf8"));
    this.acik.set(h.id, { K, baslik, veri });
    return { rol: "mukellef", mid: h.id, K, kullanici: ad };
  }

  /* ---- erişim ---- */
  yetkili(o, mid) { return o && (o.rol === "ofis" ? this.sistem.mukellefler.includes(mid) : o.mid === mid); }
  mukellefIdleri(o) { return o.rol === "ofis" ? this.sistem.mukellefler.slice() : [o.mid]; }
  mukellef(o, mid) {
    if (!this.yetkili(o, mid)) throw new Error("Bu mükellef için yetkiniz yok.");
    let e = this.acik.get(mid);
    if (!e) {
      if (o.rol !== "ofis") throw new Error("Kasa açık değil.");
      const v = this.vaultOku(mid), K = ac(o.M, v.wrapOfis);
      e = { K, baslik: { tuz: v.tuz, iter: v.iter, wrapSifre: v.wrapSifre, wrapOfis: v.wrapOfis }, veri: JSON.parse(ac(K, v.veri).toString("utf8")) };
      this.acik.set(mid, e);
    }
    return e;
  }
  /* Etkin oturumlardan hiçbirinin erişemediği kasalar bellekten atılır (anahtarlar dahil). */
  temizle(oturumlar) {
    const liste = [...oturumlar]; // oturumlar tek kullanımlık bir yineleyici olabilir (Map.values()): bir kez diziye alınmalı, yoksa ilk kasadan sonra boş görünür
    for (const id of [...this.acik.keys()]) {
      if (!liste.some((o) => o.rol === "ofis" || o.mid === id)) this.acik.delete(id);
    }
  }

  /* ---- mükellef / hesap yönetimi (yalnız ofis) ---- */
  varsayilanVeri(id, b) {
    return { id, ad: String(b.ad || "").slice(0, 150), vkn: String(b.vkn || "").slice(0, 11), kullanici: String(b.kullanici || "").slice(0, 60), gibSifre: String(b.gibSifre || ""), earsiv: b.earsiv !== false, aliciler: [],
      hizmetler: this.hizmet.map((h) => Object.assign({}, h)), hazirV2: true, marka: { logo: "", imza: "" }, gecmis: [], gunluk: [], sonGiris: null };
  }
  async mukellefEkle(o, b, veriHazir, idHazir) {
    if (o.rol !== "ofis") throw new Error("Yalnız ofis hesabı mükellef ekleyebilir.");
    const id = idHazir || crypto.randomBytes(5).toString("hex"), K = crypto.randomBytes(32);
    const veri = veriHazir || this.varsayilanVeri(id, b);
    const tuz = crypto.randomBytes(16);
    this.acik.set(id, { K, baslik: { tuz: b64(tuz), iter: this.iter, wrapSifre: null, wrapOfis: sar(o.M, K) }, veri });
    this.kaydet(id);
    this.sistem.mukellefler.push(id); this.sistemYaz();
    return id;
  }
  adMusait(ad, haric) { return ad !== this.sistem.ofis.kullanici && !this.sistem.hesaplar.some((h) => h.kullanici === ad && h.id !== haric); }
  async hesapAyarla(o, mid, kullanici, sifre) {
    if (o.rol !== "ofis") throw new Error("Yetkiniz yok.");
    const ad = adTemiz(kullanici);
    if (!adGecerli(ad)) throw new Error("Kullanıcı adı 3-32 karakter olmalı (harf, rakam, nokta, tire, alt çizgi).");
    if (!this.adMusait(ad, mid)) throw new Error("Bu kullanıcı adı kullanılıyor.");
    const e = this.mukellef(o, mid), tuz = crypto.randomBytes(16);
    if (sifre) { e.baslik.tuz = b64(tuz); e.baslik.iter = this.iter; e.baslik.wrapSifre = sar(await kdf(sifre, tuz, this.iter), e.K); this.kaydet(mid); }
    else if (!e.baslik.wrapSifre) throw new Error("Yeni hesap için şifre belirleyin.");
    const h = this.sistem.hesaplar.filter((x) => x.id === mid)[0];
    if (h) h.kullanici = ad; else this.sistem.hesaplar.push({ id: mid, kullanici: ad });
    this.sistemYaz();
    return ad;
  }
  hesapKaldir(o, mid) {
    if (o.rol !== "ofis") throw new Error("Yetkiniz yok.");
    const e = this.mukellef(o, mid); e.baslik.wrapSifre = null; this.kaydet(mid);
    this.sistem.hesaplar = this.sistem.hesaplar.filter((x) => x.id !== mid); this.sistemYaz();
  }
  mukellefSil(o, mid) {
    if (o.rol !== "ofis") throw new Error("Yetkiniz yok.");
    if (!this.yetkili(o, mid)) throw new Error("Mükellef bulunamadı.");
    try { fs.unlinkSync(this.vaultYol(mid)); } catch (e) { /* zaten yok */ }
    if (this.yansi) this.yansi.sil(path.relative(this.dir, this.vaultYol(mid)));
    try { fs.unlinkSync(this.belgeYol(mid)); if (this.yansi) this.yansi.sil(path.relative(this.dir, this.belgeYol(mid))); } catch (e) { /* belge dosyası yoktu */ }
    this.acik.delete(mid);
    this.sistem.mukellefler = this.sistem.mukellefler.filter((x) => x !== mid); this.sistem.hesaplar = this.sistem.hesaplar.filter((x) => x.id !== mid); this.sistemYaz();
  }
  hesapKullanicisi(mid) { const h = this.sistem.hesaplar.filter((x) => x.id === mid)[0]; return h ? h.kullanici : ""; }
  async sifreDegistir(o, eski, yeni) {
    if (o.rol === "ofis") {
      const s = this.sistem.ofis, KEK = await kdf(eski, Buffer.from(s.tuz, "base64"), s.iter); ac(KEK, s.wrap); // eski şifre doğrulanır
      const tuz = crypto.randomBytes(16); s.tuz = b64(tuz); s.iter = this.iter; s.wrap = sar(await kdf(yeni, tuz, this.iter), o.M); this.sistemYaz(); return;
    }
    const e = this.mukellef(o, o.mid), v = e.baslik;
    ac(await kdf(eski, Buffer.from(v.tuz, "base64"), v.iter), v.wrapSifre); // eski şifre doğrulanır
    const tuz = crypto.randomBytes(16); v.tuz = b64(tuz); v.iter = this.iter; v.wrapSifre = sar(await kdf(yeni, tuz, this.iter), e.K); this.kaydet(o.mid);
  }

  /* ---- belgeler (imza sirküleri, faaliyet belgesi vb.) ----
   * Her mükellefin belgeleri ayrı şifreli dosyada (m/<id>.belge.json) durur: asıl kasa her kayıtta yeniden yazıldığı için büyük dosyalar onu şişirmesin.
   * Aynı kasa anahtarıyla (K) şifrelenir; GitHub yansısına da m/ klasöründen otomatik gider. Taşınabilir yedek paketine girmez (boyut): orijinaller ofiste durur. */
  belgeYol(id) { if (!KIMLIK.test(id)) throw new Error("Geçersiz mükellef."); return path.join(this.md, id + ".belge.json"); }
  belgeler(o, mid) {
    const e = this.mukellef(o, mid);
    if (!e.belge) {
      let f = null; try { f = JSON.parse(fs.readFileSync(this.belgeYol(mid), "utf8")); } catch (x) { if (x.code !== "ENOENT") throw x; } // yalnız "dosya yok" boş sayılır; bozuk/şifresi çözülemeyen dosya sessizce sıfırlanmaz
      e.belge = f ? (JSON.parse(ac(e.K, f.veri).toString("utf8")).belgeler || []) : [];
    }
    return e.belge;
  }
  belgeYaz(mid) {
    const e = this.acik.get(mid); if (!e || !e.belge) throw new Error("Kasa açık değil.");
    this.yazDosya(this.belgeYol(mid), { v: 1, id: mid, veri: sar(e.K, Buffer.from(JSON.stringify({ belgeler: e.belge }), "utf8")) });
  }
  belgeListe(o, mid) { return this.belgeler(o, mid).map((b) => ({ id: b.id, tur: b.tur, ad: b.ad, tip: b.tip, boyut: b.boyut, zaman: b.zaman })); }
  belgeEkle(o, mid, b) {
    if (o.rol !== "ofis") throw new Error("Belgeleri yalnız ofis yükleyebilir.");
    const liste = this.belgeler(o, mid);
    if (liste.length >= 12) throw new Error("Bir mükellef için en çok 12 belge yüklenebilir; önce eskisini silin.");
    if (liste.reduce((t, x) => t + x.boyut, 0) + b.boyut > 9e6) throw new Error("Bu mükellefin belgeleri toplam 9 MB sınırını aşıyor.");
    const k = { id: crypto.randomBytes(6).toString("hex"), tur: b.tur, ad: b.ad, tip: b.tip, boyut: b.boyut, zaman: new Date().toISOString(), veri: b.veri };
    liste.push(k); this.belgeYaz(mid); return k;
  }
  belgeAl(o, mid, id) { const b = this.belgeler(o, mid).filter((x) => x.id === id)[0]; if (!b) throw new Error("Belge bulunamadı."); return b; }
  belgeSil(o, mid, id) {
    if (o.rol !== "ofis") throw new Error("Belgeleri yalnız ofis silebilir.");
    const liste = this.belgeler(o, mid), i = liste.findIndex((x) => x.id === id); if (i < 0) throw new Error("Belge bulunamadı.");
    const [k] = liste.splice(i, 1); this.belgeYaz(mid); return k;
  }

  /* ---- yedek ---- */
  paket(o) {
    if (o.rol !== "ofis") throw new Error("Yetkiniz yok.");
    const kasalar = {}; for (const id of this.sistem.mukellefler) { try { kasalar[id] = this.vaultOku(id); } catch (e) { /* eksik dosya atlanır */ } }
    return { surum: 2, zaman: new Date().toISOString(), sistem: this.sistem, kasalar };
  }
  paketGecerli(p) {
    const s = p && p.sistem;
    if (!s || s.v !== 2 || !s.ofis || typeof s.ofis.kullanici !== "string" || !sarmaGecerli(s.ofis.wrap) || typeof s.ofis.tuz !== "string" || !Number.isInteger(s.ofis.iter) || s.ofis.iter < 1000 || s.ofis.iter > 2e6) return false;
    if (!Array.isArray(s.mukellefler) || !Array.isArray(s.hesaplar) || !s.mukellefler.every((x) => KIMLIK.test(x))) return false;
    return Object.keys(p.kasalar || {}).every((id) => KIMLIK.test(id) && p.kasalar[id] && sarmaGecerli(p.kasalar[id].veri) && sarmaGecerli(p.kasalar[id].wrapOfis));
  }
  async paketYukle(p, kullanici, sifre) {
    if (this.sistem) throw new Error("Sunucuda kayıt zaten var.");
    if (!this.paketGecerli(p)) throw new Error("Yedek biçimi geçersiz.");
    const ad = adTemiz(kullanici);
    if (ad !== p.sistem.ofis.kullanici) { await kdf(sifre, this.sahte, this.iter); throw new Error("Giriş başarısız."); }
    const o = p.sistem.ofis, M = ac(await kdf(sifre, Buffer.from(o.tuz, "base64"), o.iter), o.wrap); // yanlış şifrede fırlatır
    for (const id of Object.keys(p.kasalar)) { const v = p.kasalar[id], K = ac(M, v.wrapOfis); ac(K, v.veri); } // her kasa doğrulanır
    for (const id of Object.keys(p.kasalar)) this.yazDosya(this.vaultYol(id), p.kasalar[id]);
    this.sistem = p.sistem; this.sistemYaz();
    return { rol: "ofis", M, kullanici: ad };
  }

  /* ---- eski tek kasadan (kasa.json, v1) taşıma: mükellef başına ayrı kasa ---- */
  async eskiyiTasi(kullanici, sifre) {
    if (!this.eskiVar) throw new Error("Taşınacak eski kayıt yok.");
    const ad = adTemiz(kullanici);
    if (!adGecerli(ad)) throw new Error("Kullanıcı adı 3-32 karakter olmalı (harf, rakam, nokta, tire, alt çizgi).");
    const k = JSON.parse(fs.readFileSync(this.eski, "utf8")), tuz = Buffer.from(k.tuz, "base64"), kk = await kdf(sifre, tuz, k.iter);
    const eski = JSON.parse(ac(kk, { iv: k.iv, tag: k.tag, ct: k.veri }).toString("utf8")); // yanlış şifrede fırlatır
    const o = await this.ofisOlustur(ad, sifre);
    const hizmetler = (eski.hizmetler && eski.hizmetler.length ? eski.hizmetler : this.hizmet).map((h) => Object.assign({}, h)), mk = eski.mukellefler || [], gecmis = eski.gecmis || [];
    mk.forEach((m, i) => {
      const veri = this.varsayilanVeri(String(m.id), m);
      Object.assign(veri, { aliciler: m.aliciler || [], hizmetler: hizmetler.map((h) => Object.assign({}, h)), marka: eski.marka || { logo: "", imza: "" }, hazirV2: true,
        gecmis: gecmis.filter((g) => g.mukellefId === m.id || (!g.mukellefId && i === 0)) });
      // eski kimlikler dosya adına uygun değilse yenisi verilir (geçmiş kayıtlarındaki mukellefId de güncellenir)
      let id = String(m.id); if (!KIMLIK.test(id)) { id = crypto.randomBytes(5).toString("hex"); veri.id = id; veri.gecmis.forEach((g) => { g.mukellefId = id; }); }
      this.mukellefEkleSenkron(o, veri, id);
    });
    fs.renameSync(this.eski, path.join(this.dir, "kasa.eski.json"));
    return o;
  }
  mukellefEkleSenkron(o, veri, id) {
    const K = crypto.randomBytes(32);
    this.acik.set(id, { K, baslik: { tuz: b64(crypto.randomBytes(16)), iter: this.iter, wrapSifre: null, wrapOfis: sar(o.M, K) }, veri });
    this.kaydet(id); this.sistem.mukellefler.push(id); this.sistemYaz();
  }
}

module.exports = { Depo, adTemiz, adGecerli };
