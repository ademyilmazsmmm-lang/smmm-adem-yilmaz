"""
TCMB EVDS API'sinden günlük USD/EUR/GBP alış-satış kurlarını çekip
index.html'deki "Kur & Enflasyon" kartındaki döviz tablosunu günceller.

Döviz serileri günlük ve alış/satış ayrımıyla yayınlanır:
  TP.DK.USD.A.YTL / TP.DK.USD.S.YTL  -> USD alış / satış
  TP.DK.EUR.A.YTL / TP.DK.EUR.S.YTL  -> EUR alış / satış
  TP.DK.GBP.A.YTL / TP.DK.GBP.S.YTL  -> GBP alış / satış

Gerekli ortam değişkeni: TCMB_EVDS_API_KEY
"""

import os
import re
import sys
from datetime import date, timedelta

import requests

INDEX_HTML = "index.html"

FX_SERIES = {
    "doviz-usd-alis": "TP.DK.USD.A.YTL",
    "doviz-usd-satis": "TP.DK.USD.S.YTL",
    "doviz-eur-alis": "TP.DK.EUR.A.YTL",
    "doviz-eur-satis": "TP.DK.EUR.S.YTL",
    "doviz-gbp-alis": "TP.DK.GBP.A.YTL",
    "doviz-gbp-satis": "TP.DK.GBP.S.YTL",
}

# (min, max) mantık kontrolü sınırları — açıkça hatalı veriyi ayıklamak için
BOUNDS = {
    "doviz-usd-alis": (5, 500), "doviz-usd-satis": (5, 500),
    "doviz-eur-alis": (5, 500), "doviz-eur-satis": (5, 500),
    "doviz-gbp-alis": (5, 500), "doviz-gbp-satis": (5, 500),
}


def _headers(api_key: str) -> dict:
    return {
        "key": api_key,
        "User-Agent": "Mozilla/5.0 (compatible; smmm-adem-yilmaz-site/1.0)",
        "Accept": "application/json",
    }


def _get_json(url: str, api_key: str):
    resp = requests.get(url, headers=_headers(api_key), timeout=30)
    if resp.status_code != 200 or not resp.text.strip():
        raise RuntimeError(
            f"EVDS isteği başarısız: status={resp.status_code}, "
            f"body_ilk_300={resp.text[:300]!r}, url={url}"
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise RuntimeError(
            f"EVDS cevabı JSON değil: status={resp.status_code}, "
            f"body_ilk_300={resp.text[:300]!r}, url={url}"
        ) from exc


def fetch_series_values(api_key: str, codes: list[str], days: int = 10) -> dict:
    """Birden çok EVDS serisini tek istekte çeker, her kod için
    (tarih, değer) listesini kronolojik sırayla döner."""
    end = date.today()
    start = end - timedelta(days=days)
    series_param = "-".join(codes)

    url = (
        "https://evds3.tcmb.gov.tr/igmevdsms-dis/"
        f"series={series_param}&startDate={start.strftime('%d-%m-%Y')}"
        f"&endDate={end.strftime('%d-%m-%Y')}&type=json"
    )
    data = _get_json(url, api_key)
    items = data.get("items", [])

    result: dict = {code: [] for code in codes}
    for item in items:
        raw_tarih = item.get("Tarih")
        if not raw_tarih:
            continue
        try:
            parts = [int(p) for p in raw_tarih.split("-")]
            if len(parts) == 2:
                year, month = parts  # aylık seri: "YYYY-MM"
                d = date(year, month, 1)
            elif len(parts) == 3:
                day, month, year = parts  # günlük seri: "DD-MM-YYYY"
                d = date(year, month, day)
            else:
                continue
        except ValueError:
            continue
        for code in codes:
            key = code.replace(".", "_")
            raw_val = item.get(key)
            if raw_val in (None, "", "-9999"):
                continue
            try:
                result[code].append((d, float(raw_val)))
            except ValueError:
                continue

    for code in codes:
        result[code].sort(key=lambda p: p[0])
    return result


def latest_value(series_map: dict, code: str):
    points = series_map.get(code) or []
    return points[-1] if points else None


def format_tr_number(value: float, decimals: int = 2) -> str:
    s = f"{value:,.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def valid(field: str, value: float) -> bool:
    lo, hi = BOUNDS[field]
    return lo <= value <= hi


def update_html(values: dict, tarih_label: str) -> set:
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    changed = set()

    for field, value in values.items():
        formatted = format_tr_number(value)
        pattern = rf'(<span class="doviz-val {field}">)[^<]*(</span>)'
        new_html, count = re.subn(pattern, rf"\g<1>{formatted}\g<2>", html, count=1)
        if count:
            html = new_html
            changed.add(field)

    if tarih_label:
        new_html, count = re.subn(
            r'(<span class="doviz-tarih">)[^<]*(</span>)',
            rf"\g<1>{tarih_label}\g<2>",
            html,
            count=1,
        )
        if count:
            html = new_html
            changed.add("tarih")

    if changed:
        with open(INDEX_HTML, "w", encoding="utf-8") as f:
            f.write(html)

    return changed


def main() -> None:
    api_key = os.environ.get("TCMB_EVDS_API_KEY")
    if not api_key:
        print("HATA: TCMB_EVDS_API_KEY ortam değişkeni tanımlı değil.", file=sys.stderr)
        sys.exit(1)

    fx_map = fetch_series_values(api_key, list(FX_SERIES.values()))

    values: dict = {}
    latest_date = None

    for field, code in FX_SERIES.items():
        point = latest_value(fx_map, code)
        if not point:
            print(f"UYARI: {field} ({code}) için veri bulunamadı.", file=sys.stderr)
            continue
        d, v = point
        if not valid(field, v):
            print(f"UYARI: {field} değeri mantık dışı ({v}), atlanıyor.", file=sys.stderr)
            continue
        values[field] = v
        latest_date = d if latest_date is None else max(latest_date, d)

    if not values:
        print("HATA: Hiçbir geçerli değer çekilemedi, index.html güncellenmedi.", file=sys.stderr)
        sys.exit(1)

    tarih_label = latest_date.strftime("%d.%m.%Y") if latest_date else ""
    changed = update_html(values, tarih_label)

    if changed:
        print(f"Güncellendi ({tarih_label}): {sorted(changed)}")
    else:
        print("Değişiklik yok (değerler zaten güncel).")


if __name__ == "__main__":
    main()
