"""
FLODATA WORKER A - CHROME (Port 9222) EXTENDED QUEUE
=====================================================
- Connects to Chrome (port 9222)
- Reuses existing single Upwork tab
- Scrapes remaining countries: Cyprus, Malta, Luxembourg, Malaysia, Morocco,
  Kuwait, Qatar, Jordan, Lebanon, Georgia, Serbia, Kazakhstan, Azerbaijan, Sri Lanka, Bangladesh
- Seamlessly saves to output/database_14days.db
"""
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import fetch_14day_dual_chrome as core

COUNTRIES_A_EXTENDED = [
    "Cyprus",
    "Malta",
    "Luxembourg",
    "Malaysia",
    "Morocco",
    "Kuwait",
    "Qatar",
    "Jordan",
    "Lebanon",
    "Georgia",
    "Serbia",
    "Kazakhstan",
    "Azerbaijan",
    "Sri Lanka",
    "Bangladesh"
]

if __name__ == "__main__":
    print("="*65, flush=True)
    print("  FLODATA WORKER A - CHROME (Port 9222) EXTENDED RUN", flush=True)
    print(f"  Countries ({len(COUNTRIES_A_EXTENDED)}):", flush=True)
    print(f"  {', '.join(COUNTRIES_A_EXTENDED)}", flush=True)
    print("="*65, flush=True)
    
    core.setup_db()
    core.worker("A", 9222, COUNTRIES_A_EXTENDED, "a")
