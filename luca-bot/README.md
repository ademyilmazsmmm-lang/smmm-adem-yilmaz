# Luca Toplu e-Fatura İndirme Botu

Luca'da her firma için tek tek yaptığınız **Akıllı Entegrasyon Noktası → e-Arşiv Alış Faturaları → GİB'den Getir → Seçilenleri İndir** işlemini
tüm firmalar için sırayla otomatik yapar. İndirilen dosyaları ve fatura listelerini bilgisayarınızda firma bazında klasörlere kaydeder.

**Şifreniz hiçbir yerde saklanmaz.** Bot tarayıcıyı açar, Luca'ya girişi **siz elle** yaparsınız, sonrasındaki 50 firmalık tekrar eden işi bot devralır.

## Kurulum (tek seferlik)

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

## Çalıştırma (çift tıklayarak)

| Dosya | Ne yapar |
| --- | --- |
| `kurulum.bat` | Tek seferlik kurulum |
| `firmalari-listele.bat` | Luca'daki firma adlarını listeler (test için doğru adı öğrenmek üzere) |
| `calistir.bat` | Tarih aralığını sorar, faturaları çeker. Firma adı sorulduğunda boş bırakırsanız tüm firmalar işlenir |
| `karsilastirmali-calistir.bat` | **Her firmada iki ekranı da çalıştırır** ve raporda karşılaştırır |
| `interaktif-earsiv.bat` | İnteraktif Vergi Dairesi ekranından e-Arşiv faturalarını sorgular (GİB Servis ile, 2 kez) |
| `bagimsiz-tarayici-ile-calistir.bat` | Chrome ve Edge çöküyorsa: Playwright Chromium ile çalışır (güvenlik yazılımlarının kancası dışında kalır) |
| `edge-ile-calistir.bat` | Chrome indirme sırasında çöküyorsa Edge ile çalıştırır |
| `gece-calistir.bat` | Tüm firmalar için çalışır, iş bitince tarayıcıyı kendisi kapatır (gece bırakıp gitmek için) |

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
  2026-09-18/
    AKIN COBAN/
      e-arsiv-alis/
        liste.csv              → ekrandaki fatura listesi
        belgeler_....zip       → Seçilenleri İndir çıktısı
        liste_....xls          → Luca'nın Excel çıktısı (iptal/itiraz sorgusundan sonraki hâli)
        iptal-itiraz.csv       → sadece iptal/itiraz edilmiş faturalar (varsa)
    rapor.xlsx                 → TOPLU RAPOR: Özet, Firma Durumu, İndirilen Faturalar, Dosyalar, Hatalar
    rapor.csv                  → aynı raporun CSV hâli
    ozet.csv                   → tüm firmaların durumu; her firmadan sonra güncellenir
    kalan-firmalar.txt         → henüz işlenmemiş firmalar (kaldığı yerden devam için)
    calisma.log                → zaman damgalı çalışma kaydı
    hatalar/                   → hata olursa ekran görüntüsü ve sayfa kaydı (Hatalar sayfasından tıklanır)
```

Bir ekranda hata olursa bot durmaz; hatayı rapora yazıp sıradaki ekrana/firmaya geçer.
`hatalar/` klasöründeki ekran görüntüsünü bana gönderirseniz o adımı düzeltirim.

## Toplu rapor (`rapor.xlsx`)

Günün klasöründe tutulur ve **her firmadan sonra güncellenir**; aynı gün farklı ekranlarla
çalıştırdıkça aynı rapor büyür. E-postaya da bu dosya eklenir. Sayfaları:

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
| Fark / Eksik-Fazla Faturalar | İnteraktif V.D. − e-Arşiv Alış; eksik/fazla faturalar ünvanın ilk kelimesi + fatura numarasının son 5 hanesi + tutarla |
| İptal/İtiraz, Tevkifatlı Alış, İnmeyen | adetler (tevkifat yalnızca alış ekranlarından, KDV2 için) |
| Alış/Satış Matrah ve KDV | iptal/itiraz hariç toplamlar; aynı faturaları gösteren ekranlarda (ör. TÜRMOB Alış ↔ e-Fatura Alış) en yüksek olan alınır |

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
| `eposta.py` | Özet e-postası (Outlook / SMTP) |
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
python -m unittest discover -s testler        # birim ve dayanıklılık testleri
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
