import fitz
import logging
import re
from .checkers.normalizer import heal_hyphens

logger = logging.getLogger(__name__)


_LINE_NUM_PATTERN = re.compile(r'^\d{1,4}$')
_NUMERIC_TABLE_PATTERN = re.compile(r'^[\+\-±]?\d+([.,]\d+)?([eE][\+\-]?\d+)?$')
_AUTHOR_YEAR_PATTERN = re.compile(
    r'(?:(?:\r?\n|\r|^)\s*\[[A-Z][^\[\]]*\d{4}[a-z]?\]\s*)'
)


def _strip_embedded_line_numbers(text: str) -> str:
    """Removes lines that are standalone 1–4 digit line numbers."""
    if not text:
        return text
    lines = text.splitlines()
    return '\n'.join(
        line for line in lines
        if not _LINE_NUM_PATTERN.match(line.strip())
    )


def _is_marginal_line_number(block: tuple, page_width: float) -> bool:
    """
    Returns True if the block is a narrow numeric block sitting in the
    left or right margin — a strong indicator of a marginal line number.
    """
    x0, _, x1, _ = block[0], block[1], block[2], block[3]
    text = block[4].strip()
    width = x1 - x0
    in_margin = x0 < 50 or x1 > page_width - 50
    return bool(in_margin and width < 60 and _LINE_NUM_PATTERN.match(text))


def _is_numeric_table_row(text: str) -> bool:
    """
    Returns True if the block looks like a numeric table row rather than a
    bibliographic reference.  Heuristic: if more than 60% of the whitespace-
    separated tokens are numeric (integers, floats, ±values), it's table data.
    """
    tokens = text.split()
    if len(tokens) < 4:
        return False
    numeric_count = sum(1 for t in tokens if _NUMERIC_TABLE_PATTERN.match(t.strip('.,;:')))
    return (numeric_count / len(tokens)) > 0.60


