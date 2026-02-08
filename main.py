#!/usr/bin/env python3
"""
TeleAutoGram Main Entry Point

This application runs both the Telegram bot and the web UI.
"""

import logging
import os
import signal
import threading
import sys
import time
from types import FrameType
from web import run_web_ui
from bot import run_bot
import bot
import config

WEB_STARTUP_DELAY = 2

log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

def _shutdown(signum: int, frame: FrameType | None) -> None:
    """Graceful shutdown handler"""
    import asyncio
    print("\n\nShutting down...")
    with bot._state_lock:
        cl = bot.client
        loop = bot._bot_loop
    if cl and loop and loop.is_running():
        try:
            result = cl.disconnect()
            if asyncio.iscoroutine(result):
                future = asyncio.run_coroutine_threadsafe(result, loop)
                future.result(timeout=5)
        except Exception:
            pass
    sys.exit(0)


def main() -> None:
    """Main entry point"""
    print("=" * 60)
    print("TeleAutoGram")
    print("=" * 60)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # Start web UI in a separate thread
    web_thread = threading.Thread(target=run_web_ui, daemon=True)
    web_thread.start()

    # Give web server time to start
    time.sleep(WEB_STARTUP_DELAY)

    # Check if configured
    if config.is_configured():
        print("\nBot is configured. Starting Telegram bot...")
        print("Tip: You can configure the bot at http://127.0.0.1:5000")

        # Start bot in a separate thread
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
    else:
        print("\nBot is not configured yet.")
        print("Please visit http://127.0.0.1:5000 to configure the bot")
        print("   You'll need:")
        print("   - API_ID and API_HASH from https://my.telegram.org")
        print("   - Your phone number with country code (e.g., +821012345678)")

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _shutdown(signal.SIGINT, None)

if __name__ == '__main__':
    main()
