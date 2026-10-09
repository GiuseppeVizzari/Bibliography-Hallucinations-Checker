---
name: auto-skill-pdf-extraction-debug
description: Debug and fix PDF bibliography/reference extraction issues including margin filters, hyphenation, and DOI detection
source: auto-skill
extracted_at: '2026-07-10T08:42:32.578Z'
---

# PDF Bibliography Extraction Debugging

When debugging PDF bibliography/reference extraction issues (missing references, broken words, failed DOI detection), follow this systematic approach:

## Step 1: Diagnose the primary extraction failure

1. **Count expected vs. extracted references** — Compare the PDF's actual bibliography section against what the code produces.
2. **Inspect the margin filter** — In `app/pdf_processor.py`, check the block filtering condition:
   ```python
   if y0 < margin or y1 > (page_height - margin):
       continue
   ```
3. **Check block coordinates against page dimensions** — For the affected page:
   - Get `page.rect.height`
   - Compute `page_height - margin` (typically `page_height - 50`)
   - Check if the reference block's `y1` exceeds this threshold
   - **Key insight:** Reference blocks often span 60-90% of page height. Footers are typically <20%. Use a height-ratio heuristic: blocks spanning >60% of page height are content, not marginalia.

## Step 2: Analyze `heal_hyphens` behavior

1. **Check the regex patterns** — Look for:
   - `r'(\w)-\n([a-z])'` — lowercase continuation (standard)
   - `r'(\w)-\s([a-z])'` — whitespace + lowercase continuation
2. **Identify the limitation** — Uppercase continuations (e.g., "Multi-\nTarget") are skipped, assuming real hyphens. This is intentional but imperfect.
3. **Assess impact** — If uppercase continuations are common in the target PDFs, add a second pass. If rare, document as a known limitation.

## Step 3: Verify DOI extraction pipeline

1. **Check `extract_doi_info()`** — Verify it handles:
   - Complete DOIs: `10.\d{4,9}/[-._;()/:a-zA-Z0-9]*`
   - Partial DOIs with space: `10.\s+` prefix (fallback)
2. **Check `heal_doi()`** — Verify it consumes whitespace + extension from `ref_text[end_pos:]` and strips trailing punctuation.
3. **Test broken DOIs** — Add a test case for DOIs with spaces after `10.` to ensure reconstruction works.

## Step 4: Write a prioritized action plan

Structure the plan as:

1. **P0: Primary fix** — The bug causing the most references to be lost (usually the margin filter)
2. **P4: Integration test** — A regression guard for the P0 fix
3. **P1: Secondary improvement** — E.g., `heal_hyphens` uppercase support
4. **P3: Validation** — Test edge cases (broken DOIs, etc.)
5. **P2: Edge case handling** — Multi-page references, etc.

Each item should include:
- **File** and **line** reference
- **Bug description** with concrete numbers (coordinates, page height, etc.)
- **Fix** with code snippet
- **Why** the fix works (rationale)
- **Verification** step

## Key debugging patterns

- **Margin filter bug:** When `y1 > (page_height - margin)` discards large content blocks, add a height-ratio check. Blocks spanning >60% of page height are content.
- **Hyphenation bug:** `heal_hyphens` only joins lowercase continuations. Uppercase continuations need a second pass with stricter heuristics to avoid false positives on real hyphens.
- **DOI bug:** Partial DOIs (e.g., "10. 1234/...") require the `heal_doi()` function to consume the whitespace + extension. Verify the fallback regex `r'(10\.)\s'` triggers correctly.
