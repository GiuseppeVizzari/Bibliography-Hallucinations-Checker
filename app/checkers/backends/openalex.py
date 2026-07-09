"""
app/checkers/backends/openalex.py

OpenAlex API backend — supports DOI lookup and full-text title search.
"""

import logging
import os
import re
import time
from typing import Any, Callable, Optional

import pyalex
from dotenv import load_dotenv
from pyalex import Works

from ..normalizer import (
    RELEVANCE_THRESHOLD,
    calculate_similarity,
    normalize_ligatures,
    normalize_quotes,
    strip_doi_punctuation,
)
from .base import BackendService

logger = logging.getLogger(__name__)

_configured = False


def _ensure_config():
    """Lazy-initialise pyalex config on first API call."""
    global _configured
    if not _configured:
        load_dotenv()
        pyalex.config.email = os.getenv("OPENALEX_EMAIL")
        pyalex.config.api_key = os.getenv("OPENALEX_API_KEY")
        _configured = True


def _execute_with_retry(func: Callable, *args, **kwargs) -> Any:
    """Executes a pyalex function with exponential backoff for 429 errors."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            err_msg = str(e).lower()
            if "429" in err_msg or "too many requests" in err_msg:
                wait_time = (2**attempt) + 1
                logger.debug(
                    f"  [DEBUG] OpenAlex Rate Limit (429). Retrying in {wait_time}s... (Attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(wait_time)
            else:
                raise e
    # Final attempt after retries
    return func(*args, **kwargs)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _process_work(work: dict) -> Optional[dict]:
    """Convert a raw OpenAlex work object into the standard result dict."""
    if work is None:
        return None

    work_title = work.get("title", "N/A")

    # Authors (up to 3 + "et al.")
    authors = "N/A"
    authorships = work.get("authorships", [])
    if authorships:
        names = []
        for auth in authorships[:3]:
            if auth and isinstance(auth, dict):
                author = auth.get("author")
                if author and isinstance(author, dict):
                    name = author.get("display_name", "")
                    if name:
                        names.append(name)
        if names:
            authors = ", ".join(names)
            if len(authorships) > 3:
                authors += ", et al."

    # Publication year
    pub_year = work.get("publication_year", "N/A")

    # Venue
    venue = "N/A"
    loc = work.get("primary_location")
    if loc and isinstance(loc, dict):
        source = loc.get("source")
        if source and isinstance(source, dict):
            venue = source.get("display_name", "N/A")

    # URL — prefer DOI, fall back to OpenAlex ID
    doi = work.get("doi")
    url = doi if doi else work.get("id", "#")

    return {
        "status": "found",
        "source": "OpenAlex",
        "title": work_title,
        "author": authors,
        "pub_year": str(pub_year) if pub_year != "N/A" else "N/A",
        "venue": venue,
        "url": url,
    }


# ---------------------------------------------------------------------------
# OpenAlexBackend Class
# ---------------------------------------------------------------------------


class OpenAlexBackend(BackendService):
    """OpenAlex API backend implementation."""

    def lookup_by_doi(self, doi: str) -> dict:
        """Fetch a work from OpenAlex by its DOI."""
        _ensure_config()
        try:
            doi_query = strip_doi_punctuation(doi)
            logger.debug(f"  OpenAlex DOI lookup: {doi_query}...")
            work = _execute_with_retry(lambda: Works()[doi_query])
            if work:
                res = _process_work(work)
                if res:
                    logger.debug(f"  ✓ Found in OpenAlex (DOI): {res['title'][:60]}...")
                    return res
            return {"status": "not_found"}
        except Exception as e:
            err = str(e)
            if "404" in err:
                return {"status": "not_found"}
            logger.debug(f"  - OpenAlex DOI error: {err[:50]}...")
            return {"status": "error", "message": err}

    def lookup_by_id(self, identifier: str) -> dict:
        """Lookup by identifier (not used for OpenAlex)."""
        # For OpenAlex, DOI lookups are preferred
        return self.lookup_by_doi(identifier)

    def lookup_by_title(self, title: str, full_ref: str = "") -> dict:
        """Search OpenAlex by title string (full-text search)."""
        _ensure_config()
        try:
            # Normalize typographic quotes and ligatures
            clean = normalize_quotes(title)
            clean = normalize_ligatures(clean)
            # Remove colons, semicolons, and common trailing punctuation for the search query
            query = re.sub(r"[:;.,!?]", " ", clean).strip()

            logger.debug(f"  OpenAlex title search: {query[:70]}...")
            results = _execute_with_retry(lambda: Works().search(query).get())

            if not results:
                # Fallback: Search with only the first ~8 words (often more robust for long titles)
                words = query.split()
                if len(words) > 10:
                    short_query = " ".join(words[:8])
                    logger.debug(
                        f"  → No results for full title. Trying fallback: {short_query}..."
                    )
                    results = _execute_with_retry(lambda: Works().search(short_query).get())

            if results:
                res = _process_work(results[0])
                if res:
                    # Pre-acceptance relevance gate: reject obviously wrong matches.
                    # OpenAlex always returns *something* even when the paper isn't indexed.
                    # If the returned title is too dissimilar from our query, treat as not found.
                    relevance = calculate_similarity(title, res["title"])
                    if relevance < RELEVANCE_THRESHOLD:
                        logger.debug(
                            f"  - OpenAlex title search: top result rejected (relevance {relevance:.2f} < {RELEVANCE_THRESHOLD}): '{res['title'][:60]}'"
                        )
                        return {"status": "not_found"}
                    logger.debug(
                        f"  ✓ Found in OpenAlex (title, relevance {relevance:.2f}): {res['title'][:60]}..."
                    )
                    return res

            logger.debug("  - Not found in OpenAlex by title")
            return {"status": "not_found"}
        except Exception as e:
            err = str(e)
            logger.debug(f"  - OpenAlex title search error: {err[:50]}...")
            return {"status": "error", "message": err}