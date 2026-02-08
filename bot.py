import asyncio
import logging
import random
import threading
from typing import Any
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

# Constants
SEND_MESSAGE_TIMEOUT = 10
DEFAULT_DELAY_MIN = 3.0
DEFAULT_DELAY_MAX = 10.0
DEFAULT_READ_RECEIPT_DELAY_MIN = 3.0
DEFAULT_READ_RECEIPT_DELAY_MAX = 10.0
HISTORY_FETCH_LIMIT = 50
_AUTH_INPUT_TIMEOUT = 600

# Module-level state (protected by _state_lock)
client = None
_bot_loop = None
_state_lock = threading.Lock()

# Pending response tasks per sender (asyncio-safe, single-threaded access within event loop)
_pending_responses: dict[int, asyncio.Task] = {}

# Private authentication state
_auth_state = {
    'status': 'disconnected',  # disconnected | waiting_code | waiting_password | authorized | error
    'error': None,
}

# Auth input coordination
_auth_inputs = {'code': None, 'password': None}
_code_event = threading.Event()
_password_event = threading.Event()


class AuthTimeoutError(Exception):
    """Raised when auth input is not received within the timeout"""


def get_auth_state() -> dict[str, Any]:
    """Return a copy of auth state (thread-safe)"""
    with _state_lock:
        return dict(_auth_state)


def _set_auth_state(status: str | None = None, error: str | None = None) -> None:
    """Update auth state fields under lock"""
    with _state_lock:
        if status is not None:
            _auth_state['status'] = status
        if error is not None:
            _auth_state['error'] = error


def _set_auth_status_and_clear_error(status: str) -> None:
    """Set auth status and clear error under lock"""
    with _state_lock:
        _auth_state['status'] = status
        _auth_state['error'] = None


def submit_auth_code(code: str) -> None:
    """Submit authentication code from web UI"""
    _auth_inputs['code'] = code
    _set_auth_state(error=None)
    _code_event.set()


def submit_auth_password(password: str) -> None:
    """Submit 2FA password from web UI"""
    _auth_inputs['password'] = password
    _set_auth_state(error=None)
    _password_event.set()


async def _wait_for_input(loop: asyncio.AbstractEventLoop, event: threading.Event, key: str, timeout: int = _AUTH_INPUT_TIMEOUT) -> str:
    """Wait for auth input from web UI (non-blocking in asyncio)

    Args:
        loop: asyncio event loop
        event: threading.Event to wait on
        key: key in _auth_inputs dict ('code' or 'password')
        timeout: max seconds to wait

    Returns:
        The input value

    Raises:
        AuthTimeoutError: if input not received within timeout
    """
    event.clear()
    _auth_inputs[key] = None

    got_input = await loop.run_in_executor(None, event.wait, timeout)
    if not got_input:
        raise AuthTimeoutError(f"Timed out waiting for {key} (>{timeout}s)")

    value = _auth_inputs[key]
    _auth_inputs[key] = None
    return value


def send_message_to_user(user_id: int, text: str) -> Any:
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
    with _state_lock:
        loop = _bot_loop
        cl = client
    if loop is None or cl is None:
        raise RuntimeError("Bot is not running")

    future = asyncio.run_coroutine_threadsafe(
        cl.send_message(user_id, text), loop
    )
    return future.result(timeout=SEND_MESSAGE_TIMEOUT)


def _create_client(cfg: dict[str, Any]) -> TelegramClient:
    """Create and return a TelegramClient from config

    Args:
        cfg: config dict with API_ID, API_HASH

    Returns:
        TelegramClient instance

    Raises:
        ValueError: if API_ID is not a valid integer
    """
    try:
        api_id = int(cfg['API_ID'])
    except (TypeError, ValueError):
        raise ValueError(f"Invalid API_ID: {cfg.get('API_ID')}")
    api_hash = cfg['API_HASH']
    return TelegramClient('data/bot_session', api_id, api_hash)


