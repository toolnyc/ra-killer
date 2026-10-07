> **Where things live** - Client: - | Bucket: `lab/` | Dropbox: `-` | Registry: Notion "Repos" DB (IDs in `~/Code/toolhub/CoS/NOTION.md`)

@import /Users/pete/Code/.agent/conventions.md

# ra-killer — Agent Instructions

NYC event aggregator + dancefloor hotline. Scrapes 6 sources, deduplicates, delivers via Telegram. The Twilio IVR hotline reads operator-set messages (set via Telegram, no LLM in the path); the recommendation engine is off (dormant code in src/recommend/, no callers).

## Commands

- `uv sync` — install deps
- `uv run python scripts/scrape_once.py` — one-shot scrape
- `uv run pytest` — run tests
- `uv run python -m src.main` — start full app (scheduler + webhooks)

## Architecture

- `src/scrapers/` — 6 async scrapers (RA, DICE, Partiful, Basement, L&S, NYC Noise)
- `src/recommend/` — dormant scoring code (no callers; kept for possible reuse)
- Hotline messages live in the `hotline_messages` table (slots: `main`, `party`); DDL in `scripts/hotline_messages.sql`
- `src/bot/` — Telegram bot + Twilio IVR
- `src/notify/` — failure alerting
- All scrapers inherit from BaseScraper, return list[ScrapedEvent]
- Supabase for persistence (raw_events, events, taste_profile, hotline_messages, scrape_logs, alert_log; weekly_scripts/recommendations/party_voice_note remain as untouched archives)

## Service Integration Notes

### Deployment
- Production runs as a systemd service on Hetzner (`ra-remote` in `~/.ssh/config`)
- Deploy: `ssh ra-remote 'cd /opt/ra-killer && git pull && sudo systemctl restart ra-killer'`
- Logs: `ssh ra-remote 'sudo journalctl -u ra-killer -n 100 --no-pager -o cat'`
- structlog uses JSONRenderer in production — exceptions only appear if `structlog.processors.format_exc_info` is in the processor chain (it is, as of this writing). Always add `error=str(exc)` to exception log calls so the message is visible even without a full traceback.

### Telegram (python-telegram-bot 21.x)
- Use `context.bot` to get the bot instance in handlers — `update.message.bot` was removed in PTB 21.x
- Use `asyncio.get_running_loop()` not `asyncio.get_event_loop()` inside async functions

### Supabase
- DB tables cannot be created via the PostgREST client — DDL requires the Supabase dashboard or migrations. Don't write code that tries to auto-create tables at startup.

### Twilio IVR
- All Twilio webhook action URLs should be absolute (`{settings.base_url}/twilio/...`).
