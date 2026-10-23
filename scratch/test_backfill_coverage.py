import sqlite3
import json
import csv
import re

# 1. Load all client reviews from client_history.csv
csv_reviews_by_job_id = {}
with open('output/client_history.csv', 'r', encoding='utf-8-sig', errors='ignore') as f:
    reader = csv.DictReader(f)
    for r in reader:
        pid = r.get('parent_job_id', '').strip()
        if not pid:
            continue
        norm_id = pid.replace('~02', '').replace('~', '')
        
        # Verify review quality
        fb = (r.get('feedback') or '').strip()
        title = (r.get('history_job_title') or '').strip()
        amt = (r.get('amount') or '').strip()
        rat = (r.get('rating') or '').strip()
        fl = (r.get('freelancer_name') or '').strip()
        
        # Clean out marketing/proposal text leaks
        low_fb = fb.lower()
        if any(leak in low_fb for leak in [
            "this range includes relevant proposals", 
            "you’ll need connects to bid", "you'll need connects to bid",
            "this is when the client last reviewed",
            "explore upwork opportunities", "already have an account"
        ]):
            fb = "Client feedback on file."
            
        item = {
            "job_title": title or "Contract Completed",
            "job_url": r.get('history_job_url', ''),
            "date": r.get('date', ''),
            "duration": r.get('duration', ''),
            "payment_type": r.get('payment_type', ''),
            "amount": amt,
            "rating": rat,
            "freelancer_name": fl,
            "feedback": fb or "No feedback given",
            "feedback_full": True
        }
        
        for key in [pid, norm_id]:
            if key not in csv_reviews_by_job_id:
                csv_reviews_by_job_id[key] = []
            csv_reviews_by_job_id[key].append(item)

print(f"Loaded CSV reviews for {len(csv_reviews_by_job_id)} job IDs.")

# 2. Build Client Profile Fingerprint Map from database.db
# A client fingerprint can be uniquely constructed from:
# - client_profile_url (e.g. https://www.upwork.com/companies/~...)
# - or (member_since, total_spent, jobs_posted, location)
client_fingerprint_to_history = {}

conn = sqlite3.connect('output/database.db')
c = conn.cursor()
for jid, raw in c.execute('SELECT job_id, job_json FROM jobs'):
    d = json.loads(raw)
    hist = d.get('client_recent_history') or []
    if len(hist) > 0:
        client = d.get('client') or {}
        comp_url = d.get('client_profile_url') or client.get('company_profile_url') or ''
        loc = d.get('client_location') or client.get('location') or ''
        spend = d.get('client_total_spent') or client.get('total_spent') or ''
        posted = client.get('jobs_posted') or ''
        since = client.get('member_since') or ''
        hours = client.get('hours_billed') or ''
        
        if comp_url:
            if comp_url not in client_fingerprint_to_history or len(hist) > len(client_fingerprint_to_history[comp_url]):
                client_fingerprint_to_history[comp_url] = (hist, client)
                
        if since and spend and (posted or hours):
            fp = f"{since}|{spend}|{posted}|{loc}"
            if fp not in client_fingerprint_to_history or len(hist) > len(client_fingerprint_to_history[fp][0]):
                client_fingerprint_to_history[fp] = (hist, client)

conn.close()
print(f"Built Client Fingerprint Map with {len(client_fingerprint_to_history)} client profiles.")

# 3. Test matching on database_14days.db
conn14 = sqlite3.connect('output/database_14days.db')
c14 = conn14.cursor()
total_14 = c14.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]

restored_from_csv = 0
restored_from_fp = 0
still_missing = 0
already_had_history = 0

for jid, raw in c14.execute('SELECT job_id, job_json FROM jobs'):
    d = json.loads(raw)
    hist = d.get('client_recent_history') or []
    if len(hist) > 0:
        already_had_history += 1
        continue
        
    client = d.get('client') or {}
    spend = d.get('client_total_spent') or client.get('total_spent') or ''
    hires = d.get('client_hire_rate') or client.get('hire_rate') or ''
    norm_id = jid.replace('~02', '').replace('~', '')
    
    # Check if in CSV
    if jid in csv_reviews_by_job_id or norm_id in csv_reviews_by_job_id:
        restored_from_csv += 1
        continue
        
    # Check if in fingerprint map
    comp_url = d.get('client_profile_url') or client.get('company_profile_url') or ''
    loc = d.get('client_location') or client.get('location') or ''
    posted = client.get('jobs_posted') or ''
    since = client.get('member_since') or ''
    fp = f"{since}|{spend}|{posted}|{loc}"
    
    if comp_url and comp_url in client_fingerprint_to_history:
        restored_from_fp += 1
    elif fp in client_fingerprint_to_history:
        restored_from_fp += 1
    else:
        has_spend = any(char.isdigit() for char in spend) and spend != '$0' and '$0 spent' not in spend
        if has_spend:
            still_missing += 1

print("\n--- RESULTS ---")
print(f"Total jobs in 14-day DB: {total_14:,}")
print(f"Already had history: {already_had_history:,} ({already_had_history/total_14*100:.1f}%)")
print(f"Can restore from client_history.csv: {restored_from_csv:,}")
print(f"Can restore from same client fingerprint: {restored_from_fp:,}")
print(f"Total restorable immediately: {already_had_history + restored_from_csv + restored_from_fp:,} ({(already_had_history + restored_from_csv + restored_from_fp)/total_14*100:.1f}%)")
print(f"Remaining established jobs truly missing: {still_missing:,}")
conn14.close()
