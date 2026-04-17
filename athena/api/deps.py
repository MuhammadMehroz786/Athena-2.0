from typing import AsyncGenerator
import redis.asyncio as aioredis
from arq import create_pool
from arq.connections import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession

from athena.config import get_settings
from athena.db.engine import get_sessionmaker
from athena.worker import WorkerSettings


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    Session = get_sessionmaker()
    async with Session() as session:
        yield session


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    client = aioredis.from_url(get_settings().redis_url)
    try:
        yield client
    finally:
        await client.aclose()


_arq_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis:
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(WorkerSettings.redis_settings)
    return _arq_pool
