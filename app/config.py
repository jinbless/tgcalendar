import os
from pathlib import Path
from zoneinfo import ZoneInfo

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TOKENS_DIR = DATA_DIR / "tokens"
CREDENTIALS_FILE = DATA_DIR / "credentials.json"

# Ensure tokens directory exists
TOKENS_DIR.mkdir(parents=True, exist_ok=True)

# Telegram
TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]

# OpenAI
OPENAI_API_KEY: str = os.environ["OPENAI_API_KEY"]

# Google OAuth
GOOGLE_CLIENT_ID: str = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET: str = os.environ["GOOGLE_CLIENT_SECRET"]
GOOGLE_REDIRECT_URI: str = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost")

# Shared Calendar
SHARED_CALENDAR_ID: str = os.environ["SHARED_CALENDAR_ID"]

# Timezone
TIMEZONE_STR: str = os.environ.get("TIMEZONE", "Asia/Seoul")
TIMEZONE = ZoneInfo(TIMEZONE_STR)

# Scheduler
DAILY_REPORT_TIME: str = os.environ.get("DAILY_REPORT_TIME", "09:00")

# Google Calendar API scope
GOOGLE_SCOPES: list[str] = ["https://www.googleapis.com/auth/calendar"]

# OAuth callback server
OAUTH_SERVER_PORT: int = int(os.environ.get("OAUTH_SERVER_PORT", "8080"))

# OpenAI model
OPENAI_MODEL: str = "gpt-4.1"

# Google Maps (Geocoding API)
GOOGLE_MAPS_API_KEY: str = os.environ.get("GOOGLE_MAPS_API_KEY", "")
