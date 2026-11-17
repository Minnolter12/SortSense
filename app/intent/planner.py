"""
OrganizationPlanner for SortSense.

Generates complete, reviewable organization plans before moving any files.
Integrates Ingestion, Semantic Analysis, Rule Matching, and Destination Resolution.
Supports:
- Mode A: AI-Directed
- Mode B: Manual Destination
- Mode C: Hybrid (Default)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Sequence

from app.analysis_models import DocumentAnalysis
from app.config import settings
from app.document import NormalizedDocument
from app.ingestion import ingest_file
from app.intent.destination_resolver import DestinationResolver
from app.intent.instruction_parser import InstructionParser
from app.intent.models import (
    AcademicYearConfig,
    OperationRecord,
    OrganizationMode,
    OrganizationPlan,
    OrganizationPlanItem,
    OrganizationRule,
    PlanItemStatus,
)
from app.intent.path_validator import PathValidator
from app.intent.rule_manager import RuleManager
from app.intent.rule_matcher import RuleMatcher
from app.validation import validate_analysis

logger = logging.getLogger(__name__)


class OrganizationPlanner:
    """
    Coordinates the construction of previewable organization plans.
    Does NOT move or modify any files on disk.
    """

    def __init__(
        self,
        rule_manager: RuleManager | None = None,
        rule_matcher: RuleMatcher | None = None,
        destination_resolver: DestinationResolver | None = None,
        instruction_parser: InstructionParser | None = None,
        academic_config: AcademicYearConfig | None = None,
        analyzer_func: Callable[[NormalizedDocument], DocumentAnalysis] | None = None,
    ) -> None:
        self.academic_config = academic_config or AcademicYearConfig()
        self.rule_manager = rule_manager or RuleManager()
        self.rule_matcher = rule_matcher or RuleMatcher(self.academic_config)
        self.destination_resolver = destination_resolver or DestinationResolver()
        self.instruction_parser = instruction_parser or InstructionParser(self.academic_config)

        # Allow injecting custom analyzer function for testing without live Ollama
        if analyzer_func is not None:
            self._analyzer_func = analyzer_func
        else:
            from app.analyzer import safe_analyze_document
            self._analyzer_func = safe_analyze_document

    def create_plan(
        self,
        file_paths: Sequence[str | Path],
        mode: OrganizationMode = OrganizationMode.HYBRID,
        instruction: str = "",
        manual_destination: str | Path | None = None,
        rule_override: OrganizationRule | None = None,
    ) -> OrganizationPlan:
        """
        Build an OrganizationPlan for the given files.
        """
        manual_root: Path | None = None
        if manual_destination:
            manual_root = Path(manual_destination).expanduser().resolve()

        plan = OrganizationPlan(
            mode=mode,
            instruction=instruction,
            manual_root=manual_root,
        )

        # If instruction string provided and no rule_override, parse instruction into temporary active rule
        active_adhoc_rule = rule_override
        if instruction.strip() and active_adhoc_rule is None:
            parsed_rule, clarification = self.instruction_parser.parse(instruction)
            if parsed_rule:
                # Set highest priority for user's explicit current instruction
                parsed_rule.priority = 100
                active_adhoc_rule = parsed_rule

        # Combine adhoc rule with saved active rules
        saved_rules = self.rule_manager.get_all_rules(include_disabled=False)
        all_rules: list[OrganizationRule] = []
        if active_adhoc_rule:
            all_rules.append(active_adhoc_rule)
        all_rules.extend(saved_rules)

        for raw_path in file_paths:
            path = Path(raw_path).expanduser().resolve()
            item = self._plan_file(
                path=path,
                mode=mode,
                manual_root=manual_root,
                rules=all_rules,
            )
            plan.items.append(item)

        return plan

    def _plan_file(
        self,
        path: Path,
        mode: OrganizationMode,
        manual_root: Path | None,
        rules: list[OrganizationRule],
    ) -> OrganizationPlanItem:
        """Analyze and plan organization for a single file."""
        warnings: list[str] = []

        if not path.exists():
            return OrganizationPlanItem(
                original_path=path,
                original_filename=path.name,
                detected_document_type="Unknown",
                proposed_destination=settings.sorted_base_dir / "Unsorted",
                proposed_filename=path.name,
                confidence=0.0,
                explanation="Source file does not exist on disk.",
                warnings=["File not found."],
                status=PlanItemStatus.REJECTED,
            )

        # 1. Ingestion
        doc = ingest_file(path)
        if doc.extraction_status not in ("ok", "empty"):
            warnings.append(f"Text extraction issue: {doc.extraction_status}")

        # 2. Document Analysis (Ollama when available, deterministic evidence-based otherwise)
        analysis: DocumentAnalysis
        if mode == OrganizationMode.MANUAL_DESTINATION:
            # Mode B is completely independent of AI; run quick deterministic analysis for metadata
            # but never add warnings if AI/Ollama is offline
            try:
                analysis = self._analyzer_func(doc)
            except Exception:
                from app.analyzer import deterministic_analyze_document
                analysis = deterministic_analyze_document(doc)
        else:
            try:
                analysis = self._analyzer_func(doc)
            except Exception as exc:
                logger.warning("Analyzer error for %s: %s", path, exc)
                from app.analyzer import deterministic_analyze_document
                analysis = deterministic_analyze_document(doc)
                warnings.append(f"AI service unavailable; evaluated using deterministic engine.")

        # 3. Deterministic Validation
        validation = validate_analysis(doc, analysis)
        if not validation.valid:
            warnings.extend(validation.issues)

        # 4. Rule Matching
        match_result = self.rule_matcher.match(doc, analysis, rules)
        matched_rule = match_result.matched_rule

        if match_result.is_conflict:
            warnings.append(match_result.explanation)

        # 5. Destination Resolution
        resolved = self.destination_resolver.resolve(
            document=doc,
            analysis=analysis,
            mode=mode,
            manual_destination_root=manual_root,
            matched_rule=matched_rule,
        )

        warnings.extend(resolved.warnings)

        # 6. Path Safety Validation
        val_result = PathValidator.validate_destination_path(resolved.target_directory)
        if not val_result.valid:
            warnings.extend(val_result.issues)

        # 7. Collision Check
        target_file_path = resolved.target_directory / resolved.target_filename
        if target_file_path.exists():
            warnings.append(f"Destination file '{resolved.target_filename}' already exists; collision suffix will be assigned.")

        explanation = resolved.explanation
        if match_result.matched_rule:
            explanation = f"{match_result.explanation} {explanation}"

        # In Mode B (Manual Destination), confidence reflects user explicit manual selection (1.0)
        item_confidence = 1.0 if (mode == OrganizationMode.MANUAL_DESTINATION and manual_root) else analysis.confidence

        return OrganizationPlanItem(
            original_path=path,
            original_filename=path.name,
            detected_document_type=analysis.document_type,
            detected_subject=analysis.subject,
            detected_academic_year=analysis.academic_year,
            detected_semester=analysis.semester,
            detected_date=analysis.document_date,
            matched_rule_id=matched_rule.id if matched_rule else None,
            matched_rule_name=matched_rule.rule_name if matched_rule else None,
            proposed_destination=resolved.target_directory,
            proposed_filename=resolved.target_filename,
            confidence=item_confidence,
            explanation=explanation.strip(),
            warnings=warnings,
            status=PlanItemStatus.PROPOSED,
        )
