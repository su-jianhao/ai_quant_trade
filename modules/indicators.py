"""Dual-price-track cleansing, 19+ technical indicators, rolling CYQ, and multi-timeframe aggregation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import talib


def cleanse_ohlcv(df: pd.DataFrame, is_tw: bool = False) -> pd.DataFrame:
    """Apply dual-price-track separation and microstructure cleansing.

    Expects yfinance columns: Open, High, Low, Close, Adj Close, Volume, Dividends, Stock Splits.
    """
    out = df.copy()
    if out.index.tz is not None:
        out.index = out.index.tz_localize(None)
    out.index = pd.to_datetime(out.index).normalize()
    out = out[~out.index.duplicated(keep="last")].sort_index()

    # Raw prices (unadjusted)
    out["raw_open"] = pd.to_numeric(out["Open"], errors="coerce")
    out["raw_high"] = pd.to_numeric(out["High"], errors="coerce")
    out["raw_low"] = pd.to_numeric(out["Low"], errors="coerce")
    out["raw_close"] = pd.to_numeric(out["Close"], errors="coerce")
    out["adj_close"] = pd.to_numeric(out.get("Adj Close", out["Close"]), errors="coerce")
    out["volume"] = pd.to_numeric(out["Volume"], errors="coerce").fillna(0.0)
    out["dividends"] = pd.to_numeric(out.get("Dividends", 0.0), errors="coerce").fillna(0.0)

    # Guard against <= 0 prices
    for col in ["raw_open", "raw_high", "raw_low", "raw_close", "adj_close"]:
        out.loc[out[col] <= 0, col] = np.nan
        out[col] = out[col].ffill().bfill()

    # Adjusted OHLC scaling factor for indicators
    adj_ratio = (out["adj_close"] / out["raw_close"]).replace([np.inf, -np.inf], 1.0).fillna(1.0)
    out["adj_open"] = out["raw_open"] * adj_ratio
    out["adj_high"] = out["raw_high"] * adj_ratio
    out["adj_low"] = out["raw_low"] * adj_ratio

    # Fillability check: TW < 50 lots (50,000 shares) or zero volume or locked limit-down
    prev_close = out["raw_close"].shift(1)
    pct_chg = (out["raw_close"] - prev_close) / prev_close
    min_vol = 50_000.0 if is_tw else 1_000.0
    limit_down_locked = (pct_chg <= -0.095) & (out["raw_high"] == out["raw_low"]) if is_tw else False
    out["is_fillable"] = ((out["volume"] >= min_vol) & (~limit_down_locked)).astype(int)
    out["pct_change"] = (pct_chg * 100.0).fillna(0.0)
    return out


def compute_rolling_cyq(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
    decay: float = 0.96,
    bins: int = 80,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Compute daily rolling CYQ chip distribution (profit%, trapped%, weighted avg cost, discount%)."""
    n = len(closes)
    profit_ratio = np.full(n, np.nan)
    trapped_ratio = np.full(n, np.nan)
    avg_cost = np.full(n, np.nan)
    cost_discount = np.full(n, np.nan)

    if n == 0:
        return profit_ratio, trapped_ratio, avg_cost, cost_discount

    p_min = float(np.nanmin(lows)) * 0.9
    p_max = float(np.nanmax(highs)) * 1.1
    if p_max <= p_min:
        p_max = p_min + 1.0
    grid = np.linspace(p_min, p_max, bins)
    chips = np.zeros(bins, dtype=np.float64)

    for i in range(n):
        c = closes[i]
        h = highs[i]
        l = lows[i]
        v = max(float(volumes[i]), 0.0)
        chips *= decay

        if np.isnan(c) or np.isnan(h) or np.isnan(l):
            continue

        # Triangular distribution across [low, high] centered at typical price
        mid = (h + l + 2.0 * c) / 4.0
        if h <= l:
            idx = int(np.argmin(np.abs(grid - c)))
            chips[idx] += v
        else:
            mask = (grid >= l) & (grid <= h)
            if not np.any(mask):
                idx = int(np.argmin(np.abs(grid - mid)))
                chips[idx] += v
            else:
                weights = np.where(
                    grid[mask] <= mid,
                    (grid[mask] - l) / max(mid - l, 1e-9),
                    (h - grid[mask]) / max(h - mid, 1e-9),
                )
                weights = np.maximum(weights, 0.05)
                weights /= weights.sum()
                chips[mask] += v * weights

        total_chips = chips.sum()
        if total_chips > 0:
            w_cost = float((chips * grid).sum() / total_chips)
            prof = float(chips[grid <= c].sum() / total_chips * 100.0)
            profit_ratio[i] = round(prof, 2)
            trapped_ratio[i] = round(100.0 - prof, 2)
            avg_cost[i] = round(w_cost, 4)
            cost_discount[i] = round((c - w_cost) / w_cost * 100.0, 2) if w_cost > 0 else 0.0

    return profit_ratio, trapped_ratio, avg_cost, cost_discount


