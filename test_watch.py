import time
from pathlib import Path
from app.watcher import start_watcher
from app.events import FileEvent

def on_event(e: FileEvent):
    print(f"EVENT: {e}")

obs = start_watcher(on_event)
print("Watching...")
time.sleep(2)
Path("/home/devmadhav/Downloads/test_drop.pdf").touch()
print("Touched /home/devmadhav/Downloads/test_drop.pdf")
time.sleep(2)
obs.stop()
obs.join()
