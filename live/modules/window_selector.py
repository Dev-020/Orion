"""
Window Selector Module for Selective Window Capture
Provides functionality to enumerate and capture specific windows on Windows OS.
"""

try:
    import ctypes
    import win32gui
    import win32ui
    import win32con
    import win32process
    WINDOWS_AVAILABLE = True
except ImportError:
    WINDOWS_AVAILABLE = False

from PIL import Image
import numpy as np
from typing import List, Dict, Optional
import traceback

# Import logging
# Import logging
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

try:
    from live.live_ui import system_log
except ImportError:
    class DummyLog:
        @staticmethod
        def info(msg, category=""):
            print(f"[{category}] {msg}")
    system_log = DummyLog()


class WindowsWindowSelector:
    """Manages window enumeration and selective window capture (Windows Only)."""
    
    def __init__(self):
        self.windows = []
        self.selected_hwnd = None
        self.selected_title = None
        
        # Make process DPI aware for accurate window capture
        if WINDOWS_AVAILABLE:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()  # Fallback for older Windows
                except Exception as e:
                    system_log.info(f"Could not set DPI awareness: {e}", category="WINDOW")
    
    def enumerate_windows(self) -> List[Dict]:
        """
        List all visible windows with titles and process names.
        
        Returns:
            List of dictionaries containing window info (hwnd, title, executable)
        """
        if not WINDOWS_AVAILABLE:
            return []

        windows = []
        
        def callback(hwnd, extra):
            try:
                # Only include visible windows
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                
                # Get window title
                title = win32gui.GetWindowText(hwnd)
                
                # Filter out windows without titles and certain system windows
                if not title or len(title) == 0:
                    return True
                
                # Skip Windows shell windows
                if title in ["", "Program Manager", "Microsoft Text Input Application"]:
                    return True
                
                # Get process name
                executable = self._get_process_name(hwnd)
                
                # Get window rect to check size (skip very small windows)
                try:
                    rect = win32gui.GetWindowRect(hwnd)
                    width = rect[2] - rect[0]
                    height = rect[3] - rect[1]
                    
                    # Skip tiny windows (likely not meant for capture)
                    if width < 100 or height < 100:
                        return True
                except Exception:
                    return True
                
                windows.append({
                    'hwnd': hwnd,
                    'title': title,
                    'executable': executable,
                    'width': width,
                    'height': height
                })
            except Exception as e:
                # Continue enumeration even if one window fails
                pass
            
            return True
        
        # Enumerate all top-level windows
        win32gui.EnumWindows(callback, None)
        
        # Sort by title for easier selection
        windows.sort(key=lambda w: w['title'].lower())
        
        self.windows = windows
        return windows
    
    def _get_process_name(self, hwnd) -> str:
        """Get the executable name for a window."""
        try:
            # Get process ID from window handle
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            
            # Try to get process name using psutil (if available)
            try:
                import psutil
                process = psutil.Process(pid)
                return process.name()
            except ImportError:
                # Fallback: just return the PID if psutil not available
                return f"PID:{pid}"
            except Exception:
                return "Unknown"
        except Exception:
            return "Unknown"
    
    def select_window(self, hwnd):
        """
        Select a window for capture by its handle.
        
        Args:
            hwnd: Window handle (HWND)
        """
        self.selected_hwnd = hwnd
        try:
            self.selected_title = win32gui.GetWindowText(hwnd)
            system_log.info(f"Selected window: {self.selected_title}", category="WINDOW")
        except Exception as e:
            system_log.info(f"Error getting window title: {e}", category="WINDOW")
            self.selected_title = "Unknown"
    
    def select_window_by_title(self, title_substring: str) -> bool:
        """
        Select a window by searching for a title substring.
        
        Args:
            title_substring: Substring to search for in window titles
            
        Returns:
            True if window was found and selected, False otherwise
        """
        if not self.windows:
            self.enumerate_windows()
        
        for window in self.windows:
            if title_substring.lower() in window['title'].lower():
                self.select_window(window['hwnd'])
                return True
        
        return False
    
    def capture_window(self) -> Optional[np.ndarray]:
        """
        Capture screenshot of the selected window.
        
        Returns:
            numpy array of the window screenshot (RGB), or None if capture fails
        """
        if not self.selected_hwnd:
            system_log.info("No window selected for capture", category="WINDOW")
            return None
        
        if not WINDOWS_AVAILABLE:
            return None

        try:
            # Check if window still exists and is visible
            if not win32gui.IsWindow(self.selected_hwnd):
                system_log.info("Selected window no longer exists", category="WINDOW")
                return None
            
            if not win32gui.IsWindowVisible(self.selected_hwnd):
                system_log.info("Selected window is not visible (may be minimized)", category="WINDOW")
                return None
            
            # Get window dimensions
            left, top, right, bottom = win32gui.GetWindowRect(self.selected_hwnd)
            width = right - left
            height = bottom - top
            
            # Validate dimensions
            if width <= 0 or height <= 0:
                system_log.info(f"Invalid window dimensions: {width}x{height}", category="WINDOW")
                return None
            
            # Get window DC
            hwndDC = win32gui.GetWindowDC(self.selected_hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            
            # Create bitmap
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)
            
            # Use PrintWindow API for accurate window capture (works even if window is partially occluded)
            # PW_RENDERFULLCONTENT (0x00000002) = Capture full window content
            result = ctypes.windll.user32.PrintWindow(self.selected_hwnd, saveDC.GetSafeHdc(), 2)
            
            if result == 0:
                # PrintWindow failed, fall back to BitBlt
                saveDC.BitBlt((0, 0), (width, height), mfcDC, (0, 0), win32con.SRCCOPY)
            
            # Convert to PIL Image
            bmpinfo = saveBitMap.GetInfo()
            bmpstr = saveBitMap.GetBitmapBits(True)
            
            img = Image.frombuffer(
                'RGB',
                (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                bmpstr, 'raw', 'BGRX', 0, 1
            )
            
            # Cleanup Windows GDI objects
            win32gui.DeleteObject(saveBitMap.GetHandle())
            saveDC.DeleteDC()
            mfcDC.DeleteDC()
            win32gui.ReleaseDC(self.selected_hwnd, hwndDC)
            
            # Convert PIL Image to numpy array
            return np.array(img)
            
        except Exception as e:
            system_log.info(f"Error capturing window: {e}", category="WINDOW")
            if __debug__:
                traceback.print_exc()
            return None
    
    def is_window_valid(self) -> bool:
        """
        Check if the currently selected window is still valid.
        
        Returns:
            True if window exists and is visible, False otherwise
        """
        if not self.selected_hwnd:
            return False
        
        if not WINDOWS_AVAILABLE:
            return False

        try:
            return win32gui.IsWindow(self.selected_hwnd) and win32gui.IsWindowVisible(self.selected_hwnd)
        except Exception:
            return False
    
    def get_selected_window_info(self) -> Optional[Dict]:
        """
        Get information about the currently selected window.
        
        Returns:
            Dictionary with window info, or None if no window selected
        """
        if not self.selected_hwnd:
            return None
        
        if not WINDOWS_AVAILABLE:
            return None

        try:
            left, top, right, bottom = win32gui.GetWindowRect(self.selected_hwnd)
            return {
                'hwnd': self.selected_hwnd,
                'title': self.selected_title or win32gui.GetWindowText(self.selected_hwnd),
                'width': right - left,
                'height': bottom - top,
                'position': (left, top),
                'valid': self.is_window_valid()
            }
        except Exception as e:
            system_log.info(f"Error getting window info: {e}", category="WINDOW")
            return None


class DummyWindowSelector:
    """Dummy implementation for non-Windows platforms."""
    def __init__(self):
        system_log.info("Window selection disabled (Linux/Non-Windows).", category="WINDOW")
    
    def enumerate_windows(self) -> List[Dict]:
        return []
    
    def select_window(self, hwnd):
        pass
    
    def select_window_by_title(self, title_substring: str) -> bool:
        return False
    
    def capture_window(self) -> Optional[np.ndarray]:
        return None
    
    def is_window_valid(self) -> bool:
        return False
    
    def get_selected_window_info(self) -> Optional[Dict]:
        return None


# Conditional alias
if WINDOWS_AVAILABLE:
    WindowSelector = WindowsWindowSelector
else:
    WindowSelector = DummyWindowSelector
