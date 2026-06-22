"""东方财富数据源适配器

注意: push2.eastmoney.com 当前环境可能为 IP 级阻断 (TCP RST)。
此适配器保留完整 API 调用逻辑,但优先使用 Sina/Tencent/Baostock 降级通路。

API: https://push2.eastmoney.com/api/qt/clist/get
"""

import json
import logging

from providers.source_base import SourceAdapter, classify_error, retry_with_backoff
from shared.logging import emit_log

logger = logging.getLogger(__name__)


class EastMoneyAdapter(SourceAdapter):
    name = "eastmoney"
    priority = 10  # 通常高优先级,但断路器会快速熔断
    timeout = 4.0  # 短超时:已知部分环境IP级阻断,SSLEOF通常<1s

    # ── 热门股票 ──

    def fetch_hot_stocks(self, sort: str = "change_pct", limit: int = 100) -> list | None:
        try:
            fid_map = {"change_pct": "f3", "volume": "f5", "turnover": "f6"}
            fid = fid_map.get(sort, "f3")
            url = (
                f"https://push2.eastmoney.com/api/qt/clist/get?"
                f"pn=1&pz={limit}&po=1&np=1&fltt=2&invt=2&fid={fid}"
                f"&fs=m:0+t:6,m:0+t:75,m:0+t:81,m:1+t:2,m:1+t:23"
                f"&fields=f2,f3,f4,f5,f6,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21"
            )
            resp = retry_with_backoff(
                lambda: self.http.get(
                    url, timeout=3, headers={"Referer": "https://quote.eastmoney.com/"}
                ),
                max_retries=1,
            )
            data = json.loads(resp.text)
            items = data.get("data", {}).get("diff", [])
            if not items:
                return None
            result = []
            for item in items:
                result.append(
                    {
                        "stock_code": str(item.get("f12", "")),
                        "stock_name": str(item.get("f14", "")),
                        "price": float(item.get("f2", 0) or 0),
                        "change_pct": float(item.get("f3", 0) or 0),
                        "change_amt": float(item.get("f4", 0) or 0),
                        "volume": float(item.get("f5", 0) or 0),
                        "amount": float(item.get("f6", 0) or 0),
                        "turnover_rate": float(item.get("f8", 0) or 0),
                        "pe_ratio": float(item.get("f9", 0) or 0),
                    }
                )
            return result
        except Exception as e:
            raise classify_error(e, self.name) from e

    # ── 纯代码列表 (热榜) ──

    def fetch_hot_stocks_code_list(self, limit: int = 100) -> list | None:
        try:
            url = (
                "https://push2.eastmoney.com/api/qt/clist/get?"
                f"pn=1&pz={limit}&po=1&np=1&fltt=2&invt=2&fid=f3"
                "&fs=m:0+t:6,m:0+t:75,m:0+t:81,m:1+t:2,m:1+t:23&fields=f12"
            )
            resp = retry_with_backoff(
                lambda: self.http.get(
                    url, timeout=3, headers={"Referer": "https://quote.eastmoney.com/"}
                ),
                max_retries=1,
            )
            data = json.loads(resp.text)
            return [i.get("f12", "") for i in data.get("data", {}).get("diff", []) if i.get("f12")]
        except Exception as e:
            raise classify_error(e, self.name) from e

    # ── 通用排序排行榜 ──

    def fetch_rank_by_field(self, fid: str, limit: int = 100) -> list | None:
        """按指定字段排序获取排行榜

        Args:
            fid: 排序字段ID (f3=涨跌幅, f6=成交额, f7=振幅, f10=量比)
            limit: 返回数量

        Returns:
            list[dict]: 排行榜列表
        """
        try:
            url = (
                f"https://push2.eastmoney.com/api/qt/clist/get?"
                f"pn=1&pz={limit}&po=1&np=1&fltt=2&invt=2&fid={fid}"
                f"&fs=m:0+t:6,m:0+t:75,m:0+t:81,m:1+t:2,m:1+t:23"
                f"&fields=f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21"
            )
            resp = retry_with_backoff(
                lambda: self.http.get(
                    url, timeout=3, headers={"Referer": "https://quote.eastmoney.com/"}
                ),
                max_retries=1,
            )
            data = json.loads(resp.text)
            items = data.get("data", {}).get("diff", [])
            if not items:
                return None
            result = []
            for item in items:
                result.append(
                    {
                        "stock_code": str(item.get("f12", "")),
                        "stock_name": str(item.get("f14", "")),
                        "price": float(item.get("f2", 0) or 0),
                        "change_pct": float(item.get("f3", 0) or 0),
                        "change_amt": float(item.get("f4", 0) or 0),
                        "volume": float(item.get("f5", 0) or 0),
                        "amount": float(item.get("f6", 0) or 0),
                        "amplitude": float(item.get("f7", 0) or 0),
                        "turnover_rate": float(item.get("f8", 0) or 0),
                        "pe_ratio": float(item.get("f9", 0) or 0),
                        "volume_ratio": float(item.get("f10", 0) or 0),
                    }
                )
            return result
        except Exception as e:
            raise classify_error(e, self.name) from e

    def fetch_turnover_rank(self, limit: int = 100) -> list | None:
        """获取成交额排行

        Returns:
            list[dict]: 成交额排行榜
        """
        return self.fetch_rank_by_field("f6", limit=limit)

    def fetch_amplitude_rank(self, limit: int = 100) -> list | None:
        """获取振幅排行

        Returns:
            list[dict]: 振幅排行榜
        """
        return self.fetch_rank_by_field("f7", limit=limit)

    def fetch_volume_ratio_rank(self, limit: int = 100) -> list | None:
        """获取量比排行

        Returns:
            list[dict]: 量比排行榜
        """
        return self.fetch_rank_by_field("f10", limit=limit)

    # ── 连接测试 ──

    def test_connect(self) -> bool:
        try:
            result = self.fetch_hot_stocks(limit=3)
            return result is not None
        except Exception as e:
            emit_log("WARNING", "eastmoney", f"Operation failed: {str(e)[:100]}")
            return False
