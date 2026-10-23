import pytest
from pathlib import Path
from models.schema import RunCheckpoint
from pipeline.checkpoint import CheckpointManager

def test_checkpoint_save_and_load():
    test_dir = Path(__file__).parent / "temp_ckpt_test"
    test_dir.mkdir(parents=True, exist_ok=True)
    try:
        ckpt_mgr = CheckpointManager(checkpoint_dir=test_dir)

        ckpt = RunCheckpoint(
            run_id="test_run_123",
            started_at="2026-09-20T12:00:00Z",
            last_updated_at="2026-09-20T12:05:00Z",
            last_page=3,
            last_job_id="~01abc",
            oldest_job_date="2026-09-10T10:00:00Z",
            newest_job_date="2026-09-20T11:00:00Z",
            cutoff_date="2026-08-21T12:00:00Z",
            jobs_collected=150,
            pages_processed=3,
            status="running",
            collected_job_ids=["~01abc", "~01def"],
        )

        saved_file = ckpt_mgr.save_checkpoint(ckpt)
        assert saved_file.exists()

        latest = ckpt_mgr.load_latest_checkpoint()
        assert latest is not None
        assert latest.run_id == "test_run_123"
        assert latest.last_page == 3
        assert latest.jobs_collected == 150
        assert "~01abc" in latest.collected_job_ids

        by_id = ckpt_mgr.load_checkpoint("test_run_123")
        assert by_id is not None
        assert by_id.run_id == "test_run_123"
    finally:
        import shutil
        if test_dir.exists():
            shutil.rmtree(test_dir, ignore_errors=True)
