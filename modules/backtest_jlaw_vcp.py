"""
modules/backtest_jlaw_vcp.py
J-Law (Law Wai-Sum) SEPA / VCP / META 策略量化實作與雙市場實證測試：
  1. 美股 7 年跨牛熊戰場：SOX 30 + MAG 7 (37 檔，2020-07 ~ 2026-11，含 2022 科技大熊市)
  2. 台股權值戰場：TW50 (50 檔，2026-01 ~ 2026-11)
輸出至：trades/jlaw_vcp_20261125/
"""
from __future__ import annotations

import os
import sqlite3
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

OUT_DIR = os.path.join("trades", "jlaw_vcp_20261125")
os.makedirs(OUT_DIR, exist_ok=True)


def enrich_jlaw_features(df: pd.DataFrame, bm_close: pd.Series, is_tw: bool = False) -> pd.DataFrame:
    """Compute Stage 2 Trend Template, RS Rating (0-99), VCP Multi-Stage Contraction, and Pivot signals."""
    frames = []
    for sym, g in df.groupby("symbol", sort=False):
        g = g.sort_values("date").reset_index(drop=True)
        c = g["close"].ffill()
        o = g["open"].ffill()
        h = g["high"].ffill()
        l = g["low"].ffill()
        v = g["volume"].fillna(1.0).clip(lower=1.0)
        g["close"] = c

        # J-Law / Minervini Moving Averages (incl. 63D quarterly MA)
        g["sma_20"] = c.rolling(20, min_periods=10).mean()
        g["sma_50"] = c.rolling(50, min_periods=20).mean()
        g["sma_63"] = c.rolling(63, min_periods=25).mean()
        g["sma_150"] = c.rolling(150, min_periods=50).mean()
        g["sma_200"] = c.rolling(200, min_periods=60).mean()
        g["sma200_slope20"] = g["sma_200"] - g["sma_200"].shift(20)
        g["sma50_slope10"] = g["sma_50"] - g["sma_50"].shift(10)

        # 52-week (252D) High / Low proximity
        g["high_252"] = h.rolling(252, min_periods=60).max()
        g["low_252"] = l.rolling(252, min_periods=60).min()

        # VCP Multi-Window Volatility Contraction (T1: 30d -> T2: 15d -> T3: 7d)
        r30 = (h.shift(1).rolling(30, min_periods=15).max() - l.shift(1).rolling(30, min_periods=15).min()) / (l.shift(1).rolling(30, min_periods=15).min() + 1e-8)
        r15 = (h.shift(1).rolling(15, min_periods=8).max() - l.shift(1).rolling(15, min_periods=8).min()) / (l.shift(1).rolling(15, min_periods=8).min() + 1e-8)
        r7 = (h.shift(1).rolling(7, min_periods=4).max() - l.shift(1).rolling(7, min_periods=4).min()) / (l.shift(1).rolling(7, min_periods=4).min() + 1e-8)
        g["vcp_r30"] = r30
        g["vcp_r15"] = r15
        g["vcp_r7"] = r7
        g["pivot_high10"] = h.shift(1).rolling(10, min_periods=5).max()
        g["pivot_low7"] = l.shift(1).rolling(7, min_periods=4).min()

        # Volume Dry-up & Breakout Surge
        g["vol_ma50"] = v.rolling(50, min_periods=15).mean()
        g["vol_ma5_prev"] = v.shift(1).rolling(5, min_periods=3).mean()
        g["vol_dry"] = g["vol_ma5_prev"] / (g["vol_ma50"] + 1e-8)
        g["vol_surge"] = v / (g["vol_ma50"] + 1e-8)

        # Weighted Momentum for IBD/J-Law RS Rating (40% 3M + 30% 6M + 30% 12M)
        ret63 = c.pct_change(63).fillna(0.0)
        ret126 = c.pct_change(126).fillna(ret63)
        ret252 = c.pct_change(252).fillna(ret126)
        g["rs_raw"] = 0.40 * ret63 + 0.30 * ret126 + 0.30 * ret252
        g["prev_c"] = c.shift(1)
        g["bull_bar"] = c > o

        # Stage 2 Trend Template
        if not is_tw:
            g["stage2"] = (
                (c > g["sma_50"]) & (c > g["sma_150"]) & (c > g["sma_200"])
                & (g["sma_50"] > g["sma_150"]) & (g["sma_150"] > g["sma_200"])
                & (g["sma200_slope20"] > 0)
                & (c >= 0.75 * g["high_252"]) & (c >= 1.25 * g["low_252"])
            )
        else:
            # TW50 2026 DB has 209 bars (pre-warmed sma_50/200 in daily_factors, here use available rolling + slope)
            g["stage2"] = (
                (c > g["sma_50"]) & (g["sma_20"] >= g["sma_50"]) & (g["sma50_slope10"] > 0)
                & (c >= 0.80 * g["high_252"])
            )

        # VCP Contraction + Breakout Pivot
        tight_cap = 0.14 if not is_tw else 0.11
        g["vcp_contract"] = (r7 < r15 * 0.90) & (r15 < r30 * 0.95) & (r7 <= tight_cap) & (g["vol_dry"] < 0.98)
        g["vcp_pivot"] = g["vcp_contract"] & (c > g["pivot_high10"]) & (g["vol_surge"] >= 1.25) & g["bull_bar"]

        # META Pullback in Strong Stage 2
        near_ma20 = (c >= g["sma_20"] * 0.985) & (c <= g["sma_20"] * 1.03)
        g["meta_pullback"] = g["stage2"] & near_ma20 & (g["vol_dry"] < 0.90) & g["bull_bar"] & (c > g["prev_c"])
        frames.append(g)

    full = pd.concat(frames, ignore_index=True)
    # Cross-sectional RS Percentile Rank (0-100) per date
    full["rs_rank"] = full.groupby("date")["rs_raw"].rank(pct=True) * 100.0

    # Market Regime Filter (Benchmark >= Benchmark SMA50)
    bm_df = pd.DataFrame({"date": bm_close.index, "bm_c": bm_close.values}).sort_values("date")
    bm_df["bm_sma50"] = bm_df["bm_c"].rolling(50, min_periods=20).mean()
    bm_df["mkt_bull"] = bm_df["bm_c"] >= bm_df["bm_sma50"]
    full = full.merge(bm_df[["date", "mkt_bull"]], on="date", how="left")
    full["mkt_bull"] = full["mkt_bull"].fillna(True)
    return full


