"""Tests for web module"""
import json
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def app_client(monkeypatch):
    """Create Flask test client with isolated config"""
    # Prevent bot module from doing real Telegram stuff
    monkeypatch.setattr('bot.client', None)
    monkeypatch.setattr('bot._bot_loop', None)

    import web
    monkeypatch.setattr('web.WEB_TOKEN', '')
    web.app.config['TESTING'] = True
    with web.app.test_client() as client:
        yield client


@pytest.fixture
def authed_client(monkeypatch):
    """Create Flask test client with token auth"""
    monkeypatch.setattr('bot.client', None)
    monkeypatch.setattr('bot._bot_loop', None)

    import web
    monkeypatch.setattr('web.WEB_TOKEN', 'test-token-123')
    web.app.config['TESTING'] = True
    with web.app.test_client() as client:
        yield client


def _json_headers(token=None):
    """Helper to create JSON request headers"""
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    return headers


class TestIndex:
    def test_index_returns_html(self, app_client):
        """GET / returns the web UI page"""
        resp = app_client.get('/')
        assert resp.status_code == 200


class TestConfig:
    def test_get_config(self, app_client, monkeypatch):
        """GET /api/config returns config with masked fields"""
        monkeypatch.setattr('config.load_config', lambda: {
            'API_ID': '123', 'API_HASH': 'abcdefghijklmnop', 'PHONE': '+1234',
            'OPENAI_API_KEY': 'sk-1234567890abcdef'
        })
        monkeypatch.setattr('config.is_configured', lambda: True)

        resp = app_client.get('/api/config')
        data = resp.get_json()
        assert data['API_ID'] == '123'
        assert '***' in data['API_HASH']
        assert '***' in data['OPENAI_API_KEY']
        assert data['is_configured'] is True

    def test_save_config(self, app_client, monkeypatch):
        """POST /api/config saves configuration"""
        saved = {}
        monkeypatch.setattr('config.load_config', lambda: {})
        monkeypatch.setattr('config.save_config', lambda d: saved.update(d))

        resp = app_client.post('/api/config',
                               data=json.dumps({'API_ID': '456', 'PHONE': '+999'}),
                               headers=_json_headers())
        assert resp.status_code == 200
        assert saved['API_ID'] == '456'

    def test_save_config_invalid_api_id(self, app_client, monkeypatch):
        """POST /api/config rejects non-numeric API_ID"""
        monkeypatch.setattr('config.load_config', lambda: {})

        resp = app_client.post('/api/config',
                               data=json.dumps({'API_ID': 'not-a-number'}),
                               headers=_json_headers())
        assert resp.status_code == 400

    def test_save_config_preserves_masked_fields(self, app_client, monkeypatch):
        """POST /api/config preserves real value when masked value is submitted"""
        monkeypatch.setattr('config.load_config', lambda: {
            'API_HASH': 'real_secret_value_here'
        })
        saved = {}
        monkeypatch.setattr('config.save_config', lambda d: saved.update(d))

        resp = app_client.post('/api/config',
                               data=json.dumps({'API_HASH': 'r**************e'}),
                               headers=_json_headers())
        assert resp.status_code == 200
        assert saved['API_HASH'] == 'real_secret_value_here'


