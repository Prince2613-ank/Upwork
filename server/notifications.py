"""Outbound messages are enabled only by dashboard delivery settings."""
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def alert(settings, message):
    if not settings.webhook:
        raise RuntimeError("Google Chat webhook is not configured")
    url = urlsplit(settings.webhook)
    if url.scheme != "https" or url.hostname != "chat.googleapis.com":
        raise ValueError("Expected an HTTPS Google Chat webhook")
    req = Request(settings.webhook, data=json.dumps({"text": message}).encode(),
                  headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=20) as response:
        return response.status


def upload_report(settings, run, path):
    if not settings.chat_space.startswith("spaces/"):
        raise RuntimeError("Google Chat space is not configured")
    if not Path(settings.token_file).exists():
        raise RuntimeError("Google Chat OAuth token is not configured")
    if path.stat().st_size > 200 * 1024 * 1024:
        raise ValueError("HTML report exceeds Google Chat's 200 MB attachment limit")
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request as GoogleRequest
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    credentials = Credentials.from_authorized_user_file(settings.token_file)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(GoogleRequest())
        token = Path(settings.token_file)
        temp = token.with_suffix(".tmp")
        temp.write_text(credentials.to_json(), encoding="utf-8")
        temp.chmod(0o600)
        temp.replace(token)
    import httplib2
    from google_auth_httplib2 import AuthorizedHttp
    service = build("chat", "v1", http=AuthorizedHttp(credentials, http=httplib2.Http(timeout=30)), cache_discovery=False)
    # Deterministic message ID prevents duplicate messages on retry. Check before upload.
    message_id = f'client-report-{run["id"]}'
    from googleapiclient.errors import HttpError
    try:
        service.spaces().messages().get(name=f'{settings.chat_space}/messages/{message_id}').execute()
        return
    except HttpError as exc:
        if exc.resp.status != 404:
            raise
    attachment = service.media().upload(parent=settings.chat_space,
        body={"filename": f'upwork_{run["start_date"]}_to_{run["end_date"]}_{run["id"][:8]}.html'},
        media_body=MediaFileUpload(str(path), mimetype="text/html", resumable=False)).execute()
    text = f'Upwork report: {run["start_date"]} to {run["end_date"]}. Status: {run["status"]}.'
    service.spaces().messages().create(parent=settings.chat_space, messageId=message_id,
        body={"text": text, "attachment": [attachment]}).execute()