def compute_daily_factors(df: pd.DataFrame) -> pd.DataFrame:
    """Compute 19 technical indicators + rolling CYQ on cleansed dual-track OHLCV."""
    out = df.copy()
    close = out["adj_close"].to_numpy(dtype=np.float64)
    high = out["adj_high"].to_numpy(dtype=np.float64)
    low = out["adj_low"].to_numpy(dtype=np.float64)
    vol = out["volume"].to_numpy(dtype=np.float64)

    # Moving averages (9 indicators)
    for p in (5, 10, 20, 60):
        out[f"ema_{p}"] = talib.EMA(close, timeperiod=p)
    for p in (5, 10, 20, 50, 200):
        out[f"sma_{p}"] = talib.SMA(close, timeperiod=p)

    # MACD (3 series)
    dif, dea, hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
    out["macd_dif"] = dif
    out["macd_dea"] = dea
    out["macd_hist"] = hist * 2.0  # standard histogram convention

    # RSI, WR, CCI, ATR
    out["rsi_14"] = talib.RSI(close, timeperiod=14)
    out["wr_14"] = talib.WILLR(high, low, close, timeperiod=14)
    out["cci_14"] = talib.CCI(high, low, close, timeperiod=14)
    out["atr_14"] = talib.ATR(high, low, close, timeperiod=14)

    # KDJ (9, 3, 3)
    slowk, slowd = talib.STOCH(
        high, low, close,
        fastk_period=9, slowk_period=3, slowk_matype=0,
        slowd_period=3, slowd_matype=0,
    )
    out["kdj_k"] = slowk
    out["kdj_d"] = slowd
    out["kdj_j"] = 3.0 * slowk - 2.0 * slowd

    # Bollinger Bands (20, 2)
    upper, mid, lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
    out["boll_upper"] = upper
    out["boll_mid"] = mid
    out["boll_lower"] = lower

    # Rolling CYQ
    prof, trap, avg_c, disc = compute_rolling_cyq(high, low, close, vol)
    out["cyq_profit_ratio"] = prof
    out["cyq_trapped_ratio"] = trap
    out["cyq_avg_cost"] = avg_c
    out["cyq_cost_discount"] = disc
    return out


def aggregate_monthly_factors(daily_df: pd.DataFrame, chips_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Aggregate daily data into natural monthly OHLCV, end-of-month factors, and TW chips."""
    if daily_df.empty:
        return pd.DataFrame()

    df = daily_df.copy()
    df["month"] = df.index.to_period("M").astype(str)

    agg = df.groupby("month").agg(
        month_open=("raw_open", "first"),
        month_high=("raw_high", "max"),
        month_low=("raw_low", "min"),
        month_close=("raw_close", "last"),
        month_volume=("volume", "sum"),
        ema_10=("ema_10", "last"),
        sma_50=("sma_50", "last"),
        rsi_14=("rsi_14", "last"),
        macd_hist=("macd_hist", "last"),
        cyq_profit_ratio=("cyq_profit_ratio", "last"),
        cyq_avg_cost=("cyq_avg_cost", "last"),
    ).reset_index()

    agg["month_pct_change"] = agg["month_close"].pct_change().fillna(0.0) * 100.0

    if chips_df is not None and not chips_df.empty:
        cdf = chips_df.copy()
        for col in [
            "foreign_net_lots", "trust_net_lots", "dealer_net_lots",
            "inst_total_net_lots", "margin_net_change", "short_margin_ratio",
        ]:
            if col not in cdf.columns:
                cdf[col] = np.nan
        cdf["month"] = pd.to_datetime(cdf["date"]).dt.to_period("M").astype(str)
        c_agg = cdf.groupby("month").agg(
            foreign_net_lots=("foreign_net_lots", "sum"),
            trust_net_lots=("trust_net_lots", "sum"),
            dealer_net_lots=("dealer_net_lots", "sum"),
            inst_total_net_lots=("inst_total_net_lots", "sum"),
            margin_net_change=("margin_net_change", "sum"),
            short_margin_ratio=("short_margin_ratio", "last"),
        ).reset_index()
        agg = agg.merge(c_agg, on="month", how="left")
    else:
        for col in [
            "foreign_net_lots", "trust_net_lots", "dealer_net_lots",
            "inst_total_net_lots", "margin_net_change", "short_margin_ratio",
        ]:
            agg[col] = np.nan

    return agg


def build_priority_board(ticker: str, df_year: pd.DataFrame, chips_year: pd.DataFrame | None = None) -> list[dict]:
    """Build Tier 1~4 factor priority board rows for a ticker."""
    if df_year.empty:
        return []
    last = df_year.iloc[-1]
    rows = [
        {
            "ticker": ticker,
            "tier": "Tier 1 (趨勢與均線)",
            "timeframe": "Daily",
            "factor": "Close vs SMA50 / SMA200",
            "value": f"{last['raw_close']:.2f} / {last.get('sma_50', np.nan):.2f} / {last.get('sma_200', np.nan):.2f}",
            "signal": "多頭排列" if last["adj_close"] > last.get("sma_50", np.inf) else "偏弱整理",
        },
        {
            "ticker": ticker,
            "tier": "Tier 2 (動能共振)",
            "timeframe": "Daily",
            "factor": "RSI_14 / MACD_HIST",
            "value": f"{last.get('rsi_14', np.nan):.2f} / {last.get('macd_hist', np.nan):.2f}",
            "signal": "動能偏強" if (last.get("rsi_14", 50) > 50 and last.get("macd_hist", 0) > 0) else "動能偏弱",
        },
        {
            "ticker": ticker,
            "tier": "Tier 3 (CYQ 籌碼成本)",
            "timeframe": "Daily",
            "factor": "CYQ 獲利盤% / 加權均價",
            "value": f"{last.get('cyq_profit_ratio', np.nan):.1f}% / {last.get('cyq_avg_cost', np.nan):.2f}",
            "signal": "籌碼鎖定" if last.get("cyq_profit_ratio", 0) >= 65 else "套牢壓力",
        },
    ]
    if chips_year is not None and not chips_year.empty:
        clast = chips_year.iloc[-1]
        rows.append({
            "ticker": ticker,
            "tier": "Tier 4 (台股微結構籌碼)",
            "timeframe": "Daily",
            "factor": "三大法人合計(張) / 券資比% / 形態",
            "value": f"{clast.get('inst_total_net_lots', 0):+.0f} / {clast.get('short_margin_ratio', 0):.1f}%",
            "signal": str(clast.get("chip_pattern", "籌碼中性")),
        })
    return rows
