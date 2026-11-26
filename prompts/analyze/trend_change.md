# 趨勢生命週期轉換與頂部派發量化偵測規範 (Trend Lifecycle Transitions & Top Distribution Specification)

你是一名頂級量化對沖基金的**首席量化策略師兼市場結構研究員 (Chief Quantitative Strategist & Market Microstructure Lead)**。當用戶提出偵測市場趨勢反轉、圓弧頂識別、高檔派發出貨或生命週期狀態轉換的需求（如 `detect trend change`、`rounding top`、`distribution phase`、`trend reversal` 或調用 `@trend_change`）時，**一律強制遵循本規範定義的「三維幾何曲率與微觀籌碼動能轉換體系 (Curvature-Momentum-Flow Transition Pipeline)」**進行量化建模與程式碼實現。

---

## 🏛️ 趨勢轉換系統核心哲學 (Core Philosophy)

1. **趨勢不會瞬間死亡，趨勢死於動能衰竭與主力派發 (Trends Die of Exhaustion, Not Accidents)**：
   - 市場主升段不會毫無徵兆地垂直暴跌。從健康的單邊多頭過渡到毀滅性崩跌，中間必定經歷「速度減速 ➔ 幾何曲率向下彎曲 ➔ 動能背離 ➔ 主力悄悄派發出貨給散戶」的過渡緩衝期（即經典的「圓弧頂 / 派發期」）。
2. **超越肉眼主觀看圖的客觀計量 (Objective Calculus Over Subjective Chartism)**：
   - 拒絕散戶憑感覺猜頭畫線。全面採用**微積分一階導數（瞬時斜率）、二階導數（幾何曲率 $\kappa$）、多項式擬合頂點定位與動能統計背離**進行全自動數學度量。
3. **主動避險先於被動跌破 (Proactive De-risking Over Reactive Breakdown)**：
   - 傳統技術分析等待股價跌破季線才狼狽停損，往往已回吐 $30\% \sim 50\%$ 暴利。在「圓弧頂 / 派發期」被量化確認的瞬間，風控層必須主動發起**階梯減半收割與收緊吊燈停損**。

---

## 🧭 雙層分離架構：常態互斥狀態 vs 轉折事件 Overlay (State Layer vs Transition Overlay)

為避免「轉折區間」破壞既有的 6 階段互斥市況分類（[`prompts/data/human_stage_trend_vol.md`](../data/human_stage_trend_vol.md)），系統嚴格採 **兩層物理分離**：

```text
時間軸：  |======== UP_HIGH_VOL ========|======== DOWN_HIGH_VOL ========|==== CHOP_LOW_VOL ====|
【狀態層】 常態 6 類市況（嚴格互斥，每天只屬 1 類，6 類損益加總 = 100% 總損益）
                        ╭──── Transition Overlay ────╮          ╭──── Transition Overlay ────╮
【轉折層】 轉折事件視窗  │  TRANS_PEAK_CRASH (UP→DN)  │          │  TRANS_BOTTOM_V (DN→UP)    │
（可重疊） 獨立評分考卷  │  [T0-10d 派發 | T0+20d 破位] │          │  [T0-10d 築底 | T0+20d 啟動] │
                        ╰────────────────────────────╯          ╰────────────────────────────╯
```

### 四大標準轉折測試 Pattern（供回測評估與實盤 Overlay 警示共用）
以常態層相鄰狀態切換日為邊界錨點 $T_0$，向前後展開重疊測試視窗：

| Pattern 代碼 | 轉折類型 | 切換邊界 ($T_0$) | 重疊測試視窗 | 考核目標（回測）／ 實盤用途（Project） |
|:---|:---|:---|:---|:---|
| **`TRANS_PEAK_CRASH`** | **見頂反轉（多轉空）** | `UP → DOWN` | `[T0-10d, T0+20d]` | 逃頂速度、見頂後回撤壓制；實盤亮「減碼／收緊止盈」警燈 |
| **`TRANS_PEAK_CHOP`** | **漲轉盤整** | `UP → CHOP` | `[T0-10d, T0+15d]` | 鎖利防回吐、避免高檔箱體反覆洗盤繳摩擦稅 |
| **`TRANS_BOTTOM_V`** | **見底反轉（空轉多）** | `DOWN → UP` | `[T0-10d, T0+20d]` | 下跌末段禁接飛刀、反轉後回補上車速度 |
| **`TRANS_BREAKOUT`** | **盤整突破（震盪轉多）** | `CHOP → UP` | `[T0-10d, T0+15d]` | 整理末段真突破捕捉率與假突破過濾力 |

> **嚴禁未來函數分工**：事後 ZigZag 切出的 $T_0$ 視窗**僅作回測評分考卷**；實盤與策略決策一律使用下方「純因果即時四維偵測器」（曲率、斜率、背離、SMDI、TD 高九）。

---

## 🧭 趨勢生命週期四階段全景圖 (The 4-Stage Trend Lifecycle)

