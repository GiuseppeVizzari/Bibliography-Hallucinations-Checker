"""
app/checkers/extraction.py

Helpers to extract structured identifiers and titles from raw reference strings.
"""
import logging
import re
from typing import Optional
from .normalizer import normalize_ligatures, normalize_quotes, strip_doi_punctuation, strip_venue_suffix, strip_author_header

logger = logging.getLogger(__name__)


COMMON_TITLE_WORDS = {
    'the', 'a', 'an', 'and', 'for', 'in', 'on', 'with', 'to', 'of', 'at', 'by',
    'from', 'using', 'study', 'survey', 'review', 'analysis', 'framework',
    'model', 'method', 'approach', 'system', 'design', 'evaluation',
    'results', 'simulation', 'experimental', 'performance',
    'impact', 'influence', 'theory', 'detection', 'learning', 'optimization',
    'improved', 'based', 'between', 'towards', 'through', 'across'
}

# Compiled regexes for cleanup
_DOI_URL_RE = re.compile(r'https?://(?:dx\.)?doi\.org/[-._;()/:a-zA-Z0-9]*(?:\s+[-._;()/:a-zA-Z0-9]+)?')
_BARE_DOI_RE = re.compile(r'\b10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+\b')
_BROKEN_DOI_RE = re.compile(r'10\.\s+[-._;()/:a-zA-Z0-9]+')  # DOI broken by space/newline
_URL_RE = re.compile(r'https?://\S+|//[a-zA-Z][-./\w]*')
_ARXIV_URL_RE = re.compile(r'https?://arxiv\.org/\S+')
_ARXIV_ID_RE = re.compile(r'arxiv\.org/(?:abs/|pdf/)?(\d{4}\.\d{4,5}(v\d+)?)')
_VENUE_YEAR_RE = re.compile(r'\b(?:19|20)\d{2}\b')
_PARTIAL_DOI_RE = re.compile(r'(10\.)\s')


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


