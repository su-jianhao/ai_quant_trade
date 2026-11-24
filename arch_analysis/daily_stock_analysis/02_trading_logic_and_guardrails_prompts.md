# 核心量化逻辑与确定性护栏（Prompt 化规则集）

> 本文档将原本由 Python 代码硬编码执行的**趋势量化规则**、**交易基线**、**分歧辩论**、**风控覆盖**和**时相防幻觉护栏**，全部翻译为显式的 Prompt 规则块，以便在纯 Prompt 工程或轻代码 Agent 中直接复用。

---

## 1. 量化技术指标与趋势判定逻辑
> 源码参考：[src/stock_analyzer.py](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/3rd/daily_stock_analysis/src/stock_analyzer.py)（`StockTrendAnalyzer`）

```markdown
## Quantitative Technical Evaluation Rules

Compute and interpret the following indicators before forming a technical opinion:

1. **Moving Average Alignment (`trend_status`)**:
   - `STRONG_BULL` (强势多头): `MA5 > MA10 > MA20` and spacing between MAs is expanding.
   - `BULL` (多头排列): `MA5 > MA10 > MA20`.
   - `WEAK_BULL` (弱势多头): `MA5 > MA10`, but `MA10 < MA20`.
   - `CONSOLIDATION` (盘整): moving averages intertwined.
   - `WEAK_BEAR` / `BEAR` / `STRONG_BEAR`: bearish alignment (`MA5 < MA10 < MA20`).

2. **Bias from MA5 (`bias_ma5 = (Close - MA5) / MA5 * 100%`)**:
   - `< 2%`: Optimal entry zone (最佳买点区间).
   - `2% – 5%`: Acceptable for light position (可小仓介入).
   - `> 5%`: **STRICTLY NO CHASING** (严禁追高) -> Downgrade to Watch (`观望`).

3. **Volume Ratio (`volume_ratio_5d = Volume / MA5_Volume`)**:
   - `<= 0.7`: Shrinking volume (`SHRINK_VOLUME_DOWN` on pullback is preferred; `SHRINK_VOLUME_UP` requires caution).
   - `>= 1.5`: Heavy volume (`HEAVY_VOLUME_UP` confirms breakout; `HEAVY_VOLUME_DOWN` warns of distribution).
   - `0.7 < ratio < 1.5`: Normal volume.

4. **MA Support Check (`MA_SUPPORT_TOLERANCE = 2%`)**:
   - Price pulling back within ±2% of `MA5` or `MA10` on shrinking volume without breaking `MA20` constitutes valid support.

5. **Momentum Indicators**:
   - **MACD (12, 26, 9)**: Distinguish `GOLDEN_CROSS_ZERO` (DIF crosses above DEA above zero axis, strongest), `GOLDEN_CROSS`, `BULLISH`, `CROSSING_UP`, `CROSSING_DOWN`, `BEARISH`, `DEATH_CROSS`.
   - **Wilder RSI (6, 12, 24)**: `> 70` Overbought (超买), `50-70` Strong Buy zone, `40-60` Neutral, `30-40` Weak, `< 30` Oversold (超卖).
```

---

## 2. 默认交易基线（Core Trading Skill Policy）
> 源码参考：[src/agent/skills/defaults.py](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/3rd/daily_stock_analysis/src/agent/skills/defaults.py)（`CORE_TRADING_SKILL_POLICY_ZH` / `_EN`）

```markdown
## 默认技能基线（必须严格遵守）

激活的专项战法可以补充细化视角，但默认风控与交易节奏必须遵守以下 7 条基线：
1. **严进策略（不追高）**：股价偏离 MA5 超过 5% 时坚决不买，直接判定为“观望”。
2. **趋势交易（顺势而为）**：只做 `MA5 > MA10 > MA20` 多头排列，空头排列坚决不碰；均线发散上行优于粘合。
3. **效率优先（筹码结构）**：90% 筹码集中度 < 15% 为筹码集中；获利盘达 70–90% 时警惕获利回吐；现价高于平均成本 5–15% 为健康区间。
4. **买点偏好（回踩支撑）**：最佳买点为缩量回踩 MA5 企稳；次优买点为回踩 MA10 企稳；跌破 MA20 时观望。
5. **风险排查重点**：减持公告、业绩预亏、监管处罚、行业政策利空、大额解禁。
6. **估值关注（PE/PB）**：PE 明显偏高时必须在风险点中明确提示。
7. **强势趋势股放宽**：仅针对强势趋势股可适当放宽乖离率，但必须轻仓追踪并设硬止损。
```

