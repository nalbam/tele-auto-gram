import logging
from openai import OpenAI
import config

logger = logging.getLogger(__name__)


def summarize_conversation(messages, sender_name):
    """Summarize recent conversation with a sender using OpenAI

    Args:
        messages: List of message dicts with 'direction', 'text', 'sender' keys
        sender_name: Name of the conversation partner

    Returns:
        Summary string, or empty string if no messages or on failure
    """
    if not messages:
        return ''

    cfg = config.load_config()
    api_key = cfg.get('OPENAI_API_KEY', '')
    if not api_key:
        return ''

    model = cfg.get('OPENAI_MODEL', 'gpt-4o-mini')

    conversation_text = '\n'.join(
        f"{'Me' if msg['direction'] == 'sent' else sender_name}: {msg['text']}"
        for msg in messages
    )

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
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


def generate_response(system_prompt, conversation_summary, sender_name,
                      incoming_message, sender_profile=''):
    """Generate an AI response based on context

    Args:
        system_prompt: User's persona/style prompt
        conversation_summary: Summary of recent conversation with sender
        sender_name: Name of the message sender
        incoming_message: The incoming message to respond to
        sender_profile: Markdown profile of the sender (preferences, key facts)

    Returns:
        Generated response string, or None on failure
    """
    cfg = config.load_config()
    api_key = cfg.get('OPENAI_API_KEY', '')
    if not api_key:
        return None

    model = cfg.get('OPENAI_MODEL', 'gpt-4o-mini')

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
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
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


def update_sender_profile(current_profile, recent_messages, sender_name):
    """Update sender profile by extracting key info from recent conversation.

    Args:
        current_profile: Existing profile markdown (may be empty)
        recent_messages: Recent message dicts
        sender_name: Name of the sender

    Returns:
        Updated profile markdown string, or current_profile on failure
    """
    if not recent_messages:
        return current_profile

    cfg = config.load_config()
    api_key = cfg.get('OPENAI_API_KEY', '')
    if not api_key:
        return current_profile

    model = cfg.get('OPENAI_MODEL', 'gpt-4o-mini')

    conversation_text = '\n'.join(
        f"{'Me' if msg['direction'] == 'sent' else sender_name}: {msg['text']}"
        for msg in recent_messages[-10:]
    )

    prompt_parts = [
        f'Below is a recent conversation with {sender_name} and their current profile.',
        '',
        '[Current Profile]',
        current_profile if current_profile else '(empty — first conversation)',
        '',
        '[Recent Conversation]',
        conversation_text,
        '',
        'Update the profile ONLY if the conversation contains genuinely important new facts.',
        'Rules:',
        '- If no new important info was revealed, return the current profile UNCHANGED',
        '- ONLY store lasting personal facts worth remembering long-term:',
        '  * Preferred name or nickname ("call me ...")',
        '  * Preferred language or tone',
        '  * Job, role, or profession',
        '  * Location or timezone',
        '  * Explicit requests ("remember that ...", "I prefer ...")',
        '- Do NOT store:',
        '  * Casual conversation topics or small talk',
        '  * Temporary states (mood, what they ate, weather)',
        '  * Anything that could be inferred from a single greeting',
        '- Keep existing info unless clearly contradicted',
        '- Use concise bullet points, no headings needed for short profiles',
        '- Output ONLY the profile in Markdown, nothing else',
    ]

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
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
