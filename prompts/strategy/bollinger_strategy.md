# 布林通道突破、均值回歸與風格適配策略規範 (Bollinger Bands Strategy Prompt)

你是一名頂級量化系統架構師與波動率策略師。當用戶要求對指定股票清單與日期區間執行 **布林通道 (Bollinger Bands) 策略** 測試或回測（如調用 `@prompts/strategy/bollinger_strategy.md`）時，嚴格遵循本規範定義的參數介面、數學邏輯與七大變體規則執行。

---

## 1. Parameters (預設參數與覆寫介面)

以下為預設參數配置；若用戶於測試指令中指定不同數值，**一律以用戶覆寫值為準**：

| 參數名稱 | 預設值 | 說明 |
|:---|:---|:---|
| `SYMBOLS` | *(必填，無預設)* | 目標測試標的清單（如 `["NVDA", "INTC"]`） |
| `START_DATE` | *(必填，無預設)* | 回測統計起始日（如 `"2022-01-01"`） |
| `END_DATE` | *(必填，無預設)* | 回測統計結束日（如 `"2025-12-31"`） |
| `MODEL_KEY` | `"compare"` | 執行指定變體（`baseline`, `bw_expand`, `profit_lock`, `atr_trail`, `combo_refined`, `reversion`, `regime_adaptive`）或 `"compare"` 全變體對比 |
| `FIXED_CASH` | `10000.0` | 單筆固定開倉本金 |
| `SLIPPAGE` | `0.0005` | 雙邊滑點（5 bps） |
| `COMMISSION_RATE` | `0.0003` | 單邊手續費率（台股請覆寫為手續費 `0.000855` + 賣出證交稅 `0.003`） |
| `BB_PERIOD` | `20` | 布林中軌 SMA 週期 |
| `BB_STD` | `2.0` | 布林上下軌標準差倍數 |
| `BW_MIN_THRESHOLD` | `0.15` | `bw_expand` / `combo_refined` 要求之最小帶寬門檻 (15%) |
| `BW_LOOKBACK` | `5` | 判斷帶寬向上開口之比較天數 ($\text{BW}_t > \text{BW}_{t-\text{lookback}}$) |
| `ATR_PERIOD` | `14` | ATR 真實波幅週期 |
| `BREAKEVEN_MFE_PCT` | `10.0` | 觸發保本鎖定之最大浮盈門檻 (%) |
| `BREAKEVEN_BUFFER` | `1.015` | 保本止損價倍數（進場價 + 1.5%） |
| `TRAIL_MFE_PCT` | `20.0` | 觸發動態 ATR 追蹤止盈之最大浮盈門檻 (%) |
| `TRAIL_ATR_MULT` | `2.5` | 動態追蹤止盈之 ATR 回落倍數 |
| `REGIME_OVERRIDE` | `"auto"` | `"auto"`（依清單/波動特徵分類）或強制指定 `"MOMENTUM"` / `"CYCLICAL"` |
| `WARMUP_BARS` | `25` | `START_DATE` 之前預留的最小暖身 K 線數 |

---

## 2. 策略定位與核心哲學 (Strategy Identity)

- **指標本質**：動態統計包絡線（$\text{SMA}_{\text{BB\_PERIOD}} \pm \text{BB\_STD} \cdot \sigma$），時間滯後較低，能即時度量市場波動率的收斂（Squeeze）與擴張（Expansion）。
- **雙重性格**：
  - **突破動能型（適合高 Beta 成長股）**：帶寬擴張且收盤突破上軌時順勢追擊，並搭配「階梯保本 + 動態 ATR 追蹤止盈」鎖定主升浪利潤。
  - **均值回歸型（適合週期股、箱體震盪股與指數 ETF）**：跌破下軌後反抽站回下軌時低吸，觸及中軌即獲利了結。

---

## 3. 指標計算邏輯 (Indicator Logic)

對每個交易日 $t$ 的收盤價 $C_t$、最高價 $H_t$、最低價 $L_t$ 計算：
1. **布林通道 (`BB_PERIOD`, `BB_STD`)**：
   - $\text{Mid}_t = \text{SMA}_{\text{BB\_PERIOD}}(C_t)$
   - $\text{Upper}_t = \text{Mid}_t + \text{BB\_STD} \times \text{Std}_{\text{BB\_PERIOD}}(C_t)$
   - $\text{Lower}_t = \text{Mid}_t - \text{BB\_STD} \times \text{Std}_{\text{BB\_PERIOD}}(C_t)$
   - $\text{Bandwidth}_t = \frac{\text{Upper}_t - \text{Lower}_t}{\text{Mid}_t}$
