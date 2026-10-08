import tkinter as tk
import customtkinter as ctk
import time
import threading

from app.config import settings
from app.watcher import start_watcher
from app.events import FileEvent

# Configure appearance
ctk.set_appearance_mode("System")  # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"

class SortSenseApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SortSense — Gemma Local File Organizer")
        self.geometry("1000x700")

        # set grid layout 1x2
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # create sidebar frame with widgets
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(5, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="SortSense", font=ctk.CTkFont(size=24, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.dashboard_button = ctk.CTkButton(self.sidebar_frame, text="Dashboard", command=self.show_dashboard)
        self.dashboard_button.grid(row=1, column=0, padx=20, pady=10)

        self.watched_button = ctk.CTkButton(self.sidebar_frame, text="Activity Log", command=self.show_watched)
        self.watched_button.grid(row=2, column=0, padx=20, pady=10)

        self.review_button = ctk.CTkButton(self.sidebar_frame, text="Review Queue", command=self.show_review)
        self.review_button.grid(row=3, column=0, padx=20, pady=10)

        self.settings_button = ctk.CTkButton(self.sidebar_frame, text="Settings", command=self.show_settings)
        self.settings_button.grid(row=4, column=0, padx=20, pady=10)

        self.appearance_mode_label = ctk.CTkLabel(self.sidebar_frame, text="Appearance Mode:", anchor="w")
        self.appearance_mode_label.grid(row=6, column=0, padx=20, pady=(10, 0))
        self.appearance_mode_optionemenu = ctk.CTkOptionMenu(self.sidebar_frame, values=["System", "Light", "Dark"],
                                                                       command=self.change_appearance_mode_event)
        self.appearance_mode_optionemenu.grid(row=7, column=0, padx=20, pady=(10, 20))

        # Initial state variables
        self.model_status_var = ctk.StringVar(value="Checking...")

        # create main frames
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

    def create_dashboard_frame(self):
        frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        
        title = ctk.CTkLabel(frame, text="Dashboard Overview", font=ctk.CTkFont(size=24, weight="bold"))
        title.grid(row=0, column=0, padx=20, pady=20, sticky="w")

        # Status Cards Frame
        cards_frame = ctk.CTkFrame(frame, fg_color="transparent")
        cards_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        cards_frame.grid_columnconfigure((0, 1, 2), weight=1)

        # Model Status Card
        model_card = ctk.CTkFrame(cards_frame)
        model_card.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(model_card, text="Model Status", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)
        self.model_status_label = ctk.CTkLabel(model_card, textvariable=self.model_status_var, font=ctk.CTkFont(size=14))
        self.model_status_label.pack(pady=10)

        # Files Processed Card
        processed_card = ctk.CTkFrame(cards_frame)
        processed_card.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(processed_card, text="Files Processed", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)
        ctk.CTkLabel(processed_card, text="142", font=ctk.CTkFont(size=24)).pack(pady=10)

        # Pending Review Card
        review_card = ctk.CTkFrame(cards_frame)
        review_card.grid(row=0, column=2, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(review_card, text="Pending Review", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)
        ctk.CTkLabel(review_card, text="3", font=ctk.CTkFont(size=24)).pack(pady=10)

        # Recent Activity Placeholder
        ctk.CTkLabel(frame, text="Recent Activity", font=ctk.CTkFont(size=18, weight="bold")).grid(row=2, column=0, padx=20, pady=(20, 10), sticky="w")
        activity_box = ctk.CTkTextbox(frame, height=200)
        activity_box.grid(row=3, column=0, padx=20, pady=10, sticky="nsew")
        activity_box.insert("0.0", "• 10:45 AM - Processed 'IMG-WA0012.pdf' -> Utilities/Electricity_Bill.pdf\n"
                                   "• 10:30 AM - Processed 'document.pdf' -> Documents/Syllabus.pdf\n"
                                   "• 09:15 AM - Sent 'unknown.txt' to Review Queue\n")
        activity_box.configure(state="disabled")

        return frame

    def create_watched_frame(self):
        frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        
        title = ctk.CTkLabel(frame, text="Activity Log / Watched Files", font=ctk.CTkFont(size=24, weight="bold"))
        title.grid(row=0, column=0, padx=20, pady=20, sticky="w")

        self.activity_textbox = ctk.CTkTextbox(frame)
        self.activity_textbox.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        watched_paths = "\n".join(f" - {d}" for d in settings.watched_dirs)
        self.activity_textbox.insert("0.0", f"Watching directories:\n{watched_paths}\n\n")
        self.activity_textbox.configure(state="disabled")

        return frame

    def create_review_frame(self):
        frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        
        title = ctk.CTkLabel(frame, text="Review Queue", font=ctk.CTkFont(size=24, weight="bold"))
        title.grid(row=0, column=0, padx=20, pady=20, sticky="w")

        desc = ctk.CTkLabel(frame, text="These files had low confidence or missing categories and require manual sorting.", text_color="gray")
        desc.grid(row=1, column=0, padx=20, pady=0, sticky="w")

        # Mock items
        items = [
            ("scan_001.pdf", "Low Confidence (0.4)"),
            ("notes.txt", "No Category Found"),
            ("receipt_unclear.jpg", "OCR Failed")
        ]

        for i, (fname, reason) in enumerate(items):
            item_frame = ctk.CTkFrame(frame)
            item_frame.grid(row=i+2, column=0, padx=20, pady=10, sticky="ew")
            item_frame.grid_columnconfigure(1, weight=1)
            
            ctk.CTkLabel(item_frame, text=fname, font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=10, pady=10)
            ctk.CTkLabel(item_frame, text=reason, text_color="orange").grid(row=0, column=1, padx=10, pady=10, sticky="w")
            ctk.CTkButton(item_frame, text="Review", width=80).grid(row=0, column=2, padx=10, pady=10)

        return frame

    def create_settings_frame(self):
        frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        
        title = ctk.CTkLabel(frame, text="Settings", font=ctk.CTkFont(size=24, weight="bold"))
        title.grid(row=0, column=0, padx=20, pady=20, sticky="w")

        # Watched Directory Setting
        dir_frame = ctk.CTkFrame(frame)
        dir_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        dir_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(dir_frame, text="Watched Directory:").grid(row=0, column=0, padx=10, pady=10)
        dir_entry = ctk.CTkEntry(dir_frame)
        dir_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        dir_entry.insert(0, ", ".join(str(d) for d in settings.watched_dirs))
        ctk.CTkButton(dir_frame, text="Browse", width=80).grid(row=0, column=2, padx=10, pady=10)

        # Ollama Model Setting
        model_frame = ctk.CTkFrame(frame)
        model_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        model_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(model_frame, text="Gemma Model:").grid(row=0, column=0, padx=10, pady=10)
        model_entry = ctk.CTkEntry(model_frame)
        model_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        model_entry.insert(0, settings.gemma_model)

        # Ollama Host Setting
        host_frame = ctk.CTkFrame(frame)
        host_frame.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        host_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(host_frame, text="Ollama Host:").grid(row=0, column=0, padx=10, pady=10)
        host_entry = ctk.CTkEntry(host_frame)
        host_entry.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        host_entry.insert(0, settings.ollama_host)

        # Save Button
        ctk.CTkButton(frame, text="Save Settings").grid(row=4, column=0, padx=20, pady=20, sticky="e")

        return frame

    def hide_all_frames(self):
        for frame in self.frames.values():
            frame.grid_forget()

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

    def check_model_status_thread(self):
        def check_status():
            try:
                import ollama
                client = ollama.Client(host=settings.ollama_host)
                client.list()
                self.model_status_var.set("🟢 Active (Ollama Running)")
                self.model_status_label.configure(text_color="green")
            except Exception as e:
                self.model_status_var.set("🔴 Offline (Cannot reach Ollama)")
                self.model_status_label.configure(text_color="red")
            
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
