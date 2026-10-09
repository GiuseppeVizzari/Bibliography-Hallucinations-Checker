# Multi-Page Reference Block Merging

When extracting bibliographic references from PDFs, individual text blocks from PyMuPDF may span page boundaries — a single reference can have its first line on one page and continuation on the next. Without merging, these appear as separate, broken references.

## When to apply

- The PDF has references that span page boundaries (common in dense bibliographies).
- Reference blocks collected from consecutive PyMuPDF blocks have a page index gap (`page_next - page_curr > 1`).
- The bibliography section is already identified and you have the `ref_content` list plus access to the full `all_blocks` array with page indices.

## Approach

```python
# Given: ref_content (list of text strings from blocks after bibliography header)
# Given: ref_start_index (index in all_blocks where bibliography header was found)
# Given: all_blocks (list of (x0, y0, x1, y1, page_width, page_height, block_text, page_idx, ...))

merged_content = []
i = 0
while i < len(ref_content):
    block_idx = ref_start_index + 1 + i
    page_curr = all_blocks[block_idx][7] if block_idx < len(all_blocks) else -1

    if i + 1 < len(ref_content):
        block_idx_next = ref_start_index + 1 + (i + 1)
        page_next = all_blocks[block_idx_next][7] if block_idx_next < len(all_blocks) else -1
        page_gap = page_next - page_curr

        if page_gap > 1:
            # Gap detected: merge all intermediate blocks into one reference
            merged = ref_content[i]
            j = i + 1
            while j < len(ref_content):
                block_idx_j = ref_start_index + 1 + j
                page_j = all_blocks[block_idx_j][7] if block_idx_j < len(all_blocks) else -1
                if page_j == page_curr + 1:
                    break
                merged += "\n" + ref_content[j]
                j += 1
            merged_content.append(merged)
            i = j
            continue

    merged_content.append(ref_content[i])
    i += 1

ref_content = merged_content
```

## Key details

- **Page index location**: In the `all_blocks` tuple, page index is at position 7 (0-based). Verify this for your block format.
- **Gap threshold**: `page_gap > 1` means there's at least one intervening page. Adjust if your PDFs use different pagination.
- **Merge direction**: Blocks are merged left-to-right in collection order, joined with `\n`. The first block's text is the anchor.
- **Termination**: The inner loop stops when it finds a block on the next sequential page (`page_j == page_curr + 1`), meaning the gap is closed.
- **Safety**: Always bounds-check block indices against `len(all_blocks)` to avoid IndexError if the bibliography extends beyond available blocks.

## Verification

1. Run with debug logging: `logger.debug(f"  [DEBUG] After multi-page merge: {len(ref_content)} blocks")`
2. Compare pre-merge vs post-merge block counts — expect fewer blocks after merging.
3. Spot-check merged references in the output to confirm they form coherent entries.
4. Add a test case with a PDF known to have page-spanning references.

## Common pitfalls

- **Over-merging**: If two separate references happen to be on different pages but consecutive, they could be merged incorrectly. Mitigate by checking that the gap is truly a page boundary (not just a layout quirk).
- **Ordering dependency**: This only works if blocks are already sorted by page then position. Verify your block sorting pipeline before applying.
- **Non-bibliography sections**: Only apply this to the bibliography section, not the main text or appendix.
