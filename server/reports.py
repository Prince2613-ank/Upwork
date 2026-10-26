import csv
import html
import json
from pathlib import Path

from sqlalchemy import select
from server.db import queue


def results(db, rid):
    with db.engine.connect() as c:
        return c.execute(select(queue.c.result).where(queue.c.run_id == rid,
                          queue.c.status == "done").order_by(queue.c.id)).scalars().all()


def build_report(db, settings, run):
    rows = results(db, run["id"])
    counts = db.counts(run["id"])
    incomplete = sum(not r.get("history_expansion_complete", False) or
                     (bool(r.get("client_recent_history")) and not (r.get("extraction_status") or {}).get("full_reviews", False)) or
                     r.get("posted_date_precision") != "exact" for r in rows)
    partial = bool(counts.get("failed") or counts.get("pending") or counts.get("running") or incomplete
                   or not run["discovery_done"])
    label = "PARTIAL / CHECK COVERAGE" if partial else "Collection finished — discoverable jobs only"
    esc = lambda x: html.escape(str(x or ""), quote=True)
    parts = [f'<!doctype html><html><head><meta charset="utf-8"><title>Upwork report</title>'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:20px;background:#f4f7fb}'
        'article{background:white;padding:24px;margin:18px 0;border-radius:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere}'
        'small{color:#526174}summary{cursor:pointer}a{color:#165bbb}</style></head><body>'
        f'<h1>Upwork intelligence</h1><p>{esc(run["start_date"])} to {esc(run["end_date"])} '
        f'({esc(run["timezone"])})</p><strong>{esc(label)}</strong>'
        f'<p>{len(rows)} saved · {counts.get("failed",0)} failed · {counts.get("unavailable",0)} unavailable · '
        f'{incomplete} requiring completeness review</p>']
    for row in rows:
        detail = row.get("job") or {}
        client = row.get("client") or {}
        # All scraped strings are escaped; report contains no executable scripts.
        from server.browser import valid_url
        url = row.get("job_url", "")
        link = f'<a href="{esc(url)}" rel="noopener noreferrer">Open job</a>' if valid_url(url) else ""
        parts.append(f'<article><h2>{esc(row.get("job_title"))}</h2>{link}'
                     f'<p>{esc(row.get("posted_at"))} · {esc(client.get("location"))}</p>'
                     f'<pre>{esc(detail.get("description"))}</pre><h3>Client</h3>'
                     f'<pre>{esc(json.dumps(client, ensure_ascii=False, indent=2))}</pre><h3>Contract history / reviews</h3>')
        for review in row.get("client_recent_history", []):
            parts.append(f'<details><summary>{esc(review.get("job_title"))} — {esc(review.get("amount"))}</summary>'
                         f'<pre>{esc(json.dumps(review, ensure_ascii=False, indent=2))}</pre></details>')
        parts.append('</article>')
    parts.append('</body></html>')
    path = settings.data_dir / "reports" / f'{run["id"]}.html'
    temp = path.with_suffix(".tmp")
    temp.write_text("".join(parts), encoding="utf-8")
    temp.replace(path)
    path.with_suffix(".json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with path.with_suffix(".csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["job_id", "job_title", "job_url", "posted_at", "description", "client_location", "reviews"])
        for r in rows:
            writer.writerow([safe_csv(r.get("job_id")), safe_csv(r.get("job_title")), safe_csv(r.get("job_url")),
                safe_csv(r.get("posted_at")), safe_csv((r.get("job") or {}).get("description")),
                safe_csv((r.get("client") or {}).get("location")), len(r.get("client_recent_history", []))])
    return path.name, partial


def safe_csv(value):
    value = str(value or "")
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
