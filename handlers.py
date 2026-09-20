import asyncio
import time
from telethon import events
from telethon.errors import FloodWaitError
from config import TARGET_GROUP_ID, DATABASE_CHANNEL_IDS, logger, WATERMARK_ID
from tmdb import search_tmdb
from database import add_to_queue, check_queue_status, increment_stat, search_movies_db

import re

# Dictionary to store cooldowns per user (prevent spam)
user_cooldowns = {}
# Dictionary to store search sessions for pagination
user_search_cache = {}
# Global flag to control if the bot is actively processing requests
BOT_IS_ACTIVE = True
BOT_OWNER_ID = None
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

async def send_movie_results(matches, event, user_id, query, tmdb_data, page=1):
    logger.info(f"Sending {len(matches)} results to {user_id}")
    
    # Cache the original full list of matches for this user to support pagination
    if page == 1:
        user_search_cache[user_id] = {
            'matches': matches,
            'tmdb_data': tmdb_data,
            'query': query
        }
        
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
            msg_id = movie.get('message_id')
            chat_id = movie.get('chat_id')
            file_id = movie.get('file_id')
            
            sent = False
            
            # 1. Try by exact message_id and chat_id (Fastest & Most Reliable)
            if msg_id and chat_id:
                try:
                    msg = await event.client.get_messages(chat_id, ids=msg_id)
                    if msg and msg.media:
                        await event.client.send_file(event.chat_id, msg.media, caption=f"🎬 `{file_name}`{watermark}")
                        sent = True
                except Exception as e:
                    logger.error(f"Failed to fetch by ID: {e}")
                    
            # 2. Try by file_id
            if not sent and file_id:
                try:
                    await event.client.send_file(event.chat_id, file_id, caption=f"🎬 `{file_name}`{watermark}")
                    sent = True
                except Exception as file_e:
                    logger.error(f"Could not send by file_id: {file_e}")
                    
            # 3. Fallback to searching the channels by text
            if not sent and DATABASE_CHANNEL_IDS:
                for channel_id in DATABASE_CHANNEL_IDS:
                    try:
                        async for msg in event.client.iter_messages(channel_id, search=file_name, limit=1):
                            if msg.media:
                                await event.client.send_file(event.chat_id, msg.media, caption=f"🎬 `{file_name}`{watermark}")
                                sent = True
                                break
                    except Exception as iter_e:
                        logger.error(f"Error searching channel {channel_id}: {iter_e}")
                    if sent:
                        break
                        
            if not sent:
                await event.client.send_message(event.chat_id, message=f"⚠️ `{file_name}` is in the database but could not be downloaded from the vault.")
        except Exception as e:
            logger.error(f"Failed to send movie file: {e}")
            
    if len(matches) > 10:
        await event.client.send_message(
            event.chat_id,
            f"**Page {page}**\nThere are more files for this search!\n\n👉 **Reply** to this message with the word `next` to see the next page!"
        )

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
    global BOT_IS_ACTIVE, BOT_OWNER_ID
    
    # Only listen to the target group
    if event.chat_id != TARGET_GROUP_ID:
        return

    user_id = event.sender_id
    raw_text = event.raw_text.strip()
    
    if not raw_text:
        return
        
    # Admin commands to pause/start the bot manually
    try:
        if BOT_OWNER_ID is None:
            me = await event.client.get_me()
            BOT_OWNER_ID = me.id
            
        is_admin = (str(user_id) in ADMIN_IDS) or (user_id == BOT_OWNER_ID)
        
        if raw_text.lower() == "!pause" and is_admin:
            BOT_IS_ACTIVE = False
            await event.client.send_message(event.chat_id, "⏸️ **Bot Paused**\nThe bot is now sleeping and will ignore all movie requests.", reply_to=event.id)
            return
            
        if raw_text.lower() == "!start" and is_admin:
            BOT_IS_ACTIVE = True
            await event.client.send_message(event.chat_id, "▶️ **Bot Resumed**\nThe bot is back online and listening for requests!", reply_to=event.id)
            return
    except Exception as e:
        logger.error(f"Admin check error: {e}")
        
    if not BOT_IS_ACTIVE:
        return
        
    # Handle pagination via reply
    if raw_text.lower() == "next" and event.is_reply:
        try:
            reply_msg = await event.get_reply_message()
            if reply_msg and reply_msg.sender_id == (await event.client.get_me()).id:
                import re
                match = re.search(r"Page (\d+)", reply_msg.text)
                if match:
                    current_page = int(match.group(1))
                    page = current_page + 1
                    
                    if user_id in user_search_cache:
                        matches = user_search_cache[user_id]['matches']
                        tmdb_data = user_search_cache[user_id]['tmdb_data']
                        original_query = user_search_cache[user_id]['query']
                        
                        start_idx = (page - 1) * 10
                        
                        if start_idx < len(matches):
                            await send_movie_results(matches[start_idx:], event, user_id, original_query, tmdb_data, page=page)
                        else:
                            await event.client.send_message(event.chat_id, "⚠️ No more results found on this page.", reply_to=event.id)
                    else:
                        await event.client.send_message(event.chat_id, "⚠️ Search session expired. Please search for the movie again.", reply_to=event.id)
                    return
        except Exception as e:
            logger.error(f"Pagination reply error: {e}")
            
    # Keep old /next_ command as a hidden fallback just in case
    if raw_text.startswith("/next_"):
        parts = raw_text.split("_")
        if len(parts) >= 2:
            try:
                page = int(parts[1])
                if user_id in user_search_cache:
                    matches = user_search_cache[user_id]['matches']
                    tmdb_data = user_search_cache[user_id]['tmdb_data']
                    original_query = user_search_cache[user_id]['query']
                    
                    start_idx = (page - 1) * 10
                    
                    if start_idx < len(matches):
                        await send_movie_results(matches[start_idx:], event, user_id, original_query, tmdb_data, page=page)
                    else:
                        await event.client.send_message(event.chat_id, "⚠️ No more results found on this page.", reply_to=event.id)
                else:
                    await event.client.send_message(event.chat_id, "⚠️ Search session expired. Please search for the movie again.", reply_to=event.id)
            except ValueError:
                pass
        return

    if raw_text.startswith('/'):
        return

    query = raw_text
    
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
        
        # 1. TMDB Auto-Correct
        if not raw_matches and tmdb_data and tmdb_data.get('title'):
            corrected_query = tmdb_data['title']
            if corrected_query.lower() != query.lower():
                raw_matches = await search_movies_db(corrected_query)
                
        # 2. GEMINI AI Auto-Correct (The Ultimate Brain)
        import os
        import random
        
        gemini_keys = []
        for i in range(1, 10):
            key = os.getenv(f"GEMINI_API_KEY_{i}")
            if key:
                gemini_keys.append(key)
        
        if not gemini_keys and os.getenv("GEMINI_API_KEY"):
            gemini_keys.append(os.getenv("GEMINI_API_KEY"))
            
        ai_model_name = os.getenv("AI_MODEL", "gemini-1.5-flash")
        
        if not raw_matches and gemini_keys:
            try:
                import google.generativeai as genai
                # Pick a random key to distribute load and avoid rate limits
                selected_key = random.choice(gemini_keys)
                genai.configure(api_key=selected_key)
                
                model = genai.GenerativeModel(ai_model_name)
                prompt = f"The user searched for a movie named '{query}'. They likely spelled it wrong (e.g. missing 'h' or 's'). Reply ONLY with the most likely correct spelling of this Indian or Hollywood movie name. Do not add quotes or periods."
                response = await model.generate_content_async(prompt)
                ai_corrected = response.text.strip()
                
                if ai_corrected and ai_corrected.lower() != query.lower():
                    raw_matches = await search_movies_db(ai_corrected)
            except Exception as e:
                logger.error(f"Gemini API Error: {e}")
        
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
