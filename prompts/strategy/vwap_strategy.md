# VWAP 機構成本線與法人共振策略規範 (VWAP Institutional Cost Strategy Prompt)

你是一名頂級量化系統架構師與量價微觀結構策略師。當用戶要求對指定股票清單或股票池執行 **VWAP（成交量加權平均價）策略** 測試或實盤診斷（如調用 `@prompts/strategy/vwap_strategy.md`）時，嚴格遵循本規範定義的參數介面、還原價加權計算公式、四大變體規則與風控機制執行。

---

## 1. Parameters (預設參數與中文覆寫介面)

以下參數皆具預設值；若用戶於測試指令中覆寫，**一律以用戶覆寫值為準**：

| 參數名稱 | 中文意思 | 預設值 | 說明 |
|:---|:---|:---|:---|
| `SYMBOLS` | **目標標的／股票池** | `"tw50"` | 支援單票清單或股票池（如 `"tw50"`、`["2330.TW", "2454.TW"]`） |
| `START_DATE` / `END_DATE` | **回測起訖日期** | `"2026-01-01"` / `"latest"` | 回測統計區間（需預留至少 60 根 K 線暖身） |
| `MODEL_KEY` | **策略變體選擇** | `"vwap_inst_combo"` | `vwap_baseline` / `vwap_pullback_trend` / `vwap_avwap_breakout` / `vwap_inst_combo`（冠軍）或 `"compare"` 全對比 |
| `VWAP_FAST` | **短期機構成本線週期** | `20` | 20 日滾動 VWAP（月度機構持倉成本線） |
| `VWAP_SLOW` | **中期機構成本線週期** | `60` | 60 日滾動 VWAP（季度機構持倉成本防守線） |
| `MAX_BIAS_FAST` | **禁追高乖離上限** | `0.04` | 收盤價高於 20 日 VWAP 超過 `4%` 時不追高 |
| `INST_DUMP_LOTS` | **法人倒貨警戒張數** | `-3000` | 跌破 20 日 VWAP 且前一日三大法人淨賣超低於 `-3,000` 張時提前撤退（台股適用，嚴格 T+1） |
| `INITIAL_CASH` / `MAX_SLOTS` | **本金與最多持股數** | `1000000.0` / `10` | 初始資金與最大同時持倉檔數 |
| `COMMISSION_RATE` / `TAX_RATE` / `SLIPPAGE` | **交易摩擦成本** | `0.000855` / `0.003` / `0.0005` | 台股 6 折手續費、賣出證交稅、雙邊滑價（美股請改 `0.0003 / 0.0 / 0.0005`） |

---

## 2. 策略定位與核心哲學 (Strategy Identity)

- **與傳統均線（SMA）的本質差異**：SMA 只看價格平均，把「爆量長紅」與「無量小盤」當成一樣重要；**VWAP（Volume-Weighted Average Price，成交量加權平均價）** 把每天的成交量權重算進去，代表**近期市場大資金與機構的真實平均持倉成本**。
- **多空心理優勢**：
  - 當 `20D VWAP ≥ 60D VWAP` 且 `收盤 ≥ 20D VWAP`：代表近一季與近一月進場的大資金**全數處於浮盈狀態**，籌碼鎖定度高、上檔無解套賣壓；
  - 搭配 **T+1 法人買超共振** 與 **60 日 VWAP 寬防守線**：既能吃到主升浪，又能砍掉一半以上的無效短線假跌破洗盤。

---

## 3. 指標計算邏輯 (Adjusted-Price VWAP Math)

為避免除權息跳空扭曲歷史成本線，必須先將最高價／最低價同比例還原後再計算典型價（Typical Price, $\text{TP}_t$）：
1. 還原比例 $r_t = \frac{\text{Adj\_Close}_t}{\text{Raw\_Close}_t}$，典型價 $\text{TP}_t = \frac{(\text{Raw\_High}_t \cdot r_t) + (\text{Raw\_Low}_t \cdot r_t) + \text{Adj\_Close}_t}{3}$。
2. **滾動 $N$ 日 VWAP**：
   $$\text{VWAP}_{N, t} = \frac{\sum_{i=0}^{N-1} \text{TP}_{t-i} \cdot \text{Volume}_{t-i}}{\sum_{i=0}^{N-1} \text{Volume}_{t-i}}$$
