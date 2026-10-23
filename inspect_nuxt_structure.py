import sqlite3
import json
from bs4 import BeautifulSoup

conn = sqlite3.connect("output/database_1week.db")
c = conn.cursor()
row = c.execute("SELECT raw_html FROM jobs WHERE job_id = '~022109339536492611536'").fetchone()
conn.close()

if row and row[0]:
    soup = BeautifulSoup(row[0], "html.parser")
    nuxt_script = soup.find("script", id="__NUXT_DATA__")
    if nuxt_script:
        nuxt_json = json.loads(nuxt_script.string)
        print("Searching for objects/keys related to history/feedback...")
        for idx, item in enumerate(nuxt_json):
            if isinstance(item, dict):
                keys = list(item.keys())
                if any(k in keys for k in ["feedback", "rating", "contract", "title", "client", "buyer"]):
                    print(f"Index {idx}: dict with keys {keys}")
            elif isinstance(item, str):
                if any(w in item.lower() for w in ["feedback", "chadrack", "ruwan"]):
                    print(f"Index {idx}: str {repr(item)}")
