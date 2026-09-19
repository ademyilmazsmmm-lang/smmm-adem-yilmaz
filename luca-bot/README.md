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
| `interaktif-earsiv.bat` | İnteraktif Vergi Dairesi ekranından e-Arşiv faturalarını sorgular (GİB Servis ile, 2 kez) |
| `gece-calistir.bat` | Tüm firmalar için çalışır, iş bitince tarayıcıyı kendisi kapatır (gece bırakıp gitmek için) |

## Ayarlar (`ayarlar.json`)

| Ayar | Anlamı |
| --- | --- |
| `sorgu_azami_dakika` | Bir GİB sorgusu için beklenecek en uzun süre (varsayılan 30) |
| `durgunluk_dakika` | İşlem Takip penceresi bu kadar süre hiç ilerlemezse sorgu takılmış sayılır (varsayılan 3) |
| `iptal_itiraz_sorgula` | Faturalar indikten sonra GİB'den iptal/itiraz durumunu da sorgula (varsayılan açık) |
| `tekrar_deneme` | İndirilemeyen fatura kalırsa sorgunun kaç kez tekrarlanacağı (varsayılan 3) |
| `ardisik_hata_siniri` | Üst üste kaç firma hata verirse çalışma durdurulur (varsayılan 5) |
| `atlanacak_firmalar` | İşlenmeyecek firma adları (kapanmış firmalar). Luca adı kısaltarak gösterdiği için adın baş kısmını yazmanız yeterli |

Kapanmış firmaların hazır listesi `kapali-firmalar.md` dosyasındadır; `ayarlar.ornek.json` içine işlenmiştir.
Ayrıca firmanın Luca'daki çalışma dönemi istediğiniz tarihlerin dışındaysa bot sorguyu hiç başlatmaz,
özete `dönem dışı` yazar.

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
python luca_bot.py --belge-tipi e-arsiv-interaktif
```

`e-arsiv-interaktif`, **İşletme Defteri → E-Arşiv Faturaları Sorgulama** ekranını kullanır.
Diğerlerinden farkı: Akıllı Entegrasyon Noktası'ndan değil doğrudan modül menüsünden açılır,
belge indirme butonu yoktur. Akış: tarih aralığı → **İnteraktif V.D'sinden E-Arşiv Faturalarını Sorgula**
→ **GİB Servis ile Sorgula** (iki kez) → tümünü seç → **GİB'den İptal/İtiraz Sorgula** → **Excel**.

İlk 3 firmayla denemek için `--limit 3` ekleyebilirsiniz.

## Çalışırken ne oluyor

1. Bot Chromium tarayıcısını açar ve Luca giriş sayfasına gider.
2. Siz giriş yaparsınız, firma ekranı gelince komut istemine dönüp **ENTER**'a basarsınız.
3. Bot sağ üstteki listeden firmaları sırayla seçer; her firma için menüden ilgili ekrana gider,
   **GİB'den Getir** der (tarih aralığını 30 günlük parçalar hâlinde sırayla sorgular),
   gelen faturaların hepsini seçer, **Seçilenleri İndir** der, ardından **GİB'den İptal/İtiraz Sorgula**
   ile iptal/itiraz durumunu çeker ve en son güncel listeyi **Excel** olarak indirir.
4. Biten her firma için ekrana durum yazar; sonunda özet çıkarır.

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
    rapor.xlsx                 → TOPLU RAPOR: her firma tek satır, aksiyon gerekenler en üstte
    rapor.csv                  → aynı raporun CSV hâli
    ozet.csv                   → tüm firmaların durumu; her firmadan sonra güncellenir
    kalan-firmalar.txt         → henüz işlenmemiş firmalar (kaldığı yerden devam için)
    calisma.log                → zaman damgalı çalışma kaydı
    hatalar/                   → hata olursa ekran görüntüsü ve sayfa kaydı
```

Bir firmada hata olursa bot durmaz, o firmayı `ozet.csv`'ye "hata" olarak yazıp sıradakine geçer.
`hatalar/` klasöründeki ekran görüntüsünü bana gönderirseniz o adımı düzeltirim.

## Toplu rapor (`rapor.xlsx`)

Günün klasöründe her firma için **tek satır** tutar; aynı gün farklı belge tipleriyle
çalıştırdıkça aynı satır güncellenir. Aksiyon gereken firmalar en üste alınır ve renklendirilir.

| Sütun | Anlamı |
| --- | --- |
| Firma / Dönem / Durum | firma, Luca çalışma dönemi, en kötü durum (hata > kaynaktan inmedi > dönem dışı > fatura yok > tamam) |
| Aksiyon | ne yapmanız gerektiği; boşsa o firmada iş yok |
| e-Arşiv Alış | Akıllı Entegrasyon Noktası ekranından gelen fatura adedi |
| İnteraktif V.D. | İnteraktif Vergi Dairesi ekranından gelen fatura adedi |
| Fark | İnteraktif − Akıllı Entegrasyon. **Artı ise Luca'ya eksik fatura inmiş demektir** |
| Eksik Faturalar | eksik kalanların listesi: ünvanın ilk kelimesi + fatura numarasının son 5 hanesi (`TURKCELL 56671, TRUGO 09988`) — firmaya dönüp bakmadan karar verirsiniz |
| İptal/İtiraz | GİB'de iptal/itiraz edilmiş fatura adedi |
| Tevkifatlı | tevkifatlı fatura adedi. İki kaynaktan bakılır: ekrandaki belge türü sütunu **ve** inen ZIP içindeki XML (`WithholdingTaxTotal`, vergi kodu 9015). XML bozuk inerse ekran, ekranda sütun yoksa XML yakalar |
| İnmeyen | GİB'de vardı ama kaynak sunucudan inmedi |
| İnen Dosya | o firma için kaydedilen dosya sayısı |

Aksiyon sütununda çıkabilecekler: `HATA - tekrar calistir`, `KAYNAKTAN INMEDI - tekrar sorgula`,
`EKSIK - interaktifte N fatura fazla`, `IPTAL/ITIRAZ - N fatura`, `TEVKIFAT - N fatura, KDV2 kontrol`.

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
