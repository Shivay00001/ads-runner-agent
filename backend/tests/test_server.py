"""Backend regression tests for ads-runner-agent.

Covers the defects fixed on branch fix/requirements-2026-09-26:
  1. litellm must be listed in backend/requirements.txt (fresh installs boot).
  2. /api/settings/keys must persist keys for ALL providers, not just OpenAI.
  3. The task lifecycle must transition pending -> running -> error with a
     dummy key, and the error must be an authentic provider auth error (this
     proves the background job makes a REAL litellm call, not a stub).
  4. Unknown task ids must 404.

Notes:
- Tests run against a throwaway SQLite DB; the repo-committed
  backend/ads_runner.db is never touched.
- The lifecycle tests make real HTTPS calls to the provider API with a dummy
  key and assert on the provider's authentic "Incorrect API key provided"
  error. No real keys are used; nothing secret is printed.
"""

import asyncio
import json
import os
import sys
import time
import uuid

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

import database  # noqa: E402
import models  # noqa: E402
import server  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


TEST_DB_PATH = f"/tmp/ads_runner_test_{uuid.uuid4().hex}.db"
TEST_DB_URL = f"sqlite+aiosqlite:///{TEST_DB_PATH}"
test_engine = create_async_engine(TEST_DB_URL)
TestSessionLocal = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def _init_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)


async def _override_get_db():
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture(scope="module")
def client():
    asyncio.run(_init_db())
    server.app.dependency_overrides[database.get_db] = _override_get_db
    # The background job uses server.SessionLocal directly; point it at the test DB.
    server.SessionLocal = TestSessionLocal
    with TestClient(server.app) as c:
        yield c
    server.app.dependency_overrides.clear()
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


def test_requirements_includes_litellm():
    """Defect 1: litellm was imported by server.py but missing from requirements."""
    req_path = os.path.join(BACKEND_DIR, "requirements.txt")
    with open(req_path) as f:
        names = {line.strip().split("=")[0].split(">")[0].split("<")[0].lower() for line in f}
    assert "litellm" in names, "litellm must be listed in backend/requirements.txt"


def test_settings_keys_persist_all_providers(client):
    """Defect 3: /api/settings/keys used to only store openai_api_key."""
    payload = {
        "openai_api_key": "sk-dummy-openai-123",
        "anthropic_api_key": "sk-dummy-anthropic-123",
        "gemini_api_key": "dummy-gemini-123",
        "zhipuai_api_key": "dummy-zhipu-123",
    }
    r = client.post("/api/settings/keys", json=payload)
    assert r.status_code == 200
    assert r.json()["status"] == "success"

    async def _read():
        async with TestSessionLocal() as db:
            from sqlalchemy.future import select

            rows = {}
            for k in payload:
                res = await db.execute(select(models.Setting).where(models.Setting.key == k))
                s = res.scalar_one_or_none()
                rows[k] = s.value if s else None
            return rows

    rows = asyncio.run(_read())
    for k, v in payload.items():
        assert rows[k] == v, f"setting {k} was not persisted"


def _poll_until_terminal(client, task_id, timeout_s=90):
    """Poll until the task leaves pending/running; return (first_seen, final_body)."""
    deadline = time.time() + timeout_s
    first_seen = None
    while time.time() < deadline:
        r = client.get(f"/api/tasks/{task_id}")
        assert r.status_code == 200
        body = r.json()
        status = body["status"]
        if first_seen is None:
            first_seen = status
        if status in ("success", "error"):
            return first_seen, body
        time.sleep(0.5)
    raise TimeoutError(f"task {task_id} did not reach a terminal state in {timeout_s}s")


def test_task_lifecycle_real_provider_auth_error(client):
    """Defect-1 root-cause proof: with a dummy key the job must reach the real
    provider and fail with its authentic auth error (no stubbing)."""
    r = client.post(
        "/api/execute",
        json={
            "product_url": "https://example.com/widget",
            "description": "A test widget",
            "budget": "50.00",
            "provider": "gpt-4o",
        },
        headers={"X-OpenAI-Key": "dummy-header-key-abc"},
    )
    assert r.status_code == 200
    task_id = r.json()["task_id"]

    first_seen, body = _poll_until_terminal(client, task_id)
    # With TestClient the background job can already be done on first poll.
    assert first_seen in ("pending", "running", "error"), f"unexpected first status: {first_seen}"
    assert body["status"] == "error"
    err = json.dumps(body["campaign_data"])
    assert "Incorrect API key provided" in err, f"not an authentic provider error: {err}"
    # OpenAI redacts key middles in the message ("dummy-he********-abc"),
    # so assert the unredacted prefix+suffix of the supplied header key.
    assert "dummy-he" in err and "-abc" in err, "job did not use the supplied header key"


def test_stored_keys_are_used_by_jobs(client):
    """Keys saved via /api/settings/keys must actually be used when the job
    runs (no headers, no env key). The authentic error echo proves it."""
    r = client.post(
        "/api/settings/keys", json={"openai_api_key": "dummy-stored-key-xyz"}
    )
    assert r.status_code == 200

    r = client.post(
        "/api/execute",
        json={
            "product_url": "https://example.com/gadget",
            "description": "A test gadget",
            "budget": "20.00",
            "provider": "gpt-4o",
        },
    )
    assert r.status_code == 200
    task_id = r.json()["task_id"]

    _, body = _poll_until_terminal(client, task_id)
    assert body["status"] == "error"
    err = json.dumps(body["campaign_data"])
    assert "Incorrect API key provided" in err
    # OpenAI redacts key middles ("dummy-st********-xyz"); the unredacted
    # prefix+suffix prove the job used the DB-stored key (no header/env given).
    assert "dummy-st" in err and "-xyz" in err, "job did not use the DB-stored key"


def test_unknown_task_returns_404(client):
    r = client.get("/api/tasks/does-not-exist")
    assert r.status_code == 404
    assert r.json()["detail"] == "Task not found"
