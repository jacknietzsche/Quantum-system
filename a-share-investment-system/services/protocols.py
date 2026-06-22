"""AShare-X 领域服务接口协议"""

from typing import Protocol, runtime_checkable

from services.base import ServiceResult


@runtime_checkable
class MarketPerceptionProtocol(Protocol):
    def perceive(self, market_data: dict) -> ServiceResult: ...
    def get_position_limits(self) -> ServiceResult: ...
    def is_trading_day(self, date: str | None = None) -> bool: ...


@runtime_checkable
class MemoryBankProtocol(Protocol):
    def store(self, situation: dict, decision: dict, outcome: dict) -> ServiceResult: ...
    def retrieve(self, current_situation: dict, top_k: int = 5) -> ServiceResult: ...
    def inject_into_prompt(self, base_prompt: str, current_situation: dict) -> ServiceResult: ...


@runtime_checkable
class DebateEngineProtocol(Protocol):
    def run_debate(
        self,
        stock_code: str,
        analyst_reports: list[dict],
        market_context: dict,
        max_rounds: int = 2,
    ) -> ServiceResult: ...


@runtime_checkable
class QuantAnalyzersProtocol(Protocol):
    def analyze_all(self, stock_code: str, financials: dict, prices: list) -> list[dict]: ...
    def buffett_analyze(self, stock_code: str, financials: dict) -> dict: ...
    def graham_analyze(self, stock_code: str, financials: dict) -> dict: ...
    def lynch_analyze(self, stock_code: str, financials: dict) -> dict: ...


@runtime_checkable
class FactorFarmProtocol(Protocol):
    def get_top_factors(self, n: int = 20, min_ic: float = 0.03) -> ServiceResult: ...
    def build_factor_score(self, stock_code: str) -> ServiceResult: ...
    def evaluate_factor(self, factor_name: str) -> ServiceResult: ...


@runtime_checkable
class RiskEngineProtocol(Protocol):
    def full_audit(
        self, portfolio: list[dict], market_regime: dict, candidate_orders: list[dict] | None = None
    ) -> ServiceResult: ...


@runtime_checkable
class PortfolioOptimizerProtocol(Protocol):
    def optimize(
        self, current_positions: list[dict], signals: list[dict], risk_report: dict, cash: float
    ) -> ServiceResult: ...
