# Polymarket News Telegram Bot

A Python Telegram bot that aggregates **Polymarket-related news** from ~25 public sources (Google News, Bing News, Reddit, Hacker News, the Polymarket blog, crypto outlets like CoinDesk / CoinTelegraph / Decrypt / The Block / Blockworks, the Polymarket X account via Nitter, YouTube, GitHub releases, and more) and pushes new items to every subscriber **every 30 minutes**.

Architecture details live in [`ARCHITECTURE.md`](../ARCHITECTURE.md:1).

---

## Features

- 📰 **~25 sources out of the box** — most need no API key.
- 🔁 **Per-user deduplication** — no duplicates across sources or bot restarts.
- ⏱ **30-minute polling cycle** with per-fetcher timeout + error isolation.
- 🧪 **Backfill cap** — new subscribers get up to 10 items from the last 24h, not months of history.
- 🛡 **Idempotent SQLite storage** — survives restarts.
- 🧱 **Pluggable fetchers** — add a new source in ~30 lines.

---

## Prerequisites

- **Python 3.11+** (3.12 also fine)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

---

## Quick start

```bash
cd poly-news-bot
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and set TELEGRAM_BOT_TOKEN=...
python bot.py
```

Then, in Telegram, find your bot and send `/start`. You'll receive Polymarket news every 30 minutes.

---

## Get a Telegram bot token

