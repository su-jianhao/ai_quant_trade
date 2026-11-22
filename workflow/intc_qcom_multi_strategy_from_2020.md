# Workflow: Intel (INTC) 與 Qualcomm (QCOM) 自 2020 年起四大策略對比回測與實盤輔助工作流

當用戶針對 **Intel (`INTC`)** 與 **Qualcomm (`QCOM`)** 執行多策略回測評估與實盤輔助（如 `run @workflow/intc_qcom_multi_strategy_from_2020.md`）時，本工作流以 [`@workflow/project_trade_assistant.md`](project_trade_assistant.md) 的四階段架構為骨幹，串聯 **布林通道 (Bollinger Bands)**、**KDJ**、**MACD**、**RSI** 四大策略規範，自 **`2020-01-01`** 起進行全週期回測、體制歸因、穩健性檢驗與操作建議歸檔。

---

## 參數與混搭設定介面 (Workflow Parameters & Overrides)

以下覆寫值套用於本工作流所有階段，優先於各單一 Prompt 預設值（用戶可於對話中再行覆寫）：

| 參數 | 預設值 | 說明 |
|:---|:---|:---|
| `PROJECT_NAME` | `"intc_qcom"` | 對應 `projects/intc_qcom/`（若不存在則依 `projects/template/` 自動初始化並改為美股 `USD` 設定） |
| `SYMBOLS` | `["INTC", "QCOM"]` | 目標評估與交易標的（Intel Corporation、Qualcomm Inc.） |
| `BENCHMARK` | `"^SOX"` | 基準指數（亦可選 `"SOXX"` 或 `"QQQ"`，皆已收錄於本地資料庫） |
| `START_DATE` | `"2020-01-01"` | 回測統計起始日（首個有效交易日為 `2020-01-02`） |
| `END_DATE` | `"latest"` | 最新可用交易日（本地資料庫已覆蓋至 `2026-11-10`） |
| `WARMUP_BARS` | `200` | `START_DATE` 前暖身 K 線數（滿足 RSI `EMA_200`、KDJ `SMA_50`、MACD 與布林預熱） |
| `MIX_STRATEGIES` | `["bollinger_strategy.md", "kdj_strategy.md", "macd_strategy.md", "rsi_strategy.md"]` | 同步測試四大技術指標策略（各策略下全變體對比） |
| `MODEL_KEY` | `"compare"` | 每項策略皆執行全變體對比（4 策略 × 7 變體 = 28 組模型） |
| `FIXED_CASH` | `10000.0` | 單筆固定開倉本金（美元 `USD`） |
| `COMMISSION_RATE` | `0.0003` | 美股單邊手續費率（3 bps） |
| `TAX_RATE` | `0.0` | 美股無證券交易稅 |
| `SLIPPAGE` | `0.0005` | 雙邊滑點（5 bps） |
| `RUN_BACKTEST` | `true` | 強制開啟四策略歷史回測與跨策略績效橫向比較 |
| `ROBUSTNESS_GATE` | `true` | 開啟 WFO、滑價壓力與參數高原檢驗閘門 |
| `POOL_ACTIONS` | *(選填)* | 額外增刪候選股（預設追蹤 `INTC`, `QCOM`） |
| `BROKER_UPDATES` | *(選填)* | 本輪用戶回報的券商實際持股、成本、可用現金或已執行交易 |
| `RUN_TAG` | `"bb_kdj_macd_rsi_2020"` | 輸出目錄自訂標籤 |

---

## 本地 `data/` 資料盤點與評估基準 (Local Data Inventory)

經檢查專案 `data/` 目錄，現有與 `INTC`、`QCOM` 相關之可用資料如下：

| 資料來源 | 路徑 | 覆蓋區間 | 筆數 / 週期 | 內含欄位與用途 |
|:---|:---|:---|:---|:---|
| **SOX/Mag7 量波資料庫** | `data/sox_mag7_price_vol_types/price_vol_analysis.db` | `2020-01-02` ~ `2026-11-10` | 各 `1,724` 根日 K 線 | `bar_price_vol`（OHLCV + `ret60`, `hv60`, `rvol60`, `regime`, `period_id`）與 `price_vol_periods`（6 大宏觀體制區間） |
| **量波結構化摘要** | `data/sox_mag7_price_vol_types/price_vol_summary.json` | `2020-01-02` ~ `2026-11-10` | `INTC`: 23 週期<br>`QCOM`: 26 週期 | 供 Stage 3 進行分體制（Type 1~6）歸因與原型對照 |

