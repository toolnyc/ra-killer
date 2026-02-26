from __future__ import annotations

import asyncio
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src import db
from src.bot.telegram import send_daily_recommendations, send_weekend_preview
from src.log import get_logger
from src.notify.alerts import send_alert
from src.scrapers.runner import run_scrape_pipeline

logger = get_logger("scheduler")


async def job_scrape() -> None:
    """Full scrape pipeline (6 AM + 6 PM daily)."""
    logger.info("job_scrape_start")
    try:
        new_count = await run_scrape_pipeline()
        logger.info("job_scrape_done", new_events=new_count)
    except Exception as e:
        logger.error("job_scrape_failed", error=str(e))
        await send_alert("scheduler", f"Scrape pipeline failed: {e}")


async def job_recommend() -> None:
    """Score and send daily recommendations (9 AM)."""
    logger.info("job_recommend_start")
    try:
        await send_daily_recommendations(top_n=10)
        logger.info("job_recommend_done")
    except Exception as e:
        logger.error("job_recommend_failed", error=str(e))
        await send_alert("scheduler", f"Recommendation pipeline failed: {e}")


async def job_weekend_preview() -> None:
    """Weekend preview push (Tuesday 9 PM)."""
    logger.info("job_weekend_preview_start")
    try:
        await send_weekend_preview()
        logger.info("job_weekend_preview_done")
    except Exception as e:
        logger.error("job_weekend_preview_failed", error=str(e))


async def job_cleanup() -> None:
    """Delete past events (midnight)."""
    logger.info("job_cleanup_start")
    try:
        yesterday = date.today() - timedelta(days=1)
        count = db.delete_past_events(yesterday)
        logger.info("job_cleanup_done", deleted=count)
    except Exception as e:
        logger.error("job_cleanup_failed", error=str(e))


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler."""
    scheduler = AsyncIOScheduler(job_defaults={
        'misfire_grace_time': 300,  # 5 min grace for missed windows
        'coalesce': True,           # collapse queued runs into one
        'max_instances': 1,         # never run same job concurrently
    })

    # Scrape at 6 AM and 6 PM ET
    scheduler.add_job(job_scrape, "cron", hour="6,18", minute=0, timezone="America/New_York")

    # Daily recommendations at 9 AM ET
    scheduler.add_job(job_recommend, "cron", hour=9, minute=0, timezone="America/New_York")

    # Weekend preview: Tuesday at 9 PM ET
    scheduler.add_job(
        job_weekend_preview, "cron", day_of_week="tue", hour=21, minute=0, timezone="America/New_York"
    )

    # Cleanup at midnight ET
    scheduler.add_job(job_cleanup, "cron", hour=0, minute=0, timezone="America/New_York")

    return scheduler
