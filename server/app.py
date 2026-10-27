"""Authenticated dashboard/API for the server pipeline."""
import secrets
import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, SecretStr, model_validator
from sqlalchemy import select, update, delete

from server.config import Settings
from server.db import ACTIVE, DEFAULTS, Database, control, events, jobs, now, queue, releases, runs, workers
from server.auth import Auth

class Login(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: SecretStr = Field(min_length=1, max_length=512)


class Launch(BaseModel):
    start_date: date
    end_date: date
    timezone: str = "UTC"

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


class CollectionSpeed(BaseModel):
    jobs_per_minute: int = Field(ge=1, le=20, strict=True)


class BrowserVisibility(BaseModel):
    visible: bool = Field(strict=True)


class Schedule(BaseModel):
    enabled: bool = False
    time: str = "07:00"
    timezone: str = "UTC"
    mode: Literal["yesterday", "rolling", "custom"] = "yesterday"
    days: int = Field(default=1, ge=1, le=31)
    start_date: str = ""
    end_date: str = ""
    jobs_per_minute: int = Field(default=6, ge=1, le=20)
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
    db = Database(settings.database_url, timezone=settings.timezone)
    auth = Auth(db, settings)

    @asynccontextmanager
    async def lifespan(app):
        if not settings.password_hash and (not settings.password or len(settings.password) < 16 or settings.password.startswith("replace-")):
            raise RuntimeError("Run python -m server.admin set-password to configure dashboard credentials")
        db.init()
        yield
        db.engine.dispose()

    app = FastAPI(title="Flodata server pipeline", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db = db

    def authenticate(request: Request):
        return auth.require(request)

    @app.middleware("http")
    async def protect_mutations(request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if request.headers.get("x-requested-with") != "pipeline-dashboard":
                return JSONResponse({"detail": "Dashboard request header required"}, status_code=403)
            origin = request.headers.get("origin")
            if origin:
                from urllib.parse import urlsplit
                if urlsplit(origin).netloc != request.url.netloc:
                    return JSONResponse({"detail": "Cross-origin requests are not allowed"}, status_code=403)
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

    @app.get("/")
    def dashboard(request: Request):
        if not auth.identify(request):
            return RedirectResponse("/login", status_code=303)
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    @app.get("/login")
    def login_page(request: Request):
        if auth.identify(request):
            return RedirectResponse("/", status_code=303)
        return FileResponse(Path(__file__).parent / "static" / "login.html")

    @app.get("/login.js")
    def login_script():
        return FileResponse(Path(__file__).parent / "static" / "login.js", media_type="application/javascript")

    @app.post("/api/auth/login")
    def login(payload: Login, request: Request):
        response = JSONResponse({"status": "signed_in"})
        auth.login(request, payload.username, payload.password.get_secret_value(), response)
        return response

    @app.get("/api/auth/me")
    def current_user(session=Depends(authenticate)):
        return {"username": session["username"], "expires_at": session["expires_at"]}

    @app.post("/api/auth/logout", dependencies=[Depends(authenticate)])
    def logout(request: Request):
        response = JSONResponse({"status": "signed_out"})
        with db.engine.connect() as c:
            remote = c.execute(select(control.c.remote_control)).scalar_one()
        if remote or os.name=='nt':
            try:
                release_control()
            except HTTPException:
                db.event(None, "remote_disconnect_failed", "Signed out; inspect remote browser services before resuming")
        auth.logout(request, response)
        return response

    @app.get("/dashboard.js", dependencies=[Depends(authenticate)])
    def javascript():
        return FileResponse(Path(__file__).parent / "static" / "dashboard.js", media_type="application/javascript")

    @app.get("/dashboard.css")
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
            run["quality"] = db.quality_counts(run["id"])
            with db.engine.connect() as c:
                run["release"] = c.execute(select(releases.c.summary).where(releases.c.run_id == run["id"])).scalar_one_or_none()
        with db.engine.connect() as c:
            remote = bool(c.execute(select(control.c.remote_control)).scalar_one())
        from server.analytics import current_context
        return {"runs": rr, "workers": ww, "events": ee, "remote_control": remote,
                "display_context": current_context(db, db.settings()["timezone"]),
                "collection_speed": db.settings()['jobs_per_minute'],
                "browser_windows_visible": remote or bool(db.settings().get('browser_windows_visible',False)),
                "browser_mode": "local_windows" if os.name == "nt" else "remote",
                "chat": {"webhook_configured": bool(settings.webhook),
                         "attachment_configured": bool(settings.chat_space and Path(settings.token_file).exists())}}

    @app.get("/api/live-feed", dependencies=[Depends(authenticate)])
    def live_feed(run_id: str | None = None):
        statement = select(queue.c.job_id, queue.c.worker, queue.c.result).where(queue.c.status == "done")
        if run_id:
            statement = statement.where(queue.c.run_id == run_id)
        with db.engine.connect() as c:
            rows = c.execute(statement.order_by(queue.c.id.desc()).limit(20)).mappings().all()
        from server.quality import release_candidate
        return [{"id": r["job_id"], "worker": r["worker"], "data": r["result"],
                 "release_check": release_candidate(r["result"])[1]} for r in rows]

    @app.get("/api/schedule", dependencies=[Depends(authenticate)])
    def get_schedule():
        return db.settings()

    @app.put('/api/collection-speed', dependencies=[Depends(authenticate)])
    def collection_speed(payload: CollectionSpeed):
        with db.engine.begin() as c:
            if db.engine.dialect.name == 'sqlite':
                c.exec_driver_sql('BEGIN IMMEDIATE')
            c.execute(select(control).where(control.c.id == 1).with_for_update()).first()
            options = db.settings(c)
            previous = options['jobs_per_minute']
            options['jobs_per_minute'] = payload.jobs_per_minute
            c.execute(update(control).where(control.c.id == 1).values(settings=options))
            active = c.execute(select(runs.c.id).where(runs.c.status.in_(ACTIVE)).limit(1)).scalar_one_or_none()
        if previous != payload.jobs_per_minute:
            db.event(active, 'speed_changed', f'Both workers: {previous} to {payload.jobs_per_minute} job attempts/minute each. Applies at the next fetch.')
        return {'jobs_per_minute': payload.jobs_per_minute, 'combined_target': 2 * payload.jobs_per_minute}

    @app.put("/api/schedule", dependencies=[Depends(authenticate)])
    def save_schedule(payload: Schedule):
        if payload.deliver_to_chat and not (settings.webhook and settings.chat_space and Path(settings.token_file).exists()):
            raise HTTPException(409, "Configure Google Chat webhook, space and OAuth token before enabling delivery")
        with db.engine.begin() as c:
            options=db.settings(c)
            options.update(payload.model_dump())
            c.execute(update(control).where(control.c.id == 1).values(settings=options))
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
        if run['status'] == 'cleaned' and command in ('retry', 'resume', 'compile'):
            raise HTTPException(409, 'This collection was cleaned. Start a new collection.')
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
                c.execute(update(runs).where(runs.c.id == rid).values(status="queued", error="", retry_at=0, finished_at=None, report="", delivery="disabled"))
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
    def get_jobs(start: date | None = None, end: date | None = None, search: str = "", offset: int = 0, limit: int = 50,
                 run_id: str | None = None):
        from server.analytics import job_source
        jobs = job_source(run_id)
        statement = select(jobs).where(jobs.c.data["_outside_filter"].as_string().is_(None))             .order_by(jobs.c.posted_date.desc(), jobs.c.first_seen.desc(), jobs.c.id)
        if start:
            statement = statement.where(jobs.c.posted_date >= start.isoformat())
        if end:
            statement = statement.where(jobs.c.posted_date <= end.isoformat())
        if search:
            # JSON portable cast; fixed query parameters, never SQL interpolation.
            from sqlalchemy import String, cast
            statement = statement.where(cast(jobs.c.data, String).contains(search, autoescape=True))
        from server.quality import release_candidate
        with db.engine.connect() as c:
            rows = [dict(r) for r in c.execute(statement.offset(max(0, offset)).limit(max(1, min(200, limit)))).mappings()]
        for row in rows:
            row["release_check"] = release_candidate(row["data"])[1]
        return rows

    @app.post('/api/data/clean-latest', dependencies=[Depends(authenticate)])
    def clean_latest():
        with db.engine.begin() as c:
            if db.engine.dialect.name == 'sqlite':
                c.exec_driver_sql('BEGIN IMMEDIATE')
            c.execute(select(control).where(control.c.id == 1).with_for_update()).first()
            if c.execute(select(runs.c.id).where(runs.c.status.in_(ACTIVE))).first():
                raise HTTPException(409, 'Stop the existing collection before cleaning its saved jobs.')
            if c.execute(select(queue.c.id).where(queue.c.status == 'running')).first():
                raise HTTPException(409, 'A worker is finishing its current job. Wait a few seconds and clean again.')
            run = c.execute(select(runs).order_by(runs.c.created_at.desc()).limit(1)).mappings().first()
            if not run or run['status'] == 'cleaned':
                return {'deleted': 0, 'run_id': run['id'] if run else None}
            ids = select(queue.c.job_id).where(queue.c.run_id == run['id'], queue.c.status == 'done')
            removed = c.execute(delete(jobs).where(jobs.c.id.in_(ids))).rowcount
            c.execute(update(queue).where(queue.c.run_id == run['id']).values(status='cleaned', result=None, card={}, error='', url=''))
            c.execute(update(runs).where(runs.c.id == run['id']).values(status='cleaned', phase='cleaned', error='', finished_at=now()))
            c.execute(delete(events).where(events.c.run_id == run['id']))
        db.event(run['id'], 'cleaned', f'{removed} saved jobs removed. HTML files retained.')
        return {'deleted': removed, 'run_id': run['id']}

    @app.get('/api/files', dependencies=[Depends(authenticate)])
    def list_files():
        from server.files import inventory
        with db.engine.connect() as c:
            records = [dict(r) for r in c.execute(select(runs).where(runs.c.report != '')).mappings()]
        result = []
        for entry in inventory(settings):
            run = next((r for r in records if r['report'] == entry['relative'] and entry['source'] == 'Reports'), None)
            result.append({k: v for k, v in entry.items() if k not in ('path', 'relative')} | {
                'run_id': run['id'] if run else None, 'start': run['start_date'] if run else None,
                'end': run['end_date'] if run else None, 'status': run['status'] if run else 'saved',
                'delivery': run['delivery'] if run else None,
                'download_url': f'/api/files/{entry["id"]}/download'})
        return result

    @app.get('/api/files/{file_id}/download', dependencies=[Depends(authenticate)])
    def download_file(file_id: str):
        from server.files import inventory
        entry = next((f for f in inventory(settings) if f['id'] == file_id), None)
        if not entry:
            raise HTTPException(404, 'HTML file not found')
        return FileResponse(entry['path'], filename=entry['name'], media_type='text/html')

    @app.get("/api/speed", dependencies=[Depends(authenticate)])
    def saving_speed(minutes: int = 60, run_id: str | None = None, start: date | None = None, end: date | None = None):
        from server.analytics import speed
        return speed(db, max(5, min(720, minutes)), run_id=run_id,
                     start=start and start.isoformat(), end=end and end.isoformat())

    @app.get("/api/analytics", dependencies=[Depends(authenticate)])
    def analytics(start: date | None = None, end: date | None = None, run_id: str | None = None):
        from server.analytics import summarize
        return summarize(db, start and start.isoformat(), end and end.isoformat(), run_id=run_id)

    @app.get("/api/runs/{rid}/export/{kind}", dependencies=[Depends(authenticate)])
    def export(rid: str, kind: Literal["html"]):
        run = db.get_run(rid)
        if not run or not run["report"]:
            raise HTTPException(404, "Report not ready")
        root = (settings.data_dir / 'reports').resolve()
        path = (root / run['report']).resolve()
        if not path.is_relative_to(root):
            raise HTTPException(404, 'Export not found')
        if not path.exists():
            raise HTTPException(404, "Export not found")
        return FileResponse(path, filename=path.name)

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

    @app.put('/api/browser/visibility', dependencies=[Depends(authenticate)])
    def browser_visibility(payload: BrowserVisibility):
        if os.name!='nt':
            raise HTTPException(409,'Local browser windows are available only on Windows')
        with db.engine.begin() as c:
            if db.engine.dialect.name=='sqlite':
                c.exec_driver_sql('BEGIN IMMEDIATE')
            c.execute(select(control).where(control.c.id==1).with_for_update()).first()
            options=db.settings(c)
            options['browser_windows_visible']=payload.visible
            values={'settings':options}
            if not payload.visible:
                values['remote_control']=0
            c.execute(update(control).where(control.c.id==1).values(**values))
        return {'visible':payload.visible}

    @app.post("/api/browser/release-control", dependencies=[Depends(authenticate)])
    def release_control():
        # Close existing noVNC sockets BEFORE allowing the worker to run again.
        from urllib.request import Request as URLRequest, urlopen
        try:
            if os.name == "nt":
                with db.engine.begin() as c:
                    options=db.settings(c)
                    options['browser_windows_visible']=False
                    c.execute(update(control).where(control.c.id == 1).values(remote_control=0,settings=options))
                return {"status": "released"}
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
