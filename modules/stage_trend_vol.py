"""6-State (Trend x Volatility) human-stage auto-draft refiner & interactive viewer."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import talib

STATE_ZH_MAP = {
    "UP_LOW_VOL": "低波慢牛",
    "UP_HIGH_VOL": "高波急漲",
    "DOWN_LOW_VOL": "低波陰跌",
    "DOWN_HIGH_VOL": "高波恐慌",
    "CHOP_LOW_VOL": "低波窄震",
    "CHOP_HIGH_VOL": "高波寬震",
}

STATE_COLORS = {
    "UP_LOW_VOL": "rgba(34, 197, 94, 0.14)",
    "UP_HIGH_VOL": "rgba(16, 185, 129, 0.24)",
    "DOWN_LOW_VOL": "rgba(249, 115, 22, 0.14)",
    "DOWN_HIGH_VOL": "rgba(239, 68, 68, 0.24)",
    "CHOP_LOW_VOL": "rgba(148, 163, 184, 0.12)",
    "CHOP_HIGH_VOL": "rgba(168, 85, 247, 0.18)",
}


def compute_volatility_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Compute HV20%, NATR20%, and RVOL20 using price & volume only."""
    out = df.copy().sort_values("date").reset_index(drop=True)
    close = out["adj_close"].to_numpy(dtype=np.float64)
    high = out["raw_high"].to_numpy(dtype=np.float64)
    low = out["raw_low"].to_numpy(dtype=np.float64)
    raw_close = out["raw_close"].to_numpy(dtype=np.float64)
    vol = out["volume"].to_numpy(dtype=np.float64)

    log_ret = np.log(np.where(close > 0, close, np.nan))
    log_ret_diff = pd.Series(log_ret).diff()
    out["hv20"] = (log_ret_diff.rolling(20, min_periods=10).std() * np.sqrt(252.0) * 100.0).bfill()

    atr20 = talib.ATR(high, low, raw_close, timeperiod=20)
    natr20 = np.where(raw_close > 0, (atr20 / raw_close) * 100.0, np.nan)
    out["natr20"] = pd.Series(natr20).bfill()

    vol_ma20 = pd.Series(vol).rolling(20, min_periods=5).mean()
    out["rvol20"] = np.where(vol_ma20 > 0, vol / vol_ma20, 1.0)
    return out


def zigzag_pivots(closes: np.ndarray, threshold: float = 0.15) -> list[int]:
    """Extract 15% ZigZag pivot indices from a close price series."""
    n = len(closes)
    if n == 0:
        return []
    if n < 3:
        return [0, n - 1] if n > 1 else [0]

    pivots = [0]
    last_pivot_idx = 0
    last_pivot_price = closes[0]
    direction = 0  # 1 = up leg, -1 = down leg

    extreme_idx = 0
    extreme_price = closes[0]

    for i in range(1, n):
        p = closes[i]
        if direction == 0:
            if p >= last_pivot_price * (1.0 + threshold):
                direction = 1
                extreme_idx, extreme_price = i, p
            elif p <= last_pivot_price * (1.0 - threshold):
                direction = -1
                extreme_idx, extreme_price = i, p
        elif direction == 1:
            if p >= extreme_price:
                extreme_idx, extreme_price = i, p
            elif p <= extreme_price * (1.0 - threshold):
                pivots.append(extreme_idx)
                last_pivot_idx, last_pivot_price = extreme_idx, extreme_price
                direction = -1
                extreme_idx, extreme_price = i, p
        else:
            if p <= extreme_price:
                extreme_idx, extreme_price = i, p
            elif p >= extreme_price * (1.0 + threshold):
                pivots.append(extreme_idx)
                last_pivot_idx, last_pivot_price = extreme_idx, extreme_price
                direction = 1
                extreme_idx, extreme_price = i, p

    if pivots[-1] != n - 1:
        pivots.append(n - 1)
    return sorted(set(pivots))


def _classify_trend(ret_pct: float) -> str:
    if ret_pct >= 14.0:
        return "UP"
    if ret_pct <= -14.0:
        return "DOWN"
    return "CHOP"


