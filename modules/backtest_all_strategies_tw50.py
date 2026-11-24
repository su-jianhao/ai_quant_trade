"""
modules/backtest_all_strategies_tw50.py
全專案策略大亂鬥 (Grand Strategy Arena on TW50)：
統一在 data/tw50/tw50_2026.db 上對比 prompts/strategy/ 全 9 大策略家族 (MACD / Bollinger / KDJ / RSI /
Grand Trinity / Taiwan Chip / Turtle Trend / Regime Stage / Buffett Value-Quality) 與 DSA 冠軍策略。
輸出至：trades/all_strategies_20261124_tw50/
"""
from __future__ import annotations

import os
import sqlite3
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

DB_PATH = "data/tw50/tw50_2026.db"
OUT_DIR = os.path.join("trades", "all_strategies_20261124_tw50")
os.makedirs(OUT_DIR, exist_ok=True)

TW_COMMISSION = 0.000855
TW_TAX = 0.003
TW_SLIPPAGE = 0.0005
INITIAL_CASH = 1_000_000.0
MAX_SLOTS = 10


def pub_date_from_quarter_end(qend: str) -> str:
    y, m, _ = qend.split("-")
    y = int(y)
    if m == "03": return f"{y}-05-15"
    if m == "06": return f"{y}-08-14"
    if m == "09": return f"{y}-11-14"
    if m == "12": return f"{y + 1}-03-31"
    return "9999-12-31"


def winsorize_mad(s: pd.Series, n_mads: float = 3.0) -> pd.Series:
    valid = s.dropna()
    if len(valid) < 5: return s
    med = valid.median()
    mad = (valid - med).abs().median()
    if mad == 0 or np.isnan(mad): return s
    return s.clip(lower=med - n_mads * 1.4826 * mad, upper=med + n_mads * 1.4826 * mad)


def zscore_clean(s: pd.Series) -> pd.Series:
    w = winsorize_mad(s)
    std = w.std()
    if std == 0 or np.isnan(std): return pd.Series(0.0, index=s.index)
    return ((w - w.mean()) / std).fillna(0.0)


