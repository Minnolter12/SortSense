"""
SortSense GUI — real-time dashboard wired to the live processing pipeline.

Architecture:
  watcher thread  →  FileEvent
                 →  self.after(0, _dispatch_event)   [marshal to Tk thread]
                 →  threading.Thread(_run_pipeline)   [off Tk thread: IO + Ollama]
                 →  self.after(0, _on_organize | _on_review | _on_pipeline_error)
                                                      [marshal result to Tk thread]
"""

import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path

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

# Configure appearance
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class SortSenseApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SortSense — Gemma Local File Organizer")
        self.geometry("1000x700")

        # set grid layout 1x2
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # ---------------------------------------------------------------
        # Internal state (source of truth for all dynamic dashboard values)
        # ---------------------------------------------------------------
        self._processed_count = 0
        self._pending_count = 0
        self._activity_lines: list[str] = []   # newest-first
        self._review_items: list[tuple[str, str]] = []  # (filename, reason)

        # StringVars for the dashboard cards
        self.model_status_var = ctk.StringVar(value="Checking...")
        self._processed_var = ctk.StringVar(value="0")
        self._pending_var = ctk.StringVar(value="0")

        # ---------------------------------------------------------------
        # Sidebar
        # ---------------------------------------------------------------
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(5, weight=1)

        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame, text="SortSense",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.dashboard_button = ctk.CTkButton(
            self.sidebar_frame, text="Dashboard", command=self.show_dashboard
        )
        self.dashboard_button.grid(row=1, column=0, padx=20, pady=10)

        self.watched_button = ctk.CTkButton(
            self.sidebar_frame, text="Activity Log", command=self.show_watched
        )
        self.watched_button.grid(row=2, column=0, padx=20, pady=10)

        self.review_button = ctk.CTkButton(
            self.sidebar_frame, text="Review Queue", command=self.show_review
        )
        self.review_button.grid(row=3, column=0, padx=20, pady=10)

        self.settings_button = ctk.CTkButton(
            self.sidebar_frame, text="Settings", command=self.show_settings
        )
        self.settings_button.grid(row=4, column=0, padx=20, pady=10)

        self.appearance_mode_label = ctk.CTkLabel(
            self.sidebar_frame, text="Appearance Mode:", anchor="w"
        )
        self.appearance_mode_label.grid(row=6, column=0, padx=20, pady=(10, 0))
        self.appearance_mode_optionemenu = ctk.CTkOptionMenu(
            self.sidebar_frame,
            values=["System", "Light", "Dark"],
            command=self.change_appearance_mode_event,
        )
        self.appearance_mode_optionemenu.grid(row=7, column=0, padx=20, pady=(10, 20))

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

    # -------------------------------------------------------------------
    # Frame builders
    # -------------------------------------------------------------------

    def _create_dashboard_frame(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(3, weight=1)

        title = ctk.CTkLabel(
            frame, text="Dashboard Overview",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title.grid(row=0, column=0, padx=20, pady=20, sticky="w")

        # --- Status Cards ---
        cards_frame = ctk.CTkFrame(frame, fg_color="transparent")
        cards_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        cards_frame.grid_columnconfigure((0, 1, 2), weight=1)

        # Model Status card
        model_card = ctk.CTkFrame(cards_frame)
        model_card.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(
            model_card, text="Model Status",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=10)
        self.model_status_label = ctk.CTkLabel(
            model_card, textvariable=self.model_status_var,
            font=ctk.CTkFont(size=14)
        )
        self.model_status_label.pack(pady=10)

        # Files Processed card — live counter
        processed_card = ctk.CTkFrame(cards_frame)
        processed_card.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(
            processed_card, text="Files Processed",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=10)
        ctk.CTkLabel(
            processed_card,
            textvariable=self._processed_var,
            font=ctk.CTkFont(size=24),
        ).pack(pady=10)

        # Pending Review card — live counter
        review_card = ctk.CTkFrame(cards_frame)
        review_card.grid(row=0, column=2, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(
            review_card, text="Pending Review",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=10)
        ctk.CTkLabel(
            review_card,
            textvariable=self._pending_var,
            font=ctk.CTkFont(size=24),
        ).pack(pady=10)

        # Recent Activity textbox — starts empty, updated by pipeline
        ctk.CTkLabel(
            frame, text="Recent Activity",
            font=ctk.CTkFont(size=18, weight="bold")
        ).grid(row=2, column=0, padx=20, pady=(20, 10), sticky="w")

        self._dashboard_activity_box = ctk.CTkTextbox(frame, height=200)
        self._dashboard_activity_box.grid(row=3, column=0, padx=20, pady=10, sticky="nsew")
        self._dashboard_activity_box.insert("0.0", "(No files processed yet — drop a file into the watched directory)\n")
        self._dashboard_activity_box.configure(state="disabled")

        return frame

    def _create_watched_frame(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        title = ctk.CTkLabel(
            frame, text="Activity Log / Watched Files",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title.grid(row=0, column=0, padx=20, pady=20, sticky="w")

        self.activity_textbox = ctk.CTkTextbox(frame)
        self.activity_textbox.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        self.activity_textbox.insert(
            "0.0", f"Watching directory: {settings.watched_dir}\n\n"
        )
        self.activity_textbox.configure(state="disabled")

        return frame

    def _create_review_frame(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        title = ctk.CTkLabel(
            frame, text="Review Queue",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title.grid(row=0, column=0, padx=20, pady=20, sticky="w")

        desc = ctk.CTkLabel(
            frame,
            text="These files had low confidence or validation issues and require manual sorting.",
            text_color="gray",
        )
        desc.grid(row=1, column=0, padx=20, pady=0, sticky="w")

        # Scrollable container for dynamic review rows
        self._review_scroll = ctk.CTkScrollableFrame(frame)
        self._review_scroll.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")
        self._review_scroll.grid_columnconfigure(1, weight=1)

        # Placeholder shown when queue is empty
        self._review_empty_label = ctk.CTkLabel(
            self._review_scroll,
            text="(Review queue is empty)",
            text_color="gray",
        )
        self._review_empty_label.grid(row=0, column=0, padx=10, pady=20)

        return frame

    def _create_settings_frame(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            frame, text="Settings", font=ctk.CTkFont(size=24, weight="bold")
        )
        title.grid(row=0, column=0, padx=20, pady=20, sticky="w")

        # Watched Directory
        dir_frame = ctk.CTkFrame(frame)
        dir_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        dir_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(dir_frame, text="Watched Directory:").grid(row=0, column=0, padx=10, pady=10)
        dir_entry = ctk.CTkEntry(dir_frame)
        dir_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        dir_entry.insert(0, str(settings.watched_dir))
        ctk.CTkButton(dir_frame, text="Browse", width=80).grid(row=0, column=2, padx=10, pady=10)

        # Gemma Model
        model_frame = ctk.CTkFrame(frame)
        model_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        model_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(model_frame, text="Gemma Model:").grid(row=0, column=0, padx=10, pady=10)
        model_entry = ctk.CTkEntry(model_frame)
        model_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        model_entry.insert(0, settings.gemma_model)

        # Ollama Host
        host_frame = ctk.CTkFrame(frame)
        host_frame.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        host_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(host_frame, text="Ollama Host:").grid(row=0, column=0, padx=10, pady=10)
        host_entry = ctk.CTkEntry(host_frame)
        host_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        host_entry.insert(0, settings.ollama_host)

        ctk.CTkButton(frame, text="Save Settings").grid(row=4, column=0, padx=20, pady=20, sticky="e")

        return frame

    # -------------------------------------------------------------------
    # Navigation
    # -------------------------------------------------------------------

    def hide_all_frames(self):
        for f in self.frames.values():
            f.grid_forget()

    def show_dashboard(self):
        self.hide_all_frames()
        self.dashboard_frame.grid(row=0, column=1, sticky="nsew")

    def show_watched(self):
        self.hide_all_frames()
        self.watched_frame.grid(row=0, column=1, sticky="nsew")

    def show_review(self):
        self.hide_all_frames()
        self.review_frame.grid(row=0, column=1, sticky="nsew")

    def show_settings(self):
        self.hide_all_frames()
        self.settings_frame.grid(row=0, column=1, sticky="nsew")

    def change_appearance_mode_event(self, new_appearance_mode: str):
        ctk.set_appearance_mode(new_appearance_mode)

    # -------------------------------------------------------------------
    # Model status poller (existing behaviour preserved)
    # -------------------------------------------------------------------

    def check_model_status_thread(self):
        def check_status():
            try:
                import ollama
                client = ollama.Client(host=settings.ollama_host)
                client.list()
                self.model_status_var.set("🟢 Active (Ollama Running)")
                self.model_status_label.configure(text_color="green")
            except Exception:
                self.model_status_var.set("🔴 Offline (Cannot reach Ollama)")
                self.model_status_label.configure(text_color="red")

            self.after(10000, self.check_model_status_thread)

        threading.Thread(target=check_status, daemon=True).start()

    # -------------------------------------------------------------------
    # Watcher
    # -------------------------------------------------------------------

    def start_background_watcher(self):
        def on_event(event: FileEvent):
            # Marshal from watcher thread → Tk main thread
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

        # Run the pipeline off the Tk thread so the UI stays responsive
        threading.Thread(
            target=self._run_pipeline,
            args=(event,),
            daemon=True,
        ).start()

    # -------------------------------------------------------------------
    # Pipeline worker (runs on a non-Tk thread — NO widget calls here)
    # -------------------------------------------------------------------

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
                self.after(0, self._on_review, timestamp, filename, reason)
                return

            try:
                analysis = analyze_document(document)
            except OllamaUnavailableError:
                reason = "AI service unavailable (Ollama offline)"
                self.after(0, self._on_review, timestamp, filename, reason)
                return
            except AnalysisParseError as exc:
                reason = f"AI parse error: {exc}"
                self.after(0, self._on_review, timestamp, filename, reason)
                return

            validation = validate_analysis(document, analysis)
            decision = decide(analysis, validation, original_extension=ext)

            if decision.action == "organize":
                self.after(
                    0, self._on_organize,
                    timestamp, filename,
                    analysis.document_type, analysis.category,
                    analysis.confidence, decision.destination_folder,
                    analysis.new_filename,
                )
            else:
                # review: collect most relevant issue as the reason
                reason = decision.reason
                self.after(0, self._on_review, timestamp, filename, reason)

        except Exception as exc:  # broad catch — one bad file must not crash the watcher
            self.after(0, self._on_pipeline_error, timestamp, filename, str(exc))

    # -------------------------------------------------------------------
    # Tk-thread UI update handlers
    # -------------------------------------------------------------------

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
        """Called on Tk thread when a file passes pipeline and gets 'organize' decision."""
        self._processed_count += 1
        self._processed_var.set(str(self._processed_count))

        line = (
            f"• {timestamp} — ✅ {filename}\n"
            f"  Type: {doc_type} | Category: {category} | "
            f"Confidence: {confidence:.0%}\n"
            f"  → {destination}/{new_filename}\n"
        )
        self._activity_lines.insert(0, line)

        self._refresh_dashboard_activity()
        self._log_raw(
            f"[{timestamp}] ORGANIZED: {filename} → {destination}/{new_filename} "
            f"(conf={confidence:.0%})\n"
        )

    def _on_review(self, timestamp: str, filename: str, reason: str):
        """Called on Tk thread when a file needs human review."""
        self._pending_count += 1
        self._pending_var.set(str(self._pending_count))

        activity_line = f"• {timestamp} — ⚠️  {filename} sent to Review Queue\n  Reason: {reason}\n"
        self._activity_lines.insert(0, activity_line)

        self._review_items.append((filename, reason))
        self._refresh_dashboard_activity()
        self._refresh_review_queue()
        self._log_raw(f"[{timestamp}] REVIEW: {filename} — {reason}\n")

    def _on_pipeline_error(self, timestamp: str, filename: str, error: str):
        """Called on Tk thread for unexpected pipeline exceptions."""
        self._log_raw(f"[{timestamp}] ERROR processing {filename}: {error}\n")

    # -------------------------------------------------------------------
    # Dashboard refresh helpers (Tk-thread only)
    # -------------------------------------------------------------------

    def _refresh_dashboard_activity(self):
        """Rewrite the Recent Activity textbox from self._activity_lines (newest first)."""
        self._dashboard_activity_box.configure(state="normal")
        self._dashboard_activity_box.delete("0.0", "end")
        # Show the 10 most recent entries
        for line in self._activity_lines[:10]:
            self._dashboard_activity_box.insert("end", line)
        self._dashboard_activity_box.configure(state="disabled")

    def _refresh_review_queue(self):
        """Rebuild the review queue scrollable frame from self._review_items."""
        # Destroy all existing child widgets
        for widget in self._review_scroll.winfo_children():
            widget.destroy()

        if not self._review_items:
            self._review_empty_label = ctk.CTkLabel(
                self._review_scroll,
                text="(Review queue is empty)",
                text_color="gray",
            )
            self._review_empty_label.grid(row=0, column=0, padx=10, pady=20)
            return

        for i, (fname, reason) in enumerate(self._review_items):
            item_frame = ctk.CTkFrame(self._review_scroll)
            item_frame.grid(row=i, column=0, padx=5, pady=5, sticky="ew")
            item_frame.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                item_frame, text=fname, font=ctk.CTkFont(weight="bold")
            ).grid(row=0, column=0, padx=10, pady=10)
            ctk.CTkLabel(
                item_frame, text=reason, text_color="orange"
            ).grid(row=0, column=1, padx=10, pady=10, sticky="w")
            ctk.CTkButton(item_frame, text="Review", width=80).grid(
                row=0, column=2, padx=10, pady=10
            )

    # -------------------------------------------------------------------
    # Raw activity log (full detail, append-only)
    # -------------------------------------------------------------------

    def _log_raw(self, msg: str):
        """Append a raw message to the Activity Log textbox. Tk-thread only."""
        self.activity_textbox.configure(state="normal")
        self.activity_textbox.insert("end", msg)
        self.activity_textbox.see("end")
        self.activity_textbox.configure(state="disabled")

    # ------------------------------------------------------------------
    # Legacy aliases kept for any external callers / tests
    # ------------------------------------------------------------------

    def log_activity(self, event: FileEvent):
        """Alias preserved for backward compatibility."""
        self._dispatch_event(event)

    def log_error(self, msg: str):
        """Alias preserved for backward compatibility."""
        self._log_raw(f"ERROR: {msg}\n")


if __name__ == "__main__":
    app = SortSenseApp()
    app.mainloop()
