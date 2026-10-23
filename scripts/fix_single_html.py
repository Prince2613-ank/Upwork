import csv, html
from pathlib import Path

with open('output/jobs.csv', 'r', encoding='utf-8-sig') as f:
    jobs = list(csv.DictReader(f))

target = [j for j in jobs if j.get('job_id') == '~022101396077124611292'][0]
html_path = Path('output') / target['raw_html_file']

j_title = html.escape(target.get('job_title', ''))
j_desc = html.escape(target.get('description', '')).replace('\n', '<br/>')
j_loc = html.escape(target.get('client_location', ''))
j_budget = html.escape(target.get('budget', ''))

content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{j_title} - Upwork Job Intelligence</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #0f172a; color: #f8fafc; padding: 30px; line-height: 1.6; }}
        .container {{ max-width: 850px; margin: 0 auto; background: #1e293b; border-radius: 10px; padding: 25px; border: 1px solid #334155; }}
        h1 {{ color: #38bdf8; margin-top: 0; }}
        .meta {{ background: #0f172a; padding: 15px; border-radius: 6px; margin: 20px 0; }}
        .desc {{ background: #0b1329; padding: 20px; border-radius: 6px; border-left: 4px solid #38bdf8; margin: 20px 0; white-space: pre-wrap; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{j_title}</h1>
        <div class="meta">
            <strong>Location:</strong> {j_loc} | 
            <strong>Budget:</strong> {j_budget} | 
            <strong>Payment Verified:</strong> Verified
        </div>
        <h3>Job Description</h3>
        <div class="desc">{j_desc}</div>
    </div>
</body>
</html>"""

html_path.write_text(content, encoding='utf-8')
print('Successfully written HTML. Size:', html_path.stat().st_size)