def load_data():
    conn = sqlite3.connect(DB_PATH)
    meta = pd.read_sql_query("SELECT ticker, name FROM universe_meta", conn)
    meta_map = dict(zip(meta["ticker"], meta["name"]))

    df = pd.read_sql_query("""
        SELECT s.ticker, s.date, s.raw_open, s.raw_high, s.raw_low, s.raw_close, s.adj_close, s.volume, s.dividends,
               f.sma_5, f.sma_10, f.sma_20, f.sma_50, f.ema_60, f.sma_200,
               f.rsi_14, f.atr_14, f.macd_dif, f.macd_dea, f.macd_hist,
               f.boll_upper, f.boll_mid, f.boll_lower, f.kdj_k, f.kdj_d, f.kdj_j,
               v.pe_ratio, v.pb_ratio, v.dividend_yield, v.roe_implied_pct,
               c.foreign_net_lots, c.trust_net_lots, c.inst_total_net_lots, c.margin_net_change
        FROM stock_daily s
        LEFT JOIN daily_factors f ON s.ticker = f.ticker AND s.date = f.date
        LEFT JOIN daily_valuation v ON s.ticker = v.ticker AND s.date = v.date
        LEFT JOIN taiwan_chips_daily c ON s.ticker = c.ticker AND s.date = c.date
        ORDER BY s.ticker, s.date
    """, conn)
    qf = pd.read_sql_query("SELECT * FROM quarterly_fundamentals ORDER BY ticker, quarter_end", conn)
    conn.close()
    qf["pub_date"] = qf["quarter_end"].apply(pub_date_from_quarter_end)

    # Precompute derived indicators & stock regime classification (MOMENTUM vs CYCLICAL)
    frames = []
    stock_regime = {}
    for t, g in df.groupby("ticker", sort=False):
        g = g.sort_values("date").reset_index(drop=True)
        g["adj_close"] = g["adj_close"].ffill()
        g["raw_close"] = g["raw_close"].ffill()
        c = g["adj_close"]
        h = g["raw_high"]
        l = g["raw_low"]
        v = g["volume"].fillna(0.0)

        # Regime classification (bollinger_strategy.md)
        rets = c.pct_change().dropna()
        ann_vol = float(rets.std() * np.sqrt(252)) if len(rets) > 20 else 0.25
        above200 = float((c > g["sma_200"]).mean()) if g["sma_200"].notnull().any() else 0.5
        stock_regime[t] = "MOMENTUM" if (ann_vol > 0.38 and above200 > 0.60) else "CYCLICAL"

        # Bollinger bandwidth
        g["boll_bw"] = np.where(g["boll_mid"] > 0, (g["boll_upper"] - g["boll_lower"]) / g["boll_mid"], 0.0)
        g["boll_bw_prev5"] = g["boll_bw"].shift(5)
        g["prev_c"] = c.shift(1)
        g["prev_upper"] = g["boll_upper"].shift(1)
        g["prev_lower"] = g["boll_lower"].shift(1)

        # MACD & KDJ crosses
        g["macd_gc"] = (g["macd_dif"] > g["macd_dea"]) & (g["macd_dif"].shift(1) <= g["macd_dea"].shift(1))
        g["macd_dc"] = (g["macd_dif"] < g["macd_dea"]) & (g["macd_dif"].shift(1) >= g["macd_dea"].shift(1))
        g["kdj_gc"] = (g["kdj_k"] > g["kdj_d"]) & (g["kdj_k"].shift(1) <= g["kdj_d"].shift(1))
        g["kdj_dc"] = (g["kdj_k"] < g["kdj_d"]) & (g["kdj_k"].shift(1) >= g["kdj_d"].shift(1))
        g["rsi_prev"] = g["rsi_14"].shift(1)

        # Donchian channels (previous N days, no look-ahead)
        g["don_h20"] = c.shift(1).rolling(20, min_periods=5).max()
        g["don_l10"] = c.shift(1).rolling(10, min_periods=5).min()
        g["don_h55"] = c.shift(1).rolling(55, min_periods=15).max()
        g["don_l20"] = c.shift(1).rolling(20, min_periods=5).min()
        g["don_h60"] = c.shift(1).rolling(60, min_periods=15).max()
        g["high_40"] = c.rolling(40, min_periods=15).max()
        g["low_40"] = c.rolling(40, min_periods=15).min()

        # Volume & Emotion indicators
        g["vol_ma5"] = v.rolling(5, min_periods=1).mean()
        g["vol_ma20"] = v.rolling(20, min_periods=5).mean()
        g["vol_ma60"] = v.rolling(60, min_periods=10).mean()
        g["bias_ma5"] = (c / g["sma_5"] - 1.0) * 100.0
        g["bias_ma50"] = (c / g["sma_50"] - 1.0) * 100.0
        g["ma_spread"] = (g[["sma_5", "sma_10", "sma_20"]].max(axis=1) - g[["sma_5", "sma_10", "sma_20"]].min(axis=1)) / (g["sma_20"] + 1e-8) * 100.0

        # Taiwan Chips strictly lagged T-1 (no look-ahead!)
        f_l = g["foreign_net_lots"].shift(1).fillna(0.0)
        t_l = g["trust_net_lots"].shift(1).fillna(0.0)
        i_l = g["inst_total_net_lots"].shift(1).fillna(0.0)
        m_l = g["margin_net_change"].shift(1).fillna(0.0)
        g["f_t1"] = f_l
        g["t_t1"] = t_l
        g["t_t2"] = g["trust_net_lots"].shift(2).fillna(0.0)
        g["i_t1"] = i_l
        g["m_t1"] = m_l
        g["regime"] = stock_regime[t]
        frames.append(g)

    full = pd.concat(frames, ignore_index=True)
    return full, qf, meta_map


