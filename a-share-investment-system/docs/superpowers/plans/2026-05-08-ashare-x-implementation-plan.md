# AShare-X 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 a-share-investment-system 渐进重构为 AShare-X，新增辩论引擎、因子工厂、交易执行器、记忆银行4个服务，增强市场感知、风控引擎、组合优化器3个服务。

**Architecture:** 4层架构 — 基础设施层(保留) → 领域服务层(7个独立服务模块) → 编排引擎层(3个LangGraph工作流) → UI/API层(保留)。领域服务通过 `BaseService` 统一接口暴露，编排层依赖注入调用。

**Tech Stack:** Python 3.10+, LangGraph, SQLAlchemy/SQLite, AkShare, jieba, BM25 (rank_bm25), pandas, PyYAML

**Spec:** `docs/superpowers/specs/2026-05-08-ashare-x-blueprint-design.md`

---

## 文件结构映射

```
services/
├── base.py                    # [新建] ServiceResult + BaseService
├── protocols.py               # [新建] 7个服务接口Protocol
├── market_perception.py       # [新建] MarketPerception
├── debate_engine.py           # [新建] DebateEngine
├── factor_farm.py             # [新建] FactorFarm
├── trade_executor.py          # [新建] TradeExecutor
├── memory_bank.py             # [新建] MemoryBank
├── risk_engine.py             # [新建/增强] RiskEngine
├── portfolio_optimizer.py     # [新建/增强] PortfolioOptimizer
├── backtest_loop.py           # [新建] BacktestLoop工作流
├── quant_analyzers.py         # [新建] 19大师纯Py子分析函数库
└── strategy_loader.py         # [新建] YAML策略加载器

strategies/                    # [新建] YAML策略定义目录
├── ma_golden_cross.yaml
├── trend_pullback.yaml
└── low_vol_breakout.yaml

memory/                        # [新建] BM25索引存储
├── bull_memory_index.pkl
└── bear_memory_index.pkl

super_workflow.py              # [修改] 依赖注入+新节点
workflow.py                    # [修改] 注入领域服务
scheduler.py                   # [修改] T+5复盘任务
skills.py                      # [修改] 移除内置分析
```

**文件职责边界**：
- `services/base.py` — 只有 ServiceResult dataclass 和 BaseService 抽象类
- `services/protocols.py` — 只有 Protocol 类，无实现
- `services/memory_bank.py` — BM25索引+检索+存储，无LLM调用
- `services/debate_engine.py` — 辩论编排，依赖 MemoryBank（注入）
- `services/market_perception.py` — 5维评分+环境分类，纯计算无LLM
- `services/risk_engine.py` — 三层风控，纯计算无LLM
- `services/portfolio_optimizer.py` — 约束预计算(纯Py)+信号融合(有LLM)
- `services/quant_analyzers.py` — 19个纯Py分析函数，无LLM，可独立测试
- `services/strategy_loader.py` — YAML加载+表达式解析+5项审计

---

## 阶段0：基础设施准备

### Task 0.1: 创建 ServiceResult 和 BaseService

**Files:**
- Create: `services/__init__.py`
- Create: `services/base.py`

- [ ] **Step 1: 创建 `services/__init__.py`**

```python
"""AShare-X 领域服务层"""
```

- [ ] **Step 2: 写 `services/base.py`**

```python
"""AShare-X 领域服务基类"""
from dataclasses import dataclass, field
from typing import Dict, List, Any, Literal
import time


@dataclass
class ServiceResult:
    """所有领域服务的统一返回类型"""
    status: Literal["ok", "degraded", "error"]
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def ok(cls, data: Dict = None, **metrics) -> "ServiceResult":
        return cls(status="ok", data=data or {}, metrics=metrics)

    @classmethod
    def degraded(cls, data: Dict, errors: List[str], **metrics) -> "ServiceResult":
        return cls(status="degraded", data=data, errors=errors, metrics=metrics)

    @classmethod
    def error(cls, errors: List[str], **metrics) -> "ServiceResult":
        return cls(status="error", errors=errors, metrics=metrics)


class BaseService:
    """所有领域服务的基类"""

    def __init__(self):
        self._call_count = 0
        self._total_elapsed_ms = 0.0

    def health_check(self) -> bool:
        """子类可重写，默认返回True"""
        return True

    def get_metrics(self) -> Dict[str, float]:
        return {
            "call_count": self._call_count,
            "total_elapsed_ms": self._total_elapsed_ms,
        }

    def _track(self, result: ServiceResult, elapsed_ms: float) -> ServiceResult:
        self._call_count += 1
        self._total_elapsed_ms += elapsed_ms
        result.metrics["elapsed_ms"] = elapsed_ms
        return result
```

- [ ] **Step 3: 验证可导入**

```bash
python -c "from services.base import ServiceResult, BaseService; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add services/__init__.py services/base.py
git commit -m "feat: add ServiceResult and BaseService base classes"
```

---

### Task 0.2: 定义7个领域服务接口协议

**Files:**
- Create: `services/protocols.py`

- [ ] **Step 1: 写 `services/protocols.py`**

```python
"""AShare-X 领域服务接口协议"""
from typing import Protocol, List, Dict, Any, Optional, runtime_checkable
from services.base import ServiceResult


@runtime_checkable
class MarketPerceptionProtocol(Protocol):
    def perceive(self, market_data: Dict) -> ServiceResult: ...
    def get_position_limits(self) -> ServiceResult: ...
    def is_trading_day(self, date: str = None) -> bool: ...


@runtime_checkable
class MemoryBankProtocol(Protocol):
    def store(self, situation: Dict, decision: Dict, outcome: Dict) -> ServiceResult: ...
    def retrieve(self, current_situation: Dict, top_k: int = 5) -> ServiceResult: ...
    def inject_into_prompt(self, base_prompt: str, current_situation: Dict) -> ServiceResult: ...


@runtime_checkable
class DebateEngineProtocol(Protocol):
    def run_debate(
        self, stock_code: str, analyst_reports: List[Dict],
        market_context: Dict, max_rounds: int = 2
    ) -> ServiceResult: ...


@runtime_checkable
class QuantAnalyzersProtocol(Protocol):
    def analyze_all(self, stock_code: str, financials: Dict, prices: List) -> List[Dict]: ...
    def buffett_analyze(self, stock_code: str, financials: Dict) -> Dict: ...
    def graham_analyze(self, stock_code: str, financials: Dict) -> Dict: ...
    def lynch_analyze(self, stock_code: str, financials: Dict) -> Dict: ...


@runtime_checkable
class FactorFarmProtocol(Protocol):
    def get_top_factors(self, n: int = 20, min_ic: float = 0.03) -> ServiceResult: ...
    def build_factor_score(self, stock_code: str) -> ServiceResult: ...
    def evaluate_factor(self, factor_name: str) -> ServiceResult: ...


@runtime_checkable
class RiskEngineProtocol(Protocol):
    def full_audit(
        self, portfolio: List[Dict], market_regime: Dict,
        candidate_orders: List[Dict] = None
    ) -> ServiceResult: ...


@runtime_checkable
class PortfolioOptimizerProtocol(Protocol):
    def optimize(
        self, current_positions: List[Dict], signals: List[Dict],
        risk_report: Dict, cash: float
    ) -> ServiceResult: ...
```

- [ ] **Step 2: 验证协议类型检查**

```bash
python -c "
from services.protocols import MarketPerceptionProtocol
print('All protocols defined OK')
print(f'MarketPerceptionProtocol is runtime_checkable: {hasattr(MarketPerceptionProtocol, \"__runtime_checkable__\")}')
"
```

Expected: `All protocols defined OK` + `runtime_checkable: True`

- [ ] **Step 3: Commit**

