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
        
        # Calculate similarity ratio using Python's built-in difflib
        ratio = difflib.SequenceMatcher(None, normalized_query, normalize_title(file_name)).ratio()
        score = int(ratio * 100)
        
        norm_file = normalize_title(file_name)
        
        # 1. Huge boost if the query is an exact standalone word in the filename
        if normalized_query in norm_file.split():
            score = max(score, 95)
        # 2. Medium boost if it's a substring, but ONLY if the query is at least 4 letters long
        elif normalized_query in norm_file:
            if len(normalized_query) >= 4:
                score = max(score, 80)
            else:
                # If it's a tiny 3-letter word (like 'leo') hidden inside another word (like 'harmeLeon'), do not boost heavily
                score = max(score, 65)
            
        if score >= threshold:
            results.append({'movie': movie, 'score': score})
            
    results.sort(key=lambda x: x['score'], reverse=True)
    
    if not results:
        return []
        
    best_score = results[0]['score']
    final_matches = [r['movie'] for r in results if best_score - r['score'] <= 15]
    
    return final_matches