def extract_bibliography(pdf_path):
    """
    Extracts bibliography references from a PDF.
    Returns a list of reference strings.
    """
    doc = fitz.open(pdf_path)
    full_text = ""

    # 1. Extract text with layout preservation (blocks)
    all_blocks = []
    for page_idx, page in enumerate(doc):
        page_height = page.rect.height
        page_width = page.rect.width
        margin = 50

        blocks = page.get_text("blocks")
        cleaned_blocks = []
        for b in blocks:
            if b[6] == 0:
                y0, y1 = b[1], b[3]
                if y0 < margin or y1 > (page_height - margin):
                    continue

                # Skip marginal line-number blocks (narrow, near edge, purely numeric)
                if _is_marginal_line_number(b, page_width):
                    continue

                block_text = b[4].strip()
                if not block_text:
                    continue

                # Filter out pure line number blocks
                if _LINE_NUM_PATTERN.match(block_text):
                    continue

                # Filter out pure line number sequence blocks
                if re.match(r'^(\d+\s*)+$', block_text):
                    continue

                b_list = list(b)
                b_list.append(page_idx)
                cleaned_blocks.append(b_list)

        mid_x = page.rect.width / 2
        cleaned_blocks.sort(key=lambda b: (0 if b[0] < mid_x else 1, b[1]))
        all_blocks.extend(cleaned_blocks)

    total_pages = len(doc)
    doc.close()

    # 2. Find "References" or "Bibliography" section
    candidates = []
    keywords = ["references", "bibliography", "works cited", "bibliografia", "riferimenti", "rererences"]

    for i, block in enumerate(all_blocks):
        raw_text = block[4].strip()
        text = raw_text.lower()

        # Check if the first line of a multi-line block is a header
        # (handles PDFs where line numbers merge header + first ref into one block)
        first_line = raw_text.splitlines()[0].lower().strip() if raw_text else ''

        # Consider the block a header candidate if:
        # - block is short (< 10 words), OR
        # - first line alone matches a header keyword (< 10 words, blocks with merged line numbers)
        text_to_check = first_line if len(text.split()) >= 10 else text

        if len(text_to_check.split()) < 10:
            if any(k in text_to_check for k in keywords):
                clean_text = re.sub(r'[^a-z]', '', text_to_check)
                if any(k in clean_text for k in keywords):
                    page_num = block[7]

                    # Strip line numbers before ToC check to avoid false positives
                    text_no_ln = _strip_embedded_line_numbers(text_to_check)
                    is_toc = False
                    if re.search(r'\d+$', text_no_ln) or '..' in text_no_ln or '. .' in text_no_ln:
                        is_toc = True
                    if total_pages >= 4 and page_num < total_pages * 0.25:
                        is_toc = True

                    if not is_toc:
                        candidates.append(i)

    ref_start_index = candidates[0] if candidates else -1
    if ref_start_index != -1:
        logger.debug(f"  [DEBUG] Bibliography section found at block {ref_start_index}: '{all_blocks[ref_start_index][4].strip()[:60]}'")

    if ref_start_index == -1:
        logger.debug("  [DEBUG] Could not find bibliography section header in any block.")
        return []

    # 3. Concatenate text until the end of references or a termination header
    ref_content = []
    termination_keywords = [
        "appendix", "appendices", "annex", "supplementary material", "supplemental material",
        "acknowledgment", "acknowledgments", "author contributions", "conflicts of interest",
        "biography", "biographies", "about the author", "about the authors",
        "author biography", "author biographies", "biographical", "index", "glossary",
        "appendice", "appendici", "ringraziamenti", "declaration of interest", "declarations of interest",
        "funding", "competing interest", "competing interests", "contributors",
        "credit", "credit author statement", "author statement", "use of generative", "generative ai"
    ]

    logger.debug(f"  [DEBUG] Scanning {len(all_blocks) - ref_start_index - 1} blocks after bibliography header...")
    for i in range(ref_start_index + 1, len(all_blocks)):
        block_text = all_blocks[i][4].strip()
        lower_text = block_text.lower()
        first_line = block_text.splitlines()[0][:80] if block_text else ''

        norm_text = re.sub(r'\s+', ' ', lower_text).strip()
        term_pattern = (
            r'^(appendix|appendices|annex|supplement|acknowledg|author\s+contribution|'
            r'conflict\s+of\s+interest|biography|biographies|author\s+biograph|'
            r'about\s+the\s+author|index|glossary|appendice|appendici|ringraziamenti|'
            r'declaration\s+of\s+interest|funding|competing\s+interest|contributor|'
            r'credit|author\s+statement|use\s+of\s+generative|generative\s+ai)\b'
        )
        if re.match(term_pattern, norm_text):
            logger.debug(f"  [DEBUG] STOP (anchor match): '{first_line}'")
            break

        if re.match(r'^appendix\s+[a-z0-9]', lower_text):
            logger.debug(f"  [DEBUG] STOP (appendix letter): '{first_line}'")
            break

        if re.match(r'^(table|fig\.?|figure)\s+[a-z]\d*\b', lower_text):
            logger.debug(f"  [DEBUG] STOP (appendix table/figure): '{first_line}'")
            break

        if len(lower_text.split()) < 10:
            clean_text = re.sub(r'[^a-z]', '', lower_text)
            if any(k.replace(' ', '') == clean_text for k in termination_keywords):
                logger.debug(f"  [DEBUG] STOP (exact match): '{first_line}'")
                break

        if _is_numeric_table_row(block_text):
            logger.debug(f"  [DEBUG]   SKIP (numeric table row): '{first_line}'")
            continue

        logger.debug(f"  [DEBUG]   INCLUDE block {i} ({len(lower_text.split())} words): '{first_line}'")
        ref_content.append(block_text)

    logger.debug(f"  [DEBUG] Total blocks collected for bibliography: {len(ref_content)}")

    full_ref_text = "\n".join(ref_content)

    # Strip embedded line numbers from the full text before splitting
    full_ref_text = _strip_embedded_line_numbers(full_ref_text)

    def prune_trailing_garbage(ref_text: str) -> str:
        lines = ref_text.splitlines()
        clean_lines = []
        for line in lines:
            lower_line = line.strip().lower()
            normalized = re.sub(r'^[\d\s\.\-\/\:]+', '', lower_line)
            is_termination = False
            for kw in termination_keywords:
                if normalized.startswith(kw):
                    is_termination = True
                    break
            if is_termination:
                break
            clean_lines.append(line)
        return "\n".join(clean_lines)

    def cleanup_ref(text: str) -> str:
        """Applies all per-reference cleanup: line numbers, hyphens, newlines."""
        text = _strip_embedded_line_numbers(text)
        return heal_hyphens(text.strip()).replace('\n', ' ')

    # 4. Split into individual references
    # Strategy A: Bracketed numbers [1], [2], etc.
    if re.search(r'^\s*\[\d+\]', full_ref_text, re.MULTILINE):
        refs = re.split(r'(?=(?:\r?\n|\r|^)\s*\[\d+\])', full_ref_text)
        refs = [prune_trailing_garbage(r) for r in refs]
        refs = [cleanup_ref(r) for r in refs if r.strip()]
        refs = [r for r in refs if len(r) > 10]
        return refs

    # Strategy B: Numbered 1., 2.
    if re.search(r'^\s*1\.\s+', full_ref_text, re.MULTILINE):
        refs = re.split(r'(?=(?:\r?\n|\r|^)\s*\d+\.\s+)', full_ref_text)
        refs = [prune_trailing_garbage(r) for r in refs]
        refs = [cleanup_ref(r) for r in refs if r.strip()]
        refs = [r for r in refs if len(r) > 10]
        return refs

    # Strategy D: Author-year [Author, Year] style
    # This handles PDFs that pack all references into a single block
    # with [Author, Year] markers (common in some LaTeX templates).
    if re.search(_AUTHOR_YEAR_PATTERN, full_ref_text):
        refs = re.split(_AUTHOR_YEAR_PATTERN, full_ref_text)
        refs = [prune_trailing_garbage(r) for r in refs]
        refs = [cleanup_ref(r) for r in refs if r.strip()]
        refs = [r for r in refs if len(r) > 20]
        return refs

    # Strategy C: Fallback — one block per reference
    raw_refs = []
    for block_text in ref_content:
        pruned_block = prune_trailing_garbage(block_text)
        text = cleanup_ref(pruned_block)
        if len(text) > 20:
            raw_refs.append(text)

    return raw_refs
