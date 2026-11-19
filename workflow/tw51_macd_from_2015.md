# Workflow: TW50 (tw51) 自 2015 年起 MACD 策略全週期回測、優化與研報

當用戶執行本工作流（如 `run @workflow/tw51_macd_from_2015.md`）時，依序串聯以下 `prompts/` 規範，對台灣 50 現有成分股（`tw50`）執行自 **`2015-01-01`** 至今的 MACD 策略全週期回測、微觀歸因優化（Refine）與最終研報交付。

> **標的說明**：本工作流名稱中的 `tw51` 對應專案內置之現行台灣 50 成分股池 **`tw50`**（`modules/target_resolver.py` 中的 `TW50_CONSTITUENTS`）。

---

## 統一參數覆寫 (Global Parameter Overrides)

以下覆寫值套用於本工作流所有階段，優先於各單一 Prompt 預設值：

| 參數 | 設定值 | 說明 |
|:---|:---|:---|
| `TARGET` / `SYMBOLS` | `tw50` | 現行台灣 50 成分股池 |
| `START_DATE` | `"2015-01-01"` | 回測統計起始日（跨越 2015、2018、2020、2022 熊市與 2023~2026 AI 多頭） |
| `END_DATE` | `"latest"` | 最新可用交易日 |
| `WARMUP_BARS` | `250` | `2015-01-01` 之前預留至少 120~250 個交易日冷啟動預熱 |
| `FIXED_CASH` | `100000.0` | 單筆固定開倉本金（新台幣） |
| `COMMISSION_RATE` | `0.000855` | 台股單邊券商手續費（6 折） |
| `TAX_RATE` | `0.003` | 台股賣出證券交易稅（`0.3%`） |
| `SLIPPAGE` | `0.0005` | 雙邊滑點（5 bps） |
| `MODEL_KEY` | `"compare"` | 對比 MACD 全部 7 大變體 |

---

## Stage 1：長週期資料準備與防雷驗證 (`@prompts/data_generate.md`)

1. **遵循規範**：`@prompts/data_generate.md`
2. **執行任務**：
   - 生成或同步 `tw50` 自 `2014-01-01`（含 2015 年前預熱窗口）至今的日頻行情、技術指標與台股籌碼資料，統一存放於 `data/tw50/`。
   - 確保嚴格分離 `Adj_Close`（指標計算）與 `Raw_Close`（撮合結算）、處理除權息股利與 `is_fillable` 流動性標籤，並避免盤後籌碼未來函數。
   - *(可選市場狀態標註)*：依 `@prompts/data/human_stage_trend_vol.md` 切分 2015 至今各年度 `UP/DOWN/CHOP × LOW/HIGH_VOL` 市況，供 Stage 3 歸因使用。

---

## Stage 2：MACD 七大變體基準回測 (`@prompts/strategy/macd_strategy.md` + `@prompts/backtest.md`)

1. **遵循規範**：`@prompts/strategy/macd_strategy.md`、`@prompts/backtest.md`
2. **執行任務**：
   - 執行 MACD 全變體對比回測（`raw`, `adx_20`, `bb_squeeze`, `water_reversal`, `adx_water`, `bb_water`, `bb_trailing`）。
   - 確認台股雙軌稅費（買進手續費 + 賣出手續費與 0.3% 證交稅）與股利調整皆正確計入。
   - 產出基準回測結果至 `trades/macd_2015_<timestamp>_tw50/`：
     - `tw50_macd_QuantStats_Report.html`（含 KPI 卡片、Key Performance Metrics 總表、月報酬熱力圖、滾動夏普、可篩選成交流水）
     - `quantstats/quantstats_<model>.html`
     - `backtest_result.db` & `backtest_report.md`

---

## Stage 3：績效覆盤、穩健性檢驗與策略優化 (Refine)

1. **遵循規範**：
   - `@prompts/strategy/quantitative_performance_workflow.md`
   - `@prompts/analyze/robustness_testing_taxonomy.md`
   - `@prompts/factors/risk_module.md`
2. **診斷與優化任務**：
   - **痛點歸因**：拆解 2015~至今不同年份（如 2015 下殺、2018 震盪、2022 升息熊市、2024~2026 多頭）各變體的 `Chop Tax (<=10d)`、假突破損耗與 `Cash Drag`。
   - **導入風控與台股微結構優化（至少設計並測試 1~2 個 Refined 版本）**：
     - 結合 `@prompts/factors/risk_module.md` 的「保本鎖定 + ATR 吊燈停利」或「大盤 120/240MA 宏觀濾網」；
     - 檢查 `ADX_THRESHOLD`（如 20 vs 25）與 `TRAILING_ATR_MULT`（如 2.5 vs 3.0）的參數高原穩定性（±20% 敏感度測試），杜絕過擬合；
     - 評估原物料景氣循環股（如 `2002.TW`、`1301.TW`、`2603.TW`）在 MACD 下的表現差異。
   - **優化前後對比回測**：將 Refined 策略在完全相同的 `2015-01-01 ~ latest` 區間重跑回測，產出至 `trades/macd_refined_2015_<timestamp>_tw50/`。

---

## Stage 4：最終綜合研報交付 (Final Report)

彙整 Stage 2 與 Stage 3 的量化證據，向用戶交付最終中文研報（並同步存檔於對應 `trades/` 目錄）：
1. **核心績效總表**：MACD 7 大基準變體 vs Refined 優化版 vs TW50 等權重 B&H（涵蓋 Total Return %, Sharpe, Sortino, Calmar, Max Drawdown %, Win Rate %, PF, Chop Tax `<=10d`）。
2. **跨週期穩健性驗證**：2015~至今分年度/分市況（牛市 / 熊市 / 震盪市）表現拆解，說明 Refined 版本實際改善了多少回撤與摩擦稅。
3. **交付物連結**：提供 Plotly 綜合 HTML 研報、QuantStats Tear Sheets、`backtest_result.db`（可用 `python3 -m modules.viewer --serve` 開啟）及優化後策略程式碼連結。
