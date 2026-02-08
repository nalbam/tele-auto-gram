from flask import Flask, render_template, request, jsonify
import config
import storage
import bot

app = Flask(__name__)

MASKED_FIELDS = ('API_HASH', 'OPENAI_API_KEY')


def mask_value(value):
    """Mask a sensitive value with 16 asterisks"""
    if not value:
        return ''
    return '*' * 16


def is_masked(value):
    """Check if a value is a masked placeholder"""
    return value == '*' * 16


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
