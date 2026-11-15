"""Interactive dark-mode Plotly & Data Tables GUI builder for single stocks and stock pools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _df_to_records(df: pd.DataFrame, date_col: str | None = None) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    work = df.copy()
    if date_col and date_col not in work.columns:
        work[date_col] = work.index.strftime("%Y-%m-%d")
    work = work.replace({np.nan: None, np.inf: None, -np.inf: None})
    records = work.to_dict(orient="records")
    for rec in records:
        for k, v in list(rec.items()):
            if isinstance(v, (np.integer,)):
                rec[k] = int(v)
            elif isinstance(v, (np.floating, float)):
                rec[k] = round(float(v), 4)
    return records


def build_gui_html(
    target_slug: str,
    target_type: str,
    year: int,
    market: str,
    benchmark: str,
    ticker_payloads: dict[str, dict[str, Any]],
    cross_summary: list[dict[str, Any]],
    out_path: Path,
) -> None:
    """Build standalone interactive dark-mode HTML GUI workbench."""
    tickers = list(ticker_payloads.keys())
    default_ticker = tickers[0] if tickers else ""

    embedded = {
        "target": target_slug,
        "target_type": target_type,
        "year": year,
        "market": market,
        "benchmark": benchmark,
        "tickers": tickers,
        "cross_summary": cross_summary,
        "data": ticker_payloads,
    }
    data_json = json.dumps(embedded, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{target_slug.upper()} ({year}) 量化數據與因子工作台</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  :root {{
    --bg: #0b0f17; --card: #131a26; --border: #232d3f; --text: #e2e8f0;
    --muted: #94a3b8; --accent: #38bdf8; --green: #22c55e; --red: #ef4444; --amber: #f59e0b;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         background: var(--bg); color: var(--text); }}
  header {{ display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
            padding: 14px 22px; background: var(--card); border-bottom: 1px solid var(--border); gap: 12px; }}
  .title {{ font-size: 18px; font-weight: 700; letter-spacing: .3px; }}
  .badge {{ display: inline-block; padding: 3px 9px; border-radius: 999px; font-size: 12px;
            background: rgba(56,189,248,.14); color: var(--accent); border: 1px solid rgba(56,189,248,.35); }}
  .controls {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
  select, input, button {{ background: #0f1623; color: var(--text); border: 1px solid var(--border);
                           border-radius: 6px; padding: 6px 10px; font-size: 13px; }}
  button {{ cursor: pointer; transition: .15s; }}
  button:hover {{ border-color: var(--accent); color: var(--accent); }}
  button.active {{ background: rgba(56,189,248,.18); border-color: var(--accent); color: var(--accent); }}
  .tabs {{ display: flex; gap: 6px; padding: 10px 22px; background: #0e1420; border-bottom: 1px solid var(--border); flex-wrap: wrap; }}
  .tab-btn {{ padding: 7px 14px; border-radius: 6px; font-weight: 600; }}
  .container {{ padding: 18px 22px; max-width: 1680px; margin: 0 auto; }}
  .panel {{ display: none; }}
  .panel.active {{ display: block; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 16px; }}
  .kpi {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; }}
  .kpi .lbl {{ font-size: 12px; color: var(--muted); }}
  .kpi .val {{ font-size: 20px; font-weight: 700; margin-top: 4px; }}
  .chart-box {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 10px; margin-bottom: 16px; }}
  .toolbar {{ display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px;
              background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; margin-bottom: 10px; }}
  .span-badge {{ font-size: 12px; color: var(--accent); font-weight: 600; }}
  .match-badge {{ font-size: 12px; color: var(--green); font-weight: 600; }}
  .chk-group {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 8px 0 12px; font-size: 12px; }}
  .chk-group label {{ display: inline-flex; align-items: center; gap: 5px; cursor: pointer; color: var(--muted); }}
  .table-wrap {{ overflow: auto; max-height: 580px; border: 1px solid var(--border); border-radius: 8px; background: var(--card); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; white-space: nowrap; }}
  th, td {{ padding: 7px 10px; border-bottom: 1px solid var(--border); text-align: right; }}
  th {{ position: sticky; top: 0; background: #172030; color: var(--muted); z-index: 2; font-weight: 600; }}
  th.anchor, td.anchor {{ position: sticky; left: 0; background: #151d2c; z-index: 3; text-align: left; font-weight: 600; color: var(--accent); }}
  th.anchor {{ z-index: 4; }}
  tr:hover td {{ background: rgba(56,189,248,.06); }}
  .pos {{ color: var(--green); }} .neg {{ color: var(--red); }}
</style>
</head>
<body>
<header>
  <div class="title">
    📊 {target_slug.upper()} ({year}) 量化數據工作台
    <span class="badge">{target_type.upper()} · {market} · Benchmark: {benchmark}</span>
  </div>
  <div class="controls">
    <label style="font-size:13px;color:var(--muted)">標的選擇：</label>
    <select id="tickerSelect"></select>
    <span id="tickerNameBadge" class="badge"></span>
  </div>
</header>

<div class="tabs">
  <button class="tab-btn active" onclick="switchTab('tabOverview', this)">🌐 股票池橫截面總覽</button>
  <button class="tab-btn" onclick="switchTab('tabPrice', this)">📈 價量與技術指標</button>
  <button class="tab-btn" onclick="switchTab('tabChips', this)">🏦 CYQ 與台股籌碼</button>
  <button class="tab-btn" onclick="switchTab('tabPriority', this)">🎯 多空因子優先級看板</button>
  <button class="tab-btn" onclick="switchTab('tabTables', this)">🎛️ Tab 5: 歷史時序數據明細表</button>
</div>

<div class="container">
  <div id="kpiGrid" class="kpi-grid"></div>

  <div id="tabOverview" class="panel active">
    <div class="chart-box"><div id="poolScatter" style="height:430px;"></div></div>
    <div class="table-wrap" style="max-height:480px;">
      <table id="poolSummaryTable"></table>
    </div>
  </div>

  <div id="tabPrice" class="panel">
    <div class="chart-box"><div id="priceChart" style="height:560px;"></div></div>
    <div class="chart-box"><div id="momentumChart" style="height:320px;"></div></div>
  </div>

  <div id="tabChips" class="panel">
    <div class="chart-box"><div id="cyqChart" style="height:360px;"></div></div>
    <div class="chart-box"><div id="twChipsChart" style="height:380px;"></div></div>
  </div>

  <div id="tabPriority" class="panel">
    <div class="table-wrap"><table id="priorityTable"></table></div>
  </div>

  <div id="tabTables" class="panel">
    <div class="controls" style="margin-bottom:10px;">
      <button class="active" onclick="switchFreq('daily', this)">日頻層 (Daily)</button>
      <button onclick="switchFreq('monthly', this)">月頻層 (Monthly)</button>
      <button onclick="switchFreq('quarterly', this)">季頻層 (Quarterly)</button>
    </div>

    <div class="toolbar">
      <div id="spanBadge" class="span-badge">📌 數據總跨度: -</div>
      <div id="dateControls" class="controls"></div>
      <div id="matchBadge" class="match-badge">✅ 當前視窗: 0 / 0 行</div>
    </div>

    <div class="toolbar">
      <div class="chk-group" id="factorToggles"></div>
      <div class="controls">
        <button onclick="setPresetMode('all')">[全選全部因子]</button>
        <button onclick="setPresetMode('core')">[僅看核心精簡模式]</button>
        <button onclick="setPresetMode('none')">[隱藏全部可選因子]</button>
      </div>
    </div>

    <div class="table-wrap"><table id="dataTable"></table></div>
  </div>
</div>

<script>
const PAYLOAD = {data_json};
let currentTicker = "{default_ticker}";
let currentFreq = "daily";

const FACTOR_GROUPS = {{
  daily: [
    {{ id: "price", label: "基礎價量(開/高/低/收/量)", cols: ["raw_open","raw_high","raw_low","raw_close","adj_close","pct_change","volume","is_fillable"] }},
    {{ id: "ma", label: "均線(EMA/SMA)", cols: ["ema_5","ema_10","ema_20","ema_60","sma_5","sma_20","sma_50","sma_200"] }},
    {{ id: "mom", label: "動能通道(RSI/MACD/KDJ/BOLL/ATR)", cols: ["rsi_14","macd_dif","macd_dea","macd_hist","kdj_k","kdj_d","kdj_j","wr_14","cci_14","boll_upper","boll_lower","atr_14"] }},
    {{ id: "cyq", label: "籌碼與宏觀(CYQ/NQ/ES/VIX)", cols: ["cyq_profit_ratio","cyq_trapped_ratio","cyq_avg_cost","cyq_cost_discount","nq_close","es_close","vix_close"] }},
    {{ id: "tw", label: "台股微結構籌碼(法人/信用/當沖)", cols: ["foreign_net_lots","trust_net_lots","dealer_net_lots","inst_total_net_lots","margin_balance","margin_net_change","short_margin_ratio","day_trading_ratio","foreign_holding_ratio","chip_pattern"] }}
  ],
  monthly: [
    {{ id: "m_ohlcv", label: "月度價量", cols: ["month_open","month_high","month_low","month_close","month_pct_change","month_volume"] }},
    {{ id: "m_tech", label: "月末技術與CYQ", cols: ["ema_10","sma_50","rsi_14","macd_hist","cyq_profit_ratio","cyq_avg_cost"] }},
    {{ id: "m_tw", label: "月度台股籌碼", cols: ["foreign_net_lots","trust_net_lots","inst_total_net_lots","margin_net_change","short_margin_ratio"] }}
  ],
  quarterly: [
    {{ id: "q_fund", label: "季度財報與現金流", cols: ["revenue","net_income","ocf","capex","fcf","debt_to_equity","current_ratio","currency"] }}
  ]
}};

const CORE_COLS = new Set(["raw_close","pct_change","volume","rsi_14","macd_hist","cyq_profit_ratio","inst_total_net_lots","chip_pattern","month_close","month_pct_change","revenue","net_income"]);
let activeGroups = new Set(["price","ma","mom","cyq","tw","m_ohlcv","m_tech","m_tw","q_fund"]);

function init() {{
  const sel = document.getElementById("tickerSelect");
  PAYLOAD.tickers.forEach(t => {{
    const opt = document.createElement("option");
    opt.value = t;
    const name = PAYLOAD.data[t]?.name || "";
    opt.textContent = name && name !== t ? `${{t}} (${{name}})` : t;
    sel.appendChild(opt);
  }});
  sel.value = currentTicker;
  sel.addEventListener("change", () => {{ currentTicker = sel.value; renderAll(); }});

  if (PAYLOAD.target_type === "single") {{
    document.querySelectorAll(".tab-btn")[0].style.display = "none";
    switchTab("tabPrice", document.querySelectorAll(".tab-btn")[1]);
  }} else {{
    renderPoolOverview();
  }}
  renderAll();
}}

function switchTab(id, btn) {{
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.getElementById(id).classList.add("active");
  if (btn) btn.classList.add("active");
  setTimeout(() => window.dispatchEvent(new Event("resize")), 50);
}}

function renderPoolOverview() {{
  const rows = PAYLOAD.cross_summary || [];
  if (!rows.length) return;
  Plotly.newPlot("poolScatter", [{{
    x: rows.map(r => r.rsi_14),
    y: rows.map(r => r.cyq_profit_ratio),
    text: rows.map(r => `${{r.ticker}} ${{r.name||""}}<br>Close: ${{r.latest_close}} (${{r.ytd_return_pct}}%)<br>Pattern: ${{r.chip_pattern||"-"}}`),
    mode: "markers+text",
    textposition: "top center",
    textfont: {{ size: 10, color: "#cbd5e1" }},
    marker: {{
      size: 11,
      color: rows.map(r => r.ytd_return_pct),
      colorscale: "RdYlGn",
      showscale: true,
      colorbar: {{ title: "YTD %" }}
    }},
    type: "scatter"
  }}], {{
    title: "股票池橫截面分佈：RSI(14) vs CYQ 獲利盤比例 (%)",
    paper_bgcolor: "#131a26", plot_bgcolor: "#0f1623", font: {{ color: "#e2e8f0" }},
    xaxis: {{ title: "RSI (14)", gridcolor: "#232d3f" }},
    yaxis: {{ title: "CYQ 獲利盤 (%)", gridcolor: "#232d3f" }}
  }}, {{ responsive: true }});

  const cols = ["ticker","name","latest_date","latest_close","pct_change","ytd_return_pct","rsi_14","macd_hist","cyq_profit_ratio","inst_total_net_lots","short_margin_ratio","chip_pattern"];
  let html = "<thead><tr>" + cols.map(c => `<th class="${{c==='ticker'?'anchor':''}}">${{c}}</th>`).join("") + "</tr></thead><tbody>";
  rows.forEach(r => {{
    html += `<tr onclick="selectTickerFromPool('${{r.ticker}}')" style="cursor:pointer">` + cols.map(c => {{
      const v = r[c] ?? "-";
      const cls = c === "ticker" ? "anchor" : (["pct_change","ytd_return_pct","inst_total_net_lots"].includes(c) && typeof v === "number" ? (v >= 0 ? "pos" : "neg") : "");
      return `<td class="${{cls}}">${{v}}</td>`;
    }}).join("") + "</tr>";
  }});
  html += "</tbody>";
  document.getElementById("poolSummaryTable").innerHTML = html;
}}

function selectTickerFromPool(t) {{
  currentTicker = t;
  document.getElementById("tickerSelect").value = t;
  renderAll();
  switchTab("tabPrice", document.querySelectorAll(".tab-btn")[1]);
}}

function renderAll() {{
  const d = PAYLOAD.data[currentTicker];
  if (!d) return;
  document.getElementById("tickerNameBadge").textContent = d.name || currentTicker;
  renderKPIs(d);
  renderCharts(d);
  renderPriority(d);
  renderDataTableControls(d);
}}

function renderKPIs(d) {{
  const daily = d.daily || [];
  const last = daily[daily.length - 1] || {{}};
  const chips = d.chips || [];
  const clast = chips[chips.length - 1] || {{}};
  const kpis = [
    ["最新日期 / 交易日數", `${{last.date || "-"}} (${{daily.length}}d)`],
    ["最新收盤價", `${{last.raw_close ?? "-"}} (${{last.pct_change >= 0 ? "+" : ""}}${{last.pct_change ?? 0}}%)`],
    ["年度高 / 低", `${{d.year_high ?? "-"}} / ${{d.year_low ?? "-"}}`],
    ["RSI(14) / MACD Hist", `${{last.rsi_14 ?? "-"}} / ${{last.macd_hist ?? "-"}}`],
    ["CYQ 獲利盤 / 均價", `${{last.cyq_profit_ratio ?? "-"}}% / ${{last.cyq_avg_cost ?? "-"}}`],
    ["三大法人合計 / 形態", `${{clast.inst_total_net_lots ?? "-"}}張 · ${{clast.chip_pattern ?? "-"}}`],
  ];
  document.getElementById("kpiGrid").innerHTML = kpis.map(([l, v]) =>
    `<div class="kpi"><div class="lbl">${{l}}</div><div class="val">${{v}}</div></div>`
  ).join("");
}}

function renderCharts(d) {{
  const rows = d.daily || [];
  const dates = rows.map(r => r.date);
  Plotly.newPlot("priceChart", [
    {{ x: dates, open: rows.map(r=>r.raw_open), high: rows.map(r=>r.raw_high), low: rows.map(r=>r.raw_low), close: rows.map(r=>r.raw_close),
       type: "candlestick", name: currentTicker, increasing: {{line:{{color:"#ef4444"}}}}, decreasing: {{line:{{color:"#22c55e"}}}} }},
    {{ x: dates, y: rows.map(r=>r.ema_20), type: "scatter", mode: "lines", name: "EMA 20", line: {{color:"#38bdf8", width:1.3}} }},
    {{ x: dates, y: rows.map(r=>r.sma_50), type: "scatter", mode: "lines", name: "SMA 50", line: {{color:"#f59e0b", width:1.3}} }},
    {{ x: dates, y: rows.map(r=>r.sma_200), type: "scatter", mode: "lines", name: "SMA 200", line: {{color:"#a855f7", width:1.3}} }},
    {{ x: dates, y: rows.map(r=>r.cyq_avg_cost), type: "scatter", mode: "lines", name: "CYQ 均價", line: {{color:"#ec4899", dash:"dot", width:1.3}} }}
  ], {{
    title: `${{currentTicker}} 日線 K 線與均線 / CYQ 成本`,
    paper_bgcolor: "#131a26", plot_bgcolor: "#0f1623", font: {{ color: "#e2e8f0" }},
    xaxis: {{ rangeslider: {{ visible: false }}, gridcolor: "#232d3f" }},
    yaxis: {{ gridcolor: "#232d3f" }}, hovermode: "x unified"
  }}, {{ responsive: true }});

  Plotly.newPlot("momentumChart", [
    {{ x: dates, y: rows.map(r=>r.macd_hist), type: "bar", name: "MACD Hist", marker: {{ color: rows.map(r => (r.macd_hist||0) >= 0 ? "#ef4444" : "#22c55e") }} }},
    {{ x: dates, y: rows.map(r=>r.rsi_14), type: "scatter", mode: "lines", name: "RSI 14", yaxis: "y2", line: {{ color: "#38bdf8" }} }}
  ], {{
    title: "動能共振：MACD 柱狀圖 & RSI(14)",
    paper_bgcolor: "#131a26", plot_bgcolor: "#0f1623", font: {{ color: "#e2e8f0" }},
    xaxis: {{ gridcolor: "#232d3f" }}, yaxis: {{ title: "MACD", gridcolor: "#232d3f" }},
    yaxis2: {{ title: "RSI", overlaying: "y", side: "right", range: [0, 100] }}, hovermode: "x unified"
  }}, {{ responsive: true }});

  Plotly.newPlot("cyqChart", [
    {{ x: dates, y: rows.map(r=>r.cyq_profit_ratio), type: "scatter", fill: "tozeroy", name: "CYQ 獲利盤%", line: {{color:"#f59e0b"}} }},
    {{ x: dates, y: rows.map(r=>r.cyq_cost_discount), type: "scatter", mode: "lines", name: "成本貼水率%", yaxis: "y2", line: {{color:"#38bdf8"}} }}
  ], {{
    title: "每日滾動 CYQ 籌碼獲利盤比例 & 成本貼水率",
    paper_bgcolor: "#131a26", plot_bgcolor: "#0f1623", font: {{ color: "#e2e8f0" }},
    yaxis: {{ title: "獲利盤 %", range: [0, 100], gridcolor: "#232d3f" }},
    yaxis2: {{ title: "貼水率 %", overlaying: "y", side: "right" }}, hovermode: "x unified"
  }}, {{ responsive: true }});

  const chips = d.chips || [];
  if (chips.length) {{
    const cdates = chips.map(c => c.date);
    Plotly.newPlot("twChipsChart", [
      {{ x: cdates, y: chips.map(c=>c.foreign_net_lots), type: "bar", name: "外資買賣超(張)" }},
      {{ x: cdates, y: chips.map(c=>c.trust_net_lots), type: "bar", name: "投信買賣超(張)" }},
      {{ x: cdates, y: chips.map(c=>c.short_margin_ratio), type: "scatter", mode: "lines", name: "券資比 %", yaxis: "y2", line: {{color:"#f59e0b"}} }}
    ], {{
      barmode: "relative", title: "台股三大法人買賣超 (張) & 券資比 (%)",
      paper_bgcolor: "#131a26", plot_bgcolor: "#0f1623", font: {{ color: "#e2e8f0" }},
      yaxis: {{ title: "張數", gridcolor: "#232d3f" }},
      yaxis2: {{ title: "券資比 %", overlaying: "y", side: "right" }}, hovermode: "x unified"
    }}, {{ responsive: true }});
  }} else {{
    document.getElementById("twChipsChart").innerHTML = "<p style='color:#94a3b8;padding:20px;'>此標的無台股微結構籌碼數據。</p>";
  }}
}}

function renderPriority(d) {{
  const rows = d.priority || [];
  const cols = ["tier","timeframe","factor","value","signal"];
  let html = "<thead><tr>" + cols.map(c => `<th>${{c}}</th>`).join("") + "</tr></thead><tbody>";
  rows.forEach(r => {{
    html += "<tr>" + cols.map(c => `<td style="text-align:left">${{r[c] ?? "-"}}</td>`).join("") + "</tr>";
  }});
  document.getElementById("priorityTable").innerHTML = html + "</tbody>";
}}

function switchFreq(freq, btn) {{
  currentFreq = freq;
  btn.parentElement.querySelectorAll("button").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  renderDataTableControls(PAYLOAD.data[currentTicker]);
}}

function setPresetMode(mode) {{
  const groups = FACTOR_GROUPS[currentFreq] || [];
  if (mode === "all") groups.forEach(g => activeGroups.add(g.id));
  else if (mode === "none") groups.forEach(g => activeGroups.delete(g.id));
  else if (mode === "core") {{
    groups.forEach(g => activeGroups.delete(g.id));
    if (groups[0]) activeGroups.add(groups[0].id);
  }}
  renderDataTableControls(PAYLOAD.data[currentTicker], mode === "core");
}}

function renderDataTableControls(d, coreOnly = false) {{
  const rows = currentFreq === "daily" ? (d.daily || []) : (currentFreq === "monthly" ? (d.monthly || []) : (d.quarterly || []));
  const anchor = currentFreq === "daily" ? "date" : (currentFreq === "monthly" ? "month" : "quarter_end");
  const first = rows[0]?.[anchor] || "-";
  const last = rows[rows.length - 1]?.[anchor] || "-";

  const spanText = currentFreq === "daily"
    ? `📌 數據總跨度: ${{first}} 至 ${{last}} (共 ${{rows.length}} 個交易日)`
    : (currentFreq === "monthly"
      ? `📌 數據總跨度: ${{first}} 至 ${{last}} (共 ${{rows.length}} 個自然月)`
      : `📌 數據總跨度: ${{first}} 至 ${{last}} (共 ${{rows.length}} 個季度)`);
  document.getElementById("spanBadge").textContent = spanText;

  const dc = document.getElementById("dateControls");
  if (currentFreq === "daily") {{
    dc.innerHTML = `起: <input type="date" id="dtStart" value="${{first}}"> 迄: <input type="date" id="dtEnd" value="${{last}}">
      <button onclick="quickRange('ytd')">全量 YTD</button>
      <button onclick="quickRange('1m')">近 1 月</button>
      <button onclick="quickRange('3m')">近 3 月</button>
      <button onclick="quickRange('6m')">近半年</button>`;
  }} else if (currentFreq === "monthly") {{
    dc.innerHTML = `起: <input type="month" id="dtStart" value="${{first}}"> 迄: <input type="month" id="dtEnd" value="${{last}}">
      <button onclick="quickRange('ytd')">全年月度</button>
      <button onclick="quickRange('3m')">近 3 月</button>
      <button onclick="quickRange('6m')">近半年</button>`;
  }} else {{
    const opts = rows.map(r => `<option value="${{r[anchor]}}">${{r[anchor]}}</option>`).join("");
    dc.innerHTML = `起: <select id="dtStart">${{opts}}</select> 迄: <select id="dtEnd">${{opts}}</select>`;
    if (rows.length) {{ document.getElementById("dtStart").value = first; document.getElementById("dtEnd").value = last; }}
  }}
  document.getElementById("dtStart").addEventListener("change", () => renderDataTable(d, coreOnly));
  document.getElementById("dtEnd").addEventListener("change", () => renderDataTable(d, coreOnly));

  const ft = document.getElementById("factorToggles");
  ft.innerHTML = (FACTOR_GROUPS[currentFreq] || []).map(g =>
    `<label><input type="checkbox" ${{activeGroups.has(g.id) ? "checked" : ""}} onchange="toggleGroup('${{g.id}}', this.checked)"> ${{g.label}}</label>`
  ).join("");

  renderDataTable(d, coreOnly);
}}

function toggleGroup(gid, checked) {{
  if (checked) activeGroups.add(gid); else activeGroups.delete(gid);
  renderDataTable(PAYLOAD.data[currentTicker]);
}}

function quickRange(preset) {{
  const d = PAYLOAD.data[currentTicker];
  const rows = currentFreq === "daily" ? (d.daily || []) : (d.monthly || []);
  const anchor = currentFreq === "daily" ? "date" : "month";
  if (!rows.length) return;
  const endStr = rows[rows.length - 1][anchor];
  let idx = 0;
  if (preset === "1m") idx = Math.max(0, rows.length - 22);
  else if (preset === "3m") idx = Math.max(0, rows.length - (currentFreq === "daily" ? 65 : 3));
  else if (preset === "6m") idx = Math.max(0, rows.length - (currentFreq === "daily" ? 130 : 6));
  document.getElementById("dtStart").value = rows[idx][anchor];
  document.getElementById("dtEnd").value = endStr;
  renderDataTable(d);
}}

function renderDataTable(d, coreOnly = false) {{
  const rows = currentFreq === "daily" ? (d.daily || []) : (currentFreq === "monthly" ? (d.monthly || []) : (d.quarterly || []));
  const anchor = currentFreq === "daily" ? "date" : (currentFreq === "monthly" ? "month" : "quarter_end");
  const startVal = document.getElementById("dtStart")?.value || "";
  const endVal = document.getElementById("dtEnd")?.value || "9999-99-99";
  const filtered = rows.filter(r => r[anchor] >= startVal && r[anchor] <= endVal).slice().reverse();

  document.getElementById("matchBadge").textContent = `✅ 當前視窗: ${{filtered.length}} / ${{rows.length}} 行`;

  let cols = [anchor];
  (FACTOR_GROUPS[currentFreq] || []).forEach(g => {{
    if (coreOnly) {{
      g.cols.forEach(c => {{ if (CORE_COLS.has(c)) cols.push(c); }});
    }} else if (activeGroups.has(g.id)) {{
      cols.push(...g.cols);
    }}
  }});

  let html = "<thead><tr>" + cols.map(c => `<th class="${{c===anchor?'anchor':''}}">${{c}}</th>`).join("") + "</tr></thead><tbody>";
  filtered.forEach(r => {{
    html += "<tr>" + cols.map(c => {{
      const v = r[c] ?? "-";
      return `<td class="${{c===anchor?'anchor':''}}">${{v}}</td>`;
    }}).join("") + "</tr>";
  }});
  document.getElementById("dataTable").innerHTML = html + "</tbody>";
}}

init();
</script>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")
