# Architecture

Detailed system architecture for TeleAutoGram — a Telegram auto-response bot.

## Overview

```
┌─────────────────────────────────────────────────────────┐
│                       main.py                           │
│  Signal handlers (SIGTERM/SIGINT) + graceful shutdown   │
├────────────────────────┬────────────────────────────────┤
│   Flask Thread (web)   │   Bot Thread (asyncio)         │
│                        │                                │
│  ┌──────────────┐      │  ┌──────────────────────────┐  │
│  │   web.py     │      │  │       bot.py             │  │
│  │  REST API    │◄─────┼──│  TelegramClient          │  │
│  │  Rate Limit  │      │  │  Auth flow               │  │
│  │  Token Auth  │      │  │  Message handler          │  │
│  └──────┬───────┘      │  │  (debounce)              │  │
│         │              │  └──────┬───────────────────┘  │
│         │              │         │                      │
├─────────┼──────────────┴─────────┼──────────────────────┤
│         │        Shared modules  │                      │
│  ┌──────▼───────┐  ┌────────────▼──┐  ┌─────────────┐  │
│  │  config.py   │  │  storage.py   │  │   ai.py     │  │
│  │  Load/save   │  │  Per-sender   │  │  OpenAI     │  │
│  │  config      │  │  JSON store   │  │  Multi-turn │  │
│  └──────────────┘  └───────────────┘  └─────────────┘  │
├─────────────────────────────────────────────────────────┤
│                     data/ directory                     │
│  config.json │ IDENTITY.md │ messages/ │ bot_session    │
└─────────────────────────────────────────────────────────┘
```

## Module Responsibilities

### main.py — Entrypoint

- Configures logging based on `LOG_LEVEL` env var
- Registers signal handlers (SIGTERM, SIGINT) for graceful shutdown
- Starts Flask web server in a daemon thread
- Waits 2 seconds, then starts bot in another daemon thread (if configured)
- Main thread sleeps in infinite loop, handling KeyboardInterrupt

**Public API**: `main()` — entry point

### bot.py — Telegram Bot

Manages Telegram connection, authentication, and message handling.

**Public API**:
- `get_auth_state() -> dict` — thread-safe auth state copy
- `submit_auth_code(code)` — receive auth code from web UI
- `submit_auth_password(password)` — receive 2FA password from web UI
- `send_message_to_user(user_id, text)` — send message from Flask thread (bridges sync → async)
- `run_bot()` — start the bot event loop
- `start_bot()` — async bot initialization and run

**Internal functions** (module-level, extracted from closure):
- `_handle_new_message(cl, event)` — main message handler with Phase A/B debounce
- `_respond_to_sender(cl, event, sender_id, sender_name)` — cancellable response task
- `_delayed_read_receipt(cl, event, msg_cfg)` — fire & forget read receipt with delay
- `_generate_response(...)` — AI response with fallback
- `_update_sender_profile(...)` — conditional profile update
- `_fetch_telegram_history(...)` — import conversation history from Telegram
- `_authenticate(cl, phone, loop)` — full auth flow (code + optional 2FA)
- `_create_client(cfg)` — TelegramClient factory
- `_parse_delay_config(...)` — parse and validate min/max delay from config
- `_wait_for_input(loop, event, key, timeout)` — non-blocking wait for auth input

### web.py — Flask REST API

Serves the web UI and provides REST endpoints for configuration, authentication, messaging, and identity management.

**Public API**:
- `run_web_ui(host, port)` — start the Flask server
- `app` — Flask application instance

**Middleware** (before_request):
- `check_rate_limit()` — per-IP rate limiting (auth: 5/min, API: 30/min)
- `check_content_type()` — enforce `application/json` for POST requests
- `check_auth_token()` — Bearer token validation when `WEB_TOKEN` is set

### ai.py — AI Integration

Manages OpenAI API interactions for response generation and profile updates.

**Public API**:
- `build_chat_messages(messages, system_prompt, sender_name, sender_profile, limit)` — build OpenAI message array from conversation history
- `generate_response(chat_messages, api_key, model)` — generate AI response
- `update_sender_profile(current_profile, recent_messages, sender_name, ...)` — extract and update sender profile
- `is_trivial_message(text)` — check if message is trivial (skip profile update)

