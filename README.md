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
- data fetch prompt : prompts/data_generate.md
- **Factors（因子分類）**：
  - **Trend（趨勢）**：`Up` / `Down` / `Chop`
  - **Volatility（波動度）**：低 / 中 / 高
- prompts/data/human_stage_trend_vol.md


- DATA is generated in data folder. 

### 2. 選股池階段

> **核心理論**：選一個有方向性的股票，Buy & Hold (B&H) 比策略操作更直接、利潤更高。

- **基本面選股**：依據營收成長、獲利能力、估值與現金流等基本面條件篩選優質標的
- **策略型選股**：結合技術面、籌碼面或多因子量化條件篩選具備動能或結構優勢的標的
- **ETF 選股**：篩選具備明確趨勢或產業代表性的 ETF 標的（如 `QQQ`、`SOXX`、`0050.TW`）
- prompts/stock_selector.md
### 3. 策略操作

- **進出場 Signal**：選擇標的的重要性與出場時機的關鍵性
- **狀態判斷**：標的與市場狀態評估（`Good` / `Bad` / `Status`）
- **風險控制**：倉位管理與停損風控機制
- prompts/backtest.md
- prompts/risk_module.md
- prompts/general_strategy.md
- Backtest resut: it should generated in runs/{date}_{strategy}_{stocks} folder


### 4. 改進模組與測試模組關係

- **總論**：改進模組與測試模組的定位與回饋閉環
- **逐筆分析**：交易明細歸因與損益拆解
- **改進**：依據分析結果進行策略與參數優化
- prompts/stock_analysis.md
- prompts/full_report.md
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
