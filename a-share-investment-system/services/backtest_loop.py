"""回测循环 - 因子验证 + 滚动IC分析 + 性能报告"""

import math

import numpy as np
import pandas as pd

from services.base import BaseService, ServiceResult
from services.factor_farm import FACTOR_METHODS
from shared.logging import emit_log


class BanditAllocator:
    """Thompson采样分配器 - 决定'挖新因子'vs'优化组合'"""

    def __init__(self):
        self.new_factor_arm = {"alpha": 1.0, "beta": 1.0}
        self.optimize_arm = {"alpha": 1.0, "beta": 1.0}

    def select_action(self) -> str:
        """Thompson采样选择动作"""
        new_sample = np.random.beta(self.new_factor_arm["alpha"], self.new_factor_arm["beta"])
        opt_sample = np.random.beta(self.optimize_arm["alpha"], self.optimize_arm["beta"])
        return "new_factor" if new_sample > opt_sample else "optimize"

    def update(self, action: str, reward: float):
        """更新Beta分布参数(reward应在0-1之间)"""
        reward = max(0.0, min(1.0, reward))
        if action == "new_factor":
            self.new_factor_arm["alpha"] += reward
            self.new_factor_arm["beta"] += 1.0 - reward
        else:
            self.optimize_arm["alpha"] += reward
            self.optimize_arm["beta"] += 1.0 - reward

    def get_status(self) -> dict:
        return {
            "new_factor": {
                "alpha": round(self.new_factor_arm["alpha"], 1),
                "beta": round(self.new_factor_arm["beta"], 1),
                "expected": round(
                    self.new_factor_arm["alpha"]
                    / (self.new_factor_arm["alpha"] + self.new_factor_arm["beta"]),
                    3,
                ),
            },
            "optimize": {
                "alpha": round(self.optimize_arm["alpha"], 1),
                "beta": round(self.optimize_arm["beta"], 1),
                "expected": round(
                    self.optimize_arm["alpha"]
                    / (self.optimize_arm["alpha"] + self.optimize_arm["beta"]),
                    3,
                ),
            },
        }


