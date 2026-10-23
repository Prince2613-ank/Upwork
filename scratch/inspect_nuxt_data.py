import re
import json

with open("scratch/sample_job_raw.html", "r", encoding="utf-8", errors="ignore") as f:
    raw = f.read()

m = re.search(r'<script[^>]*id=["\']__NUXT_DATA__["\'][^>]*>(.*?)</script>', raw, re.DOTALL)
if m:
    data_str = m.group(1).strip()
    data = json.loads(data_str)
    print(f"__NUXT_DATA__ array elements: {len(data)}")
    
    # Search for comments
    comments = [item for item in data if isinstance(item, str) and "Excellent collaboration" in item]
    print(f"Comments matching 'Excellent collaboration': {len(comments)}")
    for c in comments:
        print(f"Length: {len(c)}")
        print(f"Content: {repr(c)}")
        
    dispute = [item for item in data if isinstance(item, str) and "escalating this contractual" in item]
    print(f"\nComments matching dispute: {len(dispute)}")
    for c in dispute:
        print(f"Length: {len(c)}")
        print(f"Content: {repr(c)}")

    # Check descriptions
    descriptions = [item for item in data if isinstance(item, str) and "I run a Youtube channel" in item]
    print(f"\nDescriptions in Nuxt: {len(descriptions)}")
    for d in descriptions:
        print(f"Length: {len(d)}")
        print(f"Ends with: {repr(d[-100:])}")
else:
    print("No __NUXT_DATA__ found")
