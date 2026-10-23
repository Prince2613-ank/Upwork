import sys
sys.path.insert(0, ".")
from collector.extraction.job_parser import parse_job_detail_page

with open("scratch/scratch_latest_job.html", "r", encoding="utf-8") as f:
    html = f.read()

job_obj = parse_job_detail_page(html, job_url="https://www.upwork.com/jobs/~022110753556122502485/")
print("Job title:", job_obj.job_title)
print("Description len:", len(job_obj.job_details.description or "") if job_obj.job_details else 0)
print("Description:", repr(job_obj.job_details.description[:120] if job_obj.job_details and job_obj.job_details.description else ""))
print("Extraction status:", job_obj.extraction_status)
