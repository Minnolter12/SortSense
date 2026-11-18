"""
SortSense proposals: the approval-first layer between analysis and file moves.

A Proposal is *only a suggestion*. Nothing touches the filesystem until the user
approves it and ``ProposalManager.execute_approved`` is called. Execution goes
through SafeFileExecutor, so path validation, collision safety, history and Undo
all apply. Pure Python: no Tk, no Ollama.
"""
from __future__ import annotations

import itertools
import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from app.config import settings
from app.intent.path_validator import PathValidator

if TYPE_CHECKING:
    from app.analysis_models import DocumentAnalysis
    from app.document import NormalizedDocument
    from app.intent.executor import SafeFileExecutor

logger = logging.getLogger(__name__)

PENDING, APPROVED, REJECTED, EXECUTED, FAILED = "pending", "approved", "rejected", "executed", "failed"

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MAX_STEM = 80
_ids = itertools.count(1)


def clean_folder_name(raw: str, fallback: str = "") -> str:
    """Folder name safe for Windows, spaces preserved ('Discrete Mathematics')."""
    name = _ILLEGAL.sub("", (raw or "").replace("..", "")).strip(" .")
    name = re.sub(r"\s+", " ", name)
    if name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        name = f"safe_{name}"
    return name or fallback


def clean_filename(raw: str, original_name: str) -> str:
    """Safe filename that always keeps the original file's extension."""
    ext = Path(original_name).suffix
    base = (raw or "").strip()
    if ext and base.lower().endswith(ext.lower()):
        base = base[: -len(ext)]
    base = _ILLEGAL.sub("", base.replace("..", ""))
    base = re.sub(r"\s+", "_", base).strip("._ ")[:_MAX_STEM].rstrip("._ ")
    if not base or base.upper() in {"CON", "PRN", "AUX", "NUL"}:
        return original_name
    return f"{base}{ext}"


@dataclass
class Proposal:
    source_path: Path
    original_name: str
    proposed_name: str
    category: str
    destination_dir: Path | None          # None => user must choose a destination
    confidence: float
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    engine: str = "deterministic"
    needs_review: bool = True
    status: str = PENDING
    error: str | None = None
    operation_id: str | None = None
    executed_path: Path | None = None
    id: int = field(default_factory=lambda: next(_ids))

    @property
    def renamed(self) -> bool:
        return self.proposed_name != self.original_name


def build_proposal(
    document: "NormalizedDocument",
    analysis: "DocumentAnalysis",
    base_dir: Path | None = None,
    threshold: float | None = None,
    override: tuple[Path, str, str] | None = None,
) -> Proposal:
    """
    Turn an analysis into a Proposal. Never invents a category: weak or missing
    evidence keeps the original filename and leaves the destination for the user.

    override = (destination_dir, filename, rule_name) from a saved user rule.
    """
    from app.validation import validate_analysis

    base = Path(base_dir or settings.sorted_base_dir)
    thr = settings.confidence_threshold if threshold is None else threshold
    source = Path(document.file_path)
    warnings: list[str] = []
    evidence = list(analysis.evidence or [])
    engine = analysis.source or "deterministic"

    val = validate_analysis(document, analysis)
    for issue in val.issues:
        warnings.append(f"Validation: {issue}")

    uncertain = (
        analysis.category.strip().lower() in {"", "general"}
        or analysis.document_type == "Unclassified"
        or analysis.confidence < 0.35
        or document.extraction_status != "ok"
    )
    if document.extraction_status != "ok":
        warnings.append(f"Could not read content ({document.extraction_status}); original name kept.")

    if override is not None:
        dest, fname, rule_name = override
        evidence.append(f"Matched saved rule '{rule_name}'")
        proposal = Proposal(source, source.name, clean_filename(fname, source.name), analysis.category or "Rule",
                            Path(dest), analysis.confidence, evidence, warnings, engine)
    elif uncertain:
        warnings.append("Not confident enough to suggest a category - choose a destination yourself.")
        proposal = Proposal(source, source.name, source.name, "Unclassified", None,
                            analysis.confidence, evidence, warnings, engine)
    else:
        category = clean_folder_name(analysis.category, "Unsorted")
        name = clean_filename(analysis.new_filename, source.name) if val.valid or not any(
            "new_filename" in i for i in val.issues) else source.name
        proposal = Proposal(source, source.name, name, category, base / category,
                            analysis.confidence, evidence, warnings, engine)

    if analysis.confidence < thr:
        proposal.warnings.append(f"Confidence {analysis.confidence:.2f} is below the review threshold {thr:.2f}.")
    proposal.needs_review = bool(val.issues) or analysis.confidence < thr or proposal.destination_dir is None
    if proposal.destination_dir is not None and (proposal.destination_dir / proposal.proposed_name).exists():
        proposal.warnings.append("A file with this name already exists there; a numbered copy will be created.")
    return proposal


