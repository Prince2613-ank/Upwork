import sqlite3
import json
from bs4 import BeautifulSoup

def deref(val, data):
    if isinstance(val, int) and 0 <= val < len(data):
        return data[val]
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
        # Find all workHistory items
        print("Examining work history items:")
        for idx, item in enumerate(data):
            if isinstance(item, dict) and "feedbackToClient" in item:
                # This is a work history item!
                fb_to_client_idx = item.get("feedbackToClient")
                fb_to_fl_idx = item.get("feedback")
                job_info_idx = item.get("jobInfo")
                contractor_idx = item.get("contractorInfo")
                
                fb_to_client = deref(fb_to_client_idx, data) if fb_to_client_idx is not None else None
                fb_to_fl = deref(fb_to_fl_idx, data) if fb_to_fl_idx is not None else None
                job_info = deref(job_info_idx, data) if job_info_idx is not None else {}
                contractor = deref(contractor_idx, data) if contractor_idx is not None else {}
                
                # If job_info is dict
                contract_title = ""
                if isinstance(job_info, dict):
                    t_idx = job_info.get("title")
                    contract_title = deref(t_idx, data) if t_idx is not None else ""
                
                fl_name = ""
                if isinstance(contractor, dict):
                    name_idx = contractor.get("name") or contractor.get("contractorName")
                    fl_name = deref(name_idx, data) if name_idx is not None else ""
                
                print(f"\nContract {idx}:")
                print(f"  Title: {repr(contract_title)}")
                print(f"  Freelancer: {repr(fl_name)}")
                print(f"  Freelancer-to-Client Feedback: {repr(fb_to_client)}")
                print(f"  Client-to-Freelancer Feedback: {repr(fb_to_fl)}")
