"""
modules/attribution_decay.py
TW50 因子失效診斷與績效歸因分析引擎 (Brinson BHB/BF + Factor Ablation + Alpha/Beta + IC Decay + MAE/MFE Whipsaw)
遵循 prompts/factors.md 與 prompts/strategy/quantitative_performance_workflow.md 規範。
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
OUT_DIR = os.path.join("trades", "attribution_20261124_tw50")
os.makedirs(OUT_DIR, exist_ok=True)

TW_COMMISSION = 0.000855
TW_TAX = 0.003
TW_SLIPPAGE = 0.0005
INITIAL_CASH = 1_000_000.0
RF_ANNUAL = 0.015

# Exact TW50 50-stock Sector Classification
TW50_SECTORS: Dict[str, str] = {
    # 半導體 (6)
    "2330.TW": "半導體", "2454.TW": "半導體", "2303.TW": "半導體",
    "3711.TW": "半導體", "2379.TW": "半導體", "3034.TW": "半導體",
    # AI伺服器與網通 (6)
    "2317.TW": "AI伺服器與網通", "2382.TW": "AI伺服器與網通", "3231.TW": "AI伺服器與網通",
    "6669.TW": "AI伺服器與網通", "2357.TW": "AI伺服器與網通", "2345.TW": "AI伺服器與網通",
    # 電子零組件與設備 (10)
    "2308.TW": "電子零組件與設備", "2059.TW": "電子零組件與設備", "3017.TW": "電子零組件與設備",
    "2383.TW": "電子零組件與設備", "2360.TW": "電子零組件與設備", "3008.TW": "電子零組件與設備",
    "2327.TW": "電子零組件與設備", "3037.TW": "電子零組件與設備", "2301.TW": "電子零組件與設備",
    "2395.TW": "電子零組件與設備",
    # 金融保險與租賃 (13)
    "2880.TW": "金融保險", "2881.TW": "金融保險", "2882.TW": "金融保險",
    "2883.TW": "金融保險", "2884.TW": "金融保險", "2885.TW": "金融保險",
    "2886.TW": "金融保險", "2887.TW": "金融保險", "2890.TW": "金融保險",
    "2891.TW": "金融保險", "2892.TW": "金融保險", "5880.TW": "金融保險",
    "5871.TW": "金融保險",
    # 航運 (4)
    "2603.TW": "航運", "2609.TW": "航運", "2615.TW": "航運", "2618.TW": "航運",
    # 電信與消費 (5)
    "2412.TW": "電信與消費", "3045.TW": "電信與消費", "4904.TW": "電信與消費",
    "1216.TW": "電信與消費", "2912.TW": "電信與消費",
    # 傳產塑鋼與生技 (6)
    "1301.TW": "傳產與生技", "1303.TW": "傳產與生技", "1326.TW": "傳產與生技",
    "6505.TW": "傳產與生技", "2002.TW": "傳產與生技", "6446.TW": "傳產與生技",
}

BASE_WEIGHTS = {
    "z_roe": 0.25,
    "z_net_margin": 0.15,
    "z_fcf_margin": 0.15,
    "z_cash_conv": 0.10,
    "z_low_debt": 0.15,
    "z_ey": 0.10,
    "z_bp": 0.05,
    "z_dy": 0.05,
}

FACTOR_LABELS = {
    "z_roe": "ROE (股東權益報酬率)",
    "z_net_margin": "Net Margin (淨利率)",
    "z_fcf_margin": "FCF Margin (自由現金流率)",
    "z_cash_conv": "OCF / NI (盈餘含金量)",
    "z_low_debt": "Low Debt (-D/E)",
    "z_ey": "Earnings Yield (1/PE)",
    "z_bp": "Book-to-Price (1/PB)",
    "z_dy": "Dividend Yield (殖利率)",
}


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
    daily = pd.read_sql_query("""
        SELECT s.ticker, s.date, s.raw_high, s.raw_low, s.raw_close, s.adj_close, s.dividends,
               f.sma_20, f.sma_50, f.atr_14, f.rsi_14,
               v.pe_ratio, v.pb_ratio, v.dividend_yield, v.roe_implied_pct
        FROM stock_daily s
        LEFT JOIN daily_factors f ON s.ticker = f.ticker AND s.date = f.date
        LEFT JOIN daily_valuation v ON s.ticker = v.ticker AND s.date = v.date
        ORDER BY s.ticker, s.date
    """, conn)
    daily["adj_close"] = daily.groupby("ticker")["adj_close"].ffill()
    daily["raw_close"] = daily.groupby("ticker")["raw_close"].ffill()
    qf = pd.read_sql_query("SELECT * FROM quarterly_fundamentals ORDER BY ticker, quarter_end", conn)
    qf["pub_date"] = qf["quarter_end"].apply(pub_date_from_quarter_end)
    conn.close()
    return daily, qf, meta_map


def build_pit_snapshot(qf: pd.DataFrame, d_slice: pd.DataFrame, as_of_date: str) -> pd.DataFrame:
    avail = qf[(qf["pub_date"] <= as_of_date) & (qf["revenue"].notnull()) & (qf["revenue"] > 0)].copy()
    rows = []
    for ticker in sorted(d_slice.index):
        d = d_slice.loc[ticker]
        pe = float(d["pe_ratio"]) if pd.notnull(d["pe_ratio"]) else np.nan
        pb = float(d["pb_ratio"]) if pd.notnull(d["pb_ratio"]) else np.nan
        dy = float(d["dividend_yield"]) if pd.notnull(d["dividend_yield"]) else 0.0
        roe_imp = float(d["roe_implied_pct"]) if pd.notnull(d["roe_implied_pct"]) else np.nan

        g = avail[avail["ticker"] == ticker].sort_values("quarter_end")
        if not g.empty:
            tail4 = g.tail(4)
            latest = g.iloc[-1]
            rev_sum = tail4["revenue"].sum()
            ni_sum = tail4["net_income"].sum()
            ocf_sum = tail4["ocf"].sum()
            fcf_sum = tail4["fcf"].sum()
            nm = (ni_sum / rev_sum * 100.0) if rev_sum > 0 else np.nan
            fm = (fcf_sum / rev_sum * 100.0) if rev_sum > 0 else np.nan
            cc = (ocf_sum / ni_sum) if ni_sum > 0 else (-1.0 if ocf_sum <= 0 else 0.0)
            de = float(latest["debt_to_equity"]) if pd.notnull(latest["debt_to_equity"]) else np.nan
            valid_roe = tail4["roe_ttm_pct"].dropna()
            roe = float(valid_roe.iloc[-1]) if len(valid_roe) > 0 else roe_imp
        else:
            nm = fm = cc = de = np.nan
            roe = roe_imp

        rows.append({
            "ticker": ticker, "sector": TW50_SECTORS.get(ticker, "其他"),
            "roe_pct": roe, "net_margin": nm, "fcf_margin": fm, "cash_conv": cc,
            "debt_to_equity": de,
            "earnings_yield": (100.0 / pe) if (pd.notnull(pe) and pe > 0) else 0.0,
            "book_to_price": (1.0 / pb) if (pd.notnull(pb) and pb > 0) else 0.0,
            "dividend_yield": dy,
        })
    snap = pd.DataFrame(rows).set_index("ticker")
    de_filled = snap["debt_to_equity"].fillna(snap["debt_to_equity"].median())
    snap["z_roe"] = zscore_clean(snap["roe_pct"])
    snap["z_net_margin"] = zscore_clean(snap["net_margin"])
    snap["z_fcf_margin"] = zscore_clean(snap["fcf_margin"])
    snap["z_cash_conv"] = zscore_clean(snap["cash_conv"].clip(-2, 4))
    snap["z_low_debt"] = -zscore_clean(de_filled)
    snap["z_ey"] = zscore_clean(snap["earnings_yield"])
    snap["z_bp"] = zscore_clean(snap["book_to_price"])
    snap["z_dy"] = zscore_clean(snap["dividend_yield"])
    return snap


def run_buffett_sim(
    adj_piv: pd.DataFrame,
    raw_piv: pd.DataFrame,
    div_piv: pd.DataFrame,
    snaps: Dict[str, pd.DataFrame],
    rebal_dates: List[str],
    weights: Dict[str, float],
    meta_map: Dict[str, str],
    top_k: int = 10,
) -> Tuple[pd.Series, Dict[str, List[str]], List[dict]]:
    dates = list(adj_piv.index)
    rebal_set = set(rebal_dates)
    cash = INITIAL_CASH
    shares: Dict[str, float] = {}
    entry_info: Dict[str, dict] = {}
    period_holdings: Dict[str, List[str]] = {}
    trades = []
    eq_curve = []

    # Normalize weights
    w_sum = sum(weights.values())
    norm_w = {k: v / w_sum for k, v in weights.items()}

    for dt in dates:
        for t, sh in shares.items():
            if sh > 0:
                d = div_piv.at[dt, t]
                if pd.notnull(d) and d > 0:
                    cash += sh * float(d)

        if dt in rebal_set:
            snap = snaps[dt].copy()
            score = sum(norm_w[fk] * snap[fk] for fk in norm_w)
            ranked = list(score.sort_values(ascending=False).index)
            keep = [t for t in shares.keys() if shares[t] > 0 and t in ranked[:15]]
            sel = list(keep)
            for t in ranked:
                if len(sel) >= top_k: break
                if t not in sel: sel.append(t)
            sel = sel[:top_k]
            period_holdings[dt] = sel
            tgt_w = {t: 1.0 / len(sel) for t in sel}

            pv = cash + sum(sh * float(raw_piv.at[dt, t]) for t, sh in shares.items() if sh > 0)
            for t in list(shares.keys()):
                sh = shares[t]
                if sh <= 0: continue
                px = float(raw_piv.at[dt, t])
                cw = (sh * px) / pv
                tw = tgt_w.get(t, 0.0)
                if tw == 0.0 or (cw - tw) > 0.02:
                    sell_sh = sh if tw == 0.0 else max(0.0, min(sh, sh - (pv * tw) / px))
                    exec_px = px * (1.0 - TW_SLIPPAGE)
                    gross = sell_sh * exec_px
                    cost = gross * (TW_COMMISSION + TW_TAX)
                    cash += gross - cost
                    shares[t] -= sell_sh
                    if tw == 0.0 or shares[t] < 1e-6:
                        ei = entry_info.pop(t, None)
                        if ei is not None:
                            adj_ex = float(adj_piv.at[dt, t])
                            ret_pct = (adj_ex / ei["adj_entry"] - 1.0) * 100.0 - (TW_COMMISSION * 2 + TW_TAX + TW_SLIPPAGE * 2) * 100.0
                            pnl = (exec_px - ei["raw_entry"]) * ei["shares"] - cost - ei["buy_cost"]
                            trades.append({"ticker": t, "name": meta_map.get(t, t), "sector": TW50_SECTORS.get(t, "其他"),
                                           "entry_date": ei["entry_date"], "exit_date": dt, "net_pnl": pnl, "return_pct": ret_pct, "status": "CLOSED"})
                        shares.pop(t, None)

            pv = cash + sum(sh * float(raw_piv.at[dt, t]) for t, sh in shares.items() if sh > 0)
            plan = {}
            tot_need = 0.0
            for t, tw in tgt_w.items():
                px = float(raw_piv.at[dt, t])
                need = pv * tw - shares.get(t, 0.0) * px
                if need > pv * 0.02:
                    plan[t] = (need, px)
                    tot_need += need * (1.0 + TW_SLIPPAGE + TW_COMMISSION)
            scale = min(1.0, (cash * 0.999) / tot_need) if tot_need > 0 else 0.0
            for t, (raw_alloc, px) in plan.items():
                alloc = raw_alloc * scale
                exec_px = px * (1.0 + TW_SLIPPAGE)
                bsh = alloc / (exec_px * (1.0 + TW_COMMISSION))
                if bsh <= 0: continue
                bcost = bsh * exec_px * TW_COMMISSION
                if bsh * exec_px + bcost <= cash + 1e-6:
                    cash -= bsh * exec_px + bcost
                    prev = shares.get(t, 0.0)
                    shares[t] = prev + bsh
                    if prev == 0.0:
                        entry_info[t] = {"entry_date": dt, "raw_entry": exec_px, "adj_entry": float(adj_piv.at[dt, t]), "shares": bsh, "buy_cost": bcost}

        eq = cash + sum(sh * float(raw_piv.at[dt, t]) for t, sh in shares.items() if sh > 0)
        eq_curve.append((dt, eq))

    last_dt = dates[-1]
    for t, ei in entry_info.items():
        if shares.get(t, 0.0) > 0:
            px = float(raw_piv.at[last_dt, t])
            adj_ex = float(adj_piv.at[last_dt, t])
            ret_pct = (adj_ex / ei["adj_entry"] - 1.0) * 100.0 - (TW_COMMISSION + TW_SLIPPAGE) * 100.0
            pnl = (px - ei["raw_entry"]) * shares[t] - ei["buy_cost"]
            trades.append({"ticker": t, "name": meta_map.get(t, t), "sector": TW50_SECTORS.get(t, "其他"),
                           "entry_date": ei["entry_date"], "exit_date": last_dt, "net_pnl": pnl, "return_pct": ret_pct, "status": "OPEN"})

    eq_s = pd.Series(dict(eq_curve))
    eq_s.index = pd.to_datetime(eq_s.index)
    return eq_s, period_holdings, trades


def quick_perf(eq: pd.Series) -> Tuple[float, float, float]:
    rets = eq.pct_change().dropna()
    tot = (eq.iloc[-1] / eq.iloc[0] - 1.0) * 100.0
    sh = float(((rets - RF_ANNUAL / 252.0).mean() / (rets.std() + 1e-12)) * np.sqrt(252))
    mdd = float(((eq / eq.cummax()) - 1.0).min() * 100.0)
    return round(tot, 2), round(sh, 2), round(mdd, 2)


def compute_brinson_bhb_bf(adj_piv: pd.DataFrame, period_holdings: Dict[str, List[str]], rebal_dates: List[str]) -> Tuple[pd.DataFrame, dict]:
    """Multi-period Carino-linked Brinson BHB & BF Sector Attribution."""
    last_dt = list(adj_piv.index)[-1]
    period_ends = rebal_dates[1:] + [last_dt]
    all_tickers = sorted(adj_piv.columns)
    sectors = sorted(set(TW50_SECTORS.values()))

    # Collect per-period Brinson components
    per_period = []
    rp_list, rb_list = [], []

    for rd, ed in zip(rebal_dates, period_ends):
        stock_rets = (adj_piv.loc[ed] / adj_piv.loc[rd] - 1.0).fillna(0.0)
        p_set = period_holdings[rd]
        w_p_stock = {t: (1.0 / len(p_set) if t in p_set else 0.0) for t in all_tickers}
        w_b_stock = {t: 1.0 / len(all_tickers) for t in all_tickers}

        rp = sum(w_p_stock[t] * stock_rets[t] for t in all_tickers)
        rb = sum(w_b_stock[t] * stock_rets[t] for t in all_tickers)
        rp_list.append(rp)
        rb_list.append(rb)

        sec_rows = {}
        for sec in sectors:
            sec_t = [t for t in all_tickers if TW50_SECTORS.get(t) == sec]
            wp = sum(w_p_stock[t] for t in sec_t)
            wb = sum(w_b_stock[t] for t in sec_t)
            r_bi = sum(w_b_stock[t] * stock_rets[t] for t in sec_t) / wb if wb > 0 else 0.0
            r_pi = sum(w_p_stock[t] * stock_rets[t] for t in sec_t) / wp if wp > 0 else r_bi

            # BHB
            bhb_alloc = (wp - wb) * r_bi
            # BF
            bf_alloc = (wp - wb) * (r_bi - rb)
            sel = wb * (r_pi - r_bi)
            inter = (wp - wb) * (r_pi - r_bi)
            sec_rows[sec] = {
                "wp": wp, "wb": wb, "r_pi": r_pi, "r_bi": r_bi,
                "bhb_alloc": bhb_alloc, "bf_alloc": bf_alloc, "sel": sel, "inter": inter
            }
        per_period.append((rp, rb, sec_rows))

    # Carino Multi-Period Linking Factors
    cum_rp = float(np.prod([1.0 + r for r in rp_list]) - 1.0)
    cum_rb = float(np.prod([1.0 + r for r in rb_list]) - 1.0)
    k_tot = (np.log(1.0 + cum_rp) - np.log(1.0 + cum_rb)) / (cum_rp - cum_rb) if abs(cum_rp - cum_rb) > 1e-10 else 1.0 / (1.0 + cum_rb)

    agg = {sec: {"avg_wp": 0.0, "avg_wb": 0.0, "bhb_alloc": 0.0, "bf_alloc": 0.0, "sel": 0.0, "inter": 0.0} for sec in sectors}
    n_p = len(per_period)
    for rp, rb, sec_rows in per_period:
        k_t = (np.log(1.0 + rp) - np.log(1.0 + rb)) / (rp - rb) if abs(rp - rb) > 1e-10 else 1.0 / (1.0 + rb)
        link = k_t / k_tot
        for sec, d in sec_rows.items():
            agg[sec]["avg_wp"] += d["wp"] / n_p * 100.0
            agg[sec]["avg_wb"] += d["wb"] / n_p * 100.0
            agg[sec]["bhb_alloc"] += d["bhb_alloc"] * link * 100.0
            agg[sec]["bf_alloc"] += d["bf_alloc"] * link * 100.0
            agg[sec]["sel"] += d["sel"] * link * 100.0
            agg[sec]["inter"] += d["inter"] * link * 100.0

    rows = []
    for sec in sectors:
        a = agg[sec]
        tot_sel = a["sel"] + a["inter"]
        tot_active = a["bf_alloc"] + tot_sel
        rows.append({
            "sector": sec,
            "avg_wp_pct": round(a["avg_wp"], 2),
            "avg_wb_pct": round(a["avg_wb"], 2),
            "active_wt_pct": round(a["avg_wp"] - a["avg_wb"], 2),
            "bhb_alloc_pct": round(a["bhb_alloc"], 2),
            "bf_alloc_pct": round(a["bf_alloc"], 2),
            "selection_pct": round(a["sel"], 2),
            "interaction_pct": round(a["inter"], 2),
            "total_selection_pct": round(tot_sel, 2),
            "total_active_pct": round(tot_active, 2),
        })
    df = pd.DataFrame(rows).sort_values("total_active_pct", ascending=False)
    totals = {
        "cum_rp_pct": round(cum_rp * 100.0, 2),
        "cum_rb_pct": round(cum_rb * 100.0, 2),
        "active_return_pct": round((cum_rp - cum_rb) * 100.0, 2),
        "sum_bhb_alloc": round(df["bhb_alloc_pct"].sum(), 2),
        "sum_bf_alloc": round(df["bf_alloc_pct"].sum(), 2),
        "sum_selection": round(df["selection_pct"].sum(), 2),
        "sum_interaction": round(df["interaction_pct"].sum(), 2),
        "sum_total_selection": round(df["total_selection_pct"].sum(), 2),
    }
    return df, totals


def compute_capm_alpha_beta(port_eq: pd.Series, bm_eq: pd.Series) -> dict:
    rp = port_eq.pct_change().dropna()
    rb = bm_eq.pct_change().dropna().reindex(rp.index).fillna(0.0)
    rf_d = RF_ANNUAL / 252.0
    y = (rp - rf_d).values
    x = (rb - rf_d).values
    X = np.column_stack([np.ones(len(x)), x])
    beta_hat = np.linalg.lstsq(X, y, rcond=None)[0]
    alpha_d, beta = float(beta_hat[0]), float(beta_hat[1])
    resid = y - X @ beta_hat
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / (ss_tot + 1e-12)
    se_alpha = np.sqrt((ss_res / max(len(y) - 2, 1)) * np.linalg.inv(X.T @ X)[0, 0])
    t_alpha = alpha_d / (se_alpha + 1e-12)
    active = rp - rb
    te = float(active.std() * np.sqrt(252) * 100.0)
    ir = float((active.mean() / (active.std() + 1e-12)) * np.sqrt(252))
    return {
        "ann_jensen_alpha_pct": round(alpha_d * 252 * 100.0, 2),
        "alpha_t_stat": round(float(t_alpha), 2),
        "beta": round(beta, 3),
        "r_squared": round(float(r2), 3),
        "tracking_error_pct": round(te, 2),
        "info_ratio": round(ir, 2),
    }


def compute_factor_decay_and_regime_ic(snaps: Dict[str, pd.DataFrame], adj_piv: pd.DataFrame, rebal_dates: List[str]):
    all_dates = list(adj_piv.index)
    horizons = [5, 10, 20, 40, 60, 120]
    decay_rows = []

    for fk, flbl in FACTOR_LABELS.items():
        row = {"factor": fk, "label": flbl}
        ics_h = []
        for h in horizons:
            vals = []
            for rd in rebal_dates:
                idx = all_dates.index(rd)
                if idx + h < len(all_dates):
                    ed = all_dates[idx + h]
                    fwd = adj_piv.loc[ed] / adj_piv.loc[rd] - 1.0
                    valid = pd.concat([snaps[rd][fk], fwd], axis=1).dropna()
                    if len(valid) >= 10:
                        vals.append(float(valid.iloc[:, 0].rank().corr(valid.iloc[:, 1].rank())))
            mean_v = float(np.mean(vals)) if vals else np.nan
            row[f"IC_{h}d"] = round(mean_v, 4) if pd.notnull(mean_v) else np.nan
            ics_h.append((h, mean_v))
        decay_rows.append(row)
    decay_df = pd.DataFrame(decay_rows)

    # Period-by-period IC & Regime-Conditional IC (Bull Up: Q1-Q3 periods vs Pullback/Chop: 08-17~11-13)
    period_ends = rebal_dates[1:] + [all_dates[-1]]
    bm_ret_period = [(adj_piv.loc[ed] / adj_piv.loc[rd] - 1.0).mean() * 100.0 for rd, ed in zip(rebal_dates, period_ends)]
    # Periods with BM return > 0 = BULL_UP, BM return <= 0 = PULLBACK_CHOP
    regime_rows = []
    for fk, flbl in FACTOR_LABELS.items():
        bull_ics, bear_ics, all_ics = [], [], []
        p_map = {}
        for i, (rd, ed) in enumerate(zip(rebal_dates, period_ends)):
            fwd = adj_piv.loc[ed] / adj_piv.loc[rd] - 1.0
            valid = pd.concat([snaps[rd][fk], fwd], axis=1).dropna()
            ic = float(valid.iloc[:, 0].rank().corr(valid.iloc[:, 1].rank()))
            all_ics.append(ic)
            p_map[f"P{i+1}_{rd[5:]}"] = round(ic, 3)
            if bm_ret_period[i] > 0:
                bull_ics.append(ic)
            else:
                bear_ics.append(ic)

        mean_all = float(np.mean(all_ics))
        bull_ic = float(np.mean(bull_ics)) if bull_ics else np.nan
        bear_ic = float(np.mean(bear_ics)) if bear_ics else np.nan

        if mean_all >= 0.03 and bull_ic > 0 and bear_ic > 0:
            verdict = "ACTIVE (全天候有效)"
        elif (bull_ic > 0.03 and bear_ic < 0) or (bear_ic > 0.03 and bull_ic < 0):
            verdict = "REGIME_DEPENDENT (市況分化)"
        elif mean_all < -0.03:
            verdict = "INVERTED / DECAYED (反轉/失效)"
        else:
            verdict = "WEAK / NEUTRAL (弱效)"

        regime_rows.append({
            "factor": fk, "label": flbl,
            **p_map,
            "bull_up_ic": round(bull_ic, 4),
            "pullback_ic": round(bear_ic, 4),
            "mean_ic": round(mean_all, 4),
            "cum_ic": round(float(np.sum(all_ics)), 4),
            "status": verdict,
        })
    regime_df = pd.DataFrame(regime_rows).sort_values("mean_ic", ascending=False)

    # Collinearity Matrix (latest rebalance snapshot)
    corr_mat = snaps[rebal_dates[-1]][list(FACTOR_LABELS.keys())].rank().corr().round(3)
    return decay_df, regime_df, corr_mat


def compute_mae_mfe_whipsaw(daily: pd.DataFrame) -> pd.DataFrame:
    """Audit trades from previous buffett_tech_20261124_tw50/backtest_result.db for MAE/MFE & Post-Exit Whipsaw."""
    tech_db = os.path.join("trades", "buffett_tech_20261124_tw50", "backtest_result.db")
    if not os.path.exists(tech_db):
        return pd.DataFrame()
    conn = sqlite3.connect(tech_db)
    tr_df = pd.read_sql_query("SELECT * FROM backtest_trades", conn)
    conn.close()

    by_ticker = {t: g.set_index("date").sort_index() for t, g in daily.groupby("ticker")}
    rows = []
    for (pool, ov), grp in tr_df.groupby(["pool", "overlay"]):
        if not ((pool == "buffett_full_score_top10" and ov in ("none_bh", "sma50_trend", "risk_shield"))
                or (pool == "buffett_moat_compounder" and ov in ("none_bh", "sma50_trend", "risk_shield", "macd_timing"))):
            continue
        maes, mfes, post10_rets, whipsaws = [], [], [], []
        for _, t in grp.iterrows():
            gdf = by_ticker.get(t["ticker"])
            if gdf is None: continue
            seg = gdf.loc[t["entry_date"]:t["exit_date"]]
            if seg.empty: continue
            ep = float(seg["adj_close"].iloc[0])
            mae = float((seg["adj_close"].min() / ep - 1.0) * 100.0)
            mfe = float((seg["adj_close"].max() / ep - 1.0) * 100.0)
            maes.append(mae)
            mfes.append(mfe)

            # Post-exit 10-day check for non-fundamental technical exits
            if t["exit_reason"] not in ("Open Position", "Fundamental Rebalance Out"):
                all_idx = list(gdf.index)
                if t["exit_date"] in all_idx:
                    pos = all_idx.index(t["exit_date"])
                    if pos + 10 < len(all_idx):
                        ex_p = float(gdf["adj_close"].iloc[pos])
                        p10 = float(gdf["adj_close"].iloc[pos + 10])
                        r10 = (p10 / ex_p - 1.0) * 100.0
                        post10_rets.append(r10)
                        whipsaws.append(1 if r10 > 0 else 0)

        rows.append({
            "pool": pool, "overlay": ov, "trades": len(grp),
            "median_mae_pct": round(float(np.median(maes)), 2) if maes else 0.0,
            "median_mfe_pct": round(float(np.median(mfes)), 2) if mfes else 0.0,
            "tech_exits_checked": len(whipsaws),
            "whipsaw_10d_rate_pct": round(float(np.mean(whipsaws) * 100.0), 1) if whipsaws else 0.0,
            "avg_post_exit_10d_pct": round(float(np.mean(post10_rets)), 2) if post10_rets else 0.0,
        })
    return pd.DataFrame(rows)


def main():
    daily, qf, meta_map = load_data()
    adj_piv = daily.pivot(index="date", columns="ticker", values="adj_close").sort_index().ffill()
    raw_piv = daily.pivot(index="date", columns="ticker", values="raw_close").sort_index().ffill()
    div_piv = daily.pivot(index="date", columns="ticker", values="dividends").sort_index().fillna(0.0)
    daily_by_date = {dt: g.set_index("ticker") for dt, g in daily.groupby("date")}
    all_dates = list(adj_piv.index)
    rebal_dates = [[d for d in all_dates if d >= cd][0] for cd in ["2026-01-02", "2026-04-01", "2026-05-16", "2026-08-15"]]

    snaps = {rd: build_pit_snapshot(qf, daily_by_date[rd], rd) for rd in rebal_dates}
    bm_eq = adj_piv.div(adj_piv.iloc[0]).mean(axis=1) * INITIAL_CASH
    bm_eq.index = pd.to_datetime(bm_eq.index)

    # Full 8-factor baseline run
    full_eq, period_holdings, full_trades = run_buffett_sim(adj_piv, raw_piv, div_piv, snaps, rebal_dates, BASE_WEIGHTS, meta_map)
    base_ret, base_sh, base_mdd = quick_perf(full_eq)
    print(f"Baseline Full 8-Factor Top10: Return={base_ret:+.2f}%, Sharpe={base_sh:.2f}, MDD={base_mdd:.2f}%")

    # Module 1: Brinson BHB & BF
    brinson_df, brinson_tot = compute_brinson_bhb_bf(adj_piv, period_holdings, rebal_dates)
    print("\n=== MODULE 1: BRINSON BHB & BF SECTOR ATTRIBUTION ===")
    print(brinson_df.to_string(index=False))
    print("Totals:", brinson_tot)

    # Module 2: Leave-One-Out Factor Ablation
    ab_rows = []
    for fk, flbl in FACTOR_LABELS.items():
        w_sub = {k: v for k, v in BASE_WEIGHTS.items() if k != fk}
        eq_sub, _, _ = run_buffett_sim(adj_piv, raw_piv, div_piv, snaps, rebal_dates, w_sub, meta_map)
        r_s, sh_s, mdd_s = quick_perf(eq_sub)
        d_ret = round(base_ret - r_s, 2)
        d_sh = round(base_sh - sh_s, 2)
        d_mdd = round(abs(mdd_s) - abs(base_mdd), 2)  # positive = factor helped reduce MDD
        role = "CORE DRIVER (核心引擎)" if d_sh > 0.10 else ("DRAG / PRUNE (拖油瓶)" if d_sh < -0.05 else "NEUTRAL (中性輔助)")
        ab_rows.append({
            "dropped_factor": fk, "label": flbl, "orig_weight_pct": int(BASE_WEIGHTS[fk] * 100),
            "ret_without_pct": r_s, "sharpe_without": sh_s, "mdd_without_pct": mdd_s,
            "delta_ret_pct": d_ret, "delta_sharpe": d_sh, "delta_mdd_saved_pct": d_mdd, "role": role,
        })
    ablation_df = pd.DataFrame(ab_rows).sort_values("delta_sharpe", ascending=False)
    print("\n=== MODULE 2: LEAVE-ONE-OUT FACTOR ABLATION ===")
    print(ablation_df[["label", "orig_weight_pct", "delta_ret_pct", "delta_sharpe", "delta_mdd_saved_pct", "role"]].to_string(index=False))

    # Module 3: Alpha / Beta & Single-Stock Concentration
    capm = compute_capm_alpha_beta(full_eq, bm_eq)
    print("\n=== MODULE 3: CAPM ALPHA / BETA & STOCK ATTRIBUTION ===")
    print("CAPM:", capm)
    tr_df = pd.DataFrame(full_trades)
    stock_contrib = tr_df.groupby(["ticker", "name", "sector"]).agg(
        trades=("net_pnl", "count"), total_pnl=("net_pnl", "sum"), avg_ret_pct=("return_pct", "mean")
    ).reset_index().sort_values("total_pnl", ascending=False)
    tot_pnl = stock_contrib["total_pnl"].sum()
    stock_contrib["pnl_share_pct"] = (stock_contrib["total_pnl"] / (tot_pnl + 1e-8) * 100.0).round(1)
    stock_contrib["total_pnl"] = stock_contrib["total_pnl"].round(0)
    stock_contrib["avg_ret_pct"] = stock_contrib["avg_ret_pct"].round(2)
    print(stock_contrib.head(10).to_string(index=False))

    # Module 4: Factor Decay (Horizon IC), Regime-Conditional IC & Collinearity
    decay_df, regime_df, corr_mat = compute_factor_decay_and_regime_ic(snaps, adj_piv, rebal_dates)
    print("\n=== MODULE 4A: FACTOR IC HORIZON DECAY (5d -> 120d) ===")
    print(decay_df.to_string(index=False))
    print("\n=== MODULE 4B: REGIME-CONDITIONAL IC & FAILURE STATUS ===")
    print(regime_df.to_string(index=False))

    # High collinearity pairs
    col_pairs = []
    fkeys = list(FACTOR_LABELS.keys())
    for i in range(len(fkeys)):
        for j in range(i + 1, len(fkeys)):
            cval = float(corr_mat.loc[fkeys[i], fkeys[j]])
            if abs(cval) >= 0.65:
                col_pairs.append({"factor_a": FACTOR_LABELS[fkeys[i]], "factor_b": FACTOR_LABELS[fkeys[j]], "spearman_rho": cval})
    col_df = pd.DataFrame(col_pairs)
    print("\n=== MODULE 4C: HIGH COLLINEARITY PAIRS (|rho| >= 0.65) ===")
    print(col_df.to_string(index=False) if not col_df.empty else "None")

    # Module 5: MAE/MFE & Whipsaw
    micro_df = compute_mae_mfe_whipsaw(daily)
    print("\n=== MODULE 5: MAE / MFE & POST-EXIT 10D WHIPSAW ===")
    print(micro_df.to_string(index=False))

    # Save SQLite
    db_out = os.path.join(OUT_DIR, "attribution_result.db")
    if os.path.exists(db_out): os.remove(db_out)
    conn = sqlite3.connect(db_out)
    brinson_df.to_sql("brinson_sector", conn, index=False, if_exists="replace")
    ablation_df.to_sql("factor_ablation", conn, index=False, if_exists="replace")
    pd.DataFrame([capm]).to_sql("alpha_beta_summary", conn, index=False, if_exists="replace")
    stock_contrib.to_sql("stock_contribution", conn, index=False, if_exists="replace")
    decay_df.to_sql("factor_ic_decay", conn, index=False, if_exists="replace")
    regime_df.to_sql("regime_ic", conn, index=False, if_exists="replace")
    micro_df.to_sql("trade_micro_attribution", conn, index=False, if_exists="replace")
    conn.close()

    # Build HTML & MD
    build_html(brinson_df, brinson_tot, ablation_df, capm, stock_contrib, decay_df, regime_df, corr_mat, micro_df)
    build_md(brinson_df, brinson_tot, ablation_df, capm, stock_contrib, decay_df, regime_df, col_df, micro_df)
    print(f"\nSaved Attribution & Decay outputs -> {OUT_DIR}/")


def build_html(brinson_df, brinson_tot, ablation_df, capm, stock_contrib, decay_df, regime_df, corr_mat, micro_df):
    # Fig 1: Brinson BF Allocation vs Total Selection by Sector
    fig1 = go.Figure()
    fig1.add_trace(go.Bar(name="BF 配置效應 (Allocation)", x=brinson_df["sector"], y=brinson_df["bf_alloc_pct"], marker_color="#38BDF8"))
    fig1.add_trace(go.Bar(name="總選股效應 (Selection + Interaction)", x=brinson_df["sector"], y=brinson_df["total_selection_pct"], marker_color="#00D084"))
    fig1.add_trace(go.Bar(name="合計超額貢獻 (Total Active)", x=brinson_df["sector"], y=brinson_df["total_active_pct"], marker_color="#FCD34D"))
    fig1.update_layout(template="plotly_dark", paper_bgcolor="#181C25", plot_bgcolor="#14171F", barmode="group",
                       title=f"模組一：Brinson (BF) 產業歸因 — 總超額 {brinson_tot['active_return_pct']:+.2f}% (配置 {brinson_tot['sum_bf_alloc']:+.2f}% + 總選股 {brinson_tot['sum_total_selection']:+.2f}%)",
                       yaxis_title="超額報酬貢獻 (%)", height=420)

    # Fig 2: Leave-One-Out Factor Ablation
    fig2 = make_subplots(rows=1, cols=2, subplot_titles=("因子邊際貢獻 ΔSharpe (正值=核心引擎)", "因子邊際貢獻 ΔReturn (%)"))
    fig2.add_trace(go.Bar(y=ablation_df["label"], x=ablation_df["delta_sharpe"], orientation="h", showlegend=False,
                          marker_color=["#00D084" if v >= 0 else "#FF4D4F" for v in ablation_df["delta_sharpe"]],
                          text=[f"{v:+.2f}" for v in ablation_df["delta_sharpe"]], textposition="outside"), row=1, col=1)
    fig2.add_trace(go.Bar(y=ablation_df["label"], x=ablation_df["delta_ret_pct"], orientation="h", showlegend=False,
                          marker_color=["#38BDF8" if v >= 0 else "#FF4D4F" for v in ablation_df["delta_ret_pct"]],
                          text=[f"{v:+.2f}%" for v in ablation_df["delta_ret_pct"]], textposition="outside"), row=1, col=2)
    fig2.update_layout(template="plotly_dark", paper_bgcolor="#181C25", plot_bgcolor="#14171F", height=400, margin=dict(l=170, r=40, t=55, b=40))

    # Fig 3: Factor IC Decay Curve + Regime-Conditional IC
    fig3 = make_subplots(rows=1, cols=2, subplot_titles=("因子半衰期衰減曲線 (IC: 5d → 120d)", "分市況條件 IC：多頭主升 vs 回檔震盪"))
    horizons = [5, 10, 20, 40, 60, 120]
    for _, r in decay_df.iterrows():
        fig3.add_trace(go.Scatter(x=[f"{h}d" for h in horizons], y=[r[f"IC_{h}d"] for h in horizons],
                                  mode="lines+markers", name=r["label"].split(" ")[0]), row=1, col=1)
    fig3.add_hline(y=0, line_dash="dot", line_color="#64748B", row=1, col=1)
    fig3.add_trace(go.Bar(name="多頭主升段 IC", x=[l.split(" ")[0] for l in regime_df["label"]], y=regime_df["bull_up_ic"], marker_color="#00D084"), row=1, col=2)
    fig3.add_trace(go.Bar(name="回檔震盪段 IC", x=[l.split(" ")[0] for l in regime_df["label"]], y=regime_df["pullback_ic"], marker_color="#FF4D4F"), row=1, col=2)
    fig3.update_layout(template="plotly_dark", paper_bgcolor="#181C25", plot_bgcolor="#14171F", height=430, barmode="group")

    # Fig 4: Spearman Correlation Heatmap
    short_names = [FACTOR_LABELS[k].split(" ")[0] for k in corr_mat.columns]
    fig4 = go.Figure(data=go.Heatmap(
        z=corr_mat.values, x=short_names, y=short_names, zmin=-1, zmax=1, colorscale="RdBu",
        text=corr_mat.values, texttemplate="%{text:.2f}", textfont={"size": 11}
    ))
    fig4.update_layout(template="plotly_dark", paper_bgcolor="#181C25", plot_bgcolor="#14171F",
                       title="因子兩兩 Spearman 共線性矩陣 (|ρ| ≥ 0.65 為高度冗餘)", height=420)

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="UTF-8" /><title>TW50 巴菲特策略：歸因分析與因子失效診斷報告</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  body {{ background:#14171F; color:#E2E8F0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; margin:0; padding:24px; }}
  .container {{ max-width:1440px; margin:0 auto; }}
  .kpi-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:24px; }}
  .kpi {{ background:#181C25; border:1px solid #2A3142; border-radius:10px; padding:16px 20px; }}
  .kpi-label {{ color:#94A3B8; font-size:12px; }} .kpi-val {{ font-size:26px; font-weight:700; margin:6px 0; }} .kpi-sub {{ color:#94A3B8; font-size:12px; }}
  .card {{ background:#181C25; border:1px solid #2A3142; border-radius:10px; padding:20px; margin-bottom:24px; }}
  .pos {{ color:#00D084; }} .neg {{ color:#FF4D4F; }}
</style></head><body><div class="container">
  <h1>🔬 TW50 巴菲特 8 因子策略：Brinson (BHB/BF) 歸因與因子失效診斷報告</h1>
  <div class="kpi-grid">
    <div class="kpi"><div class="kpi-label">Brinson 總超額報酬</div><div class="kpi-val pos">{brinson_tot['active_return_pct']:+.2f}%</div><div class="kpi-sub">BF 配置 {brinson_tot['sum_bf_alloc']:+.2f}% ｜ 總選股 {brinson_tot['sum_total_selection']:+.2f}%</div></div>
    <div class="kpi"><div class="kpi-label">年化 Jensen's Alpha</div><div class="kpi-val pos">{capm['ann_jensen_alpha_pct']:+.2f}%</div><div class="kpi-sub">t-stat = {capm['alpha_t_stat']:.2f} ｜ IR = {capm['info_ratio']:.2f}</div></div>
    <div class="kpi"><div class="kpi-label">市場風險暴露 Beta</div><div class="kpi-val" style="color:#38BDF8">{capm['beta']:.2f}</div><div class="kpi-sub">R² = {capm['r_squared']:.2f} ｜ 低 Beta 賺高 Alpha</div></div>
    <div class="kpi"><div class="kpi-label">前 3 大貢獻股佔總淨利</div><div class="kpi-val" style="color:#FCD34D">{stock_contrib.head(3)['pnl_share_pct'].sum():.1f}%</div><div class="kpi-sub">{', '.join(stock_contrib.head(3)['name'].tolist())}</div></div>
  </div>
  <div class="card"><div id="f1"></div></div>
  <div class="card"><div id="f2"></div></div>
  <div class="card"><div id="f3"></div></div>
  <div class="card"><div id="f4"></div></div>
</div>
<script>
  Plotly.newPlot('f1', {fig1.to_json()}.data, {fig1.to_json()}.layout, {{responsive:true}});
  Plotly.newPlot('f2', {fig2.to_json()}.data, {fig2.to_json()}.layout, {{responsive:true}});
  Plotly.newPlot('f3', {fig3.to_json()}.data, {fig3.to_json()}.layout, {{responsive:true}});
  Plotly.newPlot('f4', {fig4.to_json()}.data, {fig4.to_json()}.layout, {{responsive:true}});
</script></body></html>"""
    with open(os.path.join(OUT_DIR, "tw50_attribution_decay_Report.html"), "w", encoding="utf-8") as f:
        f.write(html)


