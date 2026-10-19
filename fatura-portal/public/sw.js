/* Yalnızca yüklenebilirlik ve çevrimdışı uyarısı için. Fatura/veri hiçbir zaman önbelleğe alınmaz. */
var SAYFA = "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>e-Arşiv Fatura</title><body style='font:16px system-ui;display:grid;place-items:center;min-height:100vh;margin:0;background:#f2f4f3;color:#0f1d19;text-align:center;padding:24px'><div><h2>Bağlantı yok</h2><p>e-Arşiv Fatura internet bağlantısı gerektirir. Bağlandığınızda sayfayı yenileyin.</p><button onclick=location.reload() style='font:inherit;padding:12px 20px;border:0;border-radius:10px;background:#0d6b55;color:#fff'>Yenile</button></div>";
self.addEventListener("install", function(){ self.skipWaiting(); });
self.addEventListener("activate", function(e){ e.waitUntil(self.clients.claim()); });
self.addEventListener("fetch", function(e){
  if (e.request.mode !== "navigate") return;
  e.respondWith(fetch(e.request).catch(function(){ return new Response(SAYFA, { headers: { "content-type": "text/html; charset=utf-8" } }); }));
});
