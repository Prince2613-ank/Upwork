import os
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from generate_standalone_report import generate_report

DB_1WEEK = ROOT / "output" / "database_1week.db"
OUTPUT_OUT_FILE = ROOT / "output" / "upwork_1week_report.html"

print("================================================================")
print("COMPILING 1-WEEK STANDALONE INTELLIGENCE REPORT (OCT 04 - OCT 11, 2026)")
print("================================================================")

# Generate the primary master HTML report
generate_report(
    db_path=str(DB_1WEEK),
    output_html=str(OUTPUT_OUT_FILE),
    date_filter_start="2026-10-04",
    date_filter_end="2026-10-11",
    report_title="Upwork 7-Day Market Intelligence Report (Oct 04 - Oct 11, 2026)"
)

# Mirror to all standard filenames for user convenience
mirrors = [
    ROOT / "upwork_1week_report.html",
    ROOT / "upwork_this_week_report.html",
    ROOT / "upwork_1week_04-10-2026_to_11-10-2026.html",
    ROOT / "upwork_1week_fetched_report.html",
    ROOT / "upwork_monday_scrape_27-09-2026.html",
]

for m in mirrors:
    shutil.copyfile(str(OUTPUT_OUT_FILE), str(m))
    size_mb = os.path.getsize(m) / (1024 * 1024)
    print(f"  [SYNCED] {m.name} ({size_mb:.2f} MB)")

print("\n[SUCCESS] Master 7-Day HTML Report compiled and synchronized across all locations.")
