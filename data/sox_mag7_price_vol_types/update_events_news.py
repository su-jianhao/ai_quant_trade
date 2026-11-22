#!/usr/bin/env python3
"""
data/sox_mag7_price_vol_types/update_events_news.py

On-demand, incremental Events & Major News SQLite database builder for SOX 30 & Mag 7.
Database path: data/sox_mag7_price_vol_types/events_news.db

Usage:
  python data/sox_mag7_price_vol_types/update_events_news.py --symbols INTC,QCOM
  python data/sox_mag7_price_vol_types/update_events_news.py --symbols NVDA,AVGO
"""

import argparse
import json
import os
import sqlite3
import urllib.request
from datetime import datetime
from typing import Dict, List

import numpy as np
import pandas as pd
import yfinance as yf

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(SCRIPT_DIR, "events_news.db")
PV_DB = os.path.join(SCRIPT_DIR, "price_vol_analysis.db")
INTC_QCOM_DB = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "intc_qcom", "intc_qcom_2026.db"))

# SEC EDGAR CIK map for major SOX / Mag 7 stocks (expandable on demand)
CIK_MAP = {
    "INTC": "0000050863",
    "QCOM": "0000804328",
    "NVDA": "0001045810",
    "AMD": "0000002488",
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "GOOGL": "0001652044",
    "AMZN": "0001018724",
    "META": "0001326801",
    "TSLA": "0001318605",
    "AVGO": "0001730168",
    "MU": "0000723125",
    "TXN": "0000097476",
    "AMAT": "0000006951",
    "LRCX": "0000707549",
    "KLAC": "0000319201",
    "ASML": "0000937966",
    "TSM": "0001046179",
}

SEC_8K_ITEM_DESC = {
    "1.01": "重大合約 / 併購協議 (Material Agreement)",
    "1.02": "重大合約終止 (Termination of Agreement)",
    "2.01": "資產收購或處分 (Acquisition/Disposition)",
    "2.02": "財報與營運業績發布 (Earnings Results)",
    "2.05": "重組與裁員計畫 (Restructuring / Layoffs)",
    "2.06": "重大資產減損 (Material Impairment)",
    "3.01": "退市或上市合規通知",
    "4.02": "財報重編警示 (Non-Reliance on Financials)",
    "5.02": "高層 / CEO / 董事異動 (Executive Change)",
    "5.03": "公司章程修訂",
    "5.07": "股東大會表決結果",
    "7.01": "Reg FD 重大資訊揭露 (Guidance / Update)",
    "8.01": "其他重大事件 (Other Material Event)",
}

SEC_HEADERS = {"User-Agent": "AIQuantTradeResearch/1.0 (quant-research@example.com)"}