```bash
git add services/protocols.py
git commit -m "feat: add 7 domain service protocol interfaces"
```

---

### Task 0.3: 搭建策略和记忆目录结构

**Files:**
- Create: `strategies/ma_golden_cross.yaml`（示例策略）
- Create: `memory/.gitkeep`

- [ ] **Step 1: 创建目录和占位文件**

```bash
mkdir -p strategies memory
touch memory/.gitkeep
```

- [ ] **Step 2: 写示例YAML策略 `strategies/ma_golden_cross.yaml`**

```yaml
name: "均线金叉策略"
version: "1.0.0"
updated_at: "2026-05-08"
description: "MA5上穿MA20且成交量放大时入场"
market_regimes: ["bull", "neutral"]
required_indicators:
  - name: ma5
    params: {window: 5}
  - name: ma20
    params: {window: 20}
  - name: volume_ratio
    params: {window: 20}
scoring:
  - name: golden_cross
    formula: "ma5 > ma20"
    weight: 30
  - name: volume_confirm
    formula: "volume_ratio > 1.5"
    weight: 20
  - name: trend_align
    formula: "ma20 > ma60"
    weight: 25
  - name: not_limit_down
    formula: "change_pct > -9.5"
    weight: 25
filters:
  - condition: "turnover_rate > 0.5"
  - condition: "is_st == 0"
entry_threshold: 65
stop_loss_pct: -5.0
take_profit_pct: 15.0
max_hold_days: 20
```

- [ ] **Step 3: Commit**

```bash
git add strategies/ memory/
git commit -m "feat: scaffold strategies/ and memory/ directories with sample YAML"
```

---

### Task 0.4: 在 super_workflow.py 中注入依赖框架

**Files:**
- Modify: `super_workflow.py`

- [ ] **Step 1: 读取当前 super_workflow.py 的导入和类定义区域**

找到导入段和 `build_super_workflow` 函数。

- [ ] **Step 2: 添加服务容器的导入和初始化**

在 `super_workflow.py` 顶部导入区增加：

```python
# AShare-X 领域服务（渐进式引入）
from services.base import ServiceResult, BaseService
```

在 `build_super_workflow` 函数之前增加服务容器：

```python
# ════════════════════════════════════════════════════════════════
#  AShare-X 服务容器（渐进式引入，阶段0仅定义接口）
# ════════════════════════════════════════════════════════════════

class ServiceContainer:
    """领域服务依赖注入容器 — 阶段0默认使用None，阶段1起逐个填充"""

    def __init__(self):
        self.market_perception = None      # 阶段1.1填充
        self.memory_bank = None            # 阶段1.3填充
        self.debate_engine = None          # 阶段1.5填充
        self.quant_analyzers = None        # 阶段1.4填充
        self.factor_farm = None            # 阶段2填充
        self.risk_engine = None            # 阶段3填充（保留现有RiskFirewall）
        self.portfolio_optimizer = None    # 阶段3填充
        self.trade_executor = None         # 阶段3填充

    def is_ready(self, *service_names: str) -> bool:
        """检查指定服务是否已初始化"""
        return all(getattr(self, name, None) is not None for name in service_names)


# 全局服务容器实例
_services = ServiceContainer()


def get_services() -> ServiceContainer:
    """获取全局服务容器"""
    return _services
```

- [ ] **Step 3: 验证现有工作流不受影响**

```bash
python -c "
from super_workflow import build_super_workflow, get_services, ServiceContainer
svc = get_services()
assert svc.market_perception is None
assert svc.is_ready('market_perception') == False
print('Service container initialized, existing workflow unaffected')
"
```

Expected: `Service container initialized, existing workflow unaffected`

- [ ] **Step 4: Commit**

```bash
git add super_workflow.py
git commit -m "feat: inject ServiceContainer dependency framework into super_workflow"
```

---

## 阶段1：决策质量核心

### Task 1.1: 实现 MarketPerception（5维市场感知）

**Files:**
- Create: `services/market_perception.py`

- [ ] **Step 1: 写核心5维度评分函数**

`services/market_perception.py`:

```python
"""5维市场环境感知服务 — 来源: QuantLLM"""
from typing import Dict, List, Literal
import pandas as pd
from services.base import ServiceResult, BaseService


class MarketPerception(BaseService):
    """5维度融合市场环境感知"""

    # 维度权重（来源: QuantLLM IC分析）
    DIMENSION_WEIGHTS = {
        "trend_position": 0.25,
        "trend_direction": 0.25,
        "volume_confirm": 0.15,
        "volatility": 0.15,
        "price_momentum": 0.20,
    }

    def perceive(self, market_data: Dict) -> ServiceResult:
        """输入原始市场数据，输出完整环境感知"""
        try:
            breadth = market_data.get("breadth", {})
            indices = market_data.get("indices", {})

            scores = self._score_dimensions(breadth, indices)
            total = sum(s * self.DIMENSION_WEIGHTS[k] for k, s in scores.items())

            regime = self._classify(total, breadth)
            adaptive = self._adaptive_params(regime)
            phase = self._detect_trading_phase()

            return ServiceResult.ok(data={
                "regime": regime,
                "total_score": round(total, 2),
                "dimension_scores": scores,
                "adaptive_params": adaptive,
                "trading_phase": phase,
            })
        except Exception as e:
            return ServiceResult.error(errors=[f"MarketPerception failed: {e}"])

    def _score_dimensions(self, breadth: Dict, indices: Dict) -> Dict[str, float]:
        """计算5维度独立评分（范围: -2 ~ +2）"""
        up = breadth.get("up", 0)
        down = breadth.get("down", 0)
        total = breadth.get("total", 1)
        limit_down = breadth.get("limit_down", 0)
        limit_up = breadth.get("limit_up", 0)

        # D1: 趋势位置 — 涨跌比
        if total > 0:
            up_ratio = up / total
            if up_ratio > 0.7:
                d1_score = min(2.0, (up_ratio - 0.5) * 5)
            elif up_ratio < 0.3:
                d1_score = max(-2.0, (up_ratio - 0.5) * 5)
            else:
                d1_score = (up_ratio - 0.5) * 4
        else:
            d1_score = 0.0

        # D2: 趋势方向 — 涨跌比偏离中性（用涨跌绝对差）
        if total > 0:
            imbalance = (up - down) / total
            d2_score = max(-2.0, min(2.0, imbalance * 3))
        else:
            d2_score = 0.0

        # D3: 量能确认 — 涨停数 vs 跌停数
        if limit_up + limit_down > 0:
            d3_score = max(-1.0, min(1.0, (limit_up - limit_down) / max(total, 1) * 10))
        else:
            d3_score = 0.0

        # D4: 波动率 — 跌停占比反映恐慌程度
        if total > 0:
            limit_down_ratio = limit_down / total
            if limit_down_ratio > 0.05:
                d4_score = -1.0
            elif limit_down_ratio > 0.02:
                d4_score = -0.5
            elif limit_up / total > 0.1:
                d4_score = 0.5  # 过热信号
            else:
                d4_score = 0.0
        else:
            d4_score = 0.0

        # D5: 价格动量 — 从breath推断（历史数据在StockInfo中）
        d5_score = 0.0  # 默认，后续从均线数据增强
        if total > 0 and down > up * 2:
            d5_score = -1.0
        elif total > 0 and up > down * 2:
            d5_score = 1.0

        return {
            "trend_position": round(d1_score, 1),
            "trend_direction": round(d2_score, 1),
            "volume_confirm": round(d3_score, 1),
            "volatility": round(d4_score, 1),
            "price_momentum": round(d5_score, 1),
        }

    def _classify(self, total: float, breadth: Dict) -> str:
        """环境分类"""
        limit_down = breadth.get("limit_down", 0)
        limit_up = breadth.get("limit_up", 0)
        total_stocks = breadth.get("total", 1)

        # 特殊模式优先
        if limit_down > 50 and total < -3:
            return "PANIC"
        if limit_up > 80 and total_stocks > 0 and limit_up / total_stocks > 0.02:
            return "OVERHEAT"

        if total >= 2.0:
            return "BULL"
        elif total <= -2.0:
            return "BEAR"
        return "NEUTRAL"

    def _adaptive_params(self, regime: str) -> Dict:
        """自适应参数映射"""
        params = {
            "BULL": {"target_position_pct": 0.95, "max_holdings": 10, "selection_threshold": "buy+strong_buy"},
            "NEUTRAL": {"target_position_pct": 0.50, "max_holdings": 5, "selection_threshold": "buy+strong_buy"},
            "BEAR": {"target_position_pct": 0.30, "max_holdings": 3, "selection_threshold": "strong_buy_only"},
            "PANIC": {"target_position_pct": 0.10, "max_holdings": 1, "selection_threshold": "strong_buy_only"},
            "OVERHEAT": {"target_position_pct": 0.70, "max_holdings": 8, "selection_threshold": "buy+strong_buy"},
        }
        return params.get(regime, params["NEUTRAL"])

    def _detect_trading_phase(self) -> str:
        """检测当前交易阶段"""
        from datetime import datetime
        now = datetime.now()
        hour = now.hour + now.minute / 60.0
        weekday = now.weekday()

        if weekday >= 5:
            return "holiday"
        if hour < 9.5:
            return "pre_market"
        if 9.5 <= hour <= 11.5:
            return "intraday_morning"
        if 11.5 < hour < 13.0:
            return "lunch_break"
        if 13.0 <= hour <= 15.0:
            return "intraday_afternoon"
        return "post_market"

    def get_position_limits(self) -> ServiceResult:
        """获取当前环境下的仓位限制 — 需要先调用perceive"""
        return ServiceResult.ok(data={
            "message": "Call perceive() first to get adaptive_params"
        })

    def is_trading_day(self, date: str = None) -> bool:
        """判断是否为A股交易日（简化版：仅排除周末）"""
        from datetime import datetime, timedelta
        target = datetime.strptime(date, "%Y-%m-%d") if date else datetime.now()
        return target.weekday() < 5  # TODO: 后续集成akshare交易日历
```

