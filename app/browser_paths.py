"""
SortSense browser path discovery.

Dynamically locates the default download directories for the OS, Chrome, and Firefox.
Supports Windows and Linux.
"""

import os
import json
import platform
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def get_os_downloads() -> Path:
    """Get the standard OS Downloads folder."""
    home = Path.home()
    
    # Try XDG on Linux first
    if platform.system() == "Linux":
        user_dirs = home / ".config/user-dirs.dirs"
        if user_dirs.exists():
            try:
                for line in user_dirs.read_text(encoding="utf-8").splitlines():
                    if line.startswith("XDG_DOWNLOAD_DIR="):
                        val = line.split("=", 1)[1].strip('"')
                        val = val.replace("$HOME", str(home))
                        return Path(val).resolve()
            except Exception as e:
                logger.debug("Failed to read XDG_DOWNLOAD_DIR: %s", e)
                
    return home / "Downloads"

def get_browser_download_dirs() -> set[Path]:
    """
    Scans browser profiles on Windows and Linux to find custom download directories.
    Returns a set of all unique, existing download directories.
    """
    dirs = {get_os_downloads()}
    system = platform.system()
    home = Path.home()
    
    # 1. Chrome Profiles
    chrome_paths = []
    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            chrome_paths.append(Path(local_app_data) / "Google/Chrome/User Data")
    elif system == "Linux":
        chrome_paths.append(home / ".config/google-chrome")
        
    for base in chrome_paths:
        if base.exists():
            for prefs_file in base.glob("*/Preferences"):
                try:
                    with open(prefs_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        dl_dir = data.get("download", {}).get("default_directory")
                        if dl_dir:
                            dirs.add(Path(dl_dir).resolve())
                except Exception as e:
                    logger.debug("Could not parse Chrome prefs %s: %s", prefs_file, e)

    # 2. Firefox Profiles
    firefox_paths = []
    if system == "Windows":
        app_data = os.environ.get("APPDATA", "")
        if app_data:
            firefox_paths.append(Path(app_data) / "Mozilla/Firefox/Profiles")
    elif system == "Linux":
        firefox_paths.append(home / ".mozilla/firefox")
        
    for base in firefox_paths:
        if base.exists():
            for prefs_file in base.glob("*/prefs.js"):
                try:
                    with open(prefs_file, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            if "browser.download.dir" in line:
                                # Example: user_pref("browser.download.dir", "/custom/path");
                                parts = line.split('"')
                                if len(parts) >= 4:
                                    # Handle string escapes for paths
                                    dl_dir = parts[3].encode('utf-8').decode('unicode_escape')
                                    dirs.add(Path(dl_dir).resolve())
                except Exception as e:
                    logger.debug("Could not parse Firefox prefs %s: %s", prefs_file, e)
                    
    # Return only directories that actually exist
    return {d for d in dirs if d.exists() and d.is_dir()}