def simulate_jlaw(
    by_date: Dict[str, pd.DataFrame],
    dates: List[str],
    variant: str,
    init_cash: float,
    comm: float,
    tax: float,
    slip: float,
):
    max_slots = 6 if variant in ("jlaw_03_meta_sniper", "jlaw_04_meta_pullback") else 10
    cash = init_cash
    shares: Dict[str, float] = {}
    state: Dict[str, dict] = {}
    eq_curve, exposures, trades = [], [], []

    for dt in dates:
        ds = by_date[dt]
        # Dividends if available
        if "dividends" in ds.columns:
            for t, sh in shares.items():
                if sh > 0 and t in ds.index:
                    dv = float(ds.at[t, "dividends"])
                    if pd.notnull(dv) and dv > 0:
                        cash += sh * dv

        # Exits & Profit Locking
        for t in list(shares.keys()):
            if shares[t] <= 0 or t not in ds.index:
                continue
            row = ds.loc[t]
            st = state[t]
            c = float(row["close"])
            if c > st["peak"]:
                st["peak"] = c
            gain_pct = (c / st["entry"] - 1.0) * 100.0
            mfe_pct = (st["peak"] / st["entry"] - 1.0) * 100.0

            # Breakeven lock once MFE >= +10%
            stop_px = st["stop_px"]
            if mfe_pct >= 10.0:
                stop_px = max(stop_px, st["entry"] * 1.005)

            # Partial profit lock (+20% -> lock 30%) for META Sniper
            if variant in ("jlaw_03_meta_sniper", "jlaw_04_meta_pullback") and (not st["trimmed"]) and gain_pct >= 20.0:
                sh_s = shares[t] * 0.30
                px = c * (1.0 - slip)
                gross = sh_s * px
                cost = gross * (comm + tax)
                cash += gross - cost
                shares[t] -= sh_s
                st["trimmed"] = True
                ret_p = (px / st["entry"] - 1.0) * 100.0 - (comm * 2 + tax) * 100.0
                pnl = (px - st["entry"]) * sh_s - cost - st["bcost"] * 0.30
                st["bcost"] *= 0.70
                trades.append({"ticker": t, "net_pnl": pnl, "return_pct": ret_p, "hold_days": (pd.Timestamp(dt) - pd.Timestamp(st["dt"])).days})

            # Exit condition
            trail_line = float(row["sma_20"]) if variant == "jlaw_01_vcp_raw" else float(row["sma_63"] if pd.notnull(row["sma_63"]) else row["sma_50"])
            hard_hit = c <= stop_px
            trail_hit = (c < trail_line) and (mfe_pct >= 5.0 or (pd.Timestamp(dt) - pd.Timestamp(st["dt"])).days >= 10)
            if hard_hit or trail_hit:
                px = c * (1.0 - slip)
                gross = shares[t] * px
                cost = gross * (comm + tax)
                cash += gross - cost
                ret_p = (px / st["entry"] - 1.0) * 100.0 - (comm * 2 + tax) * 100.0
                pnl = (px - st["entry"]) * shares[t] - cost - st["bcost"]
                trades.append({"ticker": t, "net_pnl": pnl, "return_pct": ret_p, "hold_days": (pd.Timestamp(dt) - pd.Timestamp(st["dt"])).days})
                shares.pop(t, None)
                state.pop(t, None)

        # Entries
        open_slots = max_slots - len(shares)
        if open_slots > 0 and cash > init_cash * 0.02:
            cands = []
            for t, row in ds.iterrows():
                if t in shares:
                    continue
                ok = False
                if variant == "jlaw_01_vcp_raw":
                    ok = bool(row["stage2"] and row["vcp_pivot"])
                elif variant == "jlaw_02_vcp_rs_sma63":
                    ok = bool(row["stage2"] and row["vcp_pivot"] and row["rs_rank"] >= 70.0)
                elif variant == "jlaw_03_meta_sniper":
                    ok = bool(row["mkt_bull"] and row["stage2"] and row["vcp_pivot"] and row["rs_rank"] >= 75.0)
                elif variant == "jlaw_04_meta_pullback":
                    ok = bool(row["mkt_bull"] and row["rs_rank"] >= 75.0 and (row["vcp_pivot"] or row["meta_pullback"]))
                if ok:
                    cands.append((float(row["rs_rank"]), t, row))
            cands.sort(key=lambda x: x[0], reverse=True)
            chosen = cands[:open_slots]
            if chosen:
                pv = cash + sum(sh * float(ds.at[t, "close"]) for t, sh in shares.items() if t in ds.index and sh > 0)
                slot_cash = pv / max_slots
                for _, t, row in chosen:
                    alloc = min(slot_cash, cash * 0.995)
                    if alloc < init_cash * 0.02:
                        break
                    px = float(row["close"]) * (1.0 + slip)
                    bsh = alloc / (px * (1.0 + comm))
                    bcost = bsh * px * comm
                    if bsh * px + bcost <= cash + 1e-6:
                        cash -= bsh * px + bcost
                        shares[t] = bsh
                        # Tight J-Law Stop: max(-7%, VCP base low - 1%)
                        vcp_low = float(row["pivot_low7"]) * 0.99 if pd.notnull(row["pivot_low7"]) else px * 0.93
                        stop_px = max(px * 0.93, min(vcp_low, px * 0.96))
                        state[t] = {"dt": dt, "entry": px, "peak": px, "stop_px": stop_px, "bcost": bcost, "trimmed": False}

        inv = sum(sh * float(ds.at[t, "close"]) for t, sh in shares.items() if t in ds.index and sh > 0)
        eq = cash + inv
        eq_curve.append((dt, eq))
        exposures.append(inv / eq * 100.0 if eq > 0 else 0.0)

    eq_s = pd.Series(dict(eq_curve))
    eq_s.index = pd.to_datetime(eq_s.index)
    return eq_s, trades, float(np.mean(exposures))


