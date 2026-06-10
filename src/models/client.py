"""ModelClient — one call routes to the right backend by tier.

Providers:
  - mock        : deterministic, offline, no key. Lets the WHOLE system run
                  with zero credits.
  - aimlapi     : frontier reasoning (OpenAI-compatible).
  - featherless : open-source models (OpenAI-compatible).
  - ollama      : local fallback (OpenAI-compatible).

The specialists do their *real* work in Python (stats / graph / retrieval);
the model only narrates and reasons. So `mock` still yields a genuine verdict.
"""
from __future__ import annotations

from ..config import ProviderConfig, settings
from .cache import ResponseCache

# Per-agent token accounting, surfaced to the audit stream (§15).
TOKEN_LEDGER: list[dict] = []


class ModelClient:
    def __init__(self, provider: str | None = None):
        self.provider = (provider or settings.provider).lower()
        self.cache = ResponseCache() if settings.cache_enabled else None
        self._openai = None  # lazily created

    # -- public API --------------------------------------------------------
    def complete(self, prompt: str, *, tier: str = "specialist", agent: str = "?",
                 system: str = "", max_tokens: int = 512) -> str:
        provider = self._resolve_provider(tier)
        cfg = settings.providers.get(provider)
        model = cfg.model if cfg else "mock"

        cache_key = f"{system}\n---\n{prompt}"
        if self.cache:
            hit = self.cache.get(provider, model, cache_key)
            if hit is not None:
                return hit

        if provider == "mock" or self.provider == "mock":
            text = self._mock(prompt, system=system, agent=agent)
        else:
            # Every feature must degrade to mock (CLAUDE rule 2): if a real
            # provider errors (bad/missing key, network, rate limit, Ollama not
            # running), fall back to deterministic mock narration so a live demo
            # never crashes. The fallback is recorded transparently in the ledger.
            try:
                text = self._openai_compatible(cfg, prompt, system=system, max_tokens=max_tokens)
            except Exception:
                provider, model = f"{provider}->mock", "mock"
                text = self._mock(prompt, system=system, agent=agent)

        TOKEN_LEDGER.append({"agent": agent, "provider": provider, "model": model,
                             "approx_tokens": len(prompt) // 4 + len(text) // 4})
        if self.cache:
            self.cache.set(provider, model, cache_key, text)
        return text

    # -- provider resolution ----------------------------------------------
    def _resolve_provider(self, tier: str) -> str:
        """Pick the backend for this call.

          mock              -> everything offline (no keys).
          auto              -> route BY TIER (reasoning->aimlapi, specialist->
                               featherless, ...) per settings.tier_routing.
          <a named provider> -> force that one provider for every tier.

        In every case, if the chosen provider has no API key we fall back to the
        configured fallback (Ollama, which needs none) so a half-configured .env
        never crashes mid-run.
        """
        if self.provider == "mock":
            return "mock"
        chosen = (settings.tier_routing.get(tier, settings.tier_routing.get("fallback", "ollama"))
                  if self.provider == "auto" else self.provider)
        cfg = settings.providers.get(chosen)
        if cfg and not cfg.api_key and chosen != "ollama":
            return settings.tier_routing.get("fallback", "ollama")
        return chosen

    # -- OpenAI-compatible backends ---------------------------------------
    def _openai_compatible(self, cfg: ProviderConfig, prompt: str, *, system: str,
                           max_tokens: int) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("`openai` package not installed; `pip install openai` "
                               "or set MODEL_PROVIDER=mock") from exc
        client = OpenAI(api_key=cfg.api_key or "none", base_url=cfg.base_url)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = client.chat.completions.create(
            model=cfg.model, messages=messages, max_tokens=max_tokens, temperature=0.2,
        )
        return (resp.choices[0].message.content or "").strip()

    # -- deterministic offline mock ---------------------------------------
    def _mock(self, prompt: str, *, system: str, agent: str) -> str:
        """Return a short, plausible narration. The real signal comes from the
        agents' Python machinery, not from here — this only writes prose so the
        demo reads naturally without any API key."""
        head = prompt.strip().splitlines()[0] if prompt.strip() else ""
        return f"[{agent}] {head[:200]}"


_default = ModelClient()


def complete(prompt: str, **kwargs) -> str:
    return _default.complete(prompt, **kwargs)
