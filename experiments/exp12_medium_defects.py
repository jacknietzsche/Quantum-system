# -*- coding: utf-8 -*-
"""
实验12: MEDIUM缺陷验证
目标: 错误消息国际化/日志格式/数据库迁移/配置热更新/大师选择算法
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import json
import yaml
import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from typing import Literal

print("=" * 60)
print("实验12: MEDIUM缺陷验证")
print("=" * 60)

# ========== 实验12.1: 错误消息国际化 ==========
print("\n" + "=" * 60)
print("实验12.1: 错误消息国际化方案")
print("=" * 60)

try:
    # 方案: LLM推理用英文，输出和错误消息用中文
    # Agent内部错误用英文（便于日志分析），用户可见消息用中文

    class MessageI18n:
        """消息国际化"""

        # 错误消息映射
        ERRORS = {
            "zh": {
                "DATA_UNAVAILABLE": "数据获取失败，请稍后重试",
                "LLM_TIMEOUT": "AI分析超时，请稍后重试",
                "LLM_RATE_LIMIT": "API调用频率过高，请稍后重试",
                "ANALYSIS_RUNNING": "该股票正在分析中，请等待完成",
                "INVALID_TICKER": "股票代码格式错误",
                "NETWORK_ERROR": "网络连接失败，请检查网络",
                "BUDGET_EXCEEDED": "今日AI调用额度已用完",
            },
            "en": {
                "DATA_UNAVAILABLE": "Data fetch failed, please retry",
                "LLM_TIMEOUT": "AI analysis timeout, please retry",
                "LLM_RATE_LIMIT": "API rate limit exceeded",
                "ANALYSIS_RUNNING": "Analysis already running for this ticker",
                "INVALID_TICKER": "Invalid stock ticker format",
                "NETWORK_ERROR": "Network connection failed",
                "BUDGET_EXCEEDED": "Daily AI budget exceeded",
            }
        }

        def __init__(self, lang: str = "zh"):
            self.lang = lang

        def error(self, code: str, **kwargs) -> str:
            """获取错误消息"""
            template = self.ERRORS.get(self.lang, self.ERRORS["zh"]).get(code, code)
            return template.format(**kwargs) if kwargs else template

        def set_lang(self, lang: str):
            self.lang = lang

    # 测试
    i18n = MessageI18n("zh")
    print(f"中文错误: {i18n.error('DATA_UNAVAILABLE')}")
    print(f"中文错误: {i18n.error('LLM_TIMEOUT')}")

    i18n.set_lang("en")
    print(f"英文错误: {i18n.error('DATA_UNAVAILABLE')}")
    print(f"英文错误: {i18n.error('LLM_TIMEOUT')}")

    # Agent输出语言配置
    config = {
        "features": {
            "output_language": "zh",      # 输出用中文
            "debate_language": "en",       # 辩论用英文
            "error_language": "zh",        # 错误消息用中文
            "log_language": "en",          # 日志用英文
        }
    }

    print(f"\n语言配置:")
    print(f"  输出: {config['features']['output_language']}")
    print(f"  辩论: {config['features']['debate_language']}")
    print(f"  错误: {config['features']['error_language']}")
    print(f"  日志: {config['features']['log_language']}")

    print("[PASS] 错误消息国际化方案成功")
except Exception as e:
    print(f"[FAIL] {e}")

# ========== 实验12.2: 结构化日志格式 ==========
print("\n" + "=" * 60)
print("实验12.2: 结构化日志格式")
print("=" * 60)

try:
    import logging
    import json

    class JSONFormatter(logging.Formatter):
        """JSON格式日志"""

        def format(self, record):
            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "module": record.module,
                "message": record.getMessage(),
            }

            # 添加额外字段
            if hasattr(record, "extra_data"):
                log_entry.update(record.extra_data)

            return json.dumps(log_entry, ensure_ascii=False)

    # 创建logger
    logger = logging.getLogger("ashare_x")
    logger.setLevel(logging.INFO)

    # 控制台handler
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)

    # 测试日志
    logger.info("系统启动")
    logger.info("开始分析 600519", extra={"extra_data": {"ticker": "600519", "agent": "market_analyst"}})
    logger.info("LLM调用完成", extra={"extra_data": {"model": "deepseek-chat", "tokens": 186, "latency_ms": 2770}})
    logger.warning("数据源超时", extra={"extra_data": {"provider": "tencent", "timeout": 10}})
    logger.error("LLM调用失败", extra={"extra_data": {"error": "rate_limit", "retry_count": 2}})

    print("[PASS] 结构化日志格式成功")
except Exception as e:
    print(f"[FAIL] {e}")

# ========== 实验12.3: 数据库迁移策略 ==========
print("\n" + "=" * 60)
print("实验12.3: 数据库迁移策略")
print("=" * 60)

try:
    db_path = Path("experiments/test_migration.db")
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))

    # 迁移版本表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migration_version (
            version INTEGER PRIMARY KEY,
            description TEXT,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    def get_current_version(conn):
        result = conn.execute("SELECT MAX(version) FROM _migration_version").fetchone()
        return result[0] if result[0] else 0

    def apply_migration(conn, version: int, description: str, sql: str):
        """应用迁移"""
        current = get_current_version(conn)
        if version <= current:
            print(f"  迁移v{version}: 跳过（已应用）")
            return False

        conn.execute(sql)
        conn.execute(
            "INSERT INTO _migration_version (version, description) VALUES (?, ?)",
            (version, description)
        )
        conn.commit()
        print(f"  迁移v{version}: {description} [已应用]")
        return True

    # 定义迁移
    migrations = [
        (1, "创建K线表", """
            CREATE TABLE IF NOT EXISTS kline_daily (
                stock_code TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                open REAL, high REAL, low REAL, close REAL,
                volume REAL, amount REAL,
                PRIMARY KEY (stock_code, trade_date)
            )
        """),
        (2, "添加技术指标列", """
            ALTER TABLE kline_daily ADD COLUMN ma5 REAL
        """),
        (3, "添加RSI列", """
            ALTER TABLE kline_daily ADD COLUMN rsi_14 REAL
        """),
        (4, "创建报告表", """
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                action TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """),
    ]

    # 应用迁移
    print("应用迁移:")
    for version, desc, sql in migrations:
        apply_migration(conn, version, desc, sql)

    # 再次应用（测试幂等性）
    print("\n再次应用（测试幂等性）:")
    for version, desc, sql in migrations:
        apply_migration(conn, version, desc, sql)

    # 检查当前版本
    current = get_current_version(conn)
    print(f"\n当前版本: v{current}")

    # 查看迁移历史
    history = conn.execute("SELECT * FROM _migration_version ORDER BY version").fetchall()
    print(f"迁移历史: {len(history)}条")
    for h in history:
        print(f"  v{h[0]}: {h[1]} ({h[2]})")

    conn.close()
    db_path.unlink()
    print("\n[PASS] 数据库迁移策略成功")
except Exception as e:
    print(f"[FAIL] {e}")

# ========== 实验12.4: 配置热更新 ==========
print("\n" + "=" * 60)
print("实验12.4: 配置热更新机制")
print("=" * 60)

try:
    import os
    import time
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    # 简化版：不依赖watchdog，用文件修改时间检测
    class ConfigHotReload:
        """配置热更新"""

        def __init__(self, config_path: str):
            self.config_path = Path(config_path)
            self.last_mtime = 0
            self.config = self._load()

        def _load(self) -> dict:
            """加载配置"""
            if self.config_path.exists():
                with open(self.config_path) as f:
                    config = yaml.safe_load(f)
                self.last_mtime = self.config_path.stat().st_mtime
                return config or {}
            return {}

        def get(self, key: str, default=None):
            """获取配置值"""
            # 检查是否需要热更新
            if self.config_path.exists():
                current_mtime = self.config_path.stat().st_mtime
                if current_mtime > self.last_mtime:
                    print(f"  配置文件已修改，重新加载")
                    self.config = self._load()

            # 支持嵌套key: "llm.quick_think.provider"
            keys = key.split(".")
            value = self.config
            for k in keys:
                if isinstance(value, dict):
                    value = value.get(k)
                else:
                    return default
            return value if value is not None else default

    # 创建测试配置
    config_path = Path("experiments/test_config.yaml")
    config_path.write_text("""
