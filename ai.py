import logging
import re
import threading
from typing import Any

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Constants
DEFAULT_MODEL = 'gpt-4o-mini'
DEFAULT_SYSTEM_PROMPT = 'You are a friendly conversational partner. Respond naturally and concisely.'

MULTI_TURN_LIMIT = 20

RESPONSE_MAX_TOKENS = 500
RESPONSE_TEMPERATURE = 0.7

PROFILE_MAX_TOKENS = 500
PROFILE_TEMPERATURE = 0.3
PROFILE_RECENT_MESSAGES_LIMIT = 10

# Singleton client: reuse across calls, recreate only if api_key changes
_client = None
_client_api_key = None
_client_lock = threading.Lock()


def _get_client(api_key: str) -> AsyncOpenAI:
    """Get or create AsyncOpenAI client (reuses if api_key unchanged)"""
    global _client, _client_api_key
    with _client_lock:
        if _client is None or _client_api_key != api_key:
            _client = AsyncOpenAI(api_key=api_key)
            _client_api_key = api_key
        return _client


# Regex: matches strings that are ONLY emoji (+ variation selectors, ZWJ, whitespace)
_EMOJI_ONLY_RE = re.compile(
    r'^[\U0001F600-\U0001F64F'
    r'\U0001F300-\U0001F5FF'
    r'\U0001F680-\U0001F6FF'
    r'\U0001F1E0-\U0001F1FF'
    r'\U00002702-\U000027B0'
    r'\U0000FE00-\U0000FE0F'
    r'\U0000200D'
    r'\U00002600-\U000026FF'
    r'\U0001F900-\U0001F9FF'
    r'\U0001FA00-\U0001FA6F'
    r'\U0001FA70-\U0001FAFF'
    r'\s]+$'
)

_TRIVIAL_WORDS = frozenset({
    'ok', 'okay', 'ㅋ', 'ㅋㅋ', 'ㅋㅋㅋ', 'ㅎ', 'ㅎㅎ', 'ㅎㅎㅎ',
    'ㅇㅇ', 'ㅇㅋ', 'ㄴㄴ', 'ㄱㄱ', 'ㅇ', 'ㅜ', 'ㅠ', 'ㅜㅜ', 'ㅠㅠ',
    'lol', 'haha', 'hehe', 'hmm', 'ah', 'oh', 'yes', 'no', 'yep', 'nope',
    'k', 'kk', 'thx', 'ty', 'np',
    'ㄳ', '넵', '네', '응', '앙', '웅', '굿', '감사',
})


def is_trivial_message(text: str | None) -> bool:
    """Check if a message is trivial (not worth updating profile for)

    Args:
        text: message text

    Returns:
        True if the message is trivial
    """
    if not text:
        return True
    stripped = text.strip()
    if len(stripped) < 3:
        return True
    if stripped.lower() in _TRIVIAL_WORDS:
        return True
    if _EMOJI_ONLY_RE.match(stripped):
        return True
    return False


def build_chat_messages(messages: list[dict[str, Any]], system_prompt: str,
                        sender_name: str, sender_profile: str = '',
                        limit: int = MULTI_TURN_LIMIT) -> list[dict[str, str]]:
    """Build OpenAI multi-turn chat messages from stored conversation history.

    Converts storage messages into OpenAI-compatible message array with
    system prompt, sender profile, and multi-turn user/assistant messages.
    Consecutive same-role messages are merged (handles Telegram bursts).

    Args:
        messages: List of message dicts with 'direction' and 'text' keys
        system_prompt: Identity/persona prompt
        sender_name: Name of the conversation partner
        sender_profile: Markdown profile of the sender
        limit: Max number of recent messages to include

    Returns:
        List of OpenAI message dicts with 'role' and 'content'
    """
    # Build system message
    system_parts = [system_prompt if system_prompt else DEFAULT_SYSTEM_PROMPT]
    if sender_profile:
        system_parts.append(f'\n[Profile: {sender_name}]\n{sender_profile}')
    else:
        system_parts.append(f'\n[Profile: {sender_name}]\n(No prior information — first contact)')
    system_content = '\n'.join(system_parts)

    chat: list[dict[str, str]] = [{'role': 'system', 'content': system_content}]

    # Take last `limit` messages
    recent = messages[-limit:] if limit and len(messages) > limit else messages

    for msg in recent:
        text = msg.get('text')
        if not text:
            continue
        role = 'assistant' if msg.get('direction') == 'sent' else 'user'
        # Merge consecutive same-role messages
        if len(chat) > 1 and chat[-1]['role'] == role:
            chat[-1]['content'] += '\n' + text
        else:
            chat.append({'role': role, 'content': text})

    return chat


