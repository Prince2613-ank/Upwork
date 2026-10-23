"""
Section 11: Checkpoint & Resume Manager.
Persists and loads checkpoint.json to support safe resumption from interruption.
"""

import json
from pathlib import Path
from typing import Optional, List
from collector.models.schema import CheckpointData
from collector.config.settings import settings


class CheckpointManager:
    """Manages Section 11 checkpoint.json state."""

    def __init__(self, output_dir: Optional[Path] = None, filename: str = "checkpoint.json"):
        self.output_dir = output_dir or settings.output_path
        self.checkpoint_file = self.output_dir / filename

    def save_checkpoint(
        self,
        last_completed_page: int,
        processed_job_ids: List[str],
        cutoff_date: str,
        last_processed_job: str,
        status: str = "running",
        current_location_index: int = 0,
    ) -> Path:
        """Atomically saves checkpoint to checkpoint.json."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        ckpt = CheckpointData(
            last_completed_page=last_completed_page,
            current_location_index=current_location_index,
            processed_job_ids=processed_job_ids,
            cutoff_date=cutoff_date,
            last_processed_job=last_processed_job,
            status=status,
        )

        tmp_file = self.checkpoint_file.with_suffix(".tmp")
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(ckpt.model_dump(), f, indent=2, ensure_ascii=False)
            
            # Windows atomic replace with retries and fallback
            replaced = False
            for _ in range(5):
                try:
                    tmp_file.replace(self.checkpoint_file)
                    replaced = True
                    break
                except Exception:
                    import time
                    time.sleep(0.15)
            
            if not replaced:
                with open(self.checkpoint_file, "w", encoding="utf-8") as f:
                    json.dump(ckpt.model_dump(), f, indent=2, ensure_ascii=False)
                try:
                    if tmp_file.exists():
                        tmp_file.unlink()
                except Exception:
                    pass
        except Exception as ex:
            # Checkpoint save should never crash the collector
            try:
                with open(self.checkpoint_file, "w", encoding="utf-8") as f:
                    json.dump(ckpt.model_dump(), f, indent=2, ensure_ascii=False)
            except Exception:
                pass

        return self.checkpoint_file

    def load_checkpoint(self) -> Optional[CheckpointData]:
        """Loads existing checkpoint if available."""
        if not self.checkpoint_file.exists():
            return None
        try:
            with open(self.checkpoint_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return CheckpointData(**data)
        except Exception as e:
            print(f"Warning: Failed to load checkpoint ({e})")
            return None

    def clear_checkpoint(self):
        """Removes existing checkpoint file."""
        if self.checkpoint_file.exists():
            try:
                self.checkpoint_file.unlink()
            except Exception:
                pass