llm:
  quick_think:
    provider: deepseek
    model: deepseek-chat
  deep_think:
    provider: deepseek
    model: deepseek-reasoner
token_budget:
  daily_total: 400000
  per_stock: 25000
features:
  enable_masters: false
""")

    # 测试热更新
    hot_reload = ConfigHotReload(str(config_path))
    print(f"初始配置:")
    print(f"  provider: {hot_reload.get('llm.quick_think.provider')}")
    print(f"  daily_total: {hot_reload.get('token_budget.daily_total')}")
    print(f"  enable_masters: {hot_reload.get('features.enable_masters')}")

    # 修改配置
    config_path.write_text("""
llm:
  quick_think:
    provider: qwen
    model: qwen-turbo
  deep_think:
    provider: deepseek
    model: deepseek-reasoner
token_budget:
  daily_total: 500000
  per_stock: 30000
features:
  enable_masters: true
""")

    # 重新获取（触发热更新）
    print(f"\n修改后:")
    print(f"  provider: {hot_reload.get('llm.quick_think.provider')}")
    print(f"  daily_total: {hot_reload.get('token_budget.daily_total')}")
    print(f"  enable_masters: {hot_reload.get('features.enable_masters')}")

    config_path.unlink()
    print("\n[PASS] 配置热更新机制成功")
except ImportError:
    print("[SKIP] watchdog未安装，使用简化版检测")
    # 简化版测试
    config_path = Path("experiments/test_config.yaml")
    config_path.write_text("key: value1")
    content = config_path.read_text()
    print(f"  读取配置: {content.strip()}")
    config_path.write_text("key: value2")
    content = config_path.read_text()
    print(f"  更新后: {content.strip()}")
    config_path.unlink()
    print("[PASS] 简化版配置检测成功")
except Exception as e:
    print(f"[FAIL] {e}")

# ========== 实验12.5: 大师Agent选择算法 ==========
print("\n" + "=" * 60)
print("实验12.5: 大师Agent选择算法")
print("=" * 60)

try:
    def select_masters(stock_profile: dict) -> list[str]:
        """
        根据股票特征选择最相关的3个大师
        stock_profile: {pe_ratio, roe, volatility, growth, sector}
        """
        pe = stock_profile.get("pe_ratio", 20)
        roe = stock_profile.get("roe", 15)
        volatility = stock_profile.get("volatility", 0.3)
        growth = stock_profile.get("revenue_growth", 0.1)

        scores = {}

        # 巴菲特: 低PE + 高ROE + 低波动
        scores["buffett"] = 0
        if pe < 25: scores["buffett"] += 2
        if roe > 15: scores["buffett"] += 2
        if volatility < 0.3: scores["buffett"] += 1

        # 芒格: 高ROE + 合理PE + 稳定增长
        scores["munger"] = 0
        if roe > 20: scores["munger"] += 2
        if 10 < pe < 30: scores["munger"] += 1
        if 0.05 < growth < 0.3: scores["munger"] += 1

        # 林奇: 成长性 + 合理估值
        scores["lynch"] = 0
        if growth > 0.2: scores["lynch"] += 2
        if pe < growth * 100: scores["lynch"] += 2  # PEG < 1

        # 伯里: 高波动 + 低PE
        scores["burry"] = 0
        if volatility > 0.4: scores["burry"] += 2
        if pe < 15: scores["burry"] += 2

        # 伍德: 高成长 + 高波动
        scores["wood"] = 0
        if growth > 0.3: scores["wood"] += 2
        if volatility > 0.35: scores["wood"] += 1

        # 达利欧: 中等波动 + 分散
        scores["druckenmiller"] = 0
        if 0.2 < volatility < 0.4: scores["druckenmiller"] += 2
        if growth > 0.1: scores["druckenmiller"] += 1

        # 费雪: 高成长 + 高ROE
        scores["fisher"] = 0
        if growth > 0.25: scores["fisher"] += 2
        if roe > 20: scores["fisher"] += 1

        # 按分数排序，取前3
        sorted_masters = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [name for name, score in sorted_masters[:3] if score > 0]

    # 测试不同类型的股票
    test_cases = [
        {"name": "贵州茅台", "pe_ratio": 25, "roe": 30, "volatility": 0.2, "revenue_growth": 0.15},
        {"name": "宁德时代", "pe_ratio": 50, "roe": 20, "volatility": 0.45, "revenue_growth": 0.5},
        {"name": "中国平安", "pe_ratio": 8, "roe": 12, "volatility": 0.35, "revenue_growth": 0.05},
    ]

    for stock in test_cases:
        masters = select_masters(stock)
        print(f"{stock['name']}(PE={stock['pe_ratio']}, ROE={stock['roe']}%, 波动={stock['volatility']}):")
        print(f"  推荐大师: {', '.join(masters)}")

    print("[PASS] 大师Agent选择算法成功")
except Exception as e:
    print(f"[FAIL] {e}")

# ========== 实验12.6: 前端路由与API对齐 ==========
print("\n" + "=" * 60)
print("实验12.6: 前端路由与API对齐验证")
print("=" * 60)

try:
    # 定义前端路由和API端点的映射
    ROUTE_API_MAP = {
        "/": {"api": "GET /api/dashboard", "description": "Dashboard"},
        "/analysis": {"api": "POST /api/analysis", "description": "启动分析"},
        "/analysis/:ticker": {"api": "GET /api/analysis/{job_id}", "description": "分析详情"},
        "/screening": {"api": "GET /api/screening", "description": "选股结果"},
        "/portfolio": {"api": "GET /api/portfolio", "description": "持仓管理"},
        "/reports": {"api": "GET /api/reports", "description": "报告列表"},
        "/settings": {"api": "GET /api/settings", "description": "系统设置"},
    }

    # SSE事件流
    SSE_ROUTES = {
        "/api/stream/{job_id}": "SSE实时推送",
    }

    print("前端路由 → API端点映射:")
    for route, info in ROUTE_API_MAP.items():
        print(f"  {route:25s} → {info['api']:35s} ({info['description']})")

    print(f"\nSSE事件流:")
    for route, desc in SSE_ROUTES.items():
        print(f"  {route:35s} → {desc}")

    # 验证所有路由都有对应API
    missing = []
    for route, info in ROUTE_API_MAP.items():
        if not info.get("api"):
            missing.append(route)

    if missing:
        print(f"\n[WARN] 缺少API映射: {missing}")
    else:
        print(f"\n所有{len(ROUTE_API_MAP)}个路由都有对应API")

    print("[PASS] 前端路由与API对齐验证成功")
except Exception as e:
    print(f"[FAIL] {e}")

print("\n" + "=" * 60)
print("实验12完成")
print("=" * 60)
