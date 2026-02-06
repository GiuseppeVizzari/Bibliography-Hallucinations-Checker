import fitz  # PyMuPDF
import re

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
        blocks = page.get_text("blocks")
        # clean blocks: remove blocks with no text or just whitespace
        cleaned_blocks = []
        for b in blocks:
            if b[6] == 0: # text block
                text = b[4].strip()
                if text:
                    cleaned_blocks.append(b)
        all_blocks.extend(cleaned_blocks)

    doc.close()

    # 2. Find "References" or "Bibliography" section
    # We'll look for a block that contains *only* (or mostly) the header.
    # We iterate through blocks to find the split point.
    
    ref_start_index = -1
    keywords = ["references", "bibliography", "works cited"]
    
    for i, block in enumerate(all_blocks):
        text = block[4].strip().lower()
        # Check if the block is a header (short length, contains keyword)
        if len(text.split()) < 5: 
            if any(k in text for k in keywords):
                # Potential match. 
                # Strict check: if it's just the word (plus maybe numbers/punctuation)
                clean_text = re.sub(r'[^a-zA-Z]', '', text)
                if any(k in clean_text for k in keywords):
                    ref_start_index = i
                    break 
    
    if ref_start_index == -1:
        return [] # Could not find bibliography section

    # 3. Concatenate all text after the header
    ref_content = []
    for i in range(ref_start_index + 1, len(all_blocks)):
        ref_content.append(all_blocks[i][4])
        
    full_ref_text = "\n".join(ref_content)
    
    # 4. Split into individual references
    # Common formats: 
    # [1] Authors...
    # 1. Authors...
    # Authors... (hanging indent - harder to detect in plain text string without coordinate analysis)
    
    # We will try a few regex strategies.
    
    # Strategy A: Bracketed numbers [1], [2], etc.
    if re.search(r'\[\d+\]', full_ref_text):
        # Split by lookahead for [n]
        refs = re.split(r'(?=\[\d+\])', full_ref_text)
        # Filter out empty or whitespace only strings
        refs = [r.strip().replace('\n', ' ') for r in refs if r.strip()]
        # Filter out the header if it got caught (usually handled by block logic, but good safety)
        refs = [r for r in refs if len(r) > 10] 
        return refs

    # Strategy B: Numbered 1., 2.
    # Need to be careful not to split on "Vol. 1."
    if re.search(r'^\s*1\.\s+', full_ref_text, re.MULTILINE):
        refs = re.split(r'(?=(?:\r?\n|\r|^)\s*\d+\.\s+)', full_ref_text)
        refs = [r.strip().replace('\n', ' ') for r in refs if r.strip()]
        refs = [r for r in refs if len(r) > 10]
        return refs

    # Strategy C: Fallback - split by single newlines that look like new entries? 
    # Or just return blocks if they look like individual refs?
    # Many PDFs utilize one block per paragraph/ref.
    # Let's try to return blocks from the ref section if they are long enough.
    
    raw_refs = []
    for i in range(ref_start_index + 1, len(all_blocks)):
         text = all_blocks[i][4].strip().replace('\n', ' ')
         if len(text) > 20: # arbitrary filter for "real" ref
             raw_refs.append(text)
             
    return raw_refs