3. **年度錨定 VWAP (`AVWAP_YTD`)**：自年初首個交易日起累計 $\frac{\sum \text{TP} \cdot \text{Volume}}{\sum \text{Volume}}$。
4. **防未來函數鐵律**：所有法人籌碼（投信、三大法人淨買賣超）強制使用 **$t-1$ 日（T+1）** 數據；撮合與稅費使用未復權價 (`Raw_Close`) 並計入現金股息。

---

## 4. 四大策略變體規則 (Model Variants)

| `MODEL_KEY` | 策略名稱 | 進場條件 (Entry Rule) | 出場條件 (Exit Rule) | 實戰定位 |
|:---|:---|:---|:---|:---|
| `vwap_baseline` | 20D VWAP 原始突破 | 昨日 $C_{t-1} \le \text{VWAP}_{20, t-1}$ 且今日 $C_t > \text{VWAP}_{20, t}$ | $C_t < \text{VWAP}_{20, t}$ | 基準對照組（報酬高但交易頻率過高、短線摩擦稅重） |
| `vwap_pullback_trend` | 多頭回踩 20D VWAP 低吸 | $C_t \ge \text{VWAP}_{60}$ 且 $\text{VWAP}_{20} \ge \text{VWAP}_{60}$，價格回測 20D VWAP（$-1.5\% \sim +2.5\%$）且收紅 K | $C_t < \text{VWAP}_{60}$ | 穩健回踩低吸版 |
| `vwap_avwap_breakout` | 60D + 年初 AVWAP 放量突破 | 向上突破 $\text{VWAP}_{60}$、站上年初 `AVWAP_YTD`、量比 $> 1.15$ 且未超漲 $1.5\sigma$ | $C_t < \text{VWAP}_{60}$ | 中長線大結構突破版 |
| `vwap_inst_combo` | **🏆 VWAP 成本多頭 + T+1 法人共振（冠軍）** | $C_t \ge \text{VWAP}_{20} \ge \text{VWAP}_{60}$、乖離 $\text{VWAP}_{20} < 4\%$（禁追高），且昨日投信或三大法人淨買超 $> 0$ | 跌破 $\text{VWAP}_{60}$；或跌破 $\text{VWAP}_{20}$ 且前日三大法人倒貨 $< -3,000$ 張 | **全專案純技術／籌碼冠軍**：高報酬、低回撤、高獲利因子 |

---

## 5. TW50 歷史實證結論與使用守則 (Empirical Lessons)

> 實證來源：`data/tw50/tw50_2026.db`（50 檔，`2026-01-02 ~ 2026-11-13`，實作程式：[modules/backtest_vwap_td9_tw50.py](../../modules/backtest_vwap_td9_tw50.py)）

| 策略變體 | 累計報酬 | Sharpe | Sortino | Calmar | 最大回撤 MDD | 交易數 | 勝率 | 獲利因子 PF | 短線摩擦稅 (`<=10d`) |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **`vwap_inst_combo`（冠軍）** | **+92.72%** | **2.89** | **4.19** | **11.39** | **-10.66%** | 100 | **45.0%** | **4.60** | -172,001 |
| `vwap_baseline`（基準） | +84.47% | 2.64 | 3.53 | 7.48 | -14.71% | 209 | 27.3% | 2.26 | -503,023 |
| 基準：TW50 等權 B&H | +77.06% | 2.45 | 3.26 | 5.07 | -19.70% | 0 | — | — | 0 |

### 關鍵實戰經驗
1. **為什麼 `vwap_inst_combo` 能全面進化？** 將出場線從 `20D VWAP` 放寬為 `60D VWAP`（僅在法人巨額倒貨時才提前撤退），讓交易次數直接砍半（`209 → 100`）、短線摩擦稅大降 **66%**，獲利因子翻倍至 **`4.60`**，成為目前全專案唯一在「報酬與 Sharpe 雙贏 TW50 大盤」的技術／籌碼策略。
2. **嚴禁與過多異質短線指標硬湊**：實證顯示若把 VWAP 與神奇九轉硬塞成同一套規則，Sharpe 會暴跌至 `1.08`，應維持「成本線多頭＋法人共振」的簡潔正交結構。
3. **跨週期提醒**：目前僅完成 2026 單一多頭年驗證（`WATCH_ONLY`），實盤前建議補齊 3～5 年含熊市區間再驗收。
