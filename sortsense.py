"""
SortSense — Windows Desktop Application Launcher.

Primary entry point for packaged desktop distributions and direct execution.
Enables Windows Per-Monitor High-DPI awareness for crisp rendering on modern displays.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure application base directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Windows DPI awareness configuration
if sys.platform == "win32":
    try:
        import ctypes
        # Try Per-Monitor V2 (PROCESS_PER_MONITOR_DPI_AWARE_V2 = 2) or System (1)
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        # Fall back gracefully on older Windows builds
        pass


def run_smoke_test() -> int:
    """Headless verification of real GUI workflows and organization engine."""
    import tempfile
    import shutil
    from pathlib import Path
    from app.analyzer import safe_analyze_document
    from app.gui import SortSenseApp
    from app.ingestion import ingest_file
    from app.intent.models import OrganizationRule, RuleCondition, RuleDestination

    print("[SMOKE TEST] Initializing SortSenseApp...")
    app = SortSenseApp()
    app.update()

    temp_dir = Path(tempfile.mkdtemp(prefix="sortsense_smoketest_"))
    try:
        src_dir = temp_dir / "incoming"
        dst_dir = temp_dir / "organized"
        src_dir.mkdir(parents=True)
        dst_dir.mkdir(parents=True)

        # Ensure test isolation: isolate rule and history managers to temp directory
        from app.intent import RuleManager, HistoryManager, SafeFileExecutor
        app.rule_manager = RuleManager(storage_path=temp_dir / "smoke_rules.json")
        app.history_manager = HistoryManager(history_file=temp_dir / "smoke_history.json")
        app.executor = SafeFileExecutor(history_manager=app.history_manager)

        # 1. Create a sample test file
        test_file = src_dir / "tax_invoice_2026.txt"
        test_file.write_text("Invoice dummy content for offline packaging test", encoding="utf-8")

        # 2. Test rule creation and persistence workflow
        print("[SMOKE TEST] Testing rule creation and persistence...")
        rule = OrganizationRule(
            rule_name="Invoices Rule",
            conditions=RuleCondition(keywords=["invoice", "tax"]),
            destination=RuleDestination(root=str(dst_dir / "Invoices"))
        )
        app.rule_manager.add_rule(rule)
        all_rules = app.rule_manager.get_all_rules()
        assert any(r.rule_name == "Invoices Rule" for r in all_rules), "Failed to save rule"
        print("[SMOKE TEST] Rule persisted successfully.")

        # 3. Test ingestion and offline analysis
        print("[SMOKE TEST] Testing document ingestion & offline analysis...")
        norm_doc = ingest_file(test_file)
        analysis = safe_analyze_document(norm_doc)
        print(f"[SMOKE TEST] Analyzed document offline: category='{analysis.category}', confidence={analysis.confidence:.2f}")

        # 4. Test rule matching
        print("[SMOKE TEST] Testing rule matcher...")
        from app.intent import RuleMatcher
        rule_matcher = RuleMatcher(academic_config=app.academic_config)
        match_result = rule_matcher.match(norm_doc, analysis, [rule])
        assert match_result.matched_rule is not None, f"Rule matching failed: {match_result.explanation}"
        assert match_result.matched_rule.rule_name == "Invoices Rule"
        print(f"[SMOKE TEST] Rule matched successfully: {match_result.matched_rule.rule_name}")

        # 5. Test safe file execution workflow
        print("[SMOKE TEST] Testing safe file execution...")
        executed_record = app.executor.execute_move(
            source_path=test_file,
            destination_dir=dst_dir / "Invoices",
            destination_filename=test_file.name,
            rule=match_result.matched_rule,
            mode_name="Manual Destination"
        )
        assert (dst_dir / "Invoices" / "tax_invoice_2026.txt").exists(), "File move execution failed"
        assert not test_file.exists(), "Source file still exists after move"
        print("[SMOKE TEST] File moved safely to target folder.")

        # 6. Test History & Undo workflow
        print("[SMOKE TEST] Testing History and Undo workflow...")
        success, msg = app.executor.undo_operation(executed_record.operation_id)
        assert success, f"Undo failed: {msg}"
        assert test_file.exists(), "File was not restored by undo"
        assert not (dst_dir / "Invoices" / "tax_invoice_2026.txt").exists(), "Destination file still present after undo"
        print("[SMOKE TEST] History recorded and undo succeeded. File restored.")

        # 7. Clean up rule from storage
        app.rule_manager.delete_rule(rule.id)

        # 8. Verify clean shutdown protocol
        print("[SMOKE TEST] Testing clean shutdown protocol...")
        app._on_closing()
        print("[SMOKE TEST] ALL WORKFLOWS PASSED CLEANLY.")
        return 0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main() -> None:
    """Launch the SortSense desktop application."""
    if len(sys.argv) > 1:
        if sys.argv[1] in ("--version", "-v"):
            print("SortSense v1.0.0")
            sys.exit(0)
        elif sys.argv[1] == "--smoke-test":
            sys.exit(run_smoke_test())

    from app.gui import SortSenseApp
    app = SortSenseApp()
    app.mainloop()


if __name__ == "__main__":
    main()
