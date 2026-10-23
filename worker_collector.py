"""
Individual Worker Collector.
Called by run_parallel.py — runs independently with its own Chrome instance.
Handles a specific page range and writes to its own output directory.
"""

import argparse
import sys
import json
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent))


def main():
    parser = argparse.ArgumentParser(description="Upwork Worker Collector")
    parser.add_argument("--config", required=True, help="Path to worker config JSON")
    parser.add_argument("--worker-id", type=int, required=True)
    parser.add_argument("--start-page", type=int, required=True)
    parser.add_argument("--end-page", type=int, required=True)
    parser.add_argument("--cdp-port", type=int, required=True)
    parser.add_argument("--dashboard-port", type=int, default=8000)
    args = parser.parse_args()

    print(f"[Worker {args.worker_id}] Starting — pages {args.start_page}-{args.end_page} via CDP port {args.cdp_port}")

    # Override settings from worker config
    from collector.config.settings import settings
    config_data = json.loads(Path(args.config).read_text(encoding="utf-8"))
    settings.cdp_url = f"http://127.0.0.1:{args.cdp_port}"
    settings.output_directory = str(config_data["output_directory"])
    settings.output_path.mkdir(parents=True, exist_ok=True)

    # Import and run the engine with dedicated worker tab
    from collector.main import CollectorEngine

    engine = CollectorEngine(source_mode="auto", new_tab=True)
    jobs, summary = engine.run_full_collection(
        resume=False,
        max_pages=args.end_page,
        start_page_override=args.start_page,
    )

    print(f"[Worker {args.worker_id}] DONE — {len(jobs)} jobs collected")
    print(f"[Worker {args.worker_id}] Summary: {summary}")


if __name__ == "__main__":
    main()
