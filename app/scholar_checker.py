from scholarly import scholarly, ProxyGenerator
import time
import random
import re

# Optional: Setup proxy if needed later. 
# pg = ProxyGenerator()
# pg.FreeProxies()
# scholarly.use_proxy(pg)

def extract_title_from_reference(ref_text):
    """
    Attempts to extract the title from a reference string.
    Different citation styles have different formats.
    """
    # Remove common reference number prefixes: [1], 1., etc.
    text = re.sub(r'^\s*\[?\d+\]?\.?\s*', '', ref_text)
    
    # Many citation styles have: Authors, "Title", or Authors. Title.
    # Try to find text in quotes (common for titles)
    quoted = re.search(r'["""]([^"""]+)["""]', text)
    if quoted:
        return quoted.group(1).strip()
    
    # Try to find text after first period and before next period (rough heuristic)
    # Format: Author, A. (Year). Title. Journal...
    parts = text.split('.')
    if len(parts) >= 2:
        # Skip the first part (usually author), take the next substantive part
        for part in parts[1:]:
            part = part.strip()
            if len(part) > 20 and not re.match(r'^\d{4}', part):  # Not just a year
                return part
    
    # Fallback: use first 100 chars as query
    return text[:100].strip()

def check_reference(ref_text):
    """
    Checks a reference string against Google Scholar.
    Returns a dictionary with status and found metadata.
    """
    if not ref_text or len(ref_text) < 10:
        return {"status": "skipped", "reason": "Too short"}

    # Extract a better search query (title is more accurate than full reference)
    search_query_text = extract_title_from_reference(ref_text)
    
    print(f"\n[DEBUG] Checking reference...")
    print(f"  Original: {ref_text[:100]}...")
    print(f"  Query: {search_query_text[:80]}...")

    # Rate limiting protection
    delay = random.uniform(2.0, 4.0)  # Increased from 1-3 to 2-4
    print(f"  Waiting {delay:.1f}s before query...")
    time.sleep(delay)

    try:
        # scholarly.search_pubs returns a generator
        search_query = scholarly.search_pubs(search_query_text)
        
        try:
            # Get the first result
            print("  Fetching result...")
            first_result = next(search_query)
            
            # Extract useful metadata
            bib = first_result.get('bib', {})
            title = bib.get('title', 'N/A')
            
            print(f"  ✓ Found: {title[:60]}...")
            
            return {
                "status": "found",
                "title": title,
                "author": bib.get('author', 'N/A'),
                "pub_year": bib.get('pub_year', 'N/A'),
                "venue": bib.get('venue', 'N/A'),
                "url": first_result.get('pub_url', '#')
            }
            
        except StopIteration:
            print("  ✗ Not found in Scholar")
            return {"status": "not_found"}
            
    except Exception as e:
        # Likely a rate limit or network error
        print(f"  ✗ ERROR: {str(e)}")
        return {"status": "error", "message": str(e)}

