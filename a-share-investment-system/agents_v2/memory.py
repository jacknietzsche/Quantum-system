"""交易记忆系统 — 参考 TradingAgents/agents/utils/memory.py

Append-only markdown 决策日志,支持:
1. 存储决策 (Phase A): propagate() 结束时写入 pending 条目
2. 反射更新 (Phase B): 下次运行时注入历史上下文,事后更新 outcome
3. 跨股票经验: 同一股票 + 跨股票 lessons 自动注入 prompt

A 股适配:
- 使用 6 位股票代码而非 ticker
- 支持中文评级 (买入/持有/卖出)
- T+1 持仓周期记录
"""

from __future__ import annotations

import re
from pathlib import Path

from shared.logging import emit_log


def _parse_rating(decision_text: str) -> str:  # noqa: PLR0911
    """从决策文本提取评级"""
    text = decision_text.upper()
    # 英文
    for keyword in ("STRONG BUY", "BUY"):
        if keyword in text:
            return "买入"
    for keyword in ("STRONG SELL", "SELL"):
        if keyword in text:
            return "卖出"
    if "HOLD" in text:
        return "持有"
    # 中文
    if "买入" in text:
        return "买入"
    if "卖出" in text:
        return "卖出"
    if "持有" in text or "观望" in text:
        return "持有"
    return "中性"