def build_md(brinson_df, brinson_tot, ablation_df, capm, stock_contrib, decay_df, regime_df, col_df, micro_df):
    lines = [
        "# TW50 完整版巴菲特策略：歸因分析（BHB/BF）與因子失效診斷報告",
        "",
        "## 模組一：Brinson 產業績效歸因（BHB & BF 多期連結）",
        "",
        f"- **組合累計報酬**：`{brinson_tot['cum_rp_pct']:+.2f}%` vs **TW50 等權基準**：`{brinson_tot['cum_rb_pct']:+.2f}%` → **總超額報酬**：**`{brinson_tot['active_return_pct']:+.2f}%`**",
        f"- **BF 模型拆解**：產業配置效應 **`{brinson_tot['sum_bf_alloc']:+.2f}%`** + 純選股效應 **`{brinson_tot['sum_selection']:+.2f}%`** + 交互效應 **`{brinson_tot['sum_interaction']:+.2f}%`**（總選股效應 `S+I` = **`{brinson_tot['sum_total_selection']:+.2f}%`**）",
        f"- **BHB 模型對照**：配置效應 `{brinson_tot['sum_bhb_alloc']:+.2f}%`（與 BF 合計總超額一致）",
        "",
        "| 產業板塊 | 組合均權% | 基準均權% | 超/低配% | BHB 配置% | BF 配置% | 選股效應% | 交互效應% | 總選股(S+I)% | 合計超額% |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, r in brinson_df.iterrows():
        lines.append(f"| {r['sector']} | {r['avg_wp_pct']:.1f}% | {r['avg_wb_pct']:.1f}% | {r['active_wt_pct']:+.1f}% | {r['bhb_alloc_pct']:+.2f}% | {r['bf_alloc_pct']:+.2f}% | {r['selection_pct']:+.2f}% | {r['interaction_pct']:+.2f}% | {r['total_selection_pct']:+.2f}% | {r['total_active_pct']:+.2f}% |")

    lines += [
        "",
        "## 模組二：8 因子 Leave-One-Out 邊際貢獻消融",
        "",
        "| 剔除因子 | 原權重 | 剔除後報酬 | 剔除後 Sharpe | ΔReturn (邊際貢獻) | ΔSharpe (邊際貢獻) | ΔMDD 保護 | 角色裁決 |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | :--- |",
    ]
    for _, r in ablation_df.iterrows():
        lines.append(f"| {r['label']} | {r['orig_weight_pct']}% | {r['ret_without_pct']:+.2f}% | {r['sharpe_without']:.2f} | {r['delta_ret_pct']:+.2f}% | {r['delta_sharpe']:+.2f} | {r['delta_mdd_saved_pct']:+.2f}% | {r['role']} |")

    lines += [
        "",
        "## 模組三：CAPM Alpha/Beta 拆解與個股集中度",
        "",
        f"- **年化 Jensen's Alpha**：**`{capm['ann_jensen_alpha_pct']:+.2f}%`**（`t-stat = {capm['alpha_t_stat']:.2f}`）｜ **Beta**：**`{capm['beta']:.3f}`** ｜ **$R^2$**：`{capm['r_squared']:.3f}` ｜ **Tracking Error**：`{capm['tracking_error_pct']:.2f}%` ｜ **IR**：`{capm['info_ratio']:.2f}`",
        "",
        "| 代碼 | 名稱 | 產業 | 交易數 | 累計淨損益 (NTD) | 佔總淨利% | 平均報酬% |",
        "| :--- | :--- | :--- | ---: | ---: | ---: | ---: |",
    ]
    for _, r in stock_contrib.head(10).iterrows():
        lines.append(f"| `{r['ticker']}` | {r['name']} | {r['sector']} | {int(r['trades'])} | {r['total_pnl']:+,.0f} | {r['pnl_share_pct']:.1f}% | {r['avg_ret_pct']:+.2f}% |")

    lines += [
        "",
        "## 模組四：因子失效與半衰期衰減診斷",
        "",
        "### 4.1 因子前瞻 IC 半衰期衰減表（5d → 120d）",
        "",
        "| 因子 | IC_5d | IC_10d | IC_20d | IC_40d | IC_60d | IC_120d |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, r in decay_df.iterrows():
        lines.append(f"| {r['label']} | {r['IC_5d']:+.3f} | {r['IC_10d']:+.3f} | {r['IC_20d']:+.3f} | {r['IC_40d']:+.3f} | {r['IC_60d']:+.3f} | {r['IC_120d']:+.3f} |")

    lines += [
        "",
        "### 4.2 分市況條件 IC 與失效狀態裁決",
        "",
        "| 因子 | 多頭主升段 IC | 回檔震盪段 IC | 平均 IC | 累積 IC | 狀態診斷 |",
        "| :--- | ---: | ---: | ---: | ---: | :--- |",
    ]
    for _, r in regime_df.iterrows():
        lines.append(f"| {r['label']} | {r['bull_up_ic']:+.3f} | {r['pullback_ic']:+.3f} | {r['mean_ic']:+.3f} | {r['cum_ic']:+.3f} | {r['status']} |")

    lines += [
        "",
        "## 模組五：逐筆交易微觀歸因（MAE / MFE & 出場後 10 日洗盤率）",
        "",
        "| 選股池 | 技術策略 | 交易數 | MAE 中位數% | MFE 中位數% | 技術出場數 | 10日賣飛洗盤率% | 出場後10日均漲跌% |",
        "| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, r in micro_df.iterrows():
        lines.append(f"| {r['pool']} | `{r['overlay']}` | {int(r['trades'])} | {r['median_mae_pct']:.2f}% | {r['median_mfe_pct']:+.2f}% | {int(r['tech_exits_checked'])} | {r['whipsaw_10d_rate_pct']:.1f}% | {r['avg_post_exit_10d_pct']:+.2f}% |")

    with open(os.path.join(OUT_DIR, "attribution_decay_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
