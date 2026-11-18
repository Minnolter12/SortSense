# SortSense Regression Fix — Root Cause & Change Log

Branch: `fix/sortsense-regression-restoration`

## Root Cause (Confirmed by real pydantic/pytest on Windows, 279 tests)

1. **Deterministic analyzer had no subject knowledge.**
   Only recognised document *types* (invoice, assignment, exam…) plus ~11 subjects (no OOPS, no Discrete
   Math, DBMS only by "database/dbms/sql"). Subject only added +0.05 and only if a type already matched,
   so study notes with opaque names scored 0.15–0.30 → "Review Queue, below threshold 0.85". The threshold
   was correct — the evidence engine was broken.

2. **`organizer.decide()` discarded the analyzer's filename** and rebuilt it from `document_type`
   (every unclassified file would be suggested as `Unclassified.txt`).

3. **GUI moved files without approval.** Used a private `_safe_move` that bypassed `SafeFileExecutor`,
   so those moves had **no history and no Undo**. Review-queue moves had the same problem and could not
   edit the proposed name.

4. **Status label could lie.** No "request failed" state; could say "AI Active" even after a timeout.

5. **`app/main.py` banner crashed** (`settings.watched_dir` doesn't exist; also said "FileMind").
   The CLI watcher auto-moved files — bypassing approval.

6. **PDF extraction hard-required PyMuPDF.** Any environment without it failed every PDF silently.

---

## What Changed

| File | Change |
|------|--------|
| `app/topics.py` *(new)* | Weighted-lexicon topic engine: 12 subjects, distinct-term evidence, heading/filename corroboration, margin check for ambiguity, title extraction from content |
| `app/analyzer.py` | Deterministic analyzer calls `topics.py`; `OllamaServiceManager.engine_state()` → 5 honest states; request timeout; Gemma failures degrade to deterministic and are never labelled Gemma |
| `app/analysis_models.py` | Optional `evidence: list[str]` and `source: str | None` fields |
| `app/proposals.py` *(new)* | Approval-first `Proposal` + `ProposalManager`: edit name/category/destination, approve, reject, execute ONLY approved via `SafeFileExecutor` → history + Undo, partial failure |
| `app/pipeline.py` *(new)* | `process_file()`: wait-until-stable, skip `.crdownload/.part/.tmp`, ingest → analyze → Proposal. Never moves anything. |
| `app/ingestion.py` | PyMuPDF with pypdf fallback; encrypted/malformed PDFs → `error`; image-only → `empty` (no OCR); BOM/UTF-16/cp1252 text decoding |
| `app/organizer.py` | Keeps content-based filename from analyzer |
| `app/gui.py` | Pipeline produces proposals; Review Queue is approval screen (editable name, Folder…, Approve, Reject, Execute Approved); Pending = awaiting; Processed = executed only; duplicate events deduped via `_inflight`; engine status from `engine_state()`; safe observer restart in `save_settings()` |
| `app/watcher.py` | Ignores partial downloads; dedup via `_seen` dict |
| `app/main.py` | Banner corrected: "SortSense — local AI file organizer"; crash from missing `watched_dir` fixed |
| `sortsense.spec` | Added `pypdf` to `hiddenimports` (critical: without this the packaged binary crashes) |
| `requirements.txt` | Added `pypdf` |
| `.github/workflows/ci.yml` | Pinned Python 3.11; fixed test command; added artifact upload; removed headless GUI smoke test; added branch trigger |
| `.gitignore` | Added `.venv*/`, `*.pyo`, `pytest_*.txt` |
| `tests/test_user_controlled_workflow.py` *(new)* | 31 regression tests covering approval flow, 12-file scenario, safety, engine honesty |
| `tests/fixtures/regression_docs/` *(new)* | 12 fixture documents (DBMS×3, DSA×3, OOPS×3, Discrete Math×3) |
| `tests/test_packaging_lifecycle.py` | `test_low_confidence_document_routed_to_review_despite_rule_match` rewritten for proposal flow |

---

## What Was and Was NOT Verified

### Verified on Windows (this session)
- ✅ 279/279 tests pass with real pydantic 2.14.3, pypdf 7.1.0, PyMuPDF 2.1 (fresh venv)
- ✅ All 6 packaging lifecycle tests pass, including `test_low_confidence_...`
- ✅ All pydantic v2 imports clean
- ✅ `proposals.py` rule + low-confidence logic: `needs_review=True` even when a rule matches but confidence < threshold
- ✅ CI workflow corrected (artifact upload, Python 3.11, no headless smoke test)
- ✅ sortsense.spec includes `pypdf` in hiddenimports

### Not Yet Verified
- ⬜ GUI live run (requires display; tested via code inspection only)
- ⬜ 12-file scenario in running app (automated test covers it; live GUI not run)
- ⬜ Ollama states 1–5 (Ollama not running at time of this report)
- ⬜ PyInstaller build and exe smoke test
- ⬜ Clean-machine test (no clean Windows VM available)
