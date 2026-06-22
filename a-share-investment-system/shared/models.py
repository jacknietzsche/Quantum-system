"""
A股智能投资系统 - 数据库模型层
SQLite + SQLAlchemy ORM
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from shared.logging import emit_log

Base = declarative_base()


class TradeStatus(enum.Enum):
    HOLDING = "持有"
    SOLD = "已卖"


class TradeType(enum.Enum):
    BUY = "买入"
    SELL = "卖出"


class RiskLevel(enum.Enum):
    LOW = "低风险"
    MEDIUM = "中风险"
    HIGH = "高风险"
    EXTREME = "极高风险"


# ── 持仓表 ──
class Portfolio(Base):
    __tablename__ = "portfolio"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), nullable=False, index=True)
    stock_name = Column(String(50), nullable=False)
    buy_date = Column(String(10), nullable=False)  # YYYY-MM-DD
    buy_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    current_price = Column(Float, default=0.0)
    status = Column(Enum(TradeStatus), default=TradeStatus.HOLDING)
    sell_date = Column(String(10))
    sell_price = Column(Float, default=0.0)
    sell_reason = Column(Text, default="")
    buy_reason = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    portfolio_type = Column(String(20), default="value", index=True)

    @property
    def cost_value(self):
        return self.buy_price * self.quantity

    @property
    def current_value(self):
        if self.status == TradeStatus.HOLDING:
            return (self.current_price or 0) * self.quantity
        return (self.sell_price or 0) * self.quantity

    @property
    def profit_loss(self):
        if self.status == TradeStatus.HOLDING:
            return ((self.current_price or 0) - self.buy_price) * self.quantity
        return ((self.sell_price or 0) - self.buy_price) * self.quantity

    @property
    def profit_loss_pct(self):
        return (self.profit_loss / self.cost_value * 100) if self.cost_value > 0 else 0


# ── 交易记录表 ──
class TradeRecord(Base):
    __tablename__ = "trade_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), nullable=False, index=True)
    stock_name = Column(String(50), nullable=False)
    trade_date = Column(String(10), nullable=False)
    trade_type = Column(Enum(TradeType), nullable=False)
    price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    amount = Column(Float, default=0.0)
    reason = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)
    portfolio_type = Column(String(20), default="value", index=True)


# ── 每日报告表 ──
class DailyReport(Base):
    __tablename__ = "daily_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), nullable=False, unique=True, index=True)
    market_summary = Column(Text, default="")
    recommendations = Column(Text, default="")
    portfolio_snapshot = Column(Text, default="")
    total_return_pct = Column(Float, default=0.0)
    risk_level = Column(Enum(RiskLevel), default=RiskLevel.MEDIUM)
    report_file = Column(String(200), default="")
    created_at = Column(DateTime, default=datetime.now)


# ── 自选股表 ──
class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), nullable=False, unique=True, index=True)
    stock_name = Column(String(50), nullable=False)
    add_reason = Column(Text, default="")
    category = Column(String(50), default="自选")  # 自选/观察/备买
    created_at = Column(DateTime, default=datetime.now)


class OrderStatus(enum.Enum):
    PENDING = "待执行"
    FILLED = "已成交"
    CANCELLED = "已撤销"
    PARTIAL = "部分成交"


class OrderDirection(enum.Enum):
    BUY = "买入"
    SELL = "卖出"


# ── 订单表(模拟交易) ──
class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), nullable=False, index=True)
    stock_name = Column(String(50), nullable=False)
    direction = Column(Enum(OrderDirection), nullable=False)
    quantity = Column(Integer, nullable=False)  # 目标数量(股)
    price_type = Column(String(20), default="开盘价")  # 开盘价/限价
    limit_price = Column(Float, default=0.0)  # 限价(如果price_type=限价)
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING, index=True)
    signal_confidence = Column(Float, default=0.0)  # 信号置信度 0-100
    signal_reason = Column(Text, default="")  # 信号原因
    target_date = Column(String(10), nullable=False)  # 目标执行日期
    created_at = Column(DateTime, default=datetime.now)
    portfolio_type = Column(String(20), default="value", index=True)
    executed_at = Column(DateTime)
    filled_price = Column(Float, default=0.0)  # 实际成交价
    filled_quantity = Column(Integer, default=0)  # 实际成交数量
    commission = Column(Float, default=0.0)  # 佣金
    tax = Column(Float, default=0.0)  # 印花税
    slippage_cost = Column(Float, default=0.0)  # 滑点成本


# ── 成交记录表 ──
class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, nullable=False, index=True)
    stock_code = Column(String(10), nullable=False, index=True)
    stock_name = Column(String(50), nullable=False)
    direction = Column(Enum(OrderDirection), nullable=False)
    execute_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    amount = Column(Float, default=0.0)
    commission = Column(Float, default=0.0)
    tax = Column(Float, default=0.0)
    slippage_cost = Column(Float, default=0.0)
    trade_date = Column(String(10), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    portfolio_type = Column(String(20), default="value", index=True)


# ── 每日净值表 ──
class DailyNAV(Base):
    __tablename__ = "daily_nav"
    __table_args__ = (Index("idx_nav_date_type", "date", "portfolio_type", unique=True),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), nullable=False, index=True)
    total_asset = Column(Float, nullable=False)  # 总资产
    cash = Column(Float, default=0.0)  # 现金
    stock_value = Column(Float, default=0.0)  # 股票市值
    daily_return_pct = Column(Float, default=0.0)  # 当日收益率%
    cumulative_return_pct = Column(Float, default=0.0)  # 累计收益率%
    position_count = Column(Integer, default=0)  # 持仓数
    risk_quadrant = Column(String(5), default="")  # 风险象限
    signal_count = Column(Integer, default=0)  # 当日信号数
    order_count = Column(Integer, default=0)  # 当日订单数
    notes = Column(Text, default="")  # 备注
    created_at = Column(DateTime, default=datetime.now)
    portfolio_type = Column(String(20), default="value", index=True)


# ── 系统日志表 ──
class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    module = Column(String(50), nullable=False, index=True)
    level = Column(String(10), nullable=False, default="INFO")  # INFO/WARNING/ERROR/CRITICAL
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now, index=True)


# ── 股票信息表(投委会分析用)──
class StockInfo(Base):
    """股票基础信息 + 基本面 + 技术面汇总"""

    __tablename__ = "stock_info"
    __table_args__: dict | None = None

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), nullable=False, unique=True, index=True)
    stock_name = Column(String(50), nullable=False)
    category = Column(String(10), default="股票")  # 股票/ETF/LOF
    # 基本面
    industry = Column(String(50), default="")  # 所处行业
    pe_ratio = Column(Float, default=0.0)  # 市盈率(动)
    pb_ratio = Column(Float, default=0.0)  # 市净率
    gross_margin = Column(Float, default=0.0)  # 毛利率
    net_margin = Column(Float, default=0.0)  # 净利率
    roe = Column(Float, default=0.0)  # 净资产收益率
    net_profit = Column(Float, default=0.0)  # 净利润
    total_market_cap = Column(Float, default=0.0)  # 总市值
    float_market_cap = Column(Float, default=0.0)  # 流通市值
    # 行情快照
    latest_price = Column(Float, default=0.0)
    change_pct = Column(Float, default=0.0)
    turnover_rate = Column(Float, default=0.0)
    volume = Column(Float, default=0.0)
    amount = Column(Float, default=0.0)
    # Tech indicators (60-day K-line calc)
    ma5 = Column(Float, default=0.0)
    ma10 = Column(Float, default=0.0)
    ma20 = Column(Float, default=0.0)
    ma60 = Column(Float, default=0.0)
    rsi_14 = Column(Float, default=0.0)
    macd = Column(Float, default=0.0)
    atr_14 = Column(Float, default=0.0)
    volatility_20d = Column(Float, default=0.0)
    max_drawdown_60d = Column(Float, default=0.0)
    # Trend signals
    trend = Column(String(20), default="")
    ma_alignment = Column(String(20), default="")
    # Derived indicators (DataComputer)
    change_pct_5d = Column(Float, default=0.0)  # 5日涨幅(%)
    change_pct_20d = Column(Float, default=0.0)  # 20日涨幅(%)
    change_pct_60d = Column(Float, default=0.0)  # 60日涨幅(%)
    volume_ratio = Column(Float, default=0.0)  # 量比(今日量/5日均量)
    ma250 = Column(Float, default=0.0)  # 250日均线(年线)
    # Kline stats
    kline_count = Column(Integer, default=0)
    last_kline_date = Column(String(10), default="")
    # Valuation and financial indicators (screening)
    earnings_growth_3y = Column(Float, default=0.0)  # 近3年净利润增长率
    eps = Column(Float, default=0.0)  # 每股收益
    bvps = Column(Float, default=0.0)  # 每股净资产
    debt_to_equity = Column(Float, default=0.0)  # 负债权益比
    net_income = Column(Float, default=0.0)  # 净利润(绝对)
    current_assets = Column(Float, default=0.0)  # 流动资产 (Sina财报)
    total_liabilities = Column(Float, default=0.0)  # 总负债 (Sina财报)
    free_cash_flow = Column(Float, default=0.0)  # 自由现金流
    revenue_growth_3y = Column(Float, default=0.0)  # 近3年营收增长率
    operating_margin = Column(Float, default=0.0)  # 营业利润率
    current_ratio = Column(Float, default=0.0)  # 流动比率
    cash_ratio = Column(Float, default=0.0)  # 现金比率
    dividend_yield = Column(Float, default=0.0)  # ???(%)
    shares_outstanding = Column(Float, default=0.0)  # ????(?)
    cash_to_assets = Column(Float, default=0.0)  # ??????/???
    insider_holding_pct = Column(Float, default=0.0)  # ????????(%)
    listing_days = Column(Integer, default=0)  # 上市天数
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


# ── 历史K线缓存表 ──
class KlineCache(Base):
    """历史K线本地缓存"""

    __tablename__ = "kline_cache"
    __table_args__ = (Index("idx_kline_code_date", "stock_code", "trade_date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), nullable=False, index=True)
    trade_date = Column(String(10), nullable=False, index=True)
    open = Column(Float, default=0.0)
    high = Column(Float, default=0.0)
    low = Column(Float, default=0.0)
    close = Column(Float, default=0.0)
    volume = Column(Float, default=0.0)
    amount = Column(Float, default=0.0)
    change_pct = Column(Float, default=0.0)
    turnover_rate = Column(Float, default=0.0)


# ── 市场快照缓存表 (v4.0) ──
class MarketSnapshot(Base):
    """缓存市场指数、北向资金、板块排行等快照数据,支持本地优先即时加载"""

    __tablename__ = "market_snapshot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_type = Column(String(30), nullable=False, unique=True)
    trade_date = Column(String(10), default="")  # v5.1: 数据交易日 YYYY-MM-DD
    data_json = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"MarketSnapshot(type={self.snapshot_type}, updated={self.updated_at})"


# ── 分析任务表 ──
class AnalysisTask(Base):
    """分析任务队列"""

    __tablename__ = "analysis_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(36), nullable=False, unique=True, index=True)
    stock_code = Column(String(10), nullable=False, index=True)
    stock_name = Column(String(50), default="")
    task_type = Column(String(20), default="analysis")
    status = Column(String(20), default="pending")  # pending/running/completed/failed
    signal = Column(String(20), default="")  # bullish/bearish/neutral
    confidence = Column(Integer, default=0)
    progress = Column(Integer, default=0)
    result = Column(Text, default="")
    result_json = Column(Text, default="")
    error = Column(Text, default="")
    start_time = Column(DateTime, default=datetime.now)
    finish_time = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


# ── 风格信号评分表 ──
class StyleSignal(Base):
    """每只股票在每个选股风格下的最新评分"""

    __tablename__ = "style_signal"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), nullable=False, index=True)
    style = Column(String(20), nullable=False, index=True)
    score = Column(Float, default=0.0)
    signal = Column(String(10), default="")
    rank = Column(Integer, default=0)
    metrics_json = Column(Text, default="{}")
    data_freshness = Column(String(20), default="")
    source_chain = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("idx_style_signal_style_score", "style", "score"),
        Index("idx_style_signal_stock_style", "stock_code", "style", unique=True),
    )


# ── 选股运行记录表 ──
class ScreenResult(Base):
    """每次选股运行的完整结果"""

    __tablename__ = "screen_result"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(36), nullable=False, unique=True, index=True)
    style = Column(String(20), nullable=False, index=True)
    market_regime = Column(String(20), default="NEUTRAL")
    total_universe = Column(Integer, default=0)
    stage1_passed = Column(Integer, default=0)
    stage2_passed = Column(Integer, default=0)
    stage3_recommended = Column(Integer, default=0)
    recommendations_json = Column(Text, default="[]")
    elapsed_seconds = Column(Float, default=0.0)
    status = Column(String(20), default="completed")
    error_msg = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now, index=True)


# ── 财务指标历史表 ──
class FundMetricHist(Base):
    """财务指标时序数据 — 季报/年报"""

    __tablename__ = "fund_metric_hist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), nullable=False, index=True)
    report_period = Column(String(10), nullable=False)
    report_type = Column(String(10), default="quarter")

    revenue = Column(Float, default=0.0)
    net_income = Column(Float, default=0.0)
    net_income_parent = Column(Float, default=0.0)
    gross_profit = Column(Float, default=0.0)
    operating_income = Column(Float, default=0.0)
    eps = Column(Float, default=0.0)

    total_assets = Column(Float, default=0.0)
    total_liabilities = Column(Float, default=0.0)
    shareholders_equity = Column(Float, default=0.0)
    current_assets = Column(Float, default=0.0)
    current_liabilities = Column(Float, default=0.0)
    cash_and_equivalents = Column(Float, default=0.0)
    total_debt = Column(Float, default=0.0)
    inventory = Column(Float, default=0.0)
    accounts_receivable = Column(Float, default=0.0)

    ocf_net = Column(Float, default=0.0)
    capex = Column(Float, default=0.0)
    fcf = Column(Float, default=0.0)

    roe = Column(Float, default=0.0)
    roa = Column(Float, default=0.0)
    debt_to_equity = Column(Float, default=0.0)
    current_ratio = Column(Float, default=0.0)
    gross_margin = Column(Float, default=0.0)
    net_margin = Column(Float, default=0.0)
    revenue_yoy = Column(Float, default=0.0)
    net_income_yoy = Column(Float, default=0.0)
    bvps = Column(Float, default=0.0)
    dividend_per_share = Column(Float, default=0.0)

    institution_holding_pct = Column(Float, default=0.0)
    north_flow_hold = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index("idx_fmh_code_period", "stock_code", "report_period", unique=True),
        Index("idx_fmh_code_report", "stock_code", "report_type", "report_period"),
    )


# ── 龙虎榜数据表 ──
class DragonTiger(Base):
    """龙虎榜数据 — 涨停狙击风格专用"""

    __tablename__ = "dragon_tiger"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(String(10), nullable=False, index=True)
    stock_code = Column(String(10), nullable=False, index=True)
    stock_name = Column(String(50), default="")
    limit_up_count = Column(Integer, default=0)
    limit_type = Column(String(10), default="")
    buy_dep1 = Column(String(100), default="")
    buy_amount1 = Column(Float, default=0.0)
    buy_dep2 = Column(String(100), default="")
    buy_amount2 = Column(Float, default=0.0)
    buy_dep3 = Column(String(100), default="")
    buy_amount3 = Column(Float, default=0.0)
    total_buy = Column(Float, default=0.0)
    total_sell = Column(Float, default=0.0)
    net_inflow = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index("idx_dt_date_code", "trade_date", "stock_code", unique=True),
        Index("idx_dt_buy1", "buy_dep1"),
    )


# ── 数据库迁移版本追踪 ──
class MigrationVersion(Base):
    """数据库迁移版本追踪"""

    __tablename__ = "_migration_version"
    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(20), nullable=False, unique=True)
    applied_at = Column(DateTime, default=datetime.now)


def _ensure_migration_version(conn):
    """确保迁移版本表存在且记录当前版本"""
    tables = {
        row[0] for row in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "_migration_version" not in tables:
        MigrationVersion.__table__.create(conn.connection)
    current_version = "5.6"
    existing = conn.exec_driver_sql(
        "SELECT version FROM _migration_version ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not existing or existing[0] != current_version:
        conn.exec_driver_sql(
            "INSERT INTO _migration_version (version) VALUES (?)", (current_version,)
        )
        conn.commit()
        print(f"[DB] Migration version tracked: {current_version}")


# ── 数据库初始化 ──
DB_PATH = "data/investment.db"
_ENGINE_CACHE: dict = {}
_SESSION_MAKER_CACHE: dict = {}


def get_engine(db_path: str = DB_PATH, reuse: bool = True):
    if reuse and db_path in _ENGINE_CACHE:
        return _ENGINE_CACHE[db_path]
    engine = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _ENGINE_CACHE[db_path] = engine
    return engine


def _safe_add_column(conn, table_name: str, col_name: str, ddl: str):
    """安全给表加列:先检查表存在且列不存在"""
    tables = {
        row[0] for row in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if table_name not in tables:
        return
    cols = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table_name})")}
    if col_name not in cols:
        try:
            conn.exec_driver_sql(ddl)
            conn.commit()
            print(f"[DB] Added {col_name} to {table_name}")
        except Exception as e:
            print(f"[DB] Could not add {col_name} to {table_name}: {e}")


def init_db(db_path: str = DB_PATH):
    """初始化数据库,创建所有表 + 增量迁移"""
    # Reuse cached engine to avoid SQLite lock from multiple engines
    engine = get_engine(db_path, reuse=True)
    Base.metadata.create_all(engine)

    with engine.connect() as conn:
        _ensure_migration_version(conn)
        # v5.1: 市场快照表增加交易日期列
        _safe_add_column(
            conn,
            "market_snapshot",
            "trade_date",
            "ALTER TABLE market_snapshot ADD COLUMN trade_date VARCHAR(10) DEFAULT ''",
        )

        # v5.x: StockInfo 表补充列
        stock_info_cols = [
            (
                "earnings_growth_3y",
                "ALTER TABLE stock_info ADD COLUMN earnings_growth_3y FLOAT DEFAULT 0.0",
            ),
            ("notes", "ALTER TABLE stock_info ADD COLUMN notes TEXT DEFAULT ''"),
            ("eps", "ALTER TABLE stock_info ADD COLUMN eps FLOAT DEFAULT 0.0"),
            ("bvps", "ALTER TABLE stock_info ADD COLUMN bvps FLOAT DEFAULT 0.0"),
            (
                "debt_to_equity",
                "ALTER TABLE stock_info ADD COLUMN debt_to_equity FLOAT DEFAULT 0.0",
            ),
            ("net_income", "ALTER TABLE stock_info ADD COLUMN net_income FLOAT DEFAULT 0.0"),
            (
                "free_cash_flow",
                "ALTER TABLE stock_info ADD COLUMN free_cash_flow FLOAT DEFAULT 0.0",
            ),
            (
                "revenue_growth_3y",
                "ALTER TABLE stock_info ADD COLUMN revenue_growth_3y FLOAT DEFAULT 0.0",
            ),
        ]
        for col_name, ddl in stock_info_cols:
            _safe_add_column(conn, "stock_info", col_name, ddl)

        # v5.2: portfolio_type segregation
        for table_name in ("portfolio", "trade_records", "orders", "trades", "daily_nav"):
            _safe_add_column(
                conn,
                table_name,
                "portfolio_type",
                f"ALTER TABLE {table_name} ADD COLUMN portfolio_type VARCHAR(20) DEFAULT 'value'",
            )

        # v5.3: orphan *_deprecated columns intentionally not in ORM

        # v5.4: 重新加入资产负债表字段 (SinaFinancialAdapter 提供)
        _safe_add_column(
            conn,
            "stock_info",
            "current_assets",
            "ALTER TABLE stock_info ADD COLUMN current_assets FLOAT DEFAULT 0.0",
        )
        _safe_add_column(
            conn,
            "stock_info",
            "total_liabilities",
            "ALTER TABLE stock_info ADD COLUMN total_liabilities FLOAT DEFAULT 0.0",
        )

        # v5.5: derived indicator fields
        derived_cols = [
            "change_pct_5d",
            "change_pct_20d",
            "change_pct_60d",
            "volume_ratio",
            "ma250",
        ]
        for col in derived_cols:
            _safe_add_column(
                conn,
                "stock_info",
                col,
                f"ALTER TABLE stock_info ADD COLUMN {col} FLOAT DEFAULT 0.0",
            )

        # v5.6: screener required financial fields
        stage2_cols = [
            (
                "operating_margin",
                "ALTER TABLE stock_info ADD COLUMN operating_margin FLOAT DEFAULT 0.0",
            ),
            ("current_ratio", "ALTER TABLE stock_info ADD COLUMN current_ratio FLOAT DEFAULT 0.0"),
            ("cash_ratio", "ALTER TABLE stock_info ADD COLUMN cash_ratio FLOAT DEFAULT 0.0"),
            (
                "cash_to_assets",
                "ALTER TABLE stock_info ADD COLUMN cash_to_assets FLOAT DEFAULT 0.0",
            ),
            (
                "insider_holding_pct",
                "ALTER TABLE stock_info ADD COLUMN insider_holding_pct FLOAT DEFAULT 0.0",
            ),
            ("listing_days", "ALTER TABLE stock_info ADD COLUMN listing_days INTEGER DEFAULT 0"),
        ]
        for col_name, ddl in stage2_cols:
            _safe_add_column(conn, "stock_info", col_name, ddl)

    print(f"[OK] Database initialized: {db_path}")
    return engine


def cleanup_system_logs(max_records: int = 1000):
    """清理系统日志,保留最新的 N 条记录"""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            count = conn.exec_driver_sql("SELECT COUNT(*) FROM system_logs").scalar() or 0
            if count > max_records:
                conn.exec_driver_sql(
                    "DELETE FROM system_logs WHERE id NOT IN "
                    "(SELECT id FROM system_logs ORDER BY id DESC LIMIT ?)",
                    (max_records,),
                )
                conn.commit()
                print(f"[DB] Cleaned system_logs: removed {count - max_records} old records")
    except Exception as e:
        print(f"[DB] system_logs cleanup skipped: {e}")


def cleanup_stale_klines(keep_years: int = 3):
    """删除超过 keep_years 的旧K线数据"""
    from datetime import timedelta

    try:
        engine = get_engine()
        cutoff = (datetime.now() - timedelta(days=keep_years * 365)).strftime("%Y-%m-%d")
        with engine.connect() as conn:
            result = conn.exec_driver_sql("DELETE FROM kline_cache WHERE trade_date < ?", (cutoff,))
            conn.commit()
            print(f"[DB] Cleaned stale klines before {cutoff}: {result.rowcount} rows")
    except Exception as e:
        print(f"[DB] kline cleanup skipped: {e}")


def run_db_maintenance():
    """系统级维护任务 — 启动时调用"""
    from sqlalchemy import text

    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("PRAGMA optimize"))
            conn.commit()
        cleanup_stale_klines(keep_years=3)
        cleanup_system_logs(max_records=1000)
        print("[DB] Maintenance complete")
    except Exception as e:
        print(f"[DB] Maintenance skipped: {e}")


def get_session(db_path: str = DB_PATH):
    """获取数据库会话(复用缓存的 engine 和 sessionmaker)"""
    if db_path not in _SESSION_MAKER_CACHE:
        engine = get_engine(db_path)
        # Enable WAL mode for better concurrent access
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL")
                conn.exec_driver_sql("PRAGMA busy_timeout=5000")
        except Exception as e:
            emit_log("WARNING", "models", f"PRAGMA setup failed: {str(e)[:80]}")
        _SESSION_MAKER_CACHE[db_path] = sessionmaker(bind=engine)
    return _SESSION_MAKER_CACHE[db_path]()
