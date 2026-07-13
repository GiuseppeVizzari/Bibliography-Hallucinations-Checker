# Plan of Action: Bibliography Hallucinations Checker

> **Note:** This plan is archived. All items below have been completed.

## Completed Items

| Item | Description | Status |
|------|-------------|--------|
| P0 | Fix margin filter in `extract_bibliography()` to preserve large reference blocks | Done |
| P1 | Improve `heal_hyphens` for uppercase continuations | Done |
| P2 | Add fallback for reference blocks spanning multiple pages | Done (not needed after P0) |
| P3 | Validate DOI extraction with broken DOIs | Done |
| P4 | Add integration test for `harnessing.pdf` | Done |

## Upcoming Work

### L1 — Logging verbosity reorganization

**Goal:** Add configurable log levels so the default output shows, for each extracted reference, what happens in the pipeline — enough to make sense of negative (not_found) search results.

**Design: 3 levels**

| Level | Name | When to use | Example |
|-------|------|-------------|---------|
| `INFO` | **Pipeline progress** (default) | One entry per reference, showing the pipeline flow — which steps were tried, what each step found, and the final outcome | `→ Step 1: DOI lookup → not found`, `→ Step 5: Title search (OpenAlex) → found: "Deep Learning" (similarity 0.82)` |
| `DEBUG` | **Deep tracing** | Backend API calls, normalization details, DOI healing internals, similarity comparisons, rate-limit retries | `OpenAlex DOI lookup: 10.1234/abcd...`, `DOI healing: 10. 1371/ -> 10.1371/journal.pone.0276229` |
| `WARNING`/`ERROR` | **Problems** | Actual errors, unexpected failures, rate-limit exhaustion | `Rate-limited after 3 retries`, `OpenAlex API error: connection timeout` |

**Default log level:** `INFO` (not `DEBUG` as it is now). Users who want full tracing set `LOG_LEVEL=DEBUG`.

**Log format:** `%(levelname)s [%(asctime)s] %(name)s: %(message)s`

---

**Implementation plan:**

#### Step 1: `app/__init__.py` — Configurable log level
- Read `LOG_LEVEL` env var (default: `INFO`)
- Replace `logging.basicConfig(level=logging.DEBUG)` with the configured level
- Add `LOG_LEVEL` to `.env.example`

#### Step 2: `app/checkers/orchestrator.py` — Promote pipeline milestones to INFO
- `logger.debug(f"Checking reference...")` → `logger.info(f"Checking reference #{index}: {ref_text[:80]}...")`
  - Note: need to pass reference index from routes.py (or add a wrapper)
- `logger.debug(f"Found DOI: ...")` → `logger.info("  → Step 1 DOI: {doi}")`
- `_run_doi_search_cycle` result → log at INFO when found/not found
- `logger.debug(f"Found arXiv ID: ...")` → `logger.info("  → Step 3 arXiv: {id}")`
- URL checker result → log at INFO
- `logger.debug(f"Extracted title: ...")` → `logger.info("  → Step 5 Title: {title[:60]}...")`
- OpenAlex result → log at INFO with similarity
- DBLP result → log at INFO
- Web fallback result → log at INFO
- Final result → `logger.info("  → Result: {status} (source: {source}, similarity: {sim})")`

#### Step 3: `app/checkers/extraction.py` — Promote key milestones to INFO
- `heal_doi` success → `logger.info("  → DOI healed: {old} -> {new}")`
- DOI extraction → `logger.info("  → DOI found: {doi}")`
- arXiv extraction → `logger.info("  → arXiv ID: {id}")`
- Title extraction → `logger.info("  → Extracted title: {title[:60]}...")`

#### Step 4: Backend modules — Promote key results to INFO
Each backend currently logs everything at DEBUG. Promote:
- **DOI found** → `logger.info("  ✓ Found in {backend}: {title[:60]}...")`
- **DOI not found** → no log at INFO (silently continues to next step — this is expected behavior)
- **API errors** → `logger.warning("  ✗ {backend} error: {msg}")`
- **Rate-limit retry** → `logger.warning("  Rate-limited by {backend}. Retrying...")`

Backends to update:
- `app/checkers/backends/openalex.py`
- `app/checkers/backends/crossref.py`
- `app/checkers/backends/datacite.py`
- `app/checkers/backends/arxiv.py`
- `app/checkers/backends/dblp.py`
- `app/checkers/backends/url_checker.py`
- `app/checkers/backends/web_fallback.py`

#### Step 5: `app/checkers/config.py` — Promote rate-limit retry to WARNING
- `logger.debug(f"Rate-limited. Retrying...")` → `logger.warning(f"Rate-limited by {backend_name}. Retrying...")`

#### Step 6: `app/routes.py` — Add per-reference progress logging
- `_check_single_ref` already has `logger.info(f"[{index}/{total}]")` — keep this
- Add result summary logging at INFO level

#### Step 7: `app/pdf_processor.py` — Promote key milestones to INFO
- Bibliography section found → `logger.info("Bibliography section found: {N} references")`
- Block inclusion/skip decisions → keep at DEBUG (too verbose for INFO)

---

**Expected default (INFO) output for one reference:**
```
INFO [2026-07-13 10:00:01] app.routes: [1/5]
INFO [2026-07-13 10:00:01] app.checkers: Checking reference #1: "Smith et al., 2023. Deep Learning for Natural Language Processing..."
INFO [2026-07-13 10:00:01] app.checkers:   → DOI found: 10.1234/abc.def
INFO [2026-07-13 10:00:02] app.checkers.backends.openalex:   ✓ Found in OpenAlex (DOI): "Deep Learning for Natural Language Processing"
INFO [2026-07-13 10:00:02] app.checkers:   → Result: found (source: OpenAlex, similarity: 0.95)

INFO [2026-07-13 10:00:03] app.routes: [2/5]
INFO [2026-07-13 10:00:03] app.checkers: Checking reference #2: "Johnson, 2022. On the theory of..."
INFO [2026-07-13 10:00:03] app.checkers:   → Extracted title: "On the theory of stochastic processes"
INFO [2026-07-13 10:00:04] app.checkers.backends.openalex:   ✓ Found in OpenAlex (title): "On the theory of stochastic differential equations"
INFO [2026-07-13 10:00:04] app.checkers:   → Result: found (source: OpenAlex, similarity: 0.72)

INFO [2026-07-13 10:00:05] app.routes: [3/5]
INFO [2026-07-13 10:00:05] app.checkers: Checking reference #3: "Unknown author, 2021. Random paper..."
INFO [2026-07-13 10:00:05] app.checkers:   → Extracted title: "Random paper on obscure topics"
INFO [2026-07-13 10:00:06] app.checkers.backends.openalex:   Not found in OpenAlex (title)
INFO [2026-07-13 10:00:06] app.checkers.backends.dblp:   Not found in DBLP
INFO [2026-07-13 10:00:08] app.checkers.backends.web_fallback:   → Web search: no good match
INFO [2026-07-13 10:00:08] app.checkers:   → Result: not_found (source: none, similarity: 0.00)
```

**Expected DEBUG output (same reference, #3):**
Everything above, plus:
```
DEBUG [2026-07-13 10:00:05] app.checkers:   [DEBUG] DOI healing: 10. 1371/ -> 10.1371/journal.pone.0276229
DEBUG [2026-07-13 10:00:05] app.checkers.backends.openalex:   OpenAlex DOI lookup: 10.1371/journal.pone.0276229...
DEBUG [2026-07-13 10:00:06] app.checkers.backends.openalex:   - OpenAlex DOI error: 404 Not Found
DEBUG [2026-07-13 10:00:06] app.checkers:   [DEBUG] Similarity comparison:
DEBUG [2026-07-13 10:00:06] app.checkers:   [DEBUG]   Extracted title: 'Random paper on obscure topics'
DEBUG [2026-07-13 10:00:06] app.checkers:   [DEBUG]   Fetched title:   'Some other paper'
DEBUG [2026-07-13 10:00:06] app.checkers:   [DEBUG]   Score: 0.31
```

## Implemented: Logging verbosity reorganization (2026-07-13)

**Status: Done.** All 7 steps implemented.

### What changed

| File | Change |
|------|--------|
| `app/__init__.py` | `LOG_LEVEL` env var (default: INFO) replaces hardcoded DEBUG |
| `.env.example` | Added `LOG_LEVEL=INFO` with documentation |
| `app/checkers/orchestrator.py` | Promoted pipeline milestones to INFO: "Checking reference", "Step 1 DOI", "Step 2 DOI healed", "Step 3 arXiv", "Step 4 URL", "Step 5 Title", "Step 5b DBLP", "Step 6 Web search", "Result: found/not_found" |
| `app/pdf_processor.py` | INFO: bibliography found, blocks scanned, blocks collected, post-merge count, split strategy/result count. DEBUG: per-block decisions. WARNING: no bibliography header found |
| All backends | Remain at DEBUG — API calls, similarity scores, normalization details |

### INFO-level output (default)

For a typical PDF with 10 references:
```
Bibliography section found at block 142
Scanning 250 blocks after bibliography header...
Total blocks collected for bibliography: 45
After multi-page merge: 42 blocks
Split into 38 references (Strategy A: bracketed numbers)
============================================================
Processing 38 references
============================================================
[1/38]
  Checking reference: Smith et al., 2023: "Deep learning for..."
  → Step 1 DOI: 10.1234/abc.def
  ✓ Result: found (source: OpenAlex, similarity: 0.95)
[2/38]
  Checking reference: Johnson, 2022. On the theory of...
  → Step 5 Title: On the theory of stochastic processes
  → Step 5b DBLP
  → Step 6 Web search
  → Result: not_found
```

### DEBUG-level output (LOG_LEVEL=DEBUG)

Everything above, plus:
- Backend API call details (OpenAlex, Crossref, DataCite, arXiv, DBLP)
- DOI healing internals
- Per-block PDF extraction decisions (INCLUDE/SKIP/STOP)
- Similarity scores, normalization details
- Rate-limit retries

### WARNING/ERROR output

- WARNING: "Could not find bibliography section header" (pdf_processor)
- WARNING: "Title extraction failed" (orchestrator)
- ERROR: "Pipeline error" (orchestrator) — critical API failure

---

## Recent Work

- **AJAX form submission:** Added `X-Requested-With` header detection in `app/routes.py` to return JSON errors instead of HTTP 302 redirects for AJAX clients. This fixes the issue where error messages were silently lost during PDF upload.
- **Security hardening:** Centralized config, parallel processing, and input validation.
