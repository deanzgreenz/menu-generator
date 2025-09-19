# run.py
import os, sys, socket, threading, time, webbrowser
from pathlib import Path

SINGLETON_PORT = 54123
IDLE_TIMEOUT_SECS = 120   # quit ~2 minutes after last tab closes

BASE_PATH = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
os.chdir(BASE_PATH)

from app import app, get_last_request, get_open_client_count

def _is_port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False

def _serve():
    app.run(host="127.0.0.1", port=SINGLETON_PORT, debug=False, use_reloader=False)

def main():
    if _is_port_open(SINGLETON_PORT):
        webbrowser.open(f"http://127.0.0.1:{SINGLETON_PORT}/")
        return

    t = threading.Thread(target=_serve, daemon=True); t.start()

    for _ in range(60):
        if _is_port_open(SINGLETON_PORT):
            webbrowser.open(f"http://127.0.0.1:{SINGLETON_PORT}/")
            break
        time.sleep(0.1)

    try:
        while t.is_alive():
            open_tabs = get_open_client_count()
            last_ts = get_last_request()
            if open_tabs == 0 and (time.time() - last_ts) > IDLE_TIMEOUT_SECS:
                os._exit(0)  # graceful enough; ends Flask
            time.sleep(2)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
