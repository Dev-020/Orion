import customtkinter
import json
from typing import Dict, Any, List, Optional, Callable
from . import constants as C

def add_system_message(parent_frame, text: str, tag: str = "system", on_resize: Optional[Callable] = None):
    """Adds a system message bubble to the parent frame."""
    color = C.TEXT_GRAY if tag == "system" else C.TEXT_RED
    bubble = customtkinter.CTkLabel(
        parent_frame,
        text=text,
        text_color=color,
        font=C.get_font_small_italic(), 
        anchor="w",
        justify="left"
    )
    bubble.pack(fill="x", pady=(5, 5), padx=10)
    # Return bubble in case caller wants to track it
    return bubble

def add_exchange_widget(
    parent_frame, 
    exchange: Dict[str, Any], 
    index: int, 
    on_delete_callback: Callable[[int], None]
):
    """
    Adds a full exchange (User + Model) widget to the parent frame.
    """
    try:
        master_frame = customtkinter.CTkFrame(parent_frame, fg_color=C.COLOR_PANEL_BG)
        master_frame.pack(fill="x", pady=(5, 5), padx=5)

        labels_to_wrap = []

        # --- User Content ---
        user_content = exchange.get("user_content")
        if user_content:
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
                text_color=C.TEXT_CYAN,
                anchor="w",
                justify="left",
                font=C.get_font_bubble()
            )
            user_bubble.pack(fill="x", padx=10, pady=(5, 2))
            labels_to_wrap.append(user_bubble)
            
            if file_text:
                file_label = customtkinter.CTkLabel(
                    master_frame,
                    text=file_text.strip(),
                    text_color=C.TEXT_CYAN,
                    font=C.get_font_small_italic(),
                    anchor="w",
                    justify="left"
                )
                file_label.pack(fill="x", padx=15, pady=(0, 5))

        # --- Tool Calls ---
        tool_calls = exchange.get("tool_calls", [])
        if tool_calls:
            tool_text = f"Orion: [Executed {len(tool_calls)} Tool Call(s)]"
            tool_bubble = customtkinter.CTkLabel(
                master_frame,
                text=tool_text,
                text_color=C.TEXT_LIGHT_GRAY,
                font=C.get_font_small_italic(),
                anchor="w",
                justify="left"
            )
            tool_bubble.pack(fill="x", padx=10, pady=(0, 2))

        # --- Model Content ---
        model_content = exchange.get("model_content")
        if model_content and model_content.parts:
            model_text = "".join(part.text for part in model_content.parts if part.text)
            
            model_bubble = customtkinter.CTkLabel(
                master_frame,
                text=f"Orion: {model_text.strip()}",
                anchor="w",
                justify="left",
                font=C.get_font_bubble()
            )
            model_bubble.pack(fill="x", padx=10, pady=(2, 0))
            labels_to_wrap.append(model_bubble)

            # Token Count
            token_count = exchange.get("token_count", 0)
            if token_count > 0:
                token_label = customtkinter.CTkLabel(
                    master_frame,
                    text=f"(`Tokens: {token_count}`)",
                    text_color=C.TEXT_GRAY,
                    font=C.get_font_small_italic(10),
                    anchor="w",
                    justify="left"
                )
                token_label.pack(fill="x", padx=10, pady=(0, 5))

        # --- Delete Button ---
        delete_button = customtkinter.CTkButton(
            master_frame,
            text="X",
            width=25,
            height=25,
            fg_color=C.COLOR_BUTTON_GRAY,
            hover_color=C.COLOR_BUTTON_RED,
            command=lambda i=index: on_delete_callback(i)
        )
        delete_button.place(relx=1.0, rely=0, x=-5, y=5, anchor="ne")
        
        # --- Resize Binding ---
        if labels_to_wrap:
            master_frame.bind(
                "<Configure>", 
                lambda event, labels=labels_to_wrap: update_bubble_wraps(event, labels)
            )

    except Exception as e:
        print(f"ERROR: Failed to draw chat bubble for index {index}: {e}")
        add_system_message(parent_frame, f"--- Error rendering exchange {index} ---", "error")

def update_bubble_wraps(event, labels: List[customtkinter.CTkLabel]):
    """Dynamic text wrapping based on frame width."""
    new_wraplength = event.width - 50 
    if new_wraplength < 10:
        new_wraplength = 10
    for label in labels:
        label.configure(wraplength=new_wraplength)

def add_user_message_bubble(parent_frame, current_user_name, text, file_handles, scroll_callback=None):
    """Adds a temporary user bubble for immediate feedback."""
    master_frame = customtkinter.CTkFrame(parent_frame, fg_color=C.COLOR_PANEL_BG)
    master_frame.pack(fill="x", pady=(5, 5), padx=5)
    
    user_bubble = customtkinter.CTkLabel(
        master_frame,
        text=f"{current_user_name}: {text}",
        text_color=C.TEXT_CYAN,
        anchor="w",
        justify="left",
        font=C.get_font_bubble()
    )
    user_bubble.pack(fill="x", padx=10, pady=(5, 2))
    
    # Wrap
    user_bubble.configure(wraplength=400)
    master_frame.bind(
        "<Configure>", 
        lambda event, labels=[user_bubble]: update_bubble_wraps(event, labels)
    )
    
    if file_handles:
        file_text = "\n".join([f"[File: {f.display_name}]" for f in file_handles])
        file_label = customtkinter.CTkLabel(
            master_frame,
            text=file_text,
            text_color=C.TEXT_CYAN,
            font=C.get_font_small_italic(),
            anchor="w",
            justify="left"
        )
        file_label.pack(fill="x", padx=15, pady=(0, 5))
        
    if scroll_callback:
        scroll_callback()
    
    return master_frame

def add_model_message_bubble(parent_frame, initial_text, scroll_callback=None):
    """Adds a temporary/streaming model bubble."""
    master_frame = customtkinter.CTkFrame(parent_frame, fg_color=C.COLOR_PANEL_BG)
    master_frame.pack(fill="x", pady=(5, 5), padx=5)
    
    model_bubble = customtkinter.CTkLabel(
        master_frame,
        text=initial_text,
        anchor="w",
        justify="left",
        font=C.get_font_bubble()
    )
    model_bubble.pack(fill="x", padx=10, pady=(2, 5))
    
    model_bubble.configure(wraplength=400) 
    
    master_frame.bind(
        "<Configure>", 
        lambda event, labels=[model_bubble]: update_bubble_wraps(event, labels)
    )
    
    if scroll_callback:
        scroll_callback()
        
    return model_bubble
