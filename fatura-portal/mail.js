/* E-posta gönderimi (fatura PDF'i ekli). Render ücretsiz planı SMTP portlarını (25/465/587) kapattığı için HTTPS API'li bir servis kullanılır.
 *
 * Ortam değişkenleri:
 *   MAIL_SAGLAYICI  "gmail" (GMAIL_* tanımlıysa otomatik), "brevo" (varsayılan) ya da "resend"
 *   MAIL_GONDEREN   gönderen adres (gmail: Gmail adresinin kendisi; brevo/resend: doğrulanmış adres)
 *   Brevo/Resend için:  MAIL_ANAHTAR (API anahtarı)
 *   Gmail için:         GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN (Gmail API, yalnız "gmail.send" izni)
 * Deneme kipinde (GIB_MOCK=1) hiçbir yere gönderilmez; gönderilenler DATA_DIR/posta-kutusu.jsonl dosyasına yazılır. */
"use strict";
const fs = require("fs");
const path = require("path");

const MOCK = process.env.GIB_MOCK === "1";
const GMAIL = { id: process.env.GMAIL_CLIENT_ID || "", sir: process.env.GMAIL_CLIENT_SECRET || "", yenile: process.env.GMAIL_REFRESH_TOKEN || "" };
const SAGLAYICI = String(process.env.MAIL_SAGLAYICI || (GMAIL.yenile ? "gmail" : "brevo")).toLowerCase();
const ANAHTAR = process.env.MAIL_ANAHTAR || "";
const GONDEREN = String(process.env.MAIL_GONDEREN || "").trim();
const EPOSTA = /^[^\s@<>"]+@[^\s@<>"]+\.[^\s@<>"]+$/;

const hazir = () => MOCK || !!(EPOSTA.test(GONDEREN) && ((SAGLAYICI === "gmail" && GMAIL.id && GMAIL.sir && GMAIL.yenile) || (ANAHTAR && (SAGLAYICI === "brevo" || SAGLAYICI === "resend"))));
const durum = () => ({ hazir: hazir(), saglayici: MOCK ? "deneme" : SAGLAYICI, gonderen: MOCK ? "deneme@ornek.invalid" : GONDEREN });
const kacis = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const baslikTemiz = (s) => String(s || "").replace(/[\r\n\u0000-\u001f"<>]/g, " ").replace(/\s+/g, " ").trim().slice(0, 120);


/* RFC 2047: başlıkta Türkçe karakter */
const b64s = (b) => Buffer.from(b).toString("base64");
const baslikKodla = (t) => (/^[\x20-\x7e]*$/.test(t) ? t : "=?UTF-8?B?" + b64s(t) + "?=");
const satirla = (b64, n) => (b64.match(new RegExp(".{1," + (n || 76) + "}", "g")) || []).join("\r\n");
function mimeKur(m) {
  const sinir = "=_fatura_" + Date.now().toString(36) + Math.random().toString(36).slice(2), alt = sinir + "_alt";
  const h = ["From: " + baslikKodla(m.ad) + " <" + GONDEREN + ">", "To: " + m.to.join(", ")];
  if (m.cc.length) h.push("Cc: " + m.cc.join(", "));
  if (m.yanit && EPOSTA.test(m.yanit)) h.push("Reply-To: " + m.yanit);
  h.push("Subject: " + baslikKodla(m.konu), "MIME-Version: 1.0", "Content-Type: multipart/mixed; boundary=\"" + sinir + "\"");
  const parca = (tur, icerik) => "Content-Type: " + tur + "; charset=UTF-8\r\nContent-Transfer-Encoding: base64\r\n\r\n" + satirla(b64s(icerik));
  let g = h.join("\r\n") + "\r\n\r\n--" + sinir + "\r\nContent-Type: multipart/alternative; boundary=\"" + alt + "\"\r\n\r\n--" + alt + "\r\n" + parca("text/plain", m.metin) + "\r\n--" + alt + "\r\n" + parca("text/html", m.html) + "\r\n--" + alt + "--\r\n";
  if (m.ek) g += "--" + sinir + "\r\nContent-Type: application/pdf; name=\"" + m.ek.ad + "\"\r\nContent-Transfer-Encoding: base64\r\nContent-Disposition: attachment; filename=\"" + m.ek.ad + "\"\r\n\r\n" + satirla(m.ek.veri.toString("base64")) + "\r\n";
  return g + "--" + sinir + "--\r\n";
}
let gToken = { deger: "", bitis: 0 };
async function gmailGonder(m) {
  if (Date.now() > gToken.bitis - 60e3) {
    const r = await fetch("https://oauth2.googleapis.com/token", { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ client_id: GMAIL.id, client_secret: GMAIL.sir, refresh_token: GMAIL.yenile, grant_type: "refresh_token" }), signal: AbortSignal.timeout(20000) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.access_token) { console.log("Gmail yetkilendirme hatası: HTTP " + r.status + " " + JSON.stringify(j).slice(0, 200)); throw new Error("Gmail yetkilendirmesi reddedildi" + (j.error ? " (" + j.error + ")" : "") + (j.error === "invalid_grant" ? ": izin süresi dolmuş ya da geri alınmış; yeni yenileme anahtarı (refresh token) alın." : ".")); }
    gToken = { deger: j.access_token, bitis: Date.now() + (j.expires_in || 3600) * 1000 };
  }
  const raw = Buffer.from(mimeKur(m)).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  const r = await fetch("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", { method: "POST", headers: { authorization: "Bearer " + gToken.deger, "content-type": "application/json" }, body: JSON.stringify({ raw }), signal: AbortSignal.timeout(30000) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { if (r.status === 401) gToken = { deger: "", bitis: 0 }; const msj = (j.error && (j.error.message || j.error)) || "ayrıntı yok"; console.log("Gmail gönderim hatası: HTTP " + r.status + " " + String(msj).slice(0, 300)); throw new Error("Gmail gönderemedi (HTTP " + r.status + "): " + String(msj).slice(0, 200)); }
  return { id: j.id || "" };
}

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
  if (SAGLAYICI === "gmail") return gmailGonder({ ad, to, cc, yanit: m.yanit, konu: m.konu, metin: m.metin, html, ek: m.ek });
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

module.exports = { gonder, durum, hazir, EPOSTA, _mimeKur: mimeKur };
