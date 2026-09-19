from telethon import events
from config import ADMIN_IDS, logger
from database import movies_col, queue_col

async def handle_stats(event):
    if event.sender_id not in ADMIN_IDS:
        return
        
    try:
        movie_count = await movies_col.count_documents({})
        queue_count = await queue_col.count_documents({"status": "pending"})
        
        await event.reply(
            f"📊 **Userbot Status**\n\n"
            f"🎬 Total Movies in DB: `{movie_count}`\n"
            f"⏳ Pending Scrape Queue: `{queue_count}`\n"
            f"✅ Bot is fully integrated with CineSearch!"
        )
    except Exception as e:
        await event.reply(f"❌ Error getting stats: {e}")

def register_admin_handlers(client):
    client.add_event_handler(handle_stats, events.NewMessage(pattern='/botstats', incoming=True))
