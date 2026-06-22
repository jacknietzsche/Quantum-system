# 个人使用指南

> 本文档是面向自己的操作手册，不是对外发布的用户文档。

**最后更新**: 2026-06-12

---

## 每日操作流程

### 收盘后运行（推荐 17:00 后）

```bash
python main.py daily
```

执行时间：约 60-90 秒

输出：
- 终端：实时进度 + 最终报告摘要
- 文件：`reports/daily_YYYYMMDD.json`

### 查看报告

**方式 1: 前端界面**
```bash
python launch.py
# 打开 http://localhost:8765
# 进入 Screening 页面 → Generate Plan
```

**方式 2: CLI**
```bash
python main.py analyze 600519  # 单股分析
```

**方式 3: 直接查看 JSON**
```bash
# reports/daily_20260612.json
```

### 每日检查清单

- [ ] 运行 `python main.py daily`
- [ ] 检查报告中的推荐股票
- [ ] 对比大盘涨跌
- [ ] 如有持仓，检查止损/止盈信号

---

## 选股流程详解

### Stage 1: 硬过滤

条件（可配置）：
- 成交额 > 5000 万
- 非 ST/*ST
- 上市天数 > 250
- PE > 0 且 PE < 200

输出：约 200-500 只候选股

### Stage 2: 大师评分

17 位大师并行评分：
- Buffett（价值投资）
- Graham（安全边际）
- Lynch（成长投资）
- Taleb（反脆弱）
- Livermore（趋势交易）
- ...

输出：每只股票的综合评分

### Stage 3: AI 深度分析

StockAgent 分析：
- 调用大师分析器
- 注入投资技能知识
- 输出：评分 + 信号 + 理由

### Stage 4: 交易计划

PortfolioAgent + DecisionAgent：
- 仓位分配
- 止损/止盈设置
- 条件触发单

输出：完整交易计划

---

## 风控规则

### 仓位限制

| 波动率 | 单股最大仓位 |
|--------|--------------|
| < 15% | 25% |
| 15-30% | 15% |
| 30-50% | 10% |
| > 50% | 5% |

### 止损规则

- 单股止损：-8%
- 组合止损：总回撤 > 5% 减仓至 50%

### 集中度限制

- 单行业 < 40%
- 单股 < 25%

---

## 数据源优先级

1. **腾讯**（0.2s，最稳定）— 主力源
2. **东方财富**（0.5s）— 备用源
3. **新浪**（0.2s）— 备用源
4. **Baostock**（0.5s）— 备用源
5. **AKShare**（10s）— 仅当以上都失败时

### 数据源健康检查

```bash
python -c "from providers.market_data import MarketDataProvider; print(MarketDataProvider().health_check())"
```

---

## 已知问题

### 测试问题

```
tests/test_integration_phase2.py → cannot import 'BUILTIN_FACTORS'
tests/unit/test_workflow_nodes.py → cannot import 'Column'
```

**影响**: 不影响运行，仅影响测试收集
**修复**: 需更新 import 语句

### 数据源问题

- TickFlow 需要代理，不启用
- AKShare 响应慢（~10s），仅备用
- 部分数据源时好时坏

### 架构问题

- 设计文档描述的 LangGraph 架构未实现
- 实际用的是 workflows/nodes/ 的简单编排
- 3 Agent vs 文档描述的 5 Agent

---

## 配置文件

### config.yaml

位置: `config/config.yaml`

关键配置：
```yaml
llm:
  provider: deepseek
  model: deepseek-chat

screening:
  styles:
    value: { ... }
    momentum: { ... }

data:
  primary_sources: [tencent, eastmoney]
```

### .env

位置: `config/.env`

必需配置：
```
DEEPSEEK_API_KEY=your_key
SILICONFLOW_API_KEY=your_key
QQ_EMAIL=your@qq.com
QQ_SMTP_PASSWORD=your_password
```

---

## 常用命令

```bash
# 每日分析
python main.py daily

# 单股分析
python main.py analyze 600519

# 全市场选股
python main.py screen

# 启动前端
python launch.py

# 开发模式
python launch.py --dev

# 运行测试
pytest tests/ -m "not slow"

# 代码检查
ruff check .
ruff format --check .
```

---

## 参考资源

### 设计文档

- `docs/ACTUAL_ARCHITECTURE.md` — 当前实际架构
- `docs/architecture/README.md` — 目标架构索引
- `OPTIMIZATION_PLAN.md` — 优化计划

### 代码入口

- `main.py` — CLI 入口
- `server.py` — API 服务器
- `launch.py` — 启动脚本
- `services/screening/pipeline.py` — 选股核心
- `services/trading_orchestrator.py` — AI 分析编排

---

**维护者**: 个人使用
**更新频率**: 遇到问题时更新
