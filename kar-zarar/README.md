# Kâr / Zarar Tahmini

`luca-bot` otomasyonundan **tamamen ayrı, kendi kendine yeten bir proje**dir: kendi klasörü, kendi
`ayarlar.json`'u, kendi çıktıları (`cikti\`) var; luca-bot'a bağımlı değildir. Luca girişi, tarayıcı ve
firma seçimi için gereken modüller luca-bot'tan **kopyalanmış bir anlık görüntü**dür (`lucabot\`,
modül adları aynı) — ileride istenirse ikisi birleştirilir.

## Kurulum

Python kurulu olmalı. `ayarlar.ornek.json`'u `ayarlar.json` olarak kopyalayıp Luca `uye_no`,
`kullanici_adi`, `parola` (ve varsa `dogrulama_anahtari`) bilgilerini yazın; Defter Beyan için
`defterbeyan_kullanici` / `defterbeyan_sifre` isteğe bağlıdır. `kar-zarar.bat` paketleri kendisi kurar.

## Ne yapar

Verilen dönem için (örn. 01/07/2026 – 31/08/2026) her firmanın **satış/gelir, mal alışı, gider ve
kâr/zarar** tahminini çıkarır. Amaç, vergi çıkabilecek firmaları dönem kapanmadan görmek; asıl
inceleme sonra firmada yapılır.

| Firma türü | Kaynak | Ne okunur |
|---|---|---|
| İşletme defteri | **Defter Beyan** › Muhasebe Bilgileri › Hesap Özeti › Oluştur | Hasılat + diğer gelirler, Dönem İçinde Satın Alınan Emtia, Giderler + Amortisman, **Kâr − Zarar** |
| Genel muhasebe (bilanço) | **Luca** › Muhasebe › Hesap Planı İşlemleri › Hesap Planı Listesi › Filtre (Başlangıç/Bitiş Tarih) › Ara | Aşağıdaki hesaplama |

Luca hesap planı hesabı:
- **Gelir** = 6'lı hesaplar (alacak − borç)
- **Mal alışı** = 150–153 hesaplar (borç − alacak)
- **Gider** = 7'li hesaplar (borç − alacak)
- **Kâr** = Gelir − Mal alışı − Gider (eksi ise zarar)

Sınıf satırı (`6`, `7`) listede yoksa bir alt düzeyden (60, 61 … ya da 3 haneli ana hesaplar) toplanır.

### VKN'si Luca'dan bulunamayan firmalar

Müşteri Listesi'nden VKN/TC okunamayan firmalar Defter Beyan'a sorulamaz. Bunun için bir Excel
(ör. Luca'dan indirilen müşteri listesi) hazırlayıp `ayarlar.json > vkn_listesi` alanına yolunu yazın.
Excel'de `Kısa Adı` (ve/veya `Uzun Adı`/`Unvan`) ile `Vergi No` (ve/veya `TC Kimlik No`) sütunları
olmalı; `firma_listesi` Excel'i de bu sütunları taşıyorsa aynı şekilde kullanılır. Luca'dan bulunamayan
firmaların VKN'si buradan tamamlanır.

### Hangi firma nereden sorgulanır

**Liste her sorguda çekilmez:** Müşteri Listesi (sınıf süzmeli) ilk sorguda Luca'dan okunup `cikti\musteri-listeleri.json`'a kaydedilir; aynı yıl için sonraki sorgularda Luca'ya hiç gidilmeden bu kayıttan okunur. Yeniden çekmek için `--listeyi-yenile` (arayüzde "Firma listesini Luca'dan yeniden çek").

Luca Müşteri Listesi iki kez okunur (Yıl = dönemin yılı):
- **Sınıf = İşletme Defteri** (`musteri_sinifi`): bu firmaların VKN'si alınır, Defter Beyan'a sorulur.
- **Sınıf = 1.Sınıf** (`luca_sinifi`): Luca hesap planı **yalnız bu listedeki** firmalar için sorgulanır.
  2.Sınıf, Serbest Meslek (SMK), Basit Usul ve dönemi olmayan firmalar atlanır. `""` yazılırsa süzülmez.

Luca'da hesap planı denemesi için tek firma: `tek-firma.bat` ya da `python kar_zarar.py --sadece-luca --firma "FIRMA ADI"`
(Müşteri Listesi ve Defter Beyan atlanır, güvenlik kodu beklenmez; her adımdan sonra tanı dosyası kaydedilir).
Defter Beyan için tek firma: `tek-firma.bat` (Kaynak 2) ya da `python kar_zarar.py --sadece-defterbeyan --firma "FIRMA ADI"`
(VKN Luca Müşteri Listesi'nden alınır, Luca hesap planı atlanır; güvenlik kodunu siz yazarsınız). Hata olursa `cikti\<tarih>\tani\hesap-plani-*.png/html` kaydedilir.

## Akış

1. Luca'ya otomatik girilir, firma listesi alınır (`--firma`, `--limit`; isteğe bağlı
   `ayarlar.json > firma_listesi` Excel süzmesi ve `atlanacak_firmalar`).
2. Firmaların VKN'si/TC'si ve kapanış tarihleri Luca'nın **Yönetici › Müşteri İşlemleri › Müşteri
   Listesi** ekranından (Yıl = dönemin yılı) okunur; dönemden önce kapanmış firmalar atlanır.
3. **Defter Beyan** açılır; kullanıcı kodu/şifre `ayarlar.json`'daki `defterbeyan_kullanici` /
   `defterbeyan_sifre` ile yazılır (boşsa elle), **güvenlik kodunu siz yazıp GİRİŞ YAP'a basarsınız**
   (5 dakika beklenir). Her firma VKN ile aranıp seçilir; üst çubukta `İŞLETME` yazıyorsa Hesap Özeti
   okunur. Defter Beyan'da olmayan ya da işletme olmayan firmalar Luca'ya bırakılır.
4. Luca'da kalan firmalar için hesap planı okunur.
5. Sonuç her firmadan sonra `cikti\kar-zarar.xlsx` (kârdan zarara sıralı, renkli Excel raporu) ve `cikti\kar-zarar.json`'a yazılır (Durdur/Ctrl+C'de o ana kadarkiler kalır).

