# 15 大内置交易策略技能（Strategy Skills）Prompt 目录

> 本文档汇总 `3rd/daily_stock_analysis/strategies/*.yaml` 中的全部 15 个内置策略技能，保留其适用市场状态（`market_regimes`）、默认优先级、核心规则约束与工具依赖，并提供统一的 Strategy Skill Prompt 注入模板。

---

## 1. 策略技能总览表

| 策略 ID | 中文名称 | 分类 (`category`) | 适用市场状态 (`market_regimes`) | 默认优先级 | 核心依赖工具 |
| :--- | :--- | :--- | :--- | :---: | :--- |
| `bull_trend` | 默认多头趋势（默认启用） | `trend` | `trending_up` | 10 | `get_daily_history`, `analyze_trend` |
| `ma_golden_cross` | 均线金叉 | `trend` | `trending_up` | 20 | `get_daily_history`, `analyze_trend` |
| `volume_breakout` | 放量突破 | `trend` | `trending_up` | 30 | `get_daily_history`, `analyze_trend`, `get_realtime_quote` |
| `hot_theme` | 热点题材 | `framework` | `sector_hot` | 35 | `get_sector_rankings`, `search_stock_news`, `get_realtime_quote`, `analyze_trend` |
| `shrink_pullback` | 缩量回踩 | `trend` | `trending_down`, `sideways` | 40 | `get_daily_history`, `analyze_trend`, `get_realtime_quote` |
| `event_driven` | 事件驱动 | `framework` | `sector_hot`, `volatile` | 45 | `search_stock_news`, `get_realtime_quote`, `analyze_trend` |
| `box_oscillation` | 箱体震荡 | `framework` | `sideways` | 50 | `get_daily_history`, `analyze_trend`, `get_realtime_quote` |
| `growth_quality` | 成长质量 | `framework` | `trending_up` | 55 | `get_stock_info`, `get_realtime_quote`, `search_stock_news`, `analyze_trend` |
| `bottom_volume` | 底部放量 | `reversal` | `trending_down` | 60 | `get_daily_history`, `analyze_trend` |
| `expectation_repricing` | 预期重估 | `framework` | `volatile`, `sector_hot` | 65 | `search_stock_news`, `get_stock_info`, `get_realtime_quote`, `analyze_trend` |
| `chan_theory` | 缠论结构 | `framework` | `volatile` | 70 | `get_daily_history`, `analyze_trend`, `get_realtime_quote` |
| `wave_theory` | 波浪理论 | `framework` | `volatile` | 80 | `get_daily_history`, `analyze_trend`, `get_realtime_quote` |
| `dragon_head` | 龙头战法 | `trend` | `sector_hot` | 90 | `get_realtime_quote`, `get_sector_rankings`, `search_stock_news` |
| `emotion_cycle` | 情绪周期 | `framework` | `sector_hot` | 100 | `get_daily_history`, `get_realtime_quote`, `analyze_trend`, `search_stock_news` |
| `one_yang_three_yin` | 一阳三阴 | `pattern` | *通用* | 110 | `get_daily_history`, `analyze_trend` |

---

## 2. 分类策略 Prompt 核心要点

### A. 趋势与量价类（Trend & Pattern）
- **`bull_trend`（默认多头趋势）**：要求 `MA5 >= MA10 >= MA20` 且 `MA20` 向上；优先“回踩不破”而非高位追涨；突破日需放量确认；给出止损参考（如 MA20 下方）。
- **`ma_golden_cross`（均线金叉）**：识别 MA5 上穿 MA10（或 MA10 上穿 MA20）且伴随成交量放大的趋势启动/延续信号。
- **`volume_breakout`（放量突破）**：股价接近前期阻力位时，放量（通常 > 2 倍均量）有效突破阻力位。
- **`shrink_pullback`（缩量回踩）**：上升趋势中回调至 MA5/MA10 支撑位且成交量显著萎缩，随后企稳反弹的低吸买点。
- **`bottom_volume`（底部放量）**：长期下跌后股价企稳并出现底部放量异动，评估资金吸筹与趋势反转信号。
- **`one_yang_three_yin`（一阳三阴）**：识别“大阳线后紧跟三根小阴线缩量整理”的 K 线形态，寻找整理结束后的再次向上突破点。

### B. 题材、情绪与龙头类（Sector Hot & Event）
- **`hot_theme`（热点题材）**：结合板块涨幅榜与新闻催化，判断题材持续性、板块轮动节奏与个股梯队地位。
- **`dragon_head`（龙头战法）**：在热点板块轮动中识别领涨龙头（辨识度、连板/涨幅领先、资金承接力），仅在板块效应强时适用。
- **`emotion_cycle`（情绪周期）**：结合市场情绪、换手率与量价结构，识别情绪冰点（潜在买点）与情绪高潮（警惕分歧回落）。
- **`event_driven`（事件驱动）**：围绕业绩公告、政策利好、并购重组、行业突发事件评估落地力度与预期兑现风险。

### C. 基本面与估值框架类（Fundamental & Regime）
- **`growth_quality`（成长质量）**：结合营收/利润增速、ROE、现金流与行业空间，识别高景气优质成长股及业绩失速风险。
- **`expectation_repricing`（预期重估）**：分析业绩预期、政策预期或估值体系重构变化，捕捉“预期差修复”或“预期证伪”的关键节点。

### D. 结构与周期理论类（Technical Frameworks）
- **`box_oscillation`（箱体震荡）**：识别横盘震荡箱体的上下沿支撑与阻力，在箱底低吸、箱顶高抛。
- **`chan_theory`（缠论）**：基于笔、线段、中枢结构分析，判断趋势背驰、一/二/三类买卖点与区间套信号。
- **`wave_theory`（波浪理论）**：基于艾略特 5 浪驱动与 3 浪调整结构，判断当前所处主升浪/调整浪位置及潜在目标位与仓位管理。

---

## 3. 通用 Strategy Skill Prompt 注入模板

在构建单智能体或 Multi-Agent 系统时，可按以下模板将任意 YAML 策略动态注入到 `TechnicalAgent` 或 `DecisionAgent` 的 System Prompt 中：

```markdown
## Active Trading Strategy Skill: {display_name} (`{name}`)
- **Category**: {category}
- **Target Market Regimes**: {market_regimes}
- **Required Evidence / Tools**: {required_tools}

### Strategy Instructions
{instructions_from_yaml}

### Strategy Output Contract
When evaluating under this strategy, you MUST output:
1. Whether the current stock structure matches this strategy (`match_score`: 0-100).
2. Explicit trigger conditions for entry, hold, or exit.
3. Concrete stop-loss reference price.
4. Sentiment score adjustment (`+` / `-` points) grounded in observed price/volume/intel facts.
```
