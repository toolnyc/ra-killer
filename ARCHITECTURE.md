# ra-killer Architecture Guide

A plain-English guide to how this whole system works, how to keep it running, and how to fix things when they break.

## What is this thing?

ra-killer is a robot that finds NYC nightlife events for you. Twice a day it checks 6 different event websites and removes duplicates. You can also call a phone number — the Clubstack hotline — and hear two operator-set messages read aloud: press 1 for the dancefloor message, press 2 for the dangerous illicit techno party message. Both messages are set verbatim via Telegram commands (`/set_main`, `/set_party`); there is no LLM in the hotline path.

The recommendation engine is currently off. The scoring code still lives in `src/recommend/` but nothing calls it, and no recommendations are generated or sent.

## The server

- **IP:** `89.167.49.1`
- **Domain:** `api.clubstack.net`
- **Provider:** Hetzner Cloud (CX22 — 2 vCPU, 4 GB RAM, Ubuntu 24.04)
- **SSH key name:** `ra-hetz`

### How to get in

```bash
ssh -i ~/.ssh/ra-hetz deploy@89.167.49.1
```

You log in as `deploy`, not `root`. Root login is disabled. Password login is disabled. You **must** have the `ra-hetz` private key on your machine.

### If you get locked out

**"Permission denied (publickey)"** — Your key isn't being sent or isn't on the server.

