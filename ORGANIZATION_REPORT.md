# 项目文件系统整理报告

## 整理目标

系统性整理现有文件，按照文件类型、用途或项目模块创建相应的文件夹结构，并将文件分类移动到对应的文件夹中，确保文件夹命名规范统一、清晰易懂，文件归类逻辑一致且具有可维护性。

## 整理策略

1. **按功能分类**：根据文件的功能和用途进行分类
2. **命名规范**：使用小写字母、下划线分隔的命名方式
3. **层次清晰**：建立合理的目录层次结构
4. **保持完整性**：确保所有文件都被正确归类，无遗漏

## 整理结果

### 目录结构

```
quant system/
├── .codebuddy/            # CodeBuddy 相关文件
├── .learnings/            # 学习记录和文档
├── .workbuddy/            # WorkBuddy 相关文件
├── automation_history/    # 自动化执行历史
├── backtest/              # 回测相关Python文件
├── backtest_system/       # 回测系统核心代码
├── core/                  # 核心引擎代码
├── factors/               # 因子相关代码
├── local_db/              # 本地数据库相关文件
├── logs/                  # 日志文件
├── market_data_cache/     # 市场数据缓存
├── reports/               # 报告文件（按类型分类）
│   ├── backtest_reports/  # 回测报告
│   ├── daily_reports/     # 每日报告
│   ├── portfolio_reports/ # 投资组合报告
│   └── simulation_reports/ # 模拟报告
├── scripts/               # 运行脚本
├── utils/                 # 工具类文件
└── 根目录文件             # 配置文件、架构文档等
```

### 文件分类详情

#### 1. backtest/ 目录
- **用途**：存放回测相关的Python文件
- **文件列表**：
  - backtest_quantstats_all_factors.py
  - backtest_quantstats_full_factor.py
  - backtest_quantstats_large_cap.py
  - backtest_v15_large_cap.py
  - backtest_v15_local.py
  - final_v15_backtest.py

#### 2. core/ 目录
- **用途**：存放核心引擎代码
- **文件列表**：
  - __init__.py
  - config.py
  - data.py
  - engine.py
  - factor_engine_v2.py
  - factor_weight_optimizer.py
  - local_db_adapter.py
  - local_db_fetcher.py
  - report.py
  - risk.py
  - risk_v2.py
  - strategy.py

#### 3. factors/ 目录
- **用途**：存放因子相关代码
- **文件列表**：
  - anti_top_factors.py
  - behavioral_classic_factors.py
  - capital_flow_factors.py
  - disposition_effect_factors.py
  - microstructure_reversal_factors.py
  - momentum_factors.py
  - volatility_sentiment_factors.py

#### 4. scripts/ 目录
- **用途**：存放运行脚本
- **文件列表**：
  - dashboard_v15.py
  - run_backtest_simple.py
  - run_portfolio_v2.py
  - run_v15_full.py
  - run_v15_local.py
  - run_v15_local_db_only.py
  - run_v15_local_only.py
  - run_v15_no_tencent.py
  - test_factor_engine.py
  - test_factor_engine_debug.py

#### 5. reports/ 目录
- **用途**：存放所有报告文件，按类型分类
- **子目录**：
  - **backtest_reports/**：回测报告
  - **daily_reports/**：每日报告
  - **portfolio_reports/**：投资组合报告
  - **simulation_reports/**：模拟报告

#### 6. 其他目录
- **backtest_system/**：回测系统核心代码
- **local_db/**：本地数据库相关文件
- **logs/**：日志文件
- **market_data_cache/**：市场数据缓存

### 根目录文件

- ARCHITECTURE.md          # 架构文档
- CLAUDE.md                # Claude 相关文档
- CLEANUP_REPORT.md        # 清理报告
- CODE_REVIEW_GUIDE.md      # 代码审查指南
- CODE_REVIEW_PROCESS.md   # 代码审查流程
- CODE_REVIEW_STANDARD.md  # 代码审查标准
- a_stock_quant.db         # 股票量化数据库
- backtest_report_large_cap_20260407.html  # 回测报告
- data_fetcher.log          # 数据获取日志
- hikyuu_adapter.log       # Hikyuu 适配器日志
- hikyuu_adapter_v2.log    # Hikyuu 适配器日志（版本2）
- hikyuu_adapter_v3.log    # Hikyuu 适配器日志（版本3）
- historical_backtest.log   # 历史回测日志
- run_output.log           # 运行输出日志

## 整理效果

1. **文件结构更加清晰**：按功能分类的目录结构使文件组织更加规范化
2. **导航便捷性提升**：明确的目录层次使文件查找更加方便
3. **项目维护性增强**：统一的文件组织方式便于后续开发和维护
4. **分类逻辑一致**：相同类型的文件被归类到同一目录

## 验证结果

- ✅ 所有文件均已正确归类
- ✅ 无遗漏或放错位置的文件
- ✅ 文件夹命名规范统一
- ✅ 目录结构层次清晰

## 后续建议

1. **定期整理**：建议定期执行文件系统整理，保持目录结构的清晰性
2. **命名规范**：遵循现有的命名规范，确保新文件也能正确归类
3. **文档更新**：根据新的文件结构更新项目文档
4. **版本控制**：确保所有核心文件纳入版本控制系统

项目文件系统整理已成功完成，文件结构更加清晰，为后续的开发和维护工作提供了良好的基础。