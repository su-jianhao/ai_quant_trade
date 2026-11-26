"""
modules/backtest_sox30_verify.py
跨市場・跨多空週期 (2020-2026 近 7 年，含 2022 科技大熊市) SOX 30 半導體策略全面驗證！
驗證我們在 TW50 得出的核心結論（VWAP、神奇九轉、MACD改良、布林、海龜、三位一體、DSA情緒/箱體、B&H）
在美股高波動科技指數上是否依然成立。
輸出至：trades/sox30_verify_20261125/
"""
from __future__ import annotations

import os
import sqlite3
from typing import Dict, List

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

DB_PATH = "data/sox_mag7_price_vol_types/price_vol_analysis.db"
OUT_DIR = os.path.join("trades", "sox30_verify_20261125")
os.makedirs(OUT_DIR, exist_ok=True)

# US Stock Friction (prompts/backtest.md)
US_COMMISSION = 0.0003
US_TAX = 0.0
US_SLIPPAGE = 0.0005
INITIAL_CASH = 100_000.0
MAX_SLOTS = 10


def compute_td_setup(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    vals = close.values
    n = len(vals)
    tb = np.zeros(n, dtype=int)
    ts = np.zeros(n, dtype=int)
    for i in range(4, n):
        if vals[i] < vals[i - 4]:
            tb[i] = tb[i - 1] + 1
        elif vals[i] > vals[i - 4]:
            ts[i] = ts[i - 1] + 1
    return pd.Series(tb, index=close.index), pd.Series(ts, index=close.index)


def load_and_compute_sox30():
    conn = sqlite3.connect(DB_PATH)
    sox_syms = pd.read_sql_query("SELECT symbol FROM stock_archetypes WHERE is_sox = 1", conn)["symbol"].tolist()
    df = pd.read_sql_query(
        f"SELECT date, symbol, open, high, low, close, volume FROM bar_price_vol WHERE symbol IN ({','.join(['?']*len(sox_syms))}) ORDER BY symbol, date",
        conn, params=sox_syms
    )
    soxx_df = pd.read_sql_query("SELECT date, close FROM bar_price_vol WHERE symbol = 'SOXX' ORDER BY date", conn)
    conn.close()

    frames = []
    for sym, g in df.groupby("symbol", sort=False):
        g = g.sort_values("date").reset_index(drop=True)
        c = g["close"].ffill()
        o = g["open"].ffill()
        h = g["high"].ffill()
        l = g["low"].ffill()
        v = g["volume"].fillna(1.0).clip(lower=1.0)
        g["close"] = c

        # Moving averages
        g["sma_5"] = c.rolling(5).mean()
        g["sma_10"] = c.rolling(10).mean()
        g["sma_20"] = c.rolling(20).mean()
        g["sma_50"] = c.rolling(50).mean()
        g["sma_200"] = c.rolling(200).mean()
        g["sma50_slope"] = g["sma_50"] - g["sma_50"].shift(5)

        # VWAP 20 / 60
        tp = (h + l + c) / 3.0
        pv = tp * v
        g["vwap_20"] = pv.rolling(20, min_periods=5).sum() / v.rolling(20, min_periods=5).sum()
        g["vwap_60"] = pv.rolling(60, min_periods=10).sum() / v.rolling(60, min_periods=10).sum()

        # MACD (12, 26, 9)
        ema12 = c.ewm(span=12, adjust=False).mean()
        ema26 = c.ewm(span=26, adjust=False).mean()
        g["macd_dif"] = ema12 - ema26
        g["macd_dea"] = g["macd_dif"].ewm(span=9, adjust=False).mean()
        g["macd_hist"] = g["macd_dif"] - g["macd_dea"]
        g["macd_gc"] = (g["macd_dif"] > g["macd_dea"]) & (g["macd_dif"].shift(1) <= g["macd_dea"].shift(1))
        g["macd_dc"] = (g["macd_dif"] < g["macd_dea"]) & (g["macd_dif"].shift(1) >= g["macd_dea"].shift(1))

        # RSI 14
        delta = c.diff()
        gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
        g["rsi_14"] = 100.0 - (100.0 / (1.0 + gain / (loss + 1e-12)))
        g["rsi_prev"] = g["rsi_14"].shift(1)

        # Bollinger (20, 2)
        std20 = c.rolling(20).std()
        g["boll_mid"] = g["sma_20"]
        g["boll_upper"] = g["sma_20"] + 2.0 * std20
        g["boll_lower"] = g["sma_20"] - 2.0 * std20
        g["boll_bw"] = np.where(g["boll_mid"] > 0, (g["boll_upper"] - g["boll_lower"]) / g["boll_mid"], 0.0)
        g["boll_bw_prev5"] = g["boll_bw"].shift(5)

        # KDJ (9, 3, 3)
        l9 = l.rolling(9).min()
        h9 = h.rolling(9).max()
        rsv = np.where(h9 > l9, (c - l9) / (h9 - l9) * 100.0, 50.0)
        k = pd.Series(rsv, index=g.index).ewm(alpha=1/3, adjust=False).mean()
        d = k.ewm(alpha=1/3, adjust=False).mean()
        g["kdj_k"] = k
        g["kdj_d"] = d
        g["kdj_j"] = 3 * k - 2 * d
        g["kdj_gc"] = (k > d) & (k.shift(1) <= d.shift(1))
        g["kdj_dc"] = (k < d) & (k.shift(1) >= d.shift(1))

        # ATR 14
        tr = pd.concat([(h - l), (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
        g["atr_14"] = tr.ewm(alpha=1/14, adjust=False).mean()

        # Donchian & Box & Emotion
        g["don_h20"] = c.shift(1).rolling(20).max()
        g["don_l10"] = c.shift(1).rolling(10).min()
        g["don_h55"] = c.shift(1).rolling(55).max()
        g["don_l20"] = c.shift(1).rolling(20).min()
        g["high_40"] = c.rolling(40).max()
        g["low_40"] = c.rolling(40).min()
        g["vol_ma5"] = v.rolling(5).mean()
        g["vol_ma20"] = v.rolling(20).mean()
        g["vol_ma60"] = v.rolling(60).mean()
        g["vol_ratio5"] = v / (g["vol_ma5"] + 1e-8)
        g["bias_ma5"] = (c / g["sma_5"] - 1.0) * 100.0
        g["ma_spread"] = (g[["sma_5", "sma_10", "sma_20"]].max(axis=1) - g[["sma_5", "sma_10", "sma_20"]].min(axis=1)) / (g["sma_20"] + 1e-8) * 100.0
        g["prev_c"] = c.shift(1)
        g["prev_vwap20"] = g["vwap_20"].shift(1)
        g["prev_upper"] = g["boll_upper"].shift(1)
        g["prev_lower"] = g["boll_lower"].shift(1)

        # TD Sequential
        tb, ts = compute_td_setup(c)
        g["td_buy"] = tb
        g["td_sell"] = ts
        g["td_buy_max3"] = tb.rolling(3, min_periods=1).max()

        frames.append(g)

    full = pd.concat(frames, ignore_index=True)
    # Slice post-warmup: start 2020-04-01 so all 60D indicators are fully warmed up
    full = full[full["date"] >= "2020-04-01"].reset_index(drop=True)
    soxx_s = soxx_df[soxx_df["date"] >= "2020-04-01"].set_index("date")["close"]
    return full, soxx_s


def check_entry(row: pd.Series, skey: str) -> bool:
    c = row["close"]
    if pd.isna(c) or pd.isna(row["sma_50"]) or pd.isna(row["vwap_60"]):
        return False
    bull_bar = c > row["open"]
    rebound = bull_bar and (c > row["prev_c"])

    if skey == "vwap_20_baseline":
        return bool(row["prev_c"] <= row["prev_vwap20"] and c > row["vwap_20"])
    elif skey == "vwap_20_60_trend":
        # Refined VWAP: 20D >= 60D bullish cost + price >= 20D VWAP + no chase (<4%) + volume confirm
        return bool(c >= row["vwap_20"] and row["vwap_20"] >= row["vwap_60"] and (c / row["vwap_20"] - 1.0) < 0.04 and row["vol_ratio5"] > 1.0)
    elif skey == "vwap_pullback":
        return bool(c >= row["vwap_60"] and row["vwap_20"] >= row["vwap_60"] and -0.02 <= (c / row["vwap_20"] - 1.0) <= 0.025 and bull_bar)
    elif skey == "td_baseline":
        return bool(row["td_buy"] == 9)
    elif skey == "td_trend_dip":
        uptrend = (pd.notnull(row["sma_200"]) and c >= row["sma_200"]) or (row["sma50_slope"] > 0)
        return bool(uptrend and row["td_buy_max3"] >= 7 and rebound)
    elif skey == "sma50_trend":
        return bool(c >= row["sma_50"] and row["prev_c"] < row["sma_50"])
    elif skey == "macd_raw":
        return bool(row["macd_gc"])
    elif skey == "macd_water_bb":
        return bool((row["macd_dif"] <= 0 and row["macd_gc"] and c >= row["boll_mid"]) or (row["macd_gc"] and c > row["sma_50"]))
    elif skey == "boll_combo":
        return bool(c > row["boll_upper"] and row["boll_bw"] >= 0.15 and row["boll_bw"] > row["boll_bw_prev5"])
    elif skey == "rsi_oversold":
        return bool(row["rsi_prev"] <= 32.0 and row["rsi_14"] > 32.0)
    elif skey == "rsi_breakout":
        return bool(row["rsi_prev"] <= 55.0 and row["rsi_14"] > 55.0 and c >= row["sma_50"])
    elif skey == "kdj_oversold":
        return bool(row["kdj_gc"] and row["kdj_k"] < 35.0 and row["kdj_j"] < 20.0)
    elif skey == "grand_trinity":
        l1 = (row["macd_dif"] > 0) or (row["macd_dif"] <= 0 and row["macd_gc"])
        bb_f = (row["prev_c"] <= row["prev_upper"]) and (c > row["boll_upper"])
        l2 = (c > row["boll_mid"]) and ((row["boll_bw"] >= 0.12 and row["boll_bw"] > row["boll_bw_prev5"]) or bb_f)
        l3 = (row["kdj_gc"] and row["kdj_k"] < 65.0 and (row["kdj_k"] < 45.0 or row["kdj_j"] < 20.0 or row["macd_dif"] > 0)) or (bb_f and row["kdj_k"] < 85.0)
        return bool(l1 and l2 and l3)
    elif skey == "turtle_sys2":
        return bool(c >= row["sma_50"] and row["sma_20"] >= row["sma_50"] and c > row["don_h55"])
    elif skey == "dsa_emotion_cycle":
        return bool(row["volume"] < 0.65 * row["vol_ma60"] and row["ma_spread"] < 5.0 and (30.0 <= row["rsi_14"] <= 55.0) and c <= row["sma_20"] * 1.02)
    elif skey == "dsa_box_osc":
        h40, l40 = row["high_40"], row["low_40"]
        if pd.isna(h40) or pd.isna(l40) or l40 <= 0: return False
        w = (h40 - l40) / l40 * 100.0
        pos = (c - l40) / (h40 - l40 + 1e-8)
        return bool(8.0 <= w <= 30.0 and pos <= 0.25 and bull_bar)
    return False


def check_exit(row: pd.Series, st: dict, skey: str) -> str:
    c = row["close"]
    ep = st["entry"]
    peak = st["peak"]
    mfe = (peak / ep - 1.0) * 100.0
    ret = (c / ep - 1.0) * 100.0
    atr = float(row["atr_14"]) if (pd.notnull(row["atr_14"]) and row["atr_14"] > 0) else c * 0.03

    if skey == "vwap_20_baseline":
        return "EXIT" if c < row["vwap_20"] else "HOLD"
    elif skey in ("vwap_20_60_trend", "vwap_pullback"):
        return "EXIT" if c < row["vwap_60"] else "HOLD"
    elif skey == "td_baseline":
        return "EXIT" if (row["td_sell"] >= 9 or ret <= -8.0) else "HOLD"
    elif skey == "td_trend_dip":
        if (not st["trimmed"]) and row["td_sell"] >= 9 and ret > 10.0:
            return "TRIM_HALF"
        return "EXIT" if (c < row["sma_50"] or ret <= -8.0) else "HOLD"
    elif skey == "sma50_trend":
        return "EXIT" if c < row["sma_50"] else "HOLD"
    elif skey == "macd_raw":
        return "EXIT" if row["macd_dc"] else "HOLD"
    elif skey == "macd_water_bb":
        stop = row["boll_mid"]
        if mfe >= 15.0: stop = max(stop, peak - 2.5 * atr)
        return "EXIT" if (c < stop or row["macd_dc"]) else "HOLD"
    elif skey in ("boll_combo", "grand_trinity"):
        stop = row["boll_mid"]
        if mfe >= 10.0: stop = max(stop, ep * 1.015)
        if mfe >= 20.0: stop = max(stop, peak - 2.5 * atr)
        return "EXIT" if c < stop else "HOLD"
    elif skey == "rsi_oversold":
        return "EXIT" if (row["rsi_14"] >= 60.0 or ret <= -8.0) else "HOLD"
    elif skey == "rsi_breakout":
        return "EXIT" if c < row["sma_20"] else "HOLD"
    elif skey == "kdj_oversold":
        if row["kdj_k"] > 80.0 and row["kdj_j"] > 100.0:
            return "EXIT" if c < row["sma_10"] else "HOLD"
        return "EXIT" if ((row["kdj_k"] > 65.0 and row["kdj_dc"]) or ret <= -8.0) else "HOLD"
    elif skey == "turtle_sys2":
        return "EXIT" if (c < ep - 2.0 * atr or c < row["don_l20"]) else "HOLD"
    elif skey == "dsa_emotion_cycle":
        overheat = (row["vol_ma5"] > 1.8 * row["vol_ma20"] and row["bias_ma5"] > 6.0) or (row["rsi_14"] > 78.0)
        return "EXIT" if (overheat or ret <= -8.0) else "HOLD"
    elif skey == "dsa_box_osc":
        h40, l40 = row["high_40"], row["low_40"]
        pos = (c - l40) / (h40 - l40 + 1e-8) if (pd.notnull(h40) and h40 > l40) else 0.5
        return "EXIT" if (pos >= 0.85 or c < st["stop_low"] * 0.97) else "HOLD"
    return "HOLD"


def simulate(by_date: Dict[str, pd.DataFrame], dates: List[str], skey: str):
    cash = INITIAL_CASH
    shares: Dict[str, float] = {}
    state: Dict[str, dict] = {}
    eq_curve, exposures, trades = [], [], []

    for dt in dates:
        ds = by_date[dt]
        # Exits
        for t in list(shares.keys()):
            if shares[t] <= 0 or t not in ds.index: continue
            row = ds.loc[t]
            st = state[t]
            c = float(row["close"])
            if c > st["peak"]: st["peak"] = c
            act = check_exit(row, st, skey)
            if act == "EXIT":
                px = c * (1.0 - US_SLIPPAGE)
                gross = shares[t] * px
                cost = gross * (US_COMMISSION + US_TAX)
                cash += gross - cost
                ret_pct = (px / st["entry"] - 1.0) * 100.0 - (US_COMMISSION * 2) * 100.0
                pnl = (px - st["entry"]) * shares[t] - cost - st["bcost"]
                trades.append({"net_pnl": pnl, "return_pct": ret_pct, "hold_days": (pd.Timestamp(dt) - pd.Timestamp(st["dt"])).days})
                shares.pop(t, None); state.pop(t, None)
            elif act == "TRIM_HALF":
                sh_s = shares[t] * 0.5
                px = c * (1.0 - US_SLIPPAGE)
                gross = sh_s * px
                cost = gross * (US_COMMISSION + US_TAX)
                cash += gross - cost
                shares[t] -= sh_s
                st["trimmed"] = True
                ret_pct = (px / st["entry"] - 1.0) * 100.0 - (US_COMMISSION * 2) * 100.0
                pnl = (px - st["entry"]) * sh_s - cost - st["bcost"] * 0.5
                st["bcost"] *= 0.5
                trades.append({"net_pnl": pnl, "return_pct": ret_pct, "hold_days": (pd.Timestamp(dt) - pd.Timestamp(st["dt"])).days})

        # Entries
        open_slots = MAX_SLOTS - len(shares)
        if open_slots > 0 and cash > 1_000.0:
            cands = []
            for t, row in ds.iterrows():
                if t in shares: continue
                if check_entry(row, skey):
                    prio = float(row["vol_ratio5"]) if pd.notnull(row["vol_ratio5"]) else 1.0
                    cands.append((prio, t, row))
            cands.sort(key=lambda x: x[0], reverse=True)
            chosen = cands[:open_slots]
            if chosen:
                pv = cash + sum(sh * float(ds.at[t, "close"]) for t, sh in shares.items() if t in ds.index and sh > 0)
                slot_cash = pv / MAX_SLOTS
                for _, t, row in chosen:
                    alloc = min(slot_cash, cash * 0.995)
                    if alloc < 1_000.0: break
                    px = float(row["close"]) * (1.0 + US_SLIPPAGE)
                    bsh = alloc / (px * (1.0 + US_COMMISSION))
                    bcost = bsh * px * US_COMMISSION
                    if bsh * px + bcost <= cash + 1e-6:
                        cash -= bsh * px + bcost
                        shares[t] = bsh
                        c_p = float(row["close"])
                        state[t] = {"dt": dt, "entry": px, "peak": c_p, "bcost": bcost, "trimmed": False,
                                    "stop_low": float(row["low_40"]) if pd.notnull(row["low_40"]) else c_p * 0.92}

        inv = sum(sh * float(ds.at[t, "close"]) for t, sh in shares.items() if t in ds.index and sh > 0)
        eq = cash + inv
        eq_curve.append((dt, eq))
        exposures.append(inv / eq * 100.0 if eq > 0 else 0.0)

    eq_s = pd.Series(dict(eq_curve))
    eq_s.index = pd.to_datetime(eq_s.index)
    return eq_s, trades, float(np.mean(exposures))


def stats(eq: pd.Series, trades: List[dict], avg_exp: float) -> dict:
    rets = eq.pct_change().dropna()
    tot = (eq.iloc[-1] / eq.iloc[0] - 1.0) * 100.0
    n_yrs = max(len(rets) / 252.0, 0.1)
    cagr = ((eq.iloc[-1] / eq.iloc[0]) ** (1.0 / n_yrs) - 1.0) * 100.0
    vol = float(rets.std() * np.sqrt(252) * 100.0)
    excess = rets - 0.03 / 252.0  # US 3% avg rf over 2020-2026
    sharpe = float((excess.mean() / (rets.std() + 1e-12)) * np.sqrt(252)) if vol > 1e-6 else 0.0
    mdd = float(((eq / eq.cummax()) - 1.0).min() * 100.0)
    calmar = float(cagr / abs(mdd)) if mdd < -1e-6 else 0.0

    # 2022 Bear Market Crash slice
    eq22 = eq.loc["2022-01-01":"2022-12-31"]
    ret22 = (eq22.iloc[-1] / eq22.iloc[0] - 1.0) * 100.0 if len(eq22) > 20 else 0.0
    mdd22 = float(((eq22 / eq22.cummax()) - 1.0).min() * 100.0) if len(eq22) > 20 else 0.0

    n_tr = len(trades)
    wr = (sum(1 for t in trades if t["return_pct"] > 0) / n_tr * 100.0) if n_tr else 0.0
    gw = sum(t["net_pnl"] for t in trades if t["net_pnl"] > 0)
    gl = abs(sum(t["net_pnl"] for t in trades if t["net_pnl"] < 0))
    pf = min(gw / gl, 99.0) if gl > 1e-6 else 0.0
    return {
        "total_ret_pct": round(tot, 1), "cagr_pct": round(cagr, 2), "sharpe": round(sharpe, 2),
        "calmar": round(calmar, 2), "mdd_pct": round(mdd, 2),
        "ret_2022_pct": round(ret22, 1), "mdd_2022_pct": round(mdd22, 1),
        "exp_pct": round(avg_exp, 1), "trades": n_tr, "win_rate": round(wr, 1), "pf": round(pf, 2),
    }


def main():
    print("Loading 7-year SOX 30 multi-cycle data (2020-04 ~ 2026-11, incl. 2022 Tech Crash)...")
    full, soxx_s = load_and_compute_sox30()
    by_date = {dt: g.set_index("symbol") for dt, g in full.groupby("date")}
    dates = sorted(by_date.keys())
    piv = full.pivot(index="date", columns="symbol", values="close").sort_index().ffill()
    # Equal-weight SOX 30 B&H (daily equal-weight mean return compounded, handles late IPOs like ARM/GFS cleanly!)
    ew_rets = piv.pct_change().mean(axis=1).fillna(0.0)
    bm_ew = (1.0 + ew_rets).cumprod() * INITIAL_CASH
    bm_ew.index = pd.to_datetime(bm_ew.index)

    soxx_al = soxx_s.reindex(dates).ffill()
    bm_soxx = (soxx_al / soxx_al.iloc[0]) * INITIAL_CASH
    bm_soxx.index = pd.to_datetime(bm_soxx.index)

    roster = [
        ("vwap_20_60_trend", "VWAP 改良：20D/60D成本多頭 (守60D)", "VWAP"),
        ("vwap_20_baseline", "VWAP 基準：20D VWAP 突破/跌破", "VWAP"),
        ("vwap_pullback", "VWAP 回踩：多頭回測20D (守60D)", "VWAP"),
        ("td_trend_dip", "神奇九轉改良：多頭TD7+低吸+高九減半", "TD9"),
        ("td_baseline", "神奇九轉基準：純低九買/高九賣", "TD9"),
        ("sma50_trend", "SMA50 季線趨勢進出", "均線"),
        ("macd_water_bb", "MACD 水下+布林中軌", "MACD"),
        ("macd_raw", "MACD 原始金叉死叉", "MACD"),
        ("boll_combo", "布林帶寬突破+ATR吊燈", "Bollinger"),
        ("rsi_oversold", "RSI 極度超賣抄底 (<32)", "RSI"),
        ("rsi_breakout", "RSI 55 動能突破", "RSI"),
        ("kdj_oversold", "KDJ 超賣低位金叉", "KDJ"),
        ("grand_trinity", "三位一體四階防禦 (Grand Trinity)", "Trinity"),
        ("turtle_sys2", "海龜系統二 (55D/20D)", "Turtle"),
        ("dsa_emotion_cycle", "DSA #12 情緒週期逆向", "DSA"),
        ("dsa_box_osc", "DSA #7 箱體震盪回歸", "DSA"),
    ]

    rows = []
    eq_map = {"BM_SOX30_EW": bm_ew, "BM_SOXX_ETF": bm_soxx}
    for skey, slbl, sfam in roster:
        eq, tr, exp = simulate(by_date, dates, skey)
        eq_map[skey] = eq
        m = stats(eq, tr, exp)
        m.update({"key": skey, "label": slbl, "family": sfam})
        rows.append(m)

    for bk, bl, beq in [("BM_SOX30_EW", "基準：SOX30 等權 B&H", bm_ew), ("BM_SOXX_ETF", "基準：SOXX ETF B&H", bm_soxx)]:
        m = stats(beq, [], 100.0)
        m.update({"key": bk, "label": bl, "family": "基準"})
        rows.append(m)

    res_df = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    print(f"\n=== SOX 30 MULTI-CYCLE VERIFICATION ({dates[0]} ~ {dates[-1]}, {len(dates)} trading days) ===")
    cols = ["label", "cagr_pct", "total_ret_pct", "sharpe", "calmar", "mdd_pct", "ret_2022_pct", "mdd_2022_pct", "exp_pct", "trades", "win_rate", "pf"]
    print(res_df[cols].to_string(index=False))

    # Save SQLite & HTML
    db_out = os.path.join(OUT_DIR, "sox30_verify.db")
    if os.path.exists(db_out): os.remove(db_out)
    conn = sqlite3.connect(db_out)
    res_df.to_sql("summary", conn, index=False, if_exists="replace")
    conn.close()

    # Build Dark HTML Report
    top_k = list(res_df[~res_df["key"].str.startswith("BM_")].head(6)["key"]) + ["BM_SOX30_EW", "BM_SOXX_ETF"]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.66, 0.34],
                        subplot_titles=("SOX 30 七年跨牛熊淨值走勢 % (2020-2026，含 2022 科技大熊市)", "水下回撤深度 % (MDD)"))
    pal = ["#00D084", "#38BDF8", "#FCD34D", "#A78BFA", "#F472B6", "#FB923C", "#94A3B8", "#64748B"]
    for i, k in enumerate(top_k):
        eq = eq_map[k]
        lbl = res_df[res_df["key"] == k].iloc[0]["label"]
        is_bm = k.startswith("BM_")
        fig.add_trace(go.Scatter(x=eq.index, y=(eq / eq.iloc[0] - 1.0) * 100.0, name=lbl,
                                 line=dict(color=pal[i % len(pal)], width=2.0 if is_bm else 2.5, dash="dot" if is_bm else "solid")), row=1, col=1)
        fig.add_trace(go.Scatter(x=eq.index, y=(eq / eq.cummax() - 1.0) * 100.0, showlegend=False,
                                 line=dict(color=pal[i % len(pal)], width=1.4 if is_bm else 1.8, dash="dot" if is_bm else "solid")), row=2, col=1)
    fig.add_vrect(x0="2022-01-01", x1="2022-12-31", fillcolor="rgba(255,77,79,0.10)", line_width=0, annotation_text="2022 Tech Bear", row=1, col=1)
    fig.update_layout(template="plotly_dark", paper_bgcolor="#181C25", plot_bgcolor="#14171F", height=620, hovermode="x unified",
                      legend=dict(orientation="h", yanchor="bottom", y=1.04, x=0, font=dict(size=11)))

    rows_html = "".join(f"""<tr><td><strong>{r['label']}</strong></td><td>{r['cagr_pct']:+.2f}%</td>
        <td class="{'pos' if r['total_ret_pct']>=0 else 'neg'}">{r['total_ret_pct']:+.1f}%</td>
        <td><strong>{r['sharpe']:.2f}</strong></td><td>{r['calmar']:.2f}</td><td class="neg">{r['mdd_pct']:.2f}%</td>
        <td class="{'pos' if r['ret_2022_pct']>=0 else 'neg'}">{r['ret_2022_pct']:+.1f}%</td>
        <td class="neg">{r['mdd_2022_pct']:.1f}%</td><td>{r['exp_pct']:.1f}%</td><td>{int(r['trades'])}</td>
        <td>{r['win_rate']:.1f}%</td><td>{r['pf']:.2f}</td></tr>""" for _, r in res_df.iterrows())

    html = f"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="UTF-8" /><title>SOX 30 七年跨牛熊策略驗證報告 (2020-2026)</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>body{{background:#14171F;color:#E2E8F0;font-family:-apple-system,sans-serif;margin:0;padding:24px;}}
.c{{max-width:1440px;margin:0 auto;}} .card{{background:#181C25;border:1px solid #2A3142;border-radius:10px;padding:20px;margin-bottom:24px;}}
table{{width:100%;border-collapse:collapse;font-size:13px;}} th,td{{padding:9px 10px;border-bottom:1px solid #2A3142;text-align:right;}}
th:first-child,td:first-child{{text-align:left;}} th{{color:#94A3B8;background:#14171F;}}
.pos{{color:#00D084;font-weight:600;}} .neg{{color:#FF4D4F;font-weight:600;}}</style></head>
<body><div class="c"><h1>⚡ SOX 30 半導體七年跨牛熊驗證報告 (2020-04 ~ 2026-11，含 2022 科技大熊市)</h1>
<div class="card"><table><thead><tr><th>策略 / 基準</th><th>年化 CAGR</th><th>7年總報酬</th><th>Sharpe</th><th>Calmar</th><th>7年MDD</th>
<th>2022熊市報酬</th><th>2022熊市MDD</th><th>平均曝險</th><th>交易數</th><th>勝率</th><th>PF</th></tr></thead><tbody>{rows_html}</tbody></table></div>
<div class="card"><div id="f1"></div></div></div>
<script>Plotly.newPlot('f1', {fig.to_json()}.data, {fig.to_json()}.layout, {{responsive:true}});</script></body></html>"""
    with open(os.path.join(OUT_DIR, "sox30_verify_Report.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nSaved SOX30 report -> {OUT_DIR}/sox30_verify_Report.html")


if __name__ == "__main__":
    main()
