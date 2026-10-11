# Hatırlatma sistemi kurulumu

Hatırlatmalar **gizli** bir GitHub deposunda (`hatirlatma`) durur. Bu depo herkese açık olduğu için
yalnızca sayfa ve mail programı (kod) burada, hiçbir hatırlatma verisi yok.

- Sayfa: `https://smmmyilmaz.com/hatirlatma.html` (bilgisayar ve telefondan aynı adres)
- Mail: GitHub her 10 dakikada bir gizli depoya bakar, zamanı gelen hatırlatmayı mail atar.

## 1. Gizli depoyu oluştur (bir kere)
github.com → sağ üstte **+** → **New repository**
- Repository name: `hatirlatma`
- **Private** seç
- **Add a README file** işaretle
- Create repository

## 2. GitHub anahtarı üret (bir kere)
github.com → profil resmi → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token
- Token name: `hatirlatma`
- Expiration: seçebildiğin en uzun süre (süre dolunca sayfa yeniden anahtar ister ve mail uyarısı gelir)
- Repository access: **Only select repositories** → `hatirlatma`
- Permissions → Repository permissions → **Contents: Read and write**
- Generate token → çıkan `github_pat_...` değerini kopyala (bir daha gösterilmez)

## 3. Secret'ları ekle
Bu depoda (`smmm-adem-yilmaz`): Settings → Secrets and variables → Actions → New repository secret

| Secret | Değer |
|---|---|
| `HATIRLATMA_TOKEN` | 2. adımda kopyaladığın anahtar |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | Gmail adresin |
| `SMTP_PASS` | Gmail "uygulama şifresi" (Google Hesabı → Güvenlik → 2 Adımlı Doğrulama açık → Uygulama şifreleri) |
| `MAIL_TO` | mailin geleceği adres |

## 4. Sayfayı aç
PR birleştikten sonra `https://smmmyilmaz.com/hatirlatma.html` adresini aç, 2. adımdaki anahtarı yapıştır.
Bu işlemi telefonda ve bilgisayarda ayrı ayrı bir kere yaparsın; sonra bir daha sorulmaz.
Telefonda Safari'de Paylaş → **Ana Ekrana Ekle**.

Denemek için sayfadan ileri bir tarihe, şu andan birkaç dakika sonraki saatle bir kayıt ekle.
Actions → **Hatırlatma Maili** → Run workflow ile beklemeden de çalıştırabilirsin.

## Bilmen gerekenler
- Mail, seçtiğin saatten birkaç dakika sonra gelebilir (GitHub zamanlayıcısı bazen nadiren yarım saate kadar geciktirir).
- Anahtar yalnızca o tarayıcıda saklanır. Telefonu kaybedersen GitHub'da anahtarı sil (Revoke), yenisini üret.
- Bu depoda Actions günlükleri herkese görünür. Programa hatırlatma metni ya da firma adı yazdırılmaz; yalnızca sayılar yazılır. Bunu değiştirme.
- Gizli depodaki `hatirlatmalar.json` doğrudan GitHub'dan da düzenlenebilir, ama sayfayı kullanmak daha güvenlidir.
