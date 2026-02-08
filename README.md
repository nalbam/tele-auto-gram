# TeleAutoGram

Telegram auto-response bot built with Telethon. Manage configuration and authentication via a web UI, and automatically respond to private messages.

## Features

- **Auto Response**: Sends an automatic reply 3–10 seconds after receiving a private message
- **Manual Reply**: Select a conversation in the web UI and send messages directly
- **AI Response**: Intelligent auto-responses powered by the OpenAI API (optional)
- **Web-based Auth**: Enter Telegram verification codes and 2FA passwords from your browser
- **Message History**: Stores sent/received messages locally as JSON (last 7 days, per-sender files)
- **Web UI**: Modern management interface (settings, auth, conversations, manual reply)
- **Docker Support**: Full web-based authentication for non-interactive environments

## Getting Started

### Prerequisites

- Python 3.8+ or Docker
- A Telegram account
- API ID and API Hash (from [my.telegram.org](https://my.telegram.org))

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
LOG_LEVEL=INFO
```

## Usage

1. **Configure**: Enter API ID, API Hash, and phone number in the Settings tab
2. **Restart server**: Restart after saving settings
3. **Authenticate**: Enter the Telegram verification code in the Auth tab (and 2FA password if enabled)
4. **Auto response**: After authentication, incoming private messages get an automatic reply after 3–10 seconds
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
├── requirements.txt     # Dependencies
├── .env.example         # Environment variable example
├── CLAUDE.md            # AI coding assistant instructions
├── Dockerfile           # Docker image build config
├── docker-compose.yml   # Docker Compose config
├── templates/
│   └── index.html       # Web UI template
├── docs/
│   └── USAGE_GUIDE.md   # Usage guide and troubleshooting
├── .github/workflows/
│   └── docker-build.yml # CI/CD auto image build
└── data/                # Data directory (auto-created, Docker volume mount target)
    ├── config.json      # Configuration file
    ├── IDENTITY.md      # AI persona/identity prompt
    ├── messages/        # Per-sender message history
    │   ├── {sender_id}.json  # Message history (auto-pruned after 7 days)
    │   └── {sender_id}.md    # Sender profile (auto-updated by AI)
    └── bot_session.session   # Telethon session file
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
    "summary": "Summary",
    "sender_id": 123456789
  }
]
```

The `sender_id` is the Telegram user ID used for manual replies.

Messages older than 7 days are automatically pruned.

## Security

- This bot is designed to run only on localhost (127.0.0.1)
- Never share your API keys or session files
- Sensitive files are included in `.gitignore`

## License

MIT License

## Contributing

Issues and pull requests are always welcome!
