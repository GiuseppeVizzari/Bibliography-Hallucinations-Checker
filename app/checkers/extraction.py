"""
app/checkers/extraction.py

Helpers to extract structured identifiers and titles from raw reference strings.
"""
import re
from .normalizer import normalize_ligatures, strip_venue_suffix, strip_author_header


COMMON_TITLE_WORDS = {
    'the', 'a', 'an', 'and', 'for', 'in', 'on', 'with', 'to', 'of', 'at', 'by',
    'from', 'using', 'study', 'survey', 'review', 'analysis', 'framework',
    'model', 'method', 'approach', 'system', 'design', 'evaluation',
    'results', 'simulation', 'experimental', 'performance',
    'impact', 'influence', 'theory', 'detection', 'learning', 'optimization',
    'improved', 'based', 'between', 'towards', 'through', 'across'
}

# Compiled regexes for cleanup
_DOI_URL_RE = re.compile(r'https?://(?:dx\.)?doi\.org/[-._;()/:a-zA-Z0-9]+')
_BARE_DOI_RE = re.compile(r'\b10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+\b')
_URL_RE = re.compile(r'https?://\S+|//[a-zA-Z][-./\w]*')
_ARXIV_URL_RE = re.compile(r'https?://arxiv\.org/\S+')
_VENUE_YEAR_RE = re.compile(r'\b(?:19|20)\d{2}\b')


def _is_numeric_garbage(candidate: str) -> bool:
    """Returns True if the candidate is mostly numeric — a page number, not a title."""
    stripped = candidate.lstrip()
    if not stripped:
        return True
    # Count alphanumeric tokens; if > 50% are purely digits, reject
    tokens = re.findall(r'[A-Za-z0-9]+', stripped)
    if not tokens:
        return True
    digit_count = sum(1 for t in tokens if t.isdigit())
    return (digit_count / len(tokens)) > 0.50


def _is_author_list(part: str) -> bool:
    """Returns True if a segment looks like a list of author names, not a title."""
    if part.count(',') < 2:
        return False
    if ':' in part or 'et al' in part.lower():
        return False
    words = re.findall(r'\b[A-Za-z]+\b', part)
    if len(words) < 4:
        return False
    common = {w.lower() for w in words if w.lower() in COMMON_TITLE_WORDS}
    connecting = {'and', 'in', 'of', 'for', 'with', 'on', 'to', 'by', 'at'}
    if common - connecting:
        return False
    non_common = [w for w in words if w.lower() not in COMMON_TITLE_WORDS and len(w) > 1]
    if len(non_common) < 3:
        return False
    short_caps = sum(1 for w in non_common if w[0].isupper() and len(w) < 15)
    return (short_caps / len(non_common)) > 0.70


def _strip_trailing_venue(title: str) -> str:
    """Removes trailing venue/journal info after commas, iterating right-to-left."""
    result = title
    while True:
        last_comma = result.rfind(',')
        if last_comma == -1:
            return result
        after = result[last_comma + 1:].strip()
        if not after:
            result = result[:last_comma].strip()
            continue
        after_words = re.findall(r'\b[A-Za-z]+\b', after)
        # Rule 1: trailing text contains a year → strip
        if _VENUE_YEAR_RE.search(after):
            before = result[:last_comma].strip()
            if before:
                result = before
                continue
            return result
        # Rule 2: 1 short capitalized word, no common title words → venue abbrev
        if len(after_words) == 1 and len(after_words[0]) < 12:
            lower = after.lower()
            has_common = any(
                len(w) > 1 and w in COMMON_TITLE_WORDS
                for w in re.findall(r'\b\w+\b', lower)
            )
            if not has_common and after_words[0][0].isupper():
                before = result[:last_comma].strip()
                if before:
                    result = before
                    continue
                return result
        # Rule 3: 2-3 short capitalized words, no common title words → venue abbrev
        if 2 <= len(after_words) <= 3:
            lower = after.lower()
            has_common = any(
                len(w) > 1 and w in COMMON_TITLE_WORDS
                for w in re.findall(r'\b\w+\b', lower)
            )
            if not has_common:
                all_upper = all(w and w[0].isupper() for w in after_words)
                all_short = all(len(w) < 12 for w in after_words)
                if all_upper and all_short:
                    before = result[:last_comma].strip()
                    if before:
                        result = before
                        continue
                    return result
        break
    return result


