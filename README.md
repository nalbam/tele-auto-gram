# TeleAutoGram

Telegram auto-response bot built with Telethon. Manage configuration and authentication via a web UI, and automatically respond to private messages.

## Features

- **Auto Response**: Sends an automatic reply after a configurable delay upon receiving a private message
- **AI Multi-turn Conversation**: Context-aware responses using OpenAI with up to 20 messages of conversation history
- **Sender Profile**: Automatically builds and maintains per-sender profiles (preferred name, language, key facts)
- **Message Debounce**: Consecutive messages from the same sender are merged into a single AI response
- **Read Receipt Delay**: Configurable delay before marking messages as read for natural appearance
- **Manual Reply**: Select a conversation in the web UI and send messages directly
- **Web-based Auth**: Enter Telegram verification codes and 2FA passwords from your browser
- **Message History**: Stores sent/received messages locally as JSON (last 7 days, per-sender files)
- **Web UI**: Modern management interface (settings, auth, conversations, manual reply, identity editor)
- **Docker Support**: Full web-based authentication for non-interactive environments

## Getting Started

### Prerequisites

- Python 3.12+ or Docker
- A Telegram account
- API ID and API Hash (from [my.telegram.org](https://my.telegram.org))

### Getting Telegram API Keys

1. Go to [https://my.telegram.org](https://my.telegram.org)
2. Log in with your phone number
3. Click "API development tools"
4. Fill in app details (App title, Short name)
5. Save your **API ID** and **API Hash**

### Option 1: Docker (Recommended)

1. Pull the Docker image:
```bash
docker pull ghcr.io/nalbam/tele-auto-gram:latest
```

2. Set up environment variables:
```bash
cp .env.example .env
# Edit .env to set API_ID, API_HASH, PHONE
```

3. Run with Docker Compose:
```bash
docker-compose up -d
```

Or run directly:
```bash
docker run -d \
  -p 5000:5000 \
  -v $(pwd)/data:/app/data \
  -e API_ID=your_api_id \
  -e API_HASH=your_api_hash \
  -e PHONE=+821012345678 \
  --name tele-auto-gram \
  ghcr.io/nalbam/tele-auto-gram:latest
```

### Option 2: Run with Python

1. Clone the repository:
```bash
git clone https://github.com/nalbam/tele-auto-gram.git
cd tele-auto-gram
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run:
```bash
python main.py
```

4. (Optional) Dev mode — auto-restart on file changes:
```bash
watchmedo auto-restart --patterns="*.py;*.html" --recursive -- python main.py
```

### Option 3: ctl.sh (Background / Service, Linux & macOS)

Unified control script that auto-detects OS (systemd on Linux, launchd on macOS):

```bash
# Background
./ctl.sh start        # Start in background
./ctl.sh stop         # Stop
./ctl.sh restart      # Restart
./ctl.sh status       # Check status
./ctl.sh logs         # Tail logs

# System service (auto-restart on crash, auto-start on boot)
./ctl.sh install      # Register service
./ctl.sh svc-start    # Start service
./ctl.sh svc-stop     # Stop service
./ctl.sh svc-restart  # Restart service
./ctl.sh svc-status   # Check service status
./ctl.sh svc-logs     # Tail service logs
./ctl.sh uninstall    # Remove service
```

Then open `http://127.0.0.1:5000` in your browser.

## Configuration

### Via Web UI

1. Go to `http://127.0.0.1:5000`
2. Enter the following:
   - **API ID**: API ID from my.telegram.org
   - **API Hash**: API Hash from my.telegram.org
   - **Phone Number**: Phone number with country code (e.g. +821012345678)
   - **Auto Response Message** (optional): Fallback message when AI is not configured
   - **OpenAI API Key** (optional): Enables AI-powered auto responses
   - **OpenAI Model** (optional): Model to use (default: gpt-4o-mini)
   - **Identity** (optional): AI persona and style guide (saved as `data/IDENTITY.md`)

### Via Environment Variables (Optional)

Create a `.env` file. For local development, use `.env.local` to override `.env` (`.env.local` is gitignored):

```conf
API_ID=your_api_id
API_HASH=your_api_hash
PHONE=+821012345678
AUTO_RESPONSE_MESSAGE=I will get back to you shortly.
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
RESPONSE_DELAY_MIN=3
RESPONSE_DELAY_MAX=10
READ_RECEIPT_DELAY_MIN=3
READ_RECEIPT_DELAY_MAX=10
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=5000
WEB_TOKEN=
SECRET_KEY=
```

### Configuration Priority

Settings are resolved in this order (highest priority first):

1. `data/config.json` — saved from Web UI
2. `.env.local` — local overrides (gitignored)
3. Environment variables
4. `.env` — default values

## Usage

1. **Configure**: Enter API ID, API Hash, and phone number in the Settings tab
2. **Restart server**: Restart after saving settings
3. **Authenticate**: Enter the Telegram verification code in the Auth tab (and 2FA password if enabled)
4. **Auto response**: After authentication, incoming private messages get an automatic reply
5. **View messages**: Check recent message history in the Conversations tab
6. **Manual reply**: Click a conversation in the sidebar, then type and send a message

## Project Structure

```
tele-auto-gram/
├── main.py              # Entrypoint (starts Flask + bot thread)
├── bot.py               # Telegram bot logic (auth flow + message handler)
├── web.py               # Web UI server (settings/auth/messages API)
├── ai.py                # AI response generation (OpenAI)
├── config.py            # Configuration management
├── storage.py           # Message storage management
├── ctl.sh               # Control script (background/service management)
├── requirements.txt     # Dependencies
├── .env.example         # Environment variable example
├── CLAUDE.md            # AI coding assistant instructions
├── Dockerfile           # Docker image build config
├── docker-compose.yml   # Docker Compose config
├── templates/
│   └── index.html       # Web UI template
├── docs/
│   ├── ARCHITECTURE.md  # System architecture documentation
│   └── DEVELOPMENT.md   # Development guide
├── tests/               # Test suite (pytest)
├── .github/workflows/
│   └── docker-build.yml # CI/CD auto image build
└── data/                # Data directory (auto-created, Docker volume mount target)
    ├── config.json      # Configuration file
    ├── IDENTITY.md      # AI persona/identity prompt
    ├── messages/        # Per-sender message history
    │   ├── {sender_id}.json    # Message history (auto-pruned after 7 days)
    │   ├── {sender_id}.md      # Sender profile (auto-updated by AI)
    │   └── {sender_id}.synced  # Telegram history sync marker
    └── bot_session.session     # Telethon session file
```

## Docker Images

### Available Tags

Docker images are automatically built via GitHub Actions and published to GitHub Container Registry:

- `ghcr.io/nalbam/tele-auto-gram:latest` — Latest release
- `ghcr.io/nalbam/tele-auto-gram:1` — Major version 1.x.x
- `ghcr.io/nalbam/tele-auto-gram:1.0` — Minor version 1.0.x
- `ghcr.io/nalbam/tele-auto-gram:1.0.0` — Specific version
- `ghcr.io/nalbam/tele-auto-gram:sha-xxxxxxx` — Commit SHA

### Version Tagging

To release a new version, create a git tag in `v1.x.x` format:

```bash
git tag v1.0.0
git push origin v1.0.0
```

When the tag is pushed, GitHub Actions will automatically build and push the Docker image.

## Message Storage

Messages are stored in per-sender files under `data/messages/`:

```json
[
  {
    "timestamp": "2024-01-01T12:00:00",
    "direction": "received",
    "sender": "User Name",
    "text": "Message content",
    "summary": null,
    "sender_id": 123456789
  }
]
```

Each sender has up to three associated files:

| File | Description |
|------|-------------|
| `{sender_id}.json` | Message history (auto-pruned after 7 days) |
| `{sender_id}.md` | Sender profile — preferred name, language, key facts (auto-updated by AI) |
| `{sender_id}.synced` | Marker indicating Telegram history has been fetched for this sender |

Messages older than 7 days are automatically pruned on access.

## Security

- **Token Authentication**: Set `WEB_TOKEN` to require Bearer token for all `/api/*` endpoints
- **Rate Limiting**: In-memory per-IP rate limiter (auth: 5/min, API: 30/min)
- **Atomic File Writes**: Config and storage files written via temp file + `os.replace` to prevent corruption
- **Input Validation**: API ID numeric check, delay range validation (0–3600), auth input length limits
- **Content-Type Enforcement**: POST requests to `/api/*` require `application/json`
- **Sensitive Data Masking**: API Hash and OpenAI key masked in web UI responses
- **XSS Prevention**: User-supplied values escaped in frontend rendering
- **File Permissions**: Data files created with `0o600` (owner read/write only)
- Web UI binds to `0.0.0.0` by default for Docker compatibility. Set `HOST=127.0.0.1` to restrict to localhost
- Never share your API keys or session files
- Sensitive files are included in `.gitignore`

## Troubleshooting

### "Not Configured" status keeps showing
- Verify that API ID, API Hash, and phone number are all entered
- Make sure you clicked "Save Settings" in the web UI

### Not receiving verification code
- Check that your phone number includes the country code (e.g. +82)
- Verify you are logged into the Telegram app

### Auto response not working
- Check that the bot is running in the terminal ("Bot is running..." message should appear)
- Verify authentication is complete in the Auth tab

### Web UI won't open
- Check if port 5000 is already in use: `lsof -i :5000`
- Check if firewall is blocking localhost access

### Stopping the Bot
- **Foreground**: Press `Ctrl + C`
- **Background**: `./ctl.sh stop`
- **Service**: `./ctl.sh svc-stop`

## Contributing

### Development Setup

```bash
# Clone the repository
git clone https://github.com/nalbam/tele-auto-gram.git
cd tele-auto-gram

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# Install dependencies (including dev tools)
pip install -r requirements-dev.txt

# Copy environment config
cp .env.example .env.local
# Edit .env.local with your credentials
```

### Running Tests

```bash
python -m pytest tests/ -v
```

### Pull Request Guidelines

1. Create a feature branch from `main`
2. Make small, focused commits with descriptive messages
3. Add tests for new functionality
4. Ensure all existing tests pass
5. Open a PR with a clear description of changes

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for detailed development instructions and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for system architecture.

## License

MIT License
