"""Settings, read once from .env at startup. Change .env and restart to apply."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env(path: Path) -> None:
    """Tiny .env reader (KEY=value lines, # comments). Real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()
        os.environ.setdefault(key, value)


_load_env(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "bolo_dukaan.db"


def _flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _secret_key() -> str:
    env = os.getenv("SECRET_KEY", "").strip()
    if env:
        return env
    key_file = DATA_DIR / "secret.key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    key_file.write_text(key, encoding="utf-8")
    return key


SECRET_KEY = _secret_key()

# Public HTTPS address (your ngrok link). Leave empty to auto-detect a running ngrok.
PUBLIC_URL = os.getenv("PUBLIC_URL", "").strip().rstrip("/")

# Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts").strip()
GEMINI_TTS_VOICE = os.getenv("GEMINI_TTS_VOICE", "Kore").strip()

# Google sign-in (OAuth "Web application" client ID from Google Cloud Console)
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()

# Cashfree
CASHFREE_APP_ID = os.getenv("CASHFREE_APP_ID", "").strip()
CASHFREE_SECRET_KEY = os.getenv("CASHFREE_SECRET_KEY", "").strip()
CASHFREE_ENV = os.getenv("CASHFREE_ENV", "sandbox").strip().lower()
CASHFREE_BASE = (
    "https://api.cashfree.com/pg" if CASHFREE_ENV == "production" else "https://sandbox.cashfree.com/pg"
)
CASHFREE_API_VERSION = "2023-08-01"

# Phase 2 switches. Each one needs GEMINI_API_KEY too.
FEATURE_KANNADA_ALERTS = _flag("FEATURE_KANNADA_ALERTS", True)   # spoken alerts on the dashboard
FEATURE_GEMINI_TTS = _flag("FEATURE_GEMINI_TTS", True)           # use Gemini voice (else browser voice)
FEATURE_VOICE_ORDER = _flag("FEATURE_VOICE_ORDER", True)         # mic button at the table
FEATURE_MENU_PHOTO = _flag("FEATURE_MENU_PHOTO", True)           # menu photo during setup
FEATURE_BUDGET_ORDER = _flag("FEATURE_BUDGET_ORDER", True)       # "Rs 800, dinner for 4"
FEATURE_VOICE_ACTIONS = _flag("FEATURE_VOICE_ACTIONS", True)     # voice "bill" / "waiter"


def gemini_ready() -> bool:
    return bool(GEMINI_API_KEY)


def cashfree_ready() -> bool:
    return bool(CASHFREE_APP_ID and CASHFREE_SECRET_KEY)


def features() -> dict:
    g = gemini_ready()
    return {
        "kannada_alerts": FEATURE_KANNADA_ALERTS,
        "gemini_tts": FEATURE_KANNADA_ALERTS and FEATURE_GEMINI_TTS and g,
        "voice_order": FEATURE_VOICE_ORDER and g,
        "menu_photo": FEATURE_MENU_PHOTO and g,
        "budget_order": FEATURE_BUDGET_ORDER and g,
        "voice_actions": FEATURE_VOICE_ACTIONS and g,
        "online_payment": cashfree_ready(),
    }