def _extract_quoted_title(text: str) -> Optional[str]:
    """
    Extracts the outermost quoted title from text, handling nested quotes.

    Supports curly quotes (""…""), straight quotes ("…"), and TeX-style (``…'').
    When inner and outer quotes are the same character (e.g. curly quotes nesting),
    correctly pairs them so the outermost content is returned.
    """
    LC = '\u201c'  # left curly double quote "
    RC = '\u201d'  # right curly double quote "
    SQ = '"'       # straight double quote
    BT = '`'       # backtick
    AP = "'"       # apostrophe

    # Find all quote positions with their types
    quotes = []
    # Curly openers and closers
    for m in re.finditer(re.escape(LC), text):
        quotes.append((m.start(), 'open_lc'))
    for m in re.finditer(re.escape(RC), text):
        quotes.append((m.start(), 'close_rc'))
    # Straight quotes
    for m in re.finditer(r'"', text):
        quotes.append((m.start(), 'straight'))
    # TeX-style: `` ... ''
    for m in re.finditer(r'``', text):
        quotes.append((m.start(), 'open_tt'))
    for m in re.finditer(r"''", text):
        quotes.append((m.start(), 'close_tt'))

    if not quotes:
        return None

    # Sort by position
    quotes.sort(key=lambda x: x[0])

    # Find the first opener
    first = None
    first_idx = None
    for i, (pos, qtype) in enumerate(quotes):
        if qtype in ('open_lc', 'straight', 'open_tt'):
            first = (pos, qtype)
            first_idx = i
            break

    if first is None:
        return None

    fpos, ftype = first
    later = quotes[first_idx + 1:]

    if ftype == 'open_lc':
        # Curly opener: find matching RC closers
        closers = [q for q in later if q[1] == 'close_rc']
        if not closers:
            return None
        # Count inner LC openers before the last closer (nested same-type quotes)
        inner_opens = [q for q in later if q[1] == 'open_lc' and q[0] < closers[-1][0]]
        # The last RC is the outer closer if there are more closers than inner openers
        # (each inner opener consumes one closer; remaining closer goes to outer)
        if len(closers) > len(inner_opens):
            return text[fpos + 1:closers[-1][0]].strip()
        # No closer left for outer pair
        return None

    elif ftype == 'open_tt':
        # TeX opener: find '' closers
        closers = [q for q in later if q[1] == 'close_tt']
        if closers:
            return text[fpos + 2:closers[-1][0]].strip()
        return None

    else:  # straight
        # Straight quotes: pair by counting
        later_straight = [q for q in later if q[1] == 'straight']
        if not later_straight:
            return None
        total = 1 + len(later_straight)  # including first
        if total % 2 == 0:
            return text[fpos + 1:later_straight[-1][0]].strip()
        elif len(later_straight) >= 2:
            return text[fpos + 1:later_straight[-2][0]].strip()
        else:
            return text[fpos + 1:later_straight[0][0]].strip()

    return None


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
    ref_text = normalize_quotes(ref_text)

    # --- 2. Strip DOI URLs, bare DOIs, and broken DOI remnants ---
    # These often trail the title and confuse year and content heuristics.
    text = _DOI_URL_RE.sub('', ref_text)  # Also handles broken DOI URLs with space continuation
    text = _BARE_DOI_RE.sub('', text)
    text = _BROKEN_DOI_RE.sub('', text)  # DOIs broken by PDF line-wrapping (no URL wrapper)
    # Strip leftover DOI URL fragments (e.g. 'http://dx.doi.org/' after DOI was stripped)
    text = re.sub(r'https?://(?:dx\.)?doi\.org/(?:\s+)?', ' ', text)

    # --- 3. Cleanup ---
    # Strip bracketed labels at the start with year info: [ Wang et al., 2025b ]
    text = re.sub(r'^\s*\[\s*.*?\d{4}[a-z]?\s*\]\s*', '', text)
    # Strip simple numbered brackets: [1], [36]
    text = re.sub(r'^\s*\[?\d+\]?\s*', '', text).strip()

    # --- 4. Quote Matching ---
    # Handles nested quotes (e.g. "title with "nested" quotes")
    quoted = _extract_quoted_title(text)
    if quoted:
        # Quoted titles are already disambiguated from authors by the quotes,
        # so we skip strip_author_header to preserve subtitles like "Osmnx: New methods..."
        cleaned = strip_venue_suffix(quoted)
        cleaned = _strip_trailing_venue(cleaned)
        return _strip_trailing_url(cleaned)

    # --- 4b. Book reference heuristic ---
    # Pattern: "Author, Title. City: Publisher, Year."
    # Find "City: Publisher" by looking for ". Capitalized: Capitalized, Year."
    # Use a greedy match to find the LAST ". City: Publisher, Year." pattern.
    city_pub_match = re.search(
        r'.*\.\s+([A-Z][\w\s\'.\-]+):\s*([A-Z][\w\s\'.\-]+(?:\.[\w\s\'.\-]+)*)(?:,?\s*(?:19|20)\d{2})?\.?\s*$',
        text,
        re.DOTALL
    )
    if city_pub_match:
        city = city_pub_match.group(1).strip()
        publisher = city_pub_match.group(2).strip()
        # Validate: city should be short (1-3 words), publisher should be reasonable
        city_words = len(re.findall(r'\b\w+\b', city))
        pub_words = len(re.findall(r'\b\w+\b', publisher))
        if 1 <= city_words <= 3 and 1 <= pub_words <= 5:
            # Get text before the city:publisher segment
            before = text[:city_pub_match.start(1) - 2].strip().rstrip('.')  # -2 for '. '
            # Split at first comma to separate author from title
            first_comma = before.find(',')
            if first_comma != -1:
                author_part = before[:first_comma].strip()
                title_part = before[first_comma + 1:].strip()
                # Validate: author should look like a name, title should be substantive
                author_words = re.findall(r'\b\w+\b', author_part)
                if author_words and len(title_part) > 10 and not _is_numeric_garbage(title_part):
                    return _clean_title(title_part)

    # --- 5. Author-Year Punctuation Heuristic ---
    # Often titles follow "(Year)" or "Year."
    # Must skip years that are part of venue names (e.g. "Proceedings of the 2024 ACM...").
    _VENUE_YEAR_PATTERN = re.compile(
        r'\b(Proceedings|Conference|Journal|Transactions|Symposium|Workshop|'
        r'Lecture\s+Notes|ACM|IEEE|Springer|ACIR|ECIR|WSDM|SIGIR|WWW|CHI|'
        r'ISCA|COLING|ACL|EMNLP|NAACL|ECCV|CVPR|ICCV|NeurIPS|ICML)\b',
        re.IGNORECASE
    )
    for year_match in re.finditer(r'\(?(?:19|20)\d{2}[a-z]?\)?', text):
        # Check if the matched year is part of a venue name (tight adjacency).
        # Only flag as venue-year when a venue keyword is immediately adjacent
        # (within ~15 chars), not just somewhere nearby in the reference.
        before_text = text[max(0, year_match.start() - 15):year_match.start()]
        after_text = text[year_match.end():year_match.end() + 15].strip()
        if _VENUE_YEAR_PATTERN.search(before_text) or _VENUE_YEAR_PATTERN.search(after_text):
            continue  # Year is in venue name; skip it

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
    # Also skip segments that look like venue names (e.g. "Proceedings of the 2023...").
    _VENUE_WORD_RE = re.compile(
        r'\b(Proceedings|Lecture\s+Notes|Transactions|Symposium|Workshop|'
        r'Journal)\b',
        re.IGNORECASE
    )
    _SOFT_VENUE_RE = re.compile(r'\bConference\b', re.IGNORECASE)
    _YEAR_IN_SEGMENT_RE = re.compile(r'\b(?:19|20)\d{2}\b')
    parts = [p.strip() for p in re.split(r'\.\s+', text) if p.strip()]
    for part in parts:
        if len(part) < 20:
            continue
        if "et al" in part.lower():
            continue

        if _is_author_list(part):
            continue

        # Skip venue-like segments: contains a hard venue keyword, or contains
        # both a soft venue keyword AND a year (strong signal of a venue name).
        has_hard_venue = bool(_VENUE_WORD_RE.search(part))
        has_soft_venue = bool(_SOFT_VENUE_RE.search(part))
        has_year = bool(_YEAR_IN_SEGMENT_RE.search(part))
        if has_hard_venue or (has_soft_venue and has_year):
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
    """Removes trailing URLs, bare DOIs, 'URL' keyword, and 'Accessed' markers."""
    title = _ARXIV_URL_RE.sub('', title)
    title = _DOI_URL_RE.sub('', title)
    title = _BARE_DOI_RE.sub('', title)
    title = _URL_RE.sub('', title)
    # Strip 'URL' keyword (often left orphaned after URL removal)
    title = re.sub(r'\s*URL\s*', ' ', title)
    # Strip '(Accessed <date>)' markers
    title = re.sub(r'\s*\(Accessed\s+.*?\)', ' ', title, flags=re.IGNORECASE)
    # Clean up leading/trailing whitespace and punctuation artifacts
    title = re.sub(r'\s+', ' ', title).strip()
    title = title.rstrip('.,; ')
    return title


