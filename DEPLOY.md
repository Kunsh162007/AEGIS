# Deploying AEGIS

AEGIS deploys as **one Docker web service**: the FastAPI backend serves both the
JSON/SSE API *and* the pre-built Next.js dashboard on a single public URL. No
second service, no CORS, no proxy.

**It runs with zero API keys.** The default `MODEL_PROVIDER=mock` runs the entire
agent pipeline deterministically — the live demo, the cited-evidence chain, the
auto-clear/escalate decision, the cross-bank consortium match, and the
baseline-vs-AEGIS accuracy panel all work with nothing to sign up for. API keys
are *optional* upgrades (see the bottom).

---

## What you need (checklist)

| Thing | Required? | Why |
|-------|-----------|-----|
| A GitHub account | ✅ yes | Render deploys from a GitHub repo |
| A Render account (free) | ✅ yes | https://render.com — sign in with GitHub |
| Any API key | ❌ no | Mock mode is fully functional for the demo |
| A public AML dataset (PaySim/IBM/Elliptic) | ⚪ optional | Only for the *public-benchmark* headline accuracy number (§9) |

---

## Deploy to Render (one-time, ~10 min)

### 1. Push this folder to GitHub

A git repo has already been initialized in `aegis/` with everything committed.
Create an empty repo on GitHub (no README/.gitignore), then:

```powershell
# from the aegis\ folder
git remote add origin https://github.com/<YOUR_USERNAME>/aegis.git
git branch -M main
git push -u origin main
```

### 2. Create the service on Render

1. Go to **https://dashboard.render.com** → **New** → **Blueprint**.
2. Connect the GitHub repo you just pushed.
3. Render auto-detects [`render.yaml`](./render.yaml) and shows one service, **aegis**, on the **free** plan. Click **Apply**.
4. First build takes ~5–8 min (it builds the dashboard, then the Python image).
   Watch the logs; it's healthy once `/api/health` returns `200`.

Your demo is live at **`https://aegis-<random>.onrender.com`** — open it and the
dashboard loads directly. Pick a fixture → **Run investigation** → watch the
agents work; tick **cross-bank consortium** for the headline match; **Run accuracy
eval** for the metrics panel.

> **Free-tier note:** Render free services sleep after ~15 min idle and cold-start
> in ~50s on the next hit. For a live demo, open the URL a minute before you
> present so it's warm. Upgrading to the $7/mo Starter plan removes the sleep —
> change `plan: free` → `plan: starter` in `render.yaml`.

### Redeploys
With `autoDeploy: true`, every `git push` to `main` triggers a rebuild. No extra steps.

---

## Run it locally with Docker (optional sanity check)

```powershell
# from the aegis\ folder
docker build -t aegis .
docker run --rm -p 8000:8000 aegis
# open http://localhost:8000
```

---

## Turning on real models / Band (all optional)

Everything below is an upgrade from mock mode. **Add these as environment
variables in the Render dashboard** (Service → *Environment* → *Add Environment
Variable*), then redeploy. Never commit keys to git.

| Goal | Env vars to set on Render | Where to get the key |
|------|---------------------------|----------------------|
| Frontier reasoning for Challenger/Verifier/Adjudicator | `MODEL_PROVIDER=aimlapi`, `AIMLAPI_KEY=…` | https://aimlapi.com (free starter credit) |
| Open-source models for the specialists | `MODEL_PROVIDER=featherless`, `FEATHERLESS_KEY=…` | https://featherless.ai |
| AEGIS as a live agent on the Band platform | `BAND_AGENT_ID=…`, `BAND_AGENT_KEY=…` (run `python -m src.band.band_agent` — see README "AEGIS on Band") | https://app.band.ai → create a remote agent |
| Public-benchmark headline accuracy (§9) | `PUBLIC_DATASET_PATH=…`, `PUBLIC_DATASET_KIND=paysim\|ibm_aml\|elliptic` | Kaggle (download a CSV; see README §9) |

Notes:
- **The Band agent is a separate long-running process** (it holds a WebSocket to
  Band Cloud), not an endpoint of the web service. For the demo, run it on your
  laptop (`python -m src.band.band_agent`) — it works from anywhere with internet;
  the deployed website doesn't need it. To run it 24/7 instead, add a Render
  **Background Worker** with the same repo and start command
  `python -m src.band.band_agent`.
- `MODEL_CACHE=true` (already set) caches LLM responses on disk so re-running a
  demo costs nothing. On Render's ephemeral free disk the cache resets on
  redeploy — fine for a demo; attach a Render Disk if you want it to persist.
- **The public-benchmark number works on the deployed demo out of the box** — a
  small IBM-AML slice (`src/data/benchmarks/ibm_sample.csv`) ships in the image,
  so the dashboard's "Run public benchmark (IBM AML)" button needs no dataset and
  no keys. To score a *full* dataset, set `PUBLIC_DATASET_PATH` (the CSV must be
  inside the image or on a mounted disk) and run `python -m src.eval.harness
  --public`.
- Ollama (`MODEL_PROVIDER=ollama`) is a *local-only* fallback — it expects a
  server on `localhost:11434`, so it isn't used in the cloud deploy.

---

## Files involved

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage: Node builds the static dashboard → Python runs the API serving it |
| `render.yaml` | Render Blueprint (one free Docker web service, mock mode, health check) |
| `.dockerignore` | Keeps the build context small |
| `dashboard/next.config.js` | `STATIC_EXPORT=1` → static export (prod); otherwise dev proxy |
| `src/api/main.py` | Mounts `dashboard/out` as static files when present (single origin) |
