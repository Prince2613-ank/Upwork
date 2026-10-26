"""Authenticated dashboard/API for the server pipeline."""
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, update

from server.config import Settings
from server.db import ACTIVE, DEFAULTS, Database, control, events, jobs, now, queue, runs, workers

security = HTTPBasic()


class Launch(BaseModel):
    start_date: date
    end_date: date
    timezone: str = "Asia/Kolkata"

    @model_validator(mode="after")
    def valid(self):
        try:
            ZoneInfo(self.timezone)
        except Exception as exc:
            raise ValueError("Use a valid IANA timezone") from exc
        if self.start_date > self.end_date:
            raise ValueError("Start date must not follow end date")
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("Use a date window of at most 367 days")
        if self.end_date >= datetime.now(ZoneInfo(self.timezone)).date():
            raise ValueError("Select completed days; today is excluded")
        return self


class Schedule(BaseModel):
    enabled: bool = False
    time: str = "07:00"
    timezone: str = "Asia/Kolkata"
    mode: Literal["yesterday", "rolling", "custom"] = "yesterday"
    days: int = Field(default=1, ge=1, le=31)
    start_date: str = ""
    end_date: str = ""
    jobs_per_minute: int = Field(default=6, ge=5, le=7)
    search_delay_seconds: int = Field(default=10, ge=5, le=120)
    deliver_to_chat: bool = False

    @model_validator(mode="after")
    def valid(self):
        try:
            datetime.strptime(self.time, "%H:%M")
            if len(self.time) != 5:
                raise ValueError()
            ZoneInfo(self.timezone)
        except Exception as exc:
            raise ValueError("Use HH:MM time and a valid IANA timezone") from exc
        if self.mode == "yesterday":
            self.days = 1
        if self.mode == "custom":
            Launch(start_date=self.start_date, end_date=self.end_date, timezone=self.timezone)
        return self


