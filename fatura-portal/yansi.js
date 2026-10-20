/* Verinin GitHub'daki ÖZEL bir depoya şifreli yansıması (kalıcı diski olmayan, örneğin ücretsiz Render, kurulumlar için).
 *
 * Neyi saklar: yalnızca zaten şifreli olan dosyaları (sistem.json ve m/<id>.json). Düz metin, parola ya da anahtar GitHub'a gitmez.
 * Ne zaman yazar: her dosya değişikliğinden birkaç saniye sonra (aynı dosyadaki ardışık değişiklikler birleşir).
 * Açılışta: yerelde veri yoksa GitHub'dan geri yükler. GitHub'a ulaşılamıyorsa BOŞ başlamaz: hazır olana kadar API'ye 503 döner
 * (aksi halde "ilk kurulum" yapılıp GitHub'daki gerçek veri ezilirdi).
 *
 * Ortam değişkenleri: GITHUB_DEPO ("sahip/depo"), GITHUB_TOKEN (yalnız o depoda "Contents: Read and write" izinli),
 * isteğe bağlı GITHUB_DAL (varsayılan main). GITHUB_API yalnız testlerde değiştirilir. */
"use strict";
const fs = require("fs");
const path = require("path");

const KLASOR = "veri/";
const GEC = (ms) => new Promise((r) => setTimeout(r, ms));