- [ ] **Step 2: 验证MarketPerception独立可运行**

```bash
python -c "
from services.market_perception import MarketPerception
mp = MarketPerception()
result = mp.perceive({
    'breadth': {'up': 1500, 'down': 3000, 'total': 5000, 'limit_up': 20, 'limit_down': 80},
    'indices': {'上证指数': {'price': 3200, 'change_pct': -2.5}},
})
print(f'Regime: {result.data[\"regime\"]}')
print(f'Scores: {result.data[\"dimension_scores\"]}')
print(f'Params: {result.data[\"adaptive_params\"]}')
print(f'Phase: {result.data[\"trading_phase\"]}')
"
```

Expected: 输出 `Regime: PANIC` 或 `BEAR`，含5维评分。

- [ ] **Step 3: 在 ServiceContainer 中注册**

修改 `super_workflow.py` 的 `ServiceContainer.__init__`:

```python
def __init__(self):
    from services.market_perception import MarketPerception
    self.market_perception = MarketPerception()  # 阶段1: 立即初始化
    self.memory_bank = None
    self.debate_engine = None
    self.quant_analyzers = None
    self.factor_farm = None
    self.risk_engine = None
    self.portfolio_optimizer = None
    self.trade_executor = None
```

- [ ] **Step 4: Commit**

```bash
git add services/market_perception.py super_workflow.py
git commit -m "feat: implement MarketPerception with 5-dimension regime detection"
```

---

### Task 1.2: 注入 MarketPerception 到数据获取节点

**Files:**
- Modify: `super_workflow.py` (`node_fetch_global_data`)

- [ ] **Step 1: 读取当前 `node_fetch_global_data` 函数**

确认 panic_score 计算逻辑的位置。

- [ ] **Step 2: 替换市场风险判断逻辑**

在 `node_fetch_global_data` 返回前，增加 MarketPerception 调用，替代当前的 `panic_score` 计算：

```python
# 在 market_data 构建完成后，注入MarketPerception
services = get_services()
if services.market_perception:
    perception_result = services.market_perception.perceive(market_data)
    if perception_result.status == "ok":
        market_data["_perception"] = perception_result.data
        logs.append(_log(state, f"📊 市场感知: {perception_result.data['regime']} "
                       f"(总分{perception_result.data['total_score']}, "
                       f"目标仓位{perception_result.data['adaptive_params']['target_position_pct']:.0%})"))
```

- [ ] **Step 3: 验证集成**

```bash
python -c "
from super_workflow import get_services
svc = get_services()
assert svc.market_perception is not None
regime = svc.market_perception.perceive({
    'breadth': {'up': 2500, 'down': 2000, 'total': 5000, 'limit_up': 50, 'limit_down': 10},
    'indices': {},
})
assert regime.status == 'ok'
print(f'Integration OK — regime: {regime.data[\"regime\"]}')
"
```

- [ ] **Step 4: Commit**

```bash
git add super_workflow.py
git commit -m "feat: inject MarketPerception into node_fetch_global_data"
```

---

### Task 1.3: 实现 MemoryBank（BM25记忆银行）

**Files:**
- Create: `services/memory_bank.py`

- [ ] **Step 1: 安装依赖**

```bash
pip install rank-bm25 jieba
```

- [ ] **Step 2: 写 `services/memory_bank.py`**

