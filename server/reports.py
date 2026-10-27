import csv
import html
import json
from pathlib import Path

from sqlalchemy import insert, select, update
from server.db import now, queue, releases
from server.quality import REASON_LABELS, release_candidate
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo


def report_name(run):
    day = datetime.fromtimestamp(run["created_at"], ZoneInfo(run["timezone"]))
    weekday = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")[day.weekday()]
    return f'upwork_{weekday}_scrape_{day.date().isoformat()}.html'


def results(db, rid):
    with db.engine.connect() as c:
        rows = c.execute(select(queue.c.job_id, queue.c.result).where(queue.c.run_id == rid,
                         queue.c.status == "done").order_by(queue.c.id)).all()
    return [{**r.result, "job_id": (r.result.get("job_id") if isinstance(r.result, dict) else None) or r.job_id, "_job_id": r.job_id} if isinstance(r.result, dict) else r.result for r in rows]


def explorer_record(row):
    """Maps a released job onto the record shape the standalone explorer renders."""
    from generate_standalone_report import clean_freelancer_review, format_location
    detail, client = row.get("job") or {}, row.get("client") or {}
    reviews, seen = [], set()
    for h in row.get("client_recent_history") or []:
        fl = str(h.get("freelancer_name") or "").strip()
        text = clean_freelancer_review(h.get("feedback") or "", fl)
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        reviews.append({"job_title": h.get("job_title") or "Completed Project", "feedback": text, "rating": h.get("rating") or "5.0",
                        "date": h.get("date") or "", "amount": h.get("amount") or "", "freelancer": fl})
    skills = detail.get("skills") or row.get("skills") or []
    if isinstance(skills, str):
        skills = [x.strip() for x in skills.split(",") if x.strip()]
    na = lambda key: client.get(key) or "N/A"
    return {"id": row.get("_job_id") or row.get("job_url", ""), "title": row.get("job_title") or detail.get("title") or "Untitled Job",
            "url": row.get("job_url", ""), "posted": row.get("posted_at") or row.get("posted_raw") or "", "posted_raw": row.get("posted_raw") or "",
            "location": format_location(str(client.get("location") or row.get("client_location") or "Unknown").strip()),
            "verified": client.get("payment_verified") is True, "rating": na("rating"), "spend": na("total_spent"),
            "jobs_posted": na("jobs_posted"), "hire_rate": na("hire_rate"), "total_hires": na("total_hires"),
            "active_hires": na("active_hires"), "hours_billed": na("hours_billed"), "member_since": na("member_since"),
            "client_type": client.get("client_type") or "",
            "budget": (row.get("budget_min") and f"${row.get('budget_min')}") or detail.get("budget") or "Not Specified",
            "budget_type": row.get("job_type") or "Fixed", "experience": row.get("experience_level") or "Intermediate",
            "description": detail.get("description") or "", "skills": skills, "reviews": reviews, "total_reviews": len(reviews)}


def render_explorer(rows, run, label, summary):
    from generate_standalone_report import render_report_html
    records = [explorer_record(r) for r in rows]
    stars = []
    for r in records:
        try:
            stars.append(float(str(r["rating"]).split()[0].replace("/5", "")))
        except ValueError:
            pass
    stars = [v for v in stars if v > 0]
    countries = {r["location"].split(",")[0].strip() for r in records if r["location"] != "Unknown"}
    dates = {r["posted"][:10] for r in records if r["posted"][:10].count("-") == 2}
    title = f'Upwork Intelligence Master Report — {run["start_date"]} to {run["end_date"]} ({run["timezone"]}) · {label}'
    return render_report_html(records, countries, dates, sum(r["verified"] for r in records), sum(stars), len(stars), title)


def build_report(db, settings, run):
    candidates = results(db, run["id"])
    rows, exclusions = [], Counter()
    for candidate in candidates:
        approved, reason = release_candidate(candidate)
        if approved is None:
            exclusions[reason] += 1
        else:
            rows.append(approved)
    counts = db.counts(run["id"])
    uncertain_dates = sum(r.get("posted_date_precision") != "exact" for r in rows)
    partial = bool(counts.get("failed") or counts.get("pending") or counts.get("running")
                   or uncertain_dates or not run["discovery_done"])
    label = "PARTIAL COLLECTION: coverage requires attention" if partial else "Collection finished: validated jobs only"
    summary = {"collected": len(candidates), "released": len(rows), "excluded": sum(exclusions.values()),
               "skipped": counts.get("unavailable", 0),
               "exclusion_reasons": dict(exclusions), "failed": counts.get("failed", 0),
               "pending": counts.get("pending", 0) + counts.get("running", 0),
               "uncertain_dates": uncertain_dates, "partial_collection": partial}
    html_text = render_explorer(rows, run, label, summary)
    # Separate run folders retain multiple runs made on the same day without changing the requested filename.
    root = settings.data_dir / "reports"
    path = root / run["id"] / report_name(run)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(html_text, encoding="utf-8")
    temp.replace(path)
    path.with_suffix(".json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with path.with_suffix(".csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["job_id", "job_title", "job_url", "posted_at", "description", "client_location", "reviews"])
        for r in rows:
            writer.writerow([safe_csv(r.get("job_id")), safe_csv(r.get("job_title")), safe_csv(r.get("job_url")),
                safe_csv(r.get("posted_at")), safe_csv((r.get("job") or {}).get("description")),
                safe_csv((r.get("client") or {}).get("location")), len(r.get("client_recent_history", []))])
    with db.engine.begin() as c:
        previous = c.execute(select(releases.c.run_id).where(releases.c.run_id == run["id"])).first()
        values = dict(created_at=now(), summary=summary)
        if previous:
            c.execute(update(releases).where(releases.c.run_id == run["id"]).values(**values))
        else:
            c.execute(insert(releases).values(run_id=run["id"], **values))
    return path.relative_to(root).as_posix(), partial


def safe_csv(value):
    value = str(value or "")
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
