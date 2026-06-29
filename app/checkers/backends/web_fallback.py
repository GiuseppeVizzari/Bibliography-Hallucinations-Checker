"""
app/checkers/backends/web_fallback.py

Fallback mechanism that uses a web search engine to find references
that are not indexed in academic databases (e.g. datasets, reports, news).
"""

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

from ..normalizer import calculate_similarity

# Confidence threshold to mark a web result as 'found'
TITLE_SIMILARITY_THRESHOLD = 0.75


def _verify_page(url: str, target_title: str) -> bool:
    """
    Fetches the page and checks if the title is present in the <h1> or <title> tags.
    """
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return False

        soup = BeautifulSoup(response.text, "html.parser")

        # 1. Check <title> tag
        page_title = soup.title.string.strip() if soup.title else ""
        if (
            page_title
            and calculate_similarity(target_title, page_title)
            > TITLE_SIMILARITY_THRESHOLD
        ):
            return True

        # 2. Check <h1> tags
        for h1 in soup.find_all("h1"):
            h1_text = h1.get_text().strip()
            if (
                h1_text
                and calculate_similarity(target_title, h1_text)
                > TITLE_SIMILARITY_THRESHOLD
            ):
                return True

        return False
    except Exception:
        return False


def lookup_by_title(title: str, full_ref: str = "") -> dict:
    """
    Searches the web for the given title.
    If found and verified, returns a result dict.
    """
    if not title:
        return {"status": "not_found"}

    # Construct search query (quoted title for precision)
    query = f'"{title}"'

    try:
        with DDGS() as ddgs:
            # Try quoted search first (high precision)
            results = list(ddgs.text(query, max_results=3))

            if not results:
                # Fallback to unquoted search (higher recall)
                unquoted_query = title
                results = list(ddgs.text(unquoted_query, max_results=3))

            for res in results:
                url = res.get("href", "")
                snippet = res.get("body", "")

                # Basic snippet check to avoid unnecessary requests
                if target_title_in_snippet(title, snippet):
                    # Thorough verification by visiting the page
                    if _verify_page(url, title):
                        return {
                            "status": "found",
                            "source": "Web Search",
                            "title": title,
                            "url": url,
                            "venue": "Web Page",
                            "author": "Unknown",
                            "pub_year": "Unknown",
                        }
    except Exception as e:
        print(f"  [DEBUG] Web search error: {e}")
    except Exception as e:
        print(f"  [DEBUG] Web search error: {e}")
    except Exception as e:
        print(f"  [DEBUG] Web search error: {e}")
        print(f"  [DEBUG] Web search error: {e}")
    except Exception as e:
        print(f"  [DEBUG] Web search error: {e}")
        print(f"  [DEBUG] Web search error: {e}")
        print(f"  [DEBUG] Web search error: {e}")

    return {"status": "not_found"}


def target_title_in_snippet(title: str, snippet: str) -> bool:
    """Returns True if the target title is reasonably present in the snippet."""
    if not snippet:
        return False

    # Normalize both for a loose match
    t_norm = title.lower().strip()
    s_norm = snippet.lower()

    # Check if title is in snippet (or a large part of it)
    if t_norm in s_norm:
        return True

    # Fallback: check if most words of the title are present
    title_words = [w for w in t_norm.split() if len(w) > 3]
    if not title_words:
        return False

    matches = sum(1 for w in title_words if w in s_norm)
    return (matches / len(title_words)) > 0.6
