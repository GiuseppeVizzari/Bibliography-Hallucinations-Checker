"""
app/checkers/config.py

Centralised configuration for the checker pipeline.
Thresholds are defined here once and imported everywhere they are needed.
"""
import time

# --- Similarity thresholds ---

RELEVANCE_THRESHOLD = 0.50       # Pre-acceptance filter for OpenAlex title search
WEB_FALLBACK_TRIGGER = 0.60      # OpenAlex → web search fallback gate
TITLE_SIMILARITY_THRESHOLD = 0.75  # Web search page-verification threshold

# --- Web fallback ranking boosts ---

WEB_BOOST_SNIPPET_CONTAINS = 0.80   # Title found in snippet
WEB_BOOST_TITLE_OVERLAP = 0.85      # Result title overlaps target title
WEB_BOOST_LENGTH_MATCH = 0.90       # Very similar-length titles

# --- URL checker ---

URL_REJECT_FLOOR = 0.20       # Minimum similarity floor for keyword-overlap fallback
URL_KEYWORD_OVERLAP_MIN = 3   # Minimum overlapping words to accept despite low similarity

# --- DBLP ---

DBLP_FOUND_THRESHOLD = 0.60   # Similarity to return "found" from DBLP
DBLP_CANDIDATE_THRESHOLD = 0.40  # Similarity to return "candidate" from DBLP
DBLP_MAX_RESULTS = 10         # Max hits per page
DBLP_MAX_PAGES = 2            # Max pages to paginate
DBLP_MIN_DELAY = 1.0          # Minimum seconds between DBLP API requests (polite pool)

# --- Pipeline ---

MAX_WORKERS = 4               # ThreadPoolExecutor workers for parallel ref checking
ARXIV_MIN_DELAY = 3.0         # Minimum seconds between arXiv API requests (their rate limit)


def execute_with_retry(func, max_retries=3, *args, **kwargs):
    """Execute *func* with exponential backoff on 429 / rate-limit errors.

    Works with any callable that may raise an exception whose string
    representation contains ``429`` or ``too many requests``.
    """
    import logging
    logger = logging.getLogger(__name__)
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            err_msg = str(e).lower()
            if "429" in err_msg or "too many requests" in err_msg:
                wait = (2 ** attempt) + 1
                logger.debug(
                    f"  Rate-limited. Retrying in {wait}s... (attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(wait)
            else:
                raise
    # Final attempt after retries exhausted
    return func(*args, **kwargs)
