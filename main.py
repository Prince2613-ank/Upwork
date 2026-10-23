"""
Flodata Analytics: Upwork Market-Intelligence Data Collection System.
Main CLI Entrypoint.
Supports Section 20 3-Job Test Mode, Full 1-Month Collection, Resume, and Local Dashboard.
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from collector.config.settings import settings
from collector.main import CollectorEngine
from collector.logging.logger import logger


def launch_dashboard(port: int = 8000, host: str = "127.0.0.1"):
    """Launches Section 17 interactive local web dashboard."""
    import uvicorn
    print(f"\n========================================================")
    print(f"  UPWORK INTELLIGENCE COLLECTOR LOCAL DASHBOARD")
    print(f"  Access URL: http://{host}:{port}")
    print(f"========================================================\n")
    uvicorn.run("collector.dashboard.app:app", host=host, port=port, reload=False)


def main():
    parser = argparse.ArgumentParser(
        description="Upwork One-Month Job Intelligence Collector — Flodata Analytics",
    )
    parser.add_argument(
        "--test-3",
        action="store_true",
        help="Run mandatory Section 20 3-job Test Mode with field validation metrics",
    )
    parser.add_argument(
        "--poc",
        action="store_true",
        help="Run 5-job proof of concept",
    )
    parser.add_argument(
        "--test-50",
        action="store_true",
        help="Run 50-job multi-page verification test",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run complete 1-month collection governed by rolling date cutoff",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume collection from latest checkpoint.json",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Launch local web dashboard UI",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9222,
        help="Chrome remote debugging port (default: 9222). Use a different port to scrape with multiple accounts simultaneously.",
    )
    parser.add_argument(
        "--new-tab",
        action="store_true",
        help="Force open a new tab instead of attaching to the current one.",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Start a clean 1-month collection from page 1 (clears previous run state)",
    )
    parser.add_argument(
        "--source",
        choices=["auto", "browser", "mock"],
        default="auto",
        help="Data source mode: 'browser' (attaches to Chrome CDP), 'mock' (test fixtures), or 'auto'",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=None,
        help="Starting search page number (e.g. 50 to collect older jobs)",
    )
    parser.add_argument(
        "--min-days",
        type=float,
        default=None,
        help="Minimum job age in days (e.g. 6 to skip jobs newer than 6 days)",
    )
    parser.add_argument(
        "--max-days",
        type=float,
        default=None,
        help="Maximum job age in days (e.g. 15 to skip jobs older than 15 days)",
    )
    parser.add_argument(
        "--loc-index",
        type=int,
        default=None,
        help="Specific target location index (e.g. 0 for Europe). If omitted, queries ALL 25 target locations combined in a single search URL.",
    )
    parser.add_argument(
        "--loc-indices",
        type=str,
        default=None,
        help="Range or comma-separated list of target location indices to process (e.g. '0-12' or '13-24' or '0,1,2'). Enables parallel scraping across regions.",
    )
    parser.add_argument(
        "--single-location",
        action="store_true",
        help="Process locations sequentially one by one instead of combining all 25 target locations into one URL.",
    )
    parser.add_argument(
        "--page-step",
        type=int,
        default=1,
        help="Page increment step (e.g. 2 for odd/even interleaved parallel scraping)",
    )
    parser.add_argument(
        "--odd-days",
        action="store_true",
        help="Sequentially collect all odd days: 1, 3, 5, 7, ..., up to 29 days ago.",
    )
    parser.add_argument(
        "--even-days",
        action="store_true",
        help="Sequentially collect all even days: 2, 4, 6, 8, ..., up to 30 days ago.",
    )
    parser.add_argument(
        "--days",
        type=str,
        default=None,
        help="Custom comma-separated list of target days ago to collect sequentially (e.g. '1,3,5' or '2,4,6').",
    )
    parser.add_argument(
        "--dash-port",
        type=int,
        default=8000,
        help="Port for local web dashboard (default: 8000)",
    )

    args = parser.parse_args()

    if args.dashboard:
        launch_dashboard(port=args.dash_port)
        return

    if args.port != 9222:
        settings.cdp_url = f"http://127.0.0.1:{args.port}"

    from collector.checkpoint.checkpoint_manager import CheckpointManager
    engine = CollectorEngine(source_mode=args.source, new_tab=args.new_tab)
    # Isolate checkpoint file per worker port to prevent race conditions during parallel runs
    engine.checkpoint_mgr = CheckpointManager(filename=f"checkpoint_port_{args.port}.json")

    # Stepped-days mode (Odd days / Even days sequential collection)
    if args.odd_days or args.even_days or args.days:
        if args.odd_days:
            days_list = [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29]
            mode_label = "ODD DAYS (1, 3, 5, ... 29 days ago)"
        elif args.even_days:
            days_list = [2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30]
            mode_label = "EVEN DAYS (2, 4, 6, ... 30 days ago)"
        else:
            days_list = [int(d.strip()) for d in args.days.split(",") if d.strip()]
            mode_label = f"CUSTOM DAYS ({days_list})"

        # If resuming, automatically skip days that already have substantial collected data
        if args.resume:
            import csv
            from datetime import datetime, timezone
            covered_days = set()
            try:
                with open("output/jobs.csv", "r", encoding="utf-8-sig") as f:
                    r = csv.DictReader(f)
                    now_utc = datetime.now(timezone.utc)
                    counts = {}
                    for row in r:
                        p = row.get("posted_at")
                        if p and "T" in p:
                            try:
                                dt = datetime.fromisoformat(p)
                                d = int((now_utc - dt).total_seconds() / 86400)
                                counts[d] = counts.get(d, 0) + 1
                            except Exception:
                                pass
                    for d, c in counts.items():
                        if c >= 300:  # already thoroughly completed day
                            covered_days.add(d)
            except Exception:
                pass

            remaining_days = [d for d in days_list if d not in covered_days]
            if remaining_days:
                print(f"[RESUME] Days already completed: {sorted(list(covered_days.intersection(days_list)))}")
                print(f"[RESUME] Resuming from first incomplete day: {remaining_days[0]} (remaining: {remaining_days})")
                days_list = remaining_days

        def estimate_day_start_page(target_day: int) -> int:
            """Estimates the search page where jobs of target_day ago start appearing."""
            if target_day <= 0:
                return 1
            elif target_day == 1:
                return 20
            elif target_day == 2:
                return 45
            elif target_day == 3:
                return 68
            elif target_day == 4:
                return 85
            else:
                return 90

        initial_p = args.start_page or estimate_day_start_page(days_list[0] if days_list else 1)
        current_p = initial_p
        print(f"\n{'='*70}")
        print(f"  STEPPED-DAYS INTELLIGENCE COLLECTOR: {mode_label}")
        print(f"  Worker Port: {args.port} | Target Days: {days_list}")
        print(f"  Initial Search Page: {current_p} (Direct Fast-Forward Jump)")
        print(f"{'='*70}\n")

        total_collected = 0
        try:
            for idx, day in enumerate(days_list):
                min_d = max(0.0, float(day) - 0.05)
                max_d = float(day + 1) + 0.05
                # For each step, if starting from page 1 would be too slow, use the day's estimated page
                if idx > 0 and current_p == 1:
                    current_p = estimate_day_start_page(day)
                print(f"\n>>> [STEP {idx+1}/{len(days_list)}] TARGETING DAY {day} AGO (Age: {min_d:.2f} to {max_d:.2f} days) | Starting Page {current_p} <<<")

                try:
                    jobs, summary = engine.run_full_collection(
                        resume=False,
                        start_page_override=current_p,
                        min_age_days=min_d,
                        max_age_days=max_d,
                        combined_locations=True,
                        page_step=args.page_step,
                        keep_browser_open=True,
                    )
                    total_collected += len(jobs)
                    print(f">>> Collected {len(jobs)} jobs for Day {day} (Total this run: {total_collected}).")
                except Exception as ex:
                    print(f"\n[WARNING] Note on Day {day} ago: {ex}. Continuing to next day...")

                ckpt = engine.checkpoint_mgr.load_checkpoint()
                last_p = ckpt.last_completed_page if ckpt and ckpt.last_completed_page > 0 else current_p
                if last_p >= 100:
                    current_p = 1
                else:
                    current_p = max(1, last_p - 1)
                print(f"\n>>> [COMPLETED DAY {day} AGO] Finished scanning at Page {last_p}.")
                print(f">>> Advancing to next target day starting from Page {current_p}! <<<\n")
        finally:
            if engine.browser_mgr:
                engine.browser_mgr.close()

        print(f"\n{'='*70}")
        print(f"  COMPLETED ALL TARGET DAYS IN SEQUENCE: {days_list}")
        print(f"  Total jobs collected across all steps: {total_collected}")
        print(f"{'='*70}\n")
        return

    # Regional parallel collection mode using assigned location index chunks
    if args.loc_indices:
        if "-" in args.loc_indices:
            start_i, end_i = map(int, args.loc_indices.split("-"))
            loc_indices_list = list(range(start_i, end_i + 1))
        else:
            loc_indices_list = [int(x.strip()) for x in args.loc_indices.split(",") if x.strip()]

        loc_names = [settings.target_locations[i] for i in loc_indices_list if i < len(settings.target_locations)]
        print(f"\n{'='*70}")
        print(f"  REGIONAL 1-MONTH PARALLEL COLLECTOR (Worker Port {args.port})")
        print(f"  Target Location Indices: {loc_indices_list}")
        print(f"  Regions Covered: {', '.join(loc_names)}")
        print(f"  Existing Database Jobs: {engine.db.job_count} (Protected & Deduplicated)")
        print(f"{'='*70}\n")
        jobs, summary = engine.run_full_collection(
            resume=args.resume,
            start_page_override=args.start_page or 1,
            location_indices=loc_indices_list,
            combined_locations=False,
            page_step=args.page_step,
            keep_browser_open=True,
        )
        print(f"\nCompleted regional collection: {len(jobs)} jobs processed.")
        return

    if args.min_days is not None or args.max_days is not None or args.start_page or args.page_step > 1:
        start_p = args.start_page or 1
        loc_idx = args.loc_index
        min_d = args.min_days
        max_d = args.max_days
        step_val = args.page_step
        loc_label = f"Loc {loc_idx} ({settings.target_locations[loc_idx]})" if loc_idx is not None else "All 25 Locations Combined"
        print(f"\n=== Starting Collection (Worker Port {args.port} | Step: +{step_val} | Age: {min_d or 0}-{max_d or 'cutoff'} days | {loc_label} | Page {start_p}) ===")
        jobs, summary = engine.run_full_collection(
            resume=args.resume,
            start_page_override=start_p,
            start_location_index_override=loc_idx,
            min_age_days=min_d,
            max_age_days=max_d,
            combined_locations=(loc_idx is None and not args.single_location),
            page_step=step_val,
        )
        print(f"\nCompleted collection of {len(jobs)} jobs.")
    elif args.test_3:
        engine.run_test_3_jobs()
    elif args.poc:
        # 5-job run
        print("\n=== Running 5-Job Verification ===")
        jobs, summary = engine.run_full_collection(resume=args.resume, max_pages=1)
        print(f"\nProcessed {len(jobs)} jobs. Check {summary['exports']['json']}")
    elif args.test_50:
        # 50-job run
        print("\n=== Running 50-Job Verification ===")
        jobs, summary = engine.run_full_collection(resume=args.resume, max_pages=2)
        print(f"\nProcessed {len(jobs)} jobs. Check {summary['exports']['json']}")
    elif args.fresh:
        print("\n=== Starting Fresh 1-Month Collection (Single-Tab Safe Mode) ===")
        import shutil
        target_dir = settings.output_path
        # Clean current output files (safe backup is in output_backup_700jobs)
        for fname in ["checkpoint.json", "jobs.json", "jobs.csv", "client_history.csv", "run_summary.json"]:
            fpath = target_dir / fname
            if fpath.exists():
                fpath.unlink()
        raw_dir = target_dir / "raw_html"
        if raw_dir.exists():
            shutil.rmtree(raw_dir, ignore_errors=True)
        raw_dir.mkdir(parents=True, exist_ok=True)
        jobs, summary = engine.run_full_collection(resume=False)
        print(f"\nFresh collection complete: {len(jobs)} jobs.")
    elif args.full:
        print("\n=== Running Full 1-Month Date-Cutoff Collection ===")
        jobs, summary = engine.run_full_collection(resume=args.resume)
        print(f"\nCompleted collection of {len(jobs)} jobs. Summary saved to {summary['exports']['summary']}")
    elif args.resume:
        print("\n=== Resuming Interrupted Run from checkpoint.json ===")
        jobs, summary = engine.run_full_collection(resume=True)
        print(f"\nResumed run completed: {len(jobs)} jobs.")
    else:
        # Section 20 requirement: default to 3-job TEST MODE first!
        logger.info("No run flag specified. Defaulting to mandatory Section 20 3-Job TEST MODE.")
        engine.run_test_3_jobs()


if __name__ == "__main__":
    main()
