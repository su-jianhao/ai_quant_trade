# KDJ (9,3,3) 隨機指標與超跌低吸策略規範 (KDJ Oscillator Strategy Prompt)

你是一名頂級量化系統架構師與微觀結構反轉策略師。當用戶要求對指定股票清單與日期區間執行 **KDJ 隨機指標策略** 測試或回測（如調用 `@prompts/strategy/kdj_strategy.md`）時，嚴格遵循本規範定義的參數介面、數學邏輯與七大變體規則執行。

---

## 1. Parameters (預設參數與覆寫介面)

以下為預設參數配置；若用戶於測試指令中指定不同數值，**一律以用戶覆寫值為準**：

| 參數名稱 | 預設值 | 說明 |
|:---|:---|:---|
| `SYMBOLS` | *(必填，無預設)* | 目標測試標的清單（如 `["TSLA", "INTC"]`） |
| `START_DATE` | *(必填，無預設)* | 回測統計起始日（如 `"2022-01-01"`） |
| `END_DATE` | *(必填，無預設)* | 回測統計結束日（如 `"2025-12-31"`） |
| `MODEL_KEY` | `"compare"` | 執行指定變體（`baseline`, `no_chase`, `trend_filter`, `profit_lock`, `oversold_low`, `combo_refined`, `oversold_trend`）或 `"compare"` 全變體對比 |
| `FIXED_CASH` | `10000.0` | 單筆固定開倉本金 |
| `SLIPPAGE` | `0.0005` | 雙邊滑點（5 bps） |
| `COMMISSION_RATE` | `0.0003` | 單邊手續費率（台股請覆寫為手續費 `0.000855` + 賣出證交稅 `0.003`） |
| `KDJ_N` | `9` | RSV 計算回溯天數 |
| `KDJ_M1` | `3` | K 值平滑參數（權重 $1/M_1$） |
| `KDJ_M2` | `3` | D 值平滑參數（權重 $1/M_2$） |
| `SMA_TREND_PERIOD` | `50` | 順勢濾網均線週期 |
| `ATR_PERIOD` | `14` | ATR 真實波幅週期 |
| `NO_CHASE_K_MAX` | `65.0` | 禁追高進場 K 值上限 |
| `NO_CHASE_J_MAX` | `85.0` | 禁追高進場 J 值上限 |
| `OVERSOLD_K_MAX` | `30.0` | `oversold_low` 進場超賣 K 值上限（`oversold_trend` 預設 `35.0`） |
| `OVERSOLD_J_MAX` | `0.0` | `oversold_low` 進場超賣 J 值上限（`oversold_trend` 預設 `10.0`） |
| `OVERBOUGHT_K_EXIT` | `70.0` | 超跌反轉系列出場要求之 K 值門檻 |
| `OVERBOUGHT_J_EXIT` | `100.0` | 超跌反轉系列出場要求之 J 值門檻（`oversold_trend` 預設 `90.0`） |
| `BREAKEVEN_MFE_PCT` | `5.0` | `profit_lock` / `combo_refined` 保本鎖定觸發浮盈 (%) |
| `BREAKEVEN_BUFFER` | `1.010` | 保本止損價倍數（進場價 + 1.0%） |
| `TRAIL_MFE_PCT` | `12.0` | `profit_lock` 動態 ATR 止盈觸發浮盈 (%) |
| `TRAIL_ATR_MULT` | `2.0` | `profit_lock` 動態 ATR 回落倍數 |
| `WARMUP_BARS` | `50` | `START_DATE` 之前預留的最小暖身 K 線數 |

---

## 2. 策略定位與核心哲學 (Strategy Identity)

- **指標本質**：嚴格有界振盪器 ($0 \sim 100$ 分位)，時間滯後極低（$T+1$ 甚至當日極速拐點）。
- **核心優勢**：對恐慌性急跌的超賣反彈極為敏銳，適合在極端恐慌坑底進行高勝率伏擊。
- **核心痛點**：原始 KDJ 交易頻率極高，在震盪市反覆雙巴會蒸發巨額手續費與滑價（Chop Tax）；在強趨勢中則容易因「高位超買鈍化」而誘多追高或過早被洗出場。
- **解決方案**：嚴格執行**禁追高過濾**、**極端超跌低吸**以及 **超買止盈門檻**。

---

## 3. 指標計算邏輯 (Indicator Logic)

