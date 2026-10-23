"""
Unit tests for the Section 17 Local Web Dashboard.
"""

from fastapi.testclient import TestClient
from collector.dashboard.app import app, state


def test_dashboard_homepage():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Upwork One-Month Job Intelligence Collector" in response.text
    assert "START COLLECTION" in response.text
    assert "RUN 3-JOB TEST" in response.text


def test_dashboard_status_endpoint():
    client = TestClient(app)
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "current_page" in data
    assert "jobs_discovered" in data
    assert "jobs_processed" in data
    assert "failed_count" in data


def test_dashboard_control_actions():
    client = TestClient(app)
    # Pause
    r_pause = client.post("/api/pause")
    assert r_pause.status_code == 200
    assert r_pause.json()["status"] == "paused"

    # Resume
    r_resume = client.post("/api/resume")
    assert r_resume.status_code == 200

    # Stop
    r_stop = client.post("/api/stop")
    assert r_stop.status_code == 200
    assert r_stop.json()["status"] == "stopped"

    # Export
    r_export = client.post("/api/export")
    assert r_export.status_code == 200
