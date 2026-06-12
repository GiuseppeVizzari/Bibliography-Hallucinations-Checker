"""
app/checkers/backends/url_checker.py

URL checker backend — downloads a web page or PDF from a URL in the reference,
extracts title and other metadata, and validates it against the reference.
"""
import re
import html
import requests
import urllib3
import fitz  # PyMuPDF
from typing import Optional
from ..normalizer import calculate_similarity, RELEVANCE_THRESHOLD

# Disable SSL warning for verify=False requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def extract_url(ref_text: str) -> Optional[str]:
    """Extracts a URL from a reference string."""
    # Match standard http/https URLs
    match = re.search(r'https?://[^\s,)]+', ref_text)
    if match:
        url = match.group(0).rstrip('.,;)]')
        # Skip DOIs and arXiv URLs since they are handled by their own backends
        if "doi.org" in url or "arxiv.org" in url:
            return None
        return url
    return None

def lookup_by_url(url: str, reference_title: str) -> dict:
    """
    Downloads the resource at the URL, extracts its title and metadata,
    and returns a standard result dict if it matches the reference title.
    """
    try:
        print(f"  URL resource lookup: {url}...")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        # Fetch with a timeout of 10 seconds to avoid hanging the app
        response = requests.get(url, headers=headers, timeout=10, verify=False)
        response.raise_for_status()
        
        content_type = response.headers.get("Content-Type", "").lower()
        title = "N/A"
        author = "N/A"
        pub_year = "N/A"
        venue = "N/A"
        
        if "application/pdf" in content_type or url.lower().endswith(".pdf"):
            print("  → Parsing as PDF...")
            doc = fitz.open(stream=response.content, filetype="pdf")
            
            # Try to get metadata
            title = doc.metadata.get("title", "") if doc.metadata else ""
            
            # Fallback for empty/invalid titles
            if not title or len(title.strip()) < 10 or "untitled" in title.lower() or "microsoft word" in title.lower():
                if len(doc) > 0:
                    first_page = doc[0]
                    blocks = first_page.get_text("blocks")
                    text_blocks = [b for b in blocks if b[6] == 0 and b[4].strip()]
                    if text_blocks:
                        for b in text_blocks[:3]:
                            txt = b[4].strip().replace('\n', ' ')
                            if 15 < len(txt) < 150:
                                title = txt
                                break
                                
            # Extract other metadata
            if doc.metadata:
                author = doc.metadata.get("author", "N/A") or "N/A"
                creation_date = doc.metadata.get("creationDate", "")
                if creation_date:
                    year_match = re.search(r'\b(19|20)\d{2}\b', creation_date)
                    if year_match:
                        pub_year = year_match.group(0)
                if doc.metadata.get("producer") and "adobe" not in doc.metadata.get("producer").lower():
                    venue = doc.metadata.get("producer", "N/A") or "N/A"
            doc.close()
            
        else:
            print("  → Parsing as HTML...")
            html_text = response.text
            
            # Extract HTML title
            title_match = re.search(r'<title[^>]*>(.*?)</title>', html_text, re.IGNORECASE | re.DOTALL)
            if title_match:
                title = html.unescape(title_match.group(1).strip())
                # Clean up multiple whitespaces/newlines
                title = re.sub(r'\s+', ' ', title)
                
            # Extract meta tags for other metadata
            meta_tags = re.findall(r'<meta\s+([^>]+)>', html_text, re.IGNORECASE)
            authors = []
            
            for tag in meta_tags:
                attrs = dict(re.findall(r'(\w+(?:\.\w+)?|property|name|content)\s*=\s*["\']([^"\']*)["\']', tag, re.IGNORECASE))
                if not attrs:
                    continue
                attrs = {k.lower(): v for k, v in attrs.items()}
                name = attrs.get('name') or attrs.get('property')
                content = attrs.get('content')
                
                if name and content:
                    name_lower = name.lower()
                    content_val = html.unescape(content.strip())
                    
                    if name_lower in ('author', 'citation_author', 'dc.creator', 'dcterms.creator'):
                        authors.append(content_val)
                    elif name_lower in ('citation_publication_date', 'citation_date', 'dc.date', 'dcterms.date', 'pubdate'):
                        year_match = re.search(r'\b(19|20)\d{2}\b', content_val)
                        if year_match:
                            pub_year = year_match.group(0)
                        else:
                            pub_year = content_val
                    elif name_lower in ('citation_journal_title', 'citation_conference_title', 'dc.relation.ispartof', 'citation_publisher'):
                        venue = content_val
                        
            if authors:
                author = ", ".join(authors[:3]) + (", et al." if len(authors) > 3 else "")
                
        # Clean title
        title = title.strip()
        if not title or title == "N/A":
            print("  - Could not extract a valid title from the URL")
            return {"status": "not_found"}
            
        # Relevance check
        similarity = calculate_similarity(reference_title, title)
        if similarity < RELEVANCE_THRESHOLD:
            print(f"  - URL check: top result rejected (similarity {similarity:.2f} < {RELEVANCE_THRESHOLD}): '{title[:60]}'")
            return {"status": "not_found"}
            
        print(f"  ✓ Found URL resource (similarity {similarity:.2f}): {title[:60]}...")
        return {
            "status": "found",
            "source": "URL Resource",
            "title": title,
            "author": author,
            "pub_year": pub_year,
            "venue": venue,
            "url": url,
        }
        
    except Exception as e:
        err = str(e)
        print(f"  - URL lookup error: {err[:60]}...")
        return {"status": "error", "message": err}
