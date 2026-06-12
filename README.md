# AEGIS — A Self-Verifying, Autonomous Financial-Crime Investigation Mesh

> An adversarial team of governed agents investigates each AML alert, **argues
> against itself**, refuses any conclusion that isn't backed by cited evidence,
> **auto-clears the easy cases and escalates only what matters to a human**, and
> can strengthen its judgment using patterns shared by peer banks **without any
> customer data crossing a boundary** — coordinated, governed, and audited
> through **Band**.

---

## ✨ Why this isn't an "AI wrapper"

- **Adversarial verification, not one-pass scoring.** A *Challenger* argues the
  innocent explanation; a *Verifier* rejects any uncited or rebutted claim; an
  *Adjudicator* decides on the surviving, verified evidence only.
- **Real machinery per agent.** The Transaction agent runs statistics, the
  Network agent runs a real NetworkX graph (mule hubs, cycles), the External
  Intelligence agent runs retrieval. The LLM only narrates.
- **Risk-based autonomy.** An explicit, auditable policy auto-clears
  confidently-benign cases and escalates the rest — and a **Quality Auditor
  agent** re-audits every finished investigation and *blocks* any auto-clear
  that fails a critical control.
- **A whole department, not a request handler.** Every verdict is filed in a
  persistent casebook with a priority score and an SLA clock; a **Strategic
  Intelligence agent** reads across all cases to find what no single
  investigation can see (recurring typologies, one counterparty quietly
  bridging separate cases). One human runs it all from the **Command Center**.
- **It gets better with every analysis.** Beyond threshold tuning: every case
  files an abstract **pattern signature**; officer decisions mark patterns
  confirmed or dismissed, and the **Pattern Memory agent** cites that
  institutional memory as evidence on the next structurally-identical case.
  Suspicious structure matching *no* library typology is flagged as a
  **potentially novel pattern**.
- **Personalised to the organisation.** A company registers its own watchlist,
  vetted counterparties, reporting threshold and policy notes, and uploads its
  historical data — the **Org Policy agent** then judges "unusual" against
  each account's *own* baseline, not an abstract norm.
- **You can talk to it.** The **Ask AEGIS** chat answers questions about the
  data and cases — facts are computed from the casebook; the LLM only phrases
  them.
- **Measured accuracy on a public benchmark** (IBM AML) via the CLI eval
  harness — not a self-graded number.
- **Governed + auditable on Band**, with credential traversal and a human gate.

## 🚀 Quick start (runs offline, no API keys)

