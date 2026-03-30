"""
app/checkers/extraction.py

Helpers to extract structured identifiers and titles from raw reference strings.
"""
import re


def extract_title_from_reference(ref_text: str) -> str:
    """
    Attempts to extract the title from a reference string using advanced heuristics.

    Strategy (in order):
    1. Strip bracketed citation keys [ Wang et al., 2025b ] or [36].
    2. Text enclosed in standard, smart, or LaTeX-style quotes.
    3. Heuristic for non-quoted titles (Author-Year styles).
    4. Fallback search for the first substantive segment.
    """
    # --- 1. Cleanup ---
    # Strip bracketed labels at the start with year info: [ Wang et al., 2025b ]
    text = re.sub(r'^\s*\[\s*.*?\d{4}[a-z]?\s*\]\s*', '', ref_text)
    # Strip simple numbered brackets: [1], [36]
    text = re.sub(r'^\s*\[?\d+\]?\s*', '', text).strip()

    # --- 2. Quote Matching ---
    # Quoted titles: "…", “…”, ``…'', or ``…'
    quoted = re.search(r'(?:"|“|``)(.*?)(?:"|”|\'\')', text)
    if quoted:
        return quoted.group(1).strip()

    # --- 3. Author-Year Punctuation Heuristic ---
    # Often titles follow "(Year)" or "Year."
    # We look for the first 4-digit year, possibly in parentheses
    year_match = re.search(r'\(?\d{4}[a-z]?\)?', text)
    if year_match:
        after_year = text[year_match.end():].strip()
        # If there's content after the year, it's very likely the title
        if len(after_year) > 20:
            # Strip leading dots/commas
            after_year = re.sub(r'^[.,\s]+', '', after_year)
            # Find the first segment (splitting by dot or common venue indicators)
            # We split by ". " or common journal/volume patterns
            title_candidate = re.split(r'\.\s+|,\s+[Vv]ol\.|,\s+[Pp][Pp]\.', after_year)[0]
            if len(title_candidate) > 20:
                return title_candidate.strip()

    # --- 4. Content Heuristic (First sentence that isn't just authors) ---
    # We split by periods and look for a part that "looks like a title"
    # Titles usually contain common English stop words, while author lists don't.
    common_words = {
        'the', 'a', 'an', 'and', 'for', 'in', 'on', 'with', 'to', 'of', 'at', 'by', 
        'from', 'using', 'study', 'survey', 'review', 'systematic', 'mapping',
        'social', 'behavior', 'learning', 'detection', 'group', 'crowd'
    }
    
    parts = [p.strip() for p in text.split('.') if p.strip()]
    for part in parts:
        if len(part) < 20:
            continue
        if "et al" in part.lower():
            continue
            
        # Sentiment check: does it look like names? (Author lists often have many commas)
        # We penalize segments with 3 or more commas if they aren't very long.
        comma_count = part.count(',')
        # If it looks like a list of names:
        if comma_count > 3 and len(part) < 150:
            continue

        # If it's long and has common words, it's probably the title.
        words = set(re.findall(r'\b\w+\b', part.lower()))
        if words & common_words:
            return part
            
    # Final fallback: take the longest reasonable part or the first 100 chars
    parts = [p.strip() for p in text.split('.') if len(p.strip()) > 10]
    if parts:
        return sorted(parts, key=len, reverse=True)[0]
    
    return text[:100].strip()


def extract_doi_info(ref_text: str):
    """
    Extracts a DOI from a reference string.

    Returns:
        (doi, end_position) — doi is None if not found.
    """
    pattern = r'10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+'
    match = re.search(pattern, ref_text)
    if match:
        return match.group(0), match.end()
    return None, 0


def heal_doi(base_doi: str, end_pos: int, ref_text: str):
    """
    Attempts to extend a DOI that was broken by a space in the source PDF.

    Example: ``10.1016/j.tra.2025. 104429`` → ``10.1016/j.tra.2025.104429``

    Returns:
        (healed_doi, new_end_pos) — healed_doi is None if healing fails.
    """
    tail = ref_text[end_pos:]
    match = re.match(r'^\s+([-._;()/:a-zA-Z0-9]+)', tail)
    if match:
        extension = match.group(1)
        # Ignore common English words that follow a DOI in running text
        if extension.lower() not in {'is', 'a', 'the', 'and', 'for', 'in', 'on', 'with'}:
            healed = base_doi + extension
            print(f"  [DEBUG] DOI healing: {base_doi} -> {healed}")
            return healed, end_pos + match.end()
    return None, 0


def extract_arxiv_id(ref_text: str):
    """
    Extracts an arXiv paper ID from a reference string.

    Handles:
    - ``arXiv:2412.11814`` style
    - ``arxiv.org/abs/2412.11814`` URL style
    - Legacy category IDs (e.g. ``cs.CV/0612084``)

    Returns:
        The arXiv ID string, or None.
    """
    # Modern inline style: arXiv:2412.11814 or arxiv: cs.CV/2412.11814
    match = re.search(
        r'arxiv:?\s*([a-z-]+(?:\.[a-z-]+)?/)?(\d{4}\.\d{4,5}(v\d+)?)',
        ref_text, re.IGNORECASE
    )
    if match:
        return match.group(2).strip()

    # URL style: arxiv.org/abs/... or arxiv.org/pdf/...
    match = re.search(
        r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(v\d+)?|[a-z-]+(?:\.[A-Z]{2})?/\d{7}(v\d+)?)',
        ref_text, re.IGNORECASE
    )
    if match:
        return match.group(1).strip()

    return None