def _clean_title(candidate: str) -> str:
    """Applies author-stripping, venue-stripping, and URL-stripping."""
    cleaned = strip_author_header(candidate, COMMON_TITLE_WORDS)
    cleaned = strip_venue_suffix(cleaned)
    cleaned = _strip_trailing_venue(cleaned)
    return _strip_trailing_url(cleaned)


def extract_title_from_reference(ref_text: str) -> str:
    """
    Attempts to extract the title from a reference string using advanced heuristics.

    Strategy (in order):
    1. Normalize Unicode ligatures (e.g. 'ﬁ' -> 'fi').
    2. Strip DOI URLs and bare DOIs that confuse extraction.
    3. Strip bracketed citation keys or simple numbered brackets.
    4. Text enclosed in quotes.
    5. Author-Year Punctuation Heuristic (with numeric garbage guard).
    6. Content Heuristic (first sentence that isn't just authors, splitting by dots).
    7. Comma-delimited segment.
    8. Fallback search for the longest substantive segment.
    """
    # --- 1. Normalize ---
    ref_text = normalize_ligatures(ref_text)

    # --- 2. Strip DOI URLs and bare DOIs ---
    # These often trail the title and confuse year and content heuristics.
    text = _DOI_URL_RE.sub('', ref_text)
    text = _BARE_DOI_RE.sub('', text)

    # --- 3. Cleanup ---
    # Strip bracketed labels at the start with year info: [ Wang et al., 2025b ]
    text = re.sub(r'^\s*\[\s*.*?\d{4}[a-z]?\s*\]\s*', '', text)
    # Strip simple numbered brackets: [1], [36]
    text = re.sub(r'^\s*\[?\d+\]?\s*', '', text).strip()

    # --- 4. Quote Matching ---
    # Quoted titles: "…", “…”, ``…'', or ``…'
    quoted = re.search(r'(?:"|"|``)(.*?)(?:"|"|\'\')', text)
    if quoted:
        return _clean_title(quoted.group(1).strip())

    # --- 5. Author-Year Punctuation Heuristic ---
    # Often titles follow "(Year)" or "Year."
    year_match = re.search(r'\(?(?:19|20)\d{2}[a-z]?\)?', text)
    if year_match:
        after_year = text[year_match.end():].strip()
        if len(after_year) > 20:
            after_year = re.sub(r'^[.,\s]+', '', after_year)
            title_candidate = re.split(
                r'\.\s+|[?!]\s+[Ii]n:\s+|,\s+[Ii]n:\s+|\s+[Ii]n:\s+|,\s+[Vv]ol\.|,\s+[Pp][Pp]\.',
                after_year
            )[0]
            if len(title_candidate) > 20:
                lower_cand = title_candidate.lower()
                starts_with_garbage = (
                    lower_cand.startswith('doi') or
                    lower_cand.startswith('url') or
                    lower_cand.startswith('http') or
                    lower_cand.startswith('arxiv') or
                    re.match(r'^\s*(pp\.|pages?|\d+\s*[-\u2013]\s*\d+)', lower_cand)
                )
                if not starts_with_garbage and not _is_numeric_garbage(title_candidate):
                    return _clean_title(title_candidate.strip())

    # --- 6. Content Heuristic (First sentence that isn't just authors) ---
    parts = [p.strip() for p in re.split(r'\.\s+', text) if p.strip()]
    for part in parts:
        if len(part) < 20:
            continue
        if "et al" in part.lower():
            continue

        if _is_author_list(part):
            continue

        comma_count = part.count(',')
        if comma_count > 3 and len(part) < 150:
            if ':' not in part:
                words = set(re.findall(r'\b\w+\b', part.lower()))
                if not (words & COMMON_TITLE_WORDS):
                    continue

        words = set(re.findall(r'\b\w+\b', part.lower()))
        if words & COMMON_TITLE_WORDS:
            candidate = _clean_title(part)
            if not _is_numeric_garbage(candidate) and len(candidate) >= 5:
                return candidate

    # --- 7. Comma-delimited segment ---
    if ',' in text:
        segments = [s.strip() for s in text.split(',') if s.strip()]
        for i, segment in enumerate(segments):
            if _is_author_list(segment) and ':' not in segment:
                continue
            is_author = False
            has_initials = re.search(r'[A-Z]\.?\s*[A-Z]?\.', segment)
            has_connector = re.search(r'\band\b|\bet al\b|&', segment, re.IGNORECASE)

            if has_initials and len(segment) < 25:
                is_author = True
            elif has_connector and len(segment) < 35:
                is_author = True
            elif len(segment) < 15:
                is_author = True

            if is_author:
                continue

            if len(segment) > 20:
                words = set(re.findall(r'\b\w+\b', segment.lower()))
                if words & COMMON_TITLE_WORDS:
                    candidate = _clean_title(segment)
                    if not _is_numeric_garbage(candidate) and len(candidate) >= 5:
                        return candidate

    # --- 8. Fallback ---
    fallback_parts = [p.strip() for p in re.split(r'\.\s+', text) if len(p.strip()) > 10]
    if fallback_parts:
        best = sorted(fallback_parts, key=len, reverse=True)[0]
        return _clean_title(best)

    return _clean_title(text[:100].strip())


