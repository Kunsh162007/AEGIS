# AEGIS — A Self-Verifying, Autonomous Financial-Crime Investigation Mesh

> An adversarial team of governed agents investigates each AML alert, **argues
> against itself**, refuses any conclusion that isn't backed by cited evidence,
> **auto-clears the easy cases and escalates only what matters to a human**, and
> can strengthen its judgment using patterns shared by peer banks **without any
> customer data crossing a boundary** — coordinated, governed, and audited
> through **Band**.

Dual submission: **Band of Agents Hackathon** (Track 3) + **FAR AWAY 2026**.

---

## ✨ Why this isn't an "AI wrapper"

- **Adversarial verification, not one-pass scoring.** A *Challenger* argues the
  innocent explanation; a *Verifier* rejects any uncited or rebutted claim; an
  *Adjudicator* decides on the surviving, verified evidence only.
- **Real machinery per agent.** The Transaction agent runs statistics, the
  Network agent runs a real NetworkX graph (mule hubs, cycles), the External
  Intelligence agent runs retrieval. The LLM only narrates.
- **Risk-based autonomy.** An explicit, auditable policy auto-clears
  confidently-benign cases and escalates the rest.
- **Measured accuracy on a public benchmark** (PaySim / IBM AML / Elliptic) —
  not a self-graded number.
- **Governed + auditable on Band**, with credential traversal and a human gate.

## 🚀 Quick start (runs offline, no API keys)

```powershell
# from the repo root:  aegis\
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt          # or the minimal set: pydantic python-dotenv networkx fastapi "uvicorn[standard]" sse-starlette pandas scikit-learn
copy .env.example .env                    # MODEL_PROVIDER=mock works with no keys

# 1) Run a single investigation end-to-end (watch the agents work):
python -m src.main --fixture structuring
python -m src.main --fixture salary       # benign-but-flagged -> auto-cleared
python -m src.main --fixture mule --consortium   # headline: cross-bank confirmation

# 2) The accuracy number (baseline vs AEGIS):
python -m src.eval.harness --limit 40                 # synthetic sanity check
python -m src.eval.harness --public --limit 200       # public benchmark (set PUBLIC_DATASET_PATH)

# 3) The tests:
python -m pytest tests/ -q
```

> On Windows, prefix with `$env:PYTHONUTF8=1` (or run inside the activated venv)
> so the emoji in the live feed render.

## 🖥️ The live dashboard

```powershell
# terminal 1 — backend
uvicorn src.api.main:app --reload --port 8000

# terminal 2 — dashboard
cd dashboard
npm install
npm run dev          # http://localhost:3000  (proxies /api/* to :8000)
```

Pick a fixture, tick *cross-bank consortium*, press **Run investigation** and
watch agents join, post cited evidence, get challenged, have claims rejected, and
reach an auto-clear/escalate decision live. Then **Run accuracy eval** for the
baseline-vs-AEGIS panel.

## 🔌 Switching on real models (optional)

Edit `.env`:

| Want | Set |
|------|-----|
| Frontier reasoning (Challenger/Verifier/Adjudicator) | `MODEL_PROVIDER=aimlapi`, `AIMLAPI_KEY=...` |
| Open-source specialists | `MODEL_PROVIDER=featherless`, `FEATHERLESS_KEY=...` |
| Free local fallback | `MODEL_PROVIDER=ollama` (install Ollama, `ollama pull llama3.1`) |

Responses are cached on disk (`MODEL_CACHE=true`) so re-running a demo costs nothing.
The specialists' *real* signal (stats/graph/retrieval) works the same regardless of
provider — the model only writes the narration.

## 📊 The public accuracy benchmark (the credible number — §9)

Download one of these free Kaggle datasets and point `.env` at the CSV:

| `PUBLIC_DATASET_KIND` | Dataset |
|-----------------------|---------|
| `paysim`   | *PaySim* synthetic mobile-money fraud |
| `ibm_aml`  | *IBM Transactions for Anti-Money-Laundering* |
| `elliptic` | *Elliptic* Bitcoin licit/illicit graph |

```
PUBLIC_DATASET_PATH=C:\path\to\dataset.csv
PUBLIC_DATASET_KIND=paysim
```
Then `python -m src.eval.harness --public`. The labels are external, so the
false-positive-reduction number is defensible — that's the one for the slide.

## 🧱 Architecture

```
alert → Intake opens a Band room + recruits specialists by alert type
      → Transaction / Network / Identity / External-Intel post CITED evidence
      → Challenger argues the innocent case
      → Verifier audits every claim (rejects uncited / rebutted)
      → Consortium Liaison asks peer banks about the ABSTRACT pattern only
      → Adjudicator: verdict + confidence + autonomy decision
      → auto-clear (logged) OR escalate → Report agent drafts the SAR
      → every step is a governed audit event, streamed live to the dashboard
```

See `src/` for one module per concern and `src/agents/` for one module per agent.

## 🗂️ Layout

| Path | What |
|------|------|
| `src/agents/` | the 10-agent roster (specialists + verification trio + consortium + report) |
| `src/band/` | Band transport: abstract `interface.py` + runnable `stub.py` (swap in the real SDK) |
| `src/models/` | unified AI/ML API + Featherless + Ollama + mock client, with caching |
| `src/graph/` | NetworkX entity graph (mule hubs, cycles) |
| `src/knowledge/` | typology / adverse-media retrieval + reviewed precedent |
| `src/policy/` | risk-based autonomy thresholds |
| `src/feedback/` | human-decision capture + threshold tuning |
| `src/data/` | case schema, synthetic generator, public-dataset loader |
| `src/eval/` | baseline-vs-AEGIS accuracy harness |
| `src/api/` | FastAPI backend + SSE live stream |
| `dashboard/` | Next.js live investigation UI |

## ⚠️ Status & honesty notes

- **Band** is behind a local stub until the official SDK is wired (kickoff). Agent
  logic is decoupled so this is a clean swap, not a rewrite.
- **CrewAI / LangGraph** are the intended production frameworks; the core runs
  framework-agnostic so it's always demoable. See `src/agents/frameworks/`.
- **Synthetic eval numbers are a sanity check; the public-benchmark number is the
  real one.** No real PII anywhere.

Co-built with Claude Code.
