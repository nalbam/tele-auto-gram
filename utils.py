import re
import requests
from datetime import datetime

# API request timeout in seconds
API_TIMEOUT = 10

def summarize_message(text):
    """Summarize a message (simple implementation)
    
    For a production system, you might want to use an AI API like OpenAI
    For now, we'll use a simple summarization approach
    """
    # Remove extra whitespace
    text = ' '.join(text.split())
    
    # If message is short, return as is
    if len(text) <= 100:
        return text
    
    # Extract key information (simple approach)
    # Take first sentence or first 100 characters
    sentences = re.split(r'[.!?]\s+', text)
    if sentences and len(sentences[0]) <= 100:
        return sentences[0] + ('.' if not sentences[0].endswith(('.', '!', '?')) else '')
    
    return text[:97] + '...'

def notify_api(summary, sender, notify_url):
    """Notify external API about new message
    
    Args:
        summary: Message summary
        sender: Sender name/id
        notify_url: URL to notify
    """
    if not notify_url:
        return None
    
    try:
        payload = {
            'timestamp': datetime.now().isoformat(),
            'sender': sender,
            'summary': summary
        }
        
        response = requests.post(
            notify_url,
            json=payload,
            timeout=API_TIMEOUT
        )
        
        return {
            'status_code': response.status_code,
            'success': response.status_code == 200
        }
    except Exception as e:
        print(f"Error notifying API: {e}")
        return {
            'error': str(e),
            'success': False
        }
