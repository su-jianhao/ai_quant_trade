# 量化策略提示詞庫與跨標的/跨區間回測指南 (Strategy Prompts & Testing Index)

本資料夾收錄基於 [`topic/README.md`](file:///home/jianhaos/project/ta/ta/topic/README.md) 驗證完成之五大經典量化指標體系策略提示詞（Strategy Prompts），專為**後續於不同股票池（美股個股、ETF、台股）與自訂日期區間進行快速回測、參數驗證與策略對比**而設計。

---

## 📋 策略提示詞導航總表 (Strategy Prompt Catalog)

| 策略家族 | 提示詞檔案 | 核心代表模型 (Variants) | 最佳適用場景 / 戰略定位 |
|:---|:---|:---|:---|
| **1. MACD 趨勢動能** | [`macd_strategy.md`](file:///home/jianhaos/project/ta/ta/prompts/strategy/macd_strategy.md) | `raw`, `adx_20`, `bb_squeeze`, `water_reversal`, `adx_water`, `bb_water`, `bb_trailing` | 單邊長牛趨勢跟隨；`adx_20` 保留 93% 淨利並大砍摩擦稅；`bb_water` 單筆期望最佳 |
| **2. 布林通道 (Bollinger)** | [`bollinger_strategy.md`](file:///home/jianhaos/project/ta/ta/prompts/strategy/bollinger_strategy.md) | `baseline`, `bw_expand`, `profit_lock`, `atr_trail`, `combo_refined`, `reversion`, `regime_adaptive` | 波動率擠壓突破與均值回歸；`regime_adaptive` 勝率 61.2%、摩擦稅反賺正收益 |
| **3. KDJ 隨機指標** | [`kdj_strategy.md`](file:///home/jianhaos/project/ta/ta/prompts/strategy/kdj_strategy.md) | `baseline`, `no_chase`, `trend_filter`, `profit_lock`, `oversold_low`, `combo_refined`, `oversold_trend` | 微觀恐慌抄底；`oversold_low` 勝率 70.5%、單筆期望 $476.56，極致低吸 |
| **4. RSI 相對強弱** | [`rsi_strategy.md`](file:///home/jianhaos/project/ta/ta/prompts/strategy/rsi_strategy.md) | `baseline`, `trend_filter`, `extreme_oversold`, `bullish_divergence`, `momentum_breakout`, `profit_lock`, `regime_adaptive` | `extreme_oversold` 全場勝率王 (81.3%) 與期望王 ($651.68)；`momentum_breakout` 捕獲主升浪 |
| **5. 三位一體 (Grand Trinity)** | [`trinity_strategy.md`](file:///home/jianhaos/project/ta/ta/prompts/strategy/trinity_strategy.md) | `raw_trinity`, `macd_bb_fusion`, `bb_kdj_fusion`, `grand_trinity`, `regime_adaptive_trinity` | 機構級全天候防禦盾牌；4 階風控將尾部最大回撤 (MDD) 壓制至全場最低 |
| **6. 巴菲特護城河選股 (Buffett Value-Quality)** | [`buffett_value_strategy.md`](buffett_value_strategy.md) | `buffett_full_score_top10`, `buffett_moat_compounder`, `buffett_classic_roe_value`, `buffett_pure_roe_top10` + 技術面進出場增強 | 大型權值龍頭（如 TW50）基本面 8 因子 PIT 選股 + 技術面/風控進出場對比驗證；`buffett_full_score_top10` Sharpe 3.57、MDD -8.97% |
| **7. DSA 15 大內置策略庫 (`daily_stock_analysis`)** | [`dsa_15_strategies.md`](dsa_15_strategies.md) | `emotion_cycle`, `box_oscillation`, `growth_quality`, `wave_theory`, `bull_trend` 等 15 種策略 | 完整移植自 `daily_stock_analysis` 15 大策略（可透過 `modules/backtest_15_strategies_tw50.py` 一鍵量化評比）；TW50 以 `emotion_cycle` (Sharpe 2.84) 與 `box_oscillation` (MDD -4.86%) 最強 |
| **8. VWAP 機構成本與法人共振** | [`vwap_strategy.md`](vwap_strategy.md) | `vwap_baseline`, `vwap_pullback_trend`, `vwap_avwap_breakout`, `vwap_inst_combo` | **全專案純技術／籌碼總冠軍**：`vwap_inst_combo` 在 TW50 繳出 `+92.72%`、Sharpe `2.89`、Calmar `11.39`、MDD `-10.66%`、PF `4.60` |
| **9. 神奇九轉 (TD Sequential)** | [`td_sequential_strategy.md`](td_sequential_strategy.md) | `td_baseline`, `td_confirm_rebound`, `td_trend_dip` | 時間計數轉折與減碼利器：`td_trend_dip`（多頭 TD7+ 回調買＋高九減半）將 MDD 壓至 `-7.96%`、勝率 `60.0%`、PF `3.67` |
| **10. J-Law VCP & META 精兵狙擊** | [`jlaw_vcp_strategy.md`](jlaw_vcp_strategy.md) | `jlaw_01_vcp_raw`, `jlaw_02_vcp_rs_sma63`, `jlaw_03_meta_sniper`, `jlaw_04_meta_pullback` | **跨牛熊單筆品質 & 抗崩盤總冠軍**：美股 6 年實測 PF `3.14`、勝率 `64.8%`、盈虧比 `3.34x`、2022 熊市 MDD 僅 `-8.2%`（需大股票池或搭配底倉） |

---

## 🎯 快速選型決策樹 (Quick Selection Matrix)

- **追求極限勝率與高確定性恐慌抄底**：選用 `rsi_strategy.md` (`extreme_oversold`) 或 `kdj_strategy.md` (`oversold_low`)。
- **追求單邊牛市最大資本增長爆發力**：選用 `macd_strategy.md` (`adx_20`) 或 `rsi_strategy.md` (`momentum_breakout` / `profit_lock`)。
- **追求穩健平衡（勝率與賠率兼備）**：選用 `bollinger_strategy.md` (`regime_adaptive`)。
- **追求最低回撤與極致風控防禦**：選用 `trinity_strategy.md` (`grand_trinity` / `regime_adaptive_trinity`)。

---

## 🧪 統一測試參數介面 (Standardized Test Parameters)

在對任意新標的或新日期區間進行測試時，請於對話中指定以下標準參數（未指定時採預設基準）：

- **`SYMBOLS`**：目標股票代碼清單（如 `["NVDA", "TSLA", "AAPL"]` 或 `["2330", "2454"]`）
- **`START_DATE` / `END_DATE`**：回測起訖日期（如 `2022-01-01` 至 `2025-12-31`；需預留至少 50~200 根 K 線作為指標暖身期 Warmup）
- **`MODEL_KEY`**：指定策略變體（或 `"compare"` 進行全變體橫向對比）
- **`FIXED_CASH`**：單筆固定開倉本金（預設 `$10,000.0` 美元或等值新台幣）
- **`SLIPPAGE`**：雙邊滑點（預設 `0.0005` 即 5 bps）
- **`COMMISSION_RATE`**：雙邊手續費率（美股預設 `0.0003`；台股需調整為單邊手續費 `0.000855` + 賣出證交稅 `0.003`）
- **`REGIME_MODE`**（僅雙引擎策略適用）：指定標的屬於 `MOMENTUM`（高 Beta 成長股）或 `CYCLICAL`（週期/震盪/指數 ETF），或依過去 252 日年化波動率與趨勢度自動判定。

### 統一輸出審計指標 (Standard Output Metrics)
每次測試必須輸出以下結構化指標表，便於跨股票與跨日期橫向比較：
1. 總交易次數 (`Trades`) & 綜合勝率 (`Win Rate %`)
2. 總淨利潤 (`Net PnL $`) & 累計報酬率 (`Return %`)
3. 單筆平均期望值 (`Expectancy $`) & 盈虧比 (`Payoff Ratio`) & 獲利因子 (`Profit Factor`)
4. 最大回撤 (`Strategy MDD %` vs `Buy & Hold MDD %`)
5. 短線摩擦稅 (`Chop Tax <= 10d $`) & 在市暴露度 (`Exposure %`)