```python
"""BM25记忆银行 — 来源: TradingAgents-AShare"""
import os
import json
import pickle
import jieba
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from rank_bm25 import BM25Okapi

from services.base import ServiceResult, BaseService


class MemoryBank(BaseService):
    """双库隔离的BM25记忆系统"""

    def __init__(self, memory_dir: str = "memory"):
        super().__init__()
        self.memory_dir = memory_dir
        os.makedirs(memory_dir, exist_ok=True)

        # 双库物理隔离
        self.bull_index_path = os.path.join(memory_dir, "bull_index.pkl")
        self.bear_index_path = os.path.join(memory_dir, "bear_index.pkl")

        self.bull_docs: List[Dict] = []
        self.bear_docs: List[Dict] = []
        self.bull_bm25: Optional[BM25Okapi] = None
        self.bear_bm25: Optional[BM25Okapi] = None

        self._load()

    # ── 公开接口 ──

    def store(self, situation: Dict, decision: Dict, outcome: Dict) -> ServiceResult:
        """存储一次决策记录到对应记忆库"""
        try:
            memory = {
                "id": f"mem_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(self.bull_docs)+len(self.bear_docs)}",
                "stock_code": situation.get("stock_code", ""),
                "stock_name": situation.get("stock_name", ""),
                "regime": situation.get("regime", "NEUTRAL"),
                "decision_type": decision.get("verdict", "持有"),
                "confidence": decision.get("confidence", 0.5),
                "outcome_pct": outcome.get("return_pct", 0),
                "outcome_correct": outcome.get("correct", False),
                "created_at": datetime.now().isoformat(),
                "situation_text": self._encode_situation(situation),
                "decision_text": json.dumps(decision, ensure_ascii=False),
            }

            # 按决策方向分库
            verdict = decision.get("verdict", "持有")
            if verdict in ("买入", "加仓"):
                self.bull_docs.append(memory)
                self._rebuild_bull_index()
            elif verdict in ("卖出", "减仓"):
                self.bear_docs.append(memory)
                self._rebuild_bear_index()
            # 持有决策不入库

            self._save()
            return ServiceResult.ok(data={"memory_id": memory["id"]})
        except Exception as e:
            return ServiceResult.error(errors=[f"MemoryBank.store failed: {e}"])

    def retrieve(
        self, current_situation: Dict, top_k: int = 5, bank: str = "auto"
    ) -> ServiceResult:
        """检索最相似的历史场景"""
        try:
            query_text = self._encode_situation(current_situation)
            tokenized_query = list(jieba.cut(query_text))

            if bank == "bull" or (bank == "auto" and current_situation.get("intent") == "buy"):
                memories = self._search(self.bull_bm25, self.bull_docs, tokenized_query, top_k)
            elif bank == "bear" or (bank == "auto" and current_situation.get("intent") == "sell"):
                memories = self._search(self.bear_bm25, self.bear_docs, tokenized_query, top_k)
            else:
                bull_results = self._search(self.bull_bm25, self.bull_docs, tokenized_query, top_k // 2 + 1)
                bear_results = self._search(self.bear_bm25, self.bear_docs, tokenized_query, top_k // 2 + 1)
                memories = bull_results + bear_results

            # 过期降权（>1年的记忆权重×0.5）
            one_year_ago = datetime.now() - timedelta(days=365)
            for m in memories:
                created = datetime.fromisoformat(m.get("created_at", "2000-01-01"))
                m["_weight_decay"] = 0.5 if created < one_year_ago else 1.0

            return ServiceResult.ok(data={"memories": memories[:top_k], "count": len(memories)})
        except Exception as e:
            return ServiceResult.error(errors=[f"MemoryBank.retrieve failed: {e}"])

    def inject_into_prompt(self, base_prompt: str, current_situation: Dict) -> ServiceResult:
        """将历史经验注入Agent prompt"""
        result = self.retrieve(current_situation, top_k=3)
        if result.status != "ok" or not result.data.get("memories"):
            return ServiceResult.ok(data={"prompt": base_prompt, "injected_count": 0})

        lessons = []
        for m in result.data["memories"]:
            correct = "✅成功" if m.get("outcome_correct") else "❌失败"
            weight = m.get("_weight_decay", 1.0)
            lessons.append(
                f"- [{correct}] 当{m['situation_text'][:80]}...时，"
                f"决策「{m['decision_type']}」结果{m['outcome_pct']:+.1f}%"
                f"{'（权重降低）' if weight < 1.0 else ''}"
            )

        enhanced = (
            f"{base_prompt}\n\n"
            f"[历史经验—仅供参考，不构成决策依据]\n"
            + "\n".join(lessons)
        )
        return ServiceResult.ok(data={
            "prompt": enhanced,
            "injected_count": len(lessons),
        })

    # ── 内部方法 ──

    def _encode_situation(self, situation: Dict) -> str:
        """将场景编码为可检索文本"""
        parts = [
            situation.get("stock_code", ""),
            situation.get("stock_name", ""),
            situation.get("regime", ""),
            f"PE{situation.get('pe', 0):.1f}",
            f"ROE{situation.get('roe', 0):.1f}",
            f"行业{situation.get('industry', '')}",
            f"盈亏{situation.get('pl_pct', 0):+.1f}%",
        ]
        return " ".join(str(p) for p in parts if p)

    def _search(self, bm25, docs, tokenized_query, top_k) -> List[Dict]:
        if bm25 is None or not docs:
            return []
        scores = bm25.get_scores(tokenized_query)
        ranked = sorted(enumerate(scores), key=lambda x: -x[1])[:top_k]
        return [{**docs[i], "_bm25_score": float(s)} for i, s in ranked if s > 0]

    def _rebuild_bull_index(self):
        if self.bull_docs:
            tokenized = [list(jieba.cut(d["situation_text"])) for d in self.bull_docs]
            self.bull_bm25 = BM25Okapi(tokenized)

    def _rebuild_bear_index(self):
        if self.bear_docs:
            tokenized = [list(jieba.cut(d["situation_text"])) for d in self.bear_docs]
            self.bear_bm25 = BM25Okapi(tokenized)

    def _save(self):
        data = {"bull": self.bull_docs, "bear": self.bear_docs}
        with open(os.path.join(self.memory_dir, "memory_data.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    def _load(self):
        path = os.path.join(self.memory_dir, "memory_data.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.bull_docs = data.get("bull", [])
            self.bear_docs = data.get("bear", [])
            self._rebuild_bull_index()
            self._rebuild_bear_index()
```

- [ ] **Step 3: 验证MemoryBank存储和检索**

```bash
python -c "
from services.memory_bank import MemoryBank
mb = MemoryBank(memory_dir='memory')

# 存储一条多头记录
mb.store(
    situation={'stock_code': '600519', 'stock_name': '贵州茅台', 'regime': 'BULL', 'pe': 25, 'roe': 30, 'industry': '白酒', 'pl_pct': 5.0},
    decision={'verdict': '买入', 'confidence': 0.8},
    outcome={'return_pct': 10.0, 'correct': True},
)

# 检索
result = mb.retrieve({'stock_code': '600519', 'stock_name': '贵州茅台', 'regime': 'BULL', 'pe': 26, 'roe': 29, 'industry': '白酒', 'pl_pct': 3.0})
print(f'Found {result.data[\"count\"]} memories')
for m in result.data['memories']:
    print(f'  {m[\"id\"]}: {m[\"decision_type\"]} -> {m[\"outcome_pct\"]:+.1f}%')
"
```

Expected: `Found 1 memories` + 输出买入记录的详情。

- [ ] **Step 4: Commit**

```bash
git add services/memory_bank.py
git commit -m "feat: implement MemoryBank with BM25 dual-index (bull/bear isolation)"
```

---

### Task 1.4: 实现量化子分析函数库（19大师纯Py计算）

**Files:**
- Create: `services/quant_analyzers.py`

- [ ] **Step 1: 写核心分析函数**

`services/quant_analyzers.py`:

