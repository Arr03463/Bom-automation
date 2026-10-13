# AutoBOM Deployment Guide

Current deployment: **https://autobom.tools.yanktech.net → Caddy →
127.0.0.1:8502**. Follow [HTTPS migration](AutoBOM_HTTPS_Migration.md) for
the current host's cutover, unattended startup, and rollback instructions.
Earlier general deployment sections below are reference material.

Audience: whoever deploys/redeploys AutoBOM, not the original developer.

**The normal purchasing handoff needs no DigiKey MyLists OAuth setup or
durable token store.** DigiKey's normal-flow output is a deterministic
FastAdd cart link (`src/digikey_fastadd.py`) plus a supplier CSV --
neither makes a live DigiKey API call, and neither needs anything beyond
the plain `DIGIKEY_CLIENT_ID`/`DIGIKEY_CLIENT_SECRET` product-search
credentials already required for sourcing. Sections 5 and 6 below (DigiKey
3-legged OAuth authorization, durable token-store backend) are LEGACY --
only relevant if you specifically intend to use `src/main.py`'s CLI tool
with live cart/list creation enabled. Skip them for a normal Streamlit
deployment. See `Documentation/AutoBOM_Direct_Cart_Handoff_Change_Risk_Audit.md`
for the full rationale.

## 1. Requirements

- Python 3.12 (matches the development environment this app was built
  against; see `requirements.txt` for pinned dependency names).
- Dependencies: `pip install -r requirements.txt` (requests, pandas,
  openpyxl, python-dotenv, streamlit).
- Outbound HTTPS access to: `api.mouser.com`, `api.digikey.com`,
  `api.partsbox.com` (or your configured `PARTSBOX_API_BASE_URL`). A
  DigiKey token-store HTTPS endpoint is only needed if you're using the
  legacy MyLists CLI path (§5/§6) -- not for the normal Streamlit app.

## 2. Hosting decision

**Current recommendation (supersedes the note below): the existing Yank
remote engineering Windows PC**, running one Streamlit process under a
Windows service, exposed only to the trusted corporate LAN/VPN. See
`Documentation/AutoBOM_Remote_PC_Deployment_Architecture_Audit.md` for
the full comparison and `Documentation/AutoBOM_Remote_PC_Predeployment_Report.md`
for what's been prepared/verified toward that target, and
`Documentation/AutoBOM_Onsite_Deployment_Checklist.md` for the install
procedure. This host already provides persistent local storage for the
DigiKey durable token store (`DIGIKEY_TOKEN_STORE=file`) without needing
an external HTTPS key-value service.

*Earlier assessment, kept for reference:* `Documentation/AutoBOM_Final_Deployment_Hardening_Report.md`
§1 evaluated Streamlit Community Cloud and found it conditionally
acceptable provided a durable `DIGIKEY_TOKEN_STORE=http` backend was
stood up (Community Cloud has no writable persistent filesystem). That
remains true if the team ever revisits cloud hosting, but the Windows PC
is the current authoritative target and avoids that extra dependency.

Either way, the app must be deployed with restricted network/access
control -- AutoBOM has no built-in login of its own.

## 3. Environment variables

See `.env.example` in the repository root for the full list with
placeholders, grouped by Mouser / DigiKey / PartsBox / token-store /
application configuration. Copy it to `.env` for local development, or
set the same names as your host's secrets/environment configuration for
a deployed instance.

**Never commit a file with real values.** `.env` and `Documentation/env`
are both already listed in `.gitignore`.

## 4. Deploying

1. Set every required environment variable (see `.env.example`) in your
   host's secrets/config mechanism.
2. Push/deploy the current `main` branch.
3. On first load, confirm the app shows no configuration warning banners
   (see `src/config_validation.py`). If it does, fix the named problem
   before proceeding -- these mean a feature you've enabled cannot
   actually work as configured.
4. Confirm `runs/` is writable by the running process (it's created
   automatically on first BOM run if missing).

## 5. Authorizing DigiKey (LEGACY -- only for the MyLists CLI path, first-time / after a durable-store change)

**Skip this section for a normal deployment.** It only applies if you
intend to run `src/main.py`'s CLI tool with `DIGIKEY_MYLISTS_ENABLED=true`
and live cart/list creation. The Streamlit app's normal DigiKey handoff
(FastAdd cart link + CSV) needs none of this.

1. Locally, with real DigiKey `DIGIKEY_CLIENT_ID`/`DIGIKEY_CLIENT_SECRET`
   set, run:
   ```
   python src/digikey_oauth_setup.py
   ```
   Follow its instructions to authorize against your My DigiKey account
   and obtain a refresh token.