對每個交易日 $t$ 的收盤價 $C_t$、最高價 $H_t$、最低價 $L_t$ 計算標準 **KDJ (`KDJ_N`, `KDJ_M1`, `KDJ_M2`)**：
1. **RSV (未成熟隨機值)**：
   - $L_N = \min(L_{t-N+1}, \dots, L_t)$，$H_N = \max(H_{t-N+1}, \dots, H_t)$
   - $\text{RSV}_t = \frac{C_t - L_N}{H_N - L_N} \times 100$（若 $H_N = L_N$ 則設為 50）
2. **K, D, J 平滑遞推**（初始值 $K_0 = 50, D_0 = 50$）：
   - $K_t = (1 - \frac{1}{M_1}) K_{t-1} + \frac{1}{M_1} \text{RSV}_t$
   - $D_t = (1 - \frac{1}{M_2}) D_{t-1} + \frac{1}{M_2} K_t$
   - $J_t = 3 K_t - 2 D_t$
3. **交叉訊號**：
   - 金叉 (`is_golden`)：$K_{t-1} \le D_{t-1}$ 且 $K_t > D_t$
   - 死叉 (`is_death`)：$K_{t-1} \ge D_{t-1}$ 且 $K_t < D_t$
4. **輔助指標**：$\text{SMA}_{\text{SMA\_TREND\_PERIOD}}(C_t)$ 與 $\text{ATR}_{\text{ATR\_PERIOD}}$。

---

## 4. 七大策略變體邏輯 (Model Variants)

僅在**空倉狀態**且觸發 `is_golden` 時，依所選 `MODEL_KEY` 檢查濾網進場：

| `MODEL_KEY` | 策略名稱 | 進場條件 (Entry Rule on `is_golden`) | 出場條件 (Exit Rule) | 實盤定位 |
|:---|:---|:---|:---|:---|
| `baseline` | 原始 KDJ 金叉/死叉 | 無額外濾網 | `is_death` | 基準對照組；極高頻磨損重災區 |
| `no_chase` | 禁追高過濾 | $K_t < \text{NO\_CHASE\_K\_MAX} \land J_t < \text{NO\_CHASE\_J\_MAX}$ | `is_death` | 剔除超買鈍化誘多金叉 |
| `trend_filter` | 均線順勢過濾 | $C_t > \text{SMA}_{\text{trend},t}$ | `is_death` | 避免在熊市主跌段左側接飛刀 |
| `profit_lock` | 階梯浮盈保本 | 無額外濾網 | $(\text{MFE} \ge \text{BREAKEVEN\_MFE\_PCT} \land C_t < P_{\text{entry}} \times \text{BREAKEVEN\_BUFFER})$ 或 $(\text{MFE} \ge \text{TRAIL\_MFE\_PCT} \land C_t < H_{\text{peak}} - \text{TRAIL\_ATR\_MULT} \times \text{ATR}_t)$ 或 `is_death` | 鎖定短線微利防止回吐 |
| `oversold_low` | **超跌低吸反轉 (低吸王)** | $K_t < \text{OVERSOLD\_K\_MAX} \lor J_t < \text{OVERSOLD\_J\_MAX}$ | `is_death` 且 $(K_t > \text{OVERBOUGHT\_K\_EXIT} \lor J_t > \text{OVERBOUGHT\_J\_EXIT})$ | **極致恐慌低吸王**（勝率破 70%，單筆期望極高） |
| `combo_refined` | 綜合優化模型 | $C_t > \text{SMA}_{\text{trend},t} \land K_t < \text{NO\_CHASE\_K\_MAX}$ | $(\text{MFE} \ge \text{BREAKEVEN\_MFE\_PCT} \land C_t < P_{\text{entry}} \times \text{BREAKEVEN\_BUFFER})$ 或 `is_death` | 順勢 + 禁追高 + 保本三合一 |
| `oversold_trend` | 順勢超跌反轉 | $C_t > \text{SMA}_{\text{trend},t} \land (K_t < 35.0 \lor J_t < 10.0)$ | `is_death` 且 $(K_t > 70.0 \lor J_t > 90.0)$ | 兼顧大趨勢保護與超跌高勝率 |

---

## 5. 測試執行檢查清單 (Execution Checklist)

1. 指標預熱至少需 `WARMUP_BARS` 根 K 線，僅統計 `[START_DATE, END_DATE]` 期間產生的交易。
2. 注意 `oversold_low` 與 `oversold_trend` 的出場條件：**必須在超買區發生死叉才平倉**，避免反彈剛啟動時在中低位被假死叉洗出場。
3. 產出結果時，務必附上 **Trades, Win Rate %, Total Net PnL ($), Expectancy ($), Profit Factor, Strategy MDD % vs B&H MDD %, Chop Tax (<=10d $)**。

