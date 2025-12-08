# gui.py (Refactored)
# Uses gui_modules for cleaner architecture.
# 1. Constants -> gui_modules.constants
# 2. Chat Rendering -> gui_modules.chat_components
# 3. Tab Building -> gui_modules.tab_builders
# 4. File Utils -> gui_modules.file_utils

import customtkinter
import tkinter
from tkinter import filedialog, messagebox
import threading
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

from orion_core import OrionCore
from orion_core_lite import OrionLiteCore
from main_utils import config
from gui_modules import constants as C
from gui_modules import chat_components as Chat
from gui_modules import tab_builders as Tabs
from gui_modules import file_utils as FileUtils

class OrionGUI:
    def __init__(self, core: OrionCore):
        self.core = core
        self.app = customtkinter.CTk()
        self.app.title(C.WINDOW_TITLE)
        self.app.geometry(C.WINDOW_GEOMETRY)

        self.uploaded_file_handles = []
        self.is_processing = False
        self.shutdown_mode_var = customtkinter.StringVar(value="Soft")
        
        # --- State Variables ---
        self.user_list = { C.DEFAULT_USER_ID: C.DEFAULT_USER_NAME }
        self.current_user_id = C.DEFAULT_USER_ID
        self.current_user_name = C.DEFAULT_USER_NAME
        self.current_user_var = customtkinter.StringVar(value=f"{C.DEFAULT_USER_NAME} ({C.DEFAULT_USER_ID})")
        
        self.current_session_id = C.DEFAULT_SESSION_ID
        self.session_menu_var = customtkinter.StringVar(value=self.current_session_id)
        
        self.use_streaming_var = customtkinter.BooleanVar(value=True)
        
        # --- Layout Setup ---
        self.paned_window = tkinter.PanedWindow(
            self.app, 
            orient="vertical", 
            sashwidth=C.PANE_SASH_WIDTH,
            sashrelief="flat",
            bg=C.COLOR_BG_DARK
        )
        self.paned_window.pack(pady=10, padx=10, fill="both", expand=True)

        # Top Pane: Chat + Files
        self.top_pane_frame = customtkinter.CTkFrame(self.paned_window, fg_color=C.COLOR_TRANSPARENT)
        self.paned_window.add(self.top_pane_frame, minsize=300, height=C.CHAT_PANE_HEIGHT)

        self.chat_frame = customtkinter.CTkScrollableFrame(self.top_pane_frame)
        self.chat_frame.pack(pady=0, padx=0, fill="both", expand=True)

        self.file_frame = customtkinter.CTkFrame(self.top_pane_frame, fg_color=C.COLOR_TRANSPARENT)
        self.file_frame.pack(pady=(5, 0), padx=0, fill="x")

        self.upload_button = customtkinter.CTkButton(
            self.file_frame, 
            text="Upload Files", 
            command=self.open_upload_dialog
        )
        self.upload_button.pack(side="left")

        self.file_label = customtkinter.CTkLabel(
            self.file_frame, 
            text="No files uploaded.",
            text_color="gray"
        )
        self.file_label.pack(side="left", padx=10)

        # Bottom Pane: Tabs
        self.bottom_pane_frame = customtkinter.CTkFrame(self.paned_window, fg_color=C.COLOR_TRANSPARENT)
        self.paned_window.add(self.bottom_pane_frame, minsize=300, height=C.BOTTOM_PANE_HEIGHT)

        self.setup_tabs(self.bottom_pane_frame)
        
        Chat.add_system_message(self.chat_frame, f"--- Orion GUI is active. Session: {self.current_session_id} ---")
        self.populate_history_on_load() 
        
        self.app.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_tabs(self, parent_frame):
        """Creates the main TabView and populates each tab via builders."""
        self.tab_view = customtkinter.CTkTabview(parent_frame)
        self.tab_view.pack(pady=0, padx=0, fill="both", expand=True)

        self.tab_view.add("Prompt")
        self.tab_view.add("Files")
        self.tab_view.add("Sessions") 
        self.tab_view.add("Settings")

        Tabs.build_prompt_tab(self, self.tab_view.tab("Prompt"))
        Tabs.build_files_tab(self, self.tab_view.tab("Files"))
        Tabs.build_sessions_tab(self, self.tab_view.tab("Sessions"))
        Tabs.build_settings_tab(self, self.tab_view.tab("Settings"))
        
        self.tab_view.set("Prompt")

    # --- Mode & Session Handlers ---
    def _update_user_dropdown(self):
        user_options = [f"{name} ({uid})" for uid, name in self.user_list.items()]
        self.user_menu.configure(values=user_options)

    def _on_toggle_mode(self):
        current_mode = self.core.get_session_mode(self.current_session_id)
        new_mode = "function" if current_mode == "cache" else "cache"
        self.core.set_session_mode(self.current_session_id, new_mode)
        self._update_mode_display()

    def _update_mode_display(self):
        current_mode = self.core.get_session_mode(self.current_session_id)
        if current_mode == "cache":
            self.mode_label.configure(
                text="💰 Context Caching Mode (Tools Disabled)",
                text_color=C.TEXT_GREEN
            )
            self.mode_toggle_button.configure(text="Switch to 🛠️ Tools")
        else:
            self.mode_label.configure(
                text="🛠️ Function Calling Mode (All Tools Available)",
                text_color=C.TEXT_ORANGE
            )
            self.mode_toggle_button.configure(text="Switch to 💰 Cache")

    def _on_add_user(self):
        name = self.new_user_name_entry.get().strip()
        uid = self.new_user_id_entry.get().strip()
        if not name or not uid:
            messagebox.showerror("Error", "Both User Name and User ID are required.")
            return
        self.user_list[uid] = name 
        self.new_user_name_entry.delete(0, "end")
        self.new_user_id_entry.delete(0, "end")
        self._update_user_dropdown()
        self._on_switch_user(f"{name} ({uid})")

    def _on_switch_user(self, selected_user_string: str):
        try:
            name, uid = selected_user_string.rsplit(" (", 1)
            uid = uid[:-1]
            self.current_user_id = uid
            self.current_user_name = name
            self.current_user_var.set(selected_user_string)
            self.current_user_label.configure(text=f"User Management (Current: {name})")
        except Exception as e:
            print(f"ERROR: Could not parse user string: {e}")

    def _on_create_new_session(self):
        new_id = f"gui_session_{int(datetime.now(timezone.utc).timestamp())}"
        self.current_session_id = new_id
        self._on_refresh_sessions_list()
        self.session_menu_var.set(new_id)
        self._rebuild_chat_display()

    def _on_switch_session(self, selected_session_id: str):
        self.current_session_id = selected_session_id
        self._rebuild_chat_display()
        self._update_mode_display()

    def _on_refresh_sessions_list(self):
        session_list = self.core.list_sessions()
        if not session_list and C.DEFAULT_SESSION_ID not in session_list:
            session_list.append(C.DEFAULT_SESSION_ID)
        self.session_menu.configure(values=session_list)
        if self.current_session_id not in session_list:
            # Re-add current if core lost it
            self.core.sessions.setdefault(self.current_session_id, [])
            session_list.append(self.current_session_id)
            self.session_menu.configure(values=session_list)
        self.session_menu_var.set(self.current_session_id)

    # --- Chat Display Logic ---
    def _rebuild_chat_display(self):
        for widget in self.chat_frame.winfo_children():
            widget.destroy()
        Chat.add_system_message(self.chat_frame, f"--- Loading Session: {self.current_session_id} ---")
        self.populate_history_on_load()

    def populate_history_on_load(self) -> bool:
        history_list = self.core.sessions.get(self.current_session_id)
        if not history_list:
            return False
        for index, exchange in enumerate(history_list):
            Chat.add_exchange_widget(
                self.chat_frame, 
                exchange, 
                index, 
                self._on_delete_exchange_pressed
            )
        self._scroll_chat_to_bottom()
        return True

    def _on_delete_exchange_pressed(self, index: int):
        try:
            # Try to grab prompt text to restore it
            exchange = self.core.sessions[self.current_session_id][index]
            prompt_text = ""
            if "user_content" in exchange:
                 for part in exchange["user_content"].parts:
                     if hasattr(part, 'text') and part.text:
                         try:
                             user_data = import_json_safe(part.text)
                             prompt_text = user_data.get("user_prompt", "")
                             break
                         except: continue
            self.prompt_box.delete("1.0", "end")
            self.prompt_box.insert("1.0", prompt_text)
            self.tab_view.set("Prompt")
        except: pass

        if messagebox.askyesno("Delete Exchange?", f"Delete exchange {index} and all following?"):
            self.core.manage_session_history(self.current_session_id, count=99999, index=index)
            self._rebuild_chat_display()

    def _scroll_chat_to_bottom(self):
        try:
            self.app.update_idletasks()
            self.chat_frame._parent_canvas.yview_moveto(1.0)
        except: pass

    # --- File Upload Logic ---
    def open_upload_dialog(self):
        if self.is_processing: return
        file_paths = filedialog.askopenfilenames()
        if not file_paths: return
        
        self.file_label.configure(text=f"Uploading {len(file_paths)} files...")
        threading.Thread(
            target=FileUtils.upload_files_process, 
            args=(
                self.core, 
                file_paths, 
                self._handle_upload_success, # Success callback
                self._handle_upload_error    # Error callback
            ),
            daemon=True
        ).start()

    def _handle_upload_success(self, new_handles):
        # Dispatch back to main thread
        self.app.after(0, self.on_upload_complete, new_handles)

    def _handle_upload_error(self, error_msg):
        # Dispatch back to main thread
        self.app.after(0, lambda: self.file_label.configure(text=str(error_msg), text_color="red"))

    def on_upload_complete(self, new_handles):
        for handle in new_handles:
            self.uploaded_file_handles.append(handle)
            row_frame = customtkinter.CTkFrame(self.staging_frame)
            row_frame.pack(fill="x", pady=(2, 2), padx=(2, 2))
            
            label = customtkinter.CTkLabel(row_frame, text=handle.display_name, text_color=C.TEXT_CYAN)
            label.pack(side="left", fill="x", expand=True, padx=(5, 5))
            
            remove_button = customtkinter.CTkButton(
                row_frame, text="X", width=30,
                command=lambda h=handle, rf=row_frame: self.remove_file_from_staging(h, rf)
            )
            remove_button.pack(side="right", padx=(0, 5))
        
        self.update_file_count_label()

    def remove_file_from_staging(self, file_handle, row_frame):
        try:
            self.uploaded_file_handles.remove(file_handle)
            row_frame.destroy()
            self.update_file_count_label()
        except: pass
            
    def update_file_count_label(self):
        count = len(self.uploaded_file_handles)
        if count == 0:
            self.file_label.configure(text="No files uploaded.", text_color="gray")
        else:
            self.file_label.configure(text=f"{count} file(s) ready.", text_color="cyan")

    # --- Message Sending & Processing ---
    def on_send_pressed(self, event=None):
        if self.is_processing: return
        user_input = self.prompt_box.get("1.0", "end-1c").strip()
        if not user_input and not self.uploaded_file_handles: return

        self.is_processing = True
        self.prompt_box.delete("1.0", "end")
        self.send_button.configure(state="disabled")
        self.upload_button.configure(state="disabled")

        # UI Updates
        Chat.add_user_message_bubble(
            self.chat_frame, 
            self.current_user_name, 
            user_input, 
            self.uploaded_file_handles,
            self._scroll_chat_to_bottom
        )
        model_bubble = Chat.add_model_message_bubble(
            self.chat_frame, 
            "Orion: ...",
            self._scroll_chat_to_bottom
        )

        files_to_process = list(self.uploaded_file_handles)
        self._clear_staging_area()
        
        threading.Thread(
            target=self.process_in_thread, 
            args=(user_input, files_to_process, model_bubble),
            daemon=True
        ).start()

    def _safe_configure(self, widget, **kwargs):
        """Safely configures a widget, ignoring TclError if it's destroyed."""
        try:
            widget.configure(**kwargs)
        except (tkinter.TclError, Exception):
            pass

    def process_in_thread(self, user_prompt, file_handles, model_bubble):
        try:
            use_stream = self.use_streaming_var.get()
            response_generator = self.core.process_prompt(
                session_id=self.current_session_id,
                user_prompt=user_prompt,
                file_check=file_handles,
                user_id=self.current_user_id,
                user_name=self.current_user_name,
                stream=use_stream
            )
            
            full_response_text = ""
            for chunk in response_generator:
                if isinstance(chunk, dict):
                    msg_type = chunk.get("type")
                    if msg_type == "status":
                        status_text = chunk.get("content", "Processing...")
                        self.app.after(0, lambda t=status_text: self._safe_configure(model_bubble, text=f"Orion: [{t}] ..."))
                    elif msg_type == "token":
                        full_response_text += chunk.get("content", "")
                        self.app.after(0, lambda t=full_response_text: self._safe_configure(model_bubble, text=f"Orion: {t}"))
                    elif msg_type == "usage" or msg_type == "full_response":
                        if msg_type == "full_response":
                            full_text = chunk.get("text", "")
                            self.app.after(0, lambda t=full_text: self._safe_configure(model_bubble, text=f"Orion: {t}"))
                        
                        token_count = chunk.get("token_count", 0)
                        restart_pending = chunk.get("restart_pending", False)
                        
                        def add_token_label(cnt=token_count):
                            try:
                                if not model_bubble.winfo_exists(): return
                                lbl = customtkinter.CTkLabel(model_bubble.master, text=f"({cnt} tokens)", 
                                                           font=customtkinter.CTkFont(size=10), text_color="gray")
                                lbl.pack(anchor="e", padx=10, pady=(0, 2))
                            except (tkinter.TclError, Exception):
                                pass
                        self.app.after(0, add_token_label)

                        if restart_pending:
                             self.app.after(0, lambda: Chat.add_system_message(self.chat_frame, "--- System: Restart Required. ---"))
                             self.app.after(2000, self.do_hard_restart_thread)


        except Exception as e:
            self.app.after(0, lambda: Chat.add_system_message(self.chat_frame, f"--- Error: {e} ---", "error"))
        finally:
            self.is_processing = False
            self.app.after(0, lambda: self.send_button.configure(state="normal"))
            self.app.after(0, lambda: self.upload_button.configure(state="normal"))
            self.app.after(0, self._scroll_chat_to_bottom)

    def _clear_staging_area(self):
        self.uploaded_file_handles.clear()
        self.update_file_count_label()
        for widget in self.staging_frame.winfo_children():
            widget.destroy()

    # --- System Controls ---
    def on_truncate_history_pressed(self):
        try:
            index = int(self.history_index_entry.get().strip() or 0)
            count = int(self.history_count_entry.get().strip() or 0)
            if count <= 0 or index < 0: raise ValueError
        except:
            messagebox.showerror("Invalid Input", "Using default/input error.")
            return

        if messagebox.askyesno("Execute Truncation?", f"Delete {count} exchanges from index {index}?"):
            self.core.manage_session_history(self.current_session_id, count=count, index=index)
            self._rebuild_chat_display()

    def on_shutdown_pressed(self):
        mode = self.shutdown_mode_var.get()
        if not messagebox.askyesno(f"{mode} Confirmation", f"Perform '{mode}' action?"): return
        
        if mode == "Soft":
            Chat.add_system_message(self.chat_frame, "--- Soft Refresh ---")
            threading.Thread(target=self.do_soft_refresh_thread, daemon=True).start()
        elif mode == "Hard":
            Chat.add_system_message(self.chat_frame, "--- Hard Restart ---")
            threading.Thread(target=self.do_hard_restart_thread, daemon=True).start()
        elif mode == "Full":
            self.on_closing()

    def do_soft_refresh_thread(self):
        try:
            res = self.core.trigger_instruction_refresh(full_restart=False)
            self.app.after(0, lambda: Chat.add_system_message(self.chat_frame, f"--- {res} ---"))
        except Exception as e:
             self.app.after(0, lambda: Chat.add_system_message(self.chat_frame, f"Error: {e}", "error"))

    def do_hard_restart_thread(self):
        try:
             self.app.after(0, lambda: Chat.add_system_message(self.chat_frame, "--- Saving state... ---"))
             if self.core.save_state_for_restart():
                 self.core.execute_restart()
        except Exception as e:
             self.app.after(0, lambda: Chat.add_system_message(self.chat_frame, f"Error: {e}", "error"))

    def on_closing(self):
        self.core.shutdown()
        self.app.destroy()

    def run(self):
        self.app.mainloop()

# --- Helper for parsing embedded JSON in text parts ---
import json
def import_json_safe(text):
    return json.loads(text)

if __name__ == "__main__":
    customtkinter.set_appearance_mode("Dark")
    customtkinter.set_default_color_theme("blue")
    
    try:
        # Dual Core Selection Logic (Mirrors bot.py)
        if "gemma" in config.AI_MODEL.lower() or config.BACKEND == "ollama":
            print(f"--- GUI starting with ORION LITE CORE ({config.BACKEND}) ---")
            main_core = OrionLiteCore()
        else:
            print("--- GUI starting with ORION CORE (PRO) ---")
            main_core = OrionCore()

        app = OrionGUI(core=main_core)
        app.run()
    except Exception as e:
        print(f"FATAL ERROR: {e}")