"""腾讯财经数据源适配器

API:
- 指数/实时行情: http://qt.gtimg.cn/q=...
- K线: http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=...
"""

import json
import logging

import pandas as pd

from providers.source_base import SourceAdapter, classify_error, retry_with_backoff
from shared.logging import emit_log

logger = logging.getLogger(__name__)

_CODE_MAP = {"000001": "上证指数", "399001": "深证成指", "399006": "创业板指", "000905": "中证500"}
_TX_CODES = ["sh000001", "sz399001", "sz399006", "sh000905"]


class TencentAdapter(SourceAdapter):
    name = "tencent"
    priority = 9  # 高于 EastMoney(10) — 更稳定可靠
    timeout = 8.0

    # ── 指数 ──

    def fetch_indices(self) -> dict | None:
        try:
            url = f"http://qt.gtimg.cn/q={','.join(_TX_CODES)}"
            resp = retry_with_backoff(
                lambda: self.http.get(url, timeout=5),
                max_retries=1,
            )
            text = resp.text

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
                "data_time": __import__("time").strftime("%Y-%m-%d %H:%M"),
            }
            for line in text.strip().split("\n"):
                if "~" not in line or '"' not in line:
                    continue
                fields = line.split('"')[1].split("~")
                if len(fields) < 40:
                    continue
                idx_code = fields[2]
                idx_name = _CODE_MAP.get(idx_code, idx_code)
                result["indices"][idx_name] = {
                    "price": float(fields[3] or 0),
                    "change_pct": round(float(fields[32] or 0), 2),
                    "amount": float(fields[37] or 0),
                }
            return result if result["indices"] else None
        except Exception as e:
            raise classify_error(e, self.name) from e

    # ── 实时行情 ──

    def fetch_stock_spot(self):
        try:
            return self._fetch_market_spot("sh_a", "sz_a")
        except Exception as e:
            raise classify_error(e, self.name) from e

    def fetch_etf_spot(self):
        try:
            return self._fetch_market_spot("sh_et", "sz_et", "sh_f", "sz_f")
        except Exception as e:
            raise classify_error(e, self.name) from e

    def _fetch_market_spot(self, *markets: str, max_pages: int = 20):
        """全市场快照 — 最多 max_pages 页 (每页60只), 空页提前 break"""
        rows = []
        seen_codes = set()
        import time as _time

        for mkt in markets:
            for page in range(max_pages):
                url = f"http://qt.gtimg.cn/q={mkt}&offset={page * 60}&limit=60"
                try:
                    resp = self.http.get(url, timeout=5)
                    text = resp.text
                except Exception:
                    break

                batch = [ln for ln in text.strip().split("\n") if "=" in ln]
                if not batch:
                    break

                for line in batch:
                    parts = line.split("=")[1].strip('"').strip(";").split("~")
                    if len(parts) < 45:
                        continue
                    code = parts[2]
                    if code in seen_codes:
                        continue
                    seen_codes.add(code)
                    rows.append(
                        {
                            "代码": parts[2],
                            "名称": parts[1],
                            "最新价": float(parts[3] or 0),
                            "涨跌幅": float(parts[32] or 0),
                            "涨跌额": float(parts[31] or 0),
                            "成交量": float(parts[6] or 0),
                            "成交额": float(parts[37] or 0),
                            "换手率": float(parts[38] or 0),
                            "市盈率-动态": float(parts[39] or 0),
                            "总市值": float(parts[45] or 0),  # 亿元
                            "流通市值": float(parts[44] or 0),  # 亿元
                        }
                    )

                _time.sleep(0.1)  # 反爬虫

        return pd.DataFrame(rows) if rows else None

    # ── K线 ──

    def fetch_kline(self, code: str, days: int = 90):
        try:
            prefix = "sh" if code.startswith(("6", "9")) else "sz"
            url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,{days},qfq"
            resp = retry_with_backoff(
                lambda: self.http.get(url, timeout=8),
                max_retries=1,
            )
            data = json.loads(resp.text)
            klines = data.get("data", {}).get(f"{prefix}{code}", {}).get("day", []) or data.get(
                "data", {}
            ).get(f"{prefix}{code}", {}).get("qfqday", [])
            if not klines:
                return None
            df = pd.DataFrame(klines, columns=["date", "open", "close", "high", "low", "volume"])
            for col in ["open", "close", "high", "low", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            return df.tail(days)
        except Exception as e:
            raise classify_error(e, self.name) from e

    # ── 基本面 ──

    def fetch_basic(self, code: str) -> dict | None:
        """获取个股基本面 — 腾讯行情接口提供 PE/换手率"""
        try:
            prefix = "sh" if code.startswith(("6", "9")) else "sz"
            url = f"http://qt.gtimg.cn/q={prefix}{code}"
            resp = retry_with_backoff(
                lambda: self.http.get(url, timeout=5),
                max_retries=1,
            )
            parts = resp.text.split('"')[1].split("~")
            if len(parts) < 45:
                return None
            return {
                "stock_name": parts[1],
                "latest_price": float(parts[3] or 0),
                "change_pct": float(parts[32] or 0),
                "turnover_rate": float(parts[38] or 0),
                "pe_ratio": float(parts[39] or 0),
                "high": float(parts[33] or 0),
                "low": float(parts[34] or 0),
                "volume": float(parts[6] or 0),
                "amount": float(parts[37] or 0),
                "total_market_cap": float(parts[45] or 0),  # 亿元直接返回
                "float_market_cap": float(parts[44] or 0),  # 亿元直接返回
            }
        except Exception as e:
            from providers.source_base import classify_error

            raise classify_error(e, self.name) from e

    # ── 连接测试 ──

    def test_connect(self) -> bool:
        try:
            result = self.fetch_indices()
            return result is not None and bool(result.get("indices"))
        except Exception as e:
            emit_log("WARNING", "tencent", f"Operation failed: {str(e)[:100]}")
            return False
