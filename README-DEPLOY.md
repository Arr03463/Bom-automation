# AutoBOM — Azure Deployment

Local development is primary (see [README.md](README.md)). This document is the
Azure path: everything is built ahead of time so that once Azure credentials
arrive, going live is a copy-paste operation. **None of this blocks local dev.**

Authoritative source: `docs/v1.5.1/04_Infrastructure/AutoBOM_Deployment_Readiness.md`.

> **Status:** The graceful-fallback seams exist today (config loader gates every
> Azure capability on env-var presence). The infra-as-code (`infra/*.bicep`) and
> CI/CD (`.github/workflows/*`) are scaffolded in later phases per the readiness
> doc; this file will grow with them.

---

## The switch: local ↔ Azure

One code path, gated on whether each credential holds a real value
(`backend/config/settings.py`):

- **Azure AD present** → Microsoft SSO; **absent** → seed-user login.
- **Microsoft Graph present** → writes to Josh's OneDrive purchasing sheet;
  **absent** → logs the batch rows to the console.
- **`DATABASE_URL`** → local Postgres vs. Azure Postgres; only the string changes.
- **Mouser / DigiKey / PartsBox** → real API calls in both modes.

To deploy, you populate real values; you do not change code.

---

## Deployment path (~40 min once credentials arrive)

1. **Production `.env`** — copy `.env.example` → `.env.production`, paste the 4
   Azure credentials (subscription id, tenant id, client id, client secret),
   copy the POC supplier keys, generate a random `SESSION_SECRET`.
2. **Provision Azure** —
   ```bash
   az login
   az account set --subscription <subscription-id>
   az deployment sub create --location eastus --template-file infra/main.bicep --parameters environment=dev
   ```
   (Bicep templates land per the readiness doc §2.)
3. **Backfill generated values** — copy the DB URL + backend/frontend URLs from
   the deploy output into `.env.production`.
4. **Azure AD redirect URIs** — add the real production URLs to the app
   registration.
5. **First deploy** — push to `main`; GitHub Actions builds the Vite frontend +
   backend container, deploys to Static Web Apps + App Service, runs migrations.
6. **Verify** — open the frontend URL, sign in with a real Microsoft account.

Meanwhile local dev is untouched — local `.env` and local Postgres keep working.

---

## Env var reference

`.env.example` is the single source of truth for every variable, with inline
notes on which are Azure-only (safe to leave empty locally) and which are the
external supplier keys (same in both modes). Supplier var names follow the real
`.env` and the Supplier API Integration Guide — the deployment doc's older
single `MOUSER_API_KEY` sketch is superseded.

Secrets are never committed (`.gitignore` covers `.env*`). In production they
move to Azure Key Vault; the backend reads them via managed identity (readiness
doc §7).
