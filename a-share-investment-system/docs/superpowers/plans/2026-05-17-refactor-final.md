# AShare-X 重构最终计划（基于 TradingAgents-AShare 参考）

## 参考架构：TradingAgents-AShare

```
tradingagents/
├── agents/
│   ├── analysts/         # 7个LLM分析师 (Market/Fundamentals/Macro/News/...)
│   ├── managers/         # Research Manager + Trader
│   ├── researchers/      # Bull/Bear 研究员
│   ├── risk_mgmt/        # 风险三人组 (激进/保守/中性) + 裁判
│   └── utils/            # 工具(DB-first) + 状态定义 + 记忆
├── graph/                # LangGraph 工作流
│   ├── trading_graph.py  # 主图定义
│   ├── conditional_logic.py
│   ├── data_collector.py
│   ├── signal_processing.py
│   ├── reflection.py     # 反思循环
│   └── ...
├── dataflows/            # 数据源适配(类似我们的 providers/)
├── llm_clients/          # LLM 抽象层
├── prompts/              # 提示词
└── default_config.py
```

## 核心简化原则

| 原则 | 说明 |
|------|------|
| **砍掉死的** | electron(379MB)/strategies/memory/workflows/reports/backups |
| **保留活的** | providers/shared/frontend/screening Stage1-3/启动入口 |
| **参考 TradingAgents** | Stage4 照搬 agents/ + graph/ 结构 |
| **不做过度设计** | scoring 不拆7个文件，统一放 core/scoring.py |

---

## 阶段1：安全清理（0.5天）

删除项：
- `electron/` (379MB, 13K文件) — **先修 launch.py 删回退路径**
- `strategies/` — 已被 stock_screener 替代
- `memory/` — 空目录
- `reports/` + `backups/` — 运行时生成缓存
- `multi_model_voter.py` — 已被 skills.py 覆盖

**保留但暂不删**（等Stage4迁移完成）：
- `workflows/` + `workflow.py` + `super_workflow.py` — 15个LangGraph节点需迁移

## 阶段2：新建 core/ 目录（参考 TradingAgents 结构）

```
core/
├── __init__.py
│
├── scoring.py              # ★ 简化：不放7个文件，就一个统一评分引擎
│                            #   把 quant_analyzers(19大师) + master_agents(17大师)
│                            #   的纯Python评分逻辑搬到此文件，统一输入输出格式
│
├── agents/                  # ★ 参考 TradingAgents-AShare
│   ├── __init__.py
│   ├── state.py             # AgentState 定义（参考 agent_states.py）
│   ├── toolkit.py            # DB-first @tools（6-8个，参考 agent_utils.py）
│   │                          # get_stock_data / get_indicators / get_fundamentals
│   │                          # get_balance_sheet / get_news / get_market_regime
│   ├── analysts/
│   │   ├── market.py         # 行情分析 Agent
│   │   ├── fundamentals.py   # 基本面分析 Agent
│   │   └── news.py           # 新闻分析 Agent
│   ├── risk/
│   │   ├── debaters.py       # 风险辩论三人组（激进/保守/中性）
│   │   └── judge.py          # 风险裁判
│   ├── managers/
│   │   ├── researcher.py     # 研究经理（多空辩论）
│   │   └── trader.py         # 交易决策
│   ├── signal.py             # 结构化输出（SignalProcessor）
│   └── reflector.py          # 反思循环（Reflector + SQLite记忆）
│
├── graph/                    # ★ LangGraph 工作流
│   ├── __init__.py
│   ├── workflow.py           # 主图定义（参考 trading_graph.py）
│   └── conditional.py        # 图路由逻辑
│
└── llm/
    └── client.py             # LLM 客户端（包装 skills.py）
```

### key: scoring.py — 不拆7个文件

所有36个评分函数放一个文件，按区域分节：
```python
# core/scoring.py

# ═══ 基本面分析 ═══
def buffett_analyze(code, f): ...
def graham_analyze(code, f): ...
def munger_analyze(code, f): ...
def pabrai_analyze(code, f): ...

# ═══ 增长分析 ═══
def lynch_analyze(code, f): ...
def cathie_wood_analyze(code, f): ...

# ═══ 技术分析 ═══
def livermore_analyze(code, f): ...
def turtle_analyze(code, f): ...
def candlestick_analyze(code, f): ...
def trader_vic_analyze(code, f): ...

# ═══ 风险管理 ═══
def taleb_analyze(code, f): ...
def howard_marks_analyze(code, f): ...

# ═══ 综合评分 ═══
def composite_score(code, f, weights): ...
```

### key: toolkit.py — DB-first 工具模式

参考 TradingAgents-AShare 的 agent_utils.py，每个工具遵循：
```python
@tool
def get_stock_data(code: str) -> dict:
    """获取股票行情数据，DB优先"""
    # 1. 查 StockInfo 表缓存
    info = session.query(StockInfo).filter_by(stock_code=code).first()
    # 2. 如果数据过期/缺失 → 调 providers/market_data.py 获取
    if not info or stale(info):
        raw = provider.get_stock_basic(code)
        writer._save_stock_info(code, raw)
    # 3. 从DB读取并返回
    return format_stock_info(info)
```

## 阶段3：services/ 转发存根

31个service文件每个精简为：
```python
# services/stock_screener.py
from core.scoring import composite_score, livermore_analyze  # 等
# 保留原有 API 兼容的函数签名，实现转发到 core/
```

API路由文件不改（减少回归风险），只改 services/ 下的实现。

## 阶段4：API 路由简化

13个路由文件 → **先不动**（稳定版后再考虑合并）。
理由：路由是薄层，每个文件平均80行，合并的收益低、风险高。

## 阶段5：workflows/ 迁移到 core/graph/

- 将 `workflows/nodes/` 的15个节点合并到 `core/graph/workflow.py`
- 完成后再删 `workflows/`、`workflow.py`、`super_workflow.py`

---

## 与参考项目的对照

| 参考项目 (TradingAgents-AShare) | 我们的实现 |
|--------------------------------|-----------|
| `agents/analysts/` (7个) | `core/agents/analysts/` (3个: market/fundamentals/news) |
| `agents/risk_mgmt/` (3 debaters + judge) | `core/agents/risk/` (debaters + judge) |
| `agents/managers/` (researcher + trader) | `core/agents/managers/` (researcher + trader) |
| `agents/utils/agent_utils.py` (tools) | `core/agents/toolkit.py` |
| `agents/utils/agent_states.py` | `core/agents/state.py` |
| `graph/` (trading_graph + conditional + reflection) | `core/graph/` (workflow + conditional) |
| `llm_clients/` | `core/llm/client.py` |
| `dataflows/` (数据源) | `providers/` (不动) |
| `prompts/` | 内联在 agents/ 各文件中 |
| `default_config.py` | `shared/config.py` (不动) |

## 风险控制

1. **electron 删除**：先删 launch.py 第103-106行、136-149行的回退路径
2. **services/ 转发**：每改一个文件跑一次 pytest + API手动测试
3. **workflows/ 迁移**：先复制到 core/graph/，确认运行正常再删旧文件
4. **回滚方案**：git checkout 回滚单个文件，不阻塞整体进度