async def generate_response(chat_messages: list[dict[str, str]],
                            api_key: str = '', model: str = DEFAULT_MODEL) -> str | None:
    """Generate an AI response from pre-built chat messages.

    Args:
        chat_messages: List of OpenAI message dicts (from build_chat_messages)
        api_key: OpenAI API key
        model: OpenAI model name

    Returns:
        Generated response string, or None on failure
    """
    if not api_key:
        return None

    try:
        client = _get_client(api_key)
        response = await client.chat.completions.create(
            model=model,
            messages=chat_messages,
            max_tokens=RESPONSE_MAX_TOKENS,
            temperature=RESPONSE_TEMPERATURE,
        )
        content = response.choices[0].message.content
        return content.strip() if content else None
    except Exception as e:
        logger.error('Failed to generate AI response: %s', e)
        return None


async def update_sender_profile(current_profile: str, recent_messages: list[dict[str, Any]], sender_name: str,
                                api_key: str = '', model: str = DEFAULT_MODEL,
                                message_limit: int = PROFILE_RECENT_MESSAGES_LIMIT) -> str:
    """Update sender profile by extracting key info from recent conversation.

    Args:
        current_profile: Existing profile markdown (may be empty)
        recent_messages: Recent message dicts
        sender_name: Name of the sender
        api_key: OpenAI API key
        model: OpenAI model name
        message_limit: Max messages to use (0 = all messages, default 10 for incremental updates)

    Returns:
        Updated profile markdown string, or current_profile on failure
    """
    if not recent_messages:
        return current_profile

    if not api_key:
        return current_profile

    msgs = recent_messages if message_limit == 0 else recent_messages[-message_limit:]
    conversation_text = '\n'.join(
        f"{'Me' if msg['direction'] == 'sent' else sender_name}: {msg['text']}"
        for msg in msgs
    )

    prompt_parts = [
        f'You are updating a profile about "{sender_name}" — the OTHER person in this conversation.',
        '"Me" is YOU (the bot operator). Do NOT extract or store anything "Me" said about myself.',
        f'ONLY extract facts that "{sender_name}" revealed about THEMSELVES.',
        '',
        f'[Current Profile of {sender_name}]',
        current_profile if current_profile else '(empty — first conversation)',
        '',
        '[Recent Conversation]',
        conversation_text,
        '',
        f'Update the profile of {sender_name} ONLY if they revealed genuinely important new facts about themselves.',
        'Rules:',
        '- If no new important info was revealed, return the current profile UNCHANGED',
        f'- ONLY extract info from what {sender_name} said, NEVER from what "Me" said',
        '- ONLY store lasting personal facts worth remembering long-term:',
        '  * Preferred name or nickname ("call me ...")',
        '  * Preferred language or tone',
        '  * Job, role, or profession',
        '  * Location or timezone',
        '  * Explicit requests ("remember that ...", "I prefer ...")',
        '- Do NOT store:',
        '  * Anything "Me" said about myself — that is NOT the sender\'s info',
        '  * Casual conversation topics or small talk',
        '  * Temporary states (mood, what they ate, weather)',
        '  * Anything that could be inferred from a single greeting',
        '- Keep existing info unless clearly contradicted',
        '- Use concise bullet points, no headings needed for short profiles',
        '- Output ONLY the profile in Markdown, nothing else',
    ]

    try:
        client = _get_client(api_key)
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': '\n'.join(prompt_parts)},
                {'role': 'user', 'content': 'Update the profile now.'}
            ],
            max_tokens=PROFILE_MAX_TOKENS,
            temperature=PROFILE_TEMPERATURE,
        )
        updated = response.choices[0].message.content.strip()
        return updated if updated else current_profile
    except Exception as e:
        logger.error('Failed to update sender profile: %s', e)
        return current_profile
