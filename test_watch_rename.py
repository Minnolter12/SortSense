import time
import os
from pathlib import Path
from app.watcher import start_watcher
from app.events import FileEvent

def on_event(e: FileEvent):
    print(f"EVENT: {e}")

Path("/home/devmadhav/Downloads/src_rename.pdf").touch()
obs = start_watcher(on_event)
print("Watching...")
time.sleep(2)
os.rename("/home/devmadhav/Downloads/src_rename.pdf", "/home/devmadhav/Downloads/dest_rename.pdf")
print("Renamed to dest_rename.pdf")
time.sleep(2)
obs.stop()
obs.join()
