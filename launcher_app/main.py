
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widgets import Header, Footer, Static, Button, Label, DataTable, RichLog, Input, TabbedContent, TabPane, Switch
from textual import on, work
from textual.reactive import reactive

import asyncio
import time
from datetime import datetime
from pathlib import Path

# Import Internal Logic
try:
    from .process_manager import ProcessManager, PROCESSES, LogManager
    from .monitors.amd_gpu import RadeontopMonitor
    from .config_parser import ConfigParser
except ImportError:
    # Fallback for direct execution testing
    from process_manager import ProcessManager, PROCESSES, LogManager
    from monitors.amd_gpu import RadeontopMonitor
    from config_parser import ConfigParser

# Path to config file
CONFIG_PATH = Path(__file__).parent.parent / "backends" / "main_utils" / "config.py"

class ConfigForm(ScrollableContainer):
    """Form to edit config.py variables."""
    
    def compose(self) -> ComposeResult:
        self.parser = ConfigParser(CONFIG_PATH)
        data = self.parser.load_config()
        self.initial_data = data # Store for diff checking if needed

        yield Label("Core Configuration", classes="section_header")
        
        # String Fields
        yield Label("AI Model (Cloud):")
        yield Input(value=data.get("AI_MODEL", ""), id="inp_AI_MODEL", classes="config_input")
        
        yield Label("Local Model (Ollama):")
        yield Input(value=data.get("LOCAL_MODEL", ""), id="inp_LOCAL_MODEL", classes="config_input")

        yield Label("Backend (api/ollama):")
        yield Input(value=data.get("BACKEND", ""), id="inp_BACKEND", classes="config_input")
        
        yield Label("Persona:")
        yield Input(value=data.get("PERSONA", ""), id="inp_PERSONA", classes="config_input")

        yield Label("Feature Flags", classes="section_header")

        # Switches
        with Horizontal(classes="switch_row"):
            yield Label("Voice Support (TTS):", classes="switch_label")
            yield Switch(value=data.get("VOICE", False), id="sw_VOICE")
            
        with Horizontal(classes="switch_row"):
            yield Label("Thinking Support:", classes="switch_label")
            yield Switch(value=data.get("THINKING_SUPPORT", False), id="sw_THINKING_SUPPORT")
            
        with Horizontal(classes="switch_row"):
            yield Label("Function Calling:", classes="switch_label")
            yield Switch(value=data.get("FUNCTION_CALLING_SUPPORT", False), id="sw_FUNCTION_CALLING_SUPPORT")
            
        with Horizontal(classes="switch_row"):
            yield Label("Ollama Cloud:", classes="switch_label")
            yield Switch(value=data.get("OLLAMA_CLOUD", False), id="sw_OLLAMA_CLOUD")

        with Horizontal(classes="switch_row"):
            yield Label("Vision Support:", classes="switch_label")
            yield Switch(value=data.get("VISION", False), id="sw_VISION")

        with Horizontal(classes="switch_row"):
            yield Label("Vertex AI:", classes="switch_label")
            yield Switch(value=data.get("VERTEX", False), id="sw_VERTEX")

        with Horizontal(classes="switch_row"):
            yield Label("Past Context Memory:", classes="switch_label")
            yield Switch(value=data.get("PAST_MEMORY", False), id="sw_PAST_MEMORY")

        with Horizontal(classes="switch_row"):
            yield Label("Context Caching:", classes="switch_label")
            yield Switch(value=data.get("CONTEXT_CACHING", False), id="sw_CONTEXT_CACHING")

        yield Static(id="spacer_config", classes="spacer")
        yield Button("Save & Restart Server", variant="primary", id="btn_save_config")
        yield Label("", id="lbl_save_status", classes="status_msg")

    def check_changes(self):
        """Compares current values with initial_data and updates UI styles."""
        try:
            # Check Inputs
            for key in ["AI_MODEL", "LOCAL_MODEL", "BACKEND", "PERSONA"]:
                widget = self.query_one(f"#inp_{key}")
                original = self.initial_data.get(key, "")
                if widget.value != original:
                    widget.add_class("modified")
                else:
                    widget.remove_class("modified")

            # Check Switches
            for key in ["VOICE", "THINKING_SUPPORT", "FUNCTION_CALLING_SUPPORT", "OLLAMA_CLOUD", 
                        "VISION", "VERTEX", "PAST_MEMORY", "CONTEXT_CACHING"]:
                widget = self.query_one(f"#sw_{key}")
                original = self.initial_data.get(key, False)
                if widget.value != original:
                    widget.add_class("modified")
                else:
                    widget.remove_class("modified")
        except Exception:
            pass

    @on(Input.Changed)
    def on_input_changed(self):
        self.check_changes()

    @on(Switch.Changed)
    def on_switch_changed(self):
        self.check_changes()

    @on(Button.Pressed, "#btn_save_config")
    def save_and_restart(self):
        status_lbl = self.query_one("#lbl_save_status")
        status_lbl.update("[yellow]Saving...[/]")
        
        # Gather Data
        new_data = {}
        new_data["AI_MODEL"] = self.query_one("#inp_AI_MODEL").value
        new_data["LOCAL_MODEL"] = self.query_one("#inp_LOCAL_MODEL").value
        new_data["BACKEND"] = self.query_one("#inp_BACKEND").value
        new_data["PERSONA"] = self.query_one("#inp_PERSONA").value
        
        new_data["VOICE"] = self.query_one("#sw_VOICE").value
        new_data["THINKING_SUPPORT"] = self.query_one("#sw_THINKING_SUPPORT").value
        new_data["FUNCTION_CALLING_SUPPORT"] = self.query_one("#sw_FUNCTION_CALLING_SUPPORT").value
        new_data["OLLAMA_CLOUD"] = self.query_one("#sw_OLLAMA_CLOUD").value
        
        new_data["VISION"] = self.query_one("#sw_VISION").value
        new_data["VERTEX"] = self.query_one("#sw_VERTEX").value
        new_data["PAST_MEMORY"] = self.query_one("#sw_PAST_MEMORY").value
        new_data["CONTEXT_CACHING"] = self.query_one("#sw_CONTEXT_CACHING").value

        if self.parser.save_config(new_data):
            # Update initial data to match saved data so highlighting clears
            self.initial_data = new_data
            self.check_changes()
            
            status_lbl.update("[green]Saved! Restarting Server...[/]")
            self.app.trigger_server_restart()
        else:
            status_lbl.update("[red]Error saving config file![/]")

