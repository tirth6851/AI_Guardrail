"""
Thin FastAPI shell over the guardrail core — HTTP transport, API-key tenant
identity, rate limiting, offender escalation, request IDs, and body-size
limits only. No safety logic lives here; it stays in guardrail/. Mirrors
cli.py's shape: parse input, call screen_input()/process_prompt(), log,
return. The core stays callable without HTTP (cli.py, tests, eval all still
work unmodified).

Auth: every /check call must send an X-API-Key header (see guardrail/policy.py
for how keys map to tenants — no OAuth, no multi-user login, by design).
Abuse controls (guardrail/abuse.py) are keyed by the resolved tenant_id, not
the raw key, so key rotation doesn't reset a tenant's rate-limit/offender state.

Run with: uvicorn api:app --reload
"""
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from guardrail import process_prompt, screen_input
from guardrail.abuse import offender_tracker, rate_limiter
from guardrail.model import MODEL_NAME
from guardrail.policy import TenantPolicy, get_tenant
from guardrail.store import init_db, log_interaction

MAX_PROMPT_BYTES = 8192


@asynccontextmanager
async def _lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="AI Guardrail API", lifespan=_lifespan)


class CheckRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    no_model: bool = False


class CheckResponse(BaseModel):
    request_id: str
    decision: str
    answer: str
    message: str


def require_tenant(x_api_key: str | None = Header(default=None)) -> TenantPolicy:
    tenant = get_tenant(x_api_key or "")
    if tenant is None:
        raise HTTPException(status_code=401, detail="missing or invalid X-API-Key")
    if not tenant.enabled:
        raise HTTPException(status_code=401, detail="API key disabled")
    return tenant


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/check", response_model=CheckResponse)
def check(req: CheckRequest, request: Request, tenant: TenantPolicy = Depends(require_tenant)):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

    if len(req.prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
        raise HTTPException(status_code=413, detail="prompt exceeds max size")

    if offender_tracker.is_escalated(tenant.tenant_id, tenant.offender_threshold, tenant.offender_window_seconds):
        raise HTTPException(status_code=403, detail="blocked: repeated policy violations")

    if not rate_limiter.allow(tenant.tenant_id, tenant.rate_limit_per_minute):
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    result = screen_input(req.prompt) if req.no_model else process_prompt(req.prompt)

    if result.decision == "UNSAFE":
        offender_tracker.record_unsafe(tenant.tenant_id)

    log_interaction(
        prompt=req.prompt,
        local_result="PASS" if result.local_filter_passed else "FLAGGED",
        input_verdict=result.input_decision,
        output_verdict=result.output_decision,
        final_decision=result.decision,
        model_used=MODEL_NAME if result.answer else "",
        request_id=request_id,
        tenant_id=tenant.tenant_id,
    )

    # never leak the detailed reason/scores over HTTP — same rule cli.py follows
    # for non-SAFE decisions; only the generic public_message + answer go out.
    return CheckResponse(
        request_id=request_id,
        decision=result.decision,
        answer=result.answer,
        message=result.public_message,
    )
