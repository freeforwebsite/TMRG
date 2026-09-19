import asyncio
import time
from telethon import events
from telethon.errors import FloodWaitError
from config import TARGET_GROUP_ID, DATABASE_CHANNEL_ID, logger
from matcher import search_movies
from tmdb import search_tmdb
from database import add_to_queue, check_queue_status, increment_stat

user_cooldowns = {}
COOLDOWN_SECONDS = 5

async def send_movie_results(matches, event, user_id, query):
    user = await event.client.get_entity(user_id)
    user_mention = f"[{user.first_name}](tg://user?id={user_id})"
    
    # We use the user's original query to fetch TMDB
    tmdb_data = await search_tmdb(title=query)
    
    if tmdb_data and tmdb_data.get('poster_url'):
        caption = f"🎬 **{tmdb_data['title']}**\n" \
                  f"⭐️ Rating: {tmdb_data['rating']}/10\n" \
                  f"📅 Release Date: {tmdb_data['release_date']}\n" \
                  f"📖 Plot: {tmdb_data['plot']}\n\n" \
                  f"👤 Requested by: {user_mention}"
        await event.client.send_message(event.chat_id, message=caption, file=tmdb_data['poster_url'])
    else:
        await event.client.send_message(event.chat_id, message=f"🎬 Found files for: **{query}**\n👤 Requested by: {user_mention}")

    await increment_stat("total_sent")

    # Send all matching files
    for movie in matches[:10]:
        try:
            file_name = movie.get('file_name', 'Unknown')
            file_id = movie.get('file_id')
            
            if DATABASE_CHANNEL_ID:
                found = False
                async for msg in event.client.iter_messages(DATABASE_CHANNEL_ID, search=file_name, limit=1):
                    if msg.media:
                        await event.client.send_message(event.chat_id, file=msg.media, message=f"📁 `{file_name}`")
                        found = True
                        break
                if not found:
                    await event.client.send_message(event.chat_id, message=f"⚠️ `{file_name}` is in the database but could not be found in the vault.")
            elif file_id:
                try:
                    await event.client.send_message(event.chat_id, file=file_id, message=f"📁 `{file_name}`")
                except Exception as file_e:
                    logger.error(f"Could not send by file_id: {file_e}")
                    await event.client.send_message(event.chat_id, message=f"⚠️ Unable to send `{file_name}` directly via Userbot due to Telegram file_id restrictions.")
            else:
                msg_id = movie.get('message_id')
                chat_id = movie.get('chat_id')
                if msg_id and chat_id:
                    msg = await event.client.get_messages(chat_id, ids=msg_id)
                    if msg:
                        await event.client.send_message(event.chat_id, file=msg.media, message=f"📁 `{file_name}`")
        except Exception as e:
            logger.error(f"Failed to send movie file: {e}")

async def watch_queue_and_send(query, event, user_id):
    logger.info(f"Actively watching queue for: {query}")
    
    # Poll every 10 seconds for up to 15 minutes
    for _ in range(90):
        await asyncio.sleep(10)
        status = await check_queue_status(query)
        
        if status == 'completed':
            logger.info(f"Scraper completed {query}! Sending to group...")
            await asyncio.sleep(2) # Give it a moment to ensure files are indexed
            matches = await search_movies(query)
            if matches:
                await send_movie_results(matches, event, user_id, query)
            return
        elif status == 'failed':
            logger.info(f"Scraper failed for {query}")
            await increment_stat("total_failed")
            return

async def handle_movie_request(event):
    if event.chat_id != TARGET_GROUP_ID:
        return

    if event.raw_text.startswith('/'):
        return

    user_id = event.sender_id
    current_time = time.time()
    
    if user_id in user_cooldowns:
        if current_time - user_cooldowns[user_id] < COOLDOWN_SECONDS:
            return
            
    user_cooldowns[user_id] = current_time
    query = event.raw_text.strip()
    if len(query) < 2:
        return
        
    # Prevent the bot from replying to its own automated responses
    if query.startswith('🎬') or query.startswith('📁') or query.startswith('⚠️'):
        return
        
    logger.info(f"Processing request from {user_id}: {query}")
    await increment_stat("total_requested")
    
    try:
        matches = await search_movies(query)
        
        if matches:
            await send_movie_results(matches, event, user_id, query)
        else:
            await add_to_queue(query)
            asyncio.create_task(watch_queue_and_send(query, event, user_id))
                    
    except FloodWaitError as e:
        logger.warning(f"Flood wait for {e.seconds} seconds")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        logger.error(f"Error handling request: {e}")

def register_user_handlers(client):
    # Debug handler to see ALL messages the bot receives
    @client.on(events.NewMessage())
    async def debug_handler(event):
        logger.info(f"DEBUG - Saw message in chat {event.chat_id}: {event.raw_text}")

    # Removed incoming=True so it can process messages you type yourself!
    client.add_event_handler(handle_movie_request, events.NewMessage(chats=TARGET_GROUP_ID))
