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
        raw_nuxt = nuxt_script.string
        print("Nuxt script found! Length:", len(raw_nuxt))
        nuxt_json = json.loads(raw_nuxt)
        print("Nuxt parsed items:", len(nuxt_json))
        # Search for Ruwan's feedback
        for item in nuxt_json:
            if isinstance(item, str) and "Working with Chadrack was great" in item:
                print("\nFOUND UN-TRUNCATED FEEDBACK IN __NUXT_DATA__:")
                print(repr(item))
