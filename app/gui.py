"""
SortSense GUI — real-time dashboard wired to the live processing pipeline.

Architecture:
  watcher thread  →  FileEvent
                 →  self.after(0, _dispatch_event)   [marshal to Tk thread]
                 →  threading.Thread(_run_pipeline)   [off Tk thread: IO + Ollama]
                 →  self.after(0, _on_organize | _on_review | _on_pipeline_error)
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

# ---------------------------------------------------------------------------
# Pipeline imports — all pipeline errors must be caught locally so the GUI
# never crashes due to a single bad file.
# ---------------------------------------------------------------------------
try:
    from app.ingestion import ingest_file
    from app.analyzer import analyze_document, OllamaUnavailableError, AnalysisParseError
    from app.validation import validate_analysis
    from app.organizer import decide
    _PIPELINE_AVAILABLE = True
except Exception:  # pragma: no cover
    _PIPELINE_AVAILABLE = False

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
        self.dashboard_button.pack(fill="x", pady=4)

        self.watched_button = self._create_nav_button("📋   Activity Log", self.show_watched)
        self.watched_button.pack(fill="x", pady=4)

        review_container = ctk.CTkFrame(self.nav_frame, fg_color="transparent")
        review_container.pack(fill="x", pady=4)

        self.review_button = ctk.CTkButton(
            review_container,
            text="⏳   Review Queue",
            anchor="w",
            height=40,
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
        self.settings_button.pack(fill="x", pady=4)

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
        self.watched_frame = self._create_watched_frame()
        self.review_frame = self._create_review_frame()
        self.settings_frame = self._create_settings_frame()

        self.frames["Dashboard"] = self.dashboard_frame
        self.frames["Watched"] = self.watched_frame
        self.frames["Review"] = self.review_frame
        self.frames["Settings"] = self.settings_frame

        # ---------------------------------------------------------------
        # Background tasks
        # ---------------------------------------------------------------
        self.check_model_status_thread()

        self.observer = None
        self.start_background_watcher()

        self.show_dashboard()

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
        for btn in [self.dashboard_button, self.watched_button, self.review_button, self.settings_button]:
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
            text="These files had low confidence or validation issues and require manual sorting.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
        )
        desc.pack(anchor="w", pady=(2, 0))

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
            os.environ["FILEMIND_WATCHED_DIR"] = watch_dir

        self._log_raw(
            f"[Settings] Saved — model={settings.gemma_model}  host={settings.ollama_host}\n"
            f"[Settings] Watch dir: {watch_dir or '(auto-detected)'}\n"
            f"[Settings] Restart the app to apply any watch-directory change.\n"
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

    def change_appearance_mode_event(self, new_appearance_mode: str):
        ctk.set_appearance_mode(new_appearance_mode)

    # -------------------------------------------------------------------
    # Model status polling
    # -------------------------------------------------------------------

    def check_model_status_thread(self):
        def check_status():
            try:
                import ollama
                client = ollama.Client(host=settings.ollama_host)
                client.list()
                self.model_status_var.set("🟢 Active (Ollama Running)")
                self.model_status_label.configure(text_color=COLOR_ACCENT_LIGHT)
            except Exception:
                self.model_status_var.set("🔴 Offline (Cannot reach Ollama)")
                self.model_status_label.configure(text_color="#f87171")

            self.after(10000, self.check_model_status_thread)

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
            self._log_raw(f"[{timestamp}] Pipeline unavailable — skipping {event.file_name}\n")
            return

        threading.Thread(
            target=self._run_pipeline,
            args=(event,),
            daemon=True,
        ).start()

    def _run_pipeline(self, event: FileEvent):
        """Full pipeline for a single FileEvent. All UI updates via self.after()."""
        path = str(event.path)
        filename = event.file_name
        timestamp = event.timestamp.strftime("%H:%M:%S")
        ext = Path(event.path).suffix.lower().lstrip(".")

        try:
            document = ingest_file(path)

            if document.extraction_status not in ("ok", "empty"):
                reason = f"Ingestion failed: {document.extraction_status}"
                self.after(0, self._on_review, timestamp, filename, reason, path, "", filename)
                return

            try:
                analysis = analyze_document(document)
            except OllamaUnavailableError:
                reason = "AI service unavailable (Ollama offline)"
                self.after(0, self._on_review, timestamp, filename, reason, path, "", filename)
                return
            except AnalysisParseError as exc:
                reason = f"AI parse error: {exc}"
                self.after(0, self._on_review, timestamp, filename, reason, path, "", filename)
                return

            validation = validate_analysis(document, analysis)
            decision = decide(analysis, validation, original_extension=ext)

            if decision.action == "organize":
                # Smart folder: find existing matching folder or create new one
                base = settings.sorted_base_dir
                existing = _find_existing_category_folder(base, analysis.category)
                target_dir = existing if existing else (base / analysis.category)

                try:
                    dest = _safe_move(Path(path), target_dir, analysis.new_filename)
                    self.after(
                        0, self._on_organize,
                        timestamp, filename,
                        analysis.document_type, analysis.category,
                        analysis.confidence, str(target_dir),
                        dest.name,
                    )
                except Exception as move_exc:
                    self.after(0, self._on_pipeline_error, timestamp, filename, str(move_exc))
            else:
                reason = decision.reason
                suggested_dir = str(settings.sorted_base_dir / analysis.category)
                self.after(0, self._on_review, timestamp, filename, reason,
                           path, suggested_dir, decision.suggested_filename)

        except Exception as exc:
            self.after(0, self._on_pipeline_error, timestamp, filename, str(exc))

    def _on_organize(
        self,
        timestamp: str,
        filename: str,
        doc_type: str,
        category: str,
        confidence: float,
        destination: str,
        new_filename: str,
    ):
        """Called on Tk thread when a file is successfully moved and renamed."""
        self._processed_count += 1
        self._processed_var.set(str(self._processed_count))

        line = (
            f"• {timestamp} — ✅ {filename}\n"
            f"  Type: {doc_type} | Category: {category} | "
            f"Confidence: {confidence:.0%}\n"
            f"  Renamed → {new_filename}\n"
            f"  Moved to → {destination}\n"
        )
        self._activity_lines.insert(0, line)

        self._refresh_dashboard_activity()
        self._log_raw(
            f"[{timestamp}] ORGANIZED: {filename} → {destination}/{new_filename} "
            f"(conf={confidence:.0%})\n"
        )

    def _on_review(
        self,
        timestamp: str,
        filename: str,
        reason: str,
        src_path: str = "",
        suggested_dir: str = "",
        suggested_name: str = "",
    ):
        """Called on Tk thread when a file needs human review."""
        self._pending_count += 1
        self._pending_var.set(str(self._pending_count))

        activity_line = (
            f"• {timestamp} — ⚠️  {filename} → Review Queue\n"
            f"  Reason: {reason}\n"
        )
        self._activity_lines.insert(0, activity_line)

        self._review_items.append((filename, reason, src_path, suggested_dir, suggested_name))
        self._refresh_dashboard_activity()
        self._refresh_review_queue()
        self._log_raw(f"[{timestamp}] REVIEW: {filename} — {reason}\n")

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

    def _refresh_review_queue(self):
        """Rebuild the review queue scrollable frame from self._review_items with modern styling."""
        for widget in self._review_scroll.winfo_children():
            widget.destroy()

        if not self._review_items:
            self._review_empty_label = ctk.CTkLabel(
                self._review_scroll,
                text="(Review queue is empty)",
                font=ctk.CTkFont(family="Segoe UI", size=13),
                text_color=COLOR_TEXT_MUTED,
            )
            self._review_empty_label.grid(row=0, column=0, padx=16, pady=24)
            return

        for i, item in enumerate(self._review_items):
            fname = item[0]
            reason = item[1]

            item_frame = ctk.CTkFrame(
                self._review_scroll,
                corner_radius=12,
                fg_color=COLOR_CARD_BG,
                border_width=1,
                border_color=COLOR_CARD_BORDER,
                height=62,
            )
            item_frame.grid(row=i, column=0, padx=4, pady=5, sticky="ew")
            item_frame.grid_columnconfigure(1, weight=1)

            file_icon = ctk.CTkFrame(
                item_frame,
                width=34,
                height=34,
                corner_radius=8,
                fg_color=COLOR_BUTTON_SECONDARY,
            )
            file_icon.grid(row=0, column=0, padx=(14, 10), pady=12)
            file_icon.grid_propagate(False)
            ctk.CTkLabel(
                file_icon,
                text="📄",
                font=ctk.CTkFont(size=14),
            ).place(relx=0.5, rely=0.5, anchor="center")

            ctk.CTkLabel(
                item_frame,
                text=fname,
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color=COLOR_TEXT_PRIMARY,
            ).grid(row=0, column=1, padx=4, pady=12, sticky="w")

            badge = ctk.CTkFrame(
                item_frame,
                corner_radius=8,
                fg_color="#2b1e10",
                border_width=1,
                border_color="#78350f",
            )
            badge.grid(row=0, column=2, padx=12, pady=12)
            ctk.CTkLabel(
                badge,
                text=reason,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#fbbf24",
            ).pack(padx=10, pady=3)

            ctk.CTkButton(
                item_frame,
                text="Review",
                width=84,
                height=32,
                corner_radius=8,
                fg_color=COLOR_BUTTON_SECONDARY,
                hover_color=COLOR_BUTTON_SECONDARY_HOVER,
                text_color=COLOR_TEXT_PRIMARY,
                border_width=1,
                border_color="#263345",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                command=lambda it=item: self._manual_review(it),
            ).grid(row=0, column=3, padx=(4, 14), pady=12)

    def _manual_review(self, item: tuple):
        """Open folder picker, move and rename the file, remove from queue."""
        fname = item[0]
        src_path = item[2] if len(item) > 2 else ""
        suggested_dir = item[3] if len(item) > 3 else ""
        suggested_name = item[4] if len(item) > 4 else ""

        if not src_path or not Path(src_path).exists():
            self._log_raw(f"[Review] File no longer exists: {src_path or fname}\n")
            self._remove_review_item(item)
            return

        initial_dir = suggested_dir if suggested_dir and Path(suggested_dir).exists() else str(Path.home())
        target_dir = filedialog.askdirectory(
            title=f"Where should '{fname}' go?",
            initialdir=initial_dir,
        )
        if not target_dir:
            return  # user cancelled — do nothing

        use_name = suggested_name if suggested_name else Path(src_path).name

        try:
            dest = _safe_move(Path(src_path), Path(target_dir), use_name)
            self._log_raw(
                f"[Review] Manually organised: {fname}\n"
                f"  Renamed → {dest.name}\n"
                f"  Moved to → {target_dir}\n"
            )
            self._processed_count += 1
            self._processed_var.set(str(self._processed_count))
            line = (
                f"• [manual] — ✅ {fname}\n"
                f"  Renamed → {dest.name} | Moved to → {target_dir}\n"
            )
            self._activity_lines.insert(0, line)
            self._refresh_dashboard_activity()
            self._remove_review_item(item)
        except Exception as exc:
            self._log_raw(f"[Review] Error moving {fname}: {exc}\n")

    def _remove_review_item(self, item: tuple):
        if item in self._review_items:
            self._review_items.remove(item)
            self._pending_count = max(0, self._pending_count - 1)
            self._pending_var.set(str(self._pending_count))
            self._refresh_review_queue()

    def _log_raw(self, msg: str):
        """Append a raw message to the Activity Log textbox. Tk-thread only."""
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
