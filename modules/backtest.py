"""
modules/backtest.py
量化策略回測與多因子績效報告引擎 (QuantStats & Backtest Engine)
遵循 prompts/backtest.md 與 prompts/strategy/bollinger_strategy.md 規範。
"""
import argparse
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Tuple

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import quantstats as qs
from plotly.subplots import make_subplots


# 台股與美股預設交易成本
TW_FRICTION = {"commission": 0.000855, "tax": 0.003, "slippage": 0.0005}
US_FRICTION = {"commission": 0.0003, "tax": 0.0, "slippage": 0.0005}


def load_universe_data(db_path: str) -> Dict[str, pd.DataFrame]:
    """從 SQLite 資料庫讀取已預熱的日頻行情與衍生因子並依標的整理。"""
    conn = sqlite3.connect(db_path)
    query = """
        SELECT
            s.ticker, s.date, s.raw_open, s.raw_high, s.raw_low, s.raw_close,
            s.adj_close, s.volume, s.dividends, s.pct_change, s.is_fillable,
            f.sma_20, f.sma_50, f.sma_200, f.atr_14,
            f.boll_upper, f.boll_mid, f.boll_lower,
            f.rsi_14, f.macd_dif, f.macd_dea, f.macd_hist
        FROM stock_daily s
        JOIN daily_factors f ON s.ticker = f.ticker AND s.date = f.date
        ORDER BY s.ticker ASC, s.date ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    # 異常極值清洗與還原指標計算
    df["adj_close"] = df.groupby("ticker")["adj_close"].ffill()
    df["raw_close"] = df.groupby("ticker")["raw_close"].ffill()
    df["boll_bw"] = np.where(
        df["boll_mid"] > 0,
        (df["boll_upper"] - df["boll_lower"]) / df["boll_mid"],
        0.0,
    )

    return {ticker: g.reset_index(drop=True) for ticker, g in df.groupby("ticker")}


def classify_regime(df: pd.DataFrame) -> str:
    """依 bollinger_strategy.md 準則判定標的風格 (MOMENTUM vs CYCLICAL)。"""
    ret = df["adj_close"].pct_change().dropna()
    ann_vol = float(ret.std() * np.sqrt(252)) if len(ret) > 20 else 0.0
    valid_sma200 = df["sma_200"].dropna()
    if len(valid_sma200) > 0:
        above_200 = float((df.loc[valid_sma200.index, "adj_close"] > valid_sma200).mean())
    else:
        above_200 = 0.0
    return "MOMENTUM" if (ann_vol > 0.40 and above_200 > 0.60) else "CYCLICAL"


def simulate_bollinger_ticker(
    df: pd.DataFrame,
    ticker: str,
    model_key: str,
    fixed_cash: float,
    commission: float,
    tax: float,
    slippage: float,
    bw_min: float = 0.15,
    bw_lookback: int = 5,
    be_mfe_pct: float = 10.0,
    be_buffer: float = 1.015,
    trail_mfe_pct: float = 20.0,
    trail_atr_mult: float = 2.5,
) -> Tuple[List[dict], pd.Series]:
    """對單一標的執行指定布林變體回測，嚴格分離 Adj 訊號與 Raw 撮合。"""
    regime = classify_regime(df)
    effective_model = (
        ("combo_refined" if regime == "MOMENTUM" else "reversion")
        if model_key == "regime_adaptive"
        else model_key
    )

    trades: List[dict] = []
    daily_pnl = np.zeros(len(df), dtype=float)

    in_pos = False
    shares = 0.0
    entry_raw_price = 0.0
    entry_adj_price = 0.0
    entry_cost_total = 0.0
    entry_date = ""
    entry_idx = -1
    peak_adj_price = 0.0
    div_received = 0.0

    closes_adj = df["adj_close"].to_numpy()
    highs_raw = df["raw_high"].to_numpy()
    closes_raw = df["raw_close"].to_numpy()
    uppers = df["boll_upper"].to_numpy()
    mids = df["boll_mid"].to_numpy()
    lowers = df["boll_lower"].to_numpy()
    bws = df["boll_bw"].to_numpy()
    atrs = df["atr_14"].to_numpy()
    fillables = df["is_fillable"].to_numpy()
    divs = df["dividends"].fillna(0.0).to_numpy()
    dates = df["date"].to_numpy()

    for i in range(bw_lookback, len(df)):
        c_adj = closes_adj[i]
        c_raw = closes_raw[i]
        u, m, l = uppers[i], mids[i], lowers[i]
        bw = bws[i]
        bw_prev = bws[i - bw_lookback]
        atr = atrs[i] if np.isfinite(atrs[i]) and atrs[i] > 0 else c_adj * 0.02
        fillable = bool(fillables[i])

        if np.isnan(c_adj) or np.isnan(u) or np.isnan(m) or np.isnan(l) or c_raw <= 0:
            continue

        if in_pos:
            # 累計現金股利與每日市值損益
            if divs[i] > 0:
                div_received += shares * divs[i]
                daily_pnl[i] += shares * divs[i]
            daily_pnl[i] += shares * (c_raw - closes_raw[i - 1])

            if c_adj > peak_adj_price:
                peak_adj_price = c_adj
            mfe_pct = (peak_adj_price / entry_adj_price - 1.0) * 100.0

            should_exit = False
            exit_reason = ""
            if effective_model in ("baseline", "bw_expand"):
                if c_adj < m:
                    should_exit, exit_reason = True, "Below Mid Band"
            elif effective_model == "profit_lock":
                stop = max(m, entry_adj_price * be_buffer) if mfe_pct >= be_mfe_pct else m
                if c_adj < stop:
                    should_exit, exit_reason = True, "Profit Lock / Mid"
            elif effective_model == "atr_trail":
                stop = max(m, peak_adj_price - trail_atr_mult * atr) if mfe_pct >= trail_mfe_pct else m
                if c_adj < stop:
                    should_exit, exit_reason = True, "ATR Trail / Mid"
            elif effective_model == "combo_refined":
                if mfe_pct >= trail_mfe_pct:
                    stop = max(m, entry_adj_price * be_buffer, peak_adj_price - trail_atr_mult * atr)
                elif mfe_pct >= be_mfe_pct:
                    stop = max(m, entry_adj_price * be_buffer)
                else:
                    stop = m
                if c_adj < stop:
                    should_exit, exit_reason = True, "Combo Stop"
            elif effective_model == "reversion":
                if c_adj >= m:
                    should_exit, exit_reason = True, "Reversion Target Mid"

            # 最後一日強制平倉結算
            is_last_bar = i == len(df) - 1
            if (should_exit and fillable) or is_last_bar:
                exec_exit = c_raw * (1.0 - slippage)
                gross_proceeds = shares * exec_exit
                sell_fee = gross_proceeds * (commission + tax)
                net_proceeds = gross_proceeds - sell_fee
                net_pnl = net_proceeds + div_received - entry_cost_total
                ret_pct = (net_pnl / entry_cost_total) * 100.0
                hold_days = i - entry_idx

                trades.append({
                    "ticker": ticker,
                    "regime": regime,
                    "model_key": model_key,
                    "effective_engine": effective_model,
                    "entry_date": entry_date,
                    "exit_date": str(dates[i]),
                    "entry_price": round(entry_raw_price, 2),
                    "exit_price": round(exec_exit, 2),
                    "shares": round(shares, 4),
                    "hold_days": hold_days,
                    "net_pnl": round(net_pnl, 2),
                    "return_pct": round(ret_pct, 2),
                    "reason": "Mark-to-Market" if is_last_bar and not should_exit else exit_reason,
                })
                daily_pnl[i] -= (shares * c_raw - net_proceeds)
                in_pos = False
                shares = 0.0
                div_received = 0.0
        else:
            if not fillable:
                continue
            should_enter = False
            if effective_model in ("baseline", "profit_lock", "atr_trail"):
                should_enter = c_adj > u
            elif effective_model in ("bw_expand", "combo_refined"):
                should_enter = (c_adj > u) and (bw > bw_prev) and (bw >= bw_min)
            elif effective_model == "reversion":
                should_enter = (closes_adj[i - 1] <= lowers[i - 1]) and (c_adj > l)

            if should_enter and i < len(df) - 1:
                exec_entry = c_raw * (1.0 + slippage)
                shares = (fixed_cash * (1.0 - commission)) / exec_entry
                entry_cost_total = fixed_cash
                entry_raw_price = exec_entry
                entry_adj_price = c_adj
                entry_date = str(dates[i])
                entry_idx = i
                peak_adj_price = max(c_adj, highs_raw[i] * (c_adj / c_raw))
                div_received = 0.0
                in_pos = True

    return trades, pd.Series(daily_pnl, index=df["date"])


def compute_metrics(trades: List[dict], daily_pnl_series: pd.Series, portfolio_base: float, bh_series: pd.Series) -> dict:
    """計算 QuantStats 核心與布林策略標準審計指標。"""
    n_trades = len(trades)
    pnls = np.array([t["net_pnl"] for t in trades], dtype=float) if n_trades > 0 else np.array([0.0])
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]

    win_rate = (len(wins) / n_trades * 100.0) if n_trades > 0 else 0.0
    net_pnl = float(pnls.sum()) if n_trades > 0 else 0.0
    expectancy = (net_pnl / n_trades) if n_trades > 0 else 0.0
    avg_win = float(wins.mean()) if len(wins) > 0 else 0.0
    avg_loss = float(abs(losses.mean())) if len(losses) > 0 else 0.0
    payoff = (avg_win / avg_loss) if avg_loss > 0 else (99.9 if avg_win > 0 else 0.0)
    gross_profit = float(wins.sum()) if len(wins) > 0 else 0.0
    gross_loss = float(abs(losses.sum())) if len(losses) > 0 else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.9 if gross_profit > 0 else 0.0)
    chop_tax = float(sum(t["net_pnl"] for t in trades if t["hold_days"] <= 10))

    equity = portfolio_base + daily_pnl_series.cumsum()
    equity_dt = equity.copy()
    equity_dt.index = pd.to_datetime(equity_dt.index)
    bh_dt = bh_series.copy()
    bh_dt.index = pd.to_datetime(bh_dt.index)

    tot_ret = (equity_dt.iloc[-1] / portfolio_base - 1.0) * 100.0
    daily_ret = equity_dt.pct_change().dropna()
    mdd = float(qs.stats.max_drawdown(daily_ret) * 100.0) if len(daily_ret) > 1 else 0.0
    ann_vol = float(qs.stats.volatility(daily_ret, periods=252) * 100.0) if len(daily_ret) > 1 else 0.0
    sharpe = float(qs.stats.sharpe(daily_ret, rf=0.015, periods=252)) if ann_vol > 0 else 0.0
    sortino = float(qs.stats.sortino(daily_ret, rf=0.015, periods=252)) if len(daily_ret) > 1 else 0.0
    calmar = float(qs.stats.calmar(daily_ret, periods=252)) if mdd < 0 else 0.0

    bh_ret = (bh_dt.iloc[-1] / bh_dt.iloc[0] - 1.0) * 100.0
    bh_daily_ret = bh_dt.pct_change().dropna()
    bh_mdd = float(qs.stats.max_drawdown(bh_daily_ret) * 100.0) if len(bh_daily_ret) > 1 else 0.0

    return {
        "trades": n_trades,
        "win_rate": round(win_rate, 2),
        "net_pnl": round(net_pnl, 2),
        "total_return_pct": round(tot_ret, 2),
        "bh_return_pct": round(bh_ret, 2),
        "alpha_pct": round(tot_ret - bh_ret, 2),
        "expectancy": round(expectancy, 2),
        "payoff_ratio": round(payoff, 2),
        "profit_factor": round(profit_factor, 2),
        "strategy_mdd_pct": round(mdd, 2),
        "bh_mdd_pct": round(bh_mdd, 2),
        "ann_vol_pct": round(ann_vol, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "calmar": round(calmar, 2),
        "chop_tax_10d": round(chop_tax, 2),
        "final_equity": round(float(equity_dt.iloc[-1]), 2),
    }


def build_interactive_html_report(
    html_out: str,
    target: str,
    strategy: str,
    summary_df: pd.DataFrame,
    all_trades_df: pd.DataFrame,
    equity_curves: Dict[str, pd.Series],
    bh_curve: pd.Series,
    portfolio_base: float,
    start_date: str,
    end_date: str,
):
    """建構包含 KPI 總覽、完整關鍵績效表、多維圖表與可篩選成交流水的機構級暗色 HTML 研報。"""
    colors = ["#38BDF8", "#FCD34D", "#A78BFA", "#FB923C", "#2DD4BF", "#F472B6", "#00D084"]

    # Fig 1: 累計報酬率 % & 水下回撤 %
    fig_perf = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.07, row_heights=[0.62, 0.38],
        subplot_titles=("累計報酬率曲線 (Cumulative Return % vs B&H)", "水下回撤曲線 (Underwater Drawdown %)"),
    )
    bh_ret_curve = (bh_curve / bh_curve.iloc[0] - 1.0) * 100.0
    bh_dd_curve = (bh_curve - bh_curve.cummax()) / bh_curve.cummax() * 100.0
    fig_perf.add_trace(
        go.Scatter(x=bh_ret_curve.index, y=bh_ret_curve.values, name="TW50 B&H (等權重)",
                   line=dict(color="#94A3B8", width=2, dash="dash")),
        row=1, col=1,
    )
    fig_perf.add_trace(
        go.Scatter(x=bh_dd_curve.index, y=bh_dd_curve.values, name="TW50 B&H DD%",
                   line=dict(color="#94A3B8", width=1.4, dash="dash"), showlegend=False),
        row=2, col=1,
    )
    for idx, (mk, s) in enumerate(equity_curves.items()):
        eq = portfolio_base + s.cumsum()
        ret_pct = (eq / portfolio_base - 1.0) * 100.0
        dd_pct = (eq - eq.cummax()) / eq.cummax() * 100.0
        c = colors[idx % len(colors)]
        fig_perf.add_trace(go.Scatter(x=ret_pct.index, y=ret_pct.values, name=mk, line=dict(color=c, width=2)), row=1, col=1)
        fig_perf.add_trace(go.Scatter(x=dd_pct.index, y=dd_pct.values, name=f"{mk} DD%", line=dict(color=c, width=1.4), showlegend=False), row=2, col=1)

    fig_perf.update_layout(
        template="plotly_dark", paper_bgcolor="#181C25", plot_bgcolor="#14171F",
        height=640, hovermode="x unified", margin=dict(l=55, r=25, t=50, b=35),
        legend=dict(orientation="h", yanchor="bottom", y=1.03, xanchor="right", x=1),
    )

    # Fig 2: 月度報酬熱力圖 (Monthly Returns Heatmap)
    monthly_rows = {}
    bh_dt = bh_curve.copy()
    bh_dt.index = pd.to_datetime(bh_dt.index)
    bh_m = bh_dt.resample("ME").last().pct_change().fillna(bh_dt.resample("ME").last().iloc[0] / bh_dt.iloc[0] - 1.0) * 100.0
    monthly_rows["TW50 B&H"] = bh_m
    for mk, s in equity_curves.items():
        eq = portfolio_base + s.cumsum()
        eq.index = pd.to_datetime(eq.index)
        m_end = eq.resample("ME").last()
        m_ret = m_end.pct_change() * 100.0
        m_ret.iloc[0] = (m_end.iloc[0] / portfolio_base - 1.0) * 100.0
        monthly_rows[mk] = m_ret

    hm_df = pd.DataFrame(monthly_rows).T
    hm_cols = [d.strftime("%Y-%m") for d in hm_df.columns]
    fig_hm = go.Figure(data=go.Heatmap(
        z=np.round(hm_df.values, 2), x=hm_cols, y=list(hm_df.index),
        colorscale=[[0.0, "#991B1B"], [0.5, "#1E293B"], [1.0, "#059669"]],
        zmid=0.0, text=np.round(hm_df.values, 2), texttemplate="%{text:.2f}%",
        hovertemplate="策略: %{y}<br>月份: %{x}<br>報酬: %{z:.2f}%<extra></extra>",
    ))
    fig_hm.update_layout(
        template="plotly_dark", paper_bgcolor="#181C25", plot_bgcolor="#14171F",
        height=360, margin=dict(l=130, r=25, t=45, b=40),
        title=dict(text="月度報酬率熱力圖 (Monthly Returns Heatmap %)", font=dict(size=15)),
    )

    # Fig 3: 風險報酬效率散佈圖 & 滾動 30 日夏普比率
    fig_risk = make_subplots(
        rows=1, cols=2, horizontal_spacing=0.08,
        subplot_titles=("風險報酬效率象限 (年化波動% vs 累計報酬%)", "滾動 30 日年化夏普比率 (Rolling 30D Sharpe)"),
    )
    for idx, row in summary_df.iterrows():
        c = colors[idx % len(colors)]
        fig_risk.add_trace(go.Scatter(
            x=[row["ann_vol_pct"]], y=[row["total_return_pct"]],
            mode="markers+text", text=[row["model_key"]], textposition="top center",
            marker=dict(size=max(12, min(32, row["sharpe"] * 12)), color=c, line=dict(width=1.5, color="#F8FAFC")),
            name=row["model_key"], showlegend=False,
            hovertemplate=f"{row['model_key']}<br>波動: {row['ann_vol_pct']}%<br>報酬: {row['total_return_pct']}%<br>Sharpe: {row['sharpe']}<extra></extra>",
        ), row=1, col=1)

    for idx, (mk, s) in enumerate(equity_curves.items()):
        eq = portfolio_base + s.cumsum()
        dr = eq.pct_change().dropna()
        roll_sh = (dr.rolling(30).mean() * 252 - 0.015) / (dr.rolling(30).std() * np.sqrt(252) + 1e-9)
        fig_risk.add_trace(go.Scatter(
            x=roll_sh.index, y=roll_sh.values, name=mk,
            line=dict(color=colors[idx % len(colors)], width=1.6),
        ), row=1, col=2)

    fig_risk.update_layout(
        template="plotly_dark", paper_bgcolor="#181C25", plot_bgcolor="#14171F",
        height=400, margin=dict(l=55, r=25, t=50, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=-0.22, xanchor="center", x=0.5),
    )

    # Fig 4: 總淨利 vs 短線摩擦稅 & 單筆交易報酬率分佈
    fig_pnl = make_subplots(
        rows=1, cols=2, horizontal_spacing=0.08,
        subplot_titles=("總淨利 vs 短線摩擦稅 (<=10d, NTD)", "單筆交易報酬率分佈 (Trade Return % Histogram)"),
    )
    fig_pnl.add_trace(go.Bar(x=summary_df["model_key"], y=summary_df["net_pnl"], name="總淨利", marker_color="#00D084"), row=1, col=1)
    fig_pnl.add_trace(go.Bar(x=summary_df["model_key"], y=summary_df["chop_tax_10d"], name="短線摩擦稅 (<=10d)", marker_color="#FF4D4F"), row=1, col=1)
    for mk_focus, col_focus in [("baseline", "#38BDF8"), ("regime_adaptive", "#00D084")]:
        sub = all_trades_df[all_trades_df["model_key"] == mk_focus]
        if len(sub) > 0:
            fig_pnl.add_trace(go.Histogram(x=sub["return_pct"], name=f"{mk_focus} 單筆%", opacity=0.6, marker_color=col_focus, nbinsx=30), row=1, col=2)

    fig_pnl.update_layout(
        template="plotly_dark", paper_bgcolor="#181C25", plot_bgcolor="#14171F",
        height=390, barmode="group", margin=dict(l=55, r=25, t=50, b=45),
        legend=dict(orientation="h", yanchor="bottom", y=-0.22, xanchor="center", x=0.5),
    )

    best_ret = summary_df.loc[summary_df["total_return_pct"].idxmax()]
    best_sh = summary_df.loc[summary_df["sharpe"].idxmax()]
    best_mdd = summary_df.loc[summary_df["strategy_mdd_pct"].idxmax()]
    best_wr = summary_df.loc[summary_df["win_rate"].idxmax()]

    # KPI 表格 HTML
    kpi_rows_html = []
    for _, r in summary_df.iterrows():
        chop_cls = "pos" if r["chop_tax_10d"] >= 0 else "neg"
        kpi_rows_html.append(f"""
        <tr>
            <td><strong>{r['model_key']}</strong></td>
            <td>{int(r['trades'])}</td>
            <td>{r['win_rate']:.2f}%</td>
            <td class="pos">NT$ {r['net_pnl']:,.0f}</td>
            <td class="pos">+{r['total_return_pct']:.2f}%</td>
            <td>+{r['bh_return_pct']:.2f}%</td>
            <td>NT$ {r['expectancy']:,.0f}</td>
            <td>{r['payoff_ratio']:.2f}x</td>
            <td>{r['profit_factor']:.2f}</td>
            <td class="neg">{r['strategy_mdd_pct']:.2f}%</td>
            <td>{r['ann_vol_pct']:.2f}%</td>
            <td><strong>{r['sharpe']:.2f}</strong></td>
            <td>{r['sortino']:.2f}</td>
            <td>{r['calmar']:.2f}</td>
            <td class="{chop_cls}">NT$ {r['chop_tax_10d']:,.0f}</td>
            <td><a href="quantstats/quantstats_{r['model_key']}.html" target="_blank">Tearsheet ↗</a></td>
        </tr>""")

    # 成交流水表格 (依出場日倒序取最新 400 筆)
    recent_trades = all_trades_df.sort_values(by=["exit_date", "model_key"], ascending=[False, True]).head(400)
    trade_rows_html = []
    for _, t in recent_trades.iterrows():
        cls = "pos" if t["net_pnl"] >= 0 else "neg"
        trade_rows_html.append(
            f"<tr data-model='{t['model_key']}' data-ticker='{t['ticker']}'>"
            f"<td>{t['model_key']}</td><td><strong>{t['ticker']}</strong></td><td>{t['regime']}</td>"
            f"<td>{t['entry_date']}</td><td>{t['exit_date']}</td>"
            f"<td>{t['entry_price']:.2f}</td><td>{t['exit_price']:.2f}</td><td>{int(t['hold_days'])}d</td>"
            f"<td class='{cls}'>NT$ {t['net_pnl']:,.0f}</td><td class='{cls}'>{t['return_pct']:+.2f}%</td>"
            f"<td>{t['reason']}</td></tr>"
        )

    model_options = "".join(f"<option value='{mk}'>{mk}</option>" for mk in summary_df["model_key"])

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{target.upper()} {strategy.upper()} QuantStats 綜合回測研報</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  body {{ background: #14171F; color: #E2E8F0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 24px; }}
  .container {{ max-width: 1480px; margin: 0 auto; }}
  .header {{ display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 1px solid #2A3142; padding-bottom: 16px; margin-bottom: 20px; }}
  .header h1 {{ margin: 0; font-size: 24px; color: #F8FAFC; }}
  .header .sub {{ color: #94A3B8; font-size: 13px; margin-top: 6px; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; margin-bottom: 22px; }}
  .kpi-card {{ background: #181C25; border: 1px solid #262D3D; border-radius: 10px; padding: 14px 16px; }}
  .kpi-label {{ font-size: 12px; color: #94A3B8; margin-bottom: 6px; }}
  .kpi-val {{ font-size: 22px; font-weight: 700; color: #F8FAFC; }}
  .kpi-sub {{ font-size: 12px; color: #38BDF8; margin-top: 4px; }}
  .panel {{ background: #181C25; border: 1px solid #262D3D; border-radius: 10px; padding: 16px; margin-bottom: 20px; }}
  .panel h2 {{ margin: 0 0 12px 0; font-size: 16px; color: #F8FAFC; border-left: 3px solid #38BDF8; padding-left: 10px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 9px 10px; border-bottom: 1px solid #232A3B; text-align: right; white-space: nowrap; }}
  th {{ color: #94A3B8; font-weight: 600; background: #14171F; position: sticky; top: 0; }}
  th:first-child, td:first-child, th:nth-child(2), td:nth-child(2), td:last-child {{ text-align: left; }}
  tr:hover {{ background: #1E2433; }}
  .pos {{ color: #00D084; font-weight: 600; }}
  .neg {{ color: #FF4D4F; font-weight: 600; }}
  a {{ color: #38BDF8; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .controls {{ display: flex; gap: 12px; margin-bottom: 12px; align-items: center; }}
  select, input {{ background: #14171F; color: #E2E8F0; border: 1px solid #2E374B; border-radius: 6px; padding: 6px 10px; font-size: 13px; }}
  .table-scroll {{ max-height: 440px; overflow: auto; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>{target.upper()} × {strategy.upper()} 量化策略綜合回測研報</h1>
      <div class="sub">回測區間: {start_date} ~ {end_date} ｜ 50 檔台灣 50 成分股 ｜ 單筆固定開倉 NT$ 100,000 ｜ 滑點 0.05% + 手續費 0.0855% + 賣出證交稅 0.3%</div>
    </div>
    <div class="sub">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}</div>
  </div>

  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-label">最高累計報酬 ({best_ret['model_key']})</div>
      <div class="kpi-val pos">+{best_ret['total_return_pct']:.2f}%</div>
      <div class="kpi-sub">淨利 NT$ {best_ret['net_pnl']:,.0f}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">最高夏普比率 ({best_sh['model_key']})</div>
      <div class="kpi-val">{best_sh['sharpe']:.2f}</div>
      <div class="kpi-sub">Sortino {best_sh['sortino']:.2f} ｜ Calmar {best_sh['calmar']:.2f}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">最低最大回撤 ({best_mdd['model_key']})</div>
      <div class="kpi-val pos">{best_mdd['strategy_mdd_pct']:.2f}%</div>
      <div class="kpi-sub">B&H MDD {best_mdd['bh_mdd_pct']:.2f}% (少跌 {abs(best_mdd['bh_mdd_pct']) - abs(best_mdd['strategy_mdd_pct']):.1f}%)</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">最高交易勝率 ({best_wr['model_key']})</div>
      <div class="kpi-val" style="color:#FCD34D">{best_wr['win_rate']:.2f}%</div>
      <div class="kpi-sub">PF {best_wr['profit_factor']:.2f} ｜ {int(best_wr['trades'])} 筆交易</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">TW50 等權重 Buy & Hold</div>
      <div class="kpi-val">+{best_ret['bh_return_pct']:.2f}%</div>
      <div class="kpi-sub">基準 MDD {best_ret['bh_mdd_pct']:.2f}%</div>
    </div>
  </div>

  <div class="panel">
    <h2>Key Performance Metrics (全變體量化績效總表 + QuantStats Tear Sheets)</h2>
    <div style="overflow-x:auto;">
      <table>
        <thead>
          <tr>
            <th>變體 (Model)</th><th>交易數</th><th>勝率</th><th>總淨利</th><th>累計報酬</th><th>B&H 報酬</th>
            <th>單筆期望</th><th>盈虧比</th><th>PF</th><th>策略 MDD</th><th>年化波動</th>
            <th>Sharpe</th><th>Sortino</th><th>Calmar</th><th>短線摩擦稅(&lt;=10d)</th><th>QuantStats</th>
          </tr>
        </thead>
        <tbody>{''.join(kpi_rows_html)}</tbody>
      </table>
    </div>
  </div>

  <div class="panel">{fig_perf.to_html(full_html=False, include_plotlyjs=False)}</div>
  <div class="panel">{fig_hm.to_html(full_html=False, include_plotlyjs=False)}</div>
  <div class="panel">{fig_risk.to_html(full_html=False, include_plotlyjs=False)}</div>
  <div class="panel">{fig_pnl.to_html(full_html=False, include_plotlyjs=False)}</div>

  <div class="panel">
    <h2>成交流水明細表 (Trade Execution Logs — 最新 400 筆)</h2>
    <div class="controls">
      <label>變體篩選: <select id="fModel" onchange="filterTrades()"><option value="">全部變體</option>{model_options}</select></label>
      <label>代碼搜尋: <input id="fTicker" type="text" placeholder="如 2330.TW" oninput="filterTrades()"></label>
      <span id="tCount" style="color:#94A3B8;font-size:13px;"></span>
    </div>
    <div class="table-scroll">
      <table id="tradeTable">
        <thead>
          <tr><th>變體</th><th>代碼</th><th>風格</th><th>進場日</th><th>出場日</th><th>買進均價</th><th>賣出均價</th><th>持有天數</th><th>淨損益</th><th>報酬率</th><th>出場原因</th></tr>
        </thead>
        <tbody>{''.join(trade_rows_html)}</tbody>
      </table>
    </div>
  </div>
</div>
<script>
function filterTrades() {{
  const m = document.getElementById('fModel').value;
  const t = document.getElementById('fTicker').value.trim().toUpperCase();
  const rows = document.querySelectorAll('#tradeTable tbody tr');
  let shown = 0;
  rows.forEach(r => {{
    const okM = !m || r.dataset.model === m;
    const okT = !t || r.dataset.ticker.toUpperCase().includes(t);
    r.style.display = (okM && okT) ? '' : 'none';
    if (okM && okT) shown++;
  }});
  document.getElementById('tCount').textContent = `顯示 ${{shown}} / ${{rows.length}} 筆`;
}}
filterTrades();
</script>
</body>
</html>"""
    with open(html_out, "w", encoding="utf-8") as f:
        f.write(html_doc)


