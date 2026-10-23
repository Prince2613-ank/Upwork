"""
Structured Logging and Section 13 Error Tracking for Upwork Collector.
Maintains errors.json recording all failed extractions and retries.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

from collector.config.settings import settings


class ErrorLogger:
    """Manages Section 13 errors.json persistence."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or settings.output_path
        self.errors_file = self.output_dir / "errors.json"
        self.errors: List[Dict[str, Any]] = []
        self._load_existing()

    def _load_existing(self):
        if self.errors_file.exists():
            try:
                with open(self.errors_file, "r", encoding="utf-8") as f:
                    self.errors = json.load(f)
            except Exception:
                self.errors = []

    def log_error(self, job_url: str, error_msg: str, retry_count: int = 0):
        """Records an error to errors.json matching Section 13 format."""
        entry = {
            "job_url": job_url,
            "error": str(error_msg),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "retry_count": retry_count,
        }
        self.errors.append(entry)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.errors_file, "w", encoding="utf-8") as f:
                json.dump(self.errors, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving errors.json: {e}")

    def clear(self):
        self.errors = []
        if self.errors_file.exists():
            try:
                self.errors_file.unlink()
            except Exception:
                pass


def setup_logger(name: str = "upwork_collector", log_level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(log_level)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

        class SafeStreamHandler(logging.StreamHandler):
            def emit(self, record):
                try:
                    msg = self.format(record)
                    stream = self.stream
                    stream.write(msg + self.terminator)
                    self.flush()
                except UnicodeEncodeError:
                    try:
                        safe_msg = msg.encode("ascii", errors="replace").decode("ascii")
                        self.stream.write(safe_msg + self.terminator)
                        self.flush()
                    except Exception:
                        self.handleError(record)
                except Exception:
                    self.handleError(record)

        console_handler = SafeStreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        log_dir = settings.output_path / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "collector.log", encoding="utf-8", errors="replace")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


logger = setup_logger()
error_logger = ErrorLogger()
