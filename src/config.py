"""Central configuration, loaded from environment / .env.

Every tunable lives here so the rest of the code never reads os.environ directly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class ProviderConfig:
    api_key: str
    base_url: str
    model: str


@dataclass
class Settings:
    provider: str = os.getenv("MODEL_PROVIDER", "mock").strip().lower()
    use_frameworks: bool = _bool("USE_FRAMEWORKS", False)
    cache_enabled: bool = _bool("MODEL_CACHE", True)
    cache_dir: Path = ROOT / ".cache"

    # The department casebook (SQLite). ":memory:" gives an ephemeral store.
    db_path: str = os.getenv("AEGIS_DB_PATH", str(ROOT / ".cache" / "aegis.db")).strip()
    # Optional production auth: when set, state-changing API endpoints require
    # an X-API-Key header carrying this value. Unset (default) = open.
    api_key: str = os.getenv("AEGIS_API_KEY", "").strip()

    # Public benchmark dataset (Section 9)
    public_dataset_path: str = os.getenv("PUBLIC_DATASET_PATH", "").strip()
    public_dataset_kind: str = os.getenv("PUBLIC_DATASET_KIND", "paysim").strip().lower()

    providers: dict = field(default_factory=lambda: {
        "aimlapi": ProviderConfig(
            api_key=os.getenv("AIMLAPI_KEY", ""),
            base_url=os.getenv("AIMLAPI_BASE_URL", "https://api.aimlapi.com/v1"),
            model=os.getenv("AIMLAPI_MODEL", "gpt-4o-mini"),
        ),
        "featherless": ProviderConfig(
            api_key=os.getenv("FEATHERLESS_KEY", ""),
            base_url=os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"),
            model=os.getenv("FEATHERLESS_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct"),
        ),
        "ollama": ProviderConfig(
            api_key="ollama",  # Ollama ignores the key
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            model=os.getenv("OLLAMA_MODEL", "llama3.1"),
        ),
    })

    band: dict = field(default_factory=lambda: {
        # Each remote agent created at https://app.band.ai gets its own UUID +
        # API key — used by src/band/band_agent.py (the real Band integration).
        "agent_id": os.getenv("BAND_AGENT_ID", ""),
        "agent_key": os.getenv("BAND_AGENT_KEY", ""),
        "tenant_id": os.getenv("BAND_TENANT_ID", "bank-alpha"),
    })

    # Which provider each "tier" maps to. AI/ML API for heavy reasoning,
    # Featherless for high-volume specialists, Ollama as fallback. (§5, §15)
    tier_routing: dict = field(default_factory=lambda: {
        "reasoning": "aimlapi",
        "specialist": "featherless",
        "fallback": "ollama",
    })


settings = Settings()
