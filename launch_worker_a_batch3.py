"""
FLODATA WORKER A - CHROME (Port 9222) EXTENDED QUEUE BATCH 3
=============================================================
- Connects to Chrome (port 9222)
- Reuses existing single Upwork tab
- Scrapes final global tier of countries:
  Guatemala, Dominican Republic, Jamaica, Trinidad and Tobago,
  Honduras, El Salvador, Nicaragua, Venezuela, Barbados, Belize, Bermuda,
  Uganda, Tanzania, Rwanda, Ethiopia, Zimbabwe, Zambia, Cameroon, Senegal,
  Cote d'Ivoire, Madagascar, Myanmar, Laos, Maldives, Fiji, Papua New Guinea
- Seamlessly saves to output/database_14days.db
"""
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import fetch_14day_dual_chrome as core

COUNTRIES_A_BATCH3 = [
    "Guatemala",
    "Dominican Republic",
    "Jamaica",
    "Trinidad and Tobago",
    "Honduras",
    "El Salvador",
    "Nicaragua",
    "Venezuela",
    "Barbados",
    "Belize",
    "Bermuda",
    "Uganda",
    "Tanzania",
    "Rwanda",
    "Ethiopia",
    "Zimbabwe",
    "Zambia",
    "Cameroon",
    "Senegal",
    "Cote d'Ivoire",
    "Madagascar",
    "Myanmar",
    "Laos",
    "Maldives",
    "Fiji",
    "Papua New Guinea"
]

if __name__ == "__main__":
    print("="*65, flush=True)
    print("  FLODATA WORKER A - CHROME (Port 9222) EXTENDED BATCH 3", flush=True)
    print(f"  Countries ({len(COUNTRIES_A_BATCH3)}):", flush=True)
    print(f"  {', '.join(COUNTRIES_A_BATCH3)}", flush=True)
    print("="*65, flush=True)
    
    core.setup_db()
    core.worker("A", 9222, COUNTRIES_A_BATCH3, "a")
