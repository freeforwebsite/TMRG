import asyncio
import os
import pymongo
from dotenv import load_dotenv

# Fix for Python 3.14 asyncio loop issue
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from pyrogram import Client

load_dotenv()

BOT_TOKEN = input("Enter your Bot Token (e.g. from BotFather): ").strip()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
MONGO_URI = os.getenv("MONGO_URI")

TARGET_INPUT = input("Enter the new Channel ID or @username: ").strip()
try:
    TARGET_CHANNEL = int(TARGET_INPUT)
except ValueError:
    TARGET_CHANNEL = TARGET_INPUT

db_client = pymongo.MongoClient(MONGO_URI)
movies_col = db_client['telegram_bot']['movies']

app = Client("indexer_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def scan_channel():
    print(f"\n[Scanning Channel {TARGET_CHANNEL}]")
    added = 0
    skipped = 0
    async for msg in app.get_chat_history(TARGET_CHANNEL):
        if msg.document or msg.video:
            media = msg.document or msg.video
            file_name = getattr(media, "file_name", "Unknown")
            
            # Always store the raw integer ID in the database so the Userbot can find it!
            real_chat_id = msg.chat.id
            
            if not movies_col.find_one({"message_id": msg.id, "chat_id": real_chat_id}):
                movies_col.insert_one({
                    "file_id": media.file_id,
                    "file_name": file_name,
                    "message_id": msg.id,
                    "chat_id": real_chat_id,
                    "file_size": getattr(media, "file_size", 0)
                })
                added += 1
                print(f"Added: {file_name}")
            else:
                skipped += 1
    print(f"\nDone! Successfully added {added} new movies. Skipped {skipped} duplicates.")
    os._exit(0)

@app.on_message()
async def catch_ping(client, message):
    try:
        chat_username = getattr(message.chat, "username", "") or ""
        target_username = str(TARGET_CHANNEL).replace("@", "")
        
        # Debug print so we know the bot is alive and seeing messages
        print(f"Saw message in chat: {message.chat.title} (ID: {message.chat.id}, Username: {chat_username})")
        
        if message.chat.id == TARGET_CHANNEL or chat_username.lower() == target_username.lower():
            print("\nPing received! Channel verified. Starting full database scan...")
            await scan_channel()
    except Exception as e:
        print(f"Ping Error: {e}")

async def main():
    async with app:
        try:
            # Try to scan instantly (works immediately for @usernames!)
            await scan_channel()
        except Exception as e:
            print(f"\n[Error from Telegram]: {e}")
            print(f"\nCould not read automatically (it might be private).")
            print(f"👉 Please go to your channel right now and send a test message (like 'hello').")
            print(f"As soon as you send it, the bot will see it and instantly begin scanning!\n")
            await asyncio.Event().wait()

if __name__ == "__main__":
    app.run(main())
