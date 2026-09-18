# DigiKey Refresh-Token Durable Persistence — Requirement and Options

## Status

**Not resolved.** This document defines the requirement and the shape of an
acceptable fix. It does not implement one, because no deployment host has
been chosen for a hosted, persistent secret store, and inventing that
decision is out of scope for this fix pass.

**Gate:** final team deployment with `DIGIKEY_MYLISTS_ENABLED=true` must
not be marked complete until a durable backend from this document (or an
equivalent) is selected and wired in. The process-memory fix in
`token_store.py` (Item 4 of this pass) only corrects same-process
continuity between `DigiKeyClient()` instances — it does not, and cannot,
survive a process restart or redeploy.

## Why this matters

DigiKey's OAuth refresh tokens rotate: each use of a refresh token can
return a new one, and the old one may stop working. If the value in use
is lost, the app loses its ability to call the DigiKey MyLists API on
behalf of the authorized account until someone re-runs the local
`digikey_oauth_setup.py` bootstrap flow and re-supplies a fresh token.

Streamlit Community Cloud does not provide a writable, persistent
filesystem or secret store that the running app can update at runtime —
its filesystem is ephemeral per instance, and its "Secrets" mechanism is
a config value set through the dashboard, not something the app can
rewrite from inside a request. That means, on that host today:

- `build_token_store()` resolves to `MemoryTokenStore` (no local `.env`
  file exists on Community Cloud).
- A rotated token lives only in that process's memory.
- Any restart, redeploy, or Community Cloud's own periodic app
  hibernation/wake cycle drops it, and the app falls back to whatever
  static `DIGIKEY_REFRESH_TOKEN` was last set in the host's Secrets UI —
  which may by then be stale and rejected by DigiKey.

This is an inherent limitation of that specific host, not a bug in this
codebase's `TokenStore` abstraction. The abstraction exists precisely so a
durable backend can be dropped in later without touching
`digikey_client.py` again.

## What a durable backend needs to do

Implement the existing two-method interface in `token_store.py`:

```python
class TokenStore:
    def get(self, key): ...
    def set(self, key, value): ...
```

`build_token_store()` then needs one more backend branch (e.g.
`DIGIKEY_TOKEN_STORE=<new-backend-name>`) that constructs it. No change to
`DigiKeyClient` is required — it already only calls `token_store.get()`
and `token_store.set()`.

## Candidate categories (no vendor chosen)

These are categories, not recommendations of a specific paid product —
picking one is a deployment decision for the team, not something this
codebase should assume:

1. **A small external secret/value store reachable over HTTPS.**
   A lightweight hosted key-value or secrets-management service that the
   app calls over the network to read/write a single value. Implemented
   as a `TokenStore` subclass making a `GET`/`PUT` call with an API key
   supplied via the host's own secret config (so the API key itself
   doesn't have the same rotation problem — it's static, unlike the
   DigiKey refresh token). Good fit if the team is fine adding one small
   network dependency and wants to keep hosting on Streamlit Community
   Cloud.

2. **A durable private volume on a different host.**
   Move the app (or just the token-persistence responsibility) to a host
   that provides a writable, persistent disk across restarts — a small
   VM, a container platform with a persistent volume mount, or similar.
   The existing `FileTokenStore` backend already implements exactly this
   case (atomic replace, one file per key) — pointing
   `DIGIKEY_TOKEN_STORE=file` + `DIGIKEY_TOKEN_STORE_PATH` at that volume
   is a zero-code-change fix if this path is chosen. Good fit if the team
   is open to changing where the app is hosted.

3. **A minimal persistent backend already available to the team.**
   If the team already operates *any* small persistent store for other
   purposes (a database table, an object storage bucket, an internal
   key-value service), a single row/object holding the current refresh
   token is enough — this doesn't need a purpose-built system. Good fit
   if such infrastructure already exists and adding one row/object is
   negligible operational overhead.

## Interim operational guidance until a durable backend exists

- Treat DigiKey MyLists automation on Streamlit Community Cloud as
  **best-effort, not guaranteed**, until this is resolved. Expect it to
  need manual re-authorization (`python src/digikey_oauth_setup.py`, run
  locally, then paste the new refresh token into the host's Secrets UI)
  after any restart/redeploy that lands between DigiKey token rotations.
- If that operational burden is unacceptable for the team release,
  consider keeping `DIGIKEY_MYLISTS_ENABLED=false` in the hosted
  deployment (DigiKey CSV export already remains available regardless —
  see `digikey_list_export.py`) until a durable backend is selected.
- Do not work around this by going back to writing rotated tokens into a
  committed or shared `.env` file — that reintroduces the original P1
  finding this fix pass corrected, and is worse for a multi-user host
  than the documented memory-only limitation.

## Decision needed from the team

Choose one category above (or confirm accepting the interim limitation),
then implement the corresponding `TokenStore` subclass and a
`build_token_store()` branch for it. That work is not included in this
fix pass.