**Constants**: `DEFAULT_MODEL`, `MULTI_TURN_LIMIT` (20), `RESPONSE_MAX_TOKENS` (500), `PROFILE_RECENT_MESSAGES_LIMIT` (10)

### config.py — Configuration

Loads configuration from multiple sources with priority chain.

**Public API**:
- `load_config() -> dict` — load merged config
- `save_config(config)` — save to `data/config.json` (atomic write)
- `load_identity() -> str` — load AI persona from `data/IDENTITY.md`
- `save_identity(content)` — save AI persona (atomic write)
- `is_configured() -> bool` — check if API_ID, API_HASH, PHONE are set

### storage.py — Message Storage

Per-sender JSON file storage with file locking, auto-pruning, and legacy migration.

**Public API**:
- `load_messages() -> list` — load all messages from all senders (sorted)
- `get_messages_by_sender(sender_id, limit) -> list` — load messages for one sender
- `add_message(direction, sender, text, summary, sender_id) -> dict` — store a message
- `import_messages(sender_id, messages)` — bulk import (for Telegram history sync)
- `load_sender_profile(sender_id) -> str` — load sender profile markdown
- `save_sender_profile(sender_id, content)` — save sender profile (atomic write)
- `is_history_synced(sender_id) -> bool` — check sync marker
- `mark_history_synced(sender_id)` — create sync marker file

## Threading Model

```
Main Thread                 Flask Thread (daemon)         Bot Thread (daemon)
───────────                 ────────────────────         ──────────────────
main()                      run_web_ui()                 run_bot()
  │                           │                            │
  ├─ signal handlers          ├─ Flask app.run()           ├─ asyncio.run(start_bot())
  │                           │                            │
  ├─ start web thread ──────► │  before_request:           ├─ TelegramClient.connect()
  │                           │   rate_limit               │
  ├─ sleep(2s)                │   content_type             ├─ _authenticate()
  │                           │   auth_token               │   ├─ _wait_for_input() ◄─── threading.Event
  ├─ start bot thread ──────► │                            │   └─ sign_in()
  │                           │  Endpoints:                │
  └─ while True: sleep(1)    │   /api/config              ├─ on_new_message handler
     (keeps process alive)    │   /api/messages            │   └─ _handle_new_message()
                              │   /api/auth/*              │       ├─ Phase A (always)
                              │   /api/identity            │       └─ Phase B (cancellable)
                              │                            │
                              │  send_message_to_user() ──►│  (asyncio.run_coroutine_threadsafe)
                              │  submit_auth_code() ──────►│  (threading.Event.set)
                              │  submit_auth_password() ──►│  (threading.Event.set)
```

**Thread communication**:
- Flask → Bot: `asyncio.run_coroutine_threadsafe()` for sending messages
- Flask → Bot: `threading.Event` for auth code/password submission
- Shared state: `_state_lock` (threading.Lock) protects auth state reads/writes
- Storage: per-sender `threading.Lock` with LRU eviction (max 1000 locks)

## Message Processing Pipeline

### Phase A — Non-cancellable

These steps always complete, even if another message arrives immediately:

1. **Filter**: Ignore non-private messages and empty messages (media-only)
2. **Resolve sender**: Extract name from Telegram `User` object
3. **Load config**: Single `config.load_config()` call
4. **Store message**: `storage.add_message()` — persists received message immediately
5. **Read receipt**: Fire & forget `asyncio.Task` with configurable delay (`READ_RECEIPT_DELAY_MIN/MAX`)
6. **History sync**: On first contact, fetch up to 50 messages from Telegram API, import to storage, build initial sender profile. Marked via `.synced` file.

### Phase B — Cancellable (Debounce)

If a new message arrives from the same sender before the response is sent, the pending task is cancelled and a new one is created that sees all accumulated messages.

7. **Cancel previous**: `existing_task.cancel()` if pending for this sender
8. **Create response task** (`_respond_to_sender`):
   - Load fresh messages, profile, and identity prompt
   - Build multi-turn context via `ai.build_chat_messages()`
   - Generate AI response (or use fallback message)
   - Wait random delay (`RESPONSE_DELAY_MIN` ~ `RESPONSE_DELAY_MAX`)
   - Send response via Telethon
   - Store sent message
   - Update sender profile if any pending received message is non-trivial

