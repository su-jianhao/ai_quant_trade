# INTC & QCOM 近期買賣訊號掃描、操作行動與風控報告 (20261122_2113)

## 執行條件標頭 (Run Metadata Header)
- **Run ID**：`20261122_2113_signal_action_risk`
- **測試時間 (`test_time`)**：`2026-11-22 21:13:00`
- **資料截止日**：`2026-11-20`（`data/sox_mag7_price_vol_types/price_vol_analysis.db` (2020-01-02 ~ 2026-11-10) + `data/intc_qcom/intc_qcom_2026.db` 增量更新至 **`2026-11-20`**（共 1,732 根日 K 線，含 6 大量波體制 `Type 1~6` 標記））
- **掃描範圍**：`bollinger` / `kdj` / `macd` / `rsi` 全 28 組變體（近 35 個交易日 `2026-10-01` ~ `2026-11-20` 買賣訊號 + 當前在倉狀態）
- **前期回測對照**：[20261122_2040_bb_kdj_macd_rsi_2020](../20261122_2040_bb_kdj_macd_rsi_2020/trade_advice.md)｜[backtest_report.md](../../trades/20261122_2040_multi4_intc_qcom/backtest_report.md)｜[robustness_report.md](../../trades/20261122_2040_multi4_intc_qcom/robustness_report.md)

---

## 1. 近期買賣訊號總覽 (Recent Buy / Sell Signals: `2026-11-06` ~ `2026-11-20`)

近 10 個交易日共偵測到 **32 筆** 策略買賣訊號（含 **BUY 進場 19 筆**、**SELL 出場 13 筆**）：