```powershell
# from the repo root:  aegis\
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt          # or the minimal set: pydantic python-dotenv networkx fastapi "uvicorn[standard]" python-multipart pandas
copy .env.example .env                    # MODEL_PROVIDER=mock works with no keys

# 1) Investigate a real transaction file end-to-end (watch the agents work):
python -m src.main examples\sample_transactions.csv
python -m src.main your_ledger.xlsx --focus ACC1042   # one named account
python -m src.main export.json --limit 3              # top-3 risk-triaged accounts

# 2) The accuracy number (baseline vs AEGIS, externally-labelled public data):
python -m src.eval.harness --public --limit 200       # bundled IBM AML slice / PUBLIC_DATASET_PATH

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

Drop in a transaction file (CSV / Excel / JSON / text-based PDF — try
`examples/sample_transactions.csv`), press **Run investigation** and watch the
agents join, post cited evidence, get challenged, have claims rejected, and
reach an auto-clear/escalate decision live — on *your* data. Each verdict also
**marks the suspicious rows of your dataset** (which transactions, and why)
and explains **each fraud type discovered**. The **Ask AEGIS** tab is a
grounded chat over everything analysed.

## 🧑‍✈️ Command Center — one human runs the whole department

Every investigation files itself into a persistent **casebook** (SQLite —
`AEGIS_DB_PATH`, default `.cache/aegis.db`). The **Command Center** tab is the
single operator's cockpit over it:

- **KPIs**: cases on file, auto-clear rate, pending/overdue reviews, average
  QA score, and **estimated analyst-hours saved** — with the workload
  assumptions printed next to the number, not hidden behind it.
- **Review queue**: escalated cases sorted by priority, each with an SLA
  countdown, the verified evidence chain, the QA findings, the draft
  FinCEN-style SAR, and two buttons: **Confirm** / **Dismiss**.
- **The learning loop, on screen**: each decision visibly moves the
  auto-clear bar (`0.6 → 0.58`) and files reviewed precedent the agents
  retrieve on similar future cases. Both survive a restart.
- **Strategic intelligence**: the cross-case agent's briefing — emerging
  typologies, repeat subjects, counterparties bridging otherwise separate
  investigations, and the consortium-ready *abstract* pattern descriptors
  shown verbatim (so "no data crossed" is provable, §7).

API surface: `GET /api/cases`, `GET /api/cases/{uid}`,
`POST /api/cases/{uid}/decision` (`{"decision": "confirm"|"dismiss"}`),
`GET /api/operations`, `GET /api/intel/briefing` (now incl. novel-pattern
alerts), `POST /api/chat`, `GET /api/typologies`, `GET|POST /api/org/profile`,
`POST /api/org/history`. Set `AEGIS_API_KEY` to require an `X-API-Key` header
on all state-changing endpoints (open by default for local/demo use; the
dashboard picks a key up from `localStorage["aegis_api_key"]`).

## 🔌 Switching on real models (optional)

Edit `.env`:

| Want | Set |
|------|-----|
| **Tiered (recommended): reasoning→AI/ML API, specialists→Featherless** | `MODEL_PROVIDER=auto` (+ `AIMLAPI_KEY`, `FEATHERLESS_KEY`) |
| Force frontier reasoning everywhere | `MODEL_PROVIDER=aimlapi`, `AIMLAPI_KEY=...` |
| Force open-source everywhere | `MODEL_PROVIDER=featherless`, `FEATHERLESS_KEY=...` |
| Free local fallback | `MODEL_PROVIDER=ollama` (install Ollama, `ollama pull llama3.1`) |

Any tier whose key is missing falls back to Ollama automatically, so a partly-configured `.env` never crashes.

Responses are cached on disk (`MODEL_CACHE=true`) so re-running the same case costs nothing.
The specialists' *real* signal (stats/graph/retrieval) works the same regardless of
provider. With a reasoning key on, the **Challenger** additionally uses the model to
propose case-specific *innocent explanations* (generalising the keyword list) — the
Verifier still gates them, and they can only clear soft profile flags, never
structural laundering evidence. Everything degrades to mock if a call fails.

## 📊 The public accuracy benchmark (the credible number — §9)

A small, balanced, **externally-labelled** slice of the **IBM AML** dataset
ships with the repo (`src/data/benchmarks/ibm_sample.csv`), so the credible
number works out-of-the-box via the CLI harness
(`python -m src.eval.harness`). It is deliberately **not part of the product
UI** — the app shows only what was computed from the user's own data; the
benchmark exists for the slide and the README. No download, no keys.

On this slice (200 cases) AEGIS cuts false positives by **~77%** while holding
the catch rate at the baseline's level (**~89% vs ~90%**). Recall is shown next
to the reduction — AEGIS is a triage layer, strongest on *structured*
laundering. The benchmark always runs the deterministic pipeline (the
architecture is computation; LLMs only narrate), so the number is reproducible
and identical with or without live model keys. Provenance and method:
[`src/data/benchmarks/README.md`](./src/data/benchmarks/README.md).

> **Why IBM AML, not PaySim?** PaySim's labelled "fraud" is balance-draining
> theft with no laundering *structure* (its mule transfers and cash-outs aren't
> even linked), so AEGIS correctly abstains and the dataset is a poor fit. IBM
> AML is generated from real laundering typologies (fan-in/out, cycles) — the
> structure AEGIS detects.

To score a **full** dataset yourself, point `.env` at a CSV and run
`python -m src.eval.harness`:

| `PUBLIC_DATASET_KIND` | Dataset |
|-----------------------|---------|
| `ibm_aml`  | *IBM Transactions for Anti-Money-Laundering* (recommended) |
| `paysim`   | *PaySim* synthetic mobile-money fraud |
| `elliptic` | *Elliptic* Bitcoin licit/illicit graph |

The labels are external, so the false-positive-reduction number is defensible.

## 🧱 Architecture

```
alert → Intake opens a Band room + recruits specialists by alert type
      → Transaction / Network / Identity / External-Intel post CITED evidence
      → Org Policy applies the COMPANY'S rules + each account's own baseline
      → Pattern Memory cites what the officer decided on this structure before
      → Challenger argues the innocent case
      → Verifier audits every claim (rejects uncited / rebutted)
      → Consortium Liaison asks peer banks about the ABSTRACT pattern only
      → Adjudicator: verdict + confidence + autonomy decision
      → Quality Auditor re-audits the process (blocks unsafe auto-clears)
      → auto-clear (logged) OR escalate → Report agent drafts the SAR
      → every step is a governed audit event, streamed live to the dashboard
      → the verdict is FILED in the casebook: priority, SLA clock, review queue
      → the officer decides from the Command Center → thresholds retune,
        precedent is stored → Strategic Intelligence briefs across all cases
