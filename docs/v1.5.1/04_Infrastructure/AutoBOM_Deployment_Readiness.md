# AutoBOM — Deployment Readiness (Claude Code Prep)

## Purpose

This is Claude Code's assignment. Build AutoBOM so that:

1. **Default mode is local.** The app runs entirely on Aaron's laptop with no Azure connection. All development happens here.
2. **Azure mode is a switch.** When Aaron gets his Azure credentials from admin, deployment is copy-paste. Azure integrations activate automatically based on env vars.

**Goal state:** Aaron does 90% of his work in local mode. Azure mode is for the deployed version his team uses.

Nothing in this document requires Aaron to have Azure credentials yet. Everything Claude Code builds here works locally today AND is ready for Azure the moment credentials arrive.

---

## PART 1 — Local Development Mode (Primary)

This is how AutoBOM runs on Aaron's laptop for day-to-day development. No Azure. No internet dependencies except the external supplier APIs (Mouser/DigiKey/PartsBox) which are the same in both modes.

### What Aaron installs on his laptop (one-time setup)

1. **Python 3.11+** — for the backend
2. **Node.js 20+** — for the frontend
3. **PostgreSQL 15+** — local database
4. **Git** — for version control

That's it. Everything else (dependencies, config) is handled by scripts Claude Code writes.

### How Aaron runs AutoBOM locally

Three commands in three terminal windows:

```
# Terminal 1 — Database (one-time; runs in background after)
brew services start postgresql   # Mac
# or: net start postgresql-x64-15   (Windows)

# Terminal 2 — Backend
cd backend
python main.py

# Terminal 3 — Frontend
cd frontend
npm run dev
```

Then Aaron opens `http://localhost:3000` in his browser. AutoBOM is running.

### What "local mode" means for each part of the app

| Service | Local Mode Behavior |
|---------|---------------------|
| **Database** | Local Postgres on `localhost:5432` — Claude Code sets up the schema and seed data automatically |
| **SSO / Login** | Hardcoded seed users (same as prototype today). Aaron logs in by picking his email from the seed list. No real Microsoft SSO needed. |
| **Secrets** | Read from `.env` file next to the code. No Azure Key Vault. |
| **OneDrive integration** | Logs to console instead of writing to real sheets. Aaron can see what WOULD be written without touching real data. |
| **Backend hosting** | Python running on `localhost:8000` |
| **Frontend hosting** | Vite dev server running on `localhost:3000` — auto-reloads on file changes |
| **Mouser / DigiKey / PartsBox** | Real API calls using keys from `.env`. Same as production. External APIs live on the internet, not Azure. |

### The graceful-fallback pattern

Every Azure-facing service in the code follows this pattern:

```python
# Example from backend/auth/azure_ad.py
def get_sso_config():
    client_id = os.getenv("AZURE_AD_CLIENT_ID")
    if not client_id or client_id.startswith("<paste"):
        return None  # No Azure creds — fall back to seed users
    return AzureADConfig(client_id=client_id, ...)

def authenticate(request):
    sso = get_sso_config()
    if sso is None:
        return authenticate_via_seed_users(request)  # Local dev mode
    return authenticate_via_microsoft(request, sso)  # Azure mode
```

Same pattern for OneDrive, Key Vault, everything else. **If the credential isn't set, fall back to a local behavior that doesn't need it.** No branching config, no separate code paths — just "does this env var have a real value or not."

### The `.env` file (local development template)

Aaron's local `.env` for development:

