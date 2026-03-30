from pyalex import Works
import pyalex
from habanero import Crossref
import requests
import xml.etree.ElementTree as ET
import time
import random
import re
import os
from pathlib import Path
from dotenv import load_dotenv
from difflib import SequenceMatcher

# Load environment variables
load_dotenv()

# Initialize Crossref
cr = Crossref()

# Set user agent for OpenAlex (polite pool - faster responses)
pyalex.config.email = os.getenv("OPENALEX_EMAIL", "your-email@example.com")

print("[INIT] Initializing OpenAlex, Crossref & DataCite...")
print("[INIT] ✓ Verification engines ready")

def extract_title_from_reference(ref_text):
    """
    Attempts to extract the title from a reference string.
    """
    # Remove common reference number prefixes: [1], 1., etc.
    text = re.sub(r'^\s*\[?\d+\]?\.\?\s*', '', ref_text)
    
    # Try to find text in quotes (standard, smart, or LaTeX-style)
    # This matches '""', '""', '``', and "''" as quote markers
    quoted = re.search(r'(?:"|“|``)(.*?)(?:"|”|\'\')', text)
    if quoted:
        return quoted.group(1).strip()
    
    # Try to find text after first period and before next period
    parts = text.split('.')
    if len(parts) >= 2:
        for part in parts[1:]:
            part = part.strip()
            if len(part) > 20 and not re.match(r'^\d{4}', part):
                return part
    
    # Fallback
    return text[:100].strip()

def calculate_similarity(text1, text2):
    """
    Calculates similarity between two strings using SequenceMatcher.
    Normalizes strings by removing punctuation and converting to lowercase.
    """
    if not text1 or not text2:
        return 0.0
    
    # Basic normalization: remove punctuation and lower case
    def normalize(text):
        # Remove non-alphanumeric chars (keep spaces)
        clean = re.sub(r'[^\w\s]', '', text)
        return clean.lower().strip()
    
    s1 = normalize(text1)
    s2 = normalize(text2)
    
    # If one is empty after normalization but wasn't before, use original
    if not s1 or not s2:
        s1 = text1.lower().strip()
        s2 = text2.lower().strip()
        
    return SequenceMatcher(None, s1, s2).ratio()

def extract_doi_info(ref_text):
    """
    Extracts a DOI from a reference string and returns (doi, end_position).
    """
    # Strict DOI regex
    strict_pattern = r'10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+'
    match = re.search(strict_pattern, ref_text)
    if match:
        raw_doi = match.group(0)
        # We don't rstrip here yet because we might need trailing chars for healing
        return raw_doi, match.end()
    return None, 0

def heal_doi(base_doi, end_pos, ref_text):
    """
    Attempts to extend a DOI if the original might be broken by spaces.
    Example: 10.1016/j.tra.2025. <space> 104429
    """
    tail = ref_text[end_pos:]
    # Look for a space followed by more DOI-like characters
    # We allow up to 2 segments expansion
    match = re.match(r'^\s+([-._;()/:a-zA-Z0-9]+)', tail)
    if match:
        extension = match.group(1)
        # Basic heuristic: ignore common short English words
        if extension.lower() not in ['is', 'a', 'the', 'and', 'for', 'in', 'on', 'with']:
            healed = base_doi + extension
            print(f"  [DEBUG] DOI healing: {base_doi} -> {healed}")
            return healed, end_pos + match.end()
    return None, 0