def calc_stats(eq: pd.Series, trades: List[dict], avg_exp: float, rf: float = 0.03) -> dict:
    rets = eq.pct_change().dropna()
    tot = (eq.iloc[-1] / eq.iloc[0] - 1.0) * 100.0
    n_yrs = max(len(rets) / 252.0, 0.1)
    cagr = ((eq.iloc[-1] / eq.iloc[0]) ** (1.0 / n_yrs) - 1.0) * 100.0
    vol = float(rets.std() * np.sqrt(252) * 100.0)
    excess = rets - rf / 252.0
    sharpe = float((excess.mean() / (rets.std() + 1e-12)) * np.sqrt(252)) if vol > 1e-6 else 0.0
    mdd = float(((eq / eq.cummax()) - 1.0).min() * 100.0)
    calmar = float(cagr / abs(mdd)) if mdd < -1e-6 else 0.0

    eq22 = eq.loc["2022-01-01":"2022-12-31"]
    ret22 = (eq22.iloc[-1] / eq22.iloc[0] - 1.0) * 100.0 if len(eq22) > 20 else np.nan
    mdd22 = float(((eq22 / eq22.cummax()) - 1.0).min() * 100.0) if len(eq22) > 20 else np.nan

    n_tr = len(trades)
    wins = [t["return_pct"] for t in trades if t["return_pct"] > 0]
    losses = [t["return_pct"] for t in trades if t["return_pct"] <= 0]
    wr = (len(wins) / n_tr * 100.0) if n_tr else 0.0
    payoff = (float(np.mean(wins)) / abs(float(np.mean(losses)))) if (wins and losses) else 0.0
    gw = sum(t["net_pnl"] for t in trades if t["net_pnl"] > 0)
    gl = abs(sum(t["net_pnl"] for t in trades if t["net_pnl"] < 0))
    pf = min(gw / gl, 99.0) if gl > 1e-6 else 0.0
    return {
        "total_ret_pct": round(tot, 1), "cagr_pct": round(cagr, 2), "sharpe": round(sharpe, 2),
        "calmar": round(calmar, 2), "mdd_pct": round(mdd, 2),
        "ret_2022_pct": round(ret22, 1) if pd.notnull(ret22) else None,
        "mdd_2022_pct": round(mdd22, 1) if pd.notnull(mdd22) else None,
        "exp_pct": round(avg_exp, 1), "trades": n_tr, "win_rate": round(wr, 1),
        "payoff": round(payoff, 2), "pf": round(pf, 2),
    }


