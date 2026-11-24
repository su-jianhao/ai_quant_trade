"""Target resolution and universe constituent routing for single stocks and stock pools."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests

# 台灣 50 指數核心 50 檔成分股 (TWSE)
TW50_CONSTITUENTS: List[str] = [
    "2330.TW", "2454.TW", "2317.TW", "2308.TW", "2382.TW",
    "3711.TW", "2303.TW", "2881.TW", "2882.TW", "2891.TW",
    "2412.TW", "2886.TW", "2884.TW", "2345.TW", "2357.TW",
    "3231.TW", "3034.TW", "2379.TW", "1216.TW", "2885.TW",
    "2892.TW", "5880.TW", "2880.TW", "2890.TW", "2887.TW",
    "2883.TW", "3017.TW", "2383.TW", "3037.TW", "2301.TW",
    "2327.TW", "2395.TW", "2360.TW", "2059.TW", "3008.TW",
    "3045.TW", "4904.TW", "1301.TW", "1303.TW", "1326.TW",
    "2002.TW", "2603.TW", "2609.TW", "2615.TW", "2618.TW",
    "2912.TW", "5871.TW", "6669.TW", "6505.TW", "6446.TW",
]

# 台灣中型 100 指數 (0051) 核心 100 檔成分股 (TWSE)
TW100_CONSTITUENTS: List[str] = [
    "2379.TW", "3661.TW", "1301.TW", "3481.TW", "3034.TW",
    "1326.TW", "2801.TW", "3044.TW", "3189.TW", "2313.TW",
    "5876.TW", "6770.TW", "2002.TW", "2409.TW", "1101.TW",
    "4938.TW", "2404.TW", "6239.TW", "3533.TW", "1590.TW",
    "2376.TW", "2615.TW", "2207.TW", "2337.TW", "6415.TW",
    "3036.TW", "5871.TW", "2834.TW", "2618.TW", "3702.TW",
    "2324.TW", "6213.TW", "2912.TW", "8996.TW", "2356.TW",
    "2609.TW", "6805.TW", "6515.TW", "1605.TW", "6139.TW",
    "2347.TW", "2049.TW", "2377.TW", "1402.TW", "5434.TW",
    "1102.TW", "1802.TW", "2353.TW", "2474.TW", "2027.TW",
    "2492.TW", "6257.TW", "1504.TW", "1560.TW", "1519.TW",
    "6531.TW", "1476.TW", "2812.TW", "2455.TW", "2610.TW",
    "6919.TW", "6285.TW", "6442.TW", "3026.TW", "3706.TW",
    "8464.TW", "9904.TW", "2385.TW", "3023.TW", "1513.TW",
    "6409.TW", "7750.TW", "3006.TW", "2354.TW", "2542.TW",
    "2105.TW", "3167.TW", "1717.TW", "2633.TW", "1503.TW",
    "9945.TW", "2451.TW", "3005.TW", "5269.TW", "6789.TW",
    "6691.TW", "6196.TW", "7610.TW", "1229.TW", "8210.TW",
    "3030.TW", "6526.TW", "6949.TW", "2467.TW", "9910.TW",
    "2646.TW", "6781.TW", "2838.TW", "3532.TW", "2645.TW",
]

# 費城半導體指數 (SOX) 核心 30 檔成分股
SOX_CONSTITUENTS: List[str] = [
    "NVDA", "AVGO", "TSM", "AMD", "QCOM", "TXN", "INTC", "MU", "AMAT", "LRCX",
    "KLAC", "ADI", "MRVL", "NXPI", "MCHP", "ON", "MPWR", "TER", "ENTG", "SWKS",
    "QRVO", "ASML", "ARM", "STM", "GFS", "ALGM", "CRUS", "LSCC", "RMBS", "AMKR",
]

MAG7_CONSTITUENTS: List[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
]

POOL_ALIASES = {
    "tw50": ("TW50", "0050.TW", "TW"),
    "0050": ("TW50", "0050.TW", "TW"),
    "tw100": ("TW100", "0051.TW", "TW"),
    "0051": ("TW100", "0051.TW", "TW"),
    "sox": ("SOX", "SOXX", "US"),
    "soxx": ("SOX", "SOXX", "US"),
    "sp500": ("SP500", "SPY", "US"),
    "s&p500": ("SP500", "SPY", "US"),
    "nasdaq": ("NASDAQ100", "QQQ", "US"),
    "nasdaq100": ("NASDAQ100", "QQQ", "US"),
    "qqq": ("NASDAQ100", "QQQ", "US"),
    "mag7": ("MAG7", "QQQ", "US"),
}


@dataclass
class TargetSpec:
    """Resolved target specification."""

    raw_target: str
    slug: str
    target_type: str  # "single" or "pool"
    market: str       # "TW", "US", or "MIXED"
    benchmark: str
    tickers: List[str]
    output_dir: str
    resolved_at: str

    def to_dict(self) -> dict:
        return asdict(self)


def is_taiwan_ticker(ticker: str) -> bool:
    """Return True if ticker belongs to Taiwan market."""
    t = ticker.strip().upper()
    return t.endswith(".TW") or t.endswith(".TWO") or bool(re.fullmatch(r"\d{4,6}", t))


def normalize_ticker(ticker: str) -> str:
    """Normalize ticker symbol (e.g. '2330' -> '2330.TW', 'nvda' -> 'NVDA')."""
    t = ticker.strip().upper()
    if re.fullmatch(r"\d{4,6}", t):
        return f"{t}.TW"
    return t


def _fetch_sp500_from_wikipedia() -> List[str]:
    """Fetch S&P 500 constituents from Wikipedia."""
    import bs4

    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    resp.raise_for_status()
    soup = bs4.BeautifulSoup(resp.text, "lxml")
    table = soup.find("table", {"id": "constituents"})
    tickers: List[str] = []
    if table:
        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")
            if cols:
                sym = cols[0].get_text(strip=True).replace(".", "-")
                if sym:
                    tickers.append(sym)
    return tickers


def _fetch_nasdaq100_from_wikipedia() -> List[str]:
    """Fetch NASDAQ-100 constituents from Wikipedia."""
    import bs4

    url = "https://en.wikipedia.org/wiki/Nasdaq-100"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    resp.raise_for_status()
    soup = bs4.BeautifulSoup(resp.text, "lxml")
    table = soup.find("table", {"id": "constituents"})
    tickers: List[str] = []
    if table:
        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")
            if cols:
                sym = cols[1].get_text(strip=True) if len(cols) > 1 else cols[0].get_text(strip=True)
                if sym and re.fullmatch(r"[A-Z.\-]+", sym):
                    tickers.append(sym.replace(".", "-"))
    return tickers


def resolve_target(target: str, output_dir: Optional[str] = None) -> TargetSpec:
    """Analyze `{target}` (single stock or stock pool) and route to `data/{target}/`."""
    cleaned = target.strip()
    key = cleaned.lower()
    slug = re.sub(r"[^a-z0-9._-]+", "_", key).strip("_")

    if key in POOL_ALIASES:
        pool_name, benchmark, market = POOL_ALIASES[key]
        if pool_name == "TW50":
            tickers = list(TW50_CONSTITUENTS)
        elif pool_name == "TW100":
            tickers = list(TW100_CONSTITUENTS)
        elif pool_name == "SOX":
            tickers = list(SOX_CONSTITUENTS)
        elif pool_name == "MAG7":
            tickers = list(MAG7_CONSTITUENTS)
        elif pool_name == "SP500":
            tickers = _fetch_sp500_from_wikipedia()
        elif pool_name == "NASDAQ100":
            tickers = _fetch_nasdaq100_from_wikipedia()
        else:
            tickers = []
        target_type = "pool"
    elif "," in cleaned:
        raw_list = [normalize_ticker(x) for x in cleaned.split(",") if x.strip()]
        tickers = list(dict.fromkeys(raw_list))
        tw_count = sum(1 for t in tickers if is_taiwan_ticker(t))
        if tw_count == len(tickers):
            market, benchmark = "TW", "0050.TW"
        elif tw_count == 0:
            market, benchmark = "US", "SPY"
        else:
            market, benchmark = "MIXED", "SPY"
        slug = re.sub(r"[^a-z0-9_]+", "_", key)
        target_type = "pool"
    else:
        norm_t = normalize_ticker(cleaned)
        tickers = [norm_t]
        is_tw = is_taiwan_ticker(norm_t)
        market = "TW" if is_tw else "US"
        benchmark = "0050.TW" if is_tw else "SPY"
        slug = norm_t.lower()
        target_type = "single"

    out_dir = output_dir or str(Path("data") / slug)
    return TargetSpec(
        raw_target=target,
        slug=slug,
        target_type=target_type,
        market=market,
        benchmark=benchmark,
        tickers=tickers,
        output_dir=out_dir,
        resolved_at=datetime.now().isoformat(timespec="seconds"),
    )


def save_universe_json(spec: TargetSpec, status_map: dict, out_path: Path) -> None:
    """Persist universe metadata and per-ticker fetch status to universe.json."""
    payload = spec.to_dict()
    payload["total_constituents"] = len(spec.tickers)
    payload["success_count"] = sum(1 for v in status_map.values() if v.get("ok"))
    payload["failed_count"] = len(spec.tickers) - payload["success_count"]
    payload["tickers_status"] = status_map
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