```bash
# Environment
ENV=development

# Database — local Postgres
DATABASE_URL=postgresql://localhost:5432/autobom_local

# Azure credentials — LEAVE EMPTY for local mode
AZURE_SUBSCRIPTION_ID=
AZURE_TENANT_ID=
AZURE_AD_CLIENT_ID=
AZURE_AD_CLIENT_SECRET=

# Microsoft Graph — LEAVE EMPTY for local mode (writes go to console)
MICROSOFT_GRAPH_TENANT_ID=
MICROSOFT_GRAPH_CLIENT_ID=
MICROSOFT_GRAPH_CLIENT_SECRET=
ONEDRIVE_PURCHASING_SHEET_ID=

# External APIs — SAME in local and Azure modes
MOUSER_API_KEY=<from-existing-POC>
DIGIKEY_CLIENT_ID=<from-existing-POC>
DIGIKEY_CLIENT_SECRET=<from-existing-POC>
PARTSBOX_API_KEY=<from-existing-POC>

# App config
BACKEND_URL=http://localhost:8000
FRONTEND_URL=http://localhost:3000
SESSION_SECRET=local-dev-secret-doesnt-matter
```

Empty Azure fields → fallback to local behavior. Filled fields → Azure integrations activate.

### Development workflow

Day-to-day, Aaron:

- Edits code in VS Code
- Frontend auto-reloads on file save (Vite dev server)
- Backend auto-reloads on file save (FastAPI + uvicorn `--reload`)
- Tests changes at `http://localhost:3000`
- Commits to git when a feature is done
- Pushes to GitHub, which triggers Azure deployment (only affects the deployed version, not local)

