# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TeleAutoGram — Telegram auto-response bot (Python + Telethon). Manage configuration and authentication via web UI, automatically responds to private messages.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run (starts both web UI on port 5000 and bot)
python main.py

# Dev mode: auto-restart on file changes (*.py, *.html)
watchmedo auto-restart --patterns="*.py;*.html" --recursive -- python main.py

# Docker
docker-compose up -d
```

There are no tests, linter, or type checker configured in this project.

## Architecture

```
main.py          # Entrypoint: starts Flask web server + bot in separate thread
├── web.py       # Flask REST API (config, auth, messages endpoints)
├── bot.py       # Telethon client: web-based auth flow, listens for private messages, sends manual replies
├── config.py    # Config from .env → .env.local (override) → data/config.json (file overrides env)
├── storage.py   # JSON-based message store (data/messages/{sender_id}.json, auto-prunes >7 days)
├── ai.py        # OpenAI-based conversation summarization + response generation
└── templates/
    └── index.html  # SPA web UI (vanilla JS, Tailwind-style CSS)
```

**Startup flow**: `main.py` → Flask server starts on `127.0.0.1:5000` → 2s delay → bot starts in daemon thread (only if configured).

**Auth flow**: `bot.py:start_bot` → `connect()` → `is_user_authorized()` → if not, `send_code_request()` → wait for code via web UI → `sign_in()` → optional 2FA password.

**Message flow**: Telegram message → `bot.py:handle_new_message` → store received message (with `sender_id`) → generate AI response (or fallback) → 3-10s random delay → send auto-response → store sent message.

**Manual reply flow**: Web UI → `POST /api/messages/send` → `bot.send_message_to_user()` (uses `asyncio.run_coroutine_threadsafe` to bridge Flask thread → bot asyncio loop) → Telethon `client.send_message()` → store sent message.

## Key Dependencies

- **Telethon 1.36.0** - Telegram client library (async, uses asyncio)
- **Flask 3.0.0** - Web UI and REST API
- **openai >=1.0.0** - AI response generation (optional)
- **python-dotenv** - Environment variable loading
- **watchdog >=4.0.0** - File change detection for dev mode auto-restart

## Configuration

Required env vars (or set via web UI): `API_ID`, `API_HASH`, `PHONE` (with country code like +82).
Optional: `AUTO_RESPONSE_MESSAGE`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `LOG_LEVEL`.

AI identity/persona is defined in `data/IDENTITY.md` (auto-created with defaults if missing, editable via web UI).

Config priority: `data/config.json` > `.env.local` > `.env` > environment variables. File config has highest priority; `.env.local` overrides `.env`.

## Data Storage

All data lives in `data/` directory (gitignored):
- `data/config.json` - Saved configuration from web UI
- `data/IDENTITY.md` - AI persona/system prompt (auto-created if missing, editable via web UI)
- `data/messages/{sender_id}.json` - Per-sender message history (auto-pruned after 7 days)
- `data/bot_session.session` - Telethon session file (persisted in data/ for Docker volume support)
- `*.session` / `*.session-journal` - Telethon session files (gitignored, never commit)

Legacy `data/messages.json` is auto-migrated to per-sender files on first access and renamed to `data/messages.json.bak`.

## CI/CD

GitHub Actions (`docker-build.yml`) builds and pushes Docker images to `ghcr.io/nalbam/tele-auto-gram` on semver tags (`v*.*.*`).

## Web API Endpoints

- `GET /` - Web UI
- `GET /api/config` - Get current config (sensitive fields masked)
- `POST /api/config` - Save config to `data/config.json`
- `GET /api/messages` - Get stored messages (includes `sender_id` for reply support)
- `POST /api/messages/send` - Send manual message: `{ user_id: int, text: string }`
- `GET /api/identity` - Get identity prompt content (from `data/IDENTITY.md`)
- `POST /api/identity` - Save identity prompt: `{ content: string }`
- `GET /api/auth/status` - Get auth state (`disconnected`|`waiting_code`|`waiting_password`|`authorized`|`error`)
- `POST /api/auth/code` - Submit Telegram auth code
- `POST /api/auth/password` - Submit 2FA password
