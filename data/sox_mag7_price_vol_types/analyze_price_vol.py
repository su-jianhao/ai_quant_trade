#!/usr/bin/env python3
"""analyze_price_vol.py

Pure Price & Volatility / Volume (Price & Vol Only) Quantitative Research Engine.
Target Universe: US Semiconductor SOX 30 constituents + Tech Mag 7 (39 assets, 2020-2026).

Methodology & Theoretical Grounding:
1. Pure Physical Dimensions:
   - Price Drift: 60-day rolling price momentum mu_60 = (Close_t / Close_{t-60} - 1.0) * 100%
   - Volatility Diffusion: 60-day annualized realized volatility sigma_60 = std(ln(C_t/C_{t-1})) * sqrt(252) * 100%
   - Relative Volume Intensity: RVol_60 = Volume_t / SMA_60(Volume_t)

2. 6-Regime Macro Classification Matrix:
   - Type 1: 穩健低波主升 (Low-Vol Steady Compounder):  mu > +10%, sigma <= 35%
   - Type 2: 狂熱高波噴出 (High-Vol Momentum Climax):   mu > +10%, sigma > 35%
   - Type 3: 低波壓縮蓄勢 (Low-Vol Squeeze Base):       -10% <= mu <= +10%, sigma <= 35%
   - Type 4: 高波劇烈洗盤 (High-Vol Battleground Chop):  -10% <= mu <= +10%, sigma > 35%
   - Type 5: 高波恐慌瀑布 (High-Vol Panic Liquidation): mu < -10%, sigma > 35%
   - Type 6: 無量陰跌失血 (Low-Vol Despair Bleed):       mu < -10%, sigma <= 35%

3. Macro Smoothing:
   - Topological drift-preserving merger enforcing minimum period duration >= 20 trading days (~1 month).
   - Noise flickers (< 20 days) are absorbed into consistent macroeconomic trends.

4. 5 Stock-Level Archetypes (SOX vs Mag 7 Clustering):
   - A. 低波核心巨頭 (Mega-Cap Low-Vol Titans): AAPL, MSFT, GOOGL, AMZN, META
   - B. 高波狂飆龍頭 (Hyper-Growth Momentum Leaders): NVDA, TSLA, AMD, AVGO, MU, MPWR, TSM
   - C. 週期性資本設備壟斷者 (Cyclical Semi Equipment Giants): ASML, AMAT, LRCX, KLAC, TER
   - D. 高彈性高風險轉機股 (High-Beta Speculative / Turnarounds): ENPH, WOLF, ON, ARM, COHR, GFS, LSCC, MRVL, MKSI
   - E. 成熟現金流成熟製程 (Mature Cash-Cow Tech): INTC, TXN, QCOM, ADI, NXPI, MCHP, CRUS, STM, SWKS, QRVO
   - Benchmarks: ^SOX, SOXX, QQQ

Outputs:
  - SQLite Database: price_vol_analysis.db
  - Structured JSON: price_vol_summary.json
"""

import os
import sys
import json
import sqlite3
import argparse
import numpy as np
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SRC_DB = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "us_sox30_mag7_ohlcv_2020_2026.db"))
DEFAULT_OUT_DB = os.path.join(SCRIPT_DIR, "price_vol_analysis.db")
DEFAULT_OUT_JSON = os.path.join(SCRIPT_DIR, "price_vol_summary.json")

# 6 Macro Regimes Metadata
REGIMES = [
    "TYPE1_STEADY_BULL",
    "TYPE2_MOMENTUM_CLIMAX",
    "TYPE3_SQUEEZE_BASE",
    "TYPE4_BATTLEGROUND_CHOP",
    "TYPE5_PANIC_LIQUIDATION",
    "TYPE6_DESPAIR_BLEED"
]

