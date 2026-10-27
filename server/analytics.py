"""Read-only aggregates of saved jobs for the dashboard overview."""
import re
import time
from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from server.db import ACTIVE, jobs, queue, runs


def current_context(db, timezone, reference=None):
    """Follow an unfinished run; otherwise show only a run started today locally."""
    local = datetime.fromtimestamp(reference if reference is not None else time.time(), ZoneInfo(timezone))
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    with db.engine.connect() as c:
        run = c.execute(select(runs).where(runs.c.status.in_(ACTIVE))
                        .order_by(runs.c.created_at.desc()).limit(1)).mappings().first()
        if not run:
            run = c.execute(select(runs).where(runs.c.created_at >= midnight)
                            .order_by(runs.c.created_at.desc()).limit(1)).mappings().first()
    if run and run['status'] == 'cleaned':
        run = None  # Do not repopulate today's overview from an older run after cleaning.
    return {"day": local.date().isoformat(), "timezone": timezone,
            "run_id": run["id"] if run else None,
            "start": run["start_date"] if run else None,
            "end": run["end_date"] if run else None}


def job_source(run_id=None):
    if run_id is None:
        return jobs
    # Run snapshots prevent older canonical records from inflating this collection.
    return select(jobs.c.id, jobs.c.posted_date, queue.c.result.label("data"),
                  jobs.c.raw_path, jobs.c.first_seen, jobs.c.last_seen).join(
        queue, queue.c.job_id == jobs.c.id).where(
        queue.c.run_id == run_id, queue.c.status == "done").subquery()
from server.quality import EMPTY_REVIEWS, release_candidate

MONEY = re.compile(r"\$\s*([\d,.]+)\s*([KkMm])?")
PERCENT = re.compile(r"([\d.]+)\s*%")
SPEND_TIERS = ((1e3, "Under $1K"), (1e4, "$1K–10K"), (1e5, "$10K–100K"), (1e6, "$100K–1M"), (float("inf"), "$1M+"))


def money(text):
    match = MONEY.search(str(text or ""))
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    return value * {"k": 1e3, "m": 1e6}.get((match.group(2) or "").lower(), 1)


def percent(text):
    match = PERCENT.search(str(text or ""))
    return float(match.group(1)) if match else None


def spend_tier(amount):
    if amount is None:
        return "Unknown"
    return next(label for limit, label in SPEND_TIERS if amount < limit)


def written(review):
    text = str(review.get("feedback") or "").strip()
    return bool(text) and text.lower().rstrip(".") not in EMPTY_REVIEWS


def timeline(days):
    dated = sorted(d for d in days if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d))
    if not dated:
        return []
    first, last = date.fromisoformat(dated[0]), date.fromisoformat(dated[-1])
    # Fill empty days so gaps are visible, but never expand a sparse multi-year range.
    if (last - first).days > 180:
        return [{"date": d, "count": days[d]} for d in dated]
    span = range((last - first).days + 1)
    return [{"date": (first + timedelta(n)).isoformat(), "count": days.get((first + timedelta(n)).isoformat(), 0)} for n in span]


def summarize(db, start=None, end=None, run_id=None):
    jobs = job_source(run_id)
    statement = select(jobs.c.posted_date, jobs.c.data)
    if start:
        statement = statement.where(jobs.c.posted_date >= start)
    if end:
        statement = statement.where(jobs.c.posted_date <= end)
    days, countries, tiers, checks = Counter(), Counter(), Counter(), Counter()
    total = verified = reviews = 0
    hire_rates = []
    with db.engine.connect() as c:
        for posted, data in c.execute(statement):
            if not isinstance(data, dict) or data.get("_outside_filter"):
                continue
            client = data.get("client") or {}
            location = str(client.get("location") or data.get("client_location") or "")
            total += 1
            days[posted or ""] += 1
            countries[location.split(",")[0].strip() or "Unknown"] += 1
            verified += client.get("payment_verified") is True
            rate = percent(client.get("hire_rate"))
            if rate is not None:
                hire_rates.append(rate)
            tiers[spend_tier(money(client.get("total_spent")))] += 1
            reviews += sum(1 for r in data.get("client_recent_history") or [] if isinstance(r, dict) and written(r))
            checks[release_candidate(data)[1]] += 1
    top = countries.most_common(8)
    others = total - sum(count for _, count in top)
    return {
        "total": total,
        "release_ready": checks["ready"],
        "written_reviews": reviews,
        "payment_verified_pct": round(100 * verified / total, 1) if total else None,
        "avg_hire_rate": round(sum(hire_rates) / len(hire_rates), 1) if hire_rates else None,
        "per_day": timeline(days),
        "countries": top + ([("Other", others)] if others else []),
        "spend_tiers": [(label, tiers[label]) for _, label in SPEND_TIERS] + ([("Unknown", tiers["Unknown"])] if tiers["Unknown"] else []),
        "release_checks": dict(checks),
    }


def speed(db, minutes=60, reference=None, run_id=None, start=None, end=None):
    """Jobs, written reviews and qualified jobs saved in each of the last `minutes` minutes (the last bucket is the minute in progress)."""
    stamp = reference if reference is not None else time.time()
    current = int(stamp // 60) * 60
    first = current - (minutes - 1) * 60
    buckets = {first + 60 * n: {"jobs": 0, "reviews": 0, "qualified": 0} for n in range(minutes)}
    source = job_source(run_id)
    statement = select(source.c.last_seen, source.c.data).where(source.c.last_seen >= first)
    if start:
        statement = statement.where(source.c.posted_date >= start)
    if end:
        statement = statement.where(source.c.posted_date <= end)
    with db.engine.connect() as c:
        for seen, data in c.execute(statement):
            bucket = buckets.get(int(seen // 60) * 60)
            if bucket is None or not isinstance(data, dict):
                continue
            bucket["jobs"] += 1
            bucket["reviews"] += sum(1 for r in data.get("client_recent_history") or [] if isinstance(r, dict) and written(r))
            bucket["qualified"] += release_candidate(data)[1] == "ready"
    points = [{"t": t, **values} for t, values in sorted(buckets.items())]
    finished = points[:-1]  # the minute in progress would understate every rate

    def rate(window, key):
        recent = finished[-window:]
        return round(sum(p[key] for p in recent) / len(recent), 1) if recent else 0
    return {
        "per_minute": points, "now": int(stamp), "current_minute": points[-1],
        "jobs_per_min": {w: rate(w, "jobs") for w in (5, 15, 60)},
        "reviews_per_min": {w: rate(w, "reviews") for w in (5, 15, 60)},
        "total_jobs": sum(p["jobs"] for p in points), "total_reviews": sum(p["reviews"] for p in points),
        "total_qualified": sum(p["qualified"] for p in points),
        "peak": max((p["jobs"] for p in finished), default=0),
    }