def extract_doi_info(ref_text: str):
    """
    Extracts a DOI from a reference string.

    Handles both complete DOIs (e.g. '10.1016/j.ssci.2023.106174') and partial
    DOIs broken by PDF line-wrapping (e.g. '10. 1371/journal.pone.0276229' with
    a space after '10.'). Partial DOIs are returned so that heal_doi can
    reconstruct the full identifier.
    """
    pattern = r'10\.\d{4,9}/[-._;()/:a-zA-Z0-9]*'
    match = re.search(pattern, ref_text)
    if match:
        doi = match.group(0).rstrip('.,;)]')
        return doi, match.end()

    # Fallback: match '10.' followed by whitespace (broken DOI prefix)
    partial = _PARTIAL_DOI_RE.search(ref_text)
    if partial:
        # Return position right after '10.' (before the whitespace) so heal_doi
        # can consume the whitespace and find the continuation
        end_after_prefix = partial.start(1) + len(partial.group(1))
        return partial.group(1), end_after_prefix

    return None, 0


def heal_doi(base_doi: str, end_pos: int, ref_text: str):
    """
    Attempts to extend a DOI that was broken by a space in the source PDF.
    Strips trailing punctuation (periods, commas, etc.) from the healed DOI.
    """
    tail = ref_text[end_pos:]
    match = re.match(r'^\s+([-._;()/:a-zA-Z0-9]+)', tail)
    if match:
        extension = match.group(1).rstrip('.,;)]')
        if extension.lower() not in {'is', 'a', 'the', 'and', 'for', 'in', 'on', 'with'}:
            healed = base_doi + extension
            logger.debug(f"  [DEBUG] DOI healing: {base_doi} -> {healed}")
            return healed, end_pos + match.end()
    return None, 0


