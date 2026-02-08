import asyncio
from telethon import TelegramClient, events
from telethon.tl.types import User
import config
import storage
import utils

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
        # Skip messages from self
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
            
            # Send auto-response
            response_message = cfg.get('AUTO_RESPONSE_MESSAGE', '잠시 후 응답드리겠습니다. 조금만 기다려주세요.')
            await event.respond(response_message)
            
            # Store sent response
            storage.add_message('sent', 'Me', response_message)
            
            # Summarize and notify
            summary = utils.summarize_message(message_text)
            notify_url = cfg.get('NOTIFY_API_URL')
            
            if notify_url:
                utils.notify_api(summary, sender_name, notify_url)
            
            print(f"Received message from {sender_name}: {message_text[:50]}...")
            print(f"Summary: {summary}")
    
    await client.start(phone=phone)
    print("Bot is running...")
    await client.run_until_disconnected()

def run_bot():
    """Run the bot in the asyncio event loop"""
    asyncio.run(start_bot())

if __name__ == '__main__':
    run_bot()