REGIME_CONFIG = {
    "TYPE1_STEADY_BULL": {
        "code": "TYPE1_STEADY_BULL",
        "name_zh": "穩健低波主升 (Low-Vol Steady Compounder)",
        "short_zh": "穩健主升",
        "drift": "UP",
        "vol": "LOW",
        "color": "#10b981",
        "bg_color": "rgba(16, 185, 129, 0.20)",
        "border_color": "#059669",
        "description": "走勢強勁 (μ > +10%) 且波動平緩 (σ ≤ 35%)。機構法人主導之穩健吸籌主升段，回撤小，夏普比率最高。"
    },
    "TYPE2_MOMENTUM_CLIMAX": {
        "code": "TYPE2_MOMENTUM_CLIMAX",
        "name_zh": "狂熱高波噴出 (High-Vol Momentum Climax)",
        "short_zh": "狂熱噴出",
        "drift": "UP",
        "vol": "HIGH",
        "color": "#f59e0b",
        "bg_color": "rgba(245, 158, 11, 0.20)",
        "border_color": "#d97706",
        "description": "走勢猛烈 (μ > +10%) 且波動劇烈 (σ > 35%)。動量急速狂飆，市場情緒狂熱，爆量衝頂，伴隨大幅震盪與極高 Beta。"
    },
    "TYPE3_SQUEEZE_BASE": {
        "code": "TYPE3_SQUEEZE_BASE",
        "name_zh": "低波壓縮蓄勢 (Low-Vol Squeeze Base)",
        "short_zh": "低波蓄勢",
        "drift": "FLAT",
        "vol": "LOW",
        "color": "#0ea5e9",
        "bg_color": "rgba(14, 165, 233, 0.20)",
        "border_color": "#0284c7",
        "description": "價格橫盤整理 (-10% ≤ μ ≤ +10%) 且波動降至冰點 (σ ≤ 35%)。量縮窒息，長均線聚攏走平，為下一輪大級別趨勢蓄勢醞釀。"
    },
    "TYPE4_BATTLEGROUND_CHOP": {
        "code": "TYPE4_BATTLEGROUND_CHOP",
        "name_zh": "高波劇烈洗盤 (High-Vol Battleground Chop)",
        "short_zh": "劇烈洗盤",
        "drift": "FLAT",
        "vol": "HIGH",
        "color": "#8b5cf6",
        "bg_color": "rgba(139, 92, 246, 0.20)",
        "border_color": "#7c3aed",
        "description": "價格區間震盪無方向 (-10% ≤ μ ≤ +10%) 但波動劇烈 (σ > 35%)。多空多層次拉鋸爭奪，假突破頻繁，趨勢跟隨極易遭受雙巴侵蝕。"
    },
    "TYPE5_PANIC_LIQUIDATION": {
        "code": "TYPE5_PANIC_LIQUIDATION",
        "name_zh": "高波恐慌瀑布 (High-Vol Panic Liquidation)",
        "short_zh": "恐慌瀑布",
        "drift": "DOWN",
        "vol": "HIGH",
        "color": "#ef4444",
        "bg_color": "rgba(239, 68, 68, 0.22)",
        "border_color": "#dc2626",
        "description": "價格失速重挫 (μ < -10%) 且波動率噴發 (σ > 35%)。放量恐慌下殺，流動性枯竭，融資斷頭斷鏈式 cascade 下跌，回撤極深。"
    },
    "TYPE6_DESPAIR_BLEED": {
        "code": "TYPE6_DESPAIR_BLEED",
        "name_zh": "無量陰跌失血 (Low-Vol Despair Bleed)",
        "short_zh": "無量陰跌",
        "drift": "DOWN",
        "vol": "LOW",
        "color": "#64748b",
        "bg_color": "rgba(100, 116, 139, 0.22)",
        "border_color": "#475569",
        "description": "價格持續下跌 (μ < -10%) 且波動度低於 35%。買盤全面退潮枯竭，溫水煮青蛙，持股者在長期絕望中緩慢失血。"
    }
}

DRIFT_OF = {r: REGIME_CONFIG[r]["drift"] for r in REGIMES}

# 5 Stock Archetypes Definition
ARCHETYPE_CONFIG = {
    "A_LOWVOL_TITAN": {
        "code": "A_LOWVOL_TITAN",
        "name_zh": "A. 低波核心巨頭 (Mega-Cap Low-Vol Titans)",
        "short_zh": "低波核心巨頭",
        "color": "#10b981",
        "description": "全球科技超級巨頭，具備壟斷性現金流、廣闊護城河與高定價權。波動率長年壓制在 35% 以下，回撤溫和，夏普比率優異，是投資組合的定海神針。"
    },
    "B_HYPERGROWTH_MOMENTUM": {
        "code": "B_HYPERGROWTH_MOMENTUM",
        "name_zh": "B. 高波狂飆龍頭 (Hyper-Growth Momentum Leaders)",
        "short_zh": "高波狂飆龍頭",
        "color": "#f59e0b",
        "description": "處於 AI 與先進運算超級擴張週期的主升浪龍頭。CAGR 極高 (>30%~60%)，波動率偏高 (>35%~55%)，Type 2 狂熱噴出期佔比巨大，爆發力最強。"
    },
    "C_CYCLICAL_EQUIPMENT": {
        "code": "C_CYCLICAL_EQUIPMENT",
        "name_zh": "C. 週期性資本設備壟斷者 (Cyclical Semi Equipment Giants)",
        "short_zh": "週期資本設備",
        "color": "#0ea5e9",
        "description": "半導體前段製程設備與微影、蝕刻、檢測之不可替代壟斷者。受晶圓廠資本支出 (Capex) 週期顯著驅動，主升段爆發力強，但伴隨顯著的回調消化期。"
    },
    "D_HIGHBETA_SPECULATIVE": {
        "code": "D_HIGHBETA_SPECULATIVE",
        "name_zh": "D. 高彈性高風險轉機股 (High-Beta Speculative / Turnarounds)",
        "short_zh": "高彈性轉機股",
        "color": "#ef4444",
        "description": "高波動、高 Beta、特定新興領域 (SiC/綠能/光電材料) 或轉機題材標的。年化波動率常破 50%~100%，歷史最大回撤深達 -60% 至 -90%，多空暴漲暴跌。"
    },
    "E_MATURE_CASHCOW": {
        "code": "E_MATURE_CASHCOW",
        "name_zh": "E. 成熟現金流成熟製程 (Mature Cash-Cow Tech)",
        "short_zh": "成熟現金流科技",
        "color": "#8b5cf6",
        "description": "類比 IC、微控制器 (MCU)、車用/工控成熟製程晶片或遭遇轉型陣痛的傳統 IDM。營收平穩但成長動能平緩，股價長時間處於低波壓縮或區間洗盤中。"
    },
    "BENCHMARK": {
        "code": "BENCHMARK",
        "name_zh": "基準指數 / 產業 ETF (Market Benchmarks)",
        "short_zh": "基準指數",
        "color": "#94a3b8",
        "description": "美股大盤與半導體全市場基準 (^SOX, SOXX, QQQ)，用於衡量個別股票的 Alpha 與相對強弱。"
    }
}

