import customtkinter
from . import constants as C

def build_prompt_tab(gui_app, tab_frame):
    """
    Builds the Prompt tab.
    Sets gui_app properties: mode_label, mode_toggle_button, prompt_box, send_button.
    """
    prompt_inner_frame = customtkinter.CTkFrame(tab_frame, fg_color=C.COLOR_TRANSPARENT)
    prompt_inner_frame.pack(fill="both", expand=True, padx=5, pady=5)
    prompt_inner_frame.grid_rowconfigure(1, weight=1)
    prompt_inner_frame.grid_columnconfigure(0, weight=1)
    prompt_inner_frame.grid_columnconfigure(1, weight=0)
    
    # Mode indicator (row 0)
    mode_frame = customtkinter.CTkFrame(prompt_inner_frame, fg_color=C.COLOR_TRANSPARENT)
    mode_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
    
    gui_app.mode_label = customtkinter.CTkLabel(
        mode_frame,
        text="💰 Context Caching Mode (Tools Disabled)",
        font=C.get_font_bold(12),
        text_color=C.TEXT_GREEN, 
        anchor="w"
    )
    gui_app.mode_label.pack(side="left", fill="x", expand=True)
    
    gui_app.mode_toggle_button = customtkinter.CTkButton(
        mode_frame,
        text="Switch to 🛠️ Tools",
        command=gui_app._on_toggle_mode,
        width=140,
        height=28,
        fg_color=C.COLOR_BUTTON_GRAY,
        hover_color=C.COLOR_BUTTON_GRAY_HOVER
    )
    gui_app.mode_toggle_button.pack(side="right")
    
    # Prompt box (row 1)
    gui_app.prompt_box = customtkinter.CTkTextbox(
        prompt_inner_frame,
        wrap="word",
        font=C.get_font_normal()
    )
    gui_app.prompt_box.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
    
    gui_app.send_button = customtkinter.CTkButton(
        prompt_inner_frame, 
        text="Send", 
        command=gui_app.on_send_pressed,
        width=60,
    )
    gui_app.send_button.grid(row=1, column=1, sticky="ns")

def build_files_tab(gui_app, tab_frame):
    """
    Builds the Files tab.
    Sets gui_app properties: staging_frame.
    """
    gui_app.staging_frame = customtkinter.CTkScrollableFrame(
        tab_frame,
        label_text="Staged Files (Ready to Send)"
    )
    gui_app.staging_frame.pack(fill="both", expand=True, pady=5, padx=5)

def build_sessions_tab(gui_app, tab_frame):
    """
    Builds the Sessions tab.
    Sets gui_app properties: session_menu, current_user_label, user_menu, new_user_name_entry, new_user_id_entry.
    """
    # --- 1. Switch Session Frame ---
    switch_session_frame = customtkinter.CTkFrame(tab_frame, fg_color=C.COLOR_TRANSPARENT)
    switch_session_frame.pack(fill="x", padx=10, pady=10)

    switch_label = customtkinter.CTkLabel(
        switch_session_frame,
        text="Active Session",
        font=C.get_font_bold()
    )
    switch_label.pack(anchor="w")
    
    # Dropdown and Refresh Button
    dropdown_frame = customtkinter.CTkFrame(switch_session_frame, fg_color=C.COLOR_TRANSPARENT)
    dropdown_frame.pack(fill="x", pady=(5, 5))

    gui_app.session_menu = customtkinter.CTkOptionMenu(
        dropdown_frame,
        variable=gui_app.session_menu_var,
        command=gui_app._on_switch_session,
        values=["local_gui_user"] # Placeholder
    )
    gui_app.session_menu.pack(side="left", fill="x", expand=True, padx=(0, 10))

    refresh_button = customtkinter.CTkButton(
        dropdown_frame,
        text="Refresh List",
        command=gui_app._on_refresh_sessions_list,
        width=100
    )
    refresh_button.pack(side="right")
    
    # --- Create New Session Button ---
    new_session_button = customtkinter.CTkButton(
        switch_session_frame,
        text="Create New Session",
        command=gui_app._on_create_new_session
    )
    new_session_button.pack(fill="x", pady=(5, 10))
    
    # --- Visual separator ---
    separator = customtkinter.CTkFrame(tab_frame, height=2, fg_color=C.COLOR_BUTTON_GRAY)
    separator.pack(fill="x", padx=10, pady=(10, 5))

    # --- 2. User Management Frame ---
    user_frame = customtkinter.CTkFrame(tab_frame, fg_color=C.COLOR_TRANSPARENT)
    user_frame.pack(fill="x", padx=10, pady=(10, 0))

    gui_app.current_user_label = customtkinter.CTkLabel(
        user_frame,
        text=f"Active User (Current: {gui_app.current_user_name})",
        font=C.get_font_bold()
    )
    gui_app.current_user_label.pack(anchor="w")

    # --- Switch User Dropdown ---
    switch_user_frame = customtkinter.CTkFrame(user_frame, fg_color=C.COLOR_TRANSPARENT)
    switch_user_frame.pack(fill="x", pady=(5,10))
    
    gui_app.user_menu = customtkinter.CTkOptionMenu(
        switch_user_frame,
        variable=gui_app.current_user_var,
        values=[f"{name} ({uid})" for uid, name in gui_app.user_list.items()],
        command=gui_app._on_switch_user
    )
    gui_app.user_menu.pack(fill="x", expand=True)

    # --- Add New User ---
    add_user_frame = customtkinter.CTkFrame(user_frame, fg_color=C.COLOR_TRANSPARENT)
    add_user_frame.pack(fill="x", pady=(5,5))
    
    gui_app.new_user_name_entry = customtkinter.CTkEntry(
        add_user_frame,
        placeholder_text="New User Name"
    )
    gui_app.new_user_name_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
    
    gui_app.new_user_id_entry = customtkinter.CTkEntry(
        add_user_frame,
        placeholder_text="New User ID"
    )
    gui_app.new_user_id_entry.pack(side="left", fill="x", expand=True)

    add_user_button = customtkinter.CTkButton(
        user_frame,
        text="Add/Update User",
        command=gui_app._on_add_user
    )
    add_user_button.pack(fill="x", pady=(5, 5))

    # Initial population
    gui_app._on_refresh_sessions_list()

