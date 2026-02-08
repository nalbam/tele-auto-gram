import asyncio
import logging
import random
import threading
from telethon import TelegramClient, events
from telethon.tl.types import User
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PasswordHashInvalidError,
)
import config
import storage
import ai

logger = logging.getLogger(__name__)

client = None
_bot_loop = None

# Shared authentication state
auth_state = {
    'status': 'disconnected',  # disconnected | waiting_code | waiting_password | authorized | error
    'error': None,
}

_auth_code = None
_auth_password = None
_code_event = threading.Event()
_password_event = threading.Event()


def submit_auth_code(code):
    """Submit authentication code from web UI"""
    global _auth_code
    _auth_code = code
    auth_state['error'] = None
    _code_event.set()


def submit_auth_password(password):
    """Submit 2FA password from web UI"""
    global _auth_password
    _auth_password = password
    auth_state['error'] = None
    _password_event.set()


async def _wait_for_code(loop):
    """Wait for auth code from web UI (non-blocking in asyncio)"""
    global _auth_code
    _code_event.clear()
    _auth_code = None
    await loop.run_in_executor(None, _code_event.wait)
    code = _auth_code
    _auth_code = None
    return code


async def _wait_for_password(loop):
    """Wait for 2FA password from web UI (non-blocking in asyncio)"""
    global _auth_password
    _password_event.clear()
    _auth_password = None
    await loop.run_in_executor(None, _password_event.wait)
    password = _auth_password
    _auth_password = None
    return password


def send_message_to_user(user_id, text):
    """Send a message to a Telegram user from the Flask thread.

    Uses asyncio.run_coroutine_threadsafe to bridge Flask's sync context
    to the bot's asyncio event loop running in a daemon thread.

    Args:
        user_id: Telegram user ID (int)
        text: message text to send

    Raises:
        RuntimeError: if bot loop or client is not available
        Exception: propagated from Telethon send_message
    """
    if _bot_loop is None or client is None:
        raise RuntimeError("Bot is not running")

    future = asyncio.run_coroutine_threadsafe(
        client.send_message(user_id, text), _bot_loop
    )
    return future.result(timeout=10)


