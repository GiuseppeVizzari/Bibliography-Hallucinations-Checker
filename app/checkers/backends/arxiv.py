"""
app/checkers/backends/arxiv.py

arXiv API backend — lookup by arXiv ID via the official Atom feed API.
"""

import logging
import requests
import threading
import xml.etree.ElementTree as ET
from ..config import execute_with_retry, ARXIV_MIN_DELAY
from .base import BackendService

logger = logging.getLogger(__name__)

_API_URL = "https://export.arxiv.org/api/query"
_NS = {'atom': 'http://www.w3.org/2005/Atom'}

# Thread-safe rate-limit gate for arXiv (max 1 request per 3 seconds)
_arxiv_lock = threading.Lock()
_arxiv_last_request = 0.0


def _arxiv_rate_limit():
    """Enforce arXiv's rate limit: max 10 requests per 3 seconds."""
    import time
    with _arxiv_lock:
        global _arxiv_last_request
        elapsed = time.time() - _arxiv_last_request
        if elapsed < ARXIV_MIN_DELAY:
            time.sleep(ARXIV_MIN_DELAY - elapsed)
        _arxiv_last_request = time.time()


class ArxivBackend(BackendService):
    """arXiv API backend implementation."""

    def lookup_by_doi(self, doi: str) -> dict:
        """Lookup by DOI (not used for arXiv)."""
        # For arXiv, we lookup by ID, not DOI
        return {"status": "not_found"}

    def lookup_by_id(self, arxiv_id: str) -> dict:
        """Fetch a paper from the arXiv API by its ID (e.g. '2412.11814')."""
        try:
            logger.debug(f"  arXiv API lookup: {arxiv_id}...")
            _arxiv_rate_limit()

            def _fetch():
                return requests.get(_API_URL, params={"id_list": arxiv_id}, timeout=10)

            response = execute_with_retry(_fetch)

            if response.status_code != 200:
                return {"status": "not_found"}

            root = ET.fromstring(response.content)
            entry = root.find('atom:entry', _NS)

            if entry is None:
                return {"status": "not_found"}

            title_elem = entry.find('atom:title', _NS)
            if title_elem is None or not title_elem.text:
                return {"status": "not_found"}

            work_title = title_elem.text.strip().replace('\n', ' ')

            # Authors (up to 3 + "et al.")
            author_elems = entry.findall('atom:author', _NS)
            names = []
            for auth in author_elems[:3]:
                name_elem = auth.find('atom:name', _NS)
                if name_elem is not None:
                    names.append(name_elem.text)
            authors = ', '.join(names) if names else 'N/A'
            if len(author_elems) > 3:
                authors += ', et al.'

            # Publication year
            published = entry.find('atom:published', _NS)
            pub_year = published.text[:4] if published is not None else 'N/A'

            logger.debug(f"  ✓ Found in arXiv: {work_title[:60]}...")

            return {
                "status": "found",
                "source": "arXiv",
                "title": work_title,
                "author": authors,
                "pub_year": pub_year,
                "venue": "arXiv",
                "url": f"https://arxiv.org/abs/{arxiv_id}",
            }

        except Exception as e:
            logger.debug(f"  - arXiv API error: {str(e)[:50]}...")
            return {"status": "error", "message": str(e)}

    def lookup_by_title(self, title: str, full_ref: str = "") -> dict:
        """Title search not implemented for arXiv."""
        return {"status": "not_found"}