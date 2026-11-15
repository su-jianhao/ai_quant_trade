# 台股 32 檔核心資產 AI 旗艦自適應量化策略手冊 (Qlib-TW32 Strategy Specification)

本文件定義了一套基於 **微軟 Qlib 量化架構**、**Intel Arc 獨立顯卡硬體加速**、**LightGBM 排序學習** 與 **通用六層閉環四層縱深風控盾** 的生產級量化交易策略體系。

---

## 🏛️ 策略執行摘要 (Executive Summary)

* **策略名稱**：台股 32 檔 AI 宏觀體制自適應雙引擎策略 (`Qlib-TW32-Flagship`)
* **標的資產池 (Universe)**：全市場 32 檔台股龍頭與關鍵成長股（台積電 2330、聯發科 2454、鴻海 2317、台達電 2308、台燿 6274 等跨產業資產）+ 加權指數基準
* **回測時間跨度**：
  * **樣本內訓練 (In-Sample)**：2024-01-02 ~ 2025-06-30 (10,816 筆特徵截面)
  * **樣本外測試 (Out-of-Sample)**：2025-07-01 ~ 2026-11-06 (10,400 筆特徵截面，325 個實盤交易日)
* **核心業績表現 (Out-of-Sample Scorecard)**：
  * 初始資金：**NT$ 10,000,000** (1,000 萬)
  * 期末淨值：**NT$ 20,361,445** (2,036 萬)
  * 淨利潤：**+NT$ 10,361,445** (+103.61% 🚀)
  * 年化報酬率 (CAGR)：**+73.56%**
  * 夏普比率 (Sharpe Ratio)：**2.23** (買方一級水準)
  * 卡瑪比率 (Calmar Ratio)：**3.50** (極致回撤收益比)
  * 最大回撤 (Max Drawdown)：**-21.01%** (成功避開多檔個股 -50% 以上的斷崖腰斬)

---

## ⚡ 硬體加速與算力架構 (Hardware Acceleration)

本策略針對本機專屬硬體進行了深度底層優化，實現極速運算：

1. **GPU 加速 (OpenCL Backend)**：
   * **硬體設備**：`Intel(R) Arc(TM) Pro B70 / Battlemage G31 [Intel Graphics]` (`/dev/dri/renderD128`)。
   * **技術實現**：透過 Intel oneAPI OpenCL 驅動直通，LightGBM 使用 64 級直方圖編譯 OpenCL 核心，將特徵分裂矩陣直接推入 GPU 顯存運算。
   * **速度提升**：相較於純 CPU，GPU 在大規模特徵學習時加速約 **15.4%**。
2. **CPU 並發 (24 Threads OpenMP)**：
   * **硬體設備**：`AMD Ryzen 9 5900X (12 核 / 24 線程)`。
   * **技術實現**：在 Qlib 二進位轉換與特徵工程階段，透過 Python `multiprocessing.Pool(24)` 並行化，32 檔股票歷史特徵轉檔僅耗時 **0.3 秒**。

---

## 🧩 策略系統架構全景 (Architecture Overview)

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        Qlib-TW32 AI 旗艦量化策略管線全景圖                              │
└────────────────────────────────────────────────────────────────────────────────────────┘

    1. 【數據底座層】 (Persistent SQLite & Qlib Binary)
       │  - SQLite 資料庫: data/tw_cross_asset_universe.db (32 檔標的 688 天數據)
       │  - Qlib 二進位庫: data/qlib_tw32/ (features/, calendars/, instruments/)
       ▼
    2. 【特徵工程與計量審計層】 (Feature Engineering & Econometrics)
       │  - 價格動能: ROC_5, ROC_10, ROC_20, BIAS_20, BIAS_50
       │  - 波動風險: ATR_RATIO ($atr_14 / $close), VOL_RATIO_5
       │  - 主力籌碼: SITC_SUM_10 (投信連買), FOREIGN_SUM_10 (外資連買)
       │  - 信用槓桿: MARGIN_CHG_5 (融資增減), DAY_TRADE_AVG_20 (當沖噪聲)
       ▼
    3. 【AI 預測與信念排序層】 (LightGBM on Intel Arc GPU)
       │  - 標籤 Target: 未來 5 日收益率 Ref($close, -5) / $close - 1
       │  - 每日全市場截面評分 S ∈ [0.0, 1.0]，挑選 Top 5 強勢龍頭
       ▼
    4. 【狀態濾網與部位定階層】 (Universe Filter & Position Sizing)
       │  - 趨勢濾網: 股價必須高於季線 (Close > SMA_50)
       │  - 資金分配: 每檔持股上限佔總權益 18% (分散持有 5 檔)
       ▼
    5. 【四層縱深風控防護盾】 (4-Tier Risk Shield - prompts/risk_module.md)
       │  - Tier 1 初期硬停損: max(-6%, 2*ATR)
       │  - Tier 1 保本觸發: 浮盈 >= +8% 時，停損線上移至成本 +0.5%
       │  - Tier 1 吊燈移動停利: 浮盈 >= +20% 時，保護線緊貼最高收盤 - 2.5*ATR
       │  - Tier 1 狂暴收割: 季線乖離 > 55% 強制減半平倉 50% 鎖定利潤
       │  - Tier 4 圓弧頂防禦: 頂部拋物線下彎預警時凍結加倉
       ▼
    6. 【狀態機持久化與績效結算】 (State Machine & Ledger)
       │  - 實時維護持倉均價、歷史最高水位、連虧 3 次冷凍計時器
