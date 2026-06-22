"""东方财富龙虎榜数据源适配器"""

import logging

import pandas as pd

from providers.source_base import SourceAdapter, classify_error
from shared.logging import emit_log

logger = logging.getLogger(__name__)


class LHBAdapter(SourceAdapter):
    name = "lhb"
    priority = 45
    timeout = 15.0

    def fetch_lhb_detail(self, date: str) -> pd.DataFrame | None:
        """龙虎榜每日详情 — 东财接口

        Parameters
        ----------
        date : str
            日期, 格式 ``"20260513"`` 或 ``"2026-05-13"``

        Returns
        -------
        Optional[pd.DataFrame]
            列: 代码, 名称, 龙虎榜买入额, 龙虎榜卖出额, 龙虎榜净买额, ...
        """
        # 列名映射表:AKShare 返回的原始列名 → 系统统一列名
        COL_NAME_MAP = {
            "股票代码": "代码",
            "代码": "代码",
            "股票名称": "名称",
            "名称": "名称",
            "买入额": "龙虎榜买入额",
            "买入金额": "龙虎榜买入额",
            "卖出额": "龙虎榜卖出额",
            "卖出金额": "龙虎榜卖出额",
            "净额": "龙虎榜净买额",
            "净买入额": "龙虎榜净买额",
        }
        try:
            import akshare as ak

            clean = date.replace("-", "")
            df = ak.stock_lhb_detail_em(start_date=clean, end_date=clean)
            if df is not None and not df.empty:
                # Column-name based matching (order/quantity independent)
                result = {}
                for src_col, dest_name in COL_NAME_MAP.items():
                    if src_col in df.columns:
                        result[dest_name] = df[src_col]
                if "代码" in result:
                    df = pd.DataFrame(result)
                else:
                    df = pd.DataFrame(
                        {
                            "代码": [],
                            "名称": [],
                            "龙虎榜买入额": [],
                            "龙虎榜卖出额": [],
                            "龙虎榜净买额": [],
                        }
                    )
            elif df is None:
                return None
            else:
                df = pd.DataFrame(
                    {
                        "代码": [],
                        "名称": [],
                        "龙虎榜买入额": [],
                        "龙虎榜卖出额": [],
                        "龙虎榜净买额": [],
                    }
                )
            return df
        except Exception as e:
            raise classify_error(e, self.name) from e

    def fetch_lhb_stock_statistic(self, symbol: str = "近一月") -> pd.DataFrame | None:
        """个股上榜统计

        Parameters
        ----------
        symbol : str
            统计周期, 可选 {"近一月", "近三月", "近六月", "近一年"}
        """
        try:
            import akshare as ak

            return ak.stock_lhb_stock_statistic_em(symbol=symbol)
        except Exception as e:
            raise classify_error(e, self.name) from e

    def test_connect(self) -> bool:
        try:
            import akshare as ak

            df = ak.stock_lhb_detail_em(start_date="20260401", end_date="20260430")
            return df is not None and not df.empty
        except Exception as e:
            emit_log("WARNING", "lhb", f"Operation failed: {str(e)[:100]}")
            return False