```python
"""19位投资大师纯Python量化子分析 — 来源: ai-hedge-fund"""
from typing import Dict, List, Any
import math


class QuantAnalyzers:
    """纯Python量化分析函数库，无需LLM调用"""

    def analyze_all(self, stock_code: str, financials: Dict, prices: List[float]) -> List[Dict]:
        """对所有持仓/目标股票运行全部分析师"""
        results = []
        for method in [self.buffett_analyze, self.graham_analyze, self.lynch_analyze,
                       self.taleb_analyze, self.munger_analyze, self.pabrai_analyze]:
            try:
                result = method(stock_code, financials)
                results.append(result)
            except Exception:
                pass
        return results

    def buffett_analyze(self, stock_code: str, f: Dict) -> Dict:
        """巴菲特框架：ROE + 安全边际 + 护城河评分"""
        roe = f.get("roe", 0)
        debt_equity = f.get("debt_to_equity", 100)
        gross_margin = f.get("gross_margin", 0)
        eps = f.get("eps", 0)
        bvps = f.get("bvps", 0)
        price = f.get("price", 1)

        # 1. ROE评分（>15%加分，<10%减分）
        roe_score = min(40, max(0, (roe - 10) * 4))

        # 2. 安全边际（格雷厄姆数值法）
        graham_number = math.sqrt(22.5 * max(eps, 0.01) * max(bvps, 0.01))
        safety_margin = (graham_number - price) / graham_number * 100 if graham_number > 0 else -100
        margin_score = min(30, max(0, safety_margin + 50))  # 将-50%~+50%映射到0-30

        # 3. 护城河评分
        moat_score = 0
        if gross_margin > 40:
            moat_score += 10
        if debt_equity < 50:
            moat_score += 10
        if roe > 15:
            moat_score += 10

        total = roe_score + margin_score + moat_score
        return {
            "analyst": "buffett",
            "stock_code": stock_code,
            "score": min(100, total),
            "signal": "bullish" if total >= 60 else "bearish" if total < 30 else "neutral",
            "details": {
                "roe": roe, "roe_score": roe_score,
                "graham_number": round(graham_number, 2),
                "safety_margin_pct": round(safety_margin, 1),
                "margin_score": margin_score,
                "moat_score": moat_score,
            }
        }

    def graham_analyze(self, stock_code: str, f: Dict) -> Dict:
        """格雷厄姆框架：净流动资产 + 防御型标准"""
        current_assets = f.get("current_assets", 0)
        total_liabilities = f.get("total_liabilities", 1)
        shares = f.get("shares_outstanding", 1)
        price = f.get("price", 1)
        pe = f.get("pe_ratio", 100)

        ncav = (current_assets - total_liabilities) / shares
        ncav_discount = (ncav - price) / price * 100 if price > 0 else 0
        pe_ok = pe < 15

        score = 0
        if ncav > price * 0.67:
            score += 50
        elif ncav > 0:
            score += 20
        if pe_ok:
            score += 30

        return {
            "analyst": "graham",
            "stock_code": stock_code,
            "score": min(100, score),
            "signal": "bullish" if score >= 60 else "bearish" if score < 30 else "neutral",
            "details": {
                "ncav_per_share": round(ncav, 2),
                "ncav_discount_pct": round(ncav_discount, 1),
                "pe_ok": pe_ok,
            }
        }

    def lynch_analyze(self, stock_code: str, f: Dict) -> Dict:
        """彼得·林奇框架：PEG + 业务简单性"""
        pe = f.get("pe_ratio", 100)
        earnings_growth = f.get("earnings_growth_3y", 5)
        peg = pe / max(earnings_growth, 0.1)

        score = 0
        if peg < 0.5:
            score += 50
        elif peg < 1.0:
            score += 35
        elif peg < 1.5:
            score += 20

        if earnings_growth > 15:
            score += 25
        elif earnings_growth > 10:
            score += 15

        return {
            "analyst": "lynch",
            "stock_code": stock_code,
            "score": min(100, score),
            "signal": "bullish" if score >= 50 else "neutral",
            "details": {
                "peg": round(peg, 2),
                "earnings_growth_3y": earnings_growth,
                "pe": pe,
            }
        }

    def taleb_analyze(self, stock_code: str, f: Dict) -> Dict:
        """塔勒布框架：反脆弱性 + 尾部风险"""
        debt_equity = f.get("debt_to_equity", 100)
        cash_ratio = f.get("cash_to_assets", 10)
        # 反脆弱评分：低杠杆 + 高现金 + 高毛利率
        anti_fragile = 0
        if debt_equity < 30:
            anti_fragile += 35
        elif debt_equity < 60:
            anti_fragile += 20
        if cash_ratio > 20:
            anti_fragile += 35
        elif cash_ratio > 10:
            anti_fragile += 20
        if f.get("gross_margin", 0) > 40:
            anti_fragile += 30

        return {
            "analyst": "taleb",
            "stock_code": stock_code,
            "score": min(100, anti_fragile),
            "signal": "bullish" if anti_fragile >= 60 else "bearish" if anti_fragile < 30 else "neutral",
            "details": {
                "debt_equity": debt_equity,
                "cash_to_assets": cash_ratio,
                "anti_fragile_score": anti_fragile,
            }
        }

    def munger_analyze(self, stock_code: str, f: Dict) -> Dict:
        """芒格框架：ROIC稳定性 + 管理层质量代理"""
        roe = f.get("roe", 0)
        roe_stability = f.get("roe_stability_5y", 5)  # 5年ROE标准差
        insider_holding = f.get("insider_holding_pct", 0)

        score = 0
        if roe > 15:
            score += 35
        elif roe > 10:
            score += 20
        if roe_stability < 3:  # ROE波动小
            score += 30
        if insider_holding > 5:
            score += 20
        elif insider_holding > 1:
            score += 10

        return {
            "analyst": "munger",
            "stock_code": stock_code,
            "score": min(100, score),
            "signal": "bullish" if score >= 55 else "neutral",
            "details": {
                "roe": roe,
                "roe_stability_5y": roe_stability,
                "insider_holding_pct": insider_holding,
            }
        }

    def pabrai_analyze(self, stock_code: str, f: Dict) -> Dict:
        """帕布莱框架：低风险高回报不对称机会"""
        price = f.get("price", 1)
        book_value = f.get("bvps", 1)
        roe = f.get("roe", 0)

        pb = price / max(book_value, 0.01)
        score = 0
        if pb < 1.0:
            score += 40
        elif pb < 1.5:
            score += 25
        if roe > 15:
            score += 35
        elif roe > 10:
            score += 20

        # 不对称性：低PB+高ROE=高得分
        return {
            "analyst": "pabrai",
            "stock_code": stock_code,
            "score": min(100, score),
            "signal": "bullish" if score >= 55 else "neutral",
            "details": {
                "pb": round(pb, 2),
                "roe": roe,
            }
        }
```

- [ ] **Step 2: 验证分析函数**

```bash
python -c "
from services.quant_analyzers import QuantAnalyzers
qa = QuantAnalyzers()
fake_financials = {
    'roe': 18, 'debt_to_equity': 35, 'gross_margin': 55,
    'eps': 5.2, 'bvps': 28, 'price': 120,
    'current_assets': 500e8, 'total_liabilities': 300e8,
    'shares_outstanding': 12.5e8, 'pe_ratio': 23,
    'earnings_growth_3y': 12, 'cash_to_assets': 15,
    'roe_stability_5y': 2.5, 'insider_holding_pct': 3,
}
results = qa.analyze_all('600519', fake_financials, [])
for r in results:
    print(f'{r[\"analyst\"]}: score={r[\"score\"]} signal={r[\"signal\"]}')
print(f'Total: {len(results)} analysts')
"
```

Expected: 6个分析师的评分和信号输出。

- [ ] **Step 3: Commit**

```bash
git add services/quant_analyzers.py
git commit -m "feat: implement 6 quantitative sub-analysis functions (Buffett/Graham/Lynch/Taleb/Munger/Pabrai)"
```

---

### Task 1.5: 实现 DebateEngine（多空辩论引擎）

**Files:**
- Create: `services/debate_engine.py`

- [ ] **Step 1: 写辩论引擎核心**

`services/debate_engine.py`:

