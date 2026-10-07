> **Where things live** - Client: - | Bucket: `lab/` | Dropbox: `-` | Registry: Notion "Repos" DB (IDs in `~/Code/toolhub/CoS/NOTION.md`)

@import /Users/pete/Code/.agent/conventions.md

# ra-killer — Agent Instructions

NYC dancefloor hotline. The operator sets messages via Telegram; the Twilio IVR reads them (no LLM in the path). The scraping/dedup pipeline and recommendation engine are off — dormant code in `src/scrapers/` and `src/recommend/`, no callers.

## Commands

- `uv sync --extra dev` — install deps
- `uv run pytest` — run tests
- `uv run python -m src.main` — start the app (Telegram polling + Twilio webhooks)

## Architecture

- `src/bot/` — Telegram bot + Twilio IVR (the only live paths)
- `src/scrapers/`, `src/recommend/` — dormant pipeline code (no callers; kept for possible reuse)
- Hotline messages live in a local SQLite `hotline_messages` table (slots: `main`, `party`), managed by `src/db.py`; DB path from `SQLITE_PATH` env var (default `/opt/ra-killer/hotline.db`)
- Supabase was removed (2026-10); no data migration — messages are re-set via Telegram (`/set_main`, `/set_party`)

## Service Integration Notes

### Deployment
- Production runs as a systemd service on Hetzner (`ra-remote` in `~/.ssh/config`)
- Deploy: `ssh ra-remote 'cd /opt/ra-killer && git pull && uv sync && sudo systemctl restart ra-killer'`
- Logs: `ssh ra-remote 'sudo journalctl -u ra-killer -n 100 --no-pager -o cat'`
- structlog uses JSONRenderer in production — exceptions only appear if `structlog.processors.format_exc_info` is in the processor chain (it is, as of this writing). Always add `error=str(exc)` to exception log calls so the message is visible even without a full traceback.

### Telegram (python-telegram-bot 21.x)
- Use `context.bot` to get the bot instance in handlers — `update.message.bot` was removed in PTB 21.x
- Use `asyncio.get_running_loop()` not `asyncio.get_event_loop()` inside async functions

### Twilio IVR
- All Twilio webhook action URLs should be absolute (`{settings.base_url}/twilio/...`).
