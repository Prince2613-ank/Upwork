import sqlite3
import json
import re

conn = sqlite3.connect("output/database_1week.db")
c = conn.cursor()
rows = c.execute("SELECT job_id, job_json FROM jobs").fetchall()
conn.close()

clients_with_hires_no_reviews = 0
clients_new_no_reviews = 0
clients_with_reviews = 0

sample_no_reviews_with_spend = []
sample_reviews = []

truncated_feedback_count = 0
feedback_with_ellipsis = 0

for jid, jjson in rows:
    data = json.loads(jjson)
    client = data.get("client") or {}
    hist = data.get("client_recent_history") or []
    
    spend = str(client.get("total_spent") or data.get("client_spend") or "")
    total_hires = str(client.get("total_hires") or "")
    reviews_count = len(hist)
    
    if reviews_count > 0:
        clients_with_reviews += 1
        if len(sample_reviews) < 5:
            sample_reviews.append({
                "job_id": jid,
                "job_title": data.get("job_title"),
                "client_spend": spend,
                "reviews_count": reviews_count,
                "first_review": hist[0]
            })
        for h in hist:
            fb = h.get("feedback") or ""
            if fb.endswith("...") or fb.endswith("…"):
                feedback_with_ellipsis += 1
    else:
        # Check if client has spend or hires
        has_spend = any(c.isdigit() for c in spend) and spend != "$0"
        has_hires = any(c.isdigit() for c in total_hires) and total_hires not in ["0", ""]
        if has_spend or has_hires:
            clients_with_hires_no_reviews += 1
            if len(sample_no_reviews_with_spend) < 5:
                sample_no_reviews_with_spend.append({
                    "job_id": jid,
                    "title": data.get("job_title"),
                    "spend": spend,
                    "hires": total_hires,
                    "rating": client.get("rating")
                })
        else:
            clients_new_no_reviews += 1

print("--- CLIENT REVIEWS DISTRIBUTION ---")
print(f"Total jobs: {len(rows):,}")
print(f"Jobs whose clients HAVE reviews: {clients_with_reviews:,}")
print(f"Jobs with New Clients ($0 spend / 0 hires): {clients_new_no_reviews:,}")
print(f"Jobs with Established Clients but 0 reviews in DB: {clients_with_hires_no_reviews:,}")
print(f"Reviews ending with ellipsis: {feedback_with_ellipsis}")

if sample_no_reviews_with_spend:
    print("\nSample established clients without reviews in DB:")
    for s in sample_no_reviews_with_spend:
        print(s)

if sample_reviews:
    print("\nSample reviews fetched:")
    for s in sample_reviews[:3]:
        print(f"Job: {s['job_title']} (Spend: {s['client_spend']})")
        print(f"  First review: {s['first_review']}")
