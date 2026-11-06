# Beyanname Takip

Luca'daki mükellef listesini ve verilmiş beyannameleri karşılaştırır; son güne yaklaşırken ve son gün
akşamı **verilmemiş** beyannameleri Telegram'dan bildirir. Web sayfasından durum görülür.

> **Durum:** Uyarı mantığı, web sayfası, Telegram, captcha köprüsü ve Luca toplayıcı yazıldı; 60 otomatik test geçiyor.
> **Luca toplayıcının tarayıcıyı süren kısmı gerçek Luca'da HİÇ ÇALIŞTIRILMADI.** Ekran okuma ayrıntıları
> (3 aylık dönemin filtredeki karşılığı, tablo yapısı, sayfalama, tür adları) ilk gerçek çalıştırmada
> `LUCA_TANI=1` ile doğrulanmalıdır (aşağıda "Luca modu").

## Ne kontrol eder

| Beyanname | Son gün | Not |
|---|---|---|
| KDV (KDV1) | Ertesi ayın 28'i | Aylık ya da 3 aylık |
| MUHSGK (Muhtasar + Prim Hizmet) | Ertesi ayın 26'sı | Aylık ya da 3 aylık (Ocak/Nisan/Temmuz/Ekim) |
| Geçici vergi | Dönemi izleyen 2. ayın 17'si | Şubat/Mayıs/Ağustos/Kasım (depodaki vergi takvimiyle aynı) |

Son gün hafta sonu ya da resmî tatile denk gelirse ilk iş gününe kayar (`app/tatiller.json`).
**Her yıl yeni yılın bayram tarihlerini `tatiller.json`'a ekleyin;** yoksa program her sabah uyarır.
Tablo `app/kurallar.py` içindeki `BEYANNAMELER`'dedir; yayına almadan önce güncel mevzuatla karşılaştırın.
Yıllık beyannameler (GV, KV), Ba/Bs, KDV2 vb. bu sürümde yok.

Mükellefin açılış/kapanış tarihi dikkate alınır: açılıştan önce biten dönemler beklenmez, kapanıştan
sonra başlayan dönemler beklenmez, kapanış dönemi "süre farklı olabilir" notuyla uyarılır.

## Uyarı takvimi

| Kalan gün | Saatler |
|---|---|
| 7, 3, 2 | 09:00 |
| 1 | 09:00, 17:00 |
| **0 (son gün)** | 09:00, 13:00, 17:00, **20:30, 21:00, 22:30** |
| Süre geçti (5 güne kadar) | Her sabah 09:00 |

(`app/kontrol.py` içindeki `SLOTLAR` ve `KURAL`.) Her uyarıdan önce Luca'dan veri yeniden alınır; mesajın
altında "Luca verisi: … itibarıyla" yazar. Ayrıca:

* Her sabah 09:00'da "sistem çalışıyor, en yakın son gün …" özeti gelir. **Özet gelmezse sistem durmuş demektir.**
* Luca'dan veri alınamazsa "LUCA'DAN VERİ ALINAMADI" uyarısı gider; eski veriyle de uyarı sürer.
* Uygulama geç açılırsa kaçan slotlardan yalnızca sonuncusu (en fazla 90 dk geç) "gecikmeli" diye çalışır.
* Telegram'a gönderilemeyen mesaj 5 dakikada bir tekrar denenir (en fazla 90 dk).

## Yanlış alarmı azaltmak

Her mükellef için ilk kurulumda **Mükellefler** sekmesinden hangi beyannameleri vereceği ayarlanır
(ör. çalışanı olmayanda MUHSGK "yok"). Onaylanmamış mükelleflerde varsayılan olarak üçü de beklenir ve
uyarıda "ayar onaysız" yazar (uyarı kaçmasın diye). Bir dönem için beyanname verilmeyecekse
(işlem yok vb.) **Durum** sekmesinde "Verilmeyecek" deyin; not kaydedilir.

## Çalıştırma (bilgisayarda deneme)

```bash
pip install -r requirements.txt pytest httpx
python -m pytest                                   # testler
WEB_SIFRE=en-az-10-karakter TOPLAYICI=ornek python -m uvicorn app.web:app_fabrikasi --factory --port 8000
```
`TOPLAYICI=ornek` uydurma 6 firma gösterir. Gerçek veri için aşağıdaki "dosya" modunu kullanın.

## Ortam değişkenleri

