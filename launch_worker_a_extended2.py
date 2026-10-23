"""
FLODATA WORKER A - CHROME (Port 9222) EXTENDED QUEUE BATCH 2
=============================================================
- Connects to Chrome (port 9222)
- Reuses existing single Upwork tab
- Scrapes next tier of global countries:
  Ukraine, Armenia, Moldova, Bosnia and Herzegovina, North Macedonia,
  Albania, Montenegro, Kosovo, Uzbekistan, Kyrgyzstan, Tunisia, Algeria,
  Ghana, Mauritius, Ecuador, Bolivia, Paraguay, Nepal, Cambodia, Mongolia
- Seamlessly saves to output/database_14days.db
"""
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import fetch_14day_dual_chrome as core

COUNTRIES_A_BATCH2 = [
    "Ukraine",
    "Armenia",
    "Moldova",
    "Bosnia and Herzegovina",
    "North Macedonia",
    "Albania",
    "Montenegro",
    "Kosovo",
    "Uzbekistan",
    "Kyrgyzstan",
    "Tunisia",
    "Algeria",
    "Ghana",
    "Mauritius",
    "Ecuador",
    "Bolivia",
    "Paraguay",
    "Nepal",
    "Cambodia",
    "Mongolia"
]

if __name__ == "__main__":
    print("="*65, flush=True)
    print("  FLODATA WORKER A - CHROME (Port 9222) EXTENDED BATCH 2", flush=True)
    print(f"  Countries ({len(COUNTRIES_A_BATCH2)}):", flush=True)
    print(f"  {', '.join(COUNTRIES_A_BATCH2)}", flush=True)
    print("="*65, flush=True)
    
    core.setup_db()
    core.worker("A", 9222, COUNTRIES_A_BATCH2, "a")
