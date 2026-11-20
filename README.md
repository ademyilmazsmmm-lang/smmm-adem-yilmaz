# SMMM Adem Yılmaz — smmmyilmaz.com deposunun haritası

Bu depo iki işi bir arada taşıyor: **web sitesi** (smmmyilmaz.com, GitHub Pages) ve sitenin etrafındaki **küçük programlar ve otomatik görevler**. Bu dosya "ne nerede, ne işe yarıyor" sorusunun cevabıdır. Sayfaların (`*.html`) hiçbiri taşınmadı, silinmedi ya da değiştirilmedi; yalnızca betikler ve kurulum notu klasörlere alındı (aşağıda "Depo düzeni").

> **Önemli kural:** Site derlenmeden, dosyalar olduğu gibi yayınlanır: bir dosyanın yolu onun adresidir. Örneğin `kurulus.html` dosyasının adresi `smmmyilmaz.com/kurulus.html` olur. Bir HTML dosyasını taşırsanız ya da adını değiştirirseniz adresi değişir; Google sıralaması ve paylaşılmış bağlantılar bozulur. Bu yüzden sayfalar kök klasörde duruyor.

## Bir bakışta

| Ne | Nerede | Ne işe yarar |
|---|---|---|
| Site sayfaları | kök klasör (`*.html`) | 121 gerçek sayfa + 63 yönlendirme sayfası |
| Otomatik görevler | `.github/workflows/` | 7 otomatik iş: 6'sı zamanlı, 1'i `index.html` değişince (aşağıda) |
| Python betikleri | `scripts/` | Workflow'ların çalıştırdığı 7 betik |
| Fatura Portalı | `fatura-portal/` | GİB e-Arşiv'e bağlanıp fatura kesen Node.js uygulaması |
| Program dosyaları | `programlar/` | Kurulum dosyaları, tanıtım görselleri ve videoları (≈23 MB) |
| Hatırlatma sistemi | `hatirlatma*` (kökte), `scripts/hatirlatici.py`, `docs/hatirlatma-kurulum.md` | Telefon/bilgisayardan hatırlatma sayfası ve mail gönderimi |
| Yayın ayarları | `render.yaml`, `render-ucretsiz.yaml`, `CNAME` | Fatura Portalı'nın Render ayarı; alan adı |
| Arama motoru dosyaları | `sitemap.xml`, `robots.txt`, `seo_report.csv` | `sitemap.xml` ve `seo_report.csv` otomatik üretilir, elle düzenlemeyin |

## Otomatik görevler (GitHub Actions)

| Workflow | Ne zaman | Çalıştırdığı betik | Ne yapar |
|---|---|---|---|
| `sitemap.yml` | Her gece 03:00 | `scripts/sitemap_generator.py` | `sitemap.xml` dosyasını yeniden üretir |
| `seo-audit.yml` | Her gece 03:15 | `scripts/seo_audit.py` | Sayfaları denetler, `seo_report.csv` yazar |
| `sync-contact.yml` | `index.html` değişince | `scripts/sync_contact.py` | Ana sayfadaki iletişim bilgisini diğer sayfalara yayar |
| `update-doviz-kuru.yml` | Hafta içi 17:30 (TR) | `scripts/update_doviz_kuru.py` | TCMB kurlarını `index.html`'e yazar |
| `update-kira-orani.yml` | Her ayın 1–7'si | `scripts/update_kira_orani.py` | Kira artış oranını TCMB'den çekip `index.html`'e yazar |
| `hatirlatici.yml` | Her 10 dakika | `scripts/hatirlatici.py`, `scripts/takvim_senkron.py` | Zamanı gelen hatırlatmayı mail atar, Google Takvim'e işler |
| `hatirlatma-yedek.yml` | Ayın 1'i ve 16'sı | `scripts/hatirlatici.py --yedek` | Hatırlatma ve yapılacaklar yedeğini mail eki olarak yollar |

