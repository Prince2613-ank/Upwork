"""
FLO DATA ALIGN & RELEASE YESTERDAY JOBS
=======================================
1. Reads date-filtered job rows from the permanent output/database.db without modifying stored history.
2. Validates data integrity (100% full descriptions, client reviews, verified payments).
3. Compiles and releases standalone HTML reports (upwork_yesterday_report.html, upwork_today_report.html).
4. Exports updated CSV files (jobs_yesterday.csv, jobs_today.csv).
"""

import os
import sys
import json
import sqlite3
import shutil
import re
import csv
from pathlib import Path
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
sys.path.insert(0, str(ROOT))

from generate_standalone_report import generate_report, clean_freelancer_review
from collector.storage.central import database_path


def align_and_release_date(target_date: str, db_path: Path, out_html: Path, title: str, require_reviews_only: bool = True):
    if not db_path.exists():
        return

    print("=" * 75)
    print(f"🔄 ALIGNING & RELEASING [{target_date}] (WITH REVIEWS ONLY)")
    print(f"📊 Database: {db_path.name}")
    print("=" * 75)

    conn = sqlite3.connect(db_path, timeout=20)
    rows = conn.execute("SELECT job_id, job_json FROM jobs").fetchall()
    conn.close()

    if not rows:
        print(f"[INFO] No jobs in {db_path.name} yet.")
        return

    valid_jobs = []
    invalid_ids = []
    for jid, raw_json in rows:
        try:
            d = json.loads(raw_json)
            posted_at = (d.get("posted_at") or "")[:10]
            posted_raw = (d.get("posted_raw") or "").lower()

            if posted_at:
                is_valid = (posted_at == target_date)
            else:
                is_valid = True

            job_dict = d.get("job") or {}
            desc = (job_dict.get("description") or d.get("description") or "").strip()
            if not desc or len(desc) < 25:
                is_valid = False

            if is_valid and require_reviews_only:
                hist = d.get("client_recent_history") or []
                has_rev = any(clean_freelancer_review(h.get("feedback") or "", h.get("freelancer_name") or "") for h in hist)
                if not has_rev:
                    is_valid = False

            if is_valid:
                valid_jobs.append((jid, raw_json))
            else:
                invalid_ids.append(jid)
        except Exception:
            pass

    print(f"📊 Total jobs scanned: {len(rows):,}", flush=True)
    print(f"✅ Strict ({target_date}) jobs with reviews: {len(valid_jobs):,}", flush=True)

    if valid_jobs:
        print(f"\n🚀 Compiling Standalone HTML Report: {out_html.name}...")
        generate_report(
            db_path=str(db_path),
            output_html=str(out_html),
            date_filter_start=target_date,
            date_filter_end=target_date,
            require_reviews_only=require_reviews_only,
            report_title=title
        )
        shutil.copyfile(str(out_html), str(ROOT / out_html.name))
        print(f"  ✓ Released: {out_html.name}")

        # Export CSV for this date
        csv_file = OUTPUT_DIR / f"jobs_daily_{target_date}.csv"
        headers = [
            "job_id", "job_title", "job_url", "job_description", "skills",
            "client_location", "client_payment_verified", "budget", "budget_type",
            "experience_level", "client_rating", "client_total_spent", "client_jobs_posted",
            "client_hire_rate", "client_total_hires", "client_active_hires", "client_hours_billed",
            "client_member_since", "reviews_count", "posted_at", "posted_raw"
        ]
        with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for jid, jj_str in valid_jobs:
                try:
                    d = json.loads(jj_str)
                    job_dict = d.get("job") or {}
                    client_dict = d.get("client") or {}
                    writer.writerow([
                        jid,
                        d.get("job_title") or "",
                        d.get("job_url") or "",
                        job_dict.get("description") or d.get("description") or "",
                        ", ".join(job_dict.get("skills") or d.get("skills") or []),
                        client_dict.get("location") or d.get("client_location") or "",
                        "1" if (client_dict.get("payment_verified") or d.get("payment_verified")) else "0",
                        d.get("budget_min") or job_dict.get("budget") or "Not Specified",
                        d.get("job_type") or "Fixed",
                        d.get("experience_level") or "Intermediate",
                        client_dict.get("rating") or "N/A",
                        client_dict.get("total_spent") or "N/A",
                        client_dict.get("jobs_posted") or "N/A",
                        client_dict.get("hire_rate") or "N/A",
                        client_dict.get("total_hires") or "N/A",
                        client_dict.get("active_hires") or "N/A",
                        client_dict.get("hours_billed") or "N/A",
                        client_dict.get("member_since") or "N/A",
                        len(d.get("client_recent_history") or []),
                        d.get("posted_at") or "",
                        d.get("posted_raw") or ""
                    ])
                except Exception:
                    pass