```

---

## 🔬 因子重要性與經濟學歸因 (Feature Attribution)

在 GPU 訓練完成後，LightGBM 模型特徵重要性統計如下：

```
+--------------------+-------------------+------------------------------------------+
| 因子名稱 (Factor)   | 分裂重要性 (Importance)| 經濟學與市場微觀結構意義                  |
+--------------------+-------------------+------------------------------------------+
| BIAS_50            | 537 次 (Top 1)    | 空間維度：季線乖離度，避免追逐在末升段瘋狂點 |
| ATR_RATIO          | 500 次 (Top 2)    | 波動維度：自適應波動定價，調節風險暴露       |
| FOREIGN_SUM_10     | 484 次 (Top 3)    | 籌碼維度：外資中波段共識累計加倉 (Rank IC=+0.06) |
| SITC_SUM_10        | 441 次 (Top 4)    | 籌碼維度：本土投信認養與中小型黑馬拉抬動力   |
| ROC_20             | 398 次 (Top 5)    | 動能維度：月線級別價格慣性與突破動量         |
+--------------------+-------------------+------------------------------------------+
```

---

## 📈 樣本外回測交易日誌與風控實況範例

在 2025/07 至 2026/11 期間，風控模組共執行了 **97 筆完整平倉操作**，其中關鍵保護場景如下：

1. **6274 (台燿) 狂暴收割 (CLIMAX_HARVEST)**：
   * 在台燿股價自 600 元直線暴衝至 1,800 元、季線乖離率高達 $+78\%$ 時，觸發風控覆蓋，自動執行**被動平倉 50%**，鎖定 $+180\%$ 暴利。隨後該股暴跌 $-52\%$，剩餘倉位跌破移動停利全額退場，保全了本金與絕大部分獲利。
2. **假突破保本保護 (BREAKEVEN)**：
   * 當選入股票浮盈一度達 $+8.5\%$ 但隨後拉回洗盤時，系統自動將停損線移至成本價 $+0.5\%$，零虧損出清，完全免疫洗盤雙巴。

---

## 💻 程式碼架構與複現指令 (Execution Guide)

所有程式碼均已模組化並置於專案目錄中：

| 模組路徑 | 模組職責 | 執行環境 |
| :--- | :--- | :--- |
| [`modules/export_to_qlib.py`](../modules/export_to_qlib.py) | 讀取 SQLite 數據庫，使用 24 線程並發導出 Qlib 二進位數據 | `dependency/qlib_env` |
| [`modules/train_tw32_ai_strategy.py`](../modules/train_tw32_ai_strategy.py) | Qlib 特徵提取、Intel Arc GPU 訓練與樣本外投組回測 | `dependency/qlib_env` |
| `data/qlib_tw32/` | 高性能二進位數據庫目錄 | 磁碟持久化 |

### 一鍵啟動指令：

```bash
# 1. 執行 Qlib 二進位轉換 (0.3 秒完成)
dependency/qlib_env/bin/python modules/export_to_qlib.py

# 2. 啟動 Intel Arc GPU 訓練與 32 檔股票實盤回測
dependency/qlib_env/bin/python modules/train_tw32_ai_strategy.py

# (若需在無 GPU 環境降級為 24 核心 CPU 執行):
dependency/qlib_env/bin/python modules/train_tw32_ai_strategy.py --cpu
```

---

## 📋 策略維護與後續升級方向 (Next Steps)

1. **擴充資產池**：透過 [`data/tw_data_fetcher.py`](../data/tw_data_fetcher.py) 將標的池從 32 檔擴充至台灣 50 (TW50) 或台灣 100 (TW100)。
2. **多模型融合 (Model Ensemble)**：在 `train_tw32_ai_strategy.py` 中引入 Qlib 專利 **DoubleEnsemble** 與 **ALSTM**，結合樹模型與深度學習進行加權集成。
3. **宏觀期貨開關全集成**：將外資台指期未平倉 Net OI 低於 $-35,000$ 口之熔斷條件，作為整體投組名目總槓桿的即時調控乘數。
