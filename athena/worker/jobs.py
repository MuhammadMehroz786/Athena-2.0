import logging
from athena.db.engine import get_sessionmaker
from athena.db.models import Event

logger = logging.getLogger(__name__)


async def detect_event(ctx, event_id: str) -> dict:
    Session = get_sessionmaker()
    async with Session() as session:
        event = await session.get(Event, event_id)
        if event is None:
            raise ValueError(f"Event {event_id} not found")
        logger.info("detect_event ran for event_id=%s", event_id)
        return {"event_id": event_id, "status": "detected_stub"}
