"""Local entrypoint. Production runs the same services through Docker Compose."""
import argparse
import os
import signal
import subprocess
import sys
import time
from urllib.request import urlopen

from server.config import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--web-only", action="store_true")
    parser.add_argument("--reload", action="store_true", help="Opt into local API code reload during development")
    parser.add_argument("--no-reload", action="store_true", help="Disable local API code reload")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    args = parser.parse_args()
    settings = Settings()
    if not settings.password_hash and (not settings.password or settings.password.startswith("replace-")):
        raise SystemExit("Configure login first: python -m server.admin set-password --username admin")
    children = []
    def stop(*_):
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        command = [sys.executable, "-m", "uvicorn", "server.app:app", "--host", args.host, "--port", str(args.port)]
        if args.reload and not args.no_reload:
            # Keep the reloader parent alive while API code changes, so workers are not interrupted.
            command += ["--reload", "--reload-dir", "server"]
        api = subprocess.Popen(command)
        children.append(api)
        for _ in range(60):
            if api.poll() is not None:
                raise RuntimeError("Dashboard could not start; inspect the startup error above")
            try:
                with urlopen(f"http://127.0.0.1:{args.port}/healthz", timeout=1) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError("Dashboard startup timed out")
        if not args.web_only:
            if os.name == "nt":
                children.append(subprocess.Popen([sys.executable, "-m", "server.local_browsers"], creationflags=subprocess.CREATE_NO_WINDOW))
            for service in ("worker", "scheduler"):
                children.append(subprocess.Popen([sys.executable, "-m", "server.pipeline", service]))
        print(f"Dashboard: http://localhost:{args.port}/login", flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(1)
        raise RuntimeError("A service exited; all local services have been stopped")
    except KeyboardInterrupt:
        pass
    finally:
        stop()


if __name__ == "__main__":
    main()
