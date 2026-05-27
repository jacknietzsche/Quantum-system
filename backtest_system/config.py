"""
回测系统全局配置
=================
所有模块的默认参数集中管理，支持运行时覆盖。

注: TradeConfig 的默认值与 core/config.py 不同（佣金更低、滑点更高），
这是有意为之 —— 回测使用更乐观的成本假设。
PortfolioConfig / RiskConfig / FactorConfig 与 core 一致。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path


# ============================================================
# 项目路径配置
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache"
# 调整报告输出路径，使用项目根目录的reports/backtest_reports
PROJECT_ROOT = BASE_DIR.parent
REPORT_DIR = PROJECT_ROOT / "reports" / "backtest_reports"
CACHE_DIR.mkdir(exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class DataConfig:
    """数据加载配置"""
    # akshare 在线数据源
    default_start_date: str = "20230101"      # 默认回测起始日
    default_end_date: str = "20260327"        # 默认回测截止日
    adjust_type: str = "qfq"                   # 复权类型: qfq(前复权) hfq(后复权) None(不复权)

    # 本地数据
    local_data_dir: str = str(CACHE_DIR / "market_data")
    local_data_format: str = "hdf5"            # csv / hdf5

    # 缓存
    cache_enabled: bool = True
    cache_hours: int = 24

    # 基准数据（沪深300用于对比）
    benchmark_code: str = "000300"


@dataclass
class TradeConfig:
    """交易成本配置"""
    commission_rate: float = 0.0002           # 手续费 万分之二
    stamp_duty_rate: float = 0.001             # 印花税 千分之一（仅卖出）
    slippage_rate: float = 0.001               # 滑点 千分之一
    commission_min: float = 5.0                # 最低手续费 5元


@dataclass
class PortfolioConfig:
    """仓位管理配置"""
    initial_cash: float = 1_000_000.0          # 初始资金 100万
    weight_mode: str = "equal"                 # equal(等权重) / custom
    max_position_pct: float = 0.10             # 单票仓位上限 10%
    max_total_position: float = 0.80           # 总仓位上限 80%
    min_trade_amount: int = 100                # 最小交易手数（股）


@dataclass
class RiskConfig:
    """风险评估配置"""
    risk_free_rate: float = 0.025              # 无风险利率 2.5%
    confidence_level: float = 0.95             # VaR 置信度
    lookback_window: int = 252                 # 风险计算回溯窗口（交易日）


@dataclass
class FactorConfig:
    """因子分析配置"""
    # 因子预处理
    winsorize_method: str = "mad"              # mad / quantile
    winsorize_std: float = 3.0                 # MAD 倍数

    # IC 分析
    ic_method: str = "spearman"                # spearman / pearson
    ic_rolling_window: int = 60                # 滚动IC窗口

    # 分层回测
    n_groups: int = 5                          # 分层数量

    # 风格因子
    style_factors: List[str] = field(default_factory=lambda: [
        "size", "value", "momentum", "volatility", "liquidity"
    ])


@dataclass
class ReportConfig:
    """报告生成配置"""
    output_dir: str = str(REPORT_DIR)
    report_title: str = "A股量化策略回测报告"
    # 仅保留必要配置，使用quantstats生成报告


@dataclass
class BacktestConfig:
    """回测系统总配置 —— 聚合所有子配置"""
    data: DataConfig = field(default_factory=DataConfig)
    trade: TradeConfig = field(default_factory=TradeConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    factor: FactorConfig = field(default_factory=FactorConfig)
    report: ReportConfig = field(default_factory=ReportConfig)

    # Backtrader 引擎参数
    cerebro_kwargs: Dict = field(default_factory=lambda: {
        "stdstats": True,
        "preload": True,
        "runonce": True,
    })

    # 多股票回测
    max_stocks: int = 50                       # 最多同时回测股票数
    data_feed_params: Dict = field(default_factory=lambda: {
        "nocase": True,
        "datetime": None,
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
        "openinterest": None,
    })
