"""增强的记忆和反思系统 - 参考TradingAgents设计"""

import json
import os
from datetime import datetime

from shared.logging import emit_log


class TradingMemory:
    """交易记忆系统 - 记录和学习交易经验"""

    def __init__(self, memory_file: str = "data/trading_memory.json"):
        self.memory_file = memory_file
        self.memories: dict[str, list[dict]] = self._load_memories()

    def _load_memories(self) -> dict[str, list[dict]]:
        """加载记忆文件"""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return {k: v if isinstance(v, list) else [] for k, v in data.items()}
            except Exception as e:
                emit_log("WARNING", "memory", f"加载记忆失败: {str(e)[:80]}")
        return {
            "trades": [],
            "reflections": [],
            "patterns": [],
            "lessons": [],
        }

    def _save_memories(self):
        """保存记忆文件"""
        try:
            os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self.memories, f, ensure_ascii=False, indent=2)
        except Exception as e:
            emit_log("ERROR", "memory", f"保存记忆失败: {str(e)[:80]}")

    def record_trade(self, trade: dict):
        """记录交易"""
        trade["timestamp"] = datetime.now().isoformat()
        self.memories["trades"].append(trade)

        # 保持最近1000条交易记录
        if len(self.memories["trades"]) > 1000:
            self.memories["trades"] = self.memories["trades"][-1000:]

        self._save_memories()
        emit_log("INFO", "memory", f"记录交易: {trade.get('stock_code')} {trade.get('action')}")

    def record_reflection(self, reflection: dict):
        """记录反思"""
        reflection["timestamp"] = datetime.now().isoformat()
        self.memories["reflections"].append(reflection)

        # 保持最近100条反思
        if len(self.memories["reflections"]) > 100:
            self.memories["reflections"] = self.memories["reflections"][-100:]

        self._save_memories()
        emit_log("INFO", "memory", f"记录反思: {reflection.get('topic')}")

    def record_pattern(self, pattern: dict):
        """记录模式"""
        pattern["timestamp"] = datetime.now().isoformat()
        self.memories["patterns"].append(pattern)
        self._save_memories()

    def record_lesson(self, lesson: dict):
        """记录教训"""
        lesson["timestamp"] = datetime.now().isoformat()
        self.memories["lessons"].append(lesson)
        self._save_memories()

    def get_recent_trades(self, limit: int = 10) -> list[dict]:
        """获取最近的交易"""
        return self.memories["trades"][-limit:]

    def get_reflections(self, limit: int = 10) -> list[dict]:
        """获取反思"""
        return self.memories["reflections"][-limit:]

    def get_patterns(self) -> list[dict]:
        """获取模式"""
        return self.memories["patterns"]

    def get_lessons(self) -> list[dict]:
        """获取教训"""
        return self.memories["lessons"]

    def analyze_performance(self) -> dict:
        """分析交易表现"""
        trades = self.memories["trades"]
        if not trades:
            return {"total_trades": 0, "win_rate": 0, "avg_return": 0}

        # 计算胜率
        winning_trades = [t for t in trades if t.get("pnl", 0) > 0]
        win_rate = len(winning_trades) / len(trades) * 100

        # 计算平均收益
        returns = [t.get("return_pct", 0) for t in trades if "return_pct" in t]
        avg_return = sum(returns) / len(returns) if returns else 0

        return {
            "total_trades": len(trades),
            "win_rate": round(win_rate, 2),
            "avg_return": round(avg_return, 2),
            "winning_trades": len(winning_trades),
            "losing_trades": len(trades) - len(winning_trades),
        }


class TradingReflector:
    """交易反思器 - 从经验中学习"""

    def __init__(self, memory: TradingMemory):
        self.memory = memory

    def reflect_on_trade(self, trade: dict, outcome: dict):
        """对交易进行反思"""
        reflection = {
            "trade_id": trade.get("id"),
            "stock_code": trade.get("stock_code"),
            "action": trade.get("action"),
            "entry_price": trade.get("price"),
            "exit_price": outcome.get("exit_price"),
            "pnl": outcome.get("pnl"),
            "return_pct": outcome.get("return_pct"),
            "reasoning": trade.get("reasoning"),
            "outcome_reasoning": outcome.get("reasoning"),
            "lessons": self._extract_lessons(trade, outcome),
        }

        self.memory.record_reflection(reflection)
        return reflection

    def _extract_lessons(self, trade: dict, outcome: dict) -> list[str]:
        """从交易中提取教训"""
        lessons = []

        pnl = outcome.get("pnl", 0)
        return_pct = outcome.get("return_pct", 0)

        # 盈利交易的教训
        if pnl > 0:
            if return_pct > 10:
                lessons.append("大盈利交易：持仓耐心，让利润奔跑")
            elif return_pct > 5:
                lessons.append("中等盈利：及时止盈，锁定利润")

        # 亏损交易的教训
        elif pnl < 0:
            if return_pct < -10:
                lessons.append("大亏损：止损不及时，需要严格执行止损")
            elif return_pct < -5:
                lessons.append("中等亏损：入场时机不佳，需要更好的入场点")

        # 记录教训
        for lesson in lessons:
            self.memory.record_lesson(
                {
                    "trade_id": trade.get("id"),
                    "lesson": lesson,
                    "category": "profit" if pnl > 0 else "loss",
                }
            )

        return lessons

    def get_performance_summary(self) -> dict:
        """获取表现总结"""
        return self.memory.analyze_performance()

    def get_learning_points(self) -> list[str]:
        """获取学习要点"""
        lessons = self.memory.get_lessons()
        return [str(item.get("lesson")) for item in lessons[-10:] if item.get("lesson")]


# 全局实例
_memory = None
_reflector = None


def get_memory() -> TradingMemory:
    """获取全局记忆实例"""
    global _memory  # noqa: PLW0603
    if _memory is None:
        _memory = TradingMemory()
    return _memory


def get_reflector() -> TradingReflector:
    """获取全局反思器实例"""
    global _reflector  # noqa: PLW0603
    if _reflector is None:
        _reflector = TradingReflector(get_memory())
    return _reflector
