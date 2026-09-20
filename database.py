import motor.motor_asyncio
from config import MONGO_URI, logger
from bson.objectid import ObjectId

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db_movies = client['telegram_bot']
movies_col = db_movies['movies']

db_scraper = client['cinesearch_db']
queue_col = db_scraper['scrape_queue']

async def init_db():
    await movies_col.create_index([("file_name", 1)])
    logger.info("MongoDB initialized.")
import re

import difflib

# Memory cache for fuzzy searching
_movie_cache = []
_movie_cache_time = 0

async def search_movies_db(query):
    # Try exact match first
    words = re.findall(r'[a-zA-Z0-9]+', query)
    if not words:
        return []
        
    conditions = []
    for word in words:
        conditions.append({"file_name": {"$regex": rf"\b{word}\b", "$options": "i"}})
        
    cursor = movies_col.find({"$and": conditions}).limit(50)
    results = await cursor.to_list(length=50)
    
    # If no results found, use difflib to find spelling mistakes!
    if not results:
        global _movie_cache, _movie_cache_time
        import time
        # Refresh cache every hour
        if not _movie_cache or (time.time() - _movie_cache_time) > 3600:
            cursor = movies_col.find({}, {"file_name": 1})
            _movie_cache = [doc['file_name'] async for doc in cursor if 'file_name' in doc]
            _movie_cache_time = time.time()
            
        # Get closest string matches
        # Increased cutoff to 0.7 to prevent completely random movies from matching
        close_names = difflib.get_close_matches(query, _movie_cache, n=10, cutoff=0.7)
        
        if close_names:
            cursor = movies_col.find({"file_name": {"$in": close_names}}).limit(10)
            results = await cursor.to_list(length=10)
            
    return results

async def add_to_queue(movie_name):
    # Check if already pending
    exists = await queue_col.find_one({"movie_name": movie_name, "status": "pending"})
    if not exists:
        doc = {
            "movie_name": movie_name,
            "status": "pending",
            "force": True,
            "is_urgent": True
        }
        await queue_col.insert_one(doc)
        logger.info(f"Added {movie_name} to urgent scrape queue")

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
