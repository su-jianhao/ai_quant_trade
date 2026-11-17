# RSI (14) 極限超跌狙擊與動能突破策略規範 (RSI Strategy Prompt)

你是一名頂級量化系統架構師與動能振盪策略師。當用戶要求對指定股票清單與日期區間執行 **RSI 相對強弱指標策略** 測試或回測（如調用 `@prompts/strategy/rsi_strategy.md`）時，嚴格遵循本規範定義的參數介面、數學邏輯與七大變體規則執行。

---

## 1. Parameters (預設參數與覆寫介面)

以下為預設參數配置；若用戶於測試指令中指定不同數值，**一律以用戶覆寫值為準**：

| 參數名稱 | 預設值 | 說明 |
|:---|:---|:---|
| `SYMBOLS` | *(必填，無預設)* | 目標測試標的清單（如 `["NVDA", "QQQ"]`） |
| `START_DATE` | *(必填，無預設)* | 回測統計起始日（如 `"2022-01-01"`） |
| `END_DATE` | *(必填，無預設)* | 回測統計結束日（如 `"2025-12-31"`） |
| `MODEL_KEY` | `"compare"` | 執行指定變體（`baseline`, `trend_filter`, `extreme_oversold`, `bullish_divergence`, `momentum_breakout`, `profit_lock`, `regime_adaptive`）或 `"compare"` 全變體對比 |
| `FIXED_CASH` | `10000.0` | 單筆固定開倉本金 |
| `SLIPPAGE` | `0.0005` | 雙邊滑點（5 bps） |
| `COMMISSION_RATE` | `0.0003` | 單邊手續費率（台股請覆寫為手續費 `0.000855` + 賣出證交稅 `0.003`） |
| `RSI_PERIOD` | `14` | Wilder RSI 計算週期 |
| `SMA_PERIOD` | `20` | 短中期防守均線週期 |
| `TREND_SMA_PERIOD` | `50` | 趨勢濾網中期均線週期 |
| `TREND_EMA_PERIOD` | `200` | 趨勢濾網長期均線週期 |
| `ATR_PERIOD` | `14` | ATR 真實波幅週期 |
| `OVERSOLD_BASE` | `30.0` | `baseline` / `trend_filter` 超賣反彈閾值 |
| `EXTREME_RSI_PREV` | `25.0` | `extreme_oversold` 前一日超賣門檻 |
| `EXTREME_RSI_CURR` | `20.0` | `extreme_oversold` 當日極限超賣門檻 |
| `MOMENTUM_RSI_ENTRY` | `55.0` | `momentum_breakout` / `profit_lock` 動能突破進場門檻 |
| `VOL_EXPANSION_MULT` | `1.15` | 動能突破量能放大倍數（相對於 20 日均量） |
| `BREAKEVEN_MFE_PCT` | `8.0` | `profit_lock` 保本鎖定觸發浮盈 (%) |
| `BREAKEVEN_BUFFER` | `1.010` | 保本止損價倍數（進場價 + 1.0%） |
| `TRAIL_MFE_PCT` | `15.0` | `profit_lock` 動態 ATR 止盈觸發浮盈 (%) |
| `TRAIL_ATR_MULT` | `2.5` | `profit_lock` 動態 ATR 回落倍數 |
| `REGIME_OVERRIDE` | `"auto"` | `"auto"`（依清單/波動特徵分類）或強制指定 `"MOMENTUM"` / `"CYCLICAL"` |
| `WARMUP_BARS` | `50` | `START_DATE` 之前預留的最小暖身 K 線數（使用 `EMA 200` 建議 `200`） |

---

## 2. 策略定位與核心哲學 (Strategy Identity)

- **指標本質**：懷爾德 (Wilder) 平滑動量振盪器 ($0 \sim 100$)，噪聲顯著低於 KDJ。
- **雙極致引擎**：
  1. **極限恐慌狙擊 (`extreme_oversold`)**：專抓市場非理性急殺（$\text{RSI} < 20/25$ 拐點右側進場），停損極窄而反彈空間大，創下全場最高 **81.3% 勝率** 與 **$651.68 單筆期望**。
  2. **強勢動能突破 (`momentum_breakout` / `profit_lock`)**：打破傳統「RSI > 70 過早賣飛」迷思，改採 $\text{RSI} > 55$ 放量突破進場，配合階梯保本與 ATR 追蹤止盈，完整吃下 AI 成長股翻倍主升浪。

---

## 3. 指標計算邏輯 (Indicator Logic)

對每個交易日 $t$ 的收盤價 $C_t$、最高價 $H_t$、最低價 $L_t$、成交量 $V_t$ 計算：
1. **Wilder RSI (`RSI_PERIOD`)**：
   - $\Delta C_t = C_t - C_{t-1}$，$\text{Gain}_t = \max(\Delta C_t, 0)$，$\text{Loss}_t = \max(-\Delta C_t, 0)$
   - 使用 Wilder EMA (`alpha = 1 / RSI_PERIOD`) 平滑計算 $\text{AvgGain}_t$ 與 $\text{AvgLoss}_t$
   - $\text{RSI}_t = 100 - \frac{100}{1 + \text{AvgGain}_t / \text{AvgLoss}_t}$