class ProposalManager:
    """Holds proposals, applies user edits, executes only approved ones."""

    def __init__(self, executor: "SafeFileExecutor | None" = None, base_dir: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._items: dict[int, Proposal] = {}
        self._executor = executor
        self.base_dir = Path(base_dir or settings.sorted_base_dir)

    # -- queue ---------------------------------------------------------------
    def add(self, proposal: Proposal) -> Proposal:
        with self._lock:
            for old in list(self._items.values()):
                if old.source_path == proposal.source_path and old.status in (PENDING, APPROVED):
                    del self._items[old.id]
            self._items[proposal.id] = proposal
            return proposal

    def get(self, pid: int) -> Proposal | None:
        with self._lock:
            return self._items.get(pid)

    def items(self, status: str | None = None) -> list[Proposal]:
        with self._lock:
            return [p for p in self._items.values() if status is None or p.status == status]

    def counts(self) -> dict[str, int]:
        with self._lock:
            out = {s: 0 for s in (PENDING, APPROVED, REJECTED, EXECUTED, FAILED)}
            for p in self._items.values():
                out[p.status] += 1
            return out

    def remove(self, pid: int) -> None:
        with self._lock:
            self._items.pop(pid, None)

    # -- user edits ----------------------------------------------------------
    def set_name(self, pid: int, name: str) -> Proposal:
        with self._lock:
            p = self._require_open(pid)
            p.proposed_name = clean_filename(name, p.original_name)
            return p

    def set_destination(self, pid: int, directory: str | Path) -> Proposal:
        with self._lock:
            p = self._require_open(pid)
            res = PathValidator.validate_destination_path(directory)
            if not res.valid:
                raise ValueError("; ".join(res.issues))
            p.destination_dir = res.resolved_path
            p.category = res.resolved_path.name or p.category
            p.needs_review = False if p.confidence >= settings.confidence_threshold else p.needs_review
            return p

    def set_category(self, pid: int, category: str) -> Proposal:
        """Change the category; destination becomes <base>/<category>."""
        folder = clean_folder_name(category)
        if not folder:
            raise ValueError("Category cannot be empty.")
        with self._lock:
            p = self._require_open(pid)
            p.category = folder
            p.destination_dir = self.base_dir / folder
            return p

    def approve(self, pid: int) -> Proposal:
        with self._lock:
            p = self._require_open(pid)
            if p.destination_dir is None:
                raise ValueError("Choose a destination folder before approving.")
            p.status = APPROVED
            return p

    def reject(self, pid: int) -> Proposal:
        """Rejected files are never touched."""
        with self._lock:
            p = self._require_open(pid)
            p.status = REJECTED
            return p

    def approve_many(self, pids: list[int]) -> tuple[list[int], dict[int, str]]:
        done: list[int] = []
        errors: dict[int, str] = {}
        for pid in pids:
            try:
                self.approve(pid)
                done.append(pid)
            except ValueError as exc:
                errors[pid] = str(exc)
        return done, errors

    def _require_open(self, pid: int) -> Proposal:
        p = self._items.get(pid)
        if p is None:
            raise KeyError(f"Unknown proposal {pid}")
        if p.status == EXECUTED:
            raise ValueError("Proposal already executed.")
        return p

    # -- execution -----------------------------------------------------------
    def execute_approved(self, ids: list[int] | None = None) -> tuple[int, int, list[str]]:
        """Move ONLY approved proposals. Returns (succeeded, failed, errors)."""
        if self._executor is None:
            from app.intent.executor import SafeFileExecutor
            self._executor = SafeFileExecutor()
        ok = bad = 0
        errors: list[str] = []
        with self._lock:
            targets = [p for p in self._items.values()
                       if p.status == APPROVED and (ids is None or p.id in ids)]
        for p in targets:
            try:
                if p.destination_dir is None:
                    raise ValueError("No destination chosen.")
                record = self._executor.execute_move(
                    p.source_path, Path(p.destination_dir), p.proposed_name, mode_name="approved")
                p.status, p.operation_id = EXECUTED, record.operation_id
                p.executed_path = Path(record.destination_path)
                ok += 1
            except Exception as exc:  # partial failure: keep going, report it
                p.status, p.error = FAILED, str(exc)
                errors.append(f"{p.original_name}: {exc}")
                bad += 1
        return ok, bad, errors
