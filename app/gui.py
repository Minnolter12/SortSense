import tkinter as tk
import customtkinter as ctk
import time
import threading
from pathlib import Path

from app.config import settings
from app.watcher import start_watcher
from app.events import FileEvent

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


class SortSenseApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SortSense — Gemma Local File Organizer")
        self.geometry("1060x720")
        self.minsize(960, 640)
        self.configure(fg_color=COLOR_BG)

        # Main window grid layout (sidebar + content)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0, minsize=240)
        self.grid_columnconfigure(1, weight=1)

        # Create sidebar frame
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
        self.sidebar_frame.grid_rowconfigure(2, weight=1)  # Space between nav and bottom info

        # --- Sidebar Brand Header ---
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

        # --- Navigation Buttons ---
        self.nav_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.nav_frame.grid(row=1, column=0, padx=14, pady=0, sticky="ew")

        self.dashboard_button = self._create_nav_button("⊞   Dashboard", self.show_dashboard)
        self.dashboard_button.pack(fill="x", pady=4)

        self.watched_button = self._create_nav_button("📋   Activity Log", self.show_watched)
        self.watched_button.pack(fill="x", pady=4)

        # Review Queue button container with count badge
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

        review_badge = ctk.CTkFrame(
            review_container,
            width=22,
            height=22,
            corner_radius=11,
            fg_color="#2b1e10",
            border_width=1,
            border_color="#78350f",
        )
        review_badge.pack(side="right", padx=(4, 6))
        review_badge.pack_propagate(False)
        ctk.CTkLabel(
            review_badge,
            text="3",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#fbbf24",
        ).place(relx=0.5, rely=0.5, anchor="center")

        self.settings_button = self._create_nav_button("⚙   Settings", self.show_settings)
        self.settings_button.pack(fill="x", pady=4)

        # --- Sidebar Bottom Info & Theme Control ---
        bottom_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        bottom_frame.grid(row=3, column=0, padx=14, pady=16, sticky="sew")

        # Watched folder card in sidebar
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

        # Appearance mode switcher
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

        # Initial state variables
        self.model_status_var = ctk.StringVar(value="Checking...")

        # Create main content frames
        self.frames = {}
        self.dashboard_frame = self.create_dashboard_frame()
        self.watched_frame = self.create_watched_frame()
        self.review_frame = self.create_review_frame()
        self.settings_frame = self.create_settings_frame()

        self.frames["Dashboard"] = self.dashboard_frame
        self.frames["Watched"] = self.watched_frame
        self.frames["Review"] = self.review_frame
        self.frames["Settings"] = self.settings_frame

        # Start polling model status
        self.check_model_status_thread()

        # Data lists
        self.watched_files = []

        # Start watching
        self.observer = None
        self.start_background_watcher()

        # Select default frame
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

    def create_dashboard_frame(self):
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
            text="142",
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
            text="3",
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

        ctk.CTkLabel(
            activity_section_header,
            text="3 events logged",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_TEXT_MUTED,
        ).pack(side="right")

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

        activity_box = ctk.CTkTextbox(
            activity_card,
            corner_radius=10,
            fg_color="#0a0e14",
            border_width=1,
            border_color="#18202d",
            text_color="#cbd5e1",
            font=ctk.CTkFont(family="Consolas", size=13),
        )
        activity_box.grid(row=0, column=0, padx=14, pady=14, sticky="nsew")
        activity_box.insert(
            "0.0",
            "• 10:45 AM - Processed 'IMG-WA0012.pdf' -> Utilities/Electricity_Bill.pdf\n"
            "• 10:30 AM - Processed 'document.pdf' -> Documents/Syllabus.pdf\n"
            "• 09:15 AM - Sent 'unknown.txt' to Review Queue\n",
        )
        activity_box.configure(state="disabled")

        return frame

    def create_watched_frame(self):
        frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        # Header area
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

        # Terminal / Log card
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

    def create_review_frame(self):
        frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)

        # Header area
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
            text="These files had low confidence or missing categories and require manual sorting.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
        )
        desc.pack(anchor="w", pady=(2, 0))

        # Mock items matching existing placeholders
        items = [
            ("scan_001.pdf", "Low Confidence (0.4)", "#2b1e10", "#fbbf24", "#78350f"),
            ("notes.txt", "No Category Found", "#21182c", "#c084fc", "#53247d"),
            ("receipt_unclear.jpg", "OCR Failed", "#291216", "#f87171", "#6e1f2b"),
        ]

        items_container = ctk.CTkFrame(frame, fg_color="transparent")
        items_container.grid(row=1, column=0, padx=28, pady=0, sticky="ew")
        items_container.grid_columnconfigure(0, weight=1)

        for i, (fname, reason, badge_bg, badge_txt, badge_border) in enumerate(items):
            item_frame = ctk.CTkFrame(
                items_container,
                corner_radius=12,
                fg_color=COLOR_CARD_BG,
                border_width=1,
                border_color=COLOR_CARD_BORDER,
                height=62,
            )
            item_frame.grid(row=i, column=0, padx=0, pady=6, sticky="ew")
            item_frame.grid_columnconfigure(1, weight=1)

            # File icon badge
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

            # File name
            ctk.CTkLabel(
                item_frame,
                text=fname,
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color=COLOR_TEXT_PRIMARY,
            ).grid(row=0, column=1, padx=4, pady=12, sticky="w")

            # Reason Tag Badge
            badge = ctk.CTkFrame(
                item_frame,
                corner_radius=8,
                fg_color=badge_bg,
                border_width=1,
                border_color=badge_border,
            )
            badge.grid(row=0, column=2, padx=12, pady=12)
            ctk.CTkLabel(
                badge,
                text=reason,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=badge_txt,
            ).pack(padx=10, pady=3)

            # Review Action Button
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
            ).grid(row=0, column=3, padx=(4, 14), pady=12)

        return frame

    def create_settings_frame(self):
        frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)

        # Header area
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

        # Main settings card
        card = ctk.CTkFrame(
            frame,
            corner_radius=14,
            fg_color=COLOR_CARD_BG,
            border_width=1,
            border_color=COLOR_CARD_BORDER,
        )
        card.grid(row=1, column=0, padx=28, pady=8, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        # 1. Watched Directory Setting
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

        dir_entry = ctk.CTkEntry(
            dir_input_row,
            corner_radius=8,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_CARD_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
            height=38,
        )
        dir_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        dir_entry.insert(0, ", ".join(str(d) for d in settings.watched_dirs))

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
        ).grid(row=0, column=1)

        # 2. Gemma Model Setting
        model_section = ctk.CTkFrame(card, fg_color="transparent")
        model_section.pack(fill="x", padx=20, pady=12)

        ctk.CTkLabel(
            model_section,
            text="Gemma Model",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        ).pack(anchor="w", pady=(0, 6))

        model_entry = ctk.CTkEntry(
            model_section,
            corner_radius=8,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_CARD_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
            height=38,
        )
        model_entry.pack(fill="x")
        model_entry.insert(0, settings.gemma_model)

        # 3. Ollama Host Setting
        host_section = ctk.CTkFrame(card, fg_color="transparent")
        host_section.pack(fill="x", padx=20, pady=12)

        ctk.CTkLabel(
            host_section,
            text="Ollama Host",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        ).pack(anchor="w", pady=(0, 6))

        host_entry = ctk.CTkEntry(
            host_section,
            corner_radius=8,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_CARD_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
            height=38,
        )
        host_entry.pack(fill="x")
        host_entry.insert(0, settings.ollama_host)

        # Save Button Row
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
        )
        save_btn.pack(side="right")

        return frame

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

            # Re-check every 10 seconds
            self.after(10000, self.check_model_status_thread)

        threading.Thread(target=check_status, daemon=True).start()

    def start_background_watcher(self):
        def on_event(event: FileEvent):
            # Update UI from main thread
            self.after(0, self.log_activity, event)

        try:
            self.observer = start_watcher(on_event=on_event)
        except Exception as e:
            self.after(0, self.log_error, f"Failed to start watcher: {e}")

    def log_activity(self, event: FileEvent):
        timestamp = event.timestamp.strftime("%H:%M:%S")
        msg = f"[{timestamp}] File {event.event_type}: {event.path}\n"

        self.activity_textbox.configure(state="normal")
        self.activity_textbox.insert("end", msg)
        self.activity_textbox.see("end")
        self.activity_textbox.configure(state="disabled")

    def log_error(self, msg: str):
        self.activity_textbox.configure(state="normal")
        self.activity_textbox.insert("end", f"ERROR: {msg}\n")
        self.activity_textbox.see("end")
        self.activity_textbox.configure(state="disabled")


if __name__ == "__main__":
    app = SortSenseApp()
    app.mainloop()
