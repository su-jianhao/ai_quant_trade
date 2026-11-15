# 量化回测与绩效评估因子百科全书 (Quantitative Backtesting & Performance Factors Knowledge Base)

本手册由量化投资与对冲基金策略团队编写，详细解析系统中 `@backtest` 模块所涉及的**量化回测因子、QuantStats 核心绩效与风险调整指标、交易行为度量学**，以及实战回测中的**关键风控陷阱与工程准则**。

---

## 1. 收益与超额回报因子 (Return & Alpha Metrics)

### ① 策略累计复合收益率 (Cumulative Total Return)
- **数学定义**：
  回测期间每日收益率的几何复利累乘：
  $$R_{\text{total}} = \prod_{t=1}^{T} (1 + r_t) - 1 = \frac{\text{Equity}_T - \text{Equity}_0}{\text{Equity}_0}$$
  其中 $r_t = \frac{\text{Equity}_t - \text{Equity}_{t-1}}{\text{Equity}_{t-1}}$ 为第 $t$ 个交易日的策略净值涨跌幅。
- **量化研判**：
  衡量策略在整个考察区间内的绝对财富增殖能力。需结合测试区间的年限折算为**年化复合增长率（CAGR）**进行跨周期横向比较：
  $$\text{CAGR} = (1 + R_{\text{total}})^{\frac{252}{T}} - 1$$

---

### ② 超额收益率 (Alpha / Active Return vs Benchmark)
- **数学定义**：
  $$\text{Alpha} = R_{\text{strategy}} - R_{\text{benchmark}}$$
- **基准标的 (Benchmark)**：
  在单标的（如 QCOM / INTC / NVDA）回测中，基准设定为**“买入持有策略（Buy & Hold）”**；在多资产回测中，基准通常选用标普 500（SPY）或纳斯达克 100（QQQ）。
- **实战意义**：
  - **$\text{Alpha} > 0$**：策略通过主动择时（如金叉建仓、死叉空仓避险）战胜了被动死扛持股，证明择时动量系统具备超额价值；
  - **$\text{Alpha} < 0$**：策略频繁震荡磨损，未能跑赢被动买入持有。

---

## 2. 风险调整后收益因子 (Risk-Adjusted Performance Factors)

单纯看收益率是业余交易者最常犯的错误。顶级对冲基金最看重的是**“每承担一单位风险，能够换取多少单位的回报”**。

### ① 夏普比率 (Sharpe Ratio) —— 全局波动性价比
- **数学定义**：
  $$\text{Sharpe} = \frac{\mathbb{E}[R_p - R_f]}{\sigma_p} \times \sqrt{252}$$
  其中 $R_p$ 为策略日收益序列，$R_f$ 为无风险利率（通常取美国国债基准收益率或设为 0），$\sigma_p$ 为日收益率的标准差（年化因子为 $\sqrt{252}$）。
- **机构评级阈值**：
  - **`< 0`**：收益不及无风险利率，或长期亏损；
  - **`0 ~ 1.0`**：表现尚可，但在市场大波动时仍有较大回撤风险；
  - **`1.0 ~ 1.5`**：**合格的对冲基金策略**，风险收益比良好；
  - **`1.5 ~ 2.0`**：卓越的主动量化策略，收益曲线平滑稳健；
  - **`> 2.0`**：顶级自营高频或中短线动量系统（需警惕过拟合）。

---

### ② 索提诺比率 (Sortino Ratio) —— 剔除向上波动的“真实下行风控之王”
- **夏普比率的致命缺陷**：
  夏普比率将**“向上暴涨的波动”**与**“向下暴跌的波动”**一视同仁地视为风险加以惩罚。但对于投资者而言，连续涨停的向上波动是收益而非痛苦。
- **数学定义**：
  索提诺比率仅惩罚**下行半方差（Downside Deviation）**：
  $$\text{Sortino} = \frac{\mathbb{E}[R_p - R_f]}{\sigma_{\text{down}}} \times \sqrt{252}$$
  $$\sigma_{\text{down}} = \sqrt{\frac{1}{T}\sum_{t=1}^{T} \min(0, r_t - R_f)^2}$$
