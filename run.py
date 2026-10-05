import os
import sys
import time
import webbrowser
import threading
import uvicorn
from backend.utils import is_admin

def open_browser():
    time.sleep(1.2)
    url = "http://127.0.0.1:8765"
    print(f"\n[NetPulse Pro] Launching interactive interface at {url}")
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"Could not open browser automatically: {e}")

def main():
    admin = is_admin()
    banner = f"""
========================================================================
   _   _      _   ____        _              ____             
  | \\ | | ___| |_|  _ \\ _   _| |___  ___    |  _ \\ _ __ ___  
  |  \\| |/ _ \\ __| |_) | | | | / __|/ _ \\   | |_) | '__/ _ \\ 
  | |\\  |  __/ |_|  __/| |_| | \\__ \\  __/   |  __/| | | (_) |
  |_| \\_|\\___|\\__|_|    \\__,_|_|___/\\___|___|_|   |_|  \\___/ 
                                       |_____|                
  Wi-Fi Network Diagnostics & Autonomous Local Optimization
========================================================================
  * Running Mode      : {'ADMINISTRATOR (Full Hardware Control)' if admin else 'STANDARD USER (UAC prompted for hardware changes)'}
  * Web Dashboard     : http://127.0.0.1:8765
  * Local Diagnostics : Active (Zero ISP contact required)
========================================================================
"""
    print(banner)

    # Launch browser in separate thread
    threading.Thread(target=open_browser, daemon=True).start()

    host = os.environ.get("NETPULSE_HOST", "0.0.0.0")
    port = int(os.environ.get("NETPULSE_PORT", "8765"))

    # Start FastAPI server
    uvicorn.run(
        "backend.server:app",
        host=host,
        port=port,
        log_level="info",
        access_log=False
    )

if __name__ == "__main__":
    main()
