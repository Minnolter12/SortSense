"""
SortSense Intent-Driven Organization.

Components:
- OrganizationMode, AcademicYearConfig, OrganizationRule, OrganizationPlan, OperationRecord
- InstructionParser
- RuleManager
- RuleMatcher
- DestinationResolver
- FolderBrowser
- PathValidator
- OrganizationPlanner
- SafeFileExecutor, HistoryManager
"""

from app.intent.destination_resolver import DestinationResolver
from app.intent.executor import HistoryManager, SafeFileExecutor
from app.intent.folder_browser import FolderBrowser
from app.intent.instruction_parser import InstructionParser
from app.intent.models import (
    AcademicYearConfig,
    OperationRecord,
    OrganizationMode,
    OrganizationPlan,
    OrganizationPlanItem,
    OrganizationRule,
    PlanItemStatus,
    RuleCondition,
    RuleDestination,
)
from app.intent.path_validator import PathValidationResult, PathValidator
from app.intent.planner import OrganizationPlanner
from app.intent.rule_manager import RuleManager
from app.intent.rule_matcher import MatchResult, RuleMatcher

__all__ = [
    "AcademicYearConfig",
    "DestinationResolver",
    "FolderBrowser",
    "HistoryManager",
    "InstructionParser",
    "MatchResult",
    "OperationRecord",
    "OrganizationMode",
    "OrganizationPlan",
    "OrganizationPlanItem",
    "OrganizationPlanner",
    "OrganizationRule",
    "PathValidationResult",
    "PathValidator",
    "PlanItemStatus",
    "RuleCondition",
    "RuleDestination",
    "RuleManager",
    "RuleMatcher",
    "SafeFileExecutor",
]
