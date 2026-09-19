import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from config import API_ID, API_HASH, SESSION_NAME, SESSION_STRING, logger
from handlers import register_user_handlers
from admin import register_admin_handlers
from database import init_db

async def dummy_web_server(reader, writer):
    # This simple response tells Render and UptimeRobot that the bot is "Alive"
    request = await reader.read(1024)
    response = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nBot is running perfectly!"
    writer.write(response)
    await writer.drain()
    writer.close()

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
    
    if not await client.is_user_authorized():
        logger.error("Client is not logged in!")
        return
        
    logger.info(f"Logged in as: {(await client.get_me()).first_name}")
    
    register_user_handlers(client)
    register_admin_handlers(client)
    
    logger.info("Bot is running and listening for requests...")
    
    # Start the dummy web server on the port Render provides
    port = int(os.environ.get("PORT", 10000))
    server = await asyncio.start_server(dummy_web_server, '0.0.0.0', port)
    logger.info(f"Dummy web server bound to port {port} for Render health checks")
    
    async with server:
        await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped gracefully.")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