async def _generate_response(sender_name: str, messages: list[dict[str, Any]],
                             sender_profile: str, system_prompt: str,
                             msg_cfg: dict[str, Any]) -> str:
    """Generate AI response with fallback to static message

    Args:
        sender_name: display name of sender
        messages: pre-loaded conversation messages (including current incoming)
        sender_profile: pre-loaded sender profile markdown
        system_prompt: pre-loaded identity prompt
        msg_cfg: config dict

    Returns:
        Response message string
    """
    openai_key = msg_cfg.get('OPENAI_API_KEY', '')
    openai_model = msg_cfg.get('OPENAI_MODEL', ai.DEFAULT_MODEL)

    if openai_key:
        try:
            chat_messages = ai.build_chat_messages(
                messages, system_prompt, sender_name, sender_profile
            )
            response = await ai.generate_response(
                chat_messages, api_key=openai_key, model=openai_model
            )
            if response:
                return response
        except Exception as e:
            logger.error("AI response generation failed: %s", e)

    return msg_cfg.get(
        'AUTO_RESPONSE_MESSAGE',
        'I will get back to you shortly. Please wait a moment.'
    )


async def _update_sender_profile(sender_id: int, sender_name: str, msg_cfg: dict[str, Any],
                                 use_all_messages: bool = False,
                                 messages: list[dict[str, Any]] | None = None,
                                 sender_profile: str | None = None) -> None:
    """Update sender profile in background using AI

    Args:
        sender_id: Telegram user ID
        sender_name: display name of sender
        msg_cfg: config dict
        use_all_messages: If True, use all stored messages for profile extraction
                          (used for initial profile build from Telegram history)
        messages: pre-loaded messages (falls back to storage read if None)
        sender_profile: pre-loaded profile (falls back to storage read if None)
    """
    openai_key = msg_cfg.get('OPENAI_API_KEY', '')
    openai_model = msg_cfg.get('OPENAI_MODEL', ai.DEFAULT_MODEL)

    if not openai_key:
        return

    try:
        current_profile = sender_profile if sender_profile is not None else await asyncio.to_thread(
            storage.load_sender_profile, sender_id
        )
        recent = messages if messages is not None else await asyncio.to_thread(
            storage.get_messages_by_sender, sender_id
        )
        message_limit = 0 if use_all_messages else ai.PROFILE_RECENT_MESSAGES_LIMIT
        updated_profile = await ai.update_sender_profile(
            current_profile, recent, sender_name,
            api_key=openai_key, model=openai_model,
            message_limit=message_limit
        )
        if updated_profile != current_profile:
            await asyncio.to_thread(
                storage.save_sender_profile, sender_id, updated_profile
            )
            logger.debug("Updated profile for %s", sender_name)
    except Exception as e:
        logger.error("Profile update failed for %s: %s", sender_name, e)


async def _fetch_telegram_history(cl: TelegramClient, sender_id: int, sender_name: str, current_msg_id: int) -> list[dict[str, Any]]:
    """Fetch conversation history from Telegram for a sender.

    Fetches recent messages before the current one and stores them locally.
    Returns the raw imported messages (not subject to 7-day prune) so the
    caller can use them for initial profile building.

    Args:
        cl: TelegramClient instance
        sender_id: Telegram user ID
        sender_name: display name of sender
        current_msg_id: ID of the current incoming message (excluded from fetch)

    Returns:
        List of imported message dicts (empty if nothing fetched)
    """
    try:
        me = await cl.get_me()
        messages = await cl.get_messages(sender_id, limit=HISTORY_FETCH_LIMIT, max_id=current_msg_id)
    except Exception as e:
        logger.warning("Failed to fetch Telegram history for %s: %s", sender_name, e)
        return []

    if not messages:
        return []

    history = []
    for msg in reversed(messages):  # oldest first
        if not msg.text:
            continue
        is_outgoing = msg.sender_id == me.id
        history.append({
            'timestamp': msg.date.isoformat(),
            'direction': 'sent' if is_outgoing else 'received',
            'sender': 'Me' if is_outgoing else sender_name,
            'text': msg.text,
            'summary': None,
            'sender_id': sender_id,
        })

    if history:
        await asyncio.to_thread(storage.import_messages, sender_id, history)
        logger.info("Imported %d messages from Telegram history for %s", len(history), sender_name)

    return history


