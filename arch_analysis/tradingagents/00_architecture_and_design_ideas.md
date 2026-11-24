# `TradingAgents` 系统架构与核心设计思想

> 提炼自：`tradingagents/graph/setup.py`、`tradingagents/graph/conditional_logic.py`、`tradingagents/agents/analysts/turn.py`、`tradingagents/memory/reflection.py`、`tradingagents/agents/structured.py`

---

## 1. 整体拓扑：四阶段 LangGraph 多智能体流水线

系统基于 **LangGraph (`StateGraph`)** 模拟真实投研交易机构的组织分工，分为四个顺序阶段：

```
[START] ──▶ (并行执行) Market / Sentiment / News / Fundamentals Analysts + Memory Settlement
               │
               ▼ (全部报告汇总后)
        [Bull Researcher ◀──▶ Bear Researcher]  (多空结构化辩论，max_debate_rounds 轮)
               │
               ▼
        [Research Manager]  ──▶ 输出五级评级与投资计划 (investment_plan)
               │
               ▼
        [Trader]            ──▶ 结合技术面价位锚定输出具体交易提案 (trader_investment_plan)
               │
               ▼
        [Aggressive ──▶ Conservative ──▶ Neutral] (三方风控辩论，max_risk_discuss_rounds 轮)
               │
               ▼
        [Portfolio Manager] ──▶ 结合历史反思教训 (past_context) 做出最终裁决 (final_rating) ──▶ [END]
```

---

## 2. 核心工程与架构设计思想

### 2.1 分析师并行隔离与防死循环子图 (`_analyst_graph`)
- **私有消息历史隔离**（`graph/setup.py` 第 53–90 行）：每个分析师被编译为一个独立的 `StateGraph(AgentState, output_schema=output)` 子图，仅向主图返回自己的 `<key>_report` 字符串。这样多个分析师并行执行时**互不覆盖状态键**，且工具调用轨迹不会污染其他分析师的上下文。
- **工具轮次熔断 (`max_tool_rounds` + `WRAP_UP`)**（`turn.py` 第 7–27 行）：
  - 若模型调用工具达到 `max_tool_rounds` 上限，图路由器强制跳转至 `wrap_up` 节点。
  - `wrap_up` 会**解除工具绑定**（不传 `bind_tools`），并将历史 `AIMessage.tool_calls` 与 `ToolMessage` 转为纯文本，强制要求模型立即写出最终报告并说明缺失数据，彻底避免模型陷入工具调用死循环而触发 LangGraph 递归限制。

### 2.2 双层大模型算力分级 (`quick_thinking_llm` vs `deep_thinking_llm`)
- `GraphSetup` 将模型拆分为两档（`graph/setup.py` 第 125–141 行）：
  - **`quick_thinking_llm`**：用于高频/执行型节点（4 位分析师、多空研究员、交易员、3 位风控辩手、反思器）。
  - **`deep_thinking_llm`**：用于最终拍板的管理层节点（`Research Manager`、`Portfolio Manager`）。

### 2.3 结构化输出优先 + 纯文本降级 (`bind_structured` / `invoke_structured_or_freetext`)
- `Sentiment Analyst`、`Research Manager`、`Trader`、`Portfolio Manager` 均绑定 Pydantic Schema（`SentimentReport`、`ResearchPlan`、`TraderProposal`、`PortfolioDecision`）。
- 支持 Structured Output 的模型直接返回强类型对象（例如 `PortfolioDecision.rating` 直接作为 `final_rating`，避免后续从正文中正则误读）；不支持的提供商自动降级为自由文本生成并解析评级。

### 2.4 辩论路由防崩溃守卫 (`DEBATE_PATH_MAP` / `RISK_ANALYSIS_PATH_MAP`)
- `ConditionalLogic` 控制多空辩论（`2 * max_debate_rounds` 次后交由 `Research Manager`）与三方风控辩论（`3 * max_risk_discuss_rounds` 次后交由 `Portfolio Manager`）。
- 所有条件边均显式声明全量目标映射表，防止因提示词或标签漂移导致 LangGraph 运行中找不到边而崩溃。

### 2.5 事后结算与压缩记忆反思循环 (`Reflector` + `memory`)
- 在分析师并行分析的同时，记忆节点对历史待结算决策进行收益结算（计算分析日后首个收盘价起 $N$ 个交易日的原始收益与相对基准的超额 Alpha），生成 `past_context`。
- `Reflector` 强制将复盘总结压缩为 **2–4 句纯文本散文**（禁止 Markdown/列表），仅注入给最终拍板的 `Portfolio Manager`，在不撑爆上下文窗口的前提下实现跨周期经验复用。

### 2.6 前置预取防幻觉与时点一致性 (Point-in-Time)
- **Sentiment Analyst** 不暴露外部工具给模型（`NO_EXTERNAL_TOOLS`），而是在节点进入时由 Python 代码预先拉取并按时间窗口裁剪 Yahoo News、StockTwits 与 Reddit（可选 Jev 过滤），以 `<start_of_*>` 标签注入 Prompt，杜绝模型编造帖子或泄露未来情绪。
- **Market Analyst** 强制在最终报告前调用 `get_verified_market_snapshot` 作为精确 OHLCV 与指标数值的唯一可信源（Source of Truth）。
