from functools import lru_cache
from arq.connections import RedisSettings
from athena.config import get_settings
from athena.worker.jobs import detect_event


@lru_cache(maxsize=1)
def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class _LazyRedisSettings:
    """Descriptor that defers RedisSettings construction until access.

    Arq reads WorkerSettings.redis_settings via attribute access at CLI
    startup; this descriptor makes the lookup lazy so importing the module
    without REDIS_URL in the environment does not raise.
    """

    def __get__(self, obj, objtype=None):
        return _redis_settings()


class WorkerSettings:
    functions = [detect_event]
    redis_settings = _LazyRedisSettings()
    max_jobs = 10
    job_timeout = 30
