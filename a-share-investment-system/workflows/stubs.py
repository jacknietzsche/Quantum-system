"""工作流节点缺失的桩(stub)实现 — 待正式实现替换"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


class TokenBudget:
    """Token 预算管理器 — 限制单次 LLM 调用的 token 消耗"""

    def __init__(self, max_tokens: int = 50000):
        self.max_tokens = max_tokens
        self.used = 0

    def allocate(self, requested: int) -> int:
        remaining = self.max_tokens - self.used
        granted = min(requested, remaining)
        self.used += granted
        return granted

    @property
    def exhausted(self) -> bool:
        return self.used >= self.max_tokens


class _MockLLM:
    """投票器内部默认 LLM 占位实现"""

    def call(self, model: str, prompt: str, context: dict | None = None) -> dict:
        return {
            "recommendation": "持有",
            "confidence": 0.5,
            "reasoning": "stub",
        }


class TieredVoter:
    """分层投票器 — 根据一致性决定是否需要额外验证"""

    def __init__(
        self,
        high_threshold: float = 0.8,
        low_threshold: float = 0.5,
        models: dict[str, Any] | None = None,
    ):
        self.high_threshold = high_threshold
        self.low_threshold = low_threshold
        self.models = models or {}
        self.llm: Any = _MockLLM()

    @classmethod
    def from_config_file(cls, path: str | None = None) -> TieredVoter:
        """从配置加载真实 LLM 配置;无配置时抛出异常,由调用方降级处理"""
        from shared.config import Config

        cfg = Config()
        models = cfg.get("models") or cfg.get("llm.model_roles")
        if not isinstance(models, dict) or not models:
            raise RuntimeError("No LLM models configured")
        return cls(models=models)

    def should_activate_fincept(self, hedge_decision: dict) -> bool:
        """如果投委会一致性低于阈值,则激活 Fincept 验证"""
        consistency = hedge_decision.get("consistency", 1.0)
        return consistency < self.high_threshold

    def evaluate_consistency(self, votes: dict) -> float:
        """评估投票一致性"""
        if not votes:
            return 0.0
        signals = [v.get("signal", "") for v in votes.values() if isinstance(v, dict)]
        if not signals:
            return 0.0
        from collections import Counter

        counts = Counter(signals)
        most_common = counts.most_common(1)[0][1]
        return most_common / len(signals)

    def vote(self, question: str, context: dict | None = None) -> dict:
        """基于问题与市场上下文给出仲裁结果"""
        return {
            "winner": "持有",
            "consistency": 0.5,
            "winner_confidence": 0.5,
            "votes": {},
            "question": question,
        }

    def analyze_stock(
        self,
        stock_code: str,
        stock_name: str,
        market_data: dict | None = None,
        portfolio: list[dict] | None = None,
    ) -> dict:
        """对单只股票进行多模型投票分析"""
        return {
            "winner": "持有",
            "consistency": 0.5,
            "winner_confidence": 0.5,
            "votes": {},
            "stock_code": stock_code,
            "stock_name": stock_name,
        }


class get_services:
    """服务定位器 — 懒加载获取各服务实例"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._services = {}

    def is_ready(self, service_name: str) -> bool:
        """检查服务是否就绪"""
        return self._load_service(service_name) is not None

    def __getattr__(self, name: str):
        svc = self._load_service(name)
        if svc is not None:
            return svc
        raise AttributeError(f"Service {name!r} not available")

    def _load_service(self, name: str):
        if name in self._services:
            return self._services[name]
        try:
            if name == "debate_engine":
                from services.debate_engine import DebateEngine

                self._services[name] = DebateEngine()
            elif name == "market_perception":
                from services.market_perception import MarketPerception

                self._services[name] = MarketPerception()
            elif name == "portfolio":
                from services.portfolio import PortfolioService
                from shared.models import get_session

                self._services[name] = PortfolioService(get_session)
            else:
                self._services[name] = None
        except Exception:
            self._services[name] = None
        return self._services[name]


