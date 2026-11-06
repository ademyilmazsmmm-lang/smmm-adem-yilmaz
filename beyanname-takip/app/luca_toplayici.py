"""Luca'ya tarayıcıyla girip mükellef listesini ve verilmiş beyannameleri çeken toplayıcı.

DURUM: HENÜZ YAZILMADI (bilerek). Gerçek Luca ekranları bu geliştirme ortamından görülemiyor; ekran
okuma kodunu görmeden yazıp "çalışıyor" demek yanlış olurdu.

Yapılacak (gerçek Luca ekranı görüldükten sonra):
  * Giriş, doğrulama kodu (pyotp), ürün seçimi, firma listesi: Dijital Stajyer'in lucabot paketindeki
    giris.py ve musteri_listesi.py aynen kullanılır. Bu paket lisanslıdır ve bu depo herkese açıktır:
    lucabot klasörü BU DEPOYA KONMAZ; servis, lucabot'u içeren özel (private) bir depodan derlenir.
  * "Muhasebe > Beyannameler > GİB Beyanname Takip" ekranından satırlar okunur (firma, VKN, tür, dönem,
    durum). luca_beyanname.py şu an yalnızca KDV1 PDF'lerini indiriyor; satır okuma yeni yazılacak.
  * Tarayıcı ekransız (headless) çalışır; captcha çıkarsa ekran görüntüsü captcha.sor(png) ile iletilir.
  * Oturum profili DATA_DIR/profil altında kalıcı tutulur.
Bu arada TOPLAYICI=dosya ile, kendi bilgisayarınızdaki Dijital Stajyer çıktıları sunucuya yüklenerek
sistem eksiksiz çalıştırılabilir (README'ye bakın).
"""


class LucaToplayici:
    def __init__(self, veri_dizini):
        self.veri_dizini = veri_dizini

    def topla(self, bugun, captcha=None):
        raise NotImplementedError(
            "Luca toplayıcı henüz yazılmadı. TOPLAYICI=dosya kullanın ya da luca_toplayici.py'yi tamamlayın.")
