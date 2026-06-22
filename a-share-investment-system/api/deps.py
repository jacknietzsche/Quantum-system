"""FastAPI 依赖注入"""

from collections.abc import Generator

from providers.cache import CacheManager
from providers.llm import LLMCaller
from providers.market_data import MarketDataProvider
from shared.config import config
from shared.db_session import db_session


def get_db() -> Generator:
    """FastAPI 依赖: 获取数据库会话 (自动提交/回滚/关闭)"""
    with db_session() as session:
        yield session


def get_config():
    return config


def get_cache():
    return CacheManager()


def get_market_provider():
    return MarketDataProvider(cache_manager=CacheManager())


def get_llm():
    return LLMCaller(config=config)