### 既有標的物理特徵基準（2020-01-02 ~ 2026-11-10）

| 標的 | 原型歸屬 | CAGR | 年化波動率 | 中位數 HV60 | 最大回撤 | 夏普比率 | 高波時間佔比 | 體制特徵摘要 |
|:---|:---|---:|---:|---:|---:|---:|---:|:---|
| **INTC** | `E. 成熟現金流成熟製程` | `-0.66%` | `54.72%` | `42.01%` | `-73.52%` | `-0.07` | `82.02%` | 長期高波震盪與下殺（Type 4 佔 `25.99%`、Type 5 佔 `24.19%`），趨勢策略易遭雙巴 |
| **QCOM** | `E. 成熟現金流成熟製程` | `+10.29%` | `43.51%` | `38.43%` | `-45.57%` | `0.17` | `59.34%` | 兼具週期主升與箱體盤整（Type 3 佔 `25.41%`、Type 2 佔 `19.95%`、Type 5 佔 `20.24%`） |

> **資料缺口提示**：`price_vol_analysis.db` 起始於 `2020-01-02`（無 2019 年預熱 K 線，亦未拆分 `Adj_Close`/`Raw_Close`）。Stage 2 執行時應優先透過 `@prompts/data_generate.md` 補齊 `2019-01-01` 起之雙軌日頻資料至 `data/intc_qcom/`；若處於離線環境，則直接以 `data/sox_mag7_price_vol_types/price_vol_analysis.db` 執行回測，並於報告標頭註明指標暖身有效起始日。

---

## 產物保存結構與自動回顧規則 (Artifact Persistence & Auto-Review)

完全沿用 [`@workflow/project_trade_assistant.md`](project_trade_assistant.md) 之時間戳歸檔與自動回顧規則：

```text
projects/intc_qcom/
├── config.json
├── portfolio.db
├── trades/
│   └── <YYYYMMDD_HHMM>_multi4_intc_qcom/     # 四策略對比 HTML、QuantStats、backtest_result.db、backtest_report.md、robustness_report.md
└── reports/
    ├── INDEX.md                              # 累積執行索引（時間、策略混搭、回測裁決、報告連結）
    └── <YYYYMMDD_HHMM>_bb_kdj_macd_rsi_2020/
        ├── trade_advice.md                   # 本輪操作建議與四策略優選結論
        ├── analysis_snapshot.md              # Stage 3 個股三情境診斷與四策略訊號明細
        └── run_meta.json                     # 結構化中繼資料（參數快照、資料截止日、VERDICT、建議編號）
```

---

## Stage 1：專案帳本、券商持倉與候選池同步 (`@prompts/portfolio_manager.md`)

1. **遵循規範**：[`@prompts/portfolio_manager.md`](../prompts/portfolio_manager.md)
2. **執行動作**：
   - 讀取或初始化 `projects/<PROJECT_NAME>/config.json`（設定 `market: "US"`、`currency: "USD"`、`benchmark: "^SOX"`、`commission_rate: 0.0003`、`tax_rate: 0.0`、`slippage: 0.0005`、`run_backtest: true`、`robustness_gate: true`）與 `portfolio.db`。
   - **自動偵測歷史產物**：檢查 `projects/<PROJECT_NAME>/reports/INDEX.md`、`reports/` 與 `trades/`，若已有歷史執行紀錄則載入供本輪自動覆盤。
   - 同步 `POOL_ACTIONS` / `BROKER_UPDATES`，鎖定本輪目標清單至少包含 `["INTC", "QCOM"]`。

---

## Stage 2：2020 起目標標的資料準備與驗證 (`@prompts/data_generate.md`)

