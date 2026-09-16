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


def _is_citation_bracket(text: str) -> bool:
    """Returns True if the block is just a citation bracket like [1], [2], etc."""
    return bool(re.match(r'^\s*\[\s*\d+\s*\]\s*$', text))


def _starts_with_citation_bracket(text: str) -> bool:
    """Returns True if the block starts with a citation bracket like [1] or [16]."""
    return bool(re.match(r'^\s*\[\s*\d+\s*\]\s+', text))


def _is_page_number_artifact(text: str, block_width: float) -> bool:
    """Returns True if the block is a standalone page number (not reference content)."""
    return block_width < 30 and re.match(r'^\d{1,3}$', text.strip())


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

                # Blocks spanning >60% of page height are content, not footers
                block_height = y1 - y0
                height_ratio = block_height / page_height if page_height > 0 else 0
                if height_ratio > 0.6:
                    pass  # Keep this block regardless of vertical position
                elif y0 < margin or y1 > (page_height - margin):
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
    # "rererences" is a deliberate OCR typo catch — PDFs sometimes render
    # "references" as "rererences" due to the 'f' glyph being misread as 'fe'.
    # Less relevant for LaTeX-generated PDFs but kept for robustness.
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
            matched_keyword = None
            if any(k in text_to_check for k in keywords):
                clean_text = re.sub(r'[^a-z]', '', text_to_check)
                for k in keywords:
                    if k in clean_text:
                        matched_keyword = k
                        break
                if matched_keyword:
                    # Verify it's actually a header, not just an inline mention.
                    # A real header's text is essentially the keyword itself
                    # (allowing minor surrounding punctuation/whitespace).
                    no_keyword = re.sub(matched_keyword, '', clean_text).strip()
                    if len(no_keyword) <= 5:
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
        logger.info(f"Bibliography section found at block {ref_start_index}")

    if ref_start_index == -1:
        logger.warning("  Could not find bibliography section header in any block.")
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

    logger.info(f"Scanning {len(all_blocks) - ref_start_index - 1} blocks after bibliography header...")

    # Track consecutive blocks that look like non-reference content.
    # When enough blocks in a row lack DOI patterns, author names, and
    # citation structure, we assume the bibliography has ended — even
    # if the next section has no explicit "appendix" / "acknowledgments"
    # header.  This prevents appendix / supplementary content from
    # leaking into the reference list.
    non_ref_streak = 0
    NON_REF_THRESHOLD = 2  # two consecutive non-reference blocks
    MIN_REF_COUNT = 5    # don't start the non-ref streak until we've seen
                         # at least this many references (avoids cutting
                         # short genuinely short bibliographies)

    _DOI_RE = re.compile(r'10\.\d{4,9}/')
    _AUTHOR_YEAR_RE_BLOCK = re.compile(r'\[[A-Z][^\[\]]*\d{4}[a-z]?\]')
    _VENUE_YEAR_RE_BLOCK = re.compile(r'\b(?:19|20)\d{2}\b')

    def _looks_like_reference(text: str) -> bool:
        """Heuristic: does this block resemble a bibliographic reference?"""
        if not text or len(text.split()) < 5:
            return False
        # Must have at least two of: DOI pattern, author-year bracket, year
        signals = (
            bool(_DOI_RE.search(text))
            + bool(_AUTHOR_YEAR_RE_BLOCK.search(text))
            + bool(_VENUE_YEAR_RE_BLOCK.search(text))
        )
        return signals >= 2

    def _looks_like_title(text: str) -> bool:
        """Heuristic: does this block look like a section title / header?

        Section titles in PDFs often appear as short blocks with an unusual
        proportion of uppercase characters (e.g. "A The Simulator", "B
        Tunable Parameter Catalogue").  This is a soft signal used to stop
        the bibliography scan early, before appendix content leaks in.
        """
        if not text or len(text.split()) > 15:
            return False
        stripped = re.sub(r'[^A-Za-z]', '', text)
        if not stripped:
            return False
        upper_ratio = sum(1 for c in stripped if c.isupper()) / len(stripped)
        # High uppercase ratio is unusual for normal prose but common for
        # short section titles (e.g. "A The Simulator" → 6/13 ≈ 46%).
        if upper_ratio > 0.40:
            return True
        return False

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

        # Skip structural artifacts (page numbers) from the non-reference
        # streak.  Page numbers are layout artifacts, not content.
        block_width = all_blocks[i][2] - all_blocks[i][0]
        if _is_page_number_artifact(block_text, block_width):
            logger.debug(f"  [DEBUG]   SKIP (structural artifact): '{first_line}'")
            non_ref_streak = 0  # reset — not real content
            continue

        # If a block is just a citation bracket like [2], include it in
        # ref_content (so its content on the next block can be merged) but
        # reset the streak since it's not real reference content.
        if _is_citation_bracket(block_text):
            logger.debug(f"  [DEBUG]   INCLUDE (citation bracket): '{first_line}'")
            non_ref_streak = 0
            ref_content.append(block_text)
            continue

        # If a block starts with a citation bracket like [7], it's likely the
        # start of a new reference (even if it lacks a year on this line).
        # Reset the streak so we don't prematurely stop.
        if _starts_with_citation_bracket(block_text):
            non_ref_streak = 0

        # Stop early if this block looks like a section title / header.
        # Titles often have an unusual uppercase ratio and are short.
        if _looks_like_title(block_text):
            logger.debug(
                f"  [DEBUG] STOP (title-like block): '{first_line}'"
            )
            break

        if _looks_like_reference(block_text):
            non_ref_streak = 0
        elif len(ref_content) >= MIN_REF_COUNT:
            # Only start counting non-ref streak after we've collected
            # enough references to be confident we're past the bibliography.
            non_ref_streak += 1
            if non_ref_streak >= NON_REF_THRESHOLD:
                logger.debug(
                    f"  [DEBUG] STOP (non-reference streak={non_ref_streak}): "
                    f"'{first_line}'"
                )
                break

        logger.debug(f"  [DEBUG]   INCLUDE block {i} ({len(lower_text.split())} words): '{first_line}'")
        ref_content.append(block_text)

    logger.info(f"Total blocks collected for bibliography: {len(ref_content)}")

    # P2: Multi-page fallback — detect page gaps in consecutive blocks and merge
    # across the gap. This handles references that span page boundaries.
    # Also merge same-page blocks where a bracket-only block (e.g. "[2]")
    # immediately precedes its content — some PDFs lay out references this way.
    merged_content = []
    i = 0
    while i < len(ref_content):
        block_idx = ref_start_index + 1 + i
        page_curr = all_blocks[block_idx][7] if block_idx < len(all_blocks) else -1
        merged = ref_content[i]
        j = i + 1

        # Same-page merge: only merge when current block is bracket-only
        # (e.g. "[2]" alone). Don't merge full references across same-page
        # blocks — that would swallow content from multiple references.
        if _is_citation_bracket(ref_content[i]):
            while j < len(ref_content):
                block_idx_j = ref_start_index + 1 + j
                page_j = all_blocks[block_idx_j][7] if block_idx_j < len(all_blocks) else -1
                next_text = ref_content[j]

                # Stop if next block starts a new reference
                if _starts_with_citation_bracket(next_text):
                    break

                # Stop if next block is on a different page
                if page_j != page_curr:
                    break

                merged += "\n" + next_text
                j += 1

        merged_content.append(merged)
        i = j

    ref_content = merged_content
    logger.info(f"After multi-page merge: {len(ref_content)} blocks")

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
        logger.info(f"Split into {len(refs)} references (Strategy A: bracketed numbers)")
        return refs

    # Strategy B: Numbered 1., 2.
    if re.search(r'^\s*1\.\s+', full_ref_text, re.MULTILINE):
        refs = re.split(r'(?=(?:\r?\n|\r|^)\s*\d+\.\s+)', full_ref_text)
        refs = [prune_trailing_garbage(r) for r in refs]
        refs = [cleanup_ref(r) for r in refs if r.strip()]
        refs = [r for r in refs if len(r) > 10]
        logger.info(f"Split into {len(refs)} references (Strategy B: numbered)")
        return refs

    # Strategy D: Author-year [Author, Year] style
    # This handles PDFs that pack all references into a single block
    # with [Author, Year] markers (common in some LaTeX templates).
    if re.search(_AUTHOR_YEAR_PATTERN, full_ref_text):
        refs = re.split(_AUTHOR_YEAR_PATTERN, full_ref_text)
        refs = [prune_trailing_garbage(r) for r in refs]
        refs = [cleanup_ref(r) for r in refs if r.strip()]
        refs = [r for r in refs if len(r) > 20]
        logger.info(f"Split into {len(refs)} references (Strategy D: author-year)")
        return refs

    # Strategy C: Fallback — one block per reference
    raw_refs = []
    for block_text in ref_content:
        pruned_block = prune_trailing_garbage(block_text)
        text = cleanup_ref(pruned_block)
        if len(text) > 20:
            raw_refs.append(text)

    logger.info(f"Split into {len(raw_refs)} references (Strategy C: fallback)")
    return raw_refs
