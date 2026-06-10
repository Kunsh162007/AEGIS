"""Model tier routing: `auto` must split traffic across tiers (reasoning vs.
specialist), an explicit provider must force one backend, mock stays mock, and a
missing key must fall back rather than crash."""
from __future__ import annotations

from src.config import settings
from src.models.client import ModelClient


def test_mock_always_resolves_mock():
    assert ModelClient(provider="mock")._resolve_provider("reasoning") == "mock"


def test_auto_routes_by_tier_when_keys_present(monkeypatch):
    monkeypatch.setattr(settings.providers["aimlapi"], "api_key", "k1")
    monkeypatch.setattr(settings.providers["featherless"], "api_key", "k2")
    client = ModelClient(provider="auto")
    assert client._resolve_provider("reasoning") == "aimlapi"
    assert client._resolve_provider("specialist") == "featherless"


def test_auto_falls_back_when_key_missing(monkeypatch):
    monkeypatch.setattr(settings.providers["aimlapi"], "api_key", "")
    # reasoning -> aimlapi, but no key -> fall back to the configured fallback.
    assert ModelClient(provider="auto")._resolve_provider("reasoning") == "ollama"


def test_explicit_provider_forces_all_tiers(monkeypatch):
    monkeypatch.setattr(settings.providers["featherless"], "api_key", "k")
    client = ModelClient(provider="featherless")
    assert client._resolve_provider("reasoning") == "featherless"
    assert client._resolve_provider("specialist") == "featherless"
