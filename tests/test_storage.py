"""Tests for storage module"""
import json
import os
import threading
import pytest


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Isolate storage module from real filesystem"""
    import storage

    messages_dir = str(tmp_path / 'messages')
    legacy_file = str(tmp_path / 'messages.json')

    monkeypatch.setattr('storage.MESSAGES_DIR', messages_dir)
    monkeypatch.setattr('storage.LEGACY_MESSAGES_FILE', legacy_file)

    # Reset migration state
    monkeypatch.setattr('storage._migration_done', False)

    # Reset locks
    monkeypatch.setattr('storage._locks', {})

    yield tmp_path


def test_add_message_creates_file():
    """add_message creates sender file and returns message dict"""
    import storage
    msg = storage.add_message('received', 'Alice', 'Hello', sender_id=123)
    assert msg['direction'] == 'received'
    assert msg['sender'] == 'Alice'
    assert msg['text'] == 'Hello'
    assert msg['sender_id'] == 123
    assert 'timestamp' in msg


def test_get_messages_by_sender():
    """get_messages_by_sender returns messages for a specific sender"""
    import storage
    storage.add_message('received', 'Bob', 'Hi', sender_id=456)
    storage.add_message('sent', 'Me', 'Hey', sender_id=456)

    messages = storage.get_messages_by_sender(456)
    assert len(messages) == 2
    assert messages[0]['text'] == 'Hi'
    assert messages[1]['text'] == 'Hey'


def test_get_messages_by_sender_limit():
    """get_messages_by_sender respects limit parameter"""
    import storage
    for i in range(10):
        storage.add_message('received', 'User', f'msg{i}', sender_id=789)

    messages = storage.get_messages_by_sender(789, limit=3)
    assert len(messages) == 3
    assert messages[0]['text'] == 'msg7'


def test_get_messages_by_sender_empty():
    """get_messages_by_sender returns empty list for unknown sender"""
    import storage
    messages = storage.get_messages_by_sender(999)
    assert messages == []


def test_load_messages_all():
    """load_messages returns all messages sorted by timestamp"""
    import storage
    storage.add_message('received', 'A', 'first', sender_id=1)
    storage.add_message('received', 'B', 'second', sender_id=2)

    all_msgs = storage.load_messages()
    assert len(all_msgs) == 2
    # Sorted by timestamp
    assert all_msgs[0]['text'] == 'first'
    assert all_msgs[1]['text'] == 'second'


def test_auto_prune_old_messages(tmp_path):
    """Messages older than 7 days are pruned on load"""
    import storage
    from datetime import datetime, timedelta

    old_timestamp = (datetime.now() - timedelta(days=8)).isoformat()
    new_timestamp = datetime.now().isoformat()

    messages = [
        {'timestamp': old_timestamp, 'direction': 'received', 'sender': 'X', 'text': 'old', 'summary': None},
        {'timestamp': new_timestamp, 'direction': 'received', 'sender': 'X', 'text': 'new', 'summary': None},
    ]

    os.makedirs(storage.MESSAGES_DIR, exist_ok=True)
    filepath = os.path.join(storage.MESSAGES_DIR, '100.json')
    with open(filepath, 'w') as f:
        json.dump(messages, f)

    result = storage.get_messages_by_sender(100)
    assert len(result) == 1
    assert result[0]['text'] == 'new'


def test_sender_profile_save_and_load():
    """save_sender_profile + load_sender_profile roundtrip"""
    import storage
    storage.save_sender_profile(123, '- Prefers Korean\n- Works at Acme')
    profile = storage.load_sender_profile(123)
    assert 'Prefers Korean' in profile
    assert 'Acme' in profile


def test_sender_profile_empty():
    """load_sender_profile returns empty string for unknown sender"""
    import storage
    assert storage.load_sender_profile(999) == ''


def test_legacy_migration(tmp_path):
    """Legacy messages.json is migrated to per-sender files"""
    import storage
    from datetime import datetime, timedelta
    legacy_file = storage.LEGACY_MESSAGES_FILE

    # Use recent timestamps so they don't get pruned
    recent = datetime.now().isoformat()
    legacy_messages = [
        {'timestamp': recent, 'direction': 'received',
         'sender': 'Alice', 'text': 'hello', 'sender_id': 111, 'summary': None},
        {'timestamp': recent, 'direction': 'received',
         'sender': 'Bob', 'text': 'hi', 'sender_id': 222, 'summary': None},
    ]

    with open(legacy_file, 'w') as f:
        json.dump(legacy_messages, f)

    # Trigger migration via load_messages
    all_msgs = storage.load_messages()
    assert len(all_msgs) == 2

    # Legacy file should be renamed to .bak
    assert not os.path.exists(legacy_file)
    assert os.path.exists(legacy_file + '.bak')


def test_legacy_migration_empty(tmp_path):
    """Empty legacy file is handled gracefully"""
    import storage
    legacy_file = storage.LEGACY_MESSAGES_FILE

    with open(legacy_file, 'w') as f:
        json.dump([], f)

    storage.load_messages()
    assert os.path.exists(legacy_file + '.bak')


def test_delete_empty_sender_file(tmp_path):
    """Saving empty messages list deletes the sender file"""
    import storage
    storage.add_message('received', 'X', 'test', sender_id=50)
    filepath = os.path.join(storage.MESSAGES_DIR, '50.json')
    assert os.path.exists(filepath)

    storage._save_sender_messages('50', [])
    assert not os.path.exists(filepath)


def test_add_message_without_sender_id():
    """Messages without sender_id use fallback sender"""
    import storage
    msg = storage.add_message('received', 'Unknown', 'no id')
    assert 'sender_id' not in msg

    # Should be stored under _unknown
    filepath = os.path.join(storage.MESSAGES_DIR, '_unknown.json')
    assert os.path.exists(filepath)


def test_lru_lock_eviction(monkeypatch):
    """_get_lock evicts oldest unlocked entry when over MAX_LOCKS"""
    import storage
    monkeypatch.setattr('storage.MAX_LOCKS', 3)
    monkeypatch.setattr('storage._locks', {})

    storage._get_lock('a')
    storage._get_lock('b')
    storage._get_lock('c')
    assert len(storage._locks) == 3

    # Adding 4th should evict 'a' (oldest, unlocked)
    storage._get_lock('d')
    assert 'a' not in storage._locks
    assert 'd' in storage._locks


def test_lru_lock_reuse_moves_to_end(monkeypatch):
    """Accessing existing lock moves it to end (most recently used)"""
    import storage
    monkeypatch.setattr('storage.MAX_LOCKS', 3)
    monkeypatch.setattr('storage._locks', {})

    storage._get_lock('a')
    storage._get_lock('b')
    storage._get_lock('c')

    # Re-access 'a' to move it to end
    storage._get_lock('a')

    # Adding 4th should now evict 'b' (oldest after 'a' was moved)
    storage._get_lock('d')
    assert 'a' in storage._locks
    assert 'b' not in storage._locks
    assert 'd' in storage._locks
