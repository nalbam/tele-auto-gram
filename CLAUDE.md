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

# Tests (163 tests across 6 files)
python -m pytest tests/ -v
```

## Architecture

```
main.py          # Entrypoint: starts Flask web server + bot in separate thread
├── web.py       # Flask REST API (config, auth, messages endpoints) + rate limiter
├── bot.py       # Telethon client: auth flow, message handler with debounce, manual replies
│   ├── _handle_new_message()    # Module-level: Phase A/B message processing
│   ├── _respond_to_sender()     # Module-level: cancellable AI response task
│   ├── _delayed_read_receipt()  # Module-level: fire & forget read receipt
│   └── _parse_delay_config()    # Helper: parse/validate min/max delay from config
├── config.py    # Config from .env → .env.local (override) → data/config.json (file overrides env)
│   └── _secure_write()          # Atomic file write (tempfile → chmod 0o600 → os.replace)
├── storage.py   # JSON-based message store with file locking (data/messages/{sender_id}.json, auto-prunes >7 days)
│   └── _secure_write()          # Atomic file write (same pattern as config.py)
├── ai.py        # AsyncOpenAI-based multi-turn response generation + sender profile update (singleton client)
└── templates/
    └── index.html  # SPA web UI (vanilla JS, Tailwind-style CSS)
```

**Startup flow**: `main.py` → signal handlers registered (SIGTERM/SIGINT) → Flask server starts on `0.0.0.0:5000` → 2s delay → bot starts in daemon thread (only if configured). Graceful shutdown via `future.result(timeout=5)`.

**Auth flow**: `bot.py:start_bot` → `connect()` → `is_user_authorized()` → if not, `send_code_request()` → wait for code via web UI (`_wait_for_input` with 600s timeout) → `sign_in()` → optional 2FA password. Auth state protected by `_state_lock` (threading.Lock).

**Message flow** (`bot.py:_handle_new_message` — module-level function with debounce):

```
Phase A — Non-cancellable (always completes):
  1. Private message filter — ignore non-private, early return if text is empty (media-only)
  2. Resolve sender name from Telegram User object
  3. Load config (single read)
  4. Store received message immediately (non-fatal: continues on failure)
  5. Send read receipt (fire & forget via _delayed_read_receipt with configurable delay)
  6. If not yet synced → fetch Telegram history → import → build initial sender profile
     └─ Sync marker: data/messages/{sender_id}.synced

Phase B — Cancellable (debounce):
  7. Cancel any pending response task for this sender (_pending_responses dict)
  8. Create new asyncio.Task (_respond_to_sender):
     a. Load fresh messages + sender profile + identity prompt
     b. Build multi-turn chat context (up to 20 recent messages → OpenAI messages array)
        └─ ai.build_chat_messages: received→user, sent→assistant, consecutive same-role merged
     c. Generate AI response (single OpenAI call with full conversation context)
        └─ Fallback to AUTO_RESPONSE_MESSAGE if no API key or on failure
     d. Random delay (RESPONSE_DELAY_MIN ~ MAX) → send response (asyncio.shield) → store sent message
     e. Conditional profile update — skip if ALL pending received messages are trivial
        └─ Trivial: empty, <3 chars, emoji-only, common filler words (ok, ㅋㅋ, etc.)
```

I/O budget per message: config read 2x (Phase A + Phase B), storage read 3x (messages + profile + identity), storage write 2x (received + sent), OpenAI call 1~2x (response + conditional profile update).

**Manual reply flow**: Web UI → `POST /api/messages/send` → `bot.send_message_to_user()` (uses `asyncio.run_coroutine_threadsafe` to bridge Flask thread → bot asyncio loop) → Telethon `client.send_message()` → store sent message.

## Security Features

- **Rate Limiting**: In-memory per-IP rate limiter (auth: 5/min, API: 30/min) in `web.py`
- **Atomic File Writes**: `_secure_write()` in config.py and storage.py (tempfile → chmod 0o600 → os.replace)
- **Input Validation**: API_ID numeric check, delay range 0–3600 with min ≤ max, auth input length limits (code: 10, password: 256), message length limit (4096)
- **Content-Type Enforcement**: POST to `/api/*` requires `application/json`
- **Token Auth**: `WEB_TOKEN` env var enables Bearer token for all API endpoints
- **Error Masking**: Server errors return generic messages, details logged server-side only
- **XSS Prevention**: `escapeHtml()` applied to user-supplied values in frontend
- **Thread Safety**: `_state_lock` for auth state, `_locks_lock` + per-sender LRU locks in storage

## Key Dependencies

- **Telethon 1.36.0** - Telegram client library (async, uses asyncio)
- **Flask 3.0.0** - Web UI and REST API
- **openai >=1.0.0,<2.0.0** - AI response generation (optional)
- **python-dotenv 1.0.0** - Environment variable loading
- **watchdog >=4.0.0,<6.0.0** - File change detection for dev mode auto-restart

## Configuration

Required env vars (or set via web UI): `API_ID`, `API_HASH`, `PHONE` (with country code like +82).
Optional: `AUTO_RESPONSE_MESSAGE`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `RESPONSE_DELAY_MIN`, `RESPONSE_DELAY_MAX`, `READ_RECEIPT_DELAY_MIN`, `READ_RECEIPT_DELAY_MAX`, `LOG_LEVEL`, `HOST`, `PORT`, `WEB_TOKEN`, `SECRET_KEY`.

AI identity/persona is defined in `data/IDENTITY.md` (auto-created with defaults if missing, editable via web UI).

Config priority: `data/config.json` > `.env.local` > environment variables > `.env`. File config has highest priority; `.env.local` overrides env vars; `.env` only fills in variables not already set.

## Data Storage

All data lives in `data/` directory (gitignored):
- `data/config.json` - Saved configuration from web UI (atomic write, 0o600 permissions)
- `data/IDENTITY.md` - AI persona/system prompt (auto-created if missing, editable via web UI)
- `data/messages/{sender_id}.json` - Per-sender message history (auto-pruned after 7 days, atomic write)
- `data/messages/{sender_id}.md` - Per-sender profile (preferred name, language, key facts — auto-updated by AI)
- `data/messages/{sender_id}.synced` - Marker indicating Telegram history has been fetched for this sender
- `data/bot_session.session` - Telethon session file (persisted in data/ for Docker volume support)
- `*.session` / `*.session-journal` - Telethon session files (gitignored, never commit)

Legacy `data/messages.json` is auto-migrated to per-sender files on first access and renamed to `data/messages.json.bak`.

## Testing

- **Framework**: pytest with pytest-asyncio (`asyncio_mode = auto`)
- **Config**: `pytest.ini` with `testpaths = tests`
- **Dev deps**: `requirements-dev.txt` extends requirements.txt
- **Run**: `python -m pytest tests/ -v`
- **Patterns**: `monkeypatch` + `tmp_path` for file isolation, `AsyncMock` for OpenAI, Flask `test_client` for API

## CI/CD

GitHub Actions (`docker-build.yml`) builds and pushes Docker images to `ghcr.io/nalbam/tele-auto-gram` on semver tags (`v*.*.*`).

## Web API Endpoints

- `GET /` - Web UI
- `GET /api/config` - Get current config (sensitive fields masked)
- `POST /api/config` - Save config to `data/config.json` (validates API_ID, delay ranges)
- `GET /api/messages` - Get stored messages (includes `sender_id` for reply support)
- `POST /api/messages/send` - Send manual message: `{ user_id: int, text: string }` (max 4096 chars)
- `GET /api/identity` - Get identity prompt content (from `data/IDENTITY.md`)
- `POST /api/identity` - Save identity prompt: `{ content: string }` (max 50000 chars)
- `GET /api/auth/status` - Get auth state (`disconnected`|`waiting_code`|`waiting_password`|`authorized`|`error`)
- `POST /api/auth/code` - Submit Telegram auth code (max 10 chars)
- `POST /api/auth/password` - Submit 2FA password (max 256 chars)
