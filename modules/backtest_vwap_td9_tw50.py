"""
modules/backtest_vwap_td9_tw50.py
TW50 實證評估與改良測試：VWAP (成交量加權均價) 與 神奇九轉 (TD Sequential)
對比原始基準版與改良強化版，以及兩者融合策略。
輸出至：trades/vwap_td9_20261125_tw50/
"""
from __future__ import annotations

import os
import sqlite3
from typing import Dict, List

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

DB_PATH = "data/tw50/tw50_2026.db"
OUT_DIR = os.path.join("trades", "vwap_td9_20261125_tw50")
os.makedirs(OUT_DIR, exist_ok=True)

TW_COMMISSION = 0.000855
TW_TAX = 0.003
TW_SLIPPAGE = 0.0005
INITIAL_CASH = 1_000_000.0
MAX_SLOTS = 10


def compute_td_setup(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Exact Tom DeMark TD Setup counts: Buy Setup (C[t] < C[t-4]), Sell Setup (C[t] > C[t-4])."""
    vals = close.values
    n = len(vals)
    td_buy = np.zeros(n, dtype=int)
    td_sell = np.zeros(n, dtype=int)
    for i in range(4, n):
        if vals[i] < vals[i - 4]:
            td_buy[i] = td_buy[i - 1] + 1
            td_sell[i] = 0
        elif vals[i] > vals[i - 4]:
            td_sell[i] = td_sell[i - 1] + 1
            td_buy[i] = 0
        else:
            td_buy[i] = 0
            td_sell[i] = 0
    return pd.Series(td_buy, index=close.index), pd.Series(td_sell, index=close.index)


def load_tw50_vwap_td():
    conn = sqlite3.connect(DB_PATH)
    meta = pd.read_sql_query("SELECT ticker, name FROM universe_meta", conn)
    meta_map = dict(zip(meta["ticker"], meta["name"]))
    df = pd.read_sql_query("""
        SELECT s.ticker, s.date, s.raw_open, s.raw_high, s.raw_low, s.raw_close, s.adj_close, s.volume, s.dividends,
               f.sma_20, f.sma_50, f.sma_200, f.rsi_14, f.atr_14,
               c.trust_net_lots, c.inst_total_net_lots
        FROM stock_daily s
        LEFT JOIN daily_factors f ON s.ticker = f.ticker AND s.date = f.date
        LEFT JOIN taiwan_chips_daily c ON s.ticker = c.ticker AND s.date = c.date
        ORDER BY s.ticker, s.date
    """, conn)
    conn.close()

    frames = []
    for t, g in df.groupby("ticker", sort=False):
        g = g.sort_values("date").reset_index(drop=True)
        g["adj_close"] = g["adj_close"].ffill()
        g["raw_close"] = g["raw_close"].ffill()
        ratio = np.where(g["raw_close"] > 0, g["adj_close"] / g["raw_close"], 1.0)
        adj_h = g["raw_high"] * ratio
        adj_l = g["raw_low"] * ratio
        tp = (adj_h + adj_l + g["adj_close"]) / 3.0
        vol = g["volume"].fillna(0.0).clip(lower=1.0)
        pv = tp * vol

        # Rolling VWAPs & YTD Anchored VWAP
        g["vwap_20"] = pv.rolling(20, min_periods=5).sum() / vol.rolling(20, min_periods=5).sum()
        g["vwap_60"] = pv.rolling(60, min_periods=10).sum() / vol.rolling(60, min_periods=10).sum()
        g["avwap_ytd"] = pv.cumsum() / vol.cumsum()
        g["vwap60_std"] = (g["adj_close"] - g["vwap_60"]).rolling(60, min_periods=15).std().fillna(0.0)

        g["prev_c"] = g["adj_close"].shift(1)
        g["prev_vwap20"] = g["vwap_20"].shift(1)
        g["prev_vwap60"] = g["vwap_60"].shift(1)
        g["vol_ma5"] = vol.rolling(5, min_periods=1).mean()
        g["vol_ratio5"] = vol / (g["vol_ma5"] + 1e-8)
        g["sma50_slope"] = g["sma_50"] - g["sma_50"].shift(5)
        g["inst_t1"] = g["inst_total_net_lots"].shift(1).fillna(0.0)
        g["trust_t1"] = g["trust_net_lots"].shift(1).fillna(0.0)
        g["low_5"] = g["adj_close"].rolling(5, min_periods=1).min()

        # TD Sequential
        td_b, td_s = compute_td_setup(g["adj_close"])
        g["td_buy"] = td_b
        g["td_sell"] = td_s
        g["td_buy_max3"] = td_b.rolling(3, min_periods=1).max()
        g["td_buy_max5"] = td_b.rolling(5, min_periods=1).max()
        frames.append(g)

    full = pd.concat(frames, ignore_index=True)
    return full, meta_map


def eval_entry(row: pd.Series, skey: str) -> bool:
    c = row["adj_close"]
    if pd.isna(c) or pd.isna(row["vwap_20"]) or pd.isna(row["vwap_60"]):
        return False
    bull_bar = row["raw_close"] > row["raw_open"]
    rebound = bull_bar and (c > row["prev_c"])

    if skey == "vwap_01_baseline":
        return bool(row["prev_c"] <= row["prev_vwap20"] and c > row["vwap_20"])

    elif skey == "vwap_02_pullback_trend":
        # Institutional pullback to 20D VWAP within 60D VWAP uptrend
        trend = (c >= row["vwap_60"]) and (row["vwap_20"] >= row["vwap_60"])
        near_v20 = -0.015 <= (c / row["vwap_20"] - 1.0) <= 0.025
        return bool(trend and near_v20 and bull_bar)

    elif skey == "vwap_03_avwap_breakout":
        # Reclaim/breakout above 60D VWAP + volume confirm + not extended > 1.5 std
        cross60 = (row["prev_c"] <= row["prev_vwap60"] and c > row["vwap_60"])
        not_ext = c < (row["vwap_60"] + 1.5 * row["vwap60_std"] + 1e-6)
        return bool(cross60 and row["vol_ratio5"] > 1.15 and not_ext and c >= row["avwap_ytd"])

    elif skey == "vwap_04_inst_combo":
        # VWAP bullish structure + T+1 institutional buying + no chase
        struct = (c >= row["vwap_20"]) and (row["vwap_20"] >= row["vwap_60"]) and ((c / row["vwap_20"] - 1.0) < 0.04)
        inst_ok = (row["inst_t1"] > 0) or (row["trust_t1"] > 0)
        return bool(struct and inst_ok)

    elif skey == "td_01_baseline":
        return bool(row["td_buy"] == 9)

    elif skey == "td_02_confirm_rebound":
        # Wait for right-side bounce confirmation after TD Buy 8/9
        return bool(row["td_buy_max3"] >= 8 and rebound)

    elif skey == "td_03_trend_dip":
        # Buy TD 7+ exhaustion pullback inside structural uptrend
        uptrend = (pd.notnull(row["sma_200"]) and c >= row["sma_200"]) or (pd.notnull(row["sma50_slope"]) and row["sma50_slope"] > 0)
        return bool(uptrend and row["td_buy_max3"] >= 7 and rebound)

    elif skey == "td_04_vwap_fusion":
        # Fusion: TD exhaustion dip near institutional VWAP cost OR reclaim VWAP20 after TD7+ washout
        dip_near_vwap = (c >= row["vwap_60"] * 0.98) and (row["td_buy_max3"] >= 6) and rebound
        reclaim_after_td = (row["td_buy_max5"] >= 7) and (c > row["vwap_20"]) and bull_bar
        return bool(dip_near_vwap or reclaim_after_td)

    return False


def eval_exit(row: pd.Series, st: dict, skey: str) -> str:
    c = row["adj_close"]
    ret = (c / st["adj_entry"] - 1.0) * 100.0

    if skey == "vwap_01_baseline":
        return "EXIT" if c < row["vwap_20"] else "HOLD"

    elif skey in ("vwap_02_pullback_trend", "vwap_03_avwap_breakout"):
        return "EXIT" if c < row["vwap_60"] else "HOLD"

    elif skey == "vwap_04_inst_combo":
        if c < row["vwap_60"]:
            return "EXIT"
        if c < row["vwap_20"] and row["inst_t1"] < -3000:
            return "EXIT"
        return "HOLD"

    elif skey == "td_01_baseline":
        return "EXIT" if (row["td_sell"] >= 9 or ret <= -8.0) else "HOLD"

    elif skey == "td_02_confirm_rebound":
        return "EXIT" if (row["td_sell"] >= 9 or row["rsi_14"] > 78.0 or c < st["stop_low"] * 0.97) else "HOLD"

    elif skey == "td_03_trend_dip":
        if (not st["trimmed"]) and row["td_sell"] >= 9 and ret > 8.0:
            return "TRIM_HALF"
        return "EXIT" if (c < row["sma_50"] or ret <= -7.0) else "HOLD"

    elif skey == "td_04_vwap_fusion":
        # High-9 climax -> trim 50% lock profit; rest rides 60D VWAP institutional cost line!
        if (not st["trimmed"]) and row["td_sell"] >= 9 and ret > 8.0:
            return "TRIM_HALF"
        return "EXIT" if (c < row["vwap_60"] or ret <= -8.0) else "HOLD"

    return "HOLD"


def simulate(daily_by_date: Dict[str, pd.DataFrame], all_dates: List[str], skey: str, meta_map: Dict[str, str]):
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
            act = eval_exit(row, st, skey)
            if act == "EXIT":
                px = float(row["raw_close"]) * (1.0 - TW_SLIPPAGE)
                gross = shares[t] * px
                cost = gross * (TW_COMMISSION + TW_TAX)
                cash += gross - cost
                ret_pct = (adj / st["adj_entry"] - 1.0) * 100.0 - (TW_COMMISSION * 2 + TW_TAX + TW_SLIPPAGE * 2) * 100.0
                pnl = (px - st["raw_entry"]) * shares[t] - cost - st["buy_cost"]
                trades.append({"strategy": skey, "ticker": t, "name": meta_map.get(t, t), "entry_date": st["entry_date"], "exit_date": dt,
                               "net_pnl": round(pnl, 2), "return_pct": round(ret_pct, 2), "hold_days": (pd.Timestamp(dt) - pd.Timestamp(st["entry_date"])).days})
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
                trades.append({"strategy": skey, "ticker": t, "name": meta_map.get(t, t), "entry_date": st["entry_date"], "exit_date": dt,
                               "net_pnl": round(pnl, 2), "return_pct": round(ret_pct, 2), "hold_days": (pd.Timestamp(dt) - pd.Timestamp(st["entry_date"])).days})

        open_slots = MAX_SLOTS - len(shares)
        if open_slots > 0 and cash > 10_000.0:
            cands = []
            for t, row in d_slice.iterrows():
                if t in shares: continue
                if eval_entry(row, skey):
                    prio = float(row["vol_ratio5"]) if pd.notnull(row["vol_ratio5"]) else 1.0
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
                        state[t] = {"entry_date": dt, "raw_entry": px, "adj_entry": float(row["adj_close"]),
                                    "buy_cost": bcost, "trimmed": False, "stop_low": float(row["low_5"])}

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
            trades.append({"strategy": skey, "ticker": t, "name": meta_map.get(t, t), "entry_date": st["entry_date"], "exit_date": last_dt,
                           "net_pnl": round(pnl, 2), "return_pct": round(ret_pct, 2), "hold_days": (pd.Timestamp(last_dt) - pd.Timestamp(st["entry_date"])).days})

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
    wr = (len(wins) / n_tr * 100.0) if n_tr else 0.0
    gw = sum(t["net_pnl"] for t in trades if t["net_pnl"] > 0)
    gl = abs(sum(t["net_pnl"] for t in trades if t["net_pnl"] < 0))
    pf = min(gw / gl, 99.0) if gl > 1e-6 else (99.0 if gw > 0 else 0.0)
    chop = sum(t["net_pnl"] for t in trades if t["hold_days"] <= 10)
    return {
        "total_return_pct": round(tot, 2), "alpha_pct": round(tot - bm_ret, 2),
        "sharpe": round(sharpe, 2), "sortino": round(sortino, 2), "calmar": round(calmar, 2),
        "mdd_pct": round(mdd, 2), "avg_exposure_pct": round(avg_exp, 1),
        "trades": n_tr, "win_rate_pct": round(wr, 1), "profit_factor": round(pf, 2), "chop_tax_ntd": round(chop, 0),
    }


def main():
    full, meta_map = load_tw50_vwap_td()
    daily_by_date = {dt: g.set_index("ticker") for dt, g in full.groupby("date")}
    all_dates = sorted(daily_by_date.keys())
    adj_piv = full.pivot(index="date", columns="ticker", values="adj_close").sort_index().ffill()
    bm_tw50 = adj_piv.div(adj_piv.iloc[0]).mean(axis=1) * INITIAL_CASH
    bm_tw50.index = pd.to_datetime(bm_tw50.index)

    roster = [
        ("vwap_01_baseline", "VWAP 基準：20D VWAP 突破/跌破", "VWAP"),
        ("vwap_02_pullback_trend", "VWAP 改良1：多頭回踩 20D VWAP 低吸 (守60D)", "VWAP"),
        ("vwap_03_avwap_breakout", "VWAP 改良2：站上 60D+年初AVWAP 放量突破", "VWAP"),
        ("vwap_04_inst_combo", "VWAP 改良3：VWAP 成本多頭 + T+1 法人共振", "VWAP"),
        ("td_01_baseline", "神奇九轉 基準：純低九買 / 高九賣", "TD9"),
        ("td_02_confirm_rebound", "神奇九轉 改良1：低8/9右側收紅確認反彈", "TD9"),
        ("td_03_trend_dip", "神奇九轉 改良2：多頭趨勢中 TD7+ 回調買 + 高九減半", "TD9"),
        ("td_04_vwap_fusion", "終極融合：VWAP 機構成本 × 神奇九轉擇時 + 高九減半", "VWAP+TD9"),
    ]

    rows, all_trades = [], []
    eq_map = {"BM_TW50_EW": bm_tw50}
    for skey, slbl, sfam in roster:
        eq, tr, exp = simulate(daily_by_date, all_dates, skey, meta_map)
        eq_map[skey] = eq
        all_trades.extend(tr)
        met = calc_stats(eq, bm_tw50, tr, exp)
        met.update({"strategy_key": skey, "label": slbl, "family": sfam})
        rows.append(met)

    bm_met = calc_stats(bm_tw50, bm_tw50, [], 100.0)
    bm_met.update({"strategy_key": "BM_TW50_EW", "label": "基準：台灣50 等權 B&H (TW50 EW)", "family": "基準"})
    rows.append(bm_met)

    res_df = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    print("\n=== VWAP & TD SEQUENTIAL EVALUATION + REFINEMENTS ON TW50 ===")
    print(res_df[["label", "family", "total_return_pct", "sharpe", "sortino", "calmar", "mdd_pct", "avg_exposure_pct", "trades", "win_rate_pct", "profit_factor", "chop_tax_ntd"]].to_string(index=False))

    # Save SQLite & HTML
    db_out = os.path.join(OUT_DIR, "backtest_result.db")
    if os.path.exists(db_out): os.remove(db_out)
    conn = sqlite3.connect(db_out)
    res_df.to_sql("backtest_summary", conn, index=False, if_exists="replace")
    pd.DataFrame(all_trades).to_sql("backtest_trades", conn, index=False, if_exists="replace")
    conn.close()

    # Build Dark HTML Report
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.66, 0.34],
                        subplot_titles=("VWAP & 神奇九轉 (基準 vs 改良) 累計報酬率 %", "水下回撤深度 % (MDD)"))
    pal = ["#00D084", "#38BDF8", "#FCD34D", "#A78BFA", "#F472B6", "#FB923C", "#2DD4BF", "#E879F9", "#94A3B8"]
    for i, (_, r) in enumerate(res_df.iterrows()):
        k = r["strategy_key"]
        eq = eq_map[k]
        is_bm = k == "BM_TW50_EW"
        fig.add_trace(go.Scatter(x=eq.index, y=(eq / eq.iloc[0] - 1.0) * 100.0, name=r["label"],
                                 line=dict(color=pal[i % len(pal)], width=2.0 if is_bm else 2.5, dash="dot" if is_bm else "solid")), row=1, col=1)
        fig.add_trace(go.Scatter(x=eq.index, y=(eq / eq.cummax() - 1.0) * 100.0, showlegend=False,
                                 line=dict(color=pal[i % len(pal)], width=1.4 if is_bm else 1.8, dash="dot" if is_bm else "solid")), row=2, col=1)
    fig.update_layout(template="plotly_dark", paper_bgcolor="#181C25", plot_bgcolor="#14171F", height=600, hovermode="x unified",
                      legend=dict(orientation="h", yanchor="bottom", y=1.04, x=0, font=dict(size=11)))

    rows_html = "".join(f"""<tr><td><strong>{r['label']}</strong></td><td>{r['family']}</td>
        <td class="{'pos' if r['total_return_pct']>=0 else 'neg'}">{r['total_return_pct']:+.2f}%</td>
        <td><strong>{r['sharpe']:.2f}</strong></td><td>{r['calmar']:.2f}</td><td class="neg">{r['mdd_pct']:.2f}%</td>
        <td>{r['avg_exposure_pct']:.1f}%</td><td>{int(r['trades'])}</td><td>{r['win_rate_pct']:.1f}%</td>
        <td>{r['profit_factor']:.2f}</td><td class="{'pos' if r['chop_tax_ntd']>=0 else 'neg'}">{r['chop_tax_ntd']:+,.0f}</td></tr>"""
        for _, r in res_df.iterrows())

    html = f"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="UTF-8" /><title>TW50 VWAP & 神奇九轉策略評估與改良</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>body{{background:#14171F;color:#E2E8F0;font-family:-apple-system,sans-serif;margin:0;padding:24px;}}
.c{{max-width:1440px;margin:0 auto;}} .card{{background:#181C25;border:1px solid #2A3142;border-radius:10px;padding:20px;margin-bottom:24px;}}
table{{width:100%;border-collapse:collapse;font-size:13px;}} th,td{{padding:9px 11px;border-bottom:1px solid #2A3142;text-align:right;}}
th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){{text-align:left;}} th{{color:#94A3B8;background:#14171F;}}
.pos{{color:#00D084;font-weight:600;}} .neg{{color:#FF4D4F;font-weight:600;}}</style></head>
<body><div class="c"><h1>📊 TW50 新指標實證：VWAP × 神奇九轉 (TD Sequential) 基準與改良對比</h1>
<div class="card"><table><thead><tr><th>策略變體</th><th>家族</th><th>累計報酬</th><th>Sharpe</th><th>Calmar</th><th>MDD</th>
<th>平均曝險</th><th>交易數</th><th>勝率</th><th>PF</th><th>短線摩擦稅 (<=10d)</th></tr></thead><tbody>{rows_html}</tbody></table></div>
<div class="card"><div id="f1"></div></div></div>
<script>Plotly.newPlot('f1', {fig.to_json()}.data, {fig.to_json()}.layout, {{responsive:true}});</script></body></html>"""
    with open(os.path.join(OUT_DIR, "tw50_vwap_td9_Report.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved report -> {OUT_DIR}/tw50_vwap_td9_Report.html")


if __name__ == "__main__":
    main()
