"""
Unit tests for app/intent/path_validator.py.
"""

from pathlib import Path
import pytest

from app.intent.path_validator import PathValidator, PathValidationResult


class TestPathValidator:
    def test_empty_path_rejected(self):
        res = PathValidator.validate_destination_path("")
        assert res.valid is False
        assert any("empty" in i for i in res.issues)

    def test_null_byte_rejected(self):
        res = PathValidator.validate_destination_path("folder\0evil")
        assert res.valid is False
        assert any("null byte" in i.lower() for i in res.issues)

    def test_traversal_syntax_rejected(self, tmp_path):
        res = PathValidator.validate_destination_path(tmp_path / "../outside")
        assert res.valid is False
        assert any("traversal" in i.lower() for i in res.issues)

    def test_boundary_escape_rejected(self, tmp_path):
        base = tmp_path / "allowed_base"
        base.mkdir()
        outside = tmp_path / "secret_folder"
        outside.mkdir()

        res = PathValidator.validate_destination_path(outside, allowed_base=base)
        assert res.valid is False
        assert any("escapes" in i.lower() for i in res.issues)

    def test_valid_path_within_boundary(self, tmp_path):
        base = tmp_path / "allowed_base"
        base.mkdir()
        inside = base / "College" / "Exams"

        res = PathValidator.validate_destination_path(inside, allowed_base=base)
        assert res.valid is True
        assert res.resolved_path == inside.resolve()

    def test_sanitize_component_name(self):
        assert PathValidator.sanitize_component_name("Exam: 2026/Fall?") == "Exam_2026Fall"
        assert PathValidator.sanitize_component_name("../evil") == "evil"
        assert PathValidator.sanitize_component_name("CON") == "safe_CON"
        assert PathValidator.sanitize_component_name("   ") == "general"

    def test_resolve_safe_subpath(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        safe_dir = PathValidator.resolve_safe_subpath(root, "College", "NLP Notes")
        assert safe_dir == (root / "College" / "NLP_Notes").resolve()
        assert safe_dir.is_relative_to(root)
