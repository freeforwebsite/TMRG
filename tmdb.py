import json
import asyncio
import urllib.request
from urllib.parse import quote
from config import TMDB_API_KEY, logger

def _fetch_tmdb_sync(url):
    import ssl
    import time
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
                if response.status == 200:
                    return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            logger.error(f"TMDB API error (Attempt {attempt+1}): {e}")
            time.sleep(1)
    return None

async def search_tmdb(title, year=None, language=None):
    if not TMDB_API_KEY:
        logger.warning("TMDB_API_KEY not set. Cannot fetch metadata.")
        return None

    lang_map = {
        "tamil": "ta",
        "english": "en",
        "telugu": "te",
        "hindi": "hi",
        "malayalam": "ml",
        "kannada": "kn"
    }
    
    iso_lang = None
    if language:
        iso_lang = lang_map.get(language.lower(), None)

    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={quote(title)}"
    if year:
        url += f"&primary_release_year={year}"

    # Use asyncio.to_thread and urllib to bypass aiohttp C-compiler requirements
    data = await asyncio.to_thread(_fetch_tmdb_sync, url)
    
    if data:
        results = data.get('results', [])
        if not results:
            return None
            
        best_match = results[0]
        if iso_lang:
            for r in results:
                if r.get('original_language') == iso_lang:
                    best_match = r
                    break
                    
        poster_path = best_match.get('poster_path')
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
        
        return {
            'title': best_match.get('title', title),
            'rating': best_match.get('vote_average', 0.0),
            'release_date': best_match.get('release_date', 'Unknown'),
            'plot': best_match.get('overview', 'No plot available.'),
            'poster_url': poster_url
        }
    return None
