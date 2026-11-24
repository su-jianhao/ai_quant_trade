# Enhancement Module: 進場前不追高乖離基線與事件一票否決守門員 (Pre-Trade Bias Gate & Risk Veto)

> **定位**：可插拔進場前確定性審核層（銜接 `@prompts/factors/risk_module.md` 與 `@prompts/data/event_dates.md`）。調用 `@prompts/enhancement/pre_trade_veto_and_bias_gate.md` 時，所有候選 `BUY` 訊號在進入最終建議前，必須通過「乖離率不追高檢查」與「重大利空事件 `RISK_VETO` 狀態機」。

---

## 1. Parameters (可調參數 — 禁止寫死，依標的波動屬性彈性調整)

| 參數 | 預設值 | 說明 |
|:---|:---|:---|
| `MAX_BIAS_MA5_PCT` | `5.0` | 短線 `MA5` 乖離率追高警戒上限（`%`；高波趨勢股可放寬至 `7.0%~8.0%` 並縮減倉位） |
| `MAX_BIAS_MA20_PCT` | `15.0` | 月線 `MA20` 乖離率上限（`%`） |
| `EVENT_LOOKBACK_DAYS` | `5` | 往回掃描 `events_news.db` 高危利空公告之天數 |
| `PRE_EARNINGS_BLOCK_DAYS` | `0` | 財報前 N 天是否禁止新開倉（預設 `0` 僅警示，保守模式可設 `2~3`） |
| `VETO_SEC_8K_ITEMS` | `["2.05", "2.06", "3.01", "4.02"]` | 觸發高危風控審查之 SEC 8-K 項目（重組裁員、重大減損、退市警示、財報重編） |

---

## 2. 嚴進基線：不追高乖離檢查 (No-Chasing Bias Gate)

計算 $\text{BIAS}_{5} = \frac{C_t - \text{SMA}_5}{\text{SMA}_5} \times 100\%$ 與 $\text{BIAS}_{20} = \frac{C_t - \text{SMA}_{20}}{\text{SMA}_{20}} \times 100\%$：
1. **最佳回踩買點**：$|\text{BIAS}_5| \le 2\%$ 且回測 `MA5 / MA10` 縮量不破 `MA20` → **`PASS`（正常倉位）**。
2. **輕度偏離區**：$2\% < \text{BIAS}_5 \le \text{MAX\_BIAS\_MA5\_PCT}$ → **`SCALE_DOWN`（輕倉介入或分批掛單）**。
3. **極端追高區**：$\text{BIAS}_5 > \text{MAX\_BIAS\_MA5\_PCT}$ 或 $\text{BIAS}_{20} > \text{MAX\_BIAS\_MA20\_PCT}$ → **強制降級為「觀望等回踩 (`WAIT_DIP`)」**，嚴禁於短線急拉末端市價追高。

---

## 3. 事件驅動一票否決狀態機 (`RISK_VETO` / `RISK_DOWNGRADE`)

掃描專案對應之獨立事件庫（如 `data/sox_mag7_price_vol_types/events_news.db`）與基本面警報：
1. **觸發 `RISK_VETO`（一票否決）條件（符合任一項）**：
   - 近 `EVENT_LOOKBACK_DAYS` 日內出現 `VETO_SEC_8K_ITEMS`（如財報重編 `4.02`、重大資產減損 `2.06`、大規模裁員重組 `2.05`）且次日跳空重挫 $\le -5\%$；
   - 台股出現全額交割、處置分盤、大股東／內部人巨額申報轉讓或監管重罰；
   - 必要風控審核流程未完成或失敗。
   - **強制動作**：無論技術面或策略多看好，任何 `BUY` 訊號一律**封頂壓降為 `觀望 (HOLD)` 或 `賣出避險 (SELL)`**，並附帶明確否決原因。
2. **觸發 `RISK_DOWNGRADE`（降級一檔）條件**：
   - 財報發布前 $\le 3$ 天（且未設定完全禁買）；
   - 出現中性高管異動（如 `5.02` CFO/CEO 異動）尚未確認市場定價方向；
   - **強制動作**：倉位上限打折（如 `× 0.5`）並強制掛妥初始硬停損，不得滿倉賭事件。

---

## 4. 標準輸出格式

每檔候選標的於報告中須附上審核徽章：
- `✅ GATE_PASS`｜`⚠️ BIAS_WAIT_DIP (BIAS5=+6.8%)`｜`🛑 RISK_VETO (SEC 8-K 4.02)`
