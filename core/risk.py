"""
core.risk — 风控与持仓模块
============================

提供: RiskChecker / StopLossManager / PositionManager
"""

import os
import logging
import warnings as warnings_module
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

import pandas as pd
import numpy as np

from core.config import QuantConfig, RiskConfig
from core.data import UnifiedDataFetcher

logger = logging.getLogger(__name__)

__all__ = [
    "RiskChecker",
    "StopLossManager",
    "PositionManager",
]


class RiskChecker:
    """风控检查器 — 停牌/涨跌停/异常波动/仓位集中度"""

    def __init__(self, config: Optional[RiskConfig] = None):
        self.cfg = config or RiskConfig()
        self._portfolio_value_history: List[float] = []
        self._peak_value: float = 0.0

    # ===== V15 改进：动态止损+回撤控制 =====
    def check_drawdown_stop(self, current_value: float, prev_value: float) -> Dict:
        """
        检查是否触发回撤止损

        Returns:
            action: "none" / "reduce_position" / "close_all"
            reduction_pct: 需要减仓的比例
        """
        if not self.cfg.stop_loss_enabled:
            return {"action": "none", "reduction_pct": 0, "reason": "未启用"}

        # 更新峰值
        if current_value > self._peak_value:
            self._peak_value = current_value

        # 计算回撤
        if self._peak_value <= 0:
            return {"action": "none", "reduction_pct": 0, "reason": "无历史数据"}

        drawdown = (self._peak_value - current_value) / self._peak_value

        if drawdown >= self.cfg.stop_loss_heavy:
            return {
                "action": "close_all",
                "reduction_pct": 1.0,
                "reason": f"回撤{drawdown:.1%}超过{self.cfg.stop_loss_heavy:.1%}，清仓"
            }
        elif drawdown >= self.cfg.stop_loss_pct:
            return {
                "action": "reduce_position",
                "reduction_pct": self.cfg.stop_loss_position_pct,
                "reason": f"回撤{drawdown:.1%}超过{self.cfg.stop_loss_pct:.1%}，减仓{self.cfg.stop_loss_position_pct:.0%}"
            }

        return {"action": "none", "reduction_pct": 0, "reason": "未触发"}

    # ===== V15 改进：波动率约束 =====
    def check_volatility_limit(self, portfolio_returns: List[float]) -> Dict:
        """
        检查组合波动率是否超限

        Returns:
            action: "none" / "reduce_position"
            cash_pct: 需要提升的现金比例
        """
        if not self.cfg.volatility_limit_enabled or len(portfolio_returns) < 20:
            return {"action": "none", "cash_pct": 0, "reason": "未启用或数据不足"}

        # 计算年化波动率
        returns = np.array(portfolio_returns[-60:])  # 最近60天
        daily_vol = returns.std()
        annual_vol = daily_vol * np.sqrt(252)  # 年化

        if annual_vol > self.cfg.max_volatility:
            return {
                "action": "reduce_position",
                "cash_pct": self.cfg.volatility_reduction_pct,
                "reason": f"年化波动率{annual_vol:.1%}超过{self.cfg.max_volatility:.1%}，提升现金至{self.cfg.volatility_reduction_pct:.0%}"
            }

        return {"action": "none", "cash_pct": 0, "reason": "波动率正常"}

    # ===== V15 改进：行业分散化 =====
    def check_sector_diversification(self, portfolio: Dict, sector_map: Dict[str, str], total_value: float) -> Dict:
        """
        检查行业分散度

        Args:
            portfolio: {symbol: {'value': float, 'shares': int}}
            sector_map: {symbol: sector_name}
            total_value: 总市值

        Returns:
            action: "none" / "rebalance"
            overweight_sectors: 需要减仓的行业列表
        """
        if not self.cfg.sector_diversification_enabled or not portfolio:
            return {"action": "none", "overweight_sectors": [], "reason": "未启用"}

        # 计算各行业权重
        sector_weights: Dict[str, float] = {}
        for symbol, pos in portfolio.items():
            sector = sector_map.get(symbol, "未知")
            weight = pos.get('value', 0) / total_value if total_value > 0 else 0
            sector_weights[sector] = sector_weights.get(sector, 0) + weight

        # 检查超限行业
        overweight = [s for s, w in sector_weights.items() if w > self.cfg.max_sector_weight]

        if overweight:
            return {
                "action": "rebalance",
                "overweight_sectors": overweight,
                "reason": f"行业{overweight}超过{self.cfg.max_sector_weight:.0%}限制"
            }

        return {"action": "none", "overweight_sectors": [], "reason": "行业分散度正常"}

    def check_stock(self, symbol: str, df: pd.DataFrame) -> Dict:
        stock_warnings: List[str] = []
        blocks: List[str] = []
        if df.empty or len(df) < 2:
            blocks.append("数据不足")
            return {"passed": False, "warnings": stock_warnings, "blocks": blocks}

        last_date = df.index[-1] if isinstance(df.index, pd.DatetimeIndex) else pd.Timestamp.now()
        days_since = (pd.Timestamp.now() - last_date).days
        if days_since > self.cfg.max_stale_days:
            blocks.append(f"疑似停牌（{days_since}天未更新）")

        if 'pct_change' in df.columns:
            chg = df['pct_change'].iloc[-1]
            if abs(chg) > 15:
                stock_warnings.append(f"单日涨跌幅 {chg:.1f}% 超过15%")

        if 'volume' in df.columns and len(df) >= 20:
            avg = df['volume'].tail(20).mean()
            if avg > 0 and df['volume'].iloc[-1] / avg > 5:
                stock_warnings.append(f"成交量异常（{df['volume'].iloc[-1]/avg:.1f}x）")

        return {"passed": len(blocks) == 0, "warnings": stock_warnings, "blocks": blocks}

    def check_portfolio(self, portfolio: Dict, total_value: float) -> Dict:
        portfolio_warnings: List[str] = []
        for code, pos in portfolio.items():
            w = pos.get('value', 0) / total_value if total_value > 0 else 0
            if w > 0.15:
                portfolio_warnings.append(f"{code} 仓位 {w:.1%} 超过15%")
        sv = sum(p.get('value', 0) for p in portfolio.values())
        pr = sv / total_value if total_value > 0 else 0
        if pr > 0.90:
            portfolio_warnings.append(f"总仓位 {pr:.1%} 过高")
        return {"passed": len([w for w in portfolio_warnings if '过高' in w]) == 0,
                "warnings": portfolio_warnings, "position_ratio": pr}


