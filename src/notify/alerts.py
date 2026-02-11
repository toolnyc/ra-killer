from __future__ import annotations

import httpx

from src import db
from src.config import settings
from src.log import get_logger

logger = get_logger("alerts")


async def send_alert(source: str, message: str) -> None:
    """Send a failure alert via Telegram DM (rate-limited)."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("alert_skipped_no_telegram", source=source, message=message)
        return

    if not db.should_alert(source):
        logger.debug("alert_rate_limited", source=source)
        return

    text = f"[ra-killer alert] {source}: {message}"

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": text,
                },
            )
        db.log_alert(source, message)
        logger.info("alert_sent", source=source)
    except Exception as e:
        logger.error("alert_send_failed", source=source, error=str(e))