| 日期 | 標的 | 訊號 | 策略 | 變體 (`MODEL_KEY`) | 觸發價 ($) | 狀態 / 出場原因 | 穩健評級 |
|:---:|:---:|:---:|:---|:---|---:|:---|:---|
| `2026-11-18` | **INTC** | **BUY (進場)** | macd | `raw` | `$54.70` | OPEN (持倉中) | ROBUST |
| `2026-11-18` | **INTC** | **BUY (進場)** | macd | `adx_20` | `$54.70` | OPEN (持倉中) | UNSTABLE |
| `2026-11-18` | **INTC** | **BUY (進場)** | macd | `bb_squeeze` | `$54.70` | OPEN (持倉中) | ROBUST |
| `2026-11-18` | **INTC** | **BUY (進場)** | macd | `water_reversal` | `$54.70` | OPEN (持倉中) | ROBUST |
| `2026-11-18` | **INTC** | **BUY (進場)** | macd | `adx_water` | `$54.70` | OPEN (持倉中) | ROBUST |
| `2026-11-18` | **INTC** | **BUY (進場)** | macd | `bb_water` | `$54.70` | OPEN (持倉中) | PASS (6/6) |
| `2026-11-18` | **INTC** | **BUY (進場)** | macd | `bb_trailing` | `$54.70` | OPEN (持倉中) | BULL_ONLY |
| `2026-11-18` | **INTC** | **SELL (出場)** | kdj | `baseline` | `$54.64` | KDJ Death Cross (-12.67%) | BULL_ONLY |
| `2026-11-18` | **INTC** | **SELL (出場)** | kdj | `no_chase` | `$54.64` | KDJ Death Cross (-12.67%) | BULL_ONLY |
| `2026-11-18` | **INTC** | **SELL (出場)** | kdj | `profit_lock` | `$54.64` | KDJ Death Cross (-12.67%) | BULL_ONLY |
| `2026-11-18` | **QCOM** | **SELL (出場)** | macd | `raw` | `$159.73` | MACD Death Cross (-9.64%) | MEAN_REV |
| `2026-11-18` | **QCOM** | **SELL (出場)** | macd | `bb_squeeze` | `$159.73` | MACD Death Cross (-9.64%) | PASS (5/6) |
| `2026-11-18` | **QCOM** | **SELL (出場)** | macd | `water_reversal` | `$159.73` | MACD Death Cross (-9.64%) | ROBUST |
| `2026-11-18` | **QCOM** | **SELL (出場)** | macd | `bb_water` | `$159.73` | MACD Death Cross (-9.64%) | ROBUST |
| `2026-11-18` | **QCOM** | **SELL (出場)** | macd | `bb_trailing` | `$159.73` | MACD Death Cross (-9.64%) | ALL_WEATHER |
| `2026-11-17` | **QCOM** | **SELL (出場)** | kdj | `baseline` | `$166.59` | KDJ Death Cross (-2.95%) | BULL_ONLY |
| `2026-11-17` | **QCOM** | **SELL (出場)** | kdj | `no_chase` | `$166.59` | KDJ Death Cross (-2.95%) | BULL_ONLY |
| `2026-11-13` | **QCOM** | **SELL (出場)** | kdj | `profit_lock` | `$172.38` | Breakeven Stop (+0.42%) | CONDITIONAL (3/6) |
| `2026-11-11` | **INTC** | **BUY (進場)** | kdj | `baseline` | `$62.53` | 已平倉 (2026-11-18 -12.67%) | BULL_ONLY |
| `2026-11-11` | **INTC** | **BUY (進場)** | kdj | `no_chase` | `$62.53` | 已平倉 (2026-11-18 -12.67%) | BULL_ONLY |
| `2026-11-11` | **INTC** | **BUY (進場)** | kdj | `profit_lock` | `$62.53` | 已平倉 (2026-11-18 -12.67%) | BULL_ONLY |
| `2026-11-11` | **INTC** | **BUY (進場)** | rsi | `baseline` | `$62.53` | OPEN (持倉中) | BULL_ONLY |
| `2026-11-11` | **QCOM** | **BUY (進場)** | macd | `raw` | `$176.66` | 已平倉 (2026-11-18 -9.64%) | MEAN_REV |
| `2026-11-11` | **QCOM** | **BUY (進場)** | macd | `bb_squeeze` | `$176.66` | 已平倉 (2026-11-18 -9.64%) | PASS (5/6) |
| `2026-11-11` | **QCOM** | **BUY (進場)** | macd | `water_reversal` | `$176.66` | 已平倉 (2026-11-18 -9.64%) | ROBUST |
| `2026-11-11` | **QCOM** | **BUY (進場)** | macd | `bb_water` | `$176.66` | 已平倉 (2026-11-18 -9.64%) | ROBUST |
| `2026-11-11` | **QCOM** | **BUY (進場)** | macd | `bb_trailing` | `$176.66` | 已平倉 (2026-11-18 -9.64%) | ALL_WEATHER |
| `2026-11-10` | **QCOM** | **SELL (出場)** | bollinger | `reversion` | `$173.44` | Reversion Target >= BB_Mid (+5.37%) | ROBUST |
| `2026-11-10` | **QCOM** | **SELL (出場)** | bollinger | `regime_adaptive` | `$173.44` | Reversion Target >= BB_Mid (+5.37%) | ROBUST |
| `2026-11-09` | **QCOM** | **BUY (進場)** | kdj | `baseline` | `$171.56` | 已平倉 (2026-11-17 -2.95%) | BULL_ONLY |
| `2026-11-09` | **QCOM** | **BUY (進場)** | kdj | `no_chase` | `$171.56` | 已平倉 (2026-11-17 -2.95%) | BULL_ONLY |
| `2026-11-09` | **QCOM** | **BUY (進場)** | kdj | `profit_lock` | `$171.56` | 已平倉 (2026-11-13 +0.42%) | CONDITIONAL (3/6) |

### 近月完整買賣訊號流水 (`2026-10-01` ~ `2026-11-20`)

