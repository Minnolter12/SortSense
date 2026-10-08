"""
FileMind SQLite persistence layer.

Stores analyzed file records, review queue items, audit history, and extracted
document text for instant local semantic/keyword search.

Returns dictionaries formatted directly for the FileMind UI (`AnalyzedFile`,
`AuditEntry`, `SearchResult`, and `fileCategories`).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings


def extension_to_kind(ext: str) -> str:
    """Map a file extension to the UI's FileKind ('pdf' | 'image' | 'doc' | 'sheet' | 'archive')."""
    ext = ext.lstrip(".").lower()
    if ext == "pdf":
        return "pdf"
    if ext in ("png", "jpg", "jpeg", "webp", "bmp", "tiff", "gif", "svg"):
        return "image"
    if ext in ("xlsx", "xls", "csv"):
        return "sheet"
    if ext in ("zip", "tar", "gz", "rar", "7z"):
        return "archive"
    return "doc"


def format_file_size(num_bytes: int) -> str:
    """Format byte size into human-readable string (e.g. '184 KB', '2.4 MB')."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    kb = num_bytes / 1024.0
    if kb < 1024:
        return f"{int(round(kb))} KB"
    mb = kb / 1024.0
    return f"{mb:.1f} MB"


def format_relative_time(iso_ts: str) -> str:
    """Convert an ISO UTC timestamp into a friendly relative label ('Just now', '5 min ago')."""
    try:
        dt = datetime.fromisoformat(iso_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(tz=timezone.utc) - dt
        seconds = max(0, int(delta.total_seconds()))
        if seconds < 60:
            return "Just now"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} min ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours} hr ago"
        days = hours // 24
        return f"{days}d ago"
    except Exception:
        return "Recently"


class FileMindDatabase:
    """Lightweight SQLite store for analyzed files, review queue, audit log, and search."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or settings.db_path).resolve()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS analyzed_files (
                    id TEXT PRIMARY KEY,
                    original TEXT NOT NULL,
                    suggested TEXT NOT NULL,
                    original_path TEXT NOT NULL,
                    current_path TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    category TEXT NOT NULL,
                    subcategory TEXT NOT NULL,
                    confidence INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    doc_type TEXT NOT NULL,
                    topics_json TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    extracted_text TEXT NOT NULL,
                    size_label TEXT NOT NULL,
                    processed_in TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    file_id TEXT NOT NULL,
                    time_label TEXT NOT NULL,
                    day_label TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    confidence INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    action_label TEXT NOT NULL,
                    moved_to TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    def record_analyzed_file(
        self,
        *,
        original: str,
        suggested: str,
        original_path: str | Path,
        current_path: str | Path,
        extension: str,
        category: str,
        subcategory: str,
        confidence_float: float,
        status: str,
        action: str,
        doc_type: str,
        topics: list[str],
        reason: str,
        extracted_text: str,
        size_bytes: int,
        processed_seconds: float,
        file_id: str | None = None,
    ) -> dict[str, Any]:
        """Insert a processed file and its corresponding audit log entry."""
        fid = file_id or f"f_{uuid.uuid4().hex[:8]}"
        now = datetime.now(tz=timezone.utc)
        iso_now = now.isoformat()
        kind = extension_to_kind(extension)
        conf_pct = int(round(confidence_float * 100))
        size_label = format_file_size(size_bytes)
        processed_in = f"{max(0.1, processed_seconds):.1f}s"

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO analyzed_files (
                    id, original, suggested, original_path, current_path,
                    kind, category, subcategory, confidence, status,
                    doc_type, topics_json, reason, extracted_text,
                    size_label, processed_in, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fid,
                    original,
                    suggested,
                    str(original_path),
                    str(current_path),
                    kind,
                    category,
                    subcategory,
                    conf_pct,
                    status,
                    doc_type,
                    json.dumps(topics),
                    reason,
                    extracted_text,
                    size_label,
                    processed_in,
                    iso_now,
                ),
            )

        decision = (
            f"Classified as {category} / {subcategory}"
            if status == "organized"
            else f"Suggested {category} / {subcategory}"
        )
        action_labels = {
            "auto": "Automatically organized",
            "renamed": "Renamed & organized",
            "review": "Sent to Review Queue",
            "human-accept": "Accepted by you",
            "human-edit": f"Edited by you -> {category} / {subcategory}",
        }
        moved_to = str(Path(current_path).parent) if status in ("organized", "accepted") else None

        self.add_audit_entry(
            file_id=fid,
            file_name=original,
            kind=kind,
            decision=decision,
            confidence=conf_pct,
            action=action,
            action_label=action_labels.get(action, "Processed"),
            moved_to=moved_to,
        )

        return self.get_file(fid) or {}

    def add_audit_entry(
        self,
        *,
        file_id: str,
        file_name: str,
        kind: str,
        decision: str,
        confidence: int,
        action: str,
        action_label: str,
        moved_to: str | None = None,
    ) -> dict[str, Any]:
        """Insert an audit log record."""
        aid = f"a_{uuid.uuid4().hex[:8]}"
        now = datetime.now().astimezone()
        time_label = now.strftime("%I:%M %p")
        day_label = f"Today · {now.strftime('%a, %-d %b %Y')}"
        iso_now = datetime.now(tz=timezone.utc).isoformat()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_log (
                    id, file_id, time_label, day_label, file_name, kind,
                    decision, confidence, action, action_label, moved_to, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    aid,
                    file_id,
                    time_label,
                    day_label,
                    file_name,
                    kind,
                    decision,
                    confidence,
                    action,
                    action_label,
                    moved_to,
                    iso_now,
                ),
            )

        return {
            "id": aid,
            "time": time_label,
            "file": file_name,
            "kind": kind,
            "decision": decision,
            "confidence": confidence,
            "action": action,
            "actionLabel": action_label,
            "movedTo": moved_to,
        }

    def _row_to_analyzed_file(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "original": row["original"],
            "suggested": row["suggested"],
            "originalPath": row["original_path"],
            "currentPath": row["current_path"],
            "kind": row["kind"],
            "category": [row["category"], row["subcategory"]],
            "confidence": row["confidence"],
            "status": row["status"],
            "docType": row["doc_type"],
            "topics": json.loads(row["topics_json"]),
            "reason": row["reason"],
            "size": row["size_label"],
            "processedIn": row["processed_in"],
            "receivedAgo": format_relative_time(row["created_at"]),
        }

    def get_file(self, file_id: str) -> dict[str, Any] | None:
        """Fetch a single analyzed file record by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM analyzed_files WHERE id = ?", (file_id,)
            ).fetchone()
        return self._row_to_analyzed_file(row) if row else None

    def get_raw_file_row(self, file_id: str) -> dict[str, Any] | None:
        """Fetch raw database columns for internal operations (like review accept or undo)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM analyzed_files WHERE id = ?", (file_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_files(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List analyzed files, newest first, optionally filtered by status."""
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM analyzed_files WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM analyzed_files ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_analyzed_file(r) for r in rows]

    def update_file_after_action(
        self,
        file_id: str,
        *,
        status: str,
        current_path: str | Path,
        suggested: str | None = None,
        category: str | None = None,
        subcategory: str | None = None,
    ) -> dict[str, Any] | None:
        """Update an analyzed file record after review acceptance, edit, ignore, or undo."""
        raw = self.get_raw_file_row(file_id)
        if not raw:
            return None

        new_suggested = suggested or raw["suggested"]
        new_cat = category or raw["category"]
        new_subcat = subcategory or raw["subcategory"]

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE analyzed_files
                SET status = ?, current_path = ?, suggested = ?, category = ?, subcategory = ?
                WHERE id = ?
                """,
                (status, str(current_path), new_suggested, new_cat, new_subcat, file_id),
            )
        return self.get_file(file_id)

    def get_audit_log_grouped(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return audit log grouped by day matching UI `auditLog` schema."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

        grouped: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            day = r["day_label"]
            entry: dict[str, Any] = {
                "id": r["id"],
                "time": r["time_label"],
                "file": r["file_name"],
                "kind": r["kind"],
                "decision": r["decision"],
                "confidence": r["confidence"],
                "action": r["action"],
                "actionLabel": r["action_label"],
            }
            if r["moved_to"]:
                entry["movedTo"] = r["moved_to"]
            grouped.setdefault(day, []).append(entry)

        return [{"day": day, "entries": entries} for day, entries in grouped.items()]

    def get_category_summary(self) -> list[dict[str, Any]]:
        """Return category counts and subcategories matching UI `fileCategories`."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT category, subcategory FROM analyzed_files WHERE status IN ('organized', 'accepted')"
            ).fetchall()

        counts: dict[str, int] = {}
        subs: dict[str, list[str]] = {}
        for r in rows:
            cat = r["category"]
            sub = r["subcategory"]
            counts[cat] = counts.get(cat, 0) + 1
            if sub not in subs.setdefault(cat, []):
                subs[cat].append(sub)

        return [
            {
                "name": cat,
                "count": count,
                "sub": " · ".join(subs.get(cat, [])[:3]) or "General",
            }
            for cat, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
        ]

    def search_files(self, query: str, limit: int = 25) -> list[dict[str, Any]]:
        """
        Search analyzed files across extracted text, topics, filenames, and categories.
        Returns items formatted for UI `SearchResult`.
        """
        q = query.strip().lower()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM analyzed_files ORDER BY created_at DESC"
            ).fetchall()

        if not q:
            results = []
            for r in rows[:limit]:
                results.append(self._row_to_search_result(r, match_score=r["confidence"]))
            return results

        terms = [t for t in q.split() if t]
        scored: list[tuple[int, sqlite3.Row]] = []

        for r in rows:
            haystack_name = f"{r['original']} {r['suggested']}".lower()
            haystack_meta = f"{r['category']} {r['subcategory']} {r['doc_type']} {r['topics_json']} {r['reason']}".lower()
            haystack_text = (r["extracted_text"] or "").lower()

            score = 0
            for term in terms:
                if term in haystack_name:
                    score += 45
                if term in haystack_meta:
                    score += 35
                if term in haystack_text:
                    score += 25

            if score > 0:
                match_pct = min(99, max(60, score))
                scored.append((match_pct, r))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [self._row_to_search_result(r, match_score=score) for score, r in scored[:limit]]

    def _row_to_search_result(self, row: sqlite3.Row, match_score: int) -> dict[str, Any]:
        try:
            dt = datetime.fromisoformat(row["created_at"])
            modified_str = dt.strftime("%-d %b %Y")
        except Exception:
            modified_str = "Recently"

        return {
            "id": row["id"],
            "name": row["suggested"] if row["status"] in ("organized", "accepted") else row["original"],
            "kind": row["kind"],
            "category": [row["category"], row["subcategory"]],
            "match": match_score,
            "topics": json.loads(row["topics_json"]),
            "explanation": row["reason"],
            "location": str(Path(row["current_path"]).parent),
            "modified": modified_str,
        }
