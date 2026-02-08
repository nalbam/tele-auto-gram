import os
import json
from dotenv import load_dotenv

load_dotenv()

CONFIG_FILE = 'data/config.json'

def ensure_data_dir():
    """Ensure data directory exists"""
    os.makedirs('data', exist_ok=True)

def load_config():
    """Load configuration from file or environment"""
    ensure_data_dir()
    
    config = {
        'API_ID': os.getenv('API_ID'),
        'API_HASH': os.getenv('API_HASH'),
        'PHONE': os.getenv('PHONE'),
        'NOTIFY_API_URL': os.getenv('NOTIFY_API_URL', ''),
        'AUTO_RESPONSE_MESSAGE': os.getenv('AUTO_RESPONSE_MESSAGE', '잠시 후 응답드리겠습니다. 조금만 기다려주세요.')
    }
    
    # Load from config file if exists
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            file_config = json.load(f)
            config.update(file_config)
    
    return config

def save_config(config):
    """Save configuration to file"""
    ensure_data_dir()
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def is_configured():
    """Check if bot is configured"""
    config = load_config()
    return config.get('API_ID') and config.get('API_HASH') and config.get('PHONE')
