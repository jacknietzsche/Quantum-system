"""Baostock 数据源适配器

Baostock 免费、稳定、无频率限制, 适合历史K线和基本面。
注意: 需要 login/logout, 使用类级别缓存避免频繁登录。
"""

import io
import logging
import warnings
from datetime import datetime, timedelta

import pandas as pd

from providers.source_base import SourceAdapter, classify_error
from shared.logging import emit_log

logger = logging.getLogger(__name__)


class BaostockAdapter(SourceAdapter):
    name = "baostock"
    priority = 15
    timeout = 15.0

    _bs_lg = None  # 类级别缓存登录状态

    def _login(self):
        """延迟登录, 类级别缓存"""
        if BaostockAdapter._bs_lg is None:
            try:
                import baostock as bs
            except ImportError:
                return None

            old_stderr = __import__("sys").stderr
            old_stdout = __import__("sys").stdout
            null_buf = io.StringIO()
            __import__("sys").stderr = null_buf
            __import__("sys").stdout = null_buf
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=ResourceWarning)
                try:
                    lg = bs.login()
                    BaostockAdapter._bs_lg = lg if lg.error_code == "0" else False
                except Exception:
                    BaostockAdapter._bs_lg = False
                finally:
                    __import__("sys").stderr = old_stderr
                    __import__("sys").stdout = old_stdout

        return None if BaostockAdapter._bs_lg is False else BaostockAdapter._bs_lg

    def _prepare_code(self, code: str) -> str:
        """标准化为 baostock 格式 (sh.600519 / sz.000001)"""
        code = code.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
        if code.startswith(("6", "9")):
            return f"sh.{code}"
        if code.startswith(("0", "3", "2")):
            return f"sz.{code}"
        if code.startswith(("4", "8")):
            return f"bj.{code}"
        return f"sz.{code}"

    # ── 指数 ──

    def fetch_indices(self) -> dict | None:
        lg = self._login()
        if lg is None:
            return None
        try:
            import baostock as bs
        except ImportError:
            return None

        result = {
            "indices": {},
            "breadth": {
                "total": 0,
                "up": 0,
                "down": 0,
                "flat": 0,
                "limit_up": 0,
                "limit_down": 0,
                "up_ratio": 0,
            },
            "sectors": [],
            "data_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        index_map = {
            "sh.000001": "上证指数",
            "sz.399001": "深证成指",
            "sz.399006": "创业板指",
            "sh.000905": "中证500",
        }
        today = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        fields = "date,code,close,pctChg,amount"

        for bs_idx, name in index_map.items():
            try:
                rs = bs.query_history_k_data_plus(
                    bs_idx, fields, start_date=start, end_date=today, frequency="d", adjustflag="1"
                )
                if rs.error_code == "0":
                    rows = []
                    while rs.next():
                        rows.append(rs.get_row_data())
                    if rows:
                        latest = rows[-1]
                        result["indices"][name] = {
                            "price": float(latest[2]) if latest[2] else 0,
                            "change_pct": round(float(latest[3]) or 0, 2),
                            "amount": float(latest[4]) if len(latest) > 4 and latest[4] else 0,
                        }
            except Exception:
                logger.debug("Suppressed error in loop")
                continue
        return result if result["indices"] else None

    # ── K线 ──

    def fetch_kline(self, code: str, days: int = 90):
        lg = self._login()
        if lg is None:
            return None
        try:
            import baostock as bs
        except ImportError:
            return None

        try:
            bs_code = self._prepare_code(code)
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y-%m-%d")
            fields = "date,open,high,low,close,volume,amount,turn,peTTM,pbMRQ"
            rs = bs.query_history_k_data_plus(
                bs_code,
                fields,
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="2",
            )
            if rs.error_code != "0":
                return None
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())
            if not rows:
                return None
            df = pd.DataFrame(rows, columns=fields.split(","))
            for col in ["open", "high", "low", "close", "volume", "amount", "turn"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df[df["volume"] > 0]
            return df.tail(days)
        except Exception as e:
            raise classify_error(e, self.name) from e

    # ── 基本面 ──

    def fetch_basic(self, code: str) -> dict | None:
        lg = self._login()
        if lg is None:
            return None
        try:
            import baostock as bs
        except ImportError:
            return None

        try:
            bs_code = self._prepare_code(code)
            basic_data = {"stock_code": code}

            # 1. 基本信息
            rs = bs.query_stock_basic(code=bs_code)
            if rs.error_code == "0":
                while rs.next():
                    row = rs.get_row_data()
                    basic_data.update(
                        {
                            "stock_name": row[1] if len(row) > 1 else "",
                            "ipo_date": row[2] if len(row) > 2 else "",
                        }
                    )

            # 2. 估值
            today = datetime.now().strftime("%Y-%m-%d")
            rs_val = bs.query_history_k_data_plus(
                bs_code,
                "date,peTTM,pbMRQ,psTTM",
                start_date=(datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
                end_date=today,
                frequency="d",
                adjustflag="2",
            )
            if rs_val.error_code == "0":
                rows_val = []
                while rs_val.next():
                    rows_val.append(rs_val.get_row_data())
                if rows_val:
                    latest = rows_val[-1]
                    basic_data.update(
                        {
                            "pe_ratio": float(latest[1]) if latest[1] else 0,
                            "pb_ratio": float(latest[2]) if latest[2] else 0,
                        }
                    )

            # 3. 行业
            rs_ind = bs.query_stock_industry(bs_code)
            if rs_ind.error_code == "0":
                while rs_ind.next():
                    row = rs_ind.get_row_data()
                    if len(row) > 3:
                        basic_data["industry"] = row[3]

            return basic_data
        except Exception as e:
            raise classify_error(e, self.name) from e

    # ── 连接测试 ──

    def test_connect(self) -> bool:
        try:
            lg = self._login()
            return lg is not None
        except Exception as e:
            emit_log("WARNING", "baostock_src", f"Operation failed: {str(e)[:100]}")
            return False
