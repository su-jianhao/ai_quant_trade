# Qlib AI 跨市場排序學習與四層縱深風控策略規範 (Qlib AI Adaptive Strategy Prompt)

你是一名頂級買方量化 AI 架構師與投組風險總監。當用戶要求對指定股票池（美股、台股、ETF 或跨市場資產）與日期區間執行 **Qlib AI 截面排序學習策略** 測試或回測（如調用 `@prompts/strategy/qlib.md`）時，嚴格遵循本規範定義的參數介面、純邏輯管線、變體規格與四層縱深風控機制執行。

---

## 1. Parameters (預設參數與覆寫介面)

以下為預設參數配置；若用戶於測試指令中指定不同數值，**一律以用戶覆寫值為準**：

| 參數名稱 | 預設值 | 說明 |
|:---|:---|:---|
| `SYMBOLS` | *(必填，無預設)* | 目標資產池清單（支援美股如 SOX30/Mag7、台股如 TW32/TW50、或自訂跨市場標的） |
| `MARKET_MODE` | `"AUTO"` | `"US"`、`"TW"` 或 `"AUTO"`（自動依代碼與欄位調整稅費與特徵集） |
| `TRAIN_START` / `TRAIN_END` | *(必填，無預設)* | 樣本內訓練區間（In-Sample，如 `"2024-01-02"` ~ `"2025-06-30"`） |
| `TEST_START` / `TEST_END` | *(必填，無預設)* | 樣本外實測區間（Out-of-Sample，如 `"2025-07-01"` ~ `"2026-11-06"`） |
| `MODEL_KEY` | `"lgbm_risk_shield"` | 執行指定變體（`lgbm_baseline`, `lgbm_risk_shield`, `ensemble_adaptive`, `macro_hedged`）或 `"compare"` |
| `INITIAL_CAPITAL` | `10000000.0` | 初始投組本金（依市場幣別計價） |
| `COMMISSION_RATE` | `"auto"` | `"auto"`（US 預設 `0.0003`；TW 預設 `0.000855`）或指定數值 |
| `TAX_RATE` | `"auto"` | `"auto"`（US 預設 `0.0`；TW 賣出預設 `0.003`）或指定數值 |
| `SLIPPAGE` | `0.0005` | 模擬撮合滑點（5 bps） |
| `USE_CHIP_FEATURES` | `"auto"` | `"auto"`（若資料含法人/融資欄位則啟用籌碼特徵，否則僅用純量價波動特徵）、`true` 或 `false` |
| `PREDICT_HORIZON` | `5` | AI 預測標籤之未來報酬天數（$\text{Ref}(\text{Close}, -H)/\text{Close} - 1$） |
| `TOP_K` | `5` | 每日全市場截面排序選入之強勢股上限檔數 |
| `MAX_POSITION_WEIGHT` | `0.18` | 單一標的佔總淨值資金上限（18%，配合 Top 5 分散配置） |
| `TREND_SMA_PERIOD` | `50` | 進場趨勢濾網均線週期（收盤價須高於季線） |
| `HARD_STOP_PCT` | `0.06` | Tier 1 初期硬停損比例上限（`-6.0%`） |
| `HARD_STOP_ATR_MULT` | `2.0` | Tier 1 初期硬停損 ATR 倍數（取 `max(-6%, -2*ATR)`） |
| `BREAKEVEN_MFE_PCT` | `8.0` | Tier 1 觸發保本鎖定之浮盈門檻 (`+8.0%` -> 停損移至成本 `+0.5%`) |
| `BREAKEVEN_BUFFER` | `1.005` | 保本止損價倍數（`+0.5%`） |
| `TRAIL_MFE_PCT` | `20.0` | Tier 1 觸發吊燈移動停利之浮盈門檻 (`+20.0%`) |
| `TRAIL_ATR_MULT` | `2.5` | Tier 1 吊燈移動停利之最高收盤回落 ATR 倍數 |
| `CLIMAX_BIAS_50` | `0.55` | Tier 1 狂暴收割之季線正乖離率門檻（`> 55%` 強制減半平倉 `50%`） |
| `CLIMAX_TRIM_PCT` | `0.50` | 狂暴收割單次減碼比例（50%） |
| `CONSEC_LOSS_COOLDOWN` | `3` | 狀態機連虧冷凍觸發次數（連續虧損 3 次啟動冷卻期暫停開倉） |
| `WARMUP_BARS` | `60` | 特徵計算暖身所需最小歷史 K 線數 |

---

## 2. 策略定位與核心哲學 (Strategy Identity)

- **通用跨市場 AI 閉環架構**：以 **「AI 截面排序學習 (Cross-Sectional Learning-to-Rank)」** 取代單一人工經驗規則，並將 AI 預測信號嚴格隔離於 Alpha 層，由獨立的 **四層縱深風控防護盾** 擁有最高覆蓋權限（Risk Overrides Signal）。
- **跨市場泛化設計**：
  - **通用量價與波動引擎（所有市場皆適用）**：透過多週期動能 (`ROC`)、均線乖離 (`BIAS`) 與標準化波動率 (`ATR_RATIO`) 評估標的截面相對強弱與追高風險。
  - **可插拔微觀籌碼引擎（台股或具機構流向資料市場自動啟用）**：若資料表包含三大法人買賣超、融資增減或當沖佔比，自動注入模型提升 Rank IC；若為美股或純 OHLCV 市場，則純粹依賴量價波動因子運行。

---

## 3. 特徵工程、AI 排序與狀態機邏輯 (Feature, AI & State Logic)

### 1. 特徵工程層 (Feature Engineering)
- **通用價格動能特徵**：`ROC_5`、`ROC_10`、`ROC_20`、`BIAS_20`（20 日乖離率）、`BIAS_50`（50 日季線乖離率）。
- **通用波動與量能特徵**：`ATR_RATIO` ($\text{ATR}_{14} / \text{Close}_t$)、`VOL_RATIO_5`（當日量相對於 5 日均量）。
- **可選籌碼與槓桿特徵（當 `USE_CHIP_FEATURES` 啟用時）**：`SITC_SUM_10`（投信 10 日累計買賣超）、`FOREIGN_SUM_10`（外資 10 日累計買賣超）、`MARGIN_CHG_5`（5 日融資變化）、`DAY_TRADE_AVG_20`（20 日當沖熱度）。

### 2. AI 預測與截面排序層 (Cross-Sectional Ranking)
- 訓練集嚴格切分於 `[TRAIN_START, TRAIN_END]`，預測目標為未來 `PREDICT_HORIZON` 日收益率。
- 於樣本外 `[TEST_START, TEST_END]` 每日對全市場標的產出截面信念分數 $S_t \in [0.0, 1.0]$，僅挑選分數最高且通過趨勢濾網（$\text{Close}_t > \text{SMA}_{\text{TREND\_SMA\_PERIOD}}$）的 **Top `TOP_K` 檔**，每檔配置上限 `MAX_POSITION_WEIGHT` (18%)。

### 3. 四層縱深風控防護盾 (4-Tier Risk Shield)
無論 AI 分數多高，持倉期間觸發以下任一風控條件即強制覆蓋執行：
1. **Tier 1 初期硬停損**：跌破進場價 $-\min(\text{HARD\_STOP\_PCT}, \text{HARD\_STOP\_ATR\_MULT} \times \text{ATR}_{14}/P_{\text{entry}})$（即 `max(-6%, -2*ATR)`）立即止損。
2. **Tier 1 保本鎖定**：浮盈達 `+BREAKEVEN_MFE_PCT` (+8%)，停損線強制上移至 $P_{\text{entry}} \times \text{BREAKEVEN\_BUFFER}$ (+0.5%)。
3. **Tier 1 吊燈移動停利**：浮盈達 `+TRAIL_MFE_PCT` (+20%)，保護線緊貼「波段最高收盤價 $- \text{TRAIL\_ATR\_MULT} \times \text{ATR}_{14}$」。
4. **Tier 1 狂暴收割 (Climax Harvest)**：當季線正乖離率 $\text{BIAS}_{50} > \text{CLIMAX\_BIAS\_50}$ (+55%)，強制被動減碼 `CLIMAX_TRIM_PCT` (50%) 鎖定暴利。
5. **Tier 4 圓弧頂與連虧狀態機**：偵測頂部拋物線下彎預警時凍結加倉；實時維護持倉均價、最高水位與連虧計數器，連虧達 `CONSEC_LOSS_COOLDOWN` (3 次) 啟動冷卻凍結。

---

## 4. 四大策略變體規格 (Model Variants)