| 日期 | 標的 | 訊號 | 策略 | 變體 | 觸發價 ($) | 狀態 / 報酬% | 穩健評級 |
|:---:|:---:|:---:|:---|:---|---:|:---|:---|
| `2026-11-18` | **INTC** | BUY (進場) | macd | `raw` | `$54.70` | OPEN (持倉中) | ROBUST |
| `2026-11-18` | **INTC** | BUY (進場) | macd | `adx_20` | `$54.70` | OPEN (持倉中) | UNSTABLE |
| `2026-11-18` | **INTC** | BUY (進場) | macd | `bb_squeeze` | `$54.70` | OPEN (持倉中) | ROBUST |
| `2026-11-18` | **INTC** | BUY (進場) | macd | `water_reversal` | `$54.70` | OPEN (持倉中) | ROBUST |
| `2026-11-18` | **INTC** | BUY (進場) | macd | `adx_water` | `$54.70` | OPEN (持倉中) | ROBUST |
| `2026-11-18` | **INTC** | BUY (進場) | macd | `bb_water` | `$54.70` | OPEN (持倉中) | PASS (6/6) |
| `2026-11-18` | **INTC** | BUY (進場) | macd | `bb_trailing` | `$54.70` | OPEN (持倉中) | BULL_ONLY |
| `2026-11-18` | **INTC** | SELL (出場) | kdj | `baseline` | `$54.64` | KDJ Death Cross (-12.67%) | BULL_ONLY |
| `2026-11-18` | **INTC** | SELL (出場) | kdj | `no_chase` | `$54.64` | KDJ Death Cross (-12.67%) | BULL_ONLY |
| `2026-11-18` | **INTC** | SELL (出場) | kdj | `profit_lock` | `$54.64` | KDJ Death Cross (-12.67%) | BULL_ONLY |
| `2026-11-18` | **QCOM** | SELL (出場) | macd | `raw` | `$159.73` | MACD Death Cross (-9.64%) | MEAN_REV |
| `2026-11-18` | **QCOM** | SELL (出場) | macd | `bb_squeeze` | `$159.73` | MACD Death Cross (-9.64%) | PASS (5/6) |
| `2026-11-18` | **QCOM** | SELL (出場) | macd | `water_reversal` | `$159.73` | MACD Death Cross (-9.64%) | ROBUST |
| `2026-11-18` | **QCOM** | SELL (出場) | macd | `bb_water` | `$159.73` | MACD Death Cross (-9.64%) | ROBUST |
| `2026-11-18` | **QCOM** | SELL (出場) | macd | `bb_trailing` | `$159.73` | MACD Death Cross (-9.64%) | ALL_WEATHER |
| `2026-11-17` | **QCOM** | SELL (出場) | kdj | `baseline` | `$166.59` | KDJ Death Cross (-2.95%) | BULL_ONLY |
| `2026-11-17` | **QCOM** | SELL (出場) | kdj | `no_chase` | `$166.59` | KDJ Death Cross (-2.95%) | BULL_ONLY |
| `2026-11-13` | **QCOM** | SELL (出場) | kdj | `profit_lock` | `$172.38` | Breakeven Stop (+0.42%) | CONDITIONAL (3/6) |
| `2026-11-11` | **INTC** | BUY (進場) | kdj | `baseline` | `$62.53` | 已平倉 (2026-11-18 -12.67%) | BULL_ONLY |
| `2026-11-11` | **INTC** | BUY (進場) | kdj | `no_chase` | `$62.53` | 已平倉 (2026-11-18 -12.67%) | BULL_ONLY |
| `2026-11-11` | **INTC** | BUY (進場) | kdj | `profit_lock` | `$62.53` | 已平倉 (2026-11-18 -12.67%) | BULL_ONLY |
| `2026-11-11` | **INTC** | BUY (進場) | rsi | `baseline` | `$62.53` | OPEN (持倉中) | BULL_ONLY |
| `2026-11-11` | **QCOM** | BUY (進場) | macd | `raw` | `$176.66` | 已平倉 (2026-11-18 -9.64%) | MEAN_REV |
| `2026-11-11` | **QCOM** | BUY (進場) | macd | `bb_squeeze` | `$176.66` | 已平倉 (2026-11-18 -9.64%) | PASS (5/6) |
| `2026-11-11` | **QCOM** | BUY (進場) | macd | `water_reversal` | `$176.66` | 已平倉 (2026-11-18 -9.64%) | ROBUST |
| `2026-11-11` | **QCOM** | BUY (進場) | macd | `bb_water` | `$176.66` | 已平倉 (2026-11-18 -9.64%) | ROBUST |
| `2026-11-11` | **QCOM** | BUY (進場) | macd | `bb_trailing` | `$176.66` | 已平倉 (2026-11-18 -9.64%) | ALL_WEATHER |
| `2026-11-10` | **QCOM** | SELL (出場) | bollinger | `reversion` | `$173.44` | Reversion Target >= BB_Mid (+5.37%) | ROBUST |
| `2026-11-10` | **QCOM** | SELL (出場) | bollinger | `regime_adaptive` | `$173.44` | Reversion Target >= BB_Mid (+5.37%) | ROBUST |
| `2026-11-09` | **QCOM** | BUY (進場) | kdj | `baseline` | `$171.56` | 已平倉 (2026-11-17 -2.95%) | BULL_ONLY |
| `2026-11-09` | **QCOM** | BUY (進場) | kdj | `no_chase` | `$171.56` | 已平倉 (2026-11-17 -2.95%) | BULL_ONLY |
| `2026-11-09` | **QCOM** | BUY (進場) | kdj | `profit_lock` | `$171.56` | 已平倉 (2026-11-13 +0.42%) | CONDITIONAL (3/6) |
| `2026-11-03` | **INTC** | BUY (進場) | rsi | `extreme_oversold` | `$60.58` | OPEN (持倉中) | UNSTABLE |
| `2026-11-03` | **INTC** | BUY (進場) | rsi | `regime_adaptive` | `$60.58` | OPEN (持倉中) | UNSTABLE |
| `2026-11-03` | **QCOM** | BUY (進場) | bollinger | `reversion` | `$164.51` | 已平倉 (2026-11-10 +5.37%) | ROBUST |
| `2026-11-03` | **QCOM** | BUY (進場) | bollinger | `regime_adaptive` | `$164.51` | 已平倉 (2026-11-10 +5.37%) | ROBUST |
| `2026-11-02` | **INTC** | SELL (出場) | kdj | `baseline` | `$59.94` | KDJ Death Cross (-33.82%) | BULL_ONLY |
| `2026-11-02` | **INTC** | SELL (出場) | kdj | `no_chase` | `$59.94` | KDJ Death Cross (-33.82%) | BULL_ONLY |
| `2026-10-30` | **INTC** | SELL (出場) | kdj | `profit_lock` | `$65.73` | Breakeven Stop (-27.43%) | BULL_ONLY |
| `2026-10-30` | **QCOM** | SELL (出場) | kdj | `baseline` | `$164.71` | KDJ Death Cross (-7.78%) | BULL_ONLY |
| `2026-10-30` | **QCOM** | SELL (出場) | kdj | `no_chase` | `$164.71` | KDJ Death Cross (-7.78%) | BULL_ONLY |
| `2026-10-30` | **QCOM** | SELL (出場) | kdj | `trend_filter` | `$164.71` | KDJ Death Cross (-7.78%) | BULL_ONLY |
| `2026-10-30` | **QCOM** | SELL (出場) | kdj | `profit_lock` | `$164.71` | KDJ Death Cross (-7.78%) | CONDITIONAL (3/6) |
| `2026-10-30` | **QCOM** | SELL (出場) | kdj | `combo_refined` | `$164.71` | KDJ Death Cross (-7.78%) | BULL_ONLY |
| `2026-10-30` | **QCOM** | SELL (出場) | macd | `raw` | `$164.71` | MACD Death Cross (-10.67%) | MEAN_REV |
| `2026-10-30` | **QCOM** | SELL (出場) | macd | `water_reversal` | `$164.71` | MACD Death Cross (-10.67%) | ROBUST |
| `2026-10-30` | **QCOM** | SELL (出場) | rsi | `momentum_breakout` | `$164.71` | Momentum Exit (-10.67%) | BULL_ONLY |
| `2026-10-30` | **QCOM** | SELL (出場) | rsi | `profit_lock` | `$164.71` | Profit Lock/RSI Exit (-10.67%) | BULL_ONLY |
| `2026-10-27` | **QCOM** | BUY (進場) | macd | `raw` | `$184.26` | 已平倉 (2026-10-30 -10.67%) | MEAN_REV |
| `2026-10-27` | **QCOM** | BUY (進場) | macd | `water_reversal` | `$184.26` | 已平倉 (2026-10-30 -10.67%) | ROBUST |
| `2026-10-27` | **QCOM** | BUY (進場) | rsi | `momentum_breakout` | `$184.26` | 已平倉 (2026-10-30 -10.67%) | BULL_ONLY |
| `2026-10-27` | **QCOM** | BUY (進場) | rsi | `profit_lock` | `$184.26` | 已平倉 (2026-10-30 -10.67%) | BULL_ONLY |
| `2026-10-26` | **INTC** | BUY (進場) | kdj | `baseline` | `$90.52` | 已平倉 (2026-11-02 -33.82%) | BULL_ONLY |
| `2026-10-26` | **INTC** | BUY (進場) | kdj | `no_chase` | `$90.52` | 已平倉 (2026-11-02 -33.82%) | BULL_ONLY |
| `2026-10-26` | **INTC** | BUY (進場) | kdj | `profit_lock` | `$90.52` | 已平倉 (2026-10-30 -27.43%) | BULL_ONLY |
| `2026-10-22` | **INTC** | SELL (出場) | kdj | `baseline` | `$85.45` | KDJ Death Cross (-8.18%) | BULL_ONLY |
| `2026-10-22` | **INTC** | SELL (出場) | kdj | `no_chase` | `$85.45` | KDJ Death Cross (-8.18%) | BULL_ONLY |
| `2026-10-22` | **INTC** | SELL (出場) | kdj | `profit_lock` | `$85.45` | KDJ Death Cross (-8.18%) | BULL_ONLY |
| `2026-10-21` | **INTC** | BUY (進場) | kdj | `baseline` | `$93.01` | 已平倉 (2026-10-22 -8.18%) | BULL_ONLY |
| `2026-10-21` | **INTC** | BUY (進場) | kdj | `no_chase` | `$93.01` | 已平倉 (2026-10-22 -8.18%) | BULL_ONLY |
| `2026-10-21` | **INTC** | BUY (進場) | kdj | `profit_lock` | `$93.01` | 已平倉 (2026-10-22 -8.18%) | BULL_ONLY |
| `2026-10-21` | **INTC** | BUY (進場) | kdj | `oversold_low` | `$93.01` | OPEN (持倉中) | PASS (6/6) |
| `2026-10-19` | **INTC** | BUY (進場) | bollinger | `reversion` | `$92.08` | OPEN (持倉中) | BULL_ONLY |
| `2026-10-19` | **INTC** | BUY (進場) | bollinger | `regime_adaptive` | `$92.08` | OPEN (持倉中) | BULL_ONLY |
| `2026-10-15` | **QCOM** | BUY (進場) | kdj | `baseline` | `$178.49` | 已平倉 (2026-10-30 -7.78%) | BULL_ONLY |
| `2026-10-15` | **QCOM** | BUY (進場) | kdj | `no_chase` | `$178.49` | 已平倉 (2026-10-30 -7.78%) | BULL_ONLY |
| `2026-10-15` | **QCOM** | BUY (進場) | kdj | `trend_filter` | `$178.49` | 已平倉 (2026-10-30 -7.78%) | BULL_ONLY |
| `2026-10-15` | **QCOM** | BUY (進場) | kdj | `profit_lock` | `$178.49` | 已平倉 (2026-10-30 -7.78%) | CONDITIONAL (3/6) |
| `2026-10-15` | **QCOM** | BUY (進場) | kdj | `combo_refined` | `$178.49` | 已平倉 (2026-10-30 -7.78%) | BULL_ONLY |
| `2026-10-14` | **QCOM** | SELL (出場) | kdj | `baseline` | `$172.53` | KDJ Death Cross (-2.55%) | BULL_ONLY |
| `2026-10-14` | **QCOM** | SELL (出場) | kdj | `no_chase` | `$172.53` | KDJ Death Cross (-2.55%) | BULL_ONLY |
| `2026-10-14` | **QCOM** | SELL (出場) | kdj | `trend_filter` | `$172.53` | KDJ Death Cross (-2.55%) | BULL_ONLY |
| `2026-10-14` | **QCOM** | SELL (出場) | kdj | `profit_lock` | `$172.53` | KDJ Death Cross (-2.55%) | CONDITIONAL (3/6) |
| `2026-10-14` | **QCOM** | SELL (出場) | kdj | `combo_refined` | `$172.53` | KDJ Death Cross (-2.55%) | BULL_ONLY |
| `2026-10-13` | **QCOM** | BUY (進場) | kdj | `baseline` | `$176.95` | 已平倉 (2026-10-14 -2.55%) | BULL_ONLY |
| `2026-10-13` | **QCOM** | BUY (進場) | kdj | `no_chase` | `$176.95` | 已平倉 (2026-10-14 -2.55%) | BULL_ONLY |
| `2026-10-13` | **QCOM** | BUY (進場) | kdj | `trend_filter` | `$176.95` | 已平倉 (2026-10-14 -2.55%) | BULL_ONLY |
| `2026-10-13` | **QCOM** | BUY (進場) | kdj | `profit_lock` | `$176.95` | 已平倉 (2026-10-14 -2.55%) | CONDITIONAL (3/6) |
| `2026-10-13` | **QCOM** | BUY (進場) | kdj | `oversold_low` | `$176.95` | OPEN (持倉中) | UNSTABLE |
| `2026-10-13` | **QCOM** | BUY (進場) | kdj | `combo_refined` | `$176.95` | 已平倉 (2026-10-14 -2.55%) | BULL_ONLY |
| `2026-10-13` | **QCOM** | BUY (進場) | kdj | `oversold_trend` | `$176.95` | OPEN (持倉中) | UNSTABLE |
| `2026-10-06` | **INTC** | SELL (出場) | bollinger | `baseline` | `$112.44` | Close < BB_Mid (+3.24%) | BULL_ONLY |
| `2026-10-06` | **INTC** | SELL (出場) | bollinger | `bw_expand` | `$112.44` | Close < BB_Mid (+3.24%) | BULL_ONLY |
| `2026-10-06` | **INTC** | SELL (出場) | bollinger | `profit_lock` | `$112.44` | Breakeven/Mid Stop (+3.24%) | BULL_ONLY |
| `2026-10-06` | **INTC** | SELL (出場) | bollinger | `atr_trail` | `$112.44` | ATR Trail/Mid Stop (+3.24%) | BULL_ONLY |
| `2026-10-06` | **INTC** | SELL (出場) | bollinger | `combo_refined` | `$112.44` | Combo Stop (+3.24%) | CONDITIONAL (3/6) |
| `2026-10-06` | **INTC** | SELL (出場) | rsi | `momentum_breakout` | `$112.44` | Momentum Exit (+7.51%) | CONDITIONAL (3/6) |
| `2026-10-06` | **INTC** | SELL (出場) | rsi | `profit_lock` | `$112.44` | Profit Lock/RSI Exit (+7.51%) | BULL_ONLY |
| `2026-10-05` | **INTC** | SELL (出場) | macd | `raw` | `$116.13` | MACD Death Cross (+26.55%) | ROBUST |
| `2026-10-05` | **INTC** | SELL (出場) | macd | `water_reversal` | `$116.13` | MACD Death Cross (+26.55%) | ROBUST |
| `2026-10-01` | **QCOM** | SELL (出場) | bollinger | `baseline` | `$182.00` | Close < BB_Mid (+6.64%) | BULL_ONLY |
| `2026-10-01` | **QCOM** | SELL (出場) | bollinger | `bw_expand` | `$182.00` | Close < BB_Mid (-0.09%) | ALL_WEATHER |
| `2026-10-01` | **QCOM** | SELL (出場) | bollinger | `profit_lock` | `$182.00` | Breakeven/Mid Stop (+6.64%) | BULL_ONLY |
| `2026-10-01` | **QCOM** | SELL (出場) | bollinger | `atr_trail` | `$182.00` | ATR Trail/Mid Stop (+6.64%) | BULL_ONLY |
| `2026-10-01` | **QCOM** | SELL (出場) | rsi | `momentum_breakout` | `$182.00` | Momentum Exit (+6.64%) | BULL_ONLY |
| `2026-10-01` | **QCOM** | SELL (出場) | rsi | `profit_lock` | `$182.00` | Profit Lock/RSI Exit (+6.64%) | BULL_ONLY |