class BacktestLoop(BaseService):
    """回测循环引擎 - 滚动IC分析 + 因子性能评估"""

    def __init__(self, factor_farm=None):
        super().__init__()
        self._factor_farm = factor_farm  # 注入FactorFarm(避免循环导入)
        self.bandit = BanditAllocator()
        self.round_log: list[dict] = []

    @property
    def factor_farm(self):
        if self._factor_farm is None:
            from services.factor_farm import FactorFarm

            self._factor_farm = FactorFarm()
        return self._factor_farm

    def run(
        self,
        price_data: pd.DataFrame,
        start_date: str | None = None,
        end_date: str | None = None,
        forward_period: int = 5,
        window_size: int = 60,
        step_size: int = 20,
        code: str = "",
    ) -> ServiceResult:
        """
        运行滚动IC回测。

        Args:
            price_data: OHLCV DataFrame with datetime index
            start_date: 回测开始日期
            end_date: 回测结束日期
            forward_period: 前瞻收益天数
            window_size: 滚动窗口大小(交易日)
            step_size: 窗口步进大小
        """
        try:
            if price_data.empty or len(price_data) < window_size + forward_period:
                return ServiceResult.error(errors=["Insufficient data for backtest"])

            # 日期过滤
            if start_date:
                price_data = price_data[price_data.index >= start_date]
            if end_date:
                price_data = price_data[price_data.index <= end_date]

            results = []
            total_steps = max(1, (len(price_data) - window_size - forward_period) // step_size)

            for step in range(total_steps):
                window_start = step * step_size
                window_end = window_start + window_size
                forward_end = window_end + forward_period

                if forward_end > len(price_data):
                    break

                train_df = price_data.iloc[window_start:window_end]
                window_end_date = price_data.index[window_end - 1]
                forward_end_date = price_data.index[min(forward_end - 1, len(price_data) - 1)]

                # 对该窗口评估所有因子
                round_results = []
                for factor_name in FACTOR_METHODS:
                    ic_result = self.factor_farm.evaluate_ic(
                        factor_name, code, train_df, forward_period
                    )
                    if ic_result.status == "ok":
                        round_results.append(
                            {
                                "factor": factor_name,
                                "ic": ic_result.data["ic"],
                                "icir": ic_result.data["icir"],
                                "significant": ic_result.data.get("significant", False),
                            }
                        )

                if round_results:
                    # 按绝对IC排序
                    round_results.sort(key=lambda x: abs(x["ic"]), reverse=True)
                    avg_ic = np.mean([abs(r["ic"]) for r in round_results])
                    sig_count = sum(1 for r in round_results if r["significant"])

                    results.append(
                        {
                            "step": step,
                            "window_end": str(window_end_date)[:10],
                            "forward_end": str(forward_end_date)[:10],
                            "factors_evaluated": len(round_results),
                            "significant_factors": sig_count,
                            "avg_abs_ic": round(float(avg_ic), 4),
                            "top_factor": round_results[0]["factor"] if round_results else None,
                            "top_ic": round_results[0]["ic"] if round_results else 0,
                            "top5_factors": [r["factor"] for r in round_results[:5]],
                        }
                    )

                if round_results:
                    reward = min(1.0, max(0.0, avg_ic / 0.05))  # IC=0→0, IC>=0.05→1
                    action = self.bandit.select_action()
                    self.bandit.update(action, reward)

            emit_log("DEBUG", "backtest", f"????: {len(results)}?")
            self.round_log = results

            # 汇总统计
            if results:
                ic_series = [r["avg_abs_ic"] for r in results]
                summary = {
                    "total_windows": len(results),
                    "mean_abs_ic": round(float(np.mean(ic_series)), 4),
                    "std_abs_ic": round(float(np.std(ic_series)), 4),
                    "ic_stability": round(
                        float(np.mean(ic_series) / max(np.std(ic_series), 0.0001)), 2
                    ),
                    "significant_pct": round(
                        float(
                            np.mean(
                                [
                                    r["significant_factors"] / max(r["factors_evaluated"], 1)
                                    for r in results
                                ]
                            )
                        ),
                        3,
                    ),
                    "best_window": max(results, key=lambda r: r["avg_abs_ic"]),
                    "worst_window": min(results, key=lambda r: r["avg_abs_ic"]),
                }
            else:
                summary = {"total_windows": 0, "error": "No results generated"}

            return ServiceResult.ok(
                data={
                    "summary": summary,
                    "rounds": results,
                    "bandit_status": self.bandit.get_status(),
                    "total_steps": total_steps,
                }
            )
        except Exception as e:
            return ServiceResult.error(errors=[f"BacktestLoop failed: {e}"])

    def calculate_performance_metrics(self, returns: list[float]) -> ServiceResult:
        """计算策略表现的标准化指标"""
        try:
            if not returns or len(returns) < 2:
                return ServiceResult.error(errors=["Insufficient return data"])

            ret_series = pd.Series(returns)

            # 年化收益率
            total_return = (1 + ret_series).prod() - 1
            annual_return = (1 + total_return) ** (252 / len(ret_series)) - 1

            # 年化波动率
            annual_vol = ret_series.std() * math.sqrt(252)

            # Sharpe比率 (假设无风险利率2%)
            sharpe = (annual_return - 0.02) / annual_vol if annual_vol > 0 else 0

            # 最大回撤
            cumulative = (1 + ret_series).cumprod()
            running_max = cumulative.cummax()
            drawdown = (cumulative - running_max) / running_max
            max_dd = float(drawdown.min())

            # 胜率
            win_rate = float((ret_series > 0).mean())

            # 盈亏比
            gains = ret_series[ret_series > 0]
            losses = abs(ret_series[ret_series < 0])
            profit_loss_ratio = (
                float(gains.mean() / losses.mean()) if len(losses) > 0 and losses.mean() > 0 else 0
            )

            # Calmar比率
            calmar = annual_return / abs(max_dd) if max_dd != 0 else 0

            return ServiceResult.ok(
                data={
                    "total_return_pct": round(float(total_return * 100), 2),
                    "annual_return_pct": round(float(annual_return * 100), 2),
                    "annual_volatility_pct": round(float(annual_vol * 100), 2),
                    "sharpe_ratio": round(sharpe, 3),
                    "max_drawdown_pct": round(float(max_dd * 100), 2),
                    "win_rate_pct": round(float(win_rate * 100), 1),
                    "profit_loss_ratio": round(profit_loss_ratio, 2),
                    "calmar_ratio": round(calmar, 3),
                    "observations": len(returns),
                }
            )
        except Exception as e:
            return ServiceResult.error(errors=[f"Performance calculation failed: {e}"])

    def get_round_log(self) -> ServiceResult:
        """获取回测日志"""
        return ServiceResult.ok(data={"rounds": self.round_log, "count": len(self.round_log)})
