# ra-killer TODO

*Last updated: 2026-02-12*

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

## Up Next

### Deploy to Hetzner CX22 — `api.clubstack.net`

#### 1. Provision server
- [ ] Create CX22 (2 vCPU / 4 GB) at console.hetzner.cloud
- [ ] Select Ubuntu 24.04, add your SSH key
- [ ] Note the public IPv4 address

#### 2. DNS
- [ ] Add A record: `api.clubstack.net` → Hetzner IPv4
- [ ] Wait for propagation (`dig api.clubstack.net` shows the IP)

#### 3. Server hardening
```bash
ssh root@<IP>
apt update && apt upgrade -y
adduser --disabled-password --gecos "" deploy
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
usermod -aG sudo deploy
echo "deploy ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/deploy
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw enable
sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart sshd
```
- [ ] Verify `ssh deploy@<IP>` works before logging out of root

#### 4. Install dependencies
```bash
ssh deploy@<IP>
sudo apt install -y python3 python3-venv python3-dev git build-essential
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

#### 5. Install Caddy
```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

Write `/etc/caddy/Caddyfile`:
```
api.clubstack.net {
    reverse_proxy localhost:8000
}
```

```bash
sudo systemctl reload caddy
```
- [ ] Caddy auto-provisions TLS via Let's Encrypt once DNS is live

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
- [ ] Hardening pass: request timeouts on all scrapers, scraper failure isolation, Telegram error messages, scheduler recovery from transient failures
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
