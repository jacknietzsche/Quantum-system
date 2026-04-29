"""
core.data — 统一数据层
=======================
整合自: backtest_system/data_loader.py (数据加载) + real_data_fetcher.py (数据获取)

提供统一的数据获取接口，支持:
  1. 五层数据源 fallback（baostock → akshare → efinance → 新浪HTTP → 腾讯HTTP）
  2. 共享缓存机制（pickle, 24h TTL）
  3. 增量更新（仅拉取新数据）
  4. 批量获取（多线程并行）
  5. Backtrader PandasData 格式转换
  6. 股票名称映射
  7. 停牌/复权/标准化处理

对外类:
  UnifiedDataFetcher — 统一数据获取器（选股 + 持仓管理 + 回测共用）

设计原则:
  - 所有数据请求均经过统一缓存
  - 新模块必须从此接口获取数据，禁止直接调用 baostock/akshare
  - 向后兼容：旧 RealDataFetcher 保留为重导出别名
"""

import os
import sys
import time
import pickle
import hashlib
import logging
import threading
import json
import random
import warnings
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from pathlib import Path

import pandas as pd
import numpy as np

from core.config import DataSourceConfig, QuantConfig
from core.cache_manager import get_cache_manager
from core.record_manager import record_error, record_result

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)


# ============================================================
# 代码格式转换工具
# ============================================================

def normalize_code(code: str) -> str:
    """将各种格式的股票代码统一为6位数字字符串"""
    code = str(code).strip()
    for prefix in ("sh.", "sz.", "SH.", "SZ."):
        if code.startswith(prefix):
            code = code[3:]
            break
    for suffix in (".SH", ".SZ", ".SS", ".BJ"):
        if code.endswith(suffix):
            code = code[:-3]
            break
    return code.zfill(6)


def code_to_baostock(code: str) -> str:
    """将6位代码转为 baostock 格式"""
    c = normalize_code(code)
    if c.startswith("6"):
        return f"sh.{c}"
    else:
        return f"sz.{c}"


def code_to_market(code: str) -> str:
    """6位代码 → 'SH' / 'SZ'"""
    c = normalize_code(code)
    return "SH" if c.startswith("6") else "SZ"


# ============================================================
# UnifiedDataFetcher — 统一数据获取器
# ============================================================