from textual.widgets import Header, Footer, Static, Button, Label, DataTable, RichLog, Input, TabbedContent, TabPane, Switch, ProgressBar

# ... (Previous imports remain, ensuring ProgressBar is added)

class ResourceMonitor(Static):
    """A widget to display a resource label and a progress bar."""
    
    def compose(self) -> ComposeResult:
        yield Label("", id="lbl_stat")
        yield ProgressBar(total=100, show_eta=False, show_percentage=False)

    def update_resource(self, label_text: str, percentage: float):
        self.query_one("#lbl_stat").update(label_text)
        bar = self.query_one(ProgressBar)
        bar.progress = percentage

class GlobalStats(Static):
    """Widget to display global resource stats (CPU/RAM/GPU)."""

    def compose(self) -> ComposeResult:
        yield ResourceMonitor(id="gpu_mon")
        yield ResourceMonitor(id="vram_mon")

    def update_stats(self, gpu_stats):
        gpu_util = gpu_stats.get('gpu_util', 0.0)
        vram_util = gpu_stats.get('vram_util', 0.0)
        vram_used = gpu_stats.get('vram_used_mb', 0.0)

        # Update GPU
        self.query_one("#gpu_mon").update_resource(
            f"[bold cyan]GPU:[/bold cyan] {gpu_util:.1f}%", 
            gpu_util
        )
        
        # Update VRAM
        self.query_one("#vram_mon").update_resource(
            f"[bold cyan]VRAM:[/bold cyan] {vram_used:.0f}MB ({vram_util:.1f}%)", 
            vram_util
        )

