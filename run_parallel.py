"""
Parallel Upwork Collector Coordinator — Single Chrome 3-Tab Mode.
Runs 3 independent worker processes simultaneously connected to the user's
existing authorized Chrome session (port 9222).
Each worker operates in its own dedicated browser tab.
Zero extra logins or profile configuration required!
"""

import subprocess
import sys
import json
import time
import os
import shutil
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(__file__).parent
OUTPUT_DIR = PROJECT_DIR / "output"
CDP_PORT = 9222
TOTAL_PAGES = 100
NUM_WORKERS = 2


def check_chrome_ready(port: int = CDP_PORT) -> bool:
    """Check if Chrome is running on CDP port 9222."""
    import urllib.request
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=3)
        return True
    except Exception:
        return False


def get_resume_page() -> int:
    """Read last completed page from main checkpoint."""
    ckpt_path = OUTPUT_DIR / "checkpoint.json"
    if ckpt_path.exists():
        try:
            d = json.loads(ckpt_path.read_text(encoding="utf-8"))
            last_page = d.get("last_completed_page", 0)
            if last_page > 0:
                print(f"[Coordinator] Detected existing checkpoint: {last_page} pages completed.")
                return last_page + 1
        except Exception as e:
            print(f"[Coordinator] Checkpoint read note: {e}")
    return 1


def calculate_worker_ranges(start_page: int, end_page: int, num_workers: int):
    """Distribute page ranges evenly across workers."""
    total = end_page - start_page + 1
    chunk = total // num_workers
    ranges = []
    curr = start_page
    for i in range(num_workers):
        nxt = curr + chunk - 1 if i < num_workers - 1 else end_page
        ranges.append((curr, nxt))
        curr = nxt + 1
    return ranges


def generate_worker_config(worker_id: int, start_page: int, end_page: int) -> Path:
    """Generate worker_config.json for a worker subprocess."""
    worker_output = OUTPUT_DIR / f"worker_{worker_id}"
    worker_output.mkdir(parents=True, exist_ok=True)

    base_config = json.loads((PROJECT_DIR / "config.json").read_text(encoding="utf-8"))
    base_config["cdp_url"] = f"http://127.0.0.1:{CDP_PORT}"
    base_config["output_directory"] = str(worker_output)
    base_config["start_page"] = start_page
    base_config["end_page"] = end_page

    config_path = worker_output / "worker_config.json"
    config_path.write_text(json.dumps(base_config, indent=2), encoding="utf-8")
    return config_path


def run_worker(worker_id: int, start_page: int, end_page: int):
    """Launch worker subprocess."""
    config_path = generate_worker_config(worker_id, start_page, end_page)
    log_path = OUTPUT_DIR / f"worker_{worker_id}" / "worker.log"

    cmd = [
        sys.executable, "worker_collector.py",
        "--config", str(config_path),
        "--worker-id", str(worker_id),
        "--start-page", str(start_page),
        "--end-page", str(end_page),
        "--cdp-port", str(CDP_PORT),
    ]

    print(f"  Starting Worker {worker_id}: Pages {start_page}-{end_page} (Tab {worker_id})...")
    with open(log_path, "w", encoding="utf-8", errors="replace") as lf:
        proc = subprocess.Popen(cmd, cwd=str(PROJECT_DIR), stdout=lf, stderr=lf)

    return proc