# Explicit Universe Archetype Mapping
SYMBOL_ARCHETYPE_MAP = {
    # A. Mega-Cap Low-Vol Titans
    "AAPL": "A_LOWVOL_TITAN",
    "MSFT": "A_LOWVOL_TITAN",
    "GOOGL": "A_LOWVOL_TITAN",
    "AMZN": "A_LOWVOL_TITAN",
    "META": "A_LOWVOL_TITAN",
    
    # B. Hyper-Growth Momentum Leaders
    "NVDA": "B_HYPERGROWTH_MOMENTUM",
    "TSLA": "B_HYPERGROWTH_MOMENTUM",
    "AMD": "B_HYPERGROWTH_MOMENTUM",
    "AVGO": "B_HYPERGROWTH_MOMENTUM",
    "MU": "B_HYPERGROWTH_MOMENTUM",
    "MPWR": "B_HYPERGROWTH_MOMENTUM",
    "TSM": "B_HYPERGROWTH_MOMENTUM",
    
    # C. Cyclical Semi Equipment Giants
    "ASML": "C_CYCLICAL_EQUIPMENT",
    "AMAT": "C_CYCLICAL_EQUIPMENT",
    "LRCX": "C_CYCLICAL_EQUIPMENT",
    "KLAC": "C_CYCLICAL_EQUIPMENT",
    "TER": "C_CYCLICAL_EQUIPMENT",
    
    # D. High-Beta Speculative / Turnarounds
    "ENPH": "D_HIGHBETA_SPECULATIVE",
    "WOLF": "D_HIGHBETA_SPECULATIVE",
    "ON": "D_HIGHBETA_SPECULATIVE",
    "ARM": "D_HIGHBETA_SPECULATIVE",
    "COHR": "D_HIGHBETA_SPECULATIVE",
    "GFS": "D_HIGHBETA_SPECULATIVE",
    "LSCC": "D_HIGHBETA_SPECULATIVE",
    "MRVL": "D_HIGHBETA_SPECULATIVE",
    "MKSI": "D_HIGHBETA_SPECULATIVE",
    
    # E. Mature Cash-Cow Tech
    "INTC": "E_MATURE_CASHCOW",
    "TXN": "E_MATURE_CASHCOW",
    "QCOM": "E_MATURE_CASHCOW",
    "ADI": "E_MATURE_CASHCOW",
    "NXPI": "E_MATURE_CASHCOW",
    "MCHP": "E_MATURE_CASHCOW",
    "CRUS": "E_MATURE_CASHCOW",
    "STM": "E_MATURE_CASHCOW",
    "SWKS": "E_MATURE_CASHCOW",
    "QRVO": "E_MATURE_CASHCOW",
    
    # Benchmarks
    "^SOX": "BENCHMARK",
    "SOXX": "BENCHMARK",
    "QQQ": "BENCHMARK"
}

def classify_bar_raw(ret60, hv60, vol_thresh=35.0, drift_up=10.0, drift_down=-10.0):
    """Map continuous drift and diffusion into one of the 6 discrete regimes."""
    if np.isnan(ret60) or np.isnan(hv60):
        return None
    is_bull = (ret60 > drift_up)
    is_bear = (ret60 < drift_down)
    is_flat = not is_bull and not is_bear
    is_high_vol = (hv60 > vol_thresh)
    
    if is_bull and not is_high_vol:
        return "TYPE1_STEADY_BULL"
    elif is_bull and is_high_vol:
        return "TYPE2_MOMENTUM_CLIMAX"
    elif is_flat and not is_high_vol:
        return "TYPE3_SQUEEZE_BASE"
    elif is_flat and is_high_vol:
        return "TYPE4_BATTLEGROUND_CHOP"
    elif is_bear and is_high_vol:
        return "TYPE5_PANIC_LIQUIDATION"
    elif is_bear and not is_high_vol:
        return "TYPE6_DESPAIR_BLEED"
    return None

