from arq.connections import RedisSettings
from athena.config import get_settings
from athena.worker.jobs import detect_event


class WorkerSettings:
    functions = [detect_event]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    job_timeout = 30
