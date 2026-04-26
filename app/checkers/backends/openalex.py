"""
app/checkers/backends/openalex.py

OpenAlex API backend — supports DOI lookup and full-text title search.
"""
import os
import re
import pyalex
from typing import Optional
from pyalex import Works
from dotenv import load_dotenv
from ..normalizer import normalize_quotes, normalize_ligatures

load_dotenv()
pyalex.config.email = os.getenv("OPENALEX_EMAIL", "your-email@example.com")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _process_work(work: dict) -> Optional[dict]:
    """Convert a raw OpenAlex work object into the standard result dict."""
    if work is None:
        return None

    work_title = work.get('title', 'N/A')

    # Authors (up to 3 + "et al.")
    authors = 'N/A'
    authorships = work.get('authorships', [])
    if authorships:
        names = []
        for auth in authorships[:3]:
            if auth and isinstance(auth, dict):
                author = auth.get('author')
                if author and isinstance(author, dict):
                    name = author.get('display_name', '')
                    if name:
                        names.append(name)
        if names:
            authors = ', '.join(names)
            if len(authorships) > 3:
                authors += ', et al.'

    # Publication year
    pub_year = work.get('publication_year', 'N/A')

    # Venue
    venue = 'N/A'
    loc = work.get('primary_location')
    if loc and isinstance(loc, dict):
        source = loc.get('source')
        if source and isinstance(source, dict):
            venue = source.get('display_name', 'N/A')

    # URL — prefer DOI, fall back to OpenAlex ID
    doi = work.get('doi')
    url = doi if doi else work.get('id', '#')

    return {
        "status": "found",
        "source": "OpenAlex",
        "title": work_title,
        "author": authors,
        "pub_year": str(pub_year) if pub_year != 'N/A' else 'N/A',
        "venue": venue,
        "url": url,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lookup_by_doi(doi: str) -> dict:
    """Fetch a work from OpenAlex by its DOI."""
    try:
        doi_query = doi.rstrip('.,;)]')
        print(f"  OpenAlex DOI lookup: {doi_query}...")
        work = Works()[doi_query]
        if work:
            res = _process_work(work)
            if res:
                print(f"  ✓ Found in OpenAlex (DOI): {res['title'][:60]}...")
                return res
        return {"status": "not_found"}
    except Exception as e:
        err = str(e)
        if "404" in err:
            return {"status": "not_found"}
        print(f"  - OpenAlex DOI error: {err[:50]}...")
        return {"status": "error", "message": err}


def lookup_by_title(title: str) -> dict:
    """Search OpenAlex by title string (full-text search)."""
    try:
        # Normalize typographic quotes and ligatures
        clean = normalize_quotes(title)
        clean = normalize_ligatures(clean)
        # Remove colons, semicolons, and common trailing punctuation for the search query
        query = re.sub(r'[:;.,!?]', ' ', clean).strip()
        
        print(f"  OpenAlex title search: {query[:70]}...")
        results = Works().search(query).get()
        
        if not results:
            # Fallback: Search with only the first ~8 words (often more robust for long titles)
            words = query.split()
            if len(words) > 10:
                short_query = " ".join(words[:8])
                print(f"  → No results for full title. Trying fallback: {short_query}...")
                results = Works().search(short_query).get()

        if results:
            res = _process_work(results[0])
            if res:
                print(f"  ✓ Found in OpenAlex (title): {res['title'][:60]}...")
                return res
        
        print("  - Not found in OpenAlex by title")
        return {"status": "not_found"}
    except Exception as e:
        err = str(e)
        print(f"  - OpenAlex title search error: {err[:50]}...")
        return {"status": "error", "message": err}