- **研判法则**：
  若一个策略的 **Sortino 远高于 Sharpe**（如 QCOM 回测中 Sharpe=0.69, Sortino=1.05），说明该策略的波动主要来自于向上脉冲捕获主升浪，而下行亏损得到了极好的止损控制，属于**“截断亏损、让利润奔跑”**的优质策略形态。

---

### ③ 卡玛比率 (Calmar Ratio)
- **数学定义**：
  $$\text{Calmar} = \frac{\text{CAGR}}{|\text{Max Drawdown}|}$$
- **含义**：
  年化收益率与历史最大回撤的比值。
  - **$\text{Calmar} > 2.0$**：极佳。意味着每年能够赚回最大回撤两倍以上的收益，投资者持有体感极度舒适。

---

## 3. 风险、回撤与极端下行因子 (Risk & Drawdown Factors)

### ① 最大回撤 (Maximum Drawdown / MDD)
- **数学定义**：
  净值从任意历史峰值（Peak）下坠至谷底（Trough）的最大百分比跌幅：
  $$\text{MDD} = \max_{t \in [0, T]} \left( \frac{\max_{s \le t} \text{Equity}_s - \text{Equity}_t}{\max_{s \le t} \text{Equity}_s} \right)$$
- **水下曲线 (Underwater Drawdown Curve)**：
  将每日的当前回撤幅度连成的负值时序面积图。
  - **水下停留时间 (Duration)**：衡量策略从峰值跌落到再次突破前高、回到“水面”所需的交易日数。
  - **止损价值**：例如 2026 年 QCOM 从 $214 暴跌至 $150 期间，买入持有基准最大回撤高达 -38.45%，而 MACD 策略死叉空仓观望，最大回撤显著收敛至 -25.80%，保住了 3-5 月积累的大部分本金利润。

---

### ② 年化波动率 (Annualized Volatility)
- **数学定义**：
  $$\sigma_{\text{annual}} = \text{std}(r_t) \times \sqrt{252}$$
- **研判**：
  衡量净值曲线上蹿下跳的剧烈程度。波动率过高的策略极难让实盘资金放大杠杆或承受重仓。

---

## 4. 交易行为特征与微观执行因子 (Trading Behavior & Microstructure)

### ① 交易日胜率 vs 单笔交易胜率 (Win Rate)
- **日度胜率 (Daily Win Rate)**：
  $$\text{Win Rate}_{\text{daily}} = \frac{\text{净值上涨交易日数}}{\text{总交易日数}}$$
- **单笔胜率 (Trade Win Rate)**：
  $$\text{Win Rate}_{\text{trade}} = \frac{\text{盈利平仓笔数}}{\text{总平仓笔数}}$$
- **认知误区**：
  趋势跟踪策略（如 MACD、双均线、海龟交易法则）的**单笔胜率通常只有 40% ~ 50%**，但依然能获取数倍暴利。其秘诀在于**高盈亏比（Profit Factor）**：
  $$\text{Profit Factor} = \frac{\sum \text{所有盈利订单收益}}{\sum |\text{所有亏损订单亏损}|}$$
  - 平常 5 次假突破小幅止损（每次 -3% ~ -5%）；
  - 1 次真实主升浪波段死拿到底（单笔 +50% ~ +80%）；
  - 期望值依旧是极大的正数。

---

### ② 凯利判据 (Kelly Criterion)
- **数学定义**：
  在具备统计正期望值的系统下，单次下注的最佳资金比例：
  $$f^* = \frac{p \cdot b - (1 - p)}{b} = p - \frac{1 - p}{b}$$
  其中 $p$ 为胜率，$b$ 为平均盈亏比（平均盈利金额 / 平均亏损金额）。
- **实战法则**：
  实盘严格使用**“半凯利（Half-Kelly）”**或四分之一凯利（$\frac{1}{4} f^*$）进行仓位管理，防止连续黑天鹅极端行情导致账户崩解。

---