def get_runs(labels):
    """Extract consecutive identical runs from label list."""
    runs = []
    i = 0
    n = len(labels)
    while i < n:
        j = i
        while j < n and labels[j] == labels[i]:
            j += 1
        runs.append((i, j, labels[i]))
        i = j
    return runs

def smooth_macro_regimes(labels, min_len=20):
    """Enforce minimum regime duration (>= min_len) via topological drift-preserving merger.
    
    Rules:
    1. Terminal boundary regime at the end of dataset with >= 5 bars is preserved.
    2. Short runs (< min_len) are merged into neighbors.
    3. Prefer merging into neighbor sharing the SAME underlying drift (UP, FLAT, DOWN).
    4. Otherwise, merge into the longer neighbor.
    """
    res = list(labels)
    changed = True
    iterations = 0
    n = len(res)
    
    while changed and iterations < 2000:
        changed = False
        iterations += 1
        runs = get_runs(res)
        short_runs = []
        for r in runs:
            if r[1] == n and (r[1] - r[0]) >= 5:
                continue
            if (r[1] - r[0]) < min_len:
                short_runs.append(r)
        if not short_runs:
            break
            
        short_runs.sort(key=lambda r: r[1] - r[0])
        st, end, val = short_runs[0]
        prev_val = res[st - 1] if st > 0 else None
        next_val = res[end] if end < n else None
        
        if prev_val is None and next_val is None:
            break
        elif prev_val is None:
            rep = next_val
        elif next_val is None:
            rep = prev_val
        elif prev_val == next_val:
            rep = prev_val
        else:
            val_drift = DRIFT_OF[val]
            prev_drift = DRIFT_OF[prev_val]
            next_drift = DRIFT_OF[next_val]
            
            # Topological preference: merge with same drift neighbor first
            if prev_drift == val_drift and next_drift != val_drift:
                rep = prev_val
            elif next_drift == val_drift and prev_drift != val_drift:
                rep = next_val
            else:
                prev_len = st - next(r[0] for r in runs if r[1] == st)
                next_len = next(r[1] for r in runs if r[0] == end) - end
                rep = prev_val if prev_len >= next_len else next_val
                
        for k in range(st, end):
            res[k] = rep
        changed = True
        
    return res