class TestMessages:
    def test_get_messages(self, app_client, monkeypatch):
        """GET /api/messages returns stored messages"""
        monkeypatch.setattr('storage.load_messages', lambda: [
            {'text': 'hello', 'direction': 'received'}
        ])
        resp = app_client.get('/api/messages')
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]['text'] == 'hello'

    def test_send_message_success(self, app_client, monkeypatch):
        """POST /api/messages/send sends a message"""
        import bot
        monkeypatch.setattr('bot.get_auth_state', lambda: {'status': 'authorized'})
        monkeypatch.setattr('bot.send_message_to_user', lambda uid, txt: None)
        monkeypatch.setattr('storage.add_message',
                            lambda *a, **kw: {'text': kw.get('text', a[2] if len(a) > 2 else '')})

        resp = app_client.post('/api/messages/send',
                               data=json.dumps({'user_id': 123, 'text': 'hi'}),
                               headers=_json_headers())
        assert resp.status_code == 200

    def test_send_message_storage_failure_still_succeeds(self, app_client, monkeypatch):
        """POST /api/messages/send returns 200 even if storage write fails"""
        monkeypatch.setattr('bot.get_auth_state', lambda: {'status': 'authorized'})
        monkeypatch.setattr('bot.send_message_to_user', lambda uid, txt: None)
        monkeypatch.setattr('storage.add_message',
                            MagicMock(side_effect=OSError("disk full")))

        resp = app_client.post('/api/messages/send',
                               data=json.dumps({'user_id': 123, 'text': 'hi'}),
                               headers=_json_headers())
        assert resp.status_code == 200

    def test_send_message_not_authorized(self, app_client, monkeypatch):
        """POST /api/messages/send fails when bot not authorized"""
        monkeypatch.setattr('bot.get_auth_state', lambda: {'status': 'disconnected'})

        resp = app_client.post('/api/messages/send',
                               data=json.dumps({'user_id': 123, 'text': 'hi'}),
                               headers=_json_headers())
        assert resp.status_code == 400

    def test_send_message_missing_fields(self, app_client):
        """POST /api/messages/send requires user_id and text"""
        resp = app_client.post('/api/messages/send',
                               data=json.dumps({'user_id': 123}),
                               headers=_json_headers())
        assert resp.status_code == 400

    def test_send_message_too_long(self, app_client):
        """POST /api/messages/send rejects messages over 4096 chars"""
        resp = app_client.post('/api/messages/send',
                               data=json.dumps({'user_id': 123, 'text': 'x' * 4097}),
                               headers=_json_headers())
        assert resp.status_code == 400

    def test_send_message_bot_unavailable(self, app_client, monkeypatch):
        """POST /api/messages/send returns 503 when bot is not running"""
        monkeypatch.setattr('bot.get_auth_state', lambda: {'status': 'authorized'})
        monkeypatch.setattr('bot.send_message_to_user',
                            MagicMock(side_effect=RuntimeError("Bot is not running")))

        resp = app_client.post('/api/messages/send',
                               data=json.dumps({'user_id': 123, 'text': 'hi'}),
                               headers=_json_headers())
        assert resp.status_code == 503
        assert 'Bot is not available' in resp.get_json()['message']


class TestIdentity:
    def test_get_identity(self, app_client, monkeypatch):
        """GET /api/identity returns identity content"""
        monkeypatch.setattr('config.load_identity', lambda: 'Test persona')
        resp = app_client.get('/api/identity')
        assert resp.get_json()['content'] == 'Test persona'

    def test_save_identity(self, app_client, monkeypatch):
        """POST /api/identity saves identity content"""
        saved = {}
        monkeypatch.setattr('config.save_identity', lambda c: saved.update({'content': c}))

        resp = app_client.post('/api/identity',
                               data=json.dumps({'content': 'New persona'}),
                               headers=_json_headers())
        assert resp.status_code == 200
        assert saved['content'] == 'New persona'

    def test_save_identity_too_long(self, app_client, monkeypatch):
        """POST /api/identity rejects content over 50000 chars"""
        resp = app_client.post('/api/identity',
                               data=json.dumps({'content': 'x' * 50001}),
                               headers=_json_headers())
        assert resp.status_code == 400


class TestAuth:
    def test_get_auth_status(self, app_client, monkeypatch):
        """GET /api/auth/status returns auth state"""
        monkeypatch.setattr('bot.get_auth_state',
                            lambda: {'status': 'authorized', 'error': None})
        resp = app_client.get('/api/auth/status')
        assert resp.get_json()['status'] == 'authorized'

    def test_submit_auth_code(self, app_client, monkeypatch):
        """POST /api/auth/code submits code"""
        submitted = {}
        monkeypatch.setattr('bot.submit_auth_code', lambda c: submitted.update({'code': c}))

        resp = app_client.post('/api/auth/code',
                               data=json.dumps({'code': '12345'}),
                               headers=_json_headers())
        assert resp.status_code == 200
        assert submitted['code'] == '12345'

    def test_submit_auth_code_empty(self, app_client):
        """POST /api/auth/code requires code"""
        resp = app_client.post('/api/auth/code',
                               data=json.dumps({'code': ''}),
                               headers=_json_headers())
        assert resp.status_code == 400

    def test_submit_auth_password(self, app_client, monkeypatch):
        """POST /api/auth/password submits password"""
        submitted = {}
        monkeypatch.setattr('bot.submit_auth_password', lambda p: submitted.update({'pw': p}))

        resp = app_client.post('/api/auth/password',
                               data=json.dumps({'password': 'secret'}),
                               headers=_json_headers())
        assert resp.status_code == 200
        assert submitted['pw'] == 'secret'

    def test_submit_auth_password_empty(self, app_client):
        """POST /api/auth/password requires password"""
        resp = app_client.post('/api/auth/password',
                               data=json.dumps({'password': ''}),
                               headers=_json_headers())
        assert resp.status_code == 400


