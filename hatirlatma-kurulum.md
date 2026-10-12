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

## 4. Sayfayı aç ve giriş şifresini belirle (bir kere)
`https://smmmyilmaz.com/hatirlatma.html` adresini bilgisayarda aç. İlk açılışta sayfa GitHub anahtarını (2. adımdaki) ve
belirleyeceğin bir **giriş şifresini** (en az 12 karakter) sorar. Sayfa anahtarı şifreyle şifreler ve ekranda
**şifreli bir metin** gösterir. Bu metni `hatirlatma-kasa.json` adıyla siteye ekleyince (Claude'a yapıştırarak ya da GitHub'da
yeni dosya olarak) kurulum biter.

Bundan sonra **her cihazda (telefon, bilgisayar) yalnızca giriş şifresi** sorulur; anahtar bir daha istenmez.
Sekme açık kaldıkça tekrar sormaz, sayfadaki "Kilitle" ile elle kilitlenir.
Telefonda Safari'de Paylaş → **Ana Ekrana Ekle**.

Denemek için sayfadan ileri bir tarihe, şu andan birkaç dakika sonraki saatle bir kayıt ekle.
Actions → **Hatırlatma Maili** → Run workflow ile beklemeden de çalıştırabilirsin.

## Bilmen gerekenler
- Mail, seçtiğin saatten birkaç dakika sonra gelebilir (GitHub zamanlayıcısı bazen nadiren yarım saate kadar geciktirir).
- Şifreli anahtar metni (`hatirlatma-kasa.json`) herkese açık sitede durur; şifreyi bilmeyen okuyamaz, ama çevrimdışı şifre
  tahmini mümkündür. Bu yüzden şifre **en az 12 karakter ve tahmin edilmesi zor** olmalı (dört beş kelimelik bir cümle iyi olur).
  Anahtar (PBKDF2, 1.000.000 tur + AES-GCM) yalnızca gizli `hatirlatma` deposuna yazabilir; site deposuna dokunamaz.
  Şifren sızdığından şüphelenirsen GitHub'da anahtarı sil (Revoke), yeni anahtar ve şifreyle kurulumu tekrarla.
- Mailin gideceği adres `MAIL_TO` secret'ında durur (koda yazılmaz). Değiştirmek için Settings → Secrets → Actions → `MAIL_TO` → düzenle.
- Bu depoda Actions günlükleri herkese görünür. Programa hatırlatma metni ya da firma adı yazdırılmaz; yalnızca sayılar yazılır. Bunu değiştirme.
- Gizli depodaki `hatirlatmalar.json` doğrudan GitHub'dan da düzenlenebilir, ama sayfayı kullanmak daha güvenlidir.

## Süreç şablonları (Yapılacaklar sekmesi)

Kuruluş, nevi değişikliği, tasfiye gibi tekrar eden işlemleri şablon olarak tutabilirsin.
- **Yeni süreç başlat:** şablonu, firma adını ve başlangıç tarihini seç. Şablondaki bütün maddeler o firma için Yapılacaklar'a eklenir.
- **Süreler:** Şablon satırının sonuna `(15 gün)` ya da `(1 ay)` yazarsan, o madde için son tarih = başlangıç + süre olur.
  Son tarihi olan ve tamamlanmamış maddeler, son günden 3 gün önce ve son gün (seçtiğin gün ve saatlerde) mail atar.
  Maddeyi işaretlersen mail gelmez. Mailin konusu "Firma: madde" biçimindedir.
- **Şablonları düzenle:** notlarını olduğu gibi yapıştırabilirsin ("- [ ]" ve "•" işaretleri temizlenir, "15gun" gibi yazımlar da anlaşılır).
  Şablonlar gizli depoda `sablonlar.json` dosyasında durur ve yedek mailine girer.
- Tekil bir işe de son tarih verebilirsin: Yapılacaklar kutusunun altındaki "Son tarih" alanı.

## Tasfiye süreci (Yapılacaklar sekmesi → "Tasfiye süreci başlat")

Sayfa tasfiye için şu tarihleri sorar; ilk tarih zorunludur, diğer ikisi sonradan da girilebilir. Süreler şu kurallara göre hesaplanır:

| Madde | Son tarih | Hangi tarihten | Dayanak |
|---|---|---|---|
| Normal dönem kurumlar vergisi beyannamesi (tasfiye öncesi) | Tasfiye başlangıç ayını izleyen 4. ayın 25'i; kapanış girildiyse ve tasfiye sonu beyannamesinden önce doluyorsa o tarih | Tasfiyeye giriş (+ kapanış) | KVK md. 14 |
| Tasfiye dönemi kurumlar vergisi beyannamesi (başlangıç → yıl sonu) | Dönemin kapandığı yılı izleyen yılın 25 Nisan'ı; kapanış aynı yıldaysa "gerekmez" (tek dönem) | Tasfiyeye giriş (+ kapanış) | KVK md. 14 |
| Kapanış verilebilir | 3. ilan + 3 ay | 3. ilan | TTK md. 541, 543 |
| Tasfiye sonu beyannamesi | Kapanış + 30 gün | Kapanış | KVK md. 17 |

Tarihi girilmemiş maddeler "Tarih bekleniyor" olarak durur. Süreç kartındaki **Tarihler** bölümünden sonradan girilir ya da düzeltilir; bağlı maddelerin tarihleri yeniden hesaplanır.
Her maddenin altında hesabın nasıl yapıldığı yazar. Tarihli maddeler son günden 3 gün önce ve son gün mail atar.
Kurallar kodda `TASFIYE_MADDELER` ve `tasfiyeSon` bölümündedir. Süreler ikincil kaynaklardan doğrulandı; kesin tarihler için güncel mevzuat ve vergi dairesi görüşü esas alınmalıdır.
Birden fazla takvim yılına yayılan tasfiyelerde sonraki yılların tasfiye dönemi beyannameleri otomatik eklenmez.