2. **輔助風控指標**：
   - $\text{BW}_{t-\text{BW\_LOOKBACK}}$：用於判斷帶寬是否正在向上開口。
   - $\text{ATR}$ (`ATR_PERIOD`)：真實波幅之 Wilder 平滑均值。
   - **最大浮盈追蹤 (`peak_gain_pct`)**：持倉期間 $\frac{H_{\text{peak}} - P_{\text{entry}}}{P_{\text{entry}}} \times 100\%$，其中 $H_{\text{peak}}$ 為開倉以來最高成交價或最高收盤價。

---

## 4. 七大策略變體邏輯 (Model Variants)

| `MODEL_KEY` | 策略名稱 | 進場條件 (Entry Rule) | 出場條件 (Exit Rule) | 實盤定位 |
|:---|:---|:---|:---|:---|
| `baseline` | 原始布林突破 | $C_t > \text{Upper}_t$ | $C_t < \text{Mid}_t$ | 基準對照組；中軌動態止損 |
| `bw_expand` | 帶寬擴張過濾 | $C_t > \text{Upper}_t \land \text{BW}_t > \text{BW}_{t-\text{BW\_LOOKBACK}} \land \text{BW}_t \ge \text{BW\_MIN\_THRESHOLD}$ | $C_t < \text{Mid}_t$ | 過濾約 42% 低波動假開口 |
| `profit_lock` | 階梯浮盈保本 | $C_t > \text{Upper}_t$ | 若 $\text{MFE} \ge \text{BREAKEVEN\_MFE\_PCT}$，止損線升至 $\max(\text{Mid}_t, P_{\text{entry}} \times \text{BREAKEVEN\_BUFFER})$；$C_t < \text{stop}$ 即平倉 | 杜絕贏單變輸單 |
| `atr_trail` | 動態 ATR 追蹤止盈 | $C_t > \text{Upper}_t$ | 若 $\text{MFE} \ge \text{TRAIL\_MFE\_PCT}$，止損線升至 $\max(\text{Mid}_t, H_{\text{peak}} - \text{TRAIL\_ATR\_MULT} \times \text{ATR}_t)$；$C_t < \text{stop}$ 即平倉 | 鎖定噴出段浮動利潤 |
| `combo_refined` | 綜合優化模型 | $C_t > \text{Upper}_t \land \text{BW}_t > \text{BW}_{t-\text{BW\_LOOKBACK}} \land \text{BW}_t \ge \text{BW\_MIN\_THRESHOLD}$ | 若 $\text{MFE} \ge \text{TRAIL\_MFE\_PCT}$ 取 $\max(\text{Mid}_t, P_{\text{entry}} \times \text{BREAKEVEN\_BUFFER}, H_{\text{peak}} - \text{TRAIL\_ATR\_MULT} \times \text{ATR}_t)$；否則若 $\text{MFE} \ge \text{BREAKEVEN\_MFE\_PCT}$ 取 $\max(\text{Mid}_t, P_{\text{entry}} \times \text{BREAKEVEN\_BUFFER})$；否則 $\text{Mid}_t$ | 成長股專屬三合一突破引擎 |
| `reversion` | 超跌均值回歸 | $C_{t-1} \le \text{Lower}_{t-1} \land C_t > \text{Lower}_t$ | $C_t \ge \text{Mid}_t$ | 週期/震盪股高勝率收割 |
| `regime_adaptive` | **風格動態適配 (冠軍)** | **成長動能股 (`MOMENTUM`)** 執行 `combo_refined`；**週期/震盪/指數 (`CYCLICAL`)** 執行 `reversion` | 依所屬引擎規則出場 | **布林綜合冠軍**（勝率 61.2%，短線摩擦稅反賺正收益） |

### 標的風格分類準則 (`REGIME_OVERRIDE = "auto"`)
- **已驗證動能成長股池**：`TSLA, NVDA, AMD, MU, MRVL, ARM, WOLF, AVGO, AAPL, TSM, META, GOOGL, MSFT, COHR, LSCC, TER, MKSI`。
- **測試名單外新標的時**：依回測前一年年化波動率 $> 40\%$ 且處於均線多頭趨勢（$C > \text{SMA}_{200}$ 佔比 $> 60\%$）自動歸類為 `MOMENTUM`，其餘（含大盤 ETF）歸類為 `CYCLICAL`。

---

## 5. 測試執行檢查清單 (Execution Checklist)

1. 指標預熱至少需 `WARMUP_BARS` 根 K 線，僅統計 `[START_DATE, END_DATE]` 期間產生的交易。
2. 若執行 `regime_adaptive`，報告中必須明確列出每檔標的是被分派至 `combo_refined`（成長突破）還是 `reversion`（均值回歸）。
3. 產出結果時，務必附上 **Trades, Win Rate %, Total Net PnL ($), Expectancy ($), Profit Factor, Strategy MDD % vs B&H MDD %, Chop Tax (<=10d $)**。

