import os
import json
from dotenv import load_dotenv

load_dotenv('.env')
load_dotenv('.env.local', override=True)

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
        'AUTO_RESPONSE_MESSAGE': os.getenv('AUTO_RESPONSE_MESSAGE', 'I will get back to you shortly. Please wait a moment.'),
        'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY', ''),
        'OPENAI_MODEL': os.getenv('OPENAI_MODEL', 'gpt-4o-mini'),
        'RESPONSE_DELAY_MIN': int(os.getenv('RESPONSE_DELAY_MIN', '3')),
        'RESPONSE_DELAY_MAX': int(os.getenv('RESPONSE_DELAY_MAX', '10')),
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

IDENTITY_FILE = 'data/IDENTITY.md'

DEFAULT_IDENTITY = """# Identity

You are a friendly conversational partner. Respond naturally and concisely.
""".lstrip()


def load_identity():
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


def _migrate_system_prompt():
    """Migrate SYSTEM_PROMPT from config.json to IDENTITY.md"""
    if not os.path.exists(CONFIG_FILE):
        return
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        file_config = json.load(f)
    prompt = file_config.pop('SYSTEM_PROMPT', None)
    if prompt:
        save_identity(prompt)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(file_config, f, indent=2, ensure_ascii=False)


def save_identity(content):
    """Save identity prompt to data/IDENTITY.md"""
    ensure_data_dir()
    with open(IDENTITY_FILE, 'w', encoding='utf-8') as f:
        f.write(content)


def is_configured():
    """Check if bot is configured"""
    config = load_config()
    return config.get('API_ID') and config.get('API_HASH') and config.get('PHONE')
