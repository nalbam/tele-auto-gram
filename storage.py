import json
import os
from datetime import datetime, timedelta

MESSAGES_DIR = 'data/messages'
LEGACY_MESSAGES_FILE = 'data/messages.json'
FALLBACK_SENDER_ID = '_unknown'


def ensure_messages_dir():
    """Ensure messages directory exists"""
    os.makedirs(MESSAGES_DIR, exist_ok=True)


def _sender_filepath(sender_id):
    """Return file path for a sender's messages"""
    return os.path.join(MESSAGES_DIR, f'{sender_id}.json')


def _load_sender_messages(sender_id):
    """Load messages for a single sender with 7-day auto-prune"""
    filepath = _sender_filepath(sender_id)
    if not os.path.exists(filepath):
        return []

    with open(filepath, 'r', encoding='utf-8') as f:
        messages = json.load(f)

    cutoff_date = datetime.now() - timedelta(days=7)
    filtered = [
        msg for msg in messages
        if datetime.fromisoformat(msg['timestamp']) > cutoff_date
    ]

    if len(filtered) < len(messages):
        _save_sender_messages(sender_id, filtered)

    return filtered


def _save_sender_messages(sender_id, messages):
    """Save messages for a single sender. Deletes file if empty."""
    ensure_messages_dir()
    filepath = _sender_filepath(sender_id)

    if not messages:
        if os.path.exists(filepath):
            os.remove(filepath)
        return

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(messages, f, indent=2, ensure_ascii=False)


def _migrate_legacy_messages():
    """Migrate legacy messages.json to per-sender files"""
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


def load_messages():
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


def save_messages(messages):
    """Save messages grouped by sender_id (backward-compatible bulk save)"""
    ensure_messages_dir()

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


def get_messages_by_sender(sender_id, limit=20):
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

    messages = _load_sender_messages(str(sender_id))
    return messages[-limit:]


def _sender_profile_path(sender_id):
    """Return file path for a sender's profile"""
    return os.path.join(MESSAGES_DIR, f'{sender_id}.md')


def load_sender_profile(sender_id):
    """Load sender profile markdown. Returns empty string if not exists."""
    ensure_messages_dir()
    filepath = _sender_profile_path(str(sender_id))
    if not os.path.exists(filepath):
        return ''
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def save_sender_profile(sender_id, content):
    """Save sender profile markdown."""
    ensure_messages_dir()
    filepath = _sender_profile_path(str(sender_id))
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)


def add_message(direction, sender, text, summary=None, sender_id=None):
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
    messages = _load_sender_messages(sid)
    messages.append(message)
    _save_sender_messages(sid, messages)

    return message