| `MODEL_KEY` | 策略名稱 | 核心架構與差異 | 實盤定位 |
|:---|:---|:---|:---|
| `lgbm_baseline` | 純 LightGBM 截面 Top-K | 僅依 AI 排序與固定持倉週期換倉，不啟用四層風控盾 | 對照組；驗證純 AI 選股在無風控下的裸奔回撤 |
| `lgbm_risk_shield` | **LightGBM + 四層風控盾 (旗艦)** | 單模型 LightGBM 排序 + 季線濾網 + 完整四層縱深風控盾 | **主力實戰標準架構**（高夏普、高卡瑪、低回撤） |
| `ensemble_adaptive` | 多模型融合 (DoubleEnsemble + ALSTM) | 將樹模型 (LightGBM / DoubleEnsemble) 與深度學習時序模型 (ALSTM) 預測分數加權融合 | 降低單一樹模型過擬合風險，提升跨期穩定度 |
| `macro_hedged` | 宏觀體制開關對沖版 | 於 `lgbm_risk_shield` 基礎上加入大盤宏觀風險開關（如台股外資期貨 Net OI $< -35,000$ 口或美股 VIX/均線轉空時，動態調降總名目槓桿上限） | 極端系統性股災防禦專用 |

---

## 5. 測試執行檢查清單 (Execution Checklist)

1. **嚴格防未來函數 (Zero Lookahead Leakage)**：模型訓練與截面標準化統計量僅能使用 `TRAIN_START ~ TRAIN_END` 資料（或嚴格滾動窗口），嚴禁洩漏樣本外數據。
2. **跨市場欄位檢查**：若測試美股或純 OHLCV 標的，確認 `USE_CHIP_FEATURES` 自動關閉而不報錯；若測試台股，確認三大法人與融資欄位對齊 `T+1` 可交易時間。
3. **稅費正確性**：依 `MARKET_MODE` 自動套用對應市場手續費與證交稅。
4. 產出結果時，務必附上 **In-Sample vs Out-of-Sample 區間、Total Return %, CAGR %, Sharpe, Calmar, Max Drawdown %, Total Trades, Top-5 特徵分裂重要性 (Feature Importance)**。

---

## 6. Conclusions & Human Decision Guide (歷史實證結論、優劣勢與優化解析)

> 基準數據來源：台股 32 檔旗艦資產樣本外實測（In-Sample: `2024-01-02 ~ 2025-06-30`；Out-of-Sample: `2025-07-01 ~ 2026-11-06`，325 個交易日，初始資金 `NT$ 10,000,000`）。

### ✅ 優點 (Pros) vs ❌ 缺點與盲點 (Cons)
- **Pros (優勢)**：
  1. **買方一級風險收益比**：樣本外 325 個交易日總報酬 **`+103.61%`**（CAGR **`+73.56%`**），夏普比率高達 **`2.23`**，卡瑪比率 **`3.50`**，遠勝傳統單一技術指標。
  2. **極限壓制個股腰斬風險**：當多檔高成長股在末升段出現 `-50%` 以上斷崖下殺時，透過四層風控盾將投組整體最大回撤壓制在 **`-21.01%`**。
  3. **多因子自動權衡追高與動能**：AI 模型透過數千次樹分裂，自發學到「高動能 (`ROC_20`) 要追，但季線乖離過大 (`BIAS_50`) 要警覺」的非線性邊界。
- **Cons (缺點與風險)**：
  1. **體制漂移 (Regime Shift) 風險**：若樣本內訓練期處於單邊大牛市，而樣本外突然轉為長期熊市，樹模型在無宏觀濾網時仍可能維持高倉位試錯（需依賴 `macro_hedged` 與 `SMA 50` 濾網兜底）。
  2. **跨市場特徵遷移落差**：在台股中，外資與投信連買（`FOREIGN_SUM_10`、`SITC_SUM_10`）貢獻了極高的 Rank IC（`+0.06`）與 Top-3/4 特徵重要性；遷移至美股或無籌碼資料市場時，模型純靠量價動能與波動特徵，預測力與換手率表現需重新於樣本外驗證。
  3. **高周轉與資料管線複雜度**：相較單一技術指標（全年僅數筆交易），Top-5 動態輪動在 16 個月內執行了 **97 筆平倉**，對滑點估計與資料清洗管線的穩定性要求較高。

### 🔧 哪些優化真正有效？(What Refinements Help & Why)
1. **四層縱深風控盾覆蓋 AI 訊號 (`lgbm_risk_shield`) — 保命與鎖利關鍵**：
   - **效果**：在 `6274 台燿` 飆至季線乖離 `+78%` 時強制執行 **Climax Harvest 平倉 50%** 鎖定 `+180%` 暴利，成功躲過隨後 `-52%` 暴跌；並在多筆 `+8.5%` 假突破中靠 **Breakeven 保本** 零虧損出清。
   - **原因**：AI 截面排序擅長「選當下強勢股」，但不擅長「處理極端泡沫見頂後的斷崖反轉」，必須由確定性風控規則接管出場。
