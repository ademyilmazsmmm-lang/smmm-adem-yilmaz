"use strict";
/* SGK Vizite web servisi (iş göremezlik / istirahat raporu sorgulama) — YALNIZ OKUMA.
   Belge: "WS_VİZİTE (4/A çalışanlar için çalışmadı bildirim web servisi)". Güvenlik kodu gerekmez:
   wsLogin (kullanıcı kodu, işyeri kodu, işyeri şifresi) → 30 dk geçerli token → sorgu yöntemleri.
   Onay / iptal / "okundu kapat" / manuel bildirim yöntemleri bilerek YOK: bu modül hiçbir kaydı değiştirmez. */
const MOCK = process.env.GIB_MOCK === "1";
const ADRES = "https://uyg.sgk.gov.tr/Ws_Vizite/services/ViziteGonder";
const AD_ALANI = "http://service.com";
const kacis = (t) => String(t == null ? "" : t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const coz = (t) => String(t == null ? "" : t).replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&apos;|&#39;/g, "'").replace(/&#x([0-9a-f]+);/gi, (m, h) => String.fromCodePoint(parseInt(h, 16))).replace(/&#(\d+);/g, (m, d) => String.fromCodePoint(+d)).replace(/&amp;/g, "&");
const VAKA = { 1: "İş kazası", 2: "Meslek hastalığı", 3: "Hastalık", 4: "Analık" };
const DURUM = { 1: "Çalışır", 2: "Kontrol", 3: "Devamı verildi", 4: "Sevkli", 5: "Hastane kapattı", 6: "Çalışır (çakışma var)", 7: "Kontrol (çakışma var)", 8: "Maluliyet azaltılabilir, çalışır", 9: "Maluliyet sevk, çalışır", 10: "Analık doğum öncesi, çalışır", 11: "Analık doğum öncesi, çalışamaz", 12: "Analık doğum sonrası", 13: "Maluliyet azaltılır, kontrol", 14: "Maluliyet sevk, kontrol", 15: "Maluliyet azaltılır, kontrol, devam verildi", 16: "Maluliyet sevk, kontrol, devam verildi" };
const ALAN = { TCKIMLIKNO: "T.C. Kimlik No", AD: "Ad", SOYAD: "Soyad", MEDULARAPORID: "Rapor Id", RAPORTAKIPNO: "Rapor takip no", RAPORSIRANO: "Rapor sıra no", POLIKLINIKTAR: "Poliklinik tarihi", YATRAPBASTAR: "Yatarak rapor başlangıç", YATRAPBITTAR: "Yatarak rapor bitiş", ABASTAR: "Ayakta başlangıç", ABITTAR: "Ayakta bitiş", ISBASKONTTAR: "İşbaşı kontrol tarihi", DOGUMONCBASTAR: "Doğum öncesi başlangıç", RAPORBITTAR: "Rapor bitiş", ISKAZASITARIHI: "İş kazası tarihi", ISVERENEBILDIRILDIGITARIH: "İşverene bildirildiği tarih", RAPORDURUMU: "Rapor durumu", BASHEKIMONAYTARIHI: "Başhekim onay tarihi", VAKA: "Vaka", VAKAADI: "Vaka türü", TESISKODU: "Tesis kodu", TESISADI: "Sağlık tesisi", ARSIV: "Arşiv" };
const SIRA = Object.keys(ALAN);
const HATA = { 101: "Kullanıcı kodu boş.", 102: "İşyeri kodu boş.", 103: "Şifre boş.", 104: "Token boş.", 105: "Kullanıcı kodu, işyeri kodu veya şifre hatalı. Ayarlar'daki SGK bilgilerini (kullanıcı kodu = T.C. kimlik no, işyeri kodu, işyeri şifresi) kontrol edin.", 106: "Oturum süresi dolmuş.", 208: "Tarih boş.", 209: "Bitiş tarihi boş.", 210: "T.C. kimlik numarası boş.", 303: "Tarih biçimi geçersiz (gg.aa.yyyy olmalı).", 304: "Bitiş tarihi biçimi geçersiz.", 501: "Kayıt bulunamadı.", 503: "Seçtiğiniz tarih aralığında kayıt bulunamadı.", 910: "Bu T.C. kimlik numaralı sigortalı bu işyerinde çalışmıyor." };

/* küçük XML ağacı: ad alanı önekleri atılır; yalnız metin ve alt öğe */
function agac(xml) {
  const kok = { ad: "#", cocuk: [], metin: "" }, yigin = [kok];
  const re = /<!--[\s\S]*?-->|<\?[\s\S]*?\?>|<(\/?)([A-Za-z_][\w.\-]*:)?([A-Za-z_][\w.\-]*)([^>]*?)(\/?)>|([^<]+)/g; let m;
  while ((m = re.exec(xml))) {
    if (m[6] !== undefined) { const t = yigin[yigin.length - 1]; t.metin += m[6]; continue; }
    if (!m[3]) continue;
    if (m[1]) { if (yigin.length > 1) yigin.pop(); continue; }
    const d = { ad: m[3], cocuk: [], metin: "" }; yigin[yigin.length - 1].cocuk.push(d); if (!m[5]) yigin.push(d);
  }
  return kok;
}
const bul = (d, ad) => { for (const c of d.cocuk) { if (c.ad === ad) return c; const x = bul(c, ad); if (x) return x; } return null; };
/* satır: tüm alt öğeleri yaprak olan, en az 2 alanlı öğe */
function satirlar(d, out) {
  out = out || [];
  const yap = d.cocuk.filter((c) => !c.cocuk.length);
  if (d.cocuk.length >= 2 && yap.length === d.cocuk.length && !["sonucKod", "sonucAciklama"].includes(d.cocuk[0].ad)) { const o = {}; yap.forEach((c) => { const v = coz(c.metin).trim(); if (v) o[c.ad] = v; }); if (Object.keys(o).length) out.push(o); return out; }
  d.cocuk.forEach((c) => satirlar(c, out));
  return out;
}
const tarihTemiz = (v) => { const s = String(v || "").trim(); const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s); return m ? m[3] + "." + m[2] + "." + m[1] : s.replace(/T.*$/, ""); };
function satirDuzenle(o) {
  const alanlar = []; for (const k of SIRA) if (o[k] !== undefined && o[k] !== "") { let v = o[k]; if (/TAR|BAS|BIT/.test(k) && !/ID|NO|KOD|ADI/.test(k)) v = tarihTemiz(v); if (k === "VAKA") v = VAKA[+v] ? v + " – " + VAKA[+v] : v; if (k === "RAPORDURUMU") v = DURUM[+v] ? v + " – " + DURUM[+v] : v; alanlar.push({ k: ALAN[k], v }); }
  const ad = [o.AD, o.SOYAD].filter(Boolean).join(" ");
  return { tc: o.TCKIMLIKNO || "", ad, vaka: VAKA[+o.VAKA] || o.VAKAADI || "", durum: DURUM[+o.RAPORDURUMU] || "", baslangic: tarihTemiz(o.YATRAPBASTAR || o.ABASTAR || o.POLIKLINIKTAR || ""), bitis: tarihTemiz(o.RAPORBITTAR || o.YATRAPBITTAR || o.ABITTAR || ""), tesis: o.TESISADI || "", alanlar };
}

