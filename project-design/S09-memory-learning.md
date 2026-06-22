# S9 — 记忆与学习系统

> **设计参考**: LangMem(LangChain官方)的记忆管理工具 + OpenViking(字节跳动)的文件系统范式 + TradingAgents的决策日志。

## 9.1 决策日志

每次分析自动记录：
```python
entry = {
    "id": next_id(),
    "ticker": "600519",
    "date": "2026-06-13",
    "action": "Buy",
    "confidence": 0.75,
    "entry_price": 1500.0,
    "stop_loss": 1425.0,
    "thesis": "茅台Q2营收超预期，直营占比提升...",
    "source_agents": ["market", "fundamentals", "news", "sentiment", "bull", "bear", "research_mgr", "trader", "aggressive", "conservative", "neutral", "portfolio_mgr"],
}
```

## 9.2 反思引擎

当交易结果已知时，自动反思：

```python
def reflect(decision: dict, outcome: TradeOutcome) -> str:
    prompt = f"""
    决策: {decision['action']} {decision['ticker']} @ {decision['entry_price']}
    论据: {decision['thesis']}
    结果: {'盈利' if outcome.profit > 0 else '亏损'} {abs(outcome.profit)}元 ({outcome.return_pct:.1f}%)
    请分析这个决策，给出100字以内的反思。
    """
    return llm.invoke(prompt)
```

## 9.3 记忆注入

每次新分析前，注入历史记忆：

```python
def inject_memory(ticker: str) -> str:
    history = decision_log.get_history(ticker, limit=5)
    memory = "## 历史决策记忆\n\n"
    for h in history:
        memory += f"- {h['date']}: {h['action']} @ {h['entry_price']}"
        if h.get('reflection'):
            memory += f" — 反思: {h['reflection']}"
        memory += "\n"
    return memory
```

## 9.4 记忆日志轮转（借鉴TradingAgents）

TradingAgents支持`memory_log_max_entries`限制历史条目数，自动清理最旧的记录：

```python
class DecisionLog:
    """决策日志，支持自动轮转"""

    def __init__(self, db_path: str, max_entries: Optional[int] = 100):
        self.db_path = db_path
        self.max_entries = max_entries  # None=不限制

    def add_entry(self, entry: dict):
        """添加新条目"""
        with self._get_session() as session:
            session.add(DecisionLogModel(**entry))

            # 检查是否需要轮转
            if self.max_entries:
                count = session.query(DecisionLogModel).count()
                if count > self.max_entries:
                    # 删除最旧的条目
                    oldest = (
                        session.query(DecisionLogModel)
                        .order_by(DecisionLogModel.created_at.asc())
                        .limit(count - self.max_entries)
                        .all()
                    )
                    for old in oldest:
                        session.delete(old)

    def get_history(self, ticker: str, limit: int = 5) -> list[dict]:
        """获取历史决策"""
        with self._get_session() as session:
            entries = (
                session.query(DecisionLogModel)
                .filter_by(ticker=ticker)
                .order_by(DecisionLogModel.created_at.desc())
                .limit(limit)
                .all()
            )
            return [e.to_dict() for e in entries]
```

### 配置

```yaml
# config.yaml
features:
  memory_log_max_entries: 100           # 最大历史条目数（None=不限制）
```

---

**依赖**: S5(数据), S6(工作流)
**被依赖**: S4(Agent)
