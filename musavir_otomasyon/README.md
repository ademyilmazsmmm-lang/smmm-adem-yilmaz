# Müşavir Otomasyon Sistemi — Tahakkuk Gönderim Modülü

PDF tahakkuk dosyalarının bulunduğu bir klasörü tarayıp, dosya isminden
mükellef adı / vergi türü / dönem bilgisini çıkaran, `firmalar.json`
rehberinden telefon numarasını eşleştiren ve WhatsApp Desktop üzerinden
otomatik gönderim yapan Flask uygulaması.

## Kurulum

```bash
cd musavir_otomasyon
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
python app.py
```

Tarayıcıda `http://127.0.0.1:5000` adresini açın.

## Firma Rehberi

`firmalar.json` dosyasını, tahakkuk dosya isimlerindeki firma kısa adını
anahtar (key) olacak şekilde düzenleyin:

```json
{
  "ŞAKİR LTD.": {"tam_ad": "ŞAKİR İNŞAAT LTD.ŞTİ", "telefon": "90532XXXXXXX"}
}
```

`telefon` alanı WhatsApp URL şemasıyla (`whatsapp://send?phone=...`) uyumlu
olacak şekilde ülke kodu dahil, başında `+`/boşluk olmadan girilmelidir
(örn: `905321234567`).

## Dosya Adı Formatı

```
ŞAKİR LTD._034252_7981552167_KDV1_45_01072026-31072026_THK_28.pdf
```

- İlk parça (`_` ile ilk bölüm) → `firmalar.json`'da aranan firma kısa adı.
- `KDV1` → KDV, `muhsgk` → STOPAJ / SGK, `geçici` → PEŞİN VERGİ (P.V.)
- Dosya adındaki `01072026-31072026` gibi tarih aralığı → dönem.

## Önemli: Windows + WhatsApp Desktop Gerekliliği

`/gonder` rotasındaki otomasyon adımları (`PowerShell Set-Clipboard`,
`pyautogui`, WhatsApp Desktop pencere odağı) yalnızca **Windows**
üzerinde, **WhatsApp Desktop** uygulaması kurulu ve o an ekranda aktif
haldeyken güvenilir şekilde çalışır. Uygulama Windows dışında çalıştırılırsa
`/gonder` isteği anlamlı bir hata mesajıyla reddedilir; dosya tarama ve
önizleme işlevleri (`/klasor_tara`) tüm platformlarda çalışır.

Gönderim sırasında bilgisayarı kullanmayın; `pyautogui` o an odaklanmış
pencereye tuş gönderir, bu yüzden WhatsApp penceresinin öne gelmesi ve
odakta kalması gerekir.
