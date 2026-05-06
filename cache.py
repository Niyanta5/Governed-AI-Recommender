import time
import hashlib

CACHE_TTL_SECONDS = 600

_cache = {}


def get_cache(key):
    item = _cache.get(key)

    if not item:
        return None

    value, timestamp = item

    if time.time() - timestamp > CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None

    return value


def set_cache(key, value):
    _cache[key] = (value, time.time())


def clear_cache():
    _cache.clear()


def hash_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()