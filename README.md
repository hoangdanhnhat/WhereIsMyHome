# 🏠 WhereIsMyHome

A Dockerized home-server application that tracks your dynamic public IP address and notifies you via **Discord**, **Email**, or **Telegram** when it changes — or on-demand through bot commands.

## Features

- **Multi-source IP detection** — fails over through ipify, ifconfig.me, icanhazip, and more
- **SQLite history** — stores every IP change with timestamps, persisted via Docker volume
- **Discord bot** — slash commands (`/ip`, `/history`, `/status`) with ephemeral (private) replies; DMs you on IP change
- **Email (SMTP)** — HTML + plaintext email on IP change, supports Gmail & custom SMTP
- **Telegram bot** — commands (`/ip`, `/history`, `/status`); messages your chat on IP change
- **Configurable interval** — default 5 min, set via env var
- **Each channel independently toggleable** — enable only what you need
- **Graceful shutdown** — handles SIGTERM/SIGINT cleanly
- **Non-root Docker container**

## Project Structure

```
WhereIsMyHome/
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── requirements.txt
├── README.md
├── data/                  ← SQLite DB (persisted via volume)
└── app/
    ├── main.py            ← entry point, starts all services
    ├── ip_checker.py      ← IP fetch + change detection
    ├── config.py          ← loads and validates env vars
    ├── storage.py         ← SQLite read/write for IP history
    └── notifiers/
        ├── discord_bot.py
        ├── email_notifier.py
        └── telegram_bot.py
```

---

## Quick Start

### 1. Clone & configure

```bash
git clone <your-repo-url> && cd WhereIsMyHome
cp .env.example .env
```

Edit `.env` with your bot tokens and credentials (see detailed setup below).

### 2. Deploy with Docker Compose

```bash
docker compose up -d --build
```

View logs:

```bash
docker compose logs -f
```

Stop:

```bash
docker compose down
```

---

## Configuration Reference

All configuration is done through environment variables in the `.env` file.

| Variable | Default | Description |
|---|---|---|
| `CHECK_INTERVAL_SECONDS` | `300` | How often to check the public IP (seconds) |
| `HISTORY_LIMIT` | `20` | Max records shown by `/history` commands |
| `DISCORD_ENABLED` | `false` | Enable Discord bot |
| `DISCORD_BOT_TOKEN` | | Bot token from Discord Developer Portal |
| `DISCORD_USER_ID` | | Your Discord user ID (for DMs) |
| `DISCORD_CHANNEL_ID` | | Optional: private channel to also post in |
| `EMAIL_ENABLED` | `false` | Enable email notifications |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server hostname |
| `SMTP_PORT` | `587` | SMTP port (587=STARTTLS, 465=SSL) |
| `SMTP_USER` | | SMTP login username / email |
| `SMTP_PASS` | | SMTP password or app password |
| `NOTIFY_EMAIL` | | Recipient email address |
| `TELEGRAM_ENABLED` | `false` | Enable Telegram bot |
| `TELEGRAM_BOT_TOKEN` | | Bot token from BotFather |
| `TELEGRAM_CHAT_ID` | | Your personal chat ID |

---

## Detailed Setup Guides

### Discord Bot Setup

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application** → name it (e.g., "IP Tracker") → **Create**
3. Go to **Bot** tab → **Reset Token** → copy the token → paste into `DISCORD_BOT_TOKEN`
4. Under **Privileged Gateway Intents**, you do **not** need any privileged intents
5. Go to **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Send Messages in Threads`
6. Copy the generated URL → open it in your browser → select your server → **Authorize**

#### Getting your Discord User ID

1. Open Discord → **Settings → Advanced → Enable Developer Mode**
2. Right-click your own name in any chat → **Copy User ID**
3. Paste into `DISCORD_USER_ID`

#### Privacy: Ephemeral Messages & DMs

- All slash command replies (`/ip`, `/history`, `/status`) use **ephemeral messages** — only visible to you, not other server members
- IP change notifications are sent as a **direct message (DM)** to your user ID, never to a public channel
- Optionally, set `DISCORD_CHANNEL_ID` to a **private channel** for a secondary notification

---

### Telegram Bot Setup

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` → follow prompts → copy the bot token → paste into `TELEGRAM_BOT_TOKEN`
3. Start a chat with your new bot (send `/start`)

#### Getting your Telegram Chat ID

1. Message your bot (send anything)
2. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. Find the `"chat": {"id": 123456789}` value → paste into `TELEGRAM_CHAT_ID`

**Security:** The bot only responds to messages from your configured `TELEGRAM_CHAT_ID`. All other users are silently ignored.

---

### Email (Gmail) Setup

1. Go to [Google Account Security](https://myaccount.google.com/security)
2. Enable **2-Step Verification** if not already active
3. Go to [App Passwords](https://myaccount.google.com/apppasswords)
4. Generate a new app password for "Mail" → copy it
5. In `.env`:
   ```
   EMAIL_ENABLED=true
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=yourname@gmail.com
   SMTP_PASS=abcd efgh ijkl mnop     # the 16-char app password
   NOTIFY_EMAIL=yourname@gmail.com    # recipient (can be the same)
   ```

#### Custom SMTP

Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, and `SMTP_PASS` to match your provider. Use port `465` for implicit SSL or `587` for STARTTLS.

---

## Running Without Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Export env vars (or use a tool like direnv)
export $(grep -v '^#' .env | xargs)
export DATA_DIR=./data

python -m app.main
```

---

## How It Works

1. On startup, the app loads config from environment variables and initialises a SQLite database
2. An async loop fetches your public IP every `CHECK_INTERVAL_SECONDS` from multiple sources (with fallback)
3. If the IP differs from the last stored value, it:
   - Stores the new IP + timestamp in the DB
   - Fires all enabled notification callbacks concurrently (Discord DM, Email, Telegram message)
4. Bot commands (`/ip`, `/history`, `/status`) query the SQLite DB directly for instant responses
5. On SIGTERM/SIGINT the app shuts down all bots and closes the database cleanly

---

## License

MIT
