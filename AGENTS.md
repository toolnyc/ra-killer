@import /Users/pete/Code/.agent/conventions.md

# ra-killer — Agent Instructions

NYC event aggregator + recommendation system. Scrapes 6 sources, deduplicates, scores, delivers via Telegram and Twilio IVR.

## Commands

- `uv sync` — install deps
- `uv run python scripts/scrape_once.py` — one-shot scrape
- `uv run python scripts/recommend_once.py` — one-shot recommendation
- `uv run pytest` — run tests
- `uv run python -m src.main` — start full app (scheduler + webhooks)

## Architecture

- `src/scrapers/` — 6 async scrapers (RA, DICE, Partiful, Basement, L&S, NYC Noise)
- `src/recommend/` — heuristic pre-filter + batch scoring
- `src/bot/` — Telegram bot + Twilio IVR
- `src/notify/` — failure alerting
- All scrapers inherit from BaseScraper, return list[ScrapedEvent]
- Supabase for persistence (raw_events, events, taste_profile, recommendations, scrape_logs, alert_log)

## Service Integration Notes

### Deployment
- Production runs as a systemd service on Hetzner (`ra-remote` in `~/.ssh/config`)
- Deploy: `ssh ra-remote 'cd /opt/ra-killer && git pull && sudo systemctl restart ra-killer'`
- Logs: `ssh ra-remote 'sudo journalctl -u ra-killer -n 100 --no-pager -o cat'`
- structlog uses JSONRenderer in production — exceptions only appear if `structlog.processors.format_exc_info` is in the processor chain (it is, as of this writing). Always add `error=str(exc)` to exception log calls so the message is visible even without a full traceback.

### Telegram (python-telegram-bot 21.x)
- Use `context.bot` to get the bot instance in handlers — `update.message.bot` was removed in PTB 21.x
- `file.download_as_bytearray()` returns `bytearray`, not `bytes` — always cast: `bytes(await file.download_as_bytearray())` before passing to any library that type-checks (e.g. supabase storage3)
- Use `asyncio.get_running_loop()` not `asyncio.get_event_loop()` inside async functions

### Supabase Storage (storage3 2.x)
- `storage.from_(bucket).upload(file=...)` only accepts `bytes`, `BufferedReader`, `FileIO`, or `Path` — NOT `bytearray`. Passing `bytearray` silently falls into the file-path branch and raises `TypeError`.
- DB tables cannot be created via the PostgREST client — DDL requires the Supabase dashboard or migrations. Don't write code that tries to auto-create tables at startup.

### Twilio IVR
- **Never give Twilio a direct Supabase storage URL for `<Play>`** — Twilio struggles to fetch from Supabase CDN on real PSTN calls. Always proxy audio through the app server (`/twilio/party_audio`).
- **OGG/Opus is unreliable on Twilio PSTN calls** despite being listed as supported. Transcode to MP3 via ffmpeg before serving (ffmpeg is installed at `/usr/bin/ffmpeg`).
- **Twilio caches `<Play>` audio by URL** — append a cache-busting query param (e.g. `updated_at` timestamp) whenever the audio changes, or Twilio will keep playing the old file indefinitely.
- All Twilio webhook action URLs should be absolute (`{settings.base_url}/twilio/...`).
