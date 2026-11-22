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
| `RUN_BACKTEST` | `false` | 若設為 `true`，針對候選池額外混入 `@prompts/backtest.md` 驗證策略歷史勝率（若已有同策略近期回測結果則預設先引用檢視，欲強制重跑可註明覆寫） |
| `RUN_TAG` | `"advice"` | *(選填)* 本次執行的自訂標籤（如 `macd_bb_test`、`pre_earnings`），附加於輸出目錄名稱以利日後辨識 |

---

## 產物保存結構與自動回顧規則 (Artifact Persistence & Auto-Review)

為確保每次測試結果與實盤建議皆可完整追溯且不互相覆寫，所有輸出統一採**時間戳目錄**歸檔於 `projects/<PROJECT_NAME>/` 下：

```text
data/<universe_dir>/
└── events_news.db                            # 獨立、跨專案共用、按需增量之重大事件與新聞資料庫（不隨回測重建；如 data/sox_mag7_price_vol_types/events_news.db）

projects/<PROJECT_NAME>/
├── config.json
├── portfolio.db
├── review.db                                 # 專案統一覆盤 SQLite 資料庫（日K線/體制、全變體評估、跨體制穩定度、全部交易、近期訊號、行動風控、歷史報告索引）
├── review_viewer.html                        # 單檔免伺服器互動式覆盤檢視器（K線體制買賣點、財報/8-K/異常事件標記、全變體含盈虧比總表、6體制熱圖、全部交易明細、中文行動風控看板）
├── trades/
│   ├── <YYYYMMDD_HHMM>_<strategy>_<scope>/   # 第 1 次回測產物（不可覆寫）
│   └── <YYYYMMDD_HHMM>_<strategy>_<scope>/   # 第 2 次回測產物（以當下測試時間新建）
└── reports/
    ├── INDEX.md                              # 僅追加 (Append-Only) 之多版本執行索引（測試時間、資料截止日、策略混搭、裁決、連結）
    ├── <YYYYMMDD_HHMM>_<RUN_TAG>/            # 第 1 份歷史報告（完整保留）
    └── <YYYYMMDD_HHMM>_<RUN_TAG>/            # 第 2 份新報告（以當下測試時間新建）
        ├── trade_advice.md                   # 本輪操作建議報告（含全變體含盈虧比評估、跨體制穩定性、近期買賣訊號、中文行動與四層風控）
        ├── analysis_snapshot.md              # (選填) Stage 3 個股診斷與因子訊號明細
        └── run_meta.json                     # 結構化中繼資料（測試時間、參數快照、資料截止日、裁決結果、建議編號、產物路徑）
```

- **不可覆寫與多報告累積原則 (Immutable Timestamped Runs & Append-Only Index)**：
  - **每次執行必建新時間戳目錄**：無論是例行更新、補充最新行情重跑、調整策略/參數或擴充診斷，每次執行皆必須以**當下系統執行時間** `YYYYMMDD_HHMM`（若同一分鐘內連續執行則自動加上秒數 `YYYYMMDD_HHMMSS` 或遞增序號）建立全新的 `reports/<timestamp>_<RUN_TAG>/` 與 `trades/<timestamp>_<strategy>_<scope>/`，**嚴禁重用舊時間戳覆寫既有報告或回測目錄**（僅在用戶明確指定修改某個既有檔案路徑時例外）。
  - **`INDEX.md` 僅允許追加（Append-Only）**：每次新產出的報告與回測皆須於 `projects/<PROJECT_NAME>/reports/INDEX.md` **追加一筆新紀錄**（記錄測試時間 `Test Time`、資料截止日、策略與變體、穩健裁決及報告連結），不得清空或覆蓋既有歷史列，使專案累積多份帶測試時間的報告以便跨期追蹤與對比。
- **自動回顧觸發條件（無需額外切換模式）**：每次執行工作流時，系統會自動檢查 `projects/<PROJECT_NAME>/reports/INDEX.md`、`reports/` 與 `trades/` 是否已存在歷史報告或測試資料。**只要偵測到既有產物，即自動執行歷史覆盤**——載入最近一次建議與回測裁決，對照 `portfolio.db`（`trade_log`、`adaptation_history`）與最新行情檢驗先前建議表現，並優先引用仍具時效性的歷史回測數據，再銜接本輪診斷與建議生成。

---

## Stage 1：專案帳本、券商持倉與候選池同步 (`@prompts/portfolio_manager.md`)