| Ad | Anlamı |
|---|---|
| `WEB_SIFRE` | **Zorunlu**, en az 10 karakter. Şifresiz açılmaz. 5 yanlış denemeden sonra bekletir. |
| `WEB_GIZLI` | Oturum imzası için rastgele metin (yoksa her açılışta yeni üretilir, oturumlar düşer) |
| `DATA_DIR` | Veri klasörü. Render'da kalıcı disk (`/data`) |
| `TOPLAYICI` | `ornek`, `dosya` ya da `luca` |
| `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` | Telegram botu (aşağıda) |
| `ZAMANLAYICI` | `0` ise zamanlayıcı kapanır (yalnızca test için) |
| `TZ` | `Europe/Istanbul` |

Şifreler ve token'lar **yalnızca Render'ın gizli ortam değişkenlerine** girilir; koda, depoya ya da sohbete yazılmaz.

## Telegram botu

1. Telegram'da `@BotFather` → `/newbot` → verdiği **token**'ı not edin.
2. Yeni botunuza bir mesaj yazın, sonra tarayıcıda `https://api.telegram.org/bot<TOKEN>/getUpdates` açın;
   `"chat":{"id":…}` değeri **sohbet no**'dur.
3. İkisini `TELEGRAM_TOKEN` ve `TELEGRAM_CHAT_ID` olarak girin. Web sayfası → Sistem → "Test mesajı gönder".

Program yalnızca bu sohbetten gelen mesajları (captcha cevabı) dikkate alır.

## Veri: `TOPLAYICI=dosya`

`DATA_DIR/girdi/<hesap>/` klasörüne (her Luca hesabı için bir klasör: örn. `ofis`, `isletme`) şu dosyalar konur:

* `luca-musteri-listesi.json` — Dijital Stajyer'in "Luca'dan firma listesini çek" çıktısı (`{"firmalar":[…]}`).
* `luca-beyannameler.json` (`{"beyannameler":[{"vkn","firma","tur","donem","durum"}]}`) **ya da**
  `luca-beyannameler.csv` (başlıklar: `Vergi No; Unvan; Beyanname Türü; Dönem; Durum`, `;` veya `,` ayraçlı).
  `tur`: KDV1, MUHSGK/Muhtasar, GGECICI/KGECICI gibi adlar tanınır, KDV2 vb. yok sayılır.
  `durum`: "Onaylanmış" verildi sayılır; "Hatalı/Onay bekliyor" ayrı ("ONAYSIZ") uyarılır.

Dosyalar güncellenince her uyarı slotunda yeniden okunur. Web sayfasındaki "Şimdi Luca'dan çek" de dosyaları yeniden okur.

## Luca modu (`TOPLAYICI=luca`)

Her şey Luca'nın içinde yapılır, GİB/e-Beyanname'ye bağlanılmaz:

1. Luca girişi (üye no, kullanıcı, parola; **doğrulama anahtarı varsa kod otomatik üretilir**).
2. *Yönetici > Müşteri İşlemleri > Müşteri Listesi*: ekranı açar, **Yıl'ı seçip Ara'ya basar**, sonra listeyi okur. Yalnızca o yılın
   dönemi açılmış firmalar gelir (kapanış tarihi girilmemiş eski firmalar böylece listeye girmez); geçen yıl okunmaz
   (`LUCA_MUSTERI_YILI=otomatik|yok|2027,2026`; Ocak'ta yeni dönemi henüz açılmamış firmaların Aralık beyannameleri
   için gerekirse `2027,2026` yazılabilir). Sayfa HTML'inden okunur (Kısa/Uzun Ad, VKN, TC, Kuruluş ve Kapanış
   Tarihi ve Luca'nın değişmez şirket kimliği); filtrenin gerçekten uygulandığı sayfanın kendi yazdığı yıl bilgisinden ve
   "Kayıt Sayısı"ndan doğrulanır. Aynı VKN'yi taşıyan iki kayıt (tasfiye) ayrı mükelleftir. Kapanmış firmalar tarihten
   anlaşılır ve web sayfasında varsayılan olarak gizlenir. **Dönemi açılmamış firma için beyanname takibi yapılmaz.**