def build_settings_tab(gui_app, tab_frame):
    """
    Builds the Settings tab.
    Sets gui_app properties: history_index_entry, history_count_entry.
    """
    # --- History Management Frame ---
    history_frame = customtkinter.CTkFrame(tab_frame, fg_color=C.COLOR_TRANSPARENT)
    history_frame.pack(fill="x", padx=10, pady=10)

    history_label = customtkinter.CTkLabel(
        history_frame,
        text="Session History Management (Current Session)",
        font=C.get_font_bold()
    )
    history_label.pack(anchor="w")
    
    input_frame = customtkinter.CTkFrame(history_frame, fg_color=C.COLOR_TRANSPARENT)
    input_frame.pack(fill="x", pady=(5,5))
    
    gui_app.history_index_entry = customtkinter.CTkEntry(
        input_frame,
        placeholder_text="Start Index (e.g., 0)"
    )
    gui_app.history_index_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
    
    gui_app.history_count_entry = customtkinter.CTkEntry(
        input_frame,
        placeholder_text="Count (e.g., 5 or 999)"
    )
    gui_app.history_count_entry.pack(side="left", fill="x", expand=True)

    execute_button = customtkinter.CTkButton(
        history_frame,
        text="Execute History Truncation",
        command=gui_app.on_truncate_history_pressed
    )
    execute_button.pack(fill="x", pady=(5, 5))
    
    # --- System Control Frame ---
    shutdown_frame = customtkinter.CTkFrame(tab_frame, fg_color=C.COLOR_TRANSPARENT)
    shutdown_frame.pack(fill="x", padx=10, pady=20)
    
    shutdown_label = customtkinter.CTkLabel(
        shutdown_frame,
        text="System Control (Global)",
        font=C.get_font_bold()
    )
    shutdown_label.pack(anchor="w")
    
    control_frame = customtkinter.CTkFrame(shutdown_frame, fg_color=C.COLOR_TRANSPARENT)
    control_frame.pack(fill="x", pady=(5, 5))
    
    shutdown_options = customtkinter.CTkOptionMenu(
        control_frame,
        values=["Soft", "Hard", "Full"],
        variable=gui_app.shutdown_mode_var
    )
    shutdown_options.pack(side="left", padx=(0, 10))
    
    shutdown_button = customtkinter.CTkButton(
        control_frame,
        text="Execute Action",
        command=gui_app.on_shutdown_pressed,
        fg_color=C.COLOR_BUTTON_RED,
        hover_color=C.COLOR_BUTTON_RED_HOVER
    )
    shutdown_button.pack(side="left", fill="x", expand=True)

    # --- Generation Settings Frame ---
    gen_settings_frame = customtkinter.CTkFrame(tab_frame, fg_color=C.COLOR_TRANSPARENT)
    gen_settings_frame.pack(fill="x", padx=10, pady=20)
    
    gen_label = customtkinter.CTkLabel(
        gen_settings_frame,
        text="Generation Settings",
        font=C.get_font_bold()
    )
    gen_label.pack(anchor="w")
    
    stream_switch = customtkinter.CTkSwitch(
        gen_settings_frame,
        text="Enable Streaming Response",
        variable=gui_app.use_streaming_var
    )
    stream_switch.pack(anchor="w", pady=(5, 0))
