# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Telegram 자동 응답 봇 (Python + Telethon). 웹 UI를 통해 설정을 관리하고, 프라이빗 메시지에 자동으로 응답합니다.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run (starts both web UI on port 5000 and bot)
python main.py

# Docker
docker-compose up -d
```

There are no tests, linter, or type checker configured in this project.

## Architecture

```
main.py          # Entrypoint: starts Flask web server + bot in separate thread
├── web.py       # Flask REST API (GET/POST /api/config, GET /api/messages)
├── bot.py       # Telethon client: listens for private messages, auto-responds
├── config.py    # Config from .env then data/config.json (file overrides env)
├── storage.py   # JSON-based message store (data/messages.json, auto-prunes >7 days)
├── utils.py     # Message summarization + optional external API notification
└── templates/
    └── index.html  # SPA web UI (vanilla JS, Tailwind-style CSS)
```

**Startup flow**: `main.py` → Flask server starts on `127.0.0.1:5000` → 2s delay → bot starts in daemon thread (only if configured).

**Message flow**: Telegram message → `bot.py:handle_new_message` → store received message → send auto-response → store sent message → summarize → optional API notify.

## Key Dependencies

- **Telethon 1.36.0** - Telegram client library (async, uses asyncio)
- **Flask 3.0.0** - Web UI and REST API
- **python-dotenv** - Environment variable loading

## Configuration

Required env vars (or set via web UI): `API_ID`, `API_HASH`, `PHONE` (with country code like +82).
Optional: `NOTIFY_API_URL`, `AUTO_RESPONSE_MESSAGE`.

Config priority: `data/config.json` > environment variables (file config overrides env vars).

## Data Storage

All data lives in `data/` directory (gitignored):
- `data/config.json` - Saved configuration from web UI
- `data/messages.json` - Message history (auto-pruned after 7 days)
- `*.session` / `*.session-journal` - Telethon session files (gitignored, never commit)

## CI/CD

GitHub Actions (`docker-build.yml`) builds and pushes Docker images to `ghcr.io/nalbam/tele-auto-gram` on semver tags (`v*.*.*`).

## Web API Endpoints

- `GET /` - Web UI
- `GET /api/config` - Get current config (returns all fields including secrets)
- `POST /api/config` - Save config to `data/config.json`
- `GET /api/messages` - Get stored messages
