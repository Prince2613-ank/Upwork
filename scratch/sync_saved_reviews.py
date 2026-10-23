import sqlite3
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

from collector.extraction.review_parser import parse_client_history
from generate_standalone_report import clean_freelancer_review
from run_daily_system import restore_full_feedback_from_raw

db_paths = [
    ROOT / "output" / "database_daily_2026-10-20.db",
    ROOT / "output" / "database_today.db",
    ROOT / "output" / "database_weekend_2026-10-19_to_2026-10-20.db",
    ROOT / "output" / "database_daily_2026-10-19_to_2026-10-20.db"
]

for db in db_paths:
    if not db.exists():
        continue
    conn = sqlite3.connect(db, timeout=20)
    rows = conn.execute("SELECT job_id, job_json, raw_html FROM jobs").fetchall()
    updated = 0
    for jid, jj, raw in rows:
        try:
            d = json.loads(jj)
            items = parse_client_history(raw)
            clean_revs = []
            for item_obj in items:
                h = item_obj.model_dump(mode="json")
                raw_htitle = (h.get("job_title") or "").strip()
                if raw_htitle.lower().startswith("rating is") or "no feedback" in raw_htitle.lower() or raw_htitle.lower() in ["none", "completed", "n/a", ""]:
                    h["job_title"] = "Completed Project"

                orig_fb = h.get("feedback") or ""
                fl_name = h.get("freelancer_name") or ""
                restored_fb = restore_full_feedback_from_raw(orig_fb, raw)
                cleaned_fb = clean_freelancer_review(restored_fb, fl_name)
                if cleaned_fb:
                    h["feedback"] = cleaned_fb
                    clean_revs.append(h)
                elif h.get("rating"):
                    m_r = re.search(r'(\d+(?:\.\d+)?)', str(h.get("rating")))
                    if m_r and float(m_r.group(1)) > 0:
                        h["feedback"] = f"Rated {m_r.group(1)} stars (No written feedback)"
                        clean_revs.append(h)

            d["client_recent_history"] = clean_revs
            new_json = json.dumps(d, default=str)
            conn.execute("UPDATE jobs SET job_json = ? WHERE job_id = ?", (new_json, jid))
            updated += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    print(f"Updated {updated} jobs in {db.name}", flush=True)

# Verification for ~022112658363064905128
conn = sqlite3.connect(ROOT / "output" / "database_daily_2026-10-20.db")
row = conn.execute("SELECT job_json FROM jobs WHERE job_id LIKE '%022112658363064905128%'").fetchone()
conn.close()
if row:
    d = json.loads(row[0])
    hist = d.get("client_recent_history") or []
    print(f"\nVerification for ~022112658363064905128: {len(hist)} reviews saved:", flush=True)
    for idx, r in enumerate(hist):
        print(f"  [{idx+1}] {r.get('job_title')} (★{r.get('rating')}) | FL: {r.get('freelancer_name')} | Feedback: {r.get('feedback')}", flush=True)