Bu görevler depoya kendileri commit atar (`Auto-update sitemap`, `Döviz ve altın kurunu güncelle` gibi). Geçmişte gördüğünüz bu commitler normaldir. Betiklerin yolu workflow dosyalarında yazılıdır (`python scripts/...`); bir betiği taşırsanız ilgili `.yml` dosyası da güncellenmelidir.

## Programlar

**Fatura Portalı** (`fatura-portal/`) — GİB e-Arşiv Portal'a bağlanıp fatura kesen uygulama (Node 18+). Kendi `README.md`, kurulum notları ve `Dockerfile` dosyası var. Render üzerinde `render.yaml` (ücretli, kalıcı disk) veya `render-ucretsiz.yaml` (ücretsiz) ile yayınlanır. Kullanıcı verisi `data/` klasöründe şifreli tutulur ve git'e girmez.

**Program dosyaları** (`programlar/`) — sitede indirilen kurulum dosyaları (`MusavirOtomasyon_Kurulum.exe`, `DijitalStajyer-Kurulum-1.0.0.zip`) ve tanıtım görselleri/videoları. `programlar.html`, `dijital-stajyer.html`, `musavir-otomasyon.html`, `e-defter-goruntuleyici.html` ve `fatura-portal/public/index.html` bu klasöre bağlanır; adlarını değiştirirseniz bu sayfalardaki bağlantılar kırılır.

**Hatırlatma sistemi** — `hatirlatma.html` sayfası (telefona uygulama gibi eklenebilir: `hatirlatma-manifest.json`, `hatirlatma-ikon*.png`), tatil listesi `hatirlatma-tatiller.json`, şifreli kasa dosyası `hatirlatma-kasa.json` ve mail betiği `scripts/hatirlatici.py`. Asıl hatırlatma verisi bu depoda değil, gizli bir depoda (`hatirlatma`) durur. Kurulum: `docs/hatirlatma-kurulum.md`.

**`arsiv/index.html`** — "Mükellef Portalı — Giriş" adresi; ziyaretçiyi `portal.smmmyilmaz.com` adresine yönlendirir.

## Site sayfaları (kategorilere göre)

Kök klasördeki 184 HTML dosyasının 121 tanesi gerçek sayfa, 63 tanesi yönlendirmedir. Aşağıdaki başlıklar sayfa dosyalarından otomatik okunmuştur; dosya adı ile başlığın uyuşmadığı yerler aşağıda "Gözden geçirilecekler" bölümünün 1. maddesinde listelidir.

<details>
<summary><b>Ana sayfalar</b> (4)</summary>

Sitenin kendisi: ana sayfa, iletişim, hata sayfası, gizlilik.

- `index.html` — SMMM Adem Yılmaz
- `iletisim.html` — İletişim
- `404.html` — Sayfa Bulunamadı (404)
- `gizlilik-politikasi.html` — Gizlilik Politikası

</details>

<details>
<summary><b>Programlar (tanıtım ve çalışan sayfalar)</b> (6)</summary>

Programların tanıtım sayfaları. `hatirlatma` ve `fatura` doğrudan çalışan araçlardır.

- `programlar.html` — Programlar
- `dijital-stajyer.html` — Dijital Stajyer
- `musavir-otomasyon.html` — Müşavir Otomasyon Sistemi — Tahakkuk Gönderimi
- `e-defter-goruntuleyici.html` — E-Defter Görüntüleyici — Yevmiye, Kebir ve Berat Görüntüleme
- `fatura.html` — Fatura Hazırla
- `hatirlatma.html` — Hatırlatma

</details>

<details>
<summary><b>Hizmet bölgeleri</b> (6)</summary>

`il.html` bölge merkezidir. 5 ilçenin kendi sayfası var; diğer 43 ilçe/mahalle adresi yönlendirmedir (aşağıda).

- `il.html` — Türkiye Geneli Online Mali Müşavir
- `atasehir-mali-musavir.html` — Ataşehir Mali Müşavir
- `cekmekoy-mali-musavir.html` — Çekmeköy Mali Müşavir
- `kadikoy-mali-musavir.html` — Kadıköy Mali Müşavir
- `sancaktepe-mali-musavir.html` — Sancaktepe Mali Müşavir
- `uskudar-mali-musavir.html` — Üsküdar Mali Müşavir

