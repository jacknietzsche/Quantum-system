"""
统一配置中心 — 所有模块共享的参数集中管理
==============================================

整合自:
  - backtest_system/config.py (BacktestConfig / DataConfig / TradeConfig / ...)
  - portfolio_manager.py  (TOTAL_CAPITAL / MAX_POSITION / MIN_TRADE_UNIT)
  - run_v14_full.py       (TOP_N / WEIGHT_* / LLM_TYPE / ...)
  - report_generator.py   (COLORS / RISK_FREE_RATE)

设计原则:
  1. 单一数据源 — 所有模块从此文件读取配置
  2. dataclass 聚合 — 逻辑分组，支持运行时覆盖
  3. 向后兼容 — 旧代码可通过 adapter 属性访问
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path

__all__ = [
    "QuantConfig",
    "DataSourceConfig",
    "TradeConfig",
    "PortfolioConfig",
    "RiskConfig",
    "SelectionConfig",
    "FactorConfig",
    "BacktestEngineConfig",
    "ReportConfig",
    "PROJECT_ROOT",
    "COLORS",
    "A_SHARE_LOT_SIZE",
]

# ============================================================
# 项目路径
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_CACHE_DIR = PROJECT_ROOT / "real_data_cache"

# A股交易常量
A_SHARE_LOT_SIZE = 100  # A股最小交易单位：100股/手
BACKTEST_CACHE_DIR = PROJECT_ROOT / "backtest_system" / "cache" / "market_data"
REPORT_DIR = PROJECT_ROOT / "daily_reports_v14"
PORTFOLIO_REPORT_DIR = PROJECT_ROOT / "portfolio_reports"
BACKTEST_REPORT_DIR = PROJECT_ROOT / "backtest_system" / "reports"


# ============================================================
# 数据源配置
# ============================================================
@dataclass
class DataSourceConfig:
    """数据源与缓存配置"""
    # 本地数据库（优先使用）
    use_local_db: bool = True                  # 优先使用本地SQLite数据库
    local_db_path: str = str(PROJECT_ROOT / "local_db" / "a_stock_quant.db")  # 本地数据库路径
    
    # 数据源开关
    use_tencent_data: bool = False             # 是否使用腾讯数据源（默认关闭，避免RemoteDisconnected错误）
    
    # baostock（主源）
    baostock_session_timeout: int = 1800       # 会话超时（秒）
    baostock_max_retries: int = 3             # 单次请求最大重试

    # 缓存
    cache_enabled: bool = True
    cache_hours: int = 24                     # 缓存有效期（小时）
    cache_dir: str = str(DATA_CACHE_DIR)
    backtest_cache_dir: str = str(BACKTEST_CACHE_DIR)

    # 数据拉取
    request_days: int = 120                   # 默认拉取天数
    min_data_rows: int = 30                   # 最少有效数据行数
    request_delay: float = 0.08               # 请求间隔（秒）- 优化降低延迟
    max_workers: int = 8                      # 并行线程数 - 优化从3提升到8

    # 复权
    default_adjust: str = "qfq"              # 前复权

    # 基准
    benchmark_code: str = "000300"            # 沪深300

    # 名称缓存
    name_map_ttl: int = 86400                # 名称缓存24小时


# ============================================================
# 交易成本配置（A股）
# ============================================================
@dataclass
class TradeConfig:
    """A股交易成本"""
    # ===== V15 改进：真实交易成本 =====
    commission_rate: float = 0.0003           # 佣金 万分之三 (0.03%)
    stamp_duty_rate: float = 0.001             # 印花税 千分之一（仅卖出，0.1%）
    slippage_rate: float = 0.0005               # 滑点 万分之五 (0.05%)，原0.1%
    commission_min: float = 5.0                # 最低佣金 5 元


# ============================================================
# 仓位管理配置
# ============================================================
@dataclass
class PortfolioConfig:
    """仓位管理"""
    initial_cash: float = 1_000_000.0          # 初始资金（元）
    weight_mode: str = "equal"                 # equal / custom
    max_position_pct: float = 0.10             # 单票仓位上限 10%
    max_total_position: float = 0.80           # 总仓位上限 80%
    min_trade_amount: int = 100                # 最小交易单位（股）


# ============================================================
# 风控配置
# ============================================================
@dataclass
class RiskConfig:
    """风险评估与风控"""
    risk_free_rate: float = 0.025              # 无风险利率 2.5%
    confidence_level: float = 0.95             # VaR 置信度
    lookback_window: int = 252                 # 风险计算回溯窗口

    # 防顶过滤
    anti_top_enabled: bool = True
    anti_top_filter_threshold: int = 2         # 触发>=N项开始惩罚
    anti_top_heavy_threshold: int = 4          # 触发>=N项大幅惩罚

    # 停牌
    max_stale_days: int = 4                    # 数据超过N天视为过期

    # ===== V15 改进：风险控制模块 =====
    # 动态止损+回撤控制
    stop_loss_enabled: bool = True             # 启用动态止损
    stop_loss_pct: float = 0.08                # 单期回撤超8%平仓50%
    stop_loss_heavy: float = 0.15              # 单期回撤超15%清仓
    stop_loss_position_pct: float = 0.60       # 止损时平仓比例

    # 波动率约束
    volatility_limit_enabled: bool = True      # 启用波动率约束
    max_volatility: float = 0.25               # 最大年化波动率（25%）
    volatility_reduction_pct: float = 0.40     # 波动率超限时现金比例提升至40%

    # 行业分散化
    sector_diversification_enabled: bool = True  # 启用行业分散化
    max_sector_weight: float = 0.20            # 单行业持仓占比不超过20%


# ============================================================
# v14 选股配置
# ============================================================
@dataclass
class SelectionConfig:
    """v14 量化选股参数"""
    top_n: int = 10                            # 推荐股票数量
    batch_print: int = 500                     # 批量打印进度

    # 评分权重 - 调整原则：越是有效的因子越增加权重
    # IC有效性参考：学术因子综合+5.8%，因子引擎V2+3.0~5.0%，v12基础+2.0~3.0%
    # ===== V16 改进：因子权重重构 =====
    weight_base: float = 0.20                  # v12 基础因子 (25%→20%，因IC相对较低)
    weight_enhanced: float = 0.35              # 增强因子 (30%→35%，保留高IC值动量/假突破)
    weight_market: float = 0.15                # 市场环境 (20%→15%，优化宏观择时权重)
    weight_factor_v2: float = 0.30             # 因子引擎V2 (25%→30%，增加行为金融因子权重)

    # ===== V15 改进：新增因子权重 =====
    weight_liquidity: float = 0.08             # 流动性因子权重（归入市场环境）
    weight_quality: float = 0.07               # 质量因子权重（归入增强因子）
    weight_low_vol: float = 0.05               # 低波动因子权重（归入因子引擎V2）
    weight_trading_behavior: float = 0.05      # 交易行为因子权重（归入增强因子）

    # ===== V15 改进：因子有效性验证 =====
    ic_min_threshold: float = 0.05             # IC值绝对值低于此值视为失效因子
    ic_rolling_window: int = 60                # IC计算滚动窗口

    # LLM 配置
    llm_type: str = "chatanywhere"            # local / chatanywhere / openai

    # 过滤规则
    filter_st: bool = True                     # 过滤 ST/*ST
    filter_kcb: bool = True                    # 过滤科创板 688xxx
    filter_ipo_days: int = 96                  # 次新股最少天数（约120天*0.8）
    filter_max_price: float = 100.0            # 高价股过滤阈值

    # ===== V15 改进：选股池精细化筛选 =====
    # 成分股过滤（沪深300/中证500）
    filter_include_hs300: bool = False         # 仅保留沪深300成分股
    filter_include_zz500: bool = False         # 仅保留中证500成分股
    filter_include_hs300_zz500: bool = True    # 仅保留沪深300+中证500成分股（二选一）

    # 流动性过滤
    filter_min_turnover: float = 1.0           # 最小换手率（%），低于此值过滤
    filter_min_avg_amount: float = 10000000    # 最小日均成交额（元），低于此值过滤
    filter_top_by_volume: int = 20000          # 日均成交额前N只（0=不限制）

    # 停牌/退市风险过滤
    filter_max_suspended_days: int = 10        # 停牌超过N天过滤
    filter_delisted: bool = True               # 过滤退市/暂停上市股票


# ============================================================
# 因子分析配置
# ============================================================
@dataclass
class FactorConfig:
    """因子分析与归因"""
    # 因子预处理
    winsorize_method: str = "mad"
    winsorize_std: float = 3.0

    # IC 分析
    ic_method: str = "spearman"
    ic_rolling_window: int = 60

    # 分层回测
    n_groups: int = 5

    # 风格因子
    style_factors: List[str] = field(default_factory=lambda: [
        "size", "value", "momentum", "volatility", "liquidity"
    ])


# ============================================================
# 回测引擎配置
# ============================================================
@dataclass
class BacktestEngineConfig:
    """Backtrader 引擎参数"""
    preload: bool = True
    runonce: bool = True
    max_stocks: int = 50

    # ===== V16 改进：调仓机制优化 =====
    # 调仓模式选择
    rebalance_mode: str = "weekly"           # daily / biweekly / weekly / monthly / quarterly / threshold
    rebalance_days: int = 5                    # 调仓间隔（交易日），daily=1, biweekly=2, weekly=5, monthly=20, quarterly=60

    # 阈值触发式调仓
    rebalance_threshold: float = 0.30          # 评分变动超过30%触发调仓

    # 分层调仓
    rebalance_layers: int = 3                  # 分几批调仓（0=不分层）
    rebalance_layer_pct: float = 0.33          # 每批调仓比例

    # 最小持仓
    min_hold_days: int = 5                     # 最小持仓天数
    sell_score_drop: float = 0.05              # 评分降幅卖出阈值


# ============================================================
# 报告配置
# ============================================================
@dataclass
class ReportConfig:
    """报告生成参数"""
    report_title: str = "A股量化系统报告"
    theme: str = "plotly_white"
    chinese_font: str = "Microsoft YaHei"

    # 输出目录
    selection_report_dir: str = str(REPORT_DIR)
    portfolio_report_dir: str = str(PORTFOLIO_REPORT_DIR)
    backtest_report_dir: str = str(BACKTEST_REPORT_DIR)


# ============================================================
# 总配置聚合
# ============================================================
@dataclass
class QuantConfig:
    """
    量化系统总配置 — 所有子配置的聚合入口。

    用法:
        from core.config import QuantConfig
        cfg = QuantConfig()
        # 覆盖子配置
        cfg.portfolio.initial_cash = 500_000.0
    """
    data: DataSourceConfig = field(default_factory=DataSourceConfig)
    trade: TradeConfig = field(default_factory=TradeConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    selection: SelectionConfig = field(default_factory=SelectionConfig)
    factor: FactorConfig = field(default_factory=FactorConfig)
    backtest_engine: BacktestEngineConfig = field(default_factory=BacktestEngineConfig)
    report: ReportConfig = field(default_factory=ReportConfig)

    def ensure_dirs(self):
        """确保所有必要目录存在"""
        for path_key in ["cache_dir", "backtest_cache_dir"]:
            p = Path(getattr(self.data, path_key))
            p.mkdir(parents=True, exist_ok=True)
        for path_key in ["selection_report_dir", "portfolio_report_dir", "backtest_report_dir"]:
            p = Path(getattr(self.report, path_key))
            p.mkdir(parents=True, exist_ok=True)


# ============================================================
# 报告配色方案（全局共享）
# ============================================================
COLORS = {
    "primary": "#b71c1c",
    "primary_light": "#fce4ec",
    "blue": "#1565c0",
    "blue_light": "#e3f2fd",
    "green": "#2e7d32",
    "green_light": "#e8f5e9",
    "orange": "#e65100",
    "orange_light": "#fff3e0",
    "purple": "#6a1b9a",
    "purple_light": "#f3e5f5",
    "gray": "#666666",
    "bg": "#f5f5f5",
}
