"""
Section 8 & 12: JSON Export Engine.
Exports structured jobs.json adhering to Section 8 schema and run_summary.json (Section 12).
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from collector.models.schema import CollectedJob, ScrapeDataset, ScrapeRunMeta
from collector.config.settings import settings


def export_jobs_json(
    jobs: List[CollectedJob],
    scrape_meta: ScrapeRunMeta,
    output_dir: Optional[Path] = None,
    filename: str = "jobs.json",
    merge: bool = True,
) -> Path:
    """Exports dataset to jobs.json adhering strictly to Section 8, optionally merging across runs.
    Manager requirements:
    - Saves raw HTML per job in output/raw_html/<job_id>.html
    - Links dict (job_url, client_profile_url, reviews_anchor) is included in each job JSON
    - raw_html field is stripped from main jobs.json to keep file size manageable
    """
    target_dir = output_dir or settings.output_path
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / filename

    # Manager requirement: save raw HTML files separately
    raw_html_dir = target_dir / "raw_html"
    raw_html_dir.mkdir(parents=True, exist_ok=True)

    merged_jobs: Dict[str, Dict[str, Any]] = {}
    if merge and out_path.exists():
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                old_data = json.load(f)
            for oj in old_data.get("jobs", []):
                jid = oj.get("job_id") or oj.get("job_url")
                if jid:
                    merged_jobs[jid] = oj
        except Exception:
            pass

    for j in jobs:
        d = j.model_dump()
        jid = d.get("job_id") or d.get("job_url")
        if not jid:
            continue

        # Save raw HTML separately (Manager requirement 1)
        raw_html = d.pop("raw_html", "") or ""
        if raw_html:
            safe_id = jid.replace("~", "").replace("/", "_").replace(":", "_")[:80]
            html_path = raw_html_dir / f"{safe_id}.html"
            if not html_path.exists():
                try:
                    html_path.write_text(raw_html, encoding="utf-8", errors="replace")
                except Exception:
                    pass
            if "links" in d:
                d["links"]["raw_html_file"] = f"raw_html/{safe_id}.html"

        merged_jobs[jid] = d

    final_jobs = list(merged_jobs.values())
    scrape_meta.jobs_processed = len(final_jobs)

    data_dict = {
        "scrape_run": scrape_meta.model_dump(),
        "jobs": final_jobs,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data_dict, f, indent=2, ensure_ascii=False)

    return out_path


def export_run_summary_json(
    pages_processed: int,
    jobs_discovered: int,
    jobs_processed: int,
    duplicates: int,
    failed_jobs: int,
    date_from: str,
    date_to: str,
    output_dir: Optional[Path] = None,
    filename: str = "run_summary.json",
) -> Path:
    """Exports run_summary.json adhering strictly to Section 12."""
    target_dir = output_dir or settings.output_path
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / filename

    summary = {
        "pages_processed": pages_processed,
        "jobs_discovered": jobs_discovered,
        "jobs_processed": jobs_processed,
        "duplicates": duplicates,
        "failed_jobs": failed_jobs,
        "date_range": {
            "from": date_from,
            "to": date_to,
        },
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    return out_path
