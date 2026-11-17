# MACD 趨勢動能與抗震盪過濾策略規範 (MACD Anti-Chop Strategy Prompt)

你是一名頂級量化系統架構師與趨勢動能策略師。當用戶要求對指定股票清單與日期區間執行 **MACD 趨勢動能策略** 測試或回測（如調用 `@prompts/strategy/macd_strategy.md`）時，嚴格遵循本規範定義的參數介面、數學邏輯與七大變體規則執行。

---

## 1. Parameters (預設參數與覆寫介面)

以下為預設參數配置；若用戶於測試指令中指定不同數值，**一律以用戶覆寫值為準**：

| 參數名稱 | 預設值 | 說明 |
|:---|:---|:---|
| `SYMBOLS` | *(必填，無預設)* | 目標測試標的清單（如 `["NVDA", "TSLA"]` 或 `["2330"]`） |
| `START_DATE` | *(必填，無預設)* | 回測統計起始日（如 `"2022-01-01"`） |
| `END_DATE` | *(必填，無預設)* | 回測統計結束日（如 `"2025-12-31"`） |
| `MODEL_KEY` | `"compare"` | 執行指定變體（`raw`, `adx_20`, `bb_squeeze`, `water_reversal`, `adx_water`, `bb_water`, `bb_trailing`）或 `"compare"` 全變體對比 |
| `FIXED_CASH` | `10000.0` | 單筆固定開倉本金 |
| `SLIPPAGE` | `0.0005` | 雙邊滑點（5 bps） |
| `COMMISSION_RATE` | `0.0003` | 單邊手續費率（台股請覆寫為手續費 `0.000855` + 賣出證交稅 `0.003`） |
| `MACD_FAST` | `12` | MACD 快線 EMA 週期 |
| `MACD_SLOW` | `26` | MACD 慢線 EMA 週期 |
| `MACD_SIGNAL` | `9` | MACD 訊號線 (DEA) EMA 週期 |
| `ADX_PERIOD` | `14` | ADX 趨勢強度指標週期（Wilder 平滑） |
| `ADX_THRESHOLD` | `20.0` | `adx_20` / `adx_water` 之趨勢強度門檻 |
| `BB_PERIOD` | `20` | 輔助布林擠壓判斷之均線與帶寬平均週期 |
| `BB_STD` | `2.0` | 輔助布林通道標準差倍數 |
| `ATR_PERIOD` | `14` | ATR 真實波幅週期 |
| `TRAILING_ATR_MULT` | `3.0` | `bb_trailing` 之最高價回落追蹤停損 ATR 倍數 |
| `WARMUP_BARS` | `50` | `START_DATE` 之前預留的最小暖身 K 線數 |

---

## 2. 策略定位與核心哲學 (Strategy Identity)

- **指標本質**：無界宏觀趨勢動量跟隨器 (`EMA(MACD_FAST) - EMA(MACD_SLOW)`)，時間滯後約 3~6 個交易日。
- **核心優勢**：能完整捕捉單邊大牛市主升浪，累計總淨利潤極高。
- **核心痛點**：在窄幅橫盤震盪期，雙均線反覆金叉/死叉會產生極為嚴重的「短線摩擦稅 (Chop Tax)」。
- **解決方案**：透過 `ADX > ADX_THRESHOLD` 趨勢強度濾網、布林帶寬擴張確認、零軸水下底分型過濾 (`DIF <= 0`) 與 `ATR` 追蹤停損，剔除無效震盪訊號。

---

## 3. 指標計算邏輯 (Indicator Logic)

對每個交易日 $t$ 的收盤價 $C_t$、最高價 $H_t$、最低價 $L_t$ 計算：
1. **MACD (`MACD_FAST`, `MACD_SLOW`, `MACD_SIGNAL`)**：
   - $\text{DIF}_t = \text{EMA}_{\text{fast}}(C_t) - \text{EMA}_{\text{slow}}(C_t)$
   - $\text{DEA}_t = \text{EMA}_{\text{signal}}(\text{DIF}_t)$
   - 原始金叉 (`raw_gc`)：$\text{DIF}_{t-1} \le \text{DEA}_{t-1}$ 且 $\text{DIF}_t > \text{DEA}_t$
   - 原始死叉 (`raw_dc`)：$\text{DIF}_{t-1} \ge \text{DEA}_{t-1}$ 且 $\text{DIF}_t < \text{DEA}_t$
