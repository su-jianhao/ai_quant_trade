"""
modules/backtest_15_strategies_tw50.py
對 arch_analysis/daily_stock_analysis/05_strategy_original_prompts.md 中全部 15 大策略，
於本地 TW50 (data/tw50/tw50_2026.db) 執行統一規格量化回測與橫向評比。
輸出至：trades/dsa15_20261124_tw50/
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
OUT_DIR = os.path.join("trades", "dsa15_20261124_tw50")
os.makedirs(OUT_DIR, exist_ok=True)

TW_COMMISSION = 0.000855
TW_TAX = 0.003
TW_SLIPPAGE = 0.0005
INITIAL_CASH = 1_000_000.0
MAX_SLOTS = 10

TW50_SECTORS: Dict[str, str] = {
    "2330.TW": "半導體", "2454.TW": "半導體", "2303.TW": "半導體", "3711.TW": "半導體", "2379.TW": "半導體", "3034.TW": "半導體",
    "2317.TW": "AI伺服器與網通", "2382.TW": "AI伺服器與網通", "3231.TW": "AI伺服器與網通", "6669.TW": "AI伺服器與網通", "2357.TW": "AI伺服器與網通", "2345.TW": "AI伺服器與網通",
    "2308.TW": "電子零組件", "2059.TW": "電子零組件", "3017.TW": "電子零組件", "2383.TW": "電子零組件", "2360.TW": "電子零組件",
    "3008.TW": "電子零組件", "2327.TW": "電子零組件", "3037.TW": "電子零組件", "2301.TW": "電子零組件", "2395.TW": "電子零組件",
    "2880.TW": "金融保險", "2881.TW": "金融保險", "2882.TW": "金融保險", "2883.TW": "金融保險", "2884.TW": "金融保險", "2885.TW": "金融保險",
    "2886.TW": "金融保險", "2887.TW": "金融保險", "2890.TW": "金融保險", "2891.TW": "金融保險", "2892.TW": "金融保險", "5880.TW": "金融保險", "5871.TW": "金融保險",
    "2603.TW": "航運", "2609.TW": "航運", "2615.TW": "航運", "2618.TW": "航運",
    "2412.TW": "電信消費", "3045.TW": "電信消費", "4904.TW": "電信消費", "1216.TW": "電信消費", "2912.TW": "電信消費",
    "1301.TW": "傳產生技", "1303.TW": "傳產生技", "1326.TW": "傳產生技", "6505.TW": "傳產生技", "2002.TW": "傳產生技", "6446.TW": "傳產生技",
}

STRATEGIES = [
    ("01_bull_trend", "1. 預設多頭趨勢 (Bull Trend)", "趨勢"),
    ("02_ma_golden_cross", "2. 均線金叉 (MA Golden Cross)", "趨勢"),
    ("03_volume_breakout", "3. 放量突破 (Volume Breakout)", "突破"),
    ("04_shrink_pullback", "4. 縮量回踩 (Shrink Pullback)", "趨勢回踩"),
    ("05_bottom_volume", "5. 底部放量 (Bottom Volume)", "反轉"),
    ("06_one_yang_three_yin", "6. 一陽夾三陰 (1 Yang 3 Yin)", "K線形態"),
    ("07_box_oscillation", "7. 箱體震盪 (Box Oscillation)", "震盪回歸"),
    ("08_chan_theory", "8. 纏論背馳/三買 (Chan Theory)", "結構形態"),
    ("09_wave_theory", "9. 波浪黃金坑/三浪 (Wave Theory)", "結構形態"),
    ("10_dragon_head", "10. 龍頭策略 (Dragon Head)", "板塊動能"),
    ("11_hot_theme", "11. 熱點題材共振 (Hot Theme)", "板塊動能"),
    ("12_emotion_cycle", "12. 情緒週期逆向 (Emotion Cycle)", "情緒反轉"),
    ("13_event_driven", "13. 事件驅動代理 (Event Driven)", "事件催化"),
    ("14_expectation_repricing", "14. 預期重估 (Expectation Repricing)", "基本面+趨勢"),
    ("15_growth_quality", "15. 成長品質 (Growth Quality)", "基本面+趨勢"),
]


def pub_date_from_quarter_end(qend: str) -> str:
    y, m, _ = qend.split("-")
    y = int(y)
    if m == "03": return f"{y}-05-15"
    if m == "06": return f"{y}-08-14"
    if m == "09": return f"{y}-11-14"
    if m == "12": return f"{y + 1}-03-31"
    return "9999-12-31"


def load_and_enrich_tw50() -> Tuple[pd.DataFrame, Dict[str, str]]:
    conn = sqlite3.connect(DB_PATH)
    meta = pd.read_sql_query("SELECT ticker, name FROM universe_meta", conn)
    meta_map = dict(zip(meta["ticker"], meta["name"]))

    df = pd.read_sql_query("""
        SELECT s.ticker, s.date, s.raw_open, s.raw_high, s.raw_low, s.raw_close, s.adj_close, s.volume, s.dividends, s.pct_change,
               f.sma_5, f.sma_10, f.sma_20, f.sma_50, f.sma_200, f.rsi_14, f.atr_14,
               f.macd_dif, f.macd_dea, f.macd_hist, f.cyq_profit_ratio,
               v.pe_ratio, v.pb_ratio, v.dividend_yield, v.roe_implied_pct,
               c.inst_total_net_lots
        FROM stock_daily s
        LEFT JOIN daily_factors f ON s.ticker = f.ticker AND s.date = f.date
        LEFT JOIN daily_valuation v ON s.ticker = v.ticker AND s.date = v.date
        LEFT JOIN taiwan_chips_daily c ON s.ticker = c.ticker AND s.date = c.date
        ORDER BY s.ticker, s.date
    """, conn)
    qf = pd.read_sql_query("SELECT * FROM quarterly_fundamentals ORDER BY ticker, quarter_end", conn)
    conn.close()

    qf["pub_date"] = qf["quarter_end"].apply(pub_date_from_quarter_end)
    df["sector"] = df["ticker"].map(TW50_SECTORS).fillna("其他")

    # Precompute PIT quarterly fundamental state per (ticker, date)
    pit_map = {}
    for t, gq in qf[qf["revenue"].notnull() & (qf["revenue"] > 0)].groupby("ticker"):
        gq = gq.sort_values("quarter_end").reset_index(drop=True)
        pit_map[t] = gq

    enriched = []
    for t, g in df.groupby("ticker", sort=False):
        g = g.sort_values("date").reset_index(drop=True)
        g["adj_close"] = g["adj_close"].ffill()
        g["raw_close"] = g["raw_close"].ffill()
        c = g["adj_close"]
        o = g["raw_open"]
        h = g["raw_high"]
        l = g["raw_low"]
        v = g["volume"].fillna(0.0)

        g["vol_ma5"] = v.rolling(5, min_periods=1).mean()
        g["vol_ma20"] = v.rolling(20, min_periods=5).mean()
        g["vol_ma60"] = v.rolling(60, min_periods=10).mean()
        g["vol_ratio5"] = v / (g["vol_ma5"] + 1e-8)
        g["vol_ratio20"] = v / (g["vol_ma20"] + 1e-8)
        g["high_20_prev"] = c.shift(1).rolling(20, min_periods=5).max()
        g["low_20_prev"] = c.shift(1).rolling(20, min_periods=5).min()
        g["high_40"] = c.rolling(40, min_periods=15).max()
        g["low_40"] = c.rolling(40, min_periods=15).min()
        g["low_10"] = g["raw_low"].rolling(10, min_periods=3).min()
        g["ret_10d"] = c.pct_change(10) * 100.0
        g["ret_20d"] = c.pct_change(20) * 100.0
        g["dd_20d"] = (c / c.rolling(20, min_periods=5).max() - 1.0) * 100.0
        g["sma20_slope"] = g["sma_20"] - g["sma_20"].shift(5)
        g["bias_ma5"] = (c / g["sma_5"] - 1.0) * 100.0
        g["bias_ma10"] = (c / g["sma_10"] - 1.0) * 100.0
        g["close_pos"] = (g["raw_close"] - l) / (h - l + 1e-8)
        g["body_pct"] = (g["raw_close"] - o) / (o + 1e-8) * 100.0
        g["ma_spread"] = (g[["sma_5", "sma_10", "sma_20"]].max(axis=1) - g[["sma_5", "sma_10", "sma_20"]].min(axis=1)) / (g["sma_20"] + 1e-8) * 100.0
        g["inst_prev1"] = g["inst_total_net_lots"].shift(1).fillna(0.0)  # strictly T+1 no look-ahead

        # MA cross detection
        g["cross_5_10"] = (g["sma_5"] > g["sma_10"]) & (g["sma_5"].shift(1) <= g["sma_10"].shift(1))
        g["cross_5_10_3d"] = g["cross_5_10"].rolling(3, min_periods=1).max() > 0
        g["cross_10_20"] = (g["sma_10"] > g["sma_20"]) & (g["sma_10"].shift(1) <= g["sma_20"].shift(1))
        g["macd_hist_prev"] = g["macd_hist"].shift(1)
        g["macd_min20"] = g["macd_hist"].rolling(20, min_periods=5).min()
        g["macd_min40_prev"] = g["macd_hist"].shift(10).rolling(30, min_periods=5).min()

        # One Yang Three Yin pattern (t-4 big yang, t-3..t-1 small/inside, t breakout)
        y1_body = g["body_pct"].shift(4) > 2.0
        y1_open = g["raw_open"].shift(4)
        y1_close = g["raw_close"].shift(4)
        hold_low = (g["raw_low"].shift(3) >= y1_open * 0.995) & (g["raw_low"].shift(2) >= y1_open * 0.995) & (g["raw_low"].shift(1) >= y1_open * 0.995)
        shrink_3d = ((v.shift(3) + v.shift(2) + v.shift(1)) / 3.0) < (g["vol_ma5"].shift(4) * 0.95)
        y5_break = (g["raw_close"] > g["raw_open"]) & (g["raw_close"] > y1_close)
        g["pat_1y3y"] = y1_body & hold_low & shrink_3d & y5_break
        g["y1_open_stop"] = y1_open

        # PIT Fundamentals attached daily (no look-ahead)
        gq = pit_map.get(t)
        pit_roe, pit_nm, pit_ocf_ni, pit_rev_g, pit_ni_g = [], [], [], [], []
        for dt_s in g["date"]:
            if gq is not None:
                av = gq[gq["pub_date"] <= dt_s]
            else:
                av = pd.DataFrame()
            if not av.empty:
                t4 = av.tail(4)
                rev_s, ni_s, ocf_s = t4["revenue"].sum(), t4["net_income"].sum(), t4["ocf"].sum()
                nm = (ni_s / rev_s * 100.0) if rev_s > 0 else 0.0
                ocf_ni = (ocf_s / ni_s) if ni_s > 0 else -1.0
                r_roe = t4["roe_ttm_pct"].dropna()
                roe_v = float(r_roe.iloc[-1]) if len(r_roe) > 0 else np.nan
                if len(av) >= 2 and av.iloc[-2]["revenue"] > 0 and av.iloc[-2]["net_income"] > 0:
                    rg = (av.iloc[-1]["revenue"] / av.iloc[-2]["revenue"] - 1.0) * 100.0
                    ng = (av.iloc[-1]["net_income"] / av.iloc[-2]["net_income"] - 1.0) * 100.0
                else:
                    rg, ng = 0.0, 0.0
            else:
                nm = ocf_ni = rg = ng = 0.0
                roe_v = np.nan
            pit_roe.append(roe_v); pit_nm.append(nm); pit_ocf_ni.append(ocf_ni); pit_rev_g.append(rg); pit_ni_g.append(ng)
        g["pit_roe"] = pd.Series(pit_roe).fillna(g["roe_implied_pct"])
        g["pit_nm"] = pit_nm
        g["pit_ocf_ni"] = pit_ocf_ni
        g["pit_rev_g"] = pit_rev_g
        g["pit_ni_g"] = pit_ni_g
        enriched.append(g)

    full = pd.concat(enriched, ignore_index=True)

    # Cross-sectional Sector Momentum & Breadth per date
    sec_stats = full.groupby(["date", "sector"]).agg(
        sec_ret10=("ret_10d", "mean"),
        sec_pct=("pct_change", "mean"),
        sec_breadth=("adj_close", lambda s: 0.0),  # placeholder replaced below
    ).reset_index()
    full["above_ma20"] = (full["adj_close"] > full["sma_20"]).astype(float)
    breadth = full.groupby(["date", "sector"])["above_ma20"].mean().reset_index().rename(columns={"above_ma20": "sec_breadth_val"})
    sec_stats = sec_stats.drop(columns=["sec_breadth"]).merge(breadth, on=["date", "sector"])
    sec_stats["sec_rank"] = sec_stats.groupby("date")["sec_ret10"].rank(ascending=False, method="min")

    full = full.merge(sec_stats, on=["date", "sector"], how="left")
    return full, meta_map


def eval_entry(row: pd.Series, strat_key: str) -> bool:
    c = row["adj_close"]
    if pd.isna(c) or pd.isna(row["sma_20"]):
        return False

    if strat_key == "01_bull_trend":
        return bool(row["sma_5"] >= row["sma_10"] >= row["sma_20"] and row["sma20_slope"] > 0 and c > row["sma_20"] and row["bias_ma5"] < 4.0)

    elif strat_key == "02_ma_golden_cross":
        return bool((row["cross_5_10_3d"] or row["cross_10_20"]) and row["vol_ratio5"] > 1.2 and row["macd_dif"] > row["macd_dea"] and row["bias_ma10"] < 5.0)

    elif strat_key == "03_volume_breakout":
        pe_ok = pd.isna(row["pe_ratio"]) or row["pe_ratio"] <= 50.0
        return bool(c > row["high_20_prev"] and row["vol_ratio5"] > 2.0 and row["close_pos"] >= 0.70 and row["bias_ma5"] < 5.0 and pe_ok)

    elif strat_key == "04_shrink_pullback":
        bull = row["sma_5"] > row["sma_10"] > row["sma_20"]
        near_ma = (abs(row["bias_ma5"]) <= 1.5) or (abs(row["bias_ma10"]) <= 2.0)
        cyq_ok = pd.isna(row["cyq_profit_ratio"]) or (40.0 <= row["cyq_profit_ratio"] <= 85.0)
        return bool(bull and near_ma and row["vol_ratio5"] < 0.70 and c >= row["sma_10"] * 0.99 and cyq_ok)

    elif strat_key == "05_bottom_volume":
        return bool(row["dd_20d"] < -12.0 and row["vol_ratio5"] > 2.5 and row["raw_close"] > row["raw_open"])

    elif strat_key == "06_one_yang_three_yin":
        return bool(row["pat_1y3y"])

    elif strat_key == "07_box_oscillation":
        h40, l40 = row["high_40"], row["low_40"]
        if pd.isna(h40) or pd.isna(l40) or l40 <= 0:
            return False
        width = (h40 - l40) / l40 * 100.0
        pos = (c - l40) / (h40 - l40 + 1e-8)
        return bool(6.0 <= width <= 25.0 and pos <= 0.25 and row["raw_close"] > row["raw_open"])

    elif strat_key == "08_chan_theory":
        # Bottom divergence (1st buy) OR Breakout above 20d pivot (3rd buy)
        div_buy = (c <= row["low_20_prev"] * 1.02) and (row["macd_min20"] > row["macd_min40_prev"]) and (row["macd_hist"] > row["macd_hist_prev"])
        third_buy = (c > row["high_20_prev"]) and (row["macd_dif"] > 0) and (c > row["sma_20"])
        return bool(div_buy or third_buy)

    elif strat_key == "09_wave_theory":
        # Wave 2 golden pit (pullback 38.2%-61.8% in uptrend) OR Wave 3 breakout
        h40, l40 = row["high_40"], row["low_40"]
        retrace = (h40 - c) / (h40 - l40 + 1e-8) if (pd.notnull(h40) and h40 > l40) else 0.0
        wave2 = (row["ret_20d"] > 5.0) and (0.35 <= retrace <= 0.65) and (row["raw_close"] > row["raw_open"]) and (c >= row["sma_20"] * 0.98)
        wave3 = (c > row["high_20_prev"]) and (row["vol_ratio5"] > 1.3) and (row["macd_hist"] > 0)
        return bool(wave2 or wave3)

    elif strat_key == "10_dragon_head":
        return bool(row["sec_rank"] <= 2 and (row["pct_change"] - row["sec_pct"]) > 1.5 and row["vol_ratio5"] > 1.5 and row["bias_ma5"] < 7.0)

    elif strat_key == "11_hot_theme":
        return bool(row["sec_rank"] <= 2 and row["sec_breadth_val"] >= 0.60 and (row["pct_change"] >= row["sec_pct"]) and row["inst_prev1"] > 0 and row["bias_ma5"] < 6.0)

    elif strat_key == "12_emotion_cycle":
        return bool(row["volume"] < 0.65 * row["vol_ma60"] and row["ma_spread"] < 4.5 and (30.0 <= row["rsi_14"] <= 55.0) and c <= row["sma_20"] * 1.02)

    elif strat_key == "13_event_driven":
        return bool(row["pct_change"] > 3.0 and row["vol_ratio20"] > 2.0 and row["ret_20d"] < 15.0 and row["inst_prev1"] > 0)

    elif strat_key == "14_expectation_repricing":
        val_ok = (pd.notnull(row["pe_ratio"]) and 0 < row["pe_ratio"] <= 25.0) or (pd.notnull(row["pb_ratio"]) and row["pb_ratio"] <= 4.0)
        fund_ok = (row["pit_ni_g"] > 5.0 or row["pit_rev_g"] > 5.0) and (row["pit_roe"] >= 12.0)
        return bool(val_ok and fund_ok and c > row["sma_20"] and row["vol_ratio5"] > 1.2)

    elif strat_key == "15_growth_quality":
        return bool(row["pit_roe"] >= 15.0 and row["pit_nm"] >= 12.0 and row["pit_ocf_ni"] >= 0.70 and row["pit_rev_g"] > 0 and c >= row["sma_50"])

    return False


def eval_exit(row: pd.Series, st: dict, strat_key: str) -> bool:
    c = row["adj_close"]
    ep = st["adj_entry"]
    ret_now = (c / ep - 1.0) * 100.0

    if strat_key in ("01_bull_trend", "04_shrink_pullback", "09_wave_theory"):
        return bool(c < row["sma_20"])

    elif strat_key == "02_ma_golden_cross":
        return bool(row["sma_5"] < row["sma_10"] and c < row["sma_20"])

    elif strat_key == "03_volume_breakout":
        return bool(ret_now <= -3.0 or c < row["sma_20"])

    elif strat_key == "05_bottom_volume":
        return bool(row["raw_close"] < st["stop_low"] or (ret_now > 10.0 and row["rsi_14"] > 65.0) or st["hold_bars"] >= 15)

    elif strat_key == "06_one_yang_three_yin":
        return bool(row["raw_close"] < st["stop_low"] or c < row["sma_20"])

    elif strat_key == "07_box_oscillation":
        h40, l40 = row["high_40"], row["low_40"]
        pos = (c - l40) / (h40 - l40 + 1e-8) if (pd.notnull(h40) and h40 > l40) else 0.5
        return bool(pos >= 0.85 or c < st["stop_low"] * 0.97)

    elif strat_key == "08_chan_theory":
        top_div = (c >= row["high_20_prev"] * 0.99) and (row["macd_hist"] < row["macd_hist_prev"]) and (row["macd_hist"] < 0)
        return bool(top_div or c < row["sma_20"])

    elif strat_key == "10_dragon_head":
        return bool(c < row["sma_10"] or (row["sec_rank"] > 3 and c < row["sma_20"]))

    elif strat_key == "11_hot_theme":
        return bool(row["sec_breadth_val"] < 0.40 or c < row["sma_20"])

    elif strat_key == "12_emotion_cycle":
        overheat = (row["vol_ma5"] > 1.8 * row["vol_ma20"] and row["bias_ma5"] > 6.0) or (row["rsi_14"] > 78.0)
        return bool(overheat or ret_now <= -8.0)

    elif strat_key == "13_event_driven":
        stall = (row["vol_ratio5"] > 2.0 and row["raw_close"] < row["raw_open"])
        return bool(stall or c < row["sma_20"] or ret_now <= -6.0)

    elif strat_key == "14_expectation_repricing":
        return bool(c < row["sma_50"] or (pd.notnull(row["pe_ratio"]) and row["pe_ratio"] > 40.0 and c < row["sma_20"]))

    elif strat_key == "15_growth_quality":
        return bool(c < row["sma_50"])

    return False


def simulate_strategy(daily_by_date: Dict[str, pd.DataFrame], all_dates: List[str], strat_key: str, meta_map: Dict[str, str]):
    cash = INITIAL_CASH
    shares: Dict[str, float] = {}
    state: Dict[str, dict] = {}
    eq_curve = []
    exposures = []
    trades = []

    for dt in all_dates:
        d_slice = daily_by_date[dt]

        # Dividends
        for t, sh in shares.items():
            if sh > 0 and t in d_slice.index:
                div = float(d_slice.at[t, "dividends"])
                if pd.notnull(div) and div > 0:
                    cash += sh * div

        # Exits
        for t in list(shares.keys()):
            if shares[t] <= 0 or t not in d_slice.index:
                continue
            row = d_slice.loc[t]
            st = state[t]
            st["hold_bars"] += 1
            if eval_exit(row, st, strat_key):
                px = float(row["raw_close"])
                adj = float(row["adj_close"])
                exec_px = px * (1.0 - TW_SLIPPAGE)
                gross = shares[t] * exec_px
                cost = gross * (TW_COMMISSION + TW_TAX)
                cash += gross - cost
                ret_pct = (adj / st["adj_entry"] - 1.0) * 100.0 - (TW_COMMISSION * 2 + TW_TAX + TW_SLIPPAGE * 2) * 100.0
                pnl = (exec_px - st["raw_entry"]) * shares[t] - cost - st["buy_cost"]
                hold_days = (pd.Timestamp(dt) - pd.Timestamp(st["entry_date"])).days
                trades.append({
                    "strategy": strat_key, "ticker": t, "name": meta_map.get(t, t),
                    "entry_date": st["entry_date"], "exit_date": dt,
                    "net_pnl": round(pnl, 2), "return_pct": round(ret_pct, 2), "hold_days": hold_days,
                    "status": "WIN" if ret_pct > 0 else "LOSS",
                })
                shares.pop(t, None)
                state.pop(t, None)

        # Entries (fill up to MAX_SLOTS)
        open_slots = MAX_SLOTS - len(shares)
        if open_slots > 0 and cash > 10_000.0:
            cands = []
            for t, row in d_slice.iterrows():
                if t in shares:
                    continue
                if eval_entry(row, strat_key):
                    # Deterministic priority: higher relative volume / ROE
                    prio = float(row["vol_ratio5"]) if pd.notnull(row["vol_ratio5"]) else 1.0
                    cands.append((prio, t, row))
            cands.sort(key=lambda x: x[0], reverse=True)
            chosen = cands[:open_slots]
            if chosen:
                port_val = cash + sum(sh * float(d_slice.at[t, "raw_close"]) for t, sh in shares.items() if sh > 0)
                slot_cash = port_val / MAX_SLOTS
                for _, t, row in chosen:
                    alloc = min(slot_cash, cash * 0.995)
                    if alloc < 10_000.0:
                        break
                    px = float(row["raw_close"])
                    exec_px = px * (1.0 + TW_SLIPPAGE)
                    bsh = alloc / (exec_px * (1.0 + TW_COMMISSION))
                    bcost = bsh * exec_px * TW_COMMISSION
                    if bsh * exec_px + bcost <= cash + 1e-6:
                        cash -= bsh * exec_px + bcost
                        shares[t] = bsh
                        stop_low = float(row["y1_open_stop"]) if (strat_key == "06_one_yang_three_yin" and pd.notnull(row["y1_open_stop"])) else (
                            float(row["low_40"]) if (strat_key == "07_box_oscillation" and pd.notnull(row["low_40"])) else float(row["low_10"])
                        )
                        state[t] = {
                            "entry_date": dt, "raw_entry": exec_px, "adj_entry": float(row["adj_close"]),
                            "buy_cost": bcost, "hold_bars": 0, "stop_low": stop_low,
                        }

        inv = sum(sh * float(d_slice.at[t, "raw_close"]) for t, sh in shares.items() if sh > 0)
        eq = cash + inv
        eq_curve.append((dt, eq))
        exposures.append(inv / eq * 100.0 if eq > 0 else 0.0)

    # Mark-to-market open trades
    last_dt = all_dates[-1]
    d_last = daily_by_date[last_dt]
    for t, st in state.items():
        if shares.get(t, 0.0) > 0:
            px = float(d_last.at[t, "raw_close"])
            adj = float(d_last.at[t, "adj_close"])
            ret_pct = (adj / st["adj_entry"] - 1.0) * 100.0 - (TW_COMMISSION + TW_SLIPPAGE) * 100.0
            pnl = (px - st["raw_entry"]) * shares[t] - st["buy_cost"]
            hold_days = (pd.Timestamp(last_dt) - pd.Timestamp(st["entry_date"])).days
            trades.append({
                "strategy": strat_key, "ticker": t, "name": meta_map.get(t, t),
                "entry_date": st["entry_date"], "exit_date": last_dt,
                "net_pnl": round(pnl, 2), "return_pct": round(ret_pct, 2), "hold_days": hold_days,
                "status": "OPEN",
            })

    eq_s = pd.Series(dict(eq_curve))
    eq_s.index = pd.to_datetime(eq_s.index)
    return eq_s, trades, float(np.mean(exposures))


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
    payoff = (float(np.mean(wins)) / abs(float(np.mean(losses)))) if (wins and losses) else 0.0
    gw = sum(t["net_pnl"] for t in trades if t["net_pnl"] > 0)
    gl = abs(sum(t["net_pnl"] for t in trades if t["net_pnl"] < 0))
    pf = min(gw / gl, 99.0) if gl > 1e-6 else (99.0 if gw > 0 else 0.0)
    exp_ntd = float(np.mean([t["net_pnl"] for t in trades])) if n_tr else 0.0
    chop = sum(t["net_pnl"] for t in trades if t["hold_days"] <= 10)

    return {
        "total_return_pct": round(tot, 2), "alpha_pct": round(tot - bm_ret, 2),
        "ann_vol_pct": round(vol, 2), "sharpe": round(sharpe, 2), "sortino": round(sortino, 2),
        "calmar": round(calmar, 2), "mdd_pct": round(mdd, 2), "avg_exposure_pct": round(avg_exp, 1),
        "trades": n_tr, "win_rate_pct": round(wr, 1), "payoff_ratio": round(payoff, 2),
        "profit_factor": round(pf, 2), "expectancy_ntd": round(exp_ntd, 0), "chop_tax_ntd": round(chop, 0),
    }


def main():
    print("Loading & enriching TW50 data for 15 DSA strategies...")
    full, meta_map = load_and_enrich_tw50()
    daily_by_date = {dt: g.set_index("ticker") for dt, g in full.groupby("date")}
    all_dates = sorted(daily_by_date.keys())

    adj_piv = full.pivot(index="date", columns="ticker", values="adj_close").sort_index().ffill()
    bm_tw50 = adj_piv.div(adj_piv.iloc[0]).mean(axis=1) * INITIAL_CASH
    bm_tw50.index = pd.to_datetime(bm_tw50.index)

    rows = []
    eq_map = {"BM_TW50_EW": bm_tw50}
    all_trades = []

    for skey, slbl, scat in STRATEGIES:
        eq, tr, exp = simulate_strategy(daily_by_date, all_dates, skey, meta_map)
        eq_map[skey] = eq
        all_trades.extend(tr)
        met = calc_stats(eq, bm_tw50, tr, exp)
        met["strategy_key"] = skey
        met["label"] = slbl
        met["category"] = scat
        rows.append(met)

    bm_met = calc_stats(bm_tw50, bm_tw50, [], 100.0)
    bm_met["strategy_key"] = "BM_TW50_EW"
    bm_met["label"] = "基準：台灣50 等權 B&H (TW50 EW)"
    bm_met["category"] = "基準"
    rows.append(bm_met)

    res_df = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    print("\n=== ALL 15 DSA STRATEGIES ON TW50 (SORTED BY SHARPE) ===")
    cols = ["label", "category", "total_return_pct", "sharpe", "mdd_pct", "avg_exposure_pct", "trades", "win_rate_pct", "profit_factor", "chop_tax_ntd"]
    print(res_df[cols].to_string(index=False))

    # Persist SQLite
    db_out = os.path.join(OUT_DIR, "backtest_result.db")
    if os.path.exists(db_out): os.remove(db_out)
    conn = sqlite3.connect(db_out)
    res_df.to_sql("backtest_summary", conn, index=False, if_exists="replace")
    pd.DataFrame(all_trades).to_sql("backtest_trades", conn, index=False, if_exists="replace")
    eq_df = pd.DataFrame(eq_map)
    eq_df.index.name = "date"
    eq_df.reset_index().to_sql("backtest_equity_curve", conn, index=False, if_exists="replace")
    conn.close()

    # Build HTML & Markdown reports
    build_html(res_df, eq_map, all_dates[0], all_dates[-1])
    build_md(res_df, all_dates[0], all_dates[-1])
    print(f"\nSaved all 15-strategy results to {OUT_DIR}/")


def build_html(res_df: pd.DataFrame, eq_map: Dict[str, pd.Series], start_dt: str, end_dt: str):
    # Top 6 + Benchmark Equity Curves
    top_keys = list(res_df[res_df["strategy_key"] != "BM_TW50_EW"].head(6)["strategy_key"]) + ["BM_TW50_EW"]
    fig1 = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.68, 0.32],
                         subplot_titles=("Top 6 策略累計報酬 % vs TW50 等權基準", "水下回撤深度 % (MDD)"))
    palette = ["#00D084", "#38BDF8", "#FCD34D", "#A78BFA", "#F472B6", "#FB923C", "#94A3B8"]
    for idx, k in enumerate(top_keys):
        eq = eq_map[k]
        lbl = res_df[res_df["strategy_key"] == k].iloc[0]["label"]
        is_bm = k == "BM_TW50_EW"
        fig1.add_trace(go.Scatter(x=eq.index, y=(eq / eq.iloc[0] - 1.0) * 100.0, name=lbl,
                                  line=dict(color=palette[idx % len(palette)], width=2.0 if is_bm else 2.5, dash="dot" if is_bm else "solid")), row=1, col=1)
        fig1.add_trace(go.Scatter(x=eq.index, y=(eq / eq.cummax() - 1.0) * 100.0, showlegend=False,
                                  line=dict(color=palette[idx % len(palette)], width=1.4 if is_bm else 1.8, dash="dot" if is_bm else "solid")), row=2, col=1)
    fig1.update_layout(template="plotly_dark", paper_bgcolor="#181C25", plot_bgcolor="#14171F", height=580, hovermode="x unified",
                       legend=dict(orientation="h", yanchor="bottom", y=1.04, x=0, font=dict(size=11)))

    # Bar chart: Sharpe & Return of all 15
    s_only = res_df[res_df["strategy_key"] != "BM_TW50_EW"].sort_values("sharpe", ascending=True)
    fig2 = make_subplots(rows=1, cols=2, subplot_titles=("15 大策略 Sharpe Ratio 排行", "15 大策略累計報酬率 % 排行"))
    fig2.add_trace(go.Bar(y=s_only["label"], x=s_only["sharpe"], orientation="h", showlegend=False,
                          marker_color=["#00D084" if v >= 2.0 else ("#38BDF8" if v >= 1.0 else "#FF4D4F") for v in s_only["sharpe"]],
                          text=[f"{v:.2f}" for v in s_only["sharpe"]], textposition="outside"), row=1, col=1)
    fig2.add_trace(go.Bar(y=s_only["label"], x=s_only["total_return_pct"], orientation="h", showlegend=False,
                          marker_color=["#00D084" if v >= 40 else ("#FCD34D" if v >= 15 else "#FF4D4F") for v in s_only["total_return_pct"]],
                          text=[f"{v:+.1f}%" for v in s_only["total_return_pct"]], textposition="outside"), row=1, col=2)
    fig2.update_layout(template="plotly_dark", paper_bgcolor="#181C25", plot_bgcolor="#14171F", height=540, margin=dict(l=240, r=45, t=55, b=40))

    rows_html = "".join(f"""
      <tr>
        <td><strong>{r['label']}</strong></td><td>{r['category']}</td>
        <td class="{'pos' if r['total_return_pct']>=0 else 'neg'}">{r['total_return_pct']:+.2f}%</td>
        <td>{r['sharpe']:.2f}</td><td>{r['sortino']:.2f}</td><td class="neg">{r['mdd_pct']:.2f}%</td>
        <td>{r['avg_exposure_pct']:.1f}%</td><td>{int(r['trades'])}</td><td>{r['win_rate_pct']:.1f}%</td>
        <td>{r['profit_factor']:.2f}</td><td class="{'pos' if r['chop_tax_ntd']>=0 else 'neg'}">{r['chop_tax_ntd']:+,.0f}</td>
      </tr>""" for _, r in res_df.iterrows())

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="UTF-8" /><title>TW50 15 大 DSA 內置策略量化評比報告</title>
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
  <h1>🏆 TW50 實證評比：15 大內置策略 (daily_stock_analysis) 全景回測報告</h1>
  <p style="color:#94A3B8">標的池：TW50 (50 檔) ｜ 區間：{start_dt} ~ {end_dt} ｜ 資金：100 萬 NTD（最多 10 檔等權倉位）｜ 台股真實摩擦：0.0855% 手續費 + 0.3% 證交稅 + 0.05% 滑價</p>
  <div class="card">
    <h2>1. 15 大策略完整績效總表（按 Sharpe 排序）</h2>
    <table><thead><tr>
      <th>策略名稱</th><th>類型</th><th>累計報酬</th><th>Sharpe</th><th>Sortino</th><th>MDD</th>
      <th>平均曝險</th><th>交易數</th><th>勝率</th><th>獲利因子 PF</th><th>短線摩擦稅 (<=10d)</th>
    </tr></thead><tbody>{rows_html}</tbody></table>
  </div>
  <div class="card"><div id="f2"></div></div>
  <div class="card"><div id="f1"></div></div>
</div>
<script>
  Plotly.newPlot('f2', {fig2.to_json()}.data, {fig2.to_json()}.layout, {{responsive:true}});
  Plotly.newPlot('f1', {fig1.to_json()}.data, {fig1.to_json()}.layout, {{responsive:true}});
</script></body></html>"""
    with open(os.path.join(OUT_DIR, "tw50_dsa15_QuantStats_Report.html"), "w", encoding="utf-8") as f:
        f.write(html)


