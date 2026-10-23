import pytest
from sources.mock_source import MockJobDataSource

def test_mock_source_pagination():
    source = MockJobDataSource()

    page1_jobs, has_more_1 = source.fetch_search_page(page=1)
    assert len(page1_jobs) == 50
    assert has_more_1 is True

    page2_jobs, has_more_2 = source.fetch_search_page(page=2)
    assert len(page2_jobs) == 15
    assert has_more_2 is False

    # Check job details can be retrieved
    first_job = page1_jobs[0]
    html = source.fetch_job_details(first_job["job_id"], first_job["job_url"])
    assert len(html) > 500
    assert first_job["title"] in html
