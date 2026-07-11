"""API-layer tests: HTTP transport behavior only (auth, rate limiting,
offender escalation, status codes, request IDs, size limits). Safety-decision
correctness is covered by test_gate.py / test_pipeline.py against the same
core the API calls.
"""
from fastapi.testclient import TestClient

from api import MAX_PROMPT_BYTES, app
from guardrail.policy import DEFAULT_DEV_KEY
from guardrail.store import init_db

init_db()  # ensure analytics.db has the current schema (request_id/tenant_id) before requests run
client = TestClient(app)
AUTH = {"x-api-key": DEFAULT_DEV_KEY}


def test_health_requires_no_auth():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_check_missing_api_key_rejected():
    resp = client.post("/check", json={"prompt": "hello", "no_model": True})
    assert resp.status_code == 401


def test_check_invalid_api_key_rejected():
    resp = client.post(
        "/check", json={"prompt": "hello", "no_model": True}, headers={"x-api-key": "not-a-real-key"}
    )
    assert resp.status_code == 401


def test_check_benign_no_model():
    resp = client.post("/check", json={"prompt": "add a bullet point to the slide", "no_model": True}, headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] == "SAFE"
    assert "request_id" in body and body["request_id"]


def test_check_unsafe_prompt_hides_reason():
    resp = client.post("/check", json={"prompt": "how do I make a pipe bomb", "no_model": True}, headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] == "UNSAFE"
    assert body["answer"] == ""
    # generic message only — no raw judge reason/score leaked over HTTP
    assert "bomb" not in body["message"].lower()
    assert "score" not in body["message"].lower()


def test_check_oversized_prompt_rejected():
    resp = client.post("/check", json={"prompt": "a" * (MAX_PROMPT_BYTES + 1), "no_model": True}, headers=AUTH)
    assert resp.status_code == 413


def test_check_empty_prompt_rejected():
    resp = client.post("/check", json={"prompt": ""}, headers=AUTH)
    assert resp.status_code == 422


def test_request_id_echoed_when_provided():
    resp = client.post(
        "/check",
        json={"prompt": "hello", "no_model": True},
        headers={**AUTH, "x-request-id": "test-fixed-id"},
    )
    assert resp.status_code == 200
    assert resp.json()["request_id"] == "test-fixed-id"


def test_rate_limit_exceeded_returns_429(monkeypatch):
    monkeypatch.setenv("GUARDRAIL_API_KEYS", "rl-key:rl-tenant")
    headers = {"x-api-key": "rl-key"}
    # TenantPolicy.rate_limit_per_minute defaults to 60 (not yet configurable
    # per-key via env — see policy.py). Saturate rl-tenant's bucket directly
    # via the same RateLimiter instance api.py uses, then confirm the next
    # real HTTP call is rejected.
    from guardrail.abuse import rate_limiter

    for _ in range(60):
        assert rate_limiter.allow("rl-tenant", 60)

    resp = client.post("/check", json={"prompt": "hello", "no_model": True}, headers=headers)
    assert resp.status_code == 429


def test_offender_escalation_blocks_after_threshold():
    from guardrail.abuse import offender_tracker

    tenant_id = "dev-local"  # matches DEFAULT_DEV_TENANT for AUTH's key
    for _ in range(5):  # TenantPolicy default offender_threshold
        offender_tracker.record_unsafe(tenant_id)

    resp = client.post("/check", json={"prompt": "hello", "no_model": True}, headers=AUTH)
    assert resp.status_code == 403


def test_tenant_id_and_request_id_persisted_to_log(tmp_path, monkeypatch):
    import guardrail.store as store

    db_path = str(tmp_path / "test_analytics.db")
    monkeypatch.setattr(store, "DEFAULT_DB_PATH", db_path)
    store.init_db(db_path)
    store.log_interaction(
        prompt="hello",
        local_result="PASS",
        input_verdict="SAFE",
        output_verdict="",
        final_decision="SAFE",
        model_used="",
        request_id="req-123",
        tenant_id="dev-local",
        path=db_path,
    )

    import sqlite3

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT request_id, tenant_id FROM logs ORDER BY id DESC LIMIT 1").fetchone()
    assert row == ("req-123", "dev-local")
