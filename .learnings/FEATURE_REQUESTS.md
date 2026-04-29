# 量化系统自改进记录

## [FEAT-20260323-001] 市场数据网络错误处理

**Logged**: 2026-03-23T23:06:00
**Priority**: high
**Status**: resolved
**Area**: infra

### Requested Capability
akshare API 网络连接不稳定时（ConnectionResetError/SSLError）自动重试，避免单次失败导致数据全失

### Details
- 错误类型：`ConnectionResetError(10054)`（个股资金流、板块资金流）
- 错误类型：`SSLError(UNEXPECTED_EOF_WHILE_READING)`（北向资金）
- 东方财富 API 瞬时连接中断，需要指数退避重试

### Resolution
- `real_data_fetcher.py`:
  1. 添加 `_fetch_incremental()` 增量更新方法（过期缓存只拉新数据）
  2. `get_batch_daily()` 支持多线程（max_workers=3）
- `market_data_fetcher.py`:
  1. 添加 `_call_with_retry()` 函数式重试（指数退避，最多3次）
  2. 所有 akshare API 调用都使用重试机制

### Metadata
- Source: conversation
- Related Files: real_data_fetcher.py, market_data_fetcher.py
- Tags: network, retry, optimization

# Feature Requests

## [FEAT-20260404-001] 模拟交易报告功能

**Logged**: 2026-04-04T18:38:00+08:00
**Priority**: high
**Status**: resolved
**Area**: frontend

### Requested Capability
用户希望在量化分析报告中添加模拟交易功能，包括：
1. 什么时候买入和什么时候卖出的信号
2. 各股票该持仓多少（仓位管理）
3. T+1 交易模式（今晚分析 -> 明早开盘买入 -> 明晚更新评估）

### User Context
用户提到参考"顶尖量化公司"，希望有一个专业级的模拟交易系统。

### Complexity Estimate
medium

### Suggested Implementation
已实现：
1. simulation_signals.py - 买卖信号生成
2. simulation_portfolio.py - 仓位管理
3. core/report.py - SimulationReportGenerator
4. run_simulation_v2.py - 主入口

### Resolution
- **Resolved**: 2026-04-04T18:38:00+08:00
- 完成了完整的模拟交易报告系统开发
- 支持 T+1 交易模式
- 生成专业 HTML 报告（买入/卖出信号、评级、仓位建议）

---

## [FEAT-20260405-001] V15量化策略回测报告改进方案

**Logged**: 2026-04-05T17:41:00+08:00
**Priority**: high
**Status**: resolved
**Area**: strategy

### Requested Capability
基于V15回测报告暴露的核心问题（选股池过大、调仓频繁、风险收益比差、低流动性标的干扰），实施精准优化：

#### 一、核心改进方法
1. **选股池精细化筛选**
   - 市值+流动性双层过滤：沪深300/中证500成分股 + 日均成交额前20,000只
   - 标的质量前置过滤：剔除ST/退市风险/停牌超10天/近3个月换手率低于1%

2. **调仓机制优化**
   - 降低调仓频率：月度→季度（每60个交易日）或阈值触发式调仓
   - 分层调仓策略：每次调仓不超过1/3仓位

3. **风险控制模块新增**
   - 动态止损+回撤控制：单期回撤超10%平仓50%，超20%清仓
   - 波动率约束：年化波动率超30%时自动降仓至20%-50%现金
   - 行业分散化：单行业持仓占比不超过20%

4. **收益增强与参数校准**
   - 市场环境自适应：区分牛/震/熊市动态调整因子权重
   - 回测过拟合修正：样本外验证（2024-2025训练集，2026验证集）

#### 二、因子体系优化
1. **因子权重重构**
   - 基础因子：40%→25%（MACD/RSI等有效性有限）
   - 增强因子：25%→30%（保留高IC值动量/假突破）
   - 市场环境因子：10%→20%（强化宏观择时）
   - 因子引擎V2：25%保持不变

2. **新增高有效性因子**
   - 流动性因子（8%）：日均成交额、换手率、Amihud非流动性指标
   - 质量因子（7%）：ROE、净利润增速、现金流比率
   - 低波动因子（5%）：60日波动率、最大回撤、beta系数
   - 交易行为因子（5%）：大单成交占比、龙虎榜资金流向

3. **因子有效性动态验证**
   - 剔除IC值绝对值<0.05的失效因子
   - 因子正交化处理（相关性>0.8）

4. **成本模拟**
   - 加入真实交易成本（佣金0.03%+滑点0.05%）

### User Context
V15回测报告显示：
- 选股池47,718只过大
- 调仓13,392次过于频繁
- 最大回撤30.78%、年化波动率120%
- 夏普比率仅0.01

### Complexity Estimate
complex

### Suggested Implementation
1. 修改 `core/config/` 添加选股池过滤配置
2. 修改 `core/strategy/` 调仓逻辑（季度/阈值触发）
3. 新增 `core/risk/` 风险控制模块
4. 修改 `factor_engine_v2.py` 添加新因子
5. 修改回测引擎添加交易成本模拟

### Metadata
- Source: conversation
- Related Files: factor_engine_v2.py, core/strategy/, backtest_v15_local.py
- Tags: strategy, optimization, risk-management, factors

---
