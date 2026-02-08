# Development Guide

Guide for setting up the development environment, running tests, and contributing to TeleAutoGram.

## Prerequisites

- **Python 3.12+** (required — code uses `dict[str, Any]`, `str | None` syntax)
- **pip** (Python package manager)
- **Git**

## Setup

### 1. Clone the Repository

```bash
git clone https://github.com/nalbam/tele-auto-gram.git
cd tele-auto-gram
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows
```

### 3. Install Dependencies

```bash
# Production + development dependencies
pip install -r requirements-dev.txt
```

This installs:
- **telethon** — Telegram client
- **flask** — Web framework
- **openai** — AI response generation
- **python-dotenv** — Environment variable loading
- **watchdog** — File change detection
- **pytest** — Test framework
- **pytest-asyncio** — Async test support

### 4. Configure Environment

```bash
cp .env.example .env.local
```

Edit `.env.local` with your Telegram API credentials:

```conf
API_ID=your_api_id
API_HASH=your_api_hash
PHONE=+821012345678
LOG_LEVEL=DEBUG
```

> `.env.local` is gitignored and overrides `.env` values.

## Running Locally

### Standard Mode

```bash
python main.py
```

Opens web UI at `http://127.0.0.1:5000`.

### Dev Mode (Auto-Restart)

```bash
watchmedo auto-restart --patterns="*.py;*.html" --recursive -- python main.py
```

Automatically restarts the server when Python or HTML files change.

### Background / Service

```bash
./ctl.sh start     # Start in background
./ctl.sh stop      # Stop
./ctl.sh status    # Check status
./ctl.sh logs      # Tail logs
```

## Testing

### Running Tests

```bash
python -m pytest tests/ -v
```

### Test Structure

```
tests/
├── __init__.py
├── test_ai.py        # AI module: build_chat_messages, is_trivial_message, generate_response
├── test_bot.py       # Bot module: auth flow, message handling, debounce, delay parsing
├── test_config.py    # Config module: load/save config, identity, is_configured
├── test_mask.py      # Masking utility: mask_value, is_masked
├── test_storage.py   # Storage module: add/load messages, profiles, sync markers, migration
└── test_web.py       # Web API: all endpoints, rate limiting, auth, validation
```

### Test Patterns

**File-based config/storage isolation** — use `monkeypatch` + `tmp_path`:

```python
def test_save_config(monkeypatch, tmp_path):
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(config, 'CONFIG_FILE', str(config_file))
    monkeypatch.setattr(config, 'ensure_data_dir', lambda: None)

    config.save_config({"API_ID": "123"})

    with open(config_file) as f:
        saved = json.load(f)
    assert saved["API_ID"] == "123"
```

**Async OpenAI mocking** — use `unittest.mock.AsyncMock`:

```python
async def test_generate_response(monkeypatch):
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    monkeypatch.setattr(ai, '_get_client', lambda key: mock_client)

    result = await ai.generate_response(messages, api_key="test-key")
    assert result == "Expected response"
```

**Flask API testing** — use `test_client`:

```python
def test_get_config(client, monkeypatch):
    monkeypatch.setattr(config, 'load_config', lambda: {"API_ID": "123"})
    response = client.get('/api/config')
    assert response.status_code == 200
```

### Writing New Tests

1. Create test functions in the appropriate `tests/test_*.py` file
2. Use `monkeypatch` to isolate file system operations
3. Use `tmp_path` for temporary directories
4. Use `AsyncMock` for async external calls
5. Use recent timestamps (within 7 days) for storage tests — older messages are auto-pruned

## Project Conventions

### Code Style

- **Type hints**: Python 3.12 style (`dict[str, Any]`, `str | None`, `tuple[float, float]`)
- **Docstrings**: Google style with Args/Returns/Raises sections
- **Logging**: `logging.getLogger(__name__)` per module
- **Constants**: Module-level UPPER_CASE
- **Private functions**: Prefixed with `_`

