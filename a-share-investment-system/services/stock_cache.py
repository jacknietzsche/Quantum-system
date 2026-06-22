"""双层个股分析缓存 - 精确匹配(L1) + 语义匹配(L2)

L1: 复用CacheManager,key=f"screening:{code}:{style}:{date}"
L2: 10维量化特征向量,余弦相似度>0.85命中,进程内列表(上限2000条)

复用现有基础设施:
- CacheManager - L1精确缓存
- 数据新鲜度判断 - 价格变动>5%/新财报/新交易日触发失效
"""

import json
import logging
import math
import threading
import time
from dataclasses import dataclass
from datetime import date

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════
#  特征提取 - 10维量化向量
# ════════════════════════════════════════════


def extract_feature_vector(stock_data: dict) -> list[float]:
    """从股票数据提取10维归一化特征向量"""
    return [
        _norm(stock_data.get("pe", 0), 0, 100),  # 0: PE
        _norm(stock_data.get("pb", 0), 0, 20),  # 1: PB
        _norm(stock_data.get("roe", 0), -20, 50),  # 2: ROE
        _norm(stock_data.get("market_cap", 0), 0, 5000),  # 3: 市值
        _norm(stock_data.get("turnover_rate", 0), 0, 20),  # 4: 换手率
        _norm(stock_data.get("volume_ratio", 0), 0, 5),  # 5: 量比
        _norm(stock_data.get("change_pct_5d", 0), -20, 20),  # 6: 5日涨幅
        _norm(stock_data.get("change_pct_60d", 0), -50, 50),  # 7: 60日涨幅
        _norm(stock_data.get("debt_to_equity", 0), 0, 200),  # 8: 负债率
        _norm(stock_data.get("gross_margin", 0), 0, 100),  # 9: 毛利率
    ]


def _norm(v: float, lo: float, hi: float) -> float:
    """归一化到 [0, 1],超出范围则截断"""
    if hi <= lo or v is None:
        return 0.5
    clamped = max(lo, min(hi, v))
    return (clamped - lo) / (hi - lo)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """余弦相似度"""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ════════════════════════════════════════════
#  缓存条目
# ════════════════════════════════════════════


@dataclass
class CacheEntry:
    """分析缓存条目"""

    stock_code: str
    style: str
    data: dict
    feature_vector: list[float]
    price: float
    created_at: float
    expires_at: float


# ════════════════════════════════════════════
#  双层缓存
# ════════════════════════════════════════════

SIMILARITY_THRESHOLD = 0.85
MAX_SEMANTIC_ENTRIES = 2000
L1_TTL = 3600  # 1小时


def _today_str() -> str:
    return date.today().isoformat()


class StockAnalysisCache:
    """双层个股分析缓存 - 精确匹配(L1) + 语义匹配(L2)"""

    def __init__(self):
        from providers.cache import CacheManager

        self._l1_cache = CacheManager()
        self._l2_entries: list[CacheEntry] = []
        self._lock = threading.Lock()

    # ── L1: 精确匹配 ──

    def l1_key(self, stock_code: str, style: str) -> str:
        return f"screening:{stock_code}:{style}:{_today_str()}"

    def get_exact(self, stock_code: str, style: str) -> dict | None:
        """L1精确匹配"""
        key = self.l1_key(stock_code, style)
        result = self._l1_cache.get(key)
        if isinstance(result, str):
            parsed = json.loads(result)
            return parsed if isinstance(parsed, dict) else None
        return result if isinstance(result, dict) else None

    def set_exact(self, stock_code: str, style: str, data: dict, price: float):
        """写入L1精确缓存"""
        key = self.l1_key(stock_code, style)
        self._l1_cache.set(key, json.dumps(data, ensure_ascii=False), ttl_seconds=L1_TTL)
        # 同时写入L2
        self._add_to_l2(stock_code, style, data, price)

    # ── L2: 语义匹配 ──

    def get_semantic(self, stock_code: str, style: str, stock_data: dict) -> dict | None:
        """L2语义匹配 - 特征向量余弦相似度"""
        if not stock_data:
            return None
        vec = extract_feature_vector(stock_data)
        best_score = 0.0
        best_entry = None

        with self._lock:
            for entry in self._l2_entries:
                if entry.stock_code == stock_code and entry.style == style:
                    continue  # 同股票不匹配不同日数据
                if entry.expires_at < time.time():
                    continue  # 已过期
                score = cosine_similarity(vec, entry.feature_vector)
                if score > best_score:
                    best_score = score
                    best_entry = entry

        if best_score >= SIMILARITY_THRESHOLD and best_entry:
            logger.info(f"[StockCache] L2命中 {stock_code}/{style} (similarity={best_score:.3f})")
            return best_entry.data
        return None

    def _add_to_l2(self, stock_code: str, style: str, data: dict, price: float):
        """添加到L2语义缓存"""
        vec = extract_feature_vector(data)
        entry = CacheEntry(
            stock_code=stock_code,
            style=style,
            data=data,
            feature_vector=vec,
            price=price,
            created_at=time.time(),
            expires_at=time.time() + L1_TTL,
        )
        with self._lock:
            self._l2_entries.append(entry)
            if len(self._l2_entries) > MAX_SEMANTIC_ENTRIES:
                # 删除最旧的20%
                cutoff = len(self._l2_entries) // 5
                self._l2_entries = self._l2_entries[cutoff:]

    # ── 失效策略 ──

    def invalidate(self, stock_code: str | None = None, price: float | None = None):
        """失效缓存条目

        触发条件:
        - price变动>5%
        - 明示指定stock_code
        """
        now = time.time()
        with self._lock:
            remaining = []
            for entry in self._l2_entries:
                should_remove = False
                if stock_code and entry.stock_code == stock_code:
                    if price is not None and entry.price > 0:
                        change = abs(price - entry.price) / entry.price
                        if change > 0.05:
                            should_remove = True
                    else:
                        should_remove = True
                if not should_remove and entry.expires_at < now:
                    should_remove = True
                if not should_remove:
                    remaining.append(entry)
            self._l2_entries = remaining

        if stock_code:
            key = self.l1_key(stock_code, "any")
            self._l1_cache.invalidate(key)

    def invalidate_by_market_state(self, old_regime: str, new_regime: str):
        """市场状态变化时清空L2缓存"""
        if old_regime != new_regime:
            logger.info(f"[StockCache] 市场状态 {old_regime}→{new_regime}, 清空L2")
            with self._lock:
                self._l2_entries.clear()

    def clear_all(self):
        """清空所有缓存"""
        self._l1_cache.invalidate()
        with self._lock:
            self._l2_entries.clear()

    def stats(self) -> dict:
        """缓存统计"""
        with self._lock:
            l2_count = len(self._l2_entries)
        return {
            "l2_entries": l2_count,
            "l2_max": MAX_SEMANTIC_ENTRIES,
            "l1_ttl": L1_TTL,
        }


# 全局单例
_cache: StockAnalysisCache | None = None
_cache_lock = threading.Lock()


def get_stock_cache() -> StockAnalysisCache:
    global _cache  # noqa: PLW0603
    if _cache is None:
        with _cache_lock:
            if _cache is None:
                _cache = StockAnalysisCache()
    return _cache
