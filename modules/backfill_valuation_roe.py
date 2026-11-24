"""
modules/backfill_valuation_roe.py
為本地台股 SQLite 資料庫補齊歷史日頻估值 (PE / PB / 殖利率 / 隱含 ROE) 與季頻 ROE / 股東權益欄位。

用法：
  python -m modules.backfill_valuation_roe --db data/tw50/tw50_2026.db --workers 4
"""
from __future__ import annotations

import argparse
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
import yfinance as yf

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


def _fetch_finmind_per(stock_id: str, start_date: str, end_date: str, retries: int = 4) -> pd.DataFrame:
    """Fetch daily official TWSE/TPEx PE, PB, and Dividend Yield from FinMind TaiwanStockPER."""
    params = {
        "dataset": "TaiwanStockPER",
        "data_id": stock_id,
        "start_date": start_date,
        "end_date": end_date,
    }
    for attempt in range(retries):
        try:
            resp = requests.get(FINMIND_URL, params=params, timeout=15)
            if resp.status_code == 200:
                payload = resp.json()
                if payload.get("status") == 200:
                    rows = payload.get("data", [])
                    if not rows:
                        return pd.DataFrame(columns=["date", "pe_ratio", "pb_ratio", "dividend_yield", "roe_implied_pct"])
                    df = pd.DataFrame(rows)
                    out = pd.DataFrame({
                        "date": df["date"].astype(str),
                        "pe_ratio": pd.to_numeric(df.get("PER"), errors="coerce"),
                        "pb_ratio": pd.to_numeric(df.get("PBR"), errors="coerce"),
                        "dividend_yield": pd.to_numeric(df.get("dividend_yield"), errors="coerce"),
                    })
                    # Zero PE in TWSE means negative/unavailable earnings -> set NaN for clean analysis
                    out.loc[out["pe_ratio"] <= 0, "pe_ratio"] = np.nan
                    out.loc[out["pb_ratio"] <= 0, "pb_ratio"] = np.nan
                    out["roe_implied_pct"] = np.where(
                        (out["pe_ratio"] > 0) & (out["pb_ratio"] > 0),
                        np.round((out["pb_ratio"] / out["pe_ratio"]) * 100.0, 2),
                        np.nan,
                    )
                    return out.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)
            if resp.status_code in (429, 502, 503, 504):
                time.sleep(1.5 * (2 ** attempt))
                continue
        except requests.RequestException:
            time.sleep(1.0 * (attempt + 1))
    return pd.DataFrame(columns=["date", "pe_ratio", "pb_ratio", "dividend_yield", "roe_implied_pct"])


def _fetch_yf_equity(ticker: str, retries: int = 3) -> dict[str, float]:
    """Fetch quarterly Stockholders Equity (in TWD 億 / 1e8) from yfinance balance sheet."""
    for attempt in range(retries):
        try:
            bs = yf.Ticker(ticker).quarterly_balance_sheet
            if bs is None or bs.empty:
                return {}
            equity_row = None
            for key in ("Common Stock Equity", "Stockholders Equity", "Total Equity Gross Minority Interest"):
                if key in bs.index:
                    equity_row = bs.loc[key]
                    break
            if equity_row is None:
                return {}
            result: dict[str, float] = {}
            for col, val in equity_row.items():
                if pd.notnull(val) and float(val) != 0.0:
                    qend = pd.Timestamp(col).strftime("%Y-%m-%d")
                    result[qend] = round(float(val) / 1e8, 2)  # TWD 億
            return result
        except Exception:
            time.sleep(1.0 * (attempt + 1))
    return {}


def _fetch_one(ticker: str, start_date: str, end_date: str) -> dict[str, Any]:
    stock_id = ticker.split(".")[0].strip()
    per_df = _fetch_finmind_per(stock_id, start_date, end_date)
    if not per_df.empty:
        per_df.insert(0, "ticker", ticker)
    eq_map = _fetch_yf_equity(ticker)
    return {"ticker": ticker, "per_df": per_df, "eq_map": eq_map}


