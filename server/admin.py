"""Local administrative commands. Never prints OAuth tokens or scraped content."""
import argparse
import gzip
import hashlib
import json
import sqlite3
from pathlib import Path

from sqlalchemy import insert, select, update

from server.db import jobs, now
from server.pipeline import setup


def import_sqlite(settings, db, paths):
    imported, retained, errors = 0, 0, 0
    for filename in paths:
        source = Path(filename).resolve()
        conn = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
        try:
            columns = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
            raw_column = "raw_html" if "raw_html" in columns else "''"
            for jid, payload, raw in conn.execute(f"SELECT job_id, job_json, {raw_column} FROM jobs"):
                try:
                    data = json.loads(payload)
                    if not isinstance(data, dict):
                        raise ValueError("Expected job object")
                    raw = raw or data.pop("raw_html", "") or ""
                    data.pop("raw_html", None)
                    score = len((data.get("job") or {}).get("description") or data.get("description") or "")
                    score += sum(len(r.get("feedback") or r.get("full_review") or "") for r in data.get("client_recent_history", []))
                    with db.engine.begin() as c:
                        previous = c.execute(select(jobs).where(jobs.c.id == jid)).mappings().first()
                        if previous and previous["data"].get("import_score", 0) >= score:
                            retained += 1
                            continue
                        data["import_score"] = score
                        data["import_source"] = source.name
                        raw_path = ""
                        if raw:
                            raw_path = hashlib.sha256(raw.encode()).hexdigest() + ".html.gz"
                            target = settings.data_dir / "raw" / raw_path
                            if not target.exists():
                                with gzip.open(target, "wt", encoding="utf-8") as f:
                                    f.write(raw)
                        values = dict(data=data, posted_date=(data.get("posted_at") or "")[:10], raw_path=raw_path, last_seen=now())
                        if previous:
                            c.execute(update(jobs).where(jobs.c.id == jid).values(**values))
                        else:
                            c.execute(insert(jobs).values(id=jid, first_seen=now(), **values))
                    imported += 1
                except (ValueError, TypeError, KeyError):
                    errors += 1
        finally:
            conn.close()
    return {"imported_or_updated": imported, "retained_existing": retained, "invalid_rows": errors}


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    migrate = commands.add_parser("import-sqlite")
    migrate.add_argument("paths", nargs="+")
    oauth = commands.add_parser("google-login")
    oauth.add_argument("--client", required=True)
    oauth.add_argument("--output", required=True)
    commands.add_parser("prepare-update")
    password = commands.add_parser("set-password")
    password.add_argument("--username", default="admin")
    password.add_argument("--env-file", default=".env.local")
    commands.add_parser("status")
    commands.add_parser("latest-report")
    args = parser.parse_args()
    if args.command == "set-password":
        import getpass
        from dotenv import set_key
        from server.auth import hash_password
        secret = getpass.getpass("New dashboard password (at least 16 characters): ")
        confirmation = getpass.getpass("Confirm password: ")
        if secret != confirmation or len(secret) < 16:
            raise SystemExit("Passwords must match and contain at least 16 characters")
        if not args.username.strip() or len(args.username) > 128:
            raise SystemExit("Choose a username between 1 and 128 characters")
        path = Path(args.env_file)
        if not path.exists():
            path.touch(mode=0o600)
            if path.name == ".env.local":
                set_key(str(path), "PUBLIC_URL", "http://localhost:8000")
                set_key(str(path), "SESSION_COOKIE_SECURE", "false")
        set_key(str(path), "DASHBOARD_USER", args.username.strip())
        set_key(str(path), "DASHBOARD_PASSWORD_SCRYPT", hash_password(secret))
        set_key(str(path), "DASHBOARD_PASSWORD", "")
        path.chmod(0o600)
        print("Dashboard credentials saved as a salted password hash. Restart the API to apply them.")
    elif args.command in ("status", "latest-report"):
        from server.db import runs
        settings, db = setup()
        with db.engine.connect() as c:
            statement = select(runs).order_by(runs.c.created_at.desc())
            if args.command == "latest-report":
                statement = statement.where(runs.c.report != "")
            run = c.execute(statement.limit(1)).mappings().first()
        if not run:
            print("No report ready yet" if args.command == "latest-report" else "No collection runs yet")
        elif args.command == "latest-report":
            print(settings.data_dir / "reports" / run["report"])
        else:
            print(json.dumps({"window": [run["start_date"], run["end_date"]], "status": run["status"], "counts": db.counts(run["id"])}))
    elif args.command == "google-login":
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(args.client, ["https://www.googleapis.com/auth/chat.messages"])
        credentials = flow.run_local_server(port=0, open_browser=True, access_type="offline", prompt="consent")
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(credentials.to_json(), encoding="utf-8")
        target.chmod(0o600)
        print("Google Chat OAuth credentials saved. Keep this file private.")
    elif args.command == "prepare-update":
        import time
        from server.db import ACTIVE, control, runs, workers
        _, db = setup()
        with db.engine.begin() as c:
            if c.execute(select(control.c.remote_control)).scalar_one():
                raise RuntimeError("Release remote browser control before deployment")
            c.execute(update(runs).where(runs.c.status.in_(("queued", "running"))).values(status="paused"))
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            with db.engine.connect() as c:
                busy = c.execute(select(workers.c.id).where(workers.c.action != "Waiting", workers.c.heartbeat > now() - 180)).first()
            if not busy:
                print("Collection paused; services are ready for update. Resume from dashboard after verification.")
                return
            time.sleep(2)
        raise RuntimeError("Workers did not become idle; deployment cancelled")
    else:
        settings, db = setup()
        print(json.dumps(import_sqlite(settings, db, args.paths)))


if __name__ == "__main__":
    main()