def check_signal_entry(row: pd.Series, skey: str) -> bool:
    c = row["adj_close"]
    if pd.isna(c) or pd.isna(row["sma_20"]):
        return False
    reg = row["regime"]

    if skey == "macd_raw":
        return bool(row["macd_gc"])
    elif skey == "macd_water_bb":
        return bool((row["macd_dif"] <= 0 and row["macd_gc"] and c >= row["boll_mid"]) or (row["macd_gc"] and c > row["sma_50"]))
    elif skey == "boll_combo_refined":
        return bool(c > row["boll_upper"] and row["boll_bw"] >= 0.15 and row["boll_bw"] > row["boll_bw_prev5"])
    elif skey == "boll_regime_adaptive":
        if reg == "MOMENTUM":
            return bool(c > row["boll_upper"] and row["boll_bw"] >= 0.15 and row["boll_bw"] > row["boll_bw_prev5"])
        return bool(row["prev_c"] <= row["prev_lower"] and c > row["boll_lower"])
    elif skey == "kdj_oversold_low":
        return bool(row["kdj_gc"] and row["kdj_k"] < 35.0 and row["kdj_j"] < 20.0)
    elif skey == "rsi_extreme_oversold":
        return bool(row["rsi_prev"] <= 32.0 and row["rsi_14"] > 32.0)
    elif skey == "rsi_momentum_breakout":
        return bool(row["rsi_prev"] <= 55.0 and row["rsi_14"] > 55.0 and c >= row["sma_50"])
    elif skey == "trinity_grand":
        l1 = (row["macd_dif"] > 0) or (row["macd_dif"] <= 0 and row["macd_gc"])
        bb_fresh = (row["prev_c"] <= row["prev_upper"]) and (c > row["boll_upper"])
        l2 = (c > row["boll_mid"]) and ((row["boll_bw"] >= 0.12 and row["boll_bw"] > row["boll_bw_prev5"]) or bb_fresh)
        l3 = (row["kdj_gc"] and row["kdj_k"] < 65.0 and (row["kdj_k"] < 45.0 or row["kdj_j"] < 20.0 or row["macd_dif"] > 0)) or (bb_fresh and row["kdj_k"] < 85.0)
        return bool(l1 and l2 and l3)
    elif skey == "trinity_regime_adaptive":
        if reg == "MOMENTUM":
            return check_signal_entry(row, "trinity_grand")
        bb_rev = (row["prev_c"] <= row["prev_lower"]) and (c > row["boll_lower"])
        kdj_low = (row["kdj_gc"] and (row["kdj_k"] < 45.0 or row["kdj_j"] < 20.0)) or (row["kdj_k"] < 35.0 and row["kdj_k"] > row["kdj_d"])
        return bool(bb_rev and kdj_low)
    elif skey in ("tw_chip_baseline", "tw_chip_sitc_shield"):
        cond_a = (row["t_t1"] > 0) and (row["t_t2"] > 0)
        cond_b = (row["f_t1"] > 0) and (row["t_t1"] > 500) and ((row["f_t1"] + row["t_t1"]) > 2000)
        return bool((cond_a or cond_b) and (row["m_t1"] <= 300) and (c >= row["sma_20"]))
    elif skey == "turtle_sys1_trend":
        return bool(c >= row["sma_50"] and row["sma_20"] >= row["sma_50"] and c > row["don_h20"])
    elif skey == "turtle_sys2_pure":
        return bool(c >= row["sma_50"] and row["sma_20"] >= row["sma_50"] and c > row["don_h55"])
    elif skey == "regime_stage_adaptive":
        return bool(c > row["don_h60"] and (row["t_t1"] > 0 or row["i_t1"] > 0) and c >= row["sma_50"])
    elif skey == "dsa_12_emotion_cycle":
        return bool(row["volume"] < 0.65 * row["vol_ma60"] and row["ma_spread"] < 4.5 and (30.0 <= row["rsi_14"] <= 55.0) and c <= row["sma_20"] * 1.02)
    elif skey == "dsa_07_box_oscillation":
        h40, l40 = row["high_40"], row["low_40"]
        if pd.isna(h40) or pd.isna(l40) or l40 <= 0: return False
        w = (h40 - l40) / l40 * 100.0
        pos = (c - l40) / (h40 - l40 + 1e-8)
        return bool(6.0 <= w <= 25.0 and pos <= 0.25 and row["raw_close"] > row["raw_open"])
    return False


