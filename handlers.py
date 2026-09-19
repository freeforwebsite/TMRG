import asyncio
import time
from telethon import events
from telethon.errors import FloodWaitError
from config import TARGET_GROUP_ID, DATABASE_CHANNEL_IDS, logger, WATERMARK_ID
from tmdb import search_tmdb
from database import add_to_queue, check_queue_status, increment_stat, search_movies_db

import re

user_cooldowns = {}
COOLDOWN_SECONDS = 5

def filter_accurate_matches(query, matches, tmdb_data):
    if not matches:
        return []
        
    q_words = re.findall(r'[a-zA-Z0-9]+', query.lower())
    if not q_words:
        return matches
        
    expected_year = None
    if tmdb_data and tmdb_data.get('release_date'):
        match = re.search(r'\d{4}', tmdb_data['release_date'])
        if match:
            expected_year = match.group(0)
            
    scored_matches = []
    
    for movie in matches:
        file_name = movie.get('file_name', '').lower()
        score = 0
        
        words = re.findall(r'[a-zA-Z0-9]+', file_name)
        
        # 1. HUGE boost if the requested movie is in the first 4 words of the filename
        # (This ignores uploader tags like [MW] or @TeamHDT, but rejects files where the query is hidden at the end)
        if q_words[0] in words[:5]:
            score += 50
            
        # 2. HUGE boost if the TMDB release year matches a year in the filename
        years_in_file = set(re.findall(r'\b(19\d{2}|20\d{2})\b', file_name))
        if expected_year:
            if expected_year in years_in_file:
                score += 50
            elif years_in_file:
                # If there are years in the filename, but none match TMDB, strongly penalize!
                # (e.g., TMDB expects 2023, but file says "Blast 2026")
                score -= 100
                
        # 3. HUGE boost for Tamil movies (User's highest priority)
        if 'tamil' in file_name:
            score += 25
            
        # If the file passed the checks (score > 0) or if we had no strict criteria, keep it
        if score > 0 or (score == 0 and not expected_year):
            scored_matches.append({'movie': movie, 'score': score})
            
    # Sort highest score first
    scored_matches.sort(key=lambda x: x['score'], reverse=True)
    return [x['movie'] for x in scored_matches]

async def send_movie_results(matches, event, user_id, query, tmdb_data):
    sender = event.sender
    first_name = getattr(sender, 'first_name', "User") if sender else "User"
    user_mention = f"[{first_name}](tg://user?id={user_id})"
    
    if tmdb_data and tmdb_data.get('poster_url'):
        caption = (f"╭━━━ 🎬 **Search Results** ━━━\n"
                   f"┣ 🎬 **Movie :** {tmdb_data['title']}\n"
                   f"┣ 📁 **Total Files :** {len(matches)}\n"
                   f"┣ ⭐️ **Rating :** {tmdb_data['rating']}/10\n"
                   f"┣ 👤 **Requested By :** {user_mention}\n"
                   f"╰━━━ 👇 **Your Files Are Below** 👇 ━━━")
        await event.client.send_message(event.chat_id, message=caption, file=tmdb_data['poster_url'])
    else:
        caption = (f"╭━━━ 🎬 **Search Results** ━━━\n"
                   f"┣ 🎬 **Movie :** {query}\n"
                   f"┣ 📁 **Total Files :** {len(matches)}\n"
                   f"┣ 👤 **Requested By :** {user_mention}\n"
                   f"╰━━━ 👇 **Your Files Are Below** 👇 ━━━")
        await event.client.send_message(event.chat_id, message=caption)

    await increment_stat("total_sent")

    # Send all matching files
    watermark = (f"\n\n"
                 f"╭━━━━━━━━━━━━━━━━━━━\n"
                 f"┣ 👤 **Req By :** {user_mention}\n"
                 f"┣ 🤖 **Bot :** @MovieVaultFilter_bot\n"
                 f"┣ 📢 **Channel :** [Join Our Channel](https://t.me/+PNxLbUANb6NmZDhl)\n"
                 f"╰━━━━━━━━━━━━━━━━━━━")
    
    for movie in matches[:10]:
        try:
            file_name = movie.get('file_name', 'Unknown')
            file_id = movie.get('file_id')
            
            if DATABASE_CHANNEL_IDS:
                found = False
                for channel_id in DATABASE_CHANNEL_IDS:
                    async for msg in event.client.iter_messages(channel_id, search=file_name, limit=1):
                        if msg.media:
                            await event.client.send_file(event.chat_id, msg.media, caption=f"🎬 `{file_name}`{watermark}")
                            found = True
                            break
                    if found:
                        break
                if not found:
                    await event.client.send_message(event.chat_id, message=f"⚠️ `{file_name}` is in the database but could not be found in the vault(s).")
            elif file_id:
                try:
                    await event.client.send_file(event.chat_id, file_id, caption=f"🎬 `{file_name}`{watermark}")
                except Exception as file_e:
                    logger.error(f"Could not send by file_id: {file_e}")
                    await event.client.send_message(event.chat_id, message=f"⚠️ `{file_name}` is in the database but could not be sent directly via Userbot.")
            else:
                msg_id = movie.get('message_id')
                chat_id = movie.get('chat_id')
                if msg_id and chat_id:
                    msg = await event.client.get_messages(chat_id, ids=msg_id)
                    if msg and msg.media:
                        await event.client.send_file(event.chat_id, msg.media, caption=f"🎬 `{file_name}`{watermark}")
        except Exception as e:
            logger.error(f"Failed to send movie file: {e}")

