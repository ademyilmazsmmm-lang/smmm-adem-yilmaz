# Luca Toplu e-Fatura İndirme Botu

Luca'da her firma için tek tek yaptığınız **Akıllı Entegrasyon Noktası → e-Arşiv Alış Faturaları → GİB'den Getir → Seçilenleri İndir** işlemini
tüm firmalar için sırayla otomatik yapar. İndirilen dosyaları ve fatura listelerini bilgisayarınızda firma bazında klasörlere kaydeder.

**Giriş bilgileri yalnızca bu bilgisayardaki `ayarlar.json`'da tutulur** (başka yere gönderilmez); girilirse
bot Luca'ya kendisi girer, girilmezse tarayıcıyı açar ve girişi **siz elle** yaparsınız. Sonrasındaki tekrar eden işi bot devralır.

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

## Arayüz (en kolay yol): `luca-arayuz.bat`

Komut satırı kullanmadan, pencereden çalıştırmak için `luca-arayuz.bat`'a çift tıklayın
(arkada siyah pencere kalmaz: arayüz konsolsuz `pythonw` ile açılır; `.bat` bunu bulamazsa arayüz
kendisini konsolsuz yeniden başlatır. Hiçbiri olmazsa küçültülmüş bir siyah pencere kalır, onu kapatmayın).

1. **Luca Girişi › Değiştir**: Üye No, Kullanıcı Adı, Parola (ve varsa iki aşamalı giriş
   anahtarı) bir kez girilir, `ayarlar.json`'a kaydedilir. Program Luca'ya kendisi girer.
2. **Firma Listesi**: **Şablon İndir** doğru sütunlarla bir Excel indirir (daha önce işlenen
   firmalar hazır yazılı gelir); doldurup **Liste Yükle** ile seçin. Ekran sütunlarında
   **✓ = sorgulanır, X = sorgulanmaz** (boş = sorgulanır; eski X'li listeler aynen çalışır).
   **KDV Devri ve Ekran Seçimi** listeyi tablo olarak açar: her firmanın Devreden KDV'sini yazar,
   hangi ekranın sorgulanacağını kutucuklarla işaretlersiniz; alttan firma eklenir, ✕ ile çıkarılır.
   **Kaydet** Excel'e yazar (önce `firmalar.yedek-...xlsx` yedeği alınır; diğer sütun ve sayfalara
   dokunulmaz). Liste hiç seçilmemişse bu buton yeni bir `firmalar.xlsx` oluşturur.
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
   - **KDV Ödemesi Çıkabilir**: Satış KDV − Alış KDV − Devreden KDV > 0 olan firmalar. Devreden
     KDV'yi `firmalar.xlsx`'e **"Devreden KDV"** adlı bir sütun açıp elle yazın; boşsa 0 sayılır.
     Tahmindir (diğer beyan kalemleri girmez).

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
| `sure_ayrintisi` | Günlüğe `[süre]` satırlarını yaz (varsayılan açık); kapalıyken de `sure-raporu.txt` oluşur |
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

**Zaman nereye gidiyor (`[süre]` satırları)**: bot her adımı kendi saatiyle ölçer ve günlüğe yazar:

```
    [süre] Aralık 01/09/2026 - 07/09/2026 19,8 sn: açık pencereleri kapatma 6,1 sn (2×) · tarih kutularını arama 4,0 sn · ...
    [süre] e-SMM Alış ekranı 2 dk 56 sn - en çok: ...
    [süre] Firma toplamı 21 dk 4 sn - en çok: ...
```

- Her GİB tarih aralığından (ve iptal/itiraz aralığından) sonra o aralığın adımları,
  her ekranın ve her firmanın sonunda en çok zaman alan adımlar yazılır.
- `GİB yanıtı bekleme` Luca/GİB'in sorguyu yapma süresidir; `(ilk 1 sn)` yazanı, sorgu
  erken bitse de bitişin kabul edilmediği ilk saniyedir. Diğerleri botun ekranda pencere
  açma, buton arama, kapatma gibi işleridir; asıl kısaltılabilecek yer bunlardır.
- Bütün çalışmanın dökümü günlük klasördeki `sure-raporu.txt` dosyasına yazılır (her firmadan
  sonra güncellenir; arayüzde **Süre Raporu** düğmesi açar). İç içe adımlarda aynı saniye iki kez
  sayılmaz.
- Arayüzde ilerleme çubuğunun altındaki **"Şu an: … — 14 sn"** satırı botun o an ne yaptığını ve
  o adımda ne zamandır beklediğini gösterir; 30 sn değişmezse turuncu, 90 sn'de kırmızı olur.
- Satırlar kalabalık gelirse `ayarlar.json`'a `"sure_ayrintisi": false` yazın (`sure-raporu.txt`
  yine oluşur).

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
    sure-raporu.txt            → adım süreleri: zaman nereye gitti (her firmadan sonra güncellenir)
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
| Fark / Eksik-Fazla Faturalar | İnteraktif V.D. − e-Arşiv Alış; eksik/fazla faturalar ünvanın ilk kelimesi + fatura numarasının son 5 hanesi + tutarla |
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
| `gostergeler.py` | Arayüzün alt kutuları (tevkifat KDV, SMM, interaktif farkı, KDV ödemesi); arayüzün kendisi `luca_arayuz.py` |
| `firma_tablosu.py` | `firmalar.xlsx` şablonu ve arayüzdeki Firma / Ekran Seçimi tablosunun okunup yazılması |
| `eposta.py` | Özet e-postası (Outlook / SMTP) |
| `beyanname.py` | KDV1 beyanname PDF'lerinden devreden KDV'yi okuma ve firmayla eşleştirme |
| `sure_olcer.py` | Adım süreleri: `[süre]` satırları ve `sure-raporu.txt` |
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