1. **遵循規範**：[`@prompts/data_generate.md`](../prompts/data_generate.md)
2. **執行動作**：
   - **線上增量模式（建議）**：下載或同步 `INTC`、`QCOM`（及基準 `^SOX` / `SOXX`）自 **`2019-01-01`**（含 `2020-01-01` 前 200~250 日預熱窗）至最新交易日之日頻 OHLCV，嚴格分離 `Adj_Close`（計算指標）與 `Raw_Close`（撮合結算）並計算完整技術指標（`BB(20,2)`、`KDJ(9,3,3)`、`MACD(12,26,9)`、`RSI(14)`、`ADX(14)`、`ATR(14)`、`SMA 20/50`、`EMA 200`），存放於 `data/intc_qcom/`。
   - **本地離線回退模式**：若無外部網路，直接載入 `data/sox_mag7_price_vol_types/price_vol_analysis.db`（`bar_price_vol` 表，`2020-01-02` ~ `2026-11-10`）即時計算上述指標，並於報告中明確標示暖身視窗截斷日。
   - 同步將 `data/sox_mag7_price_vol_types/price_vol_periods` 中 `INTC`（23 週期）與 `QCOM`（26 週期）的 `Type 1 ~ Type 6` 宏觀體制標籤關聯至每日資料，供 Stage 3 歸因使用。
   - 更新 `portfolio.db` 中 `holdings` 之最新收盤價與未實現損益。

---

## Stage 3：四大策略全變體回測、跨體制歸因與穩健性檢驗

本階段同時覆蓋「歷史量化驗證」與「實盤多維診斷」：

### 3.1 四大策略基準與全變體回測 (`@prompts/backtest.md`)

依以下四份策略規範，對 `INTC` 與 `QCOM` 在 **`2020-01-01` ~ `END_DATE`** 區間逐一執行全變體對比（`MODEL_KEY = "compare"`），統一採 `FIXED_CASH = $10,000`、雙邊滑點 `5 bps`、單邊手續費 `3 bps`：

1. **Bollinger Bands** — [`@prompts/strategy/bollinger_strategy.md`](../prompts/strategy/bollinger_strategy.md)
   - 變體：`baseline`, `bw_expand`, `profit_lock`, `atr_trail`, `combo_refined`, `reversion`, `regime_adaptive`
   - 觀察重點：比較動能突破（`bw_expand`/`combo_refined`）與均值回歸（`reversion`）在 `INTC`（高波震盪）與 `QCOM`（週期輪動）的顯著差異。
2. **KDJ (9,3,3)** — [`@prompts/strategy/kdj_strategy.md`](../prompts/strategy/kdj_strategy.md)
   - 變體：`baseline`, `no_chase`, `trend_filter`, `profit_lock`, `oversold_low`, `combo_refined`, `oversold_trend`
   - 觀察重點：檢驗 `oversold_low` / `oversold_trend` 在兩檔晶片股恐慌急殺（Type 5）時的低吸勝率，以及 `no_chase` 減少 Chop Tax 的幅度。
3. **MACD (12,26,9)** — [`@prompts/strategy/macd_strategy.md`](../prompts/strategy/macd_strategy.md)
   - 變體：`raw`, `adx_20`, `bb_squeeze`, `water_reversal`, `adx_water`, `bb_water`, `bb_trailing`
   - 觀察重點：檢驗 `adx_20`、`bb_squeeze` 與 `water_reversal` 過濾 `INTC` 假反彈與橫盤雙巴的效果。
4. **RSI (14)** — [`@prompts/strategy/rsi_strategy.md`](../prompts/strategy/rsi_strategy.md)
   - 變體：`baseline`, `trend_filter`, `extreme_oversold`, `bullish_divergence`, `momentum_breakout`, `profit_lock`, `regime_adaptive`
   - 觀察重點：對比極限超跌狙擊（`extreme_oversold`）與放量動能突破（`momentum_breakout` / `profit_lock`）之期望值與最大回撤。

所有回測產物統一輸出至 `projects/<PROJECT_NAME>/trades/<YYYYMMDD_HHMM>_multi4_intc_qcom/`（含綜合互動 HTML、`quantstats/`、`backtest_result.db`、`backtest_report.md`）。

