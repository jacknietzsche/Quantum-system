"""轻量级依赖注入容器 — 服务注册 + 单例管理 + Mock 支持

用法:
    from shared.container import Container, inject

    # 注册服务
    Container.register("portfolio_service", PortfolioService)

    # 获取服务
    svc = Container.get("portfolio_service")

    # 测试时注入 mock
    Container.register("portfolio_service", MockPortfolioService)

    # 或用装饰器自动注册
    @inject("db_session")
    def my_endpoint(db):
        ...
"""

import logging
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class ServiceContainer:
    """轻量级服务容器 — 单例 + 工厂 + Mock 支持"""

    _instance: "ServiceContainer | None" = None
    _lock = threading.Lock()

    _services: dict[str, Any]
    _factories: dict[str, Callable[..., Any]]
    _singletons: dict[str, Any]
    _mocks: dict[str, Any]

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # 单例只初始化一次; 使用 hasattr 避免重复
        if not hasattr(self, "_services"):
            self._services = {}
            self._factories = {}
            self._singletons = {}
            self._mocks = {}

    def register(self, name: str, service_or_factory: Any, singleton: bool = True):
        """注册服务

        Args:
            name: 服务名称 (如 "portfolio_service", "db_session")
            service_or_factory: 服务类、实例或工厂函数
            singleton: 是否单例模式 (默认 True)
        """
        if callable(service_or_factory) and not isinstance(service_or_factory, type):
            # 工厂函数
            self._factories[name] = service_or_factory
        elif isinstance(service_or_factory, type):
            # 类 — 包装为工厂
            self._factories[name] = service_or_factory
        else:
            # 实例
            self._singletons[name] = service_or_factory
        if singleton and name not in self._singletons:
            pass  # Will be created on first get()

    def register_instance(self, name: str, instance: Any):
        """注册实例 (直接注册, 不经过工厂)"""
        self._singletons[name] = instance

    def register_factory(self, name: str, factory: Callable[..., Any]):
        """注册工厂函数 (每次 get() 都调用)"""
        self._factories[name] = factory

    def get(self, name: str) -> Any:
        """获取服务实例

        优先级: Mock > 单例缓存 > 工厂创建
        """
        # 1. Mock 优先 (测试模式)
        if name in self._mocks:
            return self._mocks[name]

        # 2. 单例缓存
        if name in self._singletons:
            return self._singletons[name]

        # 3. 工厂创建
        if name in self._factories:
            instance = self._factories[name]()
            self._singletons[name] = instance
            return instance

        available = (
            set(self._factories.keys()) | set(self._singletons.keys()) | set(self._mocks.keys())
        )
        raise KeyError(f"Service '{name}' not registered. Available: {list(available)}")

    def set_mock(self, name: str, mock_instance: Any):
        """设置 Mock (测试用)"""
        self._mocks[name] = mock_instance

    def clear_mocks(self):
        """清除所有 Mock"""
        self._mocks.clear()

    def reset(self):
        """重置容器 (测试 tearDown 用)"""
        self._singletons.clear()
        self._mocks.clear()

    def list_services(self) -> dict[str, str]:
        """列出所有注册的服务"""
        result = {}
        for name in set(list(self._factories.keys()) + list(self._singletons.keys())):
            if name in self._mocks:
                result[name] = "mocked"
            elif name in self._singletons:
                result[name] = "singleton"
            elif name in self._factories:
                result[name] = "factory"
        return result


# ── 全局容器单例 ──
Container = ServiceContainer()


def inject(service_name: str):
    """装饰器: 自动注入服务到函数参数

    用法:
        @inject("portfolio_service")
        def get_holdings(svc=None):
            return svc.get_holdings()
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            if service_name not in kwargs:
                kwargs[service_name] = Container.get(service_name)
            return func(*args, **kwargs)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator


def init_container():
    """初始化容器 — 注册核心服务 (server startup 时调用)"""
    # DB Session 工厂
    Container.register_factory(
        "db_session_factory",
        lambda: __import__("shared.models", fromlist=["get_session"]).get_session,
    )

    # 数据总线
    Container.register(
        "data_bus",
        lambda: __import__(
            "services.data_bus", fromlist=["DatabaseBackedDataBus"]
        ).DatabaseBackedDataBus(),
    )

    # 绩效引擎
    Container.register(
        "performance_engine",
        lambda: __import__(
            "services.performance", fromlist=["get_performance_engine"]
        ).get_performance_engine(),
    )

    # 通知器
    Container.register_factory("notifier", lambda: __import__("services.notifier"))

    logger.info("[Container] Initialized %d services", len(Container.list_services()))
