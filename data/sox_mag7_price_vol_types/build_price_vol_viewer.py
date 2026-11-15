#!/usr/bin/env python3
"""build_price_vol_viewer.py

Builds Standalone Interactive HTML Viewer for Pure Price & Vol (Price & Vol Only) Research.
Target Universe: US Semiconductor SOX 30 constituents + Tech Mag 7 (39 assets, 2020-2026).

Key Interactive Features:
1. Professional Dark Slate Styling (#0f172a, #1e293b, #334155).
2. Standalone Single HTML with embedded data: runs locally in any modern browser without a server.
3. Multi-Subplot Chart:
   - Subplot 1 (Top, 46% height): Candlestick + 6-Regime colored background bands + Period boundary markers.
   - Subplot 2 (18% height): Rolling 60-day Drift mu_60 (%) with +10% (bull) & -10% (bear) threshold guides.
   - Subplot 3 (18% height): Rolling 60-day Realized Volatility sigma_60 (%) with 35% threshold guide.
   - Subplot 4 (18% height): Trading Volume + 60-day SMA Volume line.
4. Session ID on Hover:
   - Plotly unified hover prominently displays Session ID (e.g. `NVDA_PV005 [穩健低波主升]`).
   - Sticky Hover HUD status bar updating in real time with Date, OHLC, mu_60, sigma_60, Volume, RVol, Session ID.
5. Dedicated SOX vs Mag 7 Filters & Archetype Toggles:
   - Quick Filter Pills: All (39) | Mag 7 (7) | SOX 30 (30) | Benchmarks (3).
   - Archetype Filter: All Archetypes | A. 低波核心巨頭 | B. 高波狂飆龍頭 | C. 週期資本設備 | D. 高彈性轉機股 | E. 成熟現金流科技.
   - Quick-access stock chips for market leaders.
6. Period List Table:
   - Interactive table of all macro periods for the active asset.
   - Clicking any row smoothly zooms & centers the chart onto that period with padding!
7. SOX vs Mag 7 Market-Wide Comparison Tab:
   - Interactive Scatter Plot (sigma_60 Volatility vs CAGR / Drift mu_60), bubble size = Sharpe.
   - 6-Regime Time Allocation stacked bar chart (SOX vs Mag 7).
   - Stock Archetypes distribution breakdown.
   - Group KPI Comparison Table.
8. Universe Period Matrix & Explorer Tab:
   - Search & filter all 962 periods across the 38 active assets by regime.
"""

import os
import sys
import json
import sqlite3
import pandas as pd
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "price_vol_analysis.db")
OUTPUT_HTML_PATH = os.path.join(SCRIPT_DIR, "price_vol_viewer.html")

