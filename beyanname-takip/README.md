# Beyanname Takip (Dijital Stajyer içinde)

KDV, MUHSGK, geçici vergi, KDV 2, poşet, konaklama ve yıllık (Kurumlar/Gelir) beyannamelerin **son günlerini** izler. Luca'dan (GİB Beyanname Takip
ekranı) mükellef listesini ve verilen beyannameleri okur, karşılaştırır ve **verilmemiş olanları e-postayla bildirir**. GİB'e doğrudan bağlanmaz.

## Kullanım
Dijital Stajyer'i açın → **Beyanname Takip** sekmesi:
1. **Gerekli paketleri kur** (yalnızca ilk kez, eski kurulumlarda; fastapi + uvicorn).
2. **Ayar dosyasını oluştur / aç** → `ayarlar.env`: web şifresi, Luca hesapları (üye no, kullanıcı, parola, doğrulama anahtarı), e-posta (Resend).
   Ayrıntı için `ayarlar.ornek.env` içindeki açıklamalara bakın. **Bu dosya şifre içerir, kimseyle paylaşmayın.**
3. **Başlat ve aç** → program arka planda çalışır (pencere açmaz) ve tarayıcıda `http://127.0.0.1:8765` adresinde açılır.
   Sayfadaki **Sistem** sekmesinden Luca'dan veri çekilir, uyarı önizlemesi görülür, e-posta özeti gönderilir.
4. **Kapat** → programı durdurur.

Luca bağlantısı için Dijital Stajyer'in **kendi lucabot paketi** kullanılır (`luca-bot/lucabot`); ayrıca kurulum gerekmez.
Program yalnızca bu bilgisayardan erişilebilir (`127.0.0.1`). Veriler ve günlük bu klasörde (`veri/`, `program.log`) durur.

## Geliştirme
* Başlatıcı: `baslat.py` (elle de çalıştırılabilir: `python baslat.py`). Uygulama: `app/` (FastAPI).
* Testler: `python -m pytest testler` (bu klasörde). `LUCABOT_YOLU=../luca-bot` verilirse Luca köprüsünün lucabot ile uyumu da sınanır.
* Arayüz sekmesi: `luca-bot/beyanname_takip_sekmesi.py` (testler: `luca-bot/testler/test_beyanname_takip.py`).
* Kapatma: başlatıcı her açılışta yerel bir anahtar üretip `kontrol.json`'a yazar; sekme programa bu anahtarla "kapan" der (süreç numarası öldürülmez).
