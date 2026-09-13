"""
TCMB EVDS API'sinden günlük USD/EUR alış-satış kurlarını ve (bulunabilirse)
gram altın alış-satış fiyatını çekip index.html'deki "Kur & Enflasyon"
kartındaki döviz/altın tablosunu günceller.

Döviz serileri sabit ve resmi olarak doğrulanmıştır:
  TP.DK.USD.A.YTL / TP.DK.USD.S.YTL  -> USD alış / satış
  TP.DK.EUR.A.YTL / TP.DK.EUR.S.YTL  -> EUR alış / satış

Gram altın için TCMB'nin standart döviz serileri gibi sabit, herkesçe
doğrulanmış tek bir seri kodu bulunamadığından; "Kıymetli Madenler"
veri grubu (bie_mkaltytl) EVDS metadata servisinden her çalıştırmada
otomatik keşfedilir. Bu adım başarısız olursa altın alanı GÜNCELLENMEDEN
atlanır, USD/EUR güncellemesi yine de yapılır (script tamamen durmaz).

Gerekli ortam değişkeni: TCMB_EVDS_API_KEY
"""

import os
import re
import sys
from datetime import date, timedelta

import requests

INDEX_HTML = "index.html"
GOLD_DATAGROUP = "bie_mkaltytl"

FX_SERIES = {
    "doviz-usd-alis": "TP.DK.USD.A.YTL",
    "doviz-usd-satis": "TP.DK.USD.S.YTL",
    "doviz-eur-alis": "TP.DK.EUR.A.YTL",
    "doviz-eur-satis": "TP.DK.EUR.S.YTL",
}

# (min, max) mantık kontrolü sınırları — açıkça hatalı veriyi ayıklamak için
BOUNDS = {
    "doviz-usd-alis": (5, 500), "doviz-usd-satis": (5, 500),
    "doviz-eur-alis": (5, 500), "doviz-eur-satis": (5, 500),
    "doviz-altin-alis": (500, 100000), "doviz-altin-satis": (500, 100000),
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
            d = date(*[int(p) for p in reversed(raw_tarih.split("-"))])
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


def discover_gold_series(api_key: str):
    """bie_mkaltytl veri grubundaki seriler arasından 'gram altın'
    alış/satış kodlarını isimlerine bakarak bulmaya çalışır."""
    url = (
        "https://evds3.tcmb.gov.tr/igmevdsms-dis/serieList/"
        f"type=json&code={GOLD_DATAGROUP}"
    )
    entries = _get_json(url, api_key)
    if isinstance(entries, dict):
        entries = entries.get("items", [])

    print(f"TEŞHİS: serieList({GOLD_DATAGROUP}) -> {len(entries)} kayıt: {entries[:5]}")

    alis_code = satis_code = None
    for entry in entries:
        code = entry.get("SERIE_CODE")
        name = (entry.get("SERIE_NAME") or "").lower()
        if not code:
            continue
        is_gram = "gram" in name or "995" in name
        if "alış" in name and (is_gram or alis_code is None):
            alis_code = code
        if "satış" in name and (is_gram or satis_code is None):
            satis_code = code

    return alis_code, satis_code


def fetch_gold(api_key: str):
    alis_code, satis_code = discover_gold_series(api_key)
    if not alis_code or not satis_code:
        print("UYARI: Gram altın seri kodu bulunamadı, altın alanı atlanıyor.")
        return None

    series_map = fetch_series_values(api_key, [alis_code, satis_code])
    alis = latest_value(series_map, alis_code)
    satis = latest_value(series_map, satis_code)
    if not alis or not satis:
        print("UYARI: Gram altın verisi çekilemedi, altın alanı atlanıyor.")
        return None

    return {
        "doviz-altin-alis": alis[1],
        "doviz-altin-satis": satis[1],
        "tarih": max(alis[0], satis[0]),
    }


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

    try:
        gold = fetch_gold(api_key)
    except Exception as exc:  # noqa: BLE001 - altın adımı opsiyonel, sağlam devam etsin
        print(f"UYARI: Altın verisi çekilirken hata oluştu: {exc}", file=sys.stderr)
        gold = None

    if gold:
        for field in ("doviz-altin-alis", "doviz-altin-satis"):
            v = gold[field]
            if valid(field, v):
                values[field] = v
                latest_date = gold["tarih"] if latest_date is None else max(latest_date, gold["tarih"])
            else:
                print(f"UYARI: {field} değeri mantık dışı ({v}), atlanıyor.", file=sys.stderr)

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
