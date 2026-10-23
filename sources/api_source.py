"""
Official Upwork GraphQL API Source Stub & Documenter.
Fulfills Requirement 1 & 6: Documents exactly which fields are available through
the authorized API vs which require the UI/browser representation.
"""

import logging
from typing import List, Dict, Any, Tuple
from config import UPWORK_CLIENT_ID, UPWORK_CLIENT_SECRET, UPWORK_ACCESS_TOKEN
from .base import BaseDataSource

logger = logging.getLogger(__name__)


class UpworkGraphQLApiDataSource(BaseDataSource):
    """
    Official Upwork GraphQL API adapter.

    TECHNICAL API CAPABILITY AUDIT:
    --------------------------------
    FIELD                           | OFFICIAL GRAPHQL API              | UI / BROWSER
    --------------------------------------------------------------------------------------
    job_id                          | AVAILABLE (id)                    | AVAILABLE
    job_title                       | AVAILABLE (content.title)         | AVAILABLE
    full_description                | AVAILABLE (content.description)   | AVAILABLE
    posted_date                     | AVAILABLE (createdDateTime)       | AVAILABLE
    budget / payment terms          | AVAILABLE (contractTerms)         | AVAILABLE
    skills                          | AVAILABLE (annotations.skills)    | AVAILABLE
    category / subcategory          | AVAILABLE (annotations.category)  | AVAILABLE
    client location                 | PARTIAL (country code only)       | FULL (Country + City)
    payment verification status     | AVAILABLE (client.isPaymentVer.)  | AVAILABLE
    client total spend              | RESTRICTED (summary bucket)       | FULL ($X total spent)
    client hire rate & active jobs  | UNAVAILABLE via public search     | AVAILABLE
    client_recent_history           | UNAVAILABLE across 3rd parties    | AVAILABLE
    complete review / feedback text | UNAVAILABLE across 3rd parties    | AVAILABLE

    Why is client_recent_history unavailable via the official search API?
    In the Upwork GraphQL schema, feedback is associated with the `contract` object:
        query getContractFeedback($id: ID!) { contract(id: $id) { feedback { ... } } }
    This query strictly requires permissions as a direct party to the contract.
    It cannot be queried arbitrarily across all third-party freelancers for a marketplace client.
    """

    def __init__(self):
        self.access_token = UPWORK_ACCESS_TOKEN
        self.client_id = UPWORK_CLIENT_ID
        self.client_secret = UPWORK_CLIENT_SECRET

        if not self.access_token and not (self.client_id and self.client_secret):
            logger.info(
                "Upwork GraphQL API credentials not configured in environment. "
                "To use the official API when granted, populate UPWORK_ACCESS_TOKEN or UPWORK_CLIENT_ID/SECRET in .env."
            )

    def fetch_search_page(self, page: int = 1) -> Tuple[List[Dict[str, Any]], bool]:
        if not self.access_token:
            raise PermissionError(
                "Upwork official API access token not configured. "
                "Please configure UPWORK_ACCESS_TOKEN or use browser / mock data sources."
            )
        raise NotImplementedError("Live GraphQL querying requires approved Upwork developer app keys.")

    def fetch_job_details(self, job_id: str, job_url: str) -> str:
        if not self.access_token:
            raise PermissionError("Upwork official API access token not configured.")
        raise NotImplementedError("Live GraphQL querying requires approved Upwork developer app keys.")

    def close(self):
        pass