```python
"""多空辩论引擎 — 来源: TradingAgents-AShare"""
import json
import re
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from services.base import ServiceResult, BaseService
from services.memory_bank import MemoryBank
from services.quant_analyzers import QuantAnalyzers


class Claim:
    """辩论声明"""
    def __init__(self, claim_id: str, text: str, source: str, confidence: float,
                 evidence: List[str], author: str, round_num: int):
        self.id = claim_id
        self.text = text
        self.source = source       # "bull_fundamental" | "bear_technical" | "analyst_report"
        self.confidence = confidence
        self.evidence = evidence
        self.author = author
        self.round = round_num
        self.status = "open"       # open → addressed → resolved / unresolved

    def to_dict(self) -> Dict:
        return {k: v for k, v in self.__dict__.items()}


class DebateEngine(BaseService):
    """多空辩论引擎 — 双库隔离 + 来源差异化 + 同质化门控"""

    MAX_ROUNDS = 2
    SOURCE_OVERLAP_THRESHOLD = 0.5  # 来源重合率>50%判定为低信息增量

    def __init__(self, memory_bank: MemoryBank = None):
        super().__init__()
        self.memory_bank = memory_bank or MemoryBank()
        self.quant = QuantAnalyzers()

    def run_debate(
        self,
        stock_code: str,
        analyst_reports: List[Dict],
        market_context: Dict,
        max_rounds: int = 2
    ) -> ServiceResult:
        """运行完整的多空辩论+风控辩论"""
        try:
            claims: List[Claim] = []
            bull_history: List[str] = []
            bear_history: List[str] = []

            # ── 第1步: 构建context ──
            stock_name = market_context.get("stock_name", stock_code)
            situation = self._build_situation(stock_code, stock_name, analyst_reports, market_context)

            # ── 第2步: 检索记忆（双库分别检索）──
            bull_memories = self.memory_bank.retrieve({**situation, "intent": "buy"}, top_k=3, bank="bull")
            bear_memories = self.memory_bank.retrieve({**situation, "intent": "sell"}, top_k=3, bank="bear")

            # ── 第3步: 辩论循环 ──
            round_goals = [
                "建立最核心的正反两方声明",
                "优先攻击对手最脆弱的假设",
                "围绕时间窗口与触发条件判断交易时机是否成立",
                "围绕失败路径与失效条件检查",
            ]

            for r in range(max_rounds):
                round_num = r + 1
                goal = round_goals[min(r, len(round_goals) - 1)]

                # 多头回合
                bull_claim = self._bull_turn(
                    stock_code, stock_name, analyst_reports, market_context,
                    claims, bull_history, bear_history,
                    bull_memories.data.get("memories", []),
                    goal, round_num
                )
                if bull_claim:
                    claims.append(bull_claim)
                    bull_history.append(bull_claim.text)

                # 空头回合（强制负面挖掘）
                bear_claim = self._bear_turn(
                    stock_code, stock_name, analyst_reports, market_context,
                    claims, bull_history, bear_history,
                    bear_memories.data.get("memories", []),
                    goal, round_num
                )
                if bear_claim:
                    claims.append(bear_claim)
                    bear_history.append(bear_claim.text)

            # ── 第4步: 同质化检测 ──
            overlap_ratio = self._calc_source_overlap(claims)
            low_info = overlap_ratio > self.SOURCE_OVERLAP_THRESHOLD

            # ── 第5步: 裁决 ──
            verdict = self._judge(
                stock_code, stock_name, analyst_reports, market_context,
                claims, bull_history, bear_history
            )

            # 低信息增量→置信度降一档
            if low_info:
                verdict["confidence"] = min(verdict["confidence"] * 0.7, 0.5)
                verdict["low_information_debate"] = True

            return ServiceResult.ok(data={
                "verdict": verdict["verdict"],
                "confidence": verdict["confidence"],
                "target_price": verdict.get("target_price"),
                "invalidation_condition": verdict.get("invalidation"),
                "claims": [c.to_dict() for c in claims],
                "source_overlap_ratio": round(overlap_ratio, 2),
                "low_information_debate": low_info,
                "bull_rounds": len(bull_history),
                "bear_rounds": len(bear_history),
            })
        except Exception as e:
            return ServiceResult.degraded(
                data={"verdict": "持有", "confidence": 0.3, "error": str(e)},
                errors=[f"DebateEngine failed, fallback to HOLD: {e}"]
            )

    def _build_situation(self, stock_code, stock_name, reports, context) -> Dict:
        return {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "regime": context.get("regime", "NEUTRAL"),
            "pe": context.get("pe", 0),
            "roe": context.get("roe", 0),
            "industry": context.get("industry", ""),
            "pl_pct": context.get("pl_pct", 0),
        }

    def _bull_turn(self, code, name, reports, context, claims, bull_hist, bear_hist,
                   memories, goal, round_num) -> Optional[Claim]:
        """多头研究员 — 仅使用bull_fundamental/analyst_report来源"""
        # 构建多头声明（基于基本面和正面分析师报告）
        fundamental_reports = [r for r in reports if r.get("category") in ("value", "analysis")]
        memory_texts = [m.get("situation_text", "") for m in memories if m.get("outcome_correct")]

        claim_text = f"从基本面角度，{name}具备投资价值。"
        evidence = []
        for r in fundamental_reports[:3]:
            key_finding = str(r.get("analysis_prompt", ""))[:120]
            if key_finding:
                evidence.append(key_finding)
        for mt in memory_texts[:2]:
            evidence.append(f"[历史成功案例] {mt[:80]}")

        return Claim(
            claim_id=f"BULL-{round_num}-{uuid.uuid4().hex[:6]}",
            text=claim_text[:200],
            source="bull_fundamental",
            confidence=0.7,
            evidence=evidence,
            author="BullResearcher",
            round_num=round_num,
        )

    def _bear_turn(self, code, name, reports, context, claims, bull_hist, bear_hist,
                   memories, goal, round_num) -> Optional[Claim]:
        """空头研究员 — 强制使用bear_technical来源"""
        failure_memories = [m for m in memories if not m.get("outcome_correct", True)]
        technical_reports = [r for r in reports if r.get("category") in ("analysis", "risk")]

        # 强制负面挖掘
        evidence = []
        for m in failure_memories[:2]:
            evidence.append(f"[历史失败信号] {m.get('situation_text', '')[:80]}")
        for r in technical_reports[:2]:
            risk_info = str(r.get("alerts", ""))[:100] if "alerts" in r else str(r)[:100]
            if risk_info:
                evidence.append(risk_info)

        # 如果没有失败记忆，必须标注
        if not failure_memories:
            evidence.append("[无历史失败记忆] 本次为空头首次分析该场景")

        claim_text = f"从技术面和风险角度，{name}面临下行风险。"
        return Claim(
            claim_id=f"BEAR-{round_num}-{uuid.uuid4().hex[:6]}",
            text=claim_text[:200],
            source="bear_technical",
            confidence=0.65,
            evidence=evidence,
            author="BearResearcher",
            round_num=round_num,
        )

    def _judge(self, code, name, reports, context, claims, bull_hist, bear_hist) -> Dict:
        """研究经理裁决 — 基于声明来源多样性和一致性"""
        if not claims:
            return {"verdict": "持有", "confidence": 0.4, "reasoning": "无有效声明"}

        bull_scores = [c.confidence for c in claims if c.author == "BullResearcher"]
        bear_scores = [c.confidence for c in claims if c.author == "BearResearcher"]

        avg_bull = sum(bull_scores) / len(bull_scores) if bull_scores else 0.5
        avg_bear = sum(bear_scores) / len(bear_scores) if bear_scores else 0.5

        # 来源多样性加分
        sources = set(c.source for c in claims)
        diversity_bonus = min(0.1, len(sources) * 0.03)

        if avg_bull > avg_bear + 0.15:
            return {"verdict": "买入", "confidence": min(1.0, avg_bull + diversity_bonus),
                    "reasoning": f"多头一致性高(bull={avg_bull:.2f}, bear={avg_bear:.2f})"}
        elif avg_bear > avg_bull + 0.15:
            return {"verdict": "卖出", "confidence": min(1.0, avg_bear + diversity_bonus),
                    "reasoning": f"空头信号主导(bull={avg_bull:.2f}, bear={avg_bear:.2f})"}
        return {"verdict": "持有", "confidence": 0.5,
                "reasoning": f"多空分歧小(bull={avg_bull:.2f}, bear={avg_bear:.2f})"}

    def _calc_source_overlap(self, claims: List[Claim]) -> float:
        """计算多头和空头的证据来源重合率"""
        bull_sources = set()
        bear_sources = set()
        for c in claims:
            if c.author == "BullResearcher":
                bull_sources.add(c.source)
            elif c.author == "BearResearcher":
                bear_sources.add(c.source)
        if not bull_sources or not bear_sources:
            return 0.0
        intersection = bull_sources & bear_sources
        union = bull_sources | bear_sources
        return len(intersection) / len(union) if union else 0.0
```