def check_signal_exit(row: pd.Series, st: dict, skey: str) -> str:
    """Returns 'HOLD', 'EXIT', or 'TRIM_HALF'."""
    c = row["adj_close"]
    ep = st["adj_entry"]
    peak = st["peak_adj"]
    mfe = (peak / ep - 1.0) * 100.0
    ret = (c / ep - 1.0) * 100.0
    atr = float(row["atr_14"]) if (pd.notnull(row["atr_14"]) and row["atr_14"] > 0) else c * 0.02
    reg = row["regime"]

    if skey == "macd_raw":
        return "EXIT" if row["macd_dc"] else "HOLD"
    elif skey == "macd_water_bb":
        stop = row["boll_mid"]
        if mfe >= 15.0: stop = max(stop, peak - 2.5 * atr)
        return "EXIT" if (c < stop or row["macd_dc"]) else "HOLD"
    elif skey == "boll_combo_refined":
        stop = row["boll_mid"]
        if mfe >= 10.0: stop = max(stop, ep * 1.015)
        if mfe >= 20.0: stop = max(stop, peak - 2.5 * atr)
        return "EXIT" if c < stop else "HOLD"
    elif skey == "boll_regime_adaptive":
        if reg == "MOMENTUM":
            return check_signal_exit(row, st, "boll_combo_refined")
        return "EXIT" if c >= row["boll_mid"] else "HOLD"
    elif skey == "kdj_oversold_low":
        if row["kdj_k"] > 80.0 and row["kdj_j"] > 100.0:
            return "EXIT" if c < row["sma_10"] else "HOLD"
        return "EXIT" if ((row["kdj_k"] > 65.0 and row["kdj_dc"]) or ret <= -7.0) else "HOLD"
    elif skey == "rsi_extreme_oversold":
        return "EXIT" if (row["rsi_14"] >= 60.0 or ret <= -8.0) else "HOLD"
    elif skey == "rsi_momentum_breakout":
        return "EXIT" if c < row["sma_20"] else "HOLD"
    elif skey == "trinity_grand":
        stop = row["boll_mid"]
        if mfe >= 10.0: stop = max(stop, ep * 1.015)
        if mfe >= 20.0: stop = max(stop, peak - 2.5 * atr)
        return "EXIT" if c < stop else "HOLD"
    elif skey == "trinity_regime_adaptive":
        if reg == "MOMENTUM":
            return check_signal_exit(row, st, "trinity_grand")
        return "EXIT" if (c >= row["boll_mid"] or (row["kdj_k"] > 70.0 and row["kdj_dc"])) else "HOLD"
    elif skey == "tw_chip_baseline":
        if ret <= -6.0 or c <= peak * 0.92 or (row["i_t1"] < -18000 and c < row["sma_20"]):
            return "EXIT"
        return "HOLD"
    elif skey == "tw_chip_sitc_shield":
        if ret <= -6.0 or (row["i_t1"] < -18000 and c < row["sma_20"]):
            return "EXIT"
        if c <= peak * 0.92:
            if row["t_t1"] >= 1500 and c >= row["ema_60"]:
                return "HOLD"  # SITC shield exempts washout!
            return "EXIT"
        return "HOLD"
    elif skey == "turtle_sys1_trend":
        return "EXIT" if (c < ep - 2.0 * atr or c < row["don_l10"]) else "HOLD"
    elif skey == "turtle_sys2_pure":
        return "EXIT" if (c < ep - 2.0 * atr or c < row["don_l20"]) else "HOLD"
    elif skey == "regime_stage_adaptive":
        if (not st["trimmed"]) and row["bias_ma50"] > 55.0:
            return "TRIM_HALF"
        return "EXIT" if c < row["sma_50"] else "HOLD"
    elif skey == "dsa_12_emotion_cycle":
        overheat = (row["vol_ma5"] > 1.8 * row["vol_ma20"] and row["bias_ma5"] > 6.0) or (row["rsi_14"] > 78.0)
        return "EXIT" if (overheat or ret <= -8.0) else "HOLD"
    elif skey == "dsa_07_box_oscillation":
        h40, l40 = row["high_40"], row["low_40"]
        pos = (c - l40) / (h40 - l40 + 1e-8) if (pd.notnull(h40) and h40 > l40) else 0.5
        return "EXIT" if (pos >= 0.85 or c < st["stop_low"] * 0.97) else "HOLD"
    return "HOLD"


