import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(DATA_DIR / "finance.db")))

# Optional: comma-separated Telegram user IDs allowed to use the bot.
# Empty means anyone can use it.
_ALLOWED = os.getenv("ALLOWED_USER_IDS", "").strip()
ALLOWED_USER_IDS: set[int] = {
    int(x.strip()) for x in _ALLOWED.split(",") if x.strip().isdigit()
}

DEFAULT_ACCOUNT_NAME = os.getenv("DEFAULT_ACCOUNT_NAME", "حساب اصلی")

# Google Gemini — used for smart receipt reading (vision + text)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