- [ ] **Step 2: 单元测试 — 验证辩论流程**

```bash
python -c "
from services.debate_engine import DebateEngine
from services.memory_bank import MemoryBank

mb = MemoryBank(memory_dir='memory')
engine = DebateEngine(memory_bank=mb)

result = engine.run_debate(
    stock_code='600519',
    analyst_reports=[
        {'category': 'value', 'analysis_prompt': 'ROE 18%, PE 25x, 白酒行业龙头'},
        {'category': 'risk', 'alerts': [{'level': 'WARNING', 'message': '消费降级风险'}]},
    ],
    market_context={'stock_name': '贵州茅台', 'regime': 'NEUTRAL', 'pe': 25, 'roe': 18, 'industry': '白酒', 'pl_pct': 5.0},
    max_rounds=2,
)

print(f'Verdict: {result.data[\"verdict\"]}')
print(f'Confidence: {result.data[\"confidence\"]:.2f}')
print(f'Claims: {len(result.data[\"claims\"])}')
print(f'Source overlap: {result.data[\"source_overlap_ratio\"]:.2f}')
print(f'Low info debate: {result.data[\"low_information_debate\"]}')
print(f'Status: {result.status}')
"
```

Expected: 输出裁决结果，至少4个声明，来源重合率应较低（多头用fundamental，空头用technical）。

- [ ] **Step 3: Commit**

```bash
git add services/debate_engine.py
git commit -m "feat: implement DebateEngine with source-isolated bull/bear claims"
```

---

### Task 1.6: 在 ServiceContainer 中注册阶段1服务

**Files:**
- Modify: `super_workflow.py` (`ServiceContainer.__init__`)

- [ ] **Step 1: 更新 ServiceContainer**

```python
def __init__(self):
    from services.market_perception import MarketPerception
    from services.memory_bank import MemoryBank
    from services.debate_engine import DebateEngine
    from services.quant_analyzers import QuantAnalyzers

    self.market_perception = MarketPerception()
    self.memory_bank = MemoryBank(memory_dir="memory")
    self.quant_analyzers = QuantAnalyzers()
    self.debate_engine = DebateEngine(memory_bank=self.memory_bank)
    self.factor_farm = None
    self.risk_engine = None
    self.portfolio_optimizer = None
    self.trade_executor = None
```

- [ ] **Step 2: 验证全部阶段1服务可初始化**

```bash
python -c "
from super_workflow import get_services
svc = get_services()
assert svc.market_perception is not None
assert svc.memory_bank is not None
assert svc.quant_analyzers is not None
assert svc.debate_engine is not None
assert svc.is_ready('market_perception', 'memory_bank', 'quant_analyzers', 'debate_engine')
print('All Phase 1 services initialized OK')
"
```

Expected: `All Phase 1 services initialized OK`

- [ ] **Step 3: Commit**

```bash
git add super_workflow.py
git commit -m "feat: register all Phase 1 services in ServiceContainer"
```

---

### Task 1.7: 新增 `node_debate_committee` 节点并接入工作流

**Files:**
- Modify: `super_workflow.py`

- [ ] **Step 1: 新增辩论节点函数**

在 `super_workflow.py` 中添加：

```python
def node_debate_committee(state: AShareSuperState) -> dict:
    """节点：多空辩论委员会"""
    logs = list(state.get("logs", []))
    errors = list(state.get("errors", []))
    logs.append(_log(state, "⚔️ [辩论] 多空辩论委员会启动..."))

    services = get_services()
    if not services.is_ready("debate_engine"):
        logs.append(_log(state, "⏭️ DebateEngine未就绪，跳过辩论"))
        return {"logs": logs}

    portfolio = state.get("portfolio", [])
    market_data = state.get("market_data", {})
    perception = market_data.get("_perception", {})
    skill_outputs = state.get("skill_outputs", {})
    stock_info_map = state.get("_stock_info_map", {})

    debate_results = {}
    debate_stats = {"bull_wins": 0, "bear_wins": 0, "hold": 0, "low_info_count": 0}

    for h in portfolio:
        code = h.get("stock_code", "")
        name = h.get("stock_name", "")

        # 收集该股票的分析报告
        stock_reports = []
        for skill_name, results in skill_outputs.items():
            items = results if isinstance(results, list) else [results]
            for r in items:
                if isinstance(r, dict) and r.get("stock_code") == code:
                    stock_reports.append(r)

        si = stock_info_map.get(code, {})

        result = services.debate_engine.run_debate(
            stock_code=code,
            analyst_reports=stock_reports,
            market_context={
                "stock_name": name,
                "regime": perception.get("regime", "NEUTRAL"),
                "pe": si.get("pe", 0),
                "roe": si.get("roe", 0),
                "industry": si.get("industry", ""),
                "pl_pct": h.get("profit_loss_pct", 0),
            },
            max_rounds=2,
        )

        debate_results[code] = result.data
        verdict = result.data.get("verdict", "持有")
        if verdict == "买入":
            debate_stats["bull_wins"] += 1
        elif verdict == "卖出":
            debate_stats["bear_wins"] += 1
        else:
            debate_stats["hold"] += 1
        if result.data.get("low_information_debate"):
            debate_stats["low_info_count"] += 1

        logs.append(_log(state,
            f"  {name}({code}): {verdict} "
            f"(置信度{result.data.get('confidence', 0):.0%}, "
            f"声明{len(result.data.get('claims', []))}个, "
            f"来源重合{result.data.get('source_overlap_ratio', 0):.0%})"
        ))

    logs.append(_log(state,
        f"✅ 辩论完成: 买入{debate_stats['bull_wins']} 卖出{debate_stats['bear_wins']} "
        f"持有{debate_stats['hold']} 低信息增量{debate_stats['low_info_count']}"
    ))

    return {"logs": logs, "debate_results": debate_results}
```

- [ ] **Step 2: 修改 `build_super_workflow` 添加辩论节点**

在 `build_super_workflow` 中：

```python
# 添加节点
workflow.add_node("debate_committee", node_debate_committee)

# 修改边：skill_analysis_parallel → debate_committee → ai_hedge_fund_vote
# 原: workflow.add_edge("skill_analysis_parallel", "ai_hedge_fund_vote")
workflow.add_edge("skill_analysis_parallel", "debate_committee")
workflow.add_edge("debate_committee", "ai_hedge_fund_vote")
```

- [ ] **Step 3: 在 `run_super_workflow` 的nodes列表中添加辩论节点**

```python
nodes = [
    ("fetch_global_data", "📡 获取全局市场数据"),
    ("skill_analysis_parallel", "🧠 Skill 并行分析"),
    ("debate_committee", "⚔️ 多空辩论委员会"),        # ← 新增
    ("ai_hedge_fund_vote", "🏛️ AI 对冲基金投委会投票"),
    # ... 其余节点不变
]
```

- [ ] **Step 4: 验证工作流拓扑**

```bash
python -c "
from super_workflow import build_super_workflow
wf = build_super_workflow()
print('Workflow nodes:', list(wf.nodes.keys()))
print('Debate node in workflow:', 'debate_committee' in wf.nodes)
"
```

Expected: 输出包含 `debate_committee` 节点。

- [ ] **Step 5: Commit**

```bash
git add super_workflow.py
git commit -m "feat: add debate_committee node to super workflow"
```

---

### Task 1.8: 端到端集成测试（阶段1）

**Files:**
- Create: `tests/test_integration_phase1.py`

- [ ] **Step 1: 写集成测试**

