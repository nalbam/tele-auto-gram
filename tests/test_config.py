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


def test_safe_bool_true_values():
    """_safe_bool correctly identifies truthy values"""
    import config
    assert config._safe_bool(True, False) is True
    assert config._safe_bool('true', False) is True
    assert config._safe_bool('True', False) is True
    assert config._safe_bool('1', False) is True
    assert config._safe_bool('yes', False) is True
    assert config._safe_bool(1, False) is True


def test_safe_bool_false_values():
    """_safe_bool correctly identifies falsy values"""
    import config
    assert config._safe_bool(False, True) is False
    assert config._safe_bool('false', True) is False
    assert config._safe_bool('0', True) is False
    assert config._safe_bool('no', True) is False
    assert config._safe_bool(0, True) is False


def test_safe_bool_default():
    """_safe_bool returns default on unrecognized values"""
    import config
    assert config._safe_bool(None, False) is False
    assert config._safe_bool(None, True) is True
    assert config._safe_bool('', False) is False


def test_respond_to_bots_default():
    """RESPOND_TO_BOTS defaults to False"""
    import config
    cfg = config.load_config()
    assert cfg['RESPOND_TO_BOTS'] is False


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


def test_save_config_atomic_write(tmp_path):
    """save_config uses atomic write (no partial file on crash)"""
    import config
    data = {'API_ID': '111', 'PHONE': '+999'}
    config.save_config(data)
    assert os.path.exists(config.CONFIG_FILE)
    # File should be readable and valid JSON
    with open(config.CONFIG_FILE, 'r') as f:
        loaded = json.load(f)
    assert loaded['API_ID'] == '111'


def test_save_config_file_permissions(tmp_path):
    """save_config creates file with 0o600 permissions"""
    import config
    config.save_config({'key': 'value'})
    mode = os.stat(config.CONFIG_FILE).st_mode & 0o777
    assert mode == 0o600


def test_save_identity_file_permissions(tmp_path):
    """save_identity creates file with 0o600 permissions"""
    import config
    config.save_identity('test content')
    mode = os.stat(config.IDENTITY_FILE).st_mode & 0o777
    assert mode == 0o600


def test_secure_write_cleans_up_on_error(tmp_path):
    """_secure_write removes temp file on write failure"""
    import config
    import glob

    filepath = str(tmp_path / 'fail_test.json')

    def bad_writer(f):
        raise RuntimeError("write error")

    with pytest.raises(RuntimeError):
        config._secure_write(filepath, bad_writer)

    # Target file should not exist
    assert not os.path.exists(filepath)
    # No leftover temp files
    temps = glob.glob(str(tmp_path / '*.tmp'))
    assert len(temps) == 0


def test_migrate_system_prompt_uses_secure_write(tmp_path):
    """_migrate_system_prompt uses atomic write for config.json update"""
    import config
    with open(config.CONFIG_FILE, 'w') as f:
        json.dump({'SYSTEM_PROMPT': 'Migrated', 'API_ID': '123'}, f)

    config.load_identity()

    # Config file should have restricted permissions after migration
    mode = os.stat(config.CONFIG_FILE).st_mode & 0o777
    assert mode == 0o600
