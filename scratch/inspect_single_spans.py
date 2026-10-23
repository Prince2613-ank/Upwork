import sqlite3, json, sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("file:output/database_1week.db?mode=ro", uri=True)
cur = conn.cursor()
cur.execute("SELECT job_json FROM jobs")

single_span_samples = []
for (r,) in cur.fetchall():
    d = json.loads(r)
    for h in (d.get("client_recent_history") or []):
        fb = h.get("feedback") or ""
        fl = h.get("freelancer_name") or ""
        if fb and "\n" not in fb and len(fb) > 20:
            single_span_samples.append((fb, fl, h.get("job_title", "")))

print(f"Total single-span feedback items: {len(single_span_samples)}")

print("\nSample 20 single-span items:")
for fb, fl, title in single_span_samples[:20]:
    print(f"• FL: '{fl}' | Text: '{fb}'")
