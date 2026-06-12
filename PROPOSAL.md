# AEGIS — Final Project Documentation

**A**gent-based **E**vidence-**G**rounded **I**nvestigation **S**ystem
*An autonomous financial-crime investigation department, run by one human.*

- **Live app:** https://aegis-g7vl.onrender.com
- **Repository:** https://github.com/Kunsh162007/AEGIS
- **Submissions:** Band of Agents Hackathon (Track 3 — Regulated & High-Stakes) · FAR AWAY 2026 (Agentic & Autonomous Systems)

---

## 1. The problem

Every bank must monitor transactions for money laundering. The detection
systems that do this bury human analysts under alerts — the overwhelming
majority false alarms. Banks respond with **hundreds of analysts** working the
backlog by hand: pull the history, check the profile, map the connections,
write the verdict. The result is slow, expensive, inconsistent, and still
inaccurate. Existing AI tools do **single-pass scoring** — one model emits a
risk number with no evidence and no audit trail, so no compliance officer
trusts it and the human re-investigates anyway.

The failure isn't "not enough AI". It's that *one model guessing once* is the
wrong shape for investigation, which is a **team activity**: specialists,
adversarial challenge, verification, institutional memory, quality control,
and a judgment about which cases a human even needs to see.

## 2. The solution

AEGIS is that team — **15 governed agents** that do the work of every analyst
role in a financial-intelligence unit, so that **one human** (the compliance
officer) runs what previously took a department:

| Analyst role in a real FIU | AEGIS agent(s) |
|---|---|
| L1 triage analyst | Intake & Orchestrator (risk-ranks accounts, recruits specialists per alert type) |
| L2 investigators | Transaction Pattern · Identity/KYC · Network/Graph · External Intelligence |
| In-house compliance analyst | **Org Policy** — applies the company's own watchlist, trusted counterparties, thresholds and historical baselines |
| Senior reviewer (devil's advocate) | **Challenger** — argues the innocent explanation for the specific money flows |
| Evidence auditor | **Verifier** — rejects every claim without a resolvable citation ("no evidence, no verdict") |
| Decision-maker | **Adjudicator** — verdict + confidence + the risk-based autonomy decision |
| QA reviewer | **Quality Auditor** — re-audits every finished case; blocks unsafe auto-clears |
| Institutional memory | **Pattern Memory** — cites what the officer decided on structurally identical cases before; flags novel patterns |
| Typology / intel analyst | **Strategic Intelligence** — cross-case briefing: emerging typologies, repeat subjects, bridge counterparties |
| SAR writer | **Report/Tooling** — drafts a FinCEN-style SAR with the verified evidence chain |
| Inter-bank liaison | **Consortium Liaison** — queries peer banks with abstract pattern descriptors, never records |
| Front desk | **Chat Analyst** — grounded Q&A over the casebook ("Ask AEGIS") |
| Compliance officer | **The one human**, deciding from the Command Center |

Every claim any agent makes must cite its source (`txn:`, `graph:`, `kb:`,
`kyc:`, `org:`, `memory:`); the Verifier rejects uncited or rebutted claims
and the Quality Auditor rejects unsound processes. The LLM narrates and
reasons — the **evidence itself comes from real machinery**: a statistical
pattern engine, a NetworkX entity graph, retrieval over a typology knowledge
base, baseline math over the org's own history.

## 3. How one investigation runs

```
upload (CSV/Excel/JSON/PDF) → risk triage selects focus accounts
  → Intake opens a governed case room, recruits specialists by alert type
  → specialists post CITED evidence (stats, graph, KYC, retrieval)
  → Org Policy applies the company's rules + the account's own baseline
  → Pattern Memory cites prior officer decisions on this structure
  → Challenger argues the innocent explanation (grounded in the actual flows)
  → Verifier audits every claim; uncited/rebutted claims are REJECTED on screen
  → Consortium Liaison may query peer banks (abstract patterns only)
  → Adjudicator: verdict + confidence + auto-clear/escalate decision
  → Quality Auditor re-audits the process; can block an unsafe auto-clear
  → escalated cases get a draft FinCEN-style SAR
  → the case files itself: priority score, SLA clock, review queue
```

Every step is a governed audit event streamed live to the dashboard — the
audit trail *is* the UI.

## 4. The Command Center — one human runs the department

Every verdict persists in a **casebook** (SQLite). The Command Center is the
operator's cockpit:

- **KPIs** — cases on file, auto-clear rate, pending/overdue reviews, average
  QA score, and estimated **analyst-hours saved** with the workload assumption
  printed beside the number (45 min manual per alert vs 10 min reviewing an
  AEGIS-prepared case).
- **Review queue** — escalated cases sorted by priority (verdict severity,
  confidence, money exposure, consortium confirmation, QA findings), each with
  an SLA countdown, the evidence chain, the draft SAR, and Confirm / Dismiss.
- **Strategic intelligence** — the cross-case briefing, including potentially
  **novel patterns** (laundering-shaped structure matching no known typology)
  and consortium-ready descriptors shown verbatim, so "no customer data ever
  crosses" is provable on screen.

## 5. It improves with every analysis — three learning loops

1. **Threshold tuning** — every officer decision nudges the auto-clear
   confidence bar (visible on screen: `0.6 → 0.58`), persisted across
   restarts.
2. **Reviewed precedent** — decided cases enter the knowledge base and are
   retrieved on similar future cases.
3. **Pattern memory** — every case files an abstract structural signature
   (typology, fan-in bucket, near-threshold bucket, pass-through, burst).
   When the officer confirms or dismisses a case, the *next* case with the
   same signature receives that judgment as cited evidence — the same false
   positive is never raised twice, and a confirmed scheme is recognised on
   sight.

## 6. Personalised to the organisation

Companies are not interchangeable, and neither are their risks. An org
registers its profile (watchlist, trusted counterparties, internal reporting
threshold, policy notes) and uploads **its own historical data**, from which
AEGIS builds per-account behavioural baselines. From then on, "unusual" means
*unusual for that account's own history* — and watchlisted counterparties
weigh against a case while vetted ones clear flags. Two organisations running
AEGIS on the same file get different, correctly personalised answers.

## 7. Trust architecture

- **No evidence, no verdict** — enforced by the Verifier, audited by QA.
- **Credential traversal** — agents only touch data within the officer's
  scopes; denials are recorded audit events.
- **Human-gated consequences** — AEGIS never files a SAR or closes a
  consequential case alone; it prepares the defensible case and escalates.
- **No demo content** — every number in the product is computed from data the
  user supplied. There are no canned cases anywhere.
- **Accuracy measured externally** — on a bundled, externally-labelled slice
  of the public IBM AML dataset (CLI: `python -m src.eval.harness`), AEGIS
  cuts false positives by **~77%** while holding the baseline's catch rate
  (~89% vs ~90%). Method and provenance: `src/data/benchmarks/README.md`.
- **Production controls** — optional `X-API-Key` auth on state-changing
  endpoints, size-capped in-memory file parsing, persistent learned state.

## 8. Technology

| Layer | Choice |
|---|---|
| Coordination & governance | **Band** (live remote agent `src/band/band_agent.py`; in-process governed mesh for the pipeline) |
| Frontier reasoning | **AI/ML API** — Challenger, Verifier-tier narration, Adjudicator, Chat Analyst |
| Open-source inference | **Featherless AI** — the specialist agents |
| Frameworks | **LangGraph** StateGraph for the verification trio; CrewAI adapter for specialists (`USE_FRAMEWORKS=true`) |
| Machinery | NetworkX entity graph · statistical pattern engine · keyword/vector retrieval (Chroma-ready) |
| Backend | FastAPI + NDJSON streaming; SQLite casebook |
| Frontend | Next.js (static export served by the API — one origin, one service) |
| Deploy | Docker on Render; CI-free single-image build |

## 9. API surface

| Endpoint | What |
|---|---|
| `POST /api/analyze` / `POST /api/analyze/stream` | investigate an uploaded file (stream = live audit feed) |
| `GET /api/cases` · `GET /api/cases/{uid}` | the review queue / full case detail |
| `POST /api/cases/{uid}/decision` | the officer's confirm/dismiss — feeds all three learning loops |
| `GET /api/operations` | department KPIs + learned policy state |
| `GET /api/intel/briefing` | cross-case intelligence incl. novel patterns |
| `POST /api/chat` | grounded Q&A over the casebook |
| `GET /api/typologies` | the fraud-typology library |
| `GET/POST /api/org/profile` · `POST /api/org/history` | org personalisation |
| `GET /api/health` | liveness |

## 10. Repository layout

```
src/agents/     one module per agent (15)
src/casework/   casebook, priority/SLA, org profiles, pattern signatures, department state
src/band/       Band contract + governed local mesh + live Band remote agent
src/models/     unified AI/ML API / Featherless / Ollama / mock client with caching
src/graph/ src/knowledge/ src/policy/ src/feedback/   the specialists' machinery
src/data/       case schema, upload parsing, public-benchmark loader (+ bundled IBM slice)
src/eval/       CLI accuracy harness (baseline vs AEGIS, public labels)
src/api/        FastAPI backend + static dashboard serving
dashboard/      Next.js UI (Analyze · Command Center · Ask AEGIS)
examples/       static sample datasets (see below)
tests/          68 offline tests (MODEL_PROVIDER=mock; in-memory casebook)
```

**Sample data** (static files; the repo ships no generation code):
- `examples/sample_transactions.csv` — small starter (a mule ring + structuring + benign accounts)
- `examples/test_dataset.csv` / `.xlsx` — ~190 transactions hiding a mule, cash structuring and a layering cycle among ordinary activity
- `examples/regional_bank_week.csv` — 112 transactions: a fan-in mule (`COLLECT-7`), slow-burn structuring (`DEPOT-CASH-9`), a payroll population that auto-clears, and `fatima` — a deliberate borderline the system *escalates rather than guesses*, so you can demo the human gate and watch the learning loop move.

## 11. Honest limitations & future work

- The deployed free tier has an ephemeral disk: the live casebook resets on
  redeploy/sleep (a persistent disk or managed Postgres is the production
  path).
- The feedback loop tunes thresholds and retrieval — it does not retrain
  models (framed honestly throughout).
- Sanctions/PEP context is synthetic; a production deployment would wire real
  list providers behind the same `kyc:` evidence interface.
- The consortium runs on simulated peer tenants over the governed mesh; the
  Band rooms make multi-institution deployment the natural next step.

---

*Built with Band, AI/ML API, Featherless, LangGraph and CrewAI for the Band of
Agents Hackathon and FAR AWAY 2026. No real PII anywhere. Co-built with Claude
Code.*
