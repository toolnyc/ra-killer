# ra-killer TODO

*Last updated: 2026-02-26*

## Completed

- [x] All 6 scrapers working (RA, DICE, Partiful, Basement, L&S, NYC Noise)
- [x] Dedup pipeline with string normalization (`src/normalize.py`)
- [x] Taste profile seeded (319 artists, 57 venues) with write-path normalization
- [x] Weight clamping [-1.0, 3.0] to prevent single-artist dominance
- [x] Randomized discovery sampling in heuristic pre-filter
- [x] Heuristic score normalization fix in ranker
- [x] Stripped genre/vibe from taste profile (artist + venue only)
- [x] Telegram bot with resilient duplicate-button-press handling
- [x] Training pipeline (`/train N`) operational with 494+ past events
- [x] Historical RA backfill script (`scripts/backfill_ra.py`)
- [x] 78 tests passing
- [x] Hardening pass: per-scraper 120s timeout, scraper failure alerts, Telegram command error handling, scheduler misfire/coalesce/max_instances

## Up Next

### Deploy to Hetzner CX22 — `api.clubstack.net`

#### 1. Provision server
- [x] Create CX22 (2 vCPU / 4 GB) at console.hetzner.cloud — `89.167.49.1`
- [x] Select Ubuntu 24.04, add SSH key (`ra-hetz`)
- [x] Note the public IPv4 address

#### 2. DNS
- [x] Add A record: `api.clubstack.net` → `89.167.49.1`
- [x] Wait for propagation (`dig api.clubstack.net` shows the IP)

#### 3. Server hardening
- [x] Created `deploy` user with SSH key + passwordless sudo
- [x] Firewall (ufw): SSH, 80, 443 only
- [x] Root login disabled, password auth disabled (key-only)
- [x] Verified `ssh -i ~/.ssh/ra-hetz deploy@89.167.49.1` works

#### 4. Install dependencies
- [x] Python 3, build-essential, git installed
- [x] uv installed

#### 5. Install Caddy
- [x] Caddy installed + configured for `api.clubstack.net` → `localhost:8000`
- [x] TLS auto-provisions via Let's Encrypt once DNS is live

#### 6. Deploy app
```bash
sudo mkdir -p /opt/ra-killer && sudo chown deploy:deploy /opt/ra-killer
git clone https://github.com/toolnyc/ra-killer.git /opt/ra-killer
cd /opt/ra-killer
uv sync
```
- [ ] Verify `/opt/ra-killer/.venv/bin/python --version` works

#### 7. Configure secrets
```bash
cp .env.example /opt/ra-killer/.env
nano /opt/ra-killer/.env
chmod 600 /opt/ra-killer/.env
```

| Variable | Value |
|---|---|
| `SUPABASE_URL` | `https://<project>.supabase.co` |
| `SUPABASE_KEY` | service_role key from Supabase dashboard |
| `ANTHROPIC_API_KEY` | from console.anthropic.com |
| `TELEGRAM_BOT_TOKEN` | from @BotFather |
| `TELEGRAM_CHAT_ID` | from /getUpdates |
| `TWILIO_ACCOUNT_SID` | from Twilio console |
| `TWILIO_AUTH_TOKEN` | from Twilio console |
| `TWILIO_PHONE_NUMBER` | your Twilio number |
| `BASE_URL` | `https://api.clubstack.net` |
| `LOG_LEVEL` | `INFO` |

#### 8. Start the service
```bash
sudo cp /opt/ra-killer/deploy/ra-killer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ra-killer
sudo systemctl start ra-killer
```

#### 9. Configure Twilio webhooks
- [ ] In Twilio console, set voice webhook to `https://api.clubstack.net/twilio/voice` (POST)
- [ ] Set status callback to `https://api.clubstack.net/twilio/gather` if needed

#### 10. Verify
- [ ] `curl https://api.clubstack.net/health` returns 200
- [ ] `journalctl -u ra-killer -f` — no errors
- [ ] Send `/start` to Telegram bot — responds
- [ ] Call Twilio number — IVR flow works
- [ ] Wait for scheduled scrape (6 AM / 6 PM ET) or run manually on server

### Post-Deploy

- [ ] Run several `/train` rounds via Telegram to calibrate taste weights
- [x] Hardening pass: request timeouts on all scrapers, scraper failure isolation, Telegram error messages, scheduler recovery from transient failures
- [ ] Twilio IVR smoke test (call the number, verify voice flow end-to-end)

### Future Improvements (deferred)

- [ ] Time decay on taste weights (old preferences never fade)
- [ ] Feed Claude-returned tags back into taste profile (learn genre/vibe from feedback)

## Ongoing Ops

| Task | Command |
|---|---|
| View logs | `journalctl -u ra-killer -f` |
| Restart | `sudo systemctl restart ra-killer` |
| Deploy update | `cd /opt/ra-killer && git pull && uv sync && sudo systemctl restart ra-killer` |
| Caddy logs | `journalctl -u caddy -f` |
