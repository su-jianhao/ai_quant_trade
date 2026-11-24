# 量化系统实现逆向与 Prompt 工程化总览 (`arhc_analysis`)

本目录将 [quantitative_analysis](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/3rd/3rd/quantitative_analysis) 的核心源码实现提炼为**可复用、结构化的 Prompt 规范**，覆盖智能体（Agents）、选股与择时策略（Strategies）、风控与回测逻辑（Logic）以及架构设计思想（Ideas）。

---

## 文档索引

| 文件 | 主题 | 提炼来源（源码模块） |
| --- | --- | --- |
| [extracted_original_prompts.md](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/arhc_analysis/quantitative_analysis/extracted_original_prompts.md) | **原始源码内嵌 Prompt 原文与源文件清单** | `app/services/ai/prompts.py`, `app/services/llm_service.py` |
| [agent_quant_workbench.md](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/arhc_analysis/quantitative_analysis/agent_quant_workbench.md) | AI 智能工作台与 Text2SQL 智能体 Prompt | `app/services/ai/prompts.py`, `tools.py`, `llm_service.py` |
| [strategy_chip_and_rotation.md](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/arhc_analysis/quantitative_analysis/strategy_chip_and_rotation.md) | 筹码三类信号、指数 Regime 与行业轮动策略 Prompt | `chip_signal_service.py`, `signal_defs.py`, `market_regime_service.py`, `industry_rotation_service.py` |
| [logic_factor_research_and_backtest.md](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/arhc_analysis/quantitative_analysis/logic_factor_research_and_backtest.md) | 因子体检、组合优化与 T+1 模拟盘执行逻辑 Prompt | `factor_screening.py`, `portfolio_optimizer.py`, `paper_trading_service.py` |
| [ideas_architecture_and_automation.md](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/arhc_analysis/quantitative_analysis/ideas_architecture_and_automation.md) | 零中间件架构思想与 18:30 盘后自动化编排 Prompt | `app/__init__.py`, `daily_alert_service.py`, `data_jobs/` |