def run_us_sox_mag7():
    conn = sqlite3.connect("data/sox_mag7_price_vol_types/price_vol_analysis.db")
    syms = pd.read_sql_query("SELECT symbol FROM stock_archetypes WHERE is_sox=1 OR is_mag7=1", conn)["symbol"].tolist()
    df = pd.read_sql_query(
        f"SELECT date, symbol, open, high, low, close, volume FROM bar_price_vol WHERE symbol IN ({','.join(['?']*len(syms))}) ORDER BY symbol, date",
        conn, params=syms
    )
    qqq = pd.read_sql_query("SELECT date, close FROM bar_price_vol WHERE symbol='QQQ' ORDER BY date", conn).set_index("date")["close"]
    soxx = pd.read_sql_query("SELECT date, close FROM bar_price_vol WHERE symbol='SOXX' ORDER BY date", conn).set_index("date")["close"]
    conn.close()

    full = enrich_jlaw_features(df, qqq, is_tw=False)
    full = full[full["date"] >= "2020-10-01"].reset_index(drop=True)  # full 200d warmup!
    by_date = {dt: g.set_index("symbol") for dt, g in full.groupby("date")}
    dates = sorted(by_date.keys())

    qqq_al = qqq.reindex(dates).ffill()
    bm_qqq = (qqq_al / qqq_al.iloc[0]) * 100_000.0
    bm_qqq.index = pd.to_datetime(bm_qqq.index)
    soxx_al = soxx.reindex(dates).ffill()
    bm_soxx = (soxx_al / soxx_al.iloc[0]) * 100_000.0
    bm_soxx.index = pd.to_datetime(bm_soxx.index)

    variants = [
        ("jlaw_01_vcp_raw", "J-Law 1：純 Stage2 + VCP 突破 (守20MA)"),
        ("jlaw_02_vcp_rs_sma63", "J-Law 2：Stage2 + RS≥70 + VCP (守63季線)"),
        ("jlaw_03_meta_sniper", "J-Law 3：META 旗艦精兵 (大盤濾網+RS≥75+6檔+鎖利)"),
        ("jlaw_04_meta_pullback", "J-Law 4：META 強勢股 VCP + 20MA縮量回踩"),
    ]
    rows, eq_map = [], {"BM_QQQ": bm_qqq, "BM_SOXX": bm_soxx}
    for vk, vl in variants:
        eq, tr, exp = simulate_jlaw(by_date, dates, vk, 100_000.0, 0.0003, 0.0, 0.0005)
        eq_map[vk] = eq
        m = calc_stats(eq, tr, exp, rf=0.03)
        m.update({"key": vk, "label": vl})
        rows.append(m)

    for bk, bl, beq in [("BM_SOXX", "基準：SOXX ETF B&H", bm_soxx), ("BM_QQQ", "基準：QQQ ETF B&H", bm_qqq)]:
        m = calc_stats(beq, [], 100.0, rf=0.03)
        m.update({"key": bk, "label": bl})
        rows.append(m)

    res_us = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    print(f"\n=== J-LAW VCP / META ON US TECH (SOX30+MAG7, {dates[0]} ~ {dates[-1]}) ===")
    print(res_us[["label", "cagr_pct", "total_ret_pct", "sharpe", "calmar", "mdd_pct", "ret_2022_pct", "mdd_2022_pct", "exp_pct", "trades", "win_rate", "payoff", "pf"]].to_string(index=False))
    return res_us, eq_map


