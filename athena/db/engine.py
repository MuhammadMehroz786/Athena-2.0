from functools import lru_cache
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from athena.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


def get_sessionmaker():
    return async_sessionmaker(get_engine(), expire_on_commit=False)
