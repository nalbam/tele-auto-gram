from flask import Flask, render_template, request, jsonify
import config
import storage

app = Flask(__name__)

MASKED_FIELDS = ('API_HASH', 'OPENAI_API_KEY')


def mask_value(value):
    """Mask a sensitive value, showing first 4 and last 4 characters"""
    if not value or len(value) <= 8:
        return '*' * len(value) if value else ''
    return value[:4] + '****' + value[-4:]


def is_masked(value):
    """Check if a value contains masking asterisks"""
    return bool(value) and '****' in value


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

def run_web_ui(host='127.0.0.1', port=5000):
    """Run the web UI server"""
    print(f"\n🌐 Web UI is running at http://{host}:{port}")
    print("Open this URL in your browser to configure and monitor the bot\n")
    app.run(host=host, port=port, debug=False)

if __name__ == '__main__':
    run_web_ui()
