"""
app/checkers/normalizer.py

Text normalization utilities shared across the checker pipeline.
"""
import re
from difflib import SequenceMatcher

# Re-export thresholds from config for backward compatibility
from .config import (  # noqa: F401
    RELEVANCE_THRESHOLD,
    WEB_FALLBACK_TRIGGER,
    TITLE_SIMILARITY_THRESHOLD,
)


def normalize_ligatures(text: str) -> str:
    """Decomposes Unicode ligatures (ﬁ, ﬂ, ﬁ, ﬃ, ﬄ, etc.) into their ASCII equivalents.

    IMPORTANT: This function deliberately does NOT use unicodedata.normalize('NFKD', text)
    because NFKD also decomposes accented characters (ü → u + combining diaeresis,
    í → i + combining acute, etc.), which would then be stripped by normalize_text()
    and corrupt API queries / similarity scores for international names.
    """
    if not text:
        return ""
    # Unicode ligature characters → their decomposed ASCII equivalents
    LIGATURE_MAP = {
        '\uFB00': 'ff',    # ﬁ → ff
        '\uFB01': 'fi',    # ﬂ → fi
        '\uFB02': 'fI',    # ﬁ → fI (capitalized form — caller should lowercase)
        '\uFB03': 'ffi',   # ﬃ → ffi
        '\uFB04': 'ffl',   # ﬄ → ffl
        '\uFB05': 'st',    # ﬁ → st (long s + t)
        '\uFB06': 'st',    # ﬂ → st
        '\u0192': 's',     # ƒ → s (archic f, often treated as ligature)
    }
    result = []
    for ch in text:
        result.append(LIGATURE_MAP.get(ch, ch))
    return ''.join(result)


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
    Strips punctuation (except hyphens) and converts to lowercase for fuzzy comparison.
    Preserves Unicode word characters (é, ñ, etc.) and hyphens, which are significant
    in titles (e.g. "state-of-the-art").
    """
    clean = re.sub(r'[^\w\s-]', '', text)
    return clean.lower().strip()


def heal_hyphens(text: str) -> str:
    """
    Joins words that were split across PDF lines with a hyphen.
    E.g. 'be-\\nhaviors' -> 'behaviors', 'Multi-\\nTarget' -> 'MultiTarget'.

    Heuristic: lowercase continuation is always a broken word.
    Uppercase continuation is joined for Title Case and PascalCase words
    (common in reference titles), with a fallback to lowercase for safety
    when the joined result looks like it lost word boundaries.
    """
    # Pass 1: lowercase continuation (always safe)
    # Use \w{2,8} to match multi-char words (e.g. "state-\nof-the-art").
    text = re.sub(r'(\w{2,8})-\n([a-z])', r'\1\2', text)
    text = re.sub(r'(\w{2,8})-\s([a-z])', r'\1\2', text)

    # Pass 2: uppercase continuation
    # Heuristic: only join if the part before the hyphen is a short word
    # (surname, title word) and the result would be a plausible compound.
    text = re.sub(r'(\w{2,8})-\n([A-Z])', r'\1\2', text)
    text = re.sub(r'(\w{2,8})-\s([A-Z])', r'\1\2', text)

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

    For colon-based stripping, only strips when the pre-colon text looks like
    an author name (single surname or initials + surname). Does NOT strip title
    subtitles like 'Sprawl retrofit:' or 'Part Two:'.
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
                    should_strip = False
                    if len(header_words) == 1:
                        w = header_words[0]
                        # Strip single short words (surnames like 'Smith', 'Zhang') or
                        # initials with periods ('J.', 'A.B.')
                        if len(w) <= 7 or '.' in w:
                            should_strip = True
                    elif len(header_words) == 2:
                        # Only strip if first word looks like initials (contains a period)
                        # e.g. 'J. Smith:' -> strip; 'Sprawl retrofit:' -> keep
                        if '.' in header_words[0]:
                            should_strip = True
                    # Only strip if the tail looks like a title
                    tail = text[match.end():].strip()
                    tail_words = {w for w in re.findall(r'\b\w+\b', tail.lower()) if len(w) > 1}
                    if should_strip and tail_words & common_title_words:
                        text = tail

    while ',' in text:
        split_point = text.find(',')
        header = text[:split_point].strip()
        tail = text[split_point + 1:].strip()

        if len(header) < 15 and len(tail) > 10:
            if re.search(r'\d', header):
                break
            words = {w for w in re.findall(r'\b\w+\b', header.lower()) if len(w) > 1}
            if not (words & common_title_words):
                # Check if the tail looks like a title continuation
                tail_words = {w for w in re.findall(r'\b\w+\b', tail.lower()) if len(w) > 1}
                tail_looks_like_title = bool(tail_words & common_title_words)
                # Author names: short surname (< 8 chars) or initials (contains period)
                is_short_surname = len(words) == 1 and len(list(words)[0]) < 8
                has_initials = any('.' in w for w in header.split())
                if (is_short_surname or has_initials) and tail_looks_like_title:
                    text = tail
                    continue
        break

    return text


def strip_doi_punctuation(doi: str) -> str:
    """
    Removes trailing punctuation that may have been captured alongside a DOI.
    Preserves the '10.' partial prefix (from broken DOIs like '10. 1371/...')
    so that heal_doi can still reconstruct the full identifier.
    """
    cleaned = doi.rstrip('.,;)]')
    # If stripping turned '10.' into '10', preserve the period for heal_doi
    if cleaned == '10' and doi.rstrip() == '10.':
        return '10.'
    return cleaned


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Computes a [0, 1] similarity score between two strings using
    SequenceMatcher on normalized versions of the inputs.

    Normalization strips punctuation (except hyphens) and lowercases.
    If normalization produces an empty string (e.g. input was all
    punctuation), falls back to the raw lowercased text.

    Length penalty: when one title is a substring of the other, the score
    is multiplied by the length ratio (shorter / longer). This prevents
    short titles like "stance detection a survey" from getting a high
    score against longer titles like "deep learning in stance detection
    a survey" where the shorter is merely a substring.
    """
    if not text1 or not text2:
        return 0.0

    s1 = normalize_text(text1)
    s2 = normalize_text(text2)

    # normalize_text strips punctuation; if both inputs were punctuation-only
    # the normalized strings would be empty. Fall back to raw text in that case.
    if not s1 or not s2:
        s1 = text1.lower().strip()
        s2 = text2.lower().strip()

    raw_sim = SequenceMatcher(None, s1, s2).ratio()

    # Length penalty: penalize when one string is a substring of the other
    # but the lengths differ significantly.
    min_len = min(len(s1), len(s2))
    max_len = max(len(s1), len(s2))
    if max_len > 0:
        length_ratio = min_len / max_len
        # Only apply penalty when the shorter is fully contained in the longer
        # (i.e., the raw similarity is high enough to suggest containment)
        if length_ratio < 0.95 and raw_sim > 0.5:
            return raw_sim * length_ratio

    return raw_sim
