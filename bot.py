import asyncio
import logging
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


async def start_bot():
    """Start the Telegram bot"""
    global client

    cfg = config.load_config()

    if not config.is_configured():
        logger.info("Bot is not configured. Please configure through the web UI.")
        return

    api_id = int(cfg['API_ID'])
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

        # Store received message
        storage.add_message('received', sender_name, message_text)

        # Generate response
        response_message = None
        summary = None
        openai_key = cfg.get('OPENAI_API_KEY', '')

        if openai_key:
            try:
                # Get recent conversation with this sender
                recent_messages = storage.get_messages_by_sender(sender_name)

                # Summarize conversation context
                conversation_summary = ai.summarize_conversation(
                    recent_messages, sender_name
                )
                summary = conversation_summary

                # Generate AI response
                system_prompt = cfg.get('SYSTEM_PROMPT', '')
                response_message = ai.generate_response(
                    system_prompt, conversation_summary,
                    sender_name, message_text
                )
            except Exception as e:
                logger.error("AI response generation failed: %s", e)

        # Fallback to static message
        if not response_message:
            response_message = cfg.get(
                'AUTO_RESPONSE_MESSAGE',
                '잠시 후 응답드리겠습니다. 조금만 기다려주세요.'
            )
        await event.respond(response_message)

        # Store sent response
        storage.add_message('sent', 'Me', response_message)

        logger.debug("Received message from %s: %s", sender_name, message_text)
        logger.debug("Auto-response sent to %s: %s", sender_name, response_message)

    # Manual authentication flow
    await client.connect()
    loop = asyncio.get_event_loop()

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
                auth_state['error'] = '인증 코드가 올바르지 않습니다. 다시 입력해주세요.'
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
                auth_state['error'] = '인증 코드가 만료되었습니다. 새 코드가 발송되었습니다.'
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
                        auth_state['error'] = '비밀번호가 올바르지 않습니다. 다시 입력해주세요.'
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
