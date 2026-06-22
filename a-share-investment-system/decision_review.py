"""
A股智能投资系统 - 决策复盘与动态仓位管理
决策复盘数据库 + 自动复盘 + 基于风险的动态仓位计算
"""

#  DEPRECATED: Decision review recording has been superseded by
#  MemoryBank (services/memory_bank.py) for historical memory.
#  PositionManager remains active for position sizing calculations.
#  This module will be removed in a future version.
import os
import re
from datetime import datetime, timedelta

from shared.logging import emit_log
from shared.models import (
    Base,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    get_session,
    init_db,
)


class DecisionReview(Base):
    """决策复盘记录"""

    __tablename__ = "decision_reviews"
    __table_args__: dict = {"extend_existing": True}  # noqa: RUF012

    id = Column(Integer, primary_key=True, autoincrement=True)
    decision_date = Column(String(10), nullable=False)  # 决策日期
    stock_code = Column(String(10), nullable=False)
    stock_name = Column(String(50), nullable=False)
    recommendation = Column(String(20), nullable=False)  # 买入/持有/卖出
    confidence = Column(Float, default=0.0)  # 置信度
    model_consistency = Column(Float, default=0.0)  # 模型一致性
    reason = Column(Text, default="")  # 决策理由

    # 复盘结果(后续填写)
    review_date = Column(String(10), default="")
    actual_outcome = Column(String(20), default="")  # 正确/错误/待评估
    actual_return_pct = Column(Float, default=0.0)  # 实际收益率
    outcome_reason = Column(Text, default="")  # 结果原因分析
    lessons_learned = Column(Text, default="")  # 经验教训
    review_model = Column(String(50), default="")  # 复盘使用的模型

    created_at = Column(DateTime, default=datetime.now)
    reviewed_at = Column(DateTime)