async def _delayed_read_receipt(cl: TelegramClient, event: Any, msg_cfg: dict[str, Any]) -> None:
    """Send read receipt with random delay (fire & forget).

    Args:
        cl: TelegramClient instance
        event: Telethon NewMessage event
        msg_cfg: config dict with READ_RECEIPT_DELAY_MIN/MAX
    """
    try:
        rr_min = float(msg_cfg.get('READ_RECEIPT_DELAY_MIN', DEFAULT_READ_RECEIPT_DELAY_MIN))
    except (TypeError, ValueError):
        rr_min = DEFAULT_READ_RECEIPT_DELAY_MIN
    try:
        rr_max = float(msg_cfg.get('READ_RECEIPT_DELAY_MAX', DEFAULT_READ_RECEIPT_DELAY_MAX))
    except (TypeError, ValueError):
        rr_max = DEFAULT_READ_RECEIPT_DELAY_MAX
    if rr_min > rr_max:
        rr_min, rr_max = rr_max, rr_min
    read_delay = random.uniform(rr_min, rr_max)
    await asyncio.sleep(read_delay)
    try:
        await cl.send_read_acknowledge(event.chat_id, event.message)
    except Exception as e:
        logger.warning("Failed to send read acknowledge: %s", e)


async def _respond_to_sender(cl: TelegramClient, event: Any, sender_id: int, sender_name: str) -> None:
    """Generate and send AI response to a sender (cancellable).

    This coroutine is run as an asyncio.Task and may be cancelled when a new
    message arrives from the same sender. CancelledError propagates naturally.

    Args:
        cl: TelegramClient instance
        event: Telethon NewMessage event (latest message from sender)
        sender_id: Telegram user ID
        sender_name: display name of sender
    """
    msg_cfg = await asyncio.to_thread(config.load_config)

    # Load fresh data (includes all messages stored so far in Phase A)
    existing_messages = await asyncio.to_thread(
        storage.get_messages_by_sender, sender_id
    )
    sender_profile = await asyncio.to_thread(storage.load_sender_profile, sender_id)
    system_prompt = await asyncio.to_thread(config.load_identity)

    response_message = await _generate_response(
        sender_name, existing_messages, sender_profile, system_prompt, msg_cfg
    )

    try:
        delay_min = float(msg_cfg.get('RESPONSE_DELAY_MIN', DEFAULT_DELAY_MIN))
    except (TypeError, ValueError):
        delay_min = DEFAULT_DELAY_MIN
    try:
        delay_max = float(msg_cfg.get('RESPONSE_DELAY_MAX', DEFAULT_DELAY_MAX))
    except (TypeError, ValueError):
        delay_max = DEFAULT_DELAY_MAX
    if delay_min > delay_max:
        delay_min, delay_max = delay_max, delay_min
    delay = random.uniform(delay_min, delay_max)
    logger.debug("Waiting %.2f seconds before auto-response to %s", delay, sender_name)
    await asyncio.sleep(delay)

    await event.respond(response_message)

    await asyncio.to_thread(
        storage.add_message, 'sent', 'Me', response_message, sender_id=sender_id
    )

    message_text = event.message.message
    if not ai.is_trivial_message(message_text):
        all_messages = existing_messages + [
            {'direction': 'sent', 'text': response_message},
        ]
        await _update_sender_profile(sender_id, sender_name, msg_cfg,
                                     messages=all_messages, sender_profile=sender_profile)

    logger.debug("Received message from %s: %s", sender_name, message_text)
    logger.debug("Auto-response sent to %s: %s", sender_name, response_message)