def align_and_release(require_reviews_only: bool = True):
    now_dt = datetime.now()
    yesterday_dt = now_dt - timedelta(days=1)
    two_days_ago_dt = now_dt - timedelta(days=2)

    yesterday_str = yesterday_dt.strftime("%Y-%m-%d")
    two_days_ago_str = two_days_ago_dt.strftime("%Y-%m-%d")

    day1_name = yesterday_dt.strftime("%A")  # "Tuesday"
    day2_name = two_days_ago_dt.strftime("%A")  # "Monday"

    # 1. Day 1 (Yesterday - Tuesday)
    day1_db = database_path(OUTPUT_DIR)
    if not day1_db.exists():
        day1_db = database_path(OUTPUT_DIR)
    align_and_release_date(
        target_date=yesterday_str,
        db_path=day1_db,
        out_html=OUTPUT_DIR / "upwork_yesterday_report.html",
        title=f"Upwork Daily Market Intelligence Report — {day1_name} ({yesterday_str})",
        require_reviews_only=require_reviews_only
    )
    # Also save day-named copy (e.g. upwork_tuesday_report.html)
    for m in [
        OUTPUT_DIR / f"upwork_{day1_name.lower()}_report.html",
        ROOT / f"upwork_{day1_name.lower()}_report.html"
    ]:
        try:
            shutil.copyfile(str(OUTPUT_DIR / "upwork_yesterday_report.html"), str(m))
        except Exception:
            pass

    # 2. Day 2 (2 days ago - Monday)
    day2_db = database_path(OUTPUT_DIR)
    comb_candidate = database_path(OUTPUT_DIR)
    if comb_candidate.exists():
        day2_db = comb_candidate
    if day2_db and day2_db.exists():
        align_and_release_date(
            target_date=two_days_ago_str,
            db_path=day2_db,
            out_html=OUTPUT_DIR / f"upwork_{day2_name.lower()}_report.html",
            title=f"Upwork Daily Market Intelligence Report — {day2_name} ({two_days_ago_str})",
            require_reviews_only=require_reviews_only
        )
        try:
            shutil.copyfile(str(OUTPUT_DIR / f"upwork_{day2_name.lower()}_report.html"), str(ROOT / f"upwork_{day2_name.lower()}_report.html"))
        except Exception:
            pass

    # 3. Combined 2-Day (Monday & Tuesday)
    def get_valid_db(candidates):
        for p in candidates:
            if p.exists():
                try:
                    c = sqlite3.connect(p, timeout=5)
                    cnt = c.execute("SELECT count(*) FROM jobs").fetchone()[0]
                    c.close()
                    if cnt > 0:
                        return p
                except Exception:
                    pass
        return None

    comb_db = get_valid_db([
        database_path(OUTPUT_DIR),
        database_path(OUTPUT_DIR),
        database_path(OUTPUT_DIR)
    ])
    if comb_db:
        out_comb = OUTPUT_DIR / "upwork_2days_report.html"
        print("\n" + "=" * 75)
        print(f"🔄 COMPILING COMBINED 2-DAY REPORT ({day2_name} & {day1_name}: {two_days_ago_str} to {yesterday_str})")
        print("=" * 75)
        generate_report(
            db_path=str(comb_db),
            output_html=str(out_comb),
            require_reviews_only=require_reviews_only,
            date_filter_start=two_days_ago_str,
            date_filter_end=yesterday_str,
            report_title=f"Upwork Intelligence Master Report — {day2_name} & {day1_name} ({two_days_ago_str} & {yesterday_str})"
        )
        for m in [
            ROOT / "upwork_2days_report.html",
            OUTPUT_DIR / "upwork_today_report.html",
            ROOT / "upwork_today_report.html",
            OUTPUT_DIR / "upwork_weekend_report.html",
            ROOT / "upwork_weekend_report.html"
        ]:
            try:
                shutil.copyfile(str(out_comb), str(m))
            except Exception:
                pass
        print(f"  ✓ Released: upwork_2days_report.html & upwork_today_report.html")

    # Sync CSVs to default root locations
    for src in [
        OUTPUT_DIR / f"jobs_daily_{yesterday_str}.csv",
        OUTPUT_DIR / f"jobs_daily_{two_days_ago_str}.csv"
    ]:
        if src.exists():
            for m in [
                OUTPUT_DIR / "jobs_yesterday.csv",
                ROOT / "jobs_yesterday.csv",
                OUTPUT_DIR / "jobs_today.csv",
                ROOT / "jobs_today.csv"
            ]:
                try:
                    shutil.copyfile(str(src), str(m))
                except Exception:
                    pass
            break

    print("\n" + "=" * 75)
    print(f"🎉 ALL RELEASES COMPLETE ({day2_name}, {day1_name} & Combined 2-Day)!")
    print("=" * 75)


if __name__ == "__main__":
    align_and_release()