class Vizite {
  constructor(k) { this.k = k || {}; this.token = ""; this.tokenZaman = 0; }
  async zarf(islem, alanlar) {
    const gov = Object.entries(alanlar).map(([a, v]) => "<s:" + a + ">" + kacis(v) + "</s:" + a + ">").join("");
    const xml = '<?xml version="1.0" encoding="UTF-8"?><soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:s="' + AD_ALANI + '"><soapenv:Body><s:' + islem + ">" + gov + "</s:" + islem + "></soapenv:Body></soapenv:Envelope>";
    let r;
    try { r = await fetch(ADRES, { method: "POST", headers: { "content-type": "text/xml; charset=utf-8", soapaction: '""' }, body: xml, redirect: "error", signal: AbortSignal.timeout(30000) }); }
    catch (e) { throw new Error(e && (e.name === "TimeoutError" || e.name === "AbortError") ? "SGK 30 saniyede yanıt vermedi (zaman aşımı)." : "SGK'ya ulaşılamadı: " + e.message); }
    const metin = await r.text(), a = agac(metin), hata = bul(a, "faultstring");
    if (hata) throw new Error("SGK hata verdi: " + coz(hata.metin).slice(0, 200));
    if (!r.ok && !bul(a, "sonucKod")) throw new Error("SGK servisi beklenmeyen yanıt verdi (" + r.status + ").");
    a.ham = metin; return a;
  }
  sonuc(a) { const k = bul(a, "sonucKod"), x = bul(a, "sonucAciklama"); return { kod: k ? coz(k.metin).trim() : "", aciklama: x ? coz(x.metin).trim() : "" }; }
  async giris() {
    if (this.token && Date.now() - this.tokenZaman < 25 * 60e3) return;
    const k = this.k; if (!k.kullanici || !k.isyeriKod || !k.isyeriSifre) throw new Error("Önce Ayarlar'da bu mükellefin SGK kullanıcı kodu, işyeri kodu ve işyeri şifresini girin.");
    const a = await this.zarf("wsLogin", { kullaniciAdi: k.kullanici, isyeriKodu: k.isyeriKod, isyeriSifresi: k.isyeriSifre }), s = this.sonuc(a), t = bul(a, "wsToken");
    if (s.kod !== "0" || !t || !coz(t.metin).trim()) { const e = new Error("SGK Vizite girişi kabul edilmedi" + (HATA[s.kod] ? ": " + HATA[s.kod] : s.aciklama ? ": " + s.aciklama : "") + "."); e.giris = true; throw e; }
    this.token = coz(t.metin).trim(); this.tokenZaman = Date.now();
  }
  async sorgu(islem, ek) {
    await this.giris();
    const a = await this.zarf(islem, Object.assign({ kullaniciAdi: this.k.kullanici, isyeriKodu: this.k.isyeriKod, wsToken: this.token }, ek)), s = this.sonuc(a);
    if (s.kod === "106" || s.kod === "104") { this.token = ""; return this.sorgu(islem, ek); }
    const satir = satirlar(a).filter((o) => o.TCKIMLIKNO || o.MEDULARAPORID).map(satirDuzenle);
    const bos = !satir.length && s.kod && s.kod !== "0";
    const okunamadi = !satir.length && s.kod === "0"; /* SGK başarılı dedi ama satır çıkmadı: yanıt yapısı beklenenden farklı olabilir */
    return { kod: s.kod, uyari: bos ? (HATA[s.kod] || s.aciklama || "SGK kayıt döndürmedi.") : okunamadi ? "SGK başarılı yanıt verdi ama kayıt satırı okunamadı; aşağıdaki teknik ayrıntıyı gönderin." : "", aciklama: s.aciklama, satirlar: satir.slice(0, 300), ham: okunamadi ? String(a.ham || "").replace(/[A-Za-z0-9]{30,}/g, "<kod>").slice(0, 3000) : "" };
  }
  /* bir sigortalının raporları */
  kimlik(tc) { if (!/^\d{11}$/.test(String(tc))) throw new Error("T.C. kimlik numarası 11 haneli olmalı."); return this.sorgu("raporAramaKimlikNo", { tckNo: String(tc) }); }
  /* işyerine bildirilen açık raporlar (verilen tarihten önceki poliklinik tarihli ilk 100) */
  acik(tarih) { return this.sorgu("raporAramaTarihile", { tarih: Vizite.tarih(tarih) }); }
  /* tarih aralığında çalışmazlık bildirimi (onay) yapılmış raporlar */
  onayli(t1, t2) { return this.sorgu("onayliRaporlarTarihile", { tarih1: Vizite.tarih(t1), tarih2: Vizite.tarih(t2) }); }
  static tarih(v) { const s = String(v || "").trim(), m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s); if (m) return m[3] + "." + m[2] + "." + m[1]; if (/^\d{2}\.\d{2}\.\d{4}$/.test(s)) return s; throw new Error("Tarih geçersiz (gg.aa.yyyy)."); }
}

