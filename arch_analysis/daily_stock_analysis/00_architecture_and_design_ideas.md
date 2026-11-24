# `daily_stock_analysis` 核心设计思想与系统架构（Prompt 化视角）

> 本文档提炼自 `3rd/daily_stock_analysis` 的源码实现，将原本分散在 Python 流水线、编排器、数据源与风控模块中的**架构思想与核心机制**转化为可供大模型系统设计参考的规范。

---

## 1. 核心设计理念（Design Ideas）

### 1.1 关注点分离的 Multi-Agent 协同流水线
系统没有用单一巨型 Prompt 完成所有分析，而是将股票研究拆解为职责正交的专家阶段（[src/agent/orchestrator.py](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/3rd/daily_stock_analysis/src/agent/orchestrator.py)）：
- **TechnicalAgent（技术面）**：只看量价、均线、乖离率、MACD/RSI、筹码分布与形态。
- **IntelAgent（情报与情绪面）**：只看新闻公告、业绩预告、监管风险与 A 股主力资金流向。
- **RiskAgent（独立风控官）**：专门“挑刺”——核查减持、解禁、估值极端值、监管处罚与技术破位，拥有降级甚至一票否决权（`veto_buy`）。
- **Skill / Strategy Agents（战法技能专家）**：按市场状态（`market_regimes`）激活对应的 YAML 战法（如多头趋势、缩量回踩、龙头战法、缠论等），输出独立的策略观点。
- **DecisionAgent（总决策官）**：**禁止调用外部工具**（`tool_names = []`），仅基于上游各 Agent 经过验证的上下文、分歧摘要与风控约束进行综合裁决。

### 1.2 四档成本/深度可调编排模式
编排器（`AgentOrchestrator`）通过 `VALID_MODES` 控制调用链长度与 LLM 成本：
1. **`quick`**：`Technical → Decision`（最快，约 2 次 LLM 调用）。
2. **`standard`（默认）**：`Technical → Intel → Decision`。
3. **`full`**：`Technical → Intel → Risk → Decision`。
4. **`specialist`**：`Technical → Intel → Risk → 策略技能路由/评估 → Decision`。

### 1.3 确定性护栏兜底 LLM（Deterministic Guardrails over LLM）
系统不完全信任 LLM 的自由发挥，而是在 LLM 前后包裹了多层确定性 Python 逻辑：
- **量化先行**：在 [src/stock_analyzer.py](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/3rd/daily_stock_analysis/src/stock_analyzer.py) 先算好均线、乖离率、量比、MACD/RSI 等硬指标，再喂给 LLM。
- **分歧触发辩论（Disagreement Debate）**：[src/agent/disagreement.py](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/3rd/daily_stock_analysis/src/agent/disagreement.py) 统计多空观点冲突类型（`conflict_type`），必要时生成 `evidence_debate_brief` 要求 `RiskAgent` 核实关键证据。
- **风控硬覆盖（Risk Override）**：[src/agent/risk_override.py](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/3rd/daily_stock_analysis/src/agent/risk_override.py) 定义了严格的状态机——一旦触发 `RISK_VETO` 或 `RISK_DOWNGRADE`，无论其他 Agent 多看好，最终决策必须被强制降级或封顶为 `hold` / `sell`。
- **时相与数据质量护栏（Phase & Data Quality Guardrail）**：[src/phase_decision_guardrail.py](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/3rd/daily_stock_analysis/src/phase_decision_guardrail.py) 根据当前市场阶段（盘前、盘中、午休、收盘竞价、非交易时段）以及行情数据是否缺失/过期/降级，自动限制 `confidence_level`（禁止高置信度）并拦截诸如“盘前却输出盘后复盘话术”的幻觉。

### 1.4 多源数据高可用与低并发容错
- **策略模式 + 熔断降级**：[data_provider/base.py](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/3rd/daily_stock_analysis/data_provider/base.py) 中的 `DataFetcherManager` 统一标准化多市场股票代码（A 股/港股/美股/日/韩/台）与 OHLCV 字段，内置限流、指数退避重试、熔断器（`CircuitBreaker`）和自动切源。
- **单股隔离与取消令牌**：[src/core/pipeline.py](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/3rd/daily_stock_analysis/src/core/pipeline.py) 通过 `_DaemonThreadStockExecutor` 与 `StockCancellationToken` 控制并发，单只股票抓取或分析超时不会拖垮整批任务。

---

## 2. 将系统架构转化为顶层协调器 Prompt（Meta-Orchestrator Prompt）

如果你想用纯 Prompt（如在单个大模型或 Agent 框架中）复现这套架构，可使用以下顶层协调指令：

```markdown
# Role: Quantitative Equity Research Orchestrator

You are the coordinator of a multi-stage equity research pipeline covering A-shares, HK, US, JP, KR, and TW stocks.
For any stock analysis request, you MUST execute the pipeline in strict stage isolation according to the selected depth mode (`quick` | `standard` | `full` | `specialist`), passing structured JSON state between stages without skipping risk or data-quality guardrails.

## Execution Modes
- `quick`: Technical -> Decision
- `standard`: Technical -> Intel -> Decision
- `full`: Technical -> Intel -> Risk -> Decision
- `specialist`: Technical -> Intel -> Risk -> Active Strategy Skills -> Decision

## Shared Context Rules
1. **Symbol Normalization**: Normalize stock codes before data lookup (6-digit A-share, `HK00700` for HK, ticker for US, `.T`/`.KS`/`.TW`/`.TWO` for JP/KR/TW).
2. **Data Provenance Tracking**: Always record whether `quote`, `daily_bars`, and `technical` data are `fresh`, `stale`, `fallback`, `partial`, `estimated`, or `missing`.
3. **Evidence Isolation**: Downstream agents must cite upstream evidence rather than inventing unverified facts.
4. **Risk Supremacy**: Any `high`-severity risk flag or `veto_buy: true` from the Risk stage overrides bullish signals from Technical or Strategy stages.
5. **Phase Honesty**: Respect the current market phase (`premarket`, `intraday`, `lunch_break`, `closing_auction`, `non_trading`). Never fabricate intraday price action during `premarket` or `non_trading` phases.
```
