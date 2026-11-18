"""
SortSense GUI — real-time dashboard wired to the live processing pipeline.

Architecture:
  watcher thread  →  FileEvent
                 →  self.after(0, _dispatch_event)   [marshal to Tk thread]
                 →  threading.Thread(_run_pipeline)   [off Tk thread: IO + Ollama]
                 →  self.after(0, _on_proposal | _on_pipeline_error)   [proposal only - never moves files]
                                                      [marshal result to Tk thread]
"""

import os
import shutil
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from app.config import settings
from app.events import FileEvent
from app.watcher import start_watcher
from app.pipeline import process_file
from app.proposals import APPROVED, EXECUTED, FAILED, PENDING, REJECTED, ProposalManager

# ---------------------------------------------------------------------------
# Pipeline imports — all pipeline errors must be caught locally so the GUI
# never crashes due to a single bad file.
# ---------------------------------------------------------------------------
try:
    from app.ingestion import ingest_file
    from app.analyzer import (
        analyze_document,
        safe_analyze_document,
        deterministic_analyze_document,
        OllamaUnavailableError,
        AnalysisParseError,
    )
    from app.validation import validate_analysis
    from app.organizer import decide
    _PIPELINE_AVAILABLE = True
except Exception:  # pragma: no cover
    _PIPELINE_AVAILABLE = False

from app.intent import (
    AcademicYearConfig,
    HistoryManager,
    InstructionParser,
    OperationRecord,
    OrganizationMode,
    OrganizationPlan,
    OrganizationPlanItem,
    OrganizationPlanner,
    OrganizationRule,
    PathValidator,
    PlanItemStatus,
    RuleCondition,
    RuleDestination,
    RuleManager,
    SafeFileExecutor,
)

# Supported extensions (must match ingestion layer)
_SUPPORTED_EXTS = {".pdf", ".txt", ".md"}

# Configure appearance to modern dark mode
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Design Palette - Obsidian & Emerald theme matching reference UI
COLOR_BG = "#0c0e12"
COLOR_SIDEBAR_BG = "#0f1319"
COLOR_SIDEBAR_BORDER = "#1a212d"
COLOR_CARD_BG = "#131821"
COLOR_CARD_BORDER = "#1e2634"
COLOR_CARD_HOVER = "#18202c"
COLOR_ACCENT = "#10b981"
COLOR_ACCENT_HOVER = "#059669"
COLOR_ACCENT_LIGHT = "#34d399"
COLOR_ACCENT_MUTED_BG = "#112a24"
COLOR_ACCENT_BORDER = "#174338"
COLOR_TEXT_PRIMARY = "#f8fafc"
COLOR_TEXT_SECONDARY = "#94a3b8"
COLOR_TEXT_MUTED = "#64748b"
COLOR_INPUT_BG = "#0a0e14"
COLOR_BUTTON_SECONDARY = "#1a222f"
COLOR_BUTTON_SECONDARY_HOVER = "#243042"


# ---------------------------------------------------------------------------
# Smart folder finder — checks for an existing folder matching the category
# keyword anywhere under sorted_base_dir (case-insensitive, one level deep).
# ---------------------------------------------------------------------------

def _find_existing_category_folder(base_dir: Path, category: str) -> Path | None:
    if not base_dir.exists():
        return None
    keyword = category.lower()
    try:
        for child in base_dir.iterdir():
            if child.is_dir() and keyword in child.name.lower():
                return child
    except PermissionError:
        pass
    return None


def _safe_move(src: Path, target_dir: Path, new_filename: str) -> Path:
    """Move src → target_dir/new_filename, handling collisions. Creates target_dir if needed."""
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / new_filename
    counter = 1
    while dest.exists():
        stem = Path(new_filename).stem
        ext = Path(new_filename).suffix
        dest = target_dir / f"{stem}_{counter}{ext}"
        counter += 1
    shutil.move(str(src), str(dest))
    return dest


class SortSenseApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SortSense — Gemma Local File Organizer")
        self.geometry("1060x720")
        self.minsize(960, 640)
        self.configure(fg_color=COLOR_BG)

        # set grid layout 1x2
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0, minsize=240)
        self.grid_columnconfigure(1, weight=1)

        # ---------------------------------------------------------------
        # Internal state (source of truth for all dynamic dashboard values)
        # ---------------------------------------------------------------
        self._processed_count = 0
        self._pending_count = 0
        self._activity_lines: list[str] = []   # newest-first
        self._review_items: list[tuple] = []  # (filename, reason, src_path, suggested_dir, suggested_name)

        # ---------------------------------------------------------------
        # Intent-driven system components
        # ---------------------------------------------------------------
        self.academic_config = AcademicYearConfig(start_month=settings.academic_year_start_month)
        self.rule_manager = RuleManager()
        self.history_manager = HistoryManager()
        self.instruction_parser = InstructionParser(academic_config=self.academic_config)
        self.planner = OrganizationPlanner(rule_manager=self.rule_manager, academic_config=self.academic_config)
        self.executor = SafeFileExecutor(history_manager=self.history_manager)
        self.rule_matcher = self.planner.rule_matcher
        self.destination_resolver = self.planner.destination_resolver
        self.safe_executor = self.executor
        self.proposals = ProposalManager(self.safe_executor, base_dir=settings.sorted_base_dir)
        self._inflight: set[str] = set()  # paths currently being analysed (dedupes watcher events)

        self._current_plan: OrganizationPlan | None = None
        self._intent_mode_var = ctk.StringVar(value="Hybrid")
        self._manual_dest_var = ctk.StringVar(value=str(settings.sorted_base_dir))
        self._instruction_var = ctk.StringVar(value="")
        self._rule_status_var = ctk.StringVar(value="")

        # StringVars for the dashboard cards
        self.model_status_var = ctk.StringVar(value="Checking...")
        self._processed_var = ctk.StringVar(value="0")
        self._pending_var = ctk.StringVar(value="0")

        # ---------------------------------------------------------------
        # Sidebar
        # ---------------------------------------------------------------
        self.sidebar_frame = ctk.CTkFrame(
            self,
            width=240,
            corner_radius=0,
            fg_color=COLOR_SIDEBAR_BG,
            border_color=COLOR_SIDEBAR_BORDER,
            border_width=1,
        )
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_propagate(False)
        self.sidebar_frame.grid_rowconfigure(2, weight=1)

        # Brand Header
        brand_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        brand_frame.grid(row=0, column=0, padx=18, pady=(20, 16), sticky="ew")

        icon_badge = ctk.CTkFrame(
            brand_frame,
            width=36,
            height=36,
            corner_radius=10,
            fg_color=COLOR_ACCENT_MUTED_BG,
            border_width=1,
            border_color=COLOR_ACCENT_BORDER,
        )
        icon_badge.pack(side="left", padx=(0, 12))
        icon_badge.pack_propagate(False)
        ctk.CTkLabel(
            icon_badge,
            text="📁",
            font=ctk.CTkFont(size=16),
        ).place(relx=0.5, rely=0.5, anchor="center")

        brand_text_frame = ctk.CTkFrame(brand_frame, fg_color="transparent")
        brand_text_frame.pack(side="left", fill="both", expand=True)

        self.logo_label = ctk.CTkLabel(
            brand_text_frame,
            text="SortSense",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        )
        self.logo_label.pack(anchor="w")

        brand_sub = ctk.CTkLabel(
            brand_text_frame,
            text="● Gemma 4 · Local",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_ACCENT_LIGHT,
            anchor="w",
        )
        brand_sub.pack(anchor="w")

        # Navigation
        self.nav_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.nav_frame.grid(row=1, column=0, padx=14, pady=0, sticky="ew")

        self.dashboard_button = self._create_nav_button("⊞   Dashboard", self.show_dashboard)
        self.dashboard_button.pack(fill="x", pady=2)

        self.intent_button = self._create_nav_button("✨   Intent & Rules", self.show_intent)
        self.intent_button.pack(fill="x", pady=2)

        self.preview_button = self._create_nav_button("🔍   Preview Plan", self.show_preview)
        self.preview_button.pack(fill="x", pady=2)

        self.history_button = self._create_nav_button("📜   History & Undo", self.show_history)
        self.history_button.pack(fill="x", pady=2)

        self.watched_button = self._create_nav_button("📋   Activity Log", self.show_watched)
        self.watched_button.pack(fill="x", pady=2)

        review_container = ctk.CTkFrame(self.nav_frame, fg_color="transparent")
        review_container.pack(fill="x", pady=2)

        self.review_button = ctk.CTkButton(
            review_container,
            text="⏳   Review Queue",
            anchor="w",
            height=38,
            corner_radius=10,
            fg_color="transparent",
            text_color=COLOR_TEXT_SECONDARY,
            hover_color=COLOR_CARD_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            command=self.show_review,
        )
        self.review_button.pack(side="left", fill="x", expand=True)

        self.review_badge = ctk.CTkFrame(
            review_container,
            width=26,
            height=22,
            corner_radius=11,
            fg_color="#2b1e10",
            border_width=1,
            border_color="#78350f",
        )
        self.review_badge.pack(side="right", padx=(4, 6))
        self.review_badge.pack_propagate(False)
        self.review_badge_label = ctk.CTkLabel(
            self.review_badge,
            textvariable=self._pending_var,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#fbbf24",
        )
        self.review_badge_label.place(relx=0.5, rely=0.5, anchor="center")

        self.settings_button = self._create_nav_button("⚙   Settings", self.show_settings)
        self.settings_button.pack(fill="x", pady=2)

        # Bottom Frame: Watched Folder & Appearance
        bottom_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        bottom_frame.grid(row=3, column=0, padx=14, pady=16, sticky="sew")

        watched_label = ctk.CTkLabel(
            bottom_frame,
            text="WATCHED FOLDER",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
        )
        watched_label.pack(anchor="w", pady=(0, 4))

        watched_card = ctk.CTkFrame(
            bottom_frame,
            corner_radius=10,
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER,
        )
        watched_card.pack(fill="x", pady=(0, 14), ipady=6)

        watched_card_inner = ctk.CTkFrame(watched_card, fg_color="transparent")
        watched_card_inner.pack(fill="x", padx=10, pady=2)

        watched_list = list(settings.watched_dirs)
        folder_name = watched_list[0].name if watched_list else "Downloads"
        ctk.CTkLabel(
            watched_card_inner,
            text=f"📁  {folder_name}",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            watched_card_inner,
            text="● Watching",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_ACCENT_LIGHT,
            anchor="w",
        ).pack(anchor="w")

        self.appearance_mode_label = ctk.CTkLabel(
            bottom_frame,
            text="Appearance Mode:",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
        )
        self.appearance_mode_label.pack(anchor="w", pady=(0, 4))

        self.appearance_mode_optionemenu = ctk.CTkOptionMenu(
            bottom_frame,
            values=["Dark", "System", "Light"],
            command=self.change_appearance_mode_event,
            fg_color=COLOR_CARD_BG,
            button_color=COLOR_BUTTON_SECONDARY,
            button_hover_color=COLOR_BUTTON_SECONDARY_HOVER,
            dropdown_fg_color=COLOR_CARD_BG,
            dropdown_hover_color=COLOR_CARD_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            corner_radius=8,
            height=32,
        )
        self.appearance_mode_optionemenu.pack(fill="x")

        # ---------------------------------------------------------------
        # Main frames
        # ---------------------------------------------------------------
        self.frames: dict[str, ctk.CTkFrame] = {}

        self.dashboard_frame = self._create_dashboard_frame()
        self.intent_frame = self._create_intent_frame()
        self.preview_frame = self._create_preview_frame()
        self.history_frame = self._create_history_frame()
        self.watched_frame = self._create_watched_frame()
        self.review_frame = self._create_review_frame()
        self.settings_frame = self._create_settings_frame()

        self.frames["Dashboard"] = self.dashboard_frame
        self.frames["Intent"] = self.intent_frame
        self.frames["Preview"] = self.preview_frame
        self.frames["History"] = self.history_frame
        self.frames["Watched"] = self.watched_frame
        self.frames["Review"] = self.review_frame
        self.frames["Settings"] = self.settings_frame

        # ---------------------------------------------------------------
        # Background tasks & Lifecycle
        # ---------------------------------------------------------------
        self._is_shutting_down = False
        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        self._set_app_icon()

        self.check_model_status_thread()

        self.observer = None
        self.start_background_watcher()

        self.show_dashboard()
        self.after(500, self._check_first_run)

    def _set_app_icon(self):
        """Set window icon from bundled assets if available."""
        try:
            from app.resources import get_resource_path
            ico_path = get_resource_path("assets/icon.ico")
            if ico_path.exists():
                self.iconbitmap(str(ico_path))
        except Exception:
            pass

    def _on_closing(self):
        """Clean shutdown protocol when application window is closed."""
        self._is_shutting_down = True
        if self.observer:
            try:
                self.observer.stop()
                self.observer.join(timeout=1.0)
            except Exception:
                pass
        self.destroy()

    def _check_first_run(self):
        """Check if this is the user's first launch and display Welcome modal."""
        marker_file = Path.home() / ".sortsense" / ".first_run_completed"
        if not marker_file.exists():
            self._show_welcome_dialog(marker_file)

    def _show_welcome_dialog(self, marker_file: Path):
        """Display clean first-run welcome and capability dialog."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Welcome to SortSense")
        dialog.geometry("560x440")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(fg_color=COLOR_BG)

        # Center dialog relative to main window
        try:
            x = self.winfo_x() + (self.winfo_width() // 2) - 280
            y = self.winfo_y() + (self.winfo_height() // 2) - 220
            dialog.geometry(f"+{x}+{y}")
        except Exception:
            pass

        card = ctk.CTkFrame(dialog, fg_color=COLOR_CARD_BG, corner_radius=14, border_width=1, border_color=COLOR_CARD_BORDER)
        card.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            card,
            text="✨ Welcome to SortSense",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(anchor="w", padx=24, pady=(20, 4))

        ctk.CTkLabel(
            card,
            text="Offline, Privacy-First Intelligent File Organizer",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLOR_ACCENT_LIGHT,
        ).pack(anchor="w", padx=24, pady=(0, 16))

        info_text = (
            "• Zero-Setup Core Engine: Manual folder routing, custom rules,\n"
            "  pre-execution plan preview, and 1-click undo work immediately.\n\n"
            "• 100% Private & Offline: Your files, text, and metadata never leave\n"
            "  your machine. No cloud accounts, telemetry, or API keys.\n\n"
            "• Optional Local AI: You can connect local Gemma 4 via Ollama at\n"
            "  any time to unlock natural-language semantic understanding."
        )
        ctk.CTkLabel(
            card,
            text=info_text,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLOR_TEXT_SECONDARY,
            justify="left",
            anchor="w",
        ).pack(anchor="w", padx=24, pady=(0, 16))

        # Status box
        status_box = ctk.CTkFrame(card, fg_color=COLOR_INPUT_BG, corner_radius=8, border_width=1, border_color=COLOR_CARD_BORDER)
        status_box.pack(fill="x", padx=24, pady=(0, 20))

        # Check Ollama status
        from app.analyzer import OllamaServiceManager
        ai_active = OllamaServiceManager.is_available()
        if ai_active:
            status_text = "🟢 Local AI Ready: Ollama is detected. Generative natural language rules are enabled."
            status_color = COLOR_ACCENT_LIGHT
        else:
            status_text = "⚡ Deterministic Mode: Ready to use! (Local Ollama AI is completely optional)."
            status_color = "#38bdf8"

        ctk.CTkLabel(
            status_box,
            text=status_text,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=status_color,
            wraplength=460,
            justify="left",
        ).pack(padx=14, pady=10)

        def on_get_started():
            try:
                marker_file.parent.mkdir(parents=True, exist_ok=True)
                marker_file.write_text("SortSense first run completed", encoding="utf-8")
            except Exception:
                pass
            dialog.destroy()

        ctk.CTkButton(
            card,
            text="Get Started",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color=COLOR_BG,
            height=38,
            corner_radius=8,
            command=on_get_started,
        ).pack(anchor="e", padx=24, pady=(0, 16))

    def _create_nav_button(self, text: str, command):
        return ctk.CTkButton(
            self.nav_frame,
            text=text,
            anchor="w",
            height=40,
            corner_radius=10,
            fg_color="transparent",
            text_color=COLOR_TEXT_SECONDARY,
            hover_color=COLOR_CARD_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            command=command,
        )

    def _set_active_nav(self, active_button):
        for btn in [
            self.dashboard_button,
            self.intent_button,
            self.preview_button,
            self.history_button,
            self.watched_button,
            self.review_button,
            self.settings_button,
        ]:
            if btn == active_button:
                btn.configure(
                    fg_color=COLOR_ACCENT_MUTED_BG,
                    text_color=COLOR_ACCENT_LIGHT,
                    border_width=1,
                    border_color=COLOR_ACCENT_BORDER,
                    font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=COLOR_TEXT_SECONDARY,
                    border_width=0,
                    font=ctk.CTkFont(family="Segoe UI", size=13),
                )

    # -------------------------------------------------------------------
    # Frame builders
    # -------------------------------------------------------------------

    def _create_dashboard_frame(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(3, weight=1)

        # Header area
        header_frame = ctk.CTkFrame(frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=28, pady=(24, 16), sticky="ew")

        title = ctk.CTkLabel(
            header_frame,
            text="Dashboard Overview",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        )
        title.pack(anchor="w")

        subtitle = ctk.CTkLabel(
            header_frame,
            text="Local file intelligence & autonomous sorting overview",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
        )
        subtitle.pack(anchor="w", pady=(2, 0))

        # Status Cards Frame (3 cards)
        cards_frame = ctk.CTkFrame(frame, fg_color="transparent")
        cards_frame.grid(row=1, column=0, padx=28, pady=8, sticky="ew")
        cards_frame.grid_columnconfigure((0, 1, 2), weight=1, uniform="stat_cards")

        # 1. Model Status Card
        model_card = ctk.CTkFrame(
            cards_frame,
            corner_radius=14,
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER,
        )
        model_card.grid(row=0, column=0, padx=(0, 8), pady=0, sticky="nsew")

        ctk.CTkLabel(
            model_card,
            text="MODEL STATUS",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=COLOR_TEXT_MUTED,
        ).pack(anchor="w", padx=16, pady=(14, 6))

        status_pill = ctk.CTkFrame(
            model_card,
            corner_radius=8,
            fg_color="#0a0e14",
            border_width=1,
            border_color="#18202d",
        )
        status_pill.pack(fill="x", padx=16, pady=4, ipady=4)

        self.model_status_label = ctk.CTkLabel(
            status_pill,
            textvariable=self.model_status_var,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLOR_ACCENT_LIGHT,
        )
        self.model_status_label.pack(padx=10, pady=2)

        ctk.CTkLabel(
            model_card,
            text="Ollama Local Engine",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_TEXT_MUTED,
        ).pack(anchor="w", padx=16, pady=(6, 14))

        # 2. Files Processed Card
        processed_card = ctk.CTkFrame(
            cards_frame,
            corner_radius=14,
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER,
        )
        processed_card.grid(row=0, column=1, padx=4, pady=0, sticky="nsew")

        ctk.CTkLabel(
            processed_card,
            text="FILES PROCESSED",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=COLOR_TEXT_MUTED,
        ).pack(anchor="w", padx=16, pady=(14, 6))

        ctk.CTkLabel(
            processed_card,
            textvariable=self._processed_var,
            font=ctk.CTkFont(family="Segoe UI", size=32, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(anchor="w", padx=16, pady=0)

        ctk.CTkLabel(
            processed_card,
            text="Automated & organized",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_TEXT_MUTED,
        ).pack(anchor="w", padx=16, pady=(4, 14))

        # 3. Pending Review Card
        review_card = ctk.CTkFrame(
            cards_frame,
            corner_radius=14,
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER,
        )
        review_card.grid(row=0, column=2, padx=(8, 0), pady=0, sticky="nsew")

        ctk.CTkLabel(
            review_card,
            text="PENDING REVIEW",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=COLOR_TEXT_MUTED,
        ).pack(anchor="w", padx=16, pady=(14, 6))

        ctk.CTkLabel(
            review_card,
            textvariable=self._pending_var,
            font=ctk.CTkFont(family="Segoe UI", size=32, weight="bold"),
            text_color="#fbbf24",
        ).pack(anchor="w", padx=16, pady=0)

        ctk.CTkLabel(
            review_card,
            text="Requires manual check",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_TEXT_MUTED,
        ).pack(anchor="w", padx=16, pady=(4, 14))

        # Recent Activity Section
        activity_section_header = ctk.CTkFrame(frame, fg_color="transparent")
        activity_section_header.grid(row=2, column=0, padx=28, pady=(22, 8), sticky="ew")

        ctk.CTkLabel(
            activity_section_header,
            text="Recent Activity",
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        ).pack(side="left")

        activity_card = ctk.CTkFrame(
            frame,
            corner_radius=14,
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER,
        )
        activity_card.grid(row=3, column=0, padx=28, pady=(0, 20), sticky="nsew")
        activity_card.grid_rowconfigure(0, weight=1)
        activity_card.grid_columnconfigure(0, weight=1)

        self._dashboard_activity_box = ctk.CTkTextbox(
            activity_card,
            corner_radius=10,
            fg_color="#0a0e14",
            border_width=1,
            border_color="#18202d",
            text_color="#cbd5e1",
            font=ctk.CTkFont(family="Consolas", size=13),
        )
        self._dashboard_activity_box.grid(row=0, column=0, padx=14, pady=14, sticky="nsew")
        self._dashboard_activity_box.insert(
            "0.0",
            "(No files processed yet — drop a file into the watched directory)\n",
        )
        self._dashboard_activity_box.configure(state="disabled")

        return frame

    def _create_watched_frame(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        header_frame = ctk.CTkFrame(frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=28, pady=(24, 16), sticky="ew")

        title = ctk.CTkLabel(
            header_frame,
            text="Activity Log / Watched Files",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        )
        title.pack(anchor="w")

        subtitle = ctk.CTkLabel(
            header_frame,
            text="Live monitoring event stream and routing activity",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
        )
        subtitle.pack(anchor="w", pady=(2, 0))

        log_card = ctk.CTkFrame(
            frame,
            corner_radius=14,
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER,
        )
        log_card.grid(row=1, column=0, padx=28, pady=(0, 20), sticky="nsew")
        log_card.grid_rowconfigure(1, weight=1)
        log_card.grid_columnconfigure(0, weight=1)

        log_card_header = ctk.CTkFrame(log_card, fg_color="transparent")
        log_card_header.grid(row=0, column=0, padx=16, pady=(12, 6), sticky="ew")

        ctk.CTkLabel(
            log_card_header,
            text="● Live Watcher Output",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLOR_ACCENT_LIGHT,
        ).pack(side="left")

        self.activity_textbox = ctk.CTkTextbox(
            log_card,
            corner_radius=10,
            fg_color="#0a0e14",
            border_width=1,
            border_color="#18202d",
            text_color="#cbd5e1",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.activity_textbox.grid(row=1, column=0, padx=14, pady=(6, 14), sticky="nsew")
        watched_paths = "\n".join(f" - {d}" for d in settings.watched_dirs)
        self.activity_textbox.insert("0.0", f"Watching directories:\n{watched_paths}\n\n")
        self.activity_textbox.configure(state="disabled")

        return frame

    def _create_review_frame(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        header_frame = ctk.CTkFrame(frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=28, pady=(24, 16), sticky="ew")

        title = ctk.CTkLabel(
            header_frame,
            text="Review Queue",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        )
        title.pack(anchor="w")

        desc = ctk.CTkLabel(
            header_frame,
            text="SortSense suggests a name and folder for each file. Edit anything, then approve. Nothing moves until you click Execute Approved.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
        )
        desc.pack(anchor="w", pady=(2, 0))

        bar = ctk.CTkFrame(frame, fg_color="transparent")
        bar.grid(row=1, column=0, padx=28, pady=(0, 4), sticky="ew")
        ctk.CTkButton(bar, text="Approve all ready", width=140, height=32, corner_radius=8,
                      fg_color=COLOR_BUTTON_SECONDARY, hover_color=COLOR_BUTTON_SECONDARY_HOVER,
                      command=self._approve_all_proposals).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bar, text="Execute Approved", width=150, height=32, corner_radius=8,
                      fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
                      command=self._execute_approved_proposals).pack(side="left")

        self._review_scroll = ctk.CTkScrollableFrame(
            frame,
            corner_radius=14,
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER,
        )
        self._review_scroll.grid(row=2, column=0, padx=28, pady=(10, 20), sticky="nsew")
        self._review_scroll.grid_columnconfigure(1, weight=1)

        self._review_empty_label = ctk.CTkLabel(
            self._review_scroll,
            text="(Review queue is empty)",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLOR_TEXT_MUTED,
        )
        self._review_empty_label.grid(row=0, column=0, padx=16, pady=24)

        return frame

    def _create_settings_frame(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)

        header_frame = ctk.CTkFrame(frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=28, pady=(24, 16), sticky="ew")

        title = ctk.CTkLabel(
            header_frame,
            text="Settings",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        )
        title.pack(anchor="w")

        subtitle = ctk.CTkLabel(
            header_frame,
            text="Configure watched directory paths and local Ollama model settings",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
        )
        subtitle.pack(anchor="w", pady=(2, 0))

        card = ctk.CTkFrame(
            frame,
            corner_radius=14,
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER,
        )
        card.grid(row=1, column=0, padx=28, pady=8, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        # Watched Directory
        dir_section = ctk.CTkFrame(card, fg_color="transparent")
        dir_section.pack(fill="x", padx=20, pady=(18, 12))
        dir_section.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            dir_section,
            text="Watched Directory",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        dir_input_row = ctk.CTkFrame(dir_section, fg_color="transparent")
        dir_input_row.grid(row=1, column=0, sticky="ew")
        dir_input_row.grid_columnconfigure(0, weight=1)

        self.dir_entry = ctk.CTkEntry(
            dir_input_row,
            corner_radius=8,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_CARD_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
            height=38,
        )
        self.dir_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.dir_entry.insert(0, ", ".join(str(d) for d in settings.watched_dirs))

        ctk.CTkButton(
            dir_input_row,
            text="Browse",
            width=84,
            height=38,
            corner_radius=8,
            fg_color=COLOR_BUTTON_SECONDARY,
            hover_color=COLOR_BUTTON_SECONDARY_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            border_width=1,
            border_color="#263345",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self.browse_watch_directory,
        ).grid(row=0, column=1)

        # Gemma Model
        model_section = ctk.CTkFrame(card, fg_color="transparent")
        model_section.pack(fill="x", padx=20, pady=12)

        ctk.CTkLabel(
            model_section,
            text="Gemma Model",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        ).pack(anchor="w", pady=(0, 6))

        self.model_entry = ctk.CTkEntry(
            model_section,
            corner_radius=8,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_CARD_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
            height=38,
        )
        self.model_entry.pack(fill="x")
        self.model_entry.insert(0, settings.gemma_model)

        # Ollama Host
        host_section = ctk.CTkFrame(card, fg_color="transparent")
        host_section.pack(fill="x", padx=20, pady=12)

        ctk.CTkLabel(
            host_section,
            text="Ollama Host",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        ).pack(anchor="w", pady=(0, 6))

        self.host_entry = ctk.CTkEntry(
            host_section,
            corner_radius=8,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_CARD_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
            height=38,
        )
        self.host_entry.pack(fill="x")
        self.host_entry.insert(0, settings.ollama_host)

        # Save Button
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(16, 20))

        save_btn = ctk.CTkButton(
            btn_row,
            text="Save Settings",
            height=38,
            corner_radius=8,
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self.save_settings,
        )
        save_btn.pack(side="right")

        return frame

    def _get_current_mode(self) -> OrganizationMode:
        val = self._intent_mode_var.get().lower()
        if "ai" in val:
            return OrganizationMode.AI_DIRECTED
        if "manual" in val:
            return OrganizationMode.MANUAL_DESTINATION
        return OrganizationMode.HYBRID

    def _on_mode_changed(self, value: str):
        val = value.lower()
        if "manual" in val:
            msg = "Manual Mode: 100% independent of AI. Files are routed directly to your chosen folder."
        elif "ai" in val:
            msg = "AI-Directed Mode: Automatically detects types, subjects, and dates to build folder hierarchy."
        else:
            msg = "Hybrid Mode (Default): Manually chosen root takes precedence. Subfolders organized via rules/AI."
        if hasattr(self, "_mode_guidance_label"):
            self._mode_guidance_label.configure(text=msg)

    def browse_manual_destination(self):
        directory = filedialog.askdirectory(title="Select Destination Folder")
        if directory:
            self._manual_dest_var.set(directory)

    # -------------------------------------------------------------------
    # Intent & Rules Frame
    # -------------------------------------------------------------------

    def _create_intent_frame(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(3, weight=1)

        header_frame = ctk.CTkFrame(frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=28, pady=(24, 14), sticky="ew")

        ctk.CTkLabel(
            header_frame,
            text="Intent & Rules Engine",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            header_frame,
            text="Describe organization goals in natural language or configure reusable rules",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        # Input Card
        input_card = ctk.CTkFrame(
            frame,
            corner_radius=14,
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER,
        )
        input_card.grid(row=1, column=0, padx=28, pady=6, sticky="ew")
        input_card.grid_columnconfigure(0, weight=1)

        # Mode Selector
        mode_row = ctk.CTkFrame(input_card, fg_color="transparent")
        mode_row.pack(fill="x", padx=18, pady=(14, 4))

        ctk.CTkLabel(
            mode_row,
            text="ORGANIZATION MODE:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=COLOR_TEXT_MUTED,
        ).pack(side="left", padx=(0, 14))

        mode_selector = ctk.CTkSegmentedButton(
            mode_row,
            values=["Hybrid", "AI-Directed", "Manual Destination"],
            variable=self._intent_mode_var,
            command=self._on_mode_changed,
            selected_color=COLOR_ACCENT,
            selected_hover_color=COLOR_ACCENT_HOVER,
            unselected_color=COLOR_BUTTON_SECONDARY,
            unselected_hover_color=COLOR_BUTTON_SECONDARY_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        )
        mode_selector.pack(side="left")

        # Mode Guidance Label
        self._mode_guidance_label = ctk.CTkLabel(
            input_card,
            text="Hybrid Mode (Default): Manually chosen root takes precedence. Subfolders organized via rules/AI.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
        )
        self._mode_guidance_label.pack(fill="x", padx=18, pady=(2, 6))

        # Engine Status Banner
        self._engine_status_label = ctk.CTkLabel(
            input_card,
            text="⚡ Deterministic Mode Active · Rules & manual destinations operate offline without Ollama.",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#f59e0b",
            anchor="w",
        )
        self._engine_status_label.pack(fill="x", padx=18, pady=(0, 6))

        # Instruction Entry
        instr_row = ctk.CTkFrame(input_card, fg_color="transparent")
        instr_row.pack(fill="x", padx=18, pady=6)
        instr_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            instr_row,
            text="NATURAL-LANGUAGE INSTRUCTION:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=COLOR_TEXT_MUTED,
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        self.instruction_entry = ctk.CTkEntry(
            instr_row,
            textvariable=self._instruction_var,
            placeholder_text="e.g. Move all examination papers from the 2026 academic year into this folder. Organize them by subject.",
            corner_radius=8,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_CARD_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
            height=38,
        )
        self.instruction_entry.grid(row=1, column=0, sticky="ew")

        # Destination Folder Row
        dest_row = ctk.CTkFrame(input_card, fg_color="transparent")
        dest_row.pack(fill="x", padx=18, pady=6)
        dest_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            dest_row,
            text="DESTINATION FOLDER (Manual / Hybrid Root):",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=COLOR_TEXT_MUTED,
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        dest_input_box = ctk.CTkFrame(dest_row, fg_color="transparent")
        dest_input_box.grid(row=1, column=0, sticky="ew")
        dest_input_box.grid_columnconfigure(0, weight=1)

        self.manual_dest_entry = ctk.CTkEntry(
            dest_input_box,
            textvariable=self._manual_dest_var,
            corner_radius=8,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_CARD_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
            height=36,
        )
        self.manual_dest_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            dest_input_box,
            text="Browse",
            width=76,
            height=36,
            corner_radius=8,
            fg_color=COLOR_BUTTON_SECONDARY,
            hover_color=COLOR_BUTTON_SECONDARY_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            command=self.browse_manual_destination,
        ).grid(row=0, column=1)

        # Buttons Row
        action_bar = ctk.CTkFrame(input_card, fg_color="transparent")
        action_bar.pack(fill="x", padx=18, pady=(10, 14))

        ctk.CTkButton(
            action_bar,
            text="✨ Save as Reusable Rule",
            height=36,
            corner_radius=8,
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._save_rule_from_ui,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            action_bar,
            text="🔍 Generate Preview Plan",
            height=36,
            corner_radius=8,
            fg_color=COLOR_BUTTON_SECONDARY,
            hover_color=COLOR_BUTTON_SECONDARY_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._generate_plan_from_ui,
        ).pack(side="left")

        self.rule_status_label = ctk.CTkLabel(
            action_bar,
            textvariable=self._rule_status_var,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_ACCENT_LIGHT,
        )
        self.rule_status_label.pack(side="left", padx=14)

        # Saved Rules Header
        rules_header = ctk.CTkFrame(frame, fg_color="transparent")
        rules_header.grid(row=2, column=0, padx=28, pady=(12, 4), sticky="ew")

        ctk.CTkLabel(
            rules_header,
            text="Saved Rules",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(side="left")

        self._rules_scroll = ctk.CTkScrollableFrame(
            frame,
            corner_radius=14,
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER,
        )
        self._rules_scroll.grid(row=3, column=0, padx=28, pady=(0, 18), sticky="nsew")
        self._rules_scroll.grid_columnconfigure(0, weight=1)

        return frame

    # -------------------------------------------------------------------
    # Organization Preview Frame
    # -------------------------------------------------------------------

    def _create_preview_frame(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        header_frame = ctk.CTkFrame(frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=28, pady=(24, 12), sticky="ew")

        ctk.CTkLabel(
            header_frame,
            text="Organization Preview",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            header_frame,
            text="Review and approve proposed file movements before execution. No files are moved without approval.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        # Action Bar Card
        action_card = ctk.CTkFrame(
            frame,
            corner_radius=14,
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER,
        )
        action_card.grid(row=1, column=0, padx=28, pady=6, sticky="ew")

        action_card_inner = ctk.CTkFrame(action_card, fg_color="transparent")
        action_card_inner.pack(fill="x", padx=16, pady=10)

        ctk.CTkButton(
            action_card_inner,
            text="✓ Approve All",
            height=34,
            corner_radius=8,
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._approve_all_plan_items,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            action_card_inner,
            text="▶ Execute Approved Batch",
            height=34,
            corner_radius=8,
            fg_color="#0284c7",
            hover_color="#0369a1",
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._execute_plan_batch,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            action_card_inner,
            text="✕ Cancel Plan",
            height=34,
            corner_radius=8,
            fg_color=COLOR_BUTTON_SECONDARY,
            hover_color=COLOR_BUTTON_SECONDARY_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            command=self._clear_plan,
        ).pack(side="left")

        self._plan_summary_label = ctk.CTkLabel(
            action_card_inner,
            text="(No active plan. Generate one from Intent & Rules or pick files)",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLOR_TEXT_MUTED,
        )
        self._plan_summary_label.pack(side="right", padx=10)

        # Plan Items Scrollable Frame
        self._preview_scroll = ctk.CTkScrollableFrame(
            frame,
            corner_radius=14,
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER,
        )
        self._preview_scroll.grid(row=2, column=0, padx=28, pady=(6, 18), sticky="nsew")
        self._preview_scroll.grid_columnconfigure(0, weight=1)

        return frame

    # -------------------------------------------------------------------
    # Operation History Frame
    # -------------------------------------------------------------------

    def _create_history_frame(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        header_frame = ctk.CTkFrame(frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=28, pady=(24, 12), sticky="ew")

        ctk.CTkLabel(
            header_frame,
            text="Operation History & Undo",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            header_frame,
            text="Audit trail of executed file movements. Revert moves safely with one click.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        # Top Bar
        top_bar = ctk.CTkFrame(frame, fg_color="transparent")
        top_bar.grid(row=1, column=0, padx=28, pady=4, sticky="ew")

        ctk.CTkButton(
            top_bar,
            text="🔄 Refresh History",
            width=120,
            height=32,
            corner_radius=8,
            fg_color=COLOR_BUTTON_SECONDARY,
            hover_color=COLOR_BUTTON_SECONDARY_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            command=self._refresh_history_list,
        ).pack(side="left")

        self._history_scroll = ctk.CTkScrollableFrame(
            frame,
            corner_radius=14,
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER,
        )
        self._history_scroll.grid(row=2, column=0, padx=28, pady=(6, 18), sticky="nsew")
        self._history_scroll.grid_columnconfigure(0, weight=1)

        return frame

    # -------------------------------------------------------------------
    # Intent Callbacks & Handlers
    # -------------------------------------------------------------------

    def _save_rule_from_ui(self):
        instr = self._instruction_var.get().strip()
        if not instr:
            self._rule_status_var.set("Please enter an instruction.")
            return

        rule, clarification = self.instruction_parser.parse(instr)
        if clarification or not rule:
            self._rule_status_var.set(clarification or "Instruction was ambiguous.")
            return

        dest_root = self._manual_dest_var.get().strip()
        if dest_root and not rule.destination.root:
            rule.destination.root = dest_root

        self.rule_manager.add_rule(rule)
        self._rule_status_var.set(f"Saved rule: '{rule.rule_name}'")
        self._refresh_rules_list()

    def _generate_plan_from_ui(self):
        """Scan watched directories or prompt user for files, then build preview plan."""
        watch_dirs = list(settings.watched_dirs)
        files_to_plan: list[Path] = []
        for wd in watch_dirs:
            if wd.exists():
                for f in wd.iterdir():
                    if f.is_file() and f.suffix.lower() in _SUPPORTED_EXTS:
                        files_to_plan.append(f)

        if not files_to_plan:
            # Let user select files
            chosen = filedialog.askopenfilenames(
                title="Select Files to Organize",
                filetypes=[("Documents", "*.pdf *.txt *.md"), ("All Files", "*.*")],
            )
            if chosen:
                files_to_plan = [Path(p) for p in chosen]

        if not files_to_plan:
            self._rule_status_var.set("No files found to organize.")
            return

        mode = self._get_current_mode()
        instr = self._instruction_var.get().strip()
        manual_dest = self._manual_dest_var.get().strip() or None

        self._rule_status_var.set(f"Analyzing {len(files_to_plan)} file(s)...")

        def plan_worker():
            try:
                plan = self.planner.create_plan(
                    file_paths=files_to_plan,
                    mode=mode,
                    instruction=instr,
                    manual_destination=manual_dest,
                )
                self.after(0, self._on_plan_created, plan)
            except Exception as exc:
                self.after(0, self._rule_status_var.set, f"Plan creation failed: {exc}")

        threading.Thread(target=plan_worker, daemon=True).start()

    def _on_plan_created(self, plan: OrganizationPlan):
        self._current_plan = plan
        self._rule_status_var.set(f"Plan created: {plan.total_count} file(s).")
        self.show_preview()

    def _refresh_rules_list(self):
        for widget in self._rules_scroll.winfo_children():
            widget.destroy()

        rules = self.rule_manager.get_all_rules()
        if not rules:
            ctk.CTkLabel(
                self._rules_scroll,
                text="(No saved rules yet. Enter an instruction above to create one.)",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=COLOR_TEXT_MUTED,
            ).pack(padx=16, pady=24)
            return

        for r in rules:
            row = ctk.CTkFrame(
                self._rules_scroll,
                corner_radius=10,
                fg_color=COLOR_INPUT_BG,
                border_width=1,
                border_color=COLOR_CARD_BORDER,
            )
            row.pack(fill="x", padx=6, pady=4)
            row.grid_columnconfigure(1, weight=1)

            # Toggle switch
            switch_var = ctk.BooleanVar(value=r.enabled)
            switch = ctk.CTkSwitch(
                row,
                text="",
                variable=switch_var,
                width=42,
                command=lambda rule_id=r.id, var=switch_var: self.rule_manager.set_rule_enabled(rule_id, var.get()),
            )
            switch.grid(row=0, column=0, padx=(12, 8), pady=10)

            # Info
            info_frame = ctk.CTkFrame(row, fg_color="transparent")
            info_frame.grid(row=0, column=1, padx=4, pady=10, sticky="w")

            ctk.CTkLabel(
                info_frame,
                text=r.rule_name,
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color=COLOR_TEXT_PRIMARY,
            ).pack(anchor="w")

            conds = []
            if r.conditions.document_types:
                conds.append(f"Types: {', '.join(r.conditions.document_types)}")
            if r.conditions.subjects:
                conds.append(f"Subject: {', '.join(r.conditions.subjects)}")
            if r.conditions.academic_year:
                conds.append(f"Year: {r.conditions.academic_year}")
            if r.destination.root:
                conds.append(f"Destination: {r.destination.root}")
            if r.destination.group_by:
                conds.append(f"Group by: {', '.join(r.destination.group_by)}")

            ctk.CTkLabel(
                info_frame,
                text=" | ".join(conds) if conds else "General matching rule",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=COLOR_TEXT_MUTED,
            ).pack(anchor="w")

            # Delete button
            ctk.CTkButton(
                row,
                text="✕ Delete",
                width=76,
                height=30,
                corner_radius=8,
                fg_color="#331414",
                hover_color="#4d1a1a",
                text_color="#f87171",
                command=lambda rule_id=r.id: (self.rule_manager.delete_rule(rule_id), self._refresh_rules_list()),
            ).grid(row=0, column=2, padx=(8, 14), pady=10)

    def _refresh_preview_list(self):
        for widget in self._preview_scroll.winfo_children():
            widget.destroy()

        if not self._current_plan or not self._current_plan.items:
            self._plan_summary_label.configure(text="(No active plan)")
            ctk.CTkLabel(
                self._preview_scroll,
                text="(No files in preview. Generate a preview plan from 'Intent & Rules'.)",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=COLOR_TEXT_MUTED,
            ).pack(padx=16, pady=24)
            return

        total = self._current_plan.total_count
        approved = self._current_plan.approved_count
        self._plan_summary_label.configure(text=f"Total: {total} | Approved: {approved} | Rejected: {self._current_plan.rejected_count}")

        for item in self._current_plan.items:
            card = ctk.CTkFrame(
                self._preview_scroll,
                corner_radius=12,
                fg_color=COLOR_INPUT_BG,
                border_width=1,
                border_color=COLOR_ACCENT_BORDER if item.status == PlanItemStatus.APPROVED else COLOR_CARD_BORDER,
            )
            card.pack(fill="x", padx=6, pady=5)
            card.grid_columnconfigure(0, weight=1)

            top_row = ctk.CTkFrame(card, fg_color="transparent")
            top_row.pack(fill="x", padx=14, pady=(10, 4))

            ctk.CTkLabel(
                top_row,
                text=f"📄 {item.original_filename}",
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color=COLOR_TEXT_PRIMARY,
            ).pack(side="left")

            status_color = "#34d399" if item.status == PlanItemStatus.APPROVED else ("#f87171" if item.status == PlanItemStatus.REJECTED else "#fbbf24")
            ctk.CTkLabel(
                top_row,
                text=f"[{item.status.value.upper()}]",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=status_color,
            ).pack(side="right")

            # Routing details
            mid_row = ctk.CTkFrame(card, fg_color="transparent")
            mid_row.pack(fill="x", padx=14, pady=2)

            details_text = f"Type: {item.detected_document_type}"
            if item.detected_subject:
                details_text += f" | Subject: {item.detected_subject}"
            if item.detected_academic_year:
                details_text += f" | Year: {item.detected_academic_year}"
            details_text += f" | Conf: {item.confidence:.0%}"

            ctk.CTkLabel(
                mid_row,
                text=details_text,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=COLOR_TEXT_SECONDARY,
            ).pack(anchor="w")

            ctk.CTkLabel(
                mid_row,
                text=f"Target: {item.proposed_destination} / {item.proposed_filename}",
                font=ctk.CTkFont(family="Consolas", size=11),
                text_color=COLOR_ACCENT_LIGHT,
            ).pack(anchor="w", pady=(2, 0))

            if item.warnings:
                ctk.CTkLabel(
                    mid_row,
                    text=f"⚠️ {'; '.join(item.warnings)}",
                    font=ctk.CTkFont(family="Segoe UI", size=10),
                    text_color="#fbbf24",
                ).pack(anchor="w", pady=(2, 0))

            # Buttons
            btn_row = ctk.CTkFrame(card, fg_color="transparent")
            btn_row.pack(fill="x", padx=14, pady=(6, 10))

            ctk.CTkButton(
                btn_row,
                text="Approve",
                width=76,
                height=28,
                corner_radius=6,
                fg_color=COLOR_ACCENT,
                hover_color=COLOR_ACCENT_HOVER,
                text_color="#ffffff",
                command=lambda it=item: self._approve_plan_item(it),
            ).pack(side="left", padx=(0, 8))

            ctk.CTkButton(
                btn_row,
                text="Reject",
                width=76,
                height=28,
                corner_radius=6,
                fg_color="#331414",
                hover_color="#4d1a1a",
                text_color="#f87171",
                command=lambda it=item: self._reject_plan_item(it),
            ).pack(side="left", padx=(0, 8))

            ctk.CTkButton(
                btn_row,
                text="Edit Target",
                width=88,
                height=28,
                corner_radius=6,
                fg_color=COLOR_BUTTON_SECONDARY,
                hover_color=COLOR_BUTTON_SECONDARY_HOVER,
                text_color=COLOR_TEXT_PRIMARY,
                command=lambda it=item: self._edit_item_destination(it),
            ).pack(side="left")

    def _approve_plan_item(self, item: OrganizationPlanItem):
        item.status = PlanItemStatus.APPROVED
        self._refresh_preview_list()

    def _reject_plan_item(self, item: OrganizationPlanItem):
        item.status = PlanItemStatus.REJECTED
        self._refresh_preview_list()

    def _edit_item_destination(self, item: OrganizationPlanItem):
        new_dir = filedialog.askdirectory(title=f"New destination for {item.original_filename}")
        if new_dir:
            item.proposed_destination = Path(new_dir)
            self._refresh_preview_list()

    def _approve_all_plan_items(self):
        if self._current_plan:
            for it in self._current_plan.items:
                it.status = PlanItemStatus.APPROVED
            self._refresh_preview_list()

    def _clear_plan(self):
        self._current_plan = None
        self._refresh_preview_list()

    def _execute_plan_batch(self):
        if not self._current_plan:
            return

        plan = self._current_plan

        def worker():
            s_cnt, f_cnt, errs = self.executor.execute_plan(plan, only_approved=True)
            self.after(0, self._on_batch_executed, s_cnt, f_cnt, errs)

        threading.Thread(target=worker, daemon=True).start()

    def _on_batch_executed(self, success_cnt: int, fail_cnt: int, errors: list[str]):
        self._processed_count += success_cnt
        self._processed_var.set(str(self._processed_count))
        self._log_raw(f"[Batch Execute] Success: {success_cnt}, Failed: {fail_cnt}\n")
        self._refresh_preview_list()
        self._refresh_history_list()
        self.show_history()

    def _refresh_history_list(self):
        for widget in self._history_scroll.winfo_children():
            widget.destroy()

        records = self.history_manager.get_records()
        if not records:
            ctk.CTkLabel(
                self._history_scroll,
                text="(No executed operations in history.)",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=COLOR_TEXT_MUTED,
            ).pack(padx=16, pady=24)
            return

        for r in records:
            card = ctk.CTkFrame(
                self._history_scroll,
                corner_radius=10,
                fg_color=COLOR_INPUT_BG,
                border_width=1,
                border_color=COLOR_CARD_BORDER,
            )
            card.pack(fill="x", padx=6, pady=4)
            card.grid_columnconfigure(0, weight=1)

            info_col = ctk.CTkFrame(card, fg_color="transparent")
            info_col.grid(row=0, column=0, padx=12, pady=10, sticky="w")

            time_str = r.timestamp.split("T")[0] + " " + r.timestamp.split("T")[1][:8] if "T" in r.timestamp else r.timestamp
            ctk.CTkLabel(
                info_col,
                text=f"[{time_str}] {Path(r.original_path).name} → {Path(r.destination_path).parent.name}",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color=COLOR_TEXT_PRIMARY,
            ).pack(anchor="w")

            status_txt = f"Status: {r.status.upper()} | Mode: {r.mode}"
            if r.rule_name:
                status_txt += f" | Rule: {r.rule_name}"
            ctk.CTkLabel(
                info_col,
                text=status_txt,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=COLOR_TEXT_MUTED,
            ).pack(anchor="w")

            if r.can_undo and r.status == "success":
                ctk.CTkButton(
                    card,
                    text="↩ Undo Move",
                    width=90,
                    height=28,
                    corner_radius=6,
                    fg_color=COLOR_BUTTON_SECONDARY,
                    hover_color=COLOR_BUTTON_SECONDARY_HOVER,
                    text_color=COLOR_ACCENT_LIGHT,
                    command=lambda op_id=r.operation_id: self._undo_operation(op_id),
                ).grid(row=0, column=2, padx=12, pady=10)

    def _undo_operation(self, op_id: str):
        success, msg = self.executor.undo_operation(op_id)
        self._log_raw(f"[Undo] {msg}\n")
        self._refresh_history_list()

    # -------------------------------------------------------------------
    # Settings callbacks
    # -------------------------------------------------------------------

    def browse_watch_directory(self):
        """Open native folder picker to choose a watched directory."""
        directory = filedialog.askdirectory(title="Select Watched Directory")
        if directory:
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, directory)

    def save_settings(self):
        """Apply model/host settings immediately; persist watch dir via env var."""
        settings.gemma_model = self.model_entry.get()
        settings.ollama_host = self.host_entry.get()

        watch_dir = self.dir_entry.get().strip()
        if watch_dir:
            os.environ["SORTSENSE_WATCHED_DIR"] = watch_dir
            os.environ["FILEMIND_WATCHED_DIR"] = watch_dir
            
            # Apply instantly
            if self.observer:
                self.observer.stop()
                # Do not block the GUI thread joining the observer
            self.start_background_watcher()

        self._log_raw(
            f"[Settings] Saved — model={settings.gemma_model}  host={settings.ollama_host}\n"
            f"[Settings] Watch dir updated: {watch_dir or '(auto-detected)'}\n"
        )

    # -------------------------------------------------------------------
    # Navigation
    # -------------------------------------------------------------------

    def hide_all_frames(self):
        for frame in self.frames.values():
            frame.grid_forget()

    def show_dashboard(self):
        self.hide_all_frames()
        self._set_active_nav(self.dashboard_button)
        self.dashboard_frame.grid(row=0, column=1, sticky="nsew")

    def show_watched(self):
        self.hide_all_frames()
        self._set_active_nav(self.watched_button)
        self.watched_frame.grid(row=0, column=1, sticky="nsew")

    def show_review(self):
        self.hide_all_frames()
        self._set_active_nav(self.review_button)
        self.review_frame.grid(row=0, column=1, sticky="nsew")

    def show_settings(self):
        self.hide_all_frames()
        self._set_active_nav(self.settings_button)
        self.settings_frame.grid(row=0, column=1, sticky="nsew")

    def show_intent(self):
        self.hide_all_frames()
        self._set_active_nav(self.intent_button)
        self._refresh_rules_list()
        self.intent_frame.grid(row=0, column=1, sticky="nsew")

    def show_preview(self):
        self.hide_all_frames()
        self._set_active_nav(self.preview_button)
        self._refresh_preview_list()
        self.preview_frame.grid(row=0, column=1, sticky="nsew")

    def show_history(self):
        self.hide_all_frames()
        self._set_active_nav(self.history_button)
        self._refresh_history_list()
        self.history_frame.grid(row=0, column=1, sticky="nsew")

    def change_appearance_mode_event(self, new_appearance_mode: str):
        ctk.set_appearance_mode(new_appearance_mode)

    # -------------------------------------------------------------------
    # Model status polling
    # -------------------------------------------------------------------

    def check_model_status_thread(self):
        def update_ui(status_text: str, label_color: str, engine_text: str):
            if getattr(self, "_is_shutting_down", False):
                return
            try:
                self.model_status_var.set(status_text)
                if hasattr(self, "model_status_label") and self.model_status_label.winfo_exists():
                    self.model_status_label.configure(text_color=label_color)
                if hasattr(self, "_engine_status_label") and self._engine_status_label.winfo_exists():
                    self._engine_status_label.configure(text=engine_text, text_color=label_color)
            except Exception:
                pass

        def check_status():
            if getattr(self, "_is_shutting_down", False):
                return
            colors = {"gemma_active": COLOR_ACCENT_LIGHT, "model_missing": "#f59e0b", "ollama_unavailable": "#f59e0b",
                      "deterministic": "#38bdf8", "request_failed": "#f87171"}
            try:
                from app.analyzer import OllamaServiceManager
                key, label = OllamaServiceManager.engine_state()
            except Exception:
                key, label = "deterministic", "Deterministic Mode"
            label_color = colors.get(key, "#38bdf8")
            status_text = label
            if key == "gemma_active":
                engine_text = f"{label} - semantic classification and instruction parsing enabled."
            elif key == "model_missing":
                engine_text = f"Ollama is running but '{settings.gemma_model}' is not pulled. Run: ollama pull {settings.gemma_model}. Deterministic mode is active meanwhile."
            else:
                engine_text = f"{label}. Content-based rules, suggestions and manual destinations work fully offline."

            if getattr(self, "_is_shutting_down", False):
                return
            try:
                self.after(0, update_ui, status_text, label_color, engine_text)
                self.after(10000, self.check_model_status_thread)
            except Exception:
                pass

        threading.Thread(target=check_status, daemon=True).start()

    # -------------------------------------------------------------------
    # Watcher & Event pipeline wiring
    # -------------------------------------------------------------------

    def start_background_watcher(self):
        def on_event(event: FileEvent):
            self.after(0, self._dispatch_event, event)

        try:
            self.observer = start_watcher(on_event=on_event)
        except Exception as exc:
            self.after(0, self._log_raw, f"ERROR: Failed to start watcher: {exc}\n")

    def _dispatch_event(self, event: FileEvent):
        """Called on the Tk main thread. Filters by extension, then offloads to worker."""
        ext = Path(event.path).suffix.lower()
        timestamp = event.timestamp.strftime("%H:%M:%S")
        raw_msg = f"[{timestamp}] Detected ({event.event_type}): {event.file_name}\n"
        self._log_raw(raw_msg)

        if ext not in _SUPPORTED_EXTS:
            self._log_raw(f"[{timestamp}] Skipped (unsupported extension '{ext}'): {event.file_name}\n")
            return

        if not _PIPELINE_AVAILABLE:
            self._log_raw(f"[{timestamp}] Pipeline unavailable - skipping {event.file_name}\n")
            return

        key = str(event.path)
        if key in self._inflight:  # duplicate watcher event for a file already being analysed
            return
        self._inflight.add(key)
        threading.Thread(target=self._run_pipeline, args=(event,), daemon=True).start()

    def _rule_override(self, document, analysis):
        """Saved-rule hook (worker thread; read-only). Returns (dest_dir, filename, rule_name) or None."""
        rules = self.rule_manager.get_all_rules(include_disabled=False)
        match = self.rule_matcher.match(document, analysis, rules)
        if match.matched_rule and not match.is_conflict:
            resolved = self.destination_resolver.resolve(
                document=document, analysis=analysis, matched_rule=match.matched_rule)
            return resolved.target_directory, resolved.target_filename, match.matched_rule.rule_name
        return None

    def _run_pipeline(self, event: FileEvent):
        """Worker thread: analyse one file and hand a PROPOSAL to the Tk thread. Never moves files."""
        path = str(event.path)
        filename = event.file_name
        timestamp = event.timestamp.strftime("%H:%M:%S")
        try:
            proposal = process_file(path, base_dir=settings.sorted_base_dir, rule_hook=self._rule_override)
            if proposal is None:
                self.after(0, self._log_raw, f"[{timestamp}] Skipped (incomplete or unreadable): {filename}\n")
            else:
                self.after(0, self._on_proposal, timestamp, proposal)
        except Exception as exc:
            self.after(0, self._on_pipeline_error, timestamp, filename, str(exc))
        finally:
            self.after(0, self._inflight.discard, path)

    def _update_counters(self):
        """Dashboard counters reflect real state: pending = awaiting approval/execution, processed = executed."""
        counts = self.proposals.counts()
        self._pending_count = counts[PENDING] + counts[APPROVED]
        self._pending_var.set(str(self._pending_count))
        self._processed_var.set(str(self._processed_count))

    def _on_proposal(self, timestamp: str, proposal):
        """Tk thread: a new suggestion is waiting for the user."""
        self.proposals.add(proposal)
        dest = proposal.destination_dir if proposal.destination_dir else "(you choose)"
        self._activity_lines.insert(
            0,
            f"- {timestamp} - Suggestion: {proposal.original_name}\n"
            f"  -> {proposal.proposed_name} | {proposal.category} | confidence {proposal.confidence:.0%} "
            f"({proposal.engine})\n  Awaiting your approval\n",
        )
        self._update_counters()
        self._refresh_dashboard_activity()
        self._refresh_review_queue()
        self._log_raw(f"[{timestamp}] PROPOSED: {proposal.original_name} -> {dest}/{proposal.proposed_name} "
                      f"(conf={proposal.confidence:.0%}, {proposal.engine})\n")

    def _on_pipeline_error(self, timestamp: str, filename: str, error: str):
        """Called on Tk thread for unexpected pipeline exceptions."""
        self._log_raw(f"[{timestamp}] ERROR processing {filename}: {error}\n")

    def _refresh_dashboard_activity(self):
        """Rewrite the Recent Activity textbox from self._activity_lines (newest first)."""
        self._dashboard_activity_box.configure(state="normal")
        self._dashboard_activity_box.delete("0.0", "end")
        for line in self._activity_lines[:10]:
            self._dashboard_activity_box.insert("end", line)
        self._dashboard_activity_box.configure(state="disabled")

    # -- Review Queue = approval screen ------------------------------------

    def _open_proposals(self):
        return [p for p in self.proposals.items() if p.status in (PENDING, APPROVED, REJECTED, FAILED)]

    def _refresh_review_queue(self):
        for widget in self._review_scroll.winfo_children():
            widget.destroy()
        self._name_entries = {}
        items = self._open_proposals()
        if not items:
            self._review_empty_label = ctk.CTkLabel(
                self._review_scroll, text="(Nothing waiting for review)",
                font=ctk.CTkFont(family="Segoe UI", size=13), text_color=COLOR_TEXT_MUTED)
            self._review_empty_label.grid(row=0, column=0, padx=16, pady=24)
            return
        status_color = {PENDING: "#fbbf24", APPROVED: COLOR_ACCENT_LIGHT, REJECTED: COLOR_TEXT_MUTED, FAILED: "#f87171"}
        for i, p in enumerate(items):
            card = ctk.CTkFrame(self._review_scroll, corner_radius=12, fg_color=COLOR_CARD_BG,
                                border_width=1, border_color=COLOR_CARD_BORDER)
            card.grid(row=i, column=0, padx=4, pady=5, sticky="ew")
            card.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(card, text=f"{p.original_name}", anchor="w",
                         font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                         text_color=COLOR_TEXT_PRIMARY).grid(row=0, column=0, columnspan=2, padx=12, pady=(10, 2), sticky="w")
            ctk.CTkLabel(card, text=p.status.upper(), text_color=status_color.get(p.status, COLOR_TEXT_MUTED),
                         font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold")).grid(row=0, column=2, padx=12, sticky="e")

            entry = ctk.CTkEntry(card, height=30, fg_color=COLOR_INPUT_BG)
            entry.insert(0, p.proposed_name)
            entry.grid(row=1, column=0, columnspan=2, padx=12, pady=2, sticky="ew")
            entry.bind("<FocusOut>", lambda _e, pid=p.id: self._commit_name(pid))
            entry.bind("<Return>", lambda _e, pid=p.id: self._commit_name(pid))
            self._name_entries[p.id] = entry

            dest = str(p.destination_dir) if p.destination_dir else "No destination yet - click Folder... to choose"
            ctk.CTkLabel(card, text=f"Folder: {dest}", anchor="w", text_color=COLOR_TEXT_SECONDARY,
                         font=ctk.CTkFont(family="Segoe UI", size=11)).grid(row=2, column=0, columnspan=3, padx=12, sticky="w")
            detail = f"{p.category} | confidence {p.confidence:.0%} | {p.engine}"
            if p.evidence:
                detail += " | " + p.evidence[0]
            ctk.CTkLabel(card, text=detail, anchor="w", justify="left", wraplength=620, text_color=COLOR_TEXT_MUTED,
                         font=ctk.CTkFont(family="Segoe UI", size=11)).grid(row=3, column=0, columnspan=3, padx=12, sticky="w")
            warn = " | ".join(p.warnings + ([p.error] if p.error else []))
            if warn:
                ctk.CTkLabel(card, text=warn, anchor="w", justify="left", wraplength=620, text_color="#fbbf24",
                             font=ctk.CTkFont(family="Segoe UI", size=11)).grid(row=4, column=0, columnspan=3, padx=12, sticky="w")

            btns = ctk.CTkFrame(card, fg_color="transparent")
            btns.grid(row=5, column=0, columnspan=3, padx=10, pady=(6, 10), sticky="e")
            for label, cmd, color in (
                ("Folder...", lambda pid=p.id: self._choose_proposal_folder(pid), COLOR_BUTTON_SECONDARY),
                ("Approve", lambda pid=p.id: self._approve_proposal(pid), COLOR_ACCENT),
                ("Reject", lambda pid=p.id: self._reject_proposal(pid), COLOR_BUTTON_SECONDARY),
            ):
                ctk.CTkButton(btns, text=label, width=84, height=30, corner_radius=8, fg_color=color,
                              command=cmd).pack(side="left", padx=4)

    def _commit_name(self, pid: int):
        entry = getattr(self, "_name_entries", {}).get(pid)
        if entry is not None:
            try:
                self.proposals.set_name(pid, entry.get())
            except (KeyError, ValueError) as exc:
                self._log_raw(f"[Review] {exc}\n")

    def _choose_proposal_folder(self, pid: int):
        p = self.proposals.get(pid)
        if p is None:
            return
        initial = str(p.destination_dir) if p.destination_dir and Path(p.destination_dir).exists() else str(Path.home())
        chosen = filedialog.askdirectory(title=f"Where should '{p.original_name}' go?", initialdir=initial)
        if not chosen:
            return  # cancelled: change nothing
        try:
            self.proposals.set_destination(pid, chosen)
        except (KeyError, ValueError) as exc:
            self._log_raw(f"[Review] Invalid destination: {exc}\n")
        self._refresh_review_queue()

    def _approve_proposal(self, pid: int):
        self._commit_name(pid)
        try:
            self.proposals.approve(pid)
        except (KeyError, ValueError) as exc:
            self._log_raw(f"[Review] Cannot approve: {exc}\n")
        self._update_counters()
        self._refresh_review_queue()

    def _reject_proposal(self, pid: int):
        try:
            self.proposals.reject(pid)
        except (KeyError, ValueError) as exc:
            self._log_raw(f"[Review] {exc}\n")
        self._update_counters()
        self._refresh_review_queue()

    def _approve_all_proposals(self):
        """Approve every pending suggestion that has a destination (the user still presses Execute)."""
        for p in self.proposals.items(PENDING):
            self._commit_name(p.id)
        ready = [p.id for p in self.proposals.items(PENDING) if p.destination_dir is not None]
        _done, errors = self.proposals.approve_many(ready)
        for pid, err in errors.items():
            self._log_raw(f"[Review] {err}\n")
        self._update_counters()
        self._refresh_review_queue()

    def _execute_approved_proposals(self):
        def worker():
            ok, bad, errs = self.proposals.execute_approved()
            self.after(0, self._on_proposals_executed, ok, bad, errs)
        threading.Thread(target=worker, daemon=True).start()

    def _on_proposals_executed(self, ok: int, bad: int, errors: list[str]):
        self._processed_count += ok
        self._update_counters()
        self._log_raw(f"[Execute] Moved: {ok}, Failed: {bad}\n")
        for err in errors:
            self._log_raw(f"[Execute] {err}\n")
        self._activity_lines.insert(0, f"- Executed {ok} approved file(s); {bad} failed\n")
        self._refresh_dashboard_activity()
        self._refresh_review_queue()
        self._refresh_history_list()

    def _log_raw(self, msg: str):
        """Append a raw message to the Activity Log textbox. Tk-thread only."""
        print(msg.strip())  # Also log to terminal
        self.activity_textbox.configure(state="normal")
        self.activity_textbox.insert("end", msg)
        self.activity_textbox.see("end")
        self.activity_textbox.configure(state="disabled")

    def log_activity(self, event: FileEvent):
        """Alias preserved for backward compatibility."""
        self._dispatch_event(event)

    def log_error(self, msg: str):
        """Alias preserved for backward compatibility."""
        self._log_raw(f"ERROR: {msg}\n")


if __name__ == "__main__":
    app = SortSenseApp()
    app.mainloop()