class DecisionReviewManager:
    """决策复盘管理器"""

    def __init__(self, db_path: str = "data/investment.db"):
        # 确保数据目录存在(Windows兼容)
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        init_db(db_path)
        self.session = get_session(db_path)

    def record_decision(
        self,
        stock_code: str,
        stock_name: str,
        recommendation: str,
        confidence: float = 0.0,
        model_consistency: float = 0.0,
        reason: str = "",
    ) -> dict:
        """记录一个投资决策"""
        today = datetime.now().strftime("%Y-%m-%d")
        review = DecisionReview(
            decision_date=today,
            stock_code=stock_code,
            stock_name=stock_name,
            recommendation=recommendation,
            confidence=confidence,
            model_consistency=model_consistency,
            reason=reason,
        )
        self.session.add(review)
        self.session.commit()
        return {"status": "ok", "message": f"✅ 已记录决策: {stock_name} → {recommendation}"}

    def record_vote_result(self, vote_result: dict) -> dict:
        """从多模型投票结果中提取并记录决策

        兼容两种格式:
          1. workflow格式: 有 all_results, votes, winner_confidence
          2. super_workflow格式: 有 stock_name, confidence, reasoning (无all_results/votes)
        """
        try:
            winner = vote_result.get("winner", "持有")
            confidence = vote_result.get("winner_confidence") or vote_result.get("confidence", 0)
            consistency = vote_result.get("consistency", 0)

            # 格式1: 从 all_results 提取(workflow格式)
            stock_code = ""
            stock_name = ""
            for r in vote_result.get("all_results", []):
                ctx = r.get("context", {})
                if ctx.get("stock_code"):
                    stock_code = ctx["stock_code"]
                    stock_name = ctx.get("stock_name", "")
                    break

            # 格式2: 从 vote_result 顶层提取(super_workflow格式)
            if not stock_code:
                stock_code = vote_result.get("stock_code", "")
                stock_name = vote_result.get("stock_name", "")

            # 格式3: 从 question 解析
            if not stock_code:
                question = vote_result.get("question", "")
                code_match = re.search(r"(\d{6})", question)

                if code_match:
                    stock_code = code_match.group(1)

            if not stock_code:
                return {"status": "skip", "message": "无法从投票结果中提取股票信息"}

            # 汇总理由
            reasons = []
            # 格式1: votes -> models -> reasoning
            for _rec, data in vote_result.get("votes", {}).items():
                for m in data.get("models", []):
                    if m.get("reasoning"):
                        reasons.append(f"[{m.get('role', '?')}] {m['reasoning'][:100]}")
            # 格式2: 直接有 reasoning 字段
            if not reasons and vote_result.get("reasoning"):
                reasons.append(vote_result["reasoning"][:200])
            reason_str = "\n".join(reasons[:5])

            return self.record_decision(
                stock_code, stock_name, winner, confidence, consistency, reason_str
            )
        except Exception as e:
            return {"status": "error", "message": f"记录投票结果失败: {e!s}"}

    def auto_review(self, days: int = 7) -> dict:
        """自动复盘:评估过去N天的决策"""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        pending = (
            self.session.query(DecisionReview)
            .filter(DecisionReview.decision_date >= cutoff, DecisionReview.actual_outcome == "")
            .all()
        )

        if not pending:
            return {"status": "ok", "reviewed": 0, "message": "没有待复盘的决策"}

        reviewed = 0
        correct = 0
        results = []

        for decision in pending:
            # 获取该股票在决策日之后的收益
            actual_return = self._calculate_actual_return(decision)

            # 判断决策是否正确
            if decision.recommendation == "买入":
                outcome = (
                    "正确" if actual_return > 2 else "错误" if actual_return < -2 else "部分正确"
                )
            elif decision.recommendation == "卖出":
                outcome = (
                    "正确" if actual_return < -2 else "错误" if actual_return > 2 else "部分正确"
                )
            else:  # 持有
                outcome = "正确" if -5 < actual_return < 10 else "部分正确"

            decision.review_date = datetime.now().strftime("%Y-%m-%d")
            decision.actual_outcome = outcome
            decision.actual_return_pct = actual_return
            decision.reviewed_at = datetime.now()

            if outcome == "正确":
                correct += 1

            results.append(
                {
                    "stock": f"{decision.stock_name}({decision.stock_code})",
                    "date": decision.decision_date,
                    "recommendation": decision.recommendation,
                    "actual_return": f"{actual_return:+.2f}%",
                    "outcome": outcome,
                }
            )
            reviewed += 1

        self.session.commit()

        accuracy = correct / reviewed * 100 if reviewed > 0 else 0
        return {
            "status": "ok",
            "reviewed": reviewed,
            "correct": correct,
            "accuracy": f"{accuracy:.1f}%",
            "details": results,
        }

    def _calculate_actual_return(self, decision: DecisionReview) -> float:
        """计算决策后的实际收益率"""
        try:
            from services.data_bus import DatabaseBackedDataBus as DataBus

            data_bus = DataBus()
            history = data_bus.get_stock_history(
                decision.stock_code, decision.decision_date, datetime.now().strftime("%Y-%m-%d")
            )
            if history.empty or len(history) < 2:
                return 0.0
            first_close = float(history.iloc[0]["close"])
            last_close = float(history.iloc[-1]["close"])
            return (last_close - first_close) / first_close * 100 if first_close > 0 else 0.0
        except Exception as e:
            emit_log("WARNING", "decision_review", f"Non-critical error: {str(e)[:100]}")
            return 0.0
            return 0.0

    def get_stats(self) -> dict:
        """获取复盘统计"""
        total = self.session.query(DecisionReview).count()
        reviewed = (
            self.session.query(DecisionReview).filter(DecisionReview.actual_outcome != "").count()
        )
        correct = (
            self.session.query(DecisionReview)
            .filter(DecisionReview.actual_outcome == "正确")
            .count()
        )

        # 按推荐类型统计准确率
        by_rec = {}
        for rec in ["买入", "持有", "卖出"]:
            rec_total = (
                self.session.query(DecisionReview)
                .filter(DecisionReview.recommendation == rec, DecisionReview.actual_outcome != "")
                .count()
            )
            rec_correct = (
                self.session.query(DecisionReview)
                .filter(
                    DecisionReview.recommendation == rec, DecisionReview.actual_outcome == "正确"
                )
                .count()
            )
            if rec_total > 0:
                by_rec[rec] = {
                    "total": rec_total,
                    "correct": rec_correct,
                    "accuracy": f"{rec_correct / rec_total * 100:.1f}%",
                }

        return {
            "total_decisions": total,
            "reviewed": reviewed,
            "correct": correct,
            "overall_accuracy": f"{correct / reviewed * 100:.1f}%" if reviewed > 0 else "N/A",
            "by_recommendation": by_rec,
        }

    def get_recent_reviews(self, limit: int = 20) -> list[dict]:
        """获取最近的复盘记录"""
        reviews = (
            self.session.query(DecisionReview).order_by(DecisionReview.id.desc()).limit(limit).all()
        )
        return [
            {
                "date": r.decision_date,
                "stock": f"{r.stock_name}({r.stock_code})",
                "recommendation": r.recommendation,
                "confidence": r.confidence,
                "outcome": r.actual_outcome or "待评估",
                "actual_return": f"{r.actual_return_pct:+.2f}%" if r.actual_return_pct else "N/A",
            }
            for r in reviews
        ]

    def close(self):
        self.session.close()