### 3.2 績效覆盤、跨體制歸因與穩健性閘門

1. **遵循規範**：
   - [`@prompts/strategy/quantitative_performance_workflow.md`](../prompts/strategy/quantitative_performance_workflow.md)
   - [`@prompts/analyze/robustness_testing_taxonomy.md`](../prompts/analyze/robustness_testing_taxonomy.md)
   - [`@prompts/factors/risk_module.md`](../prompts/factors/risk_module.md)
2. **核心診斷任務**：
   - **個股獨立排名（禁止混池掩蓋差異）**：分別針對 `INTC` 與 `QCOM` 排出四大策略 Top 變體，對照各自 Buy & Hold 與 `^SOX` 基準（涵蓋 Total Return %, CAGR, Sharpe, Sortino, Calmar, Max Drawdown %, Win Rate %, PF, Trade Count, Chop Tax `<=10d`）。
   - **體制切片歸因（Regime Attribution）**：結合 `price_vol_periods`（Type 1~6），拆解 2020 疫情急殺反彈、2021 缺芯多頭、2022 升息熊市、2023~2026 AI 半導體分化期間，各策略在 **Type 1/2（多頭）**、**Type 3/4（盤整洗盤）**、**Type 5/6（空頭下殺）** 的損益貢獻。
   - **穩健性六維計分卡**：對各策略勝出變體（及候選多策略共振組合）執行 WFO 樣本外檢驗、滑價 2x~3x 壓力測試與 ±20% 參數高原敏感度分析，輸出 `robustness_report.md` 與 `VERDICT`（`PASS` / `CONDITIONAL` / `FAIL`）。

### 3.3 實盤個股診斷與四層風控檢核

1. 遵循 [`@prompts/stock_analysis.md`](../prompts/stock_analysis.md) 評估 `INTC` 與 `QCOM` 最新交易日之 Tier 1~4 因子狀態與三情境推演。
2. 掃描四大策略優選變體於最新交易日是否觸發進場／出場／共振訊號。
3. 遵循 [`@prompts/factors/risk_module.md`](../prompts/factors/risk_module.md) 計算持倉或建倉之硬停損、保本鎖定線與 ATR 吊燈停利線，將明細存檔至 `reports/<YYYYMMDD_HHMM>_<RUN_TAG>/analysis_snapshot.md`。

---

## Stage 4：產出綜合研報、實盤操作建議與歸檔索引 (`@prompts/trade_advisor.md`)

1. **遵循規範**：[`@prompts/trade_advisor.md`](../prompts/trade_advisor.md)
2. **交付內容（存檔至 `projects/<PROJECT_NAME>/reports/<YYYYMMDD_HHMM>_<RUN_TAG>/trade_advice.md`）**：
   1. **執行條件標頭（Run Metadata Header）**：`run_id`、資料來源與截止日、暖身窗口說明、四大策略參數、`robustness_gate` 裁決結果，以及 `trades/` 互動報告連結。
   2. ***(若有歷史紀錄則自動納入)* 前期結果自動回顧（Auto-Review）**。
   3. **四大策略橫向總評矩陣**：`INTC` 與 `QCOM` 各自在 Bollinger / KDJ / MACD / RSI 下的最佳變體、B&H 對照、分體制適配結論（例如：高波震盪的 `INTC` 應優先採用超跌反轉/均值回歸或嚴格濾網，而 `QCOM` 應採體制切換或動能+追蹤止盈）。
   4. **現有持倉動作表 & 候選建倉排序表**：提供最新買入區間、基於 `ATR` 風險預算的建議股數、初始停損價、目標價、R/R 比與編號化建議卡（`#S1`, `#S2`, ...）。
   5. **結構化歸檔**：同步寫入同目錄 `run_meta.json` 並追加紀錄至 `projects/<PROJECT_NAME>/reports/INDEX.md`。
3. **用戶回饋與帳本閉環**：
   - 等待用戶確認實際成交或策略取捨後，由 `@prompts/portfolio_manager.md` 回寫至 `projects/<PROJECT_NAME>/portfolio.db`。