## 2. 截至 `2026-11-20` 仍處於「持倉中 (OPEN)」之策略變體

| 標的 | 策略 | 變體 | 進場日 | 進場價 ($) | 最新價 ($) | 浮盈虧% | 持有天數 | 穩健評級 / 跨體制穩定度 |
|:---:|:---|:---|:---:|---:|---:|---:|---:|:---|
| **INTC** | macd | `raw` | `2026-11-18` | `$54.70` | `$51.28` | `-6.35%` | 2 天 | ROBUST / ROBUST (跨2體制穩健) |
| **INTC** | macd | `adx_20` | `2026-11-18` | `$54.70` | `$51.28` | `-6.35%` | 2 天 | UNSTABLE / UNSTABLE (不穩定/負期望) |
| **INTC** | macd | `bb_squeeze` | `2026-11-18` | `$54.70` | `$51.28` | `-6.35%` | 2 天 | ROBUST / ROBUST (跨2體制穩健) |
| **INTC** | macd | `water_reversal` | `2026-11-18` | `$54.70` | `$51.28` | `-6.35%` | 2 天 | ROBUST / ROBUST (跨2體制穩健) |
| **INTC** | macd | `adx_water` | `2026-11-18` | `$54.70` | `$51.28` | `-6.35%` | 2 天 | ROBUST / ROBUST (跨2體制穩健) |
| **INTC** | macd | `bb_water` | `2026-11-18` | `$54.70` | `$51.28` | `-6.35%` | 2 天 | PASS (6/6) / ROBUST (跨2體制穩健) |
| **INTC** | macd | `bb_trailing` | `2026-11-18` | `$54.70` | `$51.28` | `-6.35%` | 2 天 | BULL_ONLY / BULL_ONLY (順風依賴/震盪受損) |
| **INTC** | rsi | `extreme_oversold` | `2026-11-03` | `$60.58` | `$51.28` | `-15.45%` | 13 天 | UNSTABLE / UNSTABLE (不穩定/負期望) |
| **INTC** | rsi | `regime_adaptive` | `2026-11-03` | `$60.58` | `$51.28` | `-15.45%` | 13 天 | UNSTABLE / UNSTABLE (不穩定/負期望) |
| **INTC** | rsi | `baseline` | `2026-11-11` | `$62.53` | `$51.28` | `-18.08%` | 7 天 | BULL_ONLY / BULL_ONLY (順風依賴/震盪受損) |
| **INTC** | bollinger | `reversion` | `2026-10-19` | `$92.08` | `$51.28` | `-44.37%` | 24 天 | BULL_ONLY / BULL_ONLY (順風依賴/震盪受損) |
| **INTC** | bollinger | `regime_adaptive` | `2026-10-19` | `$92.08` | `$51.28` | `-44.37%` | 24 天 | BULL_ONLY / BULL_ONLY (順風依賴/震盪受損) |
| **INTC** | kdj | `oversold_low` | `2026-10-21` | `$93.01` | `$51.28` | `-44.92%` | 22 天 | PASS (6/6) / ALL_WEATHER (全天候穩定) |
| **QCOM** | kdj | `oversold_low` | `2026-10-13` | `$176.95` | `$149.94` | `-15.36%` | 28 天 | UNSTABLE / UNSTABLE (不穩定/負期望) |
| **QCOM** | kdj | `oversold_trend` | `2026-10-13` | `$176.95` | `$149.94` | `-15.36%` | 28 天 | UNSTABLE / UNSTABLE (不穩定/負期望) |