1. Go to https://console.hetzner.cloud
2. Click on your server, then click **Console** (the web-based terminal)
3. Log in with the root password (Hetzner shows this when you create/rebuild the server — if you don't have it, use **Rescue > Reset Root Password** in the Hetzner panel)
4. Add your public key back:
   ```bash
   # Get your public key from your laptop:
   cat ~/.ssh/ra-hetz.pub
   # Paste it into the server (the web console supports short pastes,
   # or use a paste service like ix.io — see tip below)
   echo "YOUR_KEY" >> /home/deploy/.ssh/authorized_keys
   chown deploy:deploy /home/deploy/.ssh/authorized_keys
   ```

**Paste-service trick** (for keys too long to paste into the web console):
```bash
# On your laptop:
cat ~/.ssh/ra-hetz.pub | curl -F 'f:1=<-' ix.io
# That gives you a short URL. Then on the server web console:
curl https://ix.io/XXXX >> /home/deploy/.ssh/authorized_keys
```

**"WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED"** — You rebuilt the server so it has a new fingerprint. Fix it:
```bash
ssh-keygen -R 89.167.49.1
```
Then SSH in again.

**Lost the `ra-hetz` key entirely** — Generate a new one (`ssh-keygen -t ed25519 -f ~/.ssh/ra-hetz`), then use the Hetzner web console to add the new public key as described above.

## How the pieces fit together

```
                         Internet
                            |
                     ┌──────┴──────┐
                     │   Caddy     │  (reverse proxy — handles HTTPS)
                     │   :80/:443  │
                     └──────┬──────┘
                            |
                     ┌──────┴──────┐
                     │  FastAPI    │  (the app — src/main.py)
                     │   :8000    │
                     └──────┬──────┘
                            |
            ┌───────┬───────┼───────┬──────────┐
            |       |       |       |          |
        Scheduler  Telegram  Twilio  Health   Supabase
         (cron)    (polling)  (IVR)  (/health)  (DB)
```

### Caddy (the front door)

Caddy is a web server that sits in front of the app. Its only job is:
- Accept HTTPS traffic from the internet on ports 80/443
- Forward it to the app on port 8000
- Automatically get and renew TLS certificates (so you never think about SSL)

Config lives at `/etc/caddy/Caddyfile`. You almost never need to touch it.

```bash
# Check if Caddy is running
sudo systemctl status caddy

# View Caddy logs
journalctl -u caddy -f

# Restart Caddy
sudo systemctl restart caddy
```

### The app (src/main.py)

This is the brain. When it starts up, it does three things at once:
1. **Starts the scheduler** — cron jobs that scrape and recommend on a schedule
2. **Starts the Telegram bot** — listens for your messages
3. **Starts the web server** — handles Twilio calls and health checks

It runs as a systemd service, which means Linux keeps it alive automatically — if it crashes, it restarts in 10 seconds.

```bash
# Check if the app is running
sudo systemctl status ra-killer

# View live logs
journalctl -u ra-killer -f

# Restart the app
sudo systemctl restart ra-killer

# Stop the app
sudo systemctl stop ra-killer
```

### The scheduler (what runs when)

All times are Eastern (NYC time).

| Time | What happens |
|------|-------------|
| 6 AM + 6 PM | **Scrape** — hits all 6 event websites, deduplicates, stores new events |
| Tuesday 9 PM | **Weekend preview** — lists Friday-Sunday events (no scoring) |
| Midnight | **Cleanup** — deletes events that already happened |

If the server reboots and a job was missed, it catches up within 5 minutes (not instantly — that's intentional to avoid hammering everything at startup).

### The scrapers (where events come from)

Six scrapers each talk to a different event website:

| Scraper | Source | What it does |
|---------|--------|-------------|
| `ra.py` | RA.co | Hits RA's internal GraphQL API. Gets ~500 events per run. The biggest source. |
| `dice.py` | DICE.fm | Scrapes their website HTML. Gets DJ, party, and gig events. |
| `partiful.py` | Partiful | Scrapes their NYC discover page. Good for smaller/private events. |
| `basement.py` | Basement | Hits their public REST API. Two stages: basement + studio. |
| `lightandsound.py` | Light & Sound | Scrapes their website. Two-step: list page, then each event detail page. |
| `nycnoise.py` | NYC Noise | Scrapes HTML. Data hidden in HTML attributes. |

All 6 run at the same time (in parallel). Each gets a 120-second timeout. If one fails, the others still work — you just miss that source until the next run.

### Deduplication (how it avoids showing the same event twice)

The same party often appears on RA, DICE, and Partiful with slightly different names. The dedup system catches this:

1. **Exact match** — same title + date + venue (after normalizing spelling, removing "The", "DJ Set", etc.)
2. **Fuzzy match** — if 2 out of 3 are close enough (title 85%+ similar, overlapping artists, venue 90%+ similar), it's the same event
3. **Merge** — when a duplicate is found, it keeps the richest data from each source (longest artist list, best description, all source links)

### The recommendation engine (dormant)

Recommendation scoring is turned off. The code (`src/recommend/ranker.py`, `scorer.py`, `taste.py`) stays in the repo with no callers, and the old `recommendations` / `weekly_scripts` tables remain in Supabase as untouched archives. Only the midnight cleanup job still deletes old recommendation rows per its retention policy.

### Your taste profile

Stored in Supabase as a list of artist names and venue names, each with a weight. Viewable via `/taste`; editable via `/add_artist` and `/add_venue`. Nothing currently scores against it.

### Telegram bot (how you interact)

| Command | What it does |
|---------|-------------|
| `/start` | Shows help |
| `/set_main <text>` | Sets the press-1 hotline message (verbatim, max ~1500 chars) |
| `/set_party <text>` | Sets the press-2 hotline message (verbatim, max ~1500 chars) |
| `/preview_messages` | Shows both hotline messages with updated_at / updated_by |
| `/taste` | Shows your current taste profile |
| `/add_artist Honey Dijon` | Add a favorite artist (weight 2.0) |
| `/add_venue Nowadays` | Add a favorite venue (weight 2.0) |
| `/status` | Shows scraper health + event count |

### Twilio IVR (the phone hotline)

Call the Twilio number → hear the two-option greeting → press 1 to hear the "main" message, press 2 to hear the "party" message. Both are read verbatim via Polly.Emma-Neural (en-GB) from the `hotline_messages` table — no caching, so edits take effect on the next call. If a slot has no message, the caller hears "nothing is available…" and can press 0 to return to the main menu.

Twilio sends HTTP requests to `https://api.clubstack.net/twilio/voice`, `/twilio/gather`, and `/twilio/empty_nav`. Caddy routes these to the app.

### Supabase (the database)

All data lives in Supabase (hosted PostgreSQL). Key tables:

| Table | What's in it |
|-------|-------------|
| `raw_events` | Every event exactly as scraped. Never deleted. Audit trail. |
| `events` | Deduplicated "canonical" events. What the bot actually recommends from. |
| `taste_profile` | Your artist/venue preferences with weights. |
| `hotline_messages` | The two hotline messages (slots `main` and `party`), set via Telegram. |
| `scrape_logs` | Success/failure/timing for each scraper run. |
| `alert_log` | Failure alerts sent (used for rate-limiting to 1 per source per hour). |

Archived (no longer read or written, except cleanup retention deletes): `recommendations`, `weekly_scripts`, `party_voice_note`.

## File layout

```
ra-killer/
├── src/
│   ├── main.py           ← App entry point (starts everything)
│   ├── config.py          ← Loads .env settings
│   ├── db.py              ← All database operations
│   ├── models.py          ← Data shapes (Event, Recommendation, etc.)
│   ├── normalize.py       ← String cleanup for dedup + taste matching
│   ├── scheduler.py       ← Cron job definitions
│   ├── log.py             ← Logging setup
│   ├── scrapers/
│   │   ├── base.py        ← Shared scraper logic (retries, timeouts)
│   │   ├── runner.py      ← Runs all scrapers + dedup pipeline
│   │   ├── ra.py          ← RA scraper
│   │   ├── dice.py        ← DICE scraper
│   │   ├── partiful.py    ← Partiful scraper
│   │   ├── basement.py    ← Basement scraper
│   │   ├── lightandsound.py ← Light & Sound scraper
│   │   └── nycnoise.py    ← NYC Noise scraper
│   ├── recommend/
│   │   ├── scorer.py      ← Heuristic + Claude scoring (dormant)
│   │   ├── ranker.py      ← Full ranking pipeline (dormant)
│   │   └── taste.py       ← Taste profile loader (dormant)
│   ├── bot/
│   │   ├── telegram.py    ← Telegram bot commands
│   │   ├── twilio_ivr.py  ← Voice call endpoints
│   │   └── tts.py         ← Text-to-speech script builder (dormant)
│   └── notify/
│       └── alerts.py      ← Failure alerts via Telegram
├── scripts/
│   ├── scrape_once.py     ← Run scrapers manually (for testing)
│   ├── recommend_once.py  ← Run recommender manually
│   ├── seed_taste.py      ← Load initial taste profile
│   └── backfill_ra.py     ← Backfill 60 days of RA history
├── deploy/
│   └── ra-killer.service  ← systemd service config
├── tests/                 ← 78 tests
├── .env.example           ← Template for secrets
└── pyproject.toml         ← Python dependencies
```

## Day-to-day operations

### Deploying an update

```bash
ssh -i ~/.ssh/ra-hetz deploy@89.167.49.1
cd /opt/ra-killer
git pull
uv sync
sudo systemctl restart ra-killer
```

### Checking if everything is healthy

```bash
# Is the app running?
sudo systemctl status ra-killer

# Live logs (Ctrl+C to stop watching)
journalctl -u ra-killer -f

# Recent errors only
journalctl -u ra-killer --since "1 hour ago" --priority=err

# Is Caddy running?
sudo systemctl status caddy

# Health check from outside
curl https://api.clubstack.net/health
```

Or just send `/status` in Telegram — it shows scraper health and event counts.

### Running a manual scrape

```bash
cd /opt/ra-killer
uv run python scripts/scrape_once.py
```

### Editing secrets

```bash
nano /opt/ra-killer/.env
sudo systemctl restart ra-killer   # restart to pick up changes
```

### Viewing the Caddyfile

```bash
cat /etc/caddy/Caddyfile
```

### Checking the firewall

```bash
sudo ufw status
```
Should show: OpenSSH, 80, 443 allowed. Everything else blocked.

## Troubleshooting

| Problem | Likely cause | Fix |
|---------|-------------|-----|
| Bot doesn't respond to `/start` | App is down or Telegram token is wrong | `sudo systemctl status ra-killer` — check logs |
| Hotline says "nothing is available" | No message set for that slot | Set one with `/set_main` or `/set_party` in Telegram |
| "Permission denied" when SSH-ing | Wrong key or key not on server | See "If you get locked out" above |
| "Host key changed" SSH warning | Server was rebuilt | `ssh-keygen -R 89.167.49.1` then try again |
| `curl https://api.clubstack.net/health` times out | Caddy or app is down, or firewall is wrong | SSH in, check `systemctl status caddy` and `systemctl status ra-killer` |
| Scraper shows "timeout" in logs | The source website is slow or down | Usually fixes itself next run. Check `/status` |
| "ANTHROPIC_API_KEY" error in logs | API key is missing or expired | Edit `.env`, add a valid key, restart |
| "Taste profile is empty" | Never seeded | `cd /opt/ra-killer && uv run python scripts/seed_taste.py` |
| Twilio calls hang up immediately | Webhook URL wrong in Twilio console | Should be `https://api.clubstack.net/twilio/voice` (POST) |
| App keeps crash-looping | Check logs for the actual error | `journalctl -u ra-killer -n 50` — look for the traceback |
| Caddy won't start | Bad Caddyfile syntax or port 80/443 in use | `journalctl -u caddy -n 20` — usually tells you exactly what's wrong |
| DNS not working | A record not set or not propagated | `dig api.clubstack.net` — should show `89.167.49.1` |

## Secrets needed (in .env)

| Variable | Where to get it |
|----------|----------------|
| `SUPABASE_URL` | Supabase dashboard → Settings → API |
| `SUPABASE_KEY` | Same place — use the **service_role** key (not anon) |
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys |
| `TELEGRAM_BOT_TOKEN` | Telegram → @BotFather → /newbot |
| `TELEGRAM_CHAT_ID` | Send a message to your bot, then check `https://api.telegram.org/bot<TOKEN>/getUpdates` |
| `TWILIO_ACCOUNT_SID` | Twilio console |
| `TWILIO_AUTH_TOKEN` | Twilio console |
| `TWILIO_PHONE_NUMBER` | Twilio console (your purchased number, e.g. `+12125551234`) |
| `BASE_URL` | `https://api.clubstack.net` |
| `LOG_LEVEL` | `INFO` (use `DEBUG` only when troubleshooting) |