def _strip_trailing_url(title: str) -> str:
    """Removes trailing URLs and bare DOIs from an extracted title string."""
    title = _ARXIV_URL_RE.sub('', title)
    title = _DOI_URL_RE.sub('', title)
    title = _BARE_DOI_RE.sub('', title)
    title = _URL_RE.sub('', title)
    # Clean up leading/trailing whitespace and punctuation artifacts
    title = re.sub(r'\s+', ' ', title).strip()
    title = title.rstrip('.,; ')
    return title


def extract_doi_info(ref_text: str):
    """
    Extracts a DOI from a reference string.
    """
    pattern = r'10\.\d{4,9}/[-._;()/:a-zA-Z0-9]*'
    match = re.search(pattern, ref_text)
    if match:
        return match.group(0), match.end()
    return None, 0


def heal_doi(base_doi: str, end_pos: int, ref_text: str):
    """
    Attempts to extend a DOI that was broken by a space in the source PDF.
    """
    tail = ref_text[end_pos:]
    match = re.match(r'^\s+([-._;()/:a-zA-Z0-9]+)', tail)
    if match:
        extension = match.group(1)
        if extension.lower() not in {'is', 'a', 'the', 'and', 'for', 'in', 'on', 'with'}:
            healed = base_doi + extension
            print(f"  [DEBUG] DOI healing: {base_doi} -> {healed}")
            return healed, end_pos + match.end()
    return None, 0


def extract_urls_from_reference(ref_text: str) -> list:
    """
    Extracts all URLs found in the reference text.
    This includes DOIs, arXiv links, and other web URLs.
    """
    urls = []
    
    # Extract DOI URLs (both http://dx.doi.org/... and https://doi.org/...)
    doi_urls = _DOI_URL_RE.findall(ref_text)
    urls.extend(doi_urls)
    
    # Extract bare DOIs (e.g., 10.1234/abcd.5678)
    bare_dois = _BARE_DOI_RE.findall(ref_text)
    urls.extend(bare_dois)
    
    # Extract arXiv URLs (both http://arxiv.org/... and https://arxiv.org/...)
    arxiv_urls = _ARXIV_URL_RE.findall(ref_text)
    urls.extend(arxiv_urls)
    
    # Extract any other URLs found (e.g., from full text like "URL: https://example.com")
    all_urls = _URL_RE.findall(ref_text)
    urls.extend(all_urls)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    
    return unique_urls
