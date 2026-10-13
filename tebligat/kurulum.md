# Tebligat yardımcısı (Windows)

Bu program **yalnızca sizin bilgisayarınızda** çalışır. Tarayıcıyı açar; girişi ve doğrulama kodunu
**siz** yazarsınız. Program hiçbir yere tıklamaz, hiçbir alana yazmaz, hiçbir şey göndermez.
Şifre, oturum ve içerik hiçbir yere gitmez. Şu an yalnızca **keşif** modu var: ekranların yapısını
kaydeder, tebligat tarama bunlara bakılarak yazılacak.

## Kurulum (bir kere)
1. **Python:** Microsoft Store → "Python 3.12" → Al. (Zaten kuruluysa bu adımı atlayın.)
2. Zip dosyasına sağ tık → **Tümünü ayıkla** (masaüstüne).
3. `kur.bat` dosyasına çift tıklayın. Birkaç dakika sürer, internet gerekir.
   Windows "bilgisayarınızı korudu" derse: **Daha fazla bilgi → Yine de çalıştır**.

## Kullanım
1. `calistir.bat` dosyasına çift tıklayın. Tarayıcı açılır, siyah bir pencere de kalır.
2. Tarayıcıda **giriş yapın** (doğrulama kodunu siz yazın).
3. Şu ekranların her birine gelip siyah pencerede **Enter**'a basın:
   1. giriş sonrası ana ekran
   2. firma seçme / değiştirme ekranı
   3. bir firma seçiliyken tebligat listesi
   4. bir tebligat açılmışken
4. Bitince siyah pencerede `q` yazıp Enter'a basın.

## Çıktılar
`cikti` klasöründe her kayıt için bir `.txt` ve bir `.png` oluşur.

- `.txt`: rakamlar `#`, tablo ve liste içerikleri `xxxx` olarak gizlenir; kutulara yazılanlar (şifre dahil)
  ve bağlantılardaki sorgu parametreleri hiç kaydedilmez; art arda 3+ büyük harfli kelime `[AD]` olur.
  **Göndermeden önce açıp göz atın:** firma ya da kişi adı kalmışsa silin.
- `.png`: ekranın görüntüsüdür, **veriler görünür**. Göndermeden önce firma adı, vergi no ve tutarları karartın.

`cikti` klasörü git'e girmez (içinde kendi `.gitignore` dosyası var). Bu depo herkese açıktır;
çıktı dosyalarını depoya yüklemeyin.

## Sorun giderme
- "Chrome ya da Edge açılamadı": Chrome'u kurun ya da `calistir.bat --tarayici msedge` deneyin.
- "Python bulunamadı": Store'dan Python'u kurduktan sonra `kur.bat` dosyasını tekrar çalıştırın.
- Giriş ekranı açılmıyor ya da hata veriyor: ekranın görüntüsünü ve siyah penceredeki yazıyı gönderin.
