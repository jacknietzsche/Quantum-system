# AShare-X Architecture

> A股超级智能投研系统 — 4层架构，7个领域服务，3个LangGraph工作流

## 架构概览

```
UI/API 层 → 编排引擎层(LangGraph) → 领域服务层(7模块) → 基础设施层
```

## 领域服务层

| 服务 | 文件 | 类型 | 职责 |
|------|------|------|------|
| MarketPerception | services/market_perception.py | 增强 | 5维市场感知(BULL/BEAR/PANIC/OVERHEAT/NEUTRAL) |
| MemoryBank | services/memory_bank.py | 新增 | BM25双库隔离记忆(多头/空头独立索引) |
| QuantAnalyzers | services/quant_analyzers.py | 新增 | 6位投资大师纯Py量化分析(无LLM) |
| DebateEngine | services/debate_engine.py | 新增 | 多空辩论+防同质化门控(来源重合检测) |
| FactorFarm | services/factor_farm.py | 新增 | 15因子库+Rank IC评估+去重(IC>0.95) |
| StrategyLoader | services/strategy_loader.py | 新增 | YAML策略+表达式沙箱+5项前视偏差审计 |
| BacktestLoop | services/backtest_loop.py | 新增 | 滚动IC回测+Thompson Bandit分配 |
| RiskEngine | services/risk_engine.py | 增强 | 波动率+相关性矩阵+压力测试 |
| PortfolioOptimizer | services/portfolio_optimizer.py | 增强 | 约束预计算+信号融合+再平衡 |
| TradeExecutor | services/trade_executor.py | 新增 | 订单生成+模拟执行+仓位追踪+熔断 |
| ExecutionMode | services/execution_mode.py | 新增 | 双模式切换+T+5复盘调度 |

## 数据流

AkShare/Baostock → DataBus → MarketPerception → MemoryBank检索 →
QuantAnalyzers纯Py分析 → DebateEngine辩论 → RiskEngine风控 →
PortfolioOptimizer优化 → TradeExecutor执行 → MemoryBank存储

## 测试

41项集成测试覆盖全部领域服务 (tests/test_integration_phase*.py)
