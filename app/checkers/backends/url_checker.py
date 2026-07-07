"""
app/checkers/backends/url_checker.py

URL checker backend — downloads a web page or PDF from a URL in the reference,
extracts title and other metadata, and validates it against the reference.
"""

import html
import logging
import re
import requests
import urllib3
import fitz  # PyMuPDF
from typing import Optional
from ..normalizer import calculate_similarity, RELEVANCE_THRESHOLD
from .base import BackendService

logger = logging.getLogger(__name__)

# Disable SSL warning for verify=False requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class URLCheckerBackend(BackendService):
    """URL checker backend implementation."""

    def lookup_by_doi(self, doi: str) -> dict:
        """Lookup by DOI (not used for URL checker)."""
        return {"status": "not_found"}

    def lookup_by_id(self, identifier: str) -> dict:
        """Lookup by identifier (not used for URL checker)."""
        return {"status": "not_found"}

    def lookup_by_title(self, title: str) -> dict:
        """Title search not implemented for URL checker."""
        return {"status": "not_found"}

    def extract_url(self, ref_text: str) -> Optional[str]:
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

    def _fetch_page(self, url: str, headers: dict) -> requests.Response:
        """Fetch a URL, following at most one HTML meta-refresh redirect."""
        response = requests.get(url, headers=headers, timeout=10, verify=False)
        response.raise_for_status()

        # Follow HTML meta-refresh redirects (e.g. <meta http-equiv="refresh" ...>)
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" in content_type:
            refresh_match = re.search(
                r'<meta\s+[^>]*http-equiv\s*=\s*["\']?refresh["\']?[^>]*content\s*=\s*["\']?\d+;\s*url\s*=\s*([^"\'>\s]+)',
                response.text, re.IGNORECASE
            )
            if not refresh_match:
                refresh_match = re.search(
                    r'<meta\s+[^>]*content\s*=\s*["\']?\d+;\s*url\s*=\s*([^"\'>\s]+)["\']?',
                    response.text, re.IGNORECASE
                )
                # Only use this broader pattern if http-equiv="refresh" is present
                if refresh_match and 'http-equiv' not in response.text.lower().split('refresh')[0][-30:]:
                    pass

            if refresh_match:
                redirect_url = refresh_match.group(1)
                if not redirect_url.startswith("http"):
                    redirect_url = url.rstrip("/") + "/" + redirect_url.lstrip("./")
                logger.debug(f"  → Following meta-refresh to: {redirect_url}")
                response = requests.get(redirect_url, headers=headers, timeout=10, verify=False)
                response.raise_for_status()

        return response

    def lookup_by_url(self, url: str, reference_title: str) -> dict:
        """
        Downloads the resource at the URL, extracts its title and metadata,
        and returns a standard result dict if it matches the reference title.
        """
        try:
            logger.debug(f"  URL resource lookup: {url}...")
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            # Fetch with meta-refresh redirect following
            response = self._fetch_page(url, headers)

            content_type = response.headers.get("Content-Type", "").lower()
            title = "N/A"
            author = "N/A"
            pub_year = "N/A"
            venue = "N/A"

            if "application/pdf" in content_type or url.lower().endswith(".pdf"):
                logger.debug("  → Parsing as PDF...")
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
                logger.debug("  → Parsing as HTML...")
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
                logger.debug("  - Could not extract a valid title from the URL")
                return {"status": "not_found"}

            # Relevance check: similarity + keyword overlap fallback
            similarity = calculate_similarity(reference_title, title)
            if similarity < RELEVANCE_THRESHOLD:
                # Fallback: require at least 3 overlapping words AND a minimum similarity floor
                # This prevents accepting generic portal pages (e.g. "Open Data BCN") for
                # specific dataset titles (e.g. "Disposable household income per capita...")
                ref_words = {w.lower() for w in re.findall(r'\b[A-Za-z]{3,}\b', reference_title)}
                page_words = {w.lower() for w in re.findall(r'\b[A-Za-z]{3,}\b', title)}
                overlap = ref_words & page_words
                if len(overlap) >= 3 and similarity >= 0.20:
                    logger.debug(f"  [DEBUG] URL check: keyword overlap found ({len(overlap)} words) despite low similarity ({similarity:.2f})")
                else:
                    logger.debug(f"  - URL check: rejected (similarity {similarity:.2f} < {RELEVANCE_THRESHOLD}, overlap {len(overlap)} words): '{title[:60]}'")
                    return {"status": "not_found"}

            logger.debug(f"  ✓ Found URL resource (similarity {similarity:.2f}): {title[:60]}...")
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
            logger.debug(f"  - URL lookup error: {err[:60]}...")
            return {"status": "error", "message": err}