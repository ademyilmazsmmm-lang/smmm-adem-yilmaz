# luca-bot (fatura otomasyonu) ile birleştirme notları

Bu proje luca-bot'un `lucabot/` modüllerinin **kopyasını** kullanır (modül adları aynıdır). Birleştirirken:

## 1. Ortak `lucabot/` paketi — yalnız bir dosya değişti

`lucabot/musteri_listesi.py` (geriye dönük uyumlu; eski çağrılar aynen çalışır). Yama: `birlestirme/lucabot-musteri_listesi.patch`
(luca-bot'taki dosya bu projenin ilk kopyasıyla aynıysa `patch -p1 < ...` ya da dosyayı doğrudan kopyalayın).

Eklenenler:
- `SINIF_LISTESI_JS`, `_sinifi_sec()`: Müşteri Arama penceresinde **Sınıf** seçimi (gerçek seçenekler: `Tümü, 1.Sınıf, 2.Sınıf,
  İşletme Defteri, Serbest Meslek Defteri, Basit Usül`). Yıl/Sınıf `onchange=gonder()` ile formu yeniden yüklediği için
  seçim sayfa durulunca ve birkaç denemeyle yapılır.
- `FILTRE_UYGULA_JS`, `_filtreyi_dogrudan_uygula()`: **gerçek Luca'da asıl yol.** `YIL`/`SINIF` listelerinin `onchange`'i `gonder('yil')`
  çağırır ve sayfayı yeniden yükleyip Müşteri Arama penceresini kapatır; bu yüzden pencereyi açıp tek tek seçmek yerine iki değer
  JS ile ayarlanıp `gonder('yil')` bir kez çağrılır, sayfa yenilenene kadar beklenir. Müşteri Listesi ikinci açılışta yeni sekmede
  gelebildiği için filtre sonrası çerçevenin hâlâ görünür olduğu doğrulanır. Eski pencere yolu yedek olarak durur.
- `yili_filtrele(page, yil, log=None, sinif="")` ve `listeyi_oku(page, yil, tani_klasoru, log=None, bekleme_ms=30000, sinif="")`:
  `sinif` verilmezse eskisi gibi yalnız Yıl süzülür. `sinif` metin ya da alternatif metinler listesi olabilir.

Diğer tüm `lucabot/*.py` dosyaları orijinal kopyayla aynıdır.

## 2. Bu projeye özgü (luca-bot'a taşınacaklar)

| Yol | Ne |
|---|---|
| `karzarar/` | `defterbeyan.py` (Defter Beyan), `luca_mizan.py` (Luca Mizan Excel'i, varsayılan), `luca_hesap_plani.py` (Luca Hesap Planı, yedek), `hesaplama.py` (iki aşama), `rapor.py` (Excel) |
| `kar_zarar.py` | Komut satırı girişi (`--sadece-luca`, `--sadece-defterbeyan`, `--firma`, `--limit`) |
| `kar-zarar.bat`, `tek-firma.bat` | Windows başlatıcıları |
| `testler/sahte_kz.py`, `testler/test_*.py`, `testler/uctan_uca.py` | Sahte portallarla testler |
| `testler/sahte_luca.py` | luca-bot'un sahte Luca'sı; Müşteri Listesi gerçek Luca gibi sunucuda çizilir, Sınıf filtresi (`gonder('yil')` ile yeniden yükleme) eklendi; test verileri anonimleştirildi |

## 3. Dikkat edilecekler

- **Luca ekranları (öğrendiklerimiz):** Luca menüsü JS ile çizilir; menü çerçevesinde `menuItems` ve `aktar(link)` vardır
  (`karzarar/luca_hesap_plani.py: menuden_dogrudan_ac`). Hesap Planı Listesi 150'şerlik sayfalardır (`sayfaNo`, `sonraki()`);
  Hesap Arama penceresi alanları `kebirDeger`, `calismayanHesap`, `tarih1`, `tarih2`, Ara = `gonder('', 'search')`.
- **Mizan indirme:** `karzarar/luca_mizan.py: indir()` 'Rapor' düğmesine basıp Playwright `download` olayını yakalar (aynı sayfa, iframe ya da yeni pencere); fatura otomasyonunuzdaki indirme koduyla değiştirilebilir. Form alanları etikete göre (etiketin yanındaki hücre) doldurulur.
- **Ayarlar (`ayarlar.json`)**, hepsi isteğe bağlı: `luca_kaynagi` (`mizan` / `hesap-plani`), `musteri_sinifi` (liste; Defter Beyan'a sorulacak sınıflar),
  `luca_sinifi` (hesap planı sınıfı, varsayılan `1.Sınıf`), `vkn_listesi` (VKN tamamlamak için Excel), `defterbeyan_kullanici`,
  `defterbeyan_sifre`. Ortak ayarlar (uye_no, kullanici_adi, parola ...) luca-bot'unkilerle aynıdır.
- **Çıktı klasörü** `cikti/` (`KARZARAR_CIKTI` ortam değişkeniyle değişir); günlük `cikti/<tarih>/calisma.log` ve `tani/`.
- **Aynı tarayıcı profili:** Luca girişi `lucabot.giris`/`lucabot.tarayici` ile yapılır; iki proje aynı profil klasörünü
  aynı anda kullanmamalı (Chrome tek profile tek süreç açar).
- Birleştirdikten sonra: `python -m unittest discover -s testler -p test_birim.py` ve (Linux) `xvfb-run -a python testler/uctan_uca.py`.
