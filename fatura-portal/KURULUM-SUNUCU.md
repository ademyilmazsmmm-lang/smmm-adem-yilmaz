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
1. render.com'da hesap açın, **GitHub ile giriş** yapın ve depoyu (`smmm-adem-yilmaz`) Render'a bağlayın.
2. **New → Blueprint** deyip bu depoyu seçin. Depo kökündeki `render.yaml` kendiliğinden okunur; plan **Starter** ve 1 GB kalıcı disk tanımlıdır.
3. Kurulum bitince Render'ın verdiği `https://fatura-portali.onrender.com` benzeri adres açılır.
4. İsterseniz kendi alan adınızı bağlayın: Render'da servis → **Settings → Custom Domains → Add** (`fatura.smmmyilmaz.com`),
   alan adı sağlayıcınızda Render'ın gösterdiği **CNAME** kaydını ekleyin. HTTPS kendiliğinden gelir.
5. İlk açılışta uygulama şifresini (en az 12 karakter) belirleyip mükellefleri ekleyin.

## Yol C — Render ÜCRETSİZ + GitHub yansısı + cron-job.org  (0 $)
Ücretsiz Render'ın diski geçici olduğu için kayıtlar GitHub'daki **özel** bir depoda şifreli saklanır; sunucu açılırken oradan geri yükler.
1. GitHub'da **Private** bir depo açın (örn. `fatura-veri`), "Add a README" işaretli olsun.
2. GitHub → Settings → Developer settings → Fine-grained tokens → yeni anahtar: yalnız o depo, **Contents: Read and write**, süre en uzun.
3. Render → servis → Environment: `GITHUB_DEPO` = `sahip/fatura-veri`, `GITHUB_TOKEN` = anahtar (isteğe bağlı `GITHUB_DAL`, varsayılan `main`). Kaydedince servis yeniden başlar.
4. cron-job.org'da 10 dakikada bir `https://SERVIS-ADRESI/saglik` adresine GET isteği atan bir görev kurun (servis uyumaz).
5. Ayarlar → Yedek bölümünde "GitHub yedeği: açık" yazısını görün. Anahtarın süresi dolarsa yazma durur ve burada uyarı çıkar.
Sınırlar: veri GitHub'a gidene kadar ~3 sn gecikme vardır; Render servisi yeniden başlatırken (deploy) çok kısa bir pencerede son değişiklik kaybolabilir.

## Güvenlik
- Giriş denemeleri IP başına sınırlıdır (5 yanlıştan sonra bekleme artar).
- Çerez `HttpOnly`, `Secure`, `SameSite=Strict`; sayfa başlıkları sıkıdır (CSP, çerçeve yasağı).
- Veri dosyası AES-256-GCM ile şifrelidir. Düzenli olarak **Ayarlar → Şifreli yedeği indir** ile yedek alın.
- GİB tarafında oturum IP'ye bağlı değil; yine de sunucu IP'sinden ilk girişte GİB ek doğrulama isteyebilir.
  Çalışmazsa bilgisayardaki sürümü kullanmaya devam edebilirsiniz.

## E-posta ile fatura gönderimi (isteğe bağlı)
Render ücretsiz planı SMTP portlarını kapattığı için gönderim bir e-posta servisinin HTTPS API'siyle yapılır (Brevo önerilir: ücretsiz günde 300 ileti).
1. brevo.com'da hesap açın → **Senders, Domains** bölümünde gönderen adresini/alan adını doğrulayın (kendi alan adınızdan bir adres, örn. `fatura@smmmyilmaz.com`; gmail.com gibi adresler spam'e düşer).
2. **SMTP & API → API Keys** bölümünden bir anahtar oluşturun.
3. Render → servis → Environment: `MAIL_ANAHTAR` = anahtar, `MAIL_GONDEREN` = doğrulanmış adres (isteğe bağlı `MAIL_SAGLAYICI` = `brevo` ya da `resend`). Kaydedince servis yeniden başlar.
4. Yeni fatura → alıcı alanında e-posta yazılı ve "onaylanınca gönder" işaretliyse onaydan hemen sonra PDF ekli gönderilir; Geçmiş'te her faturada "E-posta" düğmesi vardır.
