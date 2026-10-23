import sqlite3
import json
from bs4 import BeautifulSoup

def deref(val, data, depth=0):
    if depth > 10:
        return val
    if isinstance(val, int) and 0 <= val < len(data):
        return deref(data[val], data, depth + 1)
    if isinstance(val, list):
        if len(val) >= 2 and val[0] in ["Reactive", "ShallowReactive", "Ref", "Computed"]:
            return deref(val[1], data, depth + 1)
        return [deref(x, data, depth + 1) for x in val]
    if isinstance(val, dict):
        return {k: deref(v, data, depth + 1) for k, v in val.items()}
    return val

conn = sqlite3.connect("output/database_1week.db")
c = conn.cursor()
row = c.execute("SELECT raw_html FROM jobs WHERE job_id = '~022109339536492611536'").fetchone()
conn.close()

if row and row[0]:
    soup = BeautifulSoup(row[0], "html.parser")
    nuxt_script = soup.find("script", id="__NUXT_DATA__")
    if nuxt_script:
        data = json.loads(nuxt_script.string)
        for idx, item in enumerate(data):
            if isinstance(item, dict) and "feedbackToClient" in item:
                resolved = deref(item, data)
                print(f"\n--- Resolved Contract {idx} ---")
                print("Job Info:", resolved.get("jobInfo"))
                print("Contractor Info:", resolved.get("contractorInfo"))
                print("Feedback to Client:", resolved.get("feedbackToClient"))
                print("Feedback to Freelancer:", resolved.get("feedback"))
                print("Total Charge:", resolved.get("totalCharge"))
