import json
import os
from datetime import datetime, timedelta

MESSAGES_FILE = 'data/messages.json'

def ensure_data_dir():
    """Ensure data directory exists"""
    os.makedirs('data', exist_ok=True)

def load_messages():
    """Load messages from storage"""
    ensure_data_dir()
    if not os.path.exists(MESSAGES_FILE):
        return []
    
    with open(MESSAGES_FILE, 'r', encoding='utf-8') as f:
        messages = json.load(f)
    
    # Filter messages from last 7 days
    cutoff_date = datetime.now() - timedelta(days=7)
    filtered_messages = [
        msg for msg in messages
        if datetime.fromisoformat(msg['timestamp']) > cutoff_date
    ]
    
    # Save filtered messages back if we removed any
    if len(filtered_messages) < len(messages):
        save_messages(filtered_messages)
    
    return filtered_messages

def save_messages(messages):
    """Save messages to storage"""
    ensure_data_dir()
    with open(MESSAGES_FILE, 'w', encoding='utf-8') as f:
        json.dump(messages, f, indent=2, ensure_ascii=False)

def get_messages_by_sender(sender_name, limit=20):
    """Get recent messages for a specific sender

    Filters received messages from sender_name and the sent responses
    that immediately follow them (paired conversation flow).

    Args:
        sender_name: Name of the sender to filter by
        limit: Maximum number of messages to return

    Returns:
        List of messages involving the sender, sorted by time (oldest first)
    """
    messages = load_messages()
    sender_messages = []

    for i, msg in enumerate(messages):
        if msg['direction'] == 'received' and msg['sender'] == sender_name:
            sender_messages.append(msg)
            # Include the paired sent response if it follows immediately
            if (i + 1 < len(messages)
                    and messages[i + 1]['direction'] == 'sent'
                    and messages[i + 1]['sender'] == 'Me'):
                sender_messages.append(messages[i + 1])

    return sender_messages[-limit:]


def add_message(direction, sender, text, summary=None):
    """Add a message to storage
    
    Args:
        direction: 'received' or 'sent'
        sender: sender name or id
        text: message text
        summary: optional message summary
    """
    messages = load_messages()
    
    message = {
        'timestamp': datetime.now().isoformat(),
        'direction': direction,
        'sender': sender,
        'text': text,
        'summary': summary
    }
    
    messages.append(message)
    save_messages(messages)
    
    return message
