FROM node:22-alpine
RUN apk add --no-cache su-exec
WORKDIR /app
COPY server.js gib.js kasa.js yansi.js ivd.js ./
COPY public ./public
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENV HOST=0.0.0.0 PORT=3000 DATA_DIR=/data GUVENLI=1 TRUST_PROXY=1
VOLUME /data
EXPOSE 3000
ENTRYPOINT ["/entrypoint.sh"]
