---
name: auto-skill-doi-extraction-testing
description: Comprehensive testing patterns for DOI extraction and healing with broken DOIs and edge cases
source: auto-skill
extracted_at: '2026-07-10T09:04:41.041Z'
---

# DOI Extraction Testing Patterns

When validating DOI extraction (`extract_doi_info`) and healing (`heal_doi`) functions, use this systematic test approach.

## Test cases to include

### 1. Complete DOI (no break)
```python
ref = "Smith, J. (2023). Title. DOI: 10.1234/abcd.5678"
doi, end = extract_doi_info(ref)
assert doi == "10.1234/abcd.5678"
healed, _ = heal_doi(doi, end, ref)
assert healed is None  # Complete DOI should not need healing
```

### 2. Broken DOI with space after `10.`
```python
ref = "Smith, J. (2023). Title. DOI: 10. 1234/abcd.5678"
doi, end = extract_doi_info(ref)
assert doi == "10."  # Partial DOI captured
healed, _ = heal_doi(doi, end, ref)
assert healed == "10.1234/abcd.5678"  # Reconstructed
```

### 3. Broken DOI with newline after `10.`
```python
ref = "Smith, J. (2023). Title. DOI: 10.\n1234/abcd.5678"
healed, _ = heal_doi("10.", end, ref)
assert healed == "10.1234/abcd.5678"
```

### 4. DOI with hyphens
```python
ref = "Doe, J. (2022). Title. DOI: 10.1016/j.ssci.2023.106174"
assert doi == "10.1016/j.ssci.2023.106174"
```

### 5. DOI in URL form
```python
ref = "Jones, M. (2021). Title. https://doi.org/10.1371/journal.pone.0276229"
assert doi == "10.1371/journal.pone.0276229"
```

### 6. Broken DOI that cannot be healed (stop-word continuation)
```python
ref = "Brown, T. (2020). Title. DOI: 10. is a valid point"
healed, _ = heal_doi("10.", end, ref)
assert healed is None  # "is" is a stop word
```

### 7. No DOI in reference
```python
ref = "Wilson, R. (2019). Title. Journal of Testing, 15(3), 45-67."
assert doi is None
assert end == 0
```

### 8. DOI at start of reference
```python
ref = "DOI: 10.21105/joss.02770. Smith, J. (2023). Title."
assert doi == "10.21105/joss.02770"
```

### 9. DOI with special characters (semicolons, parentheses)
```python
ref = "Lee, K. (2024). Title. DOI: 10.1145/3543518.3583247"
assert doi == "10.1145/3543518.3583247"
```

## Common bug: trailing punctuation captured as part of DOI

The regex `10\.\d{4,9}/[-._;()/:a-zA-Z0-9]*` can capture trailing periods (e.g., `10.21105/joss.02770.`). Fix by stripping trailing punctuation:

```python
doi = match.group(0).rstrip('.,;)]')
return doi, match.end()
```

This must match the same punctuation set that `heal_doi()` strips from the extension.

## How to apply

1. Add a `test_doi_extraction()` function to the integration test file.
2. Include all 9 test cases above.
3. Run with `python test_integration.py` or `pytest test_integration.py -v`.
4. If any test fails, check whether the regex needs adjustment or whether trailing punctuation stripping is missing.
5. For broken DOI healing, verify `heal_doi()` correctly consumes whitespace + extension and rejects stop-word continuations.
