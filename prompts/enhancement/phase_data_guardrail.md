# Enhancement Module: 時相感知與資料品質防幻覺護欄 (Phase & Data Quality Guardrail)

> **定位**：可插拔前置／後置防呆守門員。調用 `@prompts/enhancement/phase_data_guardrail.md` 時，於生成任何交易建議或信心度評分前，強制執行「資料新鮮度檢核」與「市場交易時相檢核」，杜絕過期資料誤判與盤前／盤後時態幻覺。

---

## 1. Parameters (可調參數)

| 參數 | 預設值 | 說明 |
|:---|:---|:---|
| `MAX_STALE_TRADING_DAYS` | `1` | 允許行情截止日落後最新交易日的最大天數（超過即判為 `stale`） |
| `MARKET_PHASE` | `"auto"` | `"auto"`（依當地系統時間與交易所時區自動判定）或手動指定 `premarket` / `intraday` / `closing_auction` / `non_trading` |
| `STALE_CONFIDENCE_CAP` | `"MEDIUM"` | 資料降級或過期時的最高允許信心度上限（`MEDIUM` 或 `LOW`） |

---

## 2. 資料品質狀態追蹤 (Data Provenance Tagging)

在 Stage 2 完成資料載入後，必須對三大核心資料塊標記客觀狀態：
- `quote_status`、`daily_bars_status`、`technical_status` ∈ `{ "fresh", "stale", "fallback", "partial", "missing" }`。
- **降級判定規則**：
  1. 若任何核心資料塊為 `stale` / `fallback` / `partial` / `missing`：
     - **信心度強制封頂**：`confidence_level` 不得為「高（High）」，上限壓縮至 `STALE_CONFIDENCE_CAP`（如 `Medium` 或 `Low`）；
     - **強制揭露**：必須在報告標頭的 `data_limitations` 欄位明確列出缺失或過期項目與實際資料截止日，嚴禁假裝資料為最新。
  2. 若 `daily_bars_status == "missing"`：直接阻斷買進建議，輸出 `DATA_UNAVAILABLE`。

---

## 3. 市場時相防幻覺規則 (Market-Phase Honesty)

1. **保守時相（`premarket` 盤前、`non_trading` 週末／休市、`unknown`）**：
   - **嚴禁捏造盤中走勢**：禁止出現「今日盤中放量拉升」、「今日收盤站穩」等未發生之盤後／盤中復盤話術（應明確改寫為「截至最近收盤日 `YYYY-MM-DD`」）。
   - **禁止無條件立即市價單**：將「立即買進 (`BUY_NOW`)」自動降級為「開盤條件觸發單（如：待開盤後 15 分鐘站穩 `$X` 且不破 `$Y` 再執行）」。
2. **盤中時相（`intraday`、`closing_auction`）**：
   - 著重輸出即時監控條件（`watch_conditions`）、失效價位與下一次檢核時間（`next_check_time`）。
3. **盤後時相（`postmarket`）**：
   - 明確區分「當日正規盤收盤價」與「盤後（AMC）公告／財報事件」，提醒盤後重大公告之真實定價將於次一交易日（T+1）跳空反映。

---

## 4. 標準輸出區塊（嵌入報告標頭）

```json
{
  "market_phase": "non_trading",
  "data_provenance": {
    "daily_bars": "fresh (2026-11-20)",
    "events_news": "fresh (2026-11-22)"
  },
  "confidence_cap": "MEDIUM",
  "data_limitations": "目前為非交易時段，所有動作均為次一交易日條件觸發單。"
}
```