class TradingMemory:
    """Append-only markdown 决策日志

    文件格式:
    ```
    [日期 | 股票代码 | 评级 | pending]

    DECISION:
    决策内容...

    <!-- ENTRY_END -->

    [日期 | 股票代码 | 评级 | +5.2% | +3.1% | 3d]

    DECISION:
    决策内容...

    REFLECTION:
    反思内容...
    ```
    """

    _SEPARATOR = "\n\n<!-- ENTRY_END -->\n\n"
    _DECISION_RE = re.compile(r"DECISION:\n(.*?)(?=\nREFLECTION:|\Z)", re.DOTALL)
    _REFLECTION_RE = re.compile(r"REFLECTION:\n(.*?)$", re.DOTALL)

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self._log_path = None
        path = cfg.get("memory_log_path")
        if path:
            self._log_path = Path(path).expanduser()
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._max_entries = cfg.get("memory_log_max_entries")

    # ─── 写入路径 (Phase A) ───

    def store_decision(
        self,
        stock_code: str,
        trade_date: str,
        final_trade_decision: str,
    ) -> None:
        """追加 pending 条目 (propagate() 结束时调用,无 LLM 调用)"""
        if not self._log_path:
            return
        # 幂等性检查
        if self._log_path.exists():
            raw = self._log_path.read_text(encoding="utf-8")
            for line in raw.splitlines():
                if line.startswith(f"[{trade_date} | {stock_code} |") and line.endswith(
                    "| pending]"
                ):
                    return

        rating = _parse_rating(final_trade_decision)
        tag = f"[{trade_date} | {stock_code} | {rating} | pending]"
        entry = f"{tag}\n\nDECISION:\n{final_trade_decision}{self._SEPARATOR}"

        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(entry)
            emit_log("DEBUG", "memory", f"Stored decision: {tag}")
        except Exception as e:
            emit_log("WARNING", "memory", f"Failed to store decision: {e}")

    # ─── 读取路径 (Phase A) ───

    def load_entries(self) -> list[dict]:
        """解析所有条目"""
        if not self._log_path or not self._log_path.exists():
            return []
        text = self._log_path.read_text(encoding="utf-8")
        raw_entries = [e.strip() for e in text.split(self._SEPARATOR) if e.strip()]
        entries = []
        for raw in raw_entries:
            parsed = self._parse_entry(raw)
            if parsed:
                entries.append(parsed)
        return entries

    def get_pending_entries(self) -> list[dict]:
        """返回 outcome 为 pending 的条目"""
        return [e for e in self.load_entries() if e.get("pending")]

    def get_past_context(
        self,
        stock_code: str,
        n_same: int = 5,
        n_cross: int = 3,
    ) -> str:
        """返回格式化的历史上下文字符串,用于 agent prompt 注入

        Args:
            stock_code: 当前分析的股票代码
            n_same: 同一股票取最近 N 条
            n_cross: 跨股票取最近 N 条 lessons
        """
        entries = [e for e in self.load_entries() if not e.get("pending")]
        if not entries:
            return ""

        same, cross = [], []
        for e in reversed(entries):
            if len(same) >= n_same and len(cross) >= n_cross:
                break
            if e["stock_code"] == stock_code and len(same) < n_same:
                same.append(e)
            elif e["stock_code"] != stock_code and len(cross) < n_cross:
                cross.append(e)

        if not same and not cross:
            return ""

        parts = []
        if same:
            parts.append(f"该股票 ({stock_code}) 的历史分析 (最近优先):")
            parts.extend(self._format_full(e) for e in same)
        if cross:
            parts.append("\n其他股票的经验教训:")
            parts.extend(self._format_reflection_only(e) for e in cross)
        return "\n\n".join(parts)

    # ─── 更新路径 (Phase B) ───

    def update_with_outcome(
        self,
        stock_code: str,
        trade_date: str,
        raw_return: float,
        alpha_return: float,
        holding_days: int,
        reflection: str,
    ) -> None:
        """更新 pending 条目为已解决,添加 outcome 和 reflection"""
        if not self._log_path or not self._log_path.exists():
            return

        text = self._log_path.read_text(encoding="utf-8")
        blocks = text.split(self._SEPARATOR)

        pending_prefix = f"[{trade_date} | {stock_code} |"
        raw_pct = f"{raw_return:+.1%}"
        alpha_pct = f"{alpha_return:+.1%}"

        updated = False
        new_blocks = []
        for block in blocks:
            stripped = block.strip()
            if not stripped:
                new_blocks.append(block)
                continue

            lines = stripped.splitlines()
            tag_line = lines[0].strip()

            if (
                not updated
                and tag_line.startswith(pending_prefix)
                and tag_line.endswith("| pending]")
            ):
                fields = [f.strip() for f in tag_line[1:-1].split("|")]
                rating = fields[2] if len(fields) > 2 else "?"
                new_tag = (
                    f"[{trade_date} | {stock_code} | {rating}"
                    f" | {raw_pct} | {alpha_pct} | {holding_days}d]"
                )
                rest = "\n".join(lines[1:])
                new_blocks.append(f"{new_tag}\n\n{rest.lstrip()}\n\nREFLECTION:\n{reflection}")
                updated = True
            else:
                new_blocks.append(block)

        if updated:
            new_blocks = self._apply_rotation(new_blocks)
            new_text = self._SEPARATOR.join(new_blocks)
            tmp_path = self._log_path.with_suffix(".tmp")
            tmp_path.write_text(new_text, encoding="utf-8")
            tmp_path.replace(self._log_path)
            emit_log("DEBUG", "memory", f"Updated outcome: {stock_code} {trade_date}")

    # ─── 批量更新 (Phase B) ───

    def batch_update_outcomes(self, updates: list[dict]) -> None:
        """批量更新 pending 条目

        每个 update dict 需包含:
        trade_date, stock_code, raw_return, alpha_return, holding_days, reflection
        """
        if not self._log_path or not self._log_path.exists():
            return

        text = self._log_path.read_text(encoding="utf-8")
        blocks = text.split(self._SEPARATOR)
        update_map = {(u["trade_date"], u["stock_code"]): u for u in updates}

        new_blocks = []
        for block in blocks:
            stripped = block.strip()
            if not stripped:
                new_blocks.append(block)
                continue

            lines = stripped.splitlines()
            tag_line = lines[0].strip()

            matched = False
            for (trade_date, stock_code), upd in list(update_map.items()):
                pending_prefix = f"[{trade_date} | {stock_code} |"
                if tag_line.startswith(pending_prefix) and tag_line.endswith("| pending]"):
                    fields = [f.strip() for f in tag_line[1:-1].split("|")]
                    rating = fields[2] if len(fields) > 2 else "?"
                    raw_pct = f"{upd['raw_return']:+.1%}"
                    alpha_pct = f"{upd['alpha_return']:+.1%}"
                    new_tag = (
                        f"[{trade_date} | {stock_code} | {rating}"
                        f" | {raw_pct} | {alpha_pct} | {upd['holding_days']}d]"
                    )
                    rest = "\n".join(lines[1:])
                    new_blocks.append(
                        f"{new_tag}\n\n{rest.lstrip()}\n\nREFLECTION:\n{upd['reflection']}"
                    )
                    del update_map[(trade_date, stock_code)]
                    matched = True
                    break

            if not matched:
                new_blocks.append(block)

        new_blocks = self._apply_rotation(new_blocks)
        new_text = self._SEPARATOR.join(new_blocks)
        tmp_path = self._log_path.with_suffix(".tmp")
        tmp_path.write_text(new_text, encoding="utf-8")
        tmp_path.replace(self._log_path)

    # ─── Helpers ───

    def _apply_rotation(self, blocks: list[str]) -> list[str]:
        """超过 max_entries 时丢弃最旧的已解决条目"""
        if not self._max_entries or self._max_entries <= 0:
            return blocks

        decisions = []
        for block in blocks:
            stripped = block.strip()
            if not stripped:
                decisions.append((block, False))
                continue
            tag_line = stripped.splitlines()[0].strip()
            is_resolved = (
                tag_line.startswith("[")
                and tag_line.endswith("]")
                and not tag_line.endswith("| pending]")
            )
            decisions.append((block, is_resolved))

        resolved_count = sum(1 for _, r in decisions if r)
        if resolved_count <= self._max_entries:
            return blocks

        to_drop = resolved_count - self._max_entries
        kept: list[str] = []
        for block, is_resolved in decisions:
            if is_resolved and to_drop > 0:
                to_drop -= 1
                continue
            kept.append(block)
        return kept

    def _parse_entry(self, raw: str) -> dict | None:
        lines = raw.strip().splitlines()
        if not lines:
            return None
        tag_line = lines[0].strip()
        if not (tag_line.startswith("[") and tag_line.endswith("]")):
            return None
        fields = [f.strip() for f in tag_line[1:-1].split("|")]
        if len(fields) < 4:
            return None
        entry = {
            "date": fields[0],
            "stock_code": fields[1],
            "rating": fields[2],
            "pending": fields[3] == "pending",
            "raw_return": fields[3] if fields[3] != "pending" else None,
            "alpha_return": fields[4] if len(fields) > 4 else None,
            "holding_days": fields[5] if len(fields) > 5 else None,
        }
        body = "\n".join(lines[1:]).strip()
        decision_match = self._DECISION_RE.search(body)
        reflection_match = self._REFLECTION_RE.search(body)
        entry["decision"] = decision_match.group(1).strip() if decision_match else ""
        entry["reflection"] = reflection_match.group(1).strip() if reflection_match else ""
        return entry

    def _format_full(self, e: dict) -> str:
        raw = e.get("raw_return") or "n/a"
        alpha = e.get("alpha_return") or "n/a"
        holding = e.get("holding_days") or "n/a"
        tag = f"[{e['date']} | {e['stock_code']} | {e['rating']} | 收益{raw} | 超额{alpha} | {holding}天]"
        parts = [tag, f"DECISION:\n{e['decision']}"]
        if e.get("reflection"):
            parts.append(f"REFLECTION:\n{e['reflection']}")
        return "\n\n".join(parts)

    def _format_reflection_only(self, e: dict) -> str:
        tag = f"[{e['date']} | {e['stock_code']} | {e['rating']} | {e.get('raw_return') or 'n/a'}]"
        if e.get("reflection"):
            return f"{tag}\n{e['reflection']}"
        text = e.get("decision", "")[:300]
        suffix = "..." if len(e.get("decision", "")) > 300 else ""
        return f"{tag}\n{text}{suffix}"


# ─── 全局单例 ───
_global_memory: TradingMemory | None = None


def get_trading_memory(config: dict | None = None) -> TradingMemory:
    global _global_memory  # noqa: PLW0603
    if _global_memory is None:
        _global_memory = TradingMemory(config)
    return _global_memory