def run_price_vol_analysis(src_db_path, out_db_path, out_json_path, min_duration=20, vol_thresh=35.0):
    print(f"================================================================================")
    print(f" Starting Pure Price & Vol Analysis (Threshold sigma={vol_thresh}%, min_len={min_duration}d)")
    print(f" Source DB : {src_db_path}")
    print(f" Output DB : {out_db_path}")
    print(f" Output JSON: {out_json_path}")
    print(f"================================================================================")

    if not os.path.exists(src_db_path):
        raise FileNotFoundError(f"Source database not found at {src_db_path}")

    # Connect to source database
    src_conn = sqlite3.connect(src_db_path)
    meta_df = pd.read_sql("SELECT symbol, name, sector, is_sox_constituent, is_mag7, is_benchmark FROM universe_metadata", src_conn)
    meta_dict = meta_df.set_index("symbol").to_dict(orient="index")
    
    ohlcv_df = pd.read_sql("SELECT symbol, date, open, high, low, close, volume FROM stock_ohlcv ORDER BY symbol, date ASC", src_conn)
    src_conn.close()

    total_symbols = ohlcv_df["symbol"].nunique()
    print(f"Loaded {len(ohlcv_df):,} bars across {total_symbols} symbols.")

    all_bar_records = []
    all_period_records = []
    stock_metrics = {}

    for sym, group in ohlcv_df.groupby("symbol"):
        group = group.sort_values("date").reset_index(drop=True)
        m_info = meta_dict.get(sym, {})
        is_sox = bool(m_info.get("is_sox_constituent", 0))
        is_mag7 = bool(m_info.get("is_mag7", 0))
        is_bench = bool(m_info.get("is_benchmark", 0))

        if is_bench:
            group_name = "BENCHMARK"
        elif is_sox and is_mag7:
            group_name = "SOX_MAG7"
        elif is_mag7:
            group_name = "MAG7"
        else:
            group_name = "SOX"

        archetype_code = SYMBOL_ARCHETYPE_MAP.get(sym, "E_MATURE_CASHCOW")
        arch_cfg = ARCHETYPE_CONFIG.get(archetype_code, ARCHETYPE_CONFIG["E_MATURE_CASHCOW"])

        n_bars = len(group)
        if n_bars < 60:
            print(f"⚠️ Warning: {sym} has only {n_bars} bars (< 60 warmup required). Skipping rolling calculations.")
            stock_metrics[sym] = {
                "symbol": sym,
                "name": m_info.get("name", sym),
                "sector": m_info.get("sector", "Technology"),
                "group_name": group_name,
                "is_sox": int(is_sox),
                "is_mag7": int(is_mag7),
                "is_benchmark": int(is_bench),
                "archetype_code": archetype_code,
                "archetype_name_zh": arch_cfg["name_zh"],
                "total_bars": n_bars,
                "cagr_pct": 0.0,
                "ann_vol_pct": 0.0,
                "median_hv60_pct": 0.0,
                "max_dd_pct": 0.0,
                "sharpe_ratio": 0.0,
                "pct_t1": 0.0,
                "pct_t2": 0.0,
                "pct_t3": 0.0,
                "pct_t4": 0.0,
                "pct_t5": 0.0,
                "pct_t6": 0.0,
                "pct_bull": 0.0,
                "pct_bear": 0.0,
                "pct_high_vol": 0.0,
                "pct_low_vol": 0.0,
                "total_periods": 0,
                "note": "Insufficient history (< 60 bars)"
            }
            continue

        c = group["close"]
        v = group["volume"]

        # Feature Engineering: Price & Vol Only (with expanding warmup so zero dates are unclassified)
        ret60 = (c / c.shift(60) - 1.0) * 100.0
        ret60 = ret60.fillna((c / c.iloc[0] - 1.0) * 100.0)
        log_ret = np.log(c / c.shift(1))
        hv60 = (log_ret.rolling(60, min_periods=5).std() * np.sqrt(252) * 100.0).bfill().ffill()
        sma_vol60 = v.rolling(60, min_periods=1).mean()
        rvol60 = v / sma_vol60.replace(0, np.nan)
        rvol60 = rvol60.fillna(1.0)

        # Raw classification (every bar from day 0 is classified)
        raw_regimes = [classify_bar_raw(r, h, vol_thresh=vol_thresh) for r, h in zip(ret60, hv60)]

        df_valid = group.reset_index(drop=True)
        ret60_valid = ret60.reset_index(drop=True)
        hv60_valid = hv60.reset_index(drop=True)
        rvol60_valid = rvol60.reset_index(drop=True)
        raw_valid = raw_regimes

        # Macro Smoothing
        smoothed_regimes = smooth_macro_regimes(raw_valid, min_len=min_duration)
        runs = get_runs(smoothed_regimes)

        # Build Period Records
        period_idx_map = {}
        for p_idx, (p_st, p_end, reg) in enumerate(runs, 1):
            pid = f"{sym}_PV{p_idx:03d}"
            reg_info = REGIME_CONFIG[reg]
            sess_id = f"{pid} [{reg_info['short_zh']}]"

            sub_c = df_valid["close"].iloc[p_st:p_end]
            sub_ret60 = ret60_valid.iloc[p_st:p_end]
            sub_hv60 = hv60_valid.iloc[p_st:p_end]
            sub_rvol60 = rvol60_valid.iloc[p_st:p_end]
            dur = p_end - p_st

            p_ret = float((sub_c.iloc[-1] / sub_c.iloc[0] - 1.0) * 100.0)

            # Max drawdown within period
            peak = sub_c.cummax()
            dd_series = (sub_c - peak) / peak
            mdd = float(dd_series.min() * 100.0)

            # Max runup within period
            trough = sub_c.cummin()
            ru_series = (sub_c - trough) / trough
            mru = float(ru_series.max() * 100.0)

            # Annualized Return & Realized Vol
            ann_ret = float(((1.0 + p_ret / 100.0) ** (252.0 / dur) - 1.0) * 100.0) if (1.0 + p_ret / 100.0) > 0 else -100.0
            daily_pct = sub_c.pct_change().dropna()
            daily_vol = float(daily_pct.std() * np.sqrt(252) * 100.0) if len(daily_pct) > 1 else 0.0
            sharpe = float(ann_ret / daily_vol) if daily_vol > 0.001 else 0.0

            all_period_records.append({
                "period_id": pid,
                "session_id": sess_id,
                "symbol": sym,
                "group_name": group_name,
                "archetype_code": archetype_code,
                "regime": reg,
                "regime_name_zh": reg_info["name_zh"],
                "regime_short_zh": reg_info["short_zh"],
                "drift_type": reg_info["drift"],
                "vol_type": reg_info["vol"],
                "color": reg_info["color"],
                "bg_color": reg_info["bg_color"],
                "start_date": df_valid["date"].iloc[p_st],
                "end_date": df_valid["date"].iloc[p_end - 1],
                "duration_days": int(dur),
                "start_price": round(float(sub_c.iloc[0]), 2),
                "end_price": round(float(sub_c.iloc[-1]), 2),
                "min_price": round(float(sub_c.min()), 2),
                "max_price": round(float(sub_c.max()), 2),
                "period_return_pct": round(p_ret, 2),
                "annualized_return_pct": round(ann_ret, 2),
                "max_drawdown_pct": round(mdd, 2),
                "max_runup_pct": round(mru, 2),
                "annualized_vol_pct": round(daily_vol, 2),
                "sharpe_ratio": round(sharpe, 2),
                "avg_ret60": round(float(sub_ret60.mean()), 2),
                "avg_hv60": round(float(sub_hv60.mean()), 2),
                "avg_rvol": round(float(sub_rvol60.mean()), 2)
            })

            for k in range(p_st, p_end):
                period_idx_map[k] = (pid, sess_id)

        # Build Bar Records
        for idx in range(len(df_valid)):
            pid, sess_id = period_idx_map.get(idx, (f"{sym}_PV000", f"{sym}_PV000 [未分類]"))
            all_bar_records.append({
                "date": df_valid["date"].iloc[idx],
                "symbol": sym,
                "open": round(float(df_valid["open"].iloc[idx]), 2),
                "high": round(float(df_valid["high"].iloc[idx]), 2),
                "low": round(float(df_valid["low"].iloc[idx]), 2),
                "close": round(float(df_valid["close"].iloc[idx]), 2),
                "volume": int(df_valid["volume"].iloc[idx]),
                "ret60": round(float(ret60_valid.iloc[idx]), 2),
                "hv60": round(float(hv60_valid.iloc[idx]), 2),
                "rvol60": round(float(rvol60_valid.iloc[idx]), 2),
                "raw_regime": raw_valid[idx],
                "regime": smoothed_regimes[idx],
                "period_id": pid,
                "session_id": sess_id
            })

        # Calculate Stock-Level Long-Term Performance Metrics (2020-2026)
        c_all = group["close"].values
        tot_days = (pd.to_datetime(group["date"].iloc[-1]) - pd.to_datetime(group["date"].iloc[0])).days
        years = tot_days / 365.25 if tot_days > 0 else 1.0
        cagr = ((c_all[-1] / c_all[0]) ** (1.0 / years) - 1.0) * 100.0 if (years > 0 and c_all[-1] / c_all[0] > 0) else 0.0
        ann_vol = float(log_ret.std() * np.sqrt(252) * 100.0)
        peak_all = np.maximum.accumulate(c_all)
        mdd_all = float(np.min((c_all - peak_all) / peak_all) * 100.0)
        sharpe_all = float((cagr - 3.0) / ann_vol) if ann_vol > 0 else 0.0

        reg_series = pd.Series(smoothed_regimes)
        n_valid = len(smoothed_regimes)
        pct_t1 = float((reg_series == "TYPE1_STEADY_BULL").mean() * 100.0)
        pct_t2 = float((reg_series == "TYPE2_MOMENTUM_CLIMAX").mean() * 100.0)
        pct_t3 = float((reg_series == "TYPE3_SQUEEZE_BASE").mean() * 100.0)
        pct_t4 = float((reg_series == "TYPE4_BATTLEGROUND_CHOP").mean() * 100.0)
        pct_t5 = float((reg_series == "TYPE5_PANIC_LIQUIDATION").mean() * 100.0)
        pct_t6 = float((reg_series == "TYPE6_DESPAIR_BLEED").mean() * 100.0)

        stock_metrics[sym] = {
            "symbol": sym,
            "name": m_info.get("name", sym),
            "sector": m_info.get("sector", "Technology"),
            "group_name": group_name,
            "is_sox": int(is_sox),
            "is_mag7": int(is_mag7),
            "is_benchmark": int(is_bench),
            "archetype_code": archetype_code,
            "archetype_name_zh": arch_cfg["name_zh"],
            "total_bars": n_valid,
            "cagr_pct": round(cagr, 2),
            "ann_vol_pct": round(ann_vol, 2),
            "median_hv60_pct": round(float(hv60_valid.median()), 2),
            "max_dd_pct": round(mdd_all, 2),
            "sharpe_ratio": round(sharpe_all, 2),
            "pct_t1": round(pct_t1, 2),
            "pct_t2": round(pct_t2, 2),
            "pct_t3": round(pct_t3, 2),
            "pct_t4": round(pct_t4, 2),
            "pct_t5": round(pct_t5, 2),
            "pct_t6": round(pct_t6, 2),
            "pct_bull": round(pct_t1 + pct_t2, 2),
            "pct_bear": round(pct_t5 + pct_t6, 2),
            "pct_high_vol": round(pct_t2 + pct_t4 + pct_t5, 2),
            "pct_low_vol": round(pct_t1 + pct_t3 + pct_t6, 2),
            "total_periods": len(runs),
            "note": "Normal active history"
        }

    # DataFrames
    df_bars = pd.DataFrame(all_bar_records)
    df_periods = pd.DataFrame(all_period_records)
    df_archetypes = pd.DataFrame(list(stock_metrics.values()))

    print(f"Processed: {len(df_bars):,} classified daily bars.")
    print(f"Extracted: {len(df_periods):,} macro periods across {df_periods['symbol'].nunique()} assets.")

    # -------------------------------------------------------------
    # 1. Regime Summary (Across all periods)
    # -------------------------------------------------------------
    regime_summary_records = []
    tot_duration_all = df_periods["duration_days"].sum()

    for r in REGIMES:
        sub = df_periods[df_periods["regime"] == r]
        cfg = REGIME_CONFIG[r]
        cnt = len(sub)
        days = int(sub["duration_days"].sum()) if cnt > 0 else 0
        pct_time = round((days / tot_duration_all * 100.0), 2) if tot_duration_all > 0 else 0.0
        avg_dur = round(float(sub["duration_days"].mean()), 1) if cnt > 0 else 0.0
        avg_ret = round(float(sub["period_return_pct"].mean()), 2) if cnt > 0 else 0.0
        win_rate = round(float((sub["period_return_pct"] > 0).mean() * 100.0), 2) if cnt > 0 else 0.0
        avg_ann_ret = round(float(sub["annualized_return_pct"].mean()), 2) if cnt > 0 else 0.0
        avg_mdd = round(float(sub["max_drawdown_pct"].mean()), 2) if cnt > 0 else 0.0
        avg_mru = round(float(sub["max_runup_pct"].mean()), 2) if cnt > 0 else 0.0
        avg_vol = round(float(sub["annualized_vol_pct"].mean()), 2) if cnt > 0 else 0.0
        avg_sharpe = round(float(sub["sharpe_ratio"].mean()), 2) if cnt > 0 else 0.0
        avg_rvol = round(float(sub["avg_rvol"].mean()), 2) if cnt > 0 else 0.0

        regime_summary_records.append({
            "regime": r,
            "regime_name_zh": cfg["name_zh"],
            "short_zh": cfg["short_zh"],
            "drift": cfg["drift"],
            "vol": cfg["vol"],
            "color": cfg["color"],
            "count_periods": cnt,
            "total_days": days,
            "pct_time": pct_time,
            "avg_duration_days": avg_dur,
            "avg_return_pct": avg_ret,
            "win_rate_pct": win_rate,
            "avg_ann_ret_pct": avg_ann_ret,
            "avg_mdd_pct": avg_mdd,
            "avg_mru_pct": avg_mru,
            "avg_annualized_vol": avg_vol,
            "avg_sharpe": avg_sharpe,
            "avg_rvol": avg_rvol
        })

    df_regime_summary = pd.DataFrame(regime_summary_records)

    # -------------------------------------------------------------
    # 2. SOX vs Mag 7 Summary Table
    # -------------------------------------------------------------
    sox_mag7_records = []
    for grp in ["MAG7", "SOX", "SOX_MAG7", "BENCHMARK"]:
        sub_arch = df_archetypes[df_archetypes["group_name"] == grp]
        sub_periods = df_periods[df_periods["group_name"] == grp]
        cnt_stocks = len(sub_arch)
        if cnt_stocks == 0:
            continue

        cagr_mean = round(float(sub_arch["cagr_pct"].mean()), 2)
        vol_mean = round(float(sub_arch["ann_vol_pct"].mean()), 2)
        med_hv_mean = round(float(sub_arch["median_hv60_pct"].mean()), 2)
        mdd_mean = round(float(sub_arch["max_dd_pct"].mean()), 2)
        sharpe_mean = round(float(sub_arch["sharpe_ratio"].mean()), 2)

        pct_t1 = round(float(sub_arch["pct_t1"].mean()), 2)
        pct_t2 = round(float(sub_arch["pct_t2"].mean()), 2)
        pct_t3 = round(float(sub_arch["pct_t3"].mean()), 2)
        pct_t4 = round(float(sub_arch["pct_t4"].mean()), 2)
        pct_t5 = round(float(sub_arch["pct_t5"].mean()), 2)
        pct_t6 = round(float(sub_arch["pct_t6"].mean()), 2)
        pct_bull = round(pct_t1 + pct_t2, 2)
        pct_bear = round(pct_t5 + pct_t6, 2)
        pct_high_vol = round(pct_t2 + pct_t4 + pct_t5, 2)
        pct_low_vol = round(pct_t1 + pct_t3 + pct_t6, 2)

        # Dominant Archetype in this group
        dominant_arch = sub_arch["archetype_code"].mode().iloc[0] if len(sub_arch) > 0 else "N/A"
        dominant_arch_zh = ARCHETYPE_CONFIG.get(dominant_arch, {}).get("short_zh", dominant_arch)

        sox_mag7_records.append({
            "group_name": grp,
            "stock_count": cnt_stocks,
            "avg_cagr_pct": cagr_mean,
            "avg_ann_vol_pct": vol_mean,
            "avg_median_hv60_pct": med_hv_mean,
            "avg_max_dd_pct": mdd_mean,
            "avg_sharpe_ratio": sharpe_mean,
            "pct_t1_steady": pct_t1,
            "pct_t2_climax": pct_t2,
            "pct_t3_squeeze": pct_t3,
            "pct_t4_chop": pct_t4,
            "pct_t5_panic": pct_t5,
            "pct_t6_bleed": pct_t6,
            "pct_bull_regimes": pct_bull,
            "pct_bear_regimes": pct_bear,
            "pct_high_vol_regimes": pct_high_vol,
            "pct_low_vol_regimes": pct_low_vol,
            "dominant_archetype": dominant_arch_zh
        })

    df_sox_vs_mag7 = pd.DataFrame(sox_mag7_records)

    # -------------------------------------------------------------
    # 3. Write SQLite Database
    # -------------------------------------------------------------
    os.makedirs(os.path.dirname(out_db_path), exist_ok=True)
    if os.path.exists(out_db_path):
        os.remove(out_db_path)

    out_conn = sqlite3.connect(out_db_path)
    df_bars.to_sql("bar_price_vol", out_conn, index=False)
    df_periods.to_sql("price_vol_periods", out_conn, index=False)
    df_archetypes.to_sql("stock_archetypes", out_conn, index=False)
    df_regime_summary.to_sql("regime_summary", out_conn, index=False)
    df_sox_vs_mag7.to_sql("sox_vs_mag7_summary", out_conn, index=False)

    # Create Indexes for Query Speed
    cur = out_conn.cursor()
    cur.execute("CREATE INDEX idx_bar_sym_date ON bar_price_vol(symbol, date);")
    cur.execute("CREATE INDEX idx_bar_period ON bar_price_vol(period_id);")
    cur.execute("CREATE INDEX idx_period_sym ON price_vol_periods(symbol);")
    cur.execute("CREATE INDEX idx_period_regime ON price_vol_periods(regime);")
    cur.execute("CREATE INDEX idx_arch_sym ON stock_archetypes(symbol);")
    cur.execute("CREATE INDEX idx_arch_grp ON stock_archetypes(group_name);")
    out_conn.commit()
    out_conn.close()

    print(f"Saved SQLite DB to: {out_db_path} ({os.path.getsize(out_db_path) / (1024*1024):.2f} MB)")

    # -------------------------------------------------------------
    # 4. Write Structured JSON for Frontend
    # -------------------------------------------------------------
    # Group periods by symbol
    periods_by_sym = {}
    for p in all_period_records:
        periods_by_sym.setdefault(p["symbol"], []).append(p)

    summary_json_data = {
        "metadata": {
            "title": "SOX 30 & Mag 7 Pure Price & Vol Analysis (2020-2026)",
            "total_assets": total_symbols,
            "valid_assets_analyzed": len(df_archetypes),
            "total_macro_periods": len(df_periods),
            "volatility_threshold": vol_thresh,
            "min_macro_duration_days": min_duration,
            "regime_config": REGIME_CONFIG,
            "archetype_config": ARCHETYPE_CONFIG
        },
        "regime_summary": regime_summary_records,
        "sox_vs_mag7_summary": sox_mag7_records,
        "stock_archetypes": list(stock_metrics.values()),
        "periods_by_symbol": periods_by_sym
    }

    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(summary_json_data, f, ensure_ascii=False, indent=2)

    print(f"Saved Frontend JSON to: {out_json_path} ({os.path.getsize(out_json_path) / 1024:.1f} KB)")
    print(f"================================================================================")
    print(" Price & Vol Analysis Completed Successfully! ")
    print(f"================================================================================")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Pure Price & Vol Analysis on SOX 30 + Mag 7")
    parser.add_argument("--src-db", default=DEFAULT_SRC_DB, help="Source OHLCV SQLite database path")
    parser.add_argument("--out-db", default=DEFAULT_OUT_DB, help="Output SQLite database path")
    parser.add_argument("--out-json", default=DEFAULT_OUT_JSON, help="Output JSON path")
    parser.add_argument("--min-duration", type=int, default=20, help="Minimum regime duration (bars)")
    parser.add_argument("--vol-thresh", type=float, default=35.0, help="Volatility threshold sigma_60 boundary (%)")
    args = parser.parse_args()

    run_price_vol_analysis(
        src_db_path=args.src_db,
        out_db_path=args.out_db,
        out_json_path=args.out_json,
        min_duration=args.min_duration,
        vol_thresh=args.vol_thresh
    )