### File Size

- Target: 200–400 lines
- Maximum: 800 lines
- Split when approaching 500+ lines

### Function Size

- Target: under 50 lines
- Extract helper functions for complex logic
- Single responsibility per function

### Error Handling

- Catch specific exceptions, not bare `except`
- Log errors server-side, return generic messages to clients
- Use fallback values for non-critical failures (e.g., AI response fallback)

## Adding New Features

### New API Endpoint

1. Add route in `web.py`:
```python
@app.route('/api/new-endpoint', methods=['GET'])
def new_endpoint():
    # Rate limiting and auth are handled by before_request hooks
    return jsonify({'data': 'value'})
```

2. For POST endpoints, the request body is automatically validated for `application/json` content type.

3. Add tests in `tests/test_web.py`.

### New Bot Event Handler

1. Add handler function in `bot.py` (module-level, not as closure):
```python
async def _handle_new_event(cl: TelegramClient, event: Any) -> None:
    """Handle the new event type"""
    # implementation
```

2. Register in `start_bot()`:
```python
@cl.on(events.SomeEvent())
async def on_some_event(event):
    await _handle_new_event(cl, event)
```

3. Add tests in `tests/test_bot.py`.

### New Configuration Option

1. Add default value in `config.py:load_config()`:
```python
config = {
    # ... existing keys ...
    'NEW_OPTION': os.getenv('NEW_OPTION', 'default_value'),
}
```

2. Add to `.env.example` with documentation comment.

3. If configurable via web UI, add the input field in `templates/index.html`.

4. Add validation in `web.py:save_config()` if needed.

## Docker

### Local Build

```bash
docker build -t tele-auto-gram .
```

### Run Container

```bash
docker run -d \
  -p 5000:5000 \
  -v $(pwd)/data:/app/data \
  -e API_ID=your_api_id \
  -e API_HASH=your_api_hash \
  -e PHONE=+821012345678 \
  --name tele-auto-gram \
  tele-auto-gram
```

### Docker Compose

```bash
docker-compose up -d      # Start
docker-compose logs -f     # View logs
docker-compose down        # Stop and remove
```

The `data/` directory is mounted as a volume to persist session files, configuration, and message history across container restarts.

## CI/CD

### GitHub Actions Workflow

The project uses a single workflow (`.github/workflows/docker-build.yml`) that triggers on semver tags:

1. **Trigger**: Push a tag matching `v*.*.*` (e.g., `v1.0.0`)
2. **Build**: Docker Buildx builds the image with layer caching (GitHub Actions cache)
3. **Push**: Image is pushed to GitHub Container Registry (`ghcr.io/nalbam/tele-auto-gram`)
4. **Tags**: Automatically generates `latest`, major, minor, patch, and SHA tags

### Release Process

```bash
git tag v1.0.0
git push origin v1.0.0
# GitHub Actions automatically builds and pushes Docker image
```

## Troubleshooting

### Tests failing with "messages pruned"

Storage auto-prunes messages older than 7 days. Always use recent timestamps in tests:

```python
from datetime import datetime
msg = {"timestamp": datetime.now().isoformat(), ...}
```

### `Edit tool requires exact whitespace match`

When using Claude Code to edit files, always re-read the file before editing. The Edit tool matches exact strings including whitespace.

### Import errors when running tests

Make sure you're running from the project root:

```bash
python -m pytest tests/ -v
```

Not from within the `tests/` directory.

### Port 5000 already in use

```bash
lsof -i :5000        # Find the process
kill <PID>           # Kill it
# Or use a different port:
PORT=5001 python main.py
```

### Bot not responding to messages

1. Check auth status at `http://127.0.0.1:5000` (Auth tab)
2. Verify `LOG_LEVEL=DEBUG` for detailed logs
3. Ensure the bot is running (look for "Bot is running..." in logs)
4. Check that messages are private (group messages are ignored)
