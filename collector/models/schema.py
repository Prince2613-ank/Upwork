"""
Standardized Data Models for Upwork One-Month Job Intelligence Collector.
Strictly adheres to Section 8, Section 4, Section 5, and Section 14 specifications.
"""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field


class JobDetails(BaseModel):
    description: str = Field(default="", description="Complete full job description")
    job_type: str = Field(default="", description="Fixed-price or Hourly")
    experience_level: str = Field(default="", description="Entry Level, Intermediate, or Expert")
    budget: str = Field(default="", description="Overall budget string")
    hourly_min: str = Field(default="", description="Minimum hourly rate")
    hourly_max: str = Field(default="", description="Maximum hourly rate")
    fixed_price: str = Field(default="", description="Fixed price amount")
    skills: List[str] = Field(default_factory=list, description="Extracted required skills")
    proposals: str = Field(default="", description="Number or range of proposals")


class ClientSection(BaseModel):
    location: str = Field(default="", description="Client location / country / city")
    payment_verified: bool = Field(default=False, description="True if payment verified")
    rating: str = Field(default="", description="Average rating")
    total_spent: str = Field(default="", description="Total spent e.g. $3K+ spent")
    jobs_posted: str = Field(default="", description="Number of jobs posted")
    hire_rate: str = Field(default="", description="Hire rate percentage")
    total_hires: str = Field(default="", description="Total hires")
    active_hires: str = Field(default="", description="Active hires")
    hours_billed: str = Field(default="", description="Total hours billed")
    member_since: str = Field(default="", description="Member join date")
    client_type: str = Field(default="", description="Client type / industry if available")
    about_client_text: str = Field(default="", description="Raw or aggregated text of about client section")


class ClientHistoryItem(BaseModel):
    job_title: str = Field(default="", description="Previous job / contract title")
    job_url: str = Field(default="", description="Job or contract URL if available")
    date: str = Field(default="", description="Date range or completion date")
    duration: str = Field(default="", description="Duration if displayed")
    payment_type: str = Field(default="", description="Hourly or Fixed-price")
    amount: str = Field(default="", description="Amount paid or hourly rate")
    rating: str = Field(default="", description="Rating score")
    freelancer_name: str = Field(default="", description="Freelancer name or agency")
    feedback: str = Field(default="", description="Complete feedback/review text")
    feedback_full: bool = Field(default=False, description="True if un-truncated review text")


class ExtractionStatus(BaseModel):
    job_details: bool = Field(default=False)
    description: bool = Field(default=False)
    about_client: bool = Field(default=False)
    recent_history: bool = Field(default=False)
    full_reviews: bool = Field(default=False)


class CollectedJob(BaseModel):
    job_id: str = Field(default="", description="Ciphertext job ID (~01...)")
    job_url: str = Field(default="", description="Canonical job URL")
    job_title: str = Field(default="", description="Job title")
    posted_at: str = Field(default="", description="Normalized ISO 8601 posting datetime")
    posted_raw: str = Field(default="", description="Original posted string e.g. '4 minutes ago'")
    client_location: str = Field(default="", description="Client location")
    job: JobDetails = Field(default_factory=JobDetails)
    client: ClientSection = Field(default_factory=ClientSection)
    client_recent_history: List[ClientHistoryItem] = Field(default_factory=list)
    extraction_status: ExtractionStatus = Field(default_factory=ExtractionStatus)
    # Manager requirement: raw HTML + explicit links between job/client/reviews
    raw_html: str = Field(default="", description="Full raw HTML of the job detail page")
    links: Dict[str, Any] = Field(
        default_factory=dict,
        description="Explicit links: job_url, client_profile_url, reviews_section_anchor"
    )


class ScrapeRunMeta(BaseModel):
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str = Field(default="")
    search_url: str = Field(default="")
    cutoff_date: str = Field(default="")
    pages_processed: int = 0
    jobs_discovered: int = 0
    jobs_processed: int = 0


class ScrapeDataset(BaseModel):
    scrape_run: ScrapeRunMeta = Field(default_factory=ScrapeRunMeta)
    jobs: List[CollectedJob] = Field(default_factory=list)


class CheckpointData(BaseModel):
    last_completed_page: int = 0
    current_location_index: int = 0
    processed_job_ids: List[str] = Field(default_factory=list)
    cutoff_date: str = ""
    last_processed_job: str = ""
    status: str = "running"  # running, paused, completed, stopped_on_cutoff, stopped_security_prompt