## 3. 操作行動與縱深風控矩陣 (Action & Risk Matrix)

| 標的 | 最新價 (`11/20`) | 當前體制 | 技術面讀數 (RSI / KDJ / MACD / ADX) | **建議動作 (Action)** | 建議買入區間 & 部位 (`1.5%` 風險預算) | **四層風控線 (Hard Stop / 保本 / 2.5×ATR 吊燈 / 目標)** | 主要風險提示 (Key Risks) |
|:---|---:|:---|:---|:---:|:---|:---|:---|
| **INTC** | `$51.28` | `INTC_PV023 [恐慌瀑布]` | RSI `28.03` / KDJ `21.22,30.25,3.16` / MACD `-10.394/-10.762` / ADX `42.45` | **HOLD_WITH_STOP / WAIT_CONFIRM** | `$48.72 ~ $51.28` (`143 股`, 約 `$7,333`) | 硬停損 `$40.81` (`-10.47` / `2×ATR`)｜保本啟動 `$55.38` (`+8%`)｜吊燈回落 `-$13.10` (`2.5×ATR`)｜第一目標 `$74.32` (`R/R 2.2x`) | `11/18` `macd:bb_water` (`PASS 6/6`) 已於 `$54.70` 觸發 BUY（目前浮虧 `-6.35%`），但仍處 `Type 5 恐慌瀑布` 且 `ADX 42.45`；須嚴守硬停損 `$40.81`，嚴禁無停損扛單。 |
| **QCOM** | `$149.94` | `QCOM_PV026 [劇烈洗盤]` | RSI `35.1` / KDJ `22.71,39.62,-11.11` / MACD `-4.311/-2.721` / ADX `11.7` | **SELL / STAY_FLAT (空倉觀望)** | `$142.44 ~ $149.94` (`80 股`, 約 `$11,995`) | 硬停損 `$131.26` (`-18.68` / `2×ATR`)｜保本啟動 `$161.94` (`+8%`)｜吊燈回落 `-$23.35` (`2.5×ATR`)｜第一目標 `$191.04` (`R/R 2.2x`) | `11/18` `macd:bb_squeeze` (`PASS 5/6`) 於 `$159.73` 觸發 SELL 死叉出場；目前跌破 20/50/200 均線與布林下軌（`$150.79`），**需防範惡化為 `Type 5 恐慌瀑布`**。 |

