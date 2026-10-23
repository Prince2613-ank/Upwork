"""
Data models for Flodata Analytics Upwork Market-Intelligence Data Collection System.
"""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class Budget(BaseModel):
    type: str = Field(default="unknown", description="fixed-price or hourly")
    amount: Optional[float] = Field(default=None, description="Exact fixed budget or avg hourly rate")
    min_hourly: Optional[float] = Field(default=None, description="Minimum hourly rate if range")
    max_hourly: Optional[float] = Field(default=None, description="Maximum hourly rate if range")
    currency: str = Field(default="USD", description="Currency symbol or ISO code")
    raw_text: str = Field(default="", description="Original raw budget string")


class ClientInfo(BaseModel):
    location: Optional[str] = Field(default=None, description="Client country and city")
    payment_verified: Optional[bool] = Field(default=None, description="True if payment verified")
    rating: Optional[float] = Field(default=None, description="Average client rating 0.0-5.0")
    reviews_count: Optional[int] = Field(default=None, description="Total number of reviews on client")
    total_spent: Optional[str] = Field(default=None, description="Total dollar spend formatted e.g. $10K+")
    total_spent_amount: Optional[float] = Field(default=None, description="Parsed numeric spend amount")
    jobs_posted: Optional[int] = Field(default=None, description="Total jobs posted by client")
    total_hires: Optional[int] = Field(default=None, description="Total hires made")
    active_hires: Optional[int] = Field(default=None, description="Currently active hires/contracts")
    hire_rate: Optional[float] = Field(default=None, description="Hire rate percentage 0-100")
    member_since: Optional[str] = Field(default=None, description="Client platform join date")
    avg_hourly_rate: Optional[str] = Field(default=None, description="Average hourly rate paid")
    hours_billed: Optional[int] = Field(default=None, description="Total hours billed")


class ClientRecentHistoryItem(BaseModel):
    job_title: str = Field(default="", description="Previous contract or job title")
    date: str = Field(default="", description="Contract duration or completion date")
    rating: Optional[float] = Field(default=None, description="Rating given for this contract 0.0-5.0")
    amount: Optional[str] = Field(default="", description="Amount or rate paid e.g. $150.00 or $35.00/hr")
    payment_type: str = Field(default="", description="Hourly or Fixed-price")
    freelancer: str = Field(default="", description="Freelancer name or agency")
    full_review: str = Field(default="", description="COMPLETE untruncated feedback/review text")
    client_feedback: str = Field(default="", description="Feedback given by client to freelancer if present")
    raw_text: str = Field(default="", description="Unparsed raw text of the history record")
    is_truncated: bool = Field(default=False, description="Flag if review was suspected of truncation")


class SourceMetadata(BaseModel):
    collected_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Timestamp when job record was scraped",
    )
    source_type: str = Field(
        default="mock",
        description="Origin of data: 'mock', 'browser_cdp', 'browser_persistent', or 'graphql_api'",
    )
    search_page: Optional[int] = Field(default=1, description="Search results page number")


class JobPosting(BaseModel):
    job_id: str = Field(..., description="Unique Upwork job identifier (e.g. ~0123456789abcdef)")
    job_url: str = Field(..., description="Full URL to the Upwork job posting")
    title: str = Field(..., description="Job posting title")
    posted_at: str = Field(..., description="Normalized ISO 8601 posting date/time")
    posted_raw: str = Field(default="", description="Original relative/absolute posting text")
    description: str = Field(..., description="MANDATORY full, un-truncated job description")
    budget: Budget = Field(default_factory=Budget)
    experience_level: Optional[str] = Field(default=None, description="Entry level, Intermediate, Expert")
    duration: Optional[str] = Field(default=None, description="Estimated project duration")
    skills: List[str] = Field(default_factory=list, description="Extracted skill tags")
    category: Optional[str] = Field(default=None, description="Job category")
    subcategory: Optional[str] = Field(default=None, description="Job subcategory")
    job_location: Optional[str] = Field(default=None, description="Location requirement if any")
    proposals: Optional[str] = Field(default=None, description="Applicant/proposal range e.g. '5 to 10'")
    about_client_raw: str = Field(default="", description="Raw unparsed About Client text block")
    client: ClientInfo = Field(default_factory=ClientInfo)
    client_recent_history: List[ClientRecentHistoryItem] = Field(default_factory=list)
    source: SourceMetadata = Field(default_factory=SourceMetadata)


class RunCheckpoint(BaseModel):
    run_id: str
    started_at: str
    last_updated_at: str
    last_page: int = 1
    last_job_id: Optional[str] = None
    oldest_job_date: Optional[str] = None
    newest_job_date: Optional[str] = None
    cutoff_date: str
    jobs_collected: int = 0
    pages_processed: int = 0
    status: str = "running"  # "running", "completed", "stopped_on_cutoff", "stopped_on_limit", "error"
    collected_job_ids: List[str] = Field(default_factory=list)


class ValidationReport(BaseModel):
    run_id: str
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_type: str
    jobs_requested: int
    jobs_collected: int
    duplicate_jobs_removed: int
    full_descriptions_count: int
    full_descriptions_ratio: str
    about_client_count: int
    about_client_ratio: str
    recent_history_count: int
    recent_history_ratio: str
    total_reviews_collected: int
    complete_reviews_count: int
    suspected_truncated_reviews_count: int
    oldest_job_date: Optional[str] = None
    newest_job_date: Optional[str] = None
    cutoff_date: Optional[str] = None
    pages_processed: int
    errors_count: int
    retries_count: int
    rate_limit_responses: int
    notes: List[str] = Field(default_factory=list)

    def to_markdown(self) -> str:
        return f"""## COLLECTION VALIDATION

Jobs collected: {self.jobs_collected}
Duplicate jobs: {self.duplicate_jobs_removed}
Full descriptions: {self.full_descriptions_ratio}
About Client: {self.about_client_ratio}
Recent history: {self.recent_history_ratio}
Complete reviews: {self.complete_reviews_count}/{self.total_reviews_collected}
Suspected truncated reviews: {self.suspected_truncated_reviews_count}
Oldest job: {self.oldest_job_date or 'N/A'}
Newest job: {self.newest_job_date or 'N/A'}
Pages: {self.pages_processed}
Errors: {self.errors_count}
Retries: {self.retries_count}
Rate-limit responses: {self.rate_limit_responses}
"""