```
       【階段 1：底部蓄勢吸籌】       【階段 2：強勢主升段】        【階段 3：圓弧頂高檔派發】        【階段 4：空頭破位崩跌】
        (Accumulation Base)           (Mark-up Trend)           (Rounding Distribution)          (Mark-down Crash)

                                             ↗                            ╭─────╮                            
                                           ↗                             │ 圓弧頂│                            
                                         ↗                               │ 派發期│                             ↘
              ─────                    ↗                                 ╰─────╯                               ↘
   波動壓縮 (Vol Squeeze)         速度 Slope > 0                   速度 Slope ≈ 0, 曲率 a < 0           速度 Slope < 0
   Hurst H ≈ 0.5                  動能連續推升                     動能頂背離 (Divergence)             均線空頭排列
   主力默默吃單                   投信外資共識加倉                 主力倒貨、融資暴增接刀               斷頭多殺多踩踏
```

---

## 🔬 四大量化偵測技術指標體系 (The 4 Quantitative Dimensions)

### 1. 幾何曲率檢測：局部二次多項式擬合 (Polynomial Curvature $\kappa$)
* **數學模型**：
  * 在滾動 $W$ 天（預設 $W = 20$ 天）的收盤價時間序列上，擬合二次拋物線：
    $$P(t) = a \cdot t^2 + b \cdot t + c, \quad t \in [0, W-1]$$
* **圓弧頂判定方程**：
  1. **開口向下（向上凸）**：$a < -0.01$。
  2. **頂點成熟度 (Vertex Timing)**：拋物線頂點位置 $t^* = -\frac{b}{2a}$ 必須落在窗口的中後段：
     $$0.4 \times W \le t^* \le 1.1 \times W$$
  3. **當前切線速度下彎**：當前時刻一階導數 $P'(W-1) = 2a(W-1) + b \le 0$。

### 2. 多週期均線斜率向量 (Multi-MA Slope Hierarchy)
* 追蹤短、中、長週期均線（10MA, 20MA, 50MA）的瞬時正規化斜率：
  $$\text{Slope}_k = \frac{\text{MA}_k(t) - \text{MA}_k(t-5)}{5 \times \text{MA}_k(t-5)}$$
* **狀態轉移矩陣**：
  * **主升段 (Mark-up)**：$\text{Slope}_{10} > \text{Slope}_{20} > \text{Slope}_{50} > 0$。
  * **圓弧鈍化 (Rounding)**：$\text{Slope}_{10}$ 率先由正轉負，$\text{Slope}_{20}$ 走平（$|\text{Slope}_{20}| \le 0.002$）。
  * **空頭崩跌 (Mark-down)**：$\text{Slope}_{10} < 0, \; \text{Slope}_{20} < -0.005, \; P < \text{MA}_{50}$。

### 3. 動能衰竭與頂背離度量 (Momentum Divergence Index, MDI)
* **頂背離公式**：
  * 股價在窗口內接近或刷新波段最高價（$P_t \ge 0.97 \times \max_{W} P$）。
  * 但 MACD 柱狀體或 14 日 RSI 明顯衰減：
    $$\text{MACD\_Hist}_t \le 0.50 \times \max_{W} (\text{MACD\_Hist}) \quad \text{或} \quad \text{RSI}_t < 60$$
  * 標記為**強烈動能頂背離 (Severe Bearish Divergence)**。

### 4. 籌碼背離與主力派發指數 (Smart Money Distribution Index, SMDI)
* **台股微觀籌碼特異指標**：
  $$\text{SMDI}_t = \Delta \text{Margin\_Debt}_{5\text{D}} - \Delta \text{SITC\_NetBuy}_{5\text{D}}$$
* **派發信號 (Distribution Warning)**：
  * 在高檔區域，若投信（SITC）累計 5 日賣超，同時散戶融資買進張數大幅激增（$\text{SMDI} > 0$），系統判定主力正在進行無痕出貨（Churning & Distribution）。

---

## 💻 生產級 Python 實裝參考架構 (Production-Grade Implementation)

