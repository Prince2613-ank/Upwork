"""
Configuration and settings manager for Upwork Intelligence Collector.
Reads and validates config.json as defined in Section 18.
"""

import json
import os
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE = BASE_DIR / "config.json"

DEFAULT_LOCATIONS: List[str] = [
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


class Settings:
    def __init__(self, config_path: Path = CONFIG_FILE):
        self.config_path = config_path
        self.date_range_months: int = 1
        self.date_range_days: int = 0  # If > 0, overrides date_range_months (e.g. 2 = last 2 days)
        self.results_per_page: int = 50
        self.sort: str = "most_recent"
        self.payment_verified: bool = True
        self.delay_between_jobs_seconds: float = 1.0
        self.delay_between_pages_seconds: float = 2.0
        self.max_retries: int = 3
        self.output_directory: str = "./output"
        self.cdp_url: str = "http://127.0.0.1:9222"
        self.search_url: str = ""
        self.headless: bool = False
        self.default_mode: str = "test_3"
        self.target_locations: List[str] = DEFAULT_LOCATIONS

        self.load()

    def load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.date_range_months = int(data.get("date_range_months", self.date_range_months))
                self.date_range_days = int(data.get("date_range_days", self.date_range_days))
                self.results_per_page = int(data.get("results_per_page", self.results_per_page))
                self.sort = str(data.get("sort", self.sort))
                self.payment_verified = bool(data.get("payment_verified", self.payment_verified))
                self.delay_between_jobs_seconds = float(data.get("delay_between_jobs_seconds", self.delay_between_jobs_seconds))
                self.delay_between_pages_seconds = float(data.get("delay_between_pages_seconds", self.delay_between_pages_seconds))
                self.max_retries = int(data.get("max_retries", self.max_retries))
                self.output_directory = str(data.get("output_directory", self.output_directory))
                self.cdp_url = str(data.get("cdp_url", self.cdp_url))
                self.search_url = str(data.get("search_url", self.search_url))
                self.headless = bool(data.get("headless", self.headless))
                self.default_mode = str(data.get("default_mode", self.default_mode))
                if "target_locations" in data:
                    self.target_locations = data["target_locations"]
            except Exception as e:
                print(f"Warning: Could not parse {self.config_path} ({e}). Using defaults.")

        # Ensure output directory exists
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.debug_snapshots_path.mkdir(parents=True, exist_ok=True)

    @property
    def output_path(self) -> Path:
        p = Path(self.output_directory)
        if not p.is_absolute():
            p = BASE_DIR / p
        return p

    @property
    def debug_snapshots_path(self) -> Path:
        return self.output_path / "debug_snapshots"

    def build_search_url(self, page: int = 1, location: str = None) -> str:
        """
        Constructs the canonical Upwork search URL matching the active filters
        from the manager configuration:
        Sort: Most Recent (recency), Payment verified, 50 per page, specified locations.
        """
        if self.search_url and not location:
            base = self.search_url
            if page > 1:
                delim = "&" if "?" in base else "?"
                return f"{base}{delim}page={page}"
            return base

        if location:
            joined_locs = location
        else:
            joined_locs = ",".join(self.target_locations)
            
        encoded_locs = urllib.parse.quote(joined_locs, safe=",")
        sort_val = "recency" if self.sort in ["most_recent", "recency"] else self.sort
        pv_val = "1" if self.payment_verified else "0"

        url = (
            f"https://www.upwork.com/nx/search/jobs?"
            f"location={encoded_locs}&"
            f"payment_verified={pv_val}&"
            f"per_page={self.results_per_page}&"
            f"sort={sort_val}"
        )
        if page > 1:
            url += f"&page={page}"
        return url

settings = Settings()