/* sahte (GIB_MOCK=1): ağa çıkmaz */
class SahteVizite {
  constructor(k) { this.k = k || {}; }
  async giris() { if (!this.k.kullanici || !this.k.isyeriKod || !this.k.isyeriSifre) throw new Error("Önce Ayarlar'da bu mükellefin SGK kullanıcı kodu, işyeri kodu ve işyeri şifresini girin."); }
  async kimlik(tc) { if (!/^\d{11}$/.test(String(tc))) throw new Error("T.C. kimlik numarası 11 haneli olmalı."); await this.giris(); return { kod: "0", uyari: "", aciklama: "Başarılı", satirlar: [satirDuzenle({ TCKIMLIKNO: tc, AD: "ÖRNEK", SOYAD: "KİŞİ", MEDULARAPORID: "123456", RAPORTAKIPNO: "1A2B3C", POLIKLINIKTAR: "2026-10-28", ABASTAR: "2026-10-28", ABITTAR: "2026-11-02", RAPORDURUMU: "1", VAKA: "3", VAKAADI: "Hastalık", TESISADI: "ÖRNEK DEVLET HASTANESİ" })] }; }
  async acik(t) { Vizite.tarih(t); await this.giris(); return { kod: "0", uyari: "", aciklama: "Başarılı", satirlar: [satirDuzenle({ TCKIMLIKNO: "11111111110", AD: "ÖRNEK", SOYAD: "KİŞİ", MEDULARAPORID: "1", ABASTAR: "2026-11-03", RAPORDURUMU: "2", VAKA: "3" })] }; }
  async onayli(a, b) { Vizite.tarih(a); Vizite.tarih(b); await this.giris(); return { kod: "503", uyari: "Seçtiğiniz tarih aralığında kayıt bulunamadı.", aciklama: "", satirlar: [] }; }
}

module.exports = { istemci: (k) => (MOCK ? new SahteVizite(k) : new Vizite(k)), agac, satirlar, satirDuzenle, Vizite };
