"""
Tenant identity + per-tenant policy for api.py, keyed by a simple API key —
no OAuth, no multi-user login (deliberately local-first and simple; see
CLAUDE.md). Each tenant gets an enabled flag, a requests-per-minute rate
limit, and an offender-escalation threshold/window used by guardrail/abuse.py.

Keys are never hardcoded: set GUARDRAIL_API_KEYS in the environment as
    "key1:tenant-a,key2:tenant-b"
If unset, a single local-dev key/tenant is used so the API still runs
out of the box without configuration — same "obvious, non-secret default"
pattern as store.py's GUARDRAIL_HASH_SALT.
"""
import os
from dataclasses import dataclass

DEFAULT_DEV_KEY = "dev-local-key"
DEFAULT_DEV_TENANT = "dev-local"


@dataclass
class TenantPolicy:
    tenant_id: str
    enabled: bool = True
    rate_limit_per_minute: int = 60
    offender_threshold: int = 5
    offender_window_seconds: int = 3600


def _load_tenants() -> dict:
    raw = os.getenv("GUARDRAIL_API_KEYS", "")
    tenants = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        key, tenant_id = pair.split(":", 1)
        key, tenant_id = key.strip(), tenant_id.strip()
        if key and tenant_id:
            tenants[key] = TenantPolicy(tenant_id=tenant_id)
    if not tenants:
        tenants[DEFAULT_DEV_KEY] = TenantPolicy(tenant_id=DEFAULT_DEV_TENANT)
    return tenants


def get_tenant(api_key: str) -> TenantPolicy | None:
    """Look up the tenant for an API key. Re-reads GUARDRAIL_API_KEYS each
    call (cheap: a short comma-separated string) so tests can set the env
    var per-case without needing a cache-invalidation hook."""
    if not api_key:
        return None
    return _load_tenants().get(api_key)
