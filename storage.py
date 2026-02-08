import json
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

MESSAGES_DIR = 'data/messages'
LEGACY_MESSAGES_FILE = 'data/messages.json'
FALLBACK_SENDER_ID = '_unknown'

# Per-sender file locks to prevent race conditions (LRU-bounded)
MAX_LOCKS = 1000
_locks = {}
_locks_lock = threading.Lock()

# Thread-safe migration flag to avoid repeated legacy migration checks
_migration_lock = threading.Lock()
_migration_done = False


def _get_lock(sender_id: str) -> threading.Lock:
    """Get or create a lock for a sender_id (LRU eviction when over MAX_LOCKS)"""
    with _locks_lock:
        if sender_id in _locks:
            # Move to end (most recently used)
            _locks[sender_id] = _locks.pop(sender_id)
            return _locks[sender_id]
        # Evict oldest unlocked entries if over threshold
        while len(_locks) >= MAX_LOCKS:
            oldest_key = next(iter(_locks))
            lock = _locks[oldest_key]
            if not lock.locked():
                del _locks[oldest_key]
            else:
                break
        _locks[sender_id] = threading.Lock()
        return _locks[sender_id]


def ensure_messages_dir() -> None:
    """Ensure messages directory exists"""
    os.makedirs(MESSAGES_DIR, exist_ok=True)


def _sender_filepath(sender_id: str) -> str:
    """Return file path for a sender's messages"""
    return os.path.join(MESSAGES_DIR, f'{sender_id}.json')


def _parse_timestamp(ts: str) -> datetime:
    """Parse ISO timestamp, ensuring timezone-aware (naive assumed UTC)"""
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _load_sender_messages(sender_id: str) -> list[dict[str, Any]]:
    """Load messages for a single sender with 7-day auto-prune"""
    filepath = _sender_filepath(sender_id)
    if not os.path.exists(filepath):
        return []

    with open(filepath, 'r', encoding='utf-8') as f:
        messages = json.load(f)

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)
    filtered = [
        msg for msg in messages
        if _parse_timestamp(msg['timestamp']) > cutoff_date
    ]

    if len(filtered) < len(messages):
        _save_sender_messages(sender_id, filtered)

    return filtered


def _save_sender_messages(sender_id: str, messages: list[dict[str, Any]]) -> None:
    """Save messages for a single sender. Deletes file if empty."""
    ensure_messages_dir()
    filepath = _sender_filepath(sender_id)

    if not messages:
        if os.path.exists(filepath):
            os.remove(filepath)
        return

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(messages, f, indent=2, ensure_ascii=False)


def _migrate_legacy_messages() -> None:
    """Migrate legacy messages.json to per-sender files (runs once)"""
    global _migration_done
    if _migration_done:
        return
    with _migration_lock:
        if _migration_done:
            return
        _migration_done = True

    if not os.path.exists(LEGACY_MESSAGES_FILE):
        return

    with open(LEGACY_MESSAGES_FILE, 'r', encoding='utf-8') as f:
        messages = json.load(f)

    if not messages:
        os.rename(LEGACY_MESSAGES_FILE, LEGACY_MESSAGES_FILE + '.bak')
        return

    ensure_messages_dir()

    # Group messages by sender_id
    grouped = {}
    for msg in messages:
        sid = msg.get('sender_id')
        if sid is None:
            sid = FALLBACK_SENDER_ID
        else:
            sid = str(sid)
        grouped.setdefault(sid, []).append(msg)

    for sid, msgs in grouped.items():
        _save_sender_messages(sid, msgs)

    os.rename(LEGACY_MESSAGES_FILE, LEGACY_MESSAGES_FILE + '.bak')


def load_messages() -> list[dict[str, Any]]:
    """Load all messages from all sender files, merged and sorted by time"""
    _migrate_legacy_messages()
    ensure_messages_dir()

    all_messages = []
    for filename in os.listdir(MESSAGES_DIR):
        if not filename.endswith('.json'):
            continue
        sender_id = filename[:-5]  # strip .json
        all_messages.extend(_load_sender_messages(sender_id))

    all_messages.sort(key=lambda msg: msg['timestamp'])
    return all_messages


def get_messages_by_sender(sender_id: int | str, limit: int = 20) -> list[dict[str, Any]]:
    """Get recent messages for a specific sender

    Loads only the sender's file instead of all messages.

    Args:
        sender_id: Telegram user ID (int or str)
        limit: Maximum number of messages to return

    Returns:
        List of messages involving the sender, sorted by time (oldest first)
    """
    _migrate_legacy_messages()
    ensure_messages_dir()

    sid = str(sender_id)
    with _get_lock(sid):
        messages = _load_sender_messages(sid)
    return messages[-limit:]


def _sender_profile_path(sender_id: str) -> str:
    """Return file path for a sender's profile"""
    return os.path.join(MESSAGES_DIR, f'{sender_id}.md')


def load_sender_profile(sender_id: int | str) -> str:
    """Load sender profile markdown. Returns empty string if not exists."""
    ensure_messages_dir()
    sid = str(sender_id)
    with _get_lock(sid):
        filepath = _sender_profile_path(sid)
        if not os.path.exists(filepath):
            return ''
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()


def save_sender_profile(sender_id: int | str, content: str) -> None:
    """Save sender profile markdown."""
    ensure_messages_dir()
    sid = str(sender_id)
    with _get_lock(sid):
        filepath = _sender_profile_path(sid)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)


def import_messages(sender_id: int | str, messages: list[dict[str, Any]]) -> None:
    """Import a batch of messages for a sender (e.g., from Telegram history sync).

    Messages are merged with existing ones and sorted by timestamp.

    Args:
        sender_id: Telegram user ID
        messages: List of message dicts to import
    """
    _migrate_legacy_messages()
    ensure_messages_dir()
    sid = str(sender_id)
    with _get_lock(sid):
        existing = _load_sender_messages(sid)
        existing.extend(messages)
        existing.sort(key=lambda msg: msg['timestamp'])
        _save_sender_messages(sid, existing)


def add_message(direction: str, sender: str, text: str, summary: str | None = None, sender_id: int | None = None) -> dict[str, Any]:
    """Add a message to storage

    Args:
        direction: 'received' or 'sent'
        sender: sender name or id
        text: message text
        summary: optional message summary
        sender_id: optional Telegram user ID for reply support
    """
    _migrate_legacy_messages()

    message = {
        'timestamp': datetime.now().isoformat(),
        'direction': direction,
        'sender': sender,
        'text': text,
        'summary': summary
    }

    if sender_id is not None:
        message['sender_id'] = sender_id

    sid = str(sender_id) if sender_id is not None else FALLBACK_SENDER_ID
    with _get_lock(sid):
        messages = _load_sender_messages(sid)
        messages.append(message)
        _save_sender_messages(sid, messages)

    return message
