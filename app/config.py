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

# Sarvam AI (preferred for speech, chat and menu reading when a key is set; Gemini is the backup)
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "").strip()
SARVAM_STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v4").strip()
SARVAM_TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3").strip()
SARVAM_TTS_SPEAKER = os.getenv("SARVAM_TTS_SPEAKER", "kavya").strip()
SARVAM_LLM_MODEL = os.getenv("SARVAM_LLM_MODEL", "sarvam-105b").strip()
try:
    SARVAM_TIMEOUT = float(os.getenv("SARVAM_TIMEOUT", "15"))
except ValueError:
    SARVAM_TIMEOUT = 15.0

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

# Phase 2 switches: all OFF unless .env turns them on. With every switch off the site works as working-v1.
FEATURE_KANNADA_ALERTS = _flag("FEATURE_KANNADA_ALERTS", False)  # spoken alerts on the dashboard
FEATURE_GEMINI_TTS = _flag("FEATURE_GEMINI_TTS", True)           # allow Gemini voice if Sarvam is missing
FEATURE_VOICE_ORDER = _flag("FEATURE_VOICE_ORDER", False)        # mic button at the table
FEATURE_MENU_PHOTO = _flag("FEATURE_MENU_PHOTO", False)          # menu photo / PDF during setup
FEATURE_BUDGET_ORDER = _flag("FEATURE_BUDGET_ORDER", False)      # "Rs 800, dinner for 4" (no AI needed)
FEATURE_VOICE_ACTIONS = _flag("FEATURE_VOICE_ACTIONS", False)    # voice "bill" / "waiter"
FEATURE_TABLE_QUIZ = _flag("FEATURE_TABLE_QUIZ", False)          # live quiz between tables (no AI)
FEATURE_SALES_SUMMARY = _flag("FEATURE_SALES_SUMMARY", False)    # A1: today's sales strip + bills list
FEATURE_SPLIT_BILL = _flag("FEATURE_SPLIT_BILL", False)          # A2: split the bill, one Cashfree link per share
FEATURE_OWNER_VOICE = _flag("FEATURE_OWNER_VOICE", False)        # A3: owner asks "today's sales?" by voice
FEATURE_SUPERMARKET = _flag("FEATURE_SUPERMARKET", False)        # B0/B1: supermarket business type
FEATURE_MEAL_PLANNER = _flag("FEATURE_MEAL_PLANNER", False)      # B2: AI meal planner for supermarket customers
FEATURE_NUTRITION = _flag("FEATURE_NUTRITION", False)            # calories/protein on menu dishes (computed)
FEATURE_PHOTOS = _flag("FEATURE_PHOTOS", False)                  # real food/grocery photos (Wikimedia Commons)


def gemini_ready() -> bool:
    return bool(GEMINI_API_KEY)


def sarvam_ready() -> bool:
    return bool(SARVAM_API_KEY)


def ai_ready() -> bool:
    return sarvam_ready() or gemini_ready()


def ai_provider() -> str:
    return "sarvam" if sarvam_ready() else ("gemini" if gemini_ready() else "none")


def cashfree_ready() -> bool:
    return bool(CASHFREE_APP_ID and CASHFREE_SECRET_KEY)


def features() -> dict:
    ai = ai_ready()
    return {
        "kannada_alerts": FEATURE_KANNADA_ALERTS,
        "server_tts": FEATURE_KANNADA_ALERTS and (sarvam_ready() or (FEATURE_GEMINI_TTS and gemini_ready())),
        "gemini_tts": FEATURE_KANNADA_ALERTS and (sarvam_ready() or (FEATURE_GEMINI_TTS and gemini_ready())),
        "voice_order": FEATURE_VOICE_ORDER and ai,
        "menu_photo": FEATURE_MENU_PHOTO and ai,
        "budget_order": FEATURE_BUDGET_ORDER,
        "voice_actions": FEATURE_VOICE_ACTIONS and FEATURE_VOICE_ORDER and ai,
        "table_quiz": FEATURE_TABLE_QUIZ,
        "sales_summary": FEATURE_SALES_SUMMARY,
        "split_bill": FEATURE_SPLIT_BILL and cashfree_ready(),
        "owner_voice": FEATURE_OWNER_VOICE and ai,
        "supermarket": FEATURE_SUPERMARKET,
        "meal_planner": FEATURE_SUPERMARKET and FEATURE_MEAL_PLANNER,
        "nutrition": FEATURE_NUTRITION,
        "photos": FEATURE_PHOTOS,
        "online_payment": cashfree_ready(),
        "ai_provider": ai_provider(),
    }
