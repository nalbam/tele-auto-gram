from flask import Flask, render_template, request, jsonify
import config
import storage
import bot

app = Flask(__name__)

MASKED_FIELDS = ('API_HASH', 'OPENAI_API_KEY')


def mask_value(value):
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


def is_masked(value):
    """Check if a value is a masked placeholder"""
    if not value:
        return False
    stripped = value.replace('*', '')
    return len(stripped) <= 8 and '**' in value


@app.route('/')
def index():
    """Serve the main UI page"""
    return render_template('index.html')

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

        # Preserve existing values when masked value is submitted unchanged
        existing = config.load_config()
        for field in MASKED_FIELDS:
            if is_masked(data.get(field, '')):
                data[field] = existing.get(field, '')

        config.save_config(data)
        return jsonify({'status': 'success'})
    except Exception as e:
        # Log the error server-side but return generic message to client
        print(f"Error saving configuration: {e}")
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
    user_id = data.get('user_id')
    text = (data.get('text') or '').strip()

    if not user_id or not text:
        return jsonify({'status': 'error', 'message': 'user_id and text are required'}), 400

    if bot.auth_state.get('status') != 'authorized':
        return jsonify({'status': 'error', 'message': 'Bot is not authorized'}), 400

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'message': 'Invalid user_id'}), 400

    try:
        bot.send_message_to_user(user_id, text)
    except RuntimeError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 503
    except Exception as e:
        print(f"Error sending message: {e}")
        return jsonify({'status': 'error', 'message': 'Failed to send message'}), 500

    storage.add_message('sent', 'Me', text, sender_id=user_id)
    return jsonify({'status': 'success'})


@app.route('/api/auth/status', methods=['GET'])
def get_auth_status():
    """Get current authentication status"""
    return jsonify(bot.auth_state)


@app.route('/api/auth/code', methods=['POST'])
def submit_auth_code():
    """Submit authentication code"""
    data = request.get_json()
    code = data.get('code', '').strip()
    if not code:
        return jsonify({'status': 'error', 'message': 'Code is required'}), 400
    bot.submit_auth_code(code)
    return jsonify({'status': 'success'})


@app.route('/api/auth/password', methods=['POST'])
def submit_auth_password():
    """Submit 2FA password"""
    data = request.get_json()
    password = data.get('password', '')
    if not password:
        return jsonify({'status': 'error', 'message': 'Password is required'}), 400
    bot.submit_auth_password(password)
    return jsonify({'status': 'success'})

def run_web_ui(host='127.0.0.1', port=5000):
    """Run the web UI server"""
    print(f"\n🌐 Web UI is running at http://{host}:{port}")
    print("Open this URL in your browser to configure and monitor the bot\n")
    app.run(host=host, port=port, debug=False)

if __name__ == '__main__':
    run_web_ui()
