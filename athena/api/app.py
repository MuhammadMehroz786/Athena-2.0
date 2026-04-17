from fastapi import FastAPI

from athena.api.routes.events import router as events_router
from athena.api.routes.webhooks import router as webhooks_router


def create_app() -> FastAPI:
    app = FastAPI(title="Athena API")

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    app.include_router(webhooks_router)
    app.include_router(events_router)
    return app
