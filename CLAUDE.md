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

# Background / Service (Linux & macOS)
./ctl.sh start          # background start
./ctl.sh install        # register system service (systemd / launchd)
./ctl.sh svc-start      # start service

# Dev mode: auto-restart on file changes (*.py, *.html)
watchmedo auto-restart --patterns="*.py;*.html" --recursive -- python main.py

# Docker
docker-compose up -d
```

Tests are configured with pytest (`python -m pytest tests/ -v`). No linter or type checker configured.

## Architecture

```
main.py          # Entrypoint: starts Flask web server + bot in separate thread
├── web.py       # Flask REST API (config, auth, messages endpoints)
├── bot.py       # Telethon client: web-based auth flow, listens for private messages, sends manual replies
├── config.py    # Config from .env → .env.local (override) → data/config.json (file overrides env)
├── storage.py   # JSON-based message store with file locking (data/messages/{sender_id}.json, auto-prunes >7 days)
├── ai.py        # AsyncOpenAI-based multi-turn response generation + sender profile update (singleton client)
└── templates/
    └── index.html  # SPA web UI (vanilla JS, Tailwind-style CSS)
```

**Startup flow**: `main.py` → signal handlers registered (SIGTERM/SIGINT) → Flask server starts on `0.0.0.0:5000` → 2s delay → bot starts in daemon thread (only if configured).

**Auth flow**: `bot.py:start_bot` → `connect()` → `is_user_authorized()` → if not, `send_code_request()` → wait for code via web UI → `sign_in()` → optional 2FA password.

**Message flow** (`bot.py:handle_new_message`):

```
1. Private message filter — ignore non-private, early return if text is empty (media-only)
2. Resolve sender name from Telegram User object
3. Load config (single read)
4. Load message history from storage (single read)
   └─ If no history → fetch from Telegram API → import → build initial sender profile
5. Load sender profile + identity prompt (single read each)
6. Store received message + send read receipt
7. Build multi-turn chat context (up to 20 recent messages → OpenAI messages array)
   └─ ai.build_chat_messages: received→user, sent→assistant, consecutive same-role merged
8. Generate AI response (single OpenAI call with full conversation context)
   └─ Fallback to AUTO_RESPONSE_MESSAGE if no API key or on failure
9. Random delay (RESPONSE_DELAY_MIN ~ MAX) → send response → store sent message
10. Conditional profile update — skip if message is trivial (ai.is_trivial_message)
    └─ Trivial: empty, <3 chars, emoji-only, common filler words (ok, ㅋㅋ, etc.)
```

I/O budget per message: storage read 1x, OpenAI call 1~2x (response + conditional profile update).

**Manual reply flow**: Web UI → `POST /api/messages/send` → `bot.send_message_to_user()` (uses `asyncio.run_coroutine_threadsafe` to bridge Flask thread → bot asyncio loop) → Telethon `client.send_message()` → store sent message.

## Key Dependencies

- **Telethon 1.36.0** - Telegram client library (async, uses asyncio)
- **Flask 3.0.0** - Web UI and REST API
- **openai >=1.0.0** - AI response generation (optional)
- **python-dotenv** - Environment variable loading
- **watchdog >=4.0.0** - File change detection for dev mode auto-restart

## Configuration

Required env vars (or set via web UI): `API_ID`, `API_HASH`, `PHONE` (with country code like +82).
Optional: `AUTO_RESPONSE_MESSAGE`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `RESPONSE_DELAY_MIN`, `RESPONSE_DELAY_MAX`, `LOG_LEVEL`, `HOST`, `PORT`, `WEB_TOKEN`, `SECRET_KEY`.

AI identity/persona is defined in `data/IDENTITY.md` (auto-created with defaults if missing, editable via web UI).

Config priority: `data/config.json` > `.env.local` > environment variables > `.env`. File config has highest priority; `.env.local` overrides env vars; `.env` only fills in variables not already set.

## Data Storage

All data lives in `data/` directory (gitignored):
- `data/config.json` - Saved configuration from web UI
- `data/IDENTITY.md` - AI persona/system prompt (auto-created if missing, editable via web UI)
- `data/messages/{sender_id}.json` - Per-sender message history (auto-pruned after 7 days)
- `data/messages/{sender_id}.md` - Per-sender profile (preferred name, language, key facts — auto-updated by AI)
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
