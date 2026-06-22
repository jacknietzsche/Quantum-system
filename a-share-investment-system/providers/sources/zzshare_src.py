"""ZZShare 数据源适配器 - 仅日频数据

ZZShare 提供 A 股日线数据, 股票基本信息, 板块排行, 市场情绪等。
接口兼容 Tushare 风格, 需注册 token。

数据来源: api.zizizaizai.com
文档: https://github.com/zzquant/zzshare

仅使用日频接口, 不访问任何分钟级/实时高频数据。
"""

import logging
from datetime import datetime, timedelta

import pandas as pd

from providers.source_base import SourceAdapter, TransientError

logger = logging.getLogger(__name__)

# Token 配置 (用户已提供)
_ZZSHARE_TOKEN = "2325ceca9c98c56ed1948594ba23ceaa8c7de7a3f2f33aff2733825f038917c0"  # noqa: S105


class ZZShareAdapter(SourceAdapter):
    name = "zzshare"
    priority = 30  # 在 tushare(22) 之后, sina(25) 之前
    timeout = 10.0

    _api = None

    def _get_api(self):
        if self._api is None:
            from zzshare.client import DataApi

            self._api = DataApi(token=_ZZSHARE_TOKEN, timeout=int(self.timeout))
        return self._api

    # ── 个股基本信息 ──

    def fetch_basic(self, code: str, fast: bool = False) -> dict | None:
        """获取个股基本面 (日频数据)

        ZZShare 不提供 PE/ROE/EPS 等财务字段,
        但提供 industry(行业) 和 name(股票名称),
        可填补其他数据源在这些字段上的空白。
        """
        try:
            api = self._get_api()
        except ImportError:
            logger.debug("[zzshare] zzshare not installed")
            return None

        try:
            df = api.stock_basic(ts_code=code)
            if df is None or df.empty:
                return None

            row = df.iloc[0]
            result = {
                "stock_name": str(row.get("name", row.get("symbol", "")) or ""),
                "industry": str(row.get("industry", "") or ""),
            }

            if not result.get("stock_name"):
                return None

            # non-fast mode: also fetch latest price + extended info
            if not fast:
                # 尝试获取扩展信息 stock_info (非必需)
                try:
                    info = api.query("stock_info", {"stock_id": code, "info_type": "basic"})
                    if isinstance(info, dict):
                        result["stock_name"] = str(info.get("name", result["stock_name"]))
                        if info.get("industry"):
                            result["industry"] = str(info["industry"])
                except Exception:
                    pass

                # 从 daily 获取最新价格
                try:
                    today = datetime.now().strftime("%Y-%m-%d")
                    start = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
                    kline = api.daily(ts_code=code, start_date=start, end_date=today)
                    if kline is not None and not kline.empty:
                        last = kline.iloc[-1]
                        result["latest_price"] = float(last.get("close", 0))
                        result["change_pct"] = float(last.get("pct_chg", 0))
                        result["volume"] = float(last.get("vol", 0))
                        result["amount"] = float(last.get("amount", 0))
                except Exception:
                    pass

            return result

        except Exception as e:
            err_msg = str(e)[:80]
            logger.debug("[zzshare] fetch_basic(%s) failed: %s", code, err_msg)
            raise TransientError(f"[zzshare] fetch_basic({code}): {err_msg}") from e

    # ── 日K线 ──

    def fetch_kline(self, code: str, days: int = 90) -> pd.DataFrame | None:
        """获取个股日K线 (日频数据, 非分钟级)"""
        try:
            api = self._get_api()
        except ImportError:
            logger.debug("[zzshare] zzshare not installed")
            return None

        try:
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=days + 10)).strftime("%Y-%m-%d")

            df = api.daily(ts_code=code, start_date=start, end_date=end)
            if df is None or df.empty:
                return None

            # zzshare 同时返回 change(涨跌额) 和 pct_chg(涨跌幅),
            # 统一列名为系统标准格式
            col_map = {"trade_date": "date", "pct_chg": "change"}
            rename_map = {k: v for k, v in col_map.items() if k in df.columns}
            df = df.rename(columns=rename_map)

            # 去除重复列名 (zzshare 有时返回两个 change)
            df = df.loc[:, ~df.columns.duplicated()]

            df["date"] = df["date"].astype(str)
            if "date" in df.columns:
                df = df.sort_values("date").reset_index(drop=True)
            return df.tail(days).reset_index(drop=True)

        except Exception as e:
            err_msg = str(e)[:80]
            logger.debug("[zzshare] fetch_kline(%s) failed: %s", code, err_msg)
            raise TransientError(f"[zzshare] fetch_kline({code}): {err_msg}") from e

    # ── 热门股票 ──

    def fetch_hot_stocks(self, sort: str = "change_pct", limit: int = 100) -> list | None:
        """获取热门股票 (基于同花顺热度数据, 日频)"""
        try:
            api = self._get_api()
        except ImportError:
            return None

        try:
            today = datetime.now().strftime("%Y-%m-%d")

            # 尝试1: 同花顺热门 Top
            try:
                result = api.query("ths_hot_top", {"date1": today, "top_n": limit})
                if isinstance(result, list) and result:
                    return result[:limit]
            except Exception:
                pass

            # fallback: query limit-up stocks as hot stock backup
            try:
                stocks = api.query("uplimit_stocks", {"date1": today})
                if isinstance(stocks, list) and stocks:
                    return stocks[:limit]
            except Exception:
                pass

            return None

        except Exception:
            logger.debug("[zzshare] fetch_hot_stocks failed")
            return None

    # ── 板块排行 ──

    def fetch_sector_rank(self, plate_type: int = 17, limit: int = 20) -> list | None:
        """获取板块排行 (plate_type: 17=概念, 15=地域, 14=行业)

        仅日频数据, 不涉及实时分时数据。
        """
        try:
            api = self._get_api()
        except ImportError:
            return None

        try:
            today = datetime.now().strftime("%Y-%m-%d")
            result = api.plates_rank(plate_type=plate_type, date1=today, limit=limit)
            if isinstance(result, list) and result:
                return result
            return None
        except Exception:
            logger.debug("[zzshare] sector_rank failed")
            return None

    # ── 连接测试 ──

    def test_connect(self) -> bool:
        """轻量连接测试: 直接 ping API 根路径 (~500ms, 避免 DataApi 8s+ 延迟)"""
        try:
            import urllib.request

            req = urllib.request.Request("https://api.zizizaizai.com/")
            resp = urllib.request.urlopen(req, timeout=5)  # noqa: S310
            return resp.status == 200
        except Exception:
            return False
