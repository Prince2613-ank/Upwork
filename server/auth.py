"""Revocable server-side sessions; no dashboard password is stored in the browser."""
import base64
import hashlib
import secrets
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import delete, insert, select, update

from server.db import control, login_limits, now, sessions

COOKIE = "flodata_session"
CSRF_COOKIE = "flodata_csrf"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password):
    salt = secrets.token_bytes(16)
    hashed = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=3,
                           dklen=32, maxmem=128 * 1024 * 1024)
    return "$".join(("scrypt", "32768", "8", "3", base64.urlsafe_b64encode(salt).decode(), hashed.hex()))


def verify_password(settings, password):
    if settings.password_hash:
        try:
            kind, n, r, p, salt, expected = settings.password_hash.split("$")
            if kind != "scrypt" or (int(n), int(r), int(p)) != (32768, 8, 3):
                return False
            actual = hashlib.scrypt(password.encode(), salt=base64.urlsafe_b64decode(salt),
                n=int(n), r=int(r), p=int(p), dklen=32, maxmem=128 * 1024 * 1024).hex()
            return secrets.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False
    return bool(settings.password and secrets.compare_digest(password.encode(), settings.password.encode()))


class Auth:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings

    def token_hash(self, token):
        # Password/username rotation invalidates all previously issued sessions.
        credential = digest(self.settings.password_hash or self.settings.password)
        return digest(token + ":" + self.settings.username + ":" + credential)

    def identify(self, request):
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
                user, pwd = decoded.split(":", 1)
                if secrets.compare_digest(user.encode(), self.settings.username.encode()) and verify_password(self.settings, pwd):
                    return {"username": user, "auth_type": "basic", "csrf_hash": ""}
            except Exception:
                pass
        token = request.cookies.get(COOKIE, "")
        if not token or len(token) > 256:
            return None
        with self.db.engine.connect() as c:
            row = c.execute(select(sessions).where(sessions.c.token_hash == self.token_hash(token),
                                                  sessions.c.expires_at > now())).mappings().first()
        return dict(row) if row and row["username"] == self.settings.username else None

    def require(self, request):
        session = self.identify(request)
        if not session:
            raise HTTPException(401, "Please sign in")
        if session.get("auth_type") != "basic" and request.method in ("POST", "PUT", "PATCH", "DELETE"):
            csrf = request.headers.get("x-csrf-token", "")
            if not csrf or not secrets.compare_digest(digest(csrf), session["csrf_hash"]):
                raise HTTPException(403, "Session security check failed; refresh and try again")
        return session

    def login(self, request, username, password, response):
        ip = request.client.host if request.client else "unknown"
        if self.settings.trust_proxy:
            ip = request.headers.get("x-real-ip", ip)
        key = digest(ip)
        with self.db.engine.connect() as c:
            limit = c.execute(select(login_limits).where(login_limits.c.key == key)).mappings().first()
        if limit and limit["blocked_until"] > now():
            raise HTTPException(429, "Too many sign-in attempts. Try again in 15 minutes.", headers={"Retry-After": str(max(1, int(limit["blocked_until"] - now())))})
        valid = verify_password(self.settings, password)
        valid = secrets.compare_digest(username.encode(), self.settings.username.encode()) and valid
        with self.db.engine.begin() as c:
            c.execute(select(control).where(control.c.id == 1).with_for_update()).first()
            current = c.execute(select(login_limits).where(login_limits.c.key == key)).mappings().first()
            if valid:
                c.execute(delete(login_limits).where(login_limits.c.key == key))
            else:
                failures = current["failures"] + 1 if current and current["window_start"] > now() - 900 else 1
                values = dict(failures=failures, window_start=current["window_start"] if current and failures > 1 else now(),
                              blocked_until=now() + 900 if failures >= 5 else 0)
                if current:
                    c.execute(update(login_limits).where(login_limits.c.key == key).values(**values))
                else:
                    c.execute(insert(login_limits).values(key=key, **values))
        if not valid:
            raise HTTPException(401, "Invalid username or password")
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        age = max(1, min(24, self.settings.session_hours)) * 3600
        with self.db.engine.begin() as c:
            c.execute(delete(sessions).where(sessions.c.expires_at <= now()))
            old = request.cookies.get(COOKIE)
            if old:
                c.execute(delete(sessions).where(sessions.c.token_hash == self.token_hash(old)))
            c.execute(insert(sessions).values(token_hash=self.token_hash(token), csrf_hash=digest(csrf),
                username=username, expires_at=now() + age))
        response.set_cookie(COOKIE, token, max_age=age, httponly=True, secure=self.settings.session_secure, samesite="strict")
        response.set_cookie(CSRF_COOKIE, csrf, max_age=age, httponly=False, secure=self.settings.session_secure, samesite="strict")

    def logout(self, request, response):
        token = request.cookies.get(COOKIE, "")
        with self.db.engine.begin() as c:
            c.execute(delete(sessions).where(sessions.c.token_hash == self.token_hash(token)))
        response.delete_cookie(COOKIE)
        response.delete_cookie(CSRF_COOKIE)
