import sys
import time
from run_daily_system import run_worker_stream, COUNTRIES_WORKER_A

if __name__ == "__main__":
    print("=" * 60)
    print(">>> FLODATA WORKER A (CHROME PORT 9222) PARALLEL STREAM <<<")
    print("=" * 60)
    try:
        run_worker_stream("A", "http://127.0.0.1:9222", "a", "Chrome 9222", COUNTRIES_WORKER_A)
    except KeyboardInterrupt:
        print("Worker A stopped by user.")
    except Exception as e:
        print(f"Worker A error: {e}")
