"""
Regression tests for the approval-first, deterministic (no Ollama) workflow.

No test here needs Ollama, the network, or a display. Gemma is mocked.
Documents are generic fixtures; nothing is keyed on their file names.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.analyzer import OllamaServiceManager, deterministic_analyze_document, safe_analyze_document
from app.document import NormalizedDocument
from app.ingestion import ingest_file
from app.intent.executor import HistoryManager, SafeFileExecutor
from app.pipeline import is_partial_download, process_file, wait_until_stable
from app.proposals import APPROVED, EXECUTED, FAILED, PENDING, REJECTED, ProposalManager

FIXTURES = Path(__file__).parent / "fixtures" / "regression_docs"

# What each fixture document is about (judged from its content, used only as test oracle)
EXPECTED = {
    "164729": "DSA", "592638": "DSA", "830174": "DSA",
    "219765": "Discrete Mathematics", "374192": "Discrete Mathematics", "806531": "Discrete Mathematics",
    "295841": "DBMS", "483920": "DBMS", "716305": "DBMS",
    "407216": "OOPS", "628450": "OOPS", "951083": "OOPS",
}
# Realistic opaque download names, mixed extensions (content is identical, only the name differs)
OPAQUE = [
    "DOC-WA0879845", "WhatsApp Document 2026-11-12", "download_3", "DOC-WA0926714",
    "assignment_final", "IMG-WA0048217", "Notes_28112026", "DOC-WA0765319",
    "WhatsApp Document 2026-11-15", "file (7)", "scan001", "new_document",
]


@pytest.fixture(autouse=True)
def no_ollama(monkeypatch):
    """Everything here must work with Ollama absent."""
    OllamaServiceManager.reset()
    monkeypatch.setattr(OllamaServiceManager, "is_available", classmethod(lambda cls, timeout=0.5: False))
    yield
    OllamaServiceManager.reset()


def make_pdf(path: Path, pages: list[list[str]]) -> None:
    """Write a tiny valid text PDF (no third-party library needed)."""
    objs: list[bytes] = []
    n_pages = len(pages)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n_pages))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    font_id = 3 + 2 * n_pages
    for i, lines in enumerate(pages):
        content_id = 4 + 2 * i
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode())
        text = "BT /F1 12 Tf 50 740 Td 16 TL " + " ".join(
            f"({ln.replace('(', '[').replace(')', ']')}) Tj T*" for ln in lines) + " ET"
        objs.append(f"<< /Length {len(text)} >>\nstream\n{text}\nendstream".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    path.write_bytes(out)


def stage_twelve(downloads: Path) -> dict[str, str]:
    """Copy the 12 fixtures into a 'Downloads' folder under opaque names. Returns name -> expected subject."""
    downloads.mkdir(parents=True, exist_ok=True)
    mapping = {}
    for (num, subject), opaque in zip(EXPECTED.items(), OPAQUE):
        src = FIXTURES / f"{num}.txt"
        text = src.read_text(encoding="utf-8")
        if opaque.startswith(("DOC-WA", "IMG-WA", "download", "scan")):
            dest = downloads / f"{opaque}.pdf"
            make_pdf(dest, [text.splitlines()[:3], text.splitlines()[3:]])  # multi-page PDF
        elif opaque.startswith("Notes"):
            dest = downloads / f"{opaque}.md"
            dest.write_text("# " + text, encoding="utf-8")
        else:
            dest = downloads / f"{opaque}.txt"
            shutil.copy(src, dest)
        mapping[dest.name] = subject
    return mapping


# ---------------------------------------------------------------------------
# The 12-file scenario, end to end
# ---------------------------------------------------------------------------

class TestTwelveFileScenario:
    def test_classification_titles_and_nothing_moves_before_approval(self, tmp_path):
        downloads, sorted_dir = tmp_path / "Downloads", tmp_path / "Sorted"
        mapping = stage_twelve(downloads)
        before = sorted(p.name for p in downloads.iterdir())

        proposals = {}
        for name, subject in mapping.items():
            prop = process_file(downloads / name, base_dir=sorted_dir, wait=False)
            assert prop is not None, name
            proposals[name] = prop
            assert prop.category == subject, f"{name}: {prop.category} != {subject} ({prop.evidence})"
            assert prop.proposed_name != name, "should be renamed from content"
            assert prop.proposed_name.endswith(Path(name).suffix), "extension must be preserved"
            assert prop.evidence, "reasons must be shown"
            assert prop.destination_dir == sorted_dir / subject

        # Nothing moved, nothing created
        assert sorted(p.name for p in downloads.iterdir()) == before
        assert not sorted_dir.exists()

    def test_full_flow_approve_execute_history_undo(self, tmp_path):
        downloads, sorted_dir = tmp_path / "Downloads", tmp_path / "Sorted"
        mapping = stage_twelve(downloads)
        history = HistoryManager(history_file=tmp_path / "history.json")
        mgr = ProposalManager(SafeFileExecutor(history), base_dir=sorted_dir)
        for name in mapping:
            mgr.add(process_file(downloads / name, base_dir=sorted_dir, wait=False))

        assert mgr.counts()[PENDING] == 12 and mgr.counts()[EXECUTED] == 0
        done, errors = mgr.approve_many([p.id for p in mgr.items()])
        assert len(done) == 12 and not errors
        ok, bad, errs = mgr.execute_approved()
        assert (ok, bad, errs) == (12, 0, [])
        assert mgr.counts()[EXECUTED] == 12

        for subject in ("DBMS", "DSA", "OOPS", "Discrete Mathematics"):
            assert len(list((sorted_dir / subject).iterdir())) == 3, subject
        assert list(downloads.iterdir()) == []

        records = history.get_history()
        assert len(records) == 12 and all(r.can_undo for r in records)

        undo = SafeFileExecutor(history)
        for rec in records:
            ok, msg = undo.undo_operation(rec.operation_id)
            assert ok, msg
        assert sorted(p.name for p in downloads.iterdir()) == sorted(mapping)  # original names restored


# ---------------------------------------------------------------------------
# User control
# ---------------------------------------------------------------------------

class TestUserControl:
    def _setup(self, tmp_path, n=3):
        downloads, sorted_dir = tmp_path / "Downloads", tmp_path / "Sorted"
        downloads.mkdir()
        mgr = ProposalManager(SafeFileExecutor(HistoryManager(tmp_path / "h.json")), base_dir=sorted_dir)
        names = []
        for i, num in enumerate(list(EXPECTED)[:n]):
            f = downloads / f"DOC-{i}.txt"
            shutil.copy(FIXTURES / f"{num}.txt", f)
            names.append(f)
            mgr.add(process_file(f, base_dir=sorted_dir, wait=False))
        return downloads, sorted_dir, mgr

    def test_edit_name_destination_and_category(self, tmp_path):
        downloads, sorted_dir, mgr = self._setup(tmp_path, 1)
        p = mgr.items()[0]
        mgr.set_name(p.id, "My Graph Notes")
        assert p.proposed_name == "My_Graph_Notes.txt"
        custom = tmp_path / "Competitive Programming"
        mgr.set_destination(p.id, custom)
        mgr.approve(p.id)
        ok, bad, _ = mgr.execute_approved()
        assert (ok, bad) == (1, 0)
        assert (custom / "My_Graph_Notes.txt").exists()

    def test_changing_category_changes_destination(self, tmp_path):
        _, sorted_dir, mgr = self._setup(tmp_path, 1)
        p = mgr.items()[0]
        mgr.set_category(p.id, "Semester 3")
        assert p.destination_dir == sorted_dir / "Semester 3"

    def test_rejected_untouched_and_only_selected_executed(self, tmp_path):
        downloads, sorted_dir, mgr = self._setup(tmp_path, 3)
        a, b, c = mgr.items()
        mgr.approve(a.id)
        mgr.reject(b.id)               # c stays pending
        ok, bad, _ = mgr.execute_approved()
        assert (ok, bad) == (1, 0)
        assert b.source_path.exists() and c.source_path.exists() and not a.source_path.exists()
        counts = mgr.counts()
        assert counts[EXECUTED] == 1 and counts[REJECTED] == 1 and counts[PENDING] == 1

    def test_pending_is_not_counted_as_executed(self, tmp_path):
        _, _, mgr = self._setup(tmp_path, 2)
        assert mgr.counts()[EXECUTED] == 0
        mgr.approve(mgr.items()[0].id)
        assert mgr.counts()[EXECUTED] == 0  # approved is still not executed

    def test_unapproved_never_executes(self, tmp_path):
        downloads, _, mgr = self._setup(tmp_path, 2)
        assert mgr.execute_approved() == (0, 0, [])
        assert len(list(downloads.iterdir())) == 2


# ---------------------------------------------------------------------------
# Uncertain / empty / unsupported
# ---------------------------------------------------------------------------

class TestUncertainDocuments:
    def test_empty_file_keeps_name_and_requires_manual_destination(self, tmp_path):
        f = tmp_path / "blank.txt"
        f.write_text("", encoding="utf-8")
        prop = process_file(f, base_dir=tmp_path / "S", wait=False)
        assert prop.proposed_name == "blank.txt" and prop.destination_dir is None and prop.needs_review
        mgr = ProposalManager(SafeFileExecutor(HistoryManager(tmp_path / "h.json")), base_dir=tmp_path / "S")
        mgr.add(prop)
        with pytest.raises(ValueError):
            mgr.approve(prop.id)
        mgr.set_destination(prop.id, tmp_path / "Mine")
        mgr.approve(prop.id)
        assert mgr.execute_approved()[0] == 1
        assert (tmp_path / "Mine" / "blank.txt").exists()

    def test_unrelated_text_gets_no_invented_category(self, tmp_path):
        f = tmp_path / "x1.txt"
        f.write_text("Grandma's banana bread recipe: mix flour, sugar and bananas, then bake for an hour.", encoding="utf-8")
        prop = process_file(f, base_dir=tmp_path / "S", wait=False)
        assert prop.destination_dir is None and prop.category == "Unclassified"
        assert prop.proposed_name == "x1.txt"

    def test_mixed_subject_is_ambiguous_not_forced(self):
        doc = _doc("mix.txt", "Notes on graph and tree traversal. Also relations and sets.")
        a = deterministic_analyze_document(doc)
        assert a.confidence < 0.85  # never auto-confident on thin/mixed evidence

    def test_unsupported_extension_is_ignored(self, tmp_path):
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"\xff\xd8\xff")
        assert process_file(f, wait=False) is None


def _doc(name, text, status="ok", ext="txt"):
    return NormalizedDocument(file_path=f"/tmp/{name}", file_name=name, extension=ext,
                              content_type="text/plain", text=text, character_count=len(text),
                              page_count=None, extraction_status=status)


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

class TestIngestion:
    def test_multipage_pdf_text_reaches_analyzer(self, tmp_path):
        f = tmp_path / "DOC-WA0001.pdf"
        make_pdf(f, [["DATABASE NORMALIZATION", "1NF 2NF 3NF"], ["functional dependency and candidate key"]])
        doc = ingest_file(f)
        assert doc.extraction_status == "ok" and doc.page_count == 2
        assert "functional dependency" in doc.text.lower()
        assert deterministic_analyze_document(doc).category == "DBMS"

    def test_blank_pdf_is_empty_not_crash(self, tmp_path):
        f = tmp_path / "scan.pdf"
        make_pdf(f, [[]])
        assert ingest_file(f).extraction_status == "empty"

    def test_malformed_pdf_is_error_not_crash(self, tmp_path):
        f = tmp_path / "broken.pdf"
        f.write_bytes(b"%PDF-1.4 this is not really a pdf")
        assert ingest_file(f).extraction_status in ("error", "empty")

    def test_text_encodings(self, tmp_path):
        (tmp_path / "a.txt").write_bytes("caf\u00e9 \u2013 notes".encode("utf-8-sig"))
        (tmp_path / "b.txt").write_bytes("caf\u00e9 notes".encode("cp1252"))
        (tmp_path / "c.txt").write_bytes("hello world".encode("utf-16"))
        for n in "abc":
            doc = ingest_file(tmp_path / f"{n}.txt")
            assert doc.extraction_status == "ok" and "notes" in doc.text or "hello" in doc.text

    def test_markdown_headings_and_code_blocks_kept(self, tmp_path):
        f = tmp_path / "n.md"
        f.write_text("# Binary Search Tree\n\n```python\nclass Node: pass\n```\nInorder traversal, subtree, time complexity.\n", encoding="utf-8")
        doc = ingest_file(f)
        assert "# Binary Search Tree" in doc.text and "class Node" in doc.text
        assert deterministic_analyze_document(doc).category == "DSA"

    def test_long_document_not_truncated_by_ingestion(self, tmp_path):
        f = tmp_path / "big.txt"
        f.write_text("filler line\n" * 20000 + "the end", encoding="utf-8")
        assert ingest_file(f).text.endswith("the end")


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------

class TestSafety:
    def _mgr(self, tmp_path):
        return ProposalManager(SafeFileExecutor(HistoryManager(tmp_path / "h.json")), base_dir=tmp_path / "S")

    def _prop(self, tmp_path, name="a.txt", text="x"):
        f = tmp_path / name
        f.write_text(text, encoding="utf-8")
        mgr = self._mgr(tmp_path)
        return mgr, mgr.add(process_file(f, base_dir=tmp_path / "S", wait=False))

    def test_traversal_destination_rejected(self, tmp_path):
        mgr, p = self._prop(tmp_path)
        with pytest.raises(ValueError):
            mgr.set_destination(p.id, str(tmp_path / "S" / ".." / ".." / "etc"))

    def test_reserved_and_illegal_names_sanitized(self, tmp_path):
        mgr, p = self._prop(tmp_path)
        mgr.set_name(p.id, "../../evil<>:|?.txt")
        assert "/" not in p.proposed_name and ".." not in p.proposed_name and p.proposed_name.endswith(".txt")
        mgr.set_name(p.id, "CON")
        assert p.proposed_name.upper() != "CON.TXT" or p.proposed_name == "a.txt"
        mgr.set_category(p.id, "NUL")
        assert p.destination_dir.name.upper() != "NUL"

    def test_name_collision_never_overwrites(self, tmp_path):
        dest = tmp_path / "Out"
        dest.mkdir()
        (dest / "a.txt").write_text("existing", encoding="utf-8")
        mgr, p = self._prop(tmp_path, text="new")
        mgr.set_destination(p.id, dest)
        mgr.set_name(p.id, "a.txt")
        mgr.approve(p.id)
        assert mgr.execute_approved()[0] == 1
        assert (dest / "a.txt").read_text(encoding="utf-8") == "existing"
        assert (dest / "a_1.txt").read_text(encoding="utf-8") == "new"

    def test_partial_failure_is_reported_and_others_proceed(self, tmp_path):
        mgr = self._mgr(tmp_path)
        files = []
        for i in range(3):
            f = tmp_path / f"f{i}.txt"
            f.write_text(f"doc {i}", encoding="utf-8")
            pr = mgr.add(process_file(f, base_dir=tmp_path / "S", wait=False))
            mgr.set_destination(pr.id, tmp_path / "Out")
            mgr.approve(pr.id)
            files.append(f)
        files[1].unlink()  # vanishes before execution
        ok, bad, errors = mgr.execute_approved()
        assert (ok, bad) == (2, 1) and len(errors) == 1
        assert mgr.counts()[FAILED] == 1 and mgr.counts()[EXECUTED] == 2

    def test_long_names_are_truncated(self, tmp_path):
        mgr, p = self._prop(tmp_path)
        mgr.set_name(p.id, "x" * 400)
        assert len(p.proposed_name) <= 90


# ---------------------------------------------------------------------------
# Engine honesty / Gemma (mocked)
# ---------------------------------------------------------------------------

class TestEngineStatus:
    def test_not_installed_is_deterministic(self, monkeypatch):
        import app.analyzer as az
        monkeypatch.setattr(az, "OLLAMA_INSTALLED", False)
        assert OllamaServiceManager.engine_state()[0] == "deterministic"

    def test_states(self, monkeypatch):
        import app.analyzer as az
        monkeypatch.setattr(az, "OLLAMA_INSTALLED", True)
        monkeypatch.setattr(az, "ollama", MagicMock())
        cases = [((False, False, ""), "ollama_unavailable"), ((True, False, ""), "model_missing"),
                 ((True, True, ""), "gemma_active")]
        for ret, expected in cases:
            OllamaServiceManager.reset()
            monkeypatch.setattr(OllamaServiceManager, "check_service_status",
                                classmethod(lambda cls, model_name=None, timeout=0.5, r=ret: r))
            assert OllamaServiceManager.engine_state()[0] == expected
        OllamaServiceManager.mark_request_failed("boom")
        assert OllamaServiceManager.engine_state()[0] == "request_failed"

    def _gemma(self, monkeypatch, content):
        import app.analyzer as az
        monkeypatch.setattr(OllamaServiceManager, "is_available", classmethod(lambda cls, timeout=0.5: True))
        client = MagicMock()
        client.chat.return_value.message.content = content
        monkeypatch.setattr(az, "_make_client", lambda: client)

    def test_valid_gemma_response_is_labelled_gemma(self, monkeypatch):
        good = {"document_type": "Notes", "category": "DBMS", "new_filename": "ACID.txt", "summary": "s",
                "confidence": 0.95, "suggested_action": "Archive"}
        self._gemma(monkeypatch, json.dumps(good))
        assert safe_analyze_document(_doc("q.txt", "some text")).source == "gemma"

    @pytest.mark.parametrize("bad", ["", "not json {", '{"category": 1}'])
    def test_bad_gemma_output_falls_back_and_is_not_labelled_gemma(self, monkeypatch, bad):
        self._gemma(monkeypatch, bad)
        a = safe_analyze_document(_doc("q.txt", "Database normalization 1NF 2NF 3NF functional dependency"))
        assert a.source == "deterministic" and a.category == "DBMS"

    def test_gemma_exception_falls_back(self, monkeypatch):
        import app.analyzer as az
        monkeypatch.setattr(OllamaServiceManager, "is_available", classmethod(lambda cls, timeout=0.5: True))
        client = MagicMock()
        client.chat.side_effect = TimeoutError("timed out")
        monkeypatch.setattr(az, "_make_client", lambda: client)
        assert safe_analyze_document(_doc("q.txt", "hello")).source == "deterministic"


# ---------------------------------------------------------------------------
# Watcher helpers
# ---------------------------------------------------------------------------

class TestWatcherHelpers:
    def test_partial_downloads_ignored(self, tmp_path):
        for n in ("a.pdf.crdownload", "b.part", "c.tmp"):
            assert is_partial_download(tmp_path / n)
        f = tmp_path / "x.crdownload"
        f.write_text("data", encoding="utf-8")
        assert process_file(f, wait=False) is None
        assert not is_partial_download(tmp_path / "ok.pdf")

    def test_stable_file_detected(self, tmp_path):
        f = tmp_path / "s.txt"
        f.write_text("done", encoding="utf-8")
        assert wait_until_stable(f, checks=2, interval=0.01, timeout=2)
        assert not wait_until_stable(tmp_path / "missing.txt", checks=2, interval=0.01, timeout=1)
