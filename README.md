# AI QUANT TRADE

## 📑 目錄 (Table of Contents)

- [Overall Architecture 交易系統](#overall-architecture-交易系統)
  - [1. 資料與測試](#1-資料與測試)
  - [2. 選股池階段](#2-選股池階段)
  - [3. 策略操作](#3-策略操作)
  - [4. 改進模組與測試模組關係](#4-改進模組與測試模組關係)
- [交易](#交易)
- [因子研究](#因子研究)
- [Usage](#usage)

---

## Overall Architecture 交易系統

### 1. 資料與測試
- 資料抓取、防雷（倖存者偏差 / PIT / 雙價格軌道）與多週期生成：[prompts/data_generate.md](prompts/data_generate.md)
- **Factors（因子分類）**：
  - **Trend（趨勢）**：`Up` / `Down` / `Chop`
  - **Volatility（波動度）**：低 / 中 / 高
  - 趨勢 × 波動率六階段切分：[prompts/data/human_stage_trend_vol.md](prompts/data/human_stage_trend_vol.md)
  - 漲跌震盪階段切分：[prompts/data/human_stage_up_down_chop.md](prompts/data/human_stage_up_down_chop.md)
  - 測試資料類型與台股/事件參考：[prompts/data/test_data_archetypes.md](prompts/data/test_data_archetypes.md)、[prompts/data/taiwan.md](prompts/data/taiwan.md)、[prompts/data/event_dates.md](prompts/data/event_dates.md)
  - 因子體系總覽：[prompts/factors.md](prompts/factors.md)（細分目錄：[prompts/factors/](prompts/factors/)）
- DATA is generated in `data/{target}/` folder.

### 2. 選股池階段

> **核心理論**：選一個有方向性的股票，Buy & Hold (B&H) 比策略操作更直接、利潤更高。

- **基本面選股**：依據營收成長、獲利能力、估值與現金流等基本面條件篩選優質標的
- **策略型選股**：結合技術面、籌碼面或多因子量化條件篩選具備動能或結構優勢的標的
- **ETF 選股**：篩選具備明確趨勢或產業代表性的 ETF 標的（如 `QQQ`、`SOXX`、`0050.TW`）
- 選股篩選規範：[prompts/stock_selector.md](prompts/stock_selector.md)
- 個股全維度投研與多情境推演（已整併原 `full_report.md`）：[prompts/stock_analysis.md](prompts/stock_analysis.md)
### 3. 策略操作

- **進出場 Signal**：選擇標的的重要性與出場時機的關鍵性
- **狀態判斷**：標的與市場狀態評估（`Good` / `Bad` / `Status`）
- **風險控制**：倉位管理與停損風控機制
- 通用策略架構：[prompts/general_strategy.md](prompts/general_strategy.md)
- 風控模組規範：[prompts/factors/risk_module.md](prompts/factors/risk_module.md)
- 量化回測與研報規範：[prompts/backtest.md](prompts/backtest.md)
- 策略庫總目錄（含 MACD / 布林 / KDJ / RSI / 三位一體 / 台股籌碼 / 海龜 / 生命週期 / Qlib）：[prompts/strategy/README.md](prompts/strategy/README.md)（生命週期策略：[prompts/strategy/regime_stage_strategy.md](prompts/strategy/regime_stage_strategy.md)）
- Backtest result: generated in `trades/{test_strategy}_{time}_{stocks}/` folder


### 4. 改進模組與測試模組關係

- **總論**：改進模組與測試模組的定位與回饋閉環
- **逐筆分析**：交易明細歸因與損益拆解
- **改進**：依據分析結果進行策略與參數優化
- 績效覆盤與迭代工作流：[prompts/strategy/quantitative_performance_workflow.md](prompts/strategy/quantitative_performance_workflow.md)
- 穩健性檢驗六維矩陣：[prompts/analyze/robustness_testing_taxonomy.md](prompts/analyze/robustness_testing_taxonomy.md)
- 趨勢轉折剖析：[prompts/analyze/trend_change.md](prompts/analyze/trend_change.md)
- 個股綜合診斷與情境復盤：[prompts/stock_analysis.md](prompts/stock_analysis.md)
---

## 交易 TO BE DONE

- **標的選擇**：選擇一個具備潛力與趨勢優勢的好標的
- **時機與風險**：選擇合適的交易時間窗口並評估風險報酬比
- **階段與買點**：市場存在多個運行階段與對應買點，依階段特性調整操作
- **風險管理與交易方法**：制定嚴謹的風險管理規範與系統化交易方法
- **交易訊號與資金配置**：依據明確的交易訊號進行分階段投注（Scaling In / Out）

### 市場環境與因子動態權重

> **核心思考**：牛市與熊市，你會看同樣的指標嗎？  
> 在不同的市場環境下，各類因子的有效性與權重並不相同：

- **牛市（Bull Market）**：動量因子（`ROCP`、`RSI`）更重要 → **趨勢跟隨**
- **熊市（Bear Market）**：防禦因子（波動率、換手率）更重要 → **風險規避**
- **震盪市（Chop / Sideways）**：均值回歸因子（乖離率）更重要 → **高拋低吸**

---

## 因子研究 TO BE DONE

### 1. 因子體系與研究基礎

- **多維度因子**：基本面 / 技術面 / 籌碼面
- **衍生因子（導數特徵）**：價格與指標的一階/二階變化率（斜率、加速度等）
- **風控因子化**：將風險控制方法轉化為量化因子
- **未知事件風險（Risk for Unknown Events）**：針對突發性或黑天鵝事件的防禦性因子設計
- **參考研究**：華泰金工因子研究體系
- **工具庫（Lib）**：`TA-Lib`、`Qlib`

### 2. 因子應用

- **入場 / 出場信號**：進出場觸發條件設計
- **狀態判別**：辨識市況與標的所處階段（Regime Classification）
- **信號品質與容錯**：過濾真假信號、處理多次重複訊號與容錯修正機制
- **協同濾波**：多因子交叉驗證與共鳴過濾
- **場景化調適與優化**：針對不同個股、不同市場與特定場景進行參數選擇與動態調適

---

## Usage

### 0. Python 環境設定
- **Prompt**：`follow @prompts/python_venv.md to setup python venv and packages`

### 1. 獲取 / 增量同步股票數據 (Get & Sync Data)
- **Prompt**：
  - 全量建庫（股票池）：`use @prompts/data_generate.md to generate data for tw50`（支援 `tw50`、`sox`、`sp500`、`nasdaq100`、`mag7`）
  - 單一標的：`use @prompts/data_generate.md for 2330.TW`（或 `NVDA`）
  - 增量同步最新數據：`use @prompts/data_generate.md to sync latest data for tw50`
- **CLI 指令**：
  ```bash
  # 自動模式：若 data/{target}/<target>_<year>.db 已存在則增量同步，否則全量建庫
  python3 -m modules.data_generator --target tw50 --year 2026 --workers 4

  # 強制全量重抓
  python3 -m modules.data_generator --target tw50 --year 2026 --workers 4 --mode full
  ```
- **產出位置 (`data/{target}/`)**：
  - `<target>_<year>.db`（多週期 SQLite 數據庫，台股含 `taiwan_chips_daily`）
  - `<target>_<year>_data.md`（量化總賬 / 橫截面摘要）
  - `<target>_<year>_GUI.html`（Plotly 交互式可視化工作台）
  - `universe.json`（股票池成分股元數據）

### 2. 股票趨勢 × 波動率分類 (Separate Stocks into Types)
- **Prompt**：`follow @prompts/data/human_stage_trend_vol.md to refine data for tw50`
- **CLI 指令**：
  ```bash
  python3 -m modules.stage_trend_vol --target tw50 --year 2026
  ```
- **分類結果**：依 15% ZigZag 趨勢（`UP` / `DOWN` / `CHOP`）× 個股歷史中位 `HV20%` 波動率（`LOW_VOL` / `HIGH_VOL`），切分為 6 類市況（`UP_LOW_VOL`、`UP_HIGH_VOL`、`DOWN_LOW_VOL`、`DOWN_HIGH_VOL`、`CHOP_LOW_VOL`、`CHOP_HIGH_VOL`）。
- **產出位置 (`data/{target}/`)**：
  - SQLite 資料表：`trend_vol_stages`（寫入 `<target>_<year>.db`）
  - 回測標準 CSV：`<target>_<year>_trend_vol_stages.csv`
  - 三聯圖人工標註工作台：`<target>_<year>_trend_vol_viewer.html`
  - 階段統計報告：`<target>_<year>_trend_vol_report.md`

### 3. 策略回測與 QuantStats 績效報告 (Run Backtest & QuantStats Report)
- **Prompt**：
  - 全變體對比回測：`do a bollinger strategy test @prompts/strategy/bollinger_strategy.md following @prompts/backtest.md using tw50 data`
  - 指定單一變體：`run backtest for tw50 using @prompts/strategy/bollinger_strategy.md with MODEL_KEY=regime_adaptive`
- **CLI 指令**：
  ```bash
  # 對 TW50 執行布林通道七大變體對比回測，並生成 QuantStats Tear Sheets 與綜合研報
  python3 -m modules.backtest --target tw50 --strategy bollinger --model compare

  # 指定輸出目錄與單筆開倉金額
  python3 -m modules.backtest --target tw50 --strategy bollinger --model regime_adaptive --fixed-cash 100000 --output-dir trades/bollinger_custom_tw50
  ```
- **產出位置 (`trades/{test_strategy}_{time}_{stocks}/`)**：
  - `<target>_<strategy>_QuantStats_Report.html`（綜合暗色互動研報：KPI 卡片、Key Performance Metrics 總表、累計報酬/回撤、月報酬熱力圖、風險報酬散佈/滾動夏普、損益分佈與可篩選成交流水）
  - `quantstats/quantstats_<model>.html`（各變體官方 QuantStats Tear Sheet HTML 報告）
  - `backtest_result.db`（持久化 `backtest_summary`、`backtest_trades`、`backtest_equity_curve` 三張表）
  - `backtest_report.md`（Markdown 績效對照與風格歸類報告）

### 4. 個股全維度分析與多情境推演 (Stock Analysis & Scenario Simulation)
- **Prompt**：
  - 單一標的：`use @prompts/stock_analysis.md for NVDA`（或 `2330.TW`）
  - 多標的 / 股票池組合：`do @prompts/stock_analysis.md for nvda/intc/qcom and mag7`
- **分析維度**：Tier 1~4 因子優先級金字塔（資產/CYQ 籌碼 > 趨勢/FCF/衍生品 > 動能/曲率 > 波動/宏觀）、核心多空矛盾推演，以及機率總和 100% 的三重前瞻情境樹（多頭主升 / 箱體震盪 / 破位下跌）與建倉/停損點位。
- **產出位置 (`reports/<YYYY-MM-DD>_<ticker>/`)**：
  - `market_analysis.md`（中文深度投研報告與三情境操作手冊）
  - `market_analysis.html`（Plotly 深色主題 4 聯動面板互動儀表板：K 線均線、量能與 CYQ 獲利盤、MACD+BIAS50、RSI/AI 評分）

### 5. 通用 SQLite 資料庫檢視器 (General SQLite DB Viewer)
- **檔案位置**：[modules/viewer.py](modules/viewer.py) / [modules/viewer.html](modules/viewer.html)
- **使用方式**：
  - **純瀏覽器模式**：直接開啟 `modules/viewer.html`，拖曳或選取 `data/` 或 `trades/` 下的任意 `.db` 檔案即可檢視。
  - **本地伺服器模式**（自動列出專案內所有 `.db` 並一鍵切換）：
    ```bash
    # 重新產生 viewer.html
    python3 -m modules.viewer

    # 啟動本地伺服器並開啟瀏覽器
    python3 -m modules.viewer --serve --db data/tw50/tw50_2026.db
    ```
- **核心功能**：
  - **Price / Volume & 動態指標/指數選項清單**：依 `Date` 軸同步顯示 K 線與成交量，自動列出資料庫內所有可用指標與指數（`ema_*`, `sma_*`, `boll_*`, `macd_*`, `rsi_14`, `kdj_*`, `atr_14`, `cyq_*`, `nq_close`, `es_close`, `vix_close` 及台股籌碼欄位），勾選即即時疊加於主圖或下方副圖；支援切換全部 / 近 90 / 近 30 個交易日。
  - **回測庫視覺化**：開啟 `backtest_result.db` 時自動繪製各變體與 Benchmark 淨值曲線。
  - **Table Explorer**：支援切換檢視所有資料表、關鍵字搜尋、自訂 SQL 查詢與 CSV 匯出。


## TODO
- general ui.


## reference
- https://github.com/henrylin99/quantitative_analysis
- https://github.com/tauricresearch/tradingagents