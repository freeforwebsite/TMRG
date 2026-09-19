import motor.motor_asyncio
from config import MONGO_URI, logger
from bson.objectid import ObjectId

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db_movies = client['telegram_bot']
movies_col = db_movies['movies']

db_scraper = client['cinesearch_db']
queue_col = db_scraper['scrape_queue_v2']

async def init_db():
    await movies_col.create_index([("file_name", 1)])
    logger.info("MongoDB initialized.")
import re

async def search_movies_db(query):
    # Extract alphanumeric words from the query (like CineSearch bot does)
    words = re.findall(r'[a-zA-Z0-9]+', query)
    if not words:
        return []
        
    conditions = []
    for word in words:
        # Added \b to ensure we match whole words (prevents 'leo' matching 'harmeLeon')
        conditions.append({"file_name": {"$regex": rf"\b{word}", "$options": "i"}})
        
    # Find files containing ALL words
    cursor = movies_col.find({"$and": conditions}).limit(15)
    return await cursor.to_list(length=15)

async def add_to_queue(movie_name):
    # Check if already pending
    exists = await queue_col.find_one({"movie_name": movie_name, "status": "pending"})
    if not exists:
        doc = {
            "movie_name": movie_name,
            "status": "pending",
            "force": True
        }
        await queue_col.insert_one(doc)
        logger.info(f"Added {movie_name} to queue_v2")

async def check_queue_status(movie_name):
    doc = await queue_col.find_one({"movie_name": movie_name}, sort=[("_id", -1)])
    if doc:
        return doc.get("status")
    return None

stats_col = db_movies['bot_stats']

async def increment_stat(field):
    await stats_col.update_one(
        {"_id": "global_stats"},
        {"$inc": {field: 1}},
        upsert=True
    )

async def get_bot_stats():
    stats = await stats_col.find_one({"_id": "global_stats"})
    return stats or {"total_requested": 0, "total_sent": 0, "total_failed": 0}
