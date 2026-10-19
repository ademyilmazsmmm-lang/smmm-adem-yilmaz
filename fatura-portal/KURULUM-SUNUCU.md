# Fatura Portalı — sunucuya kurulum (telefondan kullanmak için)

Program internete açılacağı için GİB şifreleriniz yalnızca **şifreli** dosyada durur ve her oturumda
uygulama şifrenizle açılır. Sunucu yeniden başlarsa yeniden giriş yapmanız gerekir (bu bilerek böyledir).
Uygulama şifresi sunucu kipinde **en az 12 karakter** olmalıdır; 4–5 kelimelik bir cümle iyi olur.

İki yol var. İkisinde de adres `https://fatura.smmmyilmaz.com` gibi bir alt alan adı olur.

## Yol A — VPS (Hetzner / DigitalOcean vb.) + Docker  (aylık ~4–6 €)
1. Ubuntu 22.04/24.04 bir sunucu açın (en küçük boyut yeter). IP adresini not edin.
2. Alan adınızın DNS ayarlarında `fatura` için bir **A kaydı** açın, değeri sunucunun IP'si olsun.
3. Sunucuya bağlanın (`ssh root@IP`) ve şunları yapıştırın:
   ```
   curl -fsSL https://get.docker.com | sh
   git clone <depo-adresi> site && cd site/fatura-portal
   cp .env.ornek .env && nano .env      # DOMAIN=fatura.smmmyilmaz.com yazın
   docker compose up -d --build
   ```
4. Birkaç dakika sonra `https://fatura.smmmyilmaz.com` açılır (HTTPS sertifikası kendiliğinden alınır).
5. İlk açılışta uygulama şifresini belirleyin, mükellefleri yeniden ekleyin ya da eski bilgisayardaki
   "Şifreli yedeği indir" dosyasını sunucudaki `/var/lib/docker/volumes/..._veri/_data/kasa.json` yerine koyun.
6. Güncelleme: `git pull && docker compose up -d --build`.

## Yol B — Render.com  (aylık ~7 $, sunucu bilgisi gerekmez)
1. Depoyu GitHub'da `main` dalında tutun (bu klasör birleştirilmiş olmalı).
2. render.com'da **New → Blueprint** ile depoyu seçin; `render.yaml` kendiliğinden okunur.
3. Kurulum bitince Render'ın verdiği adres (ya da kendi alan adınız) HTTPS ile açılır.

## Güvenlik
- Giriş denemeleri IP başına sınırlıdır (5 yanlıştan sonra bekleme artar).
- Çerez `HttpOnly`, `Secure`, `SameSite=Strict`; sayfa başlıkları sıkıdır (CSP, çerçeve yasağı).
- Veri dosyası AES-256-GCM ile şifrelidir. Düzenli olarak **Ayarlar → Şifreli yedeği indir** ile yedek alın.
- GİB tarafında oturum IP'ye bağlı değil; yine de sunucu IP'sinden ilk girişte GİB ek doğrulama isteyebilir.
  Çalışmazsa bilgisayardaki sürümü kullanmaya devam edebilirsiniz.