```
Sender sends: "Hey"  →  Phase A stores, Phase B starts response task
Sender sends: "How are you?"  →  Phase A stores, Phase B cancels old task, starts new
Sender sends: "What's up?"  →  Phase A stores, Phase B cancels old task, starts new
                                 (new task sees all 3 messages in context)
```

## Authentication Flow

```
                  ┌──────────────┐
                  │ disconnected │
                  └──────┬───────┘
                         │ connect() + send_code_request()
                         ▼
                  ┌──────────────┐
              ┌──►│ waiting_code │◄──┐
              │   └──────┬───────┘   │
              │          │ sign_in(code)
              │          │           │
              │   Invalid code      Expired code
              │   (retry)           (re-send)
              │          │
              │          ▼
              │   ┌────────────────────┐
              │   │ SessionPassword    │
              │   │ NeededError?       │
              │   └──┬─────────┬──────┘
              │      │ No      │ Yes
              │      │         ▼
              │      │  ┌──────────────────┐
              │      │  │ waiting_password  │◄──┐
              │      │  └──────┬───────────┘   │
              │      │         │ sign_in(pw)   │
              │      │         │               │
              │      │  Invalid password       │
              │      │  (retry) ───────────────┘
              │      │         │
              │      ▼         ▼
              │   ┌──────────────┐
              │   │  authorized  │
              │   └──────────────┘
              │
              │   ┌──────────────┐
              └───│    error     │ (timeout, network failure, etc.)
                  └──────────────┘
```

Auth input is received from the web UI via `threading.Event` with a 600-second timeout (`_AUTH_INPUT_TIMEOUT`). If the timeout expires, `AuthTimeoutError` is raised and the state transitions to `error`.

## Configuration Priority

```
Highest priority
  │
  ├─ data/config.json    ← Saved from Web UI (config.save_config)
  │                         Loaded via json.load, updates the dict
  │
  ├─ .env.local          ← Local development overrides (gitignored)
  │                         Loaded via load_dotenv(override=True)
  │
  ├─ Environment vars    ← System/container environment
  │                         Read via os.getenv() as base values
  │
  └─ .env                ← Default values (committed to repo as .env.example)
                            Loaded via load_dotenv() (does NOT override existing)
Lowest priority
```

## Data Storage

### File Structure

```
data/
├── config.json              # JSON: all config key/values
├── IDENTITY.md              # Markdown: AI persona/system prompt
├── bot_session.session      # Telethon SQLite session
└── messages/
    ├── 123456789.json       # Message history for sender 123456789
    ├── 123456789.md         # Sender profile for 123456789
    ├── 123456789.synced     # History sync marker for 123456789
    ├── 987654321.json
    ├── 987654321.md
    └── 987654321.synced
```

### Auto-Prune

Messages older than 7 days are automatically removed when a sender's file is loaded (`_load_sender_messages`). If all messages are pruned, the JSON file is deleted.

### File Locking

Per-sender `threading.Lock` instances are stored in an LRU-bounded dict (max 1000 entries). Eviction only removes unlocked entries, so active operations are never disrupted.

### Atomic Writes

Both `config.py` and `storage.py` use `_secure_write()`:

1. Create temp file in same directory (`tempfile.mkstemp`)
2. Write content via callback function
3. Set permissions to `0o600` (owner read/write only)
4. Atomically replace target file (`os.replace`)
5. On error: clean up temp file

### Legacy Migration

`data/messages.json` (single file) is auto-migrated to per-sender files on first access. The original file is renamed to `data/messages.json.bak`.

## AI Integration

### Response Generation

```
Stored messages ──► build_chat_messages() ──► OpenAI API ──► response text
                         │
                    Builds array:
                    [system] persona + sender profile
                    [user]   received messages
                    [assistant] sent messages
                    (consecutive same-role merged)
                    (limited to 20 most recent)
```