---

## 3. 多智能体分歧检测与证据辩论规则
> 源码参考：[src/agent/disagreement.py](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/3rd/daily_stock_analysis/src/agent/disagreement.py)

```markdown
## Disagreement & Evidence Debate Rules

Before synthesizing the final decision, classify the consensus across upstream agents (`technical`, `intel`, `risk`, `skills`):
1. Bucket valid signals into `bullish` (`strong_buy`, `buy`), `bearish` (`strong_sell`, `sell`), and `neutral` (`hold`).
2. Identify `conflict_type`:
   - Both `bullish` and `bearish` present -> **Direct Bull/Bear Conflict** -> Trigger an `evidence_debate_brief` requiring the Risk/Decision stage to explicitly verify material claims against raw evidence (e.g., `trend_score`, `capital_flow_signal`, `risk_alerts`, `flags`).
   - `risk_override_present == true` -> **Risk-Override Conflict** -> Prioritize risk control over bullish momentum.
   - Any stage degraded/timed out -> **Degraded Consensus** -> Lower conviction and disclose missing evidence.
```

---

## 4. 风控硬覆盖状态机（Risk Override Rules）
> 源码参考：[src/agent/risk_override.py](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/3rd/daily_stock_analysis/src/agent/risk_override.py)

```markdown
## Mandatory Risk Override Rules

Apply deterministic post-risk signal clamping based on the Risk Agent's output:
1. If `veto_buy == true` OR `signal_adjustment == "veto"` OR any risk flag has `severity == "high"`:
   - Trigger `RISK_VETO`.
   - Any `buy` / `strong_buy` candidate signal MUST be downgraded to `hold` (or `sell` if bearish evidence dominates).
2. If `signal_adjustment == "downgrade_two"`:
   - Downgrade 2 steps (`buy` -> `sell`, `hold` -> `sell`).
3. If `signal_adjustment == "downgrade_one"`:
   - Downgrade 1 step (`buy` -> `hold`, `hold` -> `sell`).
4. If the Risk review was required (`full` / `specialist` mode) but failed or returned incomplete JSON:
   - Append mandatory warning: "风控必审尚未完成，暂缓买入 / The mandatory risk review is incomplete. Defer buying." and block `buy`.
```

---

## 5. 时相感知与数据质量防幻觉护栏
> 源码参考：[src/phase_decision_guardrail.py](file:///c:/Users/jiansu/Documents/projects/aitrade/ai_quant_trade/3rd/daily_stock_analysis/src/phase_decision_guardrail.py)

```markdown
## Market-Phase & Data-Quality Guardrails

1. **Conservative Phases (`premarket`, `non_trading`, `unknown`)**:
   - **NEVER** fabricate today's intraday price movement or use post-market recap wording (e.g., "今日收盘后", "盘后复盘", "after today's close").
   - **NEVER** output unconditional immediate execution commands (e.g., "立即买入", "buy now") unless conditioned on market open confirmation; convert to conditional watch triggers.
2. **Intraday Phases (`intraday`, `lunch_break`, `closing_auction`)**:
   - Focus on actionable `immediate_action`, concrete `watch_conditions`, and `next_check_time`.
3. **Core Data Degradation (`quote`, `daily_bars`, `technical` is `stale`, `fallback`, `missing`, `fetch_failed`, `partial`, or `estimated`)**:
   - `confidence_level` MUST NOT be `High` / `高` (cap at `Medium` or `Low`).
   - Explicitly state the missing/degraded data block in `dashboard.phase_decision.data_limitations` and `confidence_reason`.
```
