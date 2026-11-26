"""
modules/stock_selector.py
遵循 prompts/stock_selector.md 之參數化選股與「評分＋機會＋風險」選股報告生成引擎。
範例：
  python -m modules.stock_selector --universe tw50 --strategy buffett_full --top-k 10
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

TW_COMMISSION = 0.000855
TW_TAX = 0.003
TW_SLIPPAGE = 0.0005
INITIAL_CASH = 1_000_000.0

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


def pub_date_from_quarter_end(qend: str) -> str:
    y, m, _ = qend.split("-")
    y = int(y)
    if m == "03": return f"{y}-05-15"
    if m == "06": return f"{y}-08-14"
    if m == "09": return f"{y}-11-14"
    if m == "12": return f"{y + 1}-03-31"
    return "9999-12-31"


def winsorize_mad(s: pd.Series, n_mads: float = 3.0) -> pd.Series:
    v = s.dropna()
    if len(v) < 5: return s
    med = v.median()
    mad = (v - med).abs().median()
    if mad == 0 or np.isnan(mad): return s
    return s.clip(lower=med - n_mads * 1.4826 * mad, upper=med + n_mads * 1.4826 * mad)


def zscore_clean(s: pd.Series) -> pd.Series:
    w = winsorize_mad(s)
    std = w.std()
    if std == 0 or np.isnan(std): return pd.Series(0.0, index=s.index)
    return ((w - w.mean()) / std).fillna(0.0)


def diagnose_stock_opp_risk(r: pd.Series, sec_count: int) -> Tuple[List[str], List[str], str]:
    """Generate human-readable Opportunities, Risks, and Handoff Action for a selected stock."""
    opps, risks = [], []
    roe = float(r["roe_pct"]) if pd.notnull(r["roe_pct"]) else 0.0
    pe = float(r["pe_ratio"]) if pd.notnull(r["pe_ratio"]) else np.nan
    pb = float(r["pb_ratio"]) if pd.notnull(r["pb_ratio"]) else np.nan
    dy = float(r["dividend_yield"]) if pd.notnull(r["dividend_yield"]) else 0.0
    nm = float(r["net_margin"]) if pd.notnull(r["net_margin"]) else 0.0
    fm = float(r["fcf_margin"]) if pd.notnull(r["fcf_margin"]) else 0.0
    cc = float(r["cash_conv"]) if pd.notnull(r["cash_conv"]) else 0.0
    de = float(r["debt_to_equity"]) if pd.notnull(r["debt_to_equity"]) else np.nan
    dt_r = float(r["dt_ma20"]) if pd.notnull(r["dt_ma20"]) else 0.0
    above_sma50 = bool(r["close"] >= r["sma50"])
    rsi = float(r["rsi_14"]) if pd.notnull(r["rsi_14"]) else 50.0

    # Opportunities
    if roe >= 25.0:
        opps.append(f"頂級護城河資本效率：ROE 高達 {roe:.1f}%（遠超巴菲特 15% 標準）")
    elif roe >= 15.0:
        opps.append(f"穩健股東回報：ROE 達 {roe:.1f}%，具備長期複利能力")
    if nm >= 30.0:
        opps.append(f"高定價權：稅後淨利率 {nm:.1f}%，獲利護城河深厚")
    if fm >= 15.0 and cc >= 0.8:
        opps.append(f"強勁現金牛：自由現金流率 {fm:.1f}%、盈餘含金量 {cc:.2f}x（真金白銀入帳）")
    if pd.notnull(pe) and 0 < pe <= 16.0:
        opps.append(f"估值安全邊際厚：本益比僅 {pe:.1f} 倍" + (f"、殖利率 {dy:.2f}%" if dy >= 3.0 else ""))
    elif dy >= 4.0:
        opps.append(f"高股息下檔保護：現金殖利率 {dy:.2f}%")
    if above_sma50:
        opps.append("技術面多頭確認：股價站穩 50 日季線之上")
    if not opps:
        opps.append(f"綜合多因子均衡表現佳（淨利率 {nm:.1f}%、現金流率 {fm:.1f}%）")

    # Risks
    if not above_sma50:
        risks.append("短中期趨勢偏弱：目前股價位於 50 日季線下方，尚需等待止跌確認")
    if pd.notnull(pe) and pe >= 30.0:
        risks.append(f"估值溢價風險：本益比 {pe:.1f} 倍（PB {pb:.2f} 倍），若成長放緩易面臨估值修正")
    if pd.notnull(de) and de >= 80.0:
        risks.append(f"槓桿偏高：負債權益比達 {de:.1f}%（需留意利率與景氣循環衝擊）")
    if roe < 12.0:
        risks.append(f"資本回報偏低：ROE 僅 {roe:.1f}%，主要靠低估值或高現金流拉分，成長爆發力有限")
    if dt_r >= 40.0:
        risks.append(f"短線洗盤噪聲高：近 20 日均當沖率 {dt_r:.1f}%，不適合設過緊的短線停損")
    if rsi >= 72.0:
        risks.append(f"短線過熱：RSI 達 {rsi:.1f}，切忌追高，宜等回踩")
    if sec_count >= 4:
        risks.append(f"產業集中提醒：所屬「{r['sector']}」在清單中已佔 {sec_count} 檔，須留意板塊連動風險")
    if not risks:
        risks.append("目前無明顯基本面紅旗，惟需留意大盤系統性回撤風險")

    # Handoff Action
    if above_sma50 and rsi < 72.0:
        action = "可直接交由交易策略分批建倉（或純季換倉 B&H 持有）"
    elif above_sma50 and rsi >= 72.0:
        action = "多頭但短線過熱，建議等回踩均線再進場"
    else:
        action = "放入預備觀察清單，待交易策略確認站回 50 日季線或箱底企穩後再進場（若採純基本面 B&H 則可分批低接）"
    return opps, risks, action


def run_selector(
    universe: str,
    strategy: str,
    eval_mode: str,
    top_k: int,
    buffer_k: Optional[int],
    max_sector_weight: Optional[float],
    max_dt_ratio: Optional[float],
):
    db_path = f"data/{universe}/{universe}_2026.db"
    conn = sqlite3.connect(db_path)
    meta = pd.read_sql_query("SELECT ticker, name FROM universe_meta", conn)
    meta_map = dict(zip(meta["ticker"], meta["name"]))

    daily = pd.read_sql_query("""
        SELECT s.ticker, s.date, s.raw_close, s.adj_close, s.volume, s.dividends, s.is_fillable,
               f.sma_50, f.rsi_14,
               v.pe_ratio, v.pb_ratio, v.dividend_yield, v.roe_implied_pct,
               c.day_trading_ratio
        FROM stock_daily s
        LEFT JOIN daily_factors f ON s.ticker = f.ticker AND s.date = f.date
        LEFT JOIN daily_valuation v ON s.ticker = v.ticker AND s.date = v.date
        LEFT JOIN taiwan_chips_daily c ON s.ticker = c.ticker AND s.date = c.date
        ORDER BY s.ticker, s.date
    """, conn)
    qf = pd.read_sql_query("SELECT * FROM quarterly_fundamentals ORDER BY ticker, quarter_end", conn)
    conn.close()

    qf["pub_date"] = qf["quarter_end"].apply(pub_date_from_quarter_end)
    daily["adj_close"] = daily.groupby("ticker")["adj_close"].ffill()
    daily["raw_close"] = daily.groupby("ticker")["raw_close"].ffill()
    daily["dt_ma20"] = daily.groupby("ticker")["day_trading_ratio"].transform(lambda s: s.rolling(20, min_periods=5).mean().shift(1))

    adj_piv = daily.pivot(index="date", columns="ticker", values="adj_close").sort_index().ffill()
    raw_piv = daily.pivot(index="date", columns="ticker", values="raw_close").sort_index().ffill()
    div_piv = daily.pivot(index="date", columns="ticker", values="dividends").sort_index().fillna(0.0)
    by_date = {dt: g.set_index("ticker") for dt, g in daily.groupby("date")}
    all_dates = list(adj_piv.index)
    rebal_dates = [[d for d in all_dates if d >= cd][0] for cd in ["2026-01-02", "2026-04-01", "2026-05-16", "2026-08-15"]]

    def score_slice(as_of: str, allow_q3: bool = False) -> Tuple[pd.DataFrame, List[str]]:
        d_slice = by_date[as_of]
        excluded, valid_tickers = [], []
        for t in sorted(d_slice.index):
            dt_r = d_slice.at[t, "dt_ma20"]
            if max_dt_ratio is not None and pd.notnull(dt_r) and dt_r > max_dt_ratio:
                excluded.append(f"{t}({meta_map.get(t,t)} 當沖率={dt_r:.1f}%)")
                continue
            valid_tickers.append(t)

        avail = qf[(qf["revenue"].notnull()) & (qf["revenue"] > 0)].copy()
        if not allow_q3:
            avail = avail[avail["pub_date"] <= as_of]

        rows = []
        for t in valid_tickers:
            d = d_slice.loc[t]
            pe = float(d["pe_ratio"]) if pd.notnull(d["pe_ratio"]) else np.nan
            pb = float(d["pb_ratio"]) if pd.notnull(d["pb_ratio"]) else np.nan
            dy = float(d["dividend_yield"]) if pd.notnull(d["dividend_yield"]) else 0.0
            roe_imp = float(d["roe_implied_pct"]) if pd.notnull(d["roe_implied_pct"]) else np.nan

            g = avail[avail["ticker"] == t].sort_values("quarter_end")
            if not g.empty:
                t4 = g.tail(4)
                latest = g.iloc[-1]
                rev_s, ni_s, ocf_s, fcf_s = t4["revenue"].sum(), t4["net_income"].sum(), t4["ocf"].sum(), t4["fcf"].sum()
                nm = (ni_s / rev_s * 100.0) if rev_s > 0 else np.nan
                fm = (fcf_s / rev_s * 100.0) if rev_s > 0 else np.nan
                cc = (ocf_s / ni_s) if ni_s > 0 else (-1.0 if ocf_s <= 0 else 0.0)
                de = float(latest["debt_to_equity"]) if pd.notnull(latest["debt_to_equity"]) else np.nan
                r_roe = t4["roe_ttm_pct"].dropna()
                roe = float(r_roe.iloc[-1]) if len(r_roe) > 0 else roe_imp
            else:
                nm = fm = cc = de = np.nan
                roe = roe_imp

            rows.append({
                "ticker": t, "name": meta_map.get(t, t), "sector": TW50_SECTORS.get(t, "其他"),
                "roe_pct": roe, "net_margin": nm, "fcf_margin": fm, "cash_conv": cc,
                "debt_to_equity": de, "pe_ratio": pe, "pb_ratio": pb, "dividend_yield": dy,
                "ey": (100.0 / pe) if (pd.notnull(pe) and pe > 0) else 0.0,
                "bp": (1.0 / pb) if (pd.notnull(pb) and pb > 0) else 0.0,
                "close": float(d["raw_close"]), "sma50": float(d["sma_50"]) if pd.notnull(d["sma_50"]) else 0.0,
                "rsi_14": float(d["rsi_14"]) if pd.notnull(d["rsi_14"]) else 50.0,
                "dt_ma20": float(d["dt_ma20"]) if pd.notnull(d["dt_ma20"]) else 0.0,
            })

        snap = pd.DataFrame(rows).set_index("ticker")
        de_f = snap["debt_to_equity"].fillna(snap["debt_to_equity"].median())
        snap["score_z"] = (
            0.25 * zscore_clean(snap["roe_pct"])
            + 0.15 * zscore_clean(snap["net_margin"])
            + 0.15 * zscore_clean(snap["fcf_margin"])
            + 0.10 * zscore_clean(snap["cash_conv"].clip(-2, 4))
            + 0.10 * (-zscore_clean(de_f))
            + 0.10 * zscore_clean(snap["ey"])
            + 0.075 * zscore_clean(snap["bp"])
            + 0.075 * zscore_clean(snap["dividend_yield"])
        )
        # Convert Z-score to intuitive 0-100 score (percentile + z blend)
        pct_rank = snap["score_z"].rank(pct=True) * 100.0
        snap["score_100"] = np.clip(np.round(50.0 + snap["score_z"] * 22.0 + (pct_rank - 50.0) * 0.35, 1), 1.0, 99.0)
        return snap.sort_values("score_z", ascending=False), excluded

    def pick_stocks(snap: pd.DataFrame, prev_list: List[str]) -> List[str]:
        max_per_sec = max(1, int(np.floor(top_k * max_sector_weight))) if max_sector_weight is not None else top_k
        ranked = list(snap.index)
        sec_cnt: Dict[str, int] = {}
        chosen: List[str] = []

        if buffer_k is not None:
            for t in prev_list:
                if t in ranked[:buffer_k]:
                    sec = snap.at[t, "sector"]
                    if sec_cnt.get(sec, 0) < max_per_sec and len(chosen) < top_k:
                        chosen.append(t)
                        sec_cnt[sec] = sec_cnt.get(sec, 0) + 1

        for t in ranked:
            if len(chosen) >= top_k: break
            if t in chosen: continue
            sec = snap.at[t, "sector"]
            if sec_cnt.get(sec, 0) < max_per_sec:
                chosen.append(t)
                sec_cnt[sec] = sec_cnt.get(sec, 0) + 1
        return chosen

    # Stage 3: Pure B&H Rebalance Validation
    cash = INITIAL_CASH
    shares: Dict[str, float] = {}
    rebal_set = set(rebal_dates)
    eq_curve = []

    for dt in all_dates:
        for t, sh in shares.items():
            if sh > 0:
                div = div_piv.at[dt, t]
                if pd.notnull(div) and div > 0: cash += sh * float(div)

        if dt in rebal_set:
            snap, _ = score_slice(dt, allow_q3=False)
            chosen = pick_stocks(snap, [t for t, sh in shares.items() if sh > 0])
            tgt_w = {t: 1.0 / len(chosen) for t in chosen}

            pv = cash + sum(sh * float(raw_piv.at[dt, t]) for t, sh in shares.items() if sh > 0)
            for t in list(shares.keys()):
                sh = shares[t]
                if sh <= 0: continue
                px = float(raw_piv.at[dt, t])
                tw = tgt_w.get(t, 0.0)
                if tw == 0.0 or ((sh * px) / pv - tw) > 0.02:
                    sell_sh = sh if tw == 0.0 else max(0.0, min(sh, sh - (pv * tw) / px))
                    cash += sell_sh * (px * (1.0 - TW_SLIPPAGE)) * (1.0 - TW_COMMISSION - TW_TAX)
                    shares[t] -= sell_sh
                    if tw == 0.0 or shares[t] < 1e-6: shares.pop(t, None)

            pv = cash + sum(sh * float(raw_piv.at[dt, t]) for t, sh in shares.items() if sh > 0)
            plan, tot_need = {}, 0.0
            for t, tw in tgt_w.items():
                px = float(raw_piv.at[dt, t])
                need = pv * tw - shares.get(t, 0.0) * px
                if need > pv * 0.02:
                    plan[t] = (need, px)
                    tot_need += need * (1.0 + TW_SLIPPAGE + TW_COMMISSION)
            scale = min(1.0, (cash * 0.999) / tot_need) if tot_need > 0 else 0.0
            for t, (raw_alloc, px) in plan.items():
                exec_px = px * (1.0 + TW_SLIPPAGE)
                bsh = (raw_alloc * scale) / (exec_px * (1.0 + TW_COMMISSION))
                cost = bsh * exec_px * (1.0 + TW_COMMISSION)
                if bsh > 0 and cost <= cash + 1e-6:
                    cash -= cost
                    shares[t] = shares.get(t, 0.0) + bsh

        eq_curve.append((dt, cash + sum(sh * float(raw_piv.at[dt, t]) for t, sh in shares.items() if sh > 0)))

    eq_s = pd.Series(dict(eq_curve))
    bm_ew = adj_piv.div(adj_piv.iloc[0]).mean(axis=1) * INITIAL_CASH
    rets = eq_s.pct_change().dropna()
    tot_ret = (eq_s.iloc[-1] / eq_s.iloc[0] - 1.0) * 100.0
    bm_ret = (bm_ew.iloc[-1] / bm_ew.iloc[0] - 1.0) * 100.0
    sharpe = float(((rets - 0.015 / 252.0).mean() / (rets.std() + 1e-12)) * np.sqrt(252))
    mdd = float(((eq_s / eq_s.cummax()) - 1.0).min() * 100.0)

    # Stage 4: Latest Watchlist + Per-Stock Opportunity/Risk Report
    last_dt = all_dates[-1]
    latest_snap, latest_excl = score_slice(last_dt, allow_q3=True)
    latest_picks = pick_stocks(latest_snap, list(shares.keys()))
    sec_counts = latest_snap.loc[latest_picks, "sector"].value_counts().to_dict()

    out_dir = os.path.join("reports", f"selector_{universe}_{strategy}_{datetime.now().strftime('%Y%m%d')}")
    os.makedirs(out_dir, exist_ok=True)

    candidates = []
    md_lines = [
        f"# 預備交易清單選股研報 ({universe.upper()} | {strategy})",
        "",
        f"- **產生日期**：`{datetime.now().strftime('%Y-%m-%d %H:%M')}` ｜ **最新行情基準日**：`{last_dt}`",
        f"- **參數設定**：股票池=`{universe}`｜策略=`{strategy}`｜驗收=`{eval_mode}`｜檔數=`{top_k}`｜產業上限=`{max_sector_weight or '不限制'}`｜當沖率過濾=`{max_dt_ratio or '關閉'}`",
        f"- **歷史純 B&H 驗收**：累計報酬 **`{tot_ret:+.2f}%`** vs 同池等權基準 `{bm_ret:+.2f}%`（超額 Alpha **`{tot_ret-bm_ret:+.2f}%`**）｜夏普比率 **`{sharpe:.2f}`**｜最大回撤 **`{mdd:.2f}%`**｜可靠度：`WATCH_ONLY (<3年)`",
        f"- **產業分佈提醒**：`{sec_counts}`",
        "",
        "---",
        "",
        "## 一、預備交易清單總覽（0~100 綜合評分）",
        "",
        "| 排名 | 代碼 | 名稱 | 產業 | 綜合評分 | ROE% | PE | PB | 殖利率% | 淨利率% | FCF率% | 站上季線 |",
        "| :-: | :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |",
    ]

    for rank, t in enumerate(latest_picks, 1):
        r = latest_snap.loc[t]
        opps, risks, action = diagnose_stock_opp_risk(r, sec_counts.get(r["sector"], 1))
        above50 = bool(r["close"] >= r["sma50"])
        candidates.append({
            "rank": rank, "ticker": t, "name": r["name"], "sector": r["sector"],
            "score_100": float(r["score_100"]), "roe_pct": round(float(r["roe_pct"]), 1),
            "pe_ratio": round(float(r["pe_ratio"]), 1), "pb_ratio": round(float(r["pb_ratio"]), 2),
            "dividend_yield_pct": round(float(r["dividend_yield"]), 2),
            "net_margin_pct": round(float(r["net_margin"]), 1), "fcf_margin_pct": round(float(r["fcf_margin"]), 1),
            "above_sma50": above50, "opportunities": opps, "risks": risks, "handoff_action": action,
        })
        md_lines.append(
            f"| {rank} | `{t}` | {r['name']} | {r['sector']} | **{r['score_100']:.1f}** | {r['roe_pct']:.1f}% | "
            f"{r['pe_ratio']:.1f} | {r['pb_ratio']:.2f} | {r['dividend_yield']:.2f}% | {r['net_margin']:.1f}% | {r['fcf_margin']:.1f}% | {'✅' if above50 else '⏳'} |"
        )

    md_lines += ["", "---", "", "## 二、入選個股逐檔「機會、風險與交棒建議」報告", ""]
    for c in candidates:
        md_lines.append(f"### #{c['rank']} `{c['ticker']}` {c['name']}（{c['sector']}）— 綜合評分：{c['score_100']:.1f} / 100")
        md_lines.append(f"- **核心機會（為什麼入選）**：")
        for o in c["opportunities"]:
            md_lines.append(f"  - ✅ {o}")
        md_lines.append(f"- **主要風險（要小心什麼）**：")
        for rk in c["risks"]:
            md_lines.append(f"  - ⚠️ {rk}")
        md_lines.append(f"- **交棒交易策略建議**：{c['handoff_action']}")
        md_lines.append("")

    json_path = os.path.join(out_dir, "candidates.json")
    md_path = os.path.join(out_dir, "selector_report.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"as_of_date": last_dt, "validation": {"return_pct": round(tot_ret, 2), "bm_ew_pct": round(bm_ret, 2), "sharpe": round(sharpe, 2), "mdd_pct": round(mdd, 2)}, "candidates": candidates}, f, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"Validation (Pure B&H): Return={tot_ret:+.2f}% | BM={bm_ret:+.2f}% | Alpha={tot_ret-bm_ret:+.2f}% | Sharpe={sharpe:.2f} | MDD={mdd:.2f}%")
    print(f"Sector Breakdown: {sec_counts}")
    print(f"Saved Report -> {md_path}")
    print(f"Saved Watchlist JSON -> {json_path}\n")
    for c in candidates[:5]:
        print(f"#{c['rank']} {c['ticker']} {c['name']} ({c['sector']}) | 評分 {c['score_100']}/100")
        print(f"   機會: {' ; '.join(c['opportunities'][:2])}")
        print(f"   風險: {' ; '.join(c['risks'][:2])}")
        print(f"   交棒: {c['handoff_action']}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--universe", default="tw50")
    p.add_argument("--strategy", default="buffett_full")
    p.add_argument("--eval-mode", default="bh_rebalance")
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--buffer-k", type=int, default=None)
    p.add_argument("--max-sector-weight", type=float, default=None)
    p.add_argument("--max-dt-ratio", type=float, default=None)
    a = p.parse_args()
    run_selector(a.universe, a.strategy, a.eval_mode, a.top_k, a.buffer_k, a.max_sector_weight, a.max_dt_ratio)


if __name__ == "__main__":
    main()
