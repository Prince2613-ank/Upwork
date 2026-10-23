"""
Deduplication engine using stable Upwork job identifiers.
"""

from typing import Set, Iterable


class Deduplicator:
    """
    Tracks and filters duplicate job postings across pagination steps.
    """

    def __init__(self, existing_ids: Iterable[str] = ()):
        self.seen_ids: Set[str] = set(existing_ids)
        self.duplicates_removed: int = 0

    def is_duplicate(self, job_id: str) -> bool:
        """Returns True if the job_id has already been processed."""
        return job_id in self.seen_ids

    def register(self, job_id: str) -> bool:
        """
        Registers a job ID.
        Returns:
            True if newly registered (not seen before)
            False if it was a duplicate
        """
        if not job_id:
            return False
        if job_id in self.seen_ids:
            self.duplicates_removed += 1
            return False
        self.seen_ids.add(job_id)
        return True

    def get_seen_ids(self) -> Set[str]:
        return set(self.seen_ids)