def simulate_signal_strategy(daily_by_date: Dict[str, pd.DataFrame], all_dates: List[str], skey: str, meta_map: Dict[str, str]):
    cash = INITIAL_CASH
    shares: Dict[str, float] = {}
    state: Dict[str, dict] = {}
    eq_curve, exposures, trades = [], [], []

    for dt in all_dates:
        d_slice = daily_by_date[dt]
        for t, sh in shares.items():
            if sh > 0 and t in d_slice.index:
                div = float(d_slice.at[t, "dividends"])
                if pd.notnull(div) and div > 0:
                    cash += sh * div

        for t in list(shares.keys()):
            if shares[t] <= 0 or t not in d_slice.index: continue
            row = d_slice.loc[t]
            st = state[t]
            adj = float(row["adj_close"])
            if adj > st["peak_adj"]: st["peak_adj"] = adj
            act = check_signal_exit(row, st, skey)
            if act == "EXIT":
                px = float(row["raw_close"]) * (1.0 - TW_SLIPPAGE)
                gross = shares[t] * px
                cost = gross * (TW_COMMISSION + TW_TAX)
                cash += gross - cost
                ret_pct = (adj / st["adj_entry"] - 1.0) * 100.0 - (TW_COMMISSION * 2 + TW_TAX + TW_SLIPPAGE * 2) * 100.0
                pnl = (px - st["raw_entry"]) * shares[t] - cost - st["buy_cost"]
                trades.append({"strategy": skey, "ticker": t, "net_pnl": pnl, "return_pct": ret_pct,
                               "hold_days": (pd.Timestamp(dt) - pd.Timestamp(st["entry_date"])).days})
                shares.pop(t, None); state.pop(t, None)
            elif act == "TRIM_HALF":
                sh_s = shares[t] * 0.5
                px = float(row["raw_close"]) * (1.0 - TW_SLIPPAGE)
                gross = sh_s * px
                cost = gross * (TW_COMMISSION + TW_TAX)
                cash += gross - cost
                shares[t] -= sh_s
                st["trimmed"] = True
                ret_pct = (adj / st["adj_entry"] - 1.0) * 100.0 - (TW_COMMISSION * 2 + TW_TAX + TW_SLIPPAGE * 2) * 100.0
                pnl = (px - st["raw_entry"]) * sh_s - cost - st["buy_cost"] * 0.5
                st["buy_cost"] *= 0.5
                trades.append({"strategy": skey, "ticker": t, "net_pnl": pnl, "return_pct": ret_pct,
                               "hold_days": (pd.Timestamp(dt) - pd.Timestamp(st["entry_date"])).days})

        open_slots = MAX_SLOTS - len(shares)
        if open_slots > 0 and cash > 10_000.0:
            cands = []
            for t, row in d_slice.iterrows():
                if t in shares: continue
                if check_signal_entry(row, skey):
                    prio = float(row["volume"] / (row["vol_ma20"] + 1e-8)) if pd.notnull(row["vol_ma20"]) else 1.0
                    cands.append((prio, t, row))
            cands.sort(key=lambda x: x[0], reverse=True)
            chosen = cands[:open_slots]
            if chosen:
                pv = cash + sum(sh * float(d_slice.at[t, "raw_close"]) for t, sh in shares.items() if sh > 0)
                slot_cash = pv / MAX_SLOTS
                for _, t, row in chosen:
                    alloc = min(slot_cash, cash * 0.995)
                    if alloc < 10_000.0: break
                    px = float(row["raw_close"]) * (1.0 + TW_SLIPPAGE)
                    bsh = alloc / (px * (1.0 + TW_COMMISSION))
                    bcost = bsh * px * TW_COMMISSION
                    if bsh * px + bcost <= cash + 1e-6:
                        cash -= bsh * px + bcost
                        shares[t] = bsh
                        adj_p = float(row["adj_close"])
                        state[t] = {"entry_date": dt, "raw_entry": px, "adj_entry": adj_p, "peak_adj": adj_p,
                                    "buy_cost": bcost, "trimmed": False,
                                    "stop_low": float(row["low_40"]) if pd.notnull(row["low_40"]) else adj_p * 0.92}

        inv = sum(sh * float(d_slice.at[t, "raw_close"]) for t, sh in shares.items() if sh > 0)
        eq = cash + inv
        eq_curve.append((dt, eq))
        exposures.append(inv / eq * 100.0 if eq > 0 else 0.0)

    last_dt = all_dates[-1]
    d_last = daily_by_date[last_dt]
    for t, st in state.items():
        if shares.get(t, 0.0) > 0:
            px = float(d_last.at[t, "raw_close"])
            adj = float(d_last.at[t, "adj_close"])
            ret_pct = (adj / st["adj_entry"] - 1.0) * 100.0 - (TW_COMMISSION + TW_SLIPPAGE) * 100.0
            pnl = (px - st["raw_entry"]) * shares[t] - st["buy_cost"]
            trades.append({"strategy": skey, "ticker": t, "net_pnl": pnl, "return_pct": ret_pct,
                           "hold_days": (pd.Timestamp(last_dt) - pd.Timestamp(st["entry_date"])).days})

    eq_s = pd.Series(dict(eq_curve))
    eq_s.index = pd.to_datetime(eq_s.index)
    return eq_s, trades, float(np.mean(exposures))


def load_buffett_curves_from_db():
    """Load exact already-verified Buffett Full Score Top10 & Moat Compounder + SMA50 curves for apples-to-apples leaderboard."""
    out = {}
    db1 = os.path.join("trades", "buffett_full_20261124_tw50", "backtest_result.db")
    if os.path.exists(db1):
        c = sqlite3.connect(db1)
        eq = pd.read_sql_query("SELECT date, buffett_full_score_top10 FROM backtest_equity_curve", c)
        eq["date"] = pd.to_datetime(eq["date"])
        tr = pd.read_sql_query("SELECT * FROM backtest_trades WHERE model='buffett_full_score_top10'", c).to_dict("records")
        c.close()
        out["buffett_full_score_top10"] = (eq.set_index("date")["buffett_full_score_top10"], tr, 95.9)

    db2 = os.path.join("trades", "buffett_tech_20261124_tw50", "backtest_result.db")
    if os.path.exists(db2):
        c = sqlite3.connect(db2)
        eq = pd.read_sql_query("SELECT date, buffett_moat_compounder__sma50_trend FROM backtest_equity_curve", c)
        eq["date"] = pd.to_datetime(eq["date"])
        tr = pd.read_sql_query("SELECT * FROM backtest_trades WHERE pool='buffett_moat_compounder' AND overlay='sma50_trend'", c).to_dict("records")
        c.close()
        out["buffett_moat_sma50"] = (eq.set_index("date")["buffett_moat_compounder__sma50_trend"], tr, 80.5)
    return out


