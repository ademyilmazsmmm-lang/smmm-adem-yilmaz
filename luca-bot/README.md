# Luca Toplu e-Fatura İndirme Botu

Luca'da her firma için tek tek yaptığınız **Akıllı Entegrasyon Noktası → e-Arşiv Alış Faturaları → GİB'den Getir → Seçilenleri İndir** işlemini
tüm firmalar için sırayla otomatik yapar. İndirilen dosyaları ve fatura listelerini bilgisayarınızda firma bazında klasörlere kaydeder.

**Şifreniz hiçbir yerde saklanmaz.** Bot tarayıcıyı açar, Luca'ya girişi **siz elle** yaparsınız, sonrasındaki 50 firmalık tekrar eden işi bot devralır.

## Kurulum (tek seferlik)

1. **Python kurun:** https://www.python.org/downloads/ — kurulum ekranındaki
   **"Add python.exe to PATH"** kutusunu mutlaka işaretleyin, sonra "Install Now".
2. **`kurulum.bat`** dosyasına çift tıklayın. Gerekli her şeyi kendisi kurar.

Tarayıcı olarak bilgisayarınızdaki **Google Chrome** kullanılır (yoksa Edge denenir),
ayrıca tarayıcı indirmeye gerek yoktur.

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
| `gece-calistir.bat` | Tüm firmalar için çalışır, iş bitince tarayıcıyı kendisi kapatır (gece bırakıp gitmek için) |

## Ayarlar (`ayarlar.json`)

| Ayar | Anlamı |
| --- | --- |
| `sorgu_azami_dakika` | Bir GİB sorgusu için beklenecek en uzun süre (varsayılan 30) |
| `durgunluk_dakika` | İşlem Takip penceresi bu kadar süre hiç ilerlemezse sorgu takılmış sayılır (varsayılan 3) |
| `tekrar_deneme` | İndirilemeyen fatura kalırsa sorgunun kaç kez tekrarlanacağı (varsayılan 3) |
| `ardisik_hata_siniri` | Üst üste kaç firma hata verirse çalışma durdurulur (varsayılan 5) |
| `atlanacak_firmalar` | İşlenmeyecek firma adları |

## Tarih aralığı (30 gün sınırı)

GİB sorgusu tek seferde en fazla 30 gün kabul ettiği için, siz elle nasıl ay ay sorguluyorsanız
(01/08/2026-31/08/2026 → 31/08/2026-30/09/2026 → ...) bot da aynı şekilde otomatik bölüyor.
Siz sadece geniş aralığı veriyorsunuz, parçalamayı bot yapıyor:

```
python luca_bot.py --baslangic 01/08/2026 --bitis 31/12/2026
```

Bu komut her firma için 6 ayrı GİB sorgusu çalıştırır, hepsi bittikten sonra listenin tamamını indirir.
Tarih vermezseniz içinde bulunulan ay sorgulanır.

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
```

İlk 3 firmayla denemek için `--limit 3` ekleyebilirsiniz.

## Çalışırken ne oluyor

1. Bot Chromium tarayıcısını açar ve Luca giriş sayfasına gider.
2. Siz giriş yaparsınız, firma ekranı gelince komut istemine dönüp **ENTER**'a basarsınız.
3. Bot sağ üstteki listeden firmaları sırayla seçer; her firma için menüden ilgili ekrana gider,
   **GİB'den Getir** der (tarih aralığını 30 günlük parçalar hâlinde sırayla sorgular),
   gelen faturaların hepsini seçer, **Seçilenleri İndir** ve **Excel** dosyalarını indirir.
4. Biten her firma için ekrana durum yazar; sonunda özet çıkarır.

## Dosyalar nereye iniyor

```
indirilenler/
  2026-09-18/
    AKIN COBAN/
      e-arsiv-alis/
        liste.csv              → ekrandaki fatura listesi
        belgeler_....zip       → Seçilenleri İndir çıktısı
        liste_....xls          → Luca'nın Excel çıktısı
    ozet.csv                   → tüm firmaların durumu; her firmadan sonra güncellenir
    kalan-firmalar.txt         → henüz işlenmemiş firmalar (kaldığı yerden devam için)
    calisma.log                → zaman damgalı çalışma kaydı
    hatalar/                   → hata olursa ekran görüntüsü ve sayfa kaydı
```

Bir firmada hata olursa bot durmaz, o firmayı `ozet.csv`'ye "hata" olarak yazıp sıradakine geçer.
`hatalar/` klasöründeki ekran görüntüsünü bana gönderirseniz o adımı düzeltirim.

## Sık karşılaşılan durumlar

| Durum | Ne yapmalı |
| --- | --- |
| `cdn.playwright.dev ... timed out` | Tarayıcı indirmeye çalışıyor; gerekmiyor. Güncel sürümde bot bilgisayardaki Chrome'u kullanır. Chrome yoksa google.com/chrome adresinden kurun. |
| `Python bulunamadı` | Yeni Python Install Manager kurulmuş ama Python sürümü inmemiş demektir. Komut istemine `py install` yazın, sonra `kurulum.bat`'ı tekrar çalıştırın. |
| `Firma listesi (select) bulunamadi` | Giriş tamamlanmadan ENTER'a basılmış olabilir; firma ekranı açıkken tekrar deneyin. |
| `Ogeye ulasilamadi` | Menü adı o firmada farklı olabilir (İşletme Defteri / Serbest Meslek Defteri). `hatalar/` içindeki ekran görüntüsünü paylaşın. |
| `Seçilenleri İndir butonu bulunamadi` | O firmada hiç fatura gelmemiş olabilir; `ozet.csv`'de "fatura yok" görünür. |
| Tarayıcı her seferinde giriş istiyor | `.tarayici-profili` klasörü oturumu hatırlar, silmeyin. |
| `UYARI: tarih kutulari bulunamadi` | GİB tarih penceresi tanınmamış; `hatalar/` ekran görüntüsünü paylaşın, alan adlarını düzeltirim. |

## Notlar

- Bot Luca arayüzünü kullanır; Luca ekranlarında değişiklik olursa buton/menü adlarının güncellenmesi gerekebilir.
- Aynı anda Luca'ya başka yerden girmeyin, oturum düşebilir.
- Tevkifatlı fatura uyarısı, Excel'den Luca'ya yükleme ve yapay zeka ile muhasebe kaydı sonraki adımlarda eklenecek.
