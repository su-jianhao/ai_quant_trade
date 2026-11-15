"""Main multi-timeframe quantitative data generator for single stocks and stock pools."""

from __future__ import annotations

import argparse
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from modules.gui_builder import _df_to_records, build_gui_html
from modules.indicators import (
    aggregate_monthly_factors,
    build_priority_board,
    cleanse_ohlcv,
    compute_daily_factors,
)
from modules.target_resolver import (
    TargetSpec,
    is_taiwan_ticker,
    resolve_target,
    save_universe_json,
)
from modules.tw_chips_fetcher import fetch_taiwan_chips


def _fetch_macro_series(start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch daily macro benchmarks (NQ=F, ES=F, ^VIX) aligned by date."""
    macro_map = {"NQ=F": "nq", "ES=F": "es", "^VIX": "vix"}
    frames = []
    for sym, prefix in macro_map.items():
        try:
            df = yf.Ticker(sym).history(start=start_date, end=end_date, auto_adjust=False)
            if df.empty:
                continue
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            df.index = pd.to_datetime(df.index).normalize()
            df = df[~df.index.duplicated(keep="last")].sort_index()
            sub = pd.DataFrame({
                f"{prefix}_close": df["Close"].round(2),
                f"{prefix}_pct": (df["Close"].pct_change() * 100.0).round(2),
            }, index=df.index)
            frames.append(sub)
        except Exception:
            continue
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, axis=1).sort_index().ffill()


def _extract_quarterly_fundamentals(ticker: str, is_tw: bool) -> pd.DataFrame:
    """Extract quarterly income/cashflow/balance sheet fundamentals via yfinance."""
    try:
        tk = yf.Ticker(ticker)
        inc = tk.quarterly_income_stmt
        bs = tk.quarterly_balance_sheet
        cf = tk.quarterly_cashflow
        if inc is None or inc.empty:
            return pd.DataFrame()

        scale = 1e8 if is_tw else 1e6  # 億 (1e8) for TW, Million for US
        currency = "TWD(億)" if is_tw else "USD(M)"
        cols = sorted(list(inc.columns))
        rows = []
        for dt in cols:
            q_str = pd.Timestamp(dt).strftime("%Y-%m-%d")

            def _pick(df_src: pd.DataFrame | None, keys: list[str]) -> float | None:
                if df_src is None or df_src.empty or dt not in df_src.columns:
                    return None
                for k in keys:
                    if k in df_src.index:
                        val = df_src.loc[k, dt]
                        if pd.notna(val):
                            return round(float(val) / scale, 2)
                return None

            rev = _pick(inc, ["Total Revenue", "Operating Revenue"])
            ni = _pick(inc, ["Net Income", "Net Income Common Stockholders"])
            ocf = _pick(cf, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"])
            capex = _pick(cf, ["Capital Expenditure", "Purchase Of PPE"])
            fcf = round(ocf - abs(capex), 2) if (ocf is not None and capex is not None) else _pick(cf, ["Free Cash Flow"])

            debt = _pick(bs, ["Total Debt"])
            eq = _pick(bs, ["Stockholders Equity", "Common Stock Equity"])
            de_ratio = round((debt / eq) * 100.0, 2) if (debt is not None and eq and eq != 0) else None

            ca = _pick(bs, ["Current Assets"])
            cl = _pick(bs, ["Current Liabilities"])
            curr_ratio = round(ca / cl, 2) if (ca is not None and cl and cl != 0) else None

            rows.append({
                "ticker": ticker,
                "quarter_end": q_str,
                "revenue": rev,
                "net_income": ni,
                "ocf": ocf,
                "capex": capex,
                "fcf": fcf,
                "debt_to_equity": de_ratio,
                "current_ratio": curr_ratio,
                "currency": currency,
            })
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame()


def _load_existing_cache(db_path: Path) -> dict[str, Any]:
    """Load existing SQLite tables for incremental sync."""
    cache: dict[str, Any] = {
        "daily": {},
        "chips": {},
        "quarterly": {},
        "names": {},
        "min_last_date": None,
    }
    if not db_path.exists():
        return cache

    conn = sqlite3.connect(db_path)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "stock_daily" in tables:
            df = pd.read_sql_query("SELECT * FROM stock_daily ORDER BY ticker, date", conn)
            if not df.empty:
                last_dates = df.groupby("ticker")["date"].max()
                cache["min_last_date"] = str(last_dates.min())
                for t, grp in df.groupby("ticker", sort=False):
                    g = grp.copy()
                    g["Date"] = pd.to_datetime(g["date"])
                    g = g.set_index("Date").sort_index()
                    g["Open"] = g["raw_open"]
                    g["High"] = g["raw_high"]
                    g["Low"] = g["raw_low"]
                    g["Close"] = g["raw_close"]
                    g["Adj Close"] = g["adj_close"]
                    g["Volume"] = g["volume"]
                    g["Dividends"] = g.get("dividends", 0.0)
                    cache["daily"][t] = g[["Open", "High", "Low", "Close", "Adj Close", "Volume", "Dividends"]]

        if "taiwan_chips_daily" in tables:
            cdf = pd.read_sql_query("SELECT * FROM taiwan_chips_daily ORDER BY ticker, date", conn)
            for t, grp in cdf.groupby("ticker", sort=False):
                cache["chips"][t] = grp.reset_index(drop=True)

        if "quarterly_fundamentals" in tables:
            qdf = pd.read_sql_query("SELECT * FROM quarterly_fundamentals ORDER BY ticker, quarter_end", conn)
            for t, grp in qdf.groupby("ticker", sort=False):
                cache["quarterly"][t] = grp.reset_index(drop=True)

        if "universe_meta" in tables:
            mdf = pd.read_sql_query("SELECT ticker, name FROM universe_meta", conn)
            cache["names"] = dict(zip(mdf["ticker"], mdf["name"]))
    finally:
        conn.close()
    return cache


def _process_single_ticker(
    ticker: str,
    year: int,
    warmup_start: str,
    end_date: str,
    macro_df: pd.DataFrame,
    fetch_chips: bool = True,
    cached_daily: pd.DataFrame | None = None,
    cached_chips: pd.DataFrame | None = None,
    cached_quarterly: pd.DataFrame | None = None,
    cached_name: str | None = None,
) -> dict[str, Any]:
    """Fetch (full or delta), cleanse, compute factors, and package data for a single ticker."""
    is_tw = is_taiwan_ticker(ticker)
    last_err = ""
    raw_df = pd.DataFrame()

    fetch_start = warmup_start
    if cached_daily is not None and not cached_daily.empty:
        last_dt = cached_daily.index.max()
        fetch_start = (last_dt - timedelta(days=7)).strftime("%Y-%m-%d")

    for attempt in range(3):
        try:
            raw_df = yf.Ticker(ticker).history(start=fetch_start, end=end_date, auto_adjust=False)
            if not raw_df.empty:
                break
        except Exception as exc:
            last_err = str(exc)
        time.sleep(1.0 * (attempt + 1))

    if cached_daily is not None and not cached_daily.empty:
        if not raw_df.empty:
            if raw_df.index.tz is not None:
                raw_df.index = raw_df.index.tz_localize(None)
            raw_df.index = pd.to_datetime(raw_df.index).normalize()
            cols = ["Open", "High", "Low", "Close", "Adj Close", "Volume", "Dividends"]
            delta = raw_df[[c for c in cols if c in raw_df.columns]].copy()
            merged = pd.concat([cached_daily, delta])
            raw_df = merged[~merged.index.duplicated(keep="last")].sort_index()
        else:
            raw_df = cached_daily.copy()

    if raw_df.empty:
        return {"ticker": ticker, "ok": False, "error": last_err or "Empty OHLCV"}

    cleansed = cleanse_ohlcv(raw_df, is_tw=is_tw)
    factored = compute_daily_factors(cleansed)

    if not macro_df.empty:
        factored = factored.join(macro_df, how="left")
        for col in ["nq_close", "nq_pct", "es_close", "es_pct", "vix_close", "vix_pct"]:
            if col in factored.columns:
                factored[col] = factored[col].ffill()

    year_start = pd.Timestamp(f"{year}-01-01")
    df_year = factored[factored.index >= year_start].copy()
    if df_year.empty:
        df_year = factored.tail(252).copy()

    chips_year = pd.DataFrame()
    stock_name = cached_name or ticker
    latest_date_str = df_year.index[-1].strftime("%Y-%m-%d")

    if is_tw and fetch_chips:
        if cached_chips is not None and not cached_chips.empty:
            last_chips_dt = str(cached_chips["date"].max())
            if last_chips_dt >= latest_date_str:
                chips_year = cached_chips.copy()
            else:
                next_dt = (pd.Timestamp(last_chips_dt) + timedelta(days=1)).strftime("%Y-%m-%d")
                delta_chips, fetched_name = fetch_taiwan_chips(
                    ticker, start_date=next_dt, end_date=end_date, daily_df=df_year
                )
                if fetched_name != ticker:
                    stock_name = fetched_name
                if not delta_chips.empty:
                    chips_year = pd.concat([cached_chips, delta_chips], ignore_index=True)
                    chips_year = chips_year.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)
                else:
                    chips_year = cached_chips.copy()
        else:
            chips_full, stock_name = fetch_taiwan_chips(
                ticker, start_date=f"{year}-01-01", end_date=end_date, daily_df=df_year
            )
            if not chips_full.empty:
                chips_year = chips_full[chips_full["date"] >= f"{year}-01-01"].copy()

    monthly_df = aggregate_monthly_factors(df_year, chips_year if not chips_year.empty else None)
    monthly_df["ticker"] = ticker

    if cached_quarterly is not None and not cached_quarterly.empty:
        quarterly_df = cached_quarterly.copy()
    else:
        quarterly_df = _extract_quarterly_fundamentals(ticker, is_tw=is_tw)

    priority_rows = build_priority_board(ticker, df_year, chips_year if not chips_year.empty else None)

    return {
        "ticker": ticker,
        "name": stock_name,
        "ok": True,
        "is_tw": is_tw,
        "daily": df_year,
        "chips": chips_year,
        "monthly": monthly_df,
        "quarterly": quarterly_df,
        "priority": priority_rows,
    }


def _write_sqlite(
    db_path: Path,
    results: list[dict[str, Any]],
    spec: TargetSpec,
    cross_summary: list[dict[str, Any]],
    status_map: dict[str, dict[str, Any]],
    full_reset: bool = False,
) -> None:
    """Persist all multi-timeframe tables to SQLite (preserving extra tables on incremental sync)."""
    if full_reset and db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    try:
        daily_frames, factor_frames, monthly_frames, quarterly_frames, chips_frames, prio_rows = [], [], [], [], [], []
        daily_cols = ["raw_open", "raw_high", "raw_low", "raw_close", "adj_close", "volume", "dividends", "pct_change", "is_fillable"]

        for res in results:
            if not res.get("ok"):
                continue
            t = res["ticker"]
            dy = res["daily"].copy()
            dy["date"] = dy.index.strftime("%Y-%m-%d")
            dy["ticker"] = t

            daily_frames.append(dy[["ticker", "date"] + [c for c in daily_cols if c in dy.columns]])

            f_cols = [c for c in dy.columns if c not in daily_cols and c not in ("Open", "High", "Low", "Close", "Adj Close", "Volume", "Dividends", "Stock Splits", "adj_open", "adj_high", "adj_low")]
            factor_frames.append(dy[["ticker", "date"] + [c for c in f_cols if c not in ("ticker", "date")]])

            if not res["monthly"].empty:
                monthly_frames.append(res["monthly"])
            if not res["quarterly"].empty:
                quarterly_frames.append(res["quarterly"])
            if not res["chips"].empty:
                chips_frames.append(res["chips"])
            prio_rows.extend(res["priority"])

        if daily_frames:
            pd.concat(daily_frames, ignore_index=True).to_sql("stock_daily", conn, index=False, if_exists="replace")
        if factor_frames:
            pd.concat(factor_frames, ignore_index=True).to_sql("daily_factors", conn, index=False, if_exists="replace")
        if monthly_frames:
            pd.concat(monthly_frames, ignore_index=True).to_sql("monthly_factors", conn, index=False, if_exists="replace")
        if quarterly_frames:
            pd.concat(quarterly_frames, ignore_index=True).to_sql("quarterly_fundamentals", conn, index=False, if_exists="replace")
        if prio_rows:
            pd.DataFrame(prio_rows).to_sql("factor_priority_board", conn, index=False, if_exists="replace")
        if chips_frames:
            pd.concat(chips_frames, ignore_index=True).to_sql("taiwan_chips_daily", conn, index=False, if_exists="replace")

        if spec.target_type == "pool":
            meta_rows = [{"ticker": t, **info} for t, info in status_map.items()]
            pd.DataFrame(meta_rows).to_sql("universe_meta", conn, index=False, if_exists="replace")
            if cross_summary:
                pd.DataFrame(cross_summary).to_sql("cross_sectional_summary", conn, index=False, if_exists="replace")
    finally:
        conn.close()


def _write_markdown_report(
    md_path: Path,
    spec: TargetSpec,
    year: int,
    results: list[dict[str, Any]],
    cross_summary: list[dict[str, Any]],
) -> None:
    """Write structured Markdown summary ledger to data/{target}/<target>_<year>_data.md."""
    ok_res = [r for r in results if r.get("ok")]
    fail_res = [r for r in results if not r.get("ok")]

    lines = [
        f"# {spec.slug.upper()} ({year}) 多週期量化數據總賬",
        "",
        f"- **Target**: `{spec.raw_target}` (類型: `{spec.target_type}`, 市場: `{spec.market}`, 基準: `{spec.benchmark}`)",
        f"- **生成時間**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **覆蓋率**: {len(ok_res)} / {len(spec.tickers)} 檔標的成功",
        "",
    ]

    if fail_res:
        lines.append("## ⚠️ 拉取異常標的")
        for r in fail_res:
            lines.append(f"- `{r['ticker']}`: {r.get('error', 'Unknown error')}")
        lines.append("")

    if spec.target_type == "pool" and cross_summary:
        lines.append("## 📊 最新交易日橫截面強弱總覽")
        lines.append("")
        lines.append("| Ticker | 名稱 | 最新日期 | 收盤價 | 日漲跌% | YTD% | RSI(14) | MACD Hist | CYQ 獲利盤% | 三大法人合計(張) | 券資比% | 籌碼形態 |")
        lines.append("|:---|:---|:---|---:|---:|---:|---:|---:|---:|---:|---:|:---|")
        for r in cross_summary:
            lines.append(
                f"| {r['ticker']} | {r.get('name','-')} | {r['latest_date']} | {r['latest_close']} | "
                f"{r['pct_change']:+.2f}% | {r['ytd_return_pct']:+.2f}% | {r.get('rsi_14','-')} | "
                f"{r.get('macd_hist','-')} | {r.get('cyq_profit_ratio','-')}% | "
                f"{r.get('inst_total_net_lots','-')} | {r.get('short_margin_ratio','-')}% | {r.get('chip_pattern','-')} |"
            )
        lines.append("")
    elif ok_res:
        r = ok_res[0]
        dy = r["daily"].tail(30).iloc[::-1]
        lines.append(f"## 📈 {r['ticker']} 近 30 日核心量化明細")
        lines.append("")
        lines.append("| 日期 | 收盤價 | 漲跌% | 成交量 | RSI(14) | MACD Hist | CYQ 獲利盤% | CYQ 均價 |")
        lines.append("|:---|---:|---:|---:|---:|---:|---:|---:|")
        for idx, row in dy.iterrows():
            lines.append(
                f"| {idx.strftime('%Y-%m-%d')} | {row['raw_close']:.2f} | {row['pct_change']:+.2f}% | "
                f"{int(row['volume']):,} | {row.get('rsi_14', np.nan):.2f} | {row.get('macd_hist', np.nan):.2f} | "
                f"{row.get('cyq_profit_ratio', np.nan):.1f}% | {row.get('cyq_avg_cost', np.nan):.2f} |"
            )
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")


def run_pipeline(
    target: str,
    year: int,
    output_dir: str | None = None,
    workers: int = 8,
    fetch_chips: bool = True,
    mode: str = "auto",
) -> dict[str, Any]:
    """Execute full or incremental data generation pipeline for `{target}` into `data/{target}/`."""
    spec = resolve_target(target, output_dir=output_dir)
    out_path = Path(spec.output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    db_path = out_path / f"{spec.slug}_{year}.db"
    use_incremental = (mode == "incremental") or (mode == "auto" and db_path.exists())
    cache = _load_existing_cache(db_path) if use_incremental else {
        "daily": {}, "chips": {}, "quarterly": {}, "names": {}, "min_last_date": None
    }

    warmup_start = f"{year - 1}-01-01"
    end_date = f"{year + 1}-01-01"
    macro_start = warmup_start
    if use_incremental and cache["min_last_date"]:
        macro_start = (pd.Timestamp(cache["min_last_date"]) - timedelta(days=10)).strftime("%Y-%m-%d")

    sync_label = "INCREMENTAL" if (use_incremental and cache["daily"]) else "FULL"
    print(f"[Target:{sync_label}] {spec.raw_target} -> slug={spec.slug}, type={spec.target_type}, market={spec.market}, tickers={len(spec.tickers)}, out={out_path}")

    macro_df = _fetch_macro_series(macro_start, end_date)
    results: list[dict[str, Any]] = []

    max_workers = min(workers, max(1, len(spec.tickers)))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {
            pool.submit(
                _process_single_ticker,
                t, year, warmup_start, end_date, macro_df, fetch_chips,
                cache["daily"].get(t),
                cache["chips"].get(t),
                cache["quarterly"].get(t),
                cache["names"].get(t),
            ): t
            for t in spec.tickers
        }
        for fut in as_completed(futs):
            t = futs[fut]
            try:
                res = fut.result()
                results.append(res)
                status = "OK" if res.get("ok") else f"FAIL ({res.get('error')})"
                print(f"  [{len(results)}/{len(spec.tickers)}] {t}: {status}")
            except Exception as exc:
                results.append({"ticker": t, "ok": False, "error": str(exc)})
                print(f"  [{len(results)}/{len(spec.tickers)}] {t}: ERR ({exc})")

    # Keep canonical ticker order
    order_idx = {t: i for i, t in enumerate(spec.tickers)}
    results.sort(key=lambda r: order_idx.get(r["ticker"], 999999))

    status_map: dict[str, dict[str, Any]] = {}
    cross_summary: list[dict[str, Any]] = []
    gui_payloads: dict[str, dict[str, Any]] = {}

    for res in results:
        t = res["ticker"]
        if not res.get("ok"):
            status_map[t] = {"ok": False, "error": res.get("error", "unknown")}
            continue

        dy = res["daily"]
        chips = res["chips"]
        last = dy.iloc[-1]
        first = dy.iloc[0]
        ytd_ret = round((last["adj_close"] / first["adj_close"] - 1.0) * 100.0, 2) if first["adj_close"] > 0 else 0.0
        clast = chips.iloc[-1] if not chips.empty else {}

        status_map[t] = {
            "ok": True,
            "name": res["name"],
            "rows": len(dy),
            "start_date": dy.index[0].strftime("%Y-%m-%d"),
            "end_date": dy.index[-1].strftime("%Y-%m-%d"),
            "chips_rows": len(chips),
        }

        cross_summary.append({
            "ticker": t,
            "name": res["name"],
            "latest_date": dy.index[-1].strftime("%Y-%m-%d"),
            "latest_close": round(float(last["raw_close"]), 2),
            "pct_change": round(float(last["pct_change"]), 2),
            "ytd_return_pct": ytd_ret,
            "rsi_14": round(float(last["rsi_14"]), 2) if pd.notna(last.get("rsi_14")) else None,
            "macd_hist": round(float(last["macd_hist"]), 2) if pd.notna(last.get("macd_hist")) else None,
            "cyq_profit_ratio": round(float(last["cyq_profit_ratio"]), 2) if pd.notna(last.get("cyq_profit_ratio")) else None,
            "inst_total_net_lots": round(float(clast["inst_total_net_lots"]), 1) if isinstance(clast, pd.Series) and pd.notna(clast.get("inst_total_net_lots")) else None,
            "short_margin_ratio": round(float(clast["short_margin_ratio"]), 2) if isinstance(clast, pd.Series) and pd.notna(clast.get("short_margin_ratio")) else None,
            "chip_pattern": str(clast.get("chip_pattern", "-")) if isinstance(clast, pd.Series) else "-",
        })

        # Merge chips onto daily for GUI Data Tables convenience
        dy_gui = dy.copy()
        dy_gui["date"] = dy_gui.index.strftime("%Y-%m-%d")
        if not chips.empty:
            chip_cols = [
                "date", "foreign_net_lots", "trust_net_lots", "dealer_net_lots",
                "inst_total_net_lots", "margin_balance", "margin_net_change",
                "short_margin_ratio", "day_trading_ratio", "foreign_holding_ratio", "chip_pattern",
            ]
            dy_gui = dy_gui.merge(chips[[c for c in chip_cols if c in chips.columns]], on="date", how="left")

        gui_payloads[t] = {
            "name": res["name"],
            "year_high": round(float(dy["raw_high"].max()), 2),
            "year_low": round(float(dy["raw_low"].min()), 2),
            "daily": _df_to_records(dy_gui),
            "chips": _df_to_records(chips),
            "monthly": _df_to_records(res["monthly"]),
            "quarterly": _df_to_records(res["quarterly"]),
            "priority": res["priority"],
        }

    cross_summary.sort(key=lambda x: x.get("ytd_return_pct", -999), reverse=True)

    db_path = out_path / f"{spec.slug}_{year}.db"
    md_path = out_path / f"{spec.slug}_{year}_data.md"
    gui_path = out_path / f"{spec.slug}_{year}_GUI.html"

    _write_sqlite(db_path, results, spec, cross_summary, status_map, full_reset=(mode == "full"))
    _write_markdown_report(md_path, spec, year, results, cross_summary)
    build_gui_html(
        target_slug=spec.slug,
        target_type=spec.target_type,
        year=year,
        market=spec.market,
        benchmark=spec.benchmark,
        ticker_payloads=gui_payloads,
        cross_summary=cross_summary,
        out_path=gui_path,
    )

    universe_path = None
    if spec.target_type == "pool":
        universe_path = out_path / "universe.json"
        save_universe_json(spec, status_map, universe_path)

    return {
        "spec": spec.to_dict(),
        "db_path": str(db_path),
        "md_path": str(md_path),
        "gui_path": str(gui_path),
        "universe_path": str(universe_path) if universe_path else None,
        "success_count": sum(1 for v in status_map.values() if v.get("ok")),
        "total_count": len(spec.tickers),
        "cross_summary": cross_summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-timeframe quant data generator")
    parser.add_argument("--target", "--ticker", "--pool", dest="target", required=True, help="Ticker or stock pool (e.g. NVDA, 2330.TW, tw50, sox, sp500)")
    parser.add_argument("--year", type=int, default=datetime.now().year, help="Target year (default: current year)")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: data/{target})")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent worker threads")
    parser.add_argument("--no-chips", action="store_true", help="Skip Taiwan chips fetching")
    parser.add_argument("--mode", choices=["auto", "incremental", "full"], default="auto", help="Sync mode: auto (incremental if DB exists), incremental, or full")
    args = parser.parse_args()

    summary = run_pipeline(
        target=args.target,
        year=args.year,
        output_dir=args.output_dir,
        workers=args.workers,
        fetch_chips=not args.no_chips,
        mode=args.mode,
    )
    print(f"\nDone: {summary['success_count']}/{summary['total_count']} succeeded.")
    print(f"  DB:  {summary['db_path']}")
    print(f"  MD:  {summary['md_path']}")
    print(f"  GUI: {summary['gui_path']}")
    if summary["universe_path"]:
        print(f"  Universe: {summary['universe_path']}")


if __name__ == "__main__":
    main()
