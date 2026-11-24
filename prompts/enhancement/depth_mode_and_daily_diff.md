# Enhancement Module: 四檔執行深度路由與前次異動 Diff 摘要 (Depth Mode & Daily Delta Diff)

> **定位**：借鏡 `daily_stock_analysis` 的成本／深度分級編排與 `quantitative_analysis` 的盤後異動比對機制。調用 `@prompts/enhancement/depth_mode_and_daily_diff.md` 時，依需求選擇執行深度以節省時間與算力，並在每份新報告開頭強制輸出「與上一輪的關鍵差異（Delta Diff）」。

---

## 1. 四檔執行深度模式 (`DEPTH_MODE`)

用戶可於對話、`config.json` 或 `studio.html` 中指定 `DEPTH_MODE`（預設 `"standard"`）：

| 模式 (`DEPTH_MODE`) | 執行範圍 | 適用情境 |
|:---|:---|:---|
| **`quick`** | Stage 1（帳本）→ Stage 2（增量行情）→ 最新訊號與停損價檢查 | 每日盤中／收盤 30 秒快速巡檢，不跑回測、不重建大圖表 |
| **`standard`** *(預設)* | `quick` ＋ 事件庫檢查（`events_news.db`）＋ 多空分歧裁決 ＋ 中文行動建議卡 ＋ 追加新時間戳報告 | 日常例行實盤輔助與持倉追蹤 |
| **`full`** | `standard` ＋ 四層風控回測對照 ＋ 更新 `review.db` & `review_viewer.html` | 週度／月度覆盤，或新增候選股／調整策略參數時 |
| **`specialist`** | `full` ＋ 全變體展開 ＋ 6 體制穩定性熱圖 ＋ WFO／滑價／參數高原穩健性閘門 ＋ 跨市場盲測 | 新策略研發、模型改版或季度深度體檢 |

---

## 2. 與上一輪報告之關鍵異動摘要 (Delta Diff Header)

只要 `projects/<PROJECT_NAME>/reports/INDEX.md` 已存在至少 1 份歷史報告，新報告頂部（執行標頭下方）必須自動輸出 **「🔄 本輪 vs 上一輪關鍵異動 (Delta Diff)」**，只高亮真正發生變化的項目：

1. **體制翻轉警報 (Regime Flips)**：
   - 哪檔標的的量波體制（`Type 1 ~ Type 6`）或選型（`STRONG / FLAT / WEAK`）自上一輪發生切換？
2. **新增買賣訊號 (New Buy / Sell Triggers)**：
   - 自上次 `data_end_date` 之後新增觸發的 `BUY` / `SELL` / `RISK_STOP` 訊號清單（若無新訊號則明確標示「無新增訊號」）。
3. **風控線與持倉異動 (Stop & Position Changes)**：
   - 是否有現有持倉跌破硬停損、達標升級保本（`BREAKEVEN`）、啟動吊燈停利（`TRAILING`）或價格變動超過 `±5%`？
4. **新增重大事件 (New Catalysts)**：
   - `events_news.db` 自上次報告後新增之財報預告、SEC 8-K 或異常波動日。

---

## 3. 標準輸出格式範例

```markdown
## 🔄 本輪 vs 上一輪關鍵異動 (Delta Diff: 2026-11-10 → 2026-11-20)
- **價格劇烈變動**：`INTC` `$58.13 → $51.28 (-11.8%)`、`QCOM` `$173.53 → $149.94 (-13.6%)`
- **新增賣出訊號**：`QCOM` 於 `2026-11-18` 觸發 `macd:bb_squeeze` 死叉出場 (`$159.73`)
- **新增買進訊號（含衝突）**：`INTC` 於 `2026-11-18` 觸發 `macd:bb_water` 買進 (`$54.70`)，但同日 `kdj` 死叉出場
- **新增重大事件**：`QCOM` `2026-11-13` 發布 SEC 8-K `[1.01, 8.01]` 重大合約公告；兩檔 `11/20` 皆觸發單日異常暴跌 (`-7.5%~-8.0%`)
```