```

See `src/` for one module per concern and `src/agents/` for one module per agent.

## 🗂️ Layout

| Path | What |
|------|------|
| `src/agents/` | the 15-agent roster (specialists + verification trio + consortium + report + quality auditor + strategic intelligence + **org policy** + **pattern memory** + **chat analyst**) |
| `src/casework/` | the department layer: persistent casebook (SQLite), priority/SLA model, org profile + baselines, pattern memory, shared learned state |
| `src/band/` | Band layer: abstract `interface.py` + in-process `stub.py` + **`band_agent.py` (live agent on the real Band platform)** |
| `src/models/` | unified AI/ML API + Featherless + Ollama + mock client, with caching |
| `src/graph/` | NetworkX entity graph (mule hubs, cycles) |
| `src/knowledge/` | typology / adverse-media retrieval + reviewed precedent |
| `src/policy/` | risk-based autonomy thresholds |
| `src/feedback/` | human-decision capture + threshold tuning |
| `src/data/` | case schema, synthetic generator, public-dataset loader |
| `src/eval/` | baseline-vs-AEGIS accuracy harness |
| `src/api/` | FastAPI backend + NDJSON live investigation stream |
| `dashboard/` | Next.js live investigation UI |

## 🎸 AEGIS on Band (live platform integration)

AEGIS runs as a **remote agent on the Band platform** ([band.ai](https://band.ai)) —
a compliance officer in a Band chatroom can paste transaction rows, @mention
AEGIS, and get the governed verdict posted back into the shared room:

```text
@AEGIS investigate these transactions
from,to,amount,date,type
a1,MULE-7,9400,2026-03-01 10:00,TRANSFER
a2,MULE-7,9100,2026-03-01 11:00,TRANSFER
...
```

Setup (~5 min):

1. Install the SDK (PyPI lags the module rename, so install from git):
   ```powershell
   git clone --depth 1 https://github.com/thenvoi/thenvoi-sdk-python.git $env:TEMP\band-sdk-src
   pip install "$env:TEMP\band-sdk-src[langgraph]"
   ```
2. Sign in at [app.band.ai](https://app.band.ai) → create a **remote agent**
   named `AEGIS` → copy its **agent UUID** and **API key** into `.env` as
   `BAND_AGENT_ID` / `BAND_AGENT_KEY`.
3. Set `AIMLAPI_KEY` too — the Band agent's conversational brain runs on the
   AI/ML API reasoning tier (falls back to local Ollama without it).
4. Run it and leave it running, then chat with it in any Band room:
   ```powershell
   python -m src.band.band_agent
   ```

The internal pipeline still runs on the in-process mesh (`stub.py`) so the
website works with zero keys; the Band agent is the door between Band rooms and
that pipeline.

## ⚠️ Status & honesty notes

- **Band**: the live platform integration is `src/band/band_agent.py` (above);
  the internal agent-to-agent mesh remains the local, auditable `stub.py`.
- **LangGraph** powers the verification trio as a real `StateGraph` when
  `USE_FRAMEWORKS=true` (runs offline, no keys); **CrewAI** wraps the specialist
  crew (heavier, may need a key). The core also runs framework-agnostic so it
  always works offline, and each adapter degrades if its lib is absent. See
  `src/agents/frameworks/`.
- **Every verdict shown in the app is computed from data the user supplied**
  (or, in the Benchmark tab, from a public externally-labelled dataset). There
  are no canned demo cases. No real PII anywhere.

Co-built with Claude Code.