3. *Muhasebe > Beyannameler > GİB Beyanname Takip* (Luca bunu ayrı bir pencerede açar):
   * Önce **"GİB'den Getir"**: Luca beyannameleri kendiliğinden çekmez; arama ekranı yalnızca daha önce GİB'den getirilmiş
     kayıtları bulur. Düğme bir **"GİB Beyanname Sorgula" tarih penceresi** açar (en fazla 31 günlük, aynı yıl içinde bir
     yükleme tarihi aralığı); program son `LUCA_GIB_GUN` günü (varsayılan 15, en çok 31; yıl başından öncesi kırpılır) yazar,
     "Beyannameleri GİB'dan Getir"e basar. "İşlem Takip" penceresinde GİB sorgusu ilerler (yaklaşık 1 dk/ay) ve bitince
     "Ekrandaki listeyi yenilemek için…" yazısı çıkar; pencere kendiliğinden kapanmaz: program bu yazıyı bekler ve yeşil
     **"buraya"** bağlantısına basar (pencereyi kapatır ve listeyi yeniler; kapanmazsa yedek olarak "Kapat"). `LUCA_GIB_GETIR=0` adımı kapatır, `LUCA_GIB_GETIR_SN` bekleme süresidir (180). Luca'nın GİB kullanıcı kodu/şifresi
     "Yönetici > SM/SMM Bilgileri > Kurum Şifre Bilgileri"nde kayıtlı olmalıdır. İlk kurulumda bir kez `LUCA_GIB_GUN=31` verin.
     Çalışmazsa eski veriyle devam edilir ve mesajlara "Luca verisi güncel olmayabilir" uyarısı eklenir.
   * Sonra Filtre penceresinde **"Beyanname Durum" = Tümü** (pencere varsayılan olarak "Onaylanmış" açılır; Tümü seçilmezse
     hatalı ve iptal edilmiş beyannameler hiç gelmez) ve yalnızca **Paket Yükleme Tarihi** aralığı yazılır (son günü
     yaklaşan en eski dönemin bitişinden bugüne), "Beyannameleri Listele". Dönem ve tür filtresi yoktur.
   * Ekranın kendi isteğinin yanıtı (`beyan_listele.jq`, JSON) yakalanır; tablo okunmaz. Her kayıtta tür (`beyannameKodu`:
     KDV1, MUHSGK, KGECICI…), dönem (3 aylıklarda dönem bitişi), durum, VKN/TCKN, Luca kısa adı vardır; toplam sayı
     ("243 adet beyanname kaydı listelendi") yanıttaki kayıt sayısıyla doğrulanır.
   * Eşleştirme: VKN/TCKN, yoksa Luca kısa adı, yoksa unvan. Bir dönem için **onaylanmış kayıt varsa verildi**; yalnızca
     hatalı/iptal edilmiş kayıt varsa "gönderilmiş ama ONAYLANMAMIŞ" diye uyarılır; tanınmayan bir durum metni onaylı sayılmaz.
   * **SGK (e-Bildirge):** ekrandaki "E-Bil." sütunu; simge, işyeri SGK numarası başına bir bildirgeyi gösterir (rozet: yeşil
     onaylı, kırmızı hatalı, gri iptal). Kural: **çalışanı olan firmanın MUHSGK'sında e-Bildirge de olmalı; yoksa prim hizmet
     bildirgesi verilmemiştir.** Onaylı bir MUHSGK'da en az bir e-Bildirge yoksa ya da yalnızca iptal (`muhSgkDurum` 6) /
     hatalı (0) e-Bildirge varsa durum **"SGK EKSİK"** olur ve diğer eksikler gibi uyarılır.
   * **Çalışanı olanlar:** *Personel > E-SGK İşlemleri > E-Bildirge Şifre Dosyası Oluşturma* listesi (SGK dosyası/işyeri tanımı
     olan firmalar; Luca şirket kimliğiyle müşteri listesine eşleşir) okunur: listede olan firma çalışanı var sayılır, olmayan
     sayılmaz (`LUCA_SGK_LISTESI=0` kapatır). **Bu sayfanın HTML'inde SGK sistem ve işyeri şifreleri düz metin olarak durur;**
     program yalnızca şirket/işyeri kimliklerini ve "kullanıcı adı dolu mu" bilgisini okur, şifre alanlarına dokunmaz,
     sayfanın HTML'ini ya da ekran görüntüsünü hiçbir yere kaydetmez. Liste okunamazsa firmanın geçmiş e-Bildirge
     kayıtlarına bakılır. Mükellef ayarında **SGK**: *Otomatik* (yukarıdaki), *Çalışanı var*, *Çalışanı yok*.
     `muhSgkDurum` "3"ün tam anlamı bilinmiyor; yeşil rozet olduğundan tamam sayılıyor.
4. Karşılaştırma, uyarı ve Telegram yukarıdaki gibidir.

**Doğrulanan:** JSON yorumlama (gerçek yanıtın alan yapısıyla uydurma veride), eşleştirme ve durum kuralları, 3 aylık
dönemlerin dönem bitişiyle eşleşmesi, "GİB'den Getir" ve filtre adımlarının sırası ve hata yönetimi (sahte tarayıcıyla) ve
`lucabot` paketinin köprünün çağırdığı bütün fonksiyonları içermesi. **Doğrulanmayan:** gerçek Luca'da uçtan uca çalışma,
girişin sunucuda (Xvfb, yurt dışı IP) çalışması, "GİB Beyanname Sorgula" penceresindeki tarih kutularının gerçek sayfada
bulunup doldurulduğu, filtre alanlarının beklenen biçimde doldurulduğu.

