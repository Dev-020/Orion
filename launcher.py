import sys
import os
import time
import subprocess
import shutil
import glob
import logging
from pathlib import Path
from datetime import datetime
import msvcrt # Windows specific
import atexit
import urllib.request
import urllib.error
import json

# Add backends to path to get config
sys.path.append(str(Path(__file__).resolve().parent / "backends"))
from main_utils import config
from main_utils.orion_logger import setup_logging

# RICH Imports
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich import box

# --- CONFIG ---
# Launcher has its own log too
LOG_DIR = config.DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR = LOG_DIR / "archive"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

# Standardized Logger for Launcher itself (e.g. process management errors)
# We disable console output for the launcher logger itself to avoid conflicting with TUI
LOGGER = setup_logging("Launcher", LOG_DIR / "launcher.log", level=logging.INFO, console_output=False)

PROCESSES = {
    "server": {
        "cmd": [sys.executable, "-u", "backends/server.py"],
        "log": LOG_DIR / "server.log",
        "name": "Orion Server"
    },
    "bot": {
        "cmd": [sys.executable, "-u", "frontends/bot.py"],
        "log": LOG_DIR / "bot.log",
        "name": "Discord Bot"
    },
    "gui": {
        "cmd": [sys.executable, "-u", "frontends/gui.py"], 
        "log": LOG_DIR / "gui.log",
        "name": "GUI (Tkinter)"
    }
}

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
            # Fallback if file is locked (shouldn't happen if processes are dead)
            LOGGER.error(f"Failed to archive {file_path}: {e}")

    @staticmethod
    def cleanup_all_logs():
        """Scans LOG_DIR and archives all known service logs."""
        for key, info in PROCESSES.items():
            log_path = info["log"]
            LogManager.archive_log(log_path, key)

class ProcessManager:
    def __init__(self):
        self.procs = {}
        self.start_times = {} # Track startup time for health heuristics
        # Initialize statuses for all known processes to prevent KeyError in UI
        self.statuses = {k: "STOPPED" for k in PROCESSES.keys()}
        # Ensure subprocesses use UTF-8 for IO to prevent 'charmap' errors on Windows
        self.env = os.environ.copy()
        self.env["PYTHONIOENCODING"] = "utf-8"
        
    def add_process(self, key, name, process, log_path):
        """Registers a process (already started or to be managed)."""
        self.procs[key] = process
        self.statuses[key] = "RUNNING"
        PROCESSES[key] = {"name": name, "log": log_path}

    def start_process(self, key):
        if key in self.procs:
            if self.procs[key].poll() is None: return # Already running
            
        # Re-construct command based on key
        cmd = [sys.executable, "-u"]
        if key == "server":
            cmd.append("backends/server.py")
            log_path = LOG_DIR / "server.log"
        elif key == "bot":
            cmd.append("frontends/bot.py")
            log_path = LOG_DIR / "bot.log"
        elif key == "gui":
            cmd.append("frontends/gui.py")
            log_path = LOG_DIR / "gui.log"
        else:
            return

        try:
            # STATUS: Transition
            self.statuses[key] = "STARTING..."
            self.start_times[key] = time.time() # Track start time for heuristics
            
            # SESSION LOGGING:
            err_path = LOG_DIR / f"{key}.err.log"
            f_err = open(err_path, "a", encoding="utf-8")
            
            p = subprocess.Popen(
                cmd, 
                stdout=subprocess.DEVNULL, 
                stderr=f_err,             
                cwd=str(Path(__file__).parent),
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                env=self.env
            )
            f_err.close() 

            self.procs[key] = p
            PROCESSES[key]["log"] = log_path
        except Exception as e:
            self.statuses[key] = f"ERROR: {e}"

    def stop_process(self, key, persist=False):
        if key in self.procs:
            p = self.procs[key]
            
            # 1. Graceful Shutdown Attempt
            self.statuses[key] = "STOPPING..."
            
            if key == "server" and p.poll() is None:
                try:
                    # Append persist flag to URL
                    url = f"http://127.0.0.1:8000/management/shutdown?persist={'true' if persist else 'false'}"
                    req = urllib.request.Request(url, method="POST")
                    with urllib.request.urlopen(req, timeout=2) as response: # Bump timeout slightly for DB save
                        pass
                except:
                    # If API is dead, we fallback to kill
                    pass

            # 2. Polling Wait
            start_wait = time.time()
            while p.poll() is None and (time.time() - start_wait) < 5:
                time.sleep(0.1)

            # 3. Force Kill Fallback
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    p.kill()
                    
            del self.procs[key]
            self.statuses[key] = "STOPPED"

    def start_all(self):
        self.start_process("server")
        time.sleep(1)
        self.start_process("bot")
        self.start_process("gui")

    def stop_all(self):
        for key in list(self.procs.keys()):
            self.stop_process(key)

    def check_health(self):
        for key, p in list(self.procs.items()):
            ret = p.poll()
            
            # DEAD PROCESS
            if ret is not None:
                if ret == 5:
                    self.statuses[key] = f"RESTARTING..."
                    del self.procs[key]
                    time.sleep(1)
                    self.start_process(key)
                else:
                    self.statuses[key] = f"EXITED ({ret})"
                    del self.procs[key] 
                continue

            # LIVE PROCESS - HEALTH CHECKS
            if key == "server":
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=0.5) as response:
                        if response.status == 200:
                            data = json.loads(response.read().decode())
                            # Map Backend status to UI status
                            # status: "initializing" | "healthy"
                            if data.get("status") == "healthy":
                                self.statuses[key] = "RUNNING [OK]"
                            else:
                                self.statuses[key] = "INITIALIZING..."
                except Exception:
                    # If we can't connect, but process is alive:
                    # 1. Maybe it's still starting up? (Give it 10s grace period)
                    if time.time() - self.start_times.get(key, 0) < 15:
                         self.statuses[key] = "STARTING..."
                    else:
                         self.statuses[key] = "UNRESPONSIVE" # Frozen detection!
            
            else:
                # Bot/GUI: Simple timeout heuristic
                if time.time() - self.start_times.get(key, 0) < 5:
                    self.statuses[key] = "STARTING..."
                else:
                    self.statuses[key] = "RUNNING" 

# --- LAUNCHER LOGGING ---
# Logs for the orchestrator itself (commands run, errors, etc)
LOG_DIR = Path(__file__).parent / "backends" / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / "launcher.log",
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- TUI GLOBALS ---
console = Console()
pm = ProcessManager()
atexit.register(pm.stop_all)

# Central State to avoid UnboundLocalError anomalies
APP_STATE = {
    "selected_log": "server",
    "scroll_offset": 0,
    "input_buffer": "",
    "history": [], # List of (cmd, feedback) tuples
    "last_feedback": "Type 'help' for commands."
}

def get_log_view_height():
    """Calculates available height for logs based on terminal size."""
    try:
        # Total height - Header(3) - Footer(3) - Panel Borders(2) = roughly -8
        # We allow a larger buffer AND a safety factor for wrapping (long lines take >1 row)
        available_height = max(10, console.size.height - 10)
        return int(available_height) # Maximized height
    except:
        return 20

import textwrap

def tail_logs(key, offset=0):
    """
    Reads logs and handles VISUAL wrapping to prevent TUI lag.
    """
    log_path = PROCESSES[key]["log"]
    if not log_path.exists():
        return [f"[grey]Waiting for logs...[/]"]
    
    try:
        # 1. Calculate width of the log panel (approx 3/4 screen - borders)
        # We need this to know how many visual lines 1 actual line takes.
        panel_width = int(console.size.width * 0.75) - 4
        if panel_width < 10: panel_width = 10 # Safety
        
        with open(log_path, "r", encoding='utf-8', errors='ignore') as f:
            # OPTIMIZATION: Read only last 4KB to approximate last ~50-100 lines
            # instead of reading whole file (which is slow for large logs).
            # But simple readlines is safer for now for correctness.
            lines = f.readlines()
            if not lines: return []
            
            # Read a healthy buffer (e.g., last 200 lines) to account for wrapping
            # If we only read 'view_height' file lines, wrapping might expand them to 
            # 2*view_height visual lines, pushing old stuff off screen, which is fine, 
            # but we want to maximize filling the screen.
            raw_lines = lines[-200:] 
            
            visual_lines = []
            for line in raw_lines:
                clean_line = line.rstrip()
                if not clean_line: continue
                
                # Dynamic Coloring based on Content (Since file is plain text)
                style_tag = ""
                if "ERROR" in clean_line: style_tag = "[red]"
                elif "WARNING" in clean_line: style_tag = "[yellow]"
                elif "INFO" in clean_line: style_tag = "[cyan]"
                elif "DEBUG" in clean_line: style_tag = "[grey50]"
                elif "CRITICAL" in clean_line: style_tag = "[bold red]"
                
                # Wrap based on panel width
                wrapped = textwrap.wrap(clean_line, width=panel_width)
                if not wrapped: # Handle empty/whitespace
                    visual_lines.append("\n")
                else:
                    # Append \n to each wrapped line AND apply style
                    for w in wrapped:
                        if style_tag:
                            visual_lines.append(f"{style_tag}{w}[/]\n")
                        else:
                            visual_lines.append(w + "\n")
            
            view_height = get_log_view_height()
            
            if offset == 0:
                return visual_lines[-view_height:]
            else:
                end_index = -offset
                start_index = -(view_height + offset)
                
                # Boundaries
                if abs(end_index) > len(visual_lines):
                    return [] # Scrolled past top
                    
                if abs(start_index) > len(visual_lines):
                    start_index = 0 # Cap at top
                    
                return visual_lines[start_index:end_index]

    except Exception as e:
        return [f"[red]Error reading log: {e}[/]"]

def generate_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3)
    )
    layout["body"].split_row(
        Layout(name="sidebar", ratio=1),
        Layout(name="main", ratio=3)
    )
    layout["sidebar"].split_column(
        Layout(name="status_pane", ratio=2),
        Layout(name="input_pane", ratio=1)
    )
    return layout

def render_header():
    return Panel(
        Align.center("[bold cyan]ORION COMMAND CENTER[/bold cyan] | [green]Phase 2: Client-Server[/green]"),
        box=box.ROUNDED, style="white on blue"
    )

def render_status():
    table = Table(box=box.SIMPLE, expand=True)
    table.add_column("Service", style="cyan")
    table.add_column("Status", style="magenta")
    
    for key, info in PROCESSES.items():
        status = pm.statuses[key]
        color = "green" if "RUNNING" in status else "red" if "EXITED" in status else "grey50"
        table.add_row(info["name"], f"[{color}]{status}[/{color}]")
    
    return Panel(table, title="System Status", border_style="blue")

def render_input_console():
    # Deprecated by render_control_panel but kept if layout uses it
    return render_control_panel()

def render_control_panel():
    # Show history
    history_lines = []
    if APP_STATE["history"]:
        for cmd, fb in APP_STATE["history"][-3:]: # Show last 3
            history_lines.append(f"[grey50]> {cmd}[/]")
            if fb:
                history_lines.append(f"[italic cyan]{fb}[/]")
            
    history_text = "\n".join(history_lines)
    
    # Current input
    content = f"{history_text}\n[bold white]> {APP_STATE['input_buffer']}[/]"
    if int(datetime.now().timestamp() * 2) % 2 == 0:
        content += " [blink]_[/]"
    
    return Panel(
        content,
        title="Command Input (Type 'help')",
        border_style="blue",
        height=10
    )

def render_main():
    # Fix NameError by ensuring we pull from APP_STATE
    key = APP_STATE.get("selected_log", "server")
    offset = APP_STATE.get("scroll_offset", 0)
    
    logs = tail_logs(key, offset)
    # Use from_markup to interpret the tags we added in tail_logs
    log_text = Text.from_markup("".join(logs)) 
    header_text = f"Live Logs: [bold yellow]{PROCESSES[key]['name']}[/bold yellow] (Path: {PROCESSES[key]['log']})"
    if offset > 0:
        header_text += f" [bold red](SCROLLING: {offset})[/bold red]"
        
    return Panel(
        log_text, 
        title=header_text,
        border_style="green"
    )

def render_footer():
    return Panel(
        "Commands: [bold]start/stop <service>[/] | [bold]quit[/] | [bold]logs <service>[/]",
        title="Help", border_style="white"
    )

def process_command(cmd: str):
    parts = cmd.lower().strip().split()
    if not parts: return
    action = parts[0]
    
    LOGGER.info(f"Command executed: {cmd}") 

    feedback = ""

    if action == "help":
        feedback = "Commands: start <all|server|bot|gui>, stop <...>, restart <...>, logs <server|bot|gui>, quit"
        
    elif action == "quit":
        pm.stop_all()
        sys.exit(0)
        
    elif action in ["start", "stop", "restart"]:
        if len(parts) < 2:
            feedback = f"Usage: {action} <service>"
        else:
            t = parts[1]
            if t == "all":
                if action == "start": 
                    pm.start_all()
                    feedback = "Started all services."
                elif action == "stop": 
                    pm.stop_all()
                    feedback = "Stopped all services."
                elif action == "restart": 
                    pm.stop_all()
                    # time.sleep done in start_all/restart logic if needed
                    pm.start_all() 
                    feedback = "Restarted all services."
            elif t in PROCESSES:
                if action == "start":
                    pm.start_process(t)
                    feedback = f"Started {t}..."
                elif action == "stop":
                    pm.stop_process(t)
                    feedback = f"Stopped {t}..."
                elif action == "restart":
                    # PASS PERSIST FLAG HERE
                    pm.stop_process(t, persist=True)
                    time.sleep(0.5)
                    pm.start_process(t)
                    feedback = f"Restarted {t} (Persistence Active)..."
            else:
                feedback = f"Unknown service: {t}"
                
                
    elif action == "logs":
        if len(parts) < 2:
            feedback = "Usage: logs <service>"
        else:
            target = parts[1]
            if target in PROCESSES:
                APP_STATE["selected_log"] = target
                APP_STATE["scroll_offset"] = 0
                feedback = f"Showing logs for {target}"
            else:
                feedback = f"Unknown log source: {target}"
            
    else:
        feedback = f"Unknown command: {action}"
        
    APP_STATE["last_feedback"] = feedback
    APP_STATE["history"].append((cmd, feedback))
    if len(APP_STATE["history"]) > 5:
        APP_STATE["history"].pop(0)


def main():
    # --- STARTUP CLEANUP ---
    # Archive any stale logs from previous runs before starting anything
    LogManager.cleanup_all_logs()
    # -----------------------

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--bot", action="store_true")
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args()

    if args.server or args.all:
        pm.start_process("server")
        time.sleep(1) 
    if args.bot or args.all:
        pm.start_process("bot")
    if args.gui or args.all:
        pm.start_process("gui")
    
    layout = generate_layout()
    
    with Live(layout, refresh_per_second=10, screen=True) as live:
        try:
            while True:
                layout["header"].update(render_header())
                layout["sidebar"]["status_pane"].update(render_status())
                layout["sidebar"]["input_pane"].update(render_control_panel())
                layout["main"].update(render_main())
                layout["footer"].update(render_footer())
                
                while msvcrt.kbhit():
                    char = msvcrt.getch()
                    
                    if char == b'\r': 
                        process_command(APP_STATE["input_buffer"])
                        APP_STATE["input_buffer"] = ""
                    elif char == b'\x08': 
                        APP_STATE["input_buffer"] = APP_STATE["input_buffer"][:-1]
                    elif char == b'\x03': 
                        raise KeyboardInterrupt
                    elif char == b'\xe0': 
                        # Arrow keys
                        key = msvcrt.getch()
                        if key == b'H': # Up
                            try:
                                key_log = APP_STATE["selected_log"]
                                lp = PROCESSES[key_log]["log"]
                                if lp.exists():
                                    with open(lp, "rb") as f:
                                        # Fast line count (byte scan might be faster but line count is safe)
                                        lines_count = sum(1 for _ in f)
                                        view_height = get_log_view_height()
                                        max_scroll = max(0, lines_count - view_height)
                                        if APP_STATE["scroll_offset"] < max_scroll:
                                            APP_STATE["scroll_offset"] += 1
                            except:
                                APP_STATE["scroll_offset"] += 1 # Fallback
                            
                        elif key == b'P': # Down
                            APP_STATE["scroll_offset"] = max(0, APP_STATE["scroll_offset"] - 1)
                    else:
                        try:
                            s = char.decode('utf-8')
                            if s.isprintable():
                                APP_STATE["input_buffer"] += s
                        except: pass

                pm.check_health()
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            pass
        finally:
            console.print("[bold red]Shutting down and archiving logs...[/bold red]")
            pm.stop_all()
            # --- SHUTDOWN cleanup ---
            # Wait a sec for file handles to release
            time.sleep(1) 
            LogManager.cleanup_all_logs()
            # ------------------------

if __name__ == "__main__":
    main()
