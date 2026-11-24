# 系統強化模組 Prompt 總目錄 (`prompts/enhancement/`)

本資料夾存放可自由插拔、單一職責的**系統強化模組 Prompts（Enhancement Modules）**，提煉自 `arch_analysis/`（`daily_stock_analysis`、`quantitative_analysis`、`TradingAgents`）與本專案實證經驗，供 [`workflow/project_trade_assistant.md`](../../workflow/project_trade_assistant.md) 或個別任務按需混搭呼叫。

---

## 📋 強化模組清單

| 模組檔案 | 適用階段 | 核心解決問題 |
|:---|:---|:---|
| [`phase_data_guardrail.md`](phase_data_guardrail.md) | Stage 2 → Stage 4 | **時相與資料品質防幻覺護欄**：偵測資料過期／缺失與盤前／非交易時段，自動封頂信心度並攔截不當「立即買進」話術 |
| [`pre_trade_veto_and_bias_gate.md`](pre_trade_veto_and_bias_gate.md) | Stage 3（進場前） | **不追高乖離基線 ＋ 事件 `RISK_VETO`**：禁止高位追高，並串接 `events_news.db` 對重大利空 8-K（裁員／減損／財報重編）實施一票否決 |
| [`disagreement_debate_resolver.md`](disagreement_debate_resolver.md) | Stage 3 → Stage 4 | **多策略分歧偵測與多空辯論**：當策略出現直接多空衝突（如 MACD BUY vs KDJ SELL）時，強制執行證據辯論與風險降級 |
| [`reflection_memory_loop.md`](reflection_memory_loop.md) | Stage 1 & Stage 4 | **歷史建議自動結算與壓縮記憶反思**：結算過往 `#S1, #S2` 在 T+5/10/20 真實績效，壓縮為 2~4 句教訓存於 `portfolio.db` 供下輪複用 |
| [`single_source_config_protocol.md`](single_source_config_protocol.md) | 全流程 | **單一參數真理源與原子寫入協議**：統一由 `projects/<name>/config.json` 驅動回測、掃描與 UI，消除口徑漂移與檔案損壞 |
| [`depth_mode_and_daily_diff.md`](depth_mode_and_daily_diff.md) | 全流程入口 & Stage 4 | **四檔深度路由與昨日異動 Diff**：提供 `quick / standard / full / specialist` 成本控制，並於報告頂部輸出與上一輪的關鍵翻轉 Diff |

---

## 🚀 混搭呼叫方式

在任何工作流或對話指令中直接指定需要啟用的模組即可，例如：
```text
run @workflow/project_trade_assistant.md for project intc_qcom
with ENHANCEMENTS=["phase_data_guardrail.md", "pre_trade_veto_and_bias_gate.md", "disagreement_debate_resolver.md"]
DEPTH_MODE="standard"
```
