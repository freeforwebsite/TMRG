import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from config import API_ID, API_HASH, SESSION_NAME, SESSION_STRING, logger
from handlers import register_user_handlers
from admin import register_admin_handlers
from database import init_db, movies_col, queue_col

async def dummy_web_server(reader, writer):
    request = await reader.read(1024)
    
    try:
        movie_count = await movies_col.count_documents({})
        pending_count = await queue_col.count_documents({"status": "pending"})
        completed_count = await queue_col.count_documents({"status": "completed"})
        
        html = f"""<!DOCTYPE html>
        <html>
        <head>
            <title>CineSearch Dashboard</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0f172a; color: #f8fafc; text-align: center; padding: 40px; margin: 0; }}
                h1 {{ color: #38bdf8; font-size: 2.5em; margin-bottom: 5px; }}
                p {{ color: #94a3b8; font-size: 1.1em; margin-bottom: 40px; }}
                .container {{ display: flex; justify-content: center; flex-wrap: wrap; gap: 20px; }}
                .card {{ background: #1e293b; padding: 30px; border-radius: 15px; width: 220px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5); border-top: 4px solid #38bdf8; transition: transform 0.2s; }}
                .card:hover {{ transform: translateY(-5px); }}
                .stat {{ font-size: 3em; font-weight: bold; margin: 15px 0; }}
                .label {{ color: #cbd5e1; font-size: 1.1em; text-transform: uppercase; letter-spacing: 1px; }}
                .pulse {{ display: inline-block; width: 12px; height: 12px; background-color: #22c55e; border-radius: 50%; box-shadow: 0 0 10px #22c55e; margin-right: 10px; }}
            </style>
        </head>
        <body>
            <h1>🎬 CineSearch Live Dashboard</h1>
            <p><span class="pulse"></span> System is Online and Actively Listening</p>
            
            <div class="container">
                <div class="card" style="border-top-color: #3b82f6;">
                    <div class="label">Vault Database</div>
                    <div class="stat">{movie_count:,}</div>
                    <div class="label" style="font-size: 0.8em;">Indexed Files</div>
                </div>
                <div class="card" style="border-top-color: #f59e0b;">
                    <div class="label">Pending Queue</div>
                    <div class="stat" style="color: #fcd34d;">{pending_count:,}</div>
                    <div class="label" style="font-size: 0.8em;">Waiting for AI Scraper</div>
                </div>
                <div class="card" style="border-top-color: #10b981;">
                    <div class="label">Completed</div>
                    <div class="stat" style="color: #6ee7b7;">{completed_count:,}</div>
                    <div class="label" style="font-size: 0.8em;">Successfully Scraped</div>
                </div>
            </div>
        </body>
        </html>
        """
        response_body = html.encode('utf-8')
        response = b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: " + str(len(response_body)).encode() + b"\r\n\r\n" + response_body
    except Exception as e:
        logger.error(f"Dashboard Error: {e}")
        response = b"HTTP/1.1 500 ERROR\r\n\r\n"
        
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
