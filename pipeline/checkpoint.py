"""
Checkpoint manager for resumable, safe data collection runs.
"""

import json
import logging
from pathlib import Path
from typing import Optional
from config import CHECKPOINT_DIR
from models.schema import RunCheckpoint

logger = logging.getLogger(__name__)


class CheckpointManager:
    """
    Manages atomic writing and loading of run checkpoints.
    """

    def __init__(self, checkpoint_dir: Path = CHECKPOINT_DIR):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.latest_pointer = self.checkpoint_dir / "checkpoint_latest.json"

    def save_checkpoint(self, checkpoint: RunCheckpoint) -> Path:
        """
        Atomically saves a run checkpoint.
        """
        run_file = self.checkpoint_dir / f"checkpoint_{checkpoint.run_id}.json"
        tmp_file = self.checkpoint_dir / f"checkpoint_{checkpoint.run_id}.tmp"

        data = checkpoint.model_dump()
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        tmp_file.replace(run_file)

        # Update latest pointer
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        tmp_file.replace(self.latest_pointer)

        logger.debug(f"Checkpoint saved for run {checkpoint.run_id} (Page {checkpoint.last_page}, Jobs: {checkpoint.jobs_collected})")
        return run_file

    def load_latest_checkpoint(self) -> Optional[RunCheckpoint]:
        """
        Loads the most recent checkpoint if available.
        """
        if not self.latest_pointer.exists():
            return None
        try:
            with open(self.latest_pointer, "r", encoding="utf-8") as f:
                data = json.load(f)
            return RunCheckpoint(**data)
        except Exception as e:
            logger.error(f"Failed to read latest checkpoint: {e}")
            return None

    def load_checkpoint(self, run_id: str) -> Optional[RunCheckpoint]:
        """
        Loads a checkpoint by run_id.
        """
        run_file = self.checkpoint_dir / f"checkpoint_{run_id}.json"
        if not run_file.exists():
            return None
        try:
            with open(run_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return RunCheckpoint(**data)
        except Exception as e:
            logger.error(f"Failed to load checkpoint {run_id}: {e}")
            return None