def extract_arxiv_id(ref_text):
    """
    Extracts an arXiv ID from a reference string.
    """
    # 1. Pattern for modern IDs (arxiv:2412.11814) or URL format
    arxiv_pattern = r'arxiv:?\s*([a-z-]+(?:\.[a-z-]+)?/)?(\d{4}\.\d{4,5}(v\d+)?)'
    match = re.search(arxiv_pattern, ref_text, re.IGNORECASE)
    if match:
        return match.group(2).strip()
        
    # 2. URL format (e.g., arxiv.org/abs/2412.11814)
    url_pattern = r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(v\d+)?|[a-z-]+(?:\.[A-Z]{2})?/\d{7}(v\d+)?)'
    match = re.search(url_pattern, ref_text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
        
    return None


def process_openalex_work(work):
    """
    Helper to process an OpenAlex work object into our standard format.
    """
    if work is None:
        return None
        
    work_title = work.get('title', 'N/A')
    
    # Extract authors
    authors = 'N/A'
    authorships = work.get('authorships', [])
    if authorships:
        author_names = []
        for auth in authorships[:3]:
            if auth and isinstance(auth, dict):
                author = auth.get('author')
                if author and isinstance(author, dict):
                    name = author.get('display_name', '')
                    if name:
                        author_names.append(name)
        if author_names:
            authors = ', '.join(author_names)
            if len(authorships) > 3:
                authors += ', et al.'
    
    # Extract publication year
    pub_year = work.get('publication_year', 'N/A')
    
    # Extract venue
    venue = 'N/A'
    primary_location = work.get('primary_location')
    if primary_location and isinstance(primary_location, dict):
        source = primary_location.get('source')
        if source and isinstance(source, dict):
            venue = source.get('display_name', 'N/A')
    
    # Get DOI or OpenAlex URL
    doi = work.get('doi')
    url = doi if doi else work.get('id', '#')
    
    return {
        "status": "found",
        "source": "OpenAlex",
        "title": work_title,
        "author": authors,
        "pub_year": str(pub_year) if pub_year != 'N/A' else 'N/A',
        "venue": venue,
        "url": url
    }

def check_openalex(title):
    """
    Check reference in OpenAlex database by title search.
    """
    try:
        print(f"  OpenAlex title search: {title[:70]}...")
        
        # Normalize curly quotes which can break the OpenAlex search API
        clean_title = title.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
        
        results = Works().search(clean_title).get()
        
        if results and len(results) > 0:
            res = process_openalex_work(results[0])
            if res:
                print(f"  ✓ Found in OpenAlex (title): {res['title'][:60]}...")
                return res
        
        print("  - Not found in OpenAlex by title")
        return {"status": "not_found"}
            
    except Exception as e:
        error_msg = str(e)
        print(f"  - OpenAlex title search error: {error_msg[:50]}...")
        return {"status": "error", "message": error_msg}

def check_openalex_by_doi(doi):
    """
    Check reference in OpenAlex database by DOI.
    """
    try:
        # Clean DOI for lookup
        doi_query = doi.rstrip('.,;)]')
        print(f"  OpenAlex DOI lookup: {doi_query}...")
        
        work = Works()[doi_query]
        
        if work:
            res = process_openalex_work(work)
            if res:
                print(f"  ✓ Found in OpenAlex (DOI): {res['title'][:60]}...")
                return res
        
        return {"status": "not_found"}
    except Exception as e:
        error_msg = str(e)
        if "404" in error_msg:
            return {"status": "not_found"}
        print(f"  - OpenAlex DOI error: {error_msg[:50]}...")
        return {"status": "error", "message": error_msg}

def check_crossref(doi):
    """
    Check reference in Crossref database using a DOI.
    """
    try:
        doi_query = doi.rstrip('.,;)]')
        print(f"  Crossref DOI lookup: {doi_query}...")
        res = cr.works(ids = doi_query)
        
        if res and 'message' in res:
            work = res['message']
            
            # Extract title
            title_list = work.get('title', ['N/A'])
            work_title = title_list[0] if title_list else 'N/A'
            
            print(f"  ✓ Found in Crossref: {work_title[:60]}...")
            
            # Extract authors
            author_list = work.get('author', [])
            authors = 'N/A'
            if author_list:
                author_names = []
                for auth in author_list[:3]:
                    given = auth.get('given', '')
                    family = auth.get('family', '')
                    if given and family:
                        author_names.append(f"{given} {family}")
                    elif family:
                        author_names.append(family)
                if author_names:
                    authors = ', '.join(author_names)
                    if len(author_list) > 3:
                        authors += ', et al.'
            
            # Extract publication year
            published = work.get('published-print') or work.get('published-online') or work.get('issued')
            pub_year = 'N/A'
            if published and 'date-parts' in published:
                try:
                    pub_year = str(published['date-parts'][0][0])
                except (IndexError, TypeError):
                    pass
            
            # Extract venue
            container_titles = work.get('container-title', ['N/A'])
            venue = container_titles[0] if container_titles else 'N/A'
            
            # URL
            url = work.get('URL', f"https://doi.org/{doi_query}")
            
            return {
                "status": "found",
                "source": "Crossref",
                "title": work_title,
                "author": authors,
                "pub_year": pub_year,
                "venue": venue,
                "url": url
            }
        
        return {"status": "not_found"}
    except Exception as e:
        error_msg = str(e)
        if "404" in error_msg:
            return {"status": "not_found"}
            
        print(f"  - Crossref error: {error_msg[:50]}...")
        return {"status": "error", "message": error_msg}

def check_datacite(doi):
    """
    Check reference in DataCite database.
    """
    try:
        doi_query = doi.rstrip('.,;)]')
        print(f"  DataCite DOI lookup: {doi_query}...")
        url = f"https://api.datacite.org/dois/{doi_query}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json().get('data', {})
            attributes = data.get('attributes', {})
            
            # Extract title
            titles = attributes.get('titles', [])
            work_title = titles[0].get('title', 'N/A') if titles else 'N/A'
            
            print(f"  ✓ Found in DataCite: {work_title[:60]}...")
            
            # Extract authors
            creators = attributes.get('creators', [])
            authors = 'N/A'
            if creators:
                author_names = []
                for creator in creators[:3]:
                    name = creator.get('name', '')
                    if name:
                        author_names.append(name)
                if author_names:
                    authors = ', '.join(author_names)
                    if len(creators) > 3:
                        authors += ', et al.'
            
            # Extract publication year
            pub_year = str(attributes.get('publicationYear', 'N/A'))
            
            # Extract venue/publisher
            venue = attributes.get('publisher', 'N/A')
            
            # URL
            url = f"https://doi.org/{doi_query}"
            
            return {
                "status": "found",
                "source": "DataCite",
                "title": work_title,
                "author": authors,
                "pub_year": pub_year,
                "venue": venue,
                "url": url
            }
        
        return {"status": "not_found"}
    except Exception as e:
        error_msg = str(e)
        print(f"  - DataCite error: {error_msg[:50]}...")
        return {"status": "error", "message": error_msg}

def check_arxiv(arxiv_id):
    """
    Check reference using official arXiv API.
    """
    try:
        print(f"  arXiv API lookup: {arxiv_id}...")
        url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            namespace = {'atom': 'http://www.w3.org/2005/Atom'}
            entry = root.find('atom:entry', namespace)
            
            if entry is not None:
                # ArXiv returns an "entry" even for invalid IDs sometimes, check if it has a title
                title_elem = entry.find('atom:title', namespace)
                if title_elem is not None and title_elem.text:
                    work_title = title_elem.text.strip().replace('\n', ' ')
                    
                    # Extract authors
                    author_elems = entry.findall('atom:author', namespace)
                    author_names = []
                    for auth in author_elems[:3]:
                        name_elem = auth.find('atom:name', namespace)
                        if name_elem is not None:
                            author_names.append(name_elem.text)
                    
                    authors = ', '.join(author_names) if author_names else 'N/A'
                    if len(author_elems) > 3:
                        authors += ', et al.'
                        
                    # Published year
                    published = entry.find('atom:published', namespace)
                    pub_year = published.text[:4] if published is not None else 'N/A'
                    
                    print(f"  ✓ Found in arXiv: {work_title[:60]}...")
                    
                    return {
                        "status": "found",
                        "source": "arXiv",
                        "title": work_title,
                        "author": authors,
                        "pub_year": pub_year,
                        "venue": "ArXiv",
                        "url": f"https://arxiv.org/abs/{arxiv_id}"
                    }
        
        return {"status": "not_found"}
    except Exception as e:
        print(f"  - arXiv API error: {str(e)[:50]}...")
        return {"status": "error", "message": str(e)}


def run_doi_search_cycle(doi):
    """
    Runs the tiered DOI lookup cycle (OpenAlex -> Crossref -> DataCite).
    """
    # Step 1: OpenAlex
    res = check_openalex_by_doi(doi)
    if res["status"] == "found":
        return res
        
    # Step 2: Crossref or DataCite
    if "zenodo" in doi.lower() or "10.5281" in doi:
        res = check_datacite(doi)
        if res["status"] == "found":
            return res
        res = check_crossref(doi)
        if res["status"] == "found":
            return res
    else:
        res = check_crossref(doi)
        if res["status"] == "found":
            return res
        res = check_datacite(doi)
        if res["status"] == "found":
            return res
            
    return {"status": "not_found"}

def check_reference(ref_text):
    """
    Checks a reference string with prioritizing DOI and healing broken DOIs.
    """
    if not ref_text or len(ref_text) < 10:
        return {"status": "skipped", "reason": "Too short"}

    print(f"\n[DEBUG] Checking reference...")
    print(f"  Original: {ref_text[:100]}...")

    # 0. Pre-extract title for similarity comparison later
    extracted_title = extract_title_from_reference(ref_text)

    # 1. Extract Initial DOI Info
    doi, end_pos = extract_doi_info(ref_text)
    
    result = None

    # 2. Try DOI matches if available
    if doi:
        print(f"  → Found Initial DOI: {doi}")
        
        # Initial Search Cycle
        result = run_doi_search_cycle(doi)
        
        # 3. DOI HEALING: If initial lookup fails, try to expand it
        if not result or result["status"] != "found":
            print("  → DOI not found. Attempting to heal/expand...")
            healed_doi, new_pos = heal_doi(doi, end_pos, ref_text)
            if healed_doi:
                result = run_doi_search_cycle(healed_doi)

    # 4. arXiv Support
    if not result or result["status"] != "found":
        arxiv_id = extract_arxiv_id(ref_text)
        if arxiv_id:
            print(f"  → Found arXiv ID: {arxiv_id}")
            result = check_arxiv(arxiv_id)

    # 5. Fallback to Title Search
    if not result or result["status"] != "found":
        print(f"  Extracted title: {extracted_title[:80]}...")
        print("  → Falling back to title search...")
        result = check_openalex(extracted_title)

    # Add similarity score if something was found
    if result and result.get("status") == "found":
        found_title = result.get("title", "")
        similarity = calculate_similarity(extracted_title, found_title)
        result["similarity"] = similarity
        print(f"  [DEBUG] Similarity score: {similarity:.2f}")

    return result