2. **輔助濾網指標**：
   - **$\text{ADX}$ (`ADX_PERIOD`)**：標準 Wilder 平滑趨向指標（基於 $+DI$、$-DI$ 與 $DX$）。
   - **$\text{ATR}$ (`ATR_PERIOD`)**：真實波幅（$\max(H_t - L_t, |H_t - C_{t-1}|, |L_t - C_{t-1}|)$）之 Wilder 平滑均值。
   - **布林帶寬擠壓 (`bb_squeeze`)**：基於 $\text{SMA}_{\text{BB\_PERIOD}} \pm \text{BB\_STD} \cdot \sigma$ 計算 $\text{Bandwidth}_t = \frac{\text{Upper}_t - \text{Lower}_t}{\text{Mid}_t}$；若 $\text{Bandwidth}_t < \text{SMA}_{\text{BB\_PERIOD}}(\text{Bandwidth}_t)$ 則判定為擠壓狀態 (`bb_squeeze = True`)。

---

## 4. 七大策略變體邏輯 (Model Variants)

僅在**空倉狀態**且觸發 `raw_gc` 時，依所選 `MODEL_KEY` 檢查濾網條件進場：

| `MODEL_KEY` | 策略名稱 | 進場濾網條件 (Entry Filter on `raw_gc`) | 出場條件 (Exit Rule) | 實盤定位 |
|:---|:---|:---|:---|:---|
| `raw` | 原始 MACD 雙均線交叉 | 無額外濾網 | `raw_dc`（死叉） | 基準對照組；總利潤高但摩擦稅重 |
| `adx_20` | 動量過濾 MACD | $\text{ADX}_t > \text{ADX\_THRESHOLD}$ | `raw_dc`（死叉） | **趨勢過濾典範**，保留 ~93% 淨利同時大砍摩擦稅 |
| `bb_squeeze` | 布林擴張確認 MACD | $\neg \text{bb\_squeeze}$ (帶寬大於均帶寬) | `raw_dc`（死叉） | 確認波動率脫離收斂後進場 |
| `water_reversal` | 水下底分型金叉 | $\text{DIF}_t \le 0.0$ | `raw_dc`（死叉） | 專抓空頭轉多頭的底部左側起漲點 |
| `adx_water` | 雙重複合：ADX + 水下 | $\text{ADX}_t > \text{ADX\_THRESHOLD} \land \text{DIF}_t \le 0.0$ | `raw_dc`（死叉） | 兼顧底部位置與趨勢動能確認 |
| `bb_water` | 雙重複合：BB 擴張 + 水下 | $\neg \text{bb\_squeeze} \land \text{DIF}_t \le 0.0$ | `raw_dc`（死叉） | **MACD 單筆期望最佳**，斬斷約 70%+ 假突破 |
| `bb_trailing` | 布林擴張 + ATR 追蹤止盈 | $\neg \text{bb\_squeeze}$ | `raw_dc` 或 $(H_{\text{peak}} - L_t) \ge \text{TRAILING\_ATR\_MULT} \times \text{ATR}_t$ | 高位利潤保護，防止主升浪回吐 |

> **撮合與結算邏輯**：
> - 進場價格以收盤價計入正向滑點：$P_{\text{entry}} = C_t \times (1 + \text{SLIPPAGE})$；買入股數為 $\frac{\text{FIXED\_CASH} \times (1 - \text{COMMISSION\_RATE})}{P_{\text{entry}}}$。
> - `bb_trailing` 觸發追蹤停損時，出場目標價為 $H_{\text{peak}} - \text{TRAILING\_ATR\_MULT} \times \text{ATR}_t$（再計入負向滑點與手續費）。
> - 回測最後一個交易日若仍持倉，執行 Mark-to-Market 強制平倉結算。

---

## 5. 測試執行檢查清單 (Execution Checklist)

1. 確認輸入資料包含 `date, open, high, low, close, volume`，且依時間升序排列。
2. 指標計算須涵蓋 `START_DATE` 之前至少 `WARMUP_BARS` 個交易日，僅統計 `[START_DATE, END_DATE]` 期間產生的交易。
3. 產出結果時，務必附上 **Trades, Win Rate %, Total Net PnL ($), Expectancy ($), Profit Factor, Strategy MDD % vs B&H MDD %, Chop Tax (<=10d $)**。

---