def init_db(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS events_structured (
            event_id TEXT PRIMARY KEY,
            ticker TEXT NOT NULL,
            event_date TEXT NOT NULL,
            release_timing TEXT,
            event_type TEXT NOT NULL,
            headline TEXT NOT NULL,
            details TEXT,
            eps_estimate REAL,
            eps_actual REAL,
            surprise_pct REAL,
            price_move_pct REAL,
            rvol REAL,
            sentiment TEXT,
            source TEXT,
            url TEXT
        );

        CREATE TABLE IF NOT EXISTS news_articles (
            news_id TEXT PRIMARY KEY,
            ticker TEXT NOT NULL,
            published_date TEXT NOT NULL,
            published_ts TEXT,
            headline TEXT NOT NULL,
            summary TEXT,
            publisher TEXT,
            sentiment TEXT,
            importance TEXT,
            url TEXT
        );

        CREATE TABLE IF NOT EXISTS fetch_checkpoint (
            ticker TEXT PRIMARY KEY,
            last_updated TEXT NOT NULL,
            start_date TEXT,
            end_date TEXT,
            earnings_count INTEGER DEFAULT 0,
            sec_8k_count INTEGER DEFAULT 0,
            dividend_count INTEGER DEFAULT 0,
            anomaly_count INTEGER DEFAULT 0,
            news_count INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_ev_ticker_date ON events_structured(ticker, event_date);
        CREATE INDEX IF NOT EXISTS idx_ev_type ON events_structured(event_type);
        CREATE INDEX IF NOT EXISTS idx_news_ticker_date ON news_articles(ticker, published_date);
        """
    )
    conn.commit()


def load_daily_moves(sym: str) -> pd.DataFrame:
    """Load daily close/volume from PV_DB (+ INTC_QCOM_DB if available) to compute returns & rvol."""
    frames = []
    if os.path.exists(PV_DB):
        c1 = sqlite3.connect(PV_DB)
        df1 = pd.read_sql_query(
            "SELECT date, open, close, volume, regime FROM bar_price_vol WHERE symbol=? ORDER BY date ASC",
            c1, params=(sym,),
        )
        c1.close()
        if len(df1) > 0:
            frames.append(df1)

    if os.path.exists(INTC_QCOM_DB) and sym in ("INTC", "QCOM"):
        c2 = sqlite3.connect(INTC_QCOM_DB)
        df2 = pd.read_sql_query(
            "SELECT date, raw_open AS open, raw_close AS close, volume FROM stock_daily WHERE ticker=? ORDER BY date ASC",
            c2, params=(sym,),
        )
        c2.close()
        if len(df2) > 0:
            df2["regime"] = ""
            frames.append(df2)

    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["date"], keep="first").sort_values("date").reset_index(drop=True)
    df["ret_pct"] = (df["close"].pct_change() * 100.0).round(2)
    df["gap_pct"] = ((df["open"] / df["close"].shift(1) - 1.0) * 100.0).round(2)
    df["vol_sma20"] = df["volume"].rolling(20).mean()
    df["rvol"] = (df["volume"] / df["vol_sma20"].replace(0, np.nan)).round(2)
    return df


def fetch_yfinance_events(sym: str, move_map: Dict[str, tuple], start_date: str) -> tuple:
    tk = yf.Ticker(sym)
    struct_rows = []
    news_rows = []
    earn_cnt = div_cnt = 0

    # 1. Earnings dates
    try:
        ed = tk.get_earnings_dates(limit=40)
        if ed is not None and not ed.empty:
            for idx, r in ed.iterrows():
                dt_ts = pd.Timestamp(idx)
                d_str = dt_ts.strftime("%Y-%m-%d")
                if d_str < start_date:
                    continue
                hour = dt_ts.hour
                timing = "BMO" if hour < 12 else ("AMC" if hour >= 16 else "INTRADAY")
                eps_est = None if pd.isna(r.get("EPS Estimate")) else round(float(r.get("EPS Estimate")), 3)
                eps_act = None if pd.isna(r.get("Reported EPS")) else round(float(r.get("Reported EPS")), 3)
                surp = None if pd.isna(r.get("Surprise(%)")) else round(float(r.get("Surprise(%)")), 2)
                pm, rv = move_map.get(d_str, (None, None))
                if eps_act is not None:
                    sent = "BULLISH" if (surp is not None and surp > 0) else ("BEARISH" if (surp is not None and surp < 0) else "NEUTRAL")
                    hl = f"{sym} 季度財報發布：EPS ${eps_act} vs 預期 ${eps_est} (驚喜 {surp:+.2f}%)" if (eps_est is not None and surp is not None) else f"{sym} 季度財報發布 (EPS ${eps_act})"
                else:
                    sent = "NEUTRAL"
                    hl = f"{sym} 預計季度財報發布日 (預期 EPS ${eps_est})" if eps_est is not None else f"{sym} 預計季度財報發布日"

                struct_rows.append((
                    f"{sym}_EARN_{d_str}", sym, d_str, timing, "EARNINGS", hl,
                    f"EPS Est={eps_est}, Act={eps_act}, Surprise={surp}%",
                    eps_est, eps_act, surp, pm, rv, sent, "yfinance", f"https://finance.yahoo.com/quote/{sym}/"
                ))
                earn_cnt += 1
    except Exception as e:
        print(f"  [Warn] {sym} earnings fetch error: {e}")

    # 2. Dividends
    try:
        divs = tk.dividends
        if divs is not None and len(divs) > 0:
            for idx, val in divs.items():
                d_str = pd.Timestamp(idx).strftime("%Y-%m-%d")
                if d_str < start_date:
                    continue
                pm, rv = move_map.get(d_str, (None, None))
                struct_rows.append((
                    f"{sym}_DIV_{d_str}", sym, d_str, "BMO", "DIVIDEND",
                    f"{sym} 除息日：現金股利 ${float(val):.4f}/股",
                    f"Cash dividend ${float(val):.4f}",
                    None, None, None, pm, rv, "NEUTRAL", "yfinance", f"https://finance.yahoo.com/quote/{sym}/"
                ))
                div_cnt += 1
    except Exception as e:
        print(f"  [Warn] {sym} dividends fetch error: {e}")

    # 3. Recent Yahoo Finance News
    try:
        raw_news = tk.news or []
        for item in raw_news:
            content = item.get("content", item) if isinstance(item, dict) else {}
            title = content.get("title") or item.get("title") or ""
            if not title:
                continue
            pub_date_raw = content.get("pubDate") or item.get("providerPublishTime")
            if isinstance(pub_date_raw, (int, float)):
                dt_obj = datetime.utcfromtimestamp(pub_date_raw)
                p_date = dt_obj.strftime("%Y-%m-%d")
                p_ts = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(pub_date_raw, str):
                p_date = pub_date_raw[:10]
                p_ts = pub_date_raw
            else:
                p_date = datetime.now().strftime("%Y-%m-%d")
                p_ts = p_date
            summary = content.get("summary") or ""
            provider = (content.get("provider") or {}).get("displayName") or item.get("publisher") or "Yahoo Finance"
            url = (content.get("canonicalUrl") or {}).get("url") or item.get("link") or ""
            nid = item.get("id") or f"{sym}_NEWS_{p_date}_{abs(hash(title)) % 1000000}"
            news_rows.append((
                str(nid), sym, p_date, p_ts, title, summary[:600], provider, "NEUTRAL", "RECENT", url
            ))
    except Exception as e:
        print(f"  [Warn] {sym} news fetch error: {e}")

    return struct_rows, news_rows, earn_cnt, div_cnt


def fetch_sec_8k(sym: str, move_map: Dict[str, tuple], start_date: str) -> List[tuple]:
    cik = CIK_MAP.get(sym)
    if not cik:
        return []
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    rows = []
    try:
        req = urllib.request.Request(url, headers=SEC_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        fdates = recent.get("filingDate", [])
        rdates = recent.get("reportDate", [])
        accs = recent.get("accessionNumber", [])
        items_list = recent.get("items", [])
        docs = recent.get("primaryDocument", [])

        cik_int = str(int(cik))
        for form, fdate, rdate, acc, items, doc in zip(forms, fdates, rdates, accs, items_list, docs):
            if form != "8-K":
                continue
            if fdate < start_date:
                continue
            item_codes = items if isinstance(items, list) else ([x.strip() for x in str(items).split(",") if x.strip()] if items else [])
            # Keep meaningful material 8-K items (skip pure 9.01 exhibit-only)
            key_items = [c for c in item_codes if c in SEC_8K_ITEM_DESC]
            if not key_items:
                continue
            desc = " / ".join(SEC_8K_ITEM_DESC[c] for c in key_items[:3])
            acc_clean = acc.replace("-", "")
            doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{doc}"
            pm, rv = move_map.get(fdate, (None, None))
            sent = "BULLISH" if (pm is not None and pm >= 3.0) else ("BEARISH" if (pm is not None and pm <= -3.0) else "NEUTRAL")
            rows.append((
                f"{sym}_8K_{acc_clean}", sym, fdate, "FILING", "SEC_8K",
                f"{sym} SEC 8-K 重大公告 [{','.join(key_items)}]: {desc}",
                f"Report Date: {rdate} | Items: {','.join(item_codes)}",
                None, None, None, pm, rv, sent, "SEC EDGAR", doc_url
            ))
    except Exception as e:
        print(f"  [Warn] {sym} SEC EDGAR 8-K fetch error: {e}")
    return rows


def detect_anomalies(sym: str, df_moves: pd.DataFrame, start_date: str) -> List[tuple]:
    if df_moves.empty:
        return []
    sub = df_moves[df_moves["date"] >= start_date].copy()
    mask = (sub["ret_pct"].abs() >= 7.0) | ((sub["ret_pct"].abs() >= 5.0) & (sub["rvol"] >= 2.0))
    anom = sub[mask]
    rows = []
    for _, r in anom.iterrows():
        d_str = r["date"]
        ret = float(r["ret_pct"])
        rv = None if pd.isna(r["rvol"]) else float(r["rvol"])
        gap = None if pd.isna(r["gap_pct"]) else float(r["gap_pct"])
        direction = "暴漲" if ret > 0 else "暴跌"
        sent = "BULLISH" if ret > 0 else "BEARISH"
        hl = f"{sym} 異常{direction} {ret:+.2f}%（量比 {rv if rv else 0:.2f}x，跳空 {gap if gap is not None else 0:+.2f}%）"
        rows.append((
            f"{sym}_ANOM_{d_str}", sym, d_str, "INTRADAY", "ANOMALY_MOVE", hl,
            f"Close=${r['close']:.2f}, Ret={ret:+.2f}%, Gap={gap}%, RVol={rv}x, Regime={r.get('regime','')}",
            None, None, None, ret, rv, sent, "Price/Vol Detector", ""
        ))
    return rows


def main():
    parser = argparse.ArgumentParser(description="Incremental SOX/Mag7 Events & News SQLite builder")
    parser.add_argument("--symbols", default="INTC,QCOM", help="Comma-separated symbols to add/update")
    parser.add_argument("--start", default="2020-01-01", help="Start date (default: 2020-01-01)")
    parser.add_argument("--db", default=DEFAULT_DB, help="Output SQLite DB path")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    conn = sqlite3.connect(args.db)
    init_db(conn)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for sym in symbols:
        print(f"\n[Events/News] Processing {sym} (from {args.start})...")
        df_moves = load_daily_moves(sym)
        move_map = {
            r["date"]: (None if pd.isna(r["ret_pct"]) else float(r["ret_pct"]), None if pd.isna(r["rvol"]) else float(r["rvol"]))
            for _, r in df_moves.iterrows()
        }
        end_d = df_moves["date"].max() if len(df_moves) > 0 else ""

        yf_struct, yf_news, earn_cnt, div_cnt = fetch_yfinance_events(sym, move_map, args.start)
        sec_rows = fetch_sec_8k(sym, move_map, args.start)
        anom_rows = detect_anomalies(sym, df_moves, args.start)

        all_struct = yf_struct + sec_rows + anom_rows
        conn.executemany(
            """INSERT OR REPLACE INTO events_structured
               (event_id, ticker, event_date, release_timing, event_type, headline, details,
                eps_estimate, eps_actual, surprise_pct, price_move_pct, rvol, sentiment, source, url)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            all_struct,
        )
        conn.executemany(
            """INSERT OR REPLACE INTO news_articles
               (news_id, ticker, published_date, published_ts, headline, summary, publisher, sentiment, importance, url)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            yf_news,
        )
        conn.execute(
            """INSERT OR REPLACE INTO fetch_checkpoint
               (ticker, last_updated, start_date, end_date, earnings_count, sec_8k_count, dividend_count, anomaly_count, news_count)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (sym, now_str, args.start, end_d, earn_cnt, len(sec_rows), div_cnt, len(anom_rows), len(yf_news)),
        )
        conn.commit()
        print(f"  -> {sym}: Earnings={earn_cnt}, SEC_8K={len(sec_rows)}, Dividends={div_cnt}, Anomalies={len(anom_rows)}, RecentNews={len(yf_news)}")

    conn.close()
    print(f"\n[Done] Database ready: {args.db} ({os.path.getsize(args.db)/1024:.1f} KB)")


if __name__ == "__main__":
    main()
