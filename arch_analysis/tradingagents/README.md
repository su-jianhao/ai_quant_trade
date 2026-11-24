# `TradingAgents` 架构分析与 Prompt 工程化总览

本目录提炼自 [3rd/tradingagents](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/3rd/tradingagents)（Tauric Research 开源的多智能体 LLM 金融交易框架）的源码实现。

---

## 文档索引

| 文件 | 主题 | 提炼来源（源码模块） |
| --- | --- | --- |
| [00_architecture_and_design_ideas.md](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/arhc_analysis/tradingagents/00_architecture_and_design_ideas.md) | LangGraph 多智能体编排架构、并行子图、结构化输出与反思记忆机制 | `graph/setup.py`, `graph/conditional_logic.py`, `agents/analysts/turn.py`, `memory/reflection.py` |
| [01_extracted_original_prompts.md](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/arhc_analysis/tradingagents/01_extracted_original_prompts.md) | **全部 12 个智能体 + 反思器的原始 Prompt 原文与源文件清单** | `agents/analysts/*.py`, `researchers/*.py`, `managers/*.py`, `trader/*.py`, `risk_mgmt/*.py`, `memory/reflection.py` |
| [02_trading_logic_and_strategies.md](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/arhc_analysis/tradingagents/02_trading_logic_and_strategies.md) | 交易决策逻辑、五级评级体系、价格锚定、情绪背离与复盘归因规则 | `market_analyst.py`, `sentiment_analyst.py`, `research_manager.py`, `trader.py`, `portfolio_manager.py`, `reflection.py` |
