"""新浪财经数据源适配器

API endpoints:
- 指数: http://hq.sinajs.cn/list=s_sh000001,s_sz399001,...
- 实时行情: https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/...
- K线: https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/...
"""

import json
import logging

import pandas as pd

from providers.source_base import SourceAdapter, classify_error, retry_with_backoff
from shared.logging import emit_log

logger = logging.getLogger(__name__)

_CODE_MAP = {
    "s_sh000001": "上证指数",
    "s_sz399001": "深证成指",
    "s_sz399006": "创业板指",
    "s_sh000905": "中证500",
}


class SinaAdapter(SourceAdapter):
    name = "sina"
    priority = 25
    timeout = 10.0

    # ── 指数 ──

    def fetch_indices(self) -> dict | None:
        try:
            codes = ",".join(_CODE_MAP.keys())
            url = f"http://hq.sinajs.cn/list={codes}"
            resp = retry_with_backoff(
                lambda: self.http.get(
                    url, timeout=8, headers={"Referer": "https://finance.sina.com.cn"}
                ),
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
                if "=" not in line or '"' not in line:
                    continue
                code_key = line.split("=")[0].replace("var hq_str_", "").strip()
                vals = line.split('"')[1].split(",")
                if len(vals) < 4:
                    continue
                name = _CODE_MAP.get(code_key, code_key)
                result["indices"][name] = {
                    "price": float(vals[1] or 0),
                    "change_pct": round(float(vals[3] or 0), 2),
                    "amount": float(vals[4] or 0) if len(vals) > 4 else 0,
                }
            return result if result["indices"] else None
        except Exception as e:
            raise classify_error(e, self.name) from e

    # ── 实时行情 ──

    def fetch_stock_spot(self):
        try:
            rows = []
            for page in range(1, 6):
                url = (
                    "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
                    f"Market_Center.getHQNodeData?page={page}&num=800&sort=symbol"
                    "&asc=1&node=hs_a&symbol=&_s_r_a=auto"
                )
                resp = retry_with_backoff(
                    lambda u=url: self.http.get(
                        u, timeout=10, headers={"Referer": "https://finance.sina.com.cn"}
                    ),
                    max_retries=1,
                )
                batch = json.loads(resp.text)
                if not batch:
                    break
                for item in batch:
                    code_raw = str(item.get("symbol", ""))
                    pure_code = (
                        code_raw[2:]
                        if len(code_raw) > 2 and code_raw[:2] in ("sh", "sz", "bj")
                        else code_raw
                    )
                    rows.append(
                        {
                            "代码": pure_code,
                            "名称": str(item.get("name", "")),
                            "最新价": float(item.get("trade", 0) or 0),
                            "涨跌幅": float(item.get("changepercent", 0) or 0),
                            "涨跌额": float(item.get("pricechange", 0) or 0),
                            "成交量": float(item.get("volume", 0) or 0) / 100,
                            "成交额": float(item.get("amount", 0) or 0),
                            "市盈率-动态": float(item.get("per", 0) or 0),
                        }
                    )
            return pd.DataFrame(rows) if rows else None
        except Exception as e:
            raise classify_error(e, self.name) from e

    # ── ETF ──

    def fetch_etf_spot(self):
        try:
            import pandas as pd

            rows = []
            for node in ("hs_etf", "hs_fund"):
                for page in range(1, 16):
                    url = (
                        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
                        f"Market_Center.getHQNodeData?page={page}&num=800&sort=symbol"
                        f"&asc=1&node={node}&symbol=&_s_r_a=auto"
                    )
                    resp = self.http.get(
                        url, timeout=10, headers={"Referer": "https://finance.sina.com.cn"}
                    )
                    batch = json.loads(resp.text)
                    if not batch:
                        break
                    for item in batch:
                        code_raw = str(item.get("symbol", ""))
                        pure_code = (
                            code_raw[2:]
                            if len(code_raw) > 2 and code_raw[:2] in ("sh", "sz", "bj")
                            else code_raw
                        )
                        if not pure_code or len(pure_code) != 6:
                            continue
                        rows.append(
                            {
                                "代码": pure_code,
                                "名称": str(item.get("name", "")),
                                "最新价": float(item.get("trade", 0) or 0),
                                "涨跌幅": float(item.get("changepercent", 0) or 0),
                            }
                        )
            return pd.DataFrame(rows) if rows else None
        except Exception as e:
            raise classify_error(e, self.name) from e

    # ── K线 ──

    def fetch_kline(self, code: str, days: int = 90):
        try:
            prefix = "sh" if code.startswith(("6", "9")) else "sz"
            url = (
                "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
                f"CN_MarketData.getKLineData?symbol={prefix}{code}&scale=240&ma=no&datalen={days}"
            )
            resp = retry_with_backoff(
                lambda: self.http.get(
                    url, timeout=10, headers={"Referer": "https://finance.sina.com.cn"}
                ),
                max_retries=1,
            )
            data = json.loads(resp.text)
            if not data:
                return None
            df = pd.DataFrame(data)
            for col in ["open", "close", "high", "low", "volume"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            return df.tail(days)
        except Exception as e:
            raise classify_error(e, self.name) from e

    # ── 基本面 ──

    def fetch_basic(self, code: str) -> dict | None:
        try:
            prefix = "sh" if code.startswith(("6", "9")) else "sz"
            url = f"http://hq.sinajs.cn/list={prefix}{code}"
            resp = retry_with_backoff(
                lambda: self.http.get(
                    url, timeout=8, headers={"Referer": "https://finance.sina.com.cn"}
                ),
                max_retries=1,
            )
            text = resp.text
            if '"' not in text:
                return None
            parts = text.split('"')[1].split(",")
            if len(parts) < 10:
                return None
            prev_close = float(parts[2] or 0)
            current = float(parts[3] or 0)
            change_pct = round((current - prev_close) / prev_close * 100, 2) if prev_close else 0
            return {
                "stock_name": parts[0],
                "latest_price": current,
                "price": current,
                "change_pct": change_pct,
                "high": float(parts[4] or 0),
                "low": float(parts[5] or 0),
                "volume": float(parts[8] or 0) if len(parts) > 8 else 0,
                "amount": float(parts[9] or 0) if len(parts) > 9 else 0,
            }
        except Exception as e:
            raise classify_error(e, self.name) from e

    # ── 连接测试 ──

    def test_connect(self) -> bool:
        try:
            result = self.fetch_indices()
            return result is not None and bool(result.get("indices"))
        except Exception as e:
            emit_log("WARNING", "sina", f"Operation failed: {str(e)[:100]}")
            return False
