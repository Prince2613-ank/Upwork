import pytest
from pipeline.deduplicator import Deduplicator

def test_deduplication_logic():
    dedup = Deduplicator()

    assert dedup.register("job_1") is True
    assert dedup.register("job_2") is True
    assert dedup.register("job_1") is False  # Duplicate!
    assert dedup.register("job_2") is False  # Duplicate!
    assert dedup.register("job_3") is True

    assert dedup.duplicates_removed == 2
    assert len(dedup.get_seen_ids()) == 3

def test_deduplicator_with_existing_ids():
    dedup = Deduplicator(existing_ids=["job_prev_1", "job_prev_2"])
    assert dedup.is_duplicate("job_prev_1") is True
    assert dedup.register("job_prev_1") is False
    assert dedup.register("job_new") is True
    assert dedup.duplicates_removed == 1
