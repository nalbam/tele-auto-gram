from flask import Flask, render_template, request, jsonify
import config
import storage
import threading
import sys

app = Flask(__name__)

# Bot thread reference
bot_thread = None

@app.route('/')
def index():
    """Serve the main UI page"""
    return render_template('index.html')

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    cfg = config.load_config()
    cfg['is_configured'] = config.is_configured()
    return jsonify(cfg)

@app.route('/api/config', methods=['POST'])
def save_config():
    """Save configuration"""
    try:
        data = request.get_json()
        config.save_config(data)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

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
