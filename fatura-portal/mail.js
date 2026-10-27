/* E-posta gönderimi (fatura PDF'i ekli). Render ücretsiz planı SMTP portlarını (25/465/587) kapattığı için HTTPS API'li bir servis kullanılır.
 *
 * Ortam değişkenleri:
 *   MAIL_SAGLAYICI  "brevo" (varsayılan) ya da "resend"
 *   MAIL_ANAHTAR    servisin API anahtarı
 *   MAIL_GONDEREN   doğrulanmış gönderen adresi (örn. fatura@smmmyilmaz.com)
 * Deneme kipinde (GIB_MOCK=1) hiçbir yere gönderilmez; gönderilenler DATA_DIR/posta-kutusu.jsonl dosyasına yazılır. */
"use strict";
const fs = require("fs");
const path = require("path");

const MOCK = process.env.GIB_MOCK === "1";
const SAGLAYICI = String(process.env.MAIL_SAGLAYICI || "brevo").toLowerCase();
const ANAHTAR = process.env.MAIL_ANAHTAR || "";
const GONDEREN = String(process.env.MAIL_GONDEREN || "").trim();
const EPOSTA = /^[^\s@<>"]+@[^\s@<>"]+\.[^\s@<>"]+$/;

const hazir = () => MOCK || !!(ANAHTAR && EPOSTA.test(GONDEREN) && (SAGLAYICI === "brevo" || SAGLAYICI === "resend"));
const durum = () => ({ hazir: hazir(), saglayici: MOCK ? "deneme" : SAGLAYICI, gonderen: MOCK ? "deneme@ornek.invalid" : GONDEREN });
const kacis = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const baslikTemiz = (s) => String(s || "").replace(/[\r\n\u0000-\u001f"<>]/g, " ").replace(/\s+/g, " ").trim().slice(0, 120);

/* { gonderenAd, to:[e-posta], cc:[e-posta], yanit, konu, metin, ek:{ ad, veri:Buffer } } */
async function gonder(m, dataDir) {
  const to = (m.to || []).filter((x) => EPOSTA.test(x)), cc = (m.cc || []).filter((x) => EPOSTA.test(x) && !to.includes(x));
  if (!to.length) throw new Error("Geçerli bir alıcı e-posta adresi yok.");
  const ad = baslikTemiz(m.gonderenAd) || "Fatura";
  const html = '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#222">' + kacis(m.metin).replace(/\n/g, "<br>") + "</div>";
  if (MOCK) {
    if (dataDir) fs.appendFileSync(path.join(dataDir, "posta-kutusu.jsonl"), JSON.stringify({ zaman: new Date().toISOString(), gonderenAd: ad, to, cc, yanit: m.yanit || "", konu: m.konu, metin: m.metin, ek: m.ek ? { ad: m.ek.ad, boyut: m.ek.veri.length } : null }) + "\n");
    return { id: "deneme" };
  }
  if (!hazir()) throw new Error("E-posta gönderimi bu sunucuda kurulu değil.");
  const b64 = m.ek ? m.ek.veri.toString("base64") : null;
  let url, baslik, govde;
  if (SAGLAYICI === "resend") {
    url = "https://api.resend.com/emails"; baslik = { authorization: "Bearer " + ANAHTAR };
    govde = { from: ad + " <" + GONDEREN + ">", to, cc: cc.length ? cc : undefined, reply_to: m.yanit && EPOSTA.test(m.yanit) ? m.yanit : undefined, subject: m.konu, text: m.metin, html, attachments: b64 ? [{ filename: m.ek.ad, content: b64 }] : undefined };
  } else {
    url = "https://api.brevo.com/v3/smtp/email"; baslik = { "api-key": ANAHTAR, accept: "application/json" };
    govde = { sender: { name: ad, email: GONDEREN }, to: to.map((email) => ({ email })), cc: cc.length ? cc.map((email) => ({ email })) : undefined, replyTo: m.yanit && EPOSTA.test(m.yanit) ? { email: m.yanit } : undefined, subject: m.konu, textContent: m.metin, htmlContent: html, attachment: b64 ? [{ name: m.ek.ad, content: b64 }] : undefined };
  }
  let r;
  try { r = await fetch(url, { method: "POST", headers: Object.assign({ "content-type": "application/json" }, baslik), body: JSON.stringify(govde), signal: AbortSignal.timeout(30000) }); }
  catch (e) { throw new Error(e && (e.name === "TimeoutError" || e.name === "AbortError") ? "E-posta servisi 30 saniyede yanıt vermedi." : "E-posta servisine ulaşılamadı: " + e.message); }
  const t = await r.text(); let j = null; try { j = JSON.parse(t); } catch (e) { /* JSON değil */ }
  if (!r.ok) {
    const msj = (j && (j.message || j.error || (j.errors && JSON.stringify(j.errors)))) || t.slice(0, 160);
    console.log("E-posta hatası (" + SAGLAYICI + " HTTP " + r.status + "): " + String(msj).slice(0, 300));
    throw new Error("E-posta gönderilemedi (" + SAGLAYICI + ", HTTP " + r.status + "): " + String(msj).slice(0, 200));
  }
  return { id: (j && (j.messageId || j.id)) || "" };
}

module.exports = { gonder, durum, hazir, EPOSTA };
