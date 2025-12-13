# --- IMPORTS ---
import sys
import os
import time
import subprocess
import shutil
import glob
from pathlib import Path
from datetime import datetime
import msvcrt # Windows specific

# Add backends to path to get config
sys.path.append(str(Path(__file__).resolve().parent / "backends"))
from main_utils import config

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
LOG_DIR = config.DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR = LOG_DIR / "archive"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

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
            print(f"Failed to archive {file_path}: {e}")

    @staticmethod
    def cleanup_all_logs():
        """Scans LOG_DIR and archives all known service logs."""
        for key, info in PROCESSES.items():
            log_path = info["log"]
            LogManager.archive_log(log_path, key)

class ProcessManager:
    def __init__(self):
        self.procs = {} 
        self.statuses = {k: "STOPPED" for k in PROCESSES.keys()}
        
    def start_process(self, key):
        if key in self.procs and self.procs[key].poll() is None:
            return 
            
        p_info = PROCESSES[key]
        log_path = p_info["log"]
        
        # Ensure clean state for this run if somehow file exists (e.g. created manually)
        # But global cleanup usually handles this.
        
        log_file = open(log_path, "a", encoding='utf-8') 
        
        try:
            self.procs[key] = subprocess.Popen(
                p_info["cmd"],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=str(Path(__file__).parent),
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            self.statuses[key] = "RUNNING"
        except Exception as e:
            self.statuses[key] = f"ERROR: {e}"

    def stop_process(self, key):
        if key in self.procs:
            p = self.procs[key]
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
            del self.procs[key]
            self.statuses[key] = "STOPPED"

    def stop_all(self):
        for key in list(self.procs.keys()):
            self.stop_process(key)

    def check_health(self):
        for key, p in list(self.procs.items()):
            if p.poll() is not None:
                self.statuses[key] = f"EXITED ({p.returncode})"
                del self.procs[key] 

# --- TUI ---
console = Console()
pm = ProcessManager()
command_buffer = ""
last_command_feedback = "Type 'help' for commands."
selected_log = "server" 

def tail_logs(key):
    """Reads the last N lines of the selected log file."""
    log_path = PROCESSES[key]["log"]
    if not log_path.exists():
        return [f"[grey]Waiting for logs...[/]"]
    
    try:
        with open(log_path, "r", encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            return lines[-20:] 
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
    return Panel(
        f"> {command_buffer}[blink]_[/blink]\n\n[grey]{last_command_feedback}[/]",
        title="Console Input", border_style="yellow"
    )

def render_main():
    logs = tail_logs(selected_log)
    log_text = Text.from_ansi("".join(logs)) 
    return Panel(
        log_text, 
        title=f"Live Logs: [bold yellow]{PROCESSES[selected_log]['name']}[/bold yellow] (Path: {PROCESSES[selected_log]['log']})",
        border_style="green"
    )

def render_footer():
    return Panel(
        "Commands: [bold]start/stop <service>[/] | [bold]quit[/] | [bold]logs <service>[/]",
        title="Help", border_style="white"
    )

def process_command(cmd: str):
    global last_command_feedback, selected_log
    parts = cmd.lower().strip().split()
    if not parts: return

    action = parts[0]
    
    if action == "quit" or action == "exit":
        raise KeyboardInterrupt
        
    elif action == "help":
        last_command_feedback = "Available: start/stop [server|bot|gui], logs [server|bot|gui], quit"

    elif action in ["start", "stop", "restart"]:
        if len(parts) < 2:
            last_command_feedback = f"Usage: {action} <service>"
            return
        target = parts[1]
        
        # Mapping aliases
        if target in ["all", "everything"]:
            targets = ["server", "bot"]
        elif target in PROCESSES:
            targets = [target]
        else:
            last_command_feedback = f"Unknown service: {target}"
            return
            
        for t in targets:
            if action == "start":
                pm.start_process(t)
                last_command_feedback = f"Started {t}..."
            elif action == "stop":
                pm.stop_process(t)
                last_command_feedback = f"Stopped {t}..."
            elif action == "restart":
                pm.stop_process(t)
                time.sleep(0.5)
                pm.start_process(t)
                last_command_feedback = f"Restarted {t}..."
                
    elif action == "logs":
        if len(parts) < 2:
            last_command_feedback = "Usage: logs <service>"
            return
        target = parts[1]
        if target in PROCESSES:
            selected_log = target
            last_command_feedback = f"Showing logs for {target}"
        else:
            last_command_feedback = f"Unknown log source: {target}"
            
    else:
        last_command_feedback = f"Unknown command: {action}"


def main():
    global command_buffer
    
    # --- STARTUP CLEANUP ---
    # Archive any stale logs from previous runs before starting anything
    LogManager.cleanup_all_logs()
    # -----------------------

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--bot", action="store_true")
    args = parser.parse_args()

    if args.server or args.all:
        pm.start_process("server")
        time.sleep(1) 
    if args.bot or args.all:
        pm.start_process("bot")
    
    layout = generate_layout()
    
    with Live(layout, refresh_per_second=10, screen=True) as live:
        try:
            while True:
                while msvcrt.kbhit():
                    char = msvcrt.getch()
                    
                    if char == b'\r': 
                        process_command(command_buffer)
                        command_buffer = ""
                    elif char == b'\x08': 
                        command_buffer = command_buffer[:-1]
                    elif char == b'\x03': 
                        raise KeyboardInterrupt
                    elif char == b'\xe0': 
                        msvcrt.getch()
                    else:
                        try:
                            s = char.decode('utf-8')
                            if s.isprintable():
                                command_buffer += s
                        except: pass

                pm.check_health()
                
                layout["header"].update(render_header())
                layout["sidebar"]["status_pane"].update(render_status()) 
                layout["sidebar"]["input_pane"].update(render_input_console())
                layout["main"].update(render_main())
                layout["footer"].update(render_footer())
                
                time.sleep(0.05) 
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