#  动态仓位管理器


class PositionManager:
    """基于风险评分的动态仓位管理"""

    # 仓位映射表
    POSITION_TABLE: tuple[tuple[int | float, ...], ...] = (
        (0, 30, 0.80, "低风险", "可维持80%仓位"),
        (30, 50, 0.60, "中低风险", "建议60%仓位"),
        (50, 70, 0.40, "中高风险", "建议降至40%仓位"),
        (70, 85, 0.25, "高风险", "建议降至25%仓位"),
        (85, 100, 0.10, "极高风险", "建议降至10%仓位或清仓"),
    )

    def __init__(self):
        self._position_history: list[dict] = []

    def calculate_position_ratio(self, risk_score: float) -> dict:
        """
        根据综合风险评分计算建议仓位比例
        Args:
            risk_score: 0-100,越高风险越大
        Returns:
            仓位建议详情
        """
        for low, high, ratio, level, advice in self.POSITION_TABLE:
            if low <= risk_score < high:
                result = {
                    "risk_score": risk_score,
                    "level": level,
                    "position_ratio": ratio,
                    "position_pct": f"{ratio * 100:.0f}%",
                    "advice": advice,
                }
                self._position_history.append({**result, "timestamp": datetime.now().isoformat()})
                return result
        # 超过100
        result = {
            "risk_score": risk_score,
            "level": "极高风险",
            "position_ratio": 0.05,
            "position_pct": "5%",
            "advice": "建议清仓",
        }
        self._position_history.append({**result, "timestamp": datetime.now().isoformat()})
        return result

    def calculate_stock_weight(
        self, total_capital: float, risk_score: float, stock_count: int = 5
    ) -> list[dict]:
        """
        计算每只股票的建议仓位金额
        使用塔勒布杠铃策略:核心仓位(70%) + 卫星仓位(30%)
        """
        pos = self.calculate_position_ratio(risk_score)
        total_position = total_capital * pos["position_ratio"]

        # 单只股票最大仓位不超过总资金的20%
        max_per_stock = total_capital * 0.20
        # 等权分配
        per_stock = min(total_position / max(stock_count, 1), max_per_stock)

        # 杠铃策略分配
        core_count = max(1, int(stock_count * 0.6))
        satellite_count = stock_count - core_count

        allocations = []
        for i in range(stock_count):
            if i < core_count:
                weight = per_stock * 1.2  # 核心仓位移多
                category = "核心"
            else:
                weight = per_stock * 0.7  # 卫星仓位少
                category = "卫星"
            weight = min(weight, max_per_stock)
            allocations.append(
                {
                    "slot": i + 1,
                    "category": category,
                    "max_amount": round(weight, 0),
                    "max_pct": f"{weight / total_capital * 100:.1f}%",
                }
            )

        return {
            "total_capital": total_capital,
            "risk_score": risk_score,
            "risk_level": pos["level"],
            "total_position": round(total_position, 0),
            "position_pct": pos["position_pct"],
            "stock_count": stock_count,
            "core_stocks": core_count,
            "satellite_stocks": satellite_count,
            "allocations": allocations,
            "barbell_advice": f"核心仓位{core_count}只(各{allocations[0]['max_pct'] if allocations else 'N/A'}) + 卫星仓位{satellite_count}只(各{allocations[-1]['max_pct'] if len(allocations) > core_count else 'N/A'})",
        }

    def get_history(self) -> list[dict]:
        return self._position_history