</details>

<details>
<summary><b>Sektör ve meslek sayfaları</b> (38)</summary>

Sektöre özel muhasebe rehberleri. `sektorlere-ozel-muhasebe.html` bunların listesidir.

- `sektorlere-ozel-muhasebe.html` — Sektöre Özel Muhasebe Rehberleri
- `bakkal-muhasebesi.html` — Bakkal Muhasebesi ve Açılışı
- `catering-toplu-yemek-muhasebesi.html` — Catering ve Toplu Yemek Muhasebesi
- `cicekci-muhasebesi.html` — Çiçekçi Muhasebesi ve Açılışı
- `eczane-muhasebesi.html` — Eczane Muhasebesi ve Açılışı
- `elektronik-beyaz-esya-muhasebesi.html` — Beyaz Eşya Mağazası Muhasebesi
- `emlak-danismanligi-muhasebesi.html` — Emlak Danışmanlığı Muhasebesi
- `fotografcilik-muhasebesi.html` — Fotoğrafçılık Stüdyosu Muhasebesi
- `guzellik-salonu-muhasebesi.html` — Güzellik Salonu ve SPA Muhasebesi
- `insaat-muteahhitlik-muhasebesi.html` — İnşaat ve Müteahhitlik Muhasebesi
- `kirtasiye-muhasebesi.html` — Kırtasiye Mağazası Muhasebesi
- `kuafor-muhasebesi.html` — Kuaför ve Berber Muhasebesi
- `mobilya-muhasebesi.html` — Mobilya Mağazası Muhasebesi ve Açılışı
- `motor-kurye-muhasebesi.html` — Motor Kurye Muhasebesi ve Bağ-Kur
- `nakliye-lojistik-muhasebesi.html` — Nakliye ve Lojistik Firması Muhasebesi
- `oto-tamir-servisi-muhasebesi.html` — Oto Tamir Servisi Muhasebesi
- `oto-yedek-parca-muhasebesi.html` — Oto Yedek Parça Mağazası Muhasebesi
- `pazaryeri-muhasebesi.html` — Trendyol ve Hepsiburada Muhasebesi
- `petshop-veteriner-muhasebesi.html` — Pet Shop ve Veteriner Kliniği Muhasebesi
- `reklam-ajansi-muhasebesi.html` — Reklam ve Dijital Ajans Muhasebesi
- `restoran-kafe-muhasebesi.html` — Restoran ve Kafe Muhasebesi
- `sanatci-manken-oyuncu-muhasebesi.html` — Manken, Şarkıcı ve Oyuncular için Mükellefiyet
- `spor-salonu-muhasebesi.html` — Spor Salonu Muhasebesi ve Açılışı
- `tekstil-konfeksiyon-muhasebesi.html` — Tekstil ve Konfeksiyon Muhasebesi
- `temizlik-sirketi-muhasebesi.html` — Temizlik Şirketi Muhasebesi
- `toptanci-muhasebesi.html` — Toptancı Muhasebesi ve Açılışı
- `zuccaciye-ev-esyasi-muhasebesi.html` — Züccaciye ve Ev Eşyası Muhasebesi
- `diyetisyen.html` — Özel Sağlık Hizmet Birimi Ruhsatı
- `fitness.html` — Sporcu ve Antrenörler için Mükellefiyet
- `kuyum.html` — Kuyumculukta Nakit İşlemler Hakkında Duyuru
- `taksi.html` — Taksiciler için Vergi Rehberi 2026
- `hijyen.html` — Önemli Duyuru – Karekod ve Hijyen Belgesi Zorunluluğu
- `itfaiye-raporu.html` — Konaklama Tesisleri İtfaiye Raporu Duyurusu
- `kafe-restoran-karekod-rehberi.html` — Kafe ve Restoranlarda Karekod Uygulaması: 2 Farklı Zorunluluk
- `airbnb.html` — Airbnb Kısa Dönem Kiralama Vergisi 2026
- `mikro-ihracat.html` — Etsy ve Amazon için Mikro İhracat
- `dijital-profesyoneller.html` — Dijital Profesyonellere Mali Müşavirlik
- `apartman-kapici-istihdam.html` — Apartman Kapıcısı İstihdam ve Kolay İşverenlik Rehberi