2. Set `DIGIKEY_REFRESH_TOKEN` to that value as your deployment's initial
   secret. On first use, `DigiKeyClient` reads this as a fallback if the
   durable store has nothing yet, then persists any rotated value to the
   durable store from then on (see `src/token_store.py`).
3. Confirm `DIGIKEY_TOKEN_STORE` (and `DIGIKEY_TOKEN_STORE_PATH` or
   `DIGIKEY_TOKEN_STORE_URL`/`DIGIKEY_TOKEN_STORE_API_KEY`) point at a
   location that survives a restart of your deployment. Community Cloud
   in particular has no writable persistent filesystem of its own -- see
   §2.

## 6. Choosing a durable DigiKey token-store backend (LEGACY -- MyLists CLI path only)

**Skip this section for a normal deployment** -- same scope note as §5.

| Backend | When to use | Config |
|---|---|---|
| `env_file` (default in local dev) | Local development only | none beyond the default `.env` path |
| `file` | Host with a mounted persistent volume | `DIGIKEY_TOKEN_STORE=file`, `DIGIKEY_TOKEN_STORE_PATH=<dir>` |
| `http` | Host with no persistent filesystem (e.g. Community Cloud) | `DIGIKEY_TOKEN_STORE=http`, `DIGIKEY_TOKEN_STORE_URL=<https base url>`, `DIGIKEY_TOKEN_STORE_API_KEY=<static key for that store>` |
| `memory` | Never for a real deployment with MyLists enabled | none -- this is the "not durable" fallback the startup banner warns about |

`http` assumes a small hosted key-value/secrets service reachable over
HTTPS that supports `GET {url}/{key}` → `{"value": ...}` and
`PUT {url}/{key}` with the same body shape, authenticated with a bearer
token. Picking the actual service is a team decision (see
`Documentation/AutoBOM_DigiKey_Durable_Token_Strategy.md` §"Candidate
categories") -- `HttpTokenStore` in `src/token_store.py` does not assume
any specific vendor.

## 7. Rotating credentials

Rotate any vendor credential the same way you'd rotate any secret at that
vendor (Mouser API keys, DigiKey client secret, PartsBox API key): update
it at the vendor, then update your host's secret/environment
configuration, then restart the app. The DigiKey **refresh** token
(LEGACY MyLists CLI path only, §5/§6 -- not used by the normal app) is
different -- it rotates automatically on use and is written back through
`DIGIKEY_TOKEN_STORE`; you should not need to manually rotate it unless
re-authorizing from scratch.

**Reminder:** earlier work in this project identified live credentials
present in a local, git-ignored `Documentation/env` file. Confirm those
were rotated before this deployment goes live if that has not already
happened -- see
`Documentation/AutoBOM_Final_Deployment_Hardening_Report.md` §9 for the
current verification status.

## 8. Rolling back

AutoBOM has no database migrations and no persistent state outside
`runs/<run_id>/` (ephemeral, per-run) and the supplier lookup cache
(`.cache/`, safe to delete/ignore). Rolling back is: redeploy the
previous commit/tag. No data migration/cleanup step is required.

## 9. Inspecting logs

AutoBOM prints operational messages (dry-run previews, sanitized vendor
error summaries via `describe_error_response()`) to stdout/stderr, which
your host's log viewer captures. No structured log aggregation is
implemented; see
`Documentation/AutoBOM_Final_Deployment_Hardening_Report.md` §10 for the
current state and what was deliberately not built in this pass.

## 10. Run-directory retention

`runs/<run_id>/` directories are reaped automatically once per new BOM
run kick-off (`src/run_retention.py`), based on:

- `AUTOBOM_RUN_RETENTION_DAYS` (default 14; 0 disables age-based cleanup)
- `AUTOBOM_MAX_RUNS` (default 200, a total cap including the run just
  created; 0 disables count-based cleanup)

The run that was JUST created by this cleanup call is never deleted,
regardless of its age or position -- but this is not a guarantee about
every other currently-open session. Cleanup has no registry of what
other browser sessions/users currently have open: an older run that's
still open in someone else's tab, but hasn't triggered a new run itself
recently, is not specially protected and can be reaped once it crosses
the age/count threshold. This is a known, accepted tradeoff, not a bug --
building a "currently open" session registry to close this gap would be
disproportionate complexity for a small internal tool. Keep the defaults
conservative (14 days / 200 runs) and raise `AUTOBOM_MAX_RUNS` /
`AUTOBOM_RUN_RETENTION_DAYS` if the team's actual concurrent-session
count and BOM turnaround time make the default window too tight.

Cleanup failures are caught and never crash a run. On a host with an
ephemeral filesystem (Community Cloud), a restart already wipes `runs/`
entirely -- this policy mainly matters for hosts with persistent
storage, or long uptime stretches between restarts.
