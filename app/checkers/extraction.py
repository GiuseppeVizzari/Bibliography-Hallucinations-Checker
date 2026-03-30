"""
app/checkers/extraction.py

Helpers to extract structured identifiers and titles from raw reference strings.
"""
import re


def extract_title_from_reference(ref_text: str) -> str:
    """
    Attempts to extract the title from a reference string.

    Strategy (in order):
    1. Text enclosed in standard, smart, or LaTeX-style quotes.
    2. The first period-delimited segment that looks like a title.
    3. Fallback: first 100 characters.
    """
    # Strip common reference number prefixes: [1], 1., etc.
    text = re.sub(r'^\s*\[?\d+\]?\.\?\s*', '', ref_text)

    # 1. Quoted title: "…", “…”, ``…'', or ``…'
    quoted = re.search(r'(?:"|“|``)(.*?)(?:"|”|\'\')', text)
    if quoted:
        return quoted.group(1).strip()

    # 2. Period-delimited fallback
    parts = text.split('.')
    if len(parts) >= 2:
        for part in parts[1:]:
            part = part.strip()
            if len(part) > 20 and not re.match(r'^\d{4}', part):
                return part

    # 3. Raw fallback
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