</details>

<details>
<summary><b>Hesaplama araçları</b> (11)</summary>

Tarayıcıda çalışan hesap makineleri.

- `hesaplama.html` — Mali Müşavir Hesaplama Araçları 2026
- `hizli-hesaplamalar.html` — Damga Vergisi ve Stopaj Hesaplama
- `vergi-hesaplama.html` — Gelir Vergisi ve KDV Hesaplama
- `muhasebe-hesaplama.html` — Amortisman ve Reeskont Hesaplama
- `maas-hesaplama.html` — Brüt Net Maaş Hesaplama 2026
- `kidem-ihbar-tazminati-hesaplama.html` — Kıdem ve İhbar Tazminatı Hesaplama 2026
- `kurumlar-vergisi-hesaplama.html` — Kurumlar Vergisi Hesaplama 2026
- `tecil-hesaplama.html` — Tecil ve Taksitlendirme Ödeme Planı
- `ticari-temerrut-faizi-hesaplama.html` — Ticari Temerrüt Faizi Hesaplama
- `oto-galeri-kdv-hesaplama.html` — 2. El Araç KDV Hesaplama
- `binek-arac-satin-alma-kiralama-hesaplama.html` — Binek Araç: Satın Alma mı Kiralama mı?

</details>

<details>
<summary><b>Şirket kuruluşu ve girişimci</b> (11)</summary>

Şahıs/limited/anonim/kooperatif kuruluşu ve genç girişimci konuları.

- `kurulus.html` — 2026 Şahıs Şirketi Kurulum Rehberi
- `limited-sirket-kurulus.html` — Limited Şirket Kuruluşu
- `anonim-sirket-kurulus.html` — Anonim Şirket Kuruluşu
- `kooperatif.html` — Kooperatif Kuruluşu Rehberi
- `hangi-sirket-turu-uygun.html` — Hangi Şirket Türü Size Daha Uygun? Şahıs, Limited, Anonim
- `sahis-mi-limited-mi.html` — Şahıs Şirketi mi Limited Şirket mi?
- `vergiacilis.html` — Yeni Mükellef Rehberi: Şirket Açılışı
- `basit-usulden-gercek-usule-gecis.html` — Basit Usulden Gerçek Usule Geçiş
- `genc.html` — Şahıs Şirketi ve Genç Girişimci Teşviki
- `genc-girisimci-istisnasi.html` — Genç Girişimci Kazanç İstisnası 2026
- `genc-girisimci-destegi-2025.html` — 2025 Genç Girişimci Desteği

</details>

<details>
<summary><b>Oto galeri ve yetki belgeleri</b> (5)</summary>

Galericilik, müteahhitlik ve araç kiralama belgeleri.

- `galeri.html` — Galeri Yetki Belgesi Başvuru Süreci
- `galericilik-belgesi.html` — Galericilik Belgesi Nasıl Alınır?
- `galeri-yetki-belgesi-ozel-matrahli-arac-satisi.html` — Oto Galeri Yetki Belgesi ve Özel Matrah
- `yapi-muteahhitligi-yetki-belgesi.html` — Yapı Müteahhitliği Yetki Belgesi Nasıl Alınır? 2026
- `arac-kiralama-yonetmeligi-2027.html` — Araç Kiralama Yönetmeliği 2027

</details>

<details>
<summary><b>E-ticaret ve ihracat</b> (7)</summary>

Pazaryeri, e-ticaret ve ihracat istisnaları.

