"""ZZShare 因子模块 — 从 MarketSnapshot 加载热度/涨停/板块数据, 注入筛选流水线

用法:
    zf = ZZShareFactors()
    zf.load()
    if zf.is_hot_stock("600519"):
        stock["_hot_bonus"] += 2
"""

import json
import logging

logger = logging.getLogger(__name__)

# MarketSnapshot 中 zzshare 数据的 key 名
SNAP_HOT = "hot_stocks_ths"  # 同花顺热搜 Top 50
SNAP_LIMIT_UP = "uplimit_stocks"  # 涨停股票
SNAP_SECTOR_CONCEPT = "sector_rank_concept"  # 概念板块排行
SNAP_SECTOR_INDUSTRY = "sector_rank_industry"  # 行业板块排行


class ZZShareFactors:
    """加载 zzshare MarketSnapshot 数据, 提供因子查询"""

    def __init__(self):
        self._loaded = False
        # 热搜: set of stock codes (如 {"002969", "600519"})
        self.hot_codes: set[str] = set()
        # 涨停: set of stock codes
        self.limit_up_codes: set[str] = set()
        # 概念板块排行: dict {plate_name: rank_index} (rank 越小越强)
        self.concept_ranks: dict[str, int] = {}
        # 行业板块排行: dict {industry_name: rank_index}
        self.industry_ranks: dict[str, int] = {}
        # 板块名称 → 涨跌幅映射
        self.concept_changes: dict[str, float] = {}
        self.industry_changes: dict[str, float] = {}
        # 每只股票的可选板块列表 (概念板块)  # noqa: ERA001
        self.stock_concepts: dict[str, list[str]] = {}
        # 辅助: 代码→行业名 (由外部填入, 来自 StockInfo.industry)
        self.stock_industries: dict[str, str] = {}

    def load(self) -> bool:
        """从 MarketSnapshot 加载所有 zzshare 数据"""
        try:
            from shared.models import MarketSnapshot, get_session

            session = get_session()
            rows = (
                session.query(MarketSnapshot)
                .filter(
                    MarketSnapshot.snapshot_type.in_(
                        [
                            SNAP_HOT,
                            SNAP_LIMIT_UP,
                            SNAP_SECTOR_CONCEPT,
                            SNAP_SECTOR_INDUSTRY,
                        ]
                    )
                )
                .all()
            )
            session.close()
        except Exception as e:
            logger.warning("[ZZFactors] DB query failed: %s", e)
            return False

        snapshots = {r.snapshot_type: r.data_json for r in rows}

        self._parse_hot(snapshots.get(SNAP_HOT))
        self._parse_limit_up(snapshots.get(SNAP_LIMIT_UP))
        self._parse_sector_rank(snapshots.get(SNAP_SECTOR_CONCEPT), "concept")
        self._parse_sector_rank(snapshots.get(SNAP_SECTOR_INDUSTRY), "industry")

        self._loaded = True
        logger.info(
            "[ZZFactors] loaded: %d hot, %d limit_up, %d concept plates, %d industry plates",
            len(self.hot_codes),
            len(self.limit_up_codes),
            len(self.concept_ranks),
            len(self.industry_ranks),
        )
        return True

    # ── 数据解析 ──

    def _parse_hot(self, raw: str | None):
        """解析 ths_hot_top 数据 (list of dicts with symbol_code)"""
        if not raw:
            return
        try:
            items = json.loads(raw)
            for item in items:
                code = self._normalize_code(item.get("symbol_code", ""))
                if code:
                    self.hot_codes.add(code)
        except (json.JSONDecodeError, TypeError):
            pass

    def _parse_limit_up(self, raw: str | None):
        """解析 uplimit_stocks 数据 (list of dicts with stock_code)"""
        if not raw:
            return
        try:
            items = json.loads(raw)
            for item in items:
                code = self._normalize_code(item.get("stock_code", item.get("symbol_code", "")))
                if code:
                    self.limit_up_codes.add(code)
        except (json.JSONDecodeError, TypeError):
            pass

    def _parse_sector_rank(self, raw: str | None, kind: str):
        """解析板块排行数据 (list of dicts with plate_name, 涨跌幅, 排名等)"""
        if not raw:
            return
        try:
            items = json.loads(raw)
            target = self.concept_ranks if kind == "concept" else self.industry_ranks
            chg_target = self.concept_changes if kind == "concept" else self.industry_changes
            for i, item in enumerate(items):
                name = str(item.get("plate_name", item.get("name", "")) or "")
                rank = item.get("rank", i + 1)
                if isinstance(rank, (int, float)):
                    target[name] = int(rank)
                chg = item.get(
                    "rate", item.get("涨跌幅", item.get("change_pct", item.get("pct_chg", 0)))
                )
                if chg:
                    chg_target[name] = float(chg)
        except (json.JSONDecodeError, TypeError):
            pass

    @staticmethod
    def _normalize_code(code: str) -> str:
        """标准化股票代码: '002969' → '002969', 去掉 .SH/.SZ 后缀"""
        c = code.strip().upper().replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
        if c and c.isdigit():
            return c
        return ""

    # ── 查询接口 ──

    def is_hot_stock(self, code: str) -> bool:
        """是否在同花顺热搜 Top 50"""
        return self._normalize_code(code) in self.hot_codes

    def is_limit_up_stock(self, code: str) -> bool:
        """是否在涨停名单中"""
        return self._normalize_code(code) in self.limit_up_codes

    def get_sector_rank(self, industry: str, kind: str = "industry") -> int | None:
        """获取行业/概念板块排名 (1=最强), None=未找到"""
        d = self.industry_ranks if kind == "industry" else self.concept_ranks
        return d.get(industry)

    def get_sector_change(self, industry: str, kind: str = "industry") -> float | None:
        """获取行业/概念板块涨跌幅"""
        d = self.industry_changes if kind == "industry" else self.concept_changes
        return d.get(industry)

    def hot_stock_bonus(self, code: str) -> float:
        """热度加分: 热搜 +1.5, 涨停 +1.0"""
        score = 0.0
        if self.is_hot_stock(code):
            score += 1.5
        if self.is_limit_up_stock(code):
            score += 1.0
        return score

    def sector_strength_bonus(self, stock: dict) -> float:
        """行业强度加分: 根据 stock.industry 在 sector_rank 中的排名"""
        industry = stock.get("industry", stock.get("industry_name", ""))
        if not industry:
            return 0.0

        rank = None

        # 先查行业板块排行
        r = self.get_sector_rank(industry, "industry")
        if r is not None:
            rank = r

        # 查不到再尝试概念板块
        if rank is None:
            r = self.get_sector_rank(industry, "concept")
            if r is not None:
                rank = r

        if rank is None:
            return 0.0

        # 排名 1-20 → 分档加分 (排名越小分越高)
        if rank <= 3:
            return 2.0
        if rank <= 8:
            return 1.5
        if rank <= 15:
            return 0.5
        return 0.0
