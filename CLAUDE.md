# CLAUDE.md — standing instructions for Claude Code CLI

This repo is **AEGIS**, an adversarial multi-agent AML investigation mesh.
Read `PROPOSAL.md` for the full design. Key standing rules:

1. **Verify Band first.** Before wiring real Band calls, read the official Band SDK
   docs (shared at/after the June 12 kickoff). DO NOT invent method names. Map the
   *behaviours* in `src/band/interface.py` to the real SDK; add `src/band/real.py`
   and switch `src/band/__init__.py:get_mesh()` over. The `LocalMesh` stub keeps
   everything runnable until then.
2. **The core runs offline.** `MODEL_PROVIDER=mock` runs the whole pipeline with no
   API keys. Keep it that way — every feature must degrade to mock.
3. **Specialists do REAL work.** Each specialist is backed by distinct machinery
   (stats / NetworkX graph / RAG), not just a prompt. Preserve that — it's the
   "are these real agents?" defence (PROPOSAL §5). The LLM only narrates.
4. **Evidence is mandatory.** Every `Evidence` carries a `source`. The Verifier
   rejects any uncited claim. Never relax this.
5. **Two frameworks on purpose.** Specialists → CrewAI, verification trio →
   LangGraph, coding agent → Codeband, all over Band. The framework-agnostic
   orchestrator is the default; `src/agents/frameworks/` is the production path.
   Don't collapse the split.
6. **Model tiers + caching.** Reasoning agents → AI/ML API, specialists →
   Featherless, Ollama fallback — all behind `src/models/client.py`. Cache on (§15).
7. **Public data for the headline number, synthetic for the demo storyline** (§9).
   Never use real PII.
8. **Run the checks before claiming done:**
   - `python -m src.main --fixture mule --consortium`
   - `python -m src.eval.harness --limit 40`
   - `python -m pytest tests/ -q`
9. **Delete dead code; secrets only in `.env`.** Windows shell + venv assumed.
