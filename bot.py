import asyncio
import logging
from telethon import TelegramClient, events
from telethon.tl.types import User
import config
import storage
import ai

logger = logging.getLogger(__name__)

client = None

async def start_bot():
    """Start the Telegram bot"""
    global client
    
    cfg = config.load_config()
    
    if not config.is_configured():
        print("Bot is not configured. Please configure through the web UI.")
        return
    
    api_id = int(cfg['API_ID'])
    api_hash = cfg['API_HASH']
    phone = cfg['PHONE']
    
    client = TelegramClient('bot_session', api_id, api_hash)
    
    @client.on(events.NewMessage(incoming=True, from_users=None))
    async def handle_new_message(event):
        """Handle incoming messages"""
        # Only process private messages, ignore groups/channels
        if not event.is_private:
            return
        
        if event.is_private:
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
    
    await client.start(phone=phone)
    print("Bot is running...")
    await client.run_until_disconnected()

def run_bot():
    """Run the bot in the asyncio event loop"""
    asyncio.run(start_bot())

if __name__ == '__main__':
    run_bot()
