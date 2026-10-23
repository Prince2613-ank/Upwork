"""
Configuration module for Flodata Analytics Upwork Market-Intelligence Data Collection System.
"""

import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# Directory Paths
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
CHECKPOINT_DIR = DATA_DIR / "checkpoints"
EXPORTS_DIR = DATA_DIR / "exports"

for d in [DATA_DIR, RAW_DATA_DIR, PROCESSED_DATA_DIR, CHECKPOINT_DIR, EXPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Upwork Search Parameters
PAYMENT_VERIFIED = True
SORT_BY = "recency"
PER_PAGE = 50

# Configurable Target Client Locations (from manager demonstration)
TARGET_CLIENT_LOCATIONS: List[str] = [
    "Europe",
    "Australia and New Zealand",
    "American Samoa",
    "Bahamas",
    "Bahrain",
    "Belgium",
    "Canada",
    "Cayman Islands",
    "Hong Kong",
    "India",
    "Israel",
    "Japan",
    "Kuwait",
    "Malaysia",
    "Morocco",
    "New Zealand",
    "Qatar",
    "Saudi Arabia",
    "Singapore",
    "South Korea",
    "United Arab Emirates",
    "United Kingdom",
    "United States",
    "United States Minor Outlying Islands",
    "United States Virgin Islands",
]

# Date Cutoff Configuration
# Manager requirement: approximately the most recent one month
DATE_WINDOW_DAYS = int(os.getenv("DATE_WINDOW_DAYS", "30"))

# Request Pacing & Safety Settings
MIN_REQUEST_DELAY_SEC = float(os.getenv("MIN_REQUEST_DELAY_SEC", "2.0"))
MAX_REQUEST_DELAY_SEC = float(os.getenv("MAX_REQUEST_DELAY_SEC", "4.0"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
BACKOFF_FACTOR = float(os.getenv("BACKOFF_FACTOR", "2.0"))

# Data Source Mode: "mock", "browser", "api"
DATA_SOURCE_MODE = os.getenv("DATA_SOURCE_MODE", "mock").lower()

# Browser Automation & Chrome CDP Settings
CHROME_CDP_URL = os.getenv("CHROME_CDP_URL", "http://127.0.0.1:9222")
BROWSER_HEADLESS = os.getenv("BROWSER_HEADLESS", "false").lower() == "true"
USER_DATA_DIR = BASE_DIR / "chrome_user_data"

# Upwork Official GraphQL API (if approved credentials provided)
UPWORK_CLIENT_ID = os.getenv("UPWORK_CLIENT_ID", "")
UPWORK_CLIENT_SECRET = os.getenv("UPWORK_CLIENT_SECRET", "")
UPWORK_ACCESS_TOKEN = os.getenv("UPWORK_ACCESS_TOKEN", "")
UPWORK_TENANT_ID = os.getenv("UPWORK_TENANT_ID", "")


def build_search_url(page: int = 1, locations: List[str] = None) -> str:
    """
    Constructs the canonical Upwork search URL matching the manager's search configuration.
    """
    import urllib.parse

    locs = locations if locations is not None else TARGET_CLIENT_LOCATIONS
    joined_locs = ",".join(locs)
    encoded_locs = urllib.parse.quote(joined_locs, safe=",")

    url = (
        f"https://www.upwork.com/nx/search/jobs?"
        f"location={encoded_locs}&"
        f"payment_verified=1&"
        f"per_page={PER_PAGE}&"
        f"sort={SORT_BY}"
    )
    if page > 1:
        url += f"&page={page}"
    return url