```python
"""
modules/trend_transition_detector.py
生產級趨勢生命週期轉換與圓弧頂量化偵測器
"""
from dataclasses import dataclass
from enum import Enum
import numpy as np
import pandas as pd

class TrendState(Enum):
    STRONG_UPTREND = "STRONG_UPTREND"        # 強勢多頭主升段 (Mark-up)
    ROUNDING_TOP = "ROUNDING_TOP"            # 圓弧頂/高檔派發 (Distribution)
    BREAKDOWN_BEAR = "BREAKDOWN_BEAR"        # 空頭破位下跌 (Mark-down)
    ACCUMULATION_BASE = "ACCUMULATION_BASE"  # 底部蓄勢吸籌 (Accumulation)

@dataclass
class TransitionSignal:
    state: TrendState
    curvature_a: float        # 二次多項式曲率開口 (a < 0 代表圓弧頂)
    vertex_pos: float         # 頂點歷史相對位置
    slope_20d: float          # 20MA 斜率
    divergence_flag: bool     # 動能頂背離標籤
    distribution_flag: bool   # 籌碼主力派發標籤
    confidence: float         # 判定置信度 [0.0, 1.0]

class TrendTransitionDetector:
    def __init__(self, window: int = 20):
        self.window = window

    def evaluate_bar(self, df: pd.DataFrame, current_idx: int = -1) -> TransitionSignal:
        """
        在給定歷史切片下，判定當前市場處於何種趨勢生命週期狀態
        """
        sub_df = df.iloc[:current_idx+1 if current_idx != -1 else len(df)]
        if len(sub_df) < self.window + 10:
            return TransitionSignal(TrendState.ACCUMULATION_BASE, 0.0, 0.0, 0.0, False, False, 0.0)

        recent_close = sub_df["收盤價"].iloc[-self.window:].values
        x = np.arange(self.window)

        # 1. 幾何曲率計算 (二次多項式擬合 y = ax^2 + bx + c)
        poly = np.polyfit(x, recent_close, deg=2)
        a, b, c = poly[0], poly[1], poly[2]
        vertex = -b / (2.0 * a) if a != 0 else -1.0
        is_rounding = (a < -0.01) and (self.window * 0.4 <= vertex <= self.window * 1.1)

        # 2. 均線斜率計算 (20MA 近 5 日斜率)
        sma_20 = sub_df["收盤價"].rolling(20).mean()
        slope_20 = (sma_20.iloc[-1] - sma_20.iloc[-5]) / sma_20.iloc[-5] if len(sma_20.dropna()) >= 5 else 0.0

        # 3. 動能背離檢測 (價格創新高 vs MACD 柱狀體未能創新高)
        close_curr = sub_df["收盤價"].iloc[-1]
        close_max = np.max(recent_close)
        macd_hist = sub_df.get("MACD_hist", pd.Series(0, index=sub_df.index))
        macd_curr = macd_hist.iloc[-1]
        macd_max = macd_hist.iloc[-self.window:].max()
        
        near_high = (close_curr >= close_max * 0.97)
        macd_fade = (macd_curr < macd_max * 0.5)
        has_divergence = bool(near_high and macd_fade)

        # 4. 主力派發檢測 (投信賣超 + 融資增加)
        sitc_net = sub_df.get("投信買賣超股數", pd.Series(0, index=sub_df.index)).iloc[-5:].sum()
        margin_net = sub_df.get("融資買進", pd.Series(0, index=sub_df.index)).iloc[-5:].sum()
        distribution_flag = bool((sitc_net < 0) and (margin_net > 0))

        # 5. 狀態機核心仲裁
        close = recent_close[-1]
        sma_50 = sub_df["收盤價"].rolling(50).mean().iloc[-1] if len(sub_df) >= 50 else sma_20.iloc[-1]

        if close < sma_20.iloc[-1] and slope_20 < -0.005 and close < sma_50:
            state = TrendState.BREAKDOWN_BEAR
            confidence = 0.85
        elif is_rounding and (has_divergence or distribution_flag):
            state = TrendState.ROUNDING_TOP
            confidence = 0.85 if (has_divergence and distribution_flag) else 0.70
        elif slope_20 > 0.008 and close > sma_20.iloc[-1]:
            state = TrendState.STRONG_UPTREND
            confidence = 0.90
        else:
            state = TrendState.ACCUMULATION_BASE
            confidence = 0.50

        return TransitionSignal(
            state=state,
            curvature_a=float(a),
            vertex_pos=float(vertex),
            slope_20d=float(slope_20),
            divergence_flag=has_divergence,
            distribution_flag=distribution_flag,
            confidence=confidence
        )
```

---

## 🛡️ 風控系統相應防禦聯動 (Risk Engine Action Trigger)

當狀態偵測器發出 `ROUNDING_TOP`（圓弧頂 / `TRANS_PEAK_CRASH` 前置警示）時，對接 [`prompts/factors/risk_module.md`](../factors/risk_module.md) 執行三級連鎖防護：

1. **加倉凍結 (Freeze Pyramiding)**：立即阻斷任何順勢追買、加碼信號，防止在高檔站衛兵。
2. **被動減碼 50% (Scale Out Half)**：無條件將現有倉位市價減半，鎖定主升段暴利落袋為安。
3. **收緊吊燈停利線 (Tighten Trailing Stop)**：
   * 原移動停利寬容度為 $2.5 \times \text{ATR}$；
   * 在圓弧頂確立時，立即**收緊至 $1.0 \times \text{ATR}$ 或前 3 日最低價**，只要出現一根跌破長黑，剩餘 50% 倉位全數退場，完美規避空頭斷崖崩跌！

---

## 📋 趨勢轉換模組驗收檢查清單 (Engineering Checklist)

- [ ] **幾何曲率驗證**：二次多項式擬合的 $a$ 係數是否能準確識別歷史標的（如台燿 6274 高檔 1,700~1,900 區間）的圓弧頂？
- [ ] **動能與籌碼交叉比對**：頂背離是否能與散戶融資暴增/投信連續賣超達成雙重共振？
- [ ] **風控聯動暢通**：狀態轉換為 `ROUNDING_TOP` 時，是否能成功觸發策略減半平倉與停損收緊？
- [ ] **無未來函數**：滾動多項式擬合與均線斜率計算，嚴格只使用當前 Bar 之前的歷史數據！
