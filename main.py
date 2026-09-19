import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from config import API_ID, API_HASH, SESSION_NAME, SESSION_STRING, logger
from handlers import register_user_handlers
from admin import register_admin_handlers
from database import init_db

async def main():
    await init_db()
    
    logger.info("Starting Telegram Movie Assistant...")
    
    if SESSION_STRING:
        client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
        logger.info("Using StringSession (Render Mode).")
    else:
        client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
        logger.info("Using local SQLite session file (Local Mode).")
        
    await client.start()
    
    # Check if we are logged in
    me = await client.get_me()
    logger.info(f"Logged in as: {me.first_name} (@{me.username})")
    
    # Register handlers
    register_admin_handlers(client)
    register_user_handlers(client)
    
    logger.info("Bot is running and listening for requests...")
    
    # Run the client until disconnected
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped gracefully.")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