def calc_stats(eq: pd.Series, bm: pd.Series, trades: List[dict], avg_exp: float) -> dict:
    rets = eq.pct_change().dropna()
    tot = (eq.iloc[-1] / eq.iloc[0] - 1.0) * 100.0
    bm_ret = (bm.iloc[-1] / bm.iloc[0] - 1.0) * 100.0
    cagr = ((eq.iloc[-1] / eq.iloc[0]) ** (252.0 / max(len(rets), 1)) - 1.0) * 100.0
    vol = float(rets.std() * np.sqrt(252) * 100.0)
    excess = rets - 0.015 / 252.0
    sharpe = float((excess.mean() / (rets.std() + 1e-12)) * np.sqrt(252)) if vol > 1e-6 else 0.0
    down = rets[rets < 0]
    sortino = float((excess.mean() / ((float(down.std()) if len(down) > 2 else 1e-12) + 1e-12)) * np.sqrt(252)) if vol > 1e-6 else 0.0
    mdd = float(((eq / eq.cummax()) - 1.0).min() * 100.0)
    calmar = float(cagr / abs(mdd)) if mdd < -1e-6 else 0.0

    n_tr = len(trades)
    wins = [t["return_pct"] for t in trades if t["return_pct"] > 0]
    losses = [t["return_pct"] for t in trades if t["return_pct"] <= 0]
    wr = (len(wins) / n_tr * 100.0) if n_tr else 0.0
    gw = sum(t["net_pnl"] for t in trades if t["net_pnl"] > 0)
    gl = abs(sum(t["net_pnl"] for t in trades if t["net_pnl"] < 0))
    pf = min(gw / gl, 99.0) if gl > 1e-6 else (99.0 if gw > 0 else 0.0)
    chop = sum(t["net_pnl"] for t in trades if t["hold_days"] <= 10)
    return {
        "total_return_pct": round(tot, 2), "alpha_pct": round(tot - bm_ret, 2),
        "ann_vol_pct": round(vol, 2), "sharpe": round(sharpe, 2), "sortino": round(sortino, 2),
        "calmar": round(calmar, 2), "mdd_pct": round(mdd, 2), "avg_exposure_pct": round(avg_exp, 1),
        "trades": n_tr, "win_rate_pct": round(wr, 1), "profit_factor": round(pf, 2), "chop_tax_ntd": round(chop, 0),
    }


def main():
    print("Running Grand Strategy Arena on TW50 (All 9 prompts/strategy families + DSA Champions)...")
    full, qf, meta_map = load_data()
    daily_by_date = {dt: g.set_index("ticker") for dt, g in full.groupby("date")}
    all_dates = sorted(daily_by_date.keys())

    adj_piv = full.pivot(index="date", columns="ticker", values="adj_close").sort_index().ffill()
    bm_tw50 = adj_piv.div(adj_piv.iloc[0]).mean(axis=1) * INITIAL_CASH
    bm_tw50.index = pd.to_datetime(bm_tw50.index)

    signal_roster = [
        ("macd_raw", "MACD 原始金叉死叉 (macd_raw)", "MACD"),
        ("macd_water_bb", "MACD 水下+布林中軌 (macd_water_bb)", "MACD"),
        ("boll_combo_refined", "布林帶寬突破+吊燈 (boll_combo)", "Bollinger"),
        ("boll_regime_adaptive", "布林風格自適應 (boll_adaptive)", "Bollinger"),
        ("kdj_oversold_low", "KDJ 超賣低位金叉 (kdj_oversold)", "KDJ"),
        ("rsi_extreme_oversold", "RSI 極度超賣抄底 (rsi_oversold)", "RSI"),
        ("rsi_momentum_breakout", "RSI 55 動能突破 (rsi_breakout)", "RSI"),
        ("trinity_grand", "三位一體四階防禦 (grand_trinity)", "Trinity"),
        ("trinity_regime_adaptive", "三位一體風格自適應 (trinity_adaptive)", "Trinity"),
        ("tw_chip_baseline", "台股籌碼波段基準 (tw_chip_base)", "台股籌碼"),
        ("tw_chip_sitc_shield", "台股籌碼+投信護盤 (tw_chip_shield)", "台股籌碼"),
        ("turtle_sys1_trend", "海龜系統一 20D/10D (turtle_sys1)", "Turtle"),
        ("turtle_sys2_pure", "海龜系統二 55D/20D (turtle_sys2)", "Turtle"),
        ("regime_stage_adaptive", "生命週期60D突破+季線 (regime_stage)", "生命週期"),
        ("dsa_12_emotion_cycle", "DSA #12 情緒週期逆向 (emotion_cycle)", "DSA冠軍"),
        ("dsa_07_box_oscillation", "DSA #7 箱體震盪回歸 (box_oscillation)", "DSA亞軍"),
    ]

    rows = []
    eq_map = {"BM_TW50_EW": bm_tw50}

    for skey, slbl, sfam in signal_roster:
        eq, tr, exp = simulate_signal_strategy(daily_by_date, all_dates, skey, meta_map)
        eq_map[skey] = eq
        met = calc_stats(eq, bm_tw50, tr, exp)
        met.update({"strategy_key": skey, "label": slbl, "family": sfam})
        rows.append(met)

    # Add Buffett Champions
    buffett_data = load_buffett_curves_from_db()
    for bkey, blbl in [
        ("buffett_full_score_top10", "巴菲特完整8因子 Top10 (純季換倉B&H)"),
        ("buffett_moat_sma50", "巴菲特護城河 ROE≥20% + SMA50濾網"),
    ]:
        if bkey in buffett_data:
            beq, btr, bexp = buffett_data[bkey]
            eq_map[bkey] = beq
            met = calc_stats(beq, bm_tw50, btr, bexp)
            met.update({"strategy_key": bkey, "label": blbl, "family": "巴菲特價值"})
            rows.append(met)

    bm_met = calc_stats(bm_tw50, bm_tw50, [], 100.0)
    bm_met.update({"strategy_key": "BM_TW50_EW", "label": "基準：台灣50 等權 B&H (TW50 EW)", "family": "基準"})
    rows.append(bm_met)

    res_df = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    print("\n=== GRAND STRATEGY ARENA ON TW50 (ALL FAMILIES, SORTED BY SHARPE) ===")
    cols = ["label", "family", "total_return_pct", "sharpe", "sortino", "mdd_pct", "avg_exposure_pct", "trades", "win_rate_pct", "profit_factor", "chop_tax_ntd"]
    print(res_df[cols].to_string(index=False))

    # Persist SQLite
    db_out = os.path.join(OUT_DIR, "backtest_result.db")
    if os.path.exists(db_out): os.remove(db_out)
    conn = sqlite3.connect(db_out)
    res_df.to_sql("backtest_summary", conn, index=False, if_exists="replace")
    eq_df = pd.DataFrame(eq_map)
    eq_df.index.name = "date"
    eq_df.reset_index().to_sql("backtest_equity_curve", conn, index=False, if_exists="replace")
    conn.close()

    # Build HTML & Markdown
    build_html(res_df, eq_map, all_dates[0], all_dates[-1])
    build_md(res_df, all_dates[0], all_dates[-1])
    print(f"\nSaved Grand Arena results to {OUT_DIR}/")


