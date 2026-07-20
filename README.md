# AutoBOM

Internal engineering → production → purchasing → inventory workflow platform.
Local-first (runs entirely on a laptop, no Azure) and Azure-ready via graceful
fallback on environment variables.

- **Frontend** — the working prototype (React 18), wrapped in Vite. `frontend/`
- **Backend** — FastAPI, local-first + Azure-ready. `backend/`
- **POC** — the proven Python proof-of-concept (sourcing engine, supplier
  clients). Read-only reference we port from; never edited. `poc/`
- **Docs** — authoritative specs under `docs/v1.5.1/`. Start with `CLAUDE.md`.

> **Build status:** Phase 0 (scaffold + run locally) complete. The prototype
> renders end-to-end through Vite against a live (currently near-empty) FastAPI
> backend. Later phases wire real persistence, supplier APIs, and cross-workflow
> engines. See `docs/v1.5.1/04_Infrastructure/AutoBOM_Deployment_Readiness.md`.

---

## Prerequisites (one-time)

- **Python 3.11+** (developed/tested on 3.12)
- **Node.js 20+** (tested on 24) — bundles `npm`
- **PostgreSQL 15+** — *not needed for Phase 0*; required from Phase 1 (DB layer)
- **Git**

---

## First-time setup

```bash
# 1. Backend virtualenv + deps
py -3.12 -m venv backend/.venv                 # Windows (or: python3.12 -m venv ...)
backend/.venv/Scripts/python -m pip install -r backend/requirements.txt

# 2. Frontend deps
cd frontend
npm install
# If Vite fails to start with an esbuild binary error, run its postinstall once:
node node_modules/esbuild/install.js
cd ..

# 3. Credentials
# The repo already has a local `.env` with working supplier keys (gitignored).
# If starting fresh, copy the template and fill it in:
cp .env.example .env

# 4. Database (Phase 1) — create the local DBs, run migrations, seed demo data
#    (Postgres must be installed and running; superuser/password as in .env)
createdb autobom_local        # or: psql -U postgres -c "CREATE DATABASE autobom_local;"
createdb autobom_test         # used by the test suite
cd backend
.venv/Scripts/python -m alembic upgrade head    # build the schema (POSIX: .venv/bin/python)
.venv/Scripts/python -m db.seed                 # load the demo seed data
cd ..
```

**Log in** (local mode) as one of the three seed users:
`aaron.jones@yanktech.com` (Designer), `maria.chen@yanktech.com` (Production),
`grace.hill@yanktech.com` (Admin). Everyone else in the seed is inert
referential data (no login).

**Run the backend tests:** `cd backend && .venv/Scripts/python -m pytest tests/`

The `.env` file is the local credential source. Every Azure-facing value may be
left empty/placeholder — the backend falls back to local behavior (seed-user
login, console-logged sheet writes). See **Modes** below.

---

## Run it (local dev)

Two servers. Either use the helper script or run them by hand.

**Helper script:**

```bash
pwsh scripts/dev.ps1     # Windows: opens backend + frontend in two windows
# or
bash scripts/dev.sh      # Git Bash / macOS / Linux: both in one terminal
```

**By hand (two terminals):**

```bash
# Terminal 1 — backend  (http://localhost:8000)
cd backend
.venv/Scripts/python main.py        # Windows  (POSIX: .venv/bin/python main.py)

# Terminal 2 — frontend (http://localhost:3000)
cd frontend
npm run dev
```

Open **http://localhost:3000**. Log in by picking a seed user (e.g.
`aaron.jones@yanktech.com` — Designer + Production, or `grace.hill@yanktech.com`
— Admin). The Vite dev server proxies `/api/*` to the backend on :8000.

**Verify the backend:**

```bash
curl http://localhost:8000/api/health
# {"status":"ok", "mode":"local", "auth":"seed-users",
#  "graph_sheet_writer":"console-fallback", "suppliers":{...}}
```

`mode` and the sub-fields reflect which integrations are live vs. running in
local fallback — no secrets are ever exposed here.

---

## Modes (local ↔ Azure) — the graceful-fallback pattern

There is **one** code path. Each Azure-facing capability is gated only on
whether its credential holds a real value (see `backend/config/settings.py`):

| Capability | No credential (local) | Real credential (Azure) |
|---|---|---|
| Login | Seed users (pick email) | Microsoft SSO (Azure AD) |
| Purchasing sheet write | Logs rows to console | Writes to Josh's OneDrive sheet via Graph |
| Database | Local Postgres | Azure Postgres (only `DATABASE_URL` changes) |
| Mouser / DigiKey / PartsBox | Real API calls (same in both modes) | Same |

To switch a capability on, put a real value in `.env` (or, in production, the
App Service environment). Nothing else changes. To develop entirely offline of
Azure, leave the `AZURE_*` / `MICROSOFT_GRAPH_*` / `ONEDRIVE_*` vars empty.

`.env.local` (optional, gitignored) overrides individual vars from `.env`
without editing the base file.

Azure deployment specifics: see [README-DEPLOY.md](README-DEPLOY.md).

---

## Project layout

```
backend/       FastAPI app (config loader, routes). Import root is backend/.
  config/      graceful-fallback settings
  api/         /api routes (health, auth stub)
  app/         FastAPI factory
  main.py      entry point (uvicorn)
frontend/      Vite-wrapped prototype
  index.html   Vite entry
  src/
    globals.js  installs window.React / window.ReactDOM (imported first)
    main.jsx    imports the prototype modules in load order, then app.jsx mounts
    core/ screens/ features/   the prototype (preserved as-is)
    lib/api.js  backend API helper (used from Phase 3)
scripts/       dev.ps1 / dev.sh convenience launchers
docs/          authoritative specs (v1.5.1 baseline)
poc/           proven POC — READ-ONLY, never edited
```

### A note on the frontend wrap

The prototype was written as global-script modules (each file registers its
components on `window`; cross-file refs go through a `window`-based registry).
Vite wraps it **without rewriting it**: `src/globals.js` installs the React
globals first, `src/main.jsx` side-effect-imports every prototype file in the
original load order, and Vite's esbuild uses the **classic JSX transform**
(`React.createElement` against the global React). No `@vitejs/plugin-react` /
Fast Refresh — it can't track this module shape. Editing a file triggers a full
reload.
