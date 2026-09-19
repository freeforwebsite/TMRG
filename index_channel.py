import asyncio
import os
import pymongo
from pyrogram import Client
from dotenv import load_dotenv

load_dotenv()

# We will use Pyrogram with a Bot Token so it doesn't conflict with your Userbot Session!
BOT_TOKEN = input("Enter your Bot Token (e.g. from BotFather): ").strip()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
MONGO_URI = os.getenv("MONGO_URI")

TARGET_CHANNEL = input("Enter the new Channel ID (e.g. -100...): ").strip()
TARGET_CHANNEL = int(TARGET_CHANNEL)

print("Connecting to database...")
db_client = pymongo.MongoClient(MONGO_URI)
db = db_client['telegram_bot']
movies_col = db['movies']

app = Client("indexer_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def main():
    async with app:
        print(f"Scanning channel {TARGET_CHANNEL} for movies...")
        added_count = 0
        skipped_count = 0
        
        async for msg in app.get_chat_history(TARGET_CHANNEL):
            if msg.document or msg.video:
                media = msg.document or msg.video
                file_name = getattr(media, "file_name", "Unknown")
                
                # Check if already in DB
                exists = movies_col.find_one({"message_id": msg.id, "chat_id": TARGET_CHANNEL})
                if not exists:
                    doc = {
                        "file_id": media.file_id,
                        "file_name": file_name,
                        "message_id": msg.id,
                        "chat_id": TARGET_CHANNEL,
                        "file_size": getattr(media, "file_size", 0)
                    }
                    movies_col.insert_one(doc)
                    added_count += 1
                    print(f"Added: {file_name}")
                else:
                    skipped_count += 1
                    
        print(f"\nDone! Successfully added {added_count} new movies to the database. Skipped {skipped_count} duplicates.")

if __name__ == "__main__":
    app.run(main())