def _segment_metrics(df: pd.DataFrame, s_idx: int, e_idx: int, median_hv20: float) -> dict[str, Any]:
    sub = df.iloc[s_idx : e_idx + 1]
    start_close = float(sub["raw_close"].iloc[0])
    end_close = float(sub["raw_close"].iloc[-1])
    ret_pct = ((end_close / start_close) - 1.0) * 100.0 if start_close > 0 else 0.0

    cum_max = sub["adj_close"].cummax()
    dd = ((sub["adj_close"] - cum_max) / cum_max) * 100.0
    max_dd = float(dd.min()) if not dd.empty else 0.0

    avg_hv20 = float(sub["hv20"].mean())
    avg_natr20 = float(sub["natr20"].mean())
    avg_rvol = float(sub["rvol20"].mean())
    vol_ratio = (avg_hv20 / median_hv20) if median_hv20 > 0 else 1.0

    trend = _classify_trend(ret_pct)
    vol_regime = "HIGH_VOL" if vol_ratio >= 1.0 else "LOW_VOL"
    state = f"{trend}_{vol_regime}"

    return {
        "s_idx": s_idx,
        "e_idx": e_idx,
        "trend": trend,
        "vol_regime": vol_regime,
        "state": state,
        "state_zh": STATE_ZH_MAP[state],
        "start_date": str(sub["date"].iloc[0]),
        "end_date": str(sub["date"].iloc[-1]),
        "trading_days": int(len(sub)),
        "start_close": round(start_close, 2),
        "end_close": round(end_close, 2),
        "return_pct": round(ret_pct, 2),
        "max_dd_pct": round(max_dd, 2),
        "avg_rvol": round(avg_rvol, 2),
        "avg_hv20": round(avg_hv20, 2),
        "avg_natr20": round(avg_natr20, 2),
        "vol_ratio": round(vol_ratio, 3),
    }


def build_stages_for_ticker(symbol: str, df_raw: pd.DataFrame) -> tuple[list[dict[str, Any]], pd.DataFrame, float]:
    """Run 15% ZigZag + length constraints + HV20 median ratio to produce 6-state stages."""
    df = compute_volatility_metrics(df_raw)
    n = len(df)
    if n == 0:
        return [], df, 0.0

    median_hv20 = float(df["hv20"].median())
    pivots = zigzag_pivots(df["adj_close"].to_numpy(dtype=np.float64), threshold=0.15)

    # Initial raw intervals [s_idx, e_idx]
    intervals: list[tuple[int, int]] = []
    if len(pivots) < 2:
        intervals = [(0, n - 1)]
    else:
        for i in range(len(pivots) - 1):
            s = pivots[i] if i == 0 else pivots[i] + 1
            e = pivots[i + 1]
            if s <= e:
                intervals.append((s, e))

    # Enforce length constraints: intermediate >= 30 days, final >= 11 days
    changed = True
    while changed and len(intervals) > 1:
        changed = False
        new_intervals: list[tuple[int, int]] = []
        i = 0
        while i < len(intervals):
            s, e = intervals[i]
            length = e - s + 1
            is_last = (i == len(intervals) - 1)
            min_len = 11 if is_last else 30

            if length < min_len:
                changed = True
                if is_last and new_intervals:
                    ps, _ = new_intervals.pop()
                    new_intervals.append((ps, e))
                elif i + 1 < len(intervals):
                    _, ne = intervals[i + 1]
                    new_intervals.append((s, ne))
                    i += 2
                    continue
                elif new_intervals:
                    ps, _ = new_intervals.pop()
                    new_intervals.append((ps, e))
                else:
                    new_intervals.append((s, e))
            else:
                new_intervals.append((s, e))
            i += 1
        intervals = new_intervals

        # Merge adjacent same-trend segments
        merged: list[tuple[int, int]] = []
        for s, e in intervals:
            m_curr = _segment_metrics(df, s, e, median_hv20)
            if merged:
                ps, pe = merged[-1]
                m_prev = _segment_metrics(df, ps, pe, median_hv20)
                if m_prev["trend"] == m_curr["trend"]:
                    merged[-1] = (ps, e)
                    changed = True
                    continue
            merged.append((s, e))
        intervals = merged

    stages: list[dict[str, Any]] = []
    for idx, (s, e) in enumerate(intervals, start=1):
        m = _segment_metrics(df, s, e, median_hv20)
        stages.append({
            "symbol": symbol,
            "segment_id": idx,
            "state": m["state"],
            "trend": m["trend"],
            "vol_regime": m["vol_regime"],
            "state_zh": m["state_zh"],
            "start_date": m["start_date"],
            "end_date": m["end_date"],
            "trading_days": m["trading_days"],
            "start_close": m["start_close"],
            "end_close": m["end_close"],
            "return_pct": m["return_pct"],
            "max_dd_pct": m["max_dd_pct"],
            "avg_rvol": m["avg_rvol"],
            "avg_hv20": m["avg_hv20"],
            "avg_natr20": m["avg_natr20"],
            "vol_ratio": m["vol_ratio"],
            "source": "auto_draft",
            "note": "",
        })
    return stages, df, round(median_hv20, 2)


