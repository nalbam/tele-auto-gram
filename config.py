import logging
import os
import json
import tempfile
from typing import Any
from dotenv import load_dotenv

load_dotenv('.env')
load_dotenv('.env.local', override=True)

logger = logging.getLogger(__name__)

CONFIG_FILE = 'data/config.json'


def _safe_int(value: Any, default: int) -> int:
    """Safely convert value to int, returning default on failure"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any, default: bool) -> bool:
    """Safely convert value to bool, returning default on failure.

    Accepts: True/False (bool), 'true'/'false'/'1'/'0' (str), 1/0 (int).
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ('true', '1', 'yes')
    return default


def ensure_data_dir() -> None:
    """Ensure data directory exists"""
    os.makedirs('data', exist_ok=True)


def _secure_write(filepath: str, write_fn: Any) -> None:
    """Write file atomically with restricted permissions.

    Creates a temp file in the same directory, calls write_fn(f) to populate it,
    sets permissions to 0o600, then atomically replaces the target file.
    """
    dir_name = os.path.dirname(filepath) or '.'
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            write_fn(f)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, filepath)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

def load_config() -> dict[str, Any]:
    """Load configuration from file or environment"""
    ensure_data_dir()

    config = {
        'API_ID': os.getenv('API_ID'),
        'API_HASH': os.getenv('API_HASH'),
        'PHONE': os.getenv('PHONE'),
        'AUTO_RESPONSE_MESSAGE': os.getenv('AUTO_RESPONSE_MESSAGE', 'I will get back to you shortly. Please wait a moment.'),
        'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY', ''),
        'OPENAI_MODEL': os.getenv('OPENAI_MODEL', 'gpt-4o-mini'),
        'RESPONSE_DELAY_MIN': _safe_int(os.getenv('RESPONSE_DELAY_MIN'), 3),
        'RESPONSE_DELAY_MAX': _safe_int(os.getenv('RESPONSE_DELAY_MAX'), 10),
        'READ_RECEIPT_DELAY_MIN': _safe_int(os.getenv('READ_RECEIPT_DELAY_MIN'), 3),
        'READ_RECEIPT_DELAY_MAX': _safe_int(os.getenv('READ_RECEIPT_DELAY_MAX'), 10),
        'TYPING_DELAY_MIN': _safe_int(os.getenv('TYPING_DELAY_MIN'), 3),
        'TYPING_DELAY_MAX': _safe_int(os.getenv('TYPING_DELAY_MAX'), 10),
        'RESPOND_TO_BOTS': _safe_bool(os.getenv('RESPOND_TO_BOTS'), False),
    }

    # Load from config file if exists
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                config.update(file_config)
        except (json.JSONDecodeError, OSError) as e:
            logger.error('Failed to load config file: %s', e)

    return config

def save_config(config: dict[str, Any]) -> None:
    """Save configuration to file (atomic write with restricted permissions)"""
    ensure_data_dir()
    _secure_write(CONFIG_FILE, lambda f: json.dump(config, f, indent=2, ensure_ascii=False))

IDENTITY_FILE = 'data/IDENTITY.md'

DEFAULT_IDENTITY = """# Identity

You are a friendly conversational partner. Respond naturally and concisely.
""".lstrip()


def load_identity() -> str:
    """Load identity prompt from data/IDENTITY.md, auto-create if missing.

    Migrates SYSTEM_PROMPT from config.json on first call if IDENTITY.md
    does not exist yet.
    """
    ensure_data_dir()
    if not os.path.exists(IDENTITY_FILE):
        _migrate_system_prompt()
    if not os.path.exists(IDENTITY_FILE):
        save_identity(DEFAULT_IDENTITY)
    with open(IDENTITY_FILE, 'r', encoding='utf-8') as f:
        return f.read()


def _migrate_system_prompt() -> None:
    """Migrate SYSTEM_PROMPT from config.json to IDENTITY.md"""
    if not os.path.exists(CONFIG_FILE):
        return
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            file_config = json.load(f)
    except (json.JSONDecodeError, OSError):
        return
    prompt = file_config.pop('SYSTEM_PROMPT', None)
    if prompt:
        save_identity(prompt)
        _secure_write(CONFIG_FILE, lambda f: json.dump(file_config, f, indent=2, ensure_ascii=False))


def save_identity(content: str) -> None:
    """Save identity prompt to data/IDENTITY.md (atomic write with restricted permissions)"""
    ensure_data_dir()
    _secure_write(IDENTITY_FILE, lambda f: f.write(content))


def is_configured() -> bool:
    """Check if bot is configured"""
    config = load_config()
    return bool(config.get('API_ID') and config.get('API_HASH') and config.get('PHONE'))
