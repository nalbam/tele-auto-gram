import logging
import os
import secrets
from typing import Any

from flask import Flask, render_template, request, jsonify
import config
import storage
import bot

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', secrets.token_hex(32))
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # 1 MB

MASKED_FIELDS = ('API_HASH', 'OPENAI_API_KEY')
WEB_TOKEN = os.getenv('WEB_TOKEN', '')
if not WEB_TOKEN:
    logger.warning("WEB_TOKEN is not set — API endpoints are unprotected")


@app.before_request
def check_content_type():
    """Reject POST requests to /api/* without application/json Content-Type"""
    if request.method == 'POST' and request.path.startswith('/api/'):
        content_type = request.content_type or ''
        if 'application/json' not in content_type:
            return jsonify({'status': 'error', 'message': 'Content-Type must be application/json'}), 415


@app.before_request
def check_auth_token():
    """Require token authentication for API endpoints when WEB_TOKEN is set"""
    if not WEB_TOKEN:
        return
    if not request.path.startswith('/api/'):
        return
    auth_header = request.headers.get('Authorization', '')
    token = auth_header[7:].strip() if auth_header.startswith('Bearer ') else ''
    if not secrets.compare_digest(token, WEB_TOKEN):
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401


def mask_value(value: str | None) -> str:
    """Mask a sensitive value with proportional visible characters.

    Visible chars per side = length // 8, capped at 4.
      1-7  chars: all masked
      8-15 chars: 1 char each side
      16-23 chars: 2 chars each side
      24-31 chars: 3 chars each side
      32+  chars: 4 chars each side + 32 asterisks
    """
    if not value:
        return ''
    length = len(value)
    visible = min(length // 8, 4)
    if visible == 0:
        return '*' * length
    mask_count = min(length - visible * 2, 32)
    return value[:visible] + '*' * mask_count + value[-visible:]


def is_masked(value: str | None) -> bool:
    """Check if a value is a masked placeholder"""
    if not value:
        return False
    stripped = value.replace('*', '')
    return len(stripped) <= 8 and '**' in value


@app.route('/')
def index():
    """Serve the main UI page"""
    return render_template('index.html', web_token=WEB_TOKEN)

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    cfg = config.load_config()
    cfg['is_configured'] = config.is_configured()

    for field in MASKED_FIELDS:
        if cfg.get(field):
            cfg[field] = mask_value(cfg[field])

    return jsonify(cfg)

@app.route('/api/config', methods=['POST'])
def save_config():
    """Save configuration"""
    try:
        data = request.get_json()
        if not isinstance(data, dict):
            return jsonify({'status': 'error', 'message': 'Invalid JSON payload'}), 400

        # Validate API_ID is numeric if provided
        api_id = data.get('API_ID', '')
        if api_id and str(api_id).strip():
            try:
                int(str(api_id).strip())
            except (TypeError, ValueError):
                return jsonify({'status': 'error', 'message': 'API_ID must be a number'}), 400

        # Preserve existing values when masked value is submitted unchanged
        existing = config.load_config()
        for field in MASKED_FIELDS:
            if is_masked(data.get(field, '')):
                data[field] = existing.get(field, '')

        config.save_config(data)
        return jsonify({'status': 'success'})
    except Exception as e:
        # Log the error server-side but return generic message to client
        logger.error("Error saving configuration: %s", e)
        return jsonify({'status': 'error', 'message': 'Failed to save configuration'}), 500

@app.route('/api/messages', methods=['GET'])
def get_messages():
    """Get message history"""
    messages = storage.load_messages()
    return jsonify(messages)


@app.route('/api/messages/send', methods=['POST'])
def send_message():
    """Send a message to a Telegram user"""
    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify({'status': 'error', 'message': 'Invalid JSON payload'}), 400
    user_id = data.get('user_id')
    text = (data.get('text') or '').strip()

    if not user_id or not text:
        return jsonify({'status': 'error', 'message': 'user_id and text are required'}), 400

    if len(text) > 4096:
        return jsonify({'status': 'error', 'message': 'Message too long (max 4096 characters)'}), 400

    if bot.get_auth_state().get('status') != 'authorized':
        return jsonify({'status': 'error', 'message': 'Bot is not authorized'}), 400

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'message': 'Invalid user_id'}), 400

    try:
        bot.send_message_to_user(user_id, text)
    except RuntimeError:
        return jsonify({'status': 'error', 'message': 'Bot is not available'}), 503
    except Exception as e:
        logger.error("Error sending message: %s", e)
        return jsonify({'status': 'error', 'message': 'Failed to send message'}), 500

    storage.add_message('sent', 'Me', text, sender_id=user_id)
    return jsonify({'status': 'success'})


@app.route('/api/identity', methods=['GET'])
def get_identity():
    """Get identity prompt content"""
    content = config.load_identity()
    return jsonify({'content': content})


@app.route('/api/identity', methods=['POST'])
def save_identity():
    """Save identity prompt content"""
    try:
        data = request.get_json()
        content = data.get('content', '')
        if len(content) > 50000:
            return jsonify({'status': 'error', 'message': 'Content too long (max 50000 characters)'}), 400
        config.save_identity(content)
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error("Error saving identity: %s", e)
        return jsonify({'status': 'error', 'message': 'Failed to save identity'}), 500


@app.route('/api/auth/status', methods=['GET'])
def get_auth_status():
    """Get current authentication status"""
    return jsonify(bot.get_auth_state())


@app.route('/api/auth/code', methods=['POST'])
def submit_auth_code():
    """Submit authentication code"""
    data = request.get_json() or {}
    code = data.get('code', '').strip()
    if not code:
        return jsonify({'status': 'error', 'message': 'Code is required'}), 400
    bot.submit_auth_code(code)
    return jsonify({'status': 'success'})


@app.route('/api/auth/password', methods=['POST'])
def submit_auth_password():
    """Submit 2FA password"""
    data = request.get_json() or {}
    password = data.get('password', '')
    if not password:
        return jsonify({'status': 'error', 'message': 'Password is required'}), 400
    bot.submit_auth_password(password)
    return jsonify({'status': 'success'})

def run_web_ui(host: str | None = None, port: int | None = None) -> None:
    """Run the web UI server"""
    host = host or os.getenv('HOST', '0.0.0.0')
    try:
        port = port or int(os.getenv('PORT', '5000'))
    except (TypeError, ValueError):
        port = 5000
    logger.info("Web UI is running at http://%s:%s", host, port)
    logger.info("Open this URL in your browser to configure and monitor the bot")
    app.run(host=host, port=port, debug=False)

if __name__ == '__main__':
    run_web_ui()
