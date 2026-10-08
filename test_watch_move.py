import time
import shutil
from pathlib import Path
from app.watcher import start_watcher
from app.events import FileEvent

def on_event(e: FileEvent):
    print(f"EVENT: {e}")

Path("/home/devmadhav/Documents/src_drop.pdf").touch()
obs = start_watcher(on_event)
print("Watching...")
time.sleep(2)
shutil.move("/home/devmadhav/Documents/src_drop.pdf", "/home/devmadhav/Downloads/test_moved.pdf")
print("Moved to /home/devmadhav/Downloads/test_moved.pdf")
time.sleep(2)
obs.stop()
obs.join()