1. Open [@BotFather](https://t.me/BotFather) in Telegram.
2. Send `/newbot` and follow the prompts (pick a name and a unique username ending in `bot`).
3. BotFather will reply with an HTTP token like `123456789:ABCdefGhIJKlmnoPQRsTUVwxyz`. Copy that into `TELEGRAM_BOT_TOKEN` in your `.env`.

---

## Configuration

All configuration is via env vars (loaded from `.env`). See [`.env.example`](.env.example:1) for the full list. Highlights:

| Var | Default | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | **Required.** From @BotFather. |
| `POLL_INTERVAL_MINUTES` | `30` | How often to fetch & deliver news. |
| `BACKFILL_WINDOW_HOURS` | `24` | Brand-new subscribers see items from the past N hours, no further. |
| `MAX_ITEMS_PER_CYCLE` | `10` | Hard cap per subscriber per cycle. Prevents flooding. |
| `DATABASE_PATH` | `./data/bot.db` | SQLite database location. |
| `NITTER_MIRRORS` | `nitter.net,nitter.poast.org,nitter.privacydev.net` | Nitter mirrors to try in order. Mirrors die often — keep this updated. |
| `DISABLED_SOURCES` | (empty) | Comma-separated slugs to skip (e.g. `medium_polymarket,defillama`). |

### Optional API keys for more coverage

| Env var | Free tier? | What it enables |
|---|---|---|
| `NEWSDATA_API_KEY` | ✅ Free — 200 req/day | **Recommended free replacement for CryptoPanic.** Sign up at <https://newsdata.io/register>, grab the key from the Dashboard. |
| `MEDIASTACK_API_KEY` | ✅ Free — 100 req/**month** (very low) | Secondary aggregator. Sign up at <https://mediastack.com/signup/free>. With a 30-min poll cycle this will exhaust quota in ~2 days, so use selectively. |
| `CRYPTOPANIC_API_KEY` + `CRYPTOPANIC_API_PLAN` | ❌ **PAID since 2026-04-01** | Free Developer tier was discontinued. Now requires a paid plan (`developer`, `growth`, or `enterprise`). Pricing: <https://cryptopanic.com/developers/api/>. Set both vars; `CRYPTOPANIC_API_PLAN` must match your subscription. |
| `TWITTER_BEARER_TOKEN` | ❌ Paid | X/Twitter v2 API fetcher (paid tier required since 2024). Useful if Nitter mirrors are unreliable. |
| `GITHUB_TOKEN` | ✅ Free | Raises GitHub API rate limit from 60/hr to 5000/hr for the Polymarket org events fetcher. Any classic or fine-grained PAT works (no scopes needed for public events). |
| `POLYMARKET_YOUTUBE_CHANNEL_ID` | n/a | YouTube channel ID (UC…) for the official Polymarket channel; enables direct channel-feed polling. |

Leave any of these blank to disable the corresponding source — the bot starts up either way and logs which optional sources are skipped.

> **Note on CryptoPanic:** the free Developer API tier was discontinued on **April 1, 2026**. The fetcher has been updated to the v2 endpoint (`/api/<plan>/v2/posts/`) and is now **paid-only**. If you want a free aggregator, use `NEWSDATA_API_KEY` instead — it's the recommended drop-in replacement.

---

## Bot commands

| Command | What it does |
|---|---|
| `/start` | Subscribe to updates. |
| `/stop` | Unsubscribe (data is retained; `/start` again to resume). |
| `/status` | Your subscription state, delivery count, next-poll info. |
| `/sources` | List of every enabled news source with its slug. |
| `/help` | Show the welcome & command list. |
| `/last [N]` | Show the N (default 5, max 20) most recent news items. |
| `/ping` | Health check (uptime + UTC clock). |

---

## Project layout

```
poly-news-bot/
├── bot.py              # Entry point; PTB Application + command handlers
├── scheduler.py        # APScheduler: 30-min cycle + startup catch-up
├── aggregator.py       # Runs all fetchers concurrently, dedupes
├── dispatcher.py       # Per-subscriber delivery with rate limiting
├── storage.py          # aiosqlite wrapper
├── config.py           # Env-loaded Settings dataclass
├── fetchers/           # One module per source
├── utils/              # hashing, http, keyword filter, formatter
├── tests/              # pytest unit tests
├── data/               # SQLite DB (gitignored, auto-created)
├── requirements.txt
├── .env.example
└── README.md
```

---

## Running tests

```bash
pip install pytest pytest-asyncio
pytest tests/
```

The included tests cover URL canonicalization, keyword filtering, and the fetcher registry. They do **not** hit live HTTP — they're fast & deterministic.

---

## Deployment to Railway

[Railway](https://railway.app) is the easiest way to host this bot — it auto-detects Python via Railpack, handles restarts, and provides persistent volumes for SQLite.

### Steps

1. **Push to GitHub.** Push the `poly-news-bot/` directory (or the whole repo with this as a subdirectory — root deploys are simpler) to a GitHub repo. **Do NOT commit `.env`** — it's already in `.gitignore`.
2. **Create the Railway project.** Go to <https://railway.app> → **"New Project"** → **"Deploy from GitHub repo"** → pick the repo.
3. **Set root directory (if applicable).** If `poly-news-bot/` is a subdirectory inside your repo, set **Settings → Service → Root Directory** to `poly-news-bot`.
4. **Add a Volume (CRITICAL for persistence).** Settings → **Volumes** → **New Volume** → Mount path: `/data` → Save. Without this, the SQLite database is wiped on every redeploy and every subscriber gets re-spammed their 24h backfill.
5. **Add environment variables.** Settings → **Variables** → "Raw Editor" lets you paste them all at once:

   ```
   TELEGRAM_BOT_TOKEN=<your real token from BotFather>
   POLL_INTERVAL_MINUTES=30
   BACKFILL_WINDOW_HOURS=24
   MAX_ITEMS_PER_CYCLE=50
   DATABASE_PATH=/data/bot.db
   LOG_LEVEL=INFO
   NITTER_MIRRORS=nitter.poast.org,nitter.privacydev.net,nitter.tiekoetter.com,nitter.salastil.com
   POLYMARKET_YOUTUBE_CHANNEL_ID=
   CRYPTOPANIC_API_KEY=
   CRYPTOPANIC_API_PLAN=developer
   NEWSDATA_API_KEY=
   MEDIASTACK_API_KEY=
   TWITTER_BEARER_TOKEN=
   GITHUB_TOKEN=
   ```

   > **CRITICAL:** `DATABASE_PATH=/data/bot.db` must point to the volume mount path. The relative `data/bot.db` (no leading slash) would be wiped on every redeploy.

6. **Deploy.** Railway auto-detects Python via Railpack (reading `requirements.txt` and `runtime.txt`), installs dependencies, and runs `python bot.py` (see [`railway.toml`](railway.toml:1), [`Procfile`](Procfile:1), and [`runtime.txt`](runtime.txt:1)).
7. **Verify.** The **Logs** tab should show `"post_init complete"` and `"Scheduled news cycle every 30 minutes"`. The Telegram bot is reachable immediately — send `/start`.

### Cost note

- Railway **Free Tier**: $5 trial credit, then ~$5/month for the smallest service (Hobby plan).
- This bot uses minimal resources (~128 MB RAM, near-zero CPU between cycles). Should fit comfortably in the cheapest tier.

### Updating the bot

- Push to GitHub → Railway auto-rebuilds and redeploys.
- The Volume preserves the SQLite DB, so subscribers and dedup history persist across deploys.
- Railway sends `SIGTERM` during redeploys; python-telegram-bot v21's `run_polling()` handles this gracefully and shuts down cleanly via the bot's `_post_shutdown` hook.

### Troubleshooting

- **Logs show `TELEGRAM_BOT_TOKEN missing`** → you forgot to set the env var in Railway.
- **Users get re-sent old news after a deploy** → verify `DATABASE_PATH=/data/bot.db` (absolute, on the volume), not `data/bot.db` (ephemeral).
- **Bot stops responding** → check Logs for crashes. The `restartPolicyType=ON_FAILURE` in [`railway.toml`](railway.toml:1) should auto-restart up to 10 times.

---

## Deployment (self-hosted)

### systemd (Linux server)

Create `/etc/systemd/system/poly-news-bot.service`:

```ini
[Unit]
Description=Polymarket News Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=polynews
WorkingDirectory=/opt/poly-news-bot
EnvironmentFile=/opt/poly-news-bot/.env
ExecStart=/opt/poly-news-bot/.venv/bin/python bot.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now poly-news-bot
journalctl -u poly-news-bot -f
```

### Docker (future work)

A `Dockerfile` isn't included yet — but the bot is a single-process, no-external-services app, so it's trivial to wrap:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
VOLUME /app/data
CMD ["python", "bot.py"]
```

---

## Troubleshooting

- **Bot doesn't reply** → check `TELEGRAM_BOT_TOKEN` is set; check logs for "post_init complete".
- **No news arriving** → wait one full poll cycle (default 30 min, or `STARTUP_DELAY_SECONDS` for the first run); check `/sources`; check logs for `[fetcher_name] error: ...`.
- **Nitter is down** → all 3 default mirrors die from time to time. Update `NITTER_MIRRORS` in `.env` with fresh hosts from <https://status.d420.de/>, or set `TWITTER_BEARER_TOKEN`.
- **Polymarket blog returns 0 items** → the bot tries 4 RSS candidates then falls back to scraping `polymarket.com/blog`. If both fail, the blog source silently contributes nothing (other sources continue).
- **Rate limit hits** → if you have a lot of subscribers, the dispatcher already paces at ~20 msg/sec and respects Telegram's `RetryAfter`. For >1000 subscribers, consider lowering `MAX_ITEMS_PER_CYCLE` to spread load.

---

## License

MIT.