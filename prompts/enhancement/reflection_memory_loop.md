# Enhancement Module: 歷史建議自動結算與壓縮記憶反思閉環 (Reflection & Compressed Memory Loop)

> **定位**：借鏡 `TradingAgents` 的事後結算與壓縮記憶機制。當專案在 `reports/INDEX.md` 累積多份時間戳報告後，調用 `@prompts/enhancement/reflection_memory_loop.md` 自動結算歷史建議真實表現，並壓縮成極簡純文字教訓存於 `portfolio.db`，避免重讀整份舊報告撐爆上下文。

---

## 1. Parameters (可調參數)

| 參數 | 預設值 | 說明 |
|:---|:---|:---|
| `EVAL_HORIZONS_DAYS` | `[5, 10, 20]` | 歷史建議發布後追蹤結算之交易日視窗（T+5 / T+10 / T+20） |
| `MAX_MEMORY_SENTENCES` | `4` | 每筆反思教訓的強制最大句數（`2 ~ 4` 句純文字散文，禁止長篇 Markdown） |
| `INJECT_TOP_K` | `5` | 下一輪決策時最多注入最近 K 筆相關反思教訓（防上下文膨脹） |

---

## 2. 資料庫持久化表結構 (`projects/<project_name>/portfolio.db`)

在專案既有 `portfolio.db` 中按需建立 `reflections` 表：

```sql
CREATE TABLE IF NOT EXISTS reflections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    suggestion_id TEXT,
    ticker TEXT NOT NULL,
    suggested_action TEXT,
    entry_ref_price REAL,
    eval_horizon_days INTEGER,
    realized_return_pct REAL,
    alpha_vs_benchmark_pct REAL,
    regime_at_entry TEXT,
    lesson_text TEXT NOT NULL
);
```

---

## 3. 執行閉環流程 (3 Steps)

1. **自動待結算掃描（Stage 1 啟動時）**：
   - 讀取 `projects/<project_name>/reports/*/run_meta.json` 與 `trade_log` 中已達 `T+5 / T+10 / T+20` 卻尚未結算的歷史建議（`#S1, #S2, ...`）。
   - 對照最新行情計算該建議自發布後首個收盤價起算之實際漲跌幅 `realized_return_pct` 與相對基準（如 `^SOX` / `0050.TW`）之超額 `alpha_vs_benchmark_pct`。
2. **極簡壓縮反思（Reflector Compression）**：
   - 將「當時體制＋策略建議＋後續真實走勢＋事件衝擊」壓縮成 **2～4 句純文字教訓**（**禁止條列式或長篇報表**），寫入 `reflections.lesson_text`。
   - *範例*：「2026-10-21 在 INTC 處於 Type 5 恐慌瀑布時，kdj:oversold_low 因未設硬停損導致單筆深套 -44.9%。後續凡進入 Type 5 體制，所有反轉策略皆須強制掛妥 2.5×ATR 硬停損，不可等待超買死叉出場。」
3. **跨期精華注入（Stage 4 決策前）**：
   - 僅撈取該標的（或同原型族群）最近 `INJECT_TOP_K` 筆 `lesson_text` 注入給決策階段，確保歷史教訓直接影響本輪信心度與風控判準。