## 6. Conclusions & Human Decision Guide (歷史實證結論、優劣勢與優化解析)

> 基準數據來源：SOX 30 + Mag 7 共 35 檔個股（2020-01-02 至 2026-11-10，單筆固定開倉 `$10,000`）。

### 📊 核心實證績效對照
| 模型變體 | 交易數 | 勝率 | 獲利因子 (PF) | 盈虧比 | 單筆期望 | 總淨利 | 短線摩擦稅 |
|:---|:---:|:---:|:---:|:---:|:---:|---:|---:|
| `raw` (原始雙均線) | 2,324 | 37.9% | 1.18 | 2.52x | `$147.00` | **`$341,630.69`** | `-$561,712.48` |
| `adx_20` (ADX > 20 過濾) | 1,684 | 40.6% | 1.25 | 2.45x | `$188.73` | **`$317,816.20`** | `-$381,519.50` |
| `bb_water` (BB 擴張 + 水下金叉) | 713 | **43.3%** | **1.39** | **2.65x** | **`$290.49`** | `$207,117.67` | **`-$159,274.94`** |

### ✅ 優點 (Pros) vs ❌ 缺點與盲點 (Cons)
- **Pros (優勢)**：
  1. **長牛總利潤天花板最高**：無界動量特性使其在單邊大牛市不會過早下車，能完整吃下數倍主升浪（`raw` 累計 `$341.6k` 為全場之冠）。
  2. **高盈虧比結構**：盈虧比穩定維持在 `2.45x ~ 2.65x`，少數大贏單即可覆蓋多筆小額試錯停損。
  3. **在市資金利用率高**：屬於高能常態型（暴露度約 `35% ~ 55%`），充分捕捉成長股 Beta 上行紅利。
- **Cons (缺點與風險)**：
  1. **震盪市摩擦稅極重**：EMA 天生有 **3~6 天時間滯後**，在窄幅箱體盤中雙均線反覆死結絞殺，`raw` 版在短線假突破上蒸發高達 `-$561,712.48`。
  2. **勝率偏低考驗心態**：勝率僅 `37.9% ~ 43.3%`，意味著實盤每 10 次開倉有約 6 次必須止損，連續虧損期（Drawdown Streak）容易引發交易員放棄執行。
  3. **熊市深回撤風險**：純靠 `MACD` 死叉出場在暴跌市反應偏慢，缺乏尾部風控時個股回撤可能深達 `-60%` 以上。

### 🔧 哪些優化真正有效？(What Refinements Help & Why)
1. **趨勢強度濾網 (`ADX > 20`) — 性價比最高的過濾**：
   - **效果**：過濾掉約 28% 無趨勢橫盤金叉（2,324 → 1,684 筆），大砍 **32% 摩擦稅**（省下 `$180k`），同時奇蹟般保留了 **93% 總淨利**（`$317.8k`）。
   - **原因**：強制只在方向性動能已經啟動時進場，避開無序震盪。
2. **底分型水下金叉 + 布林帶寬擴張 (`bb_water`) — 單筆品質之王**：
   - **效果**：交易數砍半以上至 713 筆，斬斷 **71.6% 摩擦稅**（降至 `-$159.2k`），單筆平均期望翻倍至 **`$290.49`**，獲利因子升至 `1.39`。
   - **原因**：`DIF <= 0` 確保買在波段相對低位（賠率空間大），`BB 擴張` 確認波動率剛脫離收斂準備噴出。
3. **進階風控建議 (`bb_trailing` 或結合階梯保本)**：
   - 單純用死叉出場容易在見頂暴跌時回吐大半浮盈；搭配 `3.0x ATR` 追蹤止盈或轉用 `trinity_strategy.md` 的階梯保本，能大幅改善尾部回撤。

### 🧠 人類決策與學習重點
- **何時採用**：目標為最大化單邊牛市總複利，且標的為高 Beta 成長股（如 `NVDA, TSLA, AMD, AVGO`）時，優先啟用 **`adx_20`** 或 **`bb_water`**。
- **測試新標的觀察點**：若新標的在 `raw` 下摩擦稅佔總淨利比例過高，立即對比 `adx_20` 與 `bb_water` 的改善幅度；若該標的長期處於橫盤箱體，應果斷放棄 MACD 改用 `bollinger_strategy.md` (`reversion`) 或 `rsi_strategy.md` (`extreme_oversold`)。