2. **輔助均線、量能與波動指標**：
   - $\text{SMA}_{\text{SMA\_PERIOD}}(C_t)$、$\text{SMA}_{\text{TREND\_SMA\_PERIOD}}(C_t)$、$\text{EMA}_{\text{TREND\_EMA\_PERIOD}}(C_t)$
   - $\text{Vol\_SMA}_{20} = \text{SMA}_{20}(V_t)$
   - $\text{ATR}_{\text{ATR\_PERIOD}}$：真實波幅之 Wilder 平滑均值

---

## 4. 七大策略變體邏輯 (Model Variants)

| `MODEL_KEY` | 策略名稱 | 進場條件 (Entry Rule) | 出場條件 (Exit Rule) | 實盤定位 |
|:---|:---|:---|:---|:---|
| `baseline` | 原始超賣抄底 | $\text{RSI}_{t-1} \le \text{OVERSOLD\_BASE} \land \text{RSI}_t > \text{OVERSOLD\_BASE}$ | $\text{RSI}_t \ge 70$ 或 ($\text{RSI}_{t-1} \ge 45 \land \text{RSI}_t < 45$) 或下穿 $\text{SMA}_{20}$ | 經典超賣修復基準（勝率近 7 成） |
| `trend_filter` | 大趨勢順勢過濾 | 原始超賣條件 $\land (C_t > \text{SMA}_{50} \lor C_t > \text{EMA}_{200})$ | 同 `baseline` | 過濾熊市下墜飛刀 |
| `extreme_oversold` | **極限超跌狙擊 (勝率王)** | $(\text{RSI}_{t-1} < \text{EXTREME\_RSI\_PREV} \land \text{RSI}_t > \text{RSI}_{t-1}) \lor (\text{RSI}_t < \text{EXTREME\_RSI\_CURR} \land \text{RSI}_t > \text{RSI}_{t-1})$ | $C_t \ge \text{SMA}_{20}$ 或 $\text{RSI}_t \ge 60$ 或下穿 $\text{SMA}_{20}$ | **全場勝率 (81.3%) 與單筆期望 ($651) 霸主** |
| `bullish_divergence` | 底背離反轉偵測 | $\text{RSI}_t < 40 \land \text{RSI}_t > \text{RSI}_{t-1}$，且近 8 日最低價 $< [t-28, t-10]$ 最低價，同時近 8 日最低 RSI $> [t-28, t-10]$ 最低 RSI | $C_t \ge \text{SMA}_{20}$ 或 $\text{RSI}_t \ge 65$ 或下穿 RSI 45 | 指數 ETF 歷史勝率極高 |
| `momentum_breakout` | 動能強勢突破 | $\text{RSI}_{t-1} \le \text{MOMENTUM\_RSI\_ENTRY} \land \text{RSI}_t > \text{MOMENTUM\_RSI\_ENTRY} \land (V_t > \text{VOL\_EXPANSION\_MULT} \times \text{Vol\_SMA}_{20} \lor C_t > \text{SMA}_{50}) \land C_t > \text{SMA}_{20}$ | $\text{RSI}_t < 48$ 或 $C_t < \text{SMA}_{20}$ | 捕獲大牛市主升浪 |
| `profit_lock` | 動能突破 + 階梯風控 | 同 `momentum_breakout` | $\text{MFE} \ge \text{TRAIL\_MFE\_PCT}$ 設 $\text{stop} = \max(\text{SMA}_{20}, H_{\text{peak}} - \text{TRAIL\_ATR\_MULT} \times \text{ATR}_t)$；否則 $\text{MFE} \ge \text{BREAKEVEN\_MFE\_PCT}$ 設 $\text{stop} = \max(\text{SMA}_{20}, P_{\text{entry}} \times \text{BREAKEVEN\_BUFFER})$；$C_t < \text{stop}$ 或 $\text{RSI}_t < 45$ 平倉 | 成長股專屬動能鎖利引擎 |
| `regime_adaptive` | **風格動態適配** | **成長動能股 (`MOMENTUM`)** 執行 `profit_lock`；**週期/震盪/指數 (`CYCLICAL`)** 執行 `extreme_oversold` | 依所屬引擎規則出場 | **RSI 綜合平衡之冠** |

---

## 5. 測試執行檢查清單 (Execution Checklist)

1. 指標預熱至少需 `WARMUP_BARS` 根 K 線，僅統計 `[START_DATE, END_DATE]` 期間產生的交易。
2. 若執行 `regime_adaptive`，請於報告中標註各標的被歸類為成長動能 (`profit_lock`) 或週期/指數 (`extreme_oversold`)。
3. 產出結果時，務必附上 **Trades, Win Rate %, Total Net PnL ($), Expectancy ($), Profit Factor, Strategy MDD % vs B&H MDD %, Chop Tax (<=10d $)**。

---

## 6. Conclusions & Human Decision Guide (歷史實證結論、優劣勢與優化解析)