## 4. 可執行編號建議卡 (Actionable Suggestions)
- **`[#S1]`** `【明確賣出 / 維持空倉】QCOM`（現價 `$149.94`，已跌破布林下軌 `$150.79` 與 `200SMA` `$170.55`）：**近期剛觸發全面 SELL 訊號**——`2026-11-18` 全部 5 組 MACD 變體（含 `PASS 5/6` 之 `macd:bb_squeeze`）於 `$159.73` 死叉平倉（`-9.64%`，避開後續再跌 `-6.1%`）；`11/17` KDJ 死叉出場、`11/10` 布林回歸已於 `$173.44` 獲利 `+5.37%` 了結。**行動**：目前所有 `PASS` 穩健策略皆為**空倉 (FLAT)**，維持觀望不急接刀；待收盤站回布林下軌或新 `macd:bb_squeeze` 金叉時，再於 `$142.44 ~ $149.94` 建倉 **`80 股`**（約 `$11,995`），硬停損嚴設 **`$131.26`**（單筆最大風險控管於 `$1,500` / 總資產 `1.5%`）。
- **`[#S2]`** `【剛觸發 MACD 買點 / 嚴格硬停損控險】INTC`（現價 `$51.28`，體制 `Type 5 恐慌瀑布`）：**近期多空分歧**——`2026-11-18` 全部 7 組 MACD 變體（含 `PASS 6/6` 之 `macd:bb_water`）於 **`$54.70`** 觸發 **BUY 進場**（目前持倉 2 天浮虧 **`-6.35%`**），但同日 `kdj:baseline/no_chase/profit_lock` 觸發 **SELL 死叉**（`-12.67%`），且 `10/21` 進場之 `kdj:oversold_low` 因原規則無硬停損已浮虧 `-44.92%`。**行動**：若已跟隨 `11/18` `macd:bb_water` 進場者，**嚴守硬停損 `$40.81`（`2×ATR`）或於 `-6%` 警戒線減碼控險**；空倉者等待止跌確認且不破前低時，再以輕倉 **`143 股`**（約 `$7,333`）分批承接，硬停損 **`$40.81`**。

---

## 5. 風險摘要與資金控管紅線 (Portfolio Risk Guardrails)
1. **單筆風險上限**：每筆新單最大停損金額嚴格限制於總資產 `1.5%`（`$1,500 USD`），以 `max(6%, 2×ATR)` 反推股數。
2. **單一標的曝險上限**：單一股票倉位不超過總資產 `25%`（`$25,000`）；兩檔同屬美股半導體 SOX 成熟製程族群，相關性高，合計總曝險建議控制在 `30% ~ 40%` 內。
3. **無硬停損之尾部風險警示**：`INTC` 的 `kdj:oversold_low` 雖於全樣本拿下 6/6 PASS，但因原規則須等超買死叉才出場，在 `2026-10-21` (`$93.01`) 進場遭遇 `Type 5 恐慌瀑布` 後目前單筆浮虧 `-44.92%`；實盤**必須疊加 `@prompts/factors/risk_module.md` 硬停損（`max(6%, 2×ATR)`）**，杜絕單筆斷崖回撤。