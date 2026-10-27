FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/opt/browsers
WORKDIR /app
COPY requirements-server.lock .
RUN pip install --no-cache-dir --no-compile -r requirements-server.lock
RUN python -m playwright install --with-deps --no-shell chromium
RUN apt-get update && apt-get install -y --no-install-recommends xvfb x11vnc novnc websockify socat tini \
    && rm -rf /var/lib/apt/lists/* && useradd --create-home --uid 10001 app \
    && mkdir -p /data /secrets /app/output && chown -R app:app /data /secrets /app
COPY --chown=app:app server ./server
COPY --chown=app:app collector ./collector
COPY --chown=app:app generate_standalone_report.py ./
COPY --chown=app:app deploy/browser_service.py ./deploy/browser_service.py
RUN chown -R app:app /app
USER app
ENV PIPELINE_DATA_DIR=/data DISPLAY=:99
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