**İlk kurulum (sırayla):**
1. Dockerfile.luca ile (özel depodan) derleyin; ortam değişkenleri: `TOPLAYICI=luca`, `LUCA_UYE_NO`, `LUCA_KULLANICI`,
   `LUCA_PAROLA`, `LUCA_DOGRULAMA_ANAHTARI`. İki Luca hesabı için `LUCA_HESAPLAR=ofis,isletme` ve
   `LUCA_OFIS_UYE_NO`, `LUCA_ISLETME_PAROLA` gibi ön ekli adlar kullanılır.
2. Web sayfasında **Tanı** sekmesi → "Tanıyı çalıştır". Luca'ya girip müşteri listesi ve GİB Beyanname Takip
   ekranlarını açar; **ekran görüntülerini ve beyanname listesinin ham yanıtını (`beyan_listele.json`, son 30 gün)** sayfada gösterir. Veri kaydetmez, beyanname kontrolünü etkilemez; 1-3 dakika sürer. Sonucu buradan inceleyin ya da
   "Hepsini indir (zip)" ile alın (mükellef adı içerir, paylaşmadan önce karalayın). Aynı işi `LUCA_TANI=1` ortam
   değişkeni de yapar, ama sekme varken gerekmez. Sayfa kaynağı (html) güvenlik için düz metin olarak gösterilir.
3. Tanı sonuçları doğruysa "Şimdi Luca'dan çek" ile gerçek veriyi alın. Web sayfasında uyarı çıkarsa
   (örn. "N beyanname satırı hiçbir mükellefle eşleşmedi") ad eşleşmesi ya da sayfalama sorunu vardır.

**Güvenlik kararları:**
* Eksik/uyumsuz bir şey varsa program sessizce devam etmez, **toplamayı durdurur ve Telegram'dan bildirir**
  (örn. "Beyanname Durum" listesinde "Tümü" yoksa, yanıtın kayıt sayısı sayfanın yazdığıyla uyuşmazsa, yanıt JSON değilse).
* İki hesaptan biri başarısız olursa tüm toplama başarısız sayılır, eski veri korunur (bir hesabın verisi sessizce silinmez).
* `lucabot` ekrana firma adı yazar; bu çıktı sunucu günlüğüne değil `DATA_DIR/tani/<hesap>/calisma.log` dosyasına yönlendirilir.
* Luca girişi başarısız olursa o anki ekran görüntüsü Telegram'a gönderilir (captcha ya da şifre sorunu görülsün).
  **Captcha cevabını sunucudan Luca'ya otomatik yazma henüz yok** (captcha alanını gerçek ekranda görmeden yazılmadı);
  Luca'da kimlik doğrulayıcı ile iki aşamalı doğrulama açıksa captcha hiç çıkmaz.
* Hatalı ve iptal edilmiş beyannameler de okunur; yalnızca onaylı kayıt "verildi" sayılır.
* Tanı ve çalışma sırasında SGK şifre sayfasının HTML'i/ekran görüntüsü diske yazılmaz (`tani_kaydet` o ekranda çağrılmaz).

## Render'a kurulum

1. Bu klasörü içeren **özel** bir depo oluşturun (yukarıdaki lisans notu) ya da yalnızca `TOPLAYICI=dosya`
   için bu depoyu kullanın (veri depoda değil, diskte durur).
2. Render → New → **Web Service** → Docker; Root Directory `beyanname-takip`; plan **Starter**;
   **Disk** ekleyin (Mount path `/data`, 1 GB); Health Check Path `/saglik`.
3. Ortam değişkenlerini girin (`DATA_DIR=/data`, `TZ=Europe/Istanbul` dahil). **Instance sayısı 1** olmalı.
4. Açılınca web sayfasından giriş yapın → Sistem → Telegram test mesajı → Mükellefler sekmesinde ayarları onaylayın.

## Güvenlik notları

* Mükellef verisi yalnızca `DATA_DIR`'de (sunucu diskinde) durur; depoya girmez (`veri/` git'te yok sayılır).
* Günlüklere mesaj metni, mükellef adı ve token yazılmaz.
* Parola ve TOTP anahtarını sunucuya koymak ikinci doğrulamayı fiilen sunucuya emanet eder; bu yüzden Luca'da
  yalnızca okuma yetkili ayrı bir robot kullanıcısı önerilir.
* Mükellef verisi yurt dışı sunucuda işleniyorsa KVKK / vergi mahremiyeti açısından kendi değerlendirmenizi yapın.