def backfill_db(db_path: Path, workers: int = 4) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        sd = pd.read_sql_query("SELECT ticker, date FROM stock_daily ORDER BY ticker, date", conn)
        tickers = sorted(sd["ticker"].unique().tolist())
        start_date = str(sd["date"].min())
        end_date = str(sd["date"].max())
        print(f"Target DB: {db_path} | Tickers: {len(tickers)} | Date range: {start_date} ~ {end_date}")

        per_frames: list[pd.DataFrame] = []
        eq_maps: dict[str, dict[str, float]] = {}

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(_fetch_one, t, start_date, end_date): t for t in tickers}
            done = 0
            for fut in as_completed(futs):
                res = fut.result()
                done += 1
                if not res["per_df"].empty:
                    per_frames.append(res["per_df"])
                if res["eq_map"]:
                    eq_maps[res["ticker"]] = res["eq_map"]
                if done % 10 == 0 or done == len(tickers):
                    print(f"  Progress: {done}/{len(tickers)} (PER ok={len(per_frames)}, Equity ok={len(eq_maps)})")

        # 1. Build daily_valuation aligned to stock_daily (ticker, date)
        if per_frames:
            val_raw = pd.concat(per_frames, ignore_index=True)
            val_aligned = sd.merge(val_raw, on=["ticker", "date"], how="left")
            for col in ("pe_ratio", "pb_ratio", "dividend_yield", "roe_implied_pct"):
                val_aligned[col] = val_aligned.groupby("ticker")[col].ffill().bfill()
            val_aligned.to_sql("daily_valuation", conn, index=False, if_exists="replace")

            # Merge into daily_factors (replacing existing valuation cols if re-run)
            df_fac = pd.read_sql_query("SELECT * FROM daily_factors", conn)
            drop_existing = [c for c in ("pe_ratio", "pb_ratio", "dividend_yield", "roe_implied_pct") if c in df_fac.columns]
            if drop_existing:
                df_fac = df_fac.drop(columns=drop_existing)
            df_fac = df_fac.merge(val_aligned, on=["ticker", "date"], how="left")
            df_fac.to_sql("daily_factors", conn, index=False, if_exists="replace")
            print(f"Updated `daily_valuation` & `daily_factors`: {len(val_aligned)} rows, PE non-null={val_aligned['pe_ratio'].notnull().sum()}, PB non-null={val_aligned['pb_ratio'].notnull().sum()}")
        else:
            val_aligned = pd.DataFrame()
            print("WARNING: No FinMind PER data fetched.")

        # 2. Update quarterly_fundamentals with stockholders_equity, roe_q_ann_pct, roe_ttm_pct
        qf = pd.read_sql_query("SELECT * FROM quarterly_fundamentals ORDER BY ticker, quarter_end", conn)
        for col in ("stockholders_equity", "roe_q_ann_pct", "roe_ttm_pct"):
            if col in qf.columns:
                qf = qf.drop(columns=[col])

        qf["stockholders_equity"] = [
            eq_maps.get(t, {}).get(q, np.nan)
            for t, q in zip(qf["ticker"], qf["quarter_end"])
        ]

        # Compute single-quarter annualized ROE and TTM ROE per ticker
        roe_q_list = []
        roe_ttm_list = []
        for t, grp in qf.groupby("ticker", sort=False):
            g = grp.sort_values("quarter_end")
            ni = pd.to_numeric(g["net_income"], errors="coerce")
            eq = pd.to_numeric(g["stockholders_equity"], errors="coerce")
            # Single-quarter annualized ROE
            rq = np.where((eq > 0) & ni.notnull(), np.round((ni * 4.0 / eq) * 100.0, 2), np.nan)
            # Rolling up to 4 quarters annualized TTM ROE
            roll_sum = ni.rolling(4, min_periods=1).sum()
            roll_cnt = ni.rolling(4, min_periods=1).count()
            ann_ni = np.where(roll_cnt > 0, roll_sum * (4.0 / roll_cnt), np.nan)
            rttm = np.where((eq > 0) & pd.notnull(ann_ni), np.round((ann_ni / eq) * 100.0, 2), np.nan)
            roe_q_list.append(pd.Series(rq, index=g.index))
            roe_ttm_list.append(pd.Series(rttm, index=g.index))

        qf["roe_q_ann_pct"] = pd.concat(roe_q_list).reindex(qf.index)
        qf["roe_ttm_pct"] = pd.concat(roe_ttm_list).reindex(qf.index)
        qf.to_sql("quarterly_fundamentals", conn, index=False, if_exists="replace")
        print(f"Updated `quarterly_fundamentals`: {len(qf)} rows, equity non-null={qf['stockholders_equity'].notnull().sum()}, roe_ttm_pct non-null={qf['roe_ttm_pct'].notnull().sum()}")

        # 3. Enrich cross_sectional_summary if present
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "cross_sectional_summary" in tables and not val_aligned.empty:
            cs = pd.read_sql_query("SELECT * FROM cross_sectional_summary", conn)
            for col in ("pe_ratio", "pb_ratio", "dividend_yield", "roe_implied_pct", "roe_ttm_pct"):
                if col in cs.columns:
                    cs = cs.drop(columns=[col])
            latest_val = val_aligned.sort_values("date").groupby("ticker").tail(1)[
                ["ticker", "pe_ratio", "pb_ratio", "dividend_yield", "roe_implied_pct"]
            ]
            latest_roe = qf[qf["roe_ttm_pct"].notnull()].sort_values("quarter_end").groupby("ticker").tail(1)[
                ["ticker", "roe_ttm_pct"]
            ]
            cs = cs.merge(latest_val, on="ticker", how="left").merge(latest_roe, on="ticker", how="left")
            cs.to_sql("cross_sectional_summary", conn, index=False, if_exists="replace")
            print(f"Updated `cross_sectional_summary`: {len(cs)} rows")

            # Print verification sample
            print("\n=== VERIFICATION SAMPLE (TW50 Top 10 by ROE TTM %) ===")
            sample_cols = ["ticker", "name", "latest_close", "pe_ratio", "pb_ratio", "dividend_yield", "roe_implied_pct", "roe_ttm_pct"]
            print(cs[sample_cols].sort_values("roe_ttm_pct", ascending=False).head(10).to_string(index=False))
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical PE, PB, Dividend Yield, and ROE into Taiwan SQLite DB.")
    parser.add_argument("--db", default="data/tw50/tw50_2026.db", help="Path to SQLite database")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent worker threads")
    args = parser.parse_args()
    backfill_db(Path(args.db), workers=args.workers)


if __name__ == "__main__":
    main()
