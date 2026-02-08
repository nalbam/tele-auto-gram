#!/usr/bin/env python3
"""
Telegram Auto-Response Bot Main Entry Point

This application runs both the Telegram bot and the web UI.
"""

import logging
import os
import threading
import sys
import time
from web import run_web_ui
from bot import run_bot
import config

log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

def main():
    """Main entry point"""
    print("=" * 60)
    print("📱 Telegram Auto-Response Bot")
    print("=" * 60)
    
    # Start web UI in a separate thread
    web_thread = threading.Thread(target=run_web_ui, daemon=True)
    web_thread.start()
    
    # Give web server time to start
    time.sleep(2)
    
    # Check if configured
    if config.is_configured():
        print("\n✅ Bot is configured. Starting Telegram bot...")
        print("💡 Tip: You can configure the bot at http://127.0.0.1:5000")
        
        # Start bot in a separate thread
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
    else:
        print("\n⚠️  Bot is not configured yet.")
        print("📝 Please visit http://127.0.0.1:5000 to configure the bot")
        print("   You'll need:")
        print("   - API_ID and API_HASH from https://my.telegram.org")
        print("   - Your phone number with country code (e.g., +821012345678)")
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down...")
        sys.exit(0)

if __name__ == '__main__':
    main()
