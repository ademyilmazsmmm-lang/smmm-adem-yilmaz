/* Güvenlik bildirimleri ve yedek sağlığı (bağımlılıksız).
 *  - Ofis ve çalışan hesabıyla YENİ CİHAZDAN girişte, ve herhangi bir hesaba art arda BAŞARISIZ denemede ofise e-posta gider (OFIS_EPOSTA + e-posta servisi gerekir).
 *  - Giriş olayları son 100 kayıt olarak tutulur (ofis Ayarlar'dan görür); e-posta kapalıysa da kayıt tutulur.
 *  - Cihaz tanıma: tarayıcıya rastgele bir "cihaz" çerezi verilir; sunucuda yalnız (kullanıcı + çerez) özeti (SHA-256) saklanır. Çerez tek başına hiçbir yetki vermez.
 *    Cihaz özetleri GitHub yansısına da yazılır (sunucu yeniden kurulursa herkesin cihazı "yeni" sayılıp e-posta yağmaz); IP ve tarayıcı bilgisi ise yalnız yerelde, kayıt dosyasında kalır.
 *  - Yedek sağlığı: GitHub yansısının son sağlam zamanı, elle şifreli yedek alma zamanı; Ana ekranda uyarı için değerlendirir. */
"use strict";
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const IKI_GUN = 2 * 864e5, YEDI_GUN = 7 * 864e5;
const bugun = () => Date.now();
const zamanTr = (ms) => new Intl.DateTimeFormat("tr-TR", { timeZone: "Europe/Istanbul", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(ms));
const kacisYok = (s) => String(s == null ? "" : s).replace(/[\r\n\u0000-\u001f]+/g, " ").slice(0, 200);

/* "iPhone · Safari" gibi kısa özet (ham User-Agent saklanmaz) */
function uaOzet(ua) {
  const u = String(ua || "");
  const sistem = /iPhone/i.test(u) ? "iPhone" : /iPad/i.test(u) ? "iPad" : /Android/i.test(u) ? "Android" : /Windows/i.test(u) ? "Windows" : /Macintosh|Mac OS/i.test(u) ? "Mac" : /Linux/i.test(u) ? "Linux" : "Bilinmeyen cihaz";
  const tarayici = /Edg\//i.test(u) ? "Edge" : /OPR\/|Opera/i.test(u) ? "Opera" : /Firefox|FxiOS/i.test(u) ? "Firefox" : /CriOS|Chrome/i.test(u) ? "Chrome" : /Safari/i.test(u) ? "Safari" : "tarayıcı";
  return sistem + " · " + tarayici;
}
const cerezAl = (req, ad) => { const m = new RegExp("(?:^|;\\s*)" + ad + "=([A-Za-z0-9_-]{16,64})").exec((req.headers && req.headers.cookie) || ""); return m && m[1]; };
const ozetle = (kullanici, cerez) => crypto.createHash("sha256").update("cihaz|" + kullanici + "|" + cerez).digest("hex").slice(0, 32);

function oku(yol, varsayilan) { try { return JSON.parse(fs.readFileSync(yol, "utf8")); } catch (e) { return varsayilan; } }
function yaz(yol, nesne) { try { fs.mkdirSync(path.dirname(yol), { recursive: true }); const g = yol + ".tmp"; fs.writeFileSync(g, JSON.stringify(nesne), { mode: 0o600 }); fs.renameSync(g, yol); } catch (e) { /* diske yazılamazsa bellekte kalır */ } }

/* seçenekler: { dir, posta, ofisEposta, yansi, hesapRolu(ad) -> "ofis"|"personel"|"musteri"|"mukellef"|null, https(req) -> bool, simdi? } */
function kur(s) {
  const DIR = s.dir, simdi = s.simdi || bugun;
  const CIHAZ_DOSYA = path.join(DIR, "cihazlar.json"), KAYIT_DOSYA = path.join(DIR, "giris-kayit.json"), SAGLIK_DOSYA = path.join(DIR, "yedek-saglik.json");
  let cihazlar = oku(CIHAZ_DOSYA, {}), kayitlar = oku(KAYIT_DOSYA, []), saglik = oku(SAGLIK_DOSYA, {});
  if (!cihazlar || typeof cihazlar !== "object" || Array.isArray(cihazlar)) cihazlar = {};
  if (!Array.isArray(kayitlar)) kayitlar = [];
  if (!saglik || typeof saglik !== "object") saglik = {};
  const basarisiz = new Map();     // kullanıcı -> { zamanlar: [], ipler: Set, ua, sonBildirim }
  const postaZamanlari = [];       // tüm e-postalar için saatlik üst sınır (hata ya da saldırı anında posta kutusunu doldurmamak için)

  const cihazlariKaydet = () => { const metin = JSON.stringify(cihazlar); yaz(CIHAZ_DOSYA, cihazlar); if (s.yansi) try { s.yansi.yaz("cihazlar.json", metin); } catch (e) { /* yansı yazamazsa yerelde kalır */ } };
  const kayitEkle = (k) => { kayitlar.unshift(Object.assign({ z: new Date(simdi()).toISOString() }, k)); if (kayitlar.length > 100) kayitlar.length = 100; yaz(KAYIT_DOSYA, kayitlar); };
  const epostaAcik = () => !!(s.ofisEposta && s.posta && s.posta.hazir());

  function bildir(konu, metin) {
    if (!epostaAcik()) return false;
    const t = simdi(); while (postaZamanlari.length && t - postaZamanlari[0] > 3600e3) postaZamanlari.shift();
    if (postaZamanlari.length >= 15) return false;
    postaZamanlari.push(t);
    try { Promise.resolve(s.posta.gonder({ gonderenAd: "Mükellef Portalı güvenlik", to: [s.ofisEposta], cc: [], konu, metin }, DIR)).catch((e) => console.log("Güvenlik e-postası gönderilemedi: " + (e && e.message))); } catch (e) { console.log("Güvenlik e-postası gönderilemedi: " + e.message); }
    return true;
  }

  /* Başarılı giriş. Dönüş: yanıta eklenecek set-cookie değerleri (yeni cihaz çerezi gerekiyorsa) */
  function girisBasarili(req, o, ip) {
    const ad = String(o.kullanici || ""), rol = o.rol, ua = req.headers && req.headers["user-agent"], ozet = uaOzet(ua), ek = [];
    const yonetici = rol === "ofis" || (rol === "personel" && o.musteri !== true); /* firma sahibi (müşteri) hesapları her gün telefondan girer: e-posta yok, yalnız kayıt */
    if (!yonetici) { kayitEkle({ tur: "giris", kullanici: ad, rol, ip, ua: ozet }); basarisiz.delete(ad); return ek; }
    let cerez = cerezAl(req, "cihaz");
    const yeniCerez = !cerez; if (yeniCerez) cerez = crypto.randomBytes(24).toString("base64url");
    const h = ozetle(ad, cerez), liste = cihazlar[ad] = cihazlar[ad] || {}, t = simdi();
    const onceki = basarisiz.get(ad), sonDeneme = onceki ? onceki.zamanlar.filter((z) => t - z < 30 * 60e3).length : 0;
    if (liste[h]) { liste[h].son = new Date(t).toISOString(); cihazlariKaydet(); kayitEkle({ tur: "giris", kullanici: ad, rol, ip, ua: ozet }); }
    else {
      const ilk = Object.keys(liste).length === 0; liste[h] = { ilk: new Date(t).toISOString(), son: new Date(t).toISOString() };
      if (Object.keys(liste).length > 30) { const eski = Object.keys(liste).sort((a, b) => String(liste[a].son).localeCompare(String(liste[b].son)))[0]; delete liste[eski]; }
      cihazlariKaydet();
      const gonderildi = bildir("Portal güvenliği: yeni cihazdan giriş (" + ad + ")",
        "Portala yeni bir cihazdan giriş yapıldı.\n\nHesap: " + ad + (rol === "personel" ? " (çalışan)" : " (ofis)") + "\nZaman: " + zamanTr(t) + "\nCihaz: " + ozet + "\nIP adresi: " + kacisYok(ip) + (ilk ? "\n\nBu hesap için kayıtlı ilk cihaz bu (bildirimler yeni açıldıysa ya da cihaz bilgisi sıfırlandıysa bu normaldir)." : "") +
        (sonDeneme ? "\n\nDİKKAT: Bu girişten önceki 30 dakikada bu hesaba " + sonDeneme + " başarısız giriş denemesi yapılmıştı." : "") +
        "\n\nBu giriş size aitse bir şey yapmanız gerekmez. Size ait değilse portalda Ayarlar bölümünden şifrenizi hemen değiştirin ve yedeğinizi kontrol edin.");
      kayitEkle({ tur: "yeni-cihaz", kullanici: ad, rol, ip, ua: ozet, eposta: gonderildi ? "gönderildi" : (epostaAcik() ? "sınır" : "e-posta kapalı") });
    }
    basarisiz.delete(ad);
    if (yeniCerez) ek.push("cihaz=" + cerez + "; HttpOnly; SameSite=Strict; Path=/; Max-Age=31536000" + (s.https && s.https(req) ? "; Secure" : ""));
    return ek;
  }

  /* Başarısız giriş: yalnız var olan hesaplar için sayılır (rastgele kullanıcı adı deneyen botlar posta üretmez) */
  function girisBasarisiz(req, ip, ad) {
    const rol = s.hesapRolu ? s.hesapRolu(ad) : null; if (!rol) return;
    const t = simdi(), b = basarisiz.get(ad) || { zamanlar: [], ipler: new Set(), sonBildirim: 0 }; basarisiz.set(ad, b);
    b.zamanlar = b.zamanlar.filter((z) => t - z < 30 * 60e3); b.zamanlar.push(t); b.ipler.add(String(ip)); if (b.ipler.size > 5) b.ipler = new Set([...b.ipler].slice(-5));
    const ozet = uaOzet(req.headers && req.headers["user-agent"]);
    kayitEkle({ tur: "basarisiz", kullanici: ad, rol, ip, ua: ozet });
    if (b.zamanlar.length >= 3 && t - b.sonBildirim > 3600e3) {
      b.sonBildirim = t;
      const g = bildir("Portal güvenliği: başarısız giriş denemeleri (" + ad + ")",
        "Bir hesaba art arda yanlış şifreyle giriş denendi.\n\nHesap: " + ad + "\nSon 30 dakikadaki deneme: " + b.zamanlar.length + "\nSon deneme: " + zamanTr(t) + "\nIP adres(ler)i: " + [...b.ipler].map(kacisYok).join(", ") + "\nCihaz: " + ozet +
        "\n\nGiriş denemeleri artan bekleme süreleriyle yavaşlatılıyor; şifre doğru tahmin edilmedikçe giriş yapılamaz. Bu denemeleri siz yapmadıysanız şifrenizi uzun ve başka yerde kullanmadığınız biriyle değiştirmeniz önerilir.");
      kayitEkle({ tur: "uyari", kullanici: ad, rol, ip, ua: ozet, eposta: g ? "gönderildi" : (epostaAcik() ? "sınır" : "e-posta kapalı"), not: b.zamanlar.length + " başarısız deneme" });
    }
  }

  const kayitListe = (n) => kayitlar.slice(0, n || 40);
  const cihazSayisi = (ad) => Object.keys(cihazlar[ad] || {}).length;

  /* ---- yedek sağlığı ---- */
  const saglikKaydet = () => yaz(SAGLIK_DOSYA, saglik);
  const ms = (iso) => { const t = Date.parse(iso || ""); return Number.isFinite(t) ? t : 0; };
  /* GitHub yansısı: son sağlam zaman (başarılı yazma ya da başarılı denetim). Hata sürerse ilk hata anından itibaren 2 günü geçince KIRMIZI */
  function yedekDegerlendir() {
    const t = simdi(), ogeler = []; let degisti = false;
    const y = s.yansi ? s.yansi.durum : null;
    if (!y) {
      ogeler.push({ seviye: "uyari", kod: "kapali", mesaj: "GitHub yedeği kapalı: verileriniz yalnız bu sunucuda duruyor; sunucu silinirse ya da diski sıfırlanırsa kaybolur." });
    } else {
      const hata = y.hata || y.kontrolHata || "", sagTz = Math.max(ms(y.sonBasari), ms(y.sonKontrol));
      if (!hata) { if (sagTz && sagTz !== ms(saglik.sonSaglam)) { saglik.sonSaglam = new Date(Math.max(sagTz, ms(saglik.sonSaglam))).toISOString(); degisti = true; } if (saglik.ilkHata) { saglik.ilkHata = null; degisti = true; } }
      else {
        if (!saglik.ilkHata) { saglik.ilkHata = new Date(t).toISOString(); degisti = true; }
        const taban = ms(saglik.sonSaglam) || ms(saglik.ilkHata), yas = t - taban, gun = Math.max(1, Math.floor(yas / 864e5));
        if (yas > IKI_GUN) ogeler.push({ seviye: "kirmizi", kod: "yansi", mesaj: "GitHub yedeği " + gun + " günden uzun süredir çalışmıyor (" + kacisYok(hata) + "). Son sağlam zaman: " + (ms(saglik.sonSaglam) ? zamanTr(ms(saglik.sonSaglam)) : "bilinmiyor") + ". Bu süredeki yeni kayıtlar GitHub'a yedeklenmedi." });
        else ogeler.push({ seviye: "uyari", kod: "yansi", mesaj: "GitHub yedeği hata veriyor (" + kacisYok(hata) + "). Düzelmezse 2 gün sonra bu uyarı kırmızıya döner." });
      }
    }
    /* elle alınan şifreli yedek (indir / e-posta): 7 günden eskiyse hatırlat */
    if (!saglik.ilkGorulme) { saglik.ilkGorulme = new Date(t).toISOString(); degisti = true; }
    const elle = ms(saglik.sonElleYedek);
    if (!elle) { if (t - ms(saglik.ilkGorulme) > 3 * 864e5) ogeler.push({ seviye: "uyari", kod: "elle", mesaj: "Henüz şifreli yedek indirmediniz. Ayarlar → Yedek bölümünden indirip harici diskinize ya da başka bir yere kopyalayın." }); }
    else if (t - elle > YEDI_GUN) ogeler.push({ seviye: "uyari", kod: "elle", mesaj: "Son şifreli yedeği " + Math.floor((t - elle) / 864e5) + " gün önce aldınız. Yenisini indirip harici diskinize kopyalamanız önerilir." });
    if (degisti) saglikKaydet();
    const seviye = ogeler.some((o) => o.seviye === "kirmizi") ? "kirmizi" : ogeler.length ? "uyari" : "iyi";
    return { seviye, ogeler, sonElleYedek: saglik.sonElleYedek || null, githubAcik: !!y };
  }
  function elleYedekYapildi() { saglik.sonElleYedek = new Date(simdi()).toISOString(); saglikKaydet(); }

  return { girisBasarili, girisBasarisiz, kayitListe, cihazSayisi, epostaAcik, yedekDegerlendir, elleYedekYapildi, _durum: () => ({ cihazlar, saglik }) };
}

module.exports = { kur, uaOzet, cerezAl };