- `eticaret.html` — E-Ticaret ve Pazaryeri Muhasebesi
- `eticaret1.html` — Trendyol ve Pazaryeri E-Ticaret Muhasebesi
- `ihrac-kayitli-satislar-rehberi.html` — İhraç Kayıtlı Satışlarda Vergi Uygulamaları / KDV, Tecil-Terkin, Fatura
- `hizmet-ihraci.html` — Yurt Dışı Hizmet Geliri Vergi Avantajı
- `hizmet-ihracati-istisnasi.html` — Yurt Dışı Hizmet İhracatı Vergi İstisnası
- `rehber.html` — Hizmet İhracatında %100 Kazanç İndirimi
- `yazilim-ihracatinda-vergi-istisnalari.html` — Yazılım İhracatında Vergi İstisnaları

</details>

<details>
<summary><b>SGK, emeklilik ve işçilik</b> (9)</summary>

Emeklilik, sigortalılık, asgari ücret, tatil ücretleri.

- `emeklilik.html` — Ne Zaman Emekli Olurum? SSK ve Bağ-Kur
- `eyt-erken-emeklilik.html` — EYT ve Erken Emeklilik Danışmanlığı
- `sgk-bagkur-emeklilik.html` — SGK ve Bağ-Kur Emeklilik Planlaması
- `sskbagkur.html` — Şirket Ortaklarında Sigortalılık Statüsü
- `ssk-10-gun-siniri.html` — SSK 10 Gün Sınırı ve SGK / İstihdamda Sigorta Esasları
- `asgari-ucret-agi-2025.html` — Asgari Ücret ve AGİ Rehberi
- `resmi-tatil-ucretleri.html` — Resmi Tatil Günleri ve Tatil Çalışma Ücretleri
- `utts-uets-vergi-sgk-gss.html` — UTTS, UETS, Vergi ve SGK Yükümlülükleri
- `gv20b.html` — GVK Mükerrer 20/B ve Bağ-Kur Yükümlülüğü

</details>

<details>
<summary><b>Vergi, beyan ve mevzuat rehberleri</b> (24)</summary>

Beyan, had, KDV, gider ve diğer vergi konuları. `rehberler.html` hepsinin dizinidir.

- `rehberler.html` — Tüm Rehberler ve Konu İndeksi
- `e-fatura-rehberi.html` — E-Fatura ve E-Arşiv Rehberi: Zorunluluk, Limitler, Geçiş Süreleri
- `gmsi.html` — GMSİ Rehberi 2026: Kira Geliri Beyanı
- `gmsi2025.html` — Mart 2027 Gelir Vergisi Beyan Rehberi
- `2025gmsi.html` — Konut Kira Gelirleri İstisna Uygulaması (2026)
- `kiragmsi.html` — 2026 Yılı Gelir Vergisi Dilimleri ve Hadler
- `2025-kira-geliri-beyan-rehberi.html` — 2026 Kira Geliri Beyan Rehberi
- `2025-enflasyon-duzeltmesi.html` — 2025 Enflasyon Düzeltmesi Rehberi
- `enflasyon-muhasebesi.html` — Enflasyon Muhasebesi 2025
- `amortisman-enflasyon.html` — Amortisman Nedir, Nasıl Hesaplanır?
- `2025-vergi-takvimi.html` — 2025 Vergi Takvimi ve Önemli Tarihler
- `2026-had.html` — 2026 Defter Tutma Hadleri
- `2026-hadler.html` — VUK 177-179-180 Hadleri
- `2025-pratik-bilgi.html` — Pratik Bilgiler - Vergi Uygulamaları
- `2025-pratik-bilgiler.html` — Pratik Bilgiler Konu Başlıkları İndeksi
- `2025-pratik-bilgiler-tablolar.html` — 2025 Pratik Bilgiler
- `kdv-iade-rehberi.html` — KDV İade Rehberi
- `kdv-oranlari-uygulama.html` — KDV Oranları ve Uygulamaları Rehberi
- `konut-kdv-oranlari.html` — Konut Teslimlerinde KDV Oranları 2025
- `kat-karsiligi-daire-satisi-5-yil-kurali.html` — Kat Karşılığı Alınan Dairenin Satışı: İktisap Tarihi ve 5 Yıl Kuralı
- `gider.html` — Hangi Harcamalar Gider Yazılır?
- `gider-pusulasi.html` — Gider Pusulası Nedir?
- `yapilandirma.html` — Vergi Borçları Yapılandırma Rehberi
- `vergi-tur-kodlari.html` — Vergi Türü Kodları Açıklaması

