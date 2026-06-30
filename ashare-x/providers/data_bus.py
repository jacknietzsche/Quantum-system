"""数据库优先数据总线（完整版）。

设计依据: S05 §5.1, experiments exp6.1。
数据库优先，API为辅。增量更新，永久存储。

所有数据获取遵循统一模式:
1. 查询数据库
2. 若无数据或数据过期，调用API获取
3. 存入数据库
4. 返回数据
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, wait
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("ashare-x.providers.data_bus")

# 各类数据在数据库中的过期时间（秒）
_STALE_THRESHOLD = {
    "kline": 3600 * 6,        # K线6小时
    "stock_info": 3600,       # 股票信息1小时
    "fundamentals": 3600 * 12, # 基本面12小时
    "financial": 3600 * 24,   # 财务报表24小时
    "news": 3600 * 2,         # 新闻2小时
    "sentiment": 1800,         # 情绪数据30分钟
    "market_breadth": 14400,   # 市场广度4小时（日频交易无需更频繁）
    "market_overview": 14400,  # 市场概览4小时（避免API超时拖慢再平衡）
}


def _safe_float(value) -> float | None:
    """安全转换为float，处理'-'、None、空字符串等。"""
    if value is None or value in ("", "-"):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _run_with_timeout(fn, timeout: float, *args, **kwargs):
    """在线程池中执行同步函数并设置超时，避免外部API挂起。"""
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(fn, *args, **kwargs)
    try:
        return future.result(timeout=timeout)
    except FutureTimeoutError:
        logger.warning("数据获取超时 (%.1fs): %s", timeout, fn.__name__)
        raise
    finally:
        # 不等待后台线程结束，避免阻塞主流程
        executor.shutdown(wait=False)


class DatabaseFirstDataBus:
    """数据库优先的数据总线。"""

    # 缓存 stock_zh_a_spot_em() 结果（5000+股票全量快照，避免重复调用）
    _spot_cache: dict | None = None
    _spot_cache_time: datetime | None = None
    _spot_cache_ttl = 300  # 5分钟
    _spot_cache_failed = False  # 标记全量快照API失败，避免短时间内重复尝试
    _spot_cache_fail_time: datetime | None = None
    _spot_cache_lock = threading.Lock()  # 保护spot缓存读写

    def __init__(self, db_path: str = "runtime/investment.db"):
        self.db_path = db_path
        self._adapter_local = threading.local()
        self._ensure_db()

    def _connect(self) -> sqlite3.Connection:
        """创建带WAL模式+忙超时的DB连接。"""
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _ensure_db(self):
        """确保数据库和表存在。"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kline_daily (
                stock_code TEXT, trade_date TEXT, open REAL, high REAL, low REAL,
                close REAL, volume REAL, amount REAL, change_pct REAL, turnover_rate REAL,
                PRIMARY KEY (stock_code, trade_date)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_info (
                stock_code TEXT PRIMARY KEY, stock_name TEXT, category TEXT, industry TEXT,
                pe_ratio REAL, pb_ratio REAL, roe REAL, latest_price REAL, change_pct REAL,
                volume REAL, amount REAL, turnover_rate REAL,
                ma5 REAL, ma20 REAL, ma60 REAL, rsi_14 REAL, macd REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_snapshot (
                snapshot_type TEXT PRIMARY KEY, trade_date TEXT, data_json TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fund_metric_hist (
                stock_code TEXT, report_period TEXT, revenue REAL, net_income REAL,
                gross_profit REAL, roe REAL, roa REAL, debt_to_equity REAL,
                gross_margin REAL, net_margin REAL, revenue_yoy REAL, net_income_yoy REAL,
                PRIMARY KEY (stock_code, report_period)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS news_cache (
                stock_code TEXT, news_date TEXT, title TEXT, content TEXT,
                source TEXT, url TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (stock_code, title, news_date)
            )
        """)
        # Phase 10: 模拟持仓 + 交易计划
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_account (
                id INTEGER PRIMARY KEY DEFAULT 1,
                initial_capital REAL DEFAULT 100000,
                cash REAL DEFAULT 100000,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_holdings (
                stock_code TEXT PRIMARY KEY,
                stock_name TEXT,
                shares INTEGER,
                avg_cost REAL,
                entry_date TEXT,
                last_update TEXT,
                t1_blocked_shares INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_code TEXT,
                stock_name TEXT,
                action TEXT,
                shares INTEGER,
                price REAL,
                amount REAL,
                commission REAL,
                stamp_tax REAL,
                trade_date TEXT,
                reasoning TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                stock_code TEXT PRIMARY KEY,
                stock_name TEXT,
                score REAL,
                style TEXT,
                added_date TEXT,
                last_analysis_date TEXT,
                analysis_count INTEGER DEFAULT 0,
                priority INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_plans (
                id TEXT PRIMARY KEY,
                date TEXT,
                plan_json TEXT,
                actions_count INTEGER,
                buy_count INTEGER,
                sell_count INTEGER,
                hold_count INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 索引优化
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_kline_code_date "
            "ON kline_daily(stock_code, trade_date)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_news_code_date "
            "ON news_cache(stock_code, news_date DESC)"
        )
        conn.commit()
        conn.close()

    # ══════════════════════════════════════════
    # K线数据
    # ══════════════════════════════════════════

    def get_kline(self, code: str, days: int = 365) -> list[dict] | None:
        """
        获取日K线数据（数据库优先 + 增量更新）。
        1. 查询数据库
        2. 如果有数据但不是最新，只从API获取缺失的日期
        3. 如果无数据，从API获取全部
        4. 返回数据
        """
        # Step 1: 查询数据库
        db_data = self._query_kline(code, days)
        if db_data and len(db_data) > 0:
            # 检查是否过期（最后一条日期是否在过期阈值内）
            last_date = db_data[-1].get("trade_date", "")
            today = datetime.now().strftime("%Y-%m-%d")
            if last_date >= today:
                logger.info("K线从数据库获取（最新）: %s, %d条", code, len(db_data))
                return db_data
            # 数据过期，尝试增量更新
            incremental = self._fetch_kline_incremental(code, last_date)
            if incremental:
                self._save_kline(code, incremental)
                # 重新查询完整数据
                db_data = self._query_kline(code, days)
                if db_data:
                    logger.info("K线增量更新: %s, +%d条, 共%d条", code, len(incremental), len(db_data))
                    return db_data
            # 增量更新失败，返回旧数据
            logger.info("K线从数据库获取（旧数据）: %s, %d条", code, len(db_data))
            return db_data

        # Step 2: 从API全量获取
        api_data = self._fetch_kline_from_api(code, days)
        if api_data:
            saved = self._save_kline(code, api_data)
            logger.info("K线从API获取并保存: %s, %d条/%d条入库", code, len(api_data), saved)
            return api_data

        logger.warning("无法获取K线数据: %s", code)
        return None

    def _fetch_kline_incremental(self, code: str, last_date: str) -> list[dict] | None:
        """只获取last_date之后的新K线数据。"""
        try:
            from datetime import datetime as dt

            start = dt.strptime(last_date, "%Y-%m-%d")
            days_since = (dt.now() - start).days + 1
            if days_since <= 0:
                return None
            return self._fetch_kline_from_api(code, days_since)
        except Exception as e:
            logger.debug("增量获取K线失败 %s: %s", code, e)
            return None

    def _query_kline(self, code: str, days: int) -> list[dict] | None:
        """从数据库查询K线。"""
        try:
            conn = self._connect()
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            cursor = conn.execute(
                "SELECT stock_code, trade_date, open, high, low, close, volume, amount "
                "FROM kline_daily WHERE stock_code=? AND trade_date>=? ORDER BY trade_date",
                (code, start_date),
            )
            rows = cursor.fetchall()
            conn.close()
            if not rows:
                return None
            return [
                {
                    "stock_code": r[0],
                    "trade_date": r[1],
                    "open": r[2],
                    "high": r[3],
                    "low": r[4],
                    "close": r[5],
                    "volume": r[6],
                    "amount": r[7],
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning("查询K线失败 %s: %s", code, e)
            return None

    def _fetch_kline_from_api(self, code: str, days: int) -> list[dict] | None:
        """从API获取K线（按K线优先级尝试，新浪优先）。"""
        adapters = sorted(
            self._load_adapters(),
            key=lambda a: getattr(a, "kline_priority", getattr(a, "priority", 99)),
        )
        for adapter in adapters:
            try:
                data = adapter.fetch_kline(code, days)
                if data:
                    logger.info("从 %s 获取K线成功: %s, %d条", adapter.name, code, len(data))
                    return data
            except Exception as e:
                logger.warning("从 %s 获取K线失败: %s", adapter.name, e)
        return None

    def _save_kline(self, code: str, data: list[dict]) -> int:
        """保存K线到数据库（增量）。"""
        conn = self._connect()
        count = 0
        for row in data:
            try:
                volume = row.get("volume")
                close = row.get("close")
                amount = row.get("amount")
                if amount is None or amount == 0:
                    amount = (volume or 0) * (close or 0)
                conn.execute(
                    "INSERT OR IGNORE INTO kline_daily "
                    "(stock_code, trade_date, open, high, low, close, volume, amount) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        code,
                        row["trade_date"],
                        row.get("open"),
                        row.get("high"),
                        row.get("low"),
                        close,
                        volume,
                        amount,
                    ),
                )
                count += 1
            except Exception:
                pass
        conn.commit()
        conn.close()
        return count

    # ══════════════════════════════════════════
    # 股票基础信息
    # ══════════════════════════════════════════

    def get_stock_info(self, code: str) -> dict | None:
        """
        获取股票基础信息（数据库优先）。
        1. 查询数据库
        2. 若无数据或数据过期，从API获取
        3. 保存到数据库
        4. 返回完整字段
        """
        # Step 1: 查询数据库
        db_data = self._query_stock_info(code)
        if db_data and not self._is_stale(db_data.get("updated_at"), "stock_info"):
            logger.info("股票信息从数据库获取: %s", code)
            return db_data

        # Step 2: 从API获取
        adapters = self._load_adapters()
        for adapter in adapters:
            try:
                data = adapter.fetch_basic(code)
                if data:
                    # Step 3: 保存到数据库
                    self._save_stock_info(code, data)
                    logger.info("股票信息从API获取并保存: %s (via %s)", code, adapter.name)
                    # Step 4: 返回合并后的数据
                    if db_data:
                        db_data.update(data)
                        return db_data
                    return data
            except Exception:
                pass

        # API获取失败但数据库有旧数据，返回旧数据
        if db_data:
            logger.info("股票信息使用数据库旧数据: %s", code)
            return db_data

        return None

    def _query_stock_info(self, code: str) -> dict | None:
        """从数据库查询股票信息（返回完整字段）。"""
        try:
            conn = self._connect()
            cursor = conn.execute("SELECT * FROM stock_info WHERE stock_code=?", (code,))
            row = cursor.fetchone()
            conn.close()
            if not row:
                return None
            return {
                "stock_code": row[0],
                "stock_name": row[1],
                "category": row[2],
                "industry": row[3],
                "pe_ratio": row[4],
                "pb_ratio": row[5],
                "roe": row[6],
                "latest_price": row[7],
                "change_pct": row[8],
                "volume": row[9],
                "amount": row[10],
                "turnover_rate": row[11],
                "ma5": row[12],
                "ma20": row[13],
                "ma60": row[14],
                "rsi_14": row[15],
                "macd": row[16],
                "updated_at": row[18] if len(row) > 18 else row[17] if len(row) > 17 else None,
            }
        except Exception as e:
            logger.warning("查询股票信息失败 %s: %s", code, e)
            return None

    def _save_stock_info(self, code: str, data: dict):
        """保存股票信息到数据库（保留已有category/industry字段）。"""
        conn = self._connect()
        # 先读取已有的category和industry（INSERT OR REPLACE会清空未列出的列）
        existing_cat = ""
        existing_ind = ""
        try:
            cur = conn.execute("SELECT category, industry FROM stock_info WHERE stock_code=?", (code,))
            row = cur.fetchone()
            if row:
                existing_cat = row[0] or ""
                existing_ind = row[1] or ""
        except Exception:
            pass
        # 优先使用data中的值，其次保留已有值
        industry_val = data.get("industry") or existing_ind
        category_val = data.get("category") or existing_cat
        conn.execute(
            "INSERT OR REPLACE INTO stock_info "
            "(stock_code, stock_name, category, industry, pe_ratio, pb_ratio, roe, latest_price, "
            "change_pct, volume, amount, turnover_rate, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                code,
                data.get("stock_name", ""),
                category_val,
                industry_val,
                data.get("pe_ratio") or 0,
                data.get("pb_ratio") or 0,
                data.get("roe") or 0,
                data.get("latest_price") or 0,
                data.get("change_pct") or 0,
                data.get("volume") or 0,
                data.get("amount") or 0,
                data.get("turnover_rate") or 0,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

    # ══════════════════════════════════════════
    # 基本面/财务数据
    # ══════════════════════════════════════════

    def get_fundamentals(self, code: str) -> dict | None:
        """
        获取基本面数据（数据库优先）。
        1. 查询 stock_info + fund_metric_hist 表
        2. 若无数据或过期，从API获取
        3. 存入数据库
        4. 返回合并数据
        """
        # Step 1: 查询数据库
        stock_info = self.get_stock_info(code)  # DB优先 → API → 存库
        fin_metrics = self._query_fund_metrics(code)
        snapshot = self._query_snapshot(f"fundamentals_{code}")

        db_result: dict = {}
        if stock_info:
            db_result.update({
                "stock_code": code,
                "stock_name": stock_info.get("stock_name", ""),
                "pe_ratio": stock_info.get("pe_ratio"),
                "pb_ratio": stock_info.get("pb_ratio"),
                "roe": stock_info.get("roe"),
                "latest_price": stock_info.get("latest_price"),
                "change_pct": stock_info.get("change_pct"),
                "industry": stock_info.get("industry"),
            })
        if fin_metrics:
            latest = fin_metrics[0]
            db_result.update({
                "report_period": latest.get("report_period"),
                "revenue": latest.get("revenue"),
                "net_income": latest.get("net_income"),
                "roe": latest.get("roe") or db_result.get("roe"),
                "roa": latest.get("roa"),
                "gross_margin": latest.get("gross_margin"),
                "net_margin": latest.get("net_margin"),
                "debt_to_equity": latest.get("debt_to_equity"),
                "revenue_yoy": latest.get("revenue_yoy"),
                "profit_yoy": latest.get("net_income_yoy"),
            })
        if snapshot and not self._is_stale(snapshot.get("updated_at"), "fundamentals"):
            db_result.update(snapshot["data"])

        # 如果数据库有足够的数据，直接返回
        if db_result and db_result.get("pe_ratio") and db_result.get("roe"):
            logger.info("基本面数据从数据库获取: %s", code)
            db_result.setdefault("revenue_growth", db_result.get("revenue_yoy"))
            db_result.setdefault("profit_growth", db_result.get("net_income_yoy"))
            db_result.setdefault("profit_yoy", db_result.get("net_income_yoy"))
            db_result.setdefault("dividend_yield", None)
            return db_result

        # Step 2: 从API获取
        api_data = self._fetch_fundamentals_from_api(code)
        if api_data:
            # Step 3: 存入数据库
            self._save_fundamentals(code, api_data)
            logger.info("基本面数据从API获取并保存: %s", code)
            # Step 4: 合并返回
            db_result.update(api_data)
            db_result.setdefault("revenue_growth", db_result.get("revenue_yoy"))
            db_result.setdefault("profit_growth", db_result.get("net_income_yoy"))
            db_result.setdefault("profit_yoy", db_result.get("net_income_yoy"))
            db_result.setdefault("dividend_yield", None)
            return db_result if db_result else None

        # API失败但有数据库旧数据
        if db_result:
            logger.info("基本面数据使用数据库旧数据: %s", code)
            db_result.setdefault("revenue_growth", db_result.get("revenue_yoy"))
            db_result.setdefault("profit_growth", db_result.get("net_income_yoy"))
            db_result.setdefault("profit_yoy", db_result.get("net_income_yoy"))
            db_result.setdefault("dividend_yield", None)
            return db_result

        return None

    def _query_fund_metrics(self, code: str) -> list[dict]:
        """从数据库查询财务指标历史。"""
        try:
            conn = self._connect()
            cursor = conn.execute(
                "SELECT * FROM fund_metric_hist WHERE stock_code=? "
                "ORDER BY report_period DESC",
                (code,),
            )
            rows = cursor.fetchall()
            conn.close()
            return [
                {
                    "stock_code": r[0],
                    "report_period": r[1],
                    "revenue": r[2],
                    "net_income": r[3],
                    "gross_profit": r[4],
                    "roe": r[5],
                    "roa": r[6],
                    "debt_to_equity": r[7],
                    "gross_margin": r[8],
                    "net_margin": r[9],
                    "revenue_yoy": r[10],
                    "net_income_yoy": r[11],
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning("查询财务指标失败 %s: %s", code, e)
            return []

    def _fetch_fundamentals_from_api(self, code: str) -> dict | None:
        """从AKShare获取基本面数据。"""
        from providers.normalizer import StockCodeNormalizer

        pure = StockCodeNormalizer.to_db(code)
        result: dict = {}

        try:
            import akshare as ak

            # 个股基本信息（行业、上市日期、总股本等）
            try:
                individual_info = ak.stock_individual_info_em(symbol=pure)
                if individual_info is not None and not individual_info.empty:
                    info_dict = {
                        str(row["item"]): row["value"]
                        for _, row in individual_info.iterrows()
                    }
                    result["industry"] = info_dict.get("行业", "")
                    result["listing_date"] = info_dict.get("上市时间", "")
                    result["total_share_capital"] = info_dict.get("总股本", "")
                    result["circulating_share_capital"] = info_dict.get("流通股", "")
                    result["total_market_cap"] = info_dict.get("总市值", "")
                    result["circulating_market_cap"] = info_dict.get("流通市值", "")
            except Exception as e:
                logger.debug("获取个股信息失败 %s: %s", pure, e)

            # 财务摘要（长格式：行=指标，列=报告期）
            try:
                fin_df = ak.stock_financial_abstract(symbol=pure)
                if fin_df is not None and not fin_df.empty:
                    # 找到最新报告期列（第3列开始是日期）
                    date_cols = [
                        c for c in fin_df.columns
                        if str(c).isdigit() and len(str(c)) == 8
                    ]
                    if date_cols:
                        latest_col = date_cols[0]  # 第一列就是最新
                        # 按"指标"列查找各指标行
                        metric_col = fin_df.columns[1]  # 第2列是指标名
                        for _, row in fin_df.iterrows():
                            metric_name = str(row[metric_col])
                            val = _safe_float(row[latest_col])
                            if val is None:
                                continue
                            # 先到先得：只设置尚未赋值的指标，避免后续重复行覆盖
                            if "ROE" in metric_name and not result.get("roe"):
                                result["roe"] = val
                            elif "ROA" in metric_name and not result.get("roa"):
                                result["roa"] = val
                            elif "毛利" in metric_name and not result.get("gross_margin"):
                                result["gross_margin"] = val
                            elif "净利率" in metric_name and not result.get("net_margin"):
                                result["net_margin"] = val
                            elif "资产负债率" in metric_name and not result.get("debt_to_equity"):
                                result["debt_to_equity"] = val
                            elif "归母净利润" in metric_name and not result.get("net_income"):
                                result["net_income"] = val
                            elif (
                                "营业总收入" in metric_name
                                and "增长" not in metric_name
                                and not result.get("revenue")
                            ):
                                result["revenue"] = val
                            elif (
                                "营业总收入" in metric_name
                                and "增长" in metric_name
                                and not result.get("revenue_yoy")
                            ):
                                result["revenue_yoy"] = val
                            elif (
                                "增长" in metric_name
                                and "营业总收入" not in metric_name
                                and not result.get("net_income_yoy")
                            ):
                                result["net_income_yoy"] = val
                        result["report_period"] = latest_col
                        logger.debug(
                            "财务摘要解析完成 %s: ROE=%s, 毛利率=%s",
                            pure, result.get("roe"), result.get("gross_margin"),
                        )
            except Exception as e:
                logger.debug("获取财务摘要失败 %s: %s", pure, e)

            # 实时行情补充PE/PB（使用缓存的快照数据）
            spot = self._get_spot_data(code)
            if spot:
                result.setdefault("pe_ratio", spot.get("pe_ratio"))
                result.setdefault("pb_ratio", spot.get("pb_ratio"))
                result.setdefault("turnover_rate", spot.get("turnover_rate"))
                result.setdefault("latest_price", spot.get("latest_price"))
                result.setdefault("change_pct", spot.get("change_pct"))
                if not result.get("stock_name"):
                    result["stock_name"] = spot.get("stock_name", "")

        except ImportError:
            logger.warning("akshare未安装，基本面数据可能不完整")
        except Exception as e:
            logger.warning("从API获取基本面数据失败 %s: %s", code, e)

        return result if result else None

    def _save_fundamentals(self, code: str, data: dict):
        """保存基本面数据到数据库。"""
        # 保存到 stock_info
        if data.get("pe_ratio") or data.get("latest_price"):
            self._save_stock_info(code, data)

        # 保存到 fund_metric_hist
        if data.get("report_period"):
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO fund_metric_hist "
                    "(stock_code, report_period, revenue, net_income, gross_profit, "
                    "roe, roa, debt_to_equity, gross_margin, net_margin, "
                    "revenue_yoy, net_income_yoy) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        code,
                        data.get("report_period", ""),
                        data.get("revenue"),
                        data.get("net_income"),
                        data.get("gross_profit"),
                        data.get("roe"),
                        data.get("roa"),
                        data.get("debt_to_equity"),
                        data.get("gross_margin"),
                        data.get("net_margin"),
                        data.get("revenue_yoy"),
                        data.get("net_income_yoy"),
                    ),
                )
                conn.commit()
            except Exception as e:
                logger.warning("保存财务指标失败 %s: %s", code, e)
            finally:
                conn.close()

        # 保存额外字段到 market_snapshot
        extra_fields = {
            k: v
            for k, v in data.items()
            if k
            not in {
                "pe_ratio", "pb_ratio", "roe", "latest_price", "change_pct",
                "report_period", "revenue", "net_income", "gross_profit",
                "roa", "debt_to_equity", "gross_margin", "net_margin",
                "revenue_yoy", "net_income_yoy", "stock_name",
            }
        }
        if extra_fields:
            self._save_snapshot(f"fundamentals_{code}", extra_fields)

    def get_financial_statements(self, code: str) -> dict | None:
        """
        获取财务报表指标（数据库优先）。
        1. 查询 fund_metric_hist 表
        2. 若无数据，从API获取
        3. 存入数据库
        4. 返回数据
        """
        # Step 1: 查询数据库
        metrics = self._query_fund_metrics(code)
        if metrics:
            logger.info("财务指标从数据库获取: %s", code)
            latest = metrics[0]
            return {
                "report_date": latest.get("report_period", ""),
                "roe": latest.get("roe"),
                "roa": latest.get("roa"),
                "gross_margin": latest.get("gross_margin"),
                "net_margin": latest.get("net_margin"),
                "debt_ratio": latest.get("debt_to_equity"),
                "revenue": latest.get("revenue"),
                "net_income": latest.get("net_income"),
            }

        # Step 2: 从API获取
        api_data = self._fetch_financial_statements_from_api(code)
        if api_data:
            # Step 3: 存入数据库
            if api_data.get("report_period"):
                conn = self._connect()
                try:
                    conn.execute(
                        "INSERT OR REPLACE INTO fund_metric_hist "
                        "(stock_code, report_period, roe, roa, "
                        "gross_margin, net_margin, debt_to_equity) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            code,
                            api_data.get("report_period", ""),
                            api_data.get("roe"),
                            api_data.get("roa"),
                            api_data.get("gross_margin"),
                            api_data.get("net_margin"),
                            api_data.get("debt_ratio"),
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()
            logger.info("财务指标从API获取并保存: %s", code)
            return api_data

        return None

    def _fetch_financial_statements_from_api(self, code: str) -> dict | None:
        """从AKShare获取财务指标。"""
        from providers.normalizer import StockCodeNormalizer

        pure = StockCodeNormalizer.to_db(code)
        result: dict = {}

        try:
            import akshare as ak

            df = ak.stock_financial_analysis_indicator(symbol=pure)
            if df is not None and not df.empty:
                latest = df.iloc[0]
                result["report_period"] = str(latest.get("日期", ""))
                result["roe"] = _safe_float(latest.get("净资产收益率(%)"))
                result["roa"] = _safe_float(latest.get("总资产收益率(%)"))
                result["gross_margin"] = _safe_float(latest.get("销售毛利率(%)"))
                result["net_margin"] = _safe_float(latest.get("销售净利率(%)"))
                result["debt_ratio"] = _safe_float(latest.get("资产负债比率(%)"))
                result["current_ratio"] = _safe_float(latest.get("流动比率"))
                result["quick_ratio"] = _safe_float(latest.get("速动比率"))

        except ImportError:
            logger.warning("akshare未安装")
        except Exception as e:
            logger.warning("从API获取财务指标失败 %s: %s", code, e)

        return result if result else None

    # ══════════════════════════════════════════
    # 新闻数据
    # ══════════════════════════════════════════

    def get_news(self, code: str, days: int = 7) -> list[dict]:
        """
        获取股票新闻（数据库优先）。
        1. 查询 news_cache 表
        2. 若无数据或过期，从API获取
        3. 存入数据库
        4. 返回数据
        """
        # Step 1: 查询数据库
        db_news = self._query_news(code, days)
        if db_news and not self._is_news_stale(code):
            logger.info("新闻从数据库获取: %s, %d条", code, len(db_news))
            return db_news

        # Step 2: 从API获取
        api_news = self._fetch_news_from_api(code)
        if api_news:
            # Step 3: 存入数据库
            self._save_news(code, api_news)
            logger.info("新闻从API获取并保存: %s, %d条", code, len(api_news))
            # 合并数据库和API数据
            existing_titles = {n["title"] for n in db_news}
            for n in api_news:
                if n["title"] not in existing_titles:
                    db_news.insert(0, n)
            return db_news

        # API失败但数据库有旧数据
        if db_news:
            logger.info("新闻使用数据库旧数据: %s", code)
            return db_news

        return []

    def _query_news(self, code: str, days: int) -> list[dict]:
        """从数据库查询新闻。"""
        try:
            conn = self._connect()
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            cursor = conn.execute(
                "SELECT title, content, source, news_date, url "
                "FROM news_cache WHERE stock_code=? AND news_date>=? "
                "ORDER BY news_date DESC LIMIT 30",
                (code, start_date),
            )
            rows = cursor.fetchall()
            conn.close()
            return [
                {
                    "title": r[0],
                    "content": r[1],
                    "source": r[2],
                    "date": r[3],
                    "url": r[4],
                }
                for r in rows
            ]
        except Exception as e:
            logger.warning("查询新闻失败 %s: %s", code, e)
            return []

    def _is_news_stale(self, code: str) -> bool:
        """检查新闻数据是否过期（通过 market_snapshot 记录最后更新时间）。"""
        snapshot = self._query_snapshot(f"news_update_{code}")
        if not snapshot:
            return True
        return self._is_stale(snapshot.get("updated_at"), "news")

    def _fetch_news_from_api(self, code: str) -> list[dict] | None:
        """从AKShare获取股票新闻。"""
        from providers.normalizer import StockCodeNormalizer

        pure = StockCodeNormalizer.to_db(code)
        news_list: list[dict] = []

        try:
            import akshare as ak

            df = ak.stock_news_em(symbol=pure)
            if df is not None and not df.empty:
                for _, row in df.head(30).iterrows():
                    news_list.append({
                        "title": str(row.get("新闻标题", "")),
                        "content": str(row.get("新闻内容", ""))[:500],
                        "source": str(row.get("文章来源", "")),
                        "date": str(row.get("发布时间", ""))[:10],
                        "url": str(row.get("新闻链接", "")),
                    })
        except ImportError:
            logger.warning("akshare未安装")
        except Exception as e:
            logger.warning("从API获取新闻失败 %s: %s", code, e)

        return news_list if news_list else None

    def _save_news(self, code: str, news_list: list[dict]):
        """保存新闻到数据库。"""
        import contextlib

        conn = self._connect()
        for n in news_list:
            with contextlib.suppress(Exception):
                conn.execute(
                    "INSERT OR IGNORE INTO news_cache "
                    "(stock_code, news_date, title, content, source, url) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        code,
                        n.get("date", ""),
                        n.get("title", ""),
                        n.get("content", ""),
                        n.get("source", ""),
                        n.get("url", ""),
                    ),
                )
        conn.commit()
        conn.close()
        # 记录更新时间
        self._save_snapshot(f"news_update_{code}", {"updated_at": datetime.now().isoformat()})

    # ══════════════════════════════════════════
    # 情绪数据
    # ══════════════════════════════════════════

    def get_social_sentiment(self, code: str) -> dict:
        """
        获取情绪数据（数据库优先）。
        1. 查询 market_snapshot 表
        2. 若无数据或过期，从API获取
        3. 存入数据库
        4. 返回数据
        """
        # Step 1: 查询数据库
        snapshot = self._query_snapshot(f"sentiment_{code}")
        if snapshot and not self._is_stale(snapshot.get("updated_at"), "sentiment"):
            logger.info("情绪数据从数据库获取: %s", code)
            return snapshot["data"]

        # Step 2: 从API获取
        api_data = self._fetch_sentiment_from_api(code)
        if api_data:
            # Step 3: 存入数据库
            self._save_snapshot(f"sentiment_{code}", api_data)
            logger.info("情绪数据从API获取并保存: %s", code)
            return api_data

        # API失败但有旧数据
        if snapshot:
            logger.info("情绪数据使用数据库旧数据: %s", code)
            return snapshot["data"]

        return {
            "north_flow": None,
            "dragon_tiger": None,
            "turnover_rate": None,
            "fund_flow": None,
        }

    def _fetch_sentiment_from_api(self, code: str) -> dict | None:
        """从AKShare获取情绪数据。"""
        from providers.normalizer import StockCodeNormalizer

        pure = StockCodeNormalizer.to_db(code)
        result: dict = {}

        try:
            import akshare as ak

            # 1. 北向资金个股明细
            try:
                for fn_name in [
                    "stock_hsgt_individual_em",
                    "stock_hsgt_individual_detail_em",
                ]:
                    fn = getattr(ak, fn_name, None)
                    if fn:
                        try:
                            df = fn(symbol=pure)
                            if df is not None and not df.empty:
                                latest = df.iloc[-1]
                                result["north_flow"] = _safe_float(
                                    latest.get("持股数量")
                                    or latest.get("持股股数")
                                    or latest.get("净买额")
                                )
                                break
                        except Exception as e:
                            logger.debug("北向资金数据源 %s 失败: %s", fn_name, e)
                            continue
            except Exception as e:
                logger.debug("获取北向资金失败 %s: %s", pure, e)

            # 2. 龙虎榜数据
            try:
                df = ak.stock_lhb_stock_detail_em(symbol=pure)
                if df is not None and not df.empty:
                    latest = df.iloc[0]
                    result["dragon_tiger"] = {
                        "date": str(latest.get("上榜日", "")),
                        "reason": str(latest.get("解读", "")),
                        "net_buy": _safe_float(latest.get("龙虎榜净买额")),
                        "buy_amount": _safe_float(latest.get("龙虎榜买入额")),
                        "sell_amount": _safe_float(latest.get("龙虎榜卖出额")),
                    }
            except Exception as e:
                logger.debug("获取龙虎榜失败 %s: %s", pure, e)

            # 3. 换手率和实时行情（使用缓存的快照数据）
            spot = self._get_spot_data(code)
            if spot:
                result["turnover_rate"] = spot.get("turnover_rate")
                result["latest_price"] = spot.get("latest_price")
                result["change_pct"] = spot.get("change_pct")
                result["amount"] = spot.get("amount")
                result["volume"] = spot.get("volume")

            # 4. 主力资金流向
            try:
                df = ak.stock_fund_flow_individual(symbol=pure)
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    result["fund_flow"] = {
                        "date": str(latest.get("日期", "")),
                        "main_net_inflow": _safe_float(
                            latest.get("主力净流入-净额")
                        ),
                        "main_net_pct": _safe_float(
                            latest.get("主力净流入-净占比")
                        ),
                        "super_large_net": _safe_float(
                            latest.get("超大单净流入-净额")
                        ),
                        "large_net": _safe_float(latest.get("大单净流入-净额")),
                        "medium_net": _safe_float(latest.get("中单净流入-净额")),
                        "small_net": _safe_float(latest.get("小单净流入-净额")),
                    }
            except Exception as e:
                logger.debug("获取资金流向失败 %s: %s", pure, e)

        except ImportError:
            logger.warning("akshare未安装")
        except Exception as e:
            logger.warning("从API获取情绪数据失败 %s: %s", code, e)

        return result if result else None

    # ══════════════════════════════════════════
    # 市场广度
    # ══════════════════════════════════════════

    def get_market_breadth(self) -> dict:
        """
        获取市场广度（数据库优先）。
        1. 查询 market_snapshot 表
        2. 若无数据或过期，从API获取
        3. 存入数据库
        4. 返回数据
        """
        # Step 1: 查询数据库
        snapshot = self._query_snapshot("market_breadth")
        if snapshot and not self._is_stale(snapshot.get("updated_at"), "market_breadth"):
            logger.info("市场广度从数据库获取")
            return snapshot["data"]

        # Step 2: 从API获取
        api_data = self._fetch_market_breadth_from_api()
        if api_data:
            # Step 3: 存入数据库
            self._save_snapshot("market_breadth", api_data)
            logger.info("市场广度从API获取并保存")
            return api_data

        # API失败但有旧数据
        if snapshot:
            logger.info("市场广度使用数据库旧数据")
            return snapshot["data"]

        # 没有任何数据时保存默认快照，避免每次调用都触发超时API
        default_breadth = {
            "total": 0, "up": 0, "down": 0, "flat": 0,
            "limit_up": 0, "limit_down": 0, "up_ratio": 0.0,
        }
        self._save_snapshot("market_breadth", default_breadth)
        logger.warning("市场广度无可用数据，已保存默认快照")
        return default_breadth

    def _fetch_market_breadth_from_api(self) -> dict | None:
        """从AKShare获取市场广度（带2秒超时，避免同步API挂起再平衡）。"""
        try:
            import akshare as ak

            spot = _run_with_timeout(ak.stock_zh_a_spot_em, 10.0)
            if spot is not None and not spot.empty and "涨跌幅" in spot.columns:
                pct = spot["涨跌幅"]
                breadth = {
                    "total": len(spot),
                    "up": int((pct > 0).sum()),
                    "down": int((pct < 0).sum()),
                    "flat": int((pct == 0).sum()),
                    "limit_up": int((pct >= 9.5).sum()),
                    "limit_down": int((pct <= -9.5).sum()),
                    "up_ratio": round(
                        int((pct > 0).sum()) / max(len(spot), 1) * 100, 1
                    ),
                }
                # 同时更新全量快照缓存
                cache: dict = {}
                for _, r in spot.iterrows():
                    code_str = str(r.get("代码", ""))
                    cache[code_str] = {
                        "stock_name": str(r.get("名称", "")),
                        "latest_price": _safe_float(r.get("最新价")),
                        "change_pct": _safe_float(r.get("涨跌幅")),
                        "volume": _safe_float(r.get("成交量")),
                        "amount": _safe_float(r.get("成交额")),
                        "pe_ratio": _safe_float(r.get("市盈率-动态")),
                        "pb_ratio": _safe_float(r.get("市净率")),
                        "turnover_rate": _safe_float(r.get("换手率")),
                    }
                with DatabaseFirstDataBus._spot_cache_lock:
                    DatabaseFirstDataBus._spot_cache = cache
                    DatabaseFirstDataBus._spot_cache_time = datetime.now()
                logger.info("全量快照缓存已更新（市场广度）: %d只股票", len(cache))
                return breadth
        except ImportError:
            logger.warning("akshare未安装")
        except Exception as e:
            logger.warning("从API获取市场广度失败: %s", e)

        return None

    # ══════════════════════════════════════════
    # 市场概览（指数数据）
    # ══════════════════════════════════════════

    def get_market_overview(self) -> dict:
        """
        获取市场概览（数据库优先）。
        1. 查询 market_snapshot 表
        2. 若无数据或过期，从API获取
        3. 存入数据库
        4. 返回数据
        """
        # Step 1: 查询数据库
        snapshot = self._query_snapshot("market_overview")
        if snapshot and not self._is_stale(snapshot.get("updated_at"), "market_overview"):
            logger.info("市场概览从数据库获取")
            return snapshot["data"]

        # Step 2: 从API获取
        api_data = self._fetch_market_overview_from_api()
        if api_data:
            # Step 3: 存入数据库
            self._save_snapshot("market_overview", api_data)
            logger.info("市场概览从API获取并保存")
            return api_data

        # API失败但有旧数据
        if snapshot:
            logger.info("市场概览使用数据库旧数据")
            return snapshot["data"]

        # 没有任何数据时保存默认快照，避免每次调用都触发超时API
        default_overview = {
            "indices": {},
            "market_state": "NEUTRAL",
            "north_flow": 0,
            "advance_count": 0,
            "decline_count": 0,
        }
        self._save_snapshot("market_overview", default_overview)
        logger.warning("市场概览无可用数据，已保存默认快照")
        return default_overview

    def _fetch_market_overview_from_api(self) -> dict | None:
        """从AKShare获取市场概览（单源5秒超时，优先复用缓存避免重复API）。"""
        result: dict = {
            "indices": {},
            "market_state": "NEUTRAL",
            "north_flow": 0,
            "advance_count": 0,
            "decline_count": 0,
        }

        try:
            import akshare as ak

            def _fetch_sh_index():
                try:
                    df = _run_with_timeout(
                        ak.stock_zh_index_spot_em, 2.0, symbol="上证系列指数"
                    )
                    if df is not None and not df.empty:
                        for _, row in df.iterrows():
                            name = str(row.get("名称", ""))
                            if "上证指数" in name:
                                return {
                                    "name": name,
                                    "price": _safe_float(row.get("最新价")),
                                    "change_pct": _safe_float(row.get("涨跌幅")),
                                }
                except Exception as e:
                    logger.debug("获取上证指数失败: %s", e)
                return None

            def _fetch_sz_index():
                try:
                    df = _run_with_timeout(
                        ak.stock_zh_index_spot_em, 2.0, symbol="深证系列指数"
                    )
                    if df is not None and not df.empty:
                        for _, row in df.iterrows():
                            name = str(row.get("名称", ""))
                            if "深证成指" in name:
                                return {
                                    "sz": {
                                        "name": name,
                                        "price": _safe_float(row.get("最新价")),
                                        "change_pct": _safe_float(row.get("涨跌幅")),
                                    }
                                }
                            if "创业板指" in name:
                                return {
                                    "cyb": {
                                        "name": name,
                                        "price": _safe_float(row.get("最新价")),
                                        "change_pct": _safe_float(row.get("涨跌幅")),
                                    }
                                }
                except Exception as e:
                    logger.debug("获取深证指数失败: %s", e)
                return None

            def _fetch_north_flow():
                """获取当日北向资金净流入（禁用历史接口，避免内部循环拖垮总超时）。"""
                try:
                    fn = getattr(ak, "stock_hsgt_fund_flow_summary_em", None)
                    if fn:
                        df = _run_with_timeout(fn, 5.0)
                        if df is not None and not df.empty:
                            latest = df.iloc[-1]
                            return _safe_float(
                                latest.get("当日成交净买额")
                                or latest.get("沪股通净买额")
                                or 0
                            ) or 0
                except Exception as e:
                    logger.debug("获取北向资金失败: %s", e)
                return 0

            # 优先复用全量快照缓存计算市场广度，避免重复调用 stock_zh_a_spot_em
            breadth = self._breadth_from_spot_cache()
            if breadth is None:
                # 缓存不存在/过期，与指数、北向资金并行获取（总超时6秒）
                futures: dict = {}
                with ThreadPoolExecutor(max_workers=4) as executor:
                    futures["sh"] = executor.submit(_fetch_sh_index)
                    futures["sz"] = executor.submit(_fetch_sz_index)
                    futures["north"] = executor.submit(_fetch_north_flow)
                    futures["breadth"] = executor.submit(self._fetch_market_breadth_from_api)

                    done, _ = wait(futures.values(), timeout=3.0)
                    for f in set(futures.values()) - done:
                        f.cancel()

                sh_data = futures["sh"].result() if futures["sh"] in done else None
                if sh_data:
                    result["indices"]["sh"] = sh_data

                sz_data = futures["sz"].result() if futures["sz"] in done else None
                if isinstance(sz_data, dict):
                    result["indices"].update(sz_data)

                north_flow = futures["north"].result() if futures["north"] in done else 0
                result["north_flow"] = north_flow or 0

                breadth = futures["breadth"].result() if futures["breadth"] in done else None
                breadth = breadth or {}
            else:
                # 已有 spot cache，只需并行获取指数和北向资金（总超时6秒）
                futures: dict = {}
                with ThreadPoolExecutor(max_workers=3) as executor:
                    futures["sh"] = executor.submit(_fetch_sh_index)
                    futures["sz"] = executor.submit(_fetch_sz_index)
                    futures["north"] = executor.submit(_fetch_north_flow)

                    done, _ = wait(futures.values(), timeout=3.0)
                    for f in set(futures.values()) - done:
                        f.cancel()

                sh_data = futures["sh"].result() if futures["sh"] in done else None
                if sh_data:
                    result["indices"]["sh"] = sh_data

                sz_data = futures["sz"].result() if futures["sz"] in done else None
                if isinstance(sz_data, dict):
                    result["indices"].update(sz_data)

                north_flow = futures["north"].result() if futures["north"] in done else 0
                result["north_flow"] = north_flow or 0

            result["advance_count"] = breadth.get("up", 0)
            result["decline_count"] = breadth.get("down", 0)

            # 市场状态
            from tools.market_state import detect_market_state

            sh_change = result["indices"].get("sh", {}).get("change_pct", 0)
            result["market_state"] = detect_market_state({
                "sh_change_20d": sh_change / 100 if sh_change else 0,
                "advance_count": result["advance_count"],
                "decline_count": result["decline_count"],
                "volume": 0,
                "volume_ma20": 0,
                "north_flow_5d": result["north_flow"],
            })

        except ImportError:
            logger.warning("akshare未安装")
        except Exception as e:
            logger.warning("从API获取市场概览失败: %s", e)

        return result if result["indices"] or result["advance_count"] else None

    def _breadth_from_spot_cache(self) -> dict | None:
        """从全量快照缓存计算市场广度（避免重复API）。"""
        cache = DatabaseFirstDataBus._spot_cache
        cache_time = DatabaseFirstDataBus._spot_cache_time
        if cache is None or cache_time is None:
            return None
        age = (datetime.now() - cache_time).total_seconds()
        if age > DatabaseFirstDataBus._spot_cache_ttl:
            return None
        change_pcts = [
            _safe_float(v.get("change_pct"))
            for v in cache.values()
            if _safe_float(v.get("change_pct")) is not None
        ]
        total = len(change_pcts)
        if total == 0:
            return None
        up = sum(1 for p in change_pcts if p > 0)
        down = sum(1 for p in change_pcts if p < 0)
        flat = sum(1 for p in change_pcts if p == 0)
        return {
            "total": total,
            "up": up,
            "down": down,
            "flat": flat,
            "limit_up": sum(1 for p in change_pcts if p >= 9.5),
            "limit_down": sum(1 for p in change_pcts if p <= -9.5),
            "up_ratio": round(up / total * 100, 1),
        }

    # ══════════════════════════════════════════
    # 数据快照通用方法（market_snapshot 表）
    # ══════════════════════════════════════════

    def _query_snapshot(self, snapshot_type: str) -> dict | None:
        """从 market_snapshot 表查询JSON快照。"""
        try:
            conn = self._connect()
            cursor = conn.execute(
                "SELECT data_json, updated_at FROM market_snapshot WHERE snapshot_type=?",
                (snapshot_type,),
            )
            row = cursor.fetchone()
            conn.close()
            if not row:
                return None
            return {
                "data": json.loads(row[0]) if row[0] else {},
                "updated_at": row[1],
            }
        except Exception as e:
            logger.warning("查询快照失败 %s: %s", snapshot_type, e)
            return None

    def _save_snapshot(self, snapshot_type: str, data: Any):
        """保存JSON快照到 market_snapshot 表。"""
        conn = self._connect()
        conn.execute(
            "INSERT OR REPLACE INTO market_snapshot "
            "(snapshot_type, trade_date, data_json, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (
                snapshot_type,
                datetime.now().strftime("%Y-%m-%d"),
                json.dumps(data, ensure_ascii=False, default=str),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

    # ══════════════════════════════════════════
    # 市场快照（全市场股票列表）
    # ══════════════════════════════════════════

    def get_market_snapshot(self, force_refresh: bool = False) -> list[dict]:
        """
        获取全市场股票快照（数据库优先）。

        返回列表，每个元素包含:
          stock_code, stock_name, latest_price, change_pct,
          pe_ratio, pb_ratio, turnover_rate, volume, amount
        """
        # 1. 查询数据库快照
        snap = self._query_snapshot("all_stocks")
        if not force_refresh and snap and snap.get("data"):
            data = snap["data"]
            if isinstance(data, list) and not self._is_stale(
                snap.get("updated_at"), "stock_info"
            ):
                logger.info("全市场快照从数据库获取: %d只", len(data))
                return data

        # 2. 从API获取
        stocks: list[dict] = []
        try:
            import akshare as ak

            spot = ak.stock_zh_a_spot_em()
            if spot is not None and not spot.empty:
                for _, r in spot.iterrows():
                    code = str(r.get("代码", "")).strip()
                    name = str(r.get("名称", "")).strip()
                    if not code or not code.isdigit():
                        continue
                    stocks.append({
                        "stock_code": code,
                        "stock_name": name,
                        "latest_price": _safe_float(r.get("最新价")),
                        "change_pct": _safe_float(r.get("涨跌幅")),
                        "volume": _safe_float(r.get("成交量")),
                        "amount": _safe_float(r.get("成交额")),
                        "pe_ratio": _safe_float(r.get("市盈率-动态")),
                        "pb_ratio": _safe_float(r.get("市净率")),
                        "turnover_rate": _safe_float(r.get("换手率")),
                    })
                # 更新缓存
                with DatabaseFirstDataBus._spot_cache_lock:
                    DatabaseFirstDataBus._spot_cache = {
                        s["stock_code"]: s for s in stocks
                    }
                    DatabaseFirstDataBus._spot_cache_time = datetime.now()
                    DatabaseFirstDataBus._spot_cache_failed = False
                logger.info("全市场快照从API获取: %d只", len(stocks))
        except ImportError:
            logger.warning("akshare未安装，无法获取全市场快照")
        except Exception as e:
            logger.warning("获取全市场快照失败: %s", e)
            with DatabaseFirstDataBus._spot_cache_lock:
                DatabaseFirstDataBus._spot_cache_failed = True
                DatabaseFirstDataBus._spot_cache_fail_time = datetime.now()

        # 3. 保存到数据库
        if stocks:
            self._save_snapshot("all_stocks", stocks)
            return stocks

        # 4. API失败但数据库有旧数据，返回旧数据
        if snap and snap.get("data") and isinstance(snap["data"], list):
            logger.info("全市场快照使用数据库旧数据: %d只", len(snap["data"]))
            return snap["data"]

        return []

    def get_stock_universe(self, force_refresh: bool = False) -> list[dict]:
        """
        获取 A 股全市场股票列表（沪深主板 + 科创 + 创业板）。

        优先从数据库读取，无数据或过期时依次尝试：
        EastMoney clist、Tushare stock_basic、TickFlow universes、AKShare stock_info_a_code_name。
        返回列表，每项包含 stock_code, stock_name, exchange。
        """
        snap = self._query_snapshot("stock_universe")
        if (
            not force_refresh
            and snap
            and snap.get("data")
            and isinstance(snap["data"], list)
            and not self._is_stale(snap.get("updated_at"), "stock_info")
        ):
            logger.info("全市场股票列表从数据库获取: %d只", len(snap["data"]))
            return snap["data"]

        stocks: list[dict] | None = None
        # 1. EastMoney（无需API Key，稳定性好）
        try:
            from providers.sources.eastmoney_src import EastMoneyAdapter

            adapter = EastMoneyAdapter()
            stocks = adapter.fetch_universe()
            if stocks:
                logger.info("全市场股票列表从 EastMoney 获取: %d只", len(stocks))
        except Exception as e:
            logger.debug("EastMoney 全市场列表失败: %s", e)

        # 2. Tushare
        if not stocks:
            try:
                from providers.sources.tushare_src import TushareAdapter

                adapter = TushareAdapter()
                stocks = adapter.fetch_universe()
                if stocks:
                    logger.info("全市场股票列表从 Tushare 获取: %d只", len(stocks))
            except Exception as e:
                logger.debug("Tushare 全市场列表失败: %s", e)

        # 3. TickFlow
        if not stocks:
            try:
                from providers.sources.tickflow_src import TickFlowAdapter

                adapter = TickFlowAdapter()
                stocks = adapter.fetch_universe()
                if stocks:
                    logger.info("全市场股票列表从 TickFlow 获取: %d只", len(stocks))
            except Exception as e:
                logger.debug("TickFlow 全市场列表失败: %s", e)

        # 4. AKShare
        if not stocks:
            try:
                import akshare as ak

                df = ak.stock_info_a_code_name()
                if df is not None and not df.empty:
                    stocks = [
                        {
                            "stock_code": str(row.get("code", "")).strip(),
                            "stock_name": str(row.get("name", "")).strip(),
                            "exchange": "",
                        }
                        for _, row in df.iterrows()
                        if str(row.get("code", "")).strip().isdigit()
                    ]
                    if stocks:
                        logger.info("全市场股票列表从 AKShare 获取: %d只", len(stocks))
            except Exception as e:
                logger.debug("AKShare 全市场列表失败: %s", e)

        if stocks:
            self._save_snapshot("stock_universe", stocks)
            return stocks

        # 返回旧数据兜底
        if snap and snap.get("data") and isinstance(snap["data"], list):
            logger.warning("全市场列表获取失败，使用数据库旧数据: %d只", len(snap["data"]))
            return snap["data"]

        return []

    # ══════════════════════════════════════════
    # 工具方法
    # ══════════════════════════════════════════

    def _is_stale(self, updated_at: str | None, data_type: str) -> bool:
        """检查数据是否过期。"""
        if not updated_at:
            return True
        threshold = _STALE_THRESHOLD.get(data_type, 3600)
        try:
            # 尝试解析ISO格式
            if "T" in str(updated_at) or ("-" in str(updated_at) and ":" in str(updated_at)):
                dt = datetime.fromisoformat(str(updated_at))
            else:
                dt = datetime.strptime(str(updated_at)[:19], "%Y-%m-%d %H:%M:%S")
            age = (datetime.now() - dt).total_seconds()
            return age > threshold
        except Exception:
            return True

    def _get_adapters(self) -> list:
        """向后兼容别名。"""
        return self._load_adapters()

    def _load_adapters(self) -> list:
        """动态加载所有可用的数据源适配器，并按优先级排序（数字越小越优先）。

        适配器按线程缓存，避免每次请求都重建 HTTP 客户端。
        """
        adapters = getattr(self._adapter_local, "adapters", None)
        if adapters is not None:
            return adapters

        adapters: list = []
        candidates = [
            "providers.sources.tencent.TencentAdapter",
            "providers.sources.sina.SinaAdapter",
            "providers.sources.eastmoney_src.EastMoneyAdapter",
            "providers.sources.tickflow_src.TickFlowAdapter",
            "providers.sources.tushare_src.TushareAdapter",
            "providers.sources.akshare_src.AKShareAdapter",
            "providers.sources.yfinance_src.YFinanceAdapter",
        ]
        for path in candidates:
            try:
                module_name, class_name = path.rsplit(".", 1)
                module = __import__(module_name, fromlist=[class_name])
                adapter_cls = getattr(module, class_name)
                adapters.append(adapter_cls())
            except Exception:
                pass
        # 按 priority 升序排列，priority 数字越小优先级越高
        adapters.sort(key=lambda a: getattr(a, "priority", 99))
        self._adapter_local.adapters = adapters
        return adapters

    def _get_spot_data(self, code: str) -> dict | None:
        """
        获取个股实时快照（带缓存的 stock_zh_a_spot_em）。
        避免对同一批股票重复调用全量API。
        """
        from providers.normalizer import StockCodeNormalizer

        pure = StockCodeNormalizer.to_db(code)

        # 检查缓存是否有效（线程安全读取）
        now = datetime.now()
        with DatabaseFirstDataBus._spot_cache_lock:
            if (
                DatabaseFirstDataBus._spot_cache is not None
                and DatabaseFirstDataBus._spot_cache_time is not None
                and (now - DatabaseFirstDataBus._spot_cache_time).total_seconds()
                < DatabaseFirstDataBus._spot_cache_ttl
            ):
                return DatabaseFirstDataBus._spot_cache.get(pure)

            # 检查是否刚刚失败过（60秒内不重试）
            if (
                DatabaseFirstDataBus._spot_cache_failed
                and DatabaseFirstDataBus._spot_cache_fail_time
                and (now - DatabaseFirstDataBus._spot_cache_fail_time).total_seconds() < 60
            ):
                return None

        # 缓存过期或不存在，重新获取（锁外执行API调用，避免阻塞其他线程）
        try:
            import akshare as ak

            spot = ak.stock_zh_a_spot_em()
            if spot is not None and not spot.empty:
                # 转为字典缓存
                cache: dict = {}
                for _, r in spot.iterrows():
                    code_str = str(r.get("代码", ""))
                    cache[code_str] = {
                        "stock_name": str(r.get("名称", "")),
                        "latest_price": _safe_float(r.get("最新价")),
                        "change_pct": _safe_float(r.get("涨跌幅")),
                        "volume": _safe_float(r.get("成交量")),
                        "amount": _safe_float(r.get("成交额")),
                        "pe_ratio": _safe_float(r.get("市盈率-动态")),
                        "pb_ratio": _safe_float(r.get("市净率")),
                        "turnover_rate": _safe_float(r.get("换手率")),
                    }
                with DatabaseFirstDataBus._spot_cache_lock:
                    DatabaseFirstDataBus._spot_cache = cache
                    DatabaseFirstDataBus._spot_cache_time = now
                    DatabaseFirstDataBus._spot_cache_failed = False
                logger.info("全量快照缓存已更新: %d只股票", len(cache))
                return cache.get(pure)
            with DatabaseFirstDataBus._spot_cache_lock:
                DatabaseFirstDataBus._spot_cache_failed = True
                DatabaseFirstDataBus._spot_cache_fail_time = now
        except ImportError:
            logger.warning("akshare未安装")
        except Exception as e:
            logger.warning("获取全量快照失败: %s", e)
            with DatabaseFirstDataBus._spot_cache_lock:
                DatabaseFirstDataBus._spot_cache_failed = True
                DatabaseFirstDataBus._spot_cache_fail_time = now

        return None
