"""
Flodata - 14-Day Quality Audit Report (15-min check)
=====================================================
Checks database_14days.db for:
- Full job descriptions
- Client details (country, rating, spend, hires)
- Freelancer reviews / client history contracts with full comments
- Coverage by date
Run: python audit_14day_quality.py
"""

import sqlite3, json, os, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

PROJECT_DIR = Path(__file__).parent.resolve()
DB_14DAYS   = PROJECT_DIR / "output" / "database_14days.db"


def check():
    if not DB_14DAYS.exists():
        print("database_14days.db not found!"); return

    conn = sqlite3.connect(DB_14DAYS, timeout=15)
    rows = conn.execute("SELECT job_id, job_json FROM jobs").fetchall()
    conn.close()

    total = len(rows)
    if total == 0:
        print("DB is empty!"); return

    TODAY = datetime.now(timezone.utc).date()
    DATE_START = TODAY - timedelta(days=14)

    # ── Counters ─────────────────────────────────────────────────────────────
    by_date        = defaultdict(int)
    has_desc       = 0
    has_client     = 0
    has_history    = 0
    has_reviews    = 0      # at least one review with comment text
    total_hist     = 0
    total_reviews  = 0
    missing_desc   = []
    missing_client = []
    sample_jobs    = []     # 5 random samples with full data

    import random
    sample_indices = set(random.sample(range(total), min(5, total)))

    for idx, (jid, raw) in enumerate(rows):
        try:
            d = json.loads(raw)
        except Exception:
            continue

        # Date bucketing
        dt = (d.get("posted_at") or d.get("job_posted_at") or "")[:10]
        if dt:
            by_date[dt] += 1

        # Description
        desc = d.get("description") or d.get("job_description") or d.get("description_snippet") or ""
        if desc and len(str(desc).strip()) > 100:
            has_desc += 1
        elif len(rows) < 100 or idx < 20:
            missing_desc.append(d.get("job_title", jid)[:50])

        # Client details
        client = d.get("client") or {}
        if isinstance(client, str):
            try:
                client = json.loads(client)
            except Exception:
                client = {}
        client_country = (
            client.get("country") or client.get("client_country") or
            d.get("client_country") or d.get("client_location") or ""
        )
        client_rating = (
            client.get("rating") or client.get("client_rating") or
            d.get("client_rating") or ""
        )
        if client_country or client_rating:
            has_client += 1
        else:
            missing_client.append(d.get("job_title", jid)[:50])

        # Client history / contracts
        history = d.get("client_recent_history") or []
        if isinstance(history, str):
            try:
                history = json.loads(history)
            except Exception:
                history = []
        if history:
            has_history += 1
            total_hist += len(history)

            # Count reviews with actual comment text
            for h in history:
                if not isinstance(h, dict):
                    continue
                comment = (
                    h.get("client_feedback") or h.get("review_text") or
                    h.get("feedback") or h.get("comment") or
                    h.get("freelancer_feedback") or h.get("review") or ""
                )
                if comment and len(str(comment).strip()) > 10:
                    has_reviews += 1
                    total_reviews += 1
                    break  # count job as having reviews once

        # Sample data
        if idx in sample_indices:
            sample_jobs.append({
                "job_id":    jid,
                "title":     d.get("job_title", "")[:60],
                "date":      dt,
                "desc_len":  len(str(desc)),
                "client_country": client_country,
                "client_rating":  client_rating,
                "client_spend":   client.get("total_spent") or client.get("spend") or d.get("client_total_spend",""),
                "client_hires":   client.get("hires") or d.get("client_hires",""),
                "history_count":  len(history),
                "has_review_comment": has_reviews > 0,
                "sample_review": next(
                    (str(h.get("client_feedback") or h.get("review_text") or h.get("feedback") or
                         h.get("comment") or "")[:200]
                     for h in history if isinstance(h, dict)
                     if (h.get("client_feedback") or h.get("review_text") or
                         h.get("feedback") or h.get("comment"))),
                    "— no review text —"
                ),
            })

    # ── Print report ──────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"  FLODATA 14-DAY QUALITY AUDIT — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print(f"\n  Total jobs in DB:       {total:,}")
    print(f"  Full description:       {has_desc:,} / {total:,}  ({has_desc*100//total if total else 0}%)")
    print(f"  Client details:         {has_client:,} / {total:,}  ({has_client*100//total if total else 0}%)")
    print(f"  Client history:         {has_history:,} / {total:,}  ({has_history*100//total if total else 0}%)")
    print(f"  Jobs with review text:  {has_reviews:,} / {total:,}  ({has_reviews*100//total if total else 0}%)")
    print(f"  Total history contracts: {total_hist:,}")
    print(f"  Total review comments:  {total_reviews:,}")

    print(f"\n{'─'*70}")
    print("  COVERAGE BY DATE:")
    print(f"{'─'*70}")
    for dt in sorted(by_date.keys(), reverse=True):
        bar = "█" * (by_date[dt] // 50)
        print(f"  {dt}:  {by_date[dt]:>5,}  {bar}")

    print(f"\n{'─'*70}")
    print("  SAMPLE JOBS (5 random):")
    print(f"{'─'*70}")
    for s in sample_jobs:
        print(f"\n  Title:          {s['title']}")
        print(f"  Date:           {s['date']}")
        print(f"  Desc length:    {s['desc_len']} chars")
        print(f"  Client country: {s['client_country'] or '—'}")
        print(f"  Client rating:  {s['client_rating'] or '—'}")
        print(f"  Client spend:   {s['client_spend'] or '—'}")
        print(f"  Client hires:   {s['client_hires'] or '—'}")
        print(f"  History jobs:   {s['history_count']}")
        print(f"  Sample review:  {s['sample_review'][:150]}")

    if missing_desc[:5]:
        print(f"\n{'─'*70}")
        print(f"  MISSING DESCRIPTIONS (first 5):")
        for t in missing_desc[:5]:
            print(f"    - {t}")

    if missing_client[:5]:
        print(f"\n{'─'*70}")
        print(f"  MISSING CLIENT DATA (first 5):")
        for t in missing_client[:5]:
            print(f"    - {t}")

    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    check()
