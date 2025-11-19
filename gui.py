# gui_app.py (v3.3 - Restored & Fixed)
# 1. Adds a "Sessions" tab to create, switch, and refresh sessions.
# 2. Replaces hardcoded 'GUI_SESSION_ID' with 'self.current_session_id'.
# 3. All GUI actions (chat, delete, clear) now target the active session.
# 4. RESTORES the "loading" placeholder bubble.
# 5. FIXES: Chat bubble text wrapping.
# 6. FIXES: Dynamic user name display.

import customtkinter
import tkinter
from tkinter import filedialog
from tkinter import messagebox
import os
import threading
import mimetypes
import json
from PIL import Image
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

from orion_core import OrionCore

class OrionGUI:
    def __init__(self, core: OrionCore):
        self.core = core
        self.app = customtkinter.CTk()
        self.app.title("Orion Core - Test Environment")
        self.app.geometry("600x1050")

        self.uploaded_file_handles = []
        self.is_processing = False
        self.shutdown_mode_var = customtkinter.StringVar(value="Soft")
        
        # --- MODIFICATION: Change from static to dynamic users ---
        default_user_id = os.getenv("DISCORD_OWNER_ID") or "000000000000000000"
        default_user_name = "Leo (GUI)"
        
        # This dictionary will store all available users {user_id: user_name}
        self.user_list = {
            default_user_id: default_user_name
        }
        
        # These are now state variables
        self.current_user_id = default_user_id
        self.current_user_name = default_user_name
        
        # This will be used for the new dropdown
        self.current_user_var = customtkinter.StringVar(value=f"{default_user_name} ({default_user_id})")
        # --- END OF MODIFICATION ---
        
        # --- MODIFICATION: New state variables for session management ---
        self.current_session_id = "local_gui_user" # Default session
        self.session_menu_var = customtkinter.StringVar(value=self.current_session_id)
        
        # --- MODIFICATION: Restore placeholder variable ---
        self.current_loading_frame = None 
        
        # --- MODIFICATION: Streaming Toggle ---
        self.use_streaming_var = customtkinter.BooleanVar(value=True)
        
        # --- (PanedWindow and Top Pane setup is unchanged) ---
        self.paned_window = tkinter.PanedWindow(
            self.app, 
            orient="vertical", 
            sashwidth=4,
            sashrelief="flat",
            bg="#242424"
        )
        self.paned_window.pack(pady=10, padx=10, fill="both", expand=True)

        self.top_pane_frame = customtkinter.CTkFrame(
            self.paned_window, 
            fg_color="transparent"
        )
        self.paned_window.add(self.top_pane_frame, minsize=300, height=750)

        self.chat_frame = customtkinter.CTkScrollableFrame(
            self.top_pane_frame
        )
        self.chat_frame.pack(pady=0, padx=0, fill="both", expand=True)

        self.file_frame = customtkinter.CTkFrame(
            self.top_pane_frame, 
            fg_color="transparent"
        )
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

        self.bottom_pane_frame = customtkinter.CTkFrame(
            self.paned_window,
            fg_color="transparent"
        )
        self.paned_window.add(self.bottom_pane_frame, minsize=300, height=300)

        self.setup_tabs(self.bottom_pane_frame)
        
        self._add_system_message(f"--- Orion GUI is active. Session: {self.current_session_id} ---")
        self.populate_history_on_load() 
        
        self.app.protocol("WM_DELETE_WINDOW", self.on_closing)

    # --- MODIFICATION: Added "Sessions" tab ---
    def setup_tabs(self, parent_frame):
        """Creates the main TabView and populates each tab."""
        self.tab_view = customtkinter.CTkTabview(parent_frame)
        self.tab_view.pack(pady=0, padx=0, fill="both", expand=True)

        self.tab_view.add("Prompt")
        self.tab_view.add("Files")
        self.tab_view.add("Sessions") # New tab
        self.tab_view.add("Settings")

        self.create_prompt_tab(self.tab_view.tab("Prompt"))
        self.create_files_tab(self.tab_view.tab("Files"))
        self.create_sessions_tab(self.tab_view.tab("Sessions")) # New builder call
        self.create_settings_tab(self.tab_view.tab("Settings"))
        
        self.tab_view.set("Prompt")

    # --- (create_prompt_tab and create_files_tab are unchanged) ---
    def create_prompt_tab(self, tab_frame):
        prompt_inner_frame = customtkinter.CTkFrame(tab_frame, fg_color="transparent")
        prompt_inner_frame.pack(fill="both", expand=True, padx=5, pady=5)
        prompt_inner_frame.grid_rowconfigure(0, weight=1)
        prompt_inner_frame.grid_columnconfigure(0, weight=1)
        prompt_inner_frame.grid_columnconfigure(1, weight=0)
        self.prompt_box = customtkinter.CTkTextbox(
            prompt_inner_frame,
            wrap="word",
            font=customtkinter.CTkFont(size=13)
        )
        self.prompt_box.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.send_button = customtkinter.CTkButton(
            prompt_inner_frame, 
            text="Send", 
            command=self.on_send_pressed,
            width=60,
        )
        self.send_button.grid(row=0, column=1, sticky="ns")
    
    def create_files_tab(self, tab_frame):
        self.staging_frame = customtkinter.CTkScrollableFrame(
            tab_frame,
            label_text="Staged Files (Ready to Send)"
        )
        self.staging_frame.pack(fill="both", expand=True, pady=5, padx=5)

    # --- MODIFICATION: New function to build the Sessions tab ---
    def create_sessions_tab(self, tab_frame):
        """
        Creates the widgets for the 'Sessions' tab, including
        Session Switching and User Management.
        """
        
        # --- 1. Switch Session Frame ---
        switch_session_frame = customtkinter.CTkFrame(tab_frame, fg_color="transparent")
        switch_session_frame.pack(fill="x", padx=10, pady=10)

        switch_label = customtkinter.CTkLabel(
            switch_session_frame,
            text="Active Session",
            font=customtkinter.CTkFont(weight="bold")
        )
        switch_label.pack(anchor="w")
        
        # Dropdown and Refresh Button
        dropdown_frame = customtkinter.CTkFrame(switch_session_frame, fg_color="transparent")
        dropdown_frame.pack(fill="x", pady=(5, 5))

        self.session_menu = customtkinter.CTkOptionMenu(
            dropdown_frame,
            variable=self.session_menu_var,
            command=self._on_switch_session,
            values=["local_gui_user"] # Placeholder
        )
        self.session_menu.pack(side="left", fill="x", expand=True, padx=(0, 10))

        refresh_button = customtkinter.CTkButton(
            dropdown_frame,
            text="Refresh List",
            command=self._on_refresh_sessions_list,
            width=100
        )
        refresh_button.pack(side="right")
        
        # --- Create New Session Button ---
        new_session_button = customtkinter.CTkButton(
            switch_session_frame,
            text="Create New Session",
            command=self._on_create_new_session
        )
        new_session_button.pack(fill="x", pady=(5, 10))
        
        # --- Add a visual separator ---
        separator = customtkinter.CTkFrame(tab_frame, height=2, fg_color="#505050")
        separator.pack(fill="x", padx=10, pady=(10, 5))

        # --- 2. User Management Frame ---
        user_frame = customtkinter.CTkFrame(tab_frame, fg_color="transparent")
        user_frame.pack(fill="x", padx=10, pady=(10, 0)) # Add padding at top

        # We make this a class property so we can update its text
        self.current_user_label = customtkinter.CTkLabel(
            user_frame,
            text=f"Active User (Current: {self.current_user_name})",
            font=customtkinter.CTkFont(weight="bold")
        )
        self.current_user_label.pack(anchor="w")

        # --- Switch User Dropdown ---
        switch_user_frame = customtkinter.CTkFrame(user_frame, fg_color="transparent")
        switch_user_frame.pack(fill="x", pady=(5,10))
        
        # We make this a class property to update its values
        self.user_menu = customtkinter.CTkOptionMenu(
            switch_user_frame,
            variable=self.current_user_var,
            values=[f"{name} ({uid})" for uid, name in self.user_list.items()],
            command=self._on_switch_user
        )
        self.user_menu.pack(fill="x", expand=True)

        # --- Add New User ---
        add_user_frame = customtkinter.CTkFrame(user_frame, fg_color="transparent")
        add_user_frame.pack(fill="x", pady=(5,5))
        
        self.new_user_name_entry = customtkinter.CTkEntry(
            add_user_frame,
            placeholder_text="New User Name"
        )
        self.new_user_name_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.new_user_id_entry = customtkinter.CTkEntry(
            add_user_frame,
            placeholder_text="New User ID"
        )
        self.new_user_id_entry.pack(side="left", fill="x", expand=True)

        add_user_button = customtkinter.CTkButton(
            user_frame,
            text="Add/Update User",
            command=self._on_add_user
        )
        add_user_button.pack(fill="x", pady=(5, 5))

        # --- Initial population of the dropdown ---
        self._on_refresh_sessions_list()

    # --- (create_settings_tab is unchanged) ---
    # In gui.py, replace your 'create_settings_tab' function:

    def create_settings_tab(self, tab_frame):
        """Creates the widgets for the 'Settings' tab."""
        
        # --- History Management Frame ---
        history_frame = customtkinter.CTkFrame(tab_frame, fg_color="transparent")
        history_frame.pack(fill="x", padx=10, pady=10)

        history_label = customtkinter.CTkLabel(
            history_frame,
            text="Session History Management (Current Session)",
            font=customtkinter.CTkFont(weight="bold")
        )
        history_label.pack(anchor="w")
        
        input_frame = customtkinter.CTkFrame(history_frame, fg_color="transparent")
        input_frame.pack(fill="x", pady=(5,5))
        
        self.history_index_entry = customtkinter.CTkEntry(
            input_frame,
            placeholder_text="Start Index (e.g., 0)"
        )
        self.history_index_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.history_count_entry = customtkinter.CTkEntry(
            input_frame,
            placeholder_text="Count (e.g., 5 or 999)"
        )
        self.history_count_entry.pack(side="left", fill="x", expand=True)

        execute_button = customtkinter.CTkButton(
            history_frame,
            text="Execute History Truncation",
            command=self.on_truncate_history_pressed
        )
        execute_button.pack(fill="x", pady=(5, 5))
        
        # --- System Control Frame (Unchanged) ---
        shutdown_frame = customtkinter.CTkFrame(tab_frame, fg_color="transparent")
        shutdown_frame.pack(fill="x", padx=10, pady=20)
        shutdown_label = customtkinter.CTkLabel(
            shutdown_frame,
            text="System Control (Global)",
            font=customtkinter.CTkFont(weight="bold")
        )
        shutdown_label.pack(anchor="w")
        control_frame = customtkinter.CTkFrame(shutdown_frame, fg_color="transparent")
        control_frame.pack(fill="x", pady=(5, 5))
        shutdown_options = customtkinter.CTkOptionMenu(
            control_frame,
            values=["Soft", "Hard", "Full"],
            variable=self.shutdown_mode_var
        )
        shutdown_options.pack(side="left", padx=(0, 10))
        shutdown_button = customtkinter.CTkButton(
            control_frame,
            text="Execute Action",
            command=self.on_shutdown_pressed,
            fg_color="#db524b",
            hover_color="#b0423d"
        )
        shutdown_button.pack(side="left", fill="x", expand=True)

        # --- Generation Settings Frame ---
        gen_settings_frame = customtkinter.CTkFrame(tab_frame, fg_color="transparent")
        gen_settings_frame.pack(fill="x", padx=10, pady=20)
        
        gen_label = customtkinter.CTkLabel(
            gen_settings_frame,
            text="Generation Settings",
            font=customtkinter.CTkFont(weight="bold")
        )
        gen_label.pack(anchor="w")
        
        stream_switch = customtkinter.CTkSwitch(
            gen_settings_frame,
            text="Enable Streaming Response",
            variable=self.use_streaming_var
        )
        stream_switch.pack(anchor="w", pady=(5, 0))

    def _update_user_dropdown(self):
        """Helper function to rebuild the user dropdown list."""
        user_options = [f"{name} ({uid})" for uid, name in self.user_list.items()]
        self.user_menu.configure(values=user_options)

    def _on_add_user(self):
        """Adds a new user to the user list and updates the UI."""
        name = self.new_user_name_entry.get().strip()
        uid = self.new_user_id_entry.get().strip()
        
        if not name or not uid:
            messagebox.showerror("Error", "Both User Name and User ID are required.")
            return
            
        print(f"--- GUI: Adding/Updating user: {name} ({uid}) ---")
        self.user_list[uid] = name # Add or update in the dictionary
        
        self.new_user_name_entry.delete(0, "end")
        self.new_user_id_entry.delete(0, "end")
        
        self._update_user_dropdown()
        # Automatically switch to the new user
        self._on_switch_user(f"{name} ({uid})")

    def _on_switch_user(self, selected_user_string: str):
        """Switches the active user state variables."""
        try:
            # --- MODIFICATION: Use rsplit to split only on the *last* ' (' ---
            # This correctly handles names that contain parentheses, like "Leo (GUI)"
            name, uid = selected_user_string.rsplit(" (", 1)
            # --- END OF MODIFICATION ---
            
            uid = uid[:-1] # Remove the closing ')'
            
            self.current_user_id = uid
            self.current_user_name = name
            self.current_user_var.set(selected_user_string)
            self.current_user_label.configure(text=f"User Management (Current: {name})")
            print(f"--- GUI: Switched active user to: {name} ({uid}) ---")
            
        except Exception as e:
            print(f"ERROR: Could not parse user string '{selected_user_string}': {e}")    
    
    def _on_create_new_session(self):
        """Generates a new session ID and switches to it."""
        new_id = f"gui_session_{int(datetime.now(timezone.utc).timestamp())}"
        print(f"--- GUI: Creating new session: {new_id} ---")
        self.current_session_id = new_id
        
        # This will create the session in the core automatically
        # when populate_history_on_load runs (and finds nothing).
        
        # Refresh the dropdown list
        self._on_refresh_sessions_list()
        # Set the dropdown to the new ID
        self.session_menu_var.set(new_id)
        # Rebuild the chat display (will be empty)
        self._rebuild_chat_display()

    def _on_switch_session(self, selected_session_id: str):
        """Switches the active session ID and rebuilds the chat."""
        print(f"--- GUI: Switching to session: {selected_session_id} ---")
        self.current_session_id = selected_session_id
        self._rebuild_chat_display()

    def _on_refresh_sessions_list(self):
        """Fetches all session IDs from the core and updates the dropdown."""
        print("--- GUI: Refreshing session list from core... ---")
        session_list = self.core.list_sessions()
        
        # Ensure there's at least one session (our default)
        if not session_list and "local_gui_user" not in session_list:
            session_list.append("local_gui_user")
            
        # Update the dropdown's values
        self.session_menu.configure(values=session_list)
        
        # Ensure the selected item is still valid
        if self.current_session_id not in session_list:
            # This can happen if the core restarts and 'local_gui_user' is gone
            # We must ensure the core *also* has this session
            self.core.sessions.setdefault(self.current_session_id, [])
            session_list.append(self.current_session_id)
            self.session_menu.configure(values=session_list)
            
        self.session_menu_var.set(self.current_session_id)
            
    # --- (End of new session functions) ---

    # --- MODIFICATION: This function now targets 'self.current_session_id' ---
    def _rebuild_chat_display(self):
        """Destroys all chat bubbles and redraws them from the core's history."""
        # 1. Destroy all current chat widgets
        for widget in self.chat_frame.winfo_children():
            widget.destroy()
            
        # --- MODIFICATION: Add this line ---
        self.current_loading_frame = None # Tell the app the placeholder is gone
        # --- END OF MODIFICATION ---
            
        # 2. Repopulate from the (now modified) core history
        self._add_system_message(f"--- Loading Session: {self.current_session_id} ---")
        self.populate_history_on_load()

    # --- MODIFICATION: This function now targets 'self.current_session_id' ---
    def populate_history_on_load(self) -> bool:
        """
        Loops through the core's session history and adds a
        chat bubble widget for each exchange.
        """
        print(f"--- GUI: (Re)populating chat display for {self.current_session_id}... ---")
        # --- Use the dynamic session ID ---
        history_list = self.core.sessions.get(self.current_session_id)

        if not history_list:
            print("--- GUI: No active history found. ---")
            return False
        
        for index, exchange in enumerate(history_list):
            self._add_exchange_widget(exchange, index)
        
        self._scroll_chat_to_bottom()
        return True

    # --- (All chat bubble functions are unchanged, but 'You: Hello Orion' now uses 15) ---
    def _add_system_message(self, text: str, tag: str = "system"):
        color = "gray" if tag == "system" else "red"
        bubble = customtkinter.CTkLabel(
            self.chat_frame,
            text=text,
            text_color=color,
            font=customtkinter.CTkFont(size=13, slant="italic"), # Your font size
            anchor="w",
            justify="left"
        )
        bubble.pack(fill="x", pady=(5, 5), padx=10)
        self._scroll_chat_to_bottom()

    def _add_exchange_widget(self, exchange: Dict[str, Any], index: int):
        try:
            master_frame = customtkinter.CTkFrame(self.chat_frame, fg_color="#303030")
            master_frame.pack(fill="x", pady=(5, 5), padx=5)

            labels_to_wrap = []

            user_content = exchange.get("user_content")
            if user_content:
                # --- REFACTORED: Intelligently parse user content parts ---
                prompt_text = "[User prompt not found]"
                user_name = "User"
                file_text = ""

                for part in user_content.parts:
                    # Check if it's a file part
                    if hasattr(part, 'display_name'):
                        file_text += f"[File: {part.display_name}]\n"
                    # Check if it's a text part containing our JSON envelope
                    elif hasattr(part, 'text') and part.text:
                        try:
                            user_data = json.loads(part.text)
                            prompt_text = user_data.get("user_prompt", "[User prompt]")
                            user_name = user_data.get("auth", {}).get("user_name", "User")
                        except (json.JSONDecodeError, TypeError):
                            continue

                user_bubble = customtkinter.CTkLabel(
                    master_frame,
                    text=f"{user_name}: {prompt_text}",
                    text_color="cyan",
                    anchor="w",
                    justify="left",
                    font=customtkinter.CTkFont(size=15)
                )
                user_bubble.pack(fill="x", padx=10, pady=(5, 2))
                labels_to_wrap.append(user_bubble)
                
                if file_text:
                    file_label = customtkinter.CTkLabel(
                        master_frame,
                        text=file_text.strip(),
                        text_color="cyan",
                        font=customtkinter.CTkFont(size=11, slant="italic"),
                        anchor="w",
                        justify="left"
                    )
                    file_label.pack(fill="x", padx=15, pady=(0, 5))

            tool_calls = exchange.get("tool_calls", [])
            if tool_calls:
                tool_text = f"Orion: [Executed {len(tool_calls)} Tool Call(s)]"
                tool_bubble = customtkinter.CTkLabel(
                    master_frame,
                    text=tool_text,
                    text_color="#AAAAAA",
                    font=customtkinter.CTkFont(size=11, slant="italic"),
                    anchor="w",
                    justify="left"
                )
                tool_bubble.pack(fill="x", padx=10, pady=(0, 2))

            model_content = exchange.get("model_content")
            if model_content and model_content.parts:
                model_text = "".join(part.text for part in model_content.parts if part.text)
                
                model_bubble = customtkinter.CTkLabel(
                    master_frame,
                    text=f"Orion: {model_text.strip()}",
                    anchor="w",
                    justify="left",
                    font=customtkinter.CTkFont(size=15)
                )
                model_bubble.pack(fill="x", padx=10, pady=(2, 0))
                labels_to_wrap.append(model_bubble)

                token_count = exchange.get("token_count", 0)
                if token_count > 0:
                    token_label = customtkinter.CTkLabel(
                        master_frame,
                        text=f"(`Tokens: {token_count}`)",
                        text_color="gray",
                        font=customtkinter.CTkFont(size=10, slant="italic"),
                        anchor="w",
                        justify="left"
                    )
                    token_label.pack(fill="x", padx=10, pady=(0, 5))

            delete_button = customtkinter.CTkButton(
                master_frame,
                text="X",
                width=25,
                height=25,
                fg_color="#505050",
                hover_color="#db524b",
                command=lambda i=index: self._on_delete_exchange_pressed(i)
            )
            delete_button.place(relx=1.0, rely=0, x=-5, y=5, anchor="ne")
            
            master_frame.bind(
                "<Configure>", 
                lambda event, labels=labels_to_wrap: self._update_bubble_wraps(event, labels)
            )

        except Exception as e:
            print(f"ERROR: Failed to draw chat bubble for index {index}: {e}")
            self._add_system_message(f"--- Error rendering exchange {index} ---", "error")

    def _on_delete_exchange_pressed(self, index: int):
        try:
            exchange = self.core.sessions[self.current_session_id][index]
            prompt_text = ""
            user_content = exchange.get("user_content")
            for part in user_content.parts:
                if hasattr(part, 'text') and part.text:
                    try:
                        user_data = json.loads(part.text)
                        prompt_text = user_data.get("user_prompt", "")
                        break
                    except: continue
            self.prompt_box.delete("1.0", "end")
            self.prompt_box.insert("1.0", prompt_text)
            self.tab_view.set("Prompt")
        except Exception as e:
            print(f"--- GUI: Could not copy prompt text: {e} ---")
        
        if not messagebox.askyesno(
            f"Delete Exchange?",
            f"This will delete the exchange at index {index} AND all messages that followed it.\n\nThe original prompt has been copied to your prompt box.\n\nAre you sure?"
        ):
            print(f"--- GUI: User cancelled 'Truncate at {index}'. ---")
            return
            
        print(f"--- GUI: User confirmed 'Truncate at {index}' ---")
        result = self.core.manage_session_history(self.current_session_id, count=99999, index=index)
        self._rebuild_chat_display()
        self.history_index_entry.delete(0, "end")
        self.history_count_entry.delete(0, "end")
        print(f"--- GUI: {result} ---")

    def _scroll_chat_to_bottom(self):
        try:
            self.app.update_idletasks()
            self.chat_frame._parent_canvas.yview_moveto(1.0)
        except Exception as e:
            print(f"Error scrolling to bottom: {e}")
            
    def _update_bubble_wraps(self, event, labels: List[customtkinter.CTkLabel]):
        new_wraplength = event.width - 50 
        if new_wraplength < 10:
            new_wraplength = 10
        for label in labels:
            label.configure(wraplength=new_wraplength)

    def open_upload_dialog(self):
        if self.is_processing:
            return
        file_paths = filedialog.askopenfilenames()
        if not file_paths:
            return
        self.file_label.configure(text=f"Uploading {len(file_paths)} files...")
        threading.Thread(
            target=self.upload_thread_target, 
            args=(file_paths,),
            daemon=True
        ).start()

    def upload_thread_target(self, file_paths: tuple):
        new_handles = []
        display_name = None
        for file_path in file_paths:
            try:
                display_name = os.path.basename(file_path)
                mime_type, _ = mimetypes.guess_type(file_path)
                if mime_type is None:
                    mime_type = "application/octet-stream"
                with open(file_path, "rb") as f:
                    file_bytes = f.read()
                file_handle = self.core.upload_file(
                    file_bytes=file_bytes,
                    display_name=display_name,
                    mime_type=mime_type
                )
                if file_handle:
                    new_handles.append(file_handle)
            except Exception as e:
                print(f"ERROR: Failed to upload file '{display_name}': {e}")
                self.app.after(0, lambda: self.file_label.configure(
                    text=f"Failed to upload {display_name}", 
                    text_color="red"
                ))
        self.app.after(0, self.on_upload_complete, new_handles)

    def on_upload_complete(self, new_handles):
        for handle in new_handles:
            self.uploaded_file_handles.append(handle)
            row_frame = customtkinter.CTkFrame(self.staging_frame)
            row_frame.pack(fill="x", pady=(2, 2), padx=(2, 2))
            label = customtkinter.CTkLabel(
                row_frame,
                text=handle.display_name,
                text_color="cyan"
            )
            label.pack(side="left", fill="x", expand=True, padx=(5, 5))
            remove_button = customtkinter.CTkButton(
                row_frame,
                text="X",
                width=30,
                command=lambda h=handle, rf=row_frame: self.remove_file_from_staging(h, rf)
            )
            remove_button.pack(side="right", padx=(0, 5))
        self.update_file_count_label()

    def remove_file_from_staging(self, file_handle, row_frame):
        try:
            self.uploaded_file_handles.remove(file_handle)
            row_frame.destroy()
            self.update_file_count_label()
        except ValueError:
            print(f"--- GUI: Could not remove file {file_handle.display_name}, not found in list.")
            
    def update_file_count_label(self):
        count = len(self.uploaded_file_handles)
        if count == 0:
            self.file_label.configure(text="No files uploaded.", text_color="gray")
        else:
            self.file_label.configure(text=f"{count} file(s) ready.", text_color="cyan")

    def on_truncate_history_pressed(self):
        try:
            index_str = self.history_index_entry.get().strip()
            count_str = self.history_count_entry.get().strip()
            index = int(index_str) if index_str else 0
            count = int(count_str) if count_str else 0

            if count <= 0:
                messagebox.showerror("Invalid Input", "Count must be a positive number (e.g., 1, 5, 999).")
                return
            if index < 0:
                messagebox.showerror("Invalid Input", "Index must be 0 or greater.")
                return
        except ValueError:
            messagebox.showerror("Invalid Input", "Index and Count must be valid numbers.")
            return

        if not messagebox.askyesno(
            f"Execute Truncation?",
            f"Are you sure you want to delete {count} exchange(s) starting from index {index}?\nThis will affect the CURRENTLY active session."
        ):
            print(f"--- GUI: User cancelled truncation. ---")
            return
            
        print(f"--- GUI: User confirmed truncation: count={count}, index={index} ---")
        result = self.core.manage_session_history(self.current_session_id, count=count, index=index)
        self._rebuild_chat_display()
        self.history_index_entry.delete(0, "end")
        self.history_count_entry.delete(0, "end")
        print(f"--- GUI: {result} ---")

    def on_shutdown_pressed(self):
        mode = self.shutdown_mode_var.get()
        title = f"{mode} Confirmation"
        message = f"Are you sure you want to perform a '{mode}' action?"
        if mode == "Hard":
            message += "\nThis will restart the application."
        elif mode == "Full":
            message += "\nThis will close the application."
        if not messagebox.askyesno(title, message):
            print(f"--- GUI: User cancelled '{mode}' action. ---")
            return
        print(f"--- GUI: User confirmed '{mode}' action. ---")
        if mode == "Soft":
            self._add_system_message(f"--- System: 'Soft' (hot-swap) refresh initiating... ---")
            threading.Thread(target=self.do_soft_refresh_thread, daemon=True).start()
        elif mode == "Hard":
            self._add_system_message(f"--- System: 'Hard' (restart) initiating... ---")
            threading.Thread(target=self.do_hard_restart_thread, daemon=True).start()
        elif mode == "Full":
            self.on_closing()
            
    def do_soft_refresh_thread(self):
        try:
            result_string = self.core.trigger_instruction_refresh(full_restart=False)
            self.app.after(0, lambda: self._add_system_message(
                f"--- System: {result_string} ---"
            ))
        except Exception as e:
            print(f"ERROR: Soft refresh failed: {e}")
            self.app.after(0, lambda: self._add_system_message(
                f"--- ERROR: Soft refresh failed: {e} ---", "error"
            ))

    def do_hard_restart_thread(self):
        try:
            self.app.after(0, lambda: self._add_system_message("--- System: Saving state... ---"))
            if self.core.save_state_for_restart():
                self.app.after(0, lambda: self._add_system_message("--- System: State saved. Executing restart now. ---"))
                self.core.execute_restart()
            else:
                raise Exception("save_state_for_restart() returned False.")
        except Exception as e:
            print(f"ERROR: Hard restart failed: {e}")
            self.app.after(0, lambda: self._add_system_message(f"--- ERROR: Hard restart failed: {e} ---", "error"))

    def _add_user_message_bubble(self, text, file_handles):
        master_frame = customtkinter.CTkFrame(self.chat_frame, fg_color="#303030")
        master_frame.pack(fill="x", pady=(5, 5), padx=5)
        
        user_bubble = customtkinter.CTkLabel(
            master_frame,
            text=f"{self.current_user_name}: {text}",
            text_color="cyan",
            anchor="w",
            justify="left",
            font=customtkinter.CTkFont(size=15)
        )
        user_bubble.pack(fill="x", padx=10, pady=(5, 2))
        
        # --- FIX: Ensure text wrapping works dynamically ---
        user_bubble.configure(wraplength=400)
        master_frame.bind(
            "<Configure>", 
            lambda event, labels=[user_bubble]: self._update_bubble_wraps(event, labels)
        )
        
        if file_handles:
            file_text = "\n".join([f"[File: {f.display_name}]" for f in file_handles])
            file_label = customtkinter.CTkLabel(
                master_frame,
                text=file_text,
                text_color="cyan",
                font=customtkinter.CTkFont(size=11, slant="italic"),
                anchor="w",
                justify="left"
            )
            file_label.pack(fill="x", padx=15, pady=(0, 5))
            
        self._scroll_chat_to_bottom()

    def _add_model_message_bubble(self, initial_text):
        master_frame = customtkinter.CTkFrame(self.chat_frame, fg_color="#303030")
        master_frame.pack(fill="x", pady=(5, 5), padx=5)
        
        model_bubble = customtkinter.CTkLabel(
            master_frame,
            text=initial_text,
            anchor="w",
            justify="left",
            font=customtkinter.CTkFont(size=15)
        )
        model_bubble.pack(fill="x", padx=10, pady=(2, 5))
        
        # --- FIX: Ensure text wrapping works dynamically ---
        # Set an initial wrap length (arbitrary, will be updated by event)
        model_bubble.configure(wraplength=400) 
        
        # Bind the Configure event to update wraplength on resize
        master_frame.bind(
            "<Configure>", 
            lambda event, labels=[model_bubble]: self._update_bubble_wraps(event, labels)
        )
        
        self._scroll_chat_to_bottom()
        return model_bubble

    def on_send_pressed(self, event=None):
        if self.is_processing:
            return
        
        user_input = self.prompt_box.get("1.0", "end-1c").strip()
        if not user_input and not self.uploaded_file_handles:
            return

        self.is_processing = True
        self.prompt_box.delete("1.0", "end")
        self.send_button.configure(state="disabled")
        self.upload_button.configure(state="disabled")

        # 1. Create User Bubble immediately
        self._add_user_message_bubble(user_input, self.uploaded_file_handles)

        # 2. Create Model Placeholder Bubble immediately
        model_bubble = self._add_model_message_bubble("Orion: ...")
        

        # 3. Start Processing Thread
        # We pass the file handles and then clear the staging list
        files_to_process = list(self.uploaded_file_handles)
        self._clear_staging_area()
        
        threading.Thread(
            target=self.process_in_thread, 
            args=(user_input, files_to_process, model_bubble),
            daemon=True
        ).start()

    def process_in_thread(self, user_prompt, file_handles, model_bubble):
        try:
            # --- Streaming Call ---
            use_stream = self.use_streaming_var.get()
            
            # We iterate over the generator returned by process_prompt (which is now ALWAYS a generator)
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
                # Handle Dictionary Events
                if isinstance(chunk, dict):
                    msg_type = chunk.get("type")
                    
                    if msg_type == "status":
                        # Update bubble with status
                        status_text = chunk.get("content", "Processing...")
                        self.app.after(0, lambda t=status_text: model_bubble.configure(text=f"Orion: [{t}] ..."))
                        
                    elif msg_type == "token":
                        # Streaming text
                        text_chunk = chunk.get("content", "")
                        full_response_text += text_chunk
                        self.app.after(0, lambda t=full_response_text: model_bubble.configure(text=f"Orion: {t}"))
                        
                    elif msg_type == "usage":
                        # Streaming complete - Show tokens
                        token_count = chunk.get("token_count", 0)
                        restart_pending = chunk.get("restart_pending", False)
                        print(f"--- Stream Complete. Tokens: {token_count} ---")
                        
                        # Add token label
                        def add_token_label(cnt=token_count):
                            master_frame = model_bubble.master
                            token_label = customtkinter.CTkLabel(
                                master_frame, 
                                text=f"({cnt} tokens)", 
                                font=customtkinter.CTkFont(size=10), 
                                text_color="gray"
                            )
                            token_label.pack(anchor="e", padx=10, pady=(0, 2))
                            
                        self.app.after(0, add_token_label)
                        
                        if restart_pending:
                             self.app.after(0, lambda: self._add_system_message("--- System: Restart Required. Initiating... ---"))
                             self.app.after(2000, self.do_hard_restart_thread)

                    elif msg_type == "full_response":
                        # Non-streaming complete
                        full_text = chunk.get("text", "")
                        token_count = chunk.get("token_count", 0)
                        restart_pending = chunk.get("restart_pending", False)
                        
                        self.app.after(0, lambda t=full_text: model_bubble.configure(text=f"Orion: {t}"))
                        
                        # Add token label
                        def add_token_label_full(cnt=token_count):
                            master_frame = model_bubble.master
                            token_label = customtkinter.CTkLabel(
                                master_frame, 
                                text=f"({cnt} tokens)", 
                                font=customtkinter.CTkFont(size=10), 
                                text_color="gray"
                            )
                            token_label.pack(anchor="e", padx=10, pady=(0, 2))
                        
                        self.app.after(0, add_token_label_full)

                        if restart_pending:
                             self.app.after(0, lambda: self._add_system_message("--- System: Restart Required. Initiating... ---"))
                             self.app.after(2000, self.do_hard_restart_thread)

        except Exception as e:
            error_msg = f"Error: {e}"
            print(error_msg)
            self.app.after(0, lambda: self._add_system_message(f"--- {error_msg} ---", "error"))
            
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

    def reset_gui_state(self):
        self.is_processing = False
        self.send_button.configure(state="normal", text="Send")
        self.upload_button.configure(state="normal")

    def execute_gui_restart(self):
        self.core.execute_restart()

    def on_closing(self):
        print("--- GUI is closing. Shutting down Orion Core... ---")
        self.core.shutdown()
        self.app.destroy()

    def run(self):
        self.app.mainloop()

# --- Main execution ---
if __name__ == "__main__":
    customtkinter.set_appearance_mode("Dark")
    customtkinter.set_default_color_theme("blue")
    print("--- Initializing Orion Core for GUI ---")
    try:
        main_core = OrionCore()
        app = OrionGUI(core=main_core)
        app.run()
    except Exception as e:
        print(f"FATAL ERROR: Failed to initialize Orion Core: {e}")
        print("Please ensure your .env file and dependencies are correct.")