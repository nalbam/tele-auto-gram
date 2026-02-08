"""Tests for config module"""
import json
import os
import pytest


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Isolate config module from real filesystem and env"""
    config_file = str(tmp_path / 'config.json')
    identity_file = str(tmp_path / 'IDENTITY.md')
    data_dir = str(tmp_path)

    monkeypatch.setattr('config.CONFIG_FILE', config_file)
    monkeypatch.setattr('config.IDENTITY_FILE', identity_file)

    # Patch ensure_data_dir to use tmp_path
    monkeypatch.setattr('config.ensure_data_dir', lambda: os.makedirs(data_dir, exist_ok=True))

    # Clear relevant env vars
    for key in ('API_ID', 'API_HASH', 'PHONE', 'AUTO_RESPONSE_MESSAGE',
                'OPENAI_API_KEY', 'OPENAI_MODEL', 'RESPONSE_DELAY_MIN', 'RESPONSE_DELAY_MAX'):
        monkeypatch.delenv(key, raising=False)

    yield tmp_path


def test_load_config_defaults():
    """load_config returns defaults when no env or file config"""
    import config
    cfg = config.load_config()
    assert cfg['API_ID'] is None
    assert cfg['API_HASH'] is None
    assert cfg['PHONE'] is None
    assert cfg['AUTO_RESPONSE_MESSAGE'] == 'I will get back to you shortly. Please wait a moment.'
    assert cfg['OPENAI_API_KEY'] == ''
    assert cfg['OPENAI_MODEL'] == 'gpt-4o-mini'
    assert cfg['RESPONSE_DELAY_MIN'] == 3
    assert cfg['RESPONSE_DELAY_MAX'] == 10


def test_load_config_from_env(monkeypatch):
    """load_config reads from environment variables"""
    import config
    monkeypatch.setenv('API_ID', '12345')
    monkeypatch.setenv('API_HASH', 'abc123')
    monkeypatch.setenv('PHONE', '+821012345678')
    cfg = config.load_config()
    assert cfg['API_ID'] == '12345'
    assert cfg['API_HASH'] == 'abc123'
    assert cfg['PHONE'] == '+821012345678'


def test_load_config_file_overrides_env(monkeypatch):
    """File config overrides environment variables"""
    import config
    monkeypatch.setenv('API_ID', '12345')
    monkeypatch.setenv('API_HASH', 'from_env')

    # Write file config
    with open(config.CONFIG_FILE, 'w') as f:
        json.dump({'API_HASH': 'from_file'}, f)

    cfg = config.load_config()
    assert cfg['API_ID'] == '12345'
    assert cfg['API_HASH'] == 'from_file'


def test_save_and_load_config_roundtrip():
    """save_config + load_config roundtrip preserves data"""
    import config
    data = {'API_ID': '999', 'API_HASH': 'test_hash', 'PHONE': '+1234'}
    config.save_config(data)
    cfg = config.load_config()
    assert cfg['API_ID'] == '999'
    assert cfg['API_HASH'] == 'test_hash'
    assert cfg['PHONE'] == '+1234'


def test_load_config_invalid_json(tmp_path):
    """load_config handles corrupt config.json gracefully"""
    import config
    with open(config.CONFIG_FILE, 'w') as f:
        f.write('{broken json')
    cfg = config.load_config()
    # Should return defaults without crashing
    assert cfg['API_ID'] is None


def test_safe_int_valid():
    """_safe_int converts valid values"""
    import config
    assert config._safe_int('42', 0) == 42
    assert config._safe_int(10, 0) == 10


def test_safe_int_invalid():
    """_safe_int returns default on invalid values"""
    import config
    assert config._safe_int('abc', 5) == 5
    assert config._safe_int(None, 7) == 7
    assert config._safe_int('', 3) == 3


def test_is_configured_false():
    """is_configured returns falsy when required fields are missing"""
    import config
    assert not config.is_configured()


def test_is_configured_true(monkeypatch):
    """is_configured returns truthy when all required fields are set"""
    import config
    monkeypatch.setenv('API_ID', '123')
    monkeypatch.setenv('API_HASH', 'abc')
    monkeypatch.setenv('PHONE', '+1234')
    assert config.is_configured()


def test_identity_load_creates_default():
    """load_identity creates default file if missing"""
    import config
    content = config.load_identity()
    assert 'friendly conversational partner' in content
    assert os.path.exists(config.IDENTITY_FILE)


def test_identity_save_and_load():
    """save_identity + load_identity roundtrip"""
    import config
    config.save_identity('Custom persona text')
    assert config.load_identity() == 'Custom persona text'


def test_identity_migration_from_config(tmp_path):
    """load_identity migrates SYSTEM_PROMPT from config.json"""
    import config
    # Write config with SYSTEM_PROMPT
    with open(config.CONFIG_FILE, 'w') as f:
        json.dump({'SYSTEM_PROMPT': 'Migrated prompt', 'API_ID': '123'}, f)

    content = config.load_identity()
    assert content == 'Migrated prompt'

    # SYSTEM_PROMPT should be removed from config.json
    with open(config.CONFIG_FILE, 'r') as f:
        data = json.load(f)
    assert 'SYSTEM_PROMPT' not in data
    assert data['API_ID'] == '123'


def test_response_delay_from_env(monkeypatch):
    """RESPONSE_DELAY_MIN/MAX are read from env as integers"""
    import config
    monkeypatch.setenv('RESPONSE_DELAY_MIN', '5')
    monkeypatch.setenv('RESPONSE_DELAY_MAX', '15')
    cfg = config.load_config()
    assert cfg['RESPONSE_DELAY_MIN'] == 5
    assert cfg['RESPONSE_DELAY_MAX'] == 15
