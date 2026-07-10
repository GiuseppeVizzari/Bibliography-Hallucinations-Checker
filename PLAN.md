# Plan of Action: Bibliography Extraction Fixes

## Issue Summary

Only 1 of 23 expected references extracted from `harnessing.pdf` page 8. The margin filter in `extract_bibliography()` discards large content blocks spanning most of the page height, which is exactly how reference blocks appear in many PDFs.

---

## P0: Fix margin filter to preserve large reference blocks

**File:** `app/pdf_processor.py`, line ~67

**Bug:** `if y0 < margin or y1 > (page_height - margin):` discards blocks whose bottom edge exceeds `page_height - 50`. On page 8 of `harnessing.pdf`, the reference block spans y=[84.1, 738.3] with page height 779.5, so y1=738.3 > 729.5 (779.5-50) and is discarded.

**Fix:** Add a block height heuristic. Blocks spanning >60% of page height are likely content, not marginalia:

```python
# In the block filtering loop:
block_height = y1 - y0
page_height = page.rect.height
height_ratio = block_height / page_height if page_height > 0 else 0

# Blocks spanning >60% of page height are content, not footers
if height_ratio > 0.6:
    # Keep this block regardless of vertical position
    pass
elif y0 < margin or y1 > (page_height - margin):
    continue
```

**Why 60%:** Reference blocks in PDFs often span most of the page. Footers are typically thin (<20% of page height). This ratio catches the reference block while still filtering actual footers.

**Verification:** Run `extract_bibliography('PDF for test/harnessing.pdf')` and confirm 23 references extracted.

---

## P1: Improve `heal_hyphens` for uppercase continuations

**File:** `app/checkers/normalizer.py`, `heal_hyphens()` function

**Current behavior:** Only joins hyphenated breaks where the continuation starts with `[a-z]`. Uppercase continuation (e.g., "Multi-\nTarget") is kept as-is.

**Fix:** Add a second pass for uppercase continuations, but with a stricter heuristic to avoid false positives on real hyphens (e.g., "state-of-the-art"):

```python
def heal_hyphens(text: str) -> str:
    # Pass 1: lowercase continuation (existing)
    text = re.sub(r'(\w)-\n([a-z])', r'\1\2', text)
    text = re.sub(r'(\w)-\s([a-z])', r'\1\2', text)
    
    # Pass 2: uppercase continuation — only if the result looks like a word break
    # Heuristic: capitalize the lowercase version and check if it's a known pattern
    # (e.g., PascalCase, camelCase, or Title Case in a reference)
    text = re.sub(r'(\w)-\n([A-Z])', r'\1\2', text)
    text = re.sub(r'(\w)-\s([A-Z])', r'\1\2', text)
    
    return text
```

**Risk:** May over-join real hyphens (e.g., "state-\nOf-the-art" → "stateOftheart"). Mitigate by testing against known references. If too aggressive, revert to lowercase-only and document the limitation.

---

## P2: Add fallback for reference blocks that span multiple pages

**File:** `app/pdf_processor.py`, after block collection

**Problem:** References can span multiple pages. The current code collects blocks after the bibliography header but has no mechanism to handle page breaks within the reference block itself.

**Fix:** After collecting blocks, detect gaps where a large block is interrupted by a page boundary:

```python
# After collecting ref_content blocks:
# Check for page gaps in consecutive blocks
i = 0
while i < len(ref_content) - 1:
    page_curr = all_blocks[ref_start_index + 1 + i][7]
    page_next = all_blocks[ref_start_index + 1 + i + 1][7]
    if page_next > page_curr + 1:
        # Gap detected — merge blocks across the gap
        # (skip the gap blocks and join text)
        pass
    i += 1
```

**Note:** This is lower priority than P0. If P0 fixes the single-block issue, multi-page references may already work since blocks from each page are collected separately and concatenated.

---

## P3: Validate DOI extraction with broken DOIs

**File:** `app/checkers/extraction.py`, `extract_doi_info()` and `heal_doi()`

**Current status:** DOI detection handles:
- Complete DOIs: `10.\d{4,9}/[-._;()/:a-zA-Z0-9]*`
- Partial DOIs with space: `10.\s+` prefix, extended by `heal_doi()`
- Hyphenated DOIs (via `heal_hyphens` before detection)

**Test:** Add a test case for a reference with a broken DOI (space after `10.`) to verify `heal_doi()` reconstructs it correctly.

```python
# Test case:
ref = "Smith, J. (2023). Title. DOI: 10. 1234/abcd.5678"
doi, end = extract_doi_info(ref)
healed, healed_end = heal_doi(doi, end, ref)
assert healed == "10.1234/abcd.5678"
```

---

## P4: Add integration test for `harnessing.pdf`

**File:** New test file or add to existing test suite

```python
def test_harnessing_pdf_extraction():
    refs = extract_bibliography('PDF for test/harnessing.pdf')
    assert len(refs) == 23
    assert any('10.' in ref for ref in refs)  # At least one has a DOI
```

This test serves as a regression guard for the P0 fix.

---

## Execution Order

1. **P0** — Fix margin filter (primary bug, highest impact)
2. **P4** — Add integration test (verifies P0)
3. **P1** — Improve `heal_hyphens` (secondary improvement)
4. **P3** — Validate DOI extraction (ensure no regressions)
5. **P2** — Multi-page fallback (only if needed after P0)

---

## Files Changed

| File | Change |
|------|--------|
| `app/pdf_processor.py` | Fix margin filter (P0), add multi-page fallback (P2) |
| `app/checkers/normalizer.py` | Improve `heal_hyphens` (P1) |
| `app/checkers/extraction.py` | No changes needed (DOI logic is sound) |
| Test suite | Add `harnessing.pdf` integration test (P4) |
