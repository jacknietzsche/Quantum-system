"""A股特色数据工具 - 龙虎榜/主力资金/涨停板 - 数据库优先 + 日频策略适配"""

import json
from datetime import datetime

from services.base import BaseService, ServiceResult
from services.trading_calendar import TradingCalendar
from shared.logging import emit_log, log_exception


class AShareDataTools(BaseService):
    """A股特色数据:龙虎榜,主力资金,涨停池。日频策略 - 默认取最近交易日数据"""

    def __init__(self, db_path: str = "data/investment.db"):
        super().__init__()
        self.db_path = db_path
        self._calendar = TradingCalendar()

    # ════════════════════════════════════════════
    #  龙虎榜
    # ════════════════════════════════════════════

    def get_lhb_detail(self, stock_code: str, date: str | None = None) -> ServiceResult:
        """龙虎榜明细 - DB缓存(24h) → AkShare → 降级空"""
        date = date or self._calendar.effective_data_date()
        cached = self._read_cache("lhb", stock_code, date)
        if cached:
            return ServiceResult.ok(data=cached)

        try:
            import akshare as ak

            df = ak.stock_sina_lhb_detail_daily(date=date.replace("-", ""))
            if df is not None and not df.empty:
                stock_rows = df[df["code"] == stock_code]
                if not stock_rows.empty:
                    result = {
                        "date": date,
                        "stock_code": stock_code,
                        "entries": stock_rows.head(20).to_dict("records"),
                        "has_data": True,
                        "count": len(stock_rows),
                    }
                    try:
                        buy_rows = stock_rows[stock_rows["type"].astype(str).str.contains("买")]
                        sell_rows = stock_rows[stock_rows["type"].astype(str).str.contains("卖")]
                        result["buy_amount"] = float(
                            buy_rows.select_dtypes(include="number").sum().sum()
                        )
                        result["sell_amount"] = float(
                            sell_rows.select_dtypes(include="number").sum().sum()
                        )
                    except Exception as e:
                        emit_log("WARNING", "ashare_data_tools", f"Data parse error: {str(e)[:80]}")
                        result["buy_amount"] = 0
                        result["sell_amount"] = 0
                    self._write_snapshot(f"lhb_{stock_code}_{date}", result)
                    return ServiceResult.ok(data=result)
        except Exception as e:
            log_exception("ashare_tools", e)
        return ServiceResult.ok(
            data={
                "date": date,
                "stock_code": stock_code,
                "entries": [],
                "has_data": False,
                "note": "无龙虎榜数据(该股当日未上榜或API不可用)",
            }
        )

    # ════════════════════════════════════════════
    #  主力资金流
    # ════════════════════════════════════════════

    def get_fund_flow(self, stock_code: str, days: int = 5) -> ServiceResult:
        """个股主力资金近N日净流向 - DB缓存(24h) → AkShare → 降级"""
        self._calendar.effective_data_date()
        cache_key = f"fundflow_{stock_code}_{days}d"
        cached = self._read_snapshot(cache_key)
        if cached:
            return ServiceResult.ok(data=cached)

        try:
            import akshare as ak

            market = "sh" if stock_code.startswith(("6", "9")) else "sz"
            df = ak.stock_individual_fund_flow(stock=stock_code, market=market)
            if df is not None and not df.empty:
                recent = df.tail(days)
                net_col = None
                for c in ["net_amount", "主力净流入", "主力净流入-净额"]:
                    if c in recent.columns:
                        net_col = c
                        break
                net_flow = float(recent[net_col].sum()) if net_col else 0
                result = {
                    "stock_code": stock_code,
                    "days": days,
                    "net_flow_sum": round(net_flow, 0),
                    "direction": "流入" if net_flow > 0 else ("流出" if net_flow < 0 else "平衡"),
                    "daily": recent.tail(days).to_dict("records") if net_col else [],
                }
                self._write_snapshot(cache_key, result)
                return ServiceResult.ok(data=result)
        except Exception as e:
            log_exception("ashare_tools", e)
        return ServiceResult.ok(
            data={
                "stock_code": stock_code,
                "net_flow_sum": 0,
                "direction": "未知",
                "note": "数据暂不可用",
            }
        )

    # ════════════════════════════════════════════
    #  涨停板情绪池
    # ════════════════════════════════════════════

    def get_limit_up_pool(self, date: str | None = None) -> ServiceResult:
        """涨停板情绪池 - 涨停数/连板数 → 市场温度计。日频策略: 每日收盘后调用"""
        date = date or self._calendar.effective_data_date()
        cache_key = f"zt_pool_{date}"
        cached = self._read_snapshot(cache_key)
        if cached:
            return ServiceResult.ok(data=cached)

        try:
            import akshare as ak

            df = ak.stock_zt_pool_em(date=date.replace("-", ""))
            if df is not None and not df.empty:
                total = len(df)
                sentiment = (
                    "极热"
                    if total > 100
                    else ("热" if total > 50 else ("温" if total > 20 else "冷"))
                )
                top_list = []
                for _, r in df.head(10).iterrows():
                    top_list.append(
                        {
                            "code": str(r.get("代码", "")),
                            "name": str(r.get("名称", "")),
                            "boards": int(r.get("连板数", 0) or 0),
                        }
                    )
                result = {
                    "date": date,
                    "total": total,
                    "sentiment": sentiment,
                    "top_stocks": top_list,
                }
                self._write_snapshot(cache_key, result)
                return ServiceResult.ok(data=result)
        except Exception as e:
            log_exception("ashare_tools", e)
        return ServiceResult.ok(
            data={"date": date, "total": 0, "sentiment": "未知", "note": "数据暂不可用"}
        )

    # ════════════════════════════════════════════
    #  人气热度
    # ════════════════════════════════════════════

    def get_hot_stocks(self) -> ServiceResult:
        """人气热度 - DB缓存(1h) → 东财API → 降级"""
        cache_key = "hot_stocks_latest"
        cached = self._read_snapshot(cache_key)
        if cached:
            return ServiceResult.ok(data=cached)

        try:
            import urllib.request

            url = (
                "https://push2.eastmoney.com/api/qt/clist/get?"
                "pn=1&pz=20&po=1&np=1&fltt=2&invt=2&fid=f3"
                "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
                "&fields=f2,f3,f4,f12,f14"
            )
            req = urllib.request.Request(  # noqa: S310
                url,
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"},
            )
            resp = urllib.request.urlopen(req, timeout=8)  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("data", {}).get("diff", [])
            result = [
                {
                    "code": i.get("f12", ""),
                    "name": i.get("f14", ""),
                    "price": i.get("f2", 0),
                    "change_pct": i.get("f3", 0),
                }
                for i in items[:20]
            ]
            self._write_snapshot(cache_key, result)
            return ServiceResult.ok(data={"stocks": result, "count": len(result)})
        except Exception as e:
            log_exception("ashare_data_tools", e, context="Operation failed")
            return ServiceResult.ok(data={"stocks": [], "count": 0, "note": "API不可用"})

    # ════════════════════════════════════════════
    # ════════════════════════════════════════════

    def _read_cache(self, category: str, stock_code: str, date: str):
        try:
            from shared.models._base import get_session
            from shared.models.market import MarketSnapshot

            key = f"{category}_{stock_code}_{date}"
            session = get_session(self.db_path)
            row = session.query(MarketSnapshot).filter_by(snapshot_type=key).first()
            session.close()
            if row and row.data_json:
                age = (datetime.now() - row.updated_at).total_seconds()
                if age < 86400:
                    return json.loads(row.data_json)
        except Exception as e:
            log_exception("ashare_tools", e)
        return None

    def _write_snapshot(self, key: str, data: dict | list):
        try:
            from shared.models._base import get_session
            from shared.models.market import MarketSnapshot

            session = get_session(self.db_path)
            row = session.query(MarketSnapshot).filter_by(snapshot_type=key).first()
            if row:
                row.data_json = json.dumps(data, ensure_ascii=False, default=str)
                row.updated_at = datetime.now()
            else:
                session.add(
                    MarketSnapshot(
                        snapshot_type=key,
                        data_json=json.dumps(data, ensure_ascii=False, default=str),
                        updated_at=datetime.now(),
                    )
                )
            session.commit()
            session.close()
        except Exception as e:
            log_exception("ashare_tools", e)

    def _read_snapshot(self, key: str):
        try:
            from shared.models._base import get_session
            from shared.models.market import MarketSnapshot

            session = get_session(self.db_path)
            row = session.query(MarketSnapshot).filter_by(snapshot_type=key).first()
            session.close()
            if row and row.data_json:
                age = (datetime.now() - row.updated_at).total_seconds()
                if age < 86400:
                    return json.loads(row.data_json)
        except Exception as e:
            log_exception("ashare_tools", e)
        return None

