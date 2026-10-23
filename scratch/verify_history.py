import sqlite3, json
from pathlib import Path

DB = Path(r"C:\Users\princ\.gemini\antigravity-ide\scratch\flodata-upwork-intelligence\output\database_14days.db")
conn = sqlite3.connect(DB)

rows = conn.execute("SELECT job_id, job_json FROM jobs ORDER BY rowid DESC").fetchall()

samples = []
for jid, raw in rows:
    try:
        d = json.loads(raw)
        hist = d.get("client_recent_history") or []
        # Find jobs with contracts and feedback
        with_feedback = [h for h in hist if len(str(h.get("feedback") or h.get("client_feedback") or "")) > 15]
        if len(hist) >= 15 and len(with_feedback) >= 5:
            samples.append((jid, d.get("title") or d.get("job_title") or "Untitled", hist))
            if len(samples) >= 2:
                break
    except Exception:
        pass

print("=== REAL DATA VERIFICATION: COMPLETE CLIENT HISTORY ===")
for jid, title, hist in samples:
    print(f"\nTarget Job: {title}")
    print(f"Upwork ID:  {jid}")
    print(f"Total Client History Items Captured: {len(hist)}")
    for i, h in enumerate(hist[:3], 1):
        fb = h.get("feedback") or h.get("client_feedback") or "No comment"
        print(f"\n  [Contract {i} of {len(hist)}]")
        print(f"    Past Job:    {h.get('job_title')}")
        print(f"    Date Range:  {h.get('date')}")
        print(f"    Freelancer:  {h.get('freelancer_name')}")
        print(f"    Score:       {h.get('rating')}")
        print(f"    Paid:        {h.get('amount')}")
        print(f"    Review Text: \"{fb}\"")
    print("-" * 65)
