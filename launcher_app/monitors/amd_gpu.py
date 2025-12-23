
import subprocess
import shutil
import re
import threading
import time

class RadeontopMonitor:
    def __init__(self):
        self.available = shutil.which("radeontop") is not None
        self.last_stats = {
            "gpu_util": 0.0,
            "vram_util": 0.0,
            "vram_used_mb": 0.0,
            "sclk": 0.0,
            "mclk": 0.0
        }
        self.running = False
        self._thread = None

    def start_monitoring(self):
        if not self.available: return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop_monitoring(self):
        self.running = False

    def _loop(self):
        while self.running:
            self._fetch_stat()
            time.sleep(2) # Update every 2s

    def _fetch_stat(self):
        # radeontop -d - -l 1
        # Dump to stdout (-d -), limit 1 line (-l 1)
        try:
            cmd = ["radeontop", "-d", "-", "-l", "1"]
            # Requires sudo? Usually yes without permissions. 
            # If user is not in video group or lacks capability, this fails.
            # We assume user can run it (as verified in Step 35/37 it worked).
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                self._parse_output(result.stdout)
        except Exception:
            pass

    def _parse_output(self, line):
        # Example: 
        # ... gpu 15.00%, ..., vram 12.16% 990.75mb, ...
        
        # Regex for patterns
        # gpu <float>%
        gpu_match = re.search(r"gpu\s+(\d+\.\d+)%", line)
        if gpu_match:
            self.last_stats["gpu_util"] = float(gpu_match.group(1))

        # vram <float>% <float>mb
        vram_match = re.search(r"vram\s+(\d+\.\d+)%\s+(\d+\.\d+)mb", line)
        if vram_match:
            self.last_stats["vram_util"] = float(vram_match.group(1))
            self.last_stats["vram_used_mb"] = float(vram_match.group(2))

    def get_stats(self):
        if not self.available:
            return {"error": "radeontop not found"}
        return self.last_stats