async def _authenticate(cl: TelegramClient, phone: str, loop: asyncio.AbstractEventLoop) -> None:
    """Run the full authentication flow (code + optional 2FA password)

    Args:
        cl: TelegramClient instance
        phone: phone number string
        loop: asyncio event loop

    Raises:
        AuthTimeoutError: if user does not provide input within timeout
    """
    if await cl.is_user_authorized():
        _set_auth_status_and_clear_error('authorized')
        logger.info("Already authorized")
        return

    try:
        await cl.send_code_request(phone)
    except Exception as e:
        _set_auth_state(status='error', error=str(e))
        logger.error("Failed to send code request: %s", e)
        raise

    _set_auth_state(status='waiting_code')
    logger.info("Waiting for auth code from web UI...")

    while True:
        code = await _wait_for_input(loop, _code_event, 'code')
        try:
            await cl.sign_in(phone, code)
            break
        except PhoneCodeInvalidError:
            _set_auth_state(status='waiting_code',
                            error='Invalid verification code. Please try again.')
            logger.warning("Invalid phone code, retrying...")
        except PhoneCodeExpiredError:
            try:
                await cl.send_code_request(phone)
            except Exception as e:
                _set_auth_state(status='error', error=str(e))
                raise
            _set_auth_state(status='waiting_code',
                            error='Verification code expired. A new code has been sent.')
            logger.warning("Phone code expired, re-sent code")
        except SessionPasswordNeededError:
            _set_auth_status_and_clear_error('waiting_password')
            logger.info("2FA password required, waiting for input from web UI...")

            while True:
                password = await _wait_for_input(loop, _password_event, 'password')
                try:
                    await cl.sign_in(password=password)
                    break
                except PasswordHashInvalidError:
                    _set_auth_state(status='waiting_password',
                                    error='Invalid password. Please try again.')
                    logger.warning("Invalid 2FA password, retrying...")
            break

    _set_auth_status_and_clear_error('authorized')
    logger.info("Authentication successful")


async def start_bot() -> None:
    """Start the Telegram bot"""
    global client, _bot_loop

    cfg = config.load_config()

    if not config.is_configured():
        logger.info("Bot is not configured. Please configure through the web UI.")
        return

    try:
        cl = _create_client(cfg)
    except ValueError as e:
        logger.error("%s", e)
        return

    client = cl
    phone = cfg['PHONE']

    @cl.on(events.NewMessage(incoming=True, from_users=None))
    async def handle_new_message(event):
        """Handle incoming messages with debounce for consecutive messages.

        Phase A (non-cancellable): store message, send read receipt, sync history.
        Phase B (cancellable): cancel any pending response for this sender,
        then create a new response task that sees all accumulated messages.
        """
        if not event.is_private:
            return

        sender = await event.get_sender()

        if isinstance(sender, User):
            sender_name = sender.first_name or ''
            if sender.last_name:
                sender_name += ' ' + sender.last_name
            sender_name = sender_name.strip() or str(sender.id)
        else:
            sender_name = str(sender.id)

        message_text = event.message.message

        if not message_text:
            return

        # --- Phase A: Non-cancellable (always complete) ---

        msg_cfg = await asyncio.to_thread(config.load_config)

        # Store received message immediately
        await asyncio.to_thread(
            storage.add_message, 'received', sender_name, message_text, sender_id=sender.id
        )

        # Read receipt (fire & forget)
        asyncio.create_task(_delayed_read_receipt(cl, event, msg_cfg))

        # Fetch Telegram history if not yet synced for this sender
        history_synced = await asyncio.to_thread(storage.is_history_synced, sender.id)
        if not history_synced:
            imported = await _fetch_telegram_history(cl, sender.id, sender_name, event.message.id)
            await asyncio.to_thread(storage.mark_history_synced, sender.id)
            if imported:
                await _update_sender_profile(sender.id, sender_name, msg_cfg,
                                             use_all_messages=True, messages=imported)

        # --- Phase B: Cancel previous + create new response task ---

        sender_id = sender.id

        existing_task = _pending_responses.get(sender_id)
        if existing_task is not None and not existing_task.done():
            existing_task.cancel()
            logger.debug("Cancelled pending response for %s (new message arrived)", sender_name)

        task = asyncio.create_task(_respond_to_sender(cl, event, sender_id, sender_name))
        _pending_responses[sender_id] = task

        try:
            await task
        except asyncio.CancelledError:
            pass  # Normal: cancelled by a newer message
        finally:
            if _pending_responses.get(sender_id) is task:
                del _pending_responses[sender_id]

    await cl.connect()
    loop = asyncio.get_event_loop()
    with _state_lock:
        _bot_loop = loop

    try:
        await _authenticate(cl, phone, loop)
    except (AuthTimeoutError, Exception) as e:
        if isinstance(e, AuthTimeoutError):
            _set_auth_state(status='error', error=str(e))
            logger.error("Auth timed out: %s", e)
        return

    logger.info("Bot is running...")
    await cl.run_until_disconnected()


def run_bot() -> None:
    """Run the bot in the asyncio event loop"""
    asyncio.run(start_bot())


if __name__ == '__main__':
    run_bot()
