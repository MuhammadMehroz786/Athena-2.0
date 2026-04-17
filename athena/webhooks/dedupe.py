from redis.asyncio import Redis

TTL_SECONDS = 24 * 60 * 60


def _key(vendor: str, vendor_event_id: str) -> str:
    return f"wh:seen:{vendor}:{vendor_event_id}"


async def already_seen(redis: Redis, *, vendor: str, vendor_event_id: str) -> bool:
    return bool(await redis.exists(_key(vendor, vendor_event_id)))


async def mark_seen(redis: Redis, *, vendor: str, vendor_event_id: str) -> None:
    await redis.set(_key(vendor, vendor_event_id), "1", ex=TTL_SECONDS)
