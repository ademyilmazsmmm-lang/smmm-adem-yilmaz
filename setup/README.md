# Dijital Stajyer — kurulum paketi ve lisans

Müşavirlere verilecek `DijitalStajyer-Kurulum-<sürüm>.exe` buradan üretilir. (Yalnızca program sahibi içindir.)

## Gerekenler (paketi üretirken)
- Python 3.9+ ve **NSIS 3** (`makensis`): Linux'ta `apt install nsis`, Windows'ta nsis.sourceforge.io'dan.
- Lisans imzalama **özel anahtarı** (`lisans-ozel-anahtar.txt`) — repoda YOKTUR; güvenli yerde saklayın,
  kimseye vermeyin. Kaybolursa yeni lisans üretilemez; sızarsa herkes lisans üretebilir.

## Paketi üretme
```
python luca-bot/lisans_araci.py uret --anahtar lisans-ozel-anahtar.txt ^
       --sahip "Dijital Stajyer 2026 Kullanıcısı" --bitis 2026-12-31 --cikti lisans-2026-genel.json
python setup/derle.py --lisans lisans-2026-genel.json
```
Çıktı: `setup/cikti/DijitalStajyer-Kurulum-<sürüm>.exe` ve `.sha256`. Paket çalışma klasöründeki
(git'te izlenen + izlenmeyen ama `.gitignore`'da olmayan) dosyalardan kurulur; testler, `lisans_araci.py`,
`ayarlar.json`, indirilenler ve geliştirici dosyaları pakete girmez. Süresi dolmuş lisans paketlenmez.

## Müşteride kurulum ne yapar?
1. `%LOCALAPPDATA%\DijitalStajyer` altına kurar (yönetici hakkı gerekmez); `luca-bot\` ve `kar-zarar\` yan yana.
2. Python 3.9+ (tkinter'lı) yoksa python.org'dan **3.12.10**'u indirir, imzasını (Python Software Foundation)
   doğrular, kullanıcı klasörüne sessiz kurar.
3. `pip install -r requirements.txt` ve `playwright install chromium` (internet gerekir; ~150 MB).
4. Masaüstü + Başlat menüsü kısayolu, kaldırıcı (`Kaldir.exe`).
5. İlk açılışta Kurulum Sihirbazı Luca/Defter Beyan bilgilerini sorar. Eksik kalan bileşenleri sihirbaz tamamlar.

Yeniden kurulum/yükseltme: ayarlar, indirilenler ve raporlar korunur; `lisans.json` paketteki lisansla değişir.
Kaldırma: program dosyaları silinir, kullanıcı verisi (ayarlar.json, indirilenler, raporlar) bırakılır.
Sessiz kurulum: `DijitalStajyer-Kurulum-1.0.0.exe /S`.

## Lisans
- `lisans.json`: Ed25519 ile imzalı `{lisans_sahibi, baslangic, bitis}`; tarih elle değiştirilirse imza bozulur.
- Süre dolunca `luca_bot.py` çalışmaz, arayüz "Çalıştır"ı engeller ve yeni lisans dosyası yüklemeyi sorar
  (alttaki "Sürüm" yazısı → Hakkında → Evet). Bitime 30 gün kala açılışta uyarır.
- Bilgisayar saati geriye alınırsa (son açılış tarihinden önceye) lisans geçersiz sayılır.
- Kişiye özel lisans: `--sahip "Ad Soyad, SMMM"` ile ayrı dosya üretip müşteriye gönderin.
- **Sınırlar:** Python kaynak kodu açık olduğundan bu bir caydırıcıdır; kodu düzenleyen birini engellemez.
  Daha sıkı koruma için programı derlenmiş (PyInstaller/Nuitka) .exe'ye çevirmek ve .exe'yi kod imzalama
  sertifikasıyla imzalamak gerekir (imzasız .exe'de Windows SmartScreen "Bilinmeyen yayıncı" uyarısı gösterir).