def build_md(res_df: pd.DataFrame, start_dt: str, end_dt: str):
    lines = [
        "# TW50 實證評比：15 大內置策略 (`05_strategy_original_prompts.md`) 回測報告",
        "",
        f"- **標的池**：`data/tw50/tw50_2026.db`（50 檔台灣 50 成分股）｜ **區間**：`{start_dt}` ～ `{end_dt}`",
        "- **統一撮合口徑**：初始本金 `1,000,000 NTD`，最多同時持有 `10` 檔（單檔 10% 倉位），嚴格雙軌價格（`Adj_Close` 訊號、`Raw_Close` 撮合+股息）、T+1 法人籌碼與 PIT 財報防未來函數、台股真實手續費 `0.0855%` + 證交稅 `0.3%` + 滑價 `0.05%`。",
        "",
        "## 1. 15 大策略績效排行榜（按 Sharpe 排序）",
        "",
        "| 策略名稱 | 類型 | 累計報酬 | Sharpe | Sortino | 最大回撤 MDD | 平均曝險 | 交易數 | 勝率 | 獲利因子 PF | 短線摩擦稅 (`<=10d`) |",
        "| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, r in res_df.iterrows():
        lines.append(
            f"| {r['label']} | {r['category']} | {r['total_return_pct']:+.2f}% | {r['sharpe']:.2f} | {r['sortino']:.2f} | "
            f"{r['mdd_pct']:.2f}% | {r['avg_exposure_pct']:.1f}% | {int(r['trades'])} | {r['win_rate_pct']:.1f}% | "
            f"{r['profit_factor']:.2f} | {r['chop_tax_ntd']:+,.0f} |"
        )
    with open(os.path.join(OUT_DIR, "backtest_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
