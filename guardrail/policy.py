"""
Tenant identity + per-tenant policy for api.py, keyed by a simple API key —
no OAuth, no multi-user login (deliberately local-first and simple; see
CLAUDE.md). Each tenant gets an enabled flag, a requests-per-minute rate
limit, and an offender-escalation threshold/window used by guardrail/abuse.py.

Keys are never hardcoded: set GUARDRAIL_API_KEYS in the environment as
    "key1:tenant-a,key2:tenant-b"
Per-tenant overrides for rate_limit/offender_threshold/offender_window are
optional extra colon-separated fields, in that order:
    "key1:tenant-a:120:10:1800,key2:tenant-b"
tenant-a above gets rate_limit_per_minute=120, offender_threshold=10,
offender_window_seconds=1800; tenant-b falls back to the class defaults
since it only specifies key:tenant_id. Trailing fields can be omitted
individually by leaving them blank ("key1:tenant-a::10" keeps the default
rate limit but overrides the offender threshold) — a blank/unparseable
field falls back to the default rather than erroring, so a malformed
override degrades to "no override" instead of breaking the tenant.
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


def _int_or_default(raw: str, default: int) -> int:
    raw = raw.strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _load_tenants() -> dict:
    raw = os.getenv("GUARDRAIL_API_KEYS", "")
    tenants = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        fields = entry.split(":")
        key, tenant_id = fields[0].strip(), fields[1].strip()
        if not key or not tenant_id:
            continue
        defaults = TenantPolicy(tenant_id=tenant_id)
        rate_limit = _int_or_default(fields[2], defaults.rate_limit_per_minute) if len(fields) > 2 else defaults.rate_limit_per_minute
        offender_threshold = _int_or_default(fields[3], defaults.offender_threshold) if len(fields) > 3 else defaults.offender_threshold
        offender_window = _int_or_default(fields[4], defaults.offender_window_seconds) if len(fields) > 4 else defaults.offender_window_seconds
        tenants[key] = TenantPolicy(
            tenant_id=tenant_id,
            rate_limit_per_minute=rate_limit,
            offender_threshold=offender_threshold,
            offender_window_seconds=offender_window,
        )
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
