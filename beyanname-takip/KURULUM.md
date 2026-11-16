# Kurulum (Render + Luca + e-posta)

> **Önemli:** Luca'nın giriş sunucusu (`agiris.luca.com.tr`) Render'ın (Almanya) sunucusundan gelen bağlantıyı kabul etmedi (ağ testinde
> zaman aşımı). **Render'da Luca'ya girilemiyor.** Güncel yol: bilgisayarda çalıştırma, bkz. **[YEREL-KURULUM.md](YEREL-KURULUM.md)**.
> Aşağıdaki Render adımları yalnızca Luca'ya Türkiye dışından erişimin açılması hâlinde geçerlidir.

Bu dosya kurulum adımlarını sırayla verir. Çalışma mantığı ve ayrıntılar için `README.md`'ye bakın.

> **Şifreleri sohbete, depoya ya da koda yazmayın.** Aşağıdaki bütün şifre/anahtar değerleri yalnızca Render'daki
> *Environment* ekranına girilir.

## 1. Özel (private) depo

Bu klasör (`beyanname-takip/`) web sitenizin deposunun içinde duruyor. Site deposu herkese açık olabilir, Dijital
Stajyer'in `luca-bot/` klasörü ise lisanslıdır. Bu yüzden `luca-bot/`'u **bu depoya koymayın.**

1. GitHub'da yeni bir **Private** depo açın (örn. `beyanname-takip-ozel`).
2. Şu yerleşimle içine koyun (depo kökü = bu klasörün içeriği):

   ```
   Dockerfile.luca
   requirements.txt
   app/...
   luca-bot/lucabot/...        <- Dijital Stajyer kurulumundaki luca-bot klasörü (içinde lucabot/ paketi)
   ```
3. `veri/`, `.env` ya da herhangi bir şifre/anahtar dosyasını depoya eklemeyin.

## 2. E-posta bildirimi (Resend, en kolayı)

**Render'ın ücretsiz planı giden SMTP portlarını (25/465/587) kapatır;** Gmail SMTP çalışmaz (`OSError`). HTTPS ile çalışan
bir e-posta servisi kullanılır. En az kurulum isteyeni **Resend**'dir:

1. https://resend.com adresinde, uyarıların gelmesini istediğiniz e-posta adresiyle hesap açın.
2. **API Keys → Create API Key** (yetki: *Sending access*). Çıkan `re_…` ile başlayan anahtarı **bir kez** gösterir; kopyalayın.
3. Render → bu servisin **Environment** sayfası → şunları ekleyin:
   `RESEND_API_KEY` = o anahtar, `MAIL_ALICI` = **hesabı açtığınız aynı e-posta adresi**.
   (Alan adı doğrulamadan Resend yalnızca hesap sahibinin kendi adresine gönderir; gönderen `onboarding@resend.dev` olur,
   `MAIL_GONDEREN` girmeyin.) Güncel ücretsiz sınırlarını Resend'in fiyat sayfasından kontrol edin.
4. `SMTP_*` ve `GMAIL_*` değişkenleri varsa **silin**.

Alternatif: Gmail API (`GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `MAIL_GONDEREN`) de desteklenir; ancak Google'da
OAuth istemcisi kurmak gerekir. Telegram sonra eklenecek: `TELEGRAM_TOKEN` ve `TELEGRAM_CHAT_ID` verilince otomatik devreye girer.

## 3. Render

1. Render → **New → Web Service** → özel depoyu bağlayın.
2. Runtime **Docker**; *Dockerfile Path*: `Dockerfile.luca`; Root Directory boş (depo kökü).
3. Plan **Starter** (zamanlayıcının kesintisiz çalışması ve kalıcı disk için).
4. **Disk** ekleyin: Mount path `/data`, 1 GB.
5. *Health Check Path*: `/saglik`. **Instance sayısı 1** olmalı.
6. Ortam değişkenleri (aşağıdaki tablo).

### Ortam değişkenleri

| Ad | Değer |
|---|---|
| `TOPLAYICI` | `luca` |
| `DATA_DIR` | `/data` |
| `TZ` | `Europe/Istanbul` |
| `WEB_SIFRE` | Web sayfası şifresi (en az 4 karakter) |
| `WEB_GIZLI` | Rastgele uzun bir metin (oturum imzası) |
| `LUCA_HESAPLAR` | `ofis,isletme` |
| `LUCA_OFIS_UYE_NO`, `LUCA_OFIS_KULLANICI`, `LUCA_OFIS_PAROLA`, `LUCA_OFIS_DOGRULAMA_ANAHTARI` | Ofis Luca hesabı (anahtar = kimlik doğrulayıcı TOTP gizli anahtarı) |
| `LUCA_ISLETME_UYE_NO`, `LUCA_ISLETME_KULLANICI`, `LUCA_ISLETME_PAROLA`, `LUCA_ISLETME_DOGRULAMA_ANAHTARI` | İşletme Luca hesabı |
| `LUCA_GIB_GUN` | `31` (yalnızca ilk kurulumda; sonra boş bırakılır, varsayılan 15) |
| `RESEND_API_KEY`, `MAIL_ALICI` | Bölüm 2 |

Luca'nın GİB kullanıcı kodu/şifresi Luca içinde kayıtlıdır (*Yönetici > SM/SMM Bilgileri > Kurum Şifre Bilgileri*);
bunları ayrıca girmeniz gerekmez.

## 4. İlk çalıştırma (sırayla)

1. Sayfayı açın, `WEB_SIFRE` ile girin.
2. **Sistem → Test mesajı gönder.** E-posta geldi mi? Gelmediyse aşağıdaki "Olası sorunlar"a bakın.
3. **Tanı → Tanıyı çalıştır** (1-3 dk). Her iki hesap için ekran görüntüleri ve `beyan_listele.json` görünür.
   Takılan bir adım olursa görüntüleri (mükellef adlarını karalayarak) bana gönderin.
4. Tanı düzgünse **Şimdi Luca'dan çek.** Uyarı çıkarsa (örn. "hiçbir mükellefle eşleşmedi") bana iletin.
5. **Mükellefler** sekmesinde her firmanın beyanname türü/periyodunu ve SGK ayarını kontrol edip onaylayın.
   Onaylanmayan firma uyarıda "ayar onaysız" etiketiyle görünür.

## Olası sorunlar

* **E-posta gitmiyor:** Sistem → Test mesajı gönder sonucunda hata türü yazar. `OSError` = SMTP portu kapalı (Resend'e geçin). Resend `HTTP 403 validation_error` = `MAIL_ALICI` hesabı açtığınız adres değil.
  `HTTP 400 invalid_grant` = Gmail izni süresi dolmuş/geri alınmış, yeni refresh token gerekir. `HTTP 403` = Gmail API'de `gmail.send` izni yok.
* **Luca girişi:** Render sunucusu yurt dışında olabilir; Luca yabancı IP'den girişi reddederse sunucunun Türkiye'de olması
  gerekir. Bu henüz denenmedi.
* **`Dockerfile.luca` hiç derlenmedi;** ilk derlemede sürüm/paket hatası çıkabilir. Derleme günlüğünü bana gönderin.
* **Güvenlik:** TOTP anahtarını sunucuya koymak ikinci doğrulamayı fiilen sunucuya emanet eder. Luca'da yalnızca okuma
  yetkili ayrı bir robot kullanıcı açıp onu kullanmanız önerilir.
