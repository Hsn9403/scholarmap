"""
Simple JSON-based cache for API responses.
"""
import json
import hashlib
from pathlib import Path
from typing import Optional, Any, Dict
from datetime import datetime, timedelta

from src.logger import logger


class SimpleCache:
    """
    File-based JSON cache with TTL support.

    Each API call is cached with a hash of the request parameters.
    """

    def __init__(self, cache_dir: str = ".cache/pathfinding", ttl_days: int = 30):
        """
        Initialize cache.

        Args:
            cache_dir: Directory to store cache files.
            ttl_days: Time-to-live in days for cache entries.
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(days=ttl_days)

        logger.debug(f"Cache initialized: {self.cache_dir} (TTL: {ttl_days} days)")

    def _make_key(self, namespace: str, params: Dict[str, Any]) -> str:
        """Generate cache key from namespace and params."""
        # Sort params for consistent hashing
        params_str = json.dumps(params, sort_keys=True)
        hash_obj = hashlib.md5(f"{namespace}:{params_str}".encode())
        return hash_obj.hexdigest()

    def _get_cache_path(self, key: str) -> Path:
        """Get cache file path for a key."""
        return self.cache_dir / f"{key}.json"

    def get(self, namespace: str, params: Dict[str, Any]) -> Optional[Any]:
        """
        Get cached value if exists and not expired.

        Args:
            namespace: Cache namespace (e.g., "openalex_author").
            params: Request parameters dict.

        Returns:
            Cached value or None if not found/expired.
        """
        key = self._make_key(namespace, params)
        cache_path = self._get_cache_path(key)

        if not cache_path.exists():
            return None

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Check expiry
            cached_at = datetime.fromisoformat(data["cached_at"])
            if datetime.now() - cached_at > self.ttl:
                logger.debug(f"Cache expired: {key}")
                cache_path.unlink()
                return None

            logger.debug(f"Cache hit: {namespace} ({key[:8]})")
            return data["value"]

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Invalid cache file {key}: {e}")
            cache_path.unlink()
            return None

    def set(self, namespace: str, params: Dict[str, Any], value: Any):
        """
        Cache a value.

        Args:
            namespace: Cache namespace.
            params: Request parameters dict.
            value: Value to cache (must be JSON-serializable).
        """
        key = self._make_key(namespace, params)
        cache_path = self._get_cache_path(key)

        try:
            data = {
                "namespace": namespace,
                "params": params,
                "value": value,
                "cached_at": datetime.now().isoformat()
            }

            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Cached: {namespace} ({key[:8]})")

        except (TypeError, ValueError) as e:
            logger.warning(f"Failed to cache {namespace}: {e}")

    def clear(self):
        """Clear all cache files."""
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
            count += 1

        logger.info(f"Cleared {count} cache files")
