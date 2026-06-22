"""模拟持仓服务 — 自动跟踪系统推荐的交易。

持久化到SQLite，遵循A股交易规则:
- T+1: 当日买入次日可卖
- 100股整数倍
- 佣金: max(0.025%, ¥5)
- 印花税: 0.1%（卖出方）
- 过户费: 0.001%
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from core.config import Config

logger = logging.getLogger("ashare-x.services.paper_portfolio")


class PaperPortfolio:
    """模拟持仓管理器。"""

    def __init__(self, db_path: str | None = None, config: Config | None = None):
        self.config = config or Config()
        if db_path is None:
            db_path = self.config.get("runtime.db_path", "runtime/investment.db")
        self.db_path = db_path
        self.initial_capital = self.config.get("portfolio.initial_capital", 100000)
        self.lot_size = self.config.get("portfolio.lot_size", 100)
        self.commission_rate = self.config.get("portfolio.commission_rate", 0.00025)
        self.min_commission = self.config.get("portfolio.min_commission", 5)
        self.stamp_tax_rate = self.config.get("portfolio.stamp_tax_rate", 0.001)
        self.transfer_fee_rate = self.config.get("portfolio.transfer_fee_rate", 0.00001)
        self._ensure_account()

    def _get_conn(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.db_path)

    def _ensure_account(self):
        """确保表和账户记录存在。"""
        conn = self._get_conn()
        # 自建表（不依赖 DatabaseFirstDataBus 已初始化）
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
        conn.execute(
            "INSERT OR IGNORE INTO paper_account (id, initial_capital, cash) "
            "VALUES (1, ?, ?)",
            (self.initial_capital, self.initial_capital),
        )
        conn.commit()
        conn.close()

    def _round_lot(self, shares: int) -> int:
        """取100股整数倍。"""
        return int((shares // self.lot_size) * self.lot_size)

    def _calc_buy_cost(self, price: float, shares: int) -> dict:
        """计算买入总成本（含手续费）。"""
        amount = price * shares
        commission = max(amount * self.commission_rate, self.min_commission)
        transfer_fee = amount * self.transfer_fee_rate
        total = amount + commission + transfer_fee
        return {
            "amount": round(amount, 2),
            "commission": round(commission, 2),
            "stamp_tax": 0.0,
            "transfer_fee": round(transfer_fee, 2),
            "total": round(total, 2),
        }

    def _calc_sell_revenue(self, price: float, shares: int) -> dict:
        """计算卖出净收入（扣除手续费）。"""
        amount = price * shares
        commission = max(amount * self.commission_rate, self.min_commission)
        stamp_tax = amount * self.stamp_tax_rate
        transfer_fee = amount * self.transfer_fee_rate
        net = amount - commission - stamp_tax - transfer_fee
        return {
            "amount": round(amount, 2),
            "commission": round(commission, 2),
            "stamp_tax": round(stamp_tax, 2),
            "transfer_fee": round(transfer_fee, 2),
            "net": round(net, 2),
        }

    def buy(self, code: str, name: str, price: float, shares: int,
            reasoning: str = "") -> dict:
        """初次买入。返回交易记录。"""
        shares = self._round_lot(shares)
        if shares <= 0:
            return {"ok": False, "error": "股数不足100股"}

        costs = self._calc_buy_cost(price, shares)
        cash = self._get_cash()
        if costs["total"] > cash:
            return {"ok": False, "error": f"资金不足: 需要¥{costs['total']:.2f}, 可用¥{cash:.2f}"}

        conn = self._get_conn()
        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now().isoformat()

        # 扣减现金
        conn.execute(
            "UPDATE paper_account SET cash = cash - ?, updated_at = ? WHERE id = 1",
            (costs["total"], now),
        )
        # 写入持仓（T+1标记全部为冻结）
        conn.execute(
            "INSERT OR REPLACE INTO paper_holdings "
            "(stock_code, stock_name, shares, avg_cost, "
            "entry_date, last_update, t1_blocked_shares) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (code, name, shares, price, today, now, shares),
        )
        # 记录交易
        conn.execute(
            "INSERT INTO paper_trades "
            "(stock_code, stock_name, action, shares, price, amount, commission, stamp_tax, "
            "trade_date, reasoning) VALUES (?, ?, 'BUY', ?, ?, ?, ?, 0, ?, ?)",
            (code, name, shares, price, costs["amount"], costs["commission"],
             today, reasoning),
        )
        conn.commit()
        conn.close()

        logger.info(
            "买入 %s %s: %d股 @¥%.2f, 总成本¥%.2f",
            code, name, shares, price, costs["total"],
        )
        return {"ok": True, "action": "BUY", "code": code, "shares": shares,
                "price": price, "total_cost": costs["total"]}

    def add(self, code: str, name: str, price: float, shares: int,
            reasoning: str = "") -> dict:
        """加仓。更新平均成本。"""
        shares = self._round_lot(shares)
        if shares <= 0:
            return {"ok": False, "error": "股数不足100股"}

        costs = self._calc_buy_cost(price, shares)
        cash = self._get_cash()
        if costs["total"] > cash:
            return {"ok": False, "error": f"资金不足: 需要¥{costs['total']:.2f}, 可用¥{cash:.2f}"}

        conn = self._get_conn()
        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now().isoformat()

        # 查询现有持仓
        row = conn.execute(
            "SELECT shares, avg_cost, t1_blocked_shares FROM paper_holdings WHERE stock_code = ?",
            (code,),
        ).fetchone()
        if not row:
            conn.close()
            return self.buy(code, name, price, shares, reasoning)

        old_shares, old_cost, old_t1 = row
        # 加权平均成本
        new_shares = old_shares + shares
        new_avg_cost = (old_shares * old_cost + shares * price) / new_shares

        # 扣减现金
        conn.execute(
            "UPDATE paper_account SET cash = cash - ?, updated_at = ? WHERE id = 1",
            (costs["total"], now),
        )
        # 更新持仓（新买入部分T+1冻结）
        conn.execute(
            "UPDATE paper_holdings SET shares = ?, avg_cost = ?, last_update = ?, "
            "t1_blocked_shares = ? WHERE stock_code = ?",
            (new_shares, new_avg_cost, now, old_t1 + shares, code),
        )
        # 记录交易
        conn.execute(
            "INSERT INTO paper_trades "
            "(stock_code, stock_name, action, shares, price, amount, commission, stamp_tax, "
            "trade_date, reasoning) VALUES (?, ?, 'ADD', ?, ?, ?, ?, 0, ?, ?)",
            (code, name, shares, price, costs["amount"], costs["commission"],
             today, reasoning),
        )
        conn.commit()
        conn.close()

        logger.info(
            "加仓 %s %s: +%d股 @¥%.2f, 新均价¥%.2f",
            code, name, shares, price, new_avg_cost,
        )
        return {"ok": True, "action": "ADD", "code": code, "shares": shares,
                "price": price, "new_avg_cost": round(new_avg_cost, 2),
                "total_shares": new_shares}

    def reduce(self, code: str, price: float, shares: int,
               reasoning: str = "") -> dict:
        """减仓。部分卖出。"""
        shares = self._round_lot(shares)
        if shares <= 0:
            return {"ok": False, "error": "股数不足100股"}

        conn = self._get_conn()
        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now().isoformat()

        row = conn.execute(
            "SELECT shares, stock_name, avg_cost, t1_blocked_shares "
            "FROM paper_holdings WHERE stock_code = ?",
            (code,),
        ).fetchone()
        if not row:
            conn.close()
            return {"ok": False, "error": f"未持有 {code}"}

        holding_shares, stock_name, avg_cost, t1_blocked = row
        # T+1检查: 可卖 = 总持仓 - 今日冻结
        sellable = holding_shares - t1_blocked
        if shares > sellable:
            conn.close()
            return {"ok": False, "error": f"可卖不足: T+1限制, 可卖{sellable}股"}

        revenue = self._calc_sell_revenue(price, shares)
        new_shares = holding_shares - shares

        # 增加现金
        conn.execute(
            "UPDATE paper_account SET cash = cash + ?, updated_at = ? WHERE id = 1",
            (revenue["net"], now),
        )
        if new_shares > 0:
            conn.execute(
                "UPDATE paper_holdings SET shares = ?, last_update = ? WHERE stock_code = ?",
                (new_shares, now, code),
            )
        else:
            conn.execute("DELETE FROM paper_holdings WHERE stock_code = ?", (code,))

        # 记录交易
        profit = (
            (price - avg_cost) * shares
            - revenue["commission"]
            - revenue["stamp_tax"]
            - revenue["transfer_fee"]
        )
        conn.execute(
            "INSERT INTO paper_trades "
            "(stock_code, stock_name, action, shares, price, amount, commission, stamp_tax, "
            "trade_date, reasoning) VALUES (?, ?, 'REDUCE', ?, ?, ?, ?, ?, ?, ?)",
            (code, stock_name, shares, price, revenue["amount"], revenue["commission"],
             revenue["stamp_tax"], today, reasoning),
        )
        conn.commit()
        conn.close()

        logger.info("减仓 %s %s: -%d股 @¥%.2f, 剩余%d股, 盈亏¥%.2f",
                    code, stock_name, shares, price, new_shares, profit)
        return {"ok": True, "action": "REDUCE", "code": code, "shares": shares,
                "price": price, "net_revenue": revenue["net"],
                "remaining_shares": new_shares, "profit": round(profit, 2)}

    def clear(self, code: str, price: float, reasoning: str = "") -> dict:
        """清仓。全部卖出。"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT shares, stock_name, avg_cost, t1_blocked_shares "
            "FROM paper_holdings WHERE stock_code = ?",
            (code,),
        ).fetchone()
        conn.close()
        if not row:
            return {"ok": False, "error": f"未持有 {code}"}

        shares, _stock_name, _avg_cost, t1_blocked = row
        # T+1检查
        sellable = shares - t1_blocked
        if sellable <= 0:
            return {"ok": False, "error": "T+1限制: 今日买入不可卖"}

        # 卖出全部可卖部分
        return self.reduce(code, price, sellable, reasoning or "清仓")

    def get_holdings(self) -> list[dict]:
        """获取当前持仓（含实时价格、盈亏）。"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT stock_code, stock_name, shares, avg_cost, entry_date, t1_blocked_shares "
            "FROM paper_holdings ORDER BY stock_code"
        ).fetchall()
        conn.close()

        holdings = []
        for r in rows:
            code, name, shares, avg_cost, entry_date, t1_blocked = r
            # 从DataBus获取最新价格
            current_price = self._fetch_price(code)
            market_value = shares * (current_price or avg_cost)
            cost_value = shares * avg_cost
            pnl = market_value - cost_value
            pnl_pct = (pnl / cost_value * 100) if cost_value > 0 else 0

            holdings.append({
                "stock_code": code,
                "stock_name": name,
                "shares": shares,
                "avg_cost": round(avg_cost, 2),
                "current_price": current_price,
                "market_value": round(market_value, 2),
                "cost_value": round(cost_value, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "entry_date": entry_date,
                "t1_blocked": t1_blocked,
                "sellable": shares - t1_blocked,
            })
        return holdings

    def get_account(self) -> dict:
        """获取账户信息。"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT initial_capital, cash FROM paper_account WHERE id = 1"
        ).fetchone()
        conn.close()

        if not row:
            return {"initial_capital": self.initial_capital, "cash": self.initial_capital,
                    "holdings_value": 0, "total_assets": self.initial_capital,
                    "pnl": 0, "pnl_pct": 0, "holding_count": 0}

        initial, cash = row
        holdings = self.get_holdings()
        holdings_value = sum(h["market_value"] for h in holdings)
        total_assets = cash + holdings_value
        pnl = total_assets - initial
        pnl_pct = (pnl / initial * 100) if initial > 0 else 0

        return {
            "initial_capital": round(initial, 2),
            "cash": round(cash, 2),
            "holdings_value": round(holdings_value, 2),
            "total_assets": round(total_assets, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "holding_count": len(holdings),
        }

    def get_trade_history(self, limit: int = 50) -> list[dict]:
        """获取交易历史。"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT stock_code, stock_name, action, shares, price, amount, "
            "commission, stamp_tax, trade_date, reasoning, created_at "
            "FROM paper_trades ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [
            {
                "stock_code": r[0], "stock_name": r[1], "action": r[2],
                "shares": r[3], "price": r[4], "amount": r[5],
                "commission": r[6], "stamp_tax": r[7], "trade_date": r[8],
                "reasoning": r[9], "created_at": r[10],
            }
            for r in rows
        ]

    def update_prices(self):
        """更新持仓的T+1冻结状态（每日开盘前调用，清除前日冻结）。"""
        conn = self._get_conn()
        now = datetime.now().isoformat()
        conn.execute(
            "UPDATE paper_holdings SET t1_blocked_shares = 0, last_update = ?",
            (now,),
        )
        conn.commit()
        conn.close()
        logger.info("已清除T+1冻结标记")

    def _get_cash(self) -> float:
        conn = self._get_conn()
        row = conn.execute("SELECT cash FROM paper_account WHERE id = 1").fetchone()
        conn.close()
        return float(row[0]) if row else float(self.initial_capital)

    def _fetch_price(self, code: str) -> float | None:
        """从DataBus获取最新价格。"""
        try:
            from providers.data_bus import DatabaseFirstDataBus

            bus = DatabaseFirstDataBus(self.db_path)
            info = bus.get_stock_info(code)
            if info:
                price = info.get("latest_price")
                if price and price > 0:
                    return float(price)
        except Exception as e:
            logger.debug("获取价格失败 %s: %s", code, e)
        return None
