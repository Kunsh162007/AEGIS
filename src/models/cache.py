"""Tiny on-disk response cache keyed on (provider, model, prompt).

Re-running the same case during development costs zero tokens (§15).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..config import settings


class ResponseCache:
    def __init__(self, directory: Path | None = None):
        self.dir = directory or settings.cache_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def _key(self, provider: str, model: str, prompt: str) -> str:
        raw = f"{provider}::{model}::{prompt}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:32]

    def get(self, provider: str, model: str, prompt: str) -> str | None:
        path = self.dir / f"{self._key(provider, model, prompt)}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))["response"]
        return None

    def set(self, provider: str, model: str, prompt: str, response: str) -> None:
        path = self.dir / f"{self._key(provider, model, prompt)}.json"
        path.write_text(json.dumps({"response": response}), encoding="utf-8")
