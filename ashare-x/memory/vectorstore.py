"""向量存储 — chromadb RAG检索。

设计依据: Phase 7.1, 对标 FinRobot/TradeGraph。
存储分析报告/新闻/公告的embedding，支持语义检索。
Agent分析时自动检索相关历史信息注入prompt。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("ashare-x.memory.vectorstore")

_COLLECTION_NAME = "ashare_research"
_DB_PATH = "runtime/chromadb"

_vectorstore: VectorStore | None = None


class VectorStore:
    """chromadb向量存储封装。"""

    def __init__(self, db_path: str = _DB_PATH):
        try:
            import chromadb

            self._client = chromadb.PersistentClient(path=db_path)
            self._collection = self._client.get_or_create_collection(
                name=_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            self._available = True
            logger.info("VectorStore初始化完成 (path=%s)", db_path)
        except Exception as e:
            logger.warning("VectorStore初始化失败，RAG功能不可用: %s", e)
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def add_document(
        self,
        doc_id: str,
        content: str,
        doc_type: str = "report",
        ticker: str = "",
        date: str = "",
        metadata: dict[str, Any] | None = None,
    ):
        """添加文档到向量库。"""
        if not self._available:
            return

        meta = {
            "doc_type": doc_type,
            "ticker": ticker,
            "date": date,
        }
        if metadata:
            meta.update(metadata)

        try:
            self._collection.add(
                ids=[doc_id],
                documents=[content],
                metadatas=[meta],
            )
        except Exception as e:
            logger.warning("添加文档失败: %s", e)

    def add_report(
        self,
        ticker: str,
        report_text: str,
        report_type: str = "analysis",
        date: str = "",
    ):
        """添加分析报告到向量库。"""
        import hashlib

        doc_id = hashlib.md5(  # noqa: S324  # 仅用于去重ID，非安全场景
            f"{ticker}_{report_type}_{date}_{report_text[:100]}".encode()
        ).hexdigest()[:16]
        self.add_document(
            doc_id=doc_id,
            content=report_text,
            doc_type=report_type,
            ticker=ticker,
            date=date,
        )

    def add_news(self, ticker: str, title: str, content: str, date: str = ""):
        """添加新闻到向量库。"""
        import hashlib

        doc_id = hashlib.md5(  # noqa: S324  # 仅用于去重ID，非安全场景
            f"news_{ticker}_{date}_{title}".encode()
        ).hexdigest()[:16]
        full_content = f"{title}\n{content}" if content else title
        self.add_document(
            doc_id=doc_id,
            content=full_content,
            doc_type="news",
            ticker=ticker,
            date=date,
        )

    def search(
        self,
        query: str,
        n_results: int = 5,
        ticker: str | None = None,
        doc_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """语义检索相关文档。

        Args:
            query: 搜索查询文本
            n_results: 返回结果数量
            ticker: 过滤特定股票（可选）
            doc_type: 过滤文档类型（可选）

        Returns:
            [{content, metadata, distance}] 列表
        """
        if not self._available:
            return []

        where: dict[str, str] | None = None
        conditions: list[dict[str, str]] = []
        if ticker:
            conditions.append({"ticker": ticker})
        if doc_type:
            conditions.append({"doc_type": doc_type})
        if len(conditions) == 1:
            where = conditions[0]
        elif len(conditions) > 1:
            where = {"$and": conditions}  # type: ignore[dict-item]

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where,  # type: ignore[arg-type]
            )
            documents = results.get("documents", [[]])[0]  # type: ignore[index]
            metadatas = results.get("metadatas", [[]])[0]  # type: ignore[index]
            distances = results.get("distances", [[]])[0]  # type: ignore[index]

            return [
                {
                    "content": doc,
                    "metadata": meta,
                    "distance": dist,
                }
                for doc, meta, dist in zip(documents, metadatas, distances, strict=False)
            ]
        except Exception as e:
            logger.warning("向量检索失败: %s", e)
            return []

    def search_for_agent(
        self,
        ticker: str,
        agent_name: str,
        query: str = "",
        n_results: int = 3,
    ) -> str:
        """为Agent检索相关历史信息，格式化为注入文本。

        Args:
            ticker: 股票代码
            agent_name: Agent名称
            query: 搜索查询（默认用ticker+agent_name）
            n_results: 返回结果数

        Returns:
            Markdown格式的检索结果文本，可直接注入prompt
        """
        if not self._available:
            return ""

        search_query = query or f"{ticker} {agent_name} 分析"

        # 搜索该股票的历史报告
        results = self.search(
            query=search_query,
            n_results=n_results,
            ticker=ticker,
            doc_type="analysis",
        )

        if not results:
            return ""

        lines = ["## RAG检索结果（历史分析）"]
        for i, r in enumerate(results, 1):
            content = r["content"][:500]
            date = r["metadata"].get("date", "")
            lines.append(f"### 参考{i} ({date})\n{content}\n")

        return "\n".join(lines)

    def count(self) -> int:
        """返回向量库中的文档数量。"""
        if not self._available:
            return 0
        try:
            return self._collection.count()
        except Exception:
            return 0


def get_vectorstore() -> VectorStore:
    """获取全局VectorStore实例（单例）。"""
    global _vectorstore  # noqa: PLW0603
    if _vectorstore is None:
        _vectorstore = VectorStore()
    return _vectorstore