def run_tw50():
    conn = sqlite3.connect("data/tw50/tw50_2026.db")
    df = pd.read_sql_query("""
        SELECT date, ticker AS symbol, raw_open AS open, raw_high AS high, raw_low AS low,
               adj_close AS close, volume, dividends
        FROM stock_daily ORDER BY ticker, date
    """, conn)
    conn.close()
    piv = df.pivot(index="date", columns="symbol", values="close").sort_index().ffill()
    bm_ew = (piv.div(piv.iloc[0]).mean(axis=1)) * 1_000_000.0

    full = enrich_jlaw_features(df, bm_ew, is_tw=True)
    full = full[full["date"] >= "2026-03-01"].reset_index(drop=True)  # allow 40d warmup inside 2026
    by_date = {dt: g.set_index("symbol") for dt, g in full.groupby("date")}
    dates = sorted(by_date.keys())

    bm_sub = bm_ew.reindex(dates).ffill()
    bm_sub = (bm_sub / bm_sub.iloc[0]) * 1_000_000.0
    bm_sub.index = pd.to_datetime(bm_sub.index)

    variants = [
        ("jlaw_01_vcp_raw", "J-Law 1：純 Stage2 + VCP 突破 (守20MA)"),
        ("jlaw_02_vcp_rs_sma63", "J-Law 2：Stage2 + RS≥70 + VCP (守63季線)"),
        ("jlaw_03_meta_sniper", "J-Law 3：META 旗艦精兵 (大盤濾網+RS≥75+6檔+鎖利)"),
        ("jlaw_04_meta_pullback", "J-Law 4：META 強勢股 VCP + 20MA縮量回踩"),
    ]
    rows = []
    for vk, vl in variants:
        eq, tr, exp = simulate_jlaw(by_date, dates, vk, 1_000_000.0, 0.000855, 0.003, 0.0005)
        m = calc_stats(eq, tr, exp, rf=0.015)
        m.update({"key": vk, "label": vl})
        rows.append(m)

    m_bm = calc_stats(bm_sub, [], 100.0, rf=0.015)
    m_bm.update({"key": "BM_TW50", "label": "基準：TW50 等權 B&H (同期)"})
    rows.append(m_bm)
    res_tw = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    print(f"\n=== J-LAW VCP / META ON TW50 ({dates[0]} ~ {dates[-1]}) ===")
    print(res_tw[["label", "total_ret_pct", "sharpe", "calmar", "mdd_pct", "exp_pct", "trades", "win_rate", "payoff", "pf"]].to_string(index=False))
    return res_tw


def main():
    res_us, eq_us = run_us_sox_mag7()
    res_tw = run_tw50()

    # Build HTML Report for US Tech 7-Year J-Law Test
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.66, 0.34],
                        subplot_titles=("J-Law VCP / META 美股科技股 (SOX30+MAG7, 2020-2026) 累計報酬 %", "水下回撤深度 % (MDD)"))
    pal = ["#00D084", "#38BDF8", "#FCD34D", "#A78BFA", "#94A3B8", "#64748B"]
    for i, (_, r) in enumerate(res_us.iterrows()):
        k = r["key"]
        eq = eq_us[k]
        is_bm = k.startswith("BM_")
        fig.add_trace(go.Scatter(x=eq.index, y=(eq / eq.iloc[0] - 1.0) * 100.0, name=r["label"],
                                 line=dict(color=pal[i % len(pal)], width=2.0 if is_bm else 2.6, dash="dot" if is_bm else "solid")), row=1, col=1)
        fig.add_trace(go.Scatter(x=eq.index, y=(eq / eq.cummax() - 1.0) * 100.0, showlegend=False,
                                 line=dict(color=pal[i % len(pal)], width=1.4 if is_bm else 1.8, dash="dot" if is_bm else "solid")), row=2, col=1)
    fig.add_vrect(x0="2022-01-01", x1="2022-12-31", fillcolor="rgba(255,77,79,0.10)", line_width=0, annotation_text="2022 Tech Bear", row=1, col=1)
    fig.update_layout(template="plotly_dark", paper_bgcolor="#181C25", plot_bgcolor="#14171F", height=600, hovermode="x unified",
                      legend=dict(orientation="h", yanchor="bottom", y=1.04, x=0, font=dict(size=11)))

    html_path = os.path.join(OUT_DIR, "jlaw_vcp_Report.html")
    fig.write_html(html_path, include_plotlyjs="cdn")
    print(f"\nSaved J-Law Plotly report -> {html_path}")


if __name__ == "__main__":
    main()
