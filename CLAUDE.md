# ra-killer

NYC event aggregator + recommendation system. Scrapes 6 sources, deduplicates, scores with Claude, delivers via Telegram and Twilio IVR.

## Dev Commands
- `uv sync` — install deps
- `uv run python scripts/scrape_once.py` — one-shot scrape
- `uv run python scripts/recommend_once.py` — one-shot recommendation
- `uv run pytest` — run tests
- `uv run python -m src.main` — start full app (scheduler + webhooks)

## Architecture
- `src/scrapers/` — 6 async scrapers (RA, DICE, Partiful, Basement, L&S, NYC Noise)
- `src/recommend/` — heuristic pre-filter + Claude batch scoring
- `src/bot/` — Telegram bot + Twilio IVR
- `src/notify/` — failure alerting
- All scrapers inherit from BaseScraper, return list[ScrapedEvent]
- Supabase for persistence (raw_events, events, taste_profile, recommendations, scrape_logs, alert_log)
