"""
Tests for app/organizer.py (File operations, naming collisions, confidence routing, and undo).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.classifier import ClassificationResult
from app.organizer import (
    execute_file_operation,
    resolve_collision_path,
    undo_file_operation,
)


class TestCollisionResolution:
    def test_no_collision_returns_exact_filename(self, tmp_path: Path):
        dest = resolve_collision_path(tmp_path, "Math_Syllabus.pdf")
        assert dest == tmp_path / "Math_Syllabus.pdf"

    def test_single_and_multiple_naming_collisions(self, tmp_path: Path):
        """
        Edge case from spec: If Math_Syllabus.pdf already exists in Academics,
        automatically append (1), (2), etc. so no data is overwritten.
        """
        (tmp_path / "Math_Syllabus.pdf").write_text("original")
        dest1 = resolve_collision_path(tmp_path, "Math_Syllabus.pdf")
        assert dest1.name == "Math_Syllabus (1).pdf"

        dest1.write_text("copy 1")
        dest2 = resolve_collision_path(tmp_path, "Math_Syllabus.pdf")
        assert dest2.name == "Math_Syllabus (2).pdf"


class TestExecuteFileOperation:
    def test_high_confidence_moves_and_renames_file(self, tmp_path: Path):
        watched = tmp_path / "Downloads"
        organized = tmp_path / "Organized"
        watched.mkdir()

        src = watched / "IMG-WA0004.pdf"
        src.write_text("Fourier transforms syllabus")

        classification = ClassificationResult(
            category="Academic",
            subcategory="Mathematics",
            suggested_filename="Math_Syllabus.pdf",
            confidence=0.95,
            doc_type="Syllabus",
            topics=["Mathematics"],
            reasoning="University math syllabus.",
        )

        outcome = execute_file_operation(
            src,
            classification,
            organized_dir=organized,
            confidence_threshold=0.85,
        )

        assert outcome.moved is True
        assert outcome.status == "organized"
        assert not src.exists()
        assert outcome.destination_path == organized / "Academic" / "Mathematics" / "Math_Syllabus.pdf"
        assert outcome.destination_path.exists()
        assert outcome.destination_path.read_text() == "Fourier transforms syllabus"

    def test_collision_during_move_never_overwrites_existing_file(self, tmp_path: Path):
        watched = tmp_path / "Downloads"
        organized = tmp_path / "Organized"
        watched.mkdir()

        target_folder = organized / "Academic" / "Mathematics"
        target_folder.mkdir(parents=True)
        existing = target_folder / "Math_Syllabus.pdf"
        existing.write_text("existing syllabus data")

        src = watched / "new_download.pdf"
        src.write_text("new syllabus data")

        classification = ClassificationResult(
            category="Academic",
            subcategory="Mathematics",
            suggested_filename="Math_Syllabus.pdf",
            confidence=0.92,
        )

        outcome = execute_file_operation(
            src,
            classification,
            organized_dir=organized,
            confidence_threshold=0.85,
        )

        assert outcome.moved is True
        assert outcome.final_filename == "Math_Syllabus (1).pdf"
        assert existing.read_text() == "existing syllabus data"
        assert (target_folder / "Math_Syllabus (1).pdf").read_text() == "new syllabus data"

    def test_low_confidence_routes_to_review_without_moving(self, tmp_path: Path):
        watched = tmp_path / "Downloads"
        organized = tmp_path / "Organized"
        watched.mkdir()

        src = watched / "IMG_20261008_WA0003.jpg"
        src.write_bytes(b"blurry receipt")

        classification = ClassificationResult(
            category="Personal",
            subcategory="Receipts",
            suggested_filename="Receipt_Photo.jpg",
            confidence=0.61,
        )

        outcome = execute_file_operation(
            src,
            classification,
            organized_dir=organized,
            confidence_threshold=0.85,
        )

        assert outcome.moved is False
        assert outcome.status == "review"
        assert outcome.destination_path is None
        assert src.exists()

    def test_undo_file_operation_restores_original_file(self, tmp_path: Path):
        watched = tmp_path / "Downloads"
        organized = tmp_path / "Organized"
        watched.mkdir()

        src = watched / "fouriertransforms.pdf"
        src.write_text("Fourier content")

        classification = ClassificationResult(
            category="Academic",
            subcategory="Mathematics",
            suggested_filename="Fourier_Transforms_Notes.pdf",
            confidence=0.96,
        )

        outcome = execute_file_operation(src, classification, organized_dir=organized)
        assert outcome.destination_path is not None
        assert outcome.destination_path.exists()
        assert not src.exists()

        restored = undo_file_operation(outcome.destination_path, outcome.source_path)
        assert restored == src
        assert src.exists()
        assert not outcome.destination_path.exists()