def merge_outputs(worker_configs: list):
    """Merge all worker outputs and copy raw HTML files into main output."""
    print("\n[Coordinator] Merging all collection outputs...")
    all_jobs = {}
    total_pages = 0

    # 1. Read existing jobs from main jobs.json
    main_jobs_file = OUTPUT_DIR / "jobs.json"
    if main_jobs_file.exists():
        try:
            data = json.loads(main_jobs_file.read_text(encoding="utf-8"))
            for job in data.get("jobs", []):
                jid = job.get("job_id") or job.get("job_url")
                if jid:
                    all_jobs[jid] = job
            total_pages += data.get("scrape_run", {}).get("pages_processed", 0)
            print(f"  Main dataset (previous): {len(all_jobs)} jobs")
        except Exception as e:
            print(f"  Main dataset read note: {e}")

    # 2. Read each worker's output and copy raw HTML
    main_raw_html = OUTPUT_DIR / "raw_html"
    main_raw_html.mkdir(parents=True, exist_ok=True)

    for w in worker_configs:
        w_id = w["id"]
        w_dir = OUTPUT_DIR / f"worker_{w_id}"
        w_jobs_file = w_dir / "jobs.json"
        w_raw_html = w_dir / "raw_html"

        if w_raw_html.exists():
            for f in w_raw_html.glob("*.html"):
                dest = main_raw_html / f.name
                if not dest.exists():
                    try:
                        shutil.copy2(f, dest)
                    except Exception:
                        pass

        if w_jobs_file.exists():
            try:
                data = json.loads(w_jobs_file.read_text(encoding="utf-8"))
                w_jobs = data.get("jobs", [])
                for job in w_jobs:
                    jid = job.get("job_id") or job.get("job_url")
                    if jid:
                        all_jobs[jid] = job
                pages = data.get("scrape_run", {}).get("pages_processed", 0)
                total_pages += pages
                print(f"  Worker {w_id}: {len(w_jobs)} jobs ({pages} pages)")
            except Exception as e:
                print(f"  Worker {w_id} read note: {e}")

    # 3. Export unified dataset
    merged = {
        "scrape_run": {
            "finished_at": datetime.utcnow().isoformat(),
            "pages_processed": total_pages,
            "jobs_processed": len(all_jobs),
            "mode": "parallel_3x_single_browser",
        },
        "jobs": list(all_jobs.values()),
    }
    main_jobs_file.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")

    # CSV exports
    try:
        from collector.models.schema import CollectedJob
        from collector.storage.csv_export import export_jobs_csv, export_client_history_csv
        # Quick re-export if schema objects available
    except Exception:
        pass

    print(f"\n[Coordinator] MERGE COMPLETE: {len(all_jobs)} total unique jobs saved to {main_jobs_file}")
    return len(all_jobs)


def main():
    print("=" * 65)
    print("  FLODATA PARALLEL COLLECTOR — 2x SPEED (2 WORKERS MODE)")
    print("=" * 65)
    print()

    # Step 1: Check Chrome on port 9222
    print(f"Checking Chrome on port {CDP_PORT}...", end=" ")
    if not check_chrome_ready():
        print("NOT FOUND!")
        print(f"\nERROR: Chrome is not running on port {CDP_PORT}.")
        print("Please ensure your Chrome browser is open.")
        sys.exit(1)
    print("READY (Connected to authorized Upwork session)")

    # Step 2: Determine start page
    start_page = get_resume_page()
    if start_page > TOTAL_PAGES:
        print(f"\nAll {TOTAL_PAGES} pages already collected!")
        sys.exit(0)

    ranges = calculate_worker_ranges(start_page, TOTAL_PAGES, NUM_WORKERS)
    worker_configs = []
    for i, (sp, ep) in enumerate(ranges, 1):
        worker_configs.append({"id": i, "start_page": sp, "end_page": ep})

    print(f"\nStarting {NUM_WORKERS} parallel worker tabs on Port {CDP_PORT}:")
    for w in worker_configs:
        print(f"  Worker {w['id']}: Pages {w['start_page']} to {w['end_page']}")
    print()

    # Step 3: Launch worker processes (staggered)
    processes = []
    for w in worker_configs:
        proc = run_worker(w["id"], w["start_page"], w["end_page"])
        processes.append((w, proc))
        time.sleep(8)  # Stagger to avoid simultaneous initial page load

    print(f"\n[Coordinator] All {len(processes)} workers active! Collecting at 3x speed...")
    print("  Logs: output/worker_N/worker.log")
    print("  Dashboard: http://127.0.0.1:8000")
    print()

    # Step 4: Monitor progress
    start_time = time.time()
    while processes:
        time.sleep(12)
        still_running = []
        status_line = []
        for w, proc in processes:
            ret = proc.poll()
            if ret is None:
                ckpt = OUTPUT_DIR / f"worker_{w['id']}" / "checkpoint.json"
                jobs = 0
                page = w["start_page"]
                if ckpt.exists():
                    try:
                        d = json.loads(ckpt.read_text())
                        jobs = len(d.get("processed_job_ids", []))
                        page = d.get("last_completed_page", w["start_page"])
                    except Exception:
                        pass
                status_line.append(f"W{w['id']}: P{page}/{w['end_page']} ({jobs} jobs)")
                still_running.append((w, proc))
            else:
                print(f"  [Worker {w['id']}] Finished (exit code {ret})")

        if status_line:
            elapsed = int(time.time() - start_time)
            print(f"  [{elapsed//60}m{elapsed%60:02d}s] " + " | ".join(status_line))

        processes = still_running

    # Step 5: Merge all results
    total = merge_outputs(worker_configs)
    elapsed = int(time.time() - start_time)
    print(f"\nParallel collection complete in {elapsed//60}m {elapsed%60}s!")
    print(f"Total Unique Jobs: {total}")
    print("Run 'python main.py --dashboard' to explore all collected jobs.")


if __name__ == "__main__":
    main()