async def watch_queue_and_send(query, event, user_id, wait_msg=None):
    logger.info(f"Actively watching queue for: {query}")
    
    # Poll every 10 seconds for up to 15 minutes
    for _ in range(90):
        await asyncio.sleep(10)
        status = await check_queue_status(query)
        
        if status == 'completed':
            logger.info(f"Scraper completed {query}! Sending to group...")
            await asyncio.sleep(2) # Give it a moment to ensure files are indexed
            
            if wait_msg:
                try:
                    await wait_msg.delete()
                except Exception:
                    pass
                    
            raw_matches = await search_movies_db(query)
            tmdb_data = await search_tmdb(title=query)
            
            matches = filter_accurate_matches(query, raw_matches, tmdb_data)
            
            if matches:
                await send_movie_results(matches, event, user_id, query, tmdb_data)
            return
        elif status == 'failed':
            logger.info(f"Scraper failed for {query}")
            await increment_stat("total_failed")
            if wait_msg:
                try:
                    await wait_msg.edit(f"❌ Sorry, our scraper could not find **{query}** on the internet.")
                except Exception:
                    pass
            return

async def handle_movie_request(event):
    if event.chat_id != TARGET_GROUP_ID:
        return

    if event.raw_text.startswith('/'):
        return

    user_id = event.sender_id
    query = event.raw_text.strip()
    
    if not query:
        return
        
    # Admin command to index a channel
    if query.startswith("!index"):
        parts = query.split()
        if len(parts) < 2:
            await event.client.send_message(event.chat_id, "⚠️ Usage: `!index @username` or `!index -100...`")
            return
        target_input = parts[1]
        try:
            target_channel = int(target_input)
        except ValueError:
            target_channel = target_input
            
        status_msg = await event.client.send_message(event.chat_id, f"⏳ Starting to index {target_channel}...")
        
        from database import movies_col
        added = 0
        skipped = 0
        try:
            async for msg in event.client.iter_messages(target_channel):
                if msg.document or msg.video:
                    media = msg.document or msg.video
                    file_name = getattr(media, "file_name", "Unknown")
                    real_chat_id = msg.chat_id
                    
                    if not movies_col.find_one({"message_id": msg.id, "chat_id": real_chat_id}):
                        movies_col.insert_one({
                            "file_id": media.file_id,
                            "file_name": file_name,
                            "message_id": msg.id,
                            "chat_id": real_chat_id,
                            "file_size": getattr(media, "size", 0)
                        })
                        added += 1
                    else:
                        skipped += 1
                        
            await status_msg.edit(f"✅ **Indexing Complete!**\n\nAdded: `{added}` new movies\nSkipped: `{skipped}` duplicates")
        except Exception as e:
            await status_msg.edit(f"❌ **Error indexing channel:** `{e}`")
        return

    current_time = time.time()
    
    if user_id in user_cooldowns:
        if current_time - user_cooldowns[user_id] < COOLDOWN_SECONDS:
            return
            
    user_cooldowns[user_id] = current_time
    if len(query) < 2:
        return
        
    # Prevent the bot from replying to its own automated responses
    if query.startswith('🎬') or query.startswith('📁') or query.startswith('⚠️'):
        return
        
    logger.info(f"Processing request from {user_id}: {query}")
    await increment_stat("total_requested")
    
    try:
        raw_matches = await search_movies_db(query)
        tmdb_data = await search_tmdb(title=query)
        
        matches = filter_accurate_matches(query, raw_matches, tmdb_data)
        
        if matches:
            await send_movie_results(matches, event, user_id, query, tmdb_data)
        else:
            sender = event.sender
            first_name = getattr(sender, 'first_name', "User") if sender else "User"
            user_mention = f"[{first_name}](tg://user?id={user_id})"
            wait_msg = await event.client.send_message(
                event.chat_id,
                message=f"⏳ {user_mention}, your movie **{query}** is not in our database!\n\n"
                        f"Please wait a few minutes, our scraper is downloading it for you now..."
            )
            await add_to_queue(query)
            asyncio.create_task(watch_queue_and_send(query, event, user_id, wait_msg))
                    
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
