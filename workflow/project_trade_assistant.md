# Workflow: 專案候選股池與券商持倉實盤輔助工作流 (Project Trade Assistant Workflow)

當用戶針對某個交易專案執行實盤輔助（如 `run @workflow/project_trade_assistant.md for project <PROJECT_NAME>`）時，本工作流以**純 Prompt 編排模式**串聯 4 個獨立階段，完成「候選股與券商持倉同步 $\to$ 最新行情更新 $\to$ 多策略自由混搭診斷 $\to$ 操作建議生成與用戶採納閉環」。

---

## 參數與混搭設定介面 (Workflow Parameters & Prompt Mixing)

用戶可在對話中覆寫以下設定（未指定時採預設組合）：

| 參數 | 預設值 | 說明 |
|:---|:---|:---|
| `PROJECT_NAME` | *(必填)* | 對應 `projects/<PROJECT_NAME>/portfolio.db`（若不存在則依 `projects/template/portfolio.db` 自動初始化） |
| `POOL_ACTIONS` | *(選填)* | 本輪欲新增或移除的候選股（如 `add 2454.TW, AVGO; remove INTC`） |
| `BROKER_UPDATES` | *(選填)* | 本輪用戶新回報的券商實際持股、成本、現金或已執行交易 |
| `MIX_STRATEGIES` | `["bollinger_strategy.md", "macd_strategy.md", "taiwan_chip_strategy.md"]` | **可自由混搭** `prompts/strategy/` 下的任意策略規範（台股自動套用籌碼/技術，美股套用動能/布林/RSI/三位一體） |
| `RUN_BACKTEST` | `false` | 若設為 `true`，針對候選池額外混入 `@prompts/backtest.md` 驗證策略歷史勝率 |

---

## Stage 1：專案帳本、券商持倉與候選池同步 (`@prompts/portfolio_manager.md`)

1. **遵循規範**：[`@prompts/portfolio_manager.md`](../prompts/portfolio_manager.md)
2. **執行動作**：
   - 讀取 `projects/<PROJECT_NAME>/config.json`（載入基準指數、券商費率、風控參數、`prompts_mix.strategies` 混搭清單，以及**專案內任意自訂欄位與交易規則**）與 `projects/<PROJECT_NAME>/portfolio.db`（`account_summary`、`holdings`、`candidates`、`trade_log`；若首次執行則從 `projects/template/` 初始化）。
   - 若用戶輸入了新的券商持倉（股數、成本、可用現金）或候選股增刪（`POOL_ACTIONS` / `BROKER_UPDATES`），先寫入更新 `portfolio.db`。
   - 彙整出本輪需追蹤的**目標股票總清單** = `券商現有持倉標的` $\cup$ `候選觀察股池標的`。

---

## Stage 2：目標股票池最新數據獲取 (`@prompts/data_generate.md`)

1. **遵循規範**：[`@prompts/data_generate.md`](../prompts/data_generate.md)
2. **執行動作**：
   - 針對 Stage 1 彙整出的目標股票清單（或對應股票池 DB），檢查並增量同步最新交易日行情、19 項技術指標、CYQ 籌碼與台股三大法人/融資數據。
   - 提取每檔標的的最新收盤價、均線位置 (`10EMA / 20SMA / 50SMA / 200SMA`)、`RSI_14`、`MACD`、布林通道、`ATR_14` 與籌碼數據，並更新 `portfolio.db` 中 `holdings` 表的 `latest_price`、`unrealized_pnl` 與 `unrealized_pct`。

---

## Stage 3：多維度個股診斷與自選策略混搭 (Mix & Match Analysis)

本階段可依用戶需求**自由插拔或混搭** `prompts/` 下的不同分析與策略模組：

1. **個股全維度診斷與三情境推演**：
   - 遵循 [`@prompts/stock_analysis.md`](../prompts/stock_analysis.md)，對現有持倉與重點候選股評估 Tier 1~4 因子多空狀態與未來三情境機率。
2. **策略信號混搭掃描 (`MIX_STRATEGIES`)**：
   - 依用戶指定的 [`@prompts/strategy/*.md`](../prompts/strategy/README.md)（例如混搭 `macd_strategy.md` + `bollinger_strategy.md` + `rsi_strategy.md` + `taiwan_chip_strategy.md`），檢查哪些候選股觸發共振進場信號、哪些持倉股出現出場/減碼信號。
3. **四層縱深風控檢核**：
   - 遵循 [`@prompts/factors/risk_module.md`](../prompts/factors/risk_module.md)，根據每檔持倉的**真實買入成本**與波段最高價，計算最新硬停損、保本鎖定線（浮盈 $\ge +8\% \sim 10\%$）與吊燈停利線（浮盈 $\ge +20\%$）。
4. *(可選)* **候選池歷史回測與穩健性閘門 (`RUN_BACKTEST = true` 或 `config.json` 開啟 `robustness_gate`)**：
   - 若用戶想先確認某策略在該批候選股上的歷史勝率與實盤抗壓度，混入 [`@prompts/backtest.md`](../prompts/backtest.md) 執行回測並輸出至 `projects/<PROJECT_NAME>/trades/`，同時調用 [`@prompts/analyze/robustness_testing_taxonomy.md`](../prompts/analyze/robustness_testing_taxonomy.md) 完成 WFO、滑價壓力與參數高原檢驗，產出 `VERDICT` 傳遞給 Stage 4。

---

## Stage 4：產出實盤操作建議與用戶採納閉環 (`@prompts/trade_advisor.md`)

1. **遵循規範**：[`@prompts/trade_advisor.md`](../prompts/trade_advisor.md)
2. **執行動作**：
   - 綜合 Stage 1~3 結果，產出結構化實盤建議報告並存檔至 `projects/<PROJECT_NAME>/reports/<YYYY-MM-DD>_advice/trade_advice.md`。
   - 報告必須包含：
     1. **現有券商持倉動作表**（續抱 `HOLD` / 上移停損 `RAISE_STOP` / 獲利減碼 `TRIM` / 順勢加碼 `ADD` / 停損清倉 `EXIT`）；
     2. **候選觀察股池建倉排序表**（建議買入區間、基於可用現金與 `ATR` 風險預算換算的**建議買入股數**、初始停損價、目標價與 R/R 比）；
     3. **編號化可執行建議卡 (`#S1`, `#S2`, ...)**。
3. **用戶回饋與帳本閉環**：
   - 等待用戶回覆實際決策（如：「我執行了 `#S1`，另外 `#S2` 我在券商買了 200 股成交在 151.5」），再由 `@prompts/portfolio_manager.md` 回寫至 `projects/<PROJECT_NAME>/portfolio.db`。
