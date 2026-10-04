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
5. Sonuç her firmadan sonra `cikti\kar-zarar.json`'a yazılır (Durdur/Ctrl+C'de o ana kadarkiler kalır).

## Kullanım

```
kar-zarar.bat
python kar_zarar.py --baslangic 01/07/2026 --bitis 31/08/2026 [--firma ADEM,AKIN] [--limit 5]
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