def heal_url(base_url: str, end_pos: int, ref_text: str) -> tuple:
    """
    Attempts to extend a URL that was broken by a space or newline in the source PDF.

    Handles cases like:
        https://example.com/some very/path  ->  https://example.com/somevery/path
        https://example.com/some-
          very/path                         ->  https://example.com/somevery/path

    Only heals when the continuation contains URL-path characters (/ . ~) to
    avoid false positives like "path end" where "end" is just the next word.

    Strips trailing punctuation (periods, commas, etc.) from the healed URL.
    Returns (healed_url, new_end_pos) or (None, 0) if no healing was needed.
    """
    tail = ref_text[end_pos:]

    # When the tail contains spaces, the continuation is likely a
    # multi-word URL path (e.g. "geometries cat bcn 2024" →
    # "geometries_cat_bcn_2024").  Try underscore replacement first.
    if ' ' in tail:
        # Check if the URL was cut mid-word: base ends with alnum AND
        # tail starts with space + alnum.  This avoids healing cases
        # like "path end" where "end" is just the next sentence word.
        base_ends_alnum = base_url[-1].isalnum() if base_url else False
        tail_has_space_alnum = (len(tail) >= 2 and tail[0] == ' '
                                and tail[1].isalnum())
        if base_ends_alnum and tail_has_space_alnum:
            # Heuristic: require a "URL-like" pattern in the tail to
            # avoid false positives like "foo the bar" → "foothe_bar".
            # Pattern: at least two lowercase words AND at least one
            # digit (common in repo/file names like "cat bcn 2024").
            tail_words = tail.strip().split()
            has_lower_words = sum(1 for w in tail_words if w.isalpha() and w.islower())
            has_digit = any(any(c.isdigit() for c in w) for w in tail_words)
            if has_lower_words >= 2 and has_digit:
                # Replace all spaces with underscores; the first space
                # (between base URL's last word and the tail) becomes
                # the underscore that joins them.
                candidate = base_url + tail.replace(' ', '_')
                if ' ' not in candidate and len(candidate) > len(base_url):
                    path_part = candidate[len(base_url):]
                    if (path_part and
                            not path_part.endswith('_') and
                            '__' not in path_part and
                            len(path_part) >= 3 and
                            all(c.isalnum() or c in '-_./~' for c in path_part)):
                        healed = candidate
                        logger.debug(f"  [DEBUG] URL healing (underscore): {base_url} -> {healed}")
                        new_end = end_pos + len(tail) - len(tail.rstrip())
                        return healed, new_end

    # Standard single-token healing (existing behavior).
    match = re.match(r'^\s+([-._;()/:a-zA-Z0-9]+)', tail)
    if match:
        extension = match.group(1).rstrip('.,;)]')
        if extension.lower() not in {'is', 'a', 'the', 'and', 'for', 'in', 'on', 'with'}:
            if '/' in extension or '.' in extension or '~' in extension:
                healed = base_url + extension
                logger.debug(f"  [DEBUG] URL healing: {base_url} -> {healed}")
                return healed, end_pos + match.end()

    return None, 0