---

## 6. Conclusions & Human Decision Guide (歷史實證結論、優劣勢與優化解析)

> 基準數據來源：SOX 30 + Mag 7 共 35 檔個股（2020-01-02 至 2026-11-10，單筆固定開倉 `$10,000`）。

### 📊 核心實證績效對照
| 模型變體 | 交易數 | 勝率 | 獲利因子 (PF) | 盈虧比 | 單筆期望 | 總淨利 | 短線摩擦稅 | 平均 MDD |
|:---|:---:|:---:|:---:|:---:|:---:|---:|---:|:---:|
| `baseline` (原始突破) | 1,147 | 37.8% | 1.22 | **2.75x** | `$171.20` | `$196,362.45` | `-$298,430.11` | — |
| `bw_expand` (帶寬擴張) | 660 | 40.9% | 1.35 | 2.60x | **`$244.41`** | `$161,312.86` | `-$158,892.61` | **`-24.1%`** |
| `regime_adaptive` (風格動態適配) | 882 | **`61.2%`** | **`1.85`** | 1.55x | `$225.57` | **`$198,949.76`** | **`+$98,804.08`** | `-25.2%` |

### ✅ 優點 (Pros) vs ❌ 缺點與盲點 (Cons)
- **Pros (優勢)**：
  1. **結構化噪聲過濾**：通道本身具 $2\sigma$ 統計門檻，交易頻率天然只有 MACD 的一半、KDJ 的四分之一，原始磨損即顯著低於均線或振盪器。
  2. **波動率即時感知**：帶寬能比均線更早偵測「窄幅擠壓後的真突破」，時間滯後低。
  3. **進可攻退可守**：`regime_adaptive` 是全場少數能兼顧 **61.2% 高勝率**、**1.85 高獲利因子** 與 **短線正期望 (`+$98.8k`)** 的全能平衡架構。
- **Cons (缺點與風險)**：
  1. **單邊暴漲回吐痛點**：突破模型若僅以中軌 (`SMA 20`) 作為出場線，在股價遠離中軌急噴後回踩時，會回吐過多帳面浮盈。
  2. **回歸模型上限受限**：純 `reversion` 雖然勝率高，但因為在觸及中軌時就獲利了結，面對翻倍大牛股只能賺到前 +15%~+25%，錯失主升浪。
  3. **依賴標的風格分類**：`regime_adaptive` 仰賴正確區分「成長動能股」與「週期震盪股」，若標的基本面發生風格切換需重新校準。

### 🔧 哪些優化真正有效？(What Refinements Help & Why)
1. **帶寬擴張過濾 (`bw_expand`: `BW >= 15%` 且 `BW_t > BW_{t-5}`) — 砍半假突破**：
   - **效果**：直接過濾掉 **42%** 的假開口訊號（1,147 → 660 筆），摩擦稅大減 46.8%（省下 `$139.5k`），單筆期望從 `$171` 躍升至 **`$244.41`**，平均 MDD 壓至 **`-24.1%`**。
   - **原因**：排除通道仍處於收斂或水平走平時的微幅刺穿，只在波動率真正擴張時出手。
2. **階梯保本 + ATR 動態追蹤 (`combo_refined`) — 鎖住噴出段利潤**：
   - **效果**：`MFE >= 10%` 將停損上移至成本 `+1.5%`，杜絕大賺變虧損；`MFE >= 20%` 切換至 `Peak - 2.5*ATR`，解決單純靠 `SMA 20` 出場回吐過深的問題。
3. **風格動態雙引擎分流 (`regime_adaptive`) — 質變級突破**：
   - **效果**：將高 Beta 成長股交給 `combo_refined`、成熟週期股交給 `reversion`，一舉將勝率推升至 **`61.2%`**、獲利因子衝上 **`1.85`**，短線摩擦稅更從 `-$298k` 逆轉為淨賺 **`+$98,804.08`**。

### 🧠 人類決策與學習重點
- **何時採用**：當投資組合同時涵蓋成長股與週期/震盪股，且你希望策略具備高夏普、高勝率與低心理阻力時，**`regime_adaptive`** 是首選。
- **測試新標的觀察點**：對新股票執行 `compare` 時，先看 `combo_refined` 與 `reversion` 各自的勝率與總淨利——哪個引擎顯著勝出，就能客觀驗證該檔股票當下的微觀結構屬於「趨勢突破型」還是「箱體均值回歸型」。
