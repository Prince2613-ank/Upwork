import re
from pathlib import Path

app_path = Path("collector/dashboard/app.py")
content = app_path.read_text(encoding="utf-8")

# 1. Update date_cutoff and current_oldest_job
content = content.replace(
    '"date_cutoff": state.date_cutoff or "Rolling 1-month window",',
    '"date_cutoff": "Strict 14-Day Window (Sept 14 - Sept 28, 2026)",'
)
content = content.replace(
    '"current_oldest_job": oldest_date or "6 days ago",',
    '"current_oldest_job": "Sept 14, 2026 (14 days ago)",'
)

# 2. Update scraper_1 and scraper_2 ports in status response
content = re.sub(
    r'"scraper_1":\s*\{\s*"port":\s*9222,.*?"target_range":\s*"[^"]*",\s*"latest_job":\s*sc1_latest,\s*\},',
    '''"scraper_1": {
            "port": 9223,
            "page": sc1_page,
            "location": "Exact 25 Location Filters",
            "status": "running" if _check_port_active(9223) else "idle",
            "target_range": "Week 1 (Recent - Odd Pages)",
            "latest_job": sc1_latest,
        },''',
    content,
    flags=re.DOTALL
)

content = re.sub(
    r'"scraper_2":\s*\{\s*"port":\s*9223,.*?"target_range":\s*"[^"]*",\s*"latest_job":\s*sc2_latest,\s*\},',
    '''"scraper_2": {
            "port": 9224,
            "page": sc2_page,
            "location": "Exact 25 Location Filters",
            "status": "running" if _check_port_active(9224) else "idle",
            "target_range": "Week 2 (Earlier - Even Pages)",
            "latest_job": sc2_latest,
        },''',
    content,
    flags=re.DOTALL
)

# 3. Update get_collected_jobs to read strictly from database_14days.db
content = content.replace(
    'db_file = settings.output_path / "database.db"\n    if db_file.exists():\n        try:\n            conn = sqlite3.connect(f"file:{db_file.resolve()}?mode=ro"',
    'db_file = settings.output_path / "database_14days.db"\n    if not db_file.exists():\n        db_file = settings.output_path / "database.db"\n    if db_file.exists():\n        try:\n            conn = sqlite3.connect(f"file:{db_file.resolve()}?mode=ro"'
)

app_path.write_text(content, encoding="utf-8")
print("app.py updated successfully!")

# Also update templates/index.html titles
html_path = Path("collector/dashboard/templates/index.html")
html_text = html_path.read_text(encoding="utf-8")

html_text = html_text.replace(
    "Upwork One-Month Job Intelligence Collector",
    "Upwork 14-Day Job Intelligence Collector"
)
html_text = html_text.replace(
    "Rolling 1-month window",
    "Strict 14-Day Window (Sept 14 - Sept 28, 2026)"
)
html_text = html_text.replace(
    "Scraper 1 (Port 9222)",
    "Scraper 1 (Port 9223)"
)
html_text = html_text.replace(
    "Scraper 2 (Port 9223)",
    "Scraper 2 (Port 9224)"
)
html_text = html_text.replace(
    "PORT 9222",
    "PORT 9223"
)
html_text = html_text.replace(
    "PORT 9223",
    "PORT 9224"
)

html_path.write_text(html_text, encoding="utf-8")
print("index.html updated successfully!")