class StopLossManager:
    """止损止盈管理器"""

    def __init__(self, stop_loss: float = -0.08, take_profit: float = 0.20, trailing: float = -0.06):
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.trailing = trailing
        self._max_prices: Dict[str, float] = {}

    def check(self, symbol: str, current_price: float, cost_price: float) -> Dict:
        if cost_price <= 0:
            return {"action": "hold", "reason": "成本价异常", "pnl_pct": 0}
        pnl = (current_price - cost_price) / cost_price
        self._max_prices[symbol] = max(self._max_prices.get(symbol, 0), current_price)
        if pnl <= self.stop_loss:
            return {"action": "stop_loss", "reason": f"止损（{pnl:.1%}）", "pnl_pct": pnl}
        if pnl >= self.take_profit:
            return {"action": "take_profit", "reason": f"止盈（{pnl:.1%}）", "pnl_pct": pnl}
        trail = (current_price - self._max_prices[symbol]) / self._max_prices[symbol]
        if trail <= self.trailing:
            return {"action": "stop_loss", "reason": f"移动止损（回撤{trail:.1%}）", "pnl_pct": pnl}
        return {"action": "hold", "reason": "未触发", "pnl_pct": pnl}

    def check_by_score(self, symbol: str, current_score: float, prev_score: float, drop: float = 0.05) -> Dict:
        d = prev_score - current_score
        if d >= drop and prev_score > 0:
            return {"action": "stop_loss", "reason": f"评分下降（{prev_score:.3f}→{current_score:.3f}）", "pnl_pct": 0}
        return {"action": "hold", "reason": "未触发", "pnl_pct": 0}

    def clear(self, symbol: str) -> None:
        self._max_prices.pop(symbol, None)