def load_data_from_db(db_path):
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at {db_path}. Please run analyze_price_vol.py first.")

    conn = sqlite3.connect(db_path)

    df_archetypes = pd.read_sql("SELECT * FROM stock_archetypes ORDER BY cagr_pct DESC", conn)
    df_regime_summary = pd.read_sql("SELECT * FROM regime_summary", conn)
    df_sox_summary = pd.read_sql("SELECT * FROM sox_vs_mag7_summary", conn)
    df_periods = pd.read_sql("SELECT * FROM price_vol_periods ORDER BY symbol, start_date ASC", conn)
    df_bars = pd.read_sql("SELECT * FROM bar_price_vol ORDER BY symbol, date ASC", conn)

    conn.close()

    print(f"Loaded from SQLite: {len(df_archetypes)} stocks, {len(df_periods)} periods, {len(df_bars):,} bars.")

    # Structure periods by symbol
    periods_by_sym = {}
    for sym, group in df_periods.groupby("symbol"):
        periods_by_sym[sym] = group.to_dict(orient="records")

    # Structure bars by symbol
    stocks_data = {}
    for sym, group in df_bars.groupby("symbol"):
        sym_periods = periods_by_sym.get(sym, [])
        arch_row = df_archetypes[df_archetypes["symbol"] == sym].iloc[0].to_dict() if len(df_archetypes[df_archetypes["symbol"] == sym]) > 0 else {}

        stocks_data[sym] = {
            "symbol": sym,
            "name": arch_row.get("name", sym),
            "sector": arch_row.get("sector", "Technology"),
            "group_name": arch_row.get("group_name", "SOX"),
            "archetype_code": arch_row.get("archetype_code", "E_MATURE_CASHCOW"),
            "archetype_name_zh": arch_row.get("archetype_name_zh", ""),
            "cagr_pct": arch_row.get("cagr_pct", 0.0),
            "ann_vol_pct": arch_row.get("ann_vol_pct", 0.0),
            "median_hv60_pct": arch_row.get("median_hv60_pct", 0.0),
            "max_dd_pct": arch_row.get("max_dd_pct", 0.0),
            "sharpe_ratio": arch_row.get("sharpe_ratio", 0.0),
            "dates": group["date"].tolist(),
            "open": [round(float(x), 2) for x in group["open"]],
            "high": [round(float(x), 2) for x in group["high"]],
            "low": [round(float(x), 2) for x in group["low"]],
            "close": [round(float(x), 2) for x in group["close"]],
            "volume": [int(x) for x in group["volume"]],
            "ret60": [round(float(x), 2) if pd.notnull(x) else None for x in group["ret60"]],
            "hv60": [round(float(x), 2) if pd.notnull(x) else None for x in group["hv60"]],
            "rvol60": [round(float(x), 2) if pd.notnull(x) else None for x in group["rvol60"]],
            "regime": group["regime"].tolist(),
            "period_id": group["period_id"].tolist(),
            "session_id": group["session_id"].tolist(),
            "periods": sym_periods
        }

    return (
        stocks_data,
        df_archetypes.to_dict(orient="records"),
        df_periods.to_dict(orient="records"),
        df_regime_summary.to_dict(orient="records"),
        df_sox_summary.to_dict(orient="records")
    )

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-TW" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>美股半導體 SOX 30 與科技七巨頭 Mag 7 純價格與量波類型 (Price & Vol Only) 量化檢視器</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.plot.ly/plotly-2.29.1.min.js"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            brand: {
              50: '#f0fdf4',
              500: '#10b981',
              600: '#059669',
              700: '#047857'
            }
          }
        }
      }
    }
  </script>
  <style>
    body { background-color: #0b0f19; color: #f1f5f9; font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; }
    .glass-card { background: rgba(17, 24, 39, 0.78); backdrop-filter: blur(14px); border: 1px solid rgba(255, 255, 255, 0.08); }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #0f172a; }
    ::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: #475569; }
    .filter-btn-active { background-color: #0284c7 !important; color: #ffffff !important; border-color: #38bdf8 !important; }
    .arch-btn-active { background-color: #7c3aed !important; color: #ffffff !important; border-color: #a78bfa !important; }
  </style>
</head>
<body class="min-h-screen flex flex-col">

  <!-- Top Navigation Header -->
  <header class="border-b border-slate-800 bg-slate-900/95 backdrop-blur sticky top-0 z-50 px-6 py-3">
    <div class="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-500 via-teal-500 to-cyan-500 flex items-center justify-center shadow-lg shadow-emerald-500/20">
          <i class="fa-solid fa-chart-line text-slate-950 text-lg font-black"></i>
        </div>
        <div>
          <div class="flex items-center gap-2">
            <h1 class="text-base font-bold text-white tracking-wide">SOX 30 & Mag 7 純價格與量波類型 (Price & Vol Only)</h1>
            <span class="text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-semibold border border-emerald-500/30">μ60 淨動量 × σ60 實現波動率 (35% 定錨)</span>
          </div>
          <p class="text-xs text-slate-400">涵蓋 39 檔標的 (2020–2026 全樣本) | 6 大宏觀體制 × 5 大群聚原型</p>
        </div>
      </div>

      <!-- Quick stock chips & selector -->
      <div class="flex items-center gap-3 flex-wrap">
        <div class="hidden lg:flex items-center gap-1.5 bg-slate-950/70 p-1 rounded-lg border border-slate-800" id="quick-chips">
          <button onclick="switchStock('NVDA')" class="chip px-2.5 py-1 text-xs font-semibold rounded hover:bg-slate-800 transition" data-sym="NVDA">NVDA</button>
          <button onclick="switchStock('TSLA')" class="chip px-2.5 py-1 text-xs font-semibold rounded hover:bg-slate-800 transition" data-sym="TSLA">TSLA</button>
          <button onclick="switchStock('AAPL')" class="chip px-2.5 py-1 text-xs font-semibold rounded hover:bg-slate-800 transition" data-sym="AAPL">AAPL</button>
          <button onclick="switchStock('MSFT')" class="chip px-2.5 py-1 text-xs font-semibold rounded hover:bg-slate-800 transition" data-sym="MSFT">MSFT</button>
          <button onclick="switchStock('ASML')" class="chip px-2.5 py-1 text-xs font-semibold rounded hover:bg-slate-800 transition" data-sym="ASML">ASML</button>
          <button onclick="switchStock('AMAT')" class="chip px-2.5 py-1 text-xs font-semibold rounded hover:bg-slate-800 transition" data-sym="AMAT">AMAT</button>
          <button onclick="switchStock('AMD')" class="chip px-2.5 py-1 text-xs font-semibold rounded hover:bg-slate-800 transition" data-sym="AMD">AMD</button>
          <button onclick="switchStock('INTC')" class="chip px-2.5 py-1 text-xs font-semibold rounded hover:bg-slate-800 transition" data-sym="INTC">INTC</button>
          <button onclick="switchStock('ENPH')" class="chip px-2.5 py-1 text-xs font-semibold rounded hover:bg-slate-800 transition" data-sym="ENPH">ENPH</button>
          <button onclick="switchStock('^SOX')" class="chip px-2.5 py-1 text-xs font-semibold rounded hover:bg-slate-800 transition" data-sym="^SOX">^SOX</button>
          <button onclick="switchStock('QQQ')" class="chip px-2.5 py-1 text-xs font-semibold rounded hover:bg-slate-800 transition" data-sym="QQQ">QQQ</button>
        </div>

        <div class="relative">
          <select id="stock-select" onchange="switchStock(this.value)" class="bg-slate-950 border border-slate-700 text-slate-200 text-sm rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-emerald-500 focus:outline-none cursor-pointer">
            <!-- options inserted by JS -->
          </select>
        </div>

        <a href="price_vol_report.md" target="_blank" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs rounded-lg transition border border-slate-700 flex items-center gap-1.5">
          <i class="fa-solid fa-file-lines text-emerald-400"></i> 量化報告
        </a>
      </div>
    </div>
  </header>

  <!-- Global Filter & Tab Controls -->
  <div class="border-b border-slate-800 bg-slate-950/80 px-6 py-2.5">
    <div class="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
      <!-- Tabs -->
      <div class="flex gap-4 text-sm font-medium">
        <button onclick="switchTab('chart')" id="tab-btn-chart" class="py-2 px-1 border-b-2 border-emerald-500 text-emerald-400 flex items-center gap-2">
          <i class="fa-solid fa-chart-candlestick"></i> 個股走勢與量波狀態
        </button>
        <button onclick="switchTab('compare')" id="tab-btn-compare" class="py-2 px-1 border-b-2 border-transparent text-slate-400 hover:text-slate-200 flex items-center gap-2">
          <i class="fa-solid fa-scale-balanced"></i> SOX vs Mag 7 全市場對比
        </button>
        <button onclick="switchTab('archetypes')" id="tab-btn-archetypes" class="py-2 px-1 border-b-2 border-transparent text-slate-400 hover:text-slate-200 flex items-center gap-2">
          <i class="fa-solid fa-boxes-stacked"></i> 5 大標的原型深度剖析
        </button>
        <button onclick="switchTab('periods')" id="tab-btn-periods" class="py-2 px-1 border-b-2 border-transparent text-slate-400 hover:text-slate-200 flex items-center gap-2">
          <i class="fa-solid fa-table-list"></i> 全市場宏觀週期矩陣 (962 週期)
        </button>
      </div>

      <!-- Universe Group Filter Pills -->
      <div class="flex items-center gap-2 text-xs">
        <span class="text-slate-400 mr-1"><i class="fa-solid fa-filter"></i> 族群篩選:</span>
        <button onclick="setGroupFilter('ALL')" id="grp-btn-ALL" class="grp-btn filter-btn-active px-2.5 py-1 rounded-md border border-slate-700 bg-slate-900 text-slate-300 font-medium hover:bg-slate-800 transition">全市場 (39)</button>
        <button onclick="setGroupFilter('MAG7')" id="grp-btn-MAG7" class="grp-btn px-2.5 py-1 rounded-md border border-slate-700 bg-slate-900 text-slate-300 font-medium hover:bg-slate-800 transition">Mag 7 巨頭 (7)</button>
        <button onclick="setGroupFilter('SOX')" id="grp-btn-SOX" class="grp-btn px-2.5 py-1 rounded-md border border-slate-700 bg-slate-900 text-slate-300 font-medium hover:bg-slate-800 transition">SOX 30 半導體 (30)</button>
        <button onclick="setGroupFilter('BENCHMARK')" id="grp-btn-BENCHMARK" class="grp-btn px-2.5 py-1 rounded-md border border-slate-700 bg-slate-900 text-slate-300 font-medium hover:bg-slate-800 transition">基準指數 (3)</button>
      </div>
    </div>
  </div>

  <!-- Main Container -->
  <main class="max-w-7xl mx-auto p-6 flex-1 w-full space-y-6">

    <!-- ========================================================================= -->
    <!-- TAB 1: SINGLE STOCK CHART & PERIODS VIEW -->
    <!-- ========================================================================= -->
    <div id="tab-chart" class="space-y-4">

      <!-- Stock Header Card -->
      <div class="glass-card rounded-2xl p-4 flex flex-wrap items-center justify-between gap-4">
        <div class="flex items-center gap-4">
          <div>
            <div class="flex items-center gap-2.5 flex-wrap">
              <span id="stock-sym-badge" class="text-3xl font-black text-white tracking-tight">NVDA</span>
              <span id="stock-name-badge" class="text-sm text-slate-300">NVIDIA Corporation</span>
              <span id="stock-group-badge" class="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">SOX & Mag 7 雙重龍頭</span>
              <span id="stock-arch-badge" class="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30">B. 高波狂飆龍頭</span>
            </div>
            <p class="text-xs text-slate-400 mt-1" id="stock-meta-info">
              年化複合報酬率 (CAGR): +62.7% | 年化波動率: 51.4% | 中位數 HV60: 47.6% | 最大回撤: -66.4% | 夏普比率: 1.16
            </p>
          </div>
        </div>

        <!-- 6 Regime Distribution Chips for Active Stock -->
        <div class="flex items-center gap-2 flex-wrap" id="regime-dist-chips">
          <!-- Dynamically populated -->
        </div>
      </div>

      <!-- Real-Time Hover HUD Bar -->
      <div id="hover-hud" class="glass-card rounded-xl px-4 py-2 text-xs flex flex-wrap items-center justify-between gap-3 border-l-4 border-emerald-500 transition-all">
        <div class="flex items-center gap-3.5 flex-wrap">
          <span class="text-slate-400"><i class="fa-regular fa-calendar mr-1 text-slate-500"></i><span id="hud-date" class="text-slate-200 font-mono font-bold">2026-11-10</span></span>
          <span class="text-slate-400">O: <span id="hud-open" class="font-mono text-slate-200">--</span></span>
          <span class="text-slate-400">H: <span id="hud-high" class="font-mono text-emerald-400">--</span></span>
          <span class="text-slate-400">L: <span id="hud-low" class="font-mono text-rose-400">--</span></span>
          <span class="text-slate-400">C: <span id="hud-close" class="font-mono font-black text-white text-sm">--</span></span>
          <span class="text-slate-400 border-l border-slate-700 pl-3">μ60 (Drift): <span id="hud-ret60" class="font-mono font-bold text-cyan-300">--</span></span>
          <span class="text-slate-400">σ60 (HV): <span id="hud-hv60" class="font-mono font-bold text-amber-300">--</span></span>
          <span class="text-slate-400">RVol: <span id="hud-rvol" class="font-mono font-bold text-purple-300">--</span></span>
        </div>
        <div class="flex items-center gap-2">
          <span id="hud-session-badge" class="px-3 py-1 rounded-full text-xs font-semibold bg-slate-800 text-emerald-300 border border-slate-700 flex items-center gap-1.5 shadow-inner">
            <i class="fa-solid fa-crosshairs text-emerald-400"></i>
            <span id="hud-session-text">滑鼠懸停 K 線圖檢視 Session ID</span>
          </span>
        </div>
      </div>

      <!-- Main Plotly Chart Container -->
      <div class="glass-card rounded-2xl p-4 relative">
        <div class="flex items-center justify-between pb-3 px-1 text-xs text-slate-400 border-b border-slate-800 mb-2 flex-wrap gap-2">
          <div class="flex items-center gap-3.5 flex-wrap">
            <span class="font-semibold text-slate-300 mr-1">6 大宏觀體制圖例:</span>
            <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded-sm bg-emerald-500/30 border border-emerald-500"></span> Type 1 穩健主升 (μ>10%, σ≤35%)</span>
            <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded-sm bg-amber-500/30 border border-amber-500"></span> Type 2 狂熱噴出 (μ>10%, σ>35%)</span>
            <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded-sm bg-sky-500/30 border border-sky-500"></span> Type 3 低波蓄勢 (|μ|≤10%, σ≤35%)</span>
            <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded-sm bg-purple-500/30 border border-purple-500"></span> Type 4 劇烈洗盤 (|μ|≤10%, σ>35%)</span>
            <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded-sm bg-rose-500/30 border border-rose-500"></span> Type 5 恐慌瀑布 (μ<-10%, σ>35%)</span>
            <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded-sm bg-slate-500/30 border border-slate-500"></span> Type 6 無量陰跌 (μ<-10%, σ≤35%)</span>
          </div>
          <button onclick="resetZoom()" class="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded text-xs transition border border-slate-700 flex items-center gap-1">
            <i class="fa-solid fa-arrows-rotate"></i> 重設全景縮放
          </button>
        </div>
        <div id="chart-div" style="height: 720px; width: 100%;"></div>
      </div>

      <!-- Current Stock Macro Periods Table -->
      <div class="glass-card rounded-2xl p-5 space-y-3">
        <div class="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h2 class="text-sm font-bold text-white flex items-center gap-2">
              <i class="fa-solid fa-list-check text-emerald-400"></i> 個股宏觀連續體制週期列表 (點擊任一行即可平滑聚焦縮放該週期)
            </h2>
            <p class="text-xs text-slate-400">依據 60 日漂移-擴散濾除小於 20 天雜訊所萃取之宏觀連續週期</p>
          </div>
          <span class="text-xs font-semibold px-2.5 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700" id="stock-period-count">共 -- 個週期</span>
        </div>
        <div class="overflow-x-auto max-h-80 overflow-y-auto rounded-xl border border-slate-800">
          <table class="w-full text-xs text-left text-slate-300">
            <thead class="text-slate-400 bg-slate-900/90 sticky top-0 uppercase tracking-wider text-[11px]">
              <tr>
                <th class="px-3 py-2.5">Session / Period ID</th>
                <th class="px-3 py-2.5">體制類型</th>
                <th class="px-3 py-2.5">起始日期</th>
                <th class="px-3 py-2.5">結束日期</th>
                <th class="px-3 py-2.5 text-right">天數</th>
                <th class="px-3 py-2.5 text-right">起始價</th>
                <th class="px-3 py-2.5 text-right">結束價</th>
                <th class="px-3 py-2.5 text-right">週期報酬</th>
                <th class="px-3 py-2.5 text-right">年化報酬</th>
                <th class="px-3 py-2.5 text-right">最大回撤</th>
                <th class="px-3 py-2.5 text-right">最大衝升</th>
                <th class="px-3 py-2.5 text-right">實現波動率</th>
                <th class="px-3 py-2.5 text-right">夏普比率</th>
                <th class="px-3 py-2.5 text-right">均量強度 RVol</th>
                <th class="px-3 py-2.5 text-center">操作</th>
              </tr>
            </thead>
            <tbody id="stock-periods-tbody" class="divide-y divide-slate-800/60 font-mono">
              <!-- Dynamically populated -->
            </tbody>
          </table>
        </div>
      </div>

    </div>

    <!-- ========================================================================= -->
    <!-- TAB 2: SOX VS MAG 7 MARKET-WIDE COMPARISON VIEW -->
    <!-- ========================================================================= -->
    <div id="tab-compare" class="space-y-6 hidden">
      
      <!-- Key KPI Comparison Banner -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4" id="kpi-banner-cards">
        <!-- Dynamically populated -->
      </div>

      <!-- Visual 1: Scatter Plot (Realized Vol vs CAGR / Drift) -->
      <div class="glass-card rounded-2xl p-5 space-y-3">
        <div class="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h2 class="text-base font-bold text-white flex items-center gap-2">
              <i class="fa-solid fa-braille text-cyan-400"></i> 全市場 39 檔標的「價格動量 (CAGR) vs 實現波動率 (σ)」正交分佈散點圖
            </h2>
            <p class="text-xs text-slate-400">橫軸為年化實現波動率，縱軸為年化報酬率 CAGR，氣泡大小對應夏普比率 (Sharpe Ratio)</p>
          </div>
          <div class="flex items-center gap-2 text-xs">
            <span class="text-slate-400">色彩分組:</span>
            <button onclick="setScatterColorMode('GROUP')" id="scat-grp-btn" class="px-2.5 py-1 rounded bg-sky-600 text-white font-medium">SOX vs Mag 7 族群</button>
            <button onclick="setScatterColorMode('ARCHETYPE')" id="scat-arch-btn" class="px-2.5 py-1 rounded bg-slate-800 text-slate-300 hover:bg-slate-700 transition">5 大標的原型</button>
          </div>
        </div>
        <div id="scatter-chart-div" style="height: 520px; width: 100%;"></div>
      </div>

      <!-- Visual 2 & 3: Two Columns: Regime Time Allocation & Archetype Breakdown -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- Regime Allocation Bar -->
        <div class="glass-card rounded-2xl p-5 space-y-3">
          <h2 class="text-base font-bold text-white flex items-center gap-2">
            <i class="fa-solid fa-chart-bar text-amber-400"></i> SOX vs Mag 7 族群「6 大體制時間分配佔比」對比
          </h2>
          <p class="text-xs text-slate-400">Mag 7 長期深耕於低波動區間 (58.2%)，而 SOX 族群高達 75.0% 的時間處於高波劇烈震盪中</p>
          <div id="regime-bar-chart-div" style="height: 380px; width: 100%;"></div>
        </div>

        <!-- Archetype Distribution Bar -->
        <div class="glass-card rounded-2xl p-5 space-y-3">
          <h2 class="text-base font-bold text-white flex items-center gap-2">
            <i class="fa-solid fa-chart-pie text-emerald-400"></i> SOX vs Mag 7 族群「5 大標的原型分佈結構」
          </h2>
          <p class="text-xs text-slate-400">Mag 7 結構性聚集於 A (低波巨頭) 與 B (狂飆龍頭)；SOX 則遍布 C (資本設備)、D (高彈性轉機) 與 E (成熟製程)</p>
          <div id="archetype-bar-chart-div" style="height: 380px; width: 100%;"></div>
        </div>
      </div>

      <!-- SOX vs Mag 7 Summary Table -->
      <div class="glass-card rounded-2xl p-5 space-y-3">
        <h2 class="text-base font-bold text-white flex items-center gap-2">
          <i class="fa-solid fa-table-cells-large text-purple-400"></i> 族群總體統計對比數據表 (Summary Table)
        </h2>
        <div class="overflow-x-auto rounded-xl border border-slate-800">
          <table class="w-full text-xs text-left text-slate-300">
            <thead class="text-slate-400 bg-slate-900/90 uppercase tracking-wider text-[11px]">
              <tr>
                <th class="px-4 py-3">族群名稱</th>
                <th class="px-3 py-3 text-right">標的數量</th>
                <th class="px-3 py-3 text-right font-bold text-emerald-400">平均 CAGR</th>
                <th class="px-3 py-3 text-right text-amber-400">平均年化波動率</th>
                <th class="px-3 py-3 text-right text-purple-400">中位數 HV60</th>
                <th class="px-3 py-3 text-right text-rose-400">平均最大回撤</th>
                <th class="px-3 py-3 text-right font-bold text-cyan-300">平均夏普比率</th>
                <th class="px-3 py-3 text-right text-emerald-300">穩健主升(%)</th>
                <th class="px-3 py-3 text-right text-amber-300">狂熱噴出(%)</th>
                <th class="px-3 py-3 text-right text-sky-300">低波蓄勢(%)</th>
                <th class="px-3 py-3 text-right text-purple-300">劇烈洗盤(%)</th>
                <th class="px-3 py-3 text-right text-rose-300">恐慌瀑布(%)</th>
                <th class="px-3 py-3 text-right text-slate-300">無量陰跌(%)</th>
                <th class="px-3 py-3">核心支配原型</th>
              </tr>
            </thead>
            <tbody id="sox-vs-mag7-tbody" class="divide-y divide-slate-800/60 font-mono">
              <!-- Dynamically populated -->
            </tbody>
          </table>
        </div>
      </div>

    </div>

    <!-- ========================================================================= -->
    <!-- TAB 3: 5 STOCK ARCHETYPES DEEP DIVE VIEW -->
    <!-- ========================================================================= -->
    <div id="tab-archetypes" class="space-y-6 hidden">
      <!-- 5 Archetype Cards -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" id="archetype-desc-cards">
        <!-- Dynamically populated -->
      </div>

      <!-- Archetype Stock Table with Filter -->
      <div class="glass-card rounded-2xl p-5 space-y-4">
        <div class="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h2 class="text-base font-bold text-white flex items-center gap-2">
              <i class="fa-solid fa-list-ol text-emerald-400"></i> 全市場 39 檔標的原型特徵完整清單
            </h2>
            <p class="text-xs text-slate-400">點擊任一標的代碼即可直接切換至主圖檢視走勢</p>
          </div>

          <!-- Archetype Filter Pills -->
          <div class="flex items-center gap-1.5 flex-wrap text-xs" id="arch-filter-pills">
            <button onclick="setArchFilter('ALL')" id="arch-flt-ALL" class="arch-flt-btn arch-btn-active px-2.5 py-1 rounded border border-slate-700 bg-slate-900 text-slate-200">全部原型</button>
            <button onclick="setArchFilter('A_LOWVOL_TITAN')" id="arch-flt-A_LOWVOL_TITAN" class="arch-flt-btn px-2.5 py-1 rounded border border-slate-700 bg-slate-900 text-slate-200">A. 低波巨頭</button>
            <button onclick="setArchFilter('B_HYPERGROWTH_MOMENTUM')" id="arch-flt-B_HYPERGROWTH_MOMENTUM" class="arch-flt-btn px-2.5 py-1 rounded border border-slate-700 bg-slate-900 text-slate-200">B. 狂飆龍頭</button>
            <button onclick="setArchFilter('C_CYCLICAL_EQUIPMENT')" id="arch-flt-C_CYCLICAL_EQUIPMENT" class="arch-flt-btn px-2.5 py-1 rounded border border-slate-700 bg-slate-900 text-slate-200">C. 資本設備</button>
            <button onclick="setArchFilter('D_HIGHBETA_SPECULATIVE')" id="arch-flt-D_HIGHBETA_SPECULATIVE" class="arch-flt-btn px-2.5 py-1 rounded border border-slate-700 bg-slate-900 text-slate-200">D. 高彈性轉機</button>
            <button onclick="setArchFilter('E_MATURE_CASHCOW')" id="arch-flt-E_MATURE_CASHCOW" class="arch-flt-btn px-2.5 py-1 rounded border border-slate-700 bg-slate-900 text-slate-200">E. 成熟現金流</button>
          </div>
        </div>

        <div class="overflow-x-auto max-h-[500px] overflow-y-auto rounded-xl border border-slate-800">
          <table class="w-full text-xs text-left text-slate-300">
            <thead class="text-slate-400 bg-slate-900/90 sticky top-0 uppercase tracking-wider text-[11px]">
              <tr>
                <th class="px-3 py-2.5">標的代碼</th>
                <th class="px-3 py-2.5">名稱</th>
                <th class="px-3 py-2.5">所屬族群</th>
                <th class="px-3 py-2.5">標的原型</th>
                <th class="px-3 py-2.5 text-right font-bold text-emerald-400">CAGR</th>
                <th class="px-3 py-2.5 text-right text-amber-400">年化波動率</th>
                <th class="px-3 py-2.5 text-right text-purple-400">中位數 HV60</th>
                <th class="px-3 py-2.5 text-right text-rose-400">最大回撤</th>
                <th class="px-3 py-2.5 text-right font-bold text-cyan-300">夏普比率</th>
                <th class="px-3 py-2.5 text-right text-emerald-300">多頭體制佔比</th>
                <th class="px-3 py-2.5 text-right text-rose-300">空頭體制佔比</th>
                <th class="px-3 py-2.5 text-right text-amber-300">高波體制佔比</th>
                <th class="px-3 py-2.5 text-center">切換走勢</th>
              </tr>
            </thead>
            <tbody id="archetype-stocks-tbody" class="divide-y divide-slate-800/60 font-mono">
              <!-- Dynamically populated -->
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ========================================================================= -->
    <!-- TAB 4: UNIVERSE PERIOD MATRIX & EXPLORER VIEW -->
    <!-- ========================================================================= -->
    <div id="tab-periods" class="space-y-6 hidden">
      <!-- 6 Regime Performance Cards -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3" id="regime-matrix-cards">
        <!-- Dynamically populated -->
      </div>

      <!-- Regime Explorer Table -->
      <div class="glass-card rounded-2xl p-5 space-y-4">
        <div class="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h2 class="text-base font-bold text-white flex items-center gap-2">
              <i class="fa-solid fa-layer-group text-cyan-400"></i> 全市場宏觀體制週期清單 (依體制篩選)
            </h2>
            <p class="text-xs text-slate-400" id="explorer-period-subtitle">全市場共有 962 個宏觀週期</p>
          </div>

          <div class="flex items-center gap-1.5 flex-wrap text-xs" id="regime-filter-pills">
            <button onclick="setRegimeFilter('ALL')" id="reg-flt-ALL" class="reg-flt-btn filter-btn-active px-2.5 py-1 rounded border border-slate-700 bg-slate-900 text-slate-200">全部體制 (962)</button>
            <button onclick="setRegimeFilter('TYPE1_STEADY_BULL')" id="reg-flt-TYPE1_STEADY_BULL" class="reg-flt-btn px-2.5 py-1 rounded border border-slate-700 bg-slate-900 text-emerald-400">Type 1 穩健主升</button>
            <button onclick="setRegimeFilter('TYPE2_MOMENTUM_CLIMAX')" id="reg-flt-TYPE2_MOMENTUM_CLIMAX" class="reg-flt-btn px-2.5 py-1 rounded border border-slate-700 bg-slate-900 text-amber-400">Type 2 狂熱噴出</button>
            <button onclick="setRegimeFilter('TYPE3_SQUEEZE_BASE')" id="reg-flt-TYPE3_SQUEEZE_BASE" class="reg-flt-btn px-2.5 py-1 rounded border border-slate-700 bg-slate-900 text-sky-400">Type 3 低波蓄勢</button>
            <button onclick="setRegimeFilter('TYPE4_BATTLEGROUND_CHOP')" id="reg-flt-TYPE4_BATTLEGROUND_CHOP" class="reg-flt-btn px-2.5 py-1 rounded border border-slate-700 bg-slate-900 text-purple-400">Type 4 劇烈洗盤</button>
            <button onclick="setRegimeFilter('TYPE5_PANIC_LIQUIDATION')" id="reg-flt-TYPE5_PANIC_LIQUIDATION" class="reg-flt-btn px-2.5 py-1 rounded border border-slate-700 bg-slate-900 text-rose-400">Type 5 恐慌瀑布</button>
            <button onclick="setRegimeFilter('TYPE6_DESPAIR_BLEED')" id="reg-flt-TYPE6_DESPAIR_BLEED" class="reg-flt-btn px-2.5 py-1 rounded border border-slate-700 bg-slate-900 text-slate-400">Type 6 無量陰跌</button>
          </div>
        </div>

        <div class="overflow-x-auto max-h-[550px] overflow-y-auto rounded-xl border border-slate-800">
          <table class="w-full text-xs text-left text-slate-300">
            <thead class="text-slate-400 bg-slate-900/90 sticky top-0 uppercase tracking-wider text-[11px]">
              <tr>
                <th class="px-3 py-2.5">標的代碼</th>
                <th class="px-3 py-2.5">Session / Period ID</th>
                <th class="px-3 py-2.5">體制類型</th>
                <th class="px-3 py-2.5">起始日期</th>
                <th class="px-3 py-2.5">結束日期</th>
                <th class="px-3 py-2.5 text-right">天數</th>
                <th class="px-3 py-2.5 text-right">起始價</th>
                <th class="px-3 py-2.5 text-right">結束價</th>
                <th class="px-3 py-2.5 text-right font-bold text-emerald-400">週期報酬</th>
                <th class="px-3 py-2.5 text-right text-rose-400">最大回撤</th>
                <th class="px-3 py-2.5 text-right text-emerald-300">最大衝升</th>
                <th class="px-3 py-2.5 text-right text-cyan-300">夏普比率</th>
                <th class="px-3 py-2.5 text-right text-amber-300">平均 σ60</th>
                <th class="px-3 py-2.5 text-right text-purple-300">均量 RVol</th>
                <th class="px-3 py-2.5 text-center">跳轉走勢</th>
              </tr>
            </thead>
            <tbody id="all-periods-tbody" class="divide-y divide-slate-800/60 font-mono">
              <!-- Dynamically populated -->
            </tbody>
          </table>
        </div>
      </div>
    </div>

  </main>

  <!-- Footer -->
  <footer class="border-t border-slate-800/80 bg-slate-950/60 py-4 px-6 text-center text-xs text-slate-500">
    純價格與量波研究系統 (Price & Vol Only) | 美股半導體 SOX 30 與科技七巨頭 Mag 7 | 資料跨度: 2020-01-02 至 2026-11-10 (1,724 交易日)
  </footer>

  <!-- Embedded JSON Data and Application Logic -->
  <script>
    const STOCKS_DATA = __STOCKS_DATA_JSON__;
    const STOCK_ARCHETYPES = __STOCK_ARCHETYPES_JSON__;
    const ALL_PERIODS = __ALL_PERIODS_JSON__;
    const REGIME_SUMMARY = __REGIME_SUMMARY_JSON__;
    const SOX_MAG7_SUMMARY = __SOX_MAG7_SUMMARY_JSON__;

    const REGIME_CONFIG = {
      "TYPE1_STEADY_BULL": { name: "穩健低波主升 (Low-Vol Steady Compounder)", short: "穩健主升", color: "#10b981", bg: "rgba(16, 185, 129, 0.20)", border: "#059669" },
      "TYPE2_MOMENTUM_CLIMAX": { name: "狂熱高波噴出 (High-Vol Momentum Climax)", short: "狂熱噴出", color: "#f59e0b", bg: "rgba(245, 158, 11, 0.20)", border: "#d97706" },
      "TYPE3_SQUEEZE_BASE": { name: "低波壓縮蓄勢 (Low-Vol Squeeze Base)", short: "低波蓄勢", color: "#0ea5e9", bg: "rgba(14, 165, 233, 0.20)", border: "#0284c7" },
      "TYPE4_BATTLEGROUND_CHOP": { name: "高波劇烈洗盤 (High-Vol Battleground Chop)", short: "劇烈洗盤", color: "#8b5cf6", bg: "rgba(139, 92, 246, 0.20)", border: "#7c3aed" },
      "TYPE5_PANIC_LIQUIDATION": { name: "高波恐慌瀑布 (High-Vol Panic Liquidation)", short: "恐慌瀑布", color: "#ef4444", bg: "rgba(239, 68, 68, 0.22)", border: "#dc2626" },
      "TYPE6_DESPAIR_BLEED": { name: "無量陰跌失血 (Low-Vol Despair Bleed)", short: "無量陰跌", color: "#64748b", bg: "rgba(100, 116, 139, 0.22)", border: "#475569" }
    };

    const ARCHETYPE_CONFIG = {
      "A_LOWVOL_TITAN": {
        name: "A. 低波核心巨頭 (Mega-Cap Low-Vol Titans)",
        short: "低波巨頭",
        color: "#10b981",
        desc: "全球科技平台超級壟斷者，現金流如印鈔機，護城河極深。中位數 HV60 壓制在 35% 以下，回撤溫和，夏普比率長年領先。",
        examples: "AAPL, MSFT, GOOGL, AMZN, META"
      },
      "B_HYPERGROWTH_MOMENTUM": {
        name: "B. 高波狂飆龍頭 (Hyper-Growth Momentum Leaders)",
        short: "狂飆龍頭",
        color: "#f59e0b",
        desc: "AI 算力與先進晶片擴張主升浪領袖。CAGR 極高 (>30%~60%)，波動率偏高 (>35%~55%)，Type 2 噴出狂歡期佔比巨大。",
        examples: "NVDA, TSLA, AMD, AVGO, MU, MPWR, TSM"
      },
      "C_CYCLICAL_EQUIPMENT": {
        name: "C. 週期性資本設備壟斷者 (Cyclical Semi Equipment Giants)",
        short: "資本設備",
        color: "#0ea5e9",
        desc: "半導體前段製程設備與曝光、蝕刻、檢測之獨家壟斷者。受晶圓廠資本開支 (Capex) 週期劇烈驅動，爆發力與消化期鮮明。",
        examples: "ASML, AMAT, LRCX, KLAC, TER"
      },
      "D_HIGHBETA_SPECULATIVE": {
        name: "D. 高彈性高風險轉機股 (High-Beta Speculative / Turnarounds)",
        short: "高彈性轉機",
        color: "#ef4444",
        desc: "高波動、高 Beta、特定材料/新興架構或困境反轉標的。年化波動率常破 50%~100%，歷史最大回撤深達 -60% 至 -90%。",
        examples: "ENPH, WOLF, ON, ARM, COHR, GFS, LSCC, MRVL, MKSI"
      },
      "E_MATURE_CASHCOW": {
        name: "E. 成熟現金流成熟製程 (Mature Cash-Cow Tech)",
        short: "成熟現金流",
        color: "#8b5cf6",
        desc: "類比 IC、微控制器 (MCU)、車用/工控晶片或轉型陣痛傳統 IDM。營收平穩但成長動能偏緩，長時間處於壓縮或區間洗盤。",
        examples: "INTC, TXN, QCOM, ADI, NXPI, MCHP, CRUS, STM, SWKS, QRVO"
      },
      "BENCHMARK": {
        name: "基準指數 / ETF (Market Benchmarks)",
        short: "基準指數",
        color: "#94a3b8",
        desc: "美股大盤與半導體產業 ETF，提供全市場走勢與相對強弱 (Alpha) 的定錨基準。",
        examples: "^SOX, SOXX, QQQ"
      }
    };

    let currentSymbol = "NVDA";
    let currentGroupFilter = "ALL";
    let currentArchFilter = "ALL";
    let currentRegimeFilter = "ALL";
    let scatterColorMode = "GROUP";

    window.addEventListener("DOMContentLoaded", () => {
      populateStockSelect();
      renderCompareTab();
      renderArchetypesTab();
      renderPeriodsTab();
      switchStock(currentSymbol);
    });

    // -------------------------------------------------------------
    // Tab Navigation
    // -------------------------------------------------------------
    function switchTab(tabId) {
      ["chart", "compare", "archetypes", "periods"].forEach(t => {
        const el = document.getElementById(`tab-${t}`);
        const btn = document.getElementById(`tab-btn-${t}`);
        if (t === tabId) {
          el.classList.remove("hidden");
          btn.classList.add("border-emerald-500", "text-emerald-400");
          btn.classList.remove("border-transparent", "text-slate-400");
        } else {
          el.classList.add("hidden");
          btn.classList.remove("border-emerald-500", "text-emerald-400");
          btn.classList.add("border-transparent", "text-slate-400");
        }
      });

      if (tabId === "chart") {
        Plotly.relayout('chart-div', { autosize: true });
      } else if (tabId === "compare") {
        Plotly.relayout('scatter-chart-div', { autosize: true });
        Plotly.relayout('regime-bar-chart-div', { autosize: true });
        Plotly.relayout('archetype-bar-chart-div', { autosize: true });
      }
    }

    // -------------------------------------------------------------
    // Universe Group Filtering
    // -------------------------------------------------------------
    function setGroupFilter(grp) {
      currentGroupFilter = grp;
      document.querySelectorAll(".grp-btn").forEach(b => {
        if (b.id === `grp-btn-${grp}`) {
          b.classList.add("filter-btn-active");
        } else {
          b.classList.remove("filter-btn-active");
        }
      });
      populateStockSelect();
      // If current stock is not in filtered list, switch to first available
      const sel = document.getElementById("stock-select");
      if (sel.options.length > 0) {
        let hasCurrent = false;
        for (let i = 0; i < sel.options.length; i++) {
          if (sel.options[i].value === currentSymbol) {
            hasCurrent = true;
            break;
          }
        }
        if (!hasCurrent) {
          switchStock(sel.options[0].value);
        }
      }
    }

    function populateStockSelect() {
      const sel = document.getElementById("stock-select");
      sel.innerHTML = "";
      
      const filteredSymbols = Object.keys(STOCKS_DATA).filter(sym => {
        const s = STOCKS_DATA[sym];
        if (currentGroupFilter === "ALL") return true;
        if (currentGroupFilter === "MAG7") return s.group_name === "MAG7" || s.group_name === "SOX_MAG7";
        if (currentGroupFilter === "SOX") return s.group_name === "SOX" || s.group_name === "SOX_MAG7";
        if (currentGroupFilter === "BENCHMARK") return s.group_name === "BENCHMARK";
        return true;
      }).sort();

      filteredSymbols.forEach(sym => {
        const opt = document.createElement("option");
        opt.value = sym;
        opt.textContent = `${sym} - ${STOCKS_DATA[sym].name} (${STOCKS_DATA[sym].group_name})`;
        sel.appendChild(opt);
      });

      if (filteredSymbols.includes(currentSymbol)) {
        sel.value = currentSymbol;
      }
    }

    // -------------------------------------------------------------
    // Stock Switcher & Main Chart
    // -------------------------------------------------------------
    function switchStock(sym) {
      if (!STOCKS_DATA[sym]) return;
      currentSymbol = sym;
      document.getElementById("stock-select").value = sym;

      // Update Quick Chips
      document.querySelectorAll("#quick-chips .chip").forEach(c => {
        if (c.dataset.sym === sym) {
          c.classList.add("bg-emerald-600", "text-slate-950", "font-black");
          c.classList.remove("text-slate-200");
        } else {
          c.classList.remove("bg-emerald-600", "text-slate-950", "font-black");
          c.classList.add("text-slate-200");
        }
      });

      const sData = STOCKS_DATA[sym];
      document.getElementById("stock-sym-badge").textContent = sym;
      document.getElementById("stock-name-badge").textContent = sData.name;

      // Badges
      let grpLabel = sData.group_name;
      if (sData.group_name === "SOX_MAG7") grpLabel = "SOX & Mag 7 雙重龍頭";
      else if (sData.group_name === "MAG7") grpLabel = "Mag 7 科技巨頭";
      else if (sData.group_name === "SOX") grpLabel = "SOX 半導體成分股";
      else if (sData.group_name === "BENCHMARK") grpLabel = "基準指數 / ETF";
      document.getElementById("stock-group-badge").textContent = grpLabel;

      const archInfo = ARCHETYPE_CONFIG[sData.archetype_code] || { name: sData.archetype_code, color: "#94a3b8" };
      const archBadge = document.getElementById("stock-arch-badge");
      archBadge.textContent = archInfo.name;
      archBadge.style.color = archInfo.color;
      archBadge.style.borderColor = archInfo.color;

      document.getElementById("stock-meta-info").textContent = 
        `年化報酬 (CAGR): ${sData.cagr_pct > 0 ? '+' : ''}${sData.cagr_pct}% | 年化波動率: ${sData.ann_vol_pct}% | 中位數 HV60: ${sData.median_hv60_pct}% | 最大回撤: ${sData.max_dd_pct}% | 夏普比率: ${sData.sharpe_ratio} | 總週期數: ${sData.periods.length} 個`;

      renderRegimeDistributionChips(sData);
      renderStockPeriodsTable(sData);
      renderMainChart(sData);

      // Reset HUD
      const lastIdx = sData.dates.length - 1;
      updateHUD(sData, lastIdx);
    }

    function renderRegimeDistributionChips(sData) {
      const counts = {
        TYPE1_STEADY_BULL: 0,
        TYPE2_MOMENTUM_CLIMAX: 0,
        TYPE3_SQUEEZE_BASE: 0,
        TYPE4_BATTLEGROUND_CHOP: 0,
        TYPE5_PANIC_LIQUIDATION: 0,
        TYPE6_DESPAIR_BLEED: 0
      };
      sData.regime.forEach(r => { if (counts[r] !== undefined) counts[r]++; });
      const total = sData.regime.length;

      const container = document.getElementById("regime-dist-chips");
      container.innerHTML = "";
      Object.keys(REGIME_CONFIG).forEach(k => {
        const cnt = counts[k] || 0;
        const pct = total > 0 ? (cnt / total * 100).toFixed(1) : "0.0";
        const cfg = REGIME_CONFIG[k];
        const chip = document.createElement("div");
        chip.className = `px-2.5 py-1 rounded-xl text-xs font-semibold flex items-center gap-1 border`;
        chip.style.backgroundColor = cfg.bg;
        chip.style.borderColor = cfg.color;
        chip.style.color = cfg.color;
        chip.innerHTML = `<span>${cfg.short}</span> <span class="text-white font-mono">${pct}%</span> <span class="text-slate-400 text-[10px]">(${cnt}d)</span>`;
        container.appendChild(chip);
      });
    }

    function renderStockPeriodsTable(sData) {
      const tbody = document.getElementById("stock-periods-tbody");
      tbody.innerHTML = "";
      document.getElementById("stock-period-count").textContent = `共 ${sData.periods.length} 個週期`;

      sData.periods.forEach(p => {
        const tr = document.createElement("tr");
        tr.className = "hover:bg-slate-800/60 cursor-pointer transition";
        tr.onclick = () => focusPeriod(p.start_date, p.end_date, p.session_id);

        const retClass = p.period_return_pct >= 0 ? "text-emerald-400" : "text-rose-400";
        const retSign = p.period_return_pct >= 0 ? "+" : "";
        const annClass = p.annualized_return_pct >= 0 ? "text-emerald-400" : "text-rose-400";
        const annSign = p.annualized_return_pct >= 0 ? "+" : "";

        tr.innerHTML = `
          <td class="px-3 py-2 font-bold text-slate-100">${p.session_id}</td>
          <td class="px-3 py-2">
            <span class="px-2 py-0.5 rounded text-[11px] font-semibold border" style="background:${p.bg_color}; color:${p.color}; border-color:${p.color}">
              ${p.regime_short_zh}
            </span>
          </td>
          <td class="px-3 py-2 text-slate-400">${p.start_date}</td>
          <td class="px-3 py-2 text-slate-400">${p.end_date}</td>
          <td class="px-3 py-2 text-right text-slate-300">${p.duration_days}d</td>
          <td class="px-3 py-2 text-right text-slate-300">$${p.start_price.toFixed(2)}</td>
          <td class="px-3 py-2 text-right text-slate-300">$${p.end_price.toFixed(2)}</td>
          <td class="px-3 py-2 text-right font-bold ${retClass}">${retSign}${p.period_return_pct.toFixed(2)}%</td>
          <td class="px-3 py-2 text-right font-medium ${annClass}">${annSign}${p.annualized_return_pct.toFixed(1)}%</td>
          <td class="px-3 py-2 text-right text-rose-400">${p.max_drawdown_pct.toFixed(2)}%</td>
          <td class="px-3 py-2 text-right text-emerald-400">+${p.max_runup_pct.toFixed(2)}%</td>
          <td class="px-3 py-2 text-right text-amber-300">${p.annualized_vol_pct.toFixed(1)}%</td>
          <td class="px-3 py-2 text-right text-cyan-300 font-bold">${p.sharpe_ratio.toFixed(2)}</td>
          <td class="px-3 py-2 text-right text-purple-300">${p.avg_rvol.toFixed(2)}x</td>
          <td class="px-3 py-2 text-center">
            <button class="px-2 py-0.5 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold rounded text-[10px]">
              <i class="fa-solid fa-magnifying-glass-plus"></i> 聚焦
            </button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    function renderMainChart(sData) {
      // 1. Candlestick
      const traceCandle = {
        type: 'candlestick',
        x: sData.dates,
        open: sData.open,
        high: sData.high,
        low: sData.low,
        close: sData.close,
        name: 'OHLC',
        increasing: { line: { color: '#10b981', width: 1 }, fillcolor: '#10b981' },
        decreasing: { line: { color: '#ef4444', width: 1 }, fillcolor: '#ef4444' },
        xaxis: 'x',
        yaxis: 'y1'
      };

      // 2. Invisible trace for Unified Hover Session ID display
      const traceSession = {
        type: 'scatter',
        mode: 'lines',
        x: sData.dates,
        y: sData.close,
        name: 'Session ID',
        text: sData.session_id,
        hovertemplate: '<b style="color:#38bdf8;">%{text}</b><br>收盤價: $%{y:.2f}<extra></extra>',
        line: { color: 'rgba(0,0,0,0)', width: 0.001 },
        showlegend: false,
        xaxis: 'x',
        yaxis: 'y1'
      };

      // 3. Quarterly Drift mu_60 (%)
      const traceRet60 = {
        type: 'scatter',
        mode: 'lines',
        x: sData.dates,
        y: sData.ret60,
        name: 'μ60 Quarterly Drift (%)',
        line: { color: '#06b6d4', width: 1.5 },
        hovertemplate: 'μ60 Drift: %{y:.2f}%<extra></extra>',
        xaxis: 'x',
        yaxis: 'y2'
      };

      // 4. Realized Volatility sigma_60 (%)
      const traceHV60 = {
        type: 'scatter',
        mode: 'lines',
        x: sData.dates,
        y: sData.hv60,
        name: 'σ60 Realized Vol (%)',
        line: { color: '#f59e0b', width: 1.5 },
        hovertemplate: 'σ60 Vol: %{y:.2f}%<extra></extra>',
        xaxis: 'x',
        yaxis: 'y3'
      };

      // 5. Volume Bar
      const traceVolume = {
        type: 'bar',
        x: sData.dates,
        y: sData.volume,
        name: '成交量 Volume',
        marker: {
          color: sData.close.map((c, i) => i === 0 || c >= sData.close[i-1] ? 'rgba(16, 185, 129, 0.45)' : 'rgba(239, 68, 68, 0.45)')
        },
        hovertemplate: 'Volume: %{y:,.0f}<extra></extra>',
        xaxis: 'x',
        yaxis: 'y4'
      };

      // Background shapes for the 6 Macro Regimes (contiguous with zero gaps)
      const shapes = [];
      sData.periods.forEach((p, idx) => {
        const nextP = sData.periods[idx + 1];
        const x1Val = nextP ? nextP.start_date : p.end_date;
        shapes.push({
          type: 'rect',
          xref: 'x',
          yref: 'paper',
          x0: p.start_date,
          x1: x1Val,
          y0: 0,
          y1: 1,
          fillcolor: p.bg_color,
          line: { width: 0 },
          layer: 'below'
        });
        // Period boundary vertical line
        shapes.push({
          type: 'line',
          xref: 'x',
          yref: 'paper',
          x0: p.start_date,
          x1: p.start_date,
          y0: 0,
          y1: 1,
          line: { color: 'rgba(255, 255, 255, 0.12)', width: 1, dash: 'dot' },
          layer: 'below'
        });
      });

      // Threshold reference lines for mu60 and sigma60
      shapes.push(
        // mu_60 +10% Bull boundary
        {
          type: 'line', xref: 'paper', yref: 'y2',
          x0: 0, x1: 1, y0: 10, y1: 10,
          line: { color: 'rgba(16, 185, 129, 0.6)', width: 1, dash: 'dash' }
        },
        // mu_60 -10% Bear boundary
        {
          type: 'line', xref: 'paper', yref: 'y2',
          x0: 0, x1: 1, y0: -10, y1: -10,
          line: { color: 'rgba(239, 68, 68, 0.6)', width: 1, dash: 'dash' }
        },
        // mu_60 0% Zero line
        {
          type: 'line', xref: 'paper', yref: 'y2',
          x0: 0, x1: 1, y0: 0, y1: 0,
          line: { color: 'rgba(148, 163, 184, 0.3)', width: 1 }
        },
        // sigma_60 35% Vol boundary
        {
          type: 'line', xref: 'paper', yref: 'y3',
          x0: 0, x1: 1, y0: 35, y1: 35,
          line: { color: 'rgba(245, 158, 11, 0.7)', width: 1.2, dash: 'dash' }
        }
      );

      const layout = {
        grid: {
          rows: 4,
          columns: 1,
          pattern: 'independent',
          roworder: 'top to bottom'
        },
        shapes: shapes,
        paper_bgcolor: '#0f172a',
        plot_bgcolor: '#0f172a',
        font: { color: '#94a3b8', family: 'ui-sans-serif, system-ui, sans-serif', size: 11 },
        showlegend: false,
        hovermode: 'x unified',
        margin: { l: 60, r: 40, t: 10, b: 40 },
        xaxis: {
          type: 'date',
          rangeslider: { visible: false },
          gridcolor: '#1e293b',
          linecolor: '#334155',
          showspikes: true,
          spikethickness: 1,
          spikedash: 'dot',
          spikecolor: '#94a3b8',
          spikemode: 'across'
        },
        yaxis: {
          domain: [0.52, 1.0],
          gridcolor: '#1e293b',
          linecolor: '#334155',
          title: { text: '價格 (USD)', font: { size: 10 } }
        },
        yaxis2: {
          domain: [0.35, 0.50],
          gridcolor: '#1e293b',
          linecolor: '#334155',
          title: { text: 'μ60 動量 (%)', font: { size: 9 } }
        },
        yaxis3: {
          domain: [0.18, 0.33],
          gridcolor: '#1e293b',
          linecolor: '#334155',
          title: { text: 'σ60 波動 (%)', font: { size: 9 } }
        },
        yaxis4: {
          domain: [0.0, 0.15],
          gridcolor: '#1e293b',
          linecolor: '#334155',
          title: { text: '成交量', font: { size: 9 } }
        }
      };

      const config = {
        responsive: true,
        displayModeBar: true,
        displaylogo: false,
        modeBarButtonsToRemove: ['select2d', 'lasso2d']
      };

      Plotly.newPlot('chart-div', [traceCandle, traceSession, traceRet60, traceHV60, traceVolume], layout, config);

      // Real-time HUD update on hover
      const chartEl = document.getElementById('chart-div');
      chartEl.on('plotly_hover', data => {
        if (!data || !data.points || data.points.length === 0) return;
        const pt = data.points[0];
        const dateStr = pt.x;
        const idx = sData.dates.indexOf(dateStr);
        if (idx !== -1) {
          updateHUD(sData, idx);
        }
      });
    }

    function updateHUD(sData, idx) {
      if (idx < 0 || idx >= sData.dates.length) return;
      document.getElementById('hud-date').textContent = sData.dates[idx];
      document.getElementById('hud-open').textContent = `$${sData.open[idx].toFixed(2)}`;
      document.getElementById('hud-high').textContent = `$${sData.high[idx].toFixed(2)}`;
      document.getElementById('hud-low').textContent = `$${sData.low[idx].toFixed(2)}`;
      document.getElementById('hud-close').textContent = `$${sData.close[idx].toFixed(2)}`;

      const retVal = sData.ret60[idx];
      document.getElementById('hud-ret60').textContent = retVal !== null ? `${retVal > 0 ? '+' : ''}${retVal.toFixed(1)}%` : '--';

      const hvVal = sData.hv60[idx];
      document.getElementById('hud-hv60').textContent = hvVal !== null ? `${hvVal.toFixed(1)}%` : '--';

      const rvolVal = sData.rvol60[idx];
      document.getElementById('hud-rvol').textContent = rvolVal !== null ? `${rvolVal.toFixed(2)}x` : '--';

      const sessId = sData.session_id[idx] || `${sData.symbol}_PV000`;
      document.getElementById('hud-session-text').textContent = sessId;

      const reg = sData.regime[idx];
      const cfg = REGIME_CONFIG[reg];
      const badge = document.getElementById('hud-session-badge');
      if (cfg) {
        badge.style.backgroundColor = cfg.bg;
        badge.style.color = cfg.color;
        badge.style.borderColor = cfg.border;
      }
    }

    function focusPeriod(startDate, endDate, sessionId) {
      switchTab('chart');
      const sDate = new Date(startDate);
      const eDate = new Date(endDate);
      // Add a 10-day buffer around the period
      sDate.setDate(sDate.getDate() - 10);
      eDate.setDate(eDate.getDate() + 10);

      Plotly.relayout('chart-div', {
        'xaxis.range': [sDate.toISOString().split('T')[0], eDate.toISOString().split('T')[0]]
      });

      document.getElementById('hud-session-text').textContent = sessionId;
    }

    function resetZoom() {
      Plotly.relayout('chart-div', { 'xaxis.autorange': true, 'yaxis.autorange': true });
    }

    // -------------------------------------------------------------
    // TAB 2: SOX VS MAG 7 MARKET-WIDE COMPARISON
    // -------------------------------------------------------------
    function renderCompareTab() {
      // 1. KPI Cards
      const kpiContainer = document.getElementById("kpi-banner-cards");
      kpiContainer.innerHTML = "";

      const mag7Row = SOX_MAG7_SUMMARY.find(r => r.group_name === "MAG7") || {};
      const soxRow = SOX_MAG7_SUMMARY.find(r => r.group_name === "SOX") || {};
      const nvdaRow = SOX_MAG7_SUMMARY.find(r => r.group_name === "SOX_MAG7") || {};
      const benchRow = SOX_MAG7_SUMMARY.find(r => r.group_name === "BENCHMARK") || {};

      const cards = [
        {
          title: "Mag 7 科技巨頭 (6檔)",
          cagr: `${mag7Row.avg_cagr_pct}%`,
          vol: `${mag7Row.avg_ann_vol_pct}%`,
          sharpe: `${mag7Row.avg_sharpe_ratio}`,
          mdd: `${mag7Row.avg_max_dd_pct}%`,
          lowVolPct: `${mag7Row.pct_low_vol_regimes}%`,
          tag: "低波複利王 (A原型支配)",
          color: "border-emerald-500",
          textColor: "text-emerald-400"
        },
        {
          title: "SOX 30 半導體族群 (29檔)",
          cagr: `${soxRow.avg_cagr_pct}%`,
          vol: `${soxRow.avg_ann_vol_pct}%`,
          sharpe: `${soxRow.avg_sharpe_ratio}`,
          mdd: `${soxRow.avg_max_dd_pct}%`,
          lowVolPct: `${soxRow.pct_low_vol_regimes}%`,
          tag: "高波動高Beta (75%高波)",
          color: "border-amber-500",
          textColor: "text-amber-400"
        },
        {
          title: "NVDA (雙重身份龍頭)",
          cagr: `+${nvdaRow.avg_cagr_pct}%`,
          vol: `${nvdaRow.avg_ann_vol_pct}%`,
          sharpe: `${nvdaRow.avg_sharpe_ratio}`,
          mdd: `${nvdaRow.avg_max_dd_pct}%`,
          lowVolPct: `${nvdaRow.pct_low_vol_regimes}%`,
          tag: "AI 主升狂飆 (B原型神話)",
          color: "border-cyan-500",
          textColor: "text-cyan-400"
        },
        {
          title: "市場基準 (^SOX, SOXX, QQQ)",
          cagr: `${benchRow.avg_cagr_pct}%`,
          vol: `${benchRow.avg_ann_vol_pct}%`,
          sharpe: `${benchRow.avg_sharpe_ratio}`,
          mdd: `${benchRow.avg_max_dd_pct}%`,
          lowVolPct: `${benchRow.pct_low_vol_regimes}%`,
          tag: "全市場基準 (夏普 0.61)",
          color: "border-purple-500",
          textColor: "text-purple-400"
        }
      ];

      cards.forEach(c => {
        const div = document.createElement("div");
        div.className = `glass-card rounded-2xl p-4 border-l-4 ${c.color} space-y-2`;
        div.innerHTML = `
          <div class="flex items-center justify-between">
            <span class="text-xs font-bold text-slate-300">${c.title}</span>
            <span class="text-[10px] px-2 py-0.5 rounded font-semibold bg-slate-800 text-slate-300">${c.tag}</span>
          </div>
          <div class="grid grid-cols-3 gap-2 pt-1 font-mono">
            <div>
              <div class="text-[10px] text-slate-500 uppercase">CAGR</div>
              <div class="text-base font-black ${c.textColor}">${c.cagr}</div>
            </div>
            <div>
              <div class="text-[10px] text-slate-500 uppercase">實現波動率</div>
              <div class="text-sm font-bold text-slate-200">${c.vol}</div>
            </div>
            <div>
              <div class="text-[10px] text-slate-500 uppercase">夏普比率</div>
              <div class="text-base font-black text-cyan-300">${c.sharpe}</div>
            </div>
          </div>
          <div class="flex items-center justify-between text-[11px] text-slate-400 pt-1 border-t border-slate-800/80">
            <span>最大回撤: <b class="text-rose-400 font-mono">${c.mdd}</b></span>
            <span>低波時間: <b class="text-emerald-400 font-mono">${c.lowVolPct}</b></span>
          </div>
        `;
        kpiContainer.appendChild(div);
      });

      // 2. Render Scatter Plot
      renderScatterPlot();

      // 3. Render 6-Regime Allocation Stacked Bar
      renderRegimeAllocationBar();

      // 4. Render Archetype Breakdown Bar
      renderArchetypeBreakdownBar();

      // 5. Render Summary Table
      renderSoxSummaryTable();
    }

    function setScatterColorMode(mode) {
      scatterColorMode = mode;
      document.getElementById("scat-grp-btn").className = mode === "GROUP" ? "px-2.5 py-1 rounded bg-sky-600 text-white font-medium" : "px-2.5 py-1 rounded bg-slate-800 text-slate-300 hover:bg-slate-700 transition";
      document.getElementById("scat-arch-btn").className = mode === "ARCHETYPE" ? "px-2.5 py-1 rounded bg-purple-600 text-white font-medium" : "px-2.5 py-1 rounded bg-slate-800 text-slate-300 hover:bg-slate-700 transition";
      renderScatterPlot();
    }

    function renderScatterPlot() {
      const validStocks = STOCK_ARCHETYPES.filter(s => s.total_bars >= 60);

      const GROUP_COLORS = {
        "MAG7": "#10b981",       // Emerald
        "SOX": "#f59e0b",        // Amber
        "SOX_MAG7": "#06b6d4",   // Cyan
        "BENCHMARK": "#a855f7"   // Purple
      };

      const ARCH_COLORS = {
        "A_LOWVOL_TITAN": "#10b981",
        "B_HYPERGROWTH_MOMENTUM": "#f59e0b",
        "C_CYCLICAL_EQUIPMENT": "#0ea5e9",
        "D_HIGHBETA_SPECULATIVE": "#ef4444",
        "E_MATURE_CASHCOW": "#8b5cf6",
        "BENCHMARK": "#94a3b8"
      };

      const trace = {
        type: 'scatter',
        mode: 'markers+text',
        x: validStocks.map(s => s.ann_vol_pct),
        y: validStocks.map(s => s.cagr_pct),
        text: validStocks.map(s => s.symbol),
        textposition: 'top center',
        textfont: { size: 10, color: '#f8fafc', family: 'ui-sans-serif, sans-serif' },
        marker: {
          size: validStocks.map(s => Math.max(12, Math.min(36, (s.sharpe_ratio + 0.3) * 22))),
          color: validStocks.map(s => scatterColorMode === "GROUP" ? GROUP_COLORS[s.group_name] : ARCH_COLORS[s.archetype_code]),
          opacity: 0.85,
          line: { color: '#ffffff', width: 1.2 }
        },
        hovertemplate: 
          '<b>%{text}</b> (%{customdata[0]})<br>' +
          '原型: %{customdata[1]}<br>' +
          '年化波動率 σ: %{x:.1f}%<br>' +
          '年化報酬率 CAGR: %{y:.1f}%<br>' +
          '中位數 HV60: %{customdata[2]:.1f}%<br>' +
          '夏普比率: %{customdata[3]:.2f}<br>' +
          '最大回撤: %{customdata[4]:.1f}%<extra></extra>',
        customdata: validStocks.map(s => [s.group_name, s.archetype_name_zh, s.median_hv60_pct, s.sharpe_ratio, s.max_dd_pct])
      };

      const layout = {
        paper_bgcolor: '#0f172a',
        plot_bgcolor: '#0f172a',
        font: { color: '#94a3b8' },
        margin: { l: 60, r: 40, t: 30, b: 50 },
        xaxis: {
          title: '年化實現波動率 σ (%)',
          gridcolor: '#1e293b',
          linecolor: '#334155',
          zerolinecolor: '#334155'
        },
        yaxis: {
          title: '年化複合報酬率 CAGR (%)',
          gridcolor: '#1e293b',
          linecolor: '#334155',
          zerolinecolor: '#475569'
        },
        shapes: [
          // 35% Volatility Barrier
          {
            type: 'line',
            x0: 35, x1: 35, y0: -20, y1: 70,
            line: { color: 'rgba(245, 158, 11, 0.6)', width: 1.5, dash: 'dash' }
          }
        ],
        annotations: [
          {
            x: 35, y: 65, xref: 'x', yref: 'y',
            text: '35% 低波 vs 高波分水嶺',
            showarrow: true, arrowhead: 2, ax: 40, ay: -20,
            font: { color: '#f59e0b', size: 10 }
          }
        ]
      };

      Plotly.newPlot('scatter-chart-div', [trace], layout, { responsive: true, displayModeBar: false });

      // Click on bubble switches to stock
      document.getElementById('scatter-chart-div').on('plotly_click', data => {
        if (data.points && data.points.length > 0) {
          const sym = data.points[0].text;
          switchStock(sym);
          switchTab('chart');
        }
      });
    }

    function renderRegimeAllocationBar() {
      const groups = ["MAG7", "SOX", "SOX_MAG7", "BENCHMARK"];
      const groupLabels = ["Mag 7 (6檔)", "SOX 30 (29檔)", "NVDA (雙重)", "基準 (3檔)"];

      const traces = [];
      Object.keys(REGIME_CONFIG).forEach(k => {
        const cfg = REGIME_CONFIG[k];
        const values = groups.map(grp => {
          const row = SOX_MAG7_SUMMARY.find(r => r.group_name === grp);
          if (!row) return 0;
          if (k === "TYPE1_STEADY_BULL") return row.pct_t1_steady;
          if (k === "TYPE2_MOMENTUM_CLIMAX") return row.pct_t2_climax;
          if (k === "TYPE3_SQUEEZE_BASE") return row.pct_t3_squeeze;
          if (k === "TYPE4_BATTLEGROUND_CHOP") return row.pct_t4_chop;
          if (k === "TYPE5_PANIC_LIQUIDATION") return row.pct_t5_panic;
          if (k === "TYPE6_DESPAIR_BLEED") return row.pct_t6_bleed;
          return 0;
        });

        traces.push({
          x: groupLabels,
          y: values,
          name: cfg.short,
          type: 'bar',
          marker: { color: cfg.color }
        });
      });

      const layout = {
        barmode: 'stack',
        paper_bgcolor: '#0f172a',
        plot_bgcolor: '#0f172a',
        font: { color: '#94a3b8', size: 11 },
        margin: { l: 50, r: 20, t: 20, b: 40 },
        legend: { orientation: 'h', y: -0.2 },
        yaxis: { title: '時間佔比 (%)', gridcolor: '#1e293b', range: [0, 100] },
        xaxis: { gridcolor: '#1e293b' }
      };

      Plotly.newPlot('regime-bar-chart-div', traces, layout, { responsive: true, displayModeBar: false });
    }

    function renderArchetypeBreakdownBar() {
      const groups = ["MAG7", "SOX", "SOX_MAG7", "BENCHMARK"];
      const groupLabels = ["Mag 7 (6檔)", "SOX 30 (29檔)", "NVDA (雙重)", "基準 (3檔)"];

      const archCodes = ["A_LOWVOL_TITAN", "B_HYPERGROWTH_MOMENTUM", "C_CYCLICAL_EQUIPMENT", "D_HIGHBETA_SPECULATIVE", "E_MATURE_CASHCOW", "BENCHMARK"];

      const traces = [];
      archCodes.forEach(code => {
        const cfg = ARCHETYPE_CONFIG[code];
        const values = groups.map(grp => {
          const sub = STOCK_ARCHETYPES.filter(s => s.group_name === grp);
          if (sub.length === 0) return 0;
          const matchCount = sub.filter(s => s.archetype_code === code).length;
          return round2(matchCount / sub.length * 100);
        });

        traces.push({
          x: groupLabels,
          y: values,
          name: cfg.short,
          type: 'bar',
          marker: { color: cfg.color }
        });
      });

      const layout = {
        barmode: 'stack',
        paper_bgcolor: '#0f172a',
        plot_bgcolor: '#0f172a',
        font: { color: '#94a3b8', size: 11 },
        margin: { l: 50, r: 20, t: 20, b: 40 },
        legend: { orientation: 'h', y: -0.2 },
        yaxis: { title: '標的佔比 (%)', gridcolor: '#1e293b', range: [0, 100] },
        xaxis: { gridcolor: '#1e293b' }
      };

      Plotly.newPlot('archetype-bar-chart-div', traces, layout, { responsive: true, displayModeBar: false });
    }

    function renderSoxSummaryTable() {
      const tbody = document.getElementById("sox-vs-mag7-tbody");
      tbody.innerHTML = "";

      SOX_MAG7_SUMMARY.forEach(r => {
        const tr = document.createElement("tr");
        tr.className = "hover:bg-slate-800/60";

        let grpName = r.group_name;
        if (r.group_name === "MAG7") grpName = "科技七巨頭 Mag 7";
        else if (r.group_name === "SOX") grpName = "半導體 SOX 30";
        else if (r.group_name === "SOX_MAG7") grpName = "NVDA (雙重身份)";
        else if (r.group_name === "BENCHMARK") grpName = "市場基準 (^SOX/SOXX/QQQ)";

        tr.innerHTML = `
          <td class="px-4 py-3 font-bold text-white">${grpName}</td>
          <td class="px-3 py-3 text-right text-slate-300 font-bold">${r.stock_count}</td>
          <td class="px-3 py-3 text-right font-black text-emerald-400">+${r.avg_cagr_pct}%</td>
          <td class="px-3 py-3 text-right text-amber-300 font-bold">${r.avg_ann_vol_pct}%</td>
          <td class="px-3 py-3 text-right text-purple-300">${r.avg_median_hv60_pct}%</td>
          <td class="px-3 py-3 text-right text-rose-400 font-bold">${r.avg_max_dd_pct}%</td>
          <td class="px-3 py-3 text-right font-black text-cyan-300 text-sm">${r.avg_sharpe_ratio}</td>
          <td class="px-3 py-3 text-right text-emerald-400">${r.pct_t1_steady}%</td>
          <td class="px-3 py-3 text-right text-amber-400">${r.pct_t2_climax}%</td>
          <td class="px-3 py-3 text-right text-sky-400">${r.pct_t3_squeeze}%</td>
          <td class="px-3 py-3 text-right text-purple-400">${r.pct_t4_chop}%</td>
          <td class="px-3 py-3 text-right text-rose-400">${r.pct_t5_panic}%</td>
          <td class="px-3 py-3 text-right text-slate-400">${r.pct_t6_bleed}%</td>
          <td class="px-3 py-3 font-semibold text-emerald-300">${r.dominant_archetype}</td>
        `;
        tbody.appendChild(tr);
      });
    }

    // -------------------------------------------------------------
    // TAB 3: ARCHETYPES DEEP DIVE
    // -------------------------------------------------------------
    function renderArchetypesTab() {
      // 1. Archetype Cards
      const container = document.getElementById("archetype-desc-cards");
      container.innerHTML = "";

      Object.keys(ARCHETYPE_CONFIG).forEach(code => {
        const cfg = ARCHETYPE_CONFIG[code];
        const matchStocks = STOCK_ARCHETYPES.filter(s => s.archetype_code === code);
        const card = document.createElement("div");
        card.className = "glass-card rounded-2xl p-5 space-y-3 border-t-4";
        card.style.borderColor = cfg.color;

        card.innerHTML = `
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-bold text-white">${cfg.name}</h3>
            <span class="text-xs px-2 py-0.5 rounded font-bold bg-slate-800" style="color:${cfg.color};">${matchStocks.length} 檔標的</span>
          </div>
          <p class="text-xs text-slate-400 leading-relaxed">${cfg.desc}</p>
          <div class="pt-2 border-t border-slate-800">
            <span class="text-[10px] text-slate-500 uppercase font-semibold">代表標的:</span>
            <div class="flex items-center gap-1.5 flex-wrap mt-1">
              ${matchStocks.map(s => `
                <button onclick="switchStock('${s.symbol}'); switchTab('chart');" class="px-2 py-0.5 rounded bg-slate-900 hover:bg-slate-800 text-xs font-mono font-bold text-slate-300 border border-slate-700 transition">
                  ${s.symbol}
                </button>
              `).join('')}
            </div>
          </div>
        `;
        container.appendChild(card);
      });

      renderArchetypeStocksTable();
    }

    function setArchFilter(archCode) {
      currentArchFilter = archCode;
      document.querySelectorAll(".arch-flt-btn").forEach(b => {
        if (b.id === `arch-flt-${archCode}`) {
          b.classList.add("arch-btn-active");
        } else {
          b.classList.remove("arch-btn-active");
        }
      });
      renderArchetypeStocksTable();
    }

    function renderArchetypeStocksTable() {
      const tbody = document.getElementById("archetype-stocks-tbody");
      tbody.innerHTML = "";

      const filtered = STOCK_ARCHETYPES.filter(s => {
        if (currentArchFilter === "ALL") return true;
        return s.archetype_code === currentArchFilter;
      });

      filtered.forEach(s => {
        const tr = document.createElement("tr");
        tr.className = "hover:bg-slate-800/60 cursor-pointer transition";
        tr.onclick = () => { switchStock(s.symbol); switchTab('chart'); };

        const cagrClass = s.cagr_pct >= 0 ? "text-emerald-400" : "text-rose-400";
        const cagrSign = s.cagr_pct >= 0 ? "+" : "";

        tr.innerHTML = `
          <td class="px-3 py-2 font-bold text-slate-100">${s.symbol}</td>
          <td class="px-3 py-2 text-slate-300 font-sans">${s.name}</td>
          <td class="px-3 py-2 text-slate-400">${s.group_name}</td>
          <td class="px-3 py-2 font-semibold" style="color:${ARCHETYPE_CONFIG[s.archetype_code]?.color || '#94a3b8'}">
            ${s.archetype_name_zh}
          </td>
          <td class="px-3 py-2 text-right font-black ${cagrClass}">${cagrSign}${s.cagr_pct}%</td>
          <td class="px-3 py-2 text-right text-amber-300">${s.ann_vol_pct}%</td>
          <td class="px-3 py-2 text-right text-purple-300">${s.median_hv60_pct}%</td>
          <td class="px-3 py-2 text-right text-rose-400 font-semibold">${s.max_dd_pct}%</td>
          <td class="px-3 py-2 text-right font-bold text-cyan-300">${s.sharpe_ratio}</td>
          <td class="px-3 py-2 text-right text-emerald-400">${s.pct_bull}%</td>
          <td class="px-3 py-2 text-right text-rose-400">${s.pct_bear}%</td>
          <td class="px-3 py-2 text-right text-amber-300">${s.pct_high_vol}%</td>
          <td class="px-3 py-2 text-center">
            <button class="px-2 py-0.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded text-[10px] border border-slate-700">
              走勢
            </button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    // -------------------------------------------------------------
    // TAB 4: UNIVERSE PERIOD MATRIX & EXPLORER
    // -------------------------------------------------------------
    function renderPeriodsTab() {
      // 1. Regime Matrix Cards
      const container = document.getElementById("regime-matrix-cards");
      container.innerHTML = "";

      REGIME_SUMMARY.forEach(r => {
        const card = document.createElement("div");
        card.className = "glass-card rounded-2xl p-4 space-y-2 border-t-4";
        card.style.borderColor = r.color;

        card.innerHTML = `
          <div class="flex items-center justify-between">
            <span class="text-xs font-bold text-white">${r.short_zh}</span>
            <span class="text-[10px] px-1.5 py-0.5 rounded font-mono font-bold bg-slate-800" style="color:${r.color};">${r.count_periods} 週期</span>
          </div>
          <div class="space-y-1 font-mono text-xs pt-1">
            <div class="flex justify-between text-slate-400">
              <span>全市場佔比:</span>
              <span class="text-slate-200 font-bold">${r.pct_time}%</span>
            </div>
            <div class="flex justify-between text-slate-400">
              <span>平均天數:</span>
              <span class="text-slate-200">${r.avg_duration_days} 天</span>
            </div>
            <div class="flex justify-between text-slate-400">
              <span>週期報酬:</span>
              <span class="font-bold ${r.avg_return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}">${r.avg_return_pct > 0 ? '+' : ''}${r.avg_return_pct}%</span>
            </div>
            <div class="flex justify-between text-slate-400">
              <span>勝率:</span>
              <span class="text-cyan-300 font-bold">${r.win_rate_pct}%</span>
            </div>
            <div class="flex justify-between text-slate-400">
              <span>夏普比率:</span>
              <span class="text-purple-300 font-bold">${r.avg_sharpe}</span>
            </div>
            <div class="flex justify-between text-slate-400">
              <span>平均回撤:</span>
              <span class="text-rose-400">${r.avg_mdd_pct}%</span>
            </div>
          </div>
        `;
        container.appendChild(card);
      });

      renderExplorerPeriodsTable();
    }

    function setRegimeFilter(regCode) {
      currentRegimeFilter = regCode;
      document.querySelectorAll(".reg-flt-btn").forEach(b => {
        if (b.id === `reg-flt-${regCode}`) {
          b.classList.add("filter-btn-active");
        } else {
          b.classList.remove("filter-btn-active");
        }
      });
      renderExplorerPeriodsTable();
    }

    function renderExplorerPeriodsTable() {
      const tbody = document.getElementById("all-periods-tbody");
      tbody.innerHTML = "";

      const filtered = ALL_PERIODS.filter(p => {
        if (currentRegimeFilter === "ALL") return true;
        return p.regime === currentRegimeFilter;
      });

      document.getElementById("explorer-period-subtitle").textContent = 
        `共顯示 ${filtered.length.toLocaleString()} 個宏觀週期 (全市場總量: 962)`;

      filtered.forEach(p => {
        const tr = document.createElement("tr");
        tr.className = "hover:bg-slate-800/60 cursor-pointer transition";
        tr.onclick = () => {
          switchStock(p.symbol);
          focusPeriod(p.start_date, p.end_date, p.session_id);
        };

        const retClass = p.period_return_pct >= 0 ? "text-emerald-400" : "text-rose-400";
        const retSign = p.period_return_pct >= 0 ? "+" : "";

        tr.innerHTML = `
          <td class="px-3 py-2 font-bold text-white">${p.symbol}</td>
          <td class="px-3 py-2 text-slate-200">${p.session_id}</td>
          <td class="px-3 py-2">
            <span class="px-2 py-0.5 rounded text-[10px] font-semibold" style="background:${p.bg_color}; color:${p.color}; border: 1px solid ${p.color};">
              ${p.regime_short_zh}
            </span>
          </td>
          <td class="px-3 py-2 text-slate-400">${p.start_date}</td>
          <td class="px-3 py-2 text-slate-400">${p.end_date}</td>
          <td class="px-3 py-2 text-right text-slate-300">${p.duration_days}d</td>
          <td class="px-3 py-2 text-right text-slate-300">$${p.start_price.toFixed(2)}</td>
          <td class="px-3 py-2 text-right text-slate-300">$${p.end_price.toFixed(2)}</td>
          <td class="px-3 py-2 text-right font-black ${retClass}">${retSign}${p.period_return_pct.toFixed(2)}%</td>
          <td class="px-3 py-2 text-right text-rose-400">${p.max_drawdown_pct.toFixed(2)}%</td>
          <td class="px-3 py-2 text-right text-emerald-400">+${p.max_runup_pct.toFixed(2)}%</td>
          <td class="px-3 py-2 text-right text-cyan-300 font-bold">${p.sharpe_ratio.toFixed(2)}</td>
          <td class="px-3 py-2 text-right text-amber-300">${p.avg_hv60 ? p.avg_hv60.toFixed(1) + '%' : '--'}</td>
          <td class="px-3 py-2 text-right text-purple-300">${p.avg_rvol ? p.avg_rvol.toFixed(2) + 'x' : '--'}</td>
          <td class="px-3 py-2 text-center">
            <button class="px-2 py-0.5 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold rounded text-[10px]">
              聚焦
            </button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    function round2(v) {
      return Math.round(v * 100) / 100;
    }
  </script>
</body>
</html>
"""

def generate_html_viewer(db_path, out_html_path):
    print(f"Loading data from {db_path}...")
    stocks_data, archetypes, periods, regime_summary, sox_summary = load_data_from_db(db_path)

    print("Serializing JSON payloads...")
    stocks_json = json.dumps(stocks_data, ensure_ascii=False)
    archetypes_json = json.dumps(archetypes, ensure_ascii=False)
    periods_json = json.dumps(periods, ensure_ascii=False)
    regime_json = json.dumps(regime_summary, ensure_ascii=False)
    sox_json = json.dumps(sox_summary, ensure_ascii=False)

    print("Injecting into HTML Template...")
    html_content = HTML_TEMPLATE.replace("__STOCKS_DATA_JSON__", stocks_json)
    html_content = html_content.replace("__STOCK_ARCHETYPES_JSON__", archetypes_json)
    html_content = html_content.replace("__ALL_PERIODS_JSON__", periods_json)
    html_content = html_content.replace("__REGIME_SUMMARY_JSON__", regime_json)
    html_content = html_content.replace("__SOX_MAG7_SUMMARY_JSON__", sox_json)

    os.makedirs(os.path.dirname(out_html_path), exist_ok=True)
    with open(out_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    file_size_mb = os.path.getsize(out_html_path) / (1024 * 1024)
    print(f"Generated Standalone HTML Viewer: {out_html_path} ({file_size_mb:.2f} MB)")

if __name__ == "__main__":
    generate_html_viewer(DB_PATH, OUTPUT_HTML_PATH)