1. **遵循規範**：[`@prompts/portfolio_manager.md`](../prompts/portfolio_manager.md)
2. **執行動作**：
   - 讀取 `projects/<PROJECT_NAME>/config.json`（載入基準指數、券商費率、風控參數、`prompts_mix.strategies` 混搭清單，以及**專案內任意自訂欄位與交易規則**）與 `projects/<PROJECT_NAME>/portfolio.db`（`account_summary`、`holdings`、`candidates`、`trade_log`、`adaptation_history`；若首次執行則從 `projects/template/` 初始化）。
   - **自動偵測歷史產物**：檢查 `projects/<PROJECT_NAME>/reports/INDEX.md`（或最新 `reports/*/`、`trades/*/`），若存在歷史報告或測試資料，載入最近一次 `run_meta.json`、`trade_advice.md` 與對應回測/穩健性裁決結果，留待 Stage 2 取得最新報價後進行自動覆盤比對。
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
3. **四層縱深風控檢核與強制風控覆蓋層（Mandatory Risk Overlay — 不可省略）**：
   - 遵循 [`@prompts/factors/risk_module.md`](../prompts/factors/risk_module.md)，**風控具備高於一切策略訊號的最高覆蓋權（Risk Overrides Alpha）**：
     - **回測階段強制內嵌風控**：凡執行策略回測（`RUN_BACKTEST = true`），不可僅跑無停損之純訊號原版；必須將 **初始硬停損（`max(6%, 2.0×ATR)`）**、**浮盈保本鎖定（`+8%` 移至成本 `+0.5%~+1%`）**、**動態 ATR 吊燈停利（`+15%~+20%` 後 `Peak - 2.5×ATR`）** 與 **波動率等風險倉位（單筆風險預算 `1.5%`）＋ 淨值回撤熔斷（`-10%` 減半 / `-15%` 冷卻）** 直接納入回測撮合引擎，並於報告與檢視器中對照「無風控原版 vs 風控強化版（Risk-Managed）」之單筆最大虧損、MDD、盈虧比與 Sharpe 改善幅度；嚴禁無硬停損策略直接進入實盤推薦。
     - **實盤持倉階段**：根據每檔持倉的**真實買入成本**與波段最高價，即時計算最新硬停損、保本鎖定線與吊燈停利線。
4. *(可選)* **候選池歷史回測與穩健性閘門 (`RUN_BACKTEST = true` 或 `config.json` 開啟 `robustness_gate`)**：
   - 若 `projects/<PROJECT_NAME>/trades/` 已有相同策略與標的之近期回測資料，預設先引用並檢視既有結果；若資料過期、策略組合變更或用戶要求重跑，則混入 [`@prompts/backtest.md`](../prompts/backtest.md) 執行回測並輸出至 `projects/<PROJECT_NAME>/trades/<YYYYMMDD_HHMM>_<strategy>_<scope>/`（含 HTML 研報、`backtest_result.db`、`backtest_report.md`）。
   - 同步調用 [`@prompts/analyze/robustness_testing_taxonomy.md`](../prompts/analyze/robustness_testing_taxonomy.md) 完成 WFO、滑價壓力與參數高原檢驗，將六維計分卡與 `VERDICT` 存檔為同目錄下的 `robustness_report.md`，並傳遞給 Stage 4。
5. *(選填歸檔)* 若本輪分析標的眾多，可將 Stage 3 的個股三情境診斷與策略掃描明細另存為 `projects/<PROJECT_NAME>/reports/<YYYYMMDD_HHMM>_<RUN_TAG>/analysis_snapshot.md`。

---

## Stage 4：產出實盤操作建議、歸檔索引與用戶採納閉環 (`@prompts/trade_advisor.md`)

