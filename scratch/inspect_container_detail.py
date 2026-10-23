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

tag = soup.find(lambda t: t.string and "Client's recent history" in t.string)
# Parent 3 is the air3-card container
container = tag.find_parent("div", class_="air3-card")
print("Container found:", bool(container))
if container:
    sections = container.find_all("section")
    print(f"Total <section> in container: {len(sections)}")
    for i, s in enumerate(sections):
        print(f"\n--- SECTION {i} --- class={s.get('class')}")
        # Check text
        lines = [line.strip() for line in s.get_text("\n").splitlines() if line.strip()]
        print("Lines count:", len(lines))
        print("First 5 lines:", lines[:5])
        
        # Check child cards or items
        items = s.find_all(["div", "section"], class_=lambda c: c and any(k in str(c) for k in ["card-section", "item", "story", "contract"]))
        print(f"Sub-items found: {len(items)}")

    # Check for pagination or buttons anywhere in this container
    all_btns = container.find_all(["button", "a"])
    print(f"\nAll buttons/links in client history container ({len(all_btns)}):")
    for b in all_btns:
        print(f"  <{b.name}> text='{b.get_text(strip=True)}' class={b.get('class')} attrs={b.attrs}")