def build_html(res_df: pd.DataFrame, eq_map: Dict[str, pd.Series], start_dt: str, end_dt: str):
    s_only = res_df[res_df["strategy_key"] != "BM_TW50_EW"].sort_values("sharpe", ascending=True)
    fig1 = make_subplots(rows=1, cols=2, subplot_titles=("全策略家族 Sharpe Ratio 總排行", "全策略家族累計報酬率 % 總排行"))
    fig1.add_trace(go.Bar(y=s_only["label"], x=s_only["sharpe"], orientation="h", showlegend=False,
                          marker_color=["#00D084" if v >= 2.45 else ("#38BDF8" if v >= 1.5 else "#FF4D4F") for v in s_only["sharpe"]],
                          text=[f"{v:.2f}" for v in s_only["sharpe"]], textposition="outside"), row=1, col=1)
    fig1.add_trace(go.Bar(y=s_only["label"], x=s_only["total_return_pct"], orientation="h", showlegend=False,
                          marker_color=["#00D084" if v >= 77 else ("#FCD34D" if v >= 30 else "#FF4D4F") for v in s_only["total_return_pct"]],
                          text=[f"{v:+.1f}%" for v in s_only["total_return_pct"]], textposition="outside"), row=1, col=2)
    fig1.update_layout(template="plotly_dark", paper_bgcolor="#181C25", plot_bgcolor="#14171F", height=620, margin=dict(l=270, r=50, t=55, b=40))

    top_keys = list(res_df[res_df["strategy_key"] != "BM_TW50_EW"].head(7)["strategy_key"]) + ["BM_TW50_EW"]
    fig2 = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.68, 0.32],
                         subplot_titles=("Top 7 冠軍策略淨值走勢 % vs TW50 基準", "水下回撤深度 % (MDD)"))
    pal = ["#00D084", "#38BDF8", "#FCD34D", "#A78BFA", "#F472B6", "#FB923C", "#2DD4BF", "#94A3B8"]
    for idx, k in enumerate(top_keys):
        eq = eq_map[k]
        lbl = res_df[res_df["strategy_key"] == k].iloc[0]["label"]
        is_bm = k == "BM_TW50_EW"
        fig2.add_trace(go.Scatter(x=eq.index, y=(eq / eq.iloc[0] - 1.0) * 100.0, name=lbl,
                                  line=dict(color=pal[idx % len(pal)], width=2.0 if is_bm else 2.5, dash="dot" if is_bm else "solid")), row=1, col=1)
        fig2.add_trace(go.Scatter(x=eq.index, y=(eq / eq.cummax() - 1.0) * 100.0, showlegend=False,
                                  line=dict(color=pal[idx % len(pal)], width=1.4 if is_bm else 1.8, dash="dot" if is_bm else "solid")), row=2, col=1)
    fig2.update_layout(template="plotly_dark", paper_bgcolor="#181C25", plot_bgcolor="#14171F", height=580, hovermode="x unified",
                       legend=dict(orientation="h", yanchor="bottom", y=1.04, x=0, font=dict(size=11)))

    rows_html = "".join(f"""
      <tr>
        <td><strong>{r['label']}</strong></td><td>{r['family']}</td>
        <td class="{'pos' if r['total_return_pct']>=0 else 'neg'}">{r['total_return_pct']:+.2f}%</td>
        <td><strong>{r['sharpe']:.2f}</strong></td><td>{r['sortino']:.2f}</td><td class="neg">{r['mdd_pct']:.2f}%</td>
        <td>{r['avg_exposure_pct']:.1f}%</td><td>{int(r['trades'])}</td><td>{r['win_rate_pct']:.1f}%</td>
        <td>{r['profit_factor']:.2f}</td><td class="{'pos' if r['chop_tax_ntd']>=0 else 'neg'}">{r['chop_tax_ntd']:+,.0f}</td>
      </tr>""" for _, r in res_df.iterrows())

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="UTF-8" /><title>TW50 全專案策略總決戰 (Grand Strategy Arena)</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  body {{ background:#14171F; color:#E2E8F0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; padding:24px; }}
  .container {{ max-width:1440px; margin:0 auto; }}
  .card {{ background:#181C25; border:1px solid #2A3142; border-radius:10px; padding:20px; margin-bottom:24px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ padding:9px 11px; border-bottom:1px solid #2A3142; text-align:right; }}
  th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) {{ text-align:left; }}
  th {{ color:#94A3B8; background:#14171F; }}
  .pos {{ color:#00D084; font-weight:600; }} .neg {{ color:#FF4D4F; font-weight:600; }}
</style></head><body><div class="container">
  <h1>👑 TW50 全專案策略總決戰 (Grand Strategy Arena: All 9 Families + DSA Champions)</h1>
  <p style="color:#94A3B8">標的池：TW50 (50 檔) ｜ 區間：{start_dt} ~ {end_dt} ｜ 統一資金：100 萬 NTD（最多 10 檔等權）｜ 台股真實手續費/證交稅/滑價</p>
  <div class="card">
    <h2>1. 全策略總排行榜（按 Sharpe 排序）</h2>
    <table><thead><tr>
      <th>策略名稱</th><th>家族</th><th>累計報酬</th><th>Sharpe</th><th>Sortino</th><th>MDD</th>
      <th>平均曝險</th><th>交易數</th><th>勝率</th><th>獲利因子 PF</th><th>短線摩擦稅 (<=10d)</th>
    </tr></thead><tbody>{rows_html}</tbody></table>
  </div>
  <div class="card"><div id="f1"></div></div>
  <div class="card"><div id="f2"></div></div>
</div>
<script>
  Plotly.newPlot('f1', {fig1.to_json()}.data, {fig1.to_json()}.layout, {{responsive:true}});
  Plotly.newPlot('f2', {fig2.to_json()}.data, {fig2.to_json()}.layout, {{responsive:true}});
</script></body></html>"""
    with open(os.path.join(OUT_DIR, "tw50_all_strategies_Arena_Report.html"), "w", encoding="utf-8") as f:
        f.write(html)


def build_md(res_df: pd.DataFrame, start_dt: str, end_dt: str):
    lines = [
        "# TW50 全專案策略總決戰 (Grand Strategy Arena)",
        "",
        f"- **標的池**：`data/tw50/tw50_2026.db`（50 檔）｜ **區間**：`{start_dt}` ～ `{end_dt}`",
        "- **涵蓋範圍**：`prompts/strategy/` 全部 9 大策略家族（MACD / Bollinger / KDJ / RSI / Grand Trinity / Taiwan Chip / Turtle Trend / Regime Stage / Buffett Value-Quality）＋ DSA 15 策略冠亞軍。",
        "",
        "## 全策略總排行榜（按 Sharpe 排序）",
        "",
        "| 策略名稱 | 家族 | 累計報酬 | Sharpe | Sortino | 最大回撤 MDD | 平均曝險 | 交易數 | 勝率 | PF | 短線摩擦稅 (`<=10d`) |",
        "| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, r in res_df.iterrows():
        lines.append(
            f"| {r['label']} | {r['family']} | {r['total_return_pct']:+.2f}% | {r['sharpe']:.2f} | {r['sortino']:.2f} | "
            f"{r['mdd_pct']:.2f}% | {r['avg_exposure_pct']:.1f}% | {int(r['trades'])} | {r['win_rate_pct']:.1f}% | "
            f"{r['profit_factor']:.2f} | {r['chop_tax_ntd']:+,.0f} |"
        )
    with open(os.path.join(OUT_DIR, "backtest_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
