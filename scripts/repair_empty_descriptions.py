"""
Repairs empty job descriptions across output/jobs.csv and output/database.db
using the raw HTML files stored in output/raw_html/.
"""

import csv
import json
import sqlite3
import re
from pathlib import Path
from bs4 import BeautifulSoup
from collector.extraction.job_parser import extract_full_description

def repair_descriptions():
    raw_html_dir = Path("output/raw_html")
    jobs_csv_path = Path("output/jobs.csv")
    db_path = Path("output/database.db")
    
    # 1. Process jobs.csv
    print(f"Reading {jobs_csv_path}...", flush=True)
    if not jobs_csv_path.exists():
        print("jobs.csv does not exist!")
        return

    recovered_csv = 0
    total_valid_rows = 0
    cleaned_rows = []
    
    with open(jobs_csv_path, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        desc_col = "description" if "description" in fieldnames else ("job_description" if "job_description" in fieldnames else None)
        
        for r in reader:
            jid = (r.get("job_id") or "").strip()
            # Drop malformed split rows that lack valid job_id and URL
            if not jid and not r.get("job_url", "").startswith("http"):
                continue
            if "Too many applicants" in jid or "Rating is" in jid:
                continue

            total_valid_rows += 1
            curr_desc = (r.get(desc_col, "") if desc_col else "").strip()
            
            if not curr_desc or curr_desc.lower() == "none":
                clean_id = jid.replace("~", "")
                p = raw_html_dir / f"{clean_id}.html"
                if not p.exists():
                    p = raw_html_dir / f"{jid}.html"
                
                if p.exists():
                    try:
                        html = p.read_text(encoding="utf-8", errors="replace")
                        soup = BeautifulSoup(html, "html.parser")
                        new_desc = extract_full_description(soup)
                        if new_desc and len(new_desc) > 20:
                            if desc_col:
                                r[desc_col] = new_desc
                            if "description" in r:
                                r["description"] = new_desc
                            recovered_csv += 1
                    except Exception as e:
                        print(f"Error parsing {p.name}: {e}")
            
            cleaned_rows.append(r)

    print(f"Recovered {recovered_csv} job descriptions in CSV. Total valid rows: {len(cleaned_rows)}", flush=True)

    # Save repaired jobs.csv
    with open(jobs_csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cleaned_rows)
    print(f"Updated {jobs_csv_path} successfully.", flush=True)

    # 2. Process database.db
    if db_path.exists():
        print(f"Checking {db_path}...", flush=True)
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT job_id, job_json FROM jobs")
        all_db_jobs = cur.fetchall()
        
        recovered_db = 0
        updated_records = []
        for jid, jjson_str in all_db_jobs:
            try:
                data = json.loads(jjson_str)
                job_inner = data.get("job", {})
                curr_desc = (job_inner.get("description") or "").strip()
                
                if not curr_desc or curr_desc.lower() == "none":
                    clean_id = jid.replace("~", "")
                    p = raw_html_dir / f"{clean_id}.html"
                    if not p.exists():
                        p = raw_html_dir / f"{jid}.html"
                    
                    if p.exists():
                        html = p.read_text(encoding="utf-8", errors="replace")
                        soup = BeautifulSoup(html, "html.parser")
                        new_desc = extract_full_description(soup)
                        if new_desc and len(new_desc) > 20:
                            job_inner["description"] = new_desc
                            data["job"] = job_inner
                            updated_records.append((json.dumps(data), jid))
                            recovered_db += 1
            except Exception as e:
                pass
        
        if updated_records:
            cur.executemany("UPDATE jobs SET job_json = ? WHERE job_id = ?", updated_records)
            conn.commit()
            print(f"Updated {recovered_db} jobs in database.db.", flush=True)
        conn.close()

if __name__ == "__main__":
    repair_descriptions()
