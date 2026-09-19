import os
from dotenv import load_dotenv
import logging

load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME", "movie_assistant")
SESSION_STRING = os.getenv("SESSION_STRING", "")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
TARGET_GROUP_ID = int(os.getenv("TARGET_GROUP_ID", "0"))
SCRAPER_CHANNEL_ID = int(os.getenv("SCRAPER_CHANNEL_ID", "0"))
DATABASE_CHANNEL_ID = int(os.getenv("DATABASE_CHANNEL_ID", "0"))
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")

if not API_ID or not API_HASH:
    raise ValueError("API_ID and API_HASH must be set in .env")

from collections import deque

log_buffer = deque(maxlen=30)

class HTMLDashboardHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        log_buffer.append(log_entry)

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Add custom handler to capture logs globally
dashboard_handler = HTMLDashboardHandler()
dashboard_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(dashboard_handler)