---

## 6. Conclusions & Human Decision Guide (歷史實證結論、優劣勢與優化解析)

> 基準數據來源：SOX 30 + Mag 7 共 35 檔個股（2020-01-02 至 2026-11-10，單筆固定開倉 `$10,000`）。

### 📊 核心實證績效對照
| 模型變體 | 交易數 | 勝率 | 獲利因子 (PF) | 盈虧比 | 單筆期望 | 總淨利 | 短線摩擦稅 |
|:---|:---:|:---:|:---:|:---:|:---:|---:|---:|
| `baseline` (原始 9,3,3) | 4,986 | 38.3% | 1.08 | 1.95x | `$32.44` | `$161,741.17` | **`-$864,327.92`** |
| `no_chase` (禁追高 `K<65 & J<85`) | 3,638 | 39.4% | 1.12 | 2.05x | `$42.83` | `$155,804.90` | `-$699,291.91` |
| `oversold_low` (超跌低吸反轉) | 583 | **`70.5%`** | **`2.48`** | 1.48x | **`$476.56`** | **`$277,832.43`** | **`+$322.45`** |

### ✅ 優點 (Pros) vs ❌ 缺點與盲點 (Cons)
- **Pros (優勢)**：
  1. **極致微觀拐點敏銳度**：時間滯後極低（$T+1$ 甚至當日拐點），在恐慌暴跌後的 V 型反彈中，進場點位遠早於 MACD 與布林通道。
  2. **超跌低吸勝率與效率驚人**：`oversold_low` 創下 **70.5% 勝率**、**2.48 獲利因子** 與 **`$476.56` 單筆期望**（全場第二），且資金暴露度僅 **4% ~ 9%**，其餘時間皆可保有現金或作無風險理財。
- **Cons (缺點與風險)**：
  1. **原始版是極度危險的高頻磨損機**：`baseline` 交易高達 4,986 筆，在震盪期頻繁金叉/死叉產生高達 **`-$864,327.92`** 的摩擦稅，單筆平均淨利僅 `$32.44`，一旦滑點或手續費略高即變負期望。
  2. **高位鈍化與過早洗出**：強趨勢中 KDJ 容易在高位反覆死叉又金叉，若未限制出場條件，極易在主升浪半途被假死叉洗下車。
  3. **熊市接飛刀風險**：純超跌 (`K<30` 或 `J<0`) 若遇基本面崩壞的連續下跌股，可能出現低位鈍化連續虧損（因此衍生出 `oversold_trend` 加上 `SMA 50` 保護）。

### 🔧 哪些優化真正有效？(What Refinements Help & Why)
1. **禁追高過濾 (`no_chase`: `K < 65 & J < 85`) — 基礎止血**：
   - **效果**：剔除 1,348 筆高位誘多金叉，省下 **16.5 萬美元**摩擦稅，同時幾乎不影響總淨利（`$161.7k → $155.8k`）。
   - **原因**：高分位金叉往往是動能末端，追高賠率極差。
2. **極端超跌低吸 + 非對稱超買出場 (`oversold_low`) — 徹底脫胎換骨**：
   - **效果**：交易數從 4,986 筆精簡至 **583 筆**，直接省下 **`+$864,650`** 摩擦稅；單筆期望暴增 **14.7 倍**（`$32.44 → $476.56`），總淨利反升至 **`$277,832.43`**。
   - **原因**：只打「極度恐慌坑」（`K < 30` 或 `J < 0`），且**嚴格規定必須等 `K > 70` 或 `J > 100` 才允許死叉平倉**，確保吃滿整段超跌修復波幅，不被中低位雜訊洗出。

### 🧠 人類決策與學習重點
- **核心鐵律**：**永遠不要把 KDJ 當作常態趨勢交叉系統使用**；KDJ 的正確打開方式只有「恐慌抄底 (`oversold_low`)」或「作為大系統的微觀扳機（如 `trinity_strategy.md`）」。
- **測試新標的觀察點**：若測試台股或高交易稅費市場，務必檢查 `baseline` 是否已因稅費轉為負期望，並重點評估 `oversold_low` 與 `oversold_trend` 在該標的歷史急跌段（如財報殺盤、系統性回調）的勝率與接刀風險。
