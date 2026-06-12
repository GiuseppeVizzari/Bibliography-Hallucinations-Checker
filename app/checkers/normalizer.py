"""
app/checkers/normalizer.py

Text normalization utilities shared across the checker pipeline.
"""
import re
import unicodedata
from difflib import SequenceMatcher


def normalize_ligatures(text: str) -> str:
    """Decomposes Unicode ligatures like 'ﬁ' into 'fi', 'ﬂ' into 'fl', etc."""
    if not text:
        return ""
    return unicodedata.normalize('NFKD', text)


def normalize_quotes(text: str) -> str:
    """
    Replaces typographic/curly quotes and apostrophes with their plain
    ASCII equivalents so API queries are not broken by fancy Unicode.
    """
    return (
        text
        .replace('\u2019', "'")   # right single quotation mark → '
        .replace('\u2018', "'")   # left single quotation mark  → '
        .replace('\u201c', '"')   # left double quotation mark  → "
        .replace('\u201d', '"')   # right double quotation mark → "
    )


def normalize_text(text: str) -> str:
    """
    Strips punctuation and converts to lowercase for fuzzy comparison.
    """
    clean = re.sub(r'[^\w\s]', '', text)
    return clean.lower().strip()


def heal_hyphens(text: str) -> str:
    """
    Joins words that were split across PDF lines with a hyphen.
    E.g. 'be-\\nhaviors' -> 'behaviors', 'multi-\\ntarget' -> 'multi-target'.

    Heuristic: if the part after the hyphen starts with a lowercase letter,
    it is a broken word; uppercase continuation suggests a real hyphen.
    """
    text = re.sub(r'(\w)-\n([a-z])', r'\1\2', text)
    text = re.sub(r'(\w)-\s([a-z])', r'\1\2', text)
    return text


def strip_venue_suffix(title: str) -> str:
    """
    Removes trailing venue/proceedings information from a title.
    """
    cleaned = re.sub(r'\s+[Ii]n:\s+.*$', '', title, flags=re.DOTALL)
    cleaned = re.sub(r'^[\s:;]+', '', cleaned)
    return cleaned.rstrip('.,; ') or title


def strip_author_header(text: str, common_title_words: set) -> str:
    """
    Cleans up a title that might still have a leftover author name at the start.
    E.g. 'Zhang, Crowd evacuation...' -> 'Crowd evacuation...'
    """
    if ':' in text:
        match = re.search(r'^[^:]{1,100}:\s*', text)
        if match:
            header = match.group(0).lower()
            words = {w for w in re.findall(r'\b\w+\b', header) if len(w) > 1}
            if not (words & common_title_words):
                header_full = match.group(0)
                header_words = re.findall(r'\b\w+\b', header_full)
                if len(header_words) <= 2:
                    should_strip = True
                    if len(header_words) == 1 and len(header_words[0]) > 4 and '.' not in header_words[0]:
                        should_strip = False
                    if should_strip:
                        text = text[match.end():].strip()

    while ',' in text:
        split_point = text.find(',')
        header = text[:split_point].strip()
        tail = text[split_point + 1:].strip()

        if len(header) < 15 and len(tail) > 10:
            if re.search(r'\d', header):
                break
            words = {w for w in re.findall(r'\b\w+\b', header.lower()) if len(w) > 1}
            if not (words & common_title_words):
                text = tail
                continue
        break

    return text


RELEVANCE_THRESHOLD = 0.35


def strip_doi_punctuation(doi: str) -> str:
    """Removes trailing punctuation that may have been captured alongside a DOI."""
    return doi.rstrip('.,;)]')


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Computes a [0, 1] similarity score between two strings using
    SequenceMatcher on normalized versions of the inputs.
    """
    if not text1 or not text2:
        return 0.0

    s1 = normalize_text(text1)
    s2 = normalize_text(text2)

    if not s1 or not s2:
        s1 = text1.lower().strip()
        s2 = text2.lower().strip()

    return SequenceMatcher(None, s1, s2).ratio()
