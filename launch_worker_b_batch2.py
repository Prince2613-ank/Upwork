"""
FLODATA WORKER B - EDGE (Port 9223) EXTENDED QUEUE BATCH 2
===========================================================
- Connects to Edge (port 9223)
- Reuses existing single Upwork tab (never touches user non-Upwork tabs)
- Scrapes remaining African & Island economies:
  Namibia, Botswana, Mozambique, Angola, Uganda, Tanzania, Rwanda,
  Ethiopia, Zimbabwe, Zambia, Cameroon, Senegal, Cote d'Ivoire,
  Madagascar, Myanmar, Laos, Maldives, Fiji, Papua New Guinea
- Seamlessly saves to output/database_14days.db
"""
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import fetch_14day_dual_chrome as core

COUNTRIES_B_BATCH2 = [
    "Namibia",
    "Botswana",
    "Mozambique",
    "Angola",
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
    print("  FLODATA WORKER B - EDGE (Port 9223) EXTENDED BATCH 2", flush=True)
    print(f"  Countries ({len(COUNTRIES_B_BATCH2)}):", flush=True)
    print(f"  {', '.join(COUNTRIES_B_BATCH2)}", flush=True)
    print("="*65, flush=True)
    
    core.setup_db()
    core.worker("B", 9223, COUNTRIES_B_BATCH2, "b")
