# Yeni müşavir kurulumu (her müşavire ayrı kurulum)

Her müşavir **kendi Render hizmetini** ve **kendi verisini** alır. Sizinle ortak veri yoktur; bir müşterinin sorunu ötekini etkilemez.
Aylık maliyet müşavir başına ~7 $ (Render Starter, 512 MB, 1 GB kalıcı disk).

## 1. Hazırlık (müşavirden alınacaklar)
- Ofis adı, unvan (örn. "Serbest Muhasebeci Mali Müşavir"), web sitesi (varsa), bildirim e-postası.
- Kendi Render hesabı (kartı kendi girer; ödeme onun adınadır) ve GitHub hesabı.

## 2. Kurulum (≈15 dk)
1. Müşavir GitHub'da bu depoyu **fork** eder (ya da siz onu depoya "collaborator" yapmadan, kopyasını vererek).
2. Render → **New → Blueprint** → fork'u seçin. `render.yaml` plan, disk ve temel ayarları kurar.
3. Render → servis → **Environment** bölümünde şu değişkenleri ekleyin:

| Değişken | Örnek | Ne işe yarar |
|---|---|---|
| `OFIS_AD` | `Başak Müşavirlik` | Giriş ekranı, fatura altı ve onay metninde ofis adı (**bunu vermek şart**: verilmezse eski varsayılanlar gelir) |
| `OFIS_UNVAN` | `Serbest Muhasebeci Mali Müşavir` | Ad yanındaki unvan (boş bırakılırsa gösterilmez) |
| `OFIS_WEB` | `basakmusavirlik.com` | Alt bilgi bağlantısı (boş bırakılırsa gösterilmez) |
| `OFIS_EPOSTA` | `info@basakmusavirlik.com` | Talep bildirimleri bu adrese gider, e-posta alanlarında varsayılan olur |
| `TAKIP_LINK` | `https://…` | Ana ekranda "Muhasebe ücreti takibi" kutusu; boşsa kutu görünmez |
| `TANITIM_VIDEO` / `TANITIM_POSTER` | `https://…/video.mp4` | Giriş ekranında tanıtım videosu; boşsa düğme görünmez |

   Diğer ayarlar (e-posta gönderimi, GitHub yedeği) için `KURULUM-SUNUCU.md` dosyasına bakın.
4. Kayıt sonrası adres açılır. İlk açılışta müşavir **kendi ofis şifresini** belirler; mükellefleri kendisi ekler.
5. İsterse alan adı bağlar (Render → Custom Domains).

## 3. Müşavire söylenecekler
- Veri ve şifreler **onun sunucusunda** şifreli saklanır; siz erişemezsiniz. Düzenli "Şifreli yedeği indir" almasını söyleyin.
- Mükelleflerine **kendi aydınlatma/KVKK metnini** vermesi gerekir (portaldaki metin genel bir örnektir).
- GİB/SGK ekranları değişirse sürüm güncellemesi gerekir: fork'unda "Sync fork" yapması yeterli (veri etkilenmez).

## 4. Ticari/hukuki not
Satış, devir ve destek şartlarını yazılı yapın; GİB/SGK kullanım şartlarını ve meslek mevzuatını (3568) kendi hukuk danışmanınızla netleştirin.
Pilot aşamada ücretsiz ya da düşük bedelle, "olduğu gibi" şartıyla verin.