**No Azure connection required for any of this.** Aaron can work on a plane with no wifi and it all still works (as long as he doesn't need to hit Mouser/DigiKey — those are the only internet-dependent parts).

### Switching between local and Azure modes

Three approaches — Claude Code picks whichever is cleanest:

**Approach A — Multiple `.env` files:**
- Keep `.env.local` with development values
- Keep `.env.production` with production values
- Symlink or copy the desired one to `.env` before running

**Approach B — Single `.env` with commented sections:**
- One `.env` file
- Comment out either the local or Azure section depending on which mode

**Approach C — Environment variable override:**
- Base `.env` has local defaults
- Override individual vars via command line: `AZURE_AD_CLIENT_ID=xxx python main.py`

**Recommendation:** Approach A. Cleanest separation. Two files. Rename to switch.

---

## PART 2 — Azure Deployment Readiness

Everything in this section is what Claude Code builds ahead of time so that when Aaron has Azure credentials, deployment is a copy-paste operation. NONE of this blocks local development.

### 1. Environment variable schema (`.env.example` file)

Create a `.env.example` file at the project root with every environment variable AutoBOM needs. This is the single source of truth for what credentials Aaron will paste in later.

Required variables (with placeholder markers):

```bash
# Environment
ENV=production

# Azure subscription (paste after getting from admin)
AZURE_SUBSCRIPTION_ID=<paste-subscription-id-here>
AZURE_TENANT_ID=<paste-tenant-id-here>
AZURE_LOCATION=eastus
AZURE_RESOURCE_GROUP=autobom-dev

# Azure AD app registration (SSO) — paste after registering the app
AZURE_AD_CLIENT_ID=<paste-client-id-here>
AZURE_AD_CLIENT_SECRET=<paste-client-secret-here>
AZURE_AD_REDIRECT_URI=https://autobom.azurewebsites.net/api/auth/callback

# Database — auto-generated after first infra deploy
DATABASE_URL=<postgres-connection-string-goes-here>

# External API credentials — copy from existing POC .env
MOUSER_API_KEY=<from-poc-env>
DIGIKEY_CLIENT_ID=<from-poc-env>
DIGIKEY_CLIENT_SECRET=<from-poc-env>
PARTSBOX_API_KEY=<from-poc-env>

# Microsoft Graph — same app registration as SSO
MICROSOFT_GRAPH_TENANT_ID=<same-as-AZURE_TENANT_ID>
MICROSOFT_GRAPH_CLIENT_ID=<same-as-AZURE_AD_CLIENT_ID>
MICROSOFT_GRAPH_CLIENT_SECRET=<same-as-AZURE_AD_CLIENT_SECRET>
ONEDRIVE_PURCHASING_SHEET_ID=<sheet-item-id-goes-here>

# App config — populated after first deploy
BACKEND_URL=<autogen-after-deploy>
FRONTEND_URL=<autogen-after-deploy>
SESSION_SECRET=<generate-random-64-char-string>
```

Also add `.env` to `.gitignore` so the real credentials never get committed.

---

### 2. Bicep templates for Azure resource creation

Create Bicep infrastructure-as-code templates in an `infra/` folder. Bicep is Microsoft's native infrastructure-as-code language for Azure — it lets us define all resources in code and deploy them in one command.

Required templates:

- **`infra/main.bicep`** — top-level template that deploys everything
- **`infra/modules/appService.bicep`** — Azure App Service for backend (Basic B1 tier)
- **`infra/modules/staticWebApp.bicep`** — Azure Static Web Apps for frontend (Free tier)
- **`infra/modules/postgres.bicep`** — Azure Database for PostgreSQL Flexible Server (Burstable B1ms)
- **`infra/modules/keyVault.bicep`** — Azure Key Vault for secrets
- **`infra/modules/appInsights.bicep`** — Application Insights for monitoring (optional but recommended)

Every template must:
- Use parameters (no hardcoded values except sensible defaults)
- Output connection strings and URLs so subsequent steps can consume them
- Follow Azure naming conventions (e.g., `autobom-{env}-{resource}`)
- Tag resources with `project=autobom` and `environment=dev` for cost tracking

**Deployment command:** `az deployment sub create --location eastus --template-file infra/main.bicep --parameters environment=dev`

Aaron runs that ONE command after logging in with `az login`. All resources spin up. Done.

---

### 3. GitHub Actions CI/CD workflow

Create `.github/workflows/deploy.yml` that:

- Triggers on push to `main` branch
- Builds the frontend (Vite production build)
- Builds the backend Docker container
- Deploys frontend to Azure Static Web Apps
- Deploys backend Docker container to Azure App Service
- Runs database migrations

Use Azure federated identity (OIDC) for authentication — no long-lived secrets in GitHub. The workflow uses these GitHub Actions secrets (Aaron will set them later):

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

Also create `.github/workflows/deploy-infra.yml` for infrastructure changes — runs the Bicep deployment when infrastructure files change.

Include a `README-DEPLOY.md` in the `.github/` folder explaining how to set up the federated identity connection between GitHub and Azure. One-time setup Aaron does after Azure resources are provisioned.

---

### 4. Backend authentication with graceful fallback

Build the backend SSO integration with placeholder credentials AND local fallback. Use the `msal` Python library for Azure.

Structure:

- **`backend/auth/azure_ad.py`** — Microsoft SSO handler. Reads `AZURE_AD_CLIENT_ID`, `AZURE_AD_CLIENT_SECRET`, `AZURE_TENANT_ID` from environment. Returns `None` if credentials are missing.
- **`backend/auth/seed_users.py`** — Local fallback authentication. Reads hardcoded seed users (matches prototype today). Used when Azure credentials aren't set.
- **`backend/auth/routes.py`** — FastAPI routes:
  - `GET /api/auth/login` — redirects to Microsoft login (Azure mode) OR shows seed user picker (local mode)
  - `GET /api/auth/callback` — receives auth code from Microsoft (Azure mode) OR handles seed user selection (local mode)
  - `POST /api/auth/logout` — clears the session
  - `GET /api/auth/me` — returns the currently authenticated user
- **`backend/auth/session.py`** — Session token issuance and validation middleware (same in both modes)
- **`backend/auth/user_lookup.py`** — Looks up an AutoBOM user by email in the database

The route handlers check `azure_ad.get_config()` — if it returns None, they route to seed_users behavior. If it returns a config, they route to Microsoft behavior.

**Result:** Same UX in both modes (login screen, session, logout), different auth source under the hood.

---

### 5. Database schema and migrations (same in both modes)

Set up the database layer so it works with local Postgres AND Azure Postgres transparently.

Structure:

- **`backend/db/models.py`** — SQLAlchemy models for every AutoBOM entity (Users, Programs, Projects, BOMs, Builds, Requests, Push-Backs, Audit, etc.)
- **`backend/db/session.py`** — Database session management using `DATABASE_URL` env var (doesn't care if it's local or Azure)
- **`backend/db/migrations/`** — Alembic migration files
- **`backend/db/seed.py`** — Seeds initial data (roles, permissions, first admin user, hardcoded seed users for local mode)

Migration commands:
- `alembic upgrade head` — apply all migrations
- `alembic revision --autogenerate -m "..."` — generate new migration

Same code, same commands, same schema. Only the `DATABASE_URL` changes.

---

### 6. Microsoft Graph integration with graceful fallback

Build the OneDrive sheet writer with local-mode fallback.

Structure:

- **`backend/integrations/microsoft_graph.py`** — Graph API client. Reads `MICROSOFT_GRAPH_*` env vars. Returns None-configured if empty.
- **`backend/services/purchasing_sheet_writer.py`** — Purchasing batch writer:
  - If Graph client is None → logs the batch to console (local mode)
  - If Graph client is real → writes to Josh's OneDrive sheet (Azure mode)
- **`backend/services/purchasing_sheet_reader.py`** — Same pattern for reads

Placeholder mode: if `ONEDRIVE_PURCHASING_SHEET_ID` isn't set, log to console instead of writing. Once the sheet ID goes in, real writes happen. This means Aaron can develop the purchasing pipeline locally without ever touching Josh's real sheet.

---

### 7. Azure Key Vault integration (Azure mode only)

Build secret management so the backend reads secrets from Key Vault in production instead of `.env` directly.

Structure:

- **`backend/config/secrets.py`** — Secret loader.
  - In development (`ENV=development`) → reads from `.env`
  - In production (`ENV=production`) → reads from Azure Key Vault

Uses Azure managed identity when running on App Service (no additional credentials needed once deployed).

Every secret AutoBOM uses (API keys, database password, session secret, Microsoft credentials) is stored in Key Vault after deployment. Secrets never appear in code, environment variables in App Service config, or logs.

---

## What's already ready (no work needed)

- **Frontend prototype** — the AutoBOM prototype JSX code is already working. Claude Code wraps it in Vite for both local dev server and production build.
- **POC Python code** — Mouser/DigiKey/PartsBox clients, sourcing engine, BOM cleaning already exist. They need to be refactored into service modules but the logic is proven.
- **External API keys** — Mouser, DigiKey, PartsBox keys are already in the POC's `.env`. Just need to be moved to the new `.env` structure.

---

## PART 3 — The Deployment Path (When Credentials Arrive)

Here's what happens when Aaron has Azure credentials from admin:

**Step 1 — Set up production `.env` (5 minutes)**
- Copy `.env.example` to `.env.production`
- Paste in the 4 Azure credentials (subscription ID, tenant ID, client ID, client secret)
- Copy existing POC API keys
- Generate a random session secret

**Step 2 — Provision Azure resources (10 minutes)**
```
az login
az account set --subscription <subscription-id>
az deployment sub create --location eastus --template-file infra/main.bicep
```
Azure creates all resources. Output includes URLs and connection strings.

**Step 3 — Update `.env.production` with generated values (2 minutes)**
- Copy the database URL from step 2 output
- Copy the backend URL from step 2 output
- Copy the frontend URL from step 2 output

**Step 4 — Update Azure AD app registration (5 minutes)**
- Azure Portal → Entra ID → App registrations → AutoBOM
- Add the real production URLs as redirect URIs

**Step 5 — First deployment (10 minutes)**
- Push code to GitHub
- GitHub Actions runs the deployment workflow
- Frontend deploys to Static Web Apps
- Backend deploys to App Service
- Database migrations run

**Step 6 — Verify (5 minutes)**
- Visit the frontend URL
- Log in with a real Microsoft account
- Confirm AutoBOM is running

**Total time from credentials → live app: ~40 minutes.**

Meanwhile, Aaron keeps working locally the entire time. Local `.env` is unchanged, local Postgres is unchanged. Azure deployment is a separate track.

---

## What NOT to build yet

Some things wait until after first deployment:

- **Custom domain** (autobom.company.com) — Azure default URLs are fine for demo. Custom domain is a Phase 3 concern.
- **Multi-environment setup** (dev/staging/prod) — start with just `dev`. Add environments when the team is large enough to need them.
- **Advanced monitoring dashboards** — Application Insights collects data by default. Custom dashboards can wait.
- **Backup and disaster recovery beyond Azure defaults** — Azure Postgres has automated backups. Advanced DR planning waits for production.
- **Scale-out configuration** — Basic tiers are enough until real load happens.

Keep the initial deployment minimal. Add complexity as needed.

---

## Delivery format

Claude Code should organize the work into a GitHub-ready repository structure:

```
autobom/
├── .env.example
├── .env.local              # Aaron's local development credentials (gitignored)
├── .env.production         # Production credentials (gitignored)
├── .gitignore
├── README.md               # Local development instructions
├── README-DEPLOY.md        # Azure deployment instructions
├── .github/
│   └── workflows/
│       ├── deploy.yml
│       └── deploy-infra.yml
├── infra/
│   ├── main.bicep
│   └── modules/
│       ├── appService.bicep
│       ├── staticWebApp.bicep
│       ├── postgres.bicep
│       ├── keyVault.bicep
│       └── appInsights.bicep
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── auth/
│   │   ├── azure_ad.py     # Real SSO when creds present
│   │   ├── seed_users.py   # Local fallback when creds absent
│   │   ├── routes.py
│   │   ├── session.py
│   │   └── user_lookup.py
│   ├── db/
│   │   ├── models.py
│   │   ├── session.py
│   │   ├── migrations/
│   │   └── seed.py
│   ├── integrations/
│   │   └── microsoft_graph.py
│   ├── services/
│   │   ├── purchasing_sheet_writer.py
│   │   ├── purchasing_sheet_reader.py
│   │   ├── sourcing_engine.py       # Refactored from POC
│   │   ├── partsbox_client.py       # Refactored from POC
│   │   ├── mouser_client.py         # Refactored from POC
│   │   └── digikey_client.py        # Refactored from POC
│   └── config/
│       └── secrets.py
└── frontend/
    ├── vite.config.js
    ├── package.json
    └── src/
        └── (AutoBOM JSX code refactored into modules)
```

`README.md` explains local development (Part 1 of this doc). `README-DEPLOY.md` explains Azure deployment (Part 3 of this doc).

---

## Handoff instruction to Claude Code

When ready to kick off Claude Code, hand them:

1. This document (`AutoBOM_Deployment_Readiness.md`)
2. `CLAUDE.md` (operating context)
3. The AutoBOM PRD v1.5.1 (product spec)
4. `AutoBOM_Platform_Architecture.md` (system architecture)
5. `AutoBOM_API_Responsibility_Map.md` (API contract)
6. `AutoBOM_POC_Baseline_Analysis.md` (what to reuse from existing POC)

Claude Code's session goal: build everything in Part 1 (local dev) and Part 2 (Azure readiness). When done:

- Aaron can `git clone`, run three commands, and be developing AutoBOM locally
- The moment Aaron has Azure credentials, the deployment path in Part 3 takes ~40 minutes end-to-end

---

**Document version:** 2.0
**For:** Aaron Jones — AutoBOM project
**Purpose:** Claude Code preparation assignment. Local development is primary; Azure integration is ready-and-waiting.