1. **遵循規範**：[`@prompts/trade_advisor.md`](../prompts/trade_advisor.md)
2. **執行動作**：
   - 綜合 Stage 1~3 結果，以**當下系統測試時間**建立全新目錄並存檔至 `projects/<PROJECT_NAME>/reports/<YYYYMMDD_HHMM>_<RUN_TAG>/trade_advice.md`（若目錄已存在則加上秒數 `YYYYMMDD_HHMMSS`，嚴禁覆寫既有歷史報告）。
   - 報告必須包含：
     1. **執行條件標頭（Run Metadata Header）**：`run_id`、**測試時間 (`test_time`)**、資料截止日、本次 `MIX_STRATEGIES`、風控參數摘要、`robustness_gate` 裁決結果，以及關聯的 `trades/` 報告或 `review_viewer.html` 連結；
     2. ***(若有歷史紀錄則自動納入)* 前期結果自動回顧（Auto-Review）**：比對上一輪 `#S1, #S2, ...` 建議與歷史回測裁決，對照 `trade_log` 實際成交與最新市價之損益/命中表現；
     3. **全變體策略評估與跨體制穩定性矩陣（若執行回測）**：不可僅列摘要，必須完整展開所有測試變體之績效（必含 **勝率%、盈虧比 (`Payoff Ratio`)、獲利因子 (`PF`)、Sharpe、MDD%、摩擦稅**）以及跨量波體制（`Type 1 ~ Type 6` 與 Bull/Chop/Bear）之損益與穩定度評級；
     4. **近期買賣訊號掃描與在倉狀態**：明確列出近期（如近 10~30 交易日）各策略變體觸發的 `BUY / SELL` 訊號，以及截至最新交易日仍處於持倉中（`OPEN`）之變體與浮盈虧；
     5. **現有券商持倉動作表 & 候選觀察股池建倉排序表（中文直觀行動標籤 + 四層風控線）**：所有建議動作須以清晰中文標示（如「已觸發賣出／空倉觀望」、「持倉嚴守停損／空倉等止跌確認」、「順勢買進／上移保本停損」等），並提供建議買入區間、基於可用現金與 `ATR` 風險預算換算的建議股數、硬停損、保本線、吊燈停利、目標價與 R/R 比；
     6. **編號化可執行建議卡 (`#S1`, `#S2`, ...)**。
   - **統一覆盤資料庫、互動檢視器與索引追加（Append-Only）**：
     - 同步更新專案根目錄之 `projects/<PROJECT_NAME>/review.db` 與免伺服器互動式 `review_viewer.html`（含 K 線體制買賣點、全變體含盈虧比總表、6 體制穩定性熱圖、近期訊號、**全部歷史交易明細清單**、中文行動風控看板與歷史報告索引）。
     - **互動式檢視器 (`review_viewer.html`) 強制交互驗收規範**：
       1. **主副圖時間軸 100% 同步**：主圖（K 線／均線／布林／買賣點）與副圖（MACD／RSI／KDJ）必須共用同一條 `xaxis`（嚴禁分離為不同步的 `xaxis` / `xaxis2`），並開啟統一懸停準線（`hovermode: 'x unified'`）。
       2. **滾輪縮放時間跨度與自動校準 Y 軸**：啟用 `scrollZoom: true` 與 `dragmode: 'pan'`，鎖定 Y 軸不被滾輪誤縮放（`fixedrange: true`），並在 `plotly_relayout` 時依可視時間區間自動重算主副圖 Y 軸上下界。
       3. **雙擊重置必生效**：顯式綁定 `plotly_doubleclick` 事件（將 `xaxis.range` 重置回全區間並將 `yaxis.autorange`、`yaxis2.autorange` 設為 `true`），確保雙擊圖表能立即還原完整視窗。
       4. **點擊交易列聯動縮放主副圖**：主圖下方交易表、近期買賣訊號表、持倉中清單與全部交易明細表之每一列皆須支援點擊聯動——點擊後自動切換至對應標的／策略／變體，將主副圖平滑縮放至該筆交易區間（如進場日前 20 根至出場日後 20 根 K 線）並自動校準主副圖 Y 軸。
       5. **高對比買賣箭頭與全欄位排序**：買賣點標記禁止使用與紅綠 K 線混色的紅／綠色，須採高對比色（如 BUY ▲ 亮青藍 `#00E5FF` + 白框、SELL ▼ 亮洋紅 `#FF2EF5` + 白框、放大尺寸）；所有交易明細表皆須支援點擊欄位標題排序（進場日、出場日、淨損益、報酬%、持有天數、進場體制等，並顯示 ▲/▼ 排序箭頭）。
       6. **持倉期間與選定交易之半透明疊層標示（保留原體制底色）**：在保留原始 6 體制色帶的前提下，主副圖須以低透明度（alpha）貫穿疊層標記所有持倉交易區間（如獲利區間淡青藍、虧損區間淡洋紅）；點擊任一筆交易時，於該筆交易區間額外疊加半透明金黃高亮層（`rgba(250, 204, 21, 0.22)` + 虛線邊框貫穿主副圖），雙擊重置時恢復基礎疊層。
       7. **重大事件與新聞聯動（串接獨立 `events_news.db`）**：遵循 [`@prompts/data/event_dates.md`](../prompts/data/event_dates.md)，事件與新聞一律存於獨立按需增量資料庫（如 `data/sox_mag7_price_vol_types/events_news.db`，預設僅抓取專案所需標的，不預拉全市場）；K 線主圖須提供可切換開關的事件標記（`💰 財報`、`📢 SEC 8-K`、`⚡ 異常波動`）；點擊任一交易列時同步浮現該持倉期間（含前 3 日～後 2 日緩衝）之重大事件與新聞面板（附官方原文連結），並提供獨立「重大事件與新聞」分頁（點擊可跳轉縮放主副圖）。
     - 於當次報告目錄寫入 `run_meta.json`（記錄 `run_id`、`test_time`、資料截止日、策略混搭、回測目錄、`VERDICT`、建議清單與報告路徑）。
     - **以追加模式**寫入一筆新紀錄至 `projects/<PROJECT_NAME>/reports/INDEX.md`（若不存在則自動建立；既有歷史紀錄必須完整保留，形成多份帶測試時間的累積報告索引），方便日後跨期對比與下一次自動回顧。
3. **用戶回饋與帳本閉環**：
   - 等待用戶回覆實際決策（如：「我執行了 `#S1`，另外 `#S2` 我在券商買了 200 股成交在 151.5」），再由 `@prompts/portfolio_manager.md` 回寫至 `projects/<PROJECT_NAME>/portfolio.db`。
