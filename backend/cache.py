import time
import threading
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple

class TTLCache:
    """Thread-safe in-memory cache with per-key TTL (Time-To-Live)."""

    def __init__(self, default_ttl: float = 4.0):
        self.default_ttl = float(default_ttl)
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._lock = threading.RLock()

    def get(self, key: str, default: Any = None) -> Any:
        now = time.time()
        with self._lock:
            if key in self._cache:
                value, expires_at = self._cache[key]
                if now < expires_at:
                    return value
                else:
                    del self._cache[key]
            return default

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        duration = self.default_ttl if ttl is None else float(ttl)
        expires_at = time.time() + duration
        with self._lock:
            self._cache[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> int:
        with self._lock:
            keys_to_del = [k for k in self._cache if k.startswith(prefix)]
            for k in keys_to_del:
                del self._cache[k]
            return len(keys_to_del)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def cleanup_expired(self) -> int:
        """Prune all expired entries."""
        now = time.time()
        with self._lock:
            expired = [k for k, (_, exp) in self._cache.items() if now >= exp]
            for k in expired:
                del self._cache[k]
            return len(expired)

# Shared global cache instance for system telemetry & hardware stats
system_cache = TTLCache(default_ttl=4.0)

def cached(ttl: float = 4.0, key_prefix: Optional[str] = None):
    """
    Decorator for caching function results with a short-lived TTL.
    Prevents repeated expensive shell / subprocess calls from thrashing CPU and latency.
    """
    def decorator(func: Callable):
        prefix = key_prefix or func.__qualname__
        lock = threading.RLock()

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Build cache key from function identity and arguments
            if not args and not kwargs:
                cache_key = prefix
            else:
                arg_repr = repr(args) + repr(sorted(kwargs.items()))
                cache_key = f"{prefix}:{arg_repr}"

            cached_val = system_cache.get(cache_key)
            if cached_val is not None:
                return cached_val

            with lock:
                # Double-check inside lock
                cached_val = system_cache.get(cache_key)
                if cached_val is not None:
                    return cached_val

                result = func(*args, **kwargs)
                if result is not None:
                    system_cache.set(cache_key, result, ttl=ttl)
                return result

        def invalidate():
            system_cache.invalidate_prefix(prefix)

        wrapper.invalidate = invalidate
        return wrapper

    return decorator
