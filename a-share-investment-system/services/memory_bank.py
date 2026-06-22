"""BM25记忆银行 - 来源: TradingAgents-AShare"""

import json
import os
from datetime import datetime, timedelta

import jieba
from rank_bm25 import BM25Okapi

from services.base import BaseService, ServiceResult


class MemoryBank(BaseService):
    """双库隔离的BM25记忆系统"""

    def __init__(self, memory_dir: str = "memory"):
        super().__init__()
        self.memory_dir = memory_dir
        os.makedirs(memory_dir, exist_ok=True)

        self.bull_index_path = os.path.join(memory_dir, "bull_index.pkl")
        self.bear_index_path = os.path.join(memory_dir, "bear_index.pkl")

        self.bull_docs: list[dict] = []
        self.bear_docs: list[dict] = []
        self.bull_bm25: BM25Okapi | None = None
        self.bear_bm25: BM25Okapi | None = None

        self._load()

    # ── 公开接口 ──

    def store(self, situation: dict, decision: dict, outcome: dict) -> ServiceResult:
        """存储一次决策记录到对应记忆库"""
        try:
            memory = {
                "id": f"mem_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(self.bull_docs) + len(self.bear_docs)}",
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

            verdict = decision.get("verdict", "持有")
            if verdict in ("买入", "加仓"):
                self.bull_docs.append(memory)
                self._rebuild_bull_index()
            elif verdict in ("卖出", "减仓"):
                self.bear_docs.append(memory)
                self._rebuild_bear_index()

            self._save()
            return ServiceResult.ok(data={"memory_id": memory["id"]})
        except Exception as e:
            return ServiceResult.error(errors=[f"MemoryBank.store failed: {e}"])

    def retrieve(
        self, current_situation: dict, top_k: int = 5, bank: str = "auto"
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
                bull_results = self._search(
                    self.bull_bm25, self.bull_docs, tokenized_query, top_k // 2 + 1
                )
                bear_results = self._search(
                    self.bear_bm25, self.bear_docs, tokenized_query, top_k // 2 + 1
                )
                memories = bull_results + bear_results

            one_year_ago = datetime.now() - timedelta(days=365)
            for m in memories:
                created = datetime.fromisoformat(m.get("created_at", "2000-01-01"))
                m["_weight_decay"] = 0.5 if created < one_year_ago else 1.0

            return ServiceResult.ok(data={"memories": memories[:top_k], "count": len(memories)})
        except Exception as e:
            return ServiceResult.error(errors=[f"MemoryBank.retrieve failed: {e}"])

    def inject_into_prompt(self, base_prompt: str, current_situation: dict) -> ServiceResult:
        """将历史经验注入Agent prompt"""
        result = self.retrieve(current_situation, top_k=3)
        if result.status != "ok" or not result.data.get("memories"):
            return ServiceResult.ok(data={"prompt": base_prompt, "injected_count": 0})

        lessons = []
        for m in result.data["memories"]:
            correct = "成功" if m.get("outcome_correct") else "失败"
            weight = m.get("_weight_decay", 1.0)
            lessons.append(
                f"- [{correct}] 当{m['situation_text'][:80]}...时,"
                f"决策[{m['decision_type']}]结果{m['outcome_pct']:+.1f}%"
                f"{'(权重降低)' if weight < 1.0 else ''}"
            )

        enhanced = f"{base_prompt}\n\n[历史经验-仅供参考,不构成决策依据]\n" + "\n".join(lessons)
        return ServiceResult.ok(data={"prompt": enhanced, "injected_count": len(lessons)})

    # ── 内部方法 ──

    def _encode_situation(self, situation: dict) -> str:
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

    def _search(self, bm25, docs, tokenized_query, top_k) -> list[dict]:
        if bm25 is None or not docs:
            return []
        scores = bm25.get_scores(tokenized_query)
        ranked = sorted(enumerate(scores), key=lambda x: -x[1])[:top_k]
        return [{**docs[i], "_bm25_score": float(s)} for i, s in ranked]

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
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.bull_docs = data.get("bull", [])
            self.bear_docs = data.get("bear", [])
            self._rebuild_bull_index()
            self._rebuild_bear_index()
