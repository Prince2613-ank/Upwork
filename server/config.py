import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urlencode
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Select one profile; local development must not inherit deployment secrets.
load_dotenv(PROJECT_ROOT / os.getenv("PIPELINE_ENV_FILE", ".env.local"))

# Preserve the existing daily collector's 25-location search filter.
LOCATIONS = ("Europe,Australia%20and%20New%20Zealand,American%20Samoa,Bahamas,Bahrain,Belgium,Canada,Cayman%20Islands,"
             "Hong%20Kong,India,Israel,Japan,Kuwait,Malaysia,Morocco,New%20Zealand,Qatar,Saudi%20Arabia,Singapore,South%20Korea,"
             "United%20Arab%20Emirates,United%20Kingdom,United%20States,United%20States%20Minor%20Outlying%20Islands,"
             "United%20States%20Virgin%20Islands")
DEFAULT_SEARCH_URL = "https://www.upwork.com/nx/search/jobs?" + urlencode({
    "location": LOCATIONS, "payment_verified": "1", "per_page": "50", "sort": "recency"})


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///output/database.db")
    data_dir: Path = Path(os.getenv("PIPELINE_DATA_DIR", "output/server"))
    timezone: str = os.getenv("PIPELINE_TIMEZONE", "Asia/Kolkata")
    username: str = os.getenv("DASHBOARD_USER", "admin")
    password: str = os.getenv("DASHBOARD_PASSWORD", "")
    password_hash: str = os.getenv("DASHBOARD_PASSWORD_SCRYPT", "")
    session_secure: bool = os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true"
    session_hours: int = int(os.getenv("SESSION_HOURS", "8"))
    trust_proxy: bool = os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true"
    browser_a: str = os.getenv("BROWSER_A_CDP", "http://127.0.0.1:9222")
    browser_b: str = os.getenv("BROWSER_B_CDP", "http://127.0.0.1:9223")
    search_url: str = os.getenv("UPWORK_SEARCH_URL") or DEFAULT_SEARCH_URL
    webhook: str = os.getenv("GOOGLE_CHAT_WEBHOOK", "")
    chat_space: str = os.getenv("GOOGLE_CHAT_SPACE", "")
    token_file: str = os.getenv("GOOGLE_CHAT_TOKEN_FILE", "/secrets/google-chat-token.json")
    public_url: str = os.getenv("PUBLIC_URL", "")

    @property
    def tz(self):
        return ZoneInfo(self.timezone)

    def prepare(self):
        for name in ("raw", "reports", "diagnostics"):
            (self.data_dir / name).mkdir(parents=True, exist_ok=True)
