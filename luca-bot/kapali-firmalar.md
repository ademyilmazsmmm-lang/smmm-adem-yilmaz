# Sorgulanmayacak firmalar (01/08/2026 sonrası çalışma için)

Kaynak: Luca firma listesindeki **Kapanış Tarihi** sütunu.
Kural: kapanış tarihi sorgu başlangıcından (01/08/2026) **önce** olan firmada o dönemde
alış faturası oluşamaz; bu firmalar hiç sorgulanmaz.

## Atlanacak — kapanış 01/08/2026'dan önce (12 firma)

| Kısa Adı | Uzun Adı | Kapanış |
| --- | --- | --- |
| BERKAYYETİ | BERKAY YETİM | 28/02/2026 |
| BURAK ÖZKA | BURAK ÖZKAN | 31/01/2026 |
| EVREN GÜNG | EVREN GÜNGÖR | 28/02/2026 |
| MERTEMİR | MERT EMİR İRMAK | 30/01/2026 |
| MEHMET ŞEN | MEHMET ŞEN | 30/03/2026 |
| EST TEDARİ | EST TEDARİK VE İNŞAAT LTD. | 16/04/2026 |
| GÜLENBER S | GÜLENBER SARIKAYA | 15/04/2026 |
| ALİ KAAN T | ALİ KAAN TÜMER | 29/04/2026 |
| ÖMÜR CAN T | ÖMÜR CAN TEMİZEL | 29/04/2026 |
| RATATOUİLL | RATATOUİLLE GIDA PASTACILIK LTD. | 04/05/2026 |
| SERKANGENÇ | SERKAN GENÇ | 30/06/2026 |
| OĞUZHAN Bİ | OĞUZHAN BİÇER | 27/06/2026 |

Bu liste `ayarlar.json` içindeki `atlanacak_firmalar` alanına yazılmıştır.

## Sorgulanacak ama kısmi dönem (atlanmaz)

| Kısa Adı | Durum | Not |
| --- | --- | --- |
| İBRAHİM EN | 17/07/2026 açıldı, 14/08/2026 kapandı | sadece 01-14/08 arası olabilir |
| AHMET EREN | 31/08/2026 kapandı | ağustos tam, eylül boş |
| ZAFER BÜLB | 03/09/2026 açılış = kapanış | tek günlük, muhtemelen boş |
| KÜBRA BÜLB | 15/09/2026 kapandı | ağustos + 01-15/09 |
| MURAT CAN | 22/08/2026 açıldı | ağustosun yarısı |
| METİN BALT | 06/08/2026 açıldı | ağustosun yarısı |
| M.EMİR KIR | 09/09/2026 açıldı | ağustos boş, eylül var |
| MUZAFFER E | 17/09/2026 açıldı | ağustos boş |

## Kapanış sütunu boş ama açıklamada kapanış geçenler (kontrol edin)

| Kısa Adı | Açıklama |
| --- | --- |
| YUNUS SEZG | "GENÇ GİRİŞİM 2025 kapanış 29/9/..." |
| RATA-TASFİ | tasfiye halinde — kapanış yok, sorgulanır |

Bu firmalarda Luca'da kapanış işlenmemiş; kapandıysa listeye ekleyin.

## RATATOUİLLE notu

İki kayıt var: kapanan **RATATOUİLL** (04/05/2026) ve tasfiye kaydı **RATA-TASFİ** (04/05/2026 açılış).
Sadece kapanan atlanır, tasfiye kaydı sorgulanır.
