# Luca Toplu e-Fatura İndirme Botu

Luca'da her firma için tek tek yaptığınız **Akıllı Entegrasyon Noktası → e-Arşiv Alış Faturaları → GİB'den Getir → Seçilenleri İndir** işlemini
tüm firmalar için sırayla otomatik yapar. İndirilen dosyaları ve fatura listelerini bilgisayarınızda firma bazında klasörlere kaydeder.

**Giriş bilgileri yalnızca bu bilgisayardaki `ayarlar.json`'da tutulur** (başka yere gönderilmez); girilirse
bot Luca'ya kendisi girer, girilmezse tarayıcıyı açar ve girişi **siz elle** yaparsınız. Sonrasındaki tekrar eden işi bot devralır.

## Kurulum (tek seferlik)

> **Hiç bilgisayar bilgisi olmayan biri için adım adım rehber: `OKU-BENI-ONCE.txt`** (Python'u nasıl kuracağınız, sihirbaz ve sorun giderme). Python kurulu değilken herhangi bir .bat dosyasını çalıştırırsanız program bunu söyler, Python indirme sayfasını ve bu rehberi kendisi açar.

1. **Python kurun:** https://www.python.org/downloads/ — kurulum ekranındaki
   **"Add python.exe to PATH"** kutusunu mutlaka işaretleyin, sonra "Install Now".
2. **`kurulum.bat`** dosyasına çift tıklayın. Gerekli her şeyi kendisi kurar.

Tarayıcı olarak **Playwright'in kendi Chromium'u** kullanılır (`tarayici-indir.bat` ile bir kez inen tarayıcı).
Bulunamazsa bilgisayardaki Chrome, sonra Edge denenir.

**Neden kurulu Chrome değil:** HP Sure Click gibi güvenlik yazılımları sistemdeki Chrome ve Edge'e kanca
takıp indirilen dosyayı izole ortamda açmaya çalışıyor ve tarayıcıyı indirme anında çökertiyor.
Paketli Chromium bu kancanın dışında kalıyor. Makinenizde böyle bir yazılım yoksa `ayarlar.json`'a
`"tarayici": "chrome"` yazarak kurulu Chrome'a dönebilirsiniz.

Komutla yapmayı tercih ederseniz, bu klasörde komut istemi açıp:

```
pip install -r requirements.txt
python -m playwright install chromium
```

## Arayüz (en kolay yol): `luca-arayuz.bat`

Komut satırı kullanmadan, pencereden çalıştırmak için `luca-arayuz.bat`'a çift tıklayın
(arkada siyah pencere kalmaz: arayüz konsolsuz `pythonw` ile açılır; `.bat` bunu bulamazsa arayüz
kendisini konsolsuz yeniden başlatır. Hiçbiri olmazsa küçültülmüş bir siyah pencere kalır, onu kapatmayın).

1. **Luca Girişi › Değiştir**: Üye No, Kullanıcı Adı, Parola (ve varsa iki aşamalı giriş
   anahtarı) bir kez girilir, `ayarlar.json`'a kaydedilir. Program Luca'ya kendisi girer.
2. **Firma Listesi**: firma listesi artık Luca'dan alınır (ayrıca Excel yüklenmez, şablon indirilmez).
   Ekran sütunlarında **✓ = sorgulanır, X = sorgulanmaz** (boş = sorgulanır).
   **KDV Devri ve Ekran Seçimi** listeyi tablo olarak açar: her firmanın Devreden KDV'sini yazar,
   hangi ekranın sorgulanacağını kutucuklarla işaretlersiniz; alttan firma eklenir, ✕ ile çıkarılır.
   **Kaydet** Excel'e yazar (önce `firmalar.yedek-...xlsx` yedeği alınır; diğer sütun ve sayfalara
   dokunulmaz). Liste hiç yoksa ilk kullanımda yeni bir `firmalar.xlsx` oluşturulur.
   **Luca'dan Firma Çek** (soldaki buton) Luca'nın **Yönetici › Müşteri İşlemleri › Müşteri Listesi**
   ekranını açar, **Filtre**'de **Yıl**'ı tarih aralığının yılına (örn. 2026) getirip **Ara**'ya basar
   ve o yılın firmalarını açılış/kapanış tarihleriyle okur. Sonra `firmalar.xlsx` ile farkı gösterilir
   (yeni firmalar, güncellenecek açılış/kapanış, Luca'nın o yıl listesinde olmayan firmalar);
   **Tabloya Uygula**'ya basmadan dosyaya yazılmaz. Liste Luca'yı yansıtır: Luca'da olmayan firmalar
   çıkarılır (kutucuktan vazgeçilebilir), yeni firmalar tüm ekranlar işaretli eklenir; listede kalan
   firmaların ekran seçimleri ve Devreden KDV'si değişmez (yedek alınır). Luca'da kapanışı boş olan firmanın tablodaki kapanışı korunur, kapanış tarihi dönem sonuysa
   (31/12) firma açık sayılır. Okunan ham liste `indirilenler\luca-musteri-listesi.json`'a, ekran
   görüntüsü ve sayfa kaynağı günlük klasörün `tani` klasörüne kaydedilir. Komut satırından:
   `python luca_bot.py --firma-listesi-cek --yil 2026`.
   **Luca'dan Devir Çek** (KDV Devri penceresinde) Luca'da **Muhasebe › Beyannameler › GİB Beyanname
   Takip** ekranını açar, **Filtre**'de dönemi (kontrol edilen dönemin bir önceki ayı, örn. Eylül
   kontrolü için Ağustos), Beyanname Durum = Onaylanmış ve Beyanname = KDV1 seçip **Beyannameleri
   Listele**'ye basar, başlıktaki kutuyla hepsini seçer ve **Toplu İşlemler**'deki "beyanname ve tahakkuk
   dosyalarını indirmek için buraya" bağlantısıyla hepsini tek ZIP olarak indirir. ZIP'ten tahakkuk
   dosyaları atılır, beyanname PDF'leri `indirilenler\beyannameler\<tarih>` klasörüne çıkarılır ve
   aşağıdaki "Beyannameden Devir Al" mantığıyla devirler tabloya yazılır (Kaydet'e kadar dosyaya geçmez).
   Bu ekran Luca'da **ayrı pencerede** açılır (bot onu kendisi bulur, iş bitince kapatır). Menü yolu her
   defter türünde aynıdır ama ilk basamak firmanın modul sekmesidir: genel muhasebede **Muhasebe**,
   serbest meslekte **Ser.Mes.Defteri**, işletmede **İşletme Defteri**; bot bu sekmeyi kendisi bulur.
   Menü hiç bulunamazsa bot firmaları dener ve bulduğunu `indirilenler\beyanname-firmasi.txt`'e yazıp sonraki
   seferde ilk onu dener (`ayarlar.json`'a `"beyanname_firmasi": "FİRMA ADI"` yazılarak da verilebilir).
   Filtredeki yıl listesi seçili firmanın çalışma dönemine bağlıdır (2025 firmasında 2024/2025); bot bu yüzden
   kontrol edilen yılın dönemi açık bir firma seçer, gerekirse firmanın o yılın dönemine geçer.
   Menü yolu değişirse `ayarlar.json`'a `"beyanname_menusu": "Muhasebe > Beyannameler > GİB Beyanname
   Takip"` biçiminde yeni yol yazılabilir. Komut satırından: `python luca_bot.py --beyanname-cek
   --baslangic 01/09/2026 --bitis 30/09/2026`.
   **Beyannameden Devir Al** ile KDV1 beyannamesi PDF'leri (birden çok seçilebilir) okunur, devir
   tabloya yazılır. Kontrol edilen dönem Eylül ise **Ağustos** beyannamesinin "Sonraki Döneme
   Devreden" satırı ya da Eylül beyannamesinin "101 - Önceki Dönemden Devreden" satırı alınır (ikisi
   aynı tutardır; ana penceredeki tarih aralığı dönemi belirler). Firma, beyannamedeki unvandan ve
   dosya adındaki kısa addan bulunur; bulunamayan, dönemi tutmayan ya da okunamayan dosyalar sonuç
   listesinde gösterilir. Düzeltme beyannamesi varsa en son onaylanan alınır. Tutarlar **Kaydet**'e
   basınca dosyaya yazılır.
   Tek firma için "Sadece bu firma" kutusuna adını yazın.
3. **Tarih Aralığı** ve **Ekranlar**'ı seçip **Çalıştır**'a basın. İlerleme ve log pencerede
   canlı akar. **Durdur** (bota `durdur.istek` dosyasıyla haber verir, bot bir sonraki bekleme adımında
   görüp) o ana kadarki sonuçları kaydederek durdurur; tekrar Çalıştır'a basınca
   kaldığı yerden sürer ("Bugün bitenleri atla" işaretliyse).
4. Alttaki kutular seçili dönem için `rapor.json`'dan hesaplanır, tıklayınca firmaları listeler
   (**Excel olarak indir** listeyi .xlsx olarak kaydedip açar):
   - **Alış Tevkifat KDV**: tevkifatlı alış faturaları (KDV2). Excel'de tevkifat tutarı sütunu
     yoksa faturanın KDV'si gösterilir ve `*` ile işaretlenir.
   - **Alış SMM**: e-SMM alış makbuzları.
   - **İnteraktif Farkı**: İnteraktif V.D. ile e-Arşiv Alış'ın fatura sayısı tutmayan firmalar.
     Her firmanın altında eksik/fazla faturalar tek tek yazar: ismin ilk kelimesi, kısaltılmış fatura
     numarası (`GIB..756`: ilk 3 karakter, son 3 hane) ve tutar (listeler farklı numaralanmışsa bunu söyler).
   - **Hata / İnmeyen**: hata alan, belge paketi/Excel'i inmeyen ya da bazı faturaları kaynak
     sunucudan inmeyen firma/ekranlar (neden ve inmeyen fatura sayısıyla). **Bunları Tekrar Sorgula**
     yalnızca bu firma ve ekranları, ana penceredeki tarih aralığı için yeniden çalıştırır
     (komut satırı: `--tekrar-listesi dosya.json`, içeriği `{"firma": ["e-arsiv-alis", ...]}`).
   - **KDV Ödemesi**: Satış KDV − Alış KDV − Devreden KDV > 0 olan firmalar. Devreden
     KDV'yi `firmalar.xlsx`'e **"Devreden KDV"** adlı bir sütun açıp elle yazın; boşsa 0 sayılır.
     Tahmindir (diğer beyan kalemleri girmez).

### Görünüm (açık / koyu tema), logo, sürüm

Logo **Robot Stajyer**'dir (`varliklar/logo.svg`, program `logo-48/96/256.png` dosyalarını kullanır; pencere simgesi de odur). Pencerenin altındaki satırda telif notu ve **Sürüm** yazar; sürüme tıklayınca *Hakkında* penceresi açılır. Telif satırındaki yıl kendiliğinden güncellenir. Sürüm numarası `lucabot/__init__.py` içindeki `SURUM`'dür.

Program **açık temayla** açılır. Sağ üstteki **🌙 Koyu tema / ☀ Açık tema** düğmesi temayı değiştirir ve seçimi `ayarlar.json > tema` (`acik` / `koyu`) olarak hatırlar. Çalışma sürerken tema değiştirilemez. Başlık bandı: "Dijital Stajyer — SMMM OFİSİ - DİJİTAL ASİSTAN"; sağ üstte lisans sahibi yazar.

### Otomatik ikinci tur ve özet e-postası

- **Otomatik ikinci tur:** Fatura indirme çalışması bitince, hata alan / dosyası ya da Excel'i inmeyen / bazı faturaları
  kaynaktan inmeyen ekranlar **ayrıca bir kez**, aynı Luca oturumunda yeniden sorgulanır (zaman aşımı gibi geçici hatalar çoğu
  zaman düzelir). "Ekran açılmadı" (firmada o ekran yok) tekrarlanmaz. Kullanıcı çalışmayı durdurduysa ya da Luca oturumu bozulduğu
  için çalışma yarıda kaldıysa ikinci tur yapılmaz. Kapatmak için `ayarlar.json > "otomatik_tekrar": false` ya da komut satırında
  `--otomatik-tekrar-yok`. Sonuçlar raporu ve **Hatalı / İnmeyen** sekmesini günceller.
- **Özet e-postası** (Outlook/SMTP ayarları aynı; bkz. `eposta.py`): konu satırı `[3 firmada hata]` ya da `[Sorunsuz]` ile başlar.
  Gövde şunları içerir: kaç firmanın sorunsuz / hatalı olduğu, otomatik ikinci turda kaç ekranın düzeldiği, **tekrar sorgulanması
  gereken ekranların listesi** (firma, ekran, hata nedeni), tevkifat / e-SMM / iptal uyarıları; rapor.xlsx ektedir.

### Yeni kullanıcı / yeni bilgisayar: Kurulum Sihirbazı

Programı başka bir bilgisayara ya da başka bir Luca kullanıcısı için kurarken: zip'i açın, Python'u kurun
(**"Add python.exe to PATH"** işaretli), `kurulum.bat`'ı çalıştırın, `luca-arayuz.bat` ile açın. **Luca giriş bilgileri
hiç girilmemişse sihirbaz kendiliğinden açılır**; sonradan sol paneldeki **Kurulum Sihirbazı…** düğmesiyle de açılır.

1. **Hoş geldiniz:** ortam kontrolü (Python, Playwright, openpyxl, Chromium, `kar-zarar` klasörü). Eksik bileşen varsa **Eksik bileşenleri şimdi kur** düğmesi `kurulum.bat`'ın işini pencerenin içinde yapar (`pip install -r requirements.txt`, gerekirse `playwright install chromium`); çıktısı canlı akar, bitince ortam yeniden kontrol edilir. (Python'un kendisi önceden kurulu olmalıdır; sihirbaz onu kuramaz.)
2. **Luca girişi:** üye no, kullanıcı adı, parola, isteğe bağlı doğrulama anahtarı.
3. **Defter Beyan** (isteğe bağlı): kod ve şifre (güvenlik kodunu yine siz yazarsınız).
4. **Tercihler:** indirme klasörü, özet e-postası (alıcı), otomatik ikinci tur, açık/koyu görünüm.
5. **Hazır:** özet; **Bitirince Luca'dan firma listesini çek** kutusu işaretliyse liste hemen çekilir (giriş bilgisi de böylece denenir).

Her kopya kendi `ayarlar.json`'unu, tarayıcı oturumunu ve `indirilenler` klasörünü kullanır; bu yüzden aynı bilgisayarda ikinci bir
Luca kullanıcısı için klasörü başka bir adla kopyalamanız yeterlidir. Bir kopyayı başkasına verirken içindeki `ayarlar.json`,
`indirilenler`, `.tarayici-profili` ve `kar-zarar\ayarlar.json`'u **vermeyin** (şifre ve müşteri verisi içerir).
`mail_gonder: false` özet e-postasını kapatır.

### Fatura İndirme sekmesinin alt ekranları

Sağ panelde üç alt sekme vardır:

- **Süreç**: çalışırken ilerleme çubuğu, canlı log ve altta özet kutuları (eskisi gibi).
- **Firma Durumu**: `rapor.xlsx`'teki firma satırlarının aynısı (durum, aksiyon, ekran başına fatura sayısı, matrahlar, not, son işlem).
  Satır renkleri: yeşil = tamam, turuncu = aksiyon gerekiyor, kırmızı = hata, gri = bekliyor. **Ara** kutusu tüm sütunlarda
  arar (Türkçe harf/büyük-küçük farkı yok), **Dönem** ve **Durum** kutularıyla süzülür, bir **başlığa tıklayınca** sıralanır
  (tekrar tıklayınca ters, üçüncüde kalkar; tutarlar ve tarihler sayı/tarih olarak sıralanır). Varsayılan dönem filtresi
  ana penceredeki tarih aralığıdır.
- **Hatalı / İnmeyen**: sorgulamada hata alan ya da faturaları kaynaktan inmeyen firma/ekranlar. Ekran ve Durum kutularıyla
  süzüp satırları (Ctrl / Shift ile birden çok) seçin; **Seçilenleri Tekrar Sorgula** yalnızca bunları, **Görünenlerin Hepsini
  Tekrar Sorgula** süzülmüş listenin tamamını ana penceredeki tarih aralığı için yeniden çalıştırır.

Kâr / Zarar sekmesindeki tabloda da aynı arama, Kaynak filtresi ve sıralama vardır. Üçüncü sekme
(**Luca Mükerrer / Eksik Fatura Tespiti**) şimdilik "Çalışma var" yer tutucusudur.

### Kâr / Zarar sekmesi

Pencerenin üstündeki **Kâr / Zarar** sekmesi, repodaki ayrı `kar-zarar/` programını
(`luca-bot` klasörünün yanında durmalı) arka planda çalıştırır; ayrıntı için `kar-zarar/README.md`.

- Dönem (varsayılan: Ocak başından Luca'ya işlenmiş son ay sonuna), isteğe bağlı tek firma, Luca
  kaynağı (Mizan / Hesap Planı) ve Defter Beyan kullanıcı kodu/şifresi girilir. Luca girişi
  Fatura İndirme'deki bilgilerden her çalıştırmada `kar-zarar/ayarlar.json`'a aktarılır.
  **Defter Beyan güvenlik kodunu açılan tarayıcıda siz yazarsınız.**
- Sonuç tablosu kârdan zarara sıralıdır; satıra tıklayınca özet cümle çıkar. **Excel olarak indir**
  tablonun tamamını (fatura sütunlarıyla) kaydeder; **Programın Excel Raporu** `kar-zarar` programının
  kendi raporunu açar.
- **Faturalar dahil** (tablonun üstündeki **Taranan Faturaları Dahil Et** düğmesi; yanındaki kutudan **hangi ayın** faturalarının dahil edileceğini seçersiniz, tekrar basınca çıkar): Luca'ya henüz işlenmemiş bir döneme ait indirilmiş faturalar (rapor.json'daki
  dönem, kâr/zarar döneminden sonra başlıyorsa) varsa, KDV hariç satış − alış kâra eklenip ayrıca
  gösterilir: "1–8. ay kâr X; Eylül faturaları dahil edilince Y". Faturalardan mal alışı ile gider
  ayrılamadığı için alış tek kalem sayılır; maaş, amortisman gibi yevmiye kalemleri faturada olmaz — **tahmindir**.
  Seçilen ay kâr/zarar dönemiyle çakışıyorsa aynı ay iki kez sayılmaması için eklenmez.
  Kutudaki aylar `indirilenler/rapor-donemler.json`'dan gelir: yeni aya geçildiğinde eski ayın tutarları orada saklanır
  (bu özellikten önce indirilip üzerine yazılmış aylar geri getirilemez; o ayı yeniden indirmek gerekir).
- Önceki sorgular tabloda kalır: yeni sorgu başkalarını silmez, yalnızca aynı firma + aynı dönemi günceller. Tabloda **Dönem** sütunu/filtresi vardır; toplam yalnızca görünen satırlardan (tek dönem seçiliyken) hesaplanır.
- Firma listesi her sorguda çekilmez: ilk sorguda Luca'dan okunup kaydedilir, sonra kayıttan yüklenir; "Firma listesini Luca'dan yeniden çek" kutusu işaretlenirse yenilenir.
- Fatura İndirme ve Kâr / Zarar aynı anda çalışmaz (ikisi de Luca'ya girer).

İptal/itiraz edilen faturalar tutarlara dahil edilmez. Python'da pencere kütüphanesi (tkinter)
yoksa `.bat` bunu söyler; python.org'dan kurarken "tcl/tk and IDLE" işaretli olmalı (varsayılan).

## Çalıştırma (çift tıklayarak)

| Dosya | Ne yapar |
| --- | --- |
| `luca-arayuz.bat` | **Pencereli arayüz** (yukarıya bakın) |
| `kurulum.bat` | Tek seferlik kurulum |
| `firmalari-listele.bat` | Luca'daki firma adlarını listeler (test için doğru adı öğrenmek üzere) |
| `calistir.bat` | Tarih aralığını sorar, faturaları çeker. Firma adı sorulduğunda boş bırakırsanız tüm firmalar işlenir |
| `karsilastirmali-calistir.bat` | **Her firmada iki ekranı da çalıştırır** ve raporda karşılaştırır |
| `interaktif-earsiv.bat` | İnteraktif Vergi Dairesi ekranından e-Arşiv faturalarını sorgular (GİB Servis ile, 2 kez) |
| `bagimsiz-tarayici-ile-calistir.bat` | Chrome ve Edge çöküyorsa: Playwright Chromium ile çalışır (güvenlik yazılımlarının kancası dışında kalır) |
| `edge-ile-calistir.bat` | Chrome indirme sırasında çöküyorsa Edge ile çalıştırır |
| `gece-calistir.bat` | Tüm firmalar için çalışır, iş bitince tarayıcıyı kendisi kapatır (gece bırakıp gitmek için) |
| `luca-giris.bat` | **Fatura çekme botuyla ilgisi yok:** `ayarlar.json`'daki bilgilerle Luca'ya tek tıkla otomatik giriş yapar, tarayıcıyı açık bırakır. Aynı klasörü (ya da OneDrive ile bu dosyayı) ofis ve ev bilgisayarına koyup ikisinde de kullanabilirsiniz; Chrome'u kapatınca pencere kendiliğinden kapanır |
| `gecis-rapor-birlestir.bat` | **Bir kereye mahsus:** eskiden her gün ayrı çıkan `indirilenler\GG-AA-YYYY\rapor.xlsx` dosyalarını, şimdiki tek ve sürekli `indirilenler\rapor.xlsx`'e birleştirir. Eski günlük dosyalara dokunmaz, üzerine yazmadan önce mevcut raporu yedekler |

## Ayarlar (`ayarlar.json`)

| Ayar | Anlamı |
| --- | --- |
| `sorgu_azami_dakika` | Bir GİB sorgusu için beklenecek en uzun süre (varsayılan 30) |
| `durgunluk_dakika` | İşlem Takip penceresi bu kadar süre hiç ilerlemezse sorgu takılmış sayılır (varsayılan 3) |
| `tarayici` | `chromium` / `chrome` / `edge`. HP Sure Click gibi güvenlik yazılımları Chrome ve Edge'e kanca takıp indirme anında tarayıcıyı çökertiyor; varsayılan `chromium` bu yüzden |
| `iptal_itiraz_sorgula` | Faturalar indikten sonra GİB'den iptal/itiraz durumunu da sorgula (varsayılan açık) |
| `tekrar_deneme` | İndirilemeyen fatura kalırsa sorgunun kaç kez tekrarlanacağı (varsayılan 3) |
| `ardisik_hata_siniri` | Üst üste kaç firma hata verirse çalışma durdurulur (varsayılan 5) |
| `dosya inmedi` durumu | Tarayıcı indirme sırasında çöktü; bot firmayı yeniden dener, o da olmazsa raporda `DOSYA INMEDI - tekrar calistir` yazar. Programı tekrar çalıştırmak yeterli. |
| `indirme_sekmesiz` | İndirme sırasında Luca'nın açtığı boş sekme yerine gizli çerçeve kullan (varsayılan açık); sorun çıkarırsa `false` yazın. Yine de sekme açılırsa `calisma.log`'a `TANI: indirme sirasinda ... yeni sekme acildi` satırı düşer |
| `atlanacak_firmalar` | İşlenmeyecek firma adları (nadiren gerekir). Luca adı kısaltarak gösterdiği için adın baş kısmını yazmanız yeterli |

**Hangi firmaların işleneceğini asıl `firmalar.xlsx` belirler**: listede olmayan firma zaten hiç açılmaz,
listede olup belirli ekranları X ile işaretlenen firmada da yalnızca o ekranlar atlanır. `atlanacak_firmalar`
bunun üzerine binen ayrı bir isim listesidir; `firmalar.xlsx`'e girmeyen bir firmayı ayrıca burada da
yazmanıza gerek yoktur — zaten atlanır. Kapanmış firmaların referans listesi `kapali-firmalar.md` dosyasındadır.
Firmanın Luca'daki çalışma dönemi istediğiniz tarihlerden eskiyse (Luca her firmada en son
kullanılan dönemi hatırlar) bot dönem listesinden **istenen yılın dönemini seçer** ve devam eder.
Yeni kurulan firmada `15/04/2026 - 31/12/2026`, eskisinde `01/01/2026 - 31/12/2026` olması fark etmez;
eşleştirme yıla göre yapılır. O yıla ait dönem hiç yoksa (gerçekten kapanmış firma) sorgu
çalıştırılmaz, özete `dönem dışı` yazılır.

## Tarih aralığı (7 gün sınırı)

GİB sorgusu tek seferde en fazla 7 gün kabul ettiği için bot geniş aralığı kendisi 7 günlük
parçalara böler (GİB 5000/30000 ve İnteraktif V.D. aylık sorgu kabul ettiği için onlarda 30 gün).
Siz sadece geniş aralığı verirsiniz:

```
python luca_bot.py --baslangic 01/08/2026 --bitis 15/09/2026
```

Sorgular bu aralıkta yapılır; **listeleme ve indirme ise başlangıç ayının tamamı** (01/08–31/08)
üzerinden yapılır — eylülde kesilen ağustos faturaları da yakalanır. Tarih vermezseniz içinde
bulunulan ay sorgulanır.

## Kullanım (komut satırı)

**İlk deneme — önce tek firma ile test edin:**

```
python luca_bot.py --firma "AKIN ÇOBAN"
```

**Firma listesini görmek için:**

```
python luca_bot.py --listele
```

**Tüm firmalar için:**

```
python luca_bot.py
```

**Diğer belge tipleri:**

```
python luca_bot.py --belge-tipi e-fatura-alis
python luca_bot.py --belge-tipi e-arsiv-satis
python luca_bot.py --belge-tipi e-fatura-satis
python luca_bot.py --belge-tipi e-arsiv-interaktif
```

`e-arsiv-interaktif`, **İşletme Defteri → E-Arşiv Faturaları Sorgulama** ekranını kullanır.
Diğerlerinden farkı: Akıllı Entegrasyon Noktası'ndan değil doğrudan modül menüsünden açılır,
belge indirme butonu yoktur. Akış: tarih aralığı → **İnteraktif V.D'sinden E-Arşiv Faturalarını Sorgula**
→ **GİB Servis ile Sorgula** (iki kez) → tümünü seç → **GİB'den İptal/İtiraz Sorgula** → **Excel**.

İlk 3 firmayla denemek için `--limit 3` ekleyebilirsiniz.

## Dosyalar nasıl iniyor

Dosyayı tarayıcı indirmez: bot indirme isteğini yakalar, gövdeyi kendisi alır ve diske yazar.
Sebebi, bu makinede Chrome'un indirmeyi kaydettiği anda çökmesi (`AddKeepAlive kDownloadInProgress`)
— hem Chrome hem Edge hem de Playwright Chromium'da aynı şekilde. İstek yakalandığı için tarayıcının
indirme mekanizması hiç devreye girmiyor. Yakalama olmazsa tarayıcı indirmesi yedek olarak dinleniyor.

Eski davranışa dönmek için: `python luca_bot.py --tarayici-indirsin` veya `ayarlar.json`'da
`"indirmeyi_yakala": false`.

## Çalışırken ne oluyor

Ekranda dört adım başlığı görürsünüz:

1. **LUCA GİRİŞ** — tarayıcı açılır; `ayarlar.json`'da giriş bilgileri varsa bot kendisi girer,
   yoksa siz girip firma ekranı gelince **ENTER**'a basarsınız.
2. **FİRMA LİSTESİ** — Luca'daki firmalar `firmalar.xlsx` ile süzülür (kapanmış firmalar, X ile
   işaretli ekranlar atlanır). Aynı gün yarıda kalmış bir çalışma varsa **[D]evam / [B]aştan** sorulur.
3. **FATURA SORGULAMA VE İNDİRME** — her firma için sıra ve tahmini kalan süre yazılır; her ekranın
   sonunda tek satırlık sonuç görünür:
   ```
   [3/45] AKIN COBAN  | tahmini kalan: 1 sa 20 dk
     [OK] e-Arşiv Alış Faturaları: tamam (12 fatura, 2 dosya, 1 tevkifatli, 48 sn)
     [--] e-Fatura Alış Faturaları: fatura yok (0 fatura, 21 sn)
     [!!] GİB 5000/30000: hata: LookupError (0 fatura) - menu maddesi bulunamadi
   ```
4. **RAPOR** — sonuç kutusu (kaç ekran başarılı/boş/sorunlu, toplam fatura, tevkifat, iptal),
   `rapor.xlsx` ve özet e-postası.

Arayüzde ilerleme çubuğunun altındaki **"Şu an: … — 14 sn"** satırı botun o an ne yaptığını ve o
adımda ne zamandır beklediğini gösterir; 30 sn değişmezse turuncu, 90 sn'de kırmızı olur.

**Durdurmak için Ctrl+C**: o ana kadarki sonuçlar ve rapor kaydedilir; programı yeniden
çalıştırıp **[D]evam** seçerseniz tamamlanan ekranlar tekrar açılmaz.

**Hata olursa ne olur**

| Durum | Botun davranışı |
| --- | --- |
| Bir ekranda hata | Ekran görüntüsü `hatalar/` klasörüne kaydedilir, hata rapora yazılır, firmanın **sonraki ekranına** geçilir |
| Firma seçilemedi / aynı firmada üst üste 2 ekran hata | O firma bırakılır, sıradakine geçilir |
| Tarayıcı sekmesi çöktü | Açık kalan Luca sekmesine geçilir; yoksa tarayıcı yeniden açılır ve firma **kalan ekranlarıyla** en fazla 3 kez tekrar denenir |
| Üst üste 2 firma başarısız | Luca oturumu yenilenir (giriş bilgileri varsa) |
| Üst üste `ardisik_hata_siniri` firma başarısız | Çalışma durur, rapor yazılır |
| `rapor.xlsx` Excel'de açık | Uyarı verilir, bir sonraki firmada tekrar yazılmaya çalışılır |

## Dosyalar nereye iniyor

```
indirilenler/
  rapor.xlsx                   → TEK ve SÜREKLİ TOPLU RAPOR: Özet, Firma Durumu, İndirilen
                                  Faturalar, Dosyalar, Hatalar (her çalışmada güncellenir)
  rapor.csv                    → aynı raporun CSV hâli
  rapor.json                   → raporun ara/ham verisi (elle düzenlenmez)
  ozet.csv                     → tüm firmaların durumu; her firmadan sonra güncellenir
  kalan-firmalar.txt           → henüz işlenmemiş firmalar (kaldığı yerden devam için)
  2026-09-18/                  → o günkü çalışmanın indirdiği dosyalar ve günlüğü
    AKIN COBAN/
      e-arsiv-alis/
        liste.csv              → ekrandaki fatura listesi
        belgeler_....zip       → Seçilenleri İndir çıktısı
        liste_....xls          → Luca'nın Excel çıktısı (iptal/itiraz sorgusundan sonraki hâli)
        iptal-itiraz.csv       → sadece iptal/itiraz edilmiş faturalar (varsa)
    calisma.log                → zaman damgalı çalışma kaydı
    hatalar/                   → hata olursa ekran görüntüsü ve sayfa kaydı (Hatalar sayfasından tıklanır)
```

Bir ekranda hata olursa bot durmaz; hatayı rapora yazıp sıradaki ekrana/firmaya geçer.
`hatalar/` klasöründeki ekran görüntüsünü bana gönderirseniz o adımı düzeltirim.

## Toplu rapor (`rapor.xlsx`)

**Tek bir dosyadır** — `indirilenler/rapor.xlsx` — günlük değildir: hangi gün, hangi ay için
çalıştırırsanız çalıştırın aynı dosya güncellenir, ayrı ayrı rapor birikmez. **Her firmadan
sonra kaydedilir**. İndirilen dosyaların kendisi (Excel/zip) yine günün klasöründe kalır;
sadece özet/rapor tektir. E-postaya da bu dosya eklenir. Sayfaları:

| Sayfa | İçerik |
| --- | --- |
| **Özet** | Genel tablo: firma sayısı, fatura inen / boş / atlanan / sorunlu / bekleyen ekran, toplam fatura (aynı fatura iki ekranda iki kez sayılmaz), tevkifatlı alış, iptal/itiraz, alış–satış matrahı ve KDV'si; altında **ekran bazında** dağılım |
| **Firma Durumu** | Her firma tek satır; aksiyon gerekenler en üstte ve renkli (kırmızı: hata, sarı: kontrol) |
| **İndirilen Faturalar** | Her fatura tek satır: firma, ekran, alış/satış, karşı taraf, fatura no, tutar ve **Mutabakat** sütunu — e-Arşiv Alış ile İnteraktif V.D. listeleri fatura numarasıyla eşleştirilir (`iki ekranda da var` / `e-Arşiv'de YOK` / `İnteraktif'te YOK`) |
| **Dosyalar** | İnen her dosya; klasör sütununa tıklayınca klasör açılır |
| **Hatalar ve Uyarılar** | Sorunlu ve bekleyen ekranlar: sebebi, **ne yapmanız gerektiği** ve hata anının ekran görüntüsü (tıklayınca açılır) |

**Firma Durumu** sütunları:

| Sütun | Anlamı |
| --- | --- |
| Firma / Dönem / Durum | firma, hedef dönem, en kötü durum (hata > dosya inmedi > kaynaktan inmedi > dönem dışı > atlandı > tamam > fatura yok) |
| Aksiyon | ne yapmanız gerektiği; boşsa o firmada iş yok |
| Ekran sütunları | her ekrandan gelen fatura adedi |
| Fark / Eksik-Fazla Faturalar | İnteraktif V.D. − e-Arşiv Alış; eksik/fazla faturalar ünvanın ilk kelimesi + kısa fatura numarası (`GIB..756`) + tutarla |
| İptal/İtiraz, Tevkifatlı Alış, İnmeyen | adetler (tevkifat yalnızca alış ekranlarından, KDV2 için) |
| Alış/Satış Matrah ve KDV | iptal/itiraz hariç toplamlar; aynı faturalar iki kez sayılmaz: TÜRMOB Alış = e-Fatura Alış, İnteraktif V.D. = e-Arşiv Alış, GİB 5000/30000 = e-Arşiv Satış, TÜRMOB Satış = e-Arşiv Satış + e-Fatura Satış (TÜRMOB ekranı açılmayan firmada iki parça toplanır) |

## Sık karşılaşılan durumlar

| Durum | Ne yapmalı |
| --- | --- |
| `cdn.playwright.dev ... timed out` | Tarayıcı indirmeye çalışıyor; gerekmiyor. Güncel sürümde bot bilgisayardaki Chrome'u kullanır. Chrome yoksa google.com/chrome adresinden kurun. |
| `Python bulunamadı` | Yeni Python Install Manager kurulmuş ama Python sürümü inmemiş demektir. Komut istemine `py install` yazın, sonra `kurulum.bat`'ı tekrar çalıştırın. |
| `Firma listesi (select) bulunamadi` | Giriş tamamlanmadan ENTER'a basılmış olabilir; firma ekranı açıkken tekrar deneyin. |
| `Ogeye ulasilamadi` | Menü adı o firmada farklı olabilir (İşletme Defteri / Serbest Meslek Defteri). `hatalar/` içindeki ekran görüntüsünü paylaşın. |
| `Seçilenleri İndir butonu bulunamadi` | O firmada hiç fatura gelmemiş olabilir; `ozet.csv`'de "fatura yok" görünür. |
| Chrome indirme sırasında kapanıyor | Önce `edge-ile-calistir.bat` deneyin — çökme Chrome kurulumuna özgüyse Edge'de olmaz. |
| (devamı) | Bot tarayıcıyı kendisi yeniden açar ve firmayı tekrar dener; profil oturumu taşıdığı için genelde yeniden giriş gerekmez. Devam ederse `calistir.bat` yerine komutla `python luca_bot.py --donem-degistirme` deneyin: dönem değiştirmeyi kapatır, eski dönemdeki firmaları atlar. |
| `TargetClosedError` | Chrome penceresi kapanmış. Bot açık kalan Luca sekmesine geçip firmayı tekrar dener; hiç sekme kalmadıysa durur ve kalan firmaları `bekliyor` bırakır — yeniden çalıştırmanız yeterli. Sık oluyorsa klasörü OneDrive dışına alın (örn. `C:\luca-bot`) |
| Tarayıcı her seferinde giriş istiyor | Oturum `%LOCALAPPDATA%\luca-bot\tarayici-profili` klasöründe tutulur, silmeyin. |
| `UYARI: tarih kutulari bulunamadi` | GİB tarih penceresi tanınmamış; `hatalar/` ekran görüntüsünü paylaşın, alan adlarını düzeltirim. |

## Program yapısı (geliştirmek isteyenler için)

`luca_bot.py` yalnızca giriş kapısıdır; iş `lucabot/` klasöründeki parçalara bölünmüştür:

| Dosya | Görevi |
| --- | --- |
| `giris.py` | **Luca giriş**: otomatik giriş, iki aşamalı doğrulama, ürün seçimi, oturum yenileme |
| `gib_sorgu.py` | **Fatura sorgulama**: GİB'den Getir, İşlem Takip, Belge Ara, İnteraktif V.D., iptal/itiraz |
| `indirme.py` | **Fatura indirme**: belge paketi (zip) ve Excel |
| `fatura_analiz.py` | İnen Excel/ZIP'ten tevkifat, iptal/itiraz, matrah/KDV |
| `rapor.py`, `rapor_excel.py` | **Raporlama**: `rapor.json` / `rapor.csv` / `rapor.xlsx` |
| `tablo_gorunumu.py` | Arayüzün ortak tablo bileşeni: arama, sütun filtresi, başlığa tıklayınca sıralama |
| `kar_zarar_sekmesi.py`, `lucabot/kar_zarar_ozet.py` | Arayüzün Kâr / Zarar sekmesi; sonuç + indirilen faturalar ("faturalar dahil") hesabı |
| `gostergeler.py` | Arayüzün alt kutuları (tevkifat KDV, SMM, interaktif farkı, KDV ödemesi); arayüzün kendisi `luca_arayuz.py` |
| `firma_tablosu.py` | `firmalar.xlsx` şablonu, arayüzdeki Firma / Ekran Seçimi tablosunun okunup yazılması, Luca listesiyle karşılaştırma/birleştirme |
| `luca_beyanname.py` | Luca'nın GİB Beyanname Takip ekranından KDV1 PDF'lerini toplu indirme |
| `musteri_listesi.py` | Luca'nın Yönetici › Müşteri Listesi ekranından firma (açılış/kapanış dahil) okuma |
| `eposta.py` | Özet e-postası (Outlook / SMTP) |
| `beyanname.py` | KDV1 beyanname PDF'lerinden devreden KDV'yi okuma ve firmayla eşleştirme |
| `ekran_isleyici.py` | Bir firmanın bir ekranını baştan sona işleyen akış (adım adım metotlar) |
| `calisma.py` | Tüm firmaları dolaşan döngü, hata/çökme kurtarma |
| `firma_listesi.py` | `firmalar.xlsx`, atlanacak firmalar, yarıda kalan çalışma |
| `luca_ekran.py`, `luca_gezinme.py` | Buton/pencere bulma, firma ve dönem seçimi, menü |
| `tarayici.py` | Tarayıcıyı açma / yeniden açma |
| `bekleme.py` | **Dinamik bekleme** |
| `sabitler.py` | Luca'daki buton ve menü yazıları — Luca bir yazıyı değiştirirse düzeltilecek tek yer |
| `konsol.py` | Ekrandaki adım/ilerleme mesajları |

**Beklemeler:** Programda "2 saniye bekle" gibi sabit bekleme yoktur. Her bekleme bir koşula
bağlıdır (Selenium'daki `WebDriverWait` karşılığı): pencere açılana, liste yenilenip sayfa durulana,
İşlem Takip'te "sona erdi" yazana kadar. Koşul sağlanınca hemen devam edilir; site yavaşsa
koşul sağlanana kadar (bir üst sınıra kadar) beklenir. Hiçbir bekleme programı çökertmez; süre
dolarsa bir sonraki güvenli adıma geçilir ve durum günlüğe yazılır.

**Testler** (Luca'ya bağlanmaz; `testler/sahte_luca.py` Luca'yı taklit eden küçük bir sitedir):

```
python -m unittest discover -s testler        # birim, dayanıklılık ve arayüz testleri
python testler/uctan_uca.py                    # programın tamamı, sahte Luca üzerinde
```

## Notlar

- Bot Luca arayüzünü kullanır; Luca ekranlarında değişiklik olursa buton/menü adlarının güncellenmesi gerekebilir
  (hepsi `lucabot/sabitler.py` içindedir).
- Aynı anda Luca'ya başka yerden girmeyin, oturum düşebilir.
- **Programı OneDrive klasöründe tutmayın.** OneDrive indirilen dosyaları ve tarayıcı profilini
  eşitlerken kilitliyor, Chrome indirme sırasında çökebiliyor. `C:\luca-bot` gibi bir yer uygundur.
  Tarayıcı profili zaten otomatik olarak OneDrive dışına (`%LOCALAPPDATA%\luca-bot`) alınır.
- Excel'den Luca'ya yükleme ve yapay zeka ile muhasebe kaydı sonraki adımlarda eklenecek.