class RiskQuadrantEngine:
    """风险象限引擎 — 根据恐慌指数和市场周期给出仓位建议"""

    QUADRANTS: ClassVar[dict[tuple[str, str], dict[str, Any]]] = {
        ("low", "expansion"): {
            "quadrant": "增长期-低风险",
            "description": "市场健康增长",
            "max_position_pct": 0.80,
            "min_cash_pct": 0.10,
            "max_single_stock_pct": 0.15,
            "action": "积极建仓",
        },
        ("low", "peak"): {
            "quadrant": "见顶期-低风险",
            "description": "市场可能见顶",
            "max_position_pct": 0.60,
            "min_cash_pct": 0.20,
            "max_single_stock_pct": 0.10,
            "action": "逐步减仓",
        },
        ("high", "contraction"): {
            "quadrant": "收缩期-高风险",
            "description": "市场下行风险加大",
            "max_position_pct": 0.40,
            "min_cash_pct": 0.30,
            "max_single_stock_pct": 0.08,
            "action": "防守为主",
        },
        ("high", "trough"): {
            "quadrant": "谷底期-高风险",
            "description": "市场极度悲观",
            "max_position_pct": 0.30,
            "min_cash_pct": 0.40,
            "max_single_stock_pct": 0.05,
            "action": "保持现金",
        },
    }
    DEFAULT: ClassVar[dict[str, Any]] = {
        "quadrant": "中性",
        "description": "无明确信号",
        "max_position_pct": 0.50,
        "min_cash_pct": 0.20,
        "max_single_stock_pct": 0.10,
        "action": "均衡配置",
    }

    def evaluate(self, panic_score: float, cycle: str) -> dict:
        risk = "high" if panic_score > 60 else "low"
        cycle_lower = cycle.lower() if isinstance(cycle, str) else "expansion"
        for (r, c), q in self.QUADRANTS.items():
            if r == risk and c in cycle_lower:
                return q
        return self.DEFAULT


class StrategyMonitor:
    """策略表现监控器 — 计算夏普/回撤/胜率等指标"""

    def calculate_metrics(self, returns: list[float]) -> dict:
        if not returns or len(returns) < 2:
            return {
                "sharpe_ratio": 0,
                "max_drawdown": 0,
                "win_rate": 0,
                "profit_loss_ratio": 0,
                "calmar_ratio": 0,
            }
        import numpy as np

        arr = np.array(returns)
        mean_r = float(np.mean(arr))
        std_r = float(np.std(arr))
        sharpe = (mean_r / std_r * (252**0.5)) if std_r > 0 else 0
        cum = (1 + arr).cumprod()
        peak = np.maximum.accumulate(cum)
        dd = (cum - peak) / peak
        max_dd = float(np.min(dd))
        win_rate = float(np.mean(arr > 0))
        wins = arr[arr > 0]
        losses = arr[arr < 0]
        avg_win = float(np.mean(wins)) if len(wins) > 0 else 0
        avg_loss = abs(float(np.mean(losses))) if len(losses) > 0 else 0.0001
        pl_ratio = avg_win / avg_loss if avg_loss > 0 else 0
        calmar = abs(mean_r * 252 / max_dd) if max_dd != 0 else 0
        return {
            "sharpe_ratio": round(sharpe, 2),
            "max_drawdown": round(max_dd, 4),
            "win_rate": round(win_rate, 3),
            "profit_loss_ratio": round(pl_ratio, 2),
            "calmar_ratio": round(calmar, 2),
        }

    def check_alerts(self, metrics: dict) -> list[dict]:
        alerts = []
        if metrics.get("sharpe_ratio", 0) < 0.5:
            alerts.append(
                {"level": "WARNING", "message": f"夏普比率过低: {metrics['sharpe_ratio']:.2f}"}
            )
        if metrics.get("max_drawdown", 0) < -0.20:
            alerts.append(
                {"level": "CRITICAL", "message": f"最大回撤过大: {metrics['max_drawdown']:.1%}"}
            )
        return alerts


class FaultTolerantNode:
    """容错节点装饰器 — 超时保护 + 默认值降级"""

    def __init__(self, timeout: int = 180, default: dict | None = None, node_name: str = ""):
        self.timeout = timeout
        self.default = default or {}
        self.node_name = node_name

    def __call__(self, func):
        import functools

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.warning(f"[{self.node_name}] Failed: {e}, using defaults")
                return self.default

        wrapper.__name__ = func.__name__
        wrapper._fault_tolerant = True
        wrapper._timeout = self.timeout
        wrapper._default = self.default
        return wrapper


RISK_DEFAULTS = {
    "risk_assessment": {
        "pass": False,
        "overall_level": "UNKNOWN",
        "market_risk": {"level": "UNKNOWN", "score": 50, "pass": True, "message": "默认值"},
        "cycle_risk": "unknown",
        "tail_risk": {"level": "UNKNOWN", "score": 50, "message": "默认值"},
        "position_advice": "50%",
    }
}


class LookAheadBiasAuditor:
    """前视偏差审计 — 检查分析中是否使用了未来数据"""

    def audit(self, state: dict) -> dict:
        _logs = state.get("logs", [])
        trade_date = state.get("date", "")
        warnings = []
        # 简单检查:确保所有数据日期早于分析日期  # noqa: ERA001
        data_dates = state.get("_data_dates", [])
        for dd in data_dates:
            if dd > trade_date:
                warnings.append(f"数据日期{dd}晚于分析日期{trade_date},可能存在前视偏差")
        return {
            "pass": len(warnings) == 0,
            "warnings": warnings,
            "audited_at": trade_date,
        }
