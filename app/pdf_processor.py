import fitz  # PyMuPDF
import re

def heal_hyphens(text):
    """
    Joins words that were split across PDF lines with a hyphen.
    E.g. 'be-\nhaviors' -> 'behaviors', 'multi-\ntarget' -> 'multi-target'.
    Heuristic: if the part after the hyphen starts with a lowercase letter,
    it's a broken word; if it starts with uppercase it might be a real hyphen.
    """
    # Pattern: word-<newline>lowercase continuation -> join without hyphen
    text = re.sub(r'(\w)-\n([a-z])', r'\1\2', text)
    # Pattern: word- <space> lowercase continuation (space inserted before us)
    text = re.sub(r'(\w)-\s([a-z])', r'\1\2', text)
    return text

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
    for page in doc:
        page_height = page.rect.height
        margin = page_height * 0.10 # 10% margin for headers/footers
        
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
                    cleaned_blocks.append(b)
        all_blocks.extend(cleaned_blocks)

    doc.close()

    # 2. Find "References" or "Bibliography" section
    # We'll look for a block that contains *only* (or mostly) the header.
    # We iterate through blocks to find the split point.
    
    ref_start_index = -1
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
                    ref_start_index = i
                    break 
    
    if ref_start_index == -1:
        return [] # Could not find bibliography section

    # 3. Concatenate text until the end of references or a termination header
    ref_content = []
    termination_keywords = [
        "appendix", "appendices", "annex", "supplementary material", "supplemental material",
        "acknowledgment", "acknowledgments", "author contributions", "conflicts of interest",
        "biography", "index", "glossary", "appendice", "appendici", "ringraziamenti"
    ]
    
    for i in range(ref_start_index + 1, len(all_blocks)):
        block_text = all_blocks[i][4].strip()
        lower_text = block_text.lower()
        
        # Check if this block looks like a new header (potentially an appendix)
        if len(lower_text.split()) < 10:
            # Clean text check (normalizes out numbers, extra punct)
            clean_text = re.sub(r'[^a-z]', '', lower_text)
            if any(k.replace(' ', '') == clean_text for k in termination_keywords):
                print(f"  [DEBUG] Bibliography termination header found: '{block_text}'")
                break
            
            # Anchor detection: Starts with Appendix/Annex...
            if re.match(r'^(appendix|appendices|annex|acknowledgment|acknowledgments|supplement|appendice|appendici|ringraziamenti)\b', lower_text):
                print(f"  [DEBUG] Anchored termination header found: '{block_text}'")
                break

        ref_content.append(block_text)
        
    full_ref_text = "\n".join(ref_content)
    
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
        # Filter out empty or whitespace only strings
        refs = [heal_hyphens(r.strip()).replace('\n', ' ') for r in refs if r.strip()]
        # Filter out the header if it got caught (usually handled by block logic, but good safety)
        refs = [r for r in refs if len(r) > 10]
        return refs

    # Strategy B: Numbered 1., 2.
    # Need to be careful not to split on "Vol. 1."
    if re.search(r'^\s*1\.\s+', full_ref_text, re.MULTILINE):
        refs = re.split(r'(?=(?:\r?\n|\r|^)\s*\d+\.\s+)', full_ref_text)
        refs = [heal_hyphens(r.strip()).replace('\n', ' ') for r in refs if r.strip()]
        refs = [r for r in refs if len(r) > 10]
        return refs

    # Strategy C: Fallback - split by single newlines that look like new entries? 
    # Or just return blocks if they look like individual refs?
    # Many PDFs utilize one block per paragraph/ref.
    # Let's try to return blocks from the ref section if they are long enough.
    
    raw_refs = []
    for i in range(ref_start_index + 1, len(all_blocks)):
         text = heal_hyphens(all_blocks[i][4].strip()).replace('\n', ' ')
         if len(text) > 20: # arbitrary filter for "real" ref
             raw_refs.append(text)
             
    return raw_refs
