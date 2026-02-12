# ra-killer TODO

## Setup (do these yourself)

- [ ] Create Supabase project at supabase.com
- [ ] Run `scripts/setup_supabase.sql` in Supabase SQL editor
- [ ] Copy `.env.example` to `.env` and fill in `SUPABASE_URL` + `SUPABASE_KEY`
- [ ] Create Telegram bot via @BotFather, add token to `.env`
- [ ] Send any message to the bot, then get your chat ID (use `https://api.telegram.org/bot<TOKEN>/getUpdates`)
- [ ] Add `ANTHROPIC_API_KEY` to `.env`
- [ ] Buy Twilio number, add creds to `.env`

## Hetzner CX22 Deployment — `api.clubstack.net`

### 1. Provision server
- [ ] Create CX22 (2 vCPU / 4 GB) at console.hetzner.cloud
- [ ] Select Ubuntu 24.04, add your SSH key
- [ ] Note the public IPv4 address

### 2. DNS
- [ ] Add A record: `api.clubstack.net` → Hetzner IPv4
- [ ] Wait for propagation (`dig api.clubstack.net` shows the IP)

### 3. Server hardening
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

### 4. Install dependencies
```bash
ssh deploy@<IP>
sudo apt install -y python3 python3-venv python3-dev git build-essential
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

### 5. Install Caddy
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

### 6. Deploy app
```bash
sudo mkdir -p /opt/ra-killer && sudo chown deploy:deploy /opt/ra-killer
git clone <your-repo-url> /opt/ra-killer
cd /opt/ra-killer
uv sync
```
- [ ] Verify `/opt/ra-killer/.venv/bin/python --version` works

### 7. Configure secrets
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

### 8. Start the service
```bash
sudo cp /opt/ra-killer/deploy/ra-killer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ra-killer
sudo systemctl start ra-killer
```

### 9. Configure Twilio webhooks
- [ ] In Twilio console, set voice webhook to `https://api.clubstack.net/twilio/voice` (POST)
- [ ] Set status callback to `https://api.clubstack.net/twilio/gather` if needed

### 10. Verify
- [ ] `curl https://api.clubstack.net/health` returns 200
- [ ] `journalctl -u ra-killer -f` — no errors
- [ ] Send `/start` to Telegram bot — responds
- [ ] Call Twilio number — IVR flow works
- [ ] Wait for scheduled scrape (6 AM / 6 PM ET) or run manually on server

### Ongoing ops

| Task | Command |
|---|---|
| View logs | `journalctl -u ra-killer -f` |
| Restart | `sudo systemctl restart ra-killer` |
| Deploy update | `cd /opt/ra-killer && git pull && uv sync && sudo systemctl restart ra-killer` |
| Caddy logs | `journalctl -u caddy -f` |

## Prompts to send Claude

### 1. First scrape test
```
Run scrape_once.py and fix whatever breaks. The scrapers are hitting real websites so expect some to need adjustments based on the actual HTML/API responses. Fix each scraper until we get real events from at least RA, DICE, and NYC Noise.
```

### 2. Seed taste profile
```
Edit scripts/seed_taste.py with my actual taste preferences (I'll tell you what I like), then run it against Supabase.
```

### 3. Test recommendations
```
Run recommend_once.py and fix whatever breaks. Make sure the heuristic scoring works against real events, and test the Claude batch scoring call.
```

### 4. Telegram bot smoke test
```
Start the app with `uv run python -m src.main` and test the Telegram bot — send /start, /upcoming, /status. Fix any issues. Then trigger a manual recommendation push and verify inline keyboards work.
```

### 5. Twilio IVR test
```
Test the Twilio IVR locally using ngrok. Start the app, run `ngrok http 8000`, point Twilio webhook to the ngrok URL, and call the number. Fix the voice flow.
```

### 6. Deploy to Hetzner
```
Help me deploy to Hetzner. I have a CX22 with Ubuntu and api.clubstack.net pointed at it. Set up: clone repo, install uv, uv sync, configure .env, install the systemd service, set up Caddy reverse proxy with auto-HTTPS, and verify everything runs.
```

### 7. Hardening pass
```
Do a hardening pass: add request timeouts to all scrapers, make sure scraper failures don't crash the pipeline, add proper error messages to the Telegram bot, and make sure the scheduler recovers from transient failures.
```
