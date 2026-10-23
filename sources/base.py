"""
Abstract Base Data Source for Upwork Data Collection.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple, Optional


class BaseDataSource(ABC):
    """
    Abstract interface for pluggable Upwork data sources.
    Supports Mock, Playwright Browser CDP, and Official GraphQL API.
    """

    @abstractmethod
    def fetch_search_page(self, page: int = 1) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Fetches a page of search results.
        Returns:
            (list_of_job_summaries, has_next_page)
        """
        pass

    @abstractmethod
    def fetch_job_details(self, job_id: str, job_url: str) -> str:
        """
        Fetches the complete HTML/data for a single job posting,
        including expanded description, About Client, and Client Recent History.
        Returns:
            raw_html_or_json_content
        """
        pass

    @abstractmethod
    def close(self):
        """Releases any active network/browser connections."""
        pass