```python
"""阶段1端到端集成测试"""
import pytest


class TestPhase1Services:
    """验证阶段1全部服务可初始化和协同工作"""

    def test_all_services_initialize(self):
        from super_workflow import get_services
        svc = get_services()
        assert svc.market_perception is not None
        assert svc.memory_bank is not None
        assert svc.quant_analyzers is not None
        assert svc.debate_engine is not None

    def test_market_perception_returns_valid_regime(self):
        from services.market_perception import MarketPerception
        mp = MarketPerception()
        result = mp.perceive({
            "breadth": {"up": 2000, "down": 2500, "total": 5000, "limit_up": 30, "limit_down": 40},
            "indices": {},
        })
        assert result.status == "ok"
        assert result.data["regime"] in ("BULL", "BEAR", "NEUTRAL", "PANIC", "OVERHEAT")
        assert -2.0 <= result.data["total_score"] <= 2.0

    def test_memory_bank_store_and_retrieve(self):
        from services.memory_bank import MemoryBank
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            mb = MemoryBank(memory_dir=tmp)
            mb.store(
                {"stock_code": "000001", "stock_name": "平安银行", "regime": "BULL",
                 "pe": 8, "roe": 12, "industry": "银行", "pl_pct": 3.0},
                {"verdict": "买入", "confidence": 0.75},
                {"return_pct": 5.0, "correct": True},
            )
            result = mb.retrieve({"stock_code": "000001", "stock_name": "平安银行",
                                  "regime": "BULL", "pe": 9, "roe": 11, "industry": "银行", "pl_pct": 2.0})
            assert result.status == "ok"
            assert result.data["count"] >= 1

    def test_quant_analyzers_all_return_scored_results(self):
        from services.quant_analyzers import QuantAnalyzers
        qa = QuantAnalyzers()
        f = {"roe": 18, "debt_to_equity": 35, "gross_margin": 55, "eps": 5.2,
             "bvps": 28, "price": 120, "current_assets": 5e10, "total_liabilities": 3e10,
             "shares_outstanding": 1.25e9, "pe_ratio": 23, "earnings_growth_3y": 12,
             "cash_to_assets": 15, "roe_stability_5y": 2.5, "insider_holding_pct": 3}
        results = qa.analyze_all("000001", f, [])
        assert len(results) >= 4
        for r in results:
            assert 0 <= r["score"] <= 100
            assert r["signal"] in ("bullish", "bearish", "neutral")

    def test_debate_engine_produces_verdict(self):
        from services.debate_engine import DebateEngine
        from services.memory_bank import MemoryBank
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            mb = MemoryBank(memory_dir=tmp)
            engine = DebateEngine(memory_bank=mb)
            result = engine.run_debate(
                "600519",
                [{"category": "value", "analysis_prompt": "ROE高"},
                 {"category": "risk", "alerts": []}],
                {"stock_name": "茅台", "regime": "NEUTRAL", "pe": 25, "roe": 18,
                 "industry": "白酒", "pl_pct": 5.0},
            )
            assert result.status in ("ok", "degraded")
            assert result.data["verdict"] in ("买入", "卖出", "持有")
            assert 0 <= result.data["confidence"] <= 1

    def test_source_isolation_no_cross_contamination(self):
        """验证多头/空头记忆库物理隔离"""
        from services.memory_bank import MemoryBank
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            mb = MemoryBank(memory_dir=tmp)
            # 存一条买入记录 → 进bull库
            mb.store(
                {"stock_code": "000001", "stock_name": "测试", "regime": "BULL",
                 "pe": 10, "roe": 15, "industry": "银行", "pl_pct": 3.0},
                {"verdict": "买入", "confidence": 0.8},
                {"return_pct": 10.0, "correct": True},
            )
            # 空头检索bull库 → 应该为空
            result = mb.retrieve(
                {"stock_code": "000001", "stock_name": "测试", "regime": "BULL",
                 "pe": 10, "roe": 15, "industry": "银行", "pl_pct": 3.0, "intent": "sell"},
                top_k=5, bank="bear"
            )
            assert result.data["count"] == 0, "空头不应检索到多头记忆"
```

- [ ] **Step 2: 运行集成测试**

```bash
python -m pytest tests/test_integration_phase1.py -v
```

Expected: 6 tests passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration_phase1.py
git commit -m "test: add Phase 1 integration tests for all 4 new services"
```

---

## 阶段2：自动化进化（任务概要）

### Task 2.1: 实现 FactorFarm 核心（假说生成+代码生成+沙箱评估）

- [ ] 实现 `services/factor_farm.py`（HypothesisGenerator / FactorCoder / FactorEvaluator / FactorLibrary）
- [ ] 导入初始因子库（QuantLLM 28个 + 经典10个）
- [ ] 实现IC评估 + 去重 + SQLite存储
- [ ] 单元测试：验证一个因子发现→评估的完整流程

### Task 2.2: 实现 YAML策略加载器

- [ ] 实现 `services/strategy_loader.py`（YAML解析+表达式沙箱+5项前视偏差审计）
- [ ] 加载并验证 `strategies/ma_golden_cross.yaml`
- [ ] 单元测试：合法YAML通过、非法表达式被拒绝、前视偏差被检测

### Task 2.3: 实现 BacktestLoop 工作流

- [ ] 实现 `services/backtest_loop.py`（7节点LangGraph工作流）
- [ ] 集成 BanditAllocator（Thompson采样）
- [ ] 集成测试：完整回测循环运行

---

## 阶段3：实盘执行（任务概要）

### Task 3.1: 实现 TradeExecutor

- [ ] 实现 `services/trade_executor.py`（OrderGenerator + SimulatedExecution + PositionTracker + KillSwitch）
- [ ] 成本感知过滤（edge_after_cost > 0）
- [ ] T+1约束 + 涨跌停限制
- [ ] KillSwitch熔断逻辑

### Task 3.2: 增强 RiskEngine

- [ ] 实现 `services/risk_engine.py`（波动率调整 + 相关性矩阵 + 压力测试）
- [ ] 在 ServiceContainer 中替换 RiskFirewall

### Task 3.3: 增强 PortfolioOptimizer

- [ ] 实现 `services/portfolio_optimizer.py`（ConstraintPrecomputer + SignalAggregator + RebalanceEngine）
- [ ] LLM仅在>1种选择时调用（预填充优化）

### Task 3.4: 双模式切换 + T+5复盘

- [ ] 半自动/全自动模式切换逻辑
- [ ] T+5复盘 → MemoryBank.store() 定时任务

---

## 阶段4：清理收尾（任务概要）

### Task 4.1: 移除废弃代码

- [ ] 移除 `optimizations.py` 中已被替代的逻辑
- [ ] 移除 `skills.py` 中的内置分析
- [ ] 移除 `decision_review.py`
- [ ] 移除 `multi_model_voter.py`

### Task 4.2: 更新文档和集成测试

- [ ] 更新 `SKILL.md`
- [ ] 编写 `docs/architecture.md`
- [ ] 端到端集成测试（3个交易日数据回放）

---

## 测试策略总结

| 阶段 | 测试类型 | 覆盖目标 |
|------|---------|---------|
| 阶段0 | 导入测试 | 所有新文件可导入 |
| 阶段1 | 单元测试 + 集成测试 | 每个服务3+测试用例；服务间协作测试 |
| 阶段2 | 单元测试 + 回测验证 | 因子评估管线；YAML审计规则 |
| 阶段3 | 集成测试 + 模拟盘验证 | 订单生成→执行→复盘完整链路 |
| 阶段4 | 端到端测试 + 回归测试 | 3日历史数据回放；无功能退化 |

---

## 关键依赖提醒

- `jieba` + `rank-bm25` → 阶段1安装
- `pyyaml` → 阶段2安装（通常已安装）
- SQLite → Python内置，无需额外安装
- 所有新服务与现有基础设施层**零耦合**，通过 ServiceContainer 注入
- 现有工作流在阶段0完工前**行为完全不变**