def _build_human_vol_viewer(
    target_slug: str,
    year: int,
    viewer_payload: dict[str, Any],
    out_path: Path,
) -> None:
    """Build 3-panel interactive HTML viewer (Candlestick+6-color bg, Volume, HV20+median)."""
    data_json = json.dumps(viewer_payload, ensure_ascii=False)
    tickers = list(viewer_payload["stocks"].keys())
    default_t = tickers[0] if tickers else ""

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{target_slug.upper()} ({year}) 六階段趨勢×波動率人工標註工作台</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  :root {{ --bg:#0b0f17; --card:#131a26; --border:#232d3f; --text:#e2e8f0; --muted:#94a3b8; --accent:#38bdf8; }}
  body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--text); }}
  header {{ display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; padding:14px 22px; background:var(--card); border-bottom:1px solid var(--border); gap:10px; }}
  select, input, button {{ background:#0f1623; color:var(--text); border:1px solid var(--border); border-radius:6px; padding:6px 10px; font-size:13px; }}
  button {{ cursor:pointer; }} button:hover {{ border-color:var(--accent); color:var(--accent); }}
  .container {{ padding:16px 22px; max-width:1680px; margin:0 auto; }}
  .chart-box {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:10px; margin-bottom:14px; }}
  .table-wrap {{ overflow:auto; border:1px solid var(--border); border-radius:8px; background:var(--card); }}
  table {{ width:100%; border-collapse:collapse; font-size:12px; white-space:nowrap; }}
  th, td {{ padding:7px 10px; border-bottom:1px solid var(--border); text-align:right; }}
  th {{ background:#172030; color:var(--muted); }}
  td.left, th.left {{ text-align:left; }}
</style>
</head>
<body>
<header>
  <div style="font-size:17px;font-weight:700;">🎛️ {target_slug.upper()} ({year}) 趨勢 × 波動率六階段標註工作台</div>
  <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
    <label style="font-size:13px;color:var(--muted)">標的：</label>
    <select id="selTicker"></select>
    <span id="medianBadge" style="font-size:12px;color:var(--accent);"></span>
    <button onclick="exportCSV()">⬇️ 匯出修正後 CSV</button>
  </div>
</header>
<div class="container">
  <div class="chart-box"><div id="mainChart" style="height:760px;"></div></div>
  <div class="table-wrap"><table id="stageTable"></table></div>
</div>
<script>
const PAYLOAD = {data_json};
const STATE_COLORS = {json.dumps(STATE_COLORS)};
const STATE_ZH = {json.dumps(STATE_ZH_MAP, ensure_ascii=False)};
let cur = "{default_t}";

function init() {{
  const sel = document.getElementById("selTicker");
  Object.keys(PAYLOAD.stocks).forEach(t => {{
    const o = document.createElement("option");
    o.value = t;
    const nm = PAYLOAD.stocks[t].name;
    o.textContent = nm && nm !== t ? `${{t}} (${{nm}})` : t;
    sel.appendChild(o);
  }});
  sel.value = cur;
  sel.onchange = () => {{ cur = sel.value; render(); }};
  render();
}}

function render() {{
  const s = PAYLOAD.stocks[cur];
  if (!s) return;
  document.getElementById("medianBadge").textContent = `歷史中位 HV20: ${{s.median_hv20}}%`;
  const d = s.daily;
  const dates = d.map(r => r.date);

  const shapes = s.stages.map(st => ({{
    type: "rect", xref: "x", yref: "paper",
    x0: st.start_date, x1: st.end_date, y0: 0, y1: 1,
    fillcolor: STATE_COLORS[st.state] || "rgba(148,163,184,0.1)",
    line: {{ width: 0 }}, layer: "below"
  }}));
  shapes.push({{
    type: "line", xref: "paper", yref: "y3",
    x0: 0, x1: 1, y0: s.median_hv20, y1: s.median_hv20,
    line: {{ color: "#f59e0b", width: 1.5, dash: "dash" }}
  }});

  const annotations = s.stages.map(st => ({{
    x: st.start_date, y: 0.98, xref: "x", yref: "paper",
    text: `${{st.segment_id}}. ${{st.state_zh}} (${{st.return_pct>=0?'+':''}}${{st.return_pct}}%)`,
    showarrow: false, xanchor: "left", font: {{ size: 10, color: "#e2e8f0" }},
    bgcolor: "rgba(15,22,35,0.75)"
  }}));

  Plotly.newPlot("mainChart", [
    {{ x: dates, open: d.map(r=>r.raw_open), high: d.map(r=>r.raw_high), low: d.map(r=>r.raw_low), close: d.map(r=>r.raw_close),
       type: "candlestick", name: cur, xaxis: "x", yaxis: "y",
       increasing: {{line:{{color:"#ef4444"}}}}, decreasing: {{line:{{color:"#22c55e"}}}} }},
    {{ x: dates, y: d.map(r=>r.volume), type: "bar", name: "Volume", xaxis: "x", yaxis: "y2", marker: {{color:"#475569"}} }},
    {{ x: dates, y: d.map(r=>r.hv20), type: "scatter", mode: "lines", name: "HV20 %", xaxis: "x", yaxis: "y3", line: {{color:"#38bdf8", width:1.6}} }}
  ], {{
    title: `${{cur}} (${{s.name}}) 三聯圖：K 線六色背景 / 成交量 / HV20% 曲線`,
    paper_bgcolor: "#131a26", plot_bgcolor: "#0f1623", font: {{ color: "#e2e8f0" }},
    grid: {{ rows: 3, columns: 1, pattern: "independent", roworder: "top to bottom" }},
    xaxis: {{ rangeslider: {{ visible: false }}, matches: "x", gridcolor: "#232d3f" }},
    yaxis: {{ domain: [0.46, 1.0], title: "Price", gridcolor: "#232d3f" }},
    yaxis2: {{ domain: [0.24, 0.42], title: "Volume", gridcolor: "#232d3f" }},
    yaxis3: {{ domain: [0.0, 0.20], title: "HV20%", gridcolor: "#232d3f" }},
    shapes, annotations, hovermode: "x unified"
  }}, {{ responsive: true }});

  let html = `<thead><tr>
    <th>#</th><th class="left">狀態</th><th class="left">中文</th><th>起日</th><th>迄日</th>
    <th>交易日</th><th>起收</th><th>迄收</th><th>漲跌%</th><th>最大回撤%</th>
    <th>RVOL</th><th>均HV20%</th><th>均NATR20%</th><th>VolRatio</th><th class="left">來源</th><th class="left">備註</th>
  </tr></thead><tbody>`;
  s.stages.forEach((st, idx) => {{
    const opts = Object.keys(STATE_ZH).map(k => `<option value="${{k}}" ${{k===st.state?'selected':''}}>${{k}}</option>`).join("");
    html += `<tr>
      <td>${{st.segment_id}}</td>
      <td class="left"><select onchange="updateState(${{idx}}, this.value)">${{opts}}</select></td>
      <td class="left">${{st.state_zh}}</td>
      <td>${{st.start_date}}</td><td>${{st.end_date}}</td><td>${{st.trading_days}}</td>
      <td>${{st.start_close}}</td><td>${{st.end_close}}</td>
      <td style="color:${{st.return_pct>=0?'#22c55e':'#ef4444'}}">${{st.return_pct}}%</td>
      <td>${{st.max_dd_pct}}%</td><td>${{st.avg_rvol}}</td><td>${{st.avg_hv20}}</td>
      <td>${{st.avg_natr20}}</td><td>${{st.vol_ratio}}</td>
      <td class="left">${{st.source}}</td>
      <td class="left"><input value="${{st.note||''}}" onchange="updateNote(${{idx}}, this.value)" placeholder="備註..." style="width:140px;"/></td>
    </tr>`;
  }});
  document.getElementById("stageTable").innerHTML = html + "</tbody>";
}}

function updateState(idx, val) {{
  const st = PAYLOAD.stocks[cur].stages[idx];
  st.state = val;
  const parts = val.split("_");
  st.trend = parts[0];
  st.vol_regime = parts.slice(1).join("_");
  st.state_zh = STATE_ZH[val] || val;
  st.source = "human";
  render();
}}

function updateNote(idx, val) {{
  const st = PAYLOAD.stocks[cur].stages[idx];
  st.note = val;
  st.source = "human";
}}

function exportCSV() {{
  const rows = [];
  Object.values(PAYLOAD.stocks).forEach(s => rows.push(...s.stages));
  if (!rows.length) return;
  const cols = Object.keys(rows[0]);
  const csv = [cols.join(","), ...rows.map(r => cols.map(c => JSON.stringify(r[c] ?? "")).join(","))].join("\\n");
  const blob = new Blob([csv], {{ type: "text/csv;charset=utf-8;" }});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "{target_slug}_{year}_trend_vol_stages_human.csv";
  a.click();
}}
init();
</script>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")


def refine_trend_vol(target: str, year: int, data_dir: str | None = None) -> dict[str, Any]:
    """Read `data/{target}/<target>_<year>.db`, compute 6-state stages, and save refined outputs."""
    slug = target.strip().lower()
    base_dir = Path(data_dir) if data_dir else Path("data") / slug
    db_path = base_dir / f"{slug}_{year}.db"
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        daily_all = pd.read_sql_query("SELECT * FROM stock_daily ORDER BY ticker, date", conn)
        name_map: dict[str, str] = {}
        try:
            meta_df = pd.read_sql_query("SELECT ticker, name FROM universe_meta", conn)
            name_map = dict(zip(meta_df["ticker"], meta_df["name"]))
        except Exception:
            pass
    finally:
        conn.close()

    all_stages: list[dict[str, Any]] = []
    viewer_stocks: dict[str, Any] = {}

    for ticker, grp in daily_all.groupby("ticker", sort=False):
        stages, df_vol, med_hv20 = build_stages_for_ticker(ticker, grp)
        all_stages.extend(stages)
        viewer_stocks[ticker] = {
            "name": name_map.get(ticker, ticker),
            "median_hv20": med_hv20,
            "stages": stages,
            "daily": df_vol[["date", "raw_open", "raw_high", "raw_low", "raw_close", "volume", "hv20"]].round(2).to_dict(orient="records"),
        }

    stages_df = pd.DataFrame(all_stages)
    conn = sqlite3.connect(db_path)
    try:
        stages_df.to_sql("trend_vol_stages", conn, index=False, if_exists="replace")
    finally:
        conn.close()

    csv_path = base_dir / f"{slug}_{year}_trend_vol_stages.csv"
    stages_df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    viewer_path = base_dir / f"{slug}_{year}_trend_vol_viewer.html"
    _build_human_vol_viewer(slug, year, {"stocks": viewer_stocks}, viewer_path)

    # Summary Markdown report
    state_counts = stages_df["state"].value_counts().to_dict()
    latest_stages = stages_df.sort_values(["symbol", "segment_id"]).groupby("symbol").tail(1)
    latest_counts = latest_stages["state"].value_counts().to_dict()

    lines = [
        f"# {slug.upper()} ({year}) 趨勢 × 波動率六階段切分總覽報告",
        "",
        f"- **方法論**：15% ZigZag 波段結構 + 個股自身中位 `HV20%` 基準 + 階段長度約束（歷史段 $\\ge 30$ 日、末段 $> 10$ 日）",
        f"- **標的家數**：{stages_df['symbol'].nunique()} 檔",
        f"- **總切分段數**：{len(stages_df)} 段",
        "",
        "## 📊 全年歷史分段分佈",
        "",
        "| 狀態代碼 | 中文名稱 | 分段數 | 佔比% | 平均區間報酬% | 平均最大回撤% |",
        "|:---|:---|---:|---:|---:|---:|",
    ]
    for st, cnt in state_counts.items():
        sub = stages_df[stages_df["state"] == st]
        lines.append(
            f"| `{st}` | {STATE_ZH_MAP[st]} | {cnt} | {cnt/len(stages_df)*100:.1f}% | "
            f"{sub['return_pct'].mean():+.2f}% | {sub['max_dd_pct'].mean():.2f}% |"
        )
    lines.extend([
        "",
        "## 🧭 截至最新交易日成分股所處階段統計",
        "",
        "| 當前狀態 | 中文名稱 | 檔數 | 代表標的 (前 8 檔) |",
        "|:---|:---|---:|:---|",
    ])
    for st, cnt in latest_counts.items():
        syms = latest_stages[latest_stages["state"] == st]["symbol"].head(8).tolist()
        lines.append(f"| `{st}` | {STATE_ZH_MAP[st]} | {cnt} | {', '.join(syms)} |")

    report_path = base_dir / f"{slug}_{year}_trend_vol_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "db_path": str(db_path),
        "csv_path": str(csv_path),
        "viewer_path": str(viewer_path),
        "report_path": str(report_path),
        "total_segments": len(stages_df),
        "tickers": int(stages_df["symbol"].nunique()),
        "state_counts": state_counts,
        "latest_counts": latest_counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Refine data with 6-state Trend x Volatility stages")
    parser.add_argument("--target", required=True, help="Target slug (e.g. tw50)")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()

    res = refine_trend_vol(args.target, args.year, args.data_dir)
    print("Refined Trend x Vol stages:", res)


if __name__ == "__main__":
    main()
