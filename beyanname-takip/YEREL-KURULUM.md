# Yerel kurulum (Windows bilgisayarda çalıştırma)

**Neden yerel?** Luca'nın giriş sunucusu (`agiris.luca.com.tr`) Render'ın Almanya'daki sunucusundan gelen bağlantıyı kabul etmiyor
(ağ testinde zaman aşımı). Kendi bilgisayarınız Türkiye'de olduğundan Luca'ya normal girer. Şifreleriniz yalnızca bu bilgisayarda kalır.

> Bu paket Windows'ta **henüz denenmedi**; ilk çalıştırmada çıkan hatayı bana yazın, birlikte düzeltiriz.

## 1. Hazırlık (bir kez)
1. **Python 3.12 veya üstü** kurun: https://www.python.org/downloads/ → kurulumun ilk ekranında **"Add python.exe to PATH"** kutusunu işaretleyin.
   (Dijital Stajyer için zaten kurduysanız bu adımı atlayın.)
2. Bilgisayarda **Google Chrome veya Microsoft Edge** kurulu olmalı (Windows'ta Edge zaten vardır). Program onu kullanır.
3. GitHub'da **`beyanname-takip-ozel`** deposunu açın → yeşil **Code** → **Download ZIP**. İndirilen zip'i bir klasöre çıkarın,
   örneğin `C:\beyanname-takip`. (Zip'in içinde `luca-bot` klasörü de olmalı.)

## 2. Ayarlar
1. `C:\beyanname-takip\yerel` klasöründe **`ayarlar-ornek.env`** dosyasını kopyalayın, kopyanın adını **`ayarlar.env`** yapın.
2. **Not Defteri** ile açıp değerleri doldurun (aşağıda hangisi ne). Tırnak koymayın, `=` işaretinden sonra boşluk bırakmayın.

| Ad | Ne yazacaksınız |
|---|---|
| `WEB_SIFRE` | Bu bilgisayarda açılan sayfaya girmek için şifre (en az 4 karakter) |
| `WEB_GIZLI` | Klavyeye rastgele basılmış 40 karakter |
| `LUCA_OFIS_...` | Kendi mükelleflerinizin Luca hesabı: üye no, kullanıcı, parola, doğrulama anahtarı |
| `LUCA_ISLETME_...` | Çalıştığınız işletmenin Luca hesabı |
| `LUCA_GIB_GUN` | `31` (ilk kurulumda) |
| `RESEND_API_KEY`, `MAIL_ALICI` | Resend'den aldığınız anahtar; `MAIL_ALICI` Resend'e kayıt olduğunuz adres |

`ayarlar.env` **şifreleriniz içerir**: kimseyle paylaşmayın, GitHub'a yüklemeyin (zaten yüklenmeyecek şekilde ayarlı).
Parolada `&`, `%`, `!` gibi işaretler olsa da olduğu gibi yazabilirsiniz.

## 3. Başlatma (siyah pencere olmadan)
1. **Bir kez:** `yerel` klasöründeki **`Masaustune kisayol koy.vbs`** dosyasına çift tıklayın. Masaüstüne **"Beyanname Takip"** kısayolu gelir.
2. Bundan sonra **masaüstündeki "Beyanname Takip"** kısayoluna çift tıklamanız yeter. Siyah pencere açılmaz; program arka planda çalışır ve tarayıcıda
   kendiliğinden açılır. **Zaten açıksa** yalnızca tarayıcıda sayfayı açar (ikinci kopya başlatmaz).
3. **İlk seferde** Python ortamını kurar (3-5 dakika); o sırada siyah bir pencere açılır, bitene kadar kapatmayın. Python yoksa kurulum size söyler.
4. Sayfada `WEB_SIFRE` ile girin. **Sistem → Test mesajı gönder**: e-posta gelmeli. **Tanı → Tanıyı çalıştır**: Luca'ya girer.
   **Bu sırada bir Chrome/Edge penceresi açılır ve kendi kendine gezer; kapatmayın, karışmayın.**

**Hata olursa:** ayar hatası gibi sorunlarda program bir **mesaj kutusu** gösterir. Ayrıntı `yerel\program.log` dosyasındadır. Siyah pencereli eski yöntem
(`baslat.bat`) hata ayıklama için durur.

## Luca'ya hızlı giriş (kısayol)
`Masaustune kisayol koy.vbs` masaüstüne ayrıca **"Luca - Ofis"** ve **"Luca - İşletme"** kısayollarını koyar (hesaplar `ayarlar.env`'deki `LUCA_HESAPLAR`'dan okunur).
Birine çift tıklayınca Chrome/Edge açılır, giriş bilgileri ve **doğrulama kodu otomatik** yazılır ve Luca ana ekranı açık kalır; siz normal çalışmanızı yaparsınız.
Tarayıcıyı kapatınca iş biter. Doğrulama kodu reddedilirse 3 dakika boyunca elle girebilirsiniz. Ayrı bir tarayıcı profili kullanır, Beyanname Takip'in çekimini kilitlemez.
**Dikkat:** Luca aynı kullanıcıyla ikinci oturumu kabul etmeyebilir; o hesapla bir Luca çekimi sürerken hızlı giriş yapmayın. Günlük: `veri\luca-giris-<hesap>.log`.

## 4. Gündelik kullanım
* **Kapatmak için:** sayfada **Sistem → "Programı kapat"**. (Siyah pencere olmadığından kapatılacak bir şey yok; bu düğme programı tamamen durdurur.)
* Uyarılar yalnızca program **çalışırken** ve bilgisayar **uyku modunda değilken** gider. Son günlerin akşamı programın açık olduğundan emin olun
  ya da **Sistem → "Şimdi çek ve e-postayla özet gönder"** düğmesini kullanın.
* Mükellef ayarları ve gönderim kayıtları `yerel\veri` klasöründe durur. Güncelleme için yeni zip'i başka bir klasöre çıkarıp `ayarlar.env` ve `veri` klasörünü kopyalayın.
* Program yalnızca bu bilgisayardan erişilebilir (`127.0.0.1`); ağdaki başka biri açamaz.

## 5. Render'daki eski servis
Render Luca'ya giremediği için orası artık gereksiz. Bilgisayardaki programla **aynı mesajı iki kez** almamak için:
Render → servis → **Settings → Suspend Service** (ya da servisi silin). Servis ücretsiz planda kalsa bile kendi zamanlayıcısı
"VERİ ALINAMADI" e-postaları gönderebilir.