class OrionLauncherApp(App):
    CSS_PATH = "styles.tcss"
    TITLE = "Orion Dashboard"
    SUB_TITLE = "https://dev-020.github.io/Orion/"

    def __init__(self):
        super().__init__()
        self.pm = ProcessManager()
        self.gpu_monitor = RadeontopMonitor()
        self.selected_log_service = "server" # Default
        self.log_seek_offsets = {} # Key -> int byte position

    def compose(self) -> ComposeResult:
        # ... (Unchanged)
        yield Header(show_clock=True)
        
        with Container(id="main_layout"):
            # LEFT SIDEBAR: Process List & CLI
            with Vertical(id="sidebar"):
                yield Label("System Services", classes="section_title")
                yield DataTable(id="process_table")
                
                yield Static(id="spacer", classes="spacer")
                
                yield Label("Command Input", classes="section_title")
                yield Input(placeholder="Type command (e.g. start server)...", id="cmd_input")
                yield Static(id="cmd_feedback", classes="feedback_text")

            # RIGHT MAIN: Tabs (Logs, Stats)
            with Vertical(id="content_area"):
                with Horizontal(id="stats_bar"):
                    yield GlobalStats(id="global_stats")

                with TabbedContent():
                    with TabPane("Live Logs", id="tab_logs"):
                         # Log Selector Buttons
                        with Horizontal(id="log_controls"):
                             for key in PROCESSES.keys():
                                 yield Button(key.upper(), id=f"btn_log_{key}", classes="log_selector")
                        
                        yield RichLog(id="log_view", wrap=True, highlight=True, markup=True, max_lines=1000)
                    
                    with TabPane("Configuration", id="tab_config"):
                        yield ConfigForm()


        yield Footer()

    def trigger_server_restart(self):
        """Called by ConfigForm to restart the server process."""
        self.pm.stop_process("server")
        time.sleep(1)
        self.pm.start_process("server")

    def on_mount(self) -> None:
        # Archive old logs from previous session
        LogManager.cleanup_all_logs()
        
        self.gpu_monitor.start_monitoring()
        
        # Setup Table
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_column("Service", key="Service")
        table.add_column("Status", key="Status")
        table.add_column("CPU%", key="CPU%")
        table.add_column("MEM (MB)", key="MEM (MB)")
        table.add_column("PID", key="PID")
        
        # Initial Population
        for key, info in PROCESSES.items():
            table.add_row(info["name"], "STOPPED", "0.0", "0.0", "---", key=key)

        # Start Update Loops
        self.set_interval(1.0, self.update_system_stats)
        self.set_interval(0.5, self.update_logs)

    # ... (Methods update_system_stats, update_logs, handle_log_switch, reload_log_view, handle_cli_command unchanged)

    def update_system_stats(self):
        # 1. Update PM
        self.pm.update_resource_stats()
        
        # 2. Update Table
        table = self.query_one(DataTable)
        for key in PROCESSES.keys():
            status = self.pm.statuses.get(key, "UNKNOWN")
            stats = self.pm.stats.get(key, {})
            
            # Styling Status
            status_styled = status
            if "RUNNING" in status: status_styled = f"[green]{status}[/green]"
            elif "STOPPED" in status: status_styled = f"[red]{status}[/red]"
            elif "STARTING" in status: status_styled = f"[yellow]{status}[/yellow]"
            
            table.update_cell(key, "Status", status_styled)
            table.update_cell(key, "CPU%", f"{stats.get('cpu', 0.0):.1f}")
            table.update_cell(key, "MEM (MB)", f"{stats.get('mem', 0.0):.1f}")
            table.update_cell(key, "PID", str(stats.get('pid', '---')))

        # 3. Global Stats (GPU)
        gpu_data = self.gpu_monitor.get_stats()
        self.query_one("#global_stats").update_stats(gpu_data)

    def update_logs(self):
        key = self.selected_log_service
        log_view = self.query_one("#log_view")
        log_path = self.pm.log_dir / f"{key}.log"
        
        if not log_path.exists():
            return

        current_offset = self.log_seek_offsets.get(key, 0)
        
        try:
            # Check file size to detect rotation or truncation
            file_size = log_path.stat().st_size
            if file_size < current_offset:
                # File was truncated or rotated
                current_offset = 0
                log_view.write(f"\n[italic grey]--- Log Rotated ---[/]\n")

            if file_size == current_offset:
                return # Nothing new

            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(current_offset)
                new_content = f.read()
                if new_content:
                    log_view.write(new_content)
                    self.log_seek_offsets[key] = f.tell()
        except Exception:
            pass

    @on(Button.Pressed)
    def handle_log_switch(self, event: Button.Pressed):
        if event.button.id.startswith("btn_log_"):
            service_key = event.button.id.replace("btn_log_", "")
            self.selected_log_service = service_key
            self.reload_log_view()

    def reload_log_view(self):
        log_view = self.query_one("#log_view")
        log_view.clear()
        
        key = self.selected_log_service
        log_path = self.pm.log_dir / f"{key}.log"
        
        # Reset offset for this key so update_logs doesn't get confused
        self.log_seek_offsets[key] = 0
        
        if log_path.exists():
            try:
                # Get total size
                file_size = log_path.stat().st_size
                
                # We want last 2000 chars approx (or last 50 lines)
                # Let's simple read last 4KB
                read_size = 4096
                start_pos = max(0, file_size - read_size)
                
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(start_pos)
                    content = f.read()
                    log_view.write(content)
                    
                    # Update global offset to end of file
                    self.log_seek_offsets[key] = f.tell()
            except Exception:
                pass
        else:
            log_view.write(f"[italic grey]No logs found for {key}[/]")

    @on(Input.Submitted)
    def handle_cli_command(self, event: Input.Submitted):
        cmd = event.value.strip().lower()
        event.input.value = "" # Clear input
        
        feedback = self.query_one("#cmd_feedback")
        
        parts = cmd.split()
        if not parts: return
        
        action = parts[0]
        
        if action == "start":
            if len(parts) < 2: 
                feedback.update("[red]Usage: start <service|all>[/]")
                return
            target = parts[1]
            if target == "all":
                self.pm.start_all()
                feedback.update("[green]Starting all services...[/]")
            elif target in PROCESSES:
                self.pm.start_process(target)
                feedback.update(f"[green]Starting {target}...[/]")
            else:
                 feedback.update(f"[red]Unknown service: {target}[/]")

        elif action == "stop":
            if len(parts) < 2:
                feedback.update("[red]Usage: stop <service|all>[/]")
                return
            target = parts[1]
            if target == "all":
                self.pm.stop_all()
                feedback.update("[yellow]Stopping all services...[/]")
            elif target in PROCESSES:
                self.pm.stop_process(target)
                feedback.update(f"[yellow]Stopping {target}...[/]")
            else:
                 feedback.update(f"[red]Unknown service: {target}[/]")
                 
        elif action == "restart":
             if len(parts) < 2: return
             target = parts[1]
             if target in PROCESSES:
                 self.pm.stop_process(target)
                 time.sleep(1)
                 self.pm.start_process(target)
                 feedback.update(f"[green]Restarted {target}[/]")
                 
        elif action == "quit":
            self.exit()
            
        else:
            feedback.update(f"[red]Unknown command: {action}[/]")

    def on_unmount(self):
        self.gpu_monitor.stop_monitoring()
        self.pm.stop_all()
        # Archive logs for this session
        LogManager.cleanup_all_logs()

if __name__ == "__main__":
    app = OrionLauncherApp()
    app.run()
