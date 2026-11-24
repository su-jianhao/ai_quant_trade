# 因子研究、组合优化与 T+1 模拟盘逻辑规范 (Factor, Portfolio & Execution Logic)

> 提炼自：`app/services/factor_screening.py`、`app/services/portfolio_optimizer.py`、`app/services/paper_trading_service.py`

## 1. 因子体检与生命周期管线 (Factor Health & Lifecycle)

对每个因子在采样截面（默认 `sample_stride = 5`、`forward_period = 5`、`n_quantiles = 5`、`min_stocks = 50`）独立评估 5 项核心指标：
1. **IC 质量**：因子值与未来 $N$ 日收益的 Spearman Rank IC 均值、ICIR、$t$ 检验值及正 IC 占比。
2. **收益单调性**：分层分桶组序与组均收益的秩相关（按日平均，1.0 表示完美单调）。
3. **换手代理**：相邻采样截面的因子秩相关均值（秩相关越低，换手成本越高）。
4. **覆盖率**：平均每截面有效股票数，配合时序质量监控检测覆盖骤降、缺席与分布漂移。
5. **共线性**：采样截面 z-score 因子间的最大绝对相关系数及最相关因子伙伴（用于贪心去冗余）。

**生命周期状态机**：`pending` → `evaluated` → `accepted` / `rejected`（仅 `accepted` 白名单可进入 ML 模型特征选择）。

---

## 2. 组合优化与防前视规则 (Portfolio Optimization)

支持 5 种优化方法：`mean_variance`（均值方差）、`risk_parity`（风险平价）、`equal_weight`（等权）、`factor_neutral`（因子中性，须提供有效 `factor_exposures` 矩阵）、`black_litterman`。

**两条防失真铁律**：
1. **截止日隔离 (`as_of_date`)**：回测调用风险模型（Ledoit-Wolf 协方差估计）时**必须传入调仓日 `as_of_date`**，严禁使用当前系统时间之后的数据估计协方差。
2. **量纲对齐 (`annualize_cov`)**：当预期收益采用年化映射区间 `[-0.15, +0.30]` 时，日频协方差**必须开启 `× 252` 年化**，否则收益项与风险项量纲相差三个数量级，优化会退化为只看收益的角点解。

---

## 3. A 股 T+1 模拟盘撮合与风控规则 (Paper Trading Execution)

以每日 18:30 筹码信号（`resonance` 优先、`squeeze` 补足 `top_n` 等权）驱动次日开盘虚拟撮合，严格遵守 A 股交易约束：

1. **板块涨跌停幅度限制 (`_limit_pct`)**：
   - 创业板 / 科创板（`300 / 301 / 688 / 689`）：`±20%`
   - 北交所（`8 / 4 / 92`）：`±30%`
   - ST 股：`±5%`
   - 主板其余股票：`±10%`
2. **挂单与成交约束**：
   - T 日 18:30 按信号日收盘价记 `target_value` 生成待执行单，**T+1 日开盘价**成交。
   - **停牌**（当日无行情）：跳过并保留挂单。
   - **一字涨跌停约束**：开盘涨停不可买入，开盘跌停不可卖出。
   - **过期撤销**：连续 `3` 个交易日未成交自动过期撤销（`_MAX_ORDER_ATTEMPTS = 3`）。
3. **成本与跟踪误差归因**：
   - 默认双边佣金 `0.0003` + 双边滑点 `0.001`，卖出单边加计印花税。
   - 每日与「信号篮子 close-close 等权基准」对齐，将跟踪误差拆解归因至：**成交价差**、**交易成本**与**未成交损耗**。
