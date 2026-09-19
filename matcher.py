import re
import difflib
from database import search_movies_db

def normalize_title(title):
    title = re.sub(r'[^\w\s]', '', str(title))
    return title.strip().lower()

async def search_movies(query, threshold=60):
    title_only = re.sub(r'\d+', '', query).strip()
    if not title_only:
        title_only = query
        
    db_movies = await search_movies_db(title_only)
    
    if not db_movies:
        return []

    normalized_query = normalize_title(query)
    
    results = []
    for movie in db_movies:
        file_name = movie.get('file_name', '')
        
        # Calculate similarity ratio using Python's built-in difflib instead of thefuzz
        ratio = difflib.SequenceMatcher(None, normalized_query, normalize_title(file_name)).ratio()
        score = int(ratio * 100)
        
        # Boost score if it's a direct substring match
        if normalized_query in normalize_title(file_name):
            score = max(score, 85)
            
        if score >= threshold:
            results.append({'movie': movie, 'score': score})
            
    results.sort(key=lambda x: x['score'], reverse=True)
    
    if not results:
        return []
        
    best_score = results[0]['score']
    final_matches = [r['movie'] for r in results if best_score - r['score'] <= 15]
    
    return final_matches
