# 量化工作流總目錄 (Workflow Orchestration Prompts)

本資料夾存放**「端到端複合工作流 Prompt」**，用於將 `prompts/` 目錄下各自獨立的單一職責規範（資料生成、策略規則、回測執行、風控優化、績效覆盤、研報交付）串聯起來，實現**一條指令自動依序執行多個 Prompts**。

---

## 📁 設計原則

1. **只寫編排與參數覆寫，不重複規則細節**：每個 workflow 明確引用 `@prompts/...` 檔案，並只列出本次任務的**參數覆寫（Overrides）**與**階段驗收標準**。
2. **標準四階段閉環**：
   - `Stage 1: Data`（`@prompts/data_generate.md` 等）
   - `Stage 2: Backtest`（`@prompts/strategy/*.md` + `@prompts/backtest.md`）
   - `Stage 3: Refine & Robustness`（`@prompts/strategy/quantitative_performance_workflow.md` + `@prompts/analyze/robustness_testing_taxonomy.md` + `@prompts/factors/risk_module.md`）
   - `Stage 4: Final Report`（產出交付物至 `trades/` / `reports/`）

---

## 📋 現有工作流清單

| Workflow 檔案 | 串聯 Prompts | 任務目標 |
|:---|:---|:---|
| [`tw51_macd_from_2015.md`](tw51_macd_from_2015.md) | `data_generate` → `macd_strategy` + `backtest` → `quantitative_performance_workflow` + `robustness_testing_taxonomy` + `risk_module` | 對台灣 50 (`tw50`) 成分股自 `2015-01-01` 至今執行 MACD 七大變體回測、診斷優化並產出綜合研報 |
| [`project_trade_assistant.md`](project_trade_assistant.md) | `portfolio_manager` → `data_generate` → `stock_analysis` + 自選 `strategy/*.md` + `risk_module` → `trade_advisor` | **實盤輔助與專案候選池管理**：結合 `projects/<name>/` 的券商真實持倉、買入成本與候選股池，混搭多策略產出加減碼與建倉建議並回寫帳本 |

---

## 🚀 觸發方式

在對話中直接指定工作流檔案即可一次執行全部階段：
```text
run @workflow/tw51_macd_from_2015.md
run @workflow/project_trade_assistant.md for project my_trade
```