class Yansi {
  constructor({ depo, token, dal, dir, api, bekleme }) {
    this.repo = depo; this.token = token; this.dal = dal || "main"; this.dir = dir; this.api = (api || "https://api.github.com").replace(/\/$/, "");
    this.bekleme = bekleme == null ? 3000 : bekleme; // ardışık değişiklikleri birleştirme süresi (ms)
    this.sha = new Map();      // repo yolu -> bilinen blob sha
    this.bekleyen = new Map(); // repo yolu -> metin | null (silme)
    this.zaman = null; this.calisiyor = false; this.hazir = false; this.hata = ""; this.sonBasari = null; this.denemeler = 0;
    this.hazirSoz = new Promise((r) => { this._hazirCoz = r; });
  }
  yolRepo(rel) { return KLASOR + rel.split(path.sep).join("/"); }
  async istek(yontem, yol, govde, kabul) {
    const r = await fetch(this.api + yol, {
      method: yontem,
      headers: Object.assign({ authorization: "Bearer " + this.token, accept: kabul || "application/vnd.github+json", "x-github-api-version": "2022-11-28", "user-agent": "fatura-portali", "content-type": "application/json" }),
      body: govde ? JSON.stringify(govde) : undefined
    });
    return r;
  }
  /* yerelde veri yoksa GitHub'dan indirir. Başarısızlıkta fırlatır; çağıran yeniden dener. */
  async geriYukle() {
    const r = await this.istek("GET", `/repos/${this.repo}/git/trees/${encodeURIComponent(this.dal)}?recursive=1`);
    if (r.status === 409) return { dosya: 0 }; // boş depo (hiç commit yok)
    if (!r.ok) throw new Error("GitHub deposu okunamadı (HTTP " + r.status + (r.status === 404 ? ": depo adı, dal ya da anahtar izni yanlış olabilir" : "") + ")");
    const j = await r.json();
    if (j.truncated) throw new Error("GitHub deposu çok büyük (liste kesildi)");
    const dosyalar = (j.tree || []).filter((x) => x.type === "blob" && x.path.startsWith(KLASOR) && /\.json$/.test(x.path));
    for (const d of dosyalar) {
      const c = await this.istek("GET", `/repos/${this.repo}/contents/${d.path.split("/").map(encodeURIComponent).join("/")}?ref=${encodeURIComponent(this.dal)}`, null, "application/vnd.github.raw+json");
      if (!c.ok) throw new Error("GitHub dosyası okunamadı: " + d.path + " (HTTP " + c.status + ")");
      const metin = await c.text();
      JSON.parse(metin); // bozuk dosyayı yerele yazma
      const hedef = path.join(this.dir, d.path.slice(KLASOR.length));
      fs.mkdirSync(path.dirname(hedef), { recursive: true });
      const g = hedef + ".tmp"; fs.writeFileSync(g, metin); fs.renameSync(g, hedef);
      this.sha.set(d.path, d.sha);
    }
    return { dosya: dosyalar.length };
  }
  /* açılış: yerelde sistem.json yoksa geri yükle; hata olursa hazır olana dek yeniden dene */
  async baslat(yerelVarMi, yuklendi) {
    for (let n = 0; ; n++) {
      try {
        if (!yerelVarMi()) { const s = await this.geriYukle(); console.log("GitHub yansısı: " + s.dosya + " dosya geri yüklendi."); }
        this.hata = ""; if (yuklendi) yuklendi(); this.hazir = true; this._hazirCoz(); return;
      } catch (e) {
        this.hata = e.message; console.error("GitHub yansısı açılamadı: " + e.message);
        await GEC(Math.min(60000, 3000 * (n + 1)));
      }
    }
  }
  yaz(rel, metin) { this.bekleyen.set(this.yolRepo(rel), metin); this.planla(); }
  sil(rel) { this.bekleyen.set(this.yolRepo(rel), null); this.planla(); }
  planla(ms) {
    if (this.zaman) clearTimeout(this.zaman);
    this.zaman = setTimeout(() => { this.zaman = null; this.bosalt().catch(() => {}); }, ms == null ? this.bekleme : ms);
    if (this.zaman.unref) this.zaman.unref();
  }
  async shaBul(yol) {
    const r = await this.istek("GET", `/repos/${this.repo}/contents/${yol.split("/").map(encodeURIComponent).join("/")}?ref=${encodeURIComponent(this.dal)}`);
    if (r.status === 404) return null;
    if (!r.ok) throw new Error("GitHub sha okunamadı (HTTP " + r.status + ")");
    return (await r.json()).sha || null;
  }
  async tekYaz(yol, metin) {
    for (let n = 0; n < 3; n++) {
      if (!this.sha.has(yol)) this.sha.set(yol, await this.shaBul(yol)); // bilinmiyorsa (ya da çakışmadan sonra) güncel sha'ya bak
      const sha = this.sha.get(yol);
      if (metin === null) {
        if (!sha) return;
        const r = await this.istek("DELETE", `/repos/${this.repo}/contents/${yol.split("/").map(encodeURIComponent).join("/")}`, { message: "veri güncellemesi", sha, branch: this.dal });
        if (r.ok || r.status === 404) { this.sha.delete(yol); return; }
        if (r.status === 409 || r.status === 422) { this.sha.delete(yol); continue; }
        throw new Error("GitHub silme hatası (HTTP " + r.status + ")");
      }
      const govde = { message: "veri güncellemesi", content: Buffer.from(metin, "utf8").toString("base64"), branch: this.dal };
      if (sha) govde.sha = sha;
      const r = await this.istek("PUT", `/repos/${this.repo}/contents/${yol.split("/").map(encodeURIComponent).join("/")}`, govde);
      if (r.ok) { this.sha.set(yol, (await r.json()).content.sha); return; }
      if (r.status === 409 || r.status === 422) { this.sha.delete(yol); continue; } // başka biri değiştirdi: güncel sha ile yeniden dene
      throw new Error("GitHub yazma hatası (HTTP " + r.status + ")");
    }
    throw new Error("GitHub yazma çakışması sürdü");
  }
  /* bekleyen tüm değişiklikleri sırayla gönderir; hata olursa bekleyenler korunur ve geri çekilmeyle yeniden denenir */
  async bosalt() {
    if (this.calisiyor) return; this.calisiyor = true;
    try {
      while (this.bekleyen.size) {
        const [yol, metin] = this.bekleyen.entries().next().value;
        this.bekleyen.delete(yol);
        try { await this.tekYaz(yol, metin); this.denemeler = 0; this.sonBasari = new Date().toISOString(); this.hata = ""; }
        catch (e) {
          if (!this.bekleyen.has(yol)) this.bekleyen.set(yol, metin); // daha yeni sürüm gelmediyse yeniden sıraya
          this.hata = e.message; this.denemeler++;
          console.error("GitHub yansısı yazılamadı: " + e.message);
          this.planla(Math.min(300000, 5000 * Math.pow(2, Math.min(this.denemeler, 6))));
          return;
        }
      }
    } finally { this.calisiyor = false; }
  }
  /* kapanışta bekleyenleri göndermeyi dener (en çok sure ms) */
  async kapat(sure) {
    if (this.zaman) { clearTimeout(this.zaman); this.zaman = null; }
    const bitis = Date.now() + (sure || 20000);
    while ((this.bekleyen.size || this.calisiyor) && Date.now() < bitis) { if (!this.calisiyor) await this.bosalt(); else await GEC(100); if (this.hata && this.bekleyen.size && !this.calisiyor) break; }
  }
  get durum() { return { acik: true, hazir: this.hazir, bekleyen: this.bekleyen.size, hata: this.hata, sonBasari: this.sonBasari }; }
}

module.exports = { Yansi };
