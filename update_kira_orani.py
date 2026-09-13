"""
TCMB EVDS API'sinden TÜFE Genel Endeksi (TP.FG.J0) verisini çekip
TBK m.344 uyarınca uygulanan "12 aylık ortalamalara göre değişim"
(yasal kira artış tavanı) oranını hesaplar ve index.html'deki
Kur & Enflasyon kartını günceller.

Oran = (son 12 ayın TÜFE ortalaması / önceki 12 ayın TÜFE ortalaması - 1) * 100

Gerekli ortam değişkeni: TCMB_EVDS_API_KEY
(https://evds2.tcmb.gov.tr adresinden ücretsiz alınır)
"""

import os
import re
import sys
from datetime import date, timedelta

import requests

SERIES = "TP.FG.J0"
INDEX_HTML = "index.html"

AY_ADLARI = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]


def fetch_series(api_key: str) -> list[tuple[date, float]]:
    end = date.today()
    start = end - timedelta(days=30 * 30)  # ~30 ay geriye, güvenli pay

    url = (
        "https://evds2.tcmb.gov.tr/service/evds/"
        f"series={SERIES}&startDate={start.strftime('%d-%m-%Y')}"
        f"&endDate={end.strftime('%d-%m-%Y')}&type=json"
    )
    resp = requests.get(url, headers={"key": api_key}, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    items = data.get("items", [])
    series_key = SERIES.replace(".", "_")

    points: list[tuple[date, float]] = []
    for item in items:
        raw_val = item.get(series_key)
        raw_tarih = item.get("Tarih")
        if raw_val in (None, "", "-9999"):
            continue
        if not raw_tarih:
            continue
        month_str, year_str = raw_tarih.split("-")
        d = date(int(year_str), int(month_str), 1)
        try:
            points.append((d, float(raw_val)))
        except ValueError:
            continue

    points.sort(key=lambda p: p[0])
    return points


def compute_rate(points: list[tuple[date, float]]) -> float:
    if len(points) < 24:
        raise RuntimeError(
            f"Yetersiz veri: {len(points)} ay bulundu, en az 24 ay gerekli."
        )

    last24 = points[-24:]
    values = [p[1] for p in last24]

    prev12 = values[:12]
    last12 = values[12:]

    avg_prev = sum(prev12) / 12
    avg_last = sum(last12) / 12

    rate = (avg_last / avg_prev - 1) * 100
    return rate


def format_tr_percent(rate: float) -> str:
    return f"%{rate:.2f}".replace(".", ",")


def update_html(rate_text: str, ay_label: str) -> bool:
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    original = html

    html = re.sub(
        r'(<span class="kira-oran-ay">)[^<]*(</span>)',
        rf"\g<1>{ay_label}\g<2>",
        html,
        count=1,
    )
    html = re.sub(
        r'(<span class="kira-oran-value">)[^<]*(</span>)',
        rf"\g<1>{rate_text}\g<2>",
        html,
    )

    if html == original:
        return False

    with open(INDEX_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    return True


def main() -> None:
    api_key = os.environ.get("TCMB_EVDS_API_KEY")
    if not api_key:
        print("HATA: TCMB_EVDS_API_KEY ortam değişkeni tanımlı değil.", file=sys.stderr)
        sys.exit(1)

    points = fetch_series(api_key)
    rate = compute_rate(points)

    # Mantık kontrolü: TÜFE ortalama artış oranı negatif ya da aşırı
    # yüksek çıkarsa (veri hatası ihtimali) siteyi güncelleme, hatayla çık.
    if not (0 <= rate <= 150):
        print(
            f"HATA: Hesaplanan oran mantık dışı görünüyor ({rate:.2f}). "
            "Güvenlik amacıyla index.html güncellenmedi.",
            file=sys.stderr,
        )
        sys.exit(1)

    rate_text = format_tr_percent(rate)

    today = date.today()
    ay_label = f"{AY_ADLARI[today.month - 1]} {today.year}"

    changed = update_html(rate_text, ay_label)
    if changed:
        print(f"Güncellendi: {ay_label} -> {rate_text}")
    else:
        print(f"Değişiklik yok: {ay_label} -> {rate_text} (zaten güncel)")


if __name__ == "__main__":
    main()