class PositionManager:
    """持仓管理器 — HDF5 存储"""

    def __init__(
        self,
        config: Optional[QuantConfig] = None,
        data_fetcher: Optional[UnifiedDataFetcher] = None,
        strategy: Optional[object] = None
    ):
        self.cfg = config or QuantConfig()
        self.fetcher = data_fetcher or UnifiedDataFetcher(self.cfg.data)
        self.strategy = strategy
        self._h5 = str(Path(self.cfg.report.portfolio_report_dir).parent / "portfolio.h5")
        Path(self._h5).parent.mkdir(parents=True, exist_ok=True)
        if not os.path.exists(self._h5):
            with pd.HDFStore(self._h5, mode='w') as s:
                s.put('snapshots', pd.DataFrame(columns=[
                    'date','code','name','shares','cost_price','current_price','market_value','pnl','pnl_pct'
                ]))
                s.put('trades', pd.DataFrame(columns=[
                    'date','code','name','action','price','shares','amount','reason'
                ]))
        logger.info(f"PositionManager 初始化完成")

    def _read(self, key: str) -> pd.DataFrame:
        try:
            with pd.HDFStore(self._h5, 'r') as s:
                return s[key] if key in s else pd.DataFrame()
        except Exception as e:
            logger.debug("HDF5 read failed: %s", e)
            return pd.DataFrame()

    def _write(self, key: str, df: pd.DataFrame) -> None:
        try:
            with pd.HDFStore(self._h5, 'r+') as s:
                s.put(key, df, format='table', data_columns=True)
        except Exception as e: logger.error("HDF5写入失败: %s", e)

    def get_current_holdings(self, as_of: Optional[str] = None) -> pd.DataFrame:
        df = self._read('snapshots')
        if df.empty: return df
        if as_of: df = df[df['date'] == as_of]
        if df.empty: return df
        return df[df['date'] == df['date'].max()]

    def get_trade_history(self, start: Optional[str] = None) -> pd.DataFrame:
        df = self._read('trades')
        if df.empty: return df
        if start: df = df[df['date'] >= start]
        return df.sort_values('date').reset_index(drop=True)

    def get_portfolio_value(self) -> float:
        h = self.get_current_holdings()
        if h.empty: return self.cfg.portfolio.initial_cash
        t = self._read('trades')
        buy = t[t['action']=='buy']['amount'].sum()
        sell = t[t['action']=='sell']['amount'].sum()
        return h['market_value'].sum() + self.cfg.portfolio.initial_cash - buy + sell

    def run_daily_rebalance(self, date_str: str) -> Dict:
        if not self.strategy:
            raise ValueError("未设置策略")
        stock_list = self.strategy.get_daily_stock_list(date_str)
        if not stock_list:
            return {"status": "no_signals", "date": date_str}

        name_map = self.strategy.get_name_map(date_str) if hasattr(self.strategy, 'get_name_map') else {}
        reasons = self.strategy.get_reasons_map(date_str) if hasattr(self.strategy, 'get_reasons_map') else {}

        cur = self.get_current_holdings()
        held = set(cur['code'].tolist()) if not cur.empty else set()
        tv = self.get_portfolio_value()
        tgt = tv * self.cfg.portfolio.max_total_position / len(stock_list)

        trades = []
        for c in held - set(stock_list):
            r = cur[cur['code']==c]
            if r.empty: continue
            p = self._open_price(c, date_str)
            if p <= 0: continue
            trades.append({'date':date_str,'code':c,'name':name_map.get(c,c),'action':'sell',
                          'price':p,'shares':int(r['shares'].iloc[0]),'amount':int(r['shares'].iloc[0])*p,'reason':'调仓'})

        for c in set(stock_list) - held:
            p = self._open_price(c, date_str)
            if p <= 0: continue
            s = int(tgt/p/100)*100
            if s <= 0: continue
            trades.append({'date':date_str,'code':c,'name':name_map.get(c,c),'action':'buy',
                          'price':p,'shares':s,'amount':s*p,
                          'reason':reasons.get(c,{}).get('summary','选股入选')})

        if trades:
            self._write('trades', pd.concat([self._read('trades'), pd.DataFrame(trades)], ignore_index=True))

        rows = []
        for c in stock_list:
            p = self._open_price(c, date_str)
            th = self._read('trades')
            bt = th[(th['code']==c)&(th['action']=='buy')]
            cp = bt['price'].iloc[-1] if not bt.empty else p
            sh = next((t['shares'] for t in trades if t['code']==c and t['action']=='buy'), 0)
            rows.append({'date':date_str,'code':c,'name':name_map.get(c,c),'shares':sh,'cost_price':cp,
                        'current_price':p,'market_value':sh*p,'pnl':(p-cp)*sh,'pnl_pct':(p/cp-1) if cp>0 else 0})
        if rows:
            self._write('snapshots', pd.concat([self._read('snapshots'), pd.DataFrame(rows)], ignore_index=True))

        return {"status":"rebalanced","date":date_str,
                "bought":len([t for t in trades if t['action']=='buy']),
                "sold":len([t for t in trades if t['action']=='sell']),"trades":trades}

    def _open_price(self, code: str, date_str: str) -> float:
        try:
            df = self.fetcher.get_daily(code, days=5)
            if df.empty: return 0.0
            return float(df['open'].iloc[-1])
        except Exception as e:
            logger.debug("open price fetch failed: %s", e)
            return 0.0
