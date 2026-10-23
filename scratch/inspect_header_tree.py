import sqlite3
import json
import re
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("output/database_daily_2026-10-20.db")
row = conn.execute("SELECT raw_html FROM jobs WHERE job_id LIKE '%022112658363064905128%'").fetchone()
conn.close()

html = row[0]
soup = BeautifulSoup(html, "html.parser")

# Find where "Client's recent history" occurs
for tag in soup.find_all(True):
    if tag.string and "Client's recent history" in tag.string:
        print("Found header tag:", tag.name, tag.attrs, tag.string.strip())
        parent = tag.parent
        for depth in range(6):
            if parent:
                print(f"  Parent {depth}: <{parent.name}> class={parent.get('class')} attrs={list(parent.attrs.keys())}")
                # Print its child tags
                children = [c.name for c in parent.children if hasattr(c, 'name')]
                print(f"    Children ({len(children)}): {children[:10]}")
                parent = parent.parent
        break
