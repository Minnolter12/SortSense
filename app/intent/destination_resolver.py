"""
DestinationResolver for SortSense.

Enforces destination resolution priority:
1. Explicit destination selected for the current operation.
2. Matching saved user rule.
3. AI-generated destination suggestion.
4. Existing default category.
5. Human review if no reliable destination is available.

Supports AI-Directed (Mode A), Manual Destination (Mode B), and Hybrid (Mode C).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from app.config import settings
from app.intent.models import OrganizationMode, OrganizationRule
from app.intent.path_validator import PathValidator

if TYPE_CHECKING:
    from app.analysis_models import DocumentAnalysis
    from app.document import NormalizedDocument

logger = logging.getLogger(__name__)

# Fallback default category mappings (matches organizer.py)
_DEFAULT_CATEGORY_FOLDERS = {
    "invoice": "Invoices",
    "receipt": "Receipts",
    "resume": "Resumes",
    "academic": "Academic",
    "report": "Reports",
    "notes": "Notes",
    "contract": "Contracts",
    "presentation": "Presentations",
    "general": "General",
}


@dataclass
class ResolvedDestination:
    """Outcome of destination resolution."""
    root_folder: Path
    subfolder_path: Path
    target_directory: Path
    target_filename: str
    priority_tier: int  # 1 (highest) to 5 (fallback review)
    explanation: str
    requires_review: bool = False
    warnings: list[str] = field(default_factory=list)


class DestinationResolver:
    """
    Resolves the final target folder and filename for a document.
    """

    def __init__(self, base_sorted_dir: Path | None = None) -> None:
        self.base_sorted_dir = Path(base_sorted_dir or settings.sorted_base_dir).resolve()

    def resolve(
        self,
        document: "NormalizedDocument",
        analysis: "DocumentAnalysis",
        mode: OrganizationMode = OrganizationMode.HYBRID,
        manual_destination_root: Path | None = None,
        matched_rule: OrganizationRule | None = None,
        custom_subfolders: Sequence[str] | None = None,
    ) -> ResolvedDestination:
        """
        Resolve destination path and filename according to mode and priority tiers.
        """
        warnings: list[str] = []
        root: Path | None = None
        subfolders: list[str] = []
        priority_tier = 5
        explanation = ""
        requires_review = False

        # --- Priority 1: Explicit destination selected for current operation ---
        if manual_destination_root and mode in (OrganizationMode.MANUAL_DESTINATION, OrganizationMode.HYBRID):
            root = manual_destination_root.expanduser().resolve()
            priority_tier = 1
            if mode == OrganizationMode.MANUAL_DESTINATION:
                explanation = f"Manual destination mode: routed directly to '{root.name}'."
            else:
                explanation = f"Manual destination root selected: '{root.name}'."

        # --- Priority 2: Matching saved user rule ---
        elif matched_rule and matched_rule.destination.root:
            rule_root = matched_rule.destination.root.strip()
            # If absolute path, use it; otherwise place inside base_sorted_dir
            if Path(rule_root).is_absolute():
                root = Path(rule_root).resolve()
            else:
                root = self.base_sorted_dir / PathValidator.sanitize_component_name(rule_root)
            priority_tier = 2
            explanation = f"Applied destination root from rule '{matched_rule.rule_name}': '{root.name}'."

        # --- Priority 3: AI-generated destination suggestion ---
        elif analysis.category and analysis.category.strip():
            cat = PathValidator.sanitize_component_name(analysis.category.strip())
            root = self.base_sorted_dir / cat
            priority_tier = 3
            explanation = f"AI suggested category destination: '{cat}'."

        # --- Priority 4: Existing default category ---
        elif analysis.document_type:
            doc_type_lower = analysis.document_type.lower()
            matched_cat = "General"
            for k, folder in _DEFAULT_CATEGORY_FOLDERS.items():
                if k in doc_type_lower:
                    matched_cat = folder
                    break
            root = self.base_sorted_dir / matched_cat
            priority_tier = 4
            explanation = f"Mapped to default category folder: '{matched_cat}'."

        # --- Priority 5: Fallback to review ---
        else:
            root = self.base_sorted_dir / "Unsorted"
            priority_tier = 5
            requires_review = True
            explanation = "No reliable destination identified. Human review required."

        # Determine subfolder grouping
        if custom_subfolders:
            subfolders.extend(custom_subfolders)
        elif matched_rule and matched_rule.destination.group_by:
            for group_field in matched_rule.destination.group_by:
                val = self._extract_group_value(group_field, analysis, document)
                if val:
                    subfolders.append(val)
        elif mode in (OrganizationMode.AI_DIRECTED, OrganizationMode.HYBRID) and analysis.subject:
            # Suggest subject subfolder if available
            subfolders.append(analysis.subject)

        # Build full target directory safely using PathValidator
        target_dir = root
        for sf in subfolders:
            target_dir = PathValidator.resolve_safe_subpath(target_dir, sf)

        # Determine target filename
        target_filename = self._resolve_filename(document, analysis, matched_rule)

        # Calculate relative subfolder path
        try:
            rel_subpath = target_dir.relative_to(root)
        except ValueError:
            rel_subpath = Path()

        return ResolvedDestination(
            root_folder=root,
            subfolder_path=rel_subpath,
            target_directory=target_dir,
            target_filename=target_filename,
            priority_tier=priority_tier,
            explanation=explanation,
            requires_review=requires_review,
            warnings=warnings,
        )

    def _extract_group_value(
        self,
        group_field: str,
        analysis: "DocumentAnalysis",
        document: "NormalizedDocument",
    ) -> str | None:
        """Extract value for subfolder grouping."""
        gf = group_field.lower().strip()
        if gf == "subject":
            return analysis.subject or analysis.category
        if gf in ("year", "academic_year"):
            return analysis.academic_year or analysis.document_date
        if gf == "semester":
            return analysis.semester
        if gf in ("type", "document_type"):
            return analysis.document_type
        if gf == "category":
            return analysis.category
        return None

    def _resolve_filename(
        self,
        document: "NormalizedDocument",
        analysis: "DocumentAnalysis",
        matched_rule: OrganizationRule | None,
    ) -> str:
        """Resolve safe output filename."""
        ext = document.extension.lstrip(".")
        if matched_rule and matched_rule.rename and matched_rule.rename_pattern:
            # Format custom pattern
            pattern = matched_rule.rename_pattern
            filename = pattern.format(
                original=document.file_name,
                subject=analysis.subject or "Subject",
                year=analysis.academic_year or "Year",
                type=analysis.document_type,
            )
            clean_stem = PathValidator.sanitize_component_name(Path(filename).stem)
            return f"{clean_stem}.{ext}" if ext else clean_stem

        # Default to safe new_filename from analysis or original filename
        if analysis.new_filename and analysis.new_filename.strip():
            candidate = analysis.new_filename.strip()
            # Ensure safe stem
            stem = Path(candidate).stem
            cand_ext = Path(candidate).suffix.lstrip(".") or ext
            clean_stem = PathValidator.sanitize_component_name(stem)
            return f"{clean_stem}.{cand_ext}" if cand_ext else clean_stem

        return document.file_name
