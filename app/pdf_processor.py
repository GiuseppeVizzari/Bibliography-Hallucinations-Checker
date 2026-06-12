import fitz  # PyMuPDF
import re
from .checkers.normalizer import heal_hyphens


def _is_numeric_table_row(text: str) -> bool:
    """
    Returns True if the block looks like a numeric table row rather than a
    bibliographic reference.  Heuristic: if more than 60% of the whitespace-
    separated tokens are numeric (integers, floats, ±values), it's table data.
    """
    tokens = text.split()
    if len(tokens) < 4:
        return False
    numeric_pat = re.compile(r'^[\+\-±]?\d+([.,]\d+)?([eE][\+\-]?\d+)?$')
    numeric_count = sum(1 for t in tokens if numeric_pat.match(t.strip('.,;:')))
    return (numeric_count / len(tokens)) > 0.60

def extract_bibliography(pdf_path):
    """
    Extracts bibliography references from a PDF.
    Returns a list of reference strings.
    """
    doc = fitz.open(pdf_path)
    full_text = ""
    
    # 1. Extract text with layout preservation (blocks)
    # PyMuPDF's get_text('blocks') returns (x0, y0, x1, y1, text, block_no, block_type)
    # We sort by vertical position then horizontal to handle columns somewhat naturally,
    # but for true 2-column support, fitz's default block ordering is usually good enough 
    # if the reading order is encoded correctly. 
    # For robust 2-column, we can sort blocks: top-down, left-right.
    
    all_blocks = []
    for page_idx, page in enumerate(doc):
        page_height = page.rect.height
        margin = 50 # Reduced from 10% to 50 points to avoid filtering out headers and content
        
        blocks = page.get_text("blocks")
        # clean blocks: remove blocks with no text or just whitespace
        cleaned_blocks = []
        for b in blocks:
            if b[6] == 0: # text block
                # Filter out headers/footers based on y-coordinate
                y0, y1 = b[1], b[3]
                if y0 < margin or y1 > (page_height - margin):
                    continue

                block_text = b[4].strip()
                if block_text:
                    # Filter out pure line number blocks (e.g., '1\n2\n3' or '45')
                    # This prevents draft line numbers from being interleaved with the text
                    if re.match(r'^(\d+\s*)+$', block_text):
                        continue
                    # Convert block to a list and append the page index
                    b_list = list(b)
                    b_list.append(page_idx)
                    cleaned_blocks.append(b_list)
        
        # Sort blocks to handle two-column layouts.
        # Group by horizontal position into left/right halves to avoid splitting indented blocks.
        # This ensures the left column is read top-to-bottom before the right column.
        mid_x = page.rect.width / 2
        cleaned_blocks.sort(key=lambda b: (0 if b[0] < mid_x else 1, b[1]))
        
        all_blocks.extend(cleaned_blocks)

    total_pages = len(doc)
    doc.close()

    # 2. Find "References" or "Bibliography" section
    # We'll look for a block that contains *only* (or mostly) the header.
    # We iterate through blocks to find the split point.
    
    candidates = []
    keywords = ["references", "bibliography", "works cited", "bibliografia", "riferimenti", "rererences"]
    
    for i, block in enumerate(all_blocks):
        text = block[4].strip().lower()
        # Check if the block is a header (short length, contains keyword)
        if len(text.split()) < 10: 
            if any(k in text for k in keywords):
                # Potential match. 
                # Strict check: if it's just the word (plus maybe numbers/punctuation)
                clean_text = re.sub(r'[^a-z]', '', text)
                if any(k in clean_text for k in keywords):
                    page_num = block[7]
                    
                    # Skip if it looks like a Table of Contents entry:
                    # e.g., contains a trailing page number, dotted lines, or appears in the first 25% of pages of a larger document.
                    is_toc = False
                    if re.search(r'\d+$', text) or '..' in text or '. .' in text:
                        is_toc = True
                    if total_pages >= 4 and page_num < total_pages * 0.25:
                        is_toc = True
                        
                    if not is_toc:
                        candidates.append(i)
                        
    ref_start_index = candidates[0] if candidates else -1
    if ref_start_index != -1:
        print(f"  [DEBUG] Bibliography section found at block {ref_start_index}: '{all_blocks[ref_start_index][4].strip()[:60]}'")

    
    if ref_start_index == -1:
        print("  [DEBUG] Could not find bibliography section header in any block.")
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
    
    print(f"  [DEBUG] Scanning {len(all_blocks) - ref_start_index - 1} blocks after bibliography header...")
    for i in range(ref_start_index + 1, len(all_blocks)):
        block_text = all_blocks[i][4].strip()
        lower_text = block_text.lower()
        first_line = block_text.splitlines()[0][:80] if block_text else ''

        # Check if this block looks like a termination header (appendix, acknowledgements, biography, etc.)
        # Normalize spaces to single space for robust matching of phrases
        norm_text = re.sub(r'\s+', ' ', lower_text).strip()
        term_pattern = (
            r'^(appendix|appendices|annex|supplement|acknowledg|author\s+contribution|'
            r'conflict\s+of\s+interest|biography|biographies|author\s+biograph|'
            r'about\s+the\s+author|index|glossary|appendice|appendici|ringraziamenti|'
            r'declaration\s+of\s+interest|funding|competing\s+interest|contributor|'
            r'credit|author\s+statement|use\s+of\s+generative|generative\s+ai)\b'
        )
        if re.match(term_pattern, norm_text):
            print(f"  [DEBUG] STOP (anchor match): '{first_line}'")
            break

        # Appendix letter-section heading: "Appendix A", "A.1 ...", etc.
        if re.match(r'^appendix\s+[a-z0-9]', lower_text):
            print(f"  [DEBUG] STOP (appendix letter): '{first_line}'")
            break

        # Appendix table / figure caption: "Table A1", "Fig. A2", "Figure A3"
        if re.match(r'^(table|fig\.?|figure)\s+[a-z]\d*\b', lower_text):
            print(f"  [DEBUG] STOP (appendix table/figure): '{first_line}'")
            break

        # Exact-match check for short blocks (normalises out numbers/punct)
        if len(lower_text.split()) < 10:
            clean_text = re.sub(r'[^a-z]', '', lower_text)
            if any(k.replace(' ', '') == clean_text for k in termination_keywords):
                print(f"  [DEBUG] STOP (exact match): '{first_line}'")
                break

        # Skip blocks that look like pure numeric table rows (appendix data)
        if _is_numeric_table_row(block_text):
            print(f"  [DEBUG]   SKIP (numeric table row): '{first_line}'")
            continue

        print(f"  [DEBUG]   INCLUDE block {i} ({len(lower_text.split())} words): '{first_line}'")
        ref_content.append(block_text)

    print(f"  [DEBUG] Total blocks collected for bibliography: {len(ref_content)}")
        
    full_ref_text = "\n".join(ref_content)
    
    def prune_trailing_garbage(ref_text: str) -> str:
        """
        Prunes any trailing garbage (biographies, appendices, etc.) from a reference string
        by checking if any line looks like a termination header.
        """
        lines = ref_text.splitlines()
        clean_lines = []
        for line in lines:
            lower_line = line.strip().lower()
            # Clean up leading numbers/punctuation/spaces for matching (e.g. "12. Biography" -> "biography")
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

    # 4. Split into individual references
    # Common formats: 
    # [1] Authors...
    # 1. Authors...
    # Authors... (hanging indent - harder to detect in plain text string without coordinate analysis)
    
    # We will try a few regex strategies.
    
    # Strategy A: Bracketed numbers [1], [2], etc.
    if re.search(r'^\s*\[\d+\]', full_ref_text, re.MULTILINE):
        # Split by lookahead for [n] at the start of a line
        refs = re.split(r'(?=(?:\r?\n|\r|^)\s*\[\d+\])', full_ref_text)
        refs = [prune_trailing_garbage(r) for r in refs]
        # Filter out empty or whitespace only strings
        refs = [heal_hyphens(r.strip()).replace('\n', ' ') for r in refs if r.strip()]
        # Filter out the header if it got caught (usually handled by block logic, but good safety)
        refs = [r for r in refs if len(r) > 10]
        return refs

    # Strategy B: Numbered 1., 2.
    # Need to be careful not to split on "Vol. 1."
    if re.search(r'^\s*1\.\s+', full_ref_text, re.MULTILINE):
        refs = re.split(r'(?=(?:\r?\n|\r|^)\s*\d+\.\s+)', full_ref_text)
        refs = [prune_trailing_garbage(r) for r in refs]
        refs = [heal_hyphens(r.strip()).replace('\n', ' ') for r in refs if r.strip()]
        refs = [r for r in refs if len(r) > 10]
        return refs

    # Strategy C: Fallback — use ref_content which has already had the termination
    # boundary applied (appendix, acknowledgements, etc. are excluded).
    # Many PDFs use one block per paragraph/reference.
    raw_refs = []
    for block_text in ref_content:
        pruned_block = prune_trailing_garbage(block_text)
        text = heal_hyphens(pruned_block).replace('\n', ' ')
        if len(text) > 20:  # arbitrary filter for "real" ref
            raw_refs.append(text)

    return raw_refs