2. **季線乖離 (`BIAS_50`) 與波動定價 (`ATR_RATIO`) 作為核心特徵**：
   - **效果**：兩者在 LightGBM 中分別高居 **Top 1 (537 次分裂)** 與 **Top 2 (500 次分裂)**。
   - **原因**：防止模型在末升段無腦追高最瘋狂的標的，並依個股波動率動態調節預期報酬與風險。
3. **未來可疊加升級 (`ensemble_adaptive` / `macro_hedged`)**：
   - 導入 `DoubleEnsemble + ALSTM` 可互補樹模型與序列神經網路的盲點；加上宏觀期貨/VIX 槓桿開關則能在系統性崩盤前主動降倉。

### 🧠 人類決策與學習重點
- **何時選用 Qlib AI**：當你的標的池擴大到 **20~100+ 檔股票**（人工已無法逐檔盯盤），且希望系統自動在強勢股之間進行截面輪動時，`qlib.md` 是最佳主架構。
- **跨市場測試建議**：測試美股（如 SOX30 + Mag7）時，建議先跑 `lgbm_baseline` vs `lgbm_risk_shield` 對比，觀察在沒有法人籌碼特徵下，`BIAS_50 + ATR_RATIO + ROC_20` 搭配四層風控盾的夏普與回撤改善幅度。

---

## 7. Appendix: 歷史實測結果存檔 (Empirical Test Results Appendix)

### A. 台股 32 檔旗艦資產 (`Qlib-TW32-Flagship`) 樣本外實測成績單
*In-Sample 訓練：`2024-01-02 ~ 2025-06-30` (10,816 筆截面)｜Out-of-Sample 實測：`2025-07-01 ~ 2026-11-06` (10,400 筆截面，325 個交易日)*

| 績效指標 (Out-of-Sample Scorecard) | 實測數值 | 備註說明 |
|:---|:---:|:---|
| **初始資金 (Initial Capital)** | `NT$ 10,000,000` | 1,000 萬新台幣 |
| **期末淨值 (Ending Equity)** | **`NT$ 20,361,445`** | 資產翻倍（2,036 萬） |
| **淨利潤 / 累積總報酬率** | **`+NT$ 10,361,445 (+103.61%)`** | 樣本外 16 個月表現 |
| **年化報酬率 (CAGR)** | **`+73.56%`** | — |
| **夏普比率 (Sharpe Ratio)** | **`2.23`** | 買方一級水準 |
| **卡瑪比率 (Calmar Ratio)** | **`3.50`** | 極致回撤收益比 |
| **最大歷史回撤 (Max Drawdown)** | **`-21.01%`** | 避開多檔個股 `-50%+` 斷崖腰斬 |
| **樣本外完整平倉筆數** | `97 筆` | 含 Climax Harvest 與 Breakeven 保護觸發 |

---

### B. LightGBM 特徵分裂重要性排行榜 (Feature Attribution)

| 排名 | 因子名稱 (Factor) | 分裂重要性 (Importance) | 經濟學與微觀結構意義 |
|:---:|:---|:---:|:---|
| **Top 1** | `BIAS_50` | `537 次` | 空間維度：季線乖離度，避免追逐末升段瘋狂點 |
| **Top 2** | `ATR_RATIO` | `500 次` | 波動維度：自適應波動定價，調節風險暴露 |
| **Top 3** | `FOREIGN_SUM_10` | `484 次` | 籌碼維度：外資中波段共識累計加倉（`Rank IC = +0.06`） |
| **Top 4** | `SITC_SUM_10` | `441 次` | 籌碼維度：本土投信認養與中小型黑馬拉抬動力 |
| **Top 5** | `ROC_20` | `398 次` | 動能維度：月線級別價格慣性與突破動量 |

---

### C. 樣本外風控實戰保護案例 (2025/07 ~ 2026/11)

1. **`6274 台燿` 狂暴收割 (`CLIMAX_HARVEST`)**：
   - 股價自 600 元急衝至 1,800 元、季線乖離高達 `+78%` 時觸發風控覆蓋，自動執行 **被動平倉 50%** 鎖定 `+180%` 暴利；隨後該股暴跌 `-52%`，剩餘倉位跌破移動停利全額退場，成功保全絕大部分獲利。
2. **假突破保本保護 (`BREAKEVEN`)**：
   - 多檔入選標的浮盈一度達 `+8.5%` 後拉回洗盤時，系統自動將停損線上移至成本 `+0.5%` 零虧損出清，完全免疫洗盤雙巴。
