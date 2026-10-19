#!/bin/sh
# Kalıcı disk (Render, Docker volume) kök sahipli bağlanabilir; veri klasörünü "node" kullanıcısına verip yetkisiz kullanıcıyla başlat.
mkdir -p "$DATA_DIR"
chown -R node:node "$DATA_DIR" 2>/dev/null || true
exec su-exec node:node node server.js
