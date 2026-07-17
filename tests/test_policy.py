"""Unit tests for guardrail/policy.py's API-key -> tenant resolution."""
from guardrail.policy import DEFAULT_DEV_KEY, DEFAULT_DEV_TENANT, get_tenant


def test_default_dev_key_resolves_when_env_unset(monkeypatch):
    monkeypatch.delenv("GUARDRAIL_API_KEYS", raising=False)
    tenant = get_tenant(DEFAULT_DEV_KEY)
    assert tenant is not None
    assert tenant.tenant_id == DEFAULT_DEV_TENANT
    assert tenant.enabled is True


def test_unknown_key_returns_none(monkeypatch):
    monkeypatch.delenv("GUARDRAIL_API_KEYS", raising=False)
    assert get_tenant("some-key-nobody-issued") is None


def test_empty_key_returns_none():
    assert get_tenant("") is None


def test_configured_keys_map_to_distinct_tenants(monkeypatch):
    monkeypatch.setenv("GUARDRAIL_API_KEYS", "key-a:tenant-a,key-b:tenant-b")
    a = get_tenant("key-a")
    b = get_tenant("key-b")
    assert a.tenant_id == "tenant-a"
    assert b.tenant_id == "tenant-b"
    # configuring explicit keys should not also expose the dev fallback
    assert get_tenant(DEFAULT_DEV_KEY) is None


def test_per_tenant_overrides_applied(monkeypatch):
    monkeypatch.setenv("GUARDRAIL_API_KEYS", "key-a:tenant-a:120:10:1800,key-b:tenant-b")
    a = get_tenant("key-a")
    b = get_tenant("key-b")
    assert (a.rate_limit_per_minute, a.offender_threshold, a.offender_window_seconds) == (120, 10, 1800)
    # tenant-b specified no overrides -> class defaults
    assert (b.rate_limit_per_minute, b.offender_threshold, b.offender_window_seconds) == (60, 5, 3600)


def test_blank_override_field_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("GUARDRAIL_API_KEYS", "key-a:tenant-a::10")
    a = get_tenant("key-a")
    assert a.rate_limit_per_minute == 60  # blank -> default
    assert a.offender_threshold == 10  # explicit override


def test_malformed_override_field_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("GUARDRAIL_API_KEYS", "key-a:tenant-a:not-a-number")
    a = get_tenant("key-a")
    assert a.rate_limit_per_minute == 60