def extract_arxiv_id_from_url(url: str) -> Optional[str]:
    """
    Extract the arXiv identifier (e.g. '2301.12345v1') from an arXiv URL.
    Returns None if the URL is not an arXiv link or no ID is found.
    """
    if 'arxiv.org' not in url:
        return None
    match = _ARXIV_ID_RE.search(url)
    return match.group(1) if match else None


def extract_arxiv_id_from_text(ref_text: str) -> Optional[str]:
    """
    Extract an arXiv identifier from any form found in the reference text:
    - arXiv URLs (https://arxiv.org/abs/2301.12345)
    - "arXiv:2403.02221" prefix
    - "CoRR, abs/1810.04805" legacy format
    Returns None if no arXiv ID is found.
    """
    # First, try URLs
    urls = extract_urls_from_reference(ref_text)
    for url in urls:
        arxiv_id = extract_arxiv_id_from_url(url)
        if arxiv_id:
            return arxiv_id

    # Then, try "arXiv:2403.02221" prefix
    match = re.search(r'arXiv:\s*(\d{4}\.\d{4,5}(v\d+)?)', ref_text, re.IGNORECASE)
    if match:
        return match.group(1)

    # Finally, try "CoRR, abs/1810.04805"
    match = re.search(r'CoRR,\s*abs/(\d{4}\.\d{4,5}(v\d+)?)', ref_text, re.IGNORECASE)
    if match:
        return match.group(1)

    return None


def extract_urls_from_reference(ref_text: str) -> list:
    """
    Extracts all URLs found in the reference text.
    This includes DOIs, arXiv links, and other web URLs.
    Trailing punctuation (periods, commas, etc.) is stripped from each URL.
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

    # --- URL healing: rejoin URLs broken across PDF line breaks ---
    healed_urls = []
    for url in urls:
        cleaned = url.rstrip('.,;:)]')
        if not cleaned:
            continue
        # Find where this URL ends in the original text
        idx = ref_text.find(cleaned)
        if idx >= 0:
            end_pos = idx + len(cleaned)
            healed, new_end = heal_url(cleaned, end_pos, ref_text)
            if healed:
                cleaned = healed.rstrip('.,;:)]')
                # Update idx to point to the healed URL for dedup check
                idx = ref_text.find(healed)
        healed_urls.append(cleaned)

    # Remove duplicates while preserving order
    seen = set()
    unique_urls = []
    for url in healed_urls:
        if url and url not in seen:
            seen.add(url)
            unique_urls.append(url)

    return unique_urls


def build_original_url(ref_text: str) -> Optional[str]:
    """
    Builds a best-effort clickable URL for a reference entry.

    Priority order:
    1. DOI → https://doi.org/...
    2. arXiv ID → https://arxiv.org/abs/...
    3. First HTTP(S) URL found in the reference text
    """
    # 1. Try DOI
    doi, _ = extract_doi_info(ref_text)
    if doi:
        return f"https://doi.org/{strip_doi_punctuation(doi)}"

    # 2. Try arXiv ID from any URL in the reference
    urls = extract_urls_from_reference(ref_text)
    for url in urls:
        arxiv_id = extract_arxiv_id_from_url(url)
        if arxiv_id:
            return f"https://arxiv.org/abs/{arxiv_id}"

    # 3. Fallback: first HTTP(S) URL in the raw text
    url_match = re.search(r'https?://[^\s,)]+', ref_text)
    if url_match:
        return url_match.group(0).rstrip('.,;)')

    return None
