# Quantum System — A股量化交易系统

> **项目状态: 开发中 (Work in Progress)**
>
> 本项目仍处于活跃开发阶段，尚未完善。因子体系、风控模型、回测引擎等核心模块持续迭代中，
> 部分功能可能存在缺陷或未经充分验证。**不建议直接用于实盘交易。**
> 欢迎 Issue 和 PR，但请做好风险评估。

A股（中国股票市场）量化交易系统，覆盖从数据采集、因子计算、多因子选股、回测验证到风险管理的完整量化投资流程。

### 当前进度

- [x] 核心架构搭建（core/ 模块化）
- [x] 51 因子计算引擎
- [x] 5 层数据源容错
- [x] 基础回测框架（Backtrader）
- [x] 本地 SQLite 数据库
- [ ] 因子有效性回测与筛选
- [ ] 实盘模拟交易验证
- [ ] 风控模型参数优化
- [ ] 完整的单元测试覆盖
- [ ] 性能基准测试与优化
- [ ] 文档完善

---

## 核心特性

- **51 个日频因子** — 动量、量价、资金流、流动性、波动率、情绪、微观结构、反转、处置效应、行为经典因子
- **5 层数据源容错** — baostock → akshare → efinance → 新浪HTTP → 腾讯HTTP，指数退避 + 自适应降速
- **多因子评分体系** — V15Scorer: 基础因子(20%) + 增强因子(35%) + 市场环境(15%) + 因子引擎V2(30%)
- **专业回测引擎** — 基于 Backtrader，A 股真实成本模型（佣金 + 印花税 + 滑点）
- **风险管理** — 动态止损(8%/15%)、波动率约束(25%)、行业分散化(20%)
- **本地数据库** — SQLite WAL 模式，~53K 股票，~564 万条价格记录

---

## 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/jacknietzsche/Quantum-system.git
cd Quantum-system

# 安装（可编辑模式 + 开发工具）
pip install -e ".[dev]"
```

### 基本使用

```bash
# 每日选股
python run_v15_full.py --top 10 --workers 8

# 使用本地数据库（更快）
python run_v15_local.py --top 10

# 组合管理
python run_portfolio_v2.py --date 20260401 --capital 100000

# 回测
python run_backtest.py

# 交互式仪表盘
streamlit run dashboard_v15.py

# 因子计算（批量，长时间运行）
python fetch_and_calculate_factors.py
python calculate_factors_all_history.py
```

### 测试与代码质量

```bash
# 运行测试
pytest tests/ -v

# 代码检查
ruff check .

# 代码格式化
ruff format .
```

---

## 架构

```
入口脚本 (run_*.py)
    │
    ▼
core/ ──────────────────────────────────────────────────
  │  config.py           统一配置中心
  │  logging_config.py   统一日志
  │  data.py             数据层（5 层容错）
  │  strategy.py         V15Scorer / StockFilter / MarketAnalyzer
  │  risk.py             RiskChecker / StopLossManager / PositionManager
  │  engine.py           BacktestEngine（Backtrader 封装）
  │  factor_engine_v2.py FactorEngineV2（51 因子编排）
  │  report.py           HTML 报告生成（Plotly）
  │  record_manager.py   错误/成果记录
  └─
factors/ ────────────────────────────────────────────────
  │  7 个因子模块，51 个日频因子，10 个类别
  └─
backtest_system/ ────────────────────────────────────────
  │  Backtrader 回测框架 + 策略适配器
  └─
local_db/ ───────────────────────────────────────────────
  │  SQLite 数据库 + 管理脚本
  └─
tests/ ──────────────────────────────────────────────────
     pytest 测试套件（unit/ + integration/）
```

### 数据流

```
数据源 (baostock/akshare/efinance/新浪/腾讯)
    │
    ▼
UnifiedDataFetcher (5 层容错 + 指数退避 + 24h 缓存)
    │
    ▼
