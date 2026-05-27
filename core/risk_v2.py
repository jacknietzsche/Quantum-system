"""
core/risk_v2.py — 量化策略风控增强模块（V2）
=============================================
基于研报和quantstats报告分析优化：

优化方向：
1. 动态仓位管理（基于波动率和Kelly准则）
2. 改进的止损/止盈机制（分阶段止损+移动止盈）
3. 尾部风险控制（VaR/CVaR）
4. 收益分布优化（修正负偏态）

参考：
- "学海拾珠"系列之九十七：基于回撤控制的最优投资组合策略
- 量化交易策略夏普比率提升与最大回撤控制实战指南
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

__all__ = [
    "RiskV2Config",
    "DynamicPositionManager",
    "EnhancedStopLossManager",
    "TailRiskManager",
    "DrawdownController",
    "RiskV2Manager",
    "create_risk_v2_manager",
]


@dataclass
class RiskV2Config:
    """V2风控配置"""
    # 仓位管理
    use_kelly_sizing: bool = True           # 使用Kelly准则动态调整仓位
    kelly_fraction: float = 0.25            # Kelly仓位比例（避免过度杠杆）
    max_position_pct: float = 0.20          # 单只股票最大仓位
    min_cash_reserve: float = 0.10          # 最低现金储备
    
    # 止损机制
    use_trailing_stop: bool = True          # 移动止损
    initial_stop_loss: float = 0.05         # 初始止损线（5%）
    trailing_stop_pct: float = 0.03         # 移动止损幅度（3%）
    time_based_stop_days: int = 20          # 时间止损（20天不涨）
    
    # 止盈机制
    use_take_profit: bool = True            # 启用止盈
    take_profit_levels: List[Tuple[float, float]] = None  # [(盈利比例, 止盈比例), ...]
    
    # 尾部风险控制
    use_var_control: bool = True            # 使用VaR控制
    var_confidence: float = 0.95            # VaR置信度
    var_max_exposure: float = 0.30          # VaR超限时最大敞口
    use_cvar_weighting: bool = True         # CVaR加权
    
    # 回撤控制
    drawdown_stop_levels: List[Tuple[float, float]] = None  # [(回撤比例, 减仓比例), ...]
    max_drawdown_limit: float = 0.08        # 最大允许回撤（8%）
    
    # 波动率控制
    target_volatility: float = 0.15         # 目标年化波动率（15%）
    vol_adjustment_enabled: bool = True     # 波动率调整
    
    def __post_init__(self):
        if self.take_profit_levels is None:
            self.take_profit_levels = [
                (0.10, 0.30),   # 盈利10%时，卖出30%仓位
                (0.20, 0.50),   # 盈利20%时，卖出50%仓位
                (0.30, 0.70),   # 盈利30%时，卖出70%仓位
            ]
        if self.drawdown_stop_levels is None:
            self.drawdown_stop_levels = [
                (0.03, 0.20),   # 回撤3%，减仓20%
                (0.05, 0.40),   # 回撤5%，减仓40%
                (0.08, 0.70),   # 回撤8%，减仓70%
            ]


class DynamicPositionManager:
    """动态仓位管理器"""
    
    def __init__(self, config: RiskV2Config):
        self.cfg = config
        self._position_history: List[Dict] = []
        
    def calculate_kelly_position(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        """
        基于Kelly准则计算仓位
        
        Kelly % = W - (1-W)/R
        其中 W = 胜率，R = 盈亏比
        
        使用fractional Kelly（0.25）避免过度杠杆
        """
        if win_rate <= 0 or win_rate >= 1:
            return self.cfg.max_position_pct * 0.5
            
        win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 1.0
        
        # Kelly公式
        kelly_pct = win_rate - (1 - win_rate) / win_loss_ratio
        
        # 限制在合理范围
        kelly_pct = max(0, min(kelly_pct, self.cfg.max_position_pct))
        
        # 使用fractional Kelly
        fractional_kelly = kelly_pct * self.cfg.kelly_fraction
        
        return fractional_kelly
    
    def calculate_volatility_adjusted_position(self, historical_returns: List[float]) -> float:
        """
        基于历史波动率调整仓位
        
        目标：将组合波动率维持在目标水平
        """
        if len(historical_returns) < 20:
            return self.cfg.max_position_pct * 0.5
            
        returns = np.array(historical_returns[-60:])  # 最近60天
        current_vol = returns.std() * np.sqrt(252)  # 年化波动率
        
        if current_vol <= 0:
            return self.cfg.max_position_pct * 0.5
        
        # 波动率调整系数
        vol_ratio = self.cfg.target_volatility / current_vol
        vol_ratio = np.clip(vol_ratio, 0.3, 1.5)  # 限制调整范围
        
        # 计算仓位
        position = self.cfg.max_position_pct * vol_ratio
        
        return np.clip(position, 0.02, self.cfg.max_position_pct)
    
    def get_recommended_position(
        self, 
        symbol: str,
        historical_returns: List[float],
        win_rate: float = 0.55,
        avg_win: float = 0.01,
        avg_loss: float = -0.01
    ) -> float:
        """综合计算推荐仓位"""
        
        # Kelly仓位
        kelly_pos = self.calculate_kelly_position(win_rate, avg_win, avg_loss)
        
        # 波动率调整仓位
        vol_pos = self.calculate_volatility_adjusted_position(historical_returns)
        
        # 取两者较小值，确保风险可控
        recommended = min(kelly_pos, vol_pos)
        
        # 确保不低于最低仓位
        recommended = max(recommended, 0.02)
        
        return recommended


class EnhancedStopLossManager:
    """增强型止损止盈管理器"""
    
    def __init__(self, config: RiskV2Config):
        self.cfg = config
        self._positions: Dict[str, Dict] = {}  # {symbol: {...}}
        
    def init_position(self, symbol: str, entry_price: float, shares: int):
        """初始化持仓"""
        self._positions[symbol] = {
            'entry_price': entry_price,
            'shares': shares,
            'entry_date': pd.Timestamp.now(),
            'highest_price': entry_price,
            'stop_loss_price': entry_price * (1 - self.cfg.initial_stop_loss),
            'trailing_stop_price': entry_price * (1 - self.cfg.trailing_stop_pct),
            'profit_levels_triggered': [],
        }
    
    def check_stop_loss(self, symbol: str, current_price: float) -> Dict:
        """
        检查是否触发止损
        
        Returns:
            action: "none" / "sell_all" / "sell_partial"
            shares: 需要卖出的数量
            reason: 原因说明
        """
        if symbol not in self._positions:
            return {"action": "none", "shares": 0, "reason": "无持仓"}
        
        pos = self._positions[symbol]
        entry_price = pos['entry_price']
        
        # 计算当前盈亏
        pnl_pct = (current_price - entry_price) / entry_price
        
        # 更新最高价（用于移动止损）
        if current_price > pos['highest_price']:
            pos['highest_price'] = current_price
            # 移动止损线上移
            pos['trailing_stop_price'] = current_price * (1 - self.cfg.trailing_stop_pct)
        
        # 1. 检查移动止损
        if current_price <= pos['trailing_stop_price']:
            return {
                "action": "sell_all",
                "shares": pos['shares'],
                "reason": f"触发移动止损，当前价格{current_price:.2f}，止损线{pos['trailing_stop_price']:.2f}"
            }
        
        # 2. 检查固定止损（入场价下跌超过initial_stop_loss%）
        if pnl_pct <= -self.cfg.initial_stop_loss:
            return {
                "action": "sell_all",
                "shares": pos['shares'],
                "reason": f"触发固定止损，亏损{pnl_pct:.1%}"
            }
        
        # 3. 检查时间止损（20天不涨）
        days_held = (pd.Timestamp.now() - pos['entry_date']).days
        if days_held >= self.cfg.time_based_stop_days and pnl_pct < 0:
            return {
                "action": "sell_all",
                "shares": pos['shares'],
                "reason": f"时间止损：持有{days_held}天未盈利"
            }
        
        return {"action": "none", "shares": 0, "reason": "未触发"}
    
    def check_take_profit(self, symbol: str, current_price: float) -> Dict:
        """
        检查是否触发止盈
        
        分阶段止盈：盈利10%卖30%，盈利20%卖50%，盈利30%卖70%
        """
        if symbol not in self._positions or not self.cfg.use_take_profit:
            return {"action": "none", "shares": 0, "reason": "无止盈条件"}
        
        pos = self._positions[symbol]
        entry_price = pos['entry_price']
        
        # 计算当前盈亏
        pnl_pct = (current_price - entry_price) / entry_price
        
        # 检查各止盈级别
        shares_to_sell = 0
        total_shares = pos['shares']
        
        for profit_threshold, sell_pct in self.cfg.take_profit_levels:
            if pnl_pct >= profit_threshold:
                # 检查是否已触发过
                level_key = f"tp_{profit_threshold}"
                if level_key not in pos['profit_levels_triggered']:
                    # 计算需要卖出的数量
                    level_shares = int(total_shares * sell_pct)
                    shares_to_sell += level_shares
                    pos['profit_levels_triggered'].append(level_key)
        
        if shares_to_sell > 0:
            return {
                "action": "sell_partial",
                "shares": shares_to_sell,
                "reason": f"触发止盈，盈利{pnl_pct:.1%}，卖出{shares_to_sell}股"
            }
        
        return {"action": "none", "shares": 0, "reason": "未触发"}
    
    def close_position(self, symbol: str):
        """平仓"""
        if symbol in self._positions:
            del self._positions[symbol]


class TailRiskManager:
    """尾部风险管理器 - VaR/CVaR控制"""
    
    def __init__(self, config: RiskV2Config):
        self.cfg = config
        self._return_history: List[float] = []
        
    def update_returns(self, returns: List[float]):
        """更新收益历史"""
        self._return_history.extend(returns)
        # 保持最近252天数据
        if len(self._return_history) > 252:
            self._return_history = self._return_history[-252:]
    
    def calculate_var(self, confidence: float = 0.95) -> float:
        """
        计算VaR（Value at Risk）
        
        使用历史模拟法
        """
        if len(self._return_history) < 30:
            return 0.0
            
        returns = np.array(self._return_history)
        
        # VaR = -quantile(returns, 1 - confidence)
        var = -np.percentile(returns, (1 - confidence) * 100)
        
        return var
    
    def calculate_cvar(self, confidence: float = 0.95) -> float:
        """
        计算CVaR（Conditional VaR / Expected Shortfall）
        
        CVaR = E[loss | loss > VaR]
        """
        if len(self._return_history) < 30:
            return 0.0
            
        returns = np.array(self._return_history)
        var = self.calculate_var(confidence)
        
        # CVaR = mean of losses beyond VaR
        tail_losses = returns[returns <= -var]
        
        if len(tail_losses) == 0:
            return 0.0
            
        cvar = -np.mean(tail_losses)
        
        return cvar
    
    def get_risk_adjusted_exposure(self) -> float:
        """
        基于VaR/CVaR计算风险调整后的敞口
        
        Returns:
            exposure: 建议的仓位比例（0-1）
        """
        if not self.cfg.use_var_control or len(self._return_history) < 30:
            return 1.0  # 满仓
            
        var_95 = self.calculate_var(0.95)
        cvar_95 = self.calculate_cvar(0.95)
        
        # 如果VaR超过阈值，降低仓位
        if var_95 > 0.05:  # 单日VaR超过5%
            exposure = self.cfg.var_max_exposure
            logger.warning(f"VaR({self.cfg.var_confidence:.0%})={var_95:.2%}, 降低仓位至{exposure:.0%}")
            return exposure
        
        # 基于CVaR进一步调整
        if self.cfg.use_cvar_weighting and cvar_95 > 0.08:
            # CVaR过高，降低仓位
            cvar_adjustment = min(1.0, 0.08 / cvar_95)
            exposure = max(self.cfg.var_max_exposure, cvar_adjustment)
            logger.info(f"CVaR={cvar_95:.2%}, 调整仓位{exposure:.0%}")
            return exposure
        
        return 1.0  # 正常仓位


class DrawdownController:
    """回撤控制器"""
    
    def __init__(self, config: RiskV2Config):
        self.cfg = config
        self._peak_value: float = 0.0
        self._current_value: float = 0.0
        
    def update_value(self, value: float):
        """更新组合价值"""
        self._current_value = value
        if value > self._peak_value:
            self._peak_value = value
    
    def get_current_drawdown(self) -> float:
        """获取当前回撤"""
        if self._peak_value <= 0:
            return 0.0
        return (self._peak_value - self._current_value) / self._peak_value
    
    def check_drawdown_action(self) -> Dict:
        """
        检查回撤是否触发动作
        
        Returns:
            action: "none" / "reduce_position" / "close_all"
            reduction_pct: 需要减仓的比例
        """
        drawdown = self.get_current_drawdown()
        
        # 检查是否超过最大回撤限制
        if drawdown >= self.cfg.max_drawdown_limit:
            return {
                "action": "close_all",
                "reduction_pct": 1.0,
                "reason": f"回撤{drawdown:.1%}超过最大限制{self.cfg.max_drawdown_limit:.1%}，清仓"
            }
        
        # 检查各阶段减仓
        for dd_threshold, reduction_pct in self.cfg.drawdown_stop_levels:
            if drawdown >= dd_threshold:
                return {
                    "action": "reduce_position",
                    "reduction_pct": reduction_pct,
                    "reason": f"回撤{drawdown:.1%}超过{dd_threshold:.1%}，减仓{reduction_pct:.0%}"
                }
        
        return {"action": "none", "reduction_pct": 0, "reason": "正常"}


class RiskV2Manager:
    """V2综合风险管理器"""
    
    def __init__(self, config: Optional[RiskV2Config] = None):
        self.cfg = config or RiskV2Config()
        
        # 初始化各子模块
        self.position_manager = DynamicPositionManager(self.cfg)
        self.stop_loss_manager = EnhancedStopLossManager(self.cfg)
        self.tail_risk_manager = TailRiskManager(self.cfg)
        self.drawdown_controller = DrawdownController(self.cfg)
        
        # 组合收益历史
        self._portfolio_returns: List[float] = []
        
    def update_portfolio_value(self, value: float, daily_return: float):
        """更新组合状态"""
        self.drawdown_controller.update_value(value)
        if daily_return is not None:
            self._portfolio_returns.append(daily_return)
            self.tail_risk_manager.update_returns([daily_return])
    
    def get_position_recommendation(
        self, 
        symbol: str,
        win_rate: float = 0.55,
        avg_win: float = 0.01,
        avg_loss: float = -0.01
    ) -> float:
        """获取仓位建议"""
        # 风险调整后的敞口
        risk_exposure = self.tail_risk_manager.get_risk_adjusted_exposure()
        
        # 动态仓位
        dynamic_position = self.position_manager.get_recommended_position(
            symbol, 
            self._portfolio_returns,
            win_rate,
            avg_win,
            avg_loss
        )
        
        # 综合
        recommended = dynamic_position * risk_exposure
        
        return min(recommended, self.cfg.max_position_pct)
    
    def check_risk_signals(self, symbol: str, current_price: float) -> List[Dict]:
        """检查所有风险信号"""
        signals = []
        
        # 止损检查
        stop_signal = self.stop_loss_manager.check_stop_loss(symbol, current_price)
        if stop_signal["action"] != "none":
            signals.append(stop_signal)
        
        # 止盈检查
        profit_signal = self.stop_loss_manager.check_take_profit(symbol, current_price)
        if profit_signal["action"] != "none":
            signals.append(profit_signal)
        
        # 回撤检查
        dd_signal = self.drawdown_controller.check_drawdown_action()
        if dd_signal["action"] != "none":
            signals.append(dd_signal)
        
        return signals
    
    def get_risk_metrics(self) -> Dict:
        """获取当前风险指标"""
        return {
            "var_95": self.tail_risk_manager.calculate_var(0.95),
            "cvar_95": self.tail_risk_manager.calculate_cvar(0.95),
            "current_drawdown": self.drawdown_controller.get_current_drawdown(),
            "risk_exposure": self.tail_risk_manager.get_risk_adjusted_exposure(),
            "portfolio_volatility": self._calculate_portfolio_volatility(),
        }
    
    def _calculate_portfolio_volatility(self) -> float:
        """计算组合波动率"""
        if len(self._portfolio_returns) < 20:
            return 0.0
        returns = np.array(self._portfolio_returns[-60:])
        return returns.std() * np.sqrt(252)


def create_risk_v2_manager() -> RiskV2Manager:
    """创建V2风险管理器（便捷函数）"""
    return RiskV2Manager()