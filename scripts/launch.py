"""Launch Flask server + open browser."""
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aivoice_studio.server.api import app
import threading

def run_flask():
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)

t = threading.Thread(target=run_flask, daemon=True)
t.start()

print("Server starting...", end="", flush=True)
import urllib.request
for _ in range(15):
    try:
        urllib.request.urlopen("http://127.0.0.1:5000", timeout=1)
        print(" ready!")
        break
    except Exception:
        print(".", end="", flush=True)
        time.sleep(1)
else:
    print(" FAIL")
    sys.exit(1)

webbrowser.open("http://127.0.0.1:5000")
print("Browser opened. Press Ctrl+C to stop.")
try:
    while t.is_alive():
        time.sleep(1)
except KeyboardInterrupt:
    print("Stopped.")
