# Hatırlatma paneli kurulumu (PythonAnywhere)

Panel, mevcut web uygulamanın yanına `/h/GİZLİ-ANAHTAR/` adresine eklenir. Şifre sorulmaz; adresi bilmeyen kimse
sayfaya ya da veriye ulaşamaz. Adres telefonda ve bilgisayarda yer imi / ana ekran simgesi olarak kalır.

## 1. Kodu PythonAnywhere'e al
Bash konsolunda:

    cd ~
    git clone https://github.com/ademyilmazsmmm-lang/smmm-adem-yilmaz.git hatirlatma_kaynak
    cd hatirlatma_kaynak/hatirlatma_paneli
    cp hatirlatma_ayar.ornek.py hatirlatma_ayar.py
    python3 -c "import secrets; print(secrets.token_urlsafe(32))"

Çıkan uzun değeri `hatirlatma_ayar.py` içindeki `ANAHTAR = "..."` satırına yapıştır (nano ile düzenleyebilirsin).
Güncelleme için sonradan: `cd ~/hatirlatma_kaynak && git pull`, sonra Web sekmesinde **Reload**.

## 2. Web uygulamasına bağla
Web sekmesi → **WSGI configuration file** bağlantısını aç. Dosyanın **en sonuna** şunları ekle
(KULLANICI yerine PythonAnywhere kullanıcı adını yaz; mevcut satırlara dokunma):

    import sys
    sys.path.insert(0, '/home/KULLANICI/hatirlatma_kaynak/hatirlatma_paneli')
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
    from uygulama import app as _hatirlatma_app
    application = DispatcherMiddleware(application, {'/h': _hatirlatma_app})

Kaydet, Web sekmesinde **Reload**'a bas. Şu adres açılmalı:

    https://KULLANICI.pythonanywhere.com/h/ANAHTARIN/

Telefonda Safari'de aç → Paylaş → **Ana Ekrana Ekle**.

## 3. Mailler (GitHub)
Depoda Settings → Secrets and variables → Actions → şu secret'ları ekle:

| Secret | Değer |
|---|---|
| `PANEL_URL` | `https://KULLANICI.pythonanywhere.com/h/ANAHTARIN` (sonunda `/` yok) |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | Gmail adresin |
| `SMTP_PASS` | Gmail "uygulama şifresi" |
| `MAIL_TO` | mailin geleceği adres |

Actions → **Hatırlatma Maili** → Run workflow ile elle dene.

## Önemli
- Ücretsiz hesapta Web sekmesindeki **"Run until ... from today"** düğmesine düzenli bas. Basmazsan panel kapanır.
  Panel kapalıyken sabah mailinde "panele ulaşılamadı" uyarısı gelir.
- Anahtarı kimseyle paylaşma. Sızarsa `hatirlatma_ayar.py`'de değiştir, WSGI'yi Reload et ve `PANEL_URL` secret'ını güncelle.
- Veri `hatirlatma_paneli/hatirlatma.db` dosyasındadır, depoya girmez. Sayfanın altındaki "Yedek indir" bağlantısı metin yedeği verir.
