# Beyanname Takip

Luca'daki mükellef listesini ve verilmiş beyannameleri karşılaştırır; son güne yaklaşırken ve son gün
akşamı **verilmemiş** beyannameleri Telegram'dan bildirir. Web sayfasından durum görülür.

> **Durum:** Uyarı mantığı, web sayfası, Telegram ve captcha köprüsü hazır ve test edilmiş (39 test).
> **Luca'dan otomatik veri çekme (`luca_toplayici.py`) henüz yazılmadı.** Şimdilik `TOPLAYICI=dosya`
> ile Dijital Stajyer çıktıları sunucuya konarak çalışır. Ayrıntı aşağıda.

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

## Luca toplayıcı (yapılacak)

`app/luca_toplayici.py` içinde ayrıntılı not var. Özet: giriş, doğrulama kodu (TOTP), mükellef listesi
Dijital Stajyer'in `lucabot` paketinden gelir; **GİB Beyanname Takip ekranından satır okuma yeni yazılacak**
(mevcut kod yalnızca KDV1 PDF'lerini indirir) ve gerçek ekran görülerek doğrulanmalıdır.

**Önemli:** `lucabot` lisanslı bir programdır ve bu depo herkese açıktır. `lucabot` klasörü bu depoya
konmamalı; Luca modu için bu klasör, `lucabot` ile birlikte **özel (private) bir depoya** taşınıp oradan
derlenmelidir. Dockerfile bu durumda Playwright imajına çevrilir.

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
