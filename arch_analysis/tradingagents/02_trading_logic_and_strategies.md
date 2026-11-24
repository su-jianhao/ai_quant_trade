# `TradingAgents` 交易逻辑、策略规则与防偏差机制

> 提炼自：`market_analyst.py`、`sentiment_analyst.py`、`research_manager.py`、`trader.py`、`portfolio_manager.py`、`memory/reflection.py`

---

## 1. 技术面指标正交选型与真实性校验 (`Market Analyst`)
- **正交不冗余原则**：从均线（`50 SMA` / `200 SMA` / `10 EMA`）、动量（`MACD` / `MACDS` / `MACDH` / `RSI`）、波动（`Bollinger Bands` / `ATR`）、量价（`VWMA`）五大类中最多挑选 **8 个互补指标**（例如严禁同时选 `rsi` 和 `stochrsi`）。
- **Snapshot 唯一可信源**：在输出最终报告前必须调用 `get_verified_market_snapshot` 校验最新 OHLCV 与指标值；若其他工具返回值冲突，必须标明差异，严禁自行“调和”捏造价格或支撑/阻力位。

---

## 2. 跨源情绪背离与拥挤度策略 (`Sentiment Analyst`)
- **三源分层加权**：
  - Yahoo Finance 新闻（机构/事件驱动，慢信号）；
  - StockTwits（散户标签快信号）；
  - Reddit（社区长文叙事，严禁仅凭标题或臆测互动量下结论）。
- **量化情绪阈值**：
  - StockTwits 多空比 `70/30` = 温和看多；`≥ 90/10` = **过度拥挤与逆向反转风险信号**；`50/50` = 分歧/不确定。
  - **跨源背离信号**：若新闻偏空而散户社区极度看多，须将该“机构/新闻 vs 散户”背离作为独立信号提示。

---

## 3. 五级评级与防“和稀泥”决策铁律 (`Research Manager` & `Portfolio Manager`)
- **五级评级映射**：`Buy`（重仓/加仓）、`Overweight`（逐步增配）、`Hold`（维持不动）、`Underweight`（减仓止盈）、`Sell`（清仓/回避）。
- **反平庸 `Hold` 约束**：辩论天然存在正反冲突，**冲突本身不是选择 `Hold` 的理由**；必须依据论据强度果断站队并按胜出程度调节仓位，仅在充分权衡后证据依然势均力敌或过薄时才允许 `Hold`；且裁决权重须独立于发言顺序（消除首因/近因偏差）。

---

## 4. 交易员价位落地与持仓映射 (`Trader`)
- **五级 → 三态执行映射**：研究总监的 `Overweight` 在交易执行层映射为 `Buy`，`Underweight` 映射为 `Sell`。
- **绝对价格锚定**：`Entry Price` 与 `Stop Loss` **必须输出计价货币的绝对价格数值**（如 `189.5`），严禁输出百分比（如 `15%`）或价格区间，并结合技术面报告中的现价、支撑/阻力与 `ATR` 给出仓位建议。

---

## 5. 持仓窗口结算与防误判复盘 (`Reflector`)
- 结算收益从**分析日之后的第一个收盘价**起算（避免当天未来函数），对比基准计算超额 `Alpha`。
- 若结算窗口（如 `5` 个交易日）短于原定投资逻辑周期，必须在复盘中明确说明“窗口过短不足以证伪长周期逻辑”，防止后续运行把短期波动误读为策略失效。