### Excel raporu sütunları

Defter Beyan firmalarında Mali Hesap Özeti'nin kalemleri ayrı sütundadır (özette yoksa/boşsa hücre boş kalır):
Hasılat, Diğer Gelir, Dönem Başı Emtia, Mal Alışı, Dönem Sonu Emtia, Giderler, Amortisman. Kâr/Zarar Defter Beyan'ın
kendi hesabıdır. Defter dönemi istenen dönemden önce bitmiş (dönem sonu) mükellefler **ATLANDI** olarak işaretlenir.

### Luca firmalarında tutarlar: Mizan (varsayılan) ya da Hesap Planı

`ayarlar.json > luca_kaynagi` (`mizan` / `hesap-plani`, komut satırında `--luca-kaynagi`). Mizan: Muhasebe › Raporlar › Genel Raporlar › Mizan
formu doldurulur (`tarih_ilk`/`tarih_son`, Bakiye Göster, Bakiyesiz Hesapları Gösterme, Rapor Türü = Excel Liste (xlsx); Hesap Tipi "Tümü" bırakılır),
**Rapor** ile inen Excel `cikti\<tarih>\mizan\` klasörüne kaydedilip okunur; Excel'deki "Tarih Aralığı" istenenle uyuşmazsa sonuç
kabul edilmez. Mizan alınamazsa o firma için Hesap Planı yöntemine dönülür. Excel raporunda Kaynak sütunu `Luca (Mizan)` /
`Luca (Hesap Planı)` olarak görünür. Hesaplama iki yöntemde de aynıdır.

## Kullanım

```
kar-zarar.bat
python kar_zarar.py --tarih 01/07/2026-31/08/2026 [--firma ADEM,AKIN] [--limit 5]
(--baslangic/--bitis ayrı ayrı da verilebilir). `.bat` dosyaları ve konsoldan tarihsiz çalıştırma **tarih aralığını sorar**, girilmeden devam etmez;
ayarlar.json'daki tarihler yalnızca otomatik/gece (`--bitince-kapat`) çalışmada kullanılır
```

Diğer seçenekler: `--tarayici chrome|edge|chromium`, `--profil-yerel`, `--chrome-gunlugu`, `--bitince-kapat`.

## Testler

Sahte Luca + sahte Defter Beyan ile (hepsi bu klasörde):

```
python -m unittest discover -s testler -p "test_birim.py"
xvfb-run -a python -m unittest testler.test_portal      (Linux; ekran gerekir)
xvfb-run -a python testler/uctan_uca.py                 (bastan sona)
```

## Henüz gerçek portalda denenmemiş / bilinmeyenler

- Defter Beyan'ın mükellef seçim kutusu (`select2` varsayıldı), tarih kutularının yazım biçimi ve
  "Hızlı Geçiş Yap" sonrası sayfa davranışı; sorun olursa log ve ekran görüntüsü gerekir.
- Luca Hesap Planı Listesi'nde Borç/Alacak sütunlarının seçilen tarih aralığına göre hesaplanıp
  hesaplanmadığı ve tabloda tüm hesapların bulunup bulunmadığı (ekran görüntüsü `tani\` klasörüne kaydedilir).
- Gerçek kişi firmalar için VKN yoksa TC kimlik no kullanılır.
- Bu bir **tahmin**dir: dönem sonu emtia, amortisman ve gelir/gider kayıtları işlenmemiş olabilir.