class TestTokenAuth:
    def test_api_requires_token(self, authed_client):
        """API endpoints require valid token when WEB_TOKEN is set"""
        resp = authed_client.get('/api/config')
        assert resp.status_code == 401

    def test_api_with_valid_token(self, authed_client, monkeypatch):
        """API endpoints accept valid bearer token"""
        monkeypatch.setattr('config.load_config', lambda: {})
        monkeypatch.setattr('config.is_configured', lambda: False)

        resp = authed_client.get('/api/config',
                                 headers={'Authorization': 'Bearer test-token-123'})
        assert resp.status_code == 200


class TestContentType:
    def test_post_without_json_content_type(self, app_client):
        """POST to /api/* without application/json returns 415"""
        resp = app_client.post('/api/config',
                               data='not json',
                               content_type='text/plain')
        assert resp.status_code == 415

    def test_post_with_json_content_type(self, app_client, monkeypatch):
        """POST to /api/* with application/json is accepted"""
        monkeypatch.setattr('config.load_config', lambda: {})
        monkeypatch.setattr('config.save_config', lambda d: None)

        resp = app_client.post('/api/config',
                               data=json.dumps({'API_ID': '123'}),
                               headers=_json_headers())
        assert resp.status_code == 200


class TestRateLimiting:
    def test_auth_rate_limit(self, app_client, monkeypatch):
        """Auth endpoints are rate limited to 5 requests per minute"""
        import web
        monkeypatch.setattr('bot.submit_auth_code', lambda c: None)

        # Clear rate store to ensure clean state
        web._rate_store.clear()

        for i in range(5):
            resp = app_client.post('/api/auth/code',
                                   data=json.dumps({'code': '12345'}),
                                   headers=_json_headers())
            assert resp.status_code == 200

        # 6th request should be rate limited
        resp = app_client.post('/api/auth/code',
                               data=json.dumps({'code': '12345'}),
                               headers=_json_headers())
        assert resp.status_code == 429
        assert 'Too many requests' in resp.get_json()['message']

    def test_api_rate_limit(self, app_client, monkeypatch):
        """API endpoints are rate limited to 30 requests per minute"""
        import web
        monkeypatch.setattr('config.load_config', lambda: {})
        monkeypatch.setattr('config.is_configured', lambda: False)

        # Clear rate store
        web._rate_store.clear()

        for i in range(30):
            resp = app_client.get('/api/config')
            assert resp.status_code == 200

        # 31st request should be rate limited
        resp = app_client.get('/api/config')
        assert resp.status_code == 429

    def test_non_api_not_rate_limited(self, app_client, monkeypatch):
        """Non-API routes are not rate limited"""
        import web
        web._rate_store.clear()

        for _ in range(50):
            resp = app_client.get('/')
            assert resp.status_code == 200


class TestDelayValidation:
    def test_save_config_delay_negative(self, app_client, monkeypatch):
        """POST /api/config rejects negative delay values"""
        monkeypatch.setattr('config.load_config', lambda: {})

        resp = app_client.post('/api/config',
                               data=json.dumps({'RESPONSE_DELAY_MIN': -1}),
                               headers=_json_headers())
        assert resp.status_code == 400

    def test_save_config_delay_too_large(self, app_client, monkeypatch):
        """POST /api/config rejects delay values over 3600"""
        monkeypatch.setattr('config.load_config', lambda: {})

        resp = app_client.post('/api/config',
                               data=json.dumps({'RESPONSE_DELAY_MAX': 3601}),
                               headers=_json_headers())
        assert resp.status_code == 400

    def test_save_config_delay_min_exceeds_max(self, app_client, monkeypatch):
        """POST /api/config rejects min > max"""
        monkeypatch.setattr('config.load_config', lambda: {})

        resp = app_client.post('/api/config',
                               data=json.dumps({'RESPONSE_DELAY_MIN': 10, 'RESPONSE_DELAY_MAX': 5}),
                               headers=_json_headers())
        assert resp.status_code == 400

    def test_save_config_delay_valid(self, app_client, monkeypatch):
        """POST /api/config accepts valid delay range"""
        monkeypatch.setattr('config.load_config', lambda: {})
        saved = {}
        monkeypatch.setattr('config.save_config', lambda d: saved.update(d))

        resp = app_client.post('/api/config',
                               data=json.dumps({'RESPONSE_DELAY_MIN': 3, 'RESPONSE_DELAY_MAX': 10}),
                               headers=_json_headers())
        assert resp.status_code == 200

    def test_save_config_delay_non_numeric(self, app_client, monkeypatch):
        """POST /api/config rejects non-numeric delay values"""
        monkeypatch.setattr('config.load_config', lambda: {})

        resp = app_client.post('/api/config',
                               data=json.dumps({'RESPONSE_DELAY_MIN': 'abc'}),
                               headers=_json_headers())
        assert resp.status_code == 400


