# ... imports
import sys
import os
import subprocess
import time
import shutil
import logging
import psutil
from pathlib import Path
from datetime import datetime

# Import Orion Config safely
try:
    sys.path.append(str(Path(__file__).resolve().parent.parent / "backends"))
    from main_utils import config
except ImportError:
    config = None # Fallback

# Services Configuration
PROCESSES = {
    "server": {
        "cmd": [sys.executable, "-u", "backends/server.py"],
        "name": "Orion Server"
    },
    "bot": {
        "cmd": [sys.executable, "-u", "frontends/bot.py"],
        "name": "Discord Bot"
    },
    "web": {
        "cmd": [sys.executable, "-u", "frontends/web_server.py"],
        "name": "Web Frontend"
    },
    "gui": {
        "cmd": [sys.executable, "-u", "frontends/gui.py"], 
        "name": "GUI (Tkinter)"
    },
    "ngrok": {
        "cmd": ["ngrok", "http", "--domain=soila-noninstructional-sallie.ngrok-free.dev", "8000", "--log", "stdout"],
        "name": "Ngrok Tunnel",
        "capture_stdout": True
    }
}

# LOGGING SETUP
LOG_DIR = Path(__file__).parent.parent / "backends" / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR = LOG_DIR / "archive"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

class LogManager:
    @staticmethod
    def archive_log(file_path: Path, service_name: str):
        """Moves a log file to the archive directory with a timestamp."""
        if not file_path.exists():
            return

        # Create service-specific archive folder
        service_archive = ARCHIVE_DIR / service_name
        service_archive.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        # Name format: timestamp_service.log
        new_name = f"{timestamp}_{file_path.name}"
        destination = service_archive / new_name

        try:
            shutil.move(str(file_path), str(destination))
        except Exception as e:
            # Fallback if file is locked
            print(f"Failed to archive {file_path}: {e}")

    @staticmethod
    def cleanup_all_logs():
        """Scans LOG_DIR and archives all known service logs."""
        for key in PROCESSES.keys():
            log_path = LOG_DIR / f"{key}.log"
            LogManager.archive_log(log_path, key)
            
            # Archive error logs too if they exist
            err_path = LOG_DIR / f"{key}.err.log"
            if err_path.exists():
                LogManager.archive_log(err_path, key + "_err")

class ProcessManager:
    def __init__(self):
        self.procs = {} # key -> Popen
        self.statuses = {k: "STOPPED" for k in PROCESSES.keys()}
        self.stats = {k: {"cpu": 0.0, "mem": 0.0, "pid": None} for k in PROCESSES.keys()}
        
        # Enforce UTF-8
        self.env = os.environ.copy()
        self.env["PYTHONIOENCODING"] = "utf-8"
        self.env["ORION_MANAGED_PROCESS"] = "true"
        
        # Logging
        self.log_dir = Path(__file__).parent.parent / "backends" / "data" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def start_process(self, key):
        if key in self.procs and self.procs[key].poll() is None:
            return # Already running

        if key not in PROCESSES: return

        info = PROCESSES[key]
        cmd = info["cmd"]
        
        try:
            self.statuses[key] = "STARTING..."
            
            # Logs
            log_path = self.log_dir / f"{key}.log"
            err_path = self.log_dir / f"{key}.err.log"
            
            # Open Files
            # We append because we want history, but maybe we should rotate?
            # For now, append is standard.
            f_out = open(log_path, "a", encoding="utf-8")
            f_err = open(err_path, "a", encoding="utf-8")
            
            kwargs = {
                "stdout": f_out,
                "stderr": f_err,
                "cwd": str(Path(__file__).parent.parent), # Context Root
                "text": True,
                "env": self.env
            }
            
            if os.name == 'nt':
                 kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            else:
                 kwargs["start_new_session"] = True

            p = subprocess.Popen(cmd, **kwargs)
            self.procs[key] = p
            
            # Close parent handles
            # f_out.close() # Actually we can't close immediately if we want to read? 
            # Subprocess has its own handle. It is safe to close here? Yes.
            # But wait, we passed the file object. Popen dups it.
            # So we SHOULD close it in parent to avoid leaks.
            f_out.close()
            f_err.close()

            self.statuses[key] = "RUNNING"
            self.stats[key]["pid"] = p.pid

        except Exception as e:
            self.statuses[key] = f"ERROR: {e}"

    def stop_process(self, key):
        if key in self.procs:
            p = self.procs[key]
            self.statuses[key] = "STOPPING..."
            
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill()
            
            del self.procs[key]
            self.statuses[key] = "STOPPED"
            self.stats[key] = {"cpu": 0.0, "mem": 0.0, "pid": None}

    def start_all(self):
        # Order matters
        self.start_process("server")
        time.sleep(1)
        self.start_process("bot")
        self.start_process("web")
        # ngrok/gui optional? Let's start ngrok by default if requested?
        # Standard behavior: Start core trilogy.

    def stop_all(self):
        for k in list(self.procs.keys()):
            self.stop_process(k)

    def update_resource_stats(self):
        """Called periodically to update CPU/RAM stats via psutil."""
        for key, p in list(self.procs.items()):
            if p.poll() is not None:
                # Process died
                self.statuses[key] = "EXITED"
                self.stop_process(key) # Cleanup 
                continue

            try:
                # Get psutil process
                proc = psutil.Process(p.pid)
                
                # Handling Ngrok (Binary wrapper) or Shell scripts
                # For basic Popen, p.pid is usually correct.
                
                # CPU Percent (interval=None is non-blocking)
                cpu = proc.cpu_percent(interval=None)
                # Normalize? psutil returns >100% for multi-core. 
                # We'll just display it as is.
                
                mem = proc.memory_info().rss / (1024 * 1024) # MB
                
                self.stats[key]["cpu"] = cpu
                self.stats[key]["mem"] = round(mem, 1)
                self.statuses[key] = "RUNNING"
                
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.statuses[key] = "ZOMBIE/DIED"
                
