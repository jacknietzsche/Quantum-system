"""单元测试 — CacheManager"""

from providers.cache import CacheManager


def test_set_and_get():
    cache = CacheManager()
    cache.set("test_key", {"value": 42})
    assert cache.get("test_key") == {"value": 42}


def test_missing_key():
    cache = CacheManager()
    assert cache.get("nonexistent") is None


def test_invalidate():
    cache = CacheManager()
    cache.set("inv_key", "data")
    assert cache.get("inv_key") is not None
    cache.invalidate()
    assert cache.get("inv_key") is None
