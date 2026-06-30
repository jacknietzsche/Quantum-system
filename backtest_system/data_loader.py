"""
DataLoader 数据加载模块
========================
支持多种数据源加载 A 股行情数据，统一输出 Backtrader PandasData 格式。

数据源支持:
    1. akshare 在线获取（日频/分钟频）
    2. CSV 本地文件
    3. HDF5 本地文件
    4. 内置 baostock 作为 fallback

数据清洗:
    - 停牌处理（填充/跳过）
    - 复权处理
    - 缺失值处理
    - 格式标准化
"""

import logging
import os
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Union, Dict, List

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class DataLoader:
    """
    统一数据加载器

    用法:
        loader = DataLoader(start_date="20240101", end_date="20260327")
        df = loader.load_stock("600519")       # 加载单只股票
        benchmark = loader.load_benchmark()    # 加载基准
        bt_data = loader.to_backtrader(df)     # 转换为 PandasData
    """

    def __init__(
        self,
        start_date: str = "20230101",
        end_date: Optional[str] = None,
        adjust: str = "qfq",
        cache_dir: Optional[str] = None,
        cache_hours: int = 24,
    ):
        """
        初始化数据加载器

        Args:
            start_date: 起始日期 (YYYYMMDD)
            end_date: 截止日期 (YYYYMMDD)，默认今天
            adjust: 复权类型 qfq/hfq/None
            cache_dir: 缓存目录
            cache_hours: 缓存有效期（小时）
        """
        self.start_date = start_date
        self.end_date = end_date or date.today().strftime("%Y%m%d")
        self.adjust = adjust
        self.cache_dir = Path(cache_dir) if cache_dir else Path(__file__).resolve().parent / "cache" / "market_data"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_hours = cache_hours

        # 标准化列名映射（不同数据源 → 统一格式）
        self._col_map = {
            "date": "date",
            "trade_date": "date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "vol": "volume",
            "volume": "volume",
            "amount": "amount",
            "turnover": "turnover",
        }

        logger.info(f"DataLoader 初始化: {start_date} ~ {self.end_date}, 复权={adjust}")

    # ================================================================
    # 公开接口
    # ================================================================

    def load_stock(
        self,
        code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        source: str = "auto",
    ) -> pd.DataFrame:
        """
        加载单只股票行情数据

        Args:
            code: 股票代码 (如 "600519")
            start_date: 起始日期，默认使用初始化参数
            end_date: 截止日期
            source: 数据源 "auto" / "akshare" / "baostock" / "csv" / "hdf5"

        Returns:
            标准化 DataFrame，列: [date, open, high, low, close, volume, amount, turnover]
        """
        start = start_date or self.start_date
        end = end_date or self.end_date

        # 尝试从缓存加载
        if source == "auto":
            cached = self._load_cache(code, start, end)
            if cached is not None:
                logger.debug(f"从缓存加载 {code}: {len(cached)} 条记录")
                return cached

        # 优先从本地数据库加载
        if source == "auto":
            try:
                from core.local_db_fetcher import LocalDBFetcher
                local_db = LocalDBFetcher("local_db/a_stock_quant.db")
                # 计算需要的天数
                from datetime import datetime
                start_dt = datetime.strptime(start, "%Y%m%d")
                end_dt = datetime.strptime(end, "%Y%m%d")
                days = (end_dt - start_dt).days + 1
                df = local_db.get_daily(code, days=days)
                if not df.empty:
                    logger.debug(f"从本地数据库加载 {code}: {len(df)} 条记录")
                    # 标准化列名
                    df = df.rename(columns=self._col_map)
                    # 确保日期格式
                    if 'date' in df.columns:
                        df['date'] = pd.to_datetime(df['date'])
                    # 保存到缓存
                    self._save_cache(code, start, end, df)
                    return df
            except Exception as e:
                logger.debug(f"本地数据库加载失败: {e}")

        # 按优先级尝试数据源
        if source == "auto" or source == "akshare":
            df = self._fetch_akshare(code, start, end)
            if df is not None and not df.empty:
                self._save_cache(code, start, end, df)
                return df

        if source == "auto" or source == "baostock":
            df = self._fetch_baostock(code, start, end)
            if df is not None and not df.empty:
                self._save_cache(code, start, end, df)
                return df

        if source == "auto" or source == "csv":
            df = self._load_csv(code)
            if df is not None and not df.empty:
                return df

        if source == "auto" or source == "hdf5":
            df = self._load_hdf5(code)
            if df is not None and not df.empty:
                return df

        raise ValueError(f"无法加载股票 {code} 的数据，所有数据源均失败")

    def load_benchmark(self, code: str = "000300") -> pd.DataFrame:
        """加载基准指数行情"""
        return self.load_stock(code)

    def load_multi(
        self,
        codes: List[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, pd.DataFrame]:
        """
        批量加载多只股票

        Args:
            codes: 股票代码列表
            start_date: 起始日期
            end_date: 截止日期

        Returns:
            {股票代码: DataFrame} 字典
        """
        results = {}
        for i, code in enumerate(codes):
            logger.info(f"加载股票 [{i+1}/{len(codes)}]: {code}")
            try:
                df = self.load_stock(code, start_date, end_date)
                if df is not None and len(df) > 0:
                    results[code] = df
            except Exception as e:
                logger.warning(f"加载 {code} 失败: {e}")
        logger.info(f"批量加载完成: 成功 {len(results)}/{len(codes)} 只")
        return results

    def to_backtrader(self, df: pd.DataFrame) -> "bt.feeds.PandasData":
        """
        将 DataFrame 转换为 Backtrader PandasData 格式

        Args:
            df: 标准化后的 DataFrame

        Returns:
            Backtrader PandasData feed
        """
        import backtrader as bt

        # 确保日期索引
        if not isinstance(df.index, pd.DatetimeIndex):
            if "date" in df.columns:
                df = df.set_index("date")
            else:
                raise ValueError("DataFrame 缺少日期列，无法转换为 Backtrader 格式")

        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

        # 确保必需列存在
        required = ["open", "high", "low", "close", "volume"]
        for col in required:
            if col not in df.columns:
                df[col] = 0.0

        # 创建 PandasData
        data_feed = bt.feeds.PandasData(
            dataname=df,
            datetime=None,  # 使用索引
            open="open",
            high="high",
            low="low",
            close="close",
            volume="volume",
            openinterest=None,
        )

        return data_feed

    # ================================================================
    # 数据源实现
    # ================================================================

    def _fetch_akshare(self, code: str, start: str, end: str) -> Optional[pd.DataFrame]:
        """通过 akshare 获取行情数据"""
        try:
            import akshare as ak

            symbol = code
            period = "daily"
            start_fmt = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
            end_fmt = f"{end[:4]}-{end[4:6]}-{end[6:8]}"

            logger.debug(f"akshare 获取 {symbol}: {start_fmt} ~ {end_fmt}")
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period=period,
                start_date=start_fmt,
                end_date=end_fmt,
                adjust=self.adjust if self.adjust else "",
            )

            if df is None or df.empty:
                logger.debug(f"akshare 返回空数据: {symbol}")
                return None

            return self._standardize(df)

        except ImportError:
            logger.warning("akshare 未安装，请运行: pip install akshare")
            return None
        except Exception as e:
            logger.warning(f"akshare 获取 {code} 失败: {e}")
            return None

    def _fetch_baostock(self, code: str, start: str, end: str) -> Optional[pd.DataFrame]:
        """通过 baostock 获取行情数据（fallback）"""
        try:
            import baostock as bs

            # 登录
            lg = bs.login()
            if lg.error_code != "0":
                logger.warning(f"baostock 登录失败: {lg.error_msg}")
                return None

            try:
                # 转换代码格式
                bs_code = self._to_baostock_code(code)
                start_fmt = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
                end_fmt = f"{end[:4]}-{end[4:6]}-{end[6:8]}"

                rs = bs.query_history_k_data_plus(
                    bs_code,
                    "date,open,high,low,close,volume,amount,turn",
                    start_date=start_fmt,
                    end_date=end_fmt,
                    frequency="d",
                    adjustflag="2" if self.adjust == "qfq" else ("1" if self.adjust == "hfq" else "3"),
                )

                rows = []
                while rs.next():
                    row = rs.get_row_data()
                    if row[0]:  # date 不为空
                        rows.append(row)

                if not rows:
                    return None

                df = pd.DataFrame(rows, columns=[
                    "date", "open", "high", "low", "close", "volume", "amount", "turnover"
                ])

                return self._standardize(df)

            finally:
                bs.logout()

        except ImportError:
            logger.warning("baostock 未安装，请运行: pip install baostock")
            return None
        except Exception as e:
            logger.warning(f"baostock 获取 {code} 失败: {e}")
            return None

    def _load_csv(self, code: str) -> Optional[pd.DataFrame]:
        """从 CSV 文件加载"""
        csv_path = self.cache_dir / f"{code}.csv"
        if not csv_path.exists():
            return None

        try:
            df = pd.read_csv(csv_path)
            return self._standardize(df)
        except Exception as e:
            logger.warning(f"CSV 加载 {code} 失败: {e}")
            return None

    def _load_hdf5(self, code: str) -> Optional[pd.DataFrame]:
        """从 HDF5 文件加载"""
        hdf5_path = self.cache_dir / "market_data.h5"
        if not hdf5_path.exists():
            return None

        try:
            df = pd.read_hdf(hdf5_path, key=f"stock/{code}")
            return self._standardize(df)
        except (KeyError, FileNotFoundError):
            return None
        except Exception as e:
            logger.warning(f"HDF5 加载 {code} 失败: {e}")
            return None

    # ================================================================
    # 数据处理
    # ================================================================

    def _standardize(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        标准化 DataFrame 格式

        输出列: [date, open, high, low, close, volume, amount, turnover]
        """
        # 重命名列
        rename_map = {}
        for col in df.columns:
            col_lower = col.lower().strip()
            if col_lower in self._col_map:
                rename_map[col] = self._col_map[col_lower]
        df = df.rename(columns=rename_map)

        # 确保日期列
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        elif isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index()
            df = df.rename(columns={"index": "date", "level_0": "date"})

        # 移除无效行
        df = df.dropna(subset=["date", "close"])
        df = df[~df["date"].duplicated(keep="last")]

        # 数值类型转换
        for col in ["open", "high", "low", "close", "volume", "amount", "turnover"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            else:
                df[col] = 0.0

        # 停牌处理：价格全为0时填充前值
        price_cols = ["open", "high", "low", "close"]
        mask_suspended = (df[price_cols] == 0).all(axis=1)
        for col in price_cols:
            df.loc[mask_suspended, col] = np.nan
        df[price_cols] = df[price_cols].ffill()
        df = df.dropna(subset=["close"])

        # 保证 OHLC 逻辑正确
        df["high"] = df[["high", "open", "close"]].max(axis=1)
        df["low"] = df[["low", "open", "close"]].min(axis=1)

        # 排序
        df = df.sort_values("date").reset_index(drop=True)

        return df

    def _to_baostock_code(self, code: str) -> str:
        """股票代码转 baostock 格式 (sh.600519 / sz.000001)"""
        code = code.lstrip("sh.sz.SH.SZ.")
        if code.startswith("6"):
            return f"sh.{code}"
        else:
            return f"sz.{code}"

    # ================================================================
    # 缓存管理
    # ================================================================

    def _cache_path(self, code: str, start: str, end: str) -> Path:
        """生成缓存文件路径"""
        return self.cache_dir / f"{code}_{start}_{end}_{self.adjust}.pkl"

    def _load_cache(self, code: str, start: str, end: str) -> Optional[pd.DataFrame]:
        """从缓存加载"""
        if not self.cache_dir.exists():
            return None

        path = self._cache_path(code, start, end)
        if not path.exists():
            return None

        try:
            # 检查缓存有效期
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            age_hours = (datetime.now() - mtime).total_seconds() / 3600
            if age_hours > self.cache_hours:
                return None

            import pickle
            with open(path, "rb") as f:
                df = pickle.load(f)
            return df
        except Exception as e:
            logger.debug("cache load failed: %s", e)
            return None

    def _save_cache(self, code: str, start: str, end: str, df: pd.DataFrame):
        """保存到缓存"""
        try:
            import pickle
            path = self._cache_path(code, start, end)
            with open(path, "wb") as f:
                pickle.dump(df, f)
        except Exception as e:
            logger.debug(f"缓存保存失败: {e}")