def create_app(settings=None):
    settings = settings or Settings()
    settings.prepare()
    db = Database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        if not settings.password or len(settings.password) < 16 or settings.password.startswith("replace-"):
            raise RuntimeError("Set DASHBOARD_PASSWORD to a unique password of at least 16 characters")
        db.init()
        yield
        db.engine.dispose()

    app = FastAPI(title="Flodata server pipeline", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db = db

    def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
        good_user = secrets.compare_digest(credentials.username.encode(), settings.username.encode())
        good_pass = secrets.compare_digest(credentials.password.encode(), settings.password.encode())
        if not settings.password or not (good_user and good_pass):
            raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Basic"})

    @app.middleware("http")
    async def protect_mutations(request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if request.headers.get("x-requested-with") != "pipeline-dashboard":
                return JSONResponse({"detail": "Dashboard request header required"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'self'; object-src 'none'; base-uri 'self'"
        return response

    @app.get("/healthz")
    def health():
        with db.engine.connect() as c:
            c.execute(select(control.c.id)).first()
        return {"status": "ok"}

    @app.get("/", dependencies=[Depends(authenticate)])
    def dashboard():
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    @app.get("/dashboard.js", dependencies=[Depends(authenticate)])
    def javascript():
        return FileResponse(Path(__file__).parent / "static" / "dashboard.js", media_type="application/javascript")

    @app.get("/dashboard.css", dependencies=[Depends(authenticate)])
    def stylesheet():
        return FileResponse(Path(__file__).parent / "static" / "dashboard.css", media_type="text/css")

    @app.get("/api/status", dependencies=[Depends(authenticate)])
    def status():
        with db.engine.connect() as c:
            rr = [dict(r) for r in c.execute(select(runs).order_by(runs.c.created_at.desc()).limit(30)).mappings()]
            ww = [dict(r) for r in c.execute(select(workers)).mappings()]
            ee = [dict(r) for r in c.execute(select(events).order_by(events.c.id.desc()).limit(40)).mappings()]
        for run in rr:
            run["counts"] = db.counts(run["id"])
        with db.engine.connect() as c:
            remote = bool(c.execute(select(control.c.remote_control)).scalar_one())
        return {"runs": rr, "workers": ww, "events": ee, "remote_control": remote,
                "chat": {"webhook_configured": bool(settings.webhook),
                         "attachment_configured": bool(settings.chat_space and Path(settings.token_file).exists())}}

    @app.get("/api/schedule", dependencies=[Depends(authenticate)])
    def get_schedule():
        return db.settings()

    @app.put("/api/schedule", dependencies=[Depends(authenticate)])
    def save_schedule(payload: Schedule):
        if payload.deliver_to_chat and not (settings.webhook and settings.chat_space and Path(settings.token_file).exists()):
            raise HTTPException(409, "Configure Google Chat webhook, space and OAuth token before enabling delivery")
        with db.engine.begin() as c:
            c.execute(update(control).where(control.c.id == 1).values(settings=payload.model_dump()))
        return payload

    @app.post("/api/runs", dependencies=[Depends(authenticate)])
    def launch(payload: Launch):
        try:
            rid = db.create_run(payload.start_date.isoformat(), payload.end_date.isoformat(), payload.timezone)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        db.event(rid, "created", "Manual collection requested")
        return {"id": rid}

    @app.post("/api/runs/{rid}/{command}", dependencies=[Depends(authenticate)])
    def command(rid: str, command: Literal["pause", "resume", "stop", "retry", "deliver", "compile"]):
        run = db.get_run(rid)
        if not run:
            raise HTTPException(404, "Run not found")
        with db.engine.begin() as c:
            c.execute(select(control).where(control.c.id == 1).with_for_update()).first()
            if command in ("resume", "retry"):
                if c.execute(select(control.c.remote_control)).scalar_one():
                    raise HTTPException(409, "Release remote browser control before resuming")
                if c.execute(select(runs.c.id).where(runs.c.id != rid, runs.c.status.in_(ACTIVE))).first():
                    raise HTTPException(409, "Another run is active")
                if run["status"] == "cooldown" and run["retry_at"] > now():
                    raise HTTPException(409, "Wait for the rate-limit cooldown to finish")
                if command == "resume" and run["status"] not in ACTIVE:
                    raise HTTPException(409, "Finished run: use Retry failed or create a new run")
                if command == "retry":
                    c.execute(update(queue).where(queue.c.run_id == rid, queue.c.status == "failed")
                              .values(status="pending", attempts=0, retry_at=0, error=""))
                c.execute(update(runs).where(runs.c.id == rid).values(status="queued", error="", finished_at=None))
            elif command in ("pause", "stop"):
                if run["status"] not in ACTIVE:
                    raise HTTPException(409, "Run is already finished")
                c.execute(update(runs).where(runs.c.id == rid).values(status="paused" if command == "pause" else "stopped"))
            elif command == "deliver":
                if not run["report"]:
                    raise HTTPException(409, "Report is not ready")
                if not db.settings(c)["deliver_to_chat"]:
                    raise HTTPException(409, "Enable Google Chat delivery in settings first")
                c.execute(update(runs).where(runs.c.id == rid).values(delivery="pending", delivery_attempts=0,
                                                                       delivery_retry_at=0, delivery_error=""))
            elif command == "compile":
                remote_ready()
                from server.reports import build_report
                filename, _ = build_report(db, settings, run)
                c.execute(update(runs).where(runs.c.id == rid).values(report=filename,
                    delivery="pending" if db.settings(c)["deliver_to_chat"] else "disabled"))
        db.event(rid, "command", command)
        return {"status": "accepted"}

    @app.get("/api/jobs", dependencies=[Depends(authenticate)])
    def get_jobs(start: date | None = None, end: date | None = None, search: str = "", offset: int = 0, limit: int = 50):
        statement = select(jobs).order_by(jobs.c.posted_date.desc(), jobs.c.id)
        if start:
            statement = statement.where(jobs.c.posted_date >= start.isoformat())
        if end:
            statement = statement.where(jobs.c.posted_date <= end.isoformat())
        if search:
            # JSON portable cast; fixed query parameters, never SQL interpolation.
            from sqlalchemy import String, cast
            statement = statement.where(cast(jobs.c.data, String).contains(search, autoescape=True))
        with db.engine.connect() as c:
            return [dict(r) for r in c.execute(statement.offset(max(0, offset)).limit(max(1, min(200, limit)))).mappings()]

    @app.get("/api/runs/{rid}/export/{kind}", dependencies=[Depends(authenticate)])
    def export(rid: str, kind: Literal["html", "csv", "json"]):
        run = db.get_run(rid)
        if not run or not run["report"]:
            raise HTTPException(404, "Report not ready")
        path = settings.data_dir / "reports" / f"{run['id']}.{kind}"
        if not path.exists():
            raise HTTPException(404, "Export not found")
        return FileResponse(path, filename=f'upwork_{run["start_date"]}_to_{run["end_date"]}.{kind}')

    def remote_ready(require_lock=False):
        with db.engine.connect() as c:
            active = c.execute(select(runs.c.id).where(runs.c.status.in_(("running", "queued")))).first()
            busy = c.execute(select(workers.c.id).where(workers.c.action != "Waiting", workers.c.heartbeat > now() - 180)).first()
            locked = c.execute(select(control.c.remote_control)).scalar_one()
        if active or busy:
            raise HTTPException(409, "Pause collection and wait until both workers show Waiting before remote control")
        if require_lock and not locked:
            raise HTTPException(409, "Take remote control from the dashboard first")

    @app.get("/api/remote-ready", dependencies=[Depends(authenticate)])
    def check_remote():
        remote_ready(require_lock=True)
        return {"status": "ready"}

    @app.post("/api/browser/take-control", dependencies=[Depends(authenticate)])
    def take_control():
        with db.engine.begin() as c:
            c.execute(select(control).where(control.c.id == 1).with_for_update()).first()
            remote_ready()
            c.execute(update(control).where(control.c.id == 1).values(remote_control=1))
        return {"status": "remote_control"}

    @app.post("/api/browser/release-control", dependencies=[Depends(authenticate)])
    def release_control():
        # Close existing noVNC sockets BEFORE allowing the worker to run again.
        from urllib.request import Request as URLRequest, urlopen
        try:
            for endpoint in (settings.browser_a, settings.browser_b):
                from urllib.parse import urlsplit
                host = urlsplit(endpoint).hostname
                with urlopen(URLRequest(f"http://{host}:7070/disconnect", data=b"", method="POST"), timeout=5) as response:
                    if response.status != 200:
                        raise RuntimeError("Remote disconnect failed")
        except Exception as exc:
            raise HTTPException(503, "Could not disconnect remote sessions; keep collection paused and inspect browser services") from exc
        with db.engine.begin() as c:
            c.execute(update(control).where(control.c.id == 1).values(remote_control=0))
        return {"status": "released"}

    @app.post("/api/browser/{wid}/restart", dependencies=[Depends(authenticate)])
    def restart_browser(wid: Literal["A", "B"]):
        remote_ready()
        from playwright.sync_api import sync_playwright
        try:
            with sync_playwright() as pw:
                from server.browser import cdp_websocket
                browser = pw.chromium.connect_over_cdp(cdp_websocket(settings.browser_a if wid == "A" else settings.browser_b), timeout=10000)
                browser.new_browser_cdp_session().send("Browser.close")
        except Exception:
            # Browser closure can tear down the CDP response transport.
            pass
        db.event(None, "browser_restart", f"Restart requested for browser {wid}; inspect its health")
        return {"status": "requested"}

    return app


app = create_app()
