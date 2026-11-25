"""
Cache service integrating with LiteLLM's built-in caching system.
Supports both disk-backed storage and in-memory caching.
"""
import os
import json
import logging
from typing import Optional, Any, List, Tuple
import litellm
from litellm import Cache
from litellm.caching.base_cache import BaseCache

from app.config import settings

logger = logging.getLogger(__name__)


def _normalize_cache_dir(path: str) -> str:
    """Normalize cache directory path across Docker and host environments."""
    if path.startswith("/data/") and os.name == "nt":
        path = "./data/" + path[6:]
    os.makedirs(path, exist_ok=True)
    return path


class FileDiskCache(BaseCache):
    """
    Disk-backed cache backend for LiteLLM.
    Persists model completion responses as JSON files in a dedicated cache directory.
    """
    def __init__(self, cache_dir: str):
        self.cache_dir = _normalize_cache_dir(cache_dir)

    def _file_path(self, key: str) -> str:
        # Sanitize key for filesystem filename
        safe_key = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(key))
        return os.path.join(self.cache_dir, f"{safe_key}.json")

    def get_cache(self, key: str, **kwargs) -> Optional[Any]:
        filepath = self._file_path(key)
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Error reading disk cache file %s: %s", filepath, e)
                return None
        return None

    def set_cache(self, key: str, value: Any, **kwargs) -> None:
        filepath = self._file_path(key)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(value, f)
        except Exception as e:
            logger.warning("Error writing disk cache file %s: %s", filepath, e)

    async def async_get_cache(self, key: str, **kwargs) -> Optional[Any]:
        return self.get_cache(key, **kwargs)

    async def async_set_cache(self, key: str, value: Any, **kwargs) -> None:
        self.set_cache(key, value, **kwargs)

    async def async_set_cache_pipeline(self, cache_list: List[Tuple[str, Any]], **kwargs) -> None:
        for k, v in cache_list:
            self.set_cache(k, v, **kwargs)


def initialize_cache() -> Optional[Cache]:
    """
    Initialize and register LiteLLM cache based on application settings.
    """
    if not settings.CACHE_ENABLED:
        litellm.cache = None
        logger.info("LiteLLM response caching is disabled.")
        return None

    try:
        if settings.CACHE_TYPE.lower() == "disk":
            disk_backend = FileDiskCache(settings.CACHE_DIR)
            litellm.cache = Cache(_backend=disk_backend)
            logger.info("LiteLLM response caching enabled (type: disk, dir: %s).", settings.CACHE_DIR)
        else:
            litellm.cache = Cache(type="local")
            logger.info("LiteLLM response caching enabled (type: in-memory / local).")
    except Exception as exc:
        logger.error("Failed to initialize LiteLLM cache: %s. Falling back to local cache.", exc)
        litellm.cache = Cache(type="local")

    return litellm.cache
