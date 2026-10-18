#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Masraf Fişi OCR Scripti
========================
Bu script, çalıştırıldığı klasördeki ALT KLASÖRLERİ tarar. Her alt klasör
bir kişiyi/grubu temsil eder (örn. "Adem", "Mehmet") ve içinde PDF/görsel
(JPG/JPEG/PNG) fiş dosyaları bulunur. Her dosyada A4 kağıdına yapıştırılmış
1, 6, 8 veya farklı sayıda masraf fişi olabilir. Standart OCR kütüphaneleri
(pytesseract vb.) bu tür düzensiz, çok nesneli sayfa düzenlerini güvenilir
şekilde okuyamadığı için, görsel anlama yeteneği olan OpenAI'nin gpt-4o
(Vision) modeli kullanılır.

KLASÖR YAPISI ÖRNEĞİ:
    Yeni klasör (2)/
        fis_okuyucu.py
        Adem/
            fis1.jpg
            fis2.pdf
        Mehmet/
            fis1.png

Bu yapıyla script çalıştırıldığında:
    - "Adem" klasörü işlenir   -> "Adem/Adem.xlsx" oluşur
    - "Mehmet" klasörü işlenir -> "Mehmet/Mehmet.xlsx" oluşur

NOT: Eğer hiç alt klasör yoksa (eski kullanım), script bulunduğu klasördeki
dosyaları doğrudan işler ve "Masraf_Fisleri.xlsx" olarak kaydeder.

Gerekli Kütüphaneler (script çalıştırılmadan önce kurulmalıdır):
    pip install openai pdf2image pandas openpyxl pillow

NOT: pdf2image, sistemde "poppler" kurulu olmasını gerektirir.
    - Windows : https://github.com/oschwartz10612/poppler-windows/releases adresinden
                indirip PATH'e eklemeniz gerekir.
    - macOS   : brew install poppler
    - Linux   : sudo apt-get install poppler-utils

Kullanım:
    1) OpenAI API anahtarınızı ortam değişkeni olarak ayarlayın:
         Windows (PowerShell): $env:OPENAI_API_KEY="sk-..."
         macOS/Linux         : export OPENAI_API_KEY="sk-..."
    2) Yukarıdaki örnekteki gibi, her kişi için bir alt klasör oluşturup
       fişlerini o klasörlerin içine koyun.
    3) Scripti, bu alt klasörlerin bulunduğu ana klasörde çalıştırın:
         python fis_okuyucu.py
    4) İşlem bitince her alt klasörün içinde, klasör adıyla bir .xlsx
       dosyası oluşur.
