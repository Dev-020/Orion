"""
Window selection UI helper for Gemini Live API
Allows users to select specific windows for selective video capture
"""

def select_window_for_capture(orchestrator):
    """
    Interactive window selection UI for selective video capture.
    
    Args:
        orchestrator: LiveSessionOrchestrator instance with video pipeline
    """
    import sys
    
    if orchestrator.video_mode != "window":
        # Not in window mode, skip selection
        return
    
    print("\n" + "="*60)
    print("  WINDOW SELECTION - Choose what to stream to Orion")
    print("="*60)
    
    # Get list of windows
    windows = orchestrator.video_pipeline.list_windows()
    
    if not windows:
        print("\n❌ No windows found. Falling back to screen capture.")
        from live.live_ui import system_log
        system_log.info("No windows available for selection, defaulting to screen", category="VIDEO")
        orchestrator.video_pipeline.mode = "screen"
        return
    
    print(f"\n📋 Available Windows ({len(windows)} found):\n")
    
    for i, win in enumerate(windows):
        # Format size for display
        size_str = f"{win['width']}x{win['height']}"
        print(f"  {i+1:2d}. {win['title'][:50]:50s} ({win['executable']}) [{size_str}]")
    
    print(f"\n  {len(windows)+1:2d}. 🖥️  Full Screen (capture entire display)")
    print(f"   0. ❌ Cancel and exit\n")
    
    while True:
        try:
            choice = input("👉 Select window number: ").strip()
            
            if not choice:
                print("❌ Please enter a number.")
                continue
            
            idx = int(choice)
            
            if idx == 0:
                print("\n❌ Cancelled. Exiting...")
                sys.exit(0)
            elif idx == len(windows) + 1:
                # User chose full screen
                print("\n✅ Selected: Full Screen Capture")
                from live.live_ui import system_log
                system_log.info("User selected full screen capture", category="VIDEO")
                orchestrator.video_pipeline.mode = "screen"
                break
            elif 1 <= idx <= len(windows):
                # User chose a specific window
                selected = windows[idx - 1]
                success = orchestrator.video_pipeline.select_window_by_hwnd(selected['hwnd'])
                
                if success:
                    print(f"\n✅ Selected: {selected['title']}")
                    from live_ui import system_log
                    system_log.info(f"User selected window: {selected['title']}", category="VIDEO")
                    break
                else:
                    print(f"\n❌ Failed to select window. Please try again.")
            else:
                print(f"❌ Invalid choice. Please enter a number between 0 and {len(windows)+1}.")
        except ValueError:
            print("❌ Invalid input. Please enter a number.")
        except KeyboardInterrupt:
            print("\n\n❌ Cancelled. Exiting...")
            sys.exit(0)
    
    print("="*60 + "\n")