</details>

## Yönlendirme sayfaları (silmeyin)

63 küçük HTML dosyası eski adreslerden asıl sayfaya yönlendirir (`noindex` + `canonical`). Önceden Google'a girmiş ya da paylaşılmış eski bağlantılar bu sayede çalışmaya devam eder. Bunlar dağınıklık gibi görünür ama silinirse o adresler 404 verir.

| Yönlendirme hedefi | Adet | Dosyalar |
|---|---|---|
| `/il.html` | 39 | `adalar-mali-musavir.html`, `adem-yavuz-mahallesi-mali-musavir.html` ve 37 dosya daha |
| `/` | 10 | `kurumsal-defter-tutma.html`, `muhasebe-uzmani-umraniye.html` ve 8 dosya daha |
| `/e-fatura-rehberi.html` | 2 | `2025-e-fatura-e-arsiv-zorunlulugu.html`, `efatura.html` |
| `/2025-pratik-bilgiler-tablolar.html` | 1 | `2025-pratik-bilgilerr.html` |
| `/gv20b.html` | 1 | `GV20B.html` |
| `/pazaryeri-muhasebesi.html` | 1 | `e-ticaret-muhasebesi.html` |
| `/kadikoy-mali-musavir.html` | 1 | `kadıköy-mali-musavir.html` |
| `/kooperatif.html` | 1 | `kooperatif-kurulusu.html` |
| `/galeri-yetki-belgesi-ozel-matrahli-arac-satisi.html` | 1 | `oto-galeri-yetki-belgesi.html` |
| `/sgk-bagkur-emeklilik.html` | 1 | `sgk-emeklilik-rehberi.html` |
| `/kurulus.html` | 1 | `sirket-kurulus-hizmetleri.html` |
| `/2025-vergi-takvimi.html` | 1 | `vergi-takvimi-2025.html` |
| `/yazilim-ihracatinda-vergi-istisnalari.html` | 1 | `yazilim-arge-istisna.html` |
| `/cekmekoy-mali-musavir.html` | 1 | `çekmeköy-mali-musavir.html` |
| `/uskudar-mali-musavir.html` | 1 | `üsküdar-mali-musavir.html` |

<details>
<summary>Tüm yönlendirmelerin tam listesi</summary>

- `2025-e-fatura-e-arsiv-zorunlulugu.html` → `/e-fatura-rehberi.html`
- `2025-pratik-bilgilerr.html` → `/2025-pratik-bilgiler-tablolar.html`
- `GV20B.html` → `/gv20b.html`
- `adalar-mali-musavir.html` → `/il.html`
- `adem-yavuz-mahallesi-mali-musavir.html` → `/il.html`
- `atakent-mahallesi-mali-musavir.html` → `/il.html`
- `bahcelievler-mali-musavir.html` → `/il.html`
- `bayrampasa-mali-musavir.html` → `/il.html`
- `beykoz-mali-musavir.html` → `/il.html`
- `beyoglu-mali-musavir.html` → `/il.html`
- `catalca-mali-musavir.html` → `/il.html`
- `dudullu-osb-mahallesi-mali-musavir.html` → `/il.html`
- `e-ticaret-muhasebesi.html` → `/pazaryeri-muhasebesi.html`
- `efatura.html` → `/e-fatura-rehberi.html`
- `elmalikent-mahallesi-mali-musavir.html` → `/il.html`
- `esenevler-mahallesi-mali-musavir.html` → `/il.html`
- `esenkent-mahallesi-mali-musavir.html` → `/il.html`
- `esenler-mali-musavir.html` → `/il.html`
- `esenyurt-mali-musavir.html` → `/il.html`
- `fatih-mali-musavir.html` → `/il.html`
- `finanskent-mahallesi-mali-musavir.html` → `/il.html`
- `fsm-mahallesi-mali-musavir.html` → `/il.html`
- `gaziosmanpasa-mali-musavir.html` → `/il.html`
- `huzur-mahallesi-mali-musavir.html` → `/il.html`
- `ihlamurkuyu-mahallesi-mali-musavir.html` → `/il.html`
- `inkilap-mahallesi-mali-musavir.html` → `/il.html`
- `kadıköy-mali-musavir.html` → `/kadikoy-mali-musavir.html`
- `kartal-mali-musavir.html` → `/il.html`
- `kazim-karabekir-mahallesi-mali-musavir.html` → `/il.html`
- `kooperatif-kurulusu.html` → `/kooperatif.html`
- `kurumsal-defter-tutma.html` → `/`
- `madenler-mahallesi-mali-musavir.html` → `/il.html`
- `maltepe-mali-musavir.html` → `/il.html`
- `mehmet-akif-mahallesi-mali-musavir.html` → `/il.html`
- `muhasebe-uzmani-umraniye.html` → `/`
- `muhasebe-ve-vergi-hizmetleri.html` → `/`
- `musavirumraniye.html` → `/`
- `oto-galeri-yetki-belgesi.html` → `/galeri-yetki-belgesi-ozel-matrahli-arac-satisi.html`
- `parseller-mahallesi-mali-musavir.html` → `/il.html`
- `pendik-mali-musavir.html` → `/il.html`
- `saray-mahallesi-mali-musavir.html` → `/il.html`
- `sgk-emeklilik-rehberi.html` → `/sgk-bagkur-emeklilik.html`
- `sile-mali-musavir.html` → `/il.html`
- `silivri-mali-musavir.html` → `/il.html`
- `sirket-kurulus-hizmetleri.html` → `/kurulus.html`
- `site-mahallesi-mali-musavir.html` → `/il.html`
- `smmmumraniye.html` → `/`
- `sultanbeyli-mali-musavir.html` → `/il.html`
- `sultangazi-mali-musavir.html` → `/il.html`
- `tantavi-mahallesi-mali-musavir.html` → `/il.html`
- `tatlisu-mahallesi-mali-musavir.html` → `/il.html`
- `tuzla-mali-musavir.html` → `/il.html`
- `umraniye-mali-musavir.html` → `/`
- `umraniye-muhasebe.html` → `/`
- `umraniye-vergi-danismani.html` → `/`
- `umraniye.html` → `/`
- `vergi-danismanligi-umraniye.html` → `/`
- `vergi-takvimi-2025.html` → `/2025-vergi-takvimi.html`
- `yamanevler-mahallesi-mali-musavir.html` → `/il.html`
- `yazilim-arge-istisna.html` → `/yazilim-ihracatinda-vergi-istisnalari.html`
- `zeytinburnu-mali-musavir.html` → `/il.html`
- `çekmeköy-mali-musavir.html` → `/cekmekoy-mali-musavir.html`
- `üsküdar-mali-musavir.html` → `/uskudar-mali-musavir.html`

</details>

## Gözden geçirilecekler

Bunlar hata değil, ileride karar vermeniz gereken noktalar. Hiçbirine dokunulmadı.

**1. Adı içeriğiyle uyuşmayan sayfalar.** Dosya adı adrestir, bu yüzden adı değiştirmek istemezsiniz; ama bu liste bir şey ararken işe yarar:

| Dosya | Gerçekte ne |
|---|---|
| `kiragmsi.html` | 2026 gelir vergisi dilimleri ve hadler |
| `gmsi2025.html` | Mart 2027 gelir vergisi beyan rehberi |
| `2025gmsi.html` | Konut kira gelirleri istisnası (2026) |
| `2025-kira-geliri-beyan-rehberi.html` | 2026 kira geliri beyan rehberi |
| `rehber.html` | Hizmet ihracatında %100 kazanç indirimi |
| `diyetisyen.html` | Özel sağlık hizmet birimi ruhsatı |
| `gv20b.html` | GVK mükerrer 20/B ve Bağ-Kur yükümlülüğü |
| `2025-pratik-bilgiler.html` | Pratik bilgiler konu indeksi |
| `eticaret1.html` | Trendyol ve pazaryeri satıcıları için muhasebe (`eticaret.html` ile aynı konunun ikinci sayfası) |

**2. Kopya sayfalar: tek bir çift, o da zaten çözülmüş.** Gerçek sayfaların metinlerini karşılaştırdım. `2025-pratik-bilgi.html` sayfasının metninin %94'ü `2025-pratik-bilgiler.html` içinde de var. Ama `2025-pratik-bilgi.html` `canonical` etiketiyle diğerine bağlı ve sitemap'ten çıkarılmış; yani Google bunu zaten kopya sayıyor. İsterseniz ileride tam yönlendirmeye çevrilebilir. Geri kalan sayfa çiftleri belirgin kopya değil. Sektör sayfaları arasındaki %40 civarı benzerlik, hepsinin aynı şablondan üretilmesinden kaynaklanıyor.

**3. Eski yıl adları.** `2025-...`, `2026-...` ile başlayan sayfa adları yıl değişince eskir (örn. içeriği 2026 olan `2025-kira-geliri-beyan-rehberi.html`). Adres sabit kalır, başlık güncellenir.

**4. Sitemap durumu: sorun yok.** Gerçek sayfaların hepsi `sitemap.xml` içinde. Tek istisnalar kasıtlı: `noindex` olan `404.html`, `fatura.html`, `hatirlatma.html` ve canonical'i başka sayfayı gösteren `2025-pratik-bilgi.html`. Bu kurallar `scripts/sitemap_generator.py` içindedir.

## Depo düzeni

Site adresleri bozulmasın diye sayfalara dokunulmadı; yalnızca sayfa olmayan dosyalar klasörlere alındı:

```
scripts/   seo_audit.py, sitemap_generator.py, sync_contact.py,
           update_doviz_kuru.py, update_kira_orani.py, hatirlatici.py, takvim_senkron.py
docs/      hatirlatma-kurulum.md
```

**Betikleri çalıştırırken** depo kökünde olun: `python scripts/sitemap_generator.py`. Betikler `index.html` ve diğer sayfaları bulunduğunuz klasörden arar; `scripts/` içine girip çalıştırırsanız sayfaları bulamaz. GitHub Actions zaten depo kökünden çalıştırır.

**Dikkat — `hatirlatici.py`:** Tatil listesini (`hatirlatma-tatiller.json`) kendi klasörünün bir üstünden, yani depo kökünden okur. Bu betiği başka bir klasöre taşırsanız o satırı (`TATIL_DOSYASI`) da güncelleyin. Güncellemezseniz hata vermez, sessizce tatil günlerini bilmez ve bayramda yanlış günde mail atar.

**Bilerek taşınmayanlar:**
- `render.yaml`: Render varsayılan olarak onu kökte arar (taşırsanız Render panelinde yolu da değiştirmeniz gerekir). `render-ucretsiz.yaml` ile birlikte kökte kaldı.
- `hatirlatma.html` ve onun okuduğu `hatirlatma-manifest.json`, `hatirlatma-ikon*.png`, `hatirlatma-kasa.json`, `hatirlatma-tatiller.json`: sayfa bunları kendi adresinden okur.
- `seo_report.csv`, `sitemap.xml`, `robots.txt`, `CNAME`: iş akışları ve arama motorları kökten okur.
- Tüm `*.html` sayfaları ve `programlar/`, `arsiv/`, `fatura-portal/`: adresleri değişmesin diye.

**Sayfaları klasörlere taşımak önerilmez.** Eski adreslerden yönlendirme, sitemap ve iç bağlantı güncellemesi gerekir; kazancı küçük, Google sıralamasını bozma riski büyüktür.
