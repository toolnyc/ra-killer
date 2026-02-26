from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from src.bot.telegram import get_app
from src.bot.twilio_ivr import router as twilio_router
from src.config import settings
from src.log import get_logger
from src.scheduler import create_scheduler

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start scheduler
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("scheduler_started")

    # Start Telegram polling in background
    tg_app = None
    if settings.telegram_bot_token:
        try:
            tg_app = get_app()
            await tg_app.initialize()
            await tg_app.start()
            await tg_app.updater.start_polling()
            logger.info("telegram_polling_started")
        except Exception:
            logger.exception("telegram_startup_failed")
            tg_app = None
    else:
        logger.warning("telegram_not_configured")

    yield

    # Shutdown
    if tg_app:
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()
    scheduler.shutdown()
    logger.info("shutdown_complete")


app = FastAPI(title="ra-killer", lifespan=lifespan)
app.include_router(twilio_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


def main():
    logger.info("starting", base_url=settings.base_url, log_level=settings.log_level)
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
