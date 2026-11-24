# 架构设计思想与盘后自动化编排规范 (Architecture & Automation Ideas)

> 提炼自：`app/__init__.py`、`app/services/daily_alert_service.py`、`app/services/signal_defs.py`、`README.md`

## 1. 核心架构设计思想 (Architectural Ideas)

### 1.1 零外部中间件混合存储边界
- **设计原则**：不引入 MySQL、Redis、Celery，确保「克隆即可运行」。
- **冷热/读写分离**：
  - **分析型宽数据 → Parquet**：日/分钟行情、财务三表、指数日线、因子值（`factor_values`）按 Hive 分区或股票分区落盘，兼顾列式压缩与向量化读取。
  - **低并发状态与元数据 → SQLite + 原子 JSON**：持仓、任务记录、AI 会话走 SQLite；模拟盘账户、预警历史、阈值配置采用 **`.tmp` + `os.replace` 原子写 JSON**，避免并发读写损坏。
  - **异步任务 → 进程内后台线程 + 本地注册表**：通过 `run_id` 轮询进度，降低部署复杂度。

### 1.2 「一处定义、多处消费」的单一配置源
- 信号阈值或寻优结果统一写入 `data/config/signal_thresholds.json`（文件不存在时无缝回退代码默认 `SignalThresholds`）。
- 截面扫描（`ChipSignalService`）、信号回测（`ChipSignalBacktestService`）与参数实验入口共享 `current_thresholds()` / `merge_thresholds()`，彻底消除“改一处漏一处”的口径漂移。

---

## 2. 盘后 18:30 自动化调度链 (Post-Market Automation Pipeline)

每个交易日 **18:30**（可通过 `DAILY_ALERT_TIME` 调整，`DAILY_ALERT_ENABLED=0` 关闭）按串行依赖自动执行以下闭环（非交易日自动跳过，任一环节失败则中止下游数据链）：

1. **数据链路自动编排**：
   `交易日历` → `日线` → `基本指标` → `资金流` → `扩展因子` → `筹码分布` → `大宽表构建` → `因子计算` → 数据完整性巡检（统计各表滞后交易天数）。
2. **事件数据归档**：
   归档当日龙虎榜、涨停池、跌停池、炸板池与连板天梯至 `data/event_archive/`，沉淀次日晋级率与情绪极值统计。
3. **每日预警扫描与外发推送**：
   - 收集当日筹码信号、指数 Regime、行业轮动榜首/榜尾、财务异动概要与情绪极值（涨停家数 ±2σ、炸板率）。
   - 与上一交易日对比生成异动预警：**Regime 翻转**、**新增筹码信号**、**行业轮动榜首变化**。
   - 原子追加至 `data/alerts/daily_alerts.json`（保留最近 90 条），并通过企业微信 / 钉钉 / Server 酱 / 自定义 Webhook 外发。
4. **模拟盘与自选股闭环**：
   触发 Paper Trading 信号挂单生成、预测跟踪归档、自选股收盘价格提醒检查，以及全市场 5 分钟线增量同步与日内/事件/PIT 基本面因子更新。
