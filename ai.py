import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Singleton client: reuse across calls, recreate only if api_key changes
_client = None
_client_api_key = None


def _get_client(api_key):
    """Get or create AsyncOpenAI client (reuses if api_key unchanged)"""
    global _client, _client_api_key
    if _client is None or _client_api_key != api_key:
        _client = AsyncOpenAI(api_key=api_key)
        _client_api_key = api_key
    return _client


async def summarize_conversation(messages, sender_name, api_key='', model='gpt-4o-mini'):
    """Summarize recent conversation with a sender using OpenAI

    Args:
        messages: List of message dicts with 'direction', 'text', 'sender' keys
        sender_name: Name of the conversation partner
        api_key: OpenAI API key
        model: OpenAI model name

    Returns:
        Summary string, or empty string if no messages or on failure
    """
    if not messages:
        return ''

    if not api_key:
        return ''

    conversation_text = '\n'.join(
        f"{'Me' if msg['direction'] == 'sent' else sender_name}: {msg['text']}"
        for msg in messages
    )

    try:
        client = _get_client(api_key)
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    'role': 'system',
                    'content': (
                        f'Below is a recent conversation between me and {sender_name}. '
                        'Summarize the key topics and context concisely.'
                    )
                },
                {
                    'role': 'user',
                    'content': conversation_text
                }
            ],
            max_tokens=300,
            temperature=0.5,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error('Failed to summarize conversation: %s', e)
        return ''


async def generate_response(system_prompt, conversation_summary, sender_name,
                            incoming_message, sender_profile='',
                            api_key='', model='gpt-4o-mini'):
    """Generate an AI response based on context

    Args:
        system_prompt: User's persona/style prompt
        conversation_summary: Summary of recent conversation with sender
        sender_name: Name of the message sender
        incoming_message: The incoming message to respond to
        sender_profile: Markdown profile of the sender (preferences, key facts)
        api_key: OpenAI API key
        model: OpenAI model name

    Returns:
        Generated response string, or None on failure
    """
    if not api_key:
        return None

    system_parts = []
    if system_prompt:
        system_parts.append(system_prompt)
    if sender_profile:
        system_parts.append(
            f'\n[Profile: {sender_name}]\n{sender_profile}'
        )
    if conversation_summary:
        system_parts.append(
            f'\n[Recent conversation summary with {sender_name}]\n{conversation_summary}'
        )

    system_message = '\n'.join(system_parts) if system_parts else (
        'You are a friendly conversational partner. Respond naturally and concisely.'
    )

    try:
        client = _get_client(api_key)
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': system_message},
                {'role': 'user', 'content': incoming_message}
            ],
            max_tokens=500,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error('Failed to generate AI response: %s', e)
        return None


async def update_sender_profile(current_profile, recent_messages, sender_name,
                                api_key='', model='gpt-4o-mini'):
    """Update sender profile by extracting key info from recent conversation.

    Args:
        current_profile: Existing profile markdown (may be empty)
        recent_messages: Recent message dicts
        sender_name: Name of the sender
        api_key: OpenAI API key
        model: OpenAI model name

    Returns:
        Updated profile markdown string, or current_profile on failure
    """
    if not recent_messages:
        return current_profile

    if not api_key:
        return current_profile

    conversation_text = '\n'.join(
        f"{'Me' if msg['direction'] == 'sent' else sender_name}: {msg['text']}"
        for msg in recent_messages[-10:]
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
            max_tokens=500,
            temperature=0.3,
        )
        updated = response.choices[0].message.content.strip()
        return updated if updated else current_profile
    except Exception as e:
        logger.error('Failed to update sender profile: %s', e)
        return current_profile