SQLite (local_db/a_stock_quant.db)
    │
    ├── stocks        → 股票元数据
    ├── daily_price   → 日线行情 (OHLCV)
    └── stock_factors → 51 因子计算结果
            │
            ▼
    V15Scorer 评分 → 风控检查 → 报告生成
```

### 评分体系

```
综合评分 = 基础因子(20%) + 增强因子(35%) + 市场环境(15%) + 因子引擎V2(30%)
                    │
                    ├── 基础因子:   MACD, RSI, 布林带, KDJ, 成交量
                    ├── 增强因子:   假突破过滤, 短期动量, K线形态, VWAP
                    ├── 市场环境:   北向资金, 融资融券, 大盘资金流, 行业强度
                    └── 因子引擎V2: 动量, 量价, 资金流, 波动率, 情绪, 微观结构
```

---

## 因子体系

| 类别 | 数量 | 核心因子 |
|------|------|----------|
| 动量因子 | 5 | 过夜动量, 截面动量, 路径依赖动量 |
| 量价因子 | 6 | OBV, VWAP偏离, 量价背离 |
| 资金流因子 | 6 | 主力净流入, 大单占比, 资金集中度 |
| 流动性因子 | 5 | Amihud非流动性, 换手率异常 |
| 波动率因子 | 6 | 已实现波动率, 特质波动率, 波动率偏度 |
| 情绪因子 | 5 | 换手率情绪, 涨停效应, 跌停效应 |
| 微观结构因子 | 6 | 价格冲击, 订单流毒性, 高频波动率 |
| 反转因子 | 6 | 短期反转, 长期反转, 最大日收益 |
| 处置效应因子 | - | CGO, VNSP, CDE |
| 行为经典因子 | - | 行为金融 + 经典多因子 |
| 防顶过滤 | 10 | 假突破, 放量滞涨, 顶部形态识别 |

---

## 项目结构

```
Quantum-system/
├── core/                    # 核心包
│   ├── config.py            # 统一配置中心
│   ├── logging_config.py    # 统一日志
│   ├── data.py              # 数据层（5 层容错）
│   ├── strategy.py          # 选股评分
│   ├── risk.py              # 风险管理
│   ├── engine.py            # 回测引擎
│   ├── factor_engine_v2.py  # 因子引擎
│   └── report.py            # 报告生成
├── factors/                 # 51 个因子模块
├── backtest_system/         # Backtrader 回测框架
├── local_db/                # SQLite 数据库管理
├── tests/                   # 测试套件
│   ├── unit/                # 单元测试
│   └── integration/         # 集成测试
├── output/                  # 生成的输出文件
├── docs/reports/            # 历史报告文档
├── pyproject.toml           # 项目配置
├── requirements.txt         # 依赖列表
├── Makefile                 # 常用命令
└── CLAUDE.md                # 开发指南
```

---

## 依赖

| 库 | 用途 |
|---|---|
| backtrader | 回测引擎 |
| pandas / numpy | 数据处理 |
| akshare / baostock / efinance | A 股数据源 |
| plotly | 交互式图表 |
| scipy / scikit-learn | 统计分析 / 因子中性化 |
| quantstats | 专业回测报告 |
| streamlit | 仪表盘 UI |

---

## 配置

所有配置集中在 `core/config.py`，通过 `QuantConfig` dataclass 管理：

```python
from core.config import QuantConfig

cfg = QuantConfig()
cfg.portfolio.initial_cash = 500_000.0   # 初始资金
cfg.selection.top_n = 10                  # 推荐股票数
cfg.risk.max_volatility = 0.25           # 最大年化波动率
```

环境变量配置见 `.env.example`。

---

## 免责声明

- 本项目仅供学习和研究使用，**不构成任何投资建议**
- 量化策略的历史回测表现不代表未来收益
- 使用本系统进行实盘交易的一切风险由使用者自行承担
- 项目代码仍在持续迭代中，接口和行为可能发生变化

## License

MIT
