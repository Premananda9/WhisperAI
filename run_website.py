import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.request import urlopen

ROOT_DIR = Path(__file__).resolve().parent
APP_FILE = ROOT_DIR / "app.py"
STREAMLIT_EXE = ROOT_DIR / ".venv" / "Scripts" / "streamlit.exe"
URL = "http://localhost:8501"


def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


def _wait_for_http(url: str, timeout_seconds: float = 20.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=0.5):  # nosec B310 (local URL only)
                return True
        except Exception:
            time.sleep(0.3)
    return False


def main() -> int:
    if not APP_FILE.exists():
        print(f"app.py not found at: {APP_FILE}")
        return 1

    streamlit_cmd = [str(STREAMLIT_EXE), "run", str(APP_FILE), "--server.headless=false"]

    if not STREAMLIT_EXE.exists():
        streamlit_cmd = [sys.executable, "-m", "streamlit", "run", str(APP_FILE), "--server.headless=false"]

    if _is_port_open("127.0.0.1", 8501):
        print("Streamlit is already running. Opening browser...")
        webbrowser.open(URL)
        return 0

    print("Starting website...")
    process = subprocess.Popen(streamlit_cmd, cwd=str(ROOT_DIR))

    if _wait_for_http(URL):
        print(f"Opening {URL}")
        webbrowser.open(URL)
    else:
        print("Website started, but browser auto-open timed out. You can open: http://localhost:8501")

    return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
