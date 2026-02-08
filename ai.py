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
        f"{'나' if msg['direction'] == 'sent' else sender_name}: {msg['text']}"
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
                        f'다음은 나와 {sender_name}의 최근 대화입니다. '
                        '핵심 주제와 맥락을 간결하게 요약하세요.'
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


def generate_response(system_prompt, conversation_summary, sender_name, incoming_message):
    """Generate an AI response based on context

    Args:
        system_prompt: User's persona/style prompt
        conversation_summary: Summary of recent conversation with sender
        sender_name: Name of the message sender
        incoming_message: The incoming message to respond to

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
    if conversation_summary:
        system_parts.append(
            f'\n[{sender_name}과의 최근 대화 요약]\n{conversation_summary}'
        )

    system_message = '\n'.join(system_parts) if system_parts else (
        '당신은 친절한 대화 상대입니다. 자연스럽고 간결하게 응답하세요.'
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