- **Model**: Configurable via `OPENAI_MODEL` (default: `gpt-4o-mini`)
- **Max tokens**: 500 for responses, 500 for profile updates
- **Temperature**: 0.7 for responses, 0.3 for profile updates
- **Fallback**: `AUTO_RESPONSE_MESSAGE` config value when no API key or on failure
- **Client**: Singleton `AsyncOpenAI` instance, recreated only if API key changes

### Sender Profile Updates

Profile updates are conditional:
1. Check all pending received messages (since last sent) for non-trivial content
2. If all messages are trivial (emoji, filler words, < 3 chars), skip update
3. Otherwise, call OpenAI to extract lasting personal facts about the sender
4. Only facts the *sender* revealed about *themselves* are stored (not bot operator info)

## Security

### Rate Limiting

In-memory per-IP rate limiter in `web.py`:
- Auth endpoints (`/api/auth/code`, `/api/auth/password`): 5 requests per minute
- Other API endpoints: 30 requests per minute
- Window: 60 seconds (sliding)
- Returns HTTP 429 when exceeded

### Input Validation

| Endpoint | Validation |
|----------|-----------|
| `POST /api/config` | API_ID numeric, delay 0–3600, min ≤ max |
| `POST /api/auth/code` | Non-empty, max 10 chars |
| `POST /api/auth/password` | Non-empty, max 256 chars |
| `POST /api/messages/send` | user_id numeric, text non-empty, max 4096 chars |
| `POST /api/identity` | max 50000 chars |

### Token Authentication

When `WEB_TOKEN` is set, all `/api/*` requests require `Authorization: Bearer <token>` header. Comparison uses `secrets.compare_digest` for timing-safe equality.

### Content-Type Enforcement

All POST requests to `/api/*` must include `Content-Type: application/json`. Returns HTTP 415 otherwise. This prevents CSRF via form submissions.

## Web API Reference

### GET /

Serves the single-page web UI (`templates/index.html`).

### GET /api/config

Returns current configuration with sensitive fields masked.

**Response**:
```json
{
  "API_ID": "12345",
  "API_HASH": "ab****cd",
  "PHONE": "+821012345678",
  "OPENAI_API_KEY": "sk-****xxxx",
  "OPENAI_MODEL": "gpt-4o-mini",
  "RESPONSE_DELAY_MIN": 3,
  "RESPONSE_DELAY_MAX": 10,
  "READ_RECEIPT_DELAY_MIN": 3,
  "READ_RECEIPT_DELAY_MAX": 10,
  "is_configured": true
}
```

### POST /api/config

Save configuration. Masked values are preserved (not overwritten).

**Request**:
```json
{
  "API_ID": "12345",
  "API_HASH": "your_api_hash",
  "PHONE": "+821012345678"
}
```

**Response**: `{ "status": "success" }`

### GET /api/messages

Returns all stored messages, sorted by timestamp.

**Response**:
```json
[
  {
    "timestamp": "2024-01-01T12:00:00",
    "direction": "received",
    "sender": "User Name",
    "text": "Hello!",
    "summary": null,
    "sender_id": 123456789
  }
]
```

### POST /api/messages/send

Send a manual message to a Telegram user.

**Request**:
```json
{
  "user_id": 123456789,
  "text": "Hello!"
}
```

**Response**: `{ "status": "success" }`

**Errors**: 400 (missing fields, invalid user_id), 503 (bot not running)

### GET /api/identity

Returns AI persona content.

**Response**: `{ "content": "# Identity\n\nYou are a friendly..." }`

### POST /api/identity

Save AI persona content.

**Request**: `{ "content": "# Identity\n\nYour custom persona..." }`

**Response**: `{ "status": "success" }`

### GET /api/auth/status

Returns current authentication state.

**Response**:
```json
{
  "status": "authorized",
  "error": null
}
```

Status values: `disconnected`, `waiting_code`, `waiting_password`, `authorized`, `error`

### POST /api/auth/code

Submit Telegram verification code.

**Request**: `{ "code": "12345" }`

**Response**: `{ "status": "success" }`

### POST /api/auth/password

Submit 2FA password.

**Request**: `{ "password": "your_password" }`

**Response**: `{ "status": "success" }`