def save_outputs(
    output_dir: str,
    target: str,
    strategy: str,
    summary_df: pd.DataFrame,
    all_trades_df: pd.DataFrame,
    equity_curves: Dict[str, pd.Series],
    bh_curve: pd.Series,
    regime_map: Dict[str, str],
    portfolio_base: float,
    start_date: str,
    end_date: str,
):
    """持久化 SQLite、Plotly 暗色互動 HTML 研報與 Markdown 分析報告。"""
    os.makedirs(output_dir, exist_ok=True)
    db_out = os.path.join(output_dir, "backtest_result.db")
    html_out = os.path.join(output_dir, f"{target}_{strategy}_QuantStats_Report.html")
    md_out = os.path.join(output_dir, "backtest_report.md")

    # 1. SQLite 持久化
    conn = sqlite3.connect(db_out)
    summary_db = summary_df.copy()
    summary_db["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary_db.to_sql("backtest_summary", conn, if_exists="replace", index=False)
    all_trades_df.to_sql("backtest_trades", conn, if_exists="replace", index=False)

    eq_rows = []
    for mk, s in equity_curves.items():
        eq = portfolio_base + s.cumsum()
        strat_pct = eq.pct_change().fillna(0.0) * 100.0
        bh_pct = bh_curve.pct_change().fillna(0.0) * 100.0
        for dt, nav, sp, bp, bhv in zip(eq.index, eq.values, strat_pct.values, bh_pct.values, bh_curve.values):
            eq_rows.append({
                "model_key": mk,
                "date": dt,
                "equity": round(float(nav), 2),
                "benchmark_nav": round(float(bhv), 2),
                "strategy_daily_pct": round(float(sp), 4),
                "benchmark_daily_pct": round(float(bp), 4),
            })
    pd.DataFrame(eq_rows).to_sql("backtest_equity_curve", conn, if_exists="replace", index=False)
    conn.close()

    # 2. Plotly 互動式暗色綜合研報
    build_interactive_html_report(
        html_out, target, strategy, summary_df, all_trades_df,
        equity_curves, bh_curve, portfolio_base, start_date, end_date,
    )

    # 2.5 QuantStats 官方 Tear Sheet HTML (逐變體產出於 quantstats/ 子目錄)
    qs_dir = os.path.join(output_dir, "quantstats")
    os.makedirs(qs_dir, exist_ok=True)
    bh_dt = bh_curve.copy()
    bh_dt.index = pd.to_datetime(bh_dt.index)
    bh_ret_series = bh_dt.pct_change().fillna(0.0)
    bh_ret_series.name = f"{target.upper()} B&H"

    qs_files = []
    for mk, s in equity_curves.items():
        eq = portfolio_base + s.cumsum()
        eq.index = pd.to_datetime(eq.index)
        strat_ret = eq.pct_change().fillna(0.0)
        strat_ret.name = f"{strategy.upper()} ({mk})"
        qs_path = os.path.join(qs_dir, f"quantstats_{mk}.html")
        qs.reports.html(
            strat_ret,
            benchmark=bh_ret_series,
            rf=0.015,
            title=f"{target.upper()} {strategy.upper()} - {mk} QuantStats Tearsheet",
            output=qs_path,
        )
        qs_files.append((mk, qs_path))

    # 3. Markdown 報告
    momentum_tickers = sorted([k for k, v in regime_map.items() if v == "MOMENTUM"])
    cyclical_tickers = sorted([k for k, v in regime_map.items() if v == "CYCLICAL"])
    md_lines = [
        f"# {target.upper()} {strategy.upper()} 策略回測報告",
        "",
        f"- **測試區間**：`{start_date}` 至 `{end_date}`（50 檔台灣 50 成分股，雙軌還原算指標 / 未復權撮合）",
        f"- **交易摩擦**：單筆開倉 `NT$ 100,000`｜滑點 `0.05%`｜手續費 `0.0855%`｜賣出證交稅 `0.3%`",
        f"- **風格分類 (`regime_adaptive`)**：`MOMENTUM` ({len(momentum_tickers)} 檔) vs `CYCLICAL` ({len(cyclical_tickers)} 檔)",
        "",
        "## 核心績效對比總表",
        "",
        summary_df.to_markdown(index=False),
        "",
        "## QuantStats 官方 Tear Sheet 報告",
        *[f"- `{mk}`: `quantstats/quantstats_{mk}.html`" for mk, _ in qs_files],
        "",
        "## `regime_adaptive` 風格歸類明細",
        f"- **MOMENTUM (`combo_refined`)**: {', '.join(momentum_tickers) if momentum_tickers else '無'}",
        f"- **CYCLICAL (`reversion`)**: {', '.join(cyclical_tickers)}",
        "",
    ]
    with open(md_out, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    return db_out, html_out, md_out, qs_files


def main():
    parser = argparse.ArgumentParser(description="量化策略回測引擎")
    parser.add_argument("--target", default="tw50")
    parser.add_argument("--strategy", default="bollinger")
    parser.add_argument("--model", default="compare")
    parser.add_argument("--fixed-cash", type=float, default=100000.0)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    db_path = f"data/{args.target}/{args.target}_2026.db"
    universe = load_universe_data(db_path)
    tickers = sorted(universe.keys())

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    output_dir = args.output_dir or f"trades/{args.strategy}_{ts}_{args.target}"

    variants = (
        ["baseline", "bw_expand", "profit_lock", "atr_trail", "combo_refined", "reversion", "regime_adaptive"]
        if args.model == "compare"
        else [args.model]
    )

    all_dates = sorted(set().union(*[set(df["date"]) for df in universe.values()]))
    start_date, end_date = all_dates[0], all_dates[-1]
    portfolio_base = args.fixed_cash * len(tickers)

    # 等權重 Buy & Hold 基準
    bh_daily = pd.Series(0.0, index=all_dates)
    for t in tickers:
        df_t = universe[t].set_index("date")["adj_close"].reindex(all_dates).ffill().bfill()
        bh_daily += args.fixed_cash * (df_t / df_t.iloc[0])

    regime_map = {t: classify_regime(universe[t]) for t in tickers}
    summary_rows = []
    all_trades = []
    equity_curves = {}

    for mk in variants:
        variant_trades = []
        agg_pnl = pd.Series(0.0, index=all_dates)
        for t in tickers:
            tr, pnl_s = simulate_bollinger_ticker(
                universe[t], t, mk, args.fixed_cash,
                TW_FRICTION["commission"], TW_FRICTION["tax"], TW_FRICTION["slippage"],
            )
            variant_trades.extend(tr)
            agg_pnl = agg_pnl.add(pnl_s.reindex(all_dates).fillna(0.0), fill_value=0.0)

        m = compute_metrics(variant_trades, agg_pnl, portfolio_base, bh_daily)
        summary_rows.append({"model_key": mk, **m})
        all_trades.extend(variant_trades)
        equity_curves[mk] = agg_pnl

    summary_df = pd.DataFrame(summary_rows)
    all_trades_df = pd.DataFrame(all_trades)
    db_out, html_out, md_out, qs_files = save_outputs(
        output_dir, args.target, args.strategy, summary_df, all_trades_df,
        equity_curves, bh_daily, regime_map, portfolio_base, start_date, end_date,
    )

    print(f"OUTPUT_DIR={output_dir}")
    print(f"DB={db_out}")
    print(f"HTML={html_out}")
    print(f"MD={md_out}")
    print(f"QUANTSTATS_COUNT={len(qs_files)}")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
