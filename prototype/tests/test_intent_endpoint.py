from __future__ import annotations

from fastapi.testclient import TestClient  # test helper that fakes HTTP requests

from api.main import app  # import our FastAPI app so we can send test requests to it
from api import jobs  # import the jobs module so we can inspect and reset the store

# TestClient wraps our app — no real server needed, everything runs in memory
client = TestClient(app)


def setup_function():
    # Clear the job store before every test so tests don't affect each other
    jobs._store.clear()


def test_submit_intent_returns_job_id():
    # Send a valid POST request with a long enough text
    response = client.post("/intent", json={"text": "I am building a URL shortener that handles 50k req/s"})

    assert response.status_code == 200  # HTTP 200 means success

    data = response.json()
    assert "job_id" in data           # response must contain a job_id
    assert data["status"] == "queued" # job starts in queued state
    assert "warnings" not in data     # no warnings — this text has no secrets


def test_submit_intent_too_short_is_rejected():
    # Text under 10 characters should be rejected before our code even runs
    response = client.post("/intent", json={"text": "short"})

    assert response.status_code == 422  # 422 = Unprocessable Entity (validation failed)


def test_submit_intent_redacts_secrets():
    # A text that contains what looks like an API key
    text = "My system uses sk-ant-api03-AAABBBCCCDDDEEEFFFGGGHHH to call the AI"

    response = client.post("/intent", json={"text": text})

    assert response.status_code == 200

    data = response.json()
    assert "job_id" in data
    # A warning should be present because a secret was detected
    assert "warnings" in data

    # The stored job text must NOT contain the raw secret
    stored_job = jobs.get_job(data["job_id"])
    assert "sk-ant-api03" not in stored_job.intent_text  # secret was redacted