class TestAuthInputLength:
    def test_auth_code_too_long(self, app_client):
        """POST /api/auth/code rejects code longer than 10 chars"""
        resp = app_client.post('/api/auth/code',
                               data=json.dumps({'code': '12345678901'}),
                               headers=_json_headers())
        assert resp.status_code == 400
        assert 'max 10' in resp.get_json()['message']

    def test_auth_code_max_length(self, app_client, monkeypatch):
        """POST /api/auth/code accepts code of exactly 10 chars"""
        monkeypatch.setattr('bot.submit_auth_code', lambda c: None)

        resp = app_client.post('/api/auth/code',
                               data=json.dumps({'code': '1234567890'}),
                               headers=_json_headers())
        assert resp.status_code == 200

    def test_auth_password_too_long(self, app_client):
        """POST /api/auth/password rejects password longer than 256 chars"""
        resp = app_client.post('/api/auth/password',
                               data=json.dumps({'password': 'x' * 257}),
                               headers=_json_headers())
        assert resp.status_code == 400
        assert 'max 256' in resp.get_json()['message']

    def test_auth_password_max_length(self, app_client, monkeypatch):
        """POST /api/auth/password accepts password of exactly 256 chars"""
        monkeypatch.setattr('bot.submit_auth_password', lambda p: None)

        resp = app_client.post('/api/auth/password',
                               data=json.dumps({'password': 'x' * 256}),
                               headers=_json_headers())
        assert resp.status_code == 200


class TestRateLimiterCleanup:
    """Tests for MEDIUM #5: rate limiter stale entry cleanup"""

    def test_stale_entries_cleaned_up(self, monkeypatch):
        """Stale rate limit entries are removed when threshold exceeded"""
        import time
        import web

        monkeypatch.setattr('web._RATE_STORE_CLEANUP_THRESHOLD', 2)

        # Insert stale entries directly
        now = time.monotonic()
        old_time = now - web.RATE_LIMIT_WINDOW - 10  # expired

        with web._rate_lock:
            web._rate_store.clear()
            web._rate_store['api:1.1.1.1'] = [old_time]
            web._rate_store['api:2.2.2.2'] = [old_time]
            web._rate_store['api:3.3.3.3'] = [old_time]

        # Trigger cleanup via a normal rate check (store size 3 > threshold 2)
        assert web._check_rate_limit('api:4.4.4.4', 30) is True

        with web._rate_lock:
            # Stale entries should be cleaned up
            assert 'api:1.1.1.1' not in web._rate_store
            assert 'api:2.2.2.2' not in web._rate_store
            assert 'api:3.3.3.3' not in web._rate_store
            # New entry should exist
            assert 'api:4.4.4.4' in web._rate_store

    def test_no_cleanup_below_threshold(self, monkeypatch):
        """No cleanup triggered when store size is below threshold"""
        import time
        import web

        monkeypatch.setattr('web._RATE_STORE_CLEANUP_THRESHOLD', 100)

        now = time.monotonic()
        old_time = now - web.RATE_LIMIT_WINDOW - 10

        with web._rate_lock:
            web._rate_store.clear()
            web._rate_store['api:old'] = [old_time]

        web._check_rate_limit('api:new', 30)

        with web._rate_lock:
            # Old entry should still be present (below threshold)
            assert 'api:old' in web._rate_store
