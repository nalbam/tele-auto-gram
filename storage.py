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