### ③ 交易摩擦成本建模 (Friction: Slippage & Commission)
- **滑点 (Slippage)**：
  因市场买卖价差（Bid-Ask Spread）、冲击成本（Market Impact）或跳空，实际成交价劣于信号触发价。
  - 买入执行价：$P_{\text{buy}} = P_{\text{close}} \times (1 + \text{Slippage})$；
  - 卖出执行价：$P_{\text{sell}} = P_{\text{close}} \times (1 - \text{Slippage})$；
  - 系统默认设定单边滑点为 **`0.05%` (5 bps)**。
- **佣金手续费 (Commission)**：
  经纪商与交易所税费，系统默认设定为 **`0.03%` (3 bps)**。

---

## 5. 核心量化避坑法则 (Quantitative Hygiene & Anti-Patterns)

### ① 严禁截断区间直接算指标 —— “指标预热充分性原则 (Warm-Up Continuity)”
- **严重错误做法**：
  如果要从 `2026-01-01` 开始回测，先截取 `2026-01-01` 至今的数据，再在上面计算 200 SMA 或 MACD。
  - **后果**：前 26 天没有 EMA(26)，前 200 天没有 200 SMA，指标出现大面积空值（NaN）或者前几十天的均线严重偏离真实值（冷启动失真）。
- **标准工程规范**：
  必须拉取包含**历史前置预热期（至少向前 252~500 个交易日）**的完整时序，先计算全量技术指标与衰减筹码分布，待全部指标平滑收敛后，再切片进入 `2026-01-01` 执行回测。

---

### ② 严格规避未来函数 (Look-Ahead Bias)
- **严重错误做法**：
  使用当天的最高价（High）买入，或者在收盘前根据当天的收盘价买入而忽略了收盘价本身是当天最后一笔交易才能确认。
- **标准工程规范**：
  信号在 $T$ 日收盘时确认，建仓动作在 $T$ 日以计入滑点后的收盘价执行，或在 $T+1$ 日开盘价执行。

---

### ③ 避免样本过拟合 (Overfitting)
- 严禁通过反复微调指标参数（如将 MACD 参数强行改成 11, 27, 8 以迎合特定股票的某一波走势）来制造虚假的“回测圣杯”。标准策略必须具备跨标的、跨周期的参数稳健性。

---

## 6. 交互式多因子回测协同与实盘增强 (Multi-Factor Synergy)

在 [`reports/QCOM_MACD_QuantStats_Report.html`](../../reports/QCOM_MACD_QuantStats_Report.html) 研报中，我们提供了多因子动态切换与叠加视图，实战中可按如下逻辑进行多因子协同增强：

| 因子组合 | 协同研判机制 | 实盘改进效果 |
| :--- | :--- | :--- |
| **MACD 金叉 + RSI 超卖区 (< 35)** | 在股价超跌反弹初期触发金叉，此时估值安全垫厚 | **大幅降低追高被套概率**，建仓成本大幅降低 |
| **MACD 金叉 + CYQ 获利盘极低 (< 15%)** | 市场陷入恐慌割肉、浮盈筹码出清完毕后的主力转折点 | 捕捉**真正大底反转主升浪**（如 3月24日 QCOM 底仓金叉） |
| **MACD 死叉 + 布林带上轨破位** | 突破布林带上轨后缩量拐头死叉 | **高位精准止盈**，规避后续假突破回吐利润 |
| **ATR 动态波动率追踪止损** | 将止损位动态设定为 $\text{Highest} - 2.5 \times \text{ATR}$ | 防止固定百分比止损在不同波动率周期下失效 |

---

## 7. 数据持久化与查询接口 (Database Persistence)

所有回测结果已自动持久化归档至 SQLite 数据库（`data/<ticker>_<year>.db`）：
- `backtest_summary`：快速提取跨策略、跨标的年化收益与夏普比率对比；
- `backtest_trades`：审计每一笔交易的执行价、滑点与佣金磨损；
- `backtest_equity_curve`：用于绘制多策略资金曲线对比或导入 QuantStats 生成综合多资产研报。