"""

import os
import re
import csv
import json
import base64
import shutil
import tempfile
import traceback
from datetime import datetime

import pandas as pd

try:
    from openai import OpenAI
except ImportError:
    print("HATA: 'openai' kütüphanesi bulunamadı. Lütfen şu komutu çalıştırın:")
    print("    pip install openai")
    raise SystemExit(1)

try:
    from pdf2image import convert_from_path
except ImportError:
    print("HATA: 'pdf2image' kütüphanesi bulunamadı. Lütfen şu komutu çalıştırın:")
    print("    pip install pdf2image")
    raise SystemExit(1)

try:
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter
except ImportError:
    print("HATA: 'openpyxl' kütüphanesi bulunamadı. Lütfen şu komutu çalıştırın:")
    print("    pip install openpyxl")
    raise SystemExit(1)


# --------------------------------------------------------------------------
# AYARLAR
# --------------------------------------------------------------------------
TARANACAK_KLASOR = os.getcwd()                  # Scriptin çalıştığı klasör
DESTEKLENEN_GORSEL_UZANTILARI = (".jpg", ".jpeg", ".png")
DESTEKLENEN_PDF_UZANTISI = (".pdf",)
MODEL_ADI = "gpt-4o"
PDF_DPI = 300                 # PDF -> görsel çözünürlüğü (okuma doğruluğu için yüksek)
HEDEF_UZUN_KENAR = 3000       # Daha küçük görseller bu uzun kenara büyütülür
MAX_CIKTI_TOKEN = 8000        # Çok fişli sayfalarda JSON kesilmesin

# OpenAI istemcisini oluştur (API anahtarı OPENAI_API_KEY ortam değişkeninden okunur)
try:
    client = OpenAI()
except Exception as e:
    print(f"HATA: OpenAI istemcisi oluşturulamadı: {e}")
    print("Lütfen OPENAI_API_KEY ortam değişkenini ayarladığınızdan emin olun.")
    raise SystemExit(1)


# --------------------------------------------------------------------------
# YARDIMCI FONKSİYONLAR
# --------------------------------------------------------------------------

def klasordeki_dosyalari_bul(klasor_yolu):
    """Klasördeki desteklenen PDF ve görsel dosyalarını bulur."""
    bulunan_dosyalar = []
    try:
        for dosya_adi in sorted(os.listdir(klasor_yolu)):
            tam_yol = os.path.join(klasor_yolu, dosya_adi)
            if not os.path.isfile(tam_yol):
                continue
            uzanti = os.path.splitext(dosya_adi)[1].lower()
            if uzanti in DESTEKLENEN_GORSEL_UZANTILARI + DESTEKLENEN_PDF_UZANTISI:
                bulunan_dosyalar.append(tam_yol)
    except Exception as e:
        print(f"HATA: Klasör taranırken bir sorun oluştu: {e}")
    return bulunan_dosyalar


def pdf_yi_gorsellere_cevir(pdf_yolu, gecici_klasor):
    """
    PDF dosyasını sayfa sayfa PNG görsellerine çevirir ve geçici klasöre
    kaydeder. Oluşan PNG dosya yollarının listesini döndürür.
    """
    olusturulan_dosyalar = []
    try:
        os.makedirs(gecici_klasor, exist_ok=True)
        sayfalar = convert_from_path(pdf_yolu, dpi=PDF_DPI)
        dosya_kok_adi = os.path.splitext(os.path.basename(pdf_yolu))[0]
        for i, sayfa in enumerate(sayfalar, start=1):
            png_yolu = os.path.join(gecici_klasor, f"{dosya_kok_adi}_sayfa{i}.png")
            sayfa.save(png_yolu, "PNG")
            olusturulan_dosyalar.append(png_yolu)
    except Exception as e:
        print(f"HATA: '{pdf_yolu}' PDF'ten görsele çevrilirken sorun oluştu: {e}")
        traceback.print_exc()
    return olusturulan_dosyalar


def gorseli_base64_yap(gorsel_yolu):
    """Görseli okunabilirliği artırmak için büyütüp keskinleştirir ve
    JPEG olarak base64 string'ine çevirir. (Küçük rakamlar bu sayede
    daha doğru okunur: fiş no, vergi/TC no, tutarlar.)"""
    try:
        from PIL import Image, ImageFilter, ImageOps
        import io
        with Image.open(gorsel_yolu) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            uzun = max(img.size)
            if uzun < HEDEF_UZUN_KENAR:
                oran = HEDEF_UZUN_KENAR / uzun
                img = img.resize((int(img.width * oran), int(img.height * oran)),
                                 Image.LANCZOS)
            img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=120, threshold=3))
            tampon = io.BytesIO()
            img.save(tampon, "JPEG", quality=93)
            return base64.b64encode(tampon.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"HATA: '{gorsel_yolu}' base64'e çevrilirken sorun oluştu: {e}")
        return None


def gorsel_mime_tipi(gorsel_yolu):
    """Dosya uzantısına göre uygun MIME tipini döndürür."""
    # gorseli_base64_yap her zaman JPEG üretir
    return "image/jpeg"


def gpt4o_ile_fisleri_cikar(gorsel_yolu, tek_fis=False):
    """
    Bir A4 sayfa görselini gpt-4o Vision modeline gönderir ve sayfa
    üzerindeki TÜM fişleri JSON listesi olarak geri döndürür.
    """
    base64_veri = gorseli_base64_yap(gorsel_yolu)
    if base64_veri is None:
        return []

    mime_tipi = gorsel_mime_tipi(gorsel_yolu)

    sistem_talimati = (
        "Sen bir muhasebe asistanısın. Sana A4 kağıdına yapıştırılmış, "
        "1'den fazla olabilecek sayıda masraf fişi/fatura içeren bir görsel "
        "verilecek. Görseldeki HER BİR fişi ayrı ayrı tespit et ve her biri "
        "için aşağıdaki alanları çıkar. Sadece geçerli bir JSON dizisi "
        "(array) döndür, başka hiçbir açıklama, markdown işareti veya metin "
        "ekleme.\n\n"
        "Her fiş nesnesi şu alanları içermeli:\n"
        "- \"tarih\": Fiş üzerindeki tarih, GG.AA.YYYY formatında (gün.ay.yıl) "
        "döndürülmeli. ÇOK ÖNEMLİ: Türk fişlerinde tarih SOLDAN SAĞA "
        "GÜN-AY-YIL sırasıyla yazılır (GG-AA-YYYY veya GG/AA/YYYY veya "
        "GG.AA.YYYY). Fişte yazılı sırayı DEĞİŞTİRME, sadece ayraçları "
        "noktaya çevir. Somut örnek: fişte \"09-05-2026\" yazıyorsa bu "
        "\"9 Mayıs 2026\" demektir (gün=09, ay=05), çıktıda \"09.05.2026\" "
        "yaz — KESİNLİKLE \"05.09.2026\" yazma (bu, gün ile ayı ters "
        "çevirmek olur ve YANLIŞTIR). Fişteki ilk iki haneyi GÜN, ikinci "
        "iki haneyi AY olarak al, bunları birbirine karıştırıp ters çevirme. "
        "Bu, o fişin KENDİ \"FİŞ NO\" satırının solunda yazılıdır. "
        "Aynı sayfadaki diğer fişlerin tarihiyle karıştırma; her fişin "
        "tarihi farklı olabilir, asla varsayılan olarak aynı tarihi tüm "
        "fişlere yazma.\n"
        "- \"fis_no\": Fiş/fatura numarası. ÇOK ÖNEMLİ: Bu değer SADECE "
        "\"FİŞ NO:\" etiketinin YANINDA, tarih/saat ile aynı satırda bulunur "
        "(örn. \"04-05-2026   FİŞ NO: 0027\"). Aşağıdaki İKİ ŞEYLE KARIŞTIRMA:\n"
        "  (a) ARAÇ PLAKASI: 2 rakam + 2-3 harf + 2-4 rakamdan oluşan bir kod "
        "(örn. \"34LCC311\") — bu plakadır, aşağıdaki \"plaka\" alanına yazılır.\n"
        "  (b) MASKELENMİŞ KART NUMARASI: \"**** **** **** 5272\" gibi "
        "yıldızlarla maskelenmiş, sonunda 4 haneli bir sayı olan kart "
        "numarası satırı — bu bir banka kartı numarasıdır, FİŞ NO DEĞİLDİR, "
        "hiçbir alana yazılmaz, tamamen göz ardı et.\n"
        "  (c) \"Z NO:\" ETİKETLİ ALAN: bu, gün sonu kasa raporu (Z raporu) "
        "numarasıdır, fişin EN ALTINDA yer alır ve FİŞ NO İLE TAMAMEN "
        "İLGİSİZDİR. \"Z NO:\" yazan hiçbir değeri fis_no alanına yazma.\n"
        "  (d) \"EKÜ NO:\" ETİKETLİ ALAN: bu da farklı bir sayaç numarasıdır, "
        "fiş no değildir, göz ardı et.\n"
        "Sadece \"FİŞ NO\", \"FİS NO\", \"NO\", \"BELGE NO\" etiketinin yanındaki "
        "değeri fis_no olarak al. Etiket bulunamazsa null yaz.\n"
        "- \"plaka\": Fişte yazılı araç plakası (örn. \"34LCC311\"). Akaryakıt "
        "fişlerinde genellikle fişin gövdesinde, ürün satırının üstünde tek "
        "başına ve büyük puntoyla yazılıdır. Plaka yoksa veya fişte araçla "
        "ilgili bir bilgi yoksa null yaz. Bu değeri asla fis_no alanına da "
        "kopyalama.\n"
        "- \"urun_adi\": Fişteki ürün/hizmet içeriğini analiz ederek SADECE şu "
        "üç kategoriden birini yaz: \"Normal Bakım Onarım Giderleri ( GVK 40/1 - 40/7\", \"Taşıt Akaryakıt Giderleri (GVK 40/1-40/5)\" veya \"Dışarıdan Sağlanan Fayda ve Hizmetler\". "
        "Yedek parça, tamir, servis, oto bakım ürünleri \"Normal Bakım Onarım Giderleri ( GVK 40/1 - 40/7 )\" sayılır. "
        "Akaryakıt (motorin, benzin, LPG) \"Taşıt Akaryakıt Giderleri (GVK 40/1-40/5)\" sayılır. Eğer bu "
        "kategorilerden hiçbirine uymuyorsa fişte yazan gerçek ürün/hizmet "
        "Dışarıdan Sağlanan Fayda ve Hizmetler\n"
        "- \"firma_adi\": Fişi kesen firmanın/işletmenin adı (fiş başlığındaki "
        "unvan, genellikle en üstte büyük harflerle yazılıdır)\n"
        "- \"vergi_veya_tc_no\": SADECE \"VD:\" veya \"VD NO:\" ya da "
        "\"VERGİ DAİRESİ:\" etiketinin YANINDAKİ sayıyı al. Bu etiket genellikle "
        "firma adres bloğunun alt kısmında, vergi dairesi adının hemen "
        "ardından gelir (örn. \"Atemdağ VD:4390034418\" → vergi_veya_tc_no = "
        "\"4390034418\"). Bu sayı vergi numarası (genellikle 10 hane) VEYA TC "
        "kimlik numarası (genellikle 11 hane, özellikle şahıs işletmelerinde/"
        "esnaf fişlerinde) olabilir — hangisi olduğunu ayırt etmeye çalışma, "
        "etikette ne yazıyorsa onu RAKAM RAKAM aynen kopyala, asla başka bir "
        "sayı ile karıştırma veya tahmin etme. \"MERSİS NO\" alanını "
        "(16 haneli, boşluklarla ayrılmış uzun bir kod) bu alana KARIŞTIRMA ve yazma — MERSİS "
        "numarası farklı bir alandır, vergi_veya_tc_no DEĞİLDİR. \"VD:\" "
        "etiketi yoksa null yaz, başka bir sayıyı tahmin etme/uydurma. Eğer "
        "bu rakamları net okuyamıyorsan (görsel bulanık/küçükse), tahmin "
        "etmek yerine null yaz.\n"
        "- \"kdv_orani\": KDV oranı, sadece sayı olarak yüzde değeri (örn. 20, "
        "10, 1). BU DEĞER GENELLİKLE ÜRÜN/HİZMET SATIRININ YANINDA \"%20\", "
        "\"%10\" gibi yazılıdır (örn. \"MOTORIN SVPD %20 *5.100,00\" → "
        "kdv_orani = 20, veya \"YEDEK.PARCA %20 *9.420,00\" → kdv_orani = 20). "
        "Ayrıca \"KDV ORANI\" diye ayrı bir etiket de olabilir. Fişte birden "
        "fazla ürün satırı varsa ve hepsinde aynı oran yazıyorsa o oranı "
        "kullan. Bu alanı SADECE rakamı hiçbir yerde bulamazsan null bırak; "
        "ürün satırındaki \"%NN\" işaretini gözden kaçırma, bu en sık "
        "bulunduğu yerdir.\n"
        "- \"kdv_tutari\": KDV tutarı, sadece sayısal değer (virgül yerine "
        "nokta kullan). Bu değer \"KDV\", \"TOPKDV\" veya \"K.D.V\" etiketinin "
        "yanında yazılıdır (örn. \"TOPKDV *850,00\" → kdv_tutari = 850.00). "
        "Bu satırı dikkatlice ara, genellikle ARATOPLAM/TOP satırının hemen "
        "üstünde veya altında bulunur. Hiçbir şekilde bulamazsan null yaz.\n"
        "- \"dahil_tutar\": KDV dahil toplam tutar, sadece sayısal değer (virgül yerine nokta kullan) (bulunamazsa null)\n\n"
        "ÇOK ÖNEMLİ GENEL KURAL: Bir görselde birden fazla fiş varsa, her "
        "fişin alanlarını SADECE o fişin kendi üzerinde basılı olan "
        "değerlerden doldur. İki fiş görsel olarak birbirine çok benziyorsa "
        "(aynı firma, aynı şablon) bile, her birinin tarihi, fiş no'su, "
        "vergi no'su, tutarları birbirinden FARKLI olabilir — bunları asla "
        "birbirine kopyalama, her fişi tek başına bağımsız olarak oku ve "
        "kendi değerlerini yaz. Net okuyamadığın bir alan için kesinlikle "
        "null yaz, asla rastgele bir sayı/değer üretme veya başka bir "
        "fişten ödünç alma.\n\n"
        "RAKAM OKUMA KURALI: fiş no, vergi/TC no ve tutarlardaki rakamları tek tek, "
        "yavaşça oku; 0/O, 1/7, 5/6, 8/3 gibi benzer rakamları karıştırma. "
        "Vergi no tam 10 hane, TC kimlik no tam 11 hane olmalıdır; hane sayısı "
        "tutmuyorsa tekrar dikkatle say. Tutarlarda binlik ayraç nokta, ondalık "
        "ayraç virgüldür (\"5.100,00\" = 5100.00). Bir fişte KDV ayrı gösterilmişse "
        "dahil_tutar = ara toplam + KDV olmalıdır, kontrol et.\n\n"
        "Sayfada hiç fiş yoksa boş bir dizi [] döndür."
    )

    try:
        yanit = client.chat.completions.create(
            model=MODEL_ADI,
            messages=[
                {"role": "system", "content": sistem_talimati},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                (
                                    "Bu görselde ORTADAKİ/ana TEK bir fiş var. Kenarlarda "
                                    "görünen komşu fişlerin parçalarını YOK SAY. Sadece bu "
                                    "tek fişi, 1 elemanlı JSON dizisi olarak döndür."
                                    if tek_fis else
                                    "Bu A4 sayfasındaki tüm masraf fişlerini analiz et "
                                    "ve sadece JSON dizisi olarak döndür."
                                )
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_tipi};base64,{base64_veri}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            max_tokens=MAX_CIKTI_TOKEN,
            temperature=0,
        )

        secim = yanit.choices[0]
        mesaj = secim.message
        icerik = mesaj.content

        if icerik is None:
            # Model içerik döndürmedi. Sebebini teşhis etmek için
            # finish_reason ve mesajın diğer alanlarını yazdır.
            print(f"HATA: '{gorsel_yolu}' için model boş içerik (None) döndürdü.")
            print(f"  finish_reason: {getattr(secim, 'finish_reason', 'bilinmiyor')}")
            refusal = getattr(mesaj, "refusal", None)
            if refusal:
                print(f"  Model reddi (refusal): {refusal}")
            try:
                print(f"  Ham yanıt nesnesi: {yanit.model_dump_json()}")
            except Exception:
                print(f"  Ham yanıt nesnesi: {yanit}")
            return []

        if getattr(secim, "finish_reason", None) == "length":
            print(f"UYARI: '{gorsel_yolu}' yanıtı token sınırında kesildi, "
                  f"MAX_CIKTI_TOKEN değerini artırın.")

        icerik = icerik.strip()

        # Model bazen yanıtı ```json ... ``` bloğu içinde döndürebilir; temizle
        icerik = re.sub(r"^```(json)?", "", icerik).strip()
        icerik = re.sub(r"```$", "", icerik).strip()

        fis_listesi = json.loads(icerik)
        if isinstance(fis_listesi, dict):
            # Model tek bir nesne döndürmüş olabilir, listeye çevir
            fis_listesi = [fis_listesi]
        return fis_listesi

    except json.JSONDecodeError as e:
        print(f"HATA: '{gorsel_yolu}' için model yanıtı geçerli JSON değil: {e}")
        print(f"Ham yanıt: {icerik if 'icerik' in locals() else 'Yanıt alınamadı'}")
        return []
    except Exception as e:
        print(f"HATA: '{gorsel_yolu}' için OpenAI API çağrısı başarısız oldu: {e}")
        traceback.print_exc()
        return []


def excel_olustur(tum_fisler, cikti_yolu):
    """Toplanan fiş verilerini pandas ile düzenler ve biçimlendirilmiş bir
    Excel dosyasına yazar."""
    if not tum_fisler:
        print("UYARI: Hiç fiş verisi bulunamadı, Excel dosyası oluşturulmadı.")
        return

    sutun_sirasi = [
        "kaynak_dosya",
        "tarih",
        "fis_no",
        "plaka",
        "urun_adi",
        "firma_adi",
        "vergi_veya_tc_no",
        "kdv_orani",
        "kdv_tutari",
        "dahil_tutar",
        "uyari",
    ]
    sutun_basliklari = {
        "kaynak_dosya": "Kaynak Dosya",
        "tarih": "Tarih",
        "fis_no": "Fiş No",
        "plaka": "Plaka",
        "urun_adi": "Ürün Adı",
        "firma_adi": "Firma Adı",
        "vergi_veya_tc_no": "Vergi/TC No",
        "kdv_orani": "KDV Oranı (%)",
        "kdv_tutari": "KDV Tutarı",
        "dahil_tutar": "Dahil Tutar",
        "uyari": "Kontrol Uyarısı",
    }

    try:
        for fis in tum_fisler:
            fis["uyari"] = " | ".join(fis_uyarilari(fis))
        df = pd.DataFrame(tum_fisler)
        # Vergi/TC ve fiş no metin kalsın (başındaki sıfırlar silinmesin)
        for sutun in ("vergi_veya_tc_no", "fis_no"):
            if sutun in df.columns:
                df[sutun] = df[sutun].astype("string")

        # Eksik sütunları boş olarak ekle (model bazı alanları döndürmemiş olabilir)
        for sutun in sutun_sirasi:
            if sutun not in df.columns:
                df[sutun] = None

        df = df[sutun_sirasi]
        df = df.rename(columns=sutun_basliklari)

        with pd.ExcelWriter(cikti_yolu, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Masraf Fişleri")
            workbook = writer.book
            sheet = writer.sheets["Masraf Fişleri"]

            # Başlıkları belirgin yap
            baslik_fonu = Font(bold=True, color="FFFFFF", size=11)
            baslik_dolgusu = PatternFill(
                start_color="4472C4", end_color="4472C4", fill_type="solid"
            )
            baslik_hizalama = Alignment(horizontal="center", vertical="center")

            for hucre in sheet[1]:
                hucre.font = baslik_fonu
                hucre.fill = baslik_dolgusu
                hucre.alignment = baslik_hizalama

            # Sütun genişliklerini içeriğe göre otomatik ayarla
            for i, sutun in enumerate(df.columns, start=1):
                harf = get_column_letter(i)
                max_uzunluk = max(
                    [len(str(sutun))] + [len(str(deger)) for deger in df[sutun]]
                )
                sheet.column_dimensions[harf].width = max_uzunluk + 4

            sheet.freeze_panes = "A2"

        print(f"\nBAŞARILI: Excel dosyası oluşturuldu -> {cikti_yolu}")
        print(f"Toplam {len(df)} fiş kaydedildi.")

    except Exception as e:
        print(f"HATA: Excel dosyası oluşturulurken bir sorun oluştu: {e}")
        traceback.print_exc()


# --------------------------------------------------------------------------
# LUCA "GELİR HIZLI FİŞ AKTARIM" CSV ÇIKTISI
# --------------------------------------------------------------------------

LUCA_BASLIKLAR = [
    "İŞLEM", "KATEGORİ", "BELGE TURU", "TARİH", "TARİH", "SERİ NO", "FİŞ NO",
    "Vergi/TC No", "VERGİ DAİRESİ", "Firma Adı", "ADI DEVAMI", "ADRES",
    "CARİ HESAP", "KDV İSTİSNASI", "KOD", "BELGE TÜRÜ(DB)", "ALIŞ/SATIŞ TÜRÜ",
    "Ürün Adı", "MAL VE HİZMET KODU", "AÇIKLAMA", "MİKTAR", "B.FİYAT",
    "TUTAR", "TEVKİFAT", "KDV Oranı (%)", "ÖZEL MATRAH İŞLEM BEDELİ",
    "MATRAHTAN DÜŞÜLECEK TUTAR", "MATRAHA DAHİL OLMAYAN BEDEL", "KDV TUTARI",
    "Dahil Tutar", "KREDİLİ TUTAR", "STOPAJ KODU", "STOPAJ TUTARI",
    "DÖNEMSELLİK İLKESİ", "FAALIYET KODU", "ÖDEME TÜRÜ",
]


def sayiyi_floata_cevir(deger):
    """Bir sayıyı (str/int/float) float'a çevirir, çözemezse None döner.
    "*5.100,00", "5.100,00 TL", "5100.00", "1,234.50" gibi biçimleri çözer."""
    if deger is None:
        return None
    if isinstance(deger, (int, float)):
        return float(deger)
    try:
        temiz = re.sub(r"[^0-9,.\-]", "", str(deger))
        if not temiz:
            return None
        if "," in temiz and "." in temiz:
            # Son görülen ayraç ondalıktır
            if temiz.rfind(",") > temiz.rfind("."):
                temiz = temiz.replace(".", "").replace(",", ".")
            else:
                temiz = temiz.replace(",", "")
        elif "," in temiz:
            temiz = temiz.replace(",", ".")
        return float(temiz)
    except (ValueError, TypeError):
        return None


def sayiyi_ondalik_virgule_cevir(deger):
    """Bir sayıyı Türkçe ondalık virgül formatında (örn. 795,96) string
    olarak döndürür. Çözümlenemezse boş string döndürür."""
    sayi = sayiyi_floata_cevir(deger)
    if sayi is None:
        return ""
    return f"{sayi:.2f}".replace(".", ",")


# --------------------------------------------------------------------------
# DOĞRULAMA (vergi no / TC no / fiş no / tutar tutarlılığı)
# --------------------------------------------------------------------------

def vkn_gecerli_mi(no):
    """10 haneli vergi kimlik numarasını resmi sağlama algoritmasıyla doğrular."""
    if not (no and no.isdigit() and len(no) == 10):
        return False
    d = [int(c) for c in no]
    toplam = 0
    for i in range(9):
        tmp = (d[i] + (9 - i)) % 10
        p = (tmp * (2 ** (9 - i))) % 9
        if tmp != 0 and p == 0:
            p = 9
        toplam += p
    return (10 - toplam % 10) % 10 == d[9]


def tckn_gecerli_mi(no):
    """11 haneli TC kimlik numarasını resmi sağlama algoritmasıyla doğrular."""
    if not (no and no.isdigit() and len(no) == 11) or no[0] == "0":
        return False
    d = [int(c) for c in no]
    if ((sum(d[0:9:2]) * 7 - sum(d[1:8:2])) % 10) != d[9]:
        return False
    return sum(d[:10]) % 10 == d[10]


def vergi_no_temizle(deger):
    """Boşluk/nokta/harf gibi karakterleri atar, sadece rakamları bırakır."""
    if deger is None:
        return None
    rakamlar = re.sub(r"\D", "", str(deger))
    return rakamlar or None


def fis_uyarilari(fis):
    """Bir fiş için şüpheli alanları listeler (boşsa sorun görünmüyor)."""
    uyarilar = []
    no = fis.get("vergi_veya_tc_no")
    if not no:
        uyarilar.append("Vergi/TC no okunamadı")
    elif len(no) == 10 and not vkn_gecerli_mi(no):
        uyarilar.append("Vergi no sağlama kontrolünden geçmedi (yanlış okunmuş olabilir)")
    elif len(no) == 11 and not tckn_gecerli_mi(no):
        uyarilar.append("TC no sağlama kontrolünden geçmedi (yanlış okunmuş olabilir)")
    elif len(no) not in (10, 11):
        uyarilar.append(f"Vergi/TC no {len(no)} haneli (10 veya 11 olmalı)")

    fis_no = fis.get("fis_no")
    if not fis_no:
        uyarilar.append("Fiş no okunamadı")

    dahil = sayiyi_floata_cevir(fis.get("dahil_tutar"))
    kdv = sayiyi_floata_cevir(fis.get("kdv_tutari"))
    oran = sayiyi_floata_cevir(fis.get("kdv_orani"))
    if dahil is None:
        uyarilar.append("Dahil tutar okunamadı")
    elif kdv is not None and oran:
        beklenen = dahil * oran / (100 + oran)
        if abs(beklenen - kdv) > max(0.05, 0.02 * beklenen):
            uyarilar.append(
                f"KDV tutarsız: dahil {dahil:.2f} ve %{oran:g} için KDV ~{beklenen:.2f} "
                f"olmalı, okunan {kdv:.2f}")
    return uyarilar


def fisleri_normalle(fis_listesi):
    """Model çıktısındaki alanları temizler (vergi no sadece rakam, fiş no
    boşluksuz)."""
    for fis in fis_listesi:
        if not isinstance(fis, dict):
            continue
        fis["vergi_veya_tc_no"] = vergi_no_temizle(fis.get("vergi_veya_tc_no"))
        if fis.get("fis_no") is not None:
            fis["fis_no"] = re.sub(r"\s+", "", str(fis["fis_no"])) or None
    return fis_listesi


def fis_konumlarini_bul(gorsel_yolu):
    """Sayfada kaç fiş olduğunu ve her birinin konumunu bulur. Konumlar
    0-1000 arası göreli koordinatlarla [x0, y0, x1, y1] listesi olarak
    döner (okuma sırasıyla: soldan sağa, yukarıdan aşağı). Başarısızsa []."""
    base64_veri = gorseli_base64_yap(gorsel_yolu)
    if base64_veri is None:
        return []
    talimat = (
        "Görselde kaç adet ayrı masraf fişi/fatura var? Her fiş için fişin TAMAMINI "
        "(en üstteki firma başlığından en alttaki Z NO/EKÜ NO satırına kadar) "
        "kapsayan sınırlayıcı kutuyu ver. Koordinatlar görselin sol üst köşesine "
        "göre 0-1000 arası ölçekte olsun (x: soldan sağa, y: yukarıdan aşağı). "
        "Kutular birbirinin fişini kesmesin. Fişleri okuma sırasıyla (önce üst "
        "satır soldan sağa, sonra alt satırlar) sırala. SADECE şu biçimde JSON "
        "dizisi döndür: [{\"x0\":0,\"y0\":0,\"x1\":500,\"y1\":1000}, ...]. "
        "Hiç fiş yoksa []."
    )
    try:
        yanit = client.chat.completions.create(
            model=MODEL_ADI,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": talimat},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_veri}", "detail": "high"}},
            ]}],
            max_tokens=2000,
            temperature=0,
        )
        icerik = (yanit.choices[0].message.content or "").strip()
        icerik = re.sub(r"^```(json)?", "", icerik).strip()
        icerik = re.sub(r"```$", "", icerik).strip()
        ham = json.loads(icerik)
        kutular = []
        for k in ham if isinstance(ham, list) else []:
            x0, y0, x1, y1 = (float(k[a]) for a in ("x0", "y0", "x1", "y1"))
            if x1 - x0 >= 30 and y1 - y0 >= 30:  # çok küçük kutuları ele
                kutular.append([x0, y0, x1, y1])
        return kutular
    except Exception as e:
        print(f"       UYARI: fiş konumları bulunamadı ({e}); tüm sayfa tek parça okunacak.")
        return []


def fisleri_kirp(gorsel_yolu, kutular, hedef_klasor):
    """Her kutuyu (kenarlarda pay bırakarak) kırpıp PNG olarak kaydeder,
    dosya yollarını döndürür."""
    from PIL import Image, ImageOps
    yollar = []
    with Image.open(gorsel_yolu) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        g, y = img.size
        for i, (x0, y0, x1, y1) in enumerate(kutular, start=1):
            pay_x, pay_y = (x1 - x0) * 0.05, (y1 - y0) * 0.03
            kutu = (
                int(max(0, x0 - pay_x) / 1000 * g), int(max(0, y0 - pay_y) / 1000 * y),
                int(min(1000, x1 + pay_x) / 1000 * g), int(min(1000, y1 + pay_y) / 1000 * y),
            )
            yol = os.path.join(hedef_klasor, f"fis{i:02d}.png")
            img.crop(kutu).save(yol, "PNG")
            yollar.append(yol)
    return yollar


def sayfayi_isle(gorsel_yolu):
    """Sayfadaki fiş sayısına göre okuma stratejisini seçer: önce fişleri
    bulur, sonra her birini ayrı kırpıp büyüterek tek tek okur (1 fiş de
    10 fiş de aynı doğrulukta okunur). Konum bulunamazsa tüm sayfayı okur."""
    kutular = fis_konumlarini_bul(gorsel_yolu)
    if not kutular:
        return sayfa_fislerini_cikar_dogrulamali(gorsel_yolu)

    print(f"       Sayfada {len(kutular)} fiş bulundu, her biri ayrı okunuyor...")
    kirpma_klasoru = tempfile.mkdtemp(prefix="fis_kirpma_")
    sonuc = []
    try:
        for i, kirpik in enumerate(fisleri_kirp(gorsel_yolu, kutular, kirpma_klasoru), start=1):
            fisler = sayfa_fislerini_cikar_dogrulamali(kirpik, tek_fis=True)
            fisler = [f for f in fisler if isinstance(f, dict)][:1]
            if not fisler:
                print(f"       UYARI: {i}. fiş okunamadı.")
            sonuc.extend(fisler)
    finally:
        shutil.rmtree(kirpma_klasoru, ignore_errors=True)
    return sonuc


def sayfa_fislerini_cikar_dogrulamali(gorsel_yolu, deneme=3, tek_fis=False):
    """Sayfayı okur; şüpheli alanı olan fiş varsa sayfayı yeniden okuyup
    (en fazla 'deneme' kez) her fiş için en az uyarılı sürümü seçer."""
    en_iyi = fisleri_normalle(gpt4o_ile_fisleri_cikar(gorsel_yolu, tek_fis))
    for n in range(2, deneme + 1):
        if not any(fis_uyarilari(f) for f in en_iyi if isinstance(f, dict)):
            break
        print(f"       Şüpheli alan var, sayfa yeniden okunuyor (deneme {n}/{deneme})...")
        yeni = fisleri_normalle(gpt4o_ile_fisleri_cikar(gorsel_yolu, tek_fis))
        if len(yeni) != len(en_iyi):
            continue  # fiş sayısı tutmuyorsa eşleştirme güvenilmez
        for i, (eski_f, yeni_f) in enumerate(zip(en_iyi, yeni)):
            if (isinstance(eski_f, dict) and isinstance(yeni_f, dict)
                    and len(fis_uyarilari(yeni_f)) < len(fis_uyarilari(eski_f))):
                en_iyi[i] = yeni_f
    return en_iyi


def luca_csv_olustur(tum_fisler, cikti_yolu):
    """
    Toplanan fiş verilerini LUCA muhasebe programının "Gelir Hızlı Fiş
    Aktarım" şablonuna uygun CSV dosyası olarak yazar. Şablondaki sabit
    alanlar (İŞLEM, KATEGORİ, BELGE TURU vb.) her satırda aynen tekrar
    eder; sadece fişe özel alanlar (tarih, fiş no, vergi no, firma adı,
    ürün adı, tutar, KDV oranı/tutarı, dahil tutar) doldurulur.
    """
    if not tum_fisler:
        print("UYARI: Hiç fiş verisi bulunamadı, LUCA CSV dosyası oluşturulmadı.")
        return

    try:
        with open(cikti_yolu, "w", newline="", encoding="cp1254") as f:
            yazici = csv.writer(f, delimiter=";", lineterminator="\r\n")
            yazici.writerow(LUCA_BASLIKLAR)

            for fis in tum_fisler:
                tarih = fis.get("tarih") or ""
                fis_no = fis.get("fis_no") or ""
                vergi_no = fis.get("vergi_veya_tc_no") or ""
                firma_adi = fis.get("firma_adi") or ""
                urun_adi = fis.get("urun_adi") or ""

                dahil_tutar_f = sayiyi_floata_cevir(fis.get("dahil_tutar"))
                kdv_tutari_f = sayiyi_floata_cevir(fis.get("kdv_tutari"))
                kdv_orani_str = sayiyi_ondalik_virgule_cevir(fis.get("kdv_orani"))
                kdv_tutari_str = sayiyi_ondalik_virgule_cevir(fis.get("kdv_tutari"))
                dahil_tutar_str = sayiyi_ondalik_virgule_cevir(fis.get("dahil_tutar"))

                # TUTAR = KDV hariç (net) tutar = Dahil Tutar - KDV Tutarı
                if dahil_tutar_f is not None and kdv_tutari_f is not None:
                    tutar_str = sayiyi_ondalik_virgule_cevir(dahil_tutar_f - kdv_tutari_f)
                else:
                    tutar_str = ""

                satir = [
                    "GİDER",                # İŞLEM
                    "DEFTER FİŞLERİ",        # KATEGORİ
                    "ALIŞ",                 # BELGE TURU
                    tarih,                   # TARİH
                    tarih,                   # TARİH (tekrar)
                    "",                      # SERİ NO
                    fis_no,                  # FİŞ NO
                    vergi_no,                # Vergi/TC No
                    "",                      # VERGİ DAİRESİ
                    firma_adi,               # Firma Adı
                    "A",                     # ADI DEVAMI
                    "",                      # ADRES
                    "",                      # CARİ HESAP
                    "",                      # KDV İSTİSNASI
                    "",                      # KOD
                    "ÖKC FİŞİ",                   # BELGE TÜRÜ(DB)
                    "NORMAL ALIM",        # ALIŞ/SATIŞ TÜRÜ
                    urun_adi,                # Ürün Adı
                    "",                      # MAL VE HİZMET KODU
                    firma_adi,               # AÇIKLAMA
                    "",                      # MİKTAR
                    "",                      # B.FİYAT
                    tutar_str,               # TUTAR
                    "",                      # TEVKİFAT
                    kdv_orani_str,           # KDV Oranı (%)
                    "",                      # ÖZEL MATRAH İŞLEM BEDELİ
                    "",                      # MATRAHTAN DÜŞÜLECEK TUTAR
                    "",                      # MATRAHA DAHİL OLMAYAN BEDEL
                    kdv_tutari_str,          # KDV TUTARI
                    dahil_tutar_str,         # Dahil Tutar
                    "",                      # KREDİLİ TUTAR
                    "",                      # STOPAJ KODU
                    "",                      # STOPAJ TUTARI
                    "",                      # DÖNEMSELLİK İLKESİ
                    "",                      # FAALIYET KODU
                    "532009",                # ÖDEME TÜRÜ
                    "",                      # (şablondaki sondaki boş alan)
                ]
                yazici.writerow(satir)

        print(f"BAŞARILI: LUCA formatında CSV oluşturuldu -> {cikti_yolu}")

    except Exception as e:
        print(f"HATA: LUCA CSV dosyası oluşturulurken bir sorun oluştu: {e}")
        traceback.print_exc()


# --------------------------------------------------------------------------
# BİR KİŞİ KLASÖRÜNÜ BAŞTAN SONA İŞLEME
# --------------------------------------------------------------------------

def klasoru_isle(klasor_yolu, cikti_yolu, luca_csv_yolu=None):
    """
    Verilen klasördeki tüm PDF/görsel dosyalarını işler ve sonucu
    cikti_yolu'na (o klasörün içine, klasör adıyla) Excel olarak yazar.
    luca_csv_yolu verilmişse, aynı veriyi LUCA "Gelir Hızlı Fiş Aktarım"
    formatında bir CSV olarak da yazar.
    """
    klasor_adi = os.path.basename(klasor_yolu.rstrip(os.sep))
    print(f"\n{'='*60}")
    print(f"KLASÖR: {klasor_adi}  ({klasor_yolu})")
    print(f"{'='*60}")

    dosyalar = klasordeki_dosyalari_bul(klasor_yolu)

    if not dosyalar:
        print(f"  '{klasor_adi}' klasöründe işlenecek PDF veya görsel dosyası bulunamadı.")
        return

    print(f"  {len(dosyalar)} adet dosya bulundu. İşlem başlıyor...\n")

    gecici_klasor = os.path.join(klasor_yolu, "_gecici_pdf_gorseller")
    tum_fisler = []
    gecici_pdf_gorselleri_olustu = False

    try:
        for dosya_yolu in dosyalar:
            dosya_adi = os.path.basename(dosya_yolu)
            uzanti = os.path.splitext(dosya_adi)[1].lower()
            print(f"  -> İşleniyor: {dosya_adi}")

            islenecek_gorseller = []
            pdf_den_olusan_gecici_gorseller = []

            try:
                if uzanti in DESTEKLENEN_PDF_UZANTISI:
                    pdf_den_olusan_gecici_gorseller = pdf_yi_gorsellere_cevir(
                        dosya_yolu, gecici_klasor
                    )
                    if pdf_den_olusan_gecici_gorseller:
                        gecici_pdf_gorselleri_olustu = True
                    islenecek_gorseller = pdf_den_olusan_gecici_gorseller
                else:
                    islenecek_gorseller = [dosya_yolu]

                for gorsel_yolu in islenecek_gorseller:
                    print(f"     - Analiz ediliyor: {os.path.basename(gorsel_yolu)}")
                    fis_listesi = sayfayi_isle(gorsel_yolu)
                    print(f"       {len(fis_listesi)} fiş tespit edildi.")
                    for fis in fis_listesi:
                        if isinstance(fis, dict):
                            fis["kaynak_dosya"] = dosya_adi
                            tum_fisler.append(fis)

            except Exception as e:
                print(f"  HATA: '{dosya_adi}' işlenirken beklenmeyen bir sorun oluştu: {e}")
                traceback.print_exc()

            finally:
                # Bu PDF'ten oluşan geçici görselleri hemen sil
                for gecici_gorsel in pdf_den_olusan_gecici_gorseller:
                    try:
                        if os.path.exists(gecici_gorsel):
                            os.remove(gecici_gorsel)
                    except Exception as e:
                        print(f"  UYARI: Geçici dosya silinemedi '{gecici_gorsel}': {e}")

        excel_olustur(tum_fisler, cikti_yolu)
        if luca_csv_yolu:
            luca_csv_olustur(tum_fisler, luca_csv_yolu)

    except Exception as e:
        print(f"  HATA: '{klasor_adi}' klasörü işlenirken beklenmeyen bir sorun oluştu: {e}")
        traceback.print_exc()

    finally:
        # Geçici klasörü tamamen temizle
        if gecici_pdf_gorselleri_olustu and os.path.isdir(gecici_klasor):
            try:
                shutil.rmtree(gecici_klasor)
                print(f"  Geçici klasör temizlendi: {gecici_klasor}")
            except Exception as e:
                print(f"  UYARI: Geçici klasör silinemedi: {e}")


# --------------------------------------------------------------------------
# ANA İŞ AKIŞI
# --------------------------------------------------------------------------

def main():
    print(f"Ana klasör taranıyor: {TARANACAK_KLASOR}")

    try:
        alt_klasorler = sorted([
            os.path.join(TARANACAK_KLASOR, ad)
            for ad in os.listdir(TARANACAK_KLASOR)
            if os.path.isdir(os.path.join(TARANACAK_KLASOR, ad))
            and not ad.startswith("_")
            and not ad.startswith(".")
        ])
    except Exception as e:
        print(f"HATA: Ana klasördeki alt klasörler taranırken sorun oluştu: {e}")
        traceback.print_exc()
        return

    if alt_klasorler:
        # Kişi/proje bazlı çalışma modu: her alt klasör ayrı işlenir,
        # her birinin Excel çıktısı kendi klasörü içine, klasör adıyla yazılır.
        print(f"{len(alt_klasorler)} adet alt klasör bulundu: "
              f"{', '.join(os.path.basename(k) for k in alt_klasorler)}\n")

        for klasor_yolu in alt_klasorler:
            klasor_adi = os.path.basename(klasor_yolu.rstrip(os.sep))
            cikti_yolu = os.path.join(klasor_yolu, f"{klasor_adi}.xlsx")
            luca_csv_yolu = os.path.join(
                klasor_yolu, f"{klasor_adi}_LUCA_GELIR_hizli_fis_aktarim.csv"
            )
            try:
                klasoru_isle(klasor_yolu, cikti_yolu, luca_csv_yolu)
            except Exception as e:
                print(f"HATA: '{klasor_adi}' klasörü işlenirken beklenmeyen bir sorun oluştu: {e}")
                traceback.print_exc()

    else:
        # Alt klasör yoksa: eski davranış - bulunduğu klasördeki dosyaları
        # doğrudan işle ve "Masraf_Fisleri.xlsx" olarak kaydet.
        print("Alt klasör bulunamadı, bulunduğu klasördeki dosyalar doğrudan işlenecek.\n")
        cikti_yolu = os.path.join(TARANACAK_KLASOR, "Masraf_Fisleri.xlsx")
        luca_csv_yolu = os.path.join(
            TARANACAK_KLASOR, "Masraf_Fisleri_LUCA_GELIR_hizli_fis_aktarim.csv"
        )
        klasoru_isle(TARANACAK_KLASOR, cikti_yolu, luca_csv_yolu)

    print("\nTüm işlemler tamamlandı.")


if __name__ == "__main__":
    main()
    try:
        input("\nİşlem tamamlandı. Çıkmak için Enter tuşuna basın...")
    except Exception:
        pass
