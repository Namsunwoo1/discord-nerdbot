<<<<<<< HEAD
import subprocess
import sys
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import time

class RestartOnChangeHandler(FileSystemEventHandler):
    def __init__(self, script):
        self.script = script
        self.process = None
        self.restart()

    def restart(self):
        if self.process:
            self.process.kill()
            self.process.wait()
        print(f"Starting {self.script} ...")
        self.process = subprocess.Popen([sys.executable, self.script])

    def on_any_event(self, event):
        if event.src_path.endswith(".py"):
            print(f"Detected change in {event.src_path}, restarting...")
            self.restart()

if __name__ == "__main__":
    path = "."  # 현재 디렉터리 감시
    script = "main.py"  # 실행할 봇 스크립트 이름

    event_handler = RestartOnChangeHandler(script)
    observer = Observer()
    observer.schedule(event_handler, path=path, recursive=True)
    observer.start()
    print(f"Watching directory {path} for changes...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
=======
import subprocess
import sys
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import time

class RestartOnChangeHandler(FileSystemEventHandler):
    def __init__(self, script):
        self.script = script
        self.process = None
        self.restart()

    def restart(self):
        if self.process:
            self.process.kill()
            self.process.wait()
        print(f"Starting {self.script} ...")
        self.process = subprocess.Popen([sys.executable, self.script])

    def on_any_event(self, event):
        if event.src_path.endswith(".py"):
            print(f"Detected change in {event.src_path}, restarting...")
            self.restart()

if __name__ == "__main__":
    path = "."  # 현재 디렉터리 감시
    script = "main.py"  # 실행할 봇 스크립트 이름

    event_handler = RestartOnChangeHandler(script)
    observer = Observer()
    observer.schedule(event_handler, path=path, recursive=True)
    observer.start()
    print(f"Watching directory {path} for changes...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
>>>>>>> 950864be99e42392aff6563d3097bc194b660368