async def start_bot():
    """Start the Telegram bot"""
    global client, _bot_loop

    cfg = config.load_config()

    if not config.is_configured():
        logger.info("Bot is not configured. Please configure through the web UI.")
        return

    try:
        api_id = int(cfg['API_ID'])
    except (TypeError, ValueError):
        logger.error("Invalid API_ID: %s", cfg.get('API_ID'))
        return
    api_hash = cfg['API_HASH']
    phone = cfg['PHONE']

    client = TelegramClient('data/bot_session', api_id, api_hash)

    @client.on(events.NewMessage(incoming=True, from_users=None))
    async def handle_new_message(event):
        """Handle incoming messages"""
        # Only process private messages, ignore groups/channels
        if not event.is_private:
            return

        sender = await event.get_sender()

        # Get sender name
        if isinstance(sender, User):
            sender_name = sender.first_name or ''
            if sender.last_name:
                sender_name += ' ' + sender.last_name
            sender_name = sender_name.strip() or str(sender.id)
        else:
            sender_name = str(sender.id)

        message_text = event.message.message

        # Reload config for each message to pick up changes
        msg_cfg = await asyncio.to_thread(config.load_config)

        # Store received message
        await asyncio.to_thread(
            storage.add_message, 'received', sender_name, message_text, sender_id=sender.id
        )

        # Generate response
        response_message = None
        summary = None
        openai_key = msg_cfg.get('OPENAI_API_KEY', '')
        openai_model = msg_cfg.get('OPENAI_MODEL', 'gpt-4o-mini')

        if openai_key:
            try:
                # Get recent conversation and sender profile
                recent_messages = await asyncio.to_thread(
                    storage.get_messages_by_sender, sender.id
                )
                sender_profile = await asyncio.to_thread(
                    storage.load_sender_profile, sender.id
                )

                # Summarize conversation context
                conversation_summary = await ai.summarize_conversation(
                    recent_messages, sender_name,
                    api_key=openai_key, model=openai_model
                )
                summary = conversation_summary

                # Generate AI response with profile context
                system_prompt = await asyncio.to_thread(config.load_identity)
                response_message = await ai.generate_response(
                    system_prompt, conversation_summary,
                    sender_name, message_text,
                    sender_profile=sender_profile,
                    api_key=openai_key, model=openai_model
                )
            except Exception as e:
                logger.error("AI response generation failed: %s", e)

        # Fallback to static message
        if not response_message:
            response_message = msg_cfg.get(
                'AUTO_RESPONSE_MESSAGE',
                'I will get back to you shortly. Please wait a moment.'
            )

        delay_min = float(msg_cfg.get('RESPONSE_DELAY_MIN', 3))
        delay_max = float(msg_cfg.get('RESPONSE_DELAY_MAX', 10))
        if delay_min > delay_max:
            delay_min, delay_max = delay_max, delay_min
        delay = random.uniform(delay_min, delay_max)
        logger.debug("Waiting %.2f seconds before auto-response to %s", delay, sender_name)
        await asyncio.sleep(delay)
        await event.respond(response_message)

        # Store sent response
        await asyncio.to_thread(
            storage.add_message, 'sent', 'Me', response_message, sender_id=sender.id
        )

        # Update sender profile in background (non-blocking)
        if openai_key:
            try:
                current_profile = await asyncio.to_thread(
                    storage.load_sender_profile, sender.id
                )
                recent = await asyncio.to_thread(
                    storage.get_messages_by_sender, sender.id
                )
                updated_profile = await ai.update_sender_profile(
                    current_profile, recent, sender_name,
                    api_key=openai_key, model=openai_model
                )
                if updated_profile != current_profile:
                    await asyncio.to_thread(
                        storage.save_sender_profile, sender.id, updated_profile
                    )
                    logger.debug("Updated profile for %s", sender_name)
            except Exception as e:
                logger.error("Profile update failed for %s: %s", sender_name, e)

        logger.debug("Received message from %s: %s", sender_name, message_text)
        logger.debug("Auto-response sent to %s: %s", sender_name, response_message)

    # Manual authentication flow
    await client.connect()
    loop = asyncio.get_event_loop()
    _bot_loop = loop

    if await client.is_user_authorized():
        auth_state['status'] = 'authorized'
        auth_state['error'] = None
        logger.info("Already authorized")
    else:
        # Send code request
        try:
            await client.send_code_request(phone)
        except Exception as e:
            auth_state['status'] = 'error'
            auth_state['error'] = str(e)
            logger.error("Failed to send code request: %s", e)
            return

        auth_state['status'] = 'waiting_code'
        logger.info("Waiting for auth code from web UI...")

        # Code input loop
        while True:
            code = await _wait_for_code(loop)
            try:
                await client.sign_in(phone, code)
                break
            except PhoneCodeInvalidError:
                auth_state['status'] = 'waiting_code'
                auth_state['error'] = 'Invalid verification code. Please try again.'
                logger.warning("Invalid phone code, retrying...")
            except PhoneCodeExpiredError:
                # Re-send code
                try:
                    await client.send_code_request(phone)
                except Exception as e:
                    auth_state['status'] = 'error'
                    auth_state['error'] = str(e)
                    return
                auth_state['status'] = 'waiting_code'
                auth_state['error'] = 'Verification code expired. A new code has been sent.'
                logger.warning("Phone code expired, re-sent code")
            except SessionPasswordNeededError:
                # 2FA required
                auth_state['status'] = 'waiting_password'
                auth_state['error'] = None
                logger.info("2FA password required, waiting for input from web UI...")

                # Password input loop
                while True:
                    password = await _wait_for_password(loop)
                    try:
                        await client.sign_in(password=password)
                        break
                    except PasswordHashInvalidError:
                        auth_state['status'] = 'waiting_password'
                        auth_state['error'] = 'Invalid password. Please try again.'
                        logger.warning("Invalid 2FA password, retrying...")
                break

        auth_state['status'] = 'authorized'
        auth_state['error'] = None
        logger.info("Authentication successful")

    print("Bot is running...")
    await client.run_until_disconnected()


def run_bot():
    """Run the bot in the asyncio event loop"""
    asyncio.run(start_bot())


if __name__ == '__main__':
    run_bot()
