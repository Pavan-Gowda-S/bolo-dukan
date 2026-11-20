"""Start Bolo Dukaan.   python run.py   [--port 8000] [--no-browser]"""
import argparse
import os
import socket
import sys
import threading
import webbrowser

for _stream in (sys.stdout, sys.stderr):  # keep Kannada/Hindi text from crashing a Windows console
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass

if sys.version_info < (3, 10):
    sys.exit("Bolo Dukaan needs Python 3.10 or newer. Get it from https://www.python.org/downloads/")

try:
    import qrcode  # noqa: F401
except ImportError:
    sys.exit("Missing the 'qrcode' package. Run:  python -m pip install -r requirements.txt   (or use start.bat)")

from app import config
from app.db import init_db
from app.main import app
from app.web import serve


def lan_ip() -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    init_db()
    f = config.features()
    ip = lan_ip()
    print()
    print("  ==============================================")
    print("   Bolo Dukaan for Restaurants is running")
    print("  ==============================================")
    print(f"   This PC:        http://localhost:{args.port}")
    if ip:
        print(f"   Same Wi-Fi:     http://{ip}:{args.port}")
    print(f"   Public (ngrok): {config.PUBLIC_URL or 'auto-detected when ngrok runs'}")
    print(f"   Sarvam AI:      {'ON (main AI)' if config.sarvam_ready() else 'OFF - add SARVAM_API_KEY to .env'}")
    print(f"   Gemini:         {('ON (' + config.GEMINI_MODEL + ')' + (' - backup' if config.sarvam_ready() else '')) if config.gemini_ready() else 'OFF'}")
    print(f"   Cashfree:       {'ON (' + config.CASHFREE_ENV + ')' if config.cashfree_ready() else 'OFF - add Cashfree keys to .env'}")
    print(f"   Features on:    {', '.join(k for k, v in f.items() if v is True) or 'none (see .env)'}")
    print("   Press Ctrl+C to stop.")
    print()

    try:
        if not args.no_browser:
            threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{args.port}")).start()
        serve(app, args.host, args.port)
    except OSError as e:
        if getattr(e, "winerror", None) == 10048 or getattr(e, "errno", None) in (98, 48):
            sys.exit(f"\n  Port {args.port} is already in use. Close the other server window, "
                     f"or run:  python run.py --port {args.port + 1}\n")
        raise


if __name__ == "__main__":
    main()
