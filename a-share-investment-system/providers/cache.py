"""缓存管理 — 内存 TTL + LLM 文件缓存"""

import hashlib
import json
import os
import threading
import time
from typing import Any

from shared.logging import emit_log


class CacheManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._store: dict = {}
        self._lock = threading.Lock()
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._llm_cache_dir = os.path.join(base, "data", "test_cache")
        os.makedirs(self._llm_cache_dir, exist_ok=True)

    # ── 内存 TTL 缓存 ──

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry and entry["expires"] > time.time():
                return entry["value"]
            if entry:
                del self._store[key]
        return None

    def get_or_stale(self, key: str, stale_seconds: int = 300) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            now = time.time()
            if entry["expires"] > now:
                return entry["value"]
            if entry.get("stale_until", 0) > now:
                return entry["value"]
            del self._store[key]
        return None

    def set(self, key: str, value: Any, ttl_seconds: int = 60, stale_seconds: int = 300):
        with self._lock:
            self._store[key] = {
                "value": value,
                "expires": time.time() + ttl_seconds,
                "stale_until": time.time() + ttl_seconds + stale_seconds,
            }

    def invalidate(self, key: str | None = None):
        with self._lock:
            if key:
                self._store.pop(key, None)
            else:
                self._store.clear()

    # ── LLM 文件缓存 ──

    def _hash_key(self, prompt: str, context: dict | None, category: str) -> str:
        raw = f"{category}:{prompt}:{json.dumps(context or {}, sort_keys=True, default=str)}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def llm_get(
        self, prompt: str, context: dict | None = None, category: str = "general"
    ) -> str | None:
        h = self._hash_key(prompt, context, category)
        fp = os.path.join(self._llm_cache_dir, f"llm_{h}.json")
        if os.path.exists(fp):
            try:
                with open(fp, encoding="utf-8") as f:
                    data = json.load(f)
                return str(data.get("response")) if isinstance(data, dict) else None
            except Exception as e:
                emit_log("WARNING", "cache", f"Cache operation failed: {str(e)[:80]}")
        return None

    def llm_set(
        self, prompt: str, response: str, context: dict | None = None, category: str = "general"
    ):
        h = self._hash_key(prompt, context, category)
        fp = os.path.join(self._llm_cache_dir, f"llm_{h}.json")
        try:
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(
                    {"prompt": prompt, "response": response, "category": category},
                    f,
                    ensure_ascii=False,
                )
        except Exception as e:
            emit_log("WARNING", "cache", f"Operation failed: {str(e)[:100]}")

    def clear_all(self):
        self.invalidate()
        import shutil

        if os.path.exists(self._llm_cache_dir):
            shutil.rmtree(self._llm_cache_dir, ignore_errors=True)
            os.makedirs(self._llm_cache_dir, exist_ok=True)