class UnifiedDataFetcher:
    """
    统一数据获取器 — 所有模块的数据入口

    整合了:
      - RealDataFetcher 的五层 fallback 机制
      - DataLoader 的 Backtrader 格式转换
      - 统一缓存管理

    用法:
        from core.data import UnifiedDataFetcher
        fetcher = UnifiedDataFetcher()

        # 获取单只股票日频数据
        df = fetcher.get_daily("000001", days=120)

        # 批量获取
        data = fetcher.get_batch_daily(["000001", "600000", "300001"])

        # 转换为 Backtrader 格式
        bt_feed = fetcher.to_backtrader(df)

        # 获取股票名称
        names = fetcher.get_name_map()
    """

    _SZ_PREFIXES = ('0', '3')
    _SH_PREFIXES = ('6',)

    def __init__(self, config: Optional[DataSourceConfig] = None):
        self.cfg = config or DataSourceConfig()

        # 确保缓存目录存在
        Path(self.cfg.cache_dir).mkdir(parents=True, exist_ok=True)
        Path(self.cfg.backtest_cache_dir).mkdir(parents=True, exist_ok=True)

        # 本地数据库获取器
        self._local_db = None
        self._local_db_enabled = False
        if self.cfg.use_local_db:
            try:
                from .local_db_fetcher import LocalDBFetcher
                self._local_db = LocalDBFetcher(self.cfg.local_db_path)
                # 测试连接
                stats = self._local_db.get_stats()
                self._local_db_enabled = True
                logger.info(f"本地数据库已启用: {self.cfg.local_db_path}")
                logger.info(f"  股票数: {stats['stock_count']}, 行情记录: {stats['price_count']:,}")
            except Exception as e:
                error_msg = f"本地数据库初始化失败: {e}，将使用网络获取"
                logger.warning(error_msg)
                record_error("database", error_msg, {"error": str(e)})
                self._local_db_enabled = False

        # 缓存管理器
        self._cache_manager = get_cache_manager(self.cfg)

        # 会话管理
        self._bs_session = None
        self._session_created_at = 0
        self._session_lock = threading.Lock()

        # 名称缓存
        self._name_map: Dict[str, str] = {}
        self._name_map_loaded_at = 0

        # 自适应降速
        self._consecutive_failures = 0
        self._adaptive_delay = self.cfg.request_delay
        self._max_adaptive_delay = 5.0
        self._failure_threshold = 10

        # 检测数据源依赖
        self._check_deps()

        logger.info(f"UnifiedDataFetcher 初始化完成 (本地DB={self._local_db_enabled}, 缓存={self.cfg.cache_dir})")

    # ── 依赖检查 ─────────────────────────────────────────────
    def _check_deps(self):
        try:
            import baostock
            logger.info(f"  baostock {baostock.__version__}")
        except ImportError:
            raise RuntimeError("baostock 未安装: pip install baostock")

        try:
            import akshare
            self._akshare_ok = True
        except ImportError:
            self._akshare_ok = False

        try:
            import efinance
            self._efinance_ok = True
        except ImportError:
            self._efinance_ok = False

    # ── 会话管理 ─────────────────────────────────────────────
    def _ensure_session(self):
        with self._session_lock:
            if self._bs_session is None or (time.time() - self._session_created_at) > self.cfg.baostock_session_timeout:
                import baostock as bs
                if self._bs_session is not None:
                    try: self._bs_session.logout()
                    except Exception: pass  # baostock会话关闭失败可忽略
                lg = bs.login()
                if lg.error_code != '0':
                    raise RuntimeError(f"baostock 登录失败: {lg.error_msg}")
                self._bs_session = bs
                self._session_created_at = time.time()
            return self._bs_session

    def _rebuild_session(self, reason=""):
        with self._session_lock:
            import baostock as bs
            try:
                if self._bs_session is not None:
                    self._bs_session.logout()
            except Exception: pass  # baostock会话关闭失败可忽略
            self._bs_session = None
            self._session_created_at = 0
            time.sleep(0.5)
            lg = bs.login()
            if lg.error_code != '0':
                self._bs_session = None
                return False
            self._bs_session = bs
            self._session_created_at = time.time()
            return True

    def _close_session(self):
        bs = getattr(self, '_bs_session', None)
        if bs is not None:
            try: bs.logout()
            except Exception: pass  # baostock会话关闭失败可忽略
        self._bs_session = None

    def __del__(self):
        try:
            self._close_session()
        except Exception:
            pass  # 防止析构时属性不存在报错

    # ── 自适应降速 ──────────────────────────────────────────
    def _record_success(self):
        if self._consecutive_failures > 0:
            self._consecutive_failures = max(0, self._consecutive_failures - 3)
        if self._adaptive_delay > self.cfg.request_delay:
            self._adaptive_delay = max(self.cfg.request_delay, self._adaptive_delay * 0.5)

    def _record_failure(self):
        self._consecutive_failures += 1
        if self._consecutive_failures > self._failure_threshold:
            factor = min(2.0, 1.0 + (self._consecutive_failures - self._failure_threshold) * 0.3)
            self._adaptive_delay = min(self._max_adaptive_delay, self._adaptive_delay * factor)

    def _get_delay(self):
        jitter = random.uniform(0, self._adaptive_delay * 0.3)
        return self._adaptive_delay + jitter

    def _is_session_broken(self, error) -> bool:
        err_str = str(error).lower()
        signals = ['error -3', 'decompressing', 'invalid distance',
                    'remote disconnected', 'remotedisconnected', 'connection reset',
                    'connection aborted', 'broken pipe', 'eof occurred',
                    'protocolerror', 'remote end closed', 'end closed']
        for sig in signals:
            if sig in err_str:
                return True
        for phrase in ['RemoteDisconnected', 'ProtocolError', 'Remote end closed']:
            if phrase in str(error):
                return True
        return False

    # ── 缓存 ─────────────────────────────────────────────────
    def _load_cache(self, key: str) -> Optional[object]:
        return self._cache_manager.get("data", key)

    def _save_cache(self, key: str, data: object):
        self._cache_manager.set("data", data, key)

    # ── 股票名称 ─────────────────────────────────────────────
    def get_name_map(self) -> Dict[str, str]:
        """返回 {code6: name} 映射"""
        now = time.time()
        if self._name_map and (now - self._name_map_loaded_at) < self.cfg.name_map_ttl:
            return self._name_map

        cache_key = "name_map_v1"
        cached = self._load_cache(cache_key)
        if cached:
            self._name_map = cached
            self._name_map_loaded_at = now
            return self._name_map

        name_map: Dict[str, str] = {}

        # akshare
        if self._akshare_ok:
            try:
                os.environ['DISABLE_TQDM'] = 'true'
                import akshare as ak
                result_holder = [None]
                def _fetch():
                    try: result_holder[0] = (ak.stock_info_a_code_name(), None)
                    except Exception as ex: result_holder[0] = (None, ex)
                t = threading.Thread(target=_fetch, daemon=True)
                t.start()
                t.join(timeout=45)
                if t.is_alive():
                    result_holder[0] = (None, TimeoutError())
                if result_holder[0]:
                    df, err = result_holder[0]
                    if err is None and df is not None and not df.empty:
                        for _, row in df.iterrows():
                            code = str(row.iloc[0]).zfill(6)
                            name = str(row.iloc[1]).strip()
                            if name and name != 'nan':
                                name_map[code] = name
            except Exception as e:
                logger.debug("akshare 名称获取失败: %s", e)

        # baostock fallback
        if not name_map:
            try:
                bs = self._ensure_session()
                today = datetime.now().strftime('%Y-%m-%d')
                rs = bs.query_all_stock(today)
                df_raw = rs.get_data()
                if not df_raw.empty and 'code_name' in df_raw.columns:
                    for _, row in df_raw.iterrows():
                        code = row['code'].split('.')[-1] if '.' in row['code'] else row['code']
                        code = code.zfill(6)
                        if len(code) == 6 and code.isdigit():
                            name = str(row['code_name']).strip()
                            if name and name != 'nan':
                                name_map[code] = name
            except Exception as e:
                logger.debug("baostock 名称获取失败: %s", e)

        if name_map:
            self._name_map = name_map
            self._name_map_loaded_at = now
            self._save_cache(cache_key, name_map)
        else:
            self._name_map = {}
            self._name_map_loaded_at = now

        return self._name_map

    # ── 股票列表 ─────────────────────────────────────────────
    def get_stock_list(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """返回个股列表 DataFrame: [symbol, bs_code, name, market]"""
        # 优先使用本地数据库
        if self._local_db_enabled and self._local_db:
            try:
                df = self._local_db.get_stock_list()
                if not df.empty:
                    logger.info(f"从本地数据库获取股票列表: {len(df)} 只")
                    return df
            except Exception as e:
                logger.warning("本地数据库获取股票列表失败: %s", e)
        
        if trade_date is None:
            trade_date = self._last_valid_trade_date()

        cache_key = f"stock_list_{trade_date}"
        cached = self._load_cache(cache_key)
        if cached is not None:
            return cached

        bs = self._ensure_session()
        rs = bs.query_all_stock(trade_date)
        df_raw = rs.get_data()

        if df_raw.empty or 'code' not in df_raw.columns:
            trade_date = self._last_valid_trade_date()
            cache_key = f"stock_list_{trade_date}"
            cached = self._load_cache(cache_key)
            if cached is not None:
                return cached
            bs = self._ensure_session()
            rs = bs.query_all_stock(trade_date)
            df_raw = rs.get_data()

        import re
        mask = df_raw['code'].str.match(r'^(sh\.6|sz\.0|sz\.3)\d{5}$')
        df_stocks = df_raw[mask].copy().reset_index(drop=True)
        df_stocks['bs_code'] = df_stocks['code']
        df_stocks['symbol'] = df_stocks['code'].str.split('.').str[-1]
        df_stocks['market'] = df_stocks['code'].str.split('.').str[0].str.upper()

        name_map = self.get_name_map()
        if 'code_name' in df_stocks.columns:
            df_stocks['name'] = df_stocks.apply(
                lambda r: name_map.get(r['symbol'], r['code_name']), axis=1
            )

        df_result = df_stocks[['symbol', 'bs_code', 'name', 'market']].copy()
        self._save_cache(cache_key, df_result)
        return df_result

    def _last_valid_trade_date(self) -> str:
        now = time.time()
        if (hasattr(self, '_trade_date_cache_time') and
                (now - self._trade_date_cache_time) < 3600 and
                hasattr(self, '_trade_date_cache')):
            return self._trade_date_cache
        try:
            bs = self._ensure_session()
            for delta in range(0, 10):
                d = (datetime.now() - timedelta(days=delta)).strftime('%Y-%m-%d')
                rs = bs.query_all_stock(d)
                if not rs.get_data().empty:
                    self._trade_date_cache = d
                    self._trade_date_cache_time = now
                    return d
            raise RuntimeError("最近10天无交易数据")
        except Exception:
            self._close_session()
            raise

    # ── 单只股票日频数据 ────────────────────────────────────
    def get_daily(self, symbol: str, days: int = 120) -> pd.DataFrame:
        """
        获取单只股票日频数据（仅从本地数据库获取）
        symbol: 6位代码（'000001'）或 baostock 格式（'sz.000001'）
        返回: DataFrame, index=date, 列: open/high/low/close/volume/amount/pct_change/turn/market_cap
        """
        if '.' not in symbol:
            symbol = symbol
        else:
            symbol = symbol.split('.')[-1]

        # 仅从本地数据库获取
        if self._local_db_enabled and self._local_db:
            try:
                df = self._local_db.get_daily(symbol, days=days)
                if not df.empty and len(df) >= self.cfg.min_data_rows:
                    # 补充 market_cap 列
                    if 'market_cap' not in df.columns:
                        df['market_cap'] = df['close'] * df['volume'] * 100
                    # 添加 turn 列别名
                    if 'turnover' in df.columns and 'turn' not in df.columns:
                        df['turn'] = df['turnover']
                    logger.debug("%s 从本地数据库获取 {len(df)} 条", symbol)
                    return df
                else:
                    logger.warning("本地数据库 %s 数据不足，需要先更新数据", symbol)
                    return pd.DataFrame()
            except Exception as e:
                error_msg = f"本地数据库获取 {symbol} 失败: {e}"
                logger.error(error_msg)
                record_error("database", error_msg, {"symbol": symbol, "error": str(e)})
                return pd.DataFrame()
        else:
            logger.error("本地数据库未启用，请先启用本地数据库")
            return pd.DataFrame()

    # ── 批量获取 ─────────────────────────────────────────────
    def get_batch_daily(
        self,
        symbols: List[str],
        days: int = 120,
        min_rows: int = 60,
        max_workers: int = 3,
    ) -> Dict[str, pd.DataFrame]:
        """
        批量获取日频数据（仅从本地数据库获取）

        返回: {symbol6: DataFrame}
        """
        result: Dict[str, pd.DataFrame] = {}
        total = len(symbols)
        success = 0

        # 仅从本地数据库批量获取
        if self._local_db_enabled and self._local_db:
            logger.info(f"从本地数据库批量获取 {len(symbols)} 只股票...")
            try:
                local_result = self._local_db.get_batch_daily(symbols, days=days)
                for code, df in local_result.items():
                    if not df.empty and len(df) >= min_rows:
                        # 补充缺失列
                        if 'market_cap' not in df.columns:
                            df['market_cap'] = df['close'] * df['volume'] * 100
                        if 'turnover' in df.columns and 'turn' not in df.columns:
                            df['turn'] = df['turnover']
                        result[code] = df
                        success += 1
                logger.info("本地数据库获取成功: %s/{len(symbols)} 只", success)
                
                # 检查数据不足的股票
                for symbol in symbols:
                    if symbol not in result:
                        logger.warning("本地数据库 %s 数据不足，需要先更新数据", symbol)
            except Exception as e:
                error_msg = f"本地数据库批量获取失败: {e}"
                logger.error(error_msg)
                record_error("database", error_msg, {"error": str(e)})
        else:
            logger.error("本地数据库未启用，请先启用本地数据库")

        logger.info("批量获取完成: %s/%s 只", success, total)
        return result

    # ── 五层 fallback 获取 ──────────────────────────────────
    def _fetch_daily_in_session(self, bs_code, days, start_str, end_str, bs_query_lock=None):
        """六源 fallback: 本地数据库 → baostock → akshare → efinance → 新浪HTTP → 腾讯HTTP"""
        import baostock as bs
        symbol = bs_code.split('.')[-1]
        session_rebuilt = False
        
        # 0. 本地数据库（最高优先级）
        if self.cfg.use_local_db:
            try:
                df = self._fetch_local_db(symbol, days, start_str, end_str)
                if not df.empty:
                    logger.debug("本地数据库获取成功: %s ({len(df)}条)", symbol)
                    return df
                else:
                    logger.debug("本地数据库无数据: %s", symbol)
            except Exception as e:
                logger.warning("本地数据库获取失败 %s: {str(e)[:80]}", symbol)

        # 1. baostock
        for attempt in range(self.cfg.baostock_max_retries):
            try:
                if bs_query_lock is not None:
                    bs_query_lock.acquire()
                try:
                    rs = bs.query_history_k_data_plus(
                        code=bs_code,
                        fields="date,open,high,low,close,volume,amount,pctChg,turn",
                        start_date=start_str, end_date=end_str,
                        frequency="d", adjustflag="2"
                    )
                    rows = []
                    while rs.next():
                        rows.append(rs.get_row_data())
                finally:
                    if bs_query_lock is not None:
                        bs_query_lock.release()
                if rows:
                    df = self._rows_to_df(rows, rs.fields, days)
                    self._record_success()
                    return df
                else:
                    break
            except Exception as e:
                if self._is_session_broken(e) and not session_rebuilt:
                    if self._rebuild_session(reason=f"{symbol}: {str(e)[:80]}"):
                        session_rebuilt = True
                        continue
                    break
                if attempt < self.cfg.baostock_max_retries - 1:
                    time.sleep(self.cfg.request_delay * (2 ** attempt))

        # 2. akshare
        time.sleep(self._get_delay())
        df = self._fetch_akshare(bs_code, days, start_str, end_str)
        if not df.empty:
            return df

        # 3. efinance
        time.sleep(self._get_delay())
        df = self._fetch_efinance(bs_code, days, start_str, end_str)
        if not df.empty:
            return df

        # 4. 新浪HTTP
        time.sleep(self._get_delay())
        df = self._fetch_sina_http(bs_code, days)
        if not df.empty:
            return df

        # 5. 腾讯HTTP（根据配置可选）
        if self.cfg.use_tencent_data:
            time.sleep(self._get_delay())
            df = self._fetch_tencent_http(bs_code, days)
            if not df.empty:
                return df
        else:
            logger.debug("跳过腾讯数据源获取 %s（配置 use_tencent_data=False）", bs_code)

        self._record_failure()
        return pd.DataFrame()

    def _fetch_incremental(self, bs_code, days, start_str, end_str, cached_df, bs_query_lock=None):
        """增量更新"""
        import baostock as bs
        if cached_df.empty or 'close' not in cached_df.columns:
            return pd.DataFrame()

        last_date = pd.to_datetime(cached_df.index[-1])
        new_start = (last_date + timedelta(days=1)).strftime('%Y-%m-%d')
        today_str = datetime.now().strftime('%Y-%m-%d')
        if last_date.strftime('%Y-%m-%d') >= today_str:
            return cached_df

        try:
            if bs_query_lock is not None:
                bs_query_lock.acquire()
            try:
                rs = bs.query_history_k_data_plus(
                    code=bs_code,
                    fields="date,open,high,low,close,volume,amount,pctChg,turn",
                    start_date=new_start, end_date=end_str,
                    frequency="d", adjustflag="2"
                )
                rows = []
                while rs.next():
                    rows.append(rs.get_row_data())
            finally:
                if bs_query_lock is not None:
                    bs_query_lock.release()

            if not rows:
                return cached_df

            df_new = self._rows_to_df(rows, rs.fields, days)
            df_merged = pd.concat([cached_df, df_new])
            df_merged = df_merged[~df_merged.index.duplicated(keep='last')].sort_index()
            df_merged = df_merged.tail(days)
            return df_merged
        except Exception as e:
            if self._is_session_broken(e):
                self._rebuild_session(reason=f"增量: {str(e)[:80]}")
            return pd.DataFrame()

    def _rows_to_df(self, rows, fields, days) -> pd.DataFrame:
        """将 baostock 行数据转为标准 DataFrame"""
        df = pd.DataFrame(rows, columns=fields)
        df['date'] = pd.to_datetime(df['date'])
        for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'pctChg', 'turn']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.rename(columns={'pctChg': 'pct_change'})
        df = df.dropna(subset=['close']).sort_values('date')
        df = df.tail(days).reset_index(drop=True)
        df['market_cap'] = df['close'] * df['volume'] * 100
        df = df.set_index('date')
        return df

    # ── 备用数据源 ──────────────────────────────────────────
    def _fetch_akshare(self, bs_code, days, start_str, end_str):
        if not self._akshare_ok:
            return pd.DataFrame()
        ak_start = start_str.replace('-', '')
        ak_end = end_str.replace('-', '')
        symbol = bs_code.split('.')[-1]
        for retry in range(2):
            try:
                os.environ['DISABLE_TQDM'] = 'true'
                import akshare as ak
                df = ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                        start_date=ak_start, end_date=ak_end,
                                        adjust="qfq", timeout=15.0)
                if df is None or df.empty:
                    return pd.DataFrame()
                field_map = {'日期':'date','开盘':'open','收盘':'close','最高':'high',
                             '最低':'low','成交量':'volume','成交额':'amount','涨跌幅':'pct_change'}
                df = df.rename(columns=field_map)
                required = ['date','open','high','low','close','volume','amount','pct_change']
                for c in required:
                    if c not in df.columns:
                        return pd.DataFrame()
                df = df[required].copy()
                df['date'] = pd.to_datetime(df['date'])
                for c in required[1:]:
                    df[c] = pd.to_numeric(df[c], errors='coerce')
                if df['pct_change'].isna().all() and len(df) > 1:
                    df['pct_change'] = df['close'].pct_change() * 100
                df = df.dropna(subset=['close']).sort_values('date').tail(days).reset_index(drop=True)
                df['market_cap'] = df['close'] * df['volume'] * 100
                df = df.set_index('date')
                self._record_success()
                return df
            except (ConnectionError, OSError) as e:
                if retry < 1:
                    time.sleep(3.0)
                    continue
            except Exception:
                if retry < 1:
                    time.sleep(1.5)
                    continue
        return pd.DataFrame()

    def _fetch_efinance(self, bs_code, days, start_str, end_str):
        if not self._efinance_ok:
            return pd.DataFrame()
        symbol = bs_code.split('.')[-1]
        for retry in range(2):
            try:
                os.environ['DISABLE_TQDM'] = 'true'
                import efinance as ef
                df = ef.stock.get_quote_history(symbol)
                if df.empty:
                    return pd.DataFrame()
                col_map = {'日期':'date','开盘':'open','收盘':'close','最高':'high',
                           '最低':'low','成交量':'volume','成交额':'amount','涨跌幅':'pct_change'}
                actual = df.columns.tolist()
                mapped = {}
                for cn, en in col_map.items():
                    for ac in actual:
                        if cn in ac or ac in cn:
                            mapped[ac] = en
                            break
                df = df.rename(columns=mapped)
                required = ['date','open','high','low','close','volume','amount','pct_change']
                missing = [c for c in required if c not in df.columns]
                if missing:
                    return pd.DataFrame()
                df = df[required].copy()
                df['date'] = pd.to_datetime(df['date'])
                for c in required[1:]:
                    df[c] = pd.to_numeric(df[c], errors='coerce')
                if df['pct_change'].isna().all() and len(df) > 1:
                    df['pct_change'] = df['close'].pct_change() * 100
                df = df.dropna(subset=['close']).sort_values('date').tail(days).reset_index(drop=True)
                df['market_cap'] = df['close'] * df['volume'] * 100
                df = df.set_index('date')
                return df
            except Exception:
                if retry < 1:
                    time.sleep(1.0)
                    continue
        return pd.DataFrame()

    def _fetch_sina_http(self, bs_code, days):
        symbol = bs_code.split('.')[-1]
        market = 'sh' if symbol.startswith('6') else 'sz'
        sina_code = f"{market}{symbol}"
        fetch_count = min(days + 30, 800)
        last_error = None

        for retry in range(3):
            try:
                url = (f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php"
                       f"/CN_MarketData.getKLineData?symbol={sina_code}"
                       f"&scale=240&ma=no&datalen={fetch_count}")
                req = Request(url, headers={
                    'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/',
                    'Connection': 'close',
                })
                # 缩短超时时间
                resp = urlopen(req, timeout=10)
                raw = resp.read().decode('utf-8', errors='ignore').strip()
                if not raw or raw in ('null', '[]'):
                    return pd.DataFrame()
                data = json.loads(raw)
                if not isinstance(data, list) or not data:
                    return pd.DataFrame()
                rows = []
                for item in data:
                    try:
                        rows.append({'date': item.get('day',''), 'open': float(item.get('open',0)),
                                     'close': float(item.get('close',0)), 'high': float(item.get('high',0)),
                                     'low': float(item.get('low',0)), 'volume': float(item.get('volume',0)),
                                     'amount': 0.0, 'pct_change': 0.0})
                    except (ValueError, TypeError):
                        continue
                if not rows:
                    return pd.DataFrame()
                df = pd.DataFrame(rows)
                df = df[df['date'] != '']
                df['date'] = pd.to_datetime(df['date'])
                df = df.dropna(subset=['close']).sort_values('date')
                if len(df) > 1:
                    df['pct_change'] = df['close'].pct_change() * 100
                    df['pct_change'] = df['pct_change'].fillna(0)
                df['market_cap'] = df['close'] * df['volume'] * 100
                df = df.tail(days).reset_index(drop=True).set_index('date')
                self._record_success()
                return df
            except Exception as e:
                last_error = e
                # 检测连接错误，快速失败
                err_str = str(e).lower()
                is_connection_error = any(x in err_str for x in [
                    'remote', 'disconnected', 'reset', 'aborted', 'broken', 'eof',
                    'timeout', 'connection'
                ])
                if is_connection_error:
                    if retry < 2:
                        time.sleep(0.3)
                        continue
                else:
                    if retry < 2:
                        time.sleep(0.5 * (retry + 1))
                        continue
        if last_error:
            logger.debug("新浪HTTP失败 %s: %s", symbol, last_error)
        return pd.DataFrame()

    def _fetch_local_db(self, symbol, days, start_str, end_str):
        """本地SQLite数据库获取"""
        try:
            # 延迟导入，避免循环依赖
            from core.local_db_fetcher import LocalDBFetcher
            local_fetcher = LocalDBFetcher()
            df = local_fetcher.get_daily(symbol, days)
            
            if not df.empty:
                # 转换为统一格式
                if 'amount' not in df.columns:
                    df['amount'] = df['close'] * df['volume'] * 10
                if 'pct_change' not in df.columns:
                    df['pct_change'] = df['close'].pct_change() * 100
                    df['pct_change'] = df['pct_change'].fillna(0)
                df['market_cap'] = df['close'] * df['volume'] * 100
                
                # 确保索引是日期
                if not isinstance(df.index, pd.DatetimeIndex):
                    if 'date' in df.columns:
                        df['date'] = pd.to_datetime(df['date'])
                        df = df.set_index('date')
                
                return df
        except ImportError:
            logger.warning("本地数据库模块未安装，跳过本地数据库获取")
        except Exception as e:
            logger.warning("本地数据库获取失败 %s: {str(e)[:80]}", symbol)
        
        return pd.DataFrame()

    def _fetch_tencent_http(self, bs_code, days):
        symbol = bs_code.split('.')[-1]
        
        # 检测是否为指数基金（腾讯API格式: 0.9xxxxx）
        # 在baostock中，指数基金可能是 sz.9xxxxx 格式
        # 但更常见的是 0.9xxxxx 格式（腾讯API看到的是这个）
        # 我们在这里过滤真正的指数基金，避免API限制
        market_prefix = bs_code.split('.')[0]
        
        # 如果是以9开头的6位代码，并且是深圳市场的，可能是指数基金
        # 腾讯API对指数基金（如0.920005）有严格限制，经常断开连接
        if market_prefix == 'sz' and symbol.startswith('9') and len(symbol) == 6 and symbol[1:].isdigit():
            # 进一步检查是否是真正的指数基金（通过代码特征）
            # 通常指数基金的代码在920000-939999范围内
            try:
                code_num = int(symbol)
                if 920000 <= code_num <= 939999:
                    logger.debug("跳过指数基金 %s（腾讯API限制，代码范围920000-939999）", bs_code)
                    return pd.DataFrame()
            except ValueError:
                pass
        
        # 附加检查：如果配置中禁用了腾讯数据源，直接返回空
        if not self.cfg.use_tencent_data:
            logger.debug("跳过腾讯数据源获取 %s（配置 use_tencent_data=False）", bs_code)
            return pd.DataFrame()
        
        market = 'sh' if symbol.startswith('6') else 'sz'
        qcode = f"{market}{symbol}"
        fetch_count = min(days + 30, 800)
        last_error = None

        for retry in range(3):
            try:
                url = (f"https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
                       f"?param={qcode},day,,,{fetch_count},qfq")
                req = Request(url, headers={
                    'User-Agent': 'Mozilla/5.0', 'Referer': 'https://gu.qq.com/',
                    'Connection': 'close',
                })
                # 缩短超时时间，避免长时间卡住
                resp = urlopen(req, timeout=10)
                raw = resp.read().decode('utf-8', errors='ignore').strip()
                if not raw:
                    return pd.DataFrame()
                data = json.loads(raw)
                if data.get('code') != 0:
                    return pd.DataFrame()
                stock_data = data.get('data', {}).get(qcode, {})
                day_data = stock_data.get('qfqday') or stock_data.get('day', [])
                if not day_data or not isinstance(day_data, list) or len(day_data) < 2:
                    return pd.DataFrame()
                rows = []
                for item in day_data:
                    if not isinstance(item, list) or len(item) < 6:
                        continue
                    try:
                        rows.append({
                            'date': str(item[0]), 'open': float(item[1]), 'close': float(item[2]),
                            'high': float(item[3]), 'low': float(item[4]), 'volume': float(item[5]),
                            'pct_change': float(item[7]) if len(item) > 7 and item[7] != '' else 0.0,
                            'amount': float(item[8]) * 10000 if len(item) > 8 and item[8] != '' else 0.0,
                        })
                    except (ValueError, TypeError, IndexError):
                        continue
                if not rows:
                    return pd.DataFrame()
                df = pd.DataFrame(rows)
                df['date'] = pd.to_datetime(df['date'])
                df = df.dropna(subset=['close']).sort_values('date')
                if df['amount'].sum() == 0:
                    df['amount'] = df['close'] * df['volume'] * 10
                if df['pct_change'].abs().sum() < 0.01 and len(df) > 1:
                    df['pct_change'] = df['close'].pct_change() * 100
                    df['pct_change'] = df['pct_change'].fillna(0)
                df['market_cap'] = df['close'] * df['volume'] * 100
                df = df.tail(days).reset_index(drop=True).set_index('date')
                self._record_success()
                return df
            except Exception as e:
                last_error = e
                # 检测连接错误，快速失败
                err_str = str(e).lower()
                is_connection_error = any(x in err_str for x in [
                    'remote', 'disconnected', 'reset', 'aborted', 'broken', 'eof',
                    'timeout', 'connection'
                ])
                if is_connection_error:
                    # 连接错误时增加等待时间，特别是RemoteDisconnected
                    # 腾讯API对高频请求有限制，需要更长等待
                    if retry < 2:
                        wait_time = 2.0 * (retry + 1)  # 2s, 4s, 6s
                        if 'remote' in err_str or 'disconnected' in err_str:
                            wait_time *= 1.5  # RemoteDisconnected错误等待更久
                        logger.debug("腾讯API连接错误 %s, 等待 {wait_time:.1f}s 后重试", symbol)
                        time.sleep(wait_time)
                        continue
                else:
                    # 非连接错误，稍作等待后重试
                    if retry < 2:
                        time.sleep(0.5 * (retry + 1))
                        continue
        # 记录失败
        if last_error:
            logger.debug("腾讯HTTP失败 %s: %s", symbol, last_error)
        return pd.DataFrame()

    # ── Backtrader 格式转换 ─────────────────────────────────
    def to_backtrader(self, df: pd.DataFrame) -> "bt.feeds.PandasData":
        """将 DataFrame 转换为 Backtrader PandasData"""
        import backtrader as bt
        if not isinstance(df.index, pd.DatetimeIndex):
            if "date" in df.columns:
                df = df.set_index("date")
            else:
                raise ValueError("缺少日期列")
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        for col in ["open", "high", "low", "close", "volume"]:
            if col not in df.columns:
                df[col] = 0.0
        return bt.feeds.PandasData(
            dataname=df, datetime=None,
            open="open", high="high", low="low", close="close",
            volume="volume", openinterest=None,
        )

    def load_multi_for_backtest(
        self,
        codes: List[str],
        start_date: str = "20230101",
        end_date: Optional[str] = None,
    ) -> Dict[str, pd.DataFrame]:
        """为回测批量加载数据（仅从本地数据库获取）"""
        end = end_date or date.today().strftime("%Y%m%d")
        results = {}

        # 仅从本地数据库获取
        if self._local_db_enabled and self._local_db:
            logger.info(f"从本地数据库加载 {len(codes)} 只股票回测数据...")
            for i, code in enumerate(codes):
                logger.info("加载 [{i+1}/{len(codes)}]: %s", code)
                try:
                    # 计算天数
                    start_dt = datetime.strptime(start_date, "%Y%m%d")
                    end_dt = datetime.strptime(end, "%Y%m%d")
                    days = (end_dt - start_dt).days + 1
                    
                    df = self._local_db.get_daily(code, days=days)
                    if not df.empty:
                        # 过滤日期范围
                        df = df[(df.index >= start_dt) & (df.index <= end_dt)]
                        if not df.empty:
                            # 标准化数据格式
                            df = self._standardize(df.reset_index())
                            results[code] = df
                        else:
                            logger.warning("本地数据库 %s 在指定日期范围内无数据", code)
                    else:
                        logger.warning("本地数据库 %s 数据不足", code)
                except Exception as e:
                    logger.error("加载 %s 失败: %s", code, e)
        else:
            logger.error("本地数据库未启用，请先启用本地数据库")
        
        return results

    def _load_for_backtest(self, code, start, end):
        """单个股票加载（回测用，仅从本地数据库获取）"""
        # 计算天数
        start_dt = datetime.strptime(start, "%Y%m%d")
        end_dt = datetime.strptime(end, "%Y%m%d")
        days = (end_dt - start_dt).days + 1
        
        try:
            df = self._local_db.get_daily(code, days=days)
            if not df.empty:
                # 过滤日期范围
                df = df[(df.index >= start_dt) & (df.index <= end_dt)]
                if not df.empty:
                    # 标准化数据格式
                    return self._standardize(df.reset_index())
                else:
                    raise ValueError(f"本地数据库 {code} 在指定日期范围内无数据")
            else:
                raise ValueError(f"本地数据库 {code} 数据不足")
        except Exception as e:
            raise ValueError(f"无法加载 {code}: {e}")

    def _standardize(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化 DataFrame → [date, open, high, low, close, volume, amount, turnover]"""
        col_map = {'日期':'date','开盘':'open','收盘':'close','最高':'high','最低':'low',
                   '成交量':'volume','成交额':'amount','涨跌幅':'pct_change'}
        rename = {}
        for col in df.columns:
            cl = col.lower().strip()
            if cl in col_map:
                rename[col] = col_map[cl]
        df = df.rename(columns=rename)

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        elif isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index().rename(columns={"index": "date"})

        df = df.dropna(subset=["date", "close"])
        df = df[~df["date"].duplicated(keep="last")]

        for col in ["open","high","low","close","volume","amount","turnover"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            else:
                df[col] = 0.0

        # 停牌处理
        price_cols = ["open", "high", "low", "close"]
        mask = (df[price_cols] == 0).all(axis=1)
        for c in price_cols:
            df.loc[mask, c] = np.nan
        df[price_cols] = df[price_cols].ffill()
        df = df.dropna(subset=["close"])

        df["high"] = df[["high", "open", "close"]].max(axis=1)
        df["low"] = df[["low", "open", "close"]].min(axis=1)
        df = df.sort_values("date").reset_index(drop=True)
        return df


# ── 向后兼容别名 ───────────────────────────────────────────
# 旧代码仍可使用:
#   from real_data_fetcher import RealDataFetcher
# 或:
#   from core.data import RealDataFetcher
RealDataFetcher = UnifiedDataFetcher
