"""双模式执行管理 - 半自动+全自动切换 + T+5复盘调度"""

import json
import os
from datetime import datetime, timedelta

from services.base import BaseService, ServiceResult
from shared.logging import emit_log

MODE_CONFIG_PATH = "config/mode.json"
DEFAULT_CONFIG = {
    "mode": "semi_auto",  # "semi_auto" | "full_auto"
    "initial_cash": 1_000_000,
    "auto_execute_threshold": 0.6,  # 全自动模式下置信度>0.6才自动执行
    "review_lookback_days": 5,  # T+N日复盘
}


class ExecutionModeManager(BaseService):
    """双模式管理器"""

    def __init__(self, config_path: str = MODE_CONFIG_PATH):
        super().__init__()
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> dict:
        if os.path.exists(self.config_path):
            with open(self.config_path, encoding="utf-8") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        return dict(DEFAULT_CONFIG)

    def _save_config(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def get_mode(self) -> ServiceResult:
        """获取当前模式"""
        return ServiceResult.ok(
            data={
                "mode": self.config["mode"],
                "description": "半自动(Web UI确认)"
                if self.config["mode"] == "semi_auto"
                else "全自动(无人值守)",
                "auto_execute_threshold": self.config["auto_execute_threshold"],
                "initial_cash": self.config["initial_cash"],
            }
        )

    def set_mode(self, mode: str) -> ServiceResult:
        """切换模式"""
        if mode not in ("semi_auto", "full_auto"):
            return ServiceResult.error(
                errors=[f"Invalid mode: {mode}. Use 'semi_auto' or 'full_auto'"]
            )
        old_mode = self.config["mode"]
        self.config["mode"] = mode
        self._save_config()
        return ServiceResult.ok(
            data={
                "previous_mode": old_mode,
                "current_mode": mode,
            }
        )

    def should_auto_execute(self, confidence: float) -> bool:
        """判断是否应自动执行(全自动模式下置信度达标则执行)"""
        if str(self.config.get("mode", "")) != "full_auto":
            return False
        threshold = float(self.config.get("auto_execute_threshold", 0.6))
        return confidence >= threshold

    def filter_orders_for_mode(self, orders: list[dict], mode: str | None = None) -> ServiceResult:
        """根据模式过滤订单"""
        current_mode = mode or self.config["mode"]
        threshold = self.config["auto_execute_threshold"]

        if current_mode == "full_auto":
            auto_orders = [o for o in orders if o.get("signal_confidence", 0) >= threshold]
            manual_orders = [o for o in orders if o.get("signal_confidence", 0) < threshold]
            return ServiceResult.ok(
                data={
                    "mode": "full_auto",
                    "auto_executed": auto_orders,
                    "needs_approval": manual_orders,
                    "auto_count": len(auto_orders),
                    "approval_count": len(manual_orders),
                }
            )
        return ServiceResult.ok(
            data={
                "mode": "semi_auto",
                "auto_executed": [],
                "needs_approval": orders,
                "auto_count": 0,
                "approval_count": len(orders),
            }
        )


class ReviewScheduler(BaseService):
    """T+N复盘调度器"""

    def __init__(self, memory_bank=None):
        super().__init__()
        self._memory_bank = memory_bank

    @property
    def memory_bank(self):
        if self._memory_bank is None:
            from services.memory_bank import MemoryBank

            self._memory_bank = MemoryBank()
        return self._memory_bank

    def schedule_review(
        self, trade_date: str, trade_records: list[dict], lookback_days: int = 5
    ) -> ServiceResult:
        """安排T+N日后的复盘任务(记录当前决策,供日后评估)"""
        try:
            review_date = datetime.strptime(trade_date, "%Y-%m-%d") + timedelta(days=lookback_days)
            scheduled = []

            for trade in trade_records:
                scheduled.append(
                    {
                        "trade_date": trade_date,
                        "review_date": review_date.strftime("%Y-%m-%d"),
                        "stock_code": trade.get("stock_code", ""),
                        "stock_name": trade.get("stock_name", ""),
                        "decision": trade.get("direction", trade.get("action", "持有")),
                        "confidence": trade.get("signal_confidence", 0.5),
                        "entry_price": trade.get("fill_price", trade.get("limit_price", 0)),
                        "status": "pending_review",
                    }
                )

            return ServiceResult.ok(
                data={
                    "scheduled": scheduled,
                    "count": len(scheduled),
                    "review_date": review_date.strftime("%Y-%m-%d"),
                    "lookback_days": lookback_days,
                }
            )
        except Exception as e:
            return ServiceResult.error(errors=[f"schedule_review failed: {e}"])

    def execute_due_reviews(self, current_date: str | None = None) -> ServiceResult:
        """执行所有到期的复盘任务 → MemoryBank.store()"""
        current_date = current_date or datetime.now().strftime("%Y-%m-%d")
        # 这里需要从持久化存储中读取待复盘记录
        reviewed = 0
        errors_list = []

        # 查找存储的待复盘记录
        pending_path = "data/pending_reviews.json"
        if os.path.exists(pending_path):
            try:
                with open(pending_path, encoding="utf-8") as f:
                    pending = json.load(f)
            except Exception as e:
                emit_log("WARNING", "execution_mode", f"Error: {str(e)[:100]}")
                pending = []
        else:
            pending = []

        due = [p for p in pending if p.get("review_date", "") <= current_date]
        remaining = [p for p in pending if p.get("review_date", "") > current_date]

        for item in due:
            try:
                situation = {
                    "stock_code": item.get("stock_code", ""),
                    "stock_name": item.get("stock_name", ""),
                    "regime": item.get("regime", "NEUTRAL"),
                    "pe": item.get("pe", 0),
                    "roe": item.get("roe", 0),
                    "industry": item.get("industry", ""),
                    "pl_pct": item.get("actual_return_pct", 0),
                }
                decision = {
                    "verdict": item.get("decision", "持有"),
                    "confidence": item.get("confidence", 0.5),
                }
                is_correct = (
                    item.get("actual_return_pct", 0) > 0
                    if item.get("decision") == "买入"
                    else item.get("actual_return_pct", 0) < 0
                )
                outcome = {
                    "return_pct": item.get("actual_return_pct", 0),
                    "correct": is_correct,
                }
                self.memory_bank.store(situation, decision, outcome)
                reviewed += 1
            except Exception as e:
                errors_list.append(f"Review failed for {item.get('stock_code')}: {e}")

        # 保存未处理的
        with open(pending_path, "w", encoding="utf-8") as f:
            json.dump(remaining, f, ensure_ascii=False, indent=2)

        return ServiceResult.ok(
            data={"reviewed": reviewed, "remaining": len(remaining), "current_date": current_date},
            errors=errors_list if errors_list else [],
        )

    def add_pending_review(self, review_item: dict) -> ServiceResult:
        """添加一条待复盘记录"""
        pending_path = "data/pending_reviews.json"
        os.makedirs(os.path.dirname(pending_path), exist_ok=True)

        if os.path.exists(pending_path):
            with open(pending_path, encoding="utf-8") as f:
                pending = json.load(f)
        else:
            pending = []

        pending.append(review_item)

        with open(pending_path, "w", encoding="utf-8") as f:
            json.dump(pending, f, ensure_ascii=False, indent=2)

        return ServiceResult.ok(data={"pending_count": len(pending)})