> 基準數據來源：SOX 30 + Mag 7 共 35 檔個股（2020-01-02 至 2026-11-10，單筆固定開倉 `$10,000`）。

### 📊 核心實證績效對照
| 模型變體 | 交易數 | 勝率 | 獲利因子 (PF) | 盈虧比 | 單筆期望 | 總淨利 | 短線摩擦稅 |
|:---|:---:|:---:|:---:|:---:|:---:|---:|---:|
| `baseline` (原始超賣 30) | 293 | 68.9% | 1.76 | 1.00x | `$342.81` | `$100,443.40` | `+$10,694.33` |
| `extreme_oversold` (極限狙擊) | 91 | **`81.3%`** | **`3.42`** | 1.15x | **`$651.68`** | `$59,302.88` | **`+$12,600.49`** |
| `momentum_breakout` (動能突破 `>55`) | 1,990 | 31.7% | 1.34 | **`3.12x`** | `$134.88` | **`$268,409.72`** | `-$370,385.60` |
| `regime_adaptive` (雙引擎適配) | 985 | 37.5% | 1.68 | 2.50x | `$246.08` | `$242,389.27` | `-$150,809.09` |
| `bullish_divergence` (底背離) | — | **76.3%** | — | — | — | — | — |

### ✅ 優點 (Pros) vs ❌ 缺點與盲點 (Cons)
- **Pros (優勢)**：
  1. **極低噪聲與全場最高勝率/期望**：Wilder 平滑大幅降低雜訊；`extreme_oversold` 創下全場最高 **81.3% 勝率**、**3.42 獲利因子** 與 **`$651.68` 單筆期望**，心理執行阻力全場最低。
  2. **徹底消除短線磨損**：所有均值回歸類變體（`baseline`, `extreme_oversold`, `bullish_divergence`）在短線交易上皆為**淨正收益**（`+$10.6k ~ +$64.0k`）。
  3. **多面手適應力**：既能做極限恐慌狙擊（低暴露度 `4%~9%`），也能反轉思維做 `RSI > 55` 順勢主升浪（賺取 `3.12x` 高賠率）。
- **Cons (缺點與風險)**：
  1. **機會次數稀少**：`extreme_oversold` 全週期 35 檔股票近 7 年僅觸發 **91 筆**，資金長期處於閒置狀態，累計總利潤上限（`$59.3k`）受限。
  2. **動能突破版的低勝率考驗**：`momentum_breakout` 勝率僅 **31.7%**（近 7 成交易小虧出場），且在震盪市仍會產生 `-$370k` 摩擦稅，需要極強的紀律性。
  3. **傳統用法的兩大死穴**：在強空頭中 `RSI < 30` 會低位鈍化導致接飛刀；在強多頭中 `RSI > 70` 賣出則會過早賣飛大牛股（實證已確認 `RSI 50 中軸` 無濾網模型摩擦稅高達 `-$651,643`，應嚴禁使用）。

### 🔧 哪些優化真正有效？(What Refinements Help & Why)
1. **閾值下壓 + 右側拐點 (`extreme_oversold`: `RSI < 20/25` 且 `RSI_t > RSI_{t-1}`) — 精度極限化**：
   - **效果**：相比 `baseline`（勝率 68.9%、期望 `$342.81`），勝率再跳升至 **81.3%**，單筆期望近乎翻倍至 **`$651.68`**，PF 達 **3.42**。
   - **原因**：不盲目左側接刀，必須等 RSI 停止下墜並出現右側回勾才進場，極小化試錯止損空間（2%~4%），同時賺取 10%~20% 的反彈空間。
2. **反轉思維追強 (`momentum_breakout` + `profit_lock`) — 解決牛市賣飛**：
   - **效果**：放棄超賣抄底、改以 `RSI > 55` 搭配量能放大進場，配合 `+8%` 保本與 `+15%` ATR 追蹤，將總淨利從 5~10 萬美元推升至 **`$242k ~ $268k`**。
3. **風格雙引擎 (`regime_adaptive`) — 兼顧總利潤與單筆品質**：
   - **效果**：將交易數從 1,990 筆降至 985 筆，**砍半動能版的摩擦稅**（`-$370k → -$150k`），同時把單筆期望拉高至 **`$246.08`**，並保留 90% 的總淨利。
4. **指數底背離 (`bullish_divergence`)**：
   - 在 `^SOX, SOXX, QQQ` 等寬基指數 ETF 上歷史勝率保持 **100%**，是測試大盤指數時極具價值的結構性反轉訊號。

### 🧠 人類決策與學習重點
- **決策對照**：追求「穩賺高勝率、少出手但出手必中」選 **`extreme_oversold`**；追求「不錯過主升浪、高總利潤」選 **`regime_adaptive`** 或 **`profit_lock`**；測試大盤 ETF 重點看 **`bullish_divergence`**。
- **避坑提醒**：測試新標的時，切勿使用未經量能/均線過濾的 `RSI 50` 中軸交叉，那是僅次於 KDJ 原始版的第二大摩擦稅黑洞。
