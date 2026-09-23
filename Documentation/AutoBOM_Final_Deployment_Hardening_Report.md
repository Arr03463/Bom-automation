# AutoBOM Final Deployment Hardening Report

Scope: make the existing, functionally-complete AutoBOM safe, reliable, deployable,
maintainable, and ready for real team use. No new product features, no
architecture redesign, no procurement-intelligence expansion. The existing
architecture (`ActiveBomState`, `component_lookup`, `record_filter`,
`engineering_units`, `sourcing_engine`, `PartsBoxClient`, `MouserClient`,
`DigiKeyClient`, `TokenStore`, `workflow_runner`, the per-artifact freshness
model, Mouser cart / DigiKey MyLists integrations) is preserved and extended,
never replaced.

**This pass involved no live vendor API calls.** Every credential available in
this environment is local-development-only (`.env`, git-ignored, not
reproduced anywhere in this report), and no safe sandbox/test-mode credential
set was provided for a genuinely live verification pass. Sections 4-9 below
are honest checklists, not fabricated results, per explicit instruction not
to invent them.

---

## 1. Hosting decision

**Recommendation: Streamlit Community Cloud remains acceptable**, conditional
on the items below. This is not a default assumption -- it was evaluated
against each requirement in turn.

| Requirement | Community Cloud characteristic | Verdict |
|---|---|---|
| Writable persistence | No writable persistent filesystem/secret store the app can update at runtime; ephemeral per instance. | Acceptable for `runs/<run_id>/` (already treated as ephemeral scratch space); **not acceptable** for the DigiKey rotating refresh token without the durable backend added in this pass (§2). |
| Secret handling | Dashboard-set "Secrets" become environment variables at boot; not rewritable by the running app. | Fine for every *static* secret (API keys, client secret). Not fine, by itself, for the *rotating* DigiKey refresh token -- that's exactly the gap `HttpTokenStore`/`FileTokenStore` close. |
| DigiKey rotating refresh-token persistence | No durable local write target. | Closed in this pass via a durable `TokenStore` backend selection (`file` for a mounted volume elsewhere, `http` for a small external HTTPS key-value/secrets service) -- see §2. `MemoryTokenStore` remains the non-durable fallback, and the app now warns at startup if `DIGIKEY_MYLISTS_ENABLED=true` resolves to it (`src/config_validation.py`). |
| Concurrent users | Single process per app; Streamlit's own `st.session_state` isolates sessions. | Already handled: every BOM run gets its own `runs/<run_id>/` directory (`src/run_workspace.py`), so two sessions uploading the same filename never collide (established in an earlier phase; unchanged here). |
| Filesystem lifecycle | Ephemeral; wiped on restart/redeploy/hibernation. | `runs/` self-cleans on every restart regardless of the new retention policy (§7 below); the retention policy mainly matters for a persistent-volume host or a long uptime stretch. |
| Run-directory retention | N/A (host doesn't provide persistence) | Implemented anyway (`src/run_retention.py`) since it's needed the moment a persistent-volume host or `DIGIKEY_TOKEN_STORE=file` is used, and is a safe no-op cost otherwise. |
| Outbound vendor API access | Outbound HTTPS permitted. | No blocker identified for Mouser/DigiKey/PartsBox REST calls, or for an `HttpTokenStore` backend. |
| Environment variables | Supported via the Secrets UI. | No blocker; see `.env.example` for the full documented list. |
| Process restarts/hibernation | Occurs on inactivity; drops all in-memory `st.session_state` for every active session, not just DigiKey's token. | Inherent to any single-process Streamlit deployment, not an AutoBOM-specific defect. A user mid-review during a hibernation-triggered restart loses their in-progress (unsaved) session and must re-run the BOM. Acceptable for an internal tool; document it in the operator guide if this proves disruptive, and consider an "always-on"/keep-warm ping if not. |
| Team access controls | Streamlit Community Cloud supports restricting a private app to specific viewer identities. | **Required, not optional**: AutoBOM has no authentication of its own. Deploy as a private app restricted to the team. |

**If the team is unwilling to stand up even a small external HTTPS
key-value/secrets service** for the DigiKey token (the `http` backend), the
smallest appropriate alternative is a host with a persistent mounted volume
(a small VM, or a container platform with persistent storage) and
`DIGIKEY_TOKEN_STORE=file` -- zero code change, already implemented and
tested. This is presented as a fallback, not a default recommendation to
migrate: per the durable-token strategy document, do not migrate unless the
external-store path is genuinely unworkable for the team.

Full operational detail: `Documentation/AutoBOM_Deployment_Guide.md`.

## 2. Durable DigiKey token implementation

Implemented in `src/token_store.py`, extending the existing `TokenStore`
abstraction (`get`/`set`) rather than replacing it or touching
`DigiKeyClient`'s authentication flow:

- **`HttpTokenStore`** (new): generic HTTPS key/value backend --
  `GET {base_url}/{key}` → `{"value": ...}`, `PUT {base_url}/{key}` with the
  same body shape, bearer-token authenticated via
  `DIGIKEY_TOKEN_STORE_API_KEY`. Deliberately vendor-agnostic (no specific
  paid service assumed, per the durable-token strategy doc's explicit
  instruction not to invent that decision). Raises the new
  `TokenStoreError` on any network/HTTP/parse failure rather than returning
  `None` -- so "the store is unreachable" is never confused with "nothing
  has been stored yet".
- **`FileTokenStore`** (pre-existing, unchanged data format): now also
  exposes a real lock (see §3).
- `build_token_store()` gained a `DIGIKEY_TOKEN_STORE=http` branch
  alongside the existing `env_file`/`file`/`memory` branches.
- `DigiKeyClient` gained a `token_store_error` attribute, set whenever a
  `get`/`set` call raises `TokenStoreError`, instead of that failure being
  silently absorbed or crashing construction. `src/config_validation.py`
  reads the resolved backend type (not a live network call) to warn at
  startup when `DIGIKEY_MYLISTS_ENABLED=true` resolves to the non-durable
  `MemoryTokenStore`.

Tests: `tests/test_digikey_token_persistence.py` (`HttpTokenStoreTests`,
`DigiKeyClientTokenStoreErrorSurfacingTests`) -- get/set success, 404,
network failure, HTTP error status, missing configuration, and that a
persistence failure during rotation is recorded on the client without
crashing token refresh (see §3).

## 3. Token concurrency behavior

Implemented the required sequence (read → refresh → new token → durable
store → subsequent readers see it) with a **file-lock-based** coordination
mechanism, reusing (not duplicating) the same advisory-lock primitive
already used by `SupplierLookupCache`:

- Extracted the pre-existing `_FileLock` out of `supplier_lookup_cache.py`
  into a new shared `src/file_lock.py` (`FileLock`), with a backward-compatible
  re-export (`from file_lock import FileLock as _FileLock`) so the existing
  cache module and its tests are unchanged.
- `TokenStore.lock()` is a new method: no-op (`contextlib.nullcontext()`) by
  default; `EnvFileTokenStore`/`FileTokenStore` override it with a real
  `FileLock` scoped to their file/directory. `HttpTokenStore`'s `lock()`
  stays a no-op -- coordinating a lock against a generic HTTP endpoint would
  require assuming a specific conditional-write/ETag capability this class
  does not assume any vendor provides (documented in its docstring as an
  extension point if the chosen backend supports it).
- `DigiKeyClient.get_user_access_token()` now performs the entire
  read-refresh-write cycle **inside `with self.token_store.lock():`**, and
  re-reads the current refresh token from the store at the START of that
  locked section (`_current_refresh_token()`) rather than trusting the
  value loaded at construction time. This is the actual fix for "do not
  overwrite a newer token with an older one": for the `file`/`env_file`
  backends (the only ones where two AutoBOM processes plausibly share the
  same durable store), a second caller racing a first is serialized by the
  lock and then reads the FIRST caller's already-rotated token before
  attempting its own refresh -- it never resubmits a token DigiKey has
  already invalidated.
- In-memory `self.refresh_token` is updated **before** the durable
  `set()` call, so a store write failure loses only the persisted copy
  (recoverable via re-auth on restart), never the in-process value DigiKey
  just invalidated the old one in favor of.
- For the `http`/`memory` backends specifically (no real cross-process
  lock), the documented safety net is DigiKey's own server-side rejection
  of an already-used refresh token: a losing process gets a clear,
  surfaced `RuntimeError` rather than silently corrupting stored state.

Tests added, all in `tests/test_digikey_token_persistence.py`:

- Normal rotation: pre-existing tests, unchanged and still passing.
- Storage failure during rotation:
  `test_rotation_updates_memory_even_when_persistence_fails`.
- **Two clients refreshing near the same time** (real concurrency, not
  simulated): `DigiKeyClientConcurrentRotationTests.test_two_concurrent_clients_never_submit_an_already_rotated_token`
  -- two `DigiKeyClient`s sharing one `FileTokenStore` directory, driven by
  two real `threading.Thread`s against a fake DigiKey token endpoint that
  rejects any refresh_token that isn't its current one. Asserts zero
  rejected/stale submissions and that the final stored token matches the
  server's final state.
- Lock serialization itself: `TokenStoreLockTests` (real `FileLock`
  instances returned by `file`/`env_file` backends;
  `test_file_token_store_lock_serializes_two_holders` proves a second
  holder cannot acquire while the first still holds it).
- Process-restart simulation: covered indirectly by every "construct a
  fresh `DigiKeyClient()` against an existing store" test (e.g.
  `test_stored_refresh_token_takes_precedence_over_env_value`) -- a new
  client picks up whatever the store currently holds, which is exactly
  what happens after a restart against a durable backend.
- Stale-token fallback: `test_construction_falls_back_to_env_value_when_store_get_fails`.

## 4. Live vendor verification

**Not performed -- no credentials/safe test mode available in this
environment for live calls.** Per instruction, no results are fabricated.
Checklist for whoever has live credentials to run this before go-live:

**Mouser**
- [ ] Create a cart with 1+ real Mouser-sourced item; capture the raw
      `add_items_to_cart()` response; confirm `CartKey`'s actual JSON
      location matches `_extract_mouser_cart_key()`'s assumptions
      (`src/workflow_runner.py`) -- top-level `CartKey`, or nested under
      `Cart.CartKey`.
- [ ] Attempt cart creation with zero eligible items; confirm
      `build_mouser_cart_items()` returns `[]` and
      `create_mouser_cart_from_bom()`'s `created: False` path is taken
      (already covered by existing unit tests with synthetic data; this
      step just confirms live behavior matches).
- [ ] Trigger a real failure response (e.g. invalid API key temporarily)
      and confirm `describe_error_response()`'s allow-listed fields
      actually appear in Mouser's real error body (`error`,
      `error_description`, etc.) -- if Mouser uses different field names,
      update `SAFE_MESSAGE_FIELDS` in `src/http_error_utils.py` (never
      widen it to "raw body").

**DigiKey**
- [ ] Create a MyList; confirm the real `create_list()`/`add_parts_to_list()`
      response field names match `list_id` extraction in
      `digikey_mylists_client.py` (`ListId`/`listId`/`Id`/`id`).
- [ ] Confirm whether any field in that response constitutes a genuine
      share identifier/link. If yes, see §6. If no, leave `share_id`
      unavailable (current, honest state).
- [ ] Exercise a real refresh-token rotation end-to-end once, confirming
      the new token round-trips through whichever `DIGIKEY_TOKEN_STORE`
      backend is chosen for the actual deployment.

**PartsBox**
- [ ] Confirm live `part/*` field shapes (id, MPN, manufacturer,
      description, category, package, characteristics) against
      `component_lookup.py`'s defensive extraction.
- [ ] Confirm `storage/tags` is really a plain list of strings (assumed by
      `storage_has_tag()` in `src/partsbox_project_builder.py`).
- [ ] Confirm `project/get-entries` response shape matches what
      `add_bom_entries_to_project()` expects for idempotency.
- [ ] Confirm whether quantity/stock fields are exposed by any confirmed,
      documented endpoint (none is used today -- Inventory intentionally
      does not display a stock/quantity column).
- [ ] Confirm whether a saved-filter creation API exists (see §9).

None of these were assumed true or false in this pass without evidence;
existing code already treats every one of these as "best-effort/inferred"
in its own comments, and that framing is left intact.

## 5. Mouser CartKey parsing

**Unchanged.** Confirming the real response shape (§4) is a prerequisite to
replacing best-effort parsing with a confirmed adapter, per the explicit
instruction to verify before implementing. `_extract_mouser_cart_key()`
still checks the two shapes referenced in Mouser's published docs and falls
back to `None` -- no behavior change, no new fixture added (a fixture built
from an unconfirmed/guessed shape would be worse than none).

## 6. DigiKey share identifier

**Not confirmed in this pass** -- no live API access. `share_id` remains
explicitly `None` everywhere it's surfaced (`_build_digikey_purchasing()`
in `src/workflow_runner.py`, the Purchasing page in `app.py`), with the
existing comment stating plainly that DigiKey's confirmed MyLists response
only returns `ListId`/`ListName` in this codebase's own tests/mocks, and
that a distinct share field is not present and must be verified against
the live API. No field was fabricated to fill this gap.

## 7. Mouser share model

**Unchanged, per instruction** -- no supported/private share API was
verified in this pass, so Model B (manual share, operator hands the Access
ID to purchasing directly, no paste-back into AutoBOM) remains in place
exactly as documented in `app.py`'s Purchasing page and the operator guide.

## 8. PartsBox live-schema verification

**Not performed** -- see the checklist in §4. No mapping was changed
without evidence; every currently-inferred field stays exactly as
inferred, with its existing "best-effort" documentation intact.

## 9. PartsBox saved filter

**Unchanged** -- `partsbox_client.py` still has no saved-filter operation,
and none was invented. The existing fallback (same-name project/storage +
`production` tag, saved filter created manually in PartsBox using the
documented conditions: Storage Location Name equals `<name>` AND Storage
Location Tags contains `production`) remains the team-release procedure
until a supported API is confirmed.

## 10. Run-directory retention implementation

`src/run_retention.py` (new), wired into `run_workspace.build_run_workspace()`
so cleanup happens **once per new run kick-off only** -- never mid-workflow,
never on a page load/rerun that isn't starting a new run:

- `AUTOBOM_RUN_RETENTION_DAYS` (default 14; `0` disables age-based
  cleanup) and `AUTOBOM_MAX_RUNS` (default 200, a total cap that includes
  the just-created active run since it's always newest; `0` disables
  count-based cleanup).
- The currently active run is never deleted, regardless of age or
  position in the count ordering.
- Every failure mode (missing directory, permission error, unexpected
  exception) is caught inside `cleanup_old_runs()` and returned in an
  `errors` list rather than raised -- retention can never crash a BOM run.
  `build_run_workspace()` additionally wraps the call in its own
  try/except as defense in depth.
- Multi-user runs remain isolated: cleanup only ever removes whole
  `runs/<run_id>/` directories by age/count, never reaches into another
  run's files selectively.

Tests: `tests/test_run_retention.py` (10 tests) -- missing root, active-run
protection, age-based deletion, count-based deletion (newest-N kept), both
policies independently disable via `0`, failure capture (unexpected
filesystem entries, a simulated exception from `iterdir()`), and an
integration test proving `build_run_workspace()` actually invokes cleanup
at kick-off (`cleanup=False` opt-out also tested).

**Known tradeoff, documented, not engineered around:** a run belonging to
a second user who hasn't touched it recently but still has it open in a
browser tab could theoretically be reaped if it's outside the retention
window/count. This is inherent to any age/count-based retention policy
without a "currently open" registry, which would be over-engineering for
a small internal tool. Conservative defaults (14 days / 200 runs) make
this practically unlikely; both are configurable per deployment.

## 11. Secrets/security review

- **Artifact security:** confirmed no run-persisted artifact contains a
  raw vendor payload with potential secret/account-metadata content.
  Structured purchasing results already excluded raw responses as of the
  Phase 4 fix pass (`response["_purchasing_raw"]`, kept out of
  `run_summary.json` by `_write_run_summary()`'s existing underscore-key
  filter). This pass found and fixed a related, previously-unaddressed
  gap: **`digikey_client.py` and `digikey_mylists_client.py` each defined
  their own `_raise_for_status()` that fell back to the RAW response body
  text when no allow-listed error field matched** (and `mouser_client.py`'s
  version did so unconditionally) -- and that raw text could end up
  embedded in a `RuntimeError` message landing in `response["errors"]`,
  which IS persisted to `run_summary.json` (unlike `_purchasing_raw`).
  Consolidated all three into one shared `http_error_utils.raise_for_status()`
  that always goes through the existing allow-list-only
  `describe_error_response()` -- no vendor client's error path can leak an
  echoed request detail (e.g. Mouser's Cart API takes its key as a URL
  query parameter) into a persisted file anymore. Tests:
  `tests/test_http_error_utils.py` (`RaiseForStatusTests`,
  `SharedRaiseForStatusReuseTests` -- the latter guards against the
  duplication regressing).
- Grepped every changed/new file for `print(` -- no new print statements
  were added; the pre-existing ones in `digikey_mylists_client.py` are
  dry-run payload previews and already-sanitized error summaries, both
  unchanged.
- Diagnostic raw-payload retention remains **non-persistent**
  (`response["_purchasing_raw"]`, in-memory only) and was not made
  opt-in-persistable in this pass -- no requirement surfaced a concrete
  need for it, and adding a persistence path for raw vendor payloads
  without one would be scope creep against "don't add features beyond
  what's needed."

## 12. Secrets management

- `.env.example` (new, repository root) documents every environment
  variable this codebase reads (`os.getenv(...)`), grouped by Mouser /
  DigiKey / DigiKey token-store / PartsBox / application configuration,
  with placeholder values only -- verified with
  `git check-ignore -v .env.example` that it is NOT git-ignored (it should
  be committed; only real-valued `.env`/`Documentation/env` are ignored).
- Verified via `git check-ignore -v Documentation/env .env` that both
  remain git-ignored in the current working tree.
- No secret values appear in this report, `.env.example`, or any other
  file changed in this pass.
- Startup does not print secret values; `src/config_validation.py` only
  reads env var *presence*, never logs a value.

## 13. Credential rotation reminder

Unchanged from earlier phases' finding: live credentials were identified in
a local, git-ignored `Documentation/env` file early in this project. That
file was never committed (confirmed then and reconfirmed now via
`git check-ignore`). **Rotate those vendor credentials before this
deployment goes live if that has not already been done** -- this report
does not claim to have verified rotation status with the vendors
themselves, since that is outside what a code-level review can confirm.

## 14. Multi-user verification

- **Session state:** each browser session gets its own `st.session_state`
  (Streamlit's own guarantee); `current_run` holds one canonical
  `ActiveBomState` per session, established in earlier phases and
  unchanged here.
- **Run workspaces:** `runs/<run_id>/` per run, unique `uuid4().hex` run
  IDs (`src/run_workspace.py`, unchanged in this pass except for the new
  retention-cleanup call at kick-off, which only ever touches OTHER runs'
  directories, never the one being created).
- **Cache locking:** `SupplierLookupCache` already used an advisory file
  lock (unchanged data path; the lock class itself was relocated to
  `src/file_lock.py` for reuse, with existing tests passing unmodified).
- **Token access:** now lock-coordinated for the shared `file`/`env_file`
  backends (§3) -- the one place two processes plausibly contend for the
  same secret.
- **Downloads:** per-artifact freshness (Phase 4 pass) already prevents
  one run's stale/failed file from being presented as another's current
  one; unchanged here.
- **Purchasing regeneration:** confirmed still explicit-action-only (§15).
- **PartsBox project updates:** unchanged; same-name reuse plus
  idempotent entry sync established in an earlier phase.
- **Supplier artifacts:** Mouser cart / DigiKey MyList creation both
  remain scoped to one operator's explicit Regenerate click against their
  own session's `ActiveBomState`; no shared mutable purchasing state
  exists across sessions.

No new multi-user defect was found in this review; the one gap that
existed (DigiKey token durability/coordination) is closed in §2/§3.

## 15. Purchasing side-effect safety verification

Re-confirmed every item explicitly, reusing existing and this pass's test
coverage rather than re-deriving the guarantee from scratch:

| Confirm | Evidence |
|---|---|
| Normal rerun creates no cart/MyList | `tests/test_app_smoke.py::PurchasingPageSmokeTests::test_rerun_alone_never_triggers_regeneration`; `tests/test_purchasing_state.py::RegeneratePurchasingTests::test_plain_rerun_creates_no_vendor_artifact` |
| Navigation creates no cart/MyList | Same mechanism -- `regenerate_purchasing()` is only reachable from one button handler in `app.py`; navigating pages never calls it. |
| Filtering creates no cart/MyList | Filtering only touches `record_filter`/`component_lookup`/session-state filter keys; no code path from a filter widget reaches `workflow_runner`. |
| Download creates no cart/MyList | `show_download()`/`render_downloads()` only read `outputs`/`artifact_status`; no write/regeneration call. |
| Replacement selection only changes canonical/sourcing state | `apply_replacement()`/`retry_exact_sourcing()` call `sourcing_engine.source_row()` and `ActiveBomState.update_row()` only; purchasing artifacts are marked stale (via `refresh_response_snapshot()`), never regenerated, by either action. |
| Regenerate Purchasing is the explicit side-effect boundary | Confirmed above; the only call site. |
| Already-current supplier artifacts are not recreated unintentionally | `tests/test_purchasing_state.py::RegeneratePurchasingTests::test_retry_after_partial_failure_does_not_recreate_successful_supplier_artifact`, `test_one_explicit_regeneration_click_creates_each_required_artifact_at_most_once` |

All Phase 4 correctness behavior (per-artifact freshness, partial-failure
isolation, readiness semantics) is preserved unmodified in this pass.

## 16. Logging/error handling

- Every vendor HTTP client now raises through the single, shared,
  secret-safe `http_error_utils.raise_for_status()` (§11) -- the main
  structural improvement in this area.
- `src/config_validation.py` surfaces configuration problems (DigiKey
  MyLists enabled without a durable store or without credentials, Mouser
  cart enabled without credentials, PartsBox not configured) as plain-
  language `st.warning()` banners at the top of every page, rather than
  letting the underlying feature fail with a raw exception later.
- **Deferred, explicitly not undertaken:** a full rewrite of every
  operator-facing error string across `app.py`/`workflow_runner.py` into a
  single consistent "what happened / what to do" template. The existing
  messages already avoid raw exception dumps in the most sensitive paths
  (vendor HTTP errors, now uniformly sanitized) and are reasonably
  actionable (e.g. "PartsBox skipped: project name is required.",
  "Mouser cart regeneration failed: {error}"), but a systematic pass over
  every message string was not done -- it would touch many files broadly
  without a specific defect driving each change, which risks scope creep
  against "don't add features/polish beyond what's needed." Flagging this
  explicitly rather than silently skipping it.
- No structured log-aggregation platform was built (correctly out of
  scope per "do not overbuild an observability platform"). Logging today
  is stdout/stderr via `print()` for dry-run previews and sanitized vendor
  error summaries, captured by whatever the hosting platform's log viewer
  is.

## 17. Deployment guide / operator guide created

- `Documentation/AutoBOM_Deployment_Guide.md` (new) -- hosting decision,
  environment variables, deploy steps, DigiKey authorization/durable-store
  setup, credential rotation, rollback, logs, retention.
- `Documentation/AutoBOM_Operator_Guide.md` (new) -- Run BOM, Needs
  Review, Component Search, PartsBox Inventory, Purchasing (including
  per-artifact freshness/stale meaning), and an explicit "what NOT to do"
  section.

## 18. Release checklist

- [x] All automated tests passing: `python -m unittest discover -s tests -v`
      → **272 tests, OK** (up from the Phase 4 pass's 231; +41 from this
      pass's token-store/lock/retention/config-validation/error-handling
      work).
- [x] Compilation passes: `python -m py_compile app.py src/*.py tests/*.py`
      → clean.
- [ ] Vendor credentials rotated (external action -- see §13; not
      verifiable from this environment).
- [x] Durable DigiKey token backend implemented and tested (§2/§3) --
      **selecting and configuring one for the real deployment is still a
      required action before enabling `DIGIKEY_MYLISTS_ENABLED=true`
      there**; the app's startup warning enforces this is not missed
      silently.
- [ ] Live Mouser cart verified (§4/§5 -- blocked on credentials/test mode).
- [ ] Live DigiKey MyList verified (§4/§6 -- blocked on credentials/test mode).
- [ ] PartsBox inventory verified (§4/§8 -- blocked on credentials/test mode).
- [x] No secrets committed (§12 -- verified via `git check-ignore`).
- [x] Multi-user side-effect/safety review complete (§14/§15 -- no live
      multi-browser session test was run, but the mechanism is unit- and
      AppTest-verified and unchanged/extended, not newly built untested).
- [x] Purchasing side-effect safety test complete (§15).
- [x] Stale artifact behavior tested (Phase 4 pass, re-confirmed
      unmodified in §15).
- [x] Retention cleanup tested (§10).
- [ ] Deployment restart tested (requires an actual host -- not
      performable in this environment).
- [ ] DigiKey token survives restart (requires an actual durable backend
      instance and a real restart -- not performable here; the file-lock
      and re-read-from-store behavior are unit-tested, but an end-to-end
      restart against a live host is an external verification step).
- [ ] Team operator smoke test complete (requires a real teammate and a
      deployed instance -- see the acceptance test plan below).

## Acceptance test plan

Use a small, known BOM (a handful of parts spanning Mouser-sourceable,
DigiKey-sourceable, and at least one that will land in Needs Review).

| # | Step | Expected outcome |
|---|---|---|
| 1 | Open AutoBOM (deployed URL) | Loads with no configuration warning banners (or only expected ones you've consciously accepted). |
| 2 | Upload the test BOM | Cleaned/normalized without error; project/build quantity accepted. |
| 3 | Run sourcing | Results Workspace shows summary metrics; at least one item lands in Needs Review by design. |
| 4 | Review Results | All Results table searchable/filterable; Source and Status are visibly distinct concepts. |
| 5 | Resolve one Needs Review item (Find Replacement, approve a candidate) | Row updates in place; Needs Review count decreases. |
| 6 | Go to Purchasing | Status shows **Stale — BOM Changed**; downloads for regeneratable artifacts are disabled. |
| 7 | Resolve all remaining Needs Review items | Needs Review count reaches 0. |
| 8 | Click Regenerate Purchasing | No errors; each supplier that actually has items gets a cart/MyList exactly once. |
| 9 | Confirm only required supplier artifacts were generated | A supplier with zero sourced items shows **Not Required**, never blocks readiness. |
| 10 | Verify downloads | Every artifact re-enabled except the multi-sheet workbook and PartsBox unmatched CSV (by design -- re-run BOM Automation for a current copy of those). |
| 11 | Verify Mouser CartKey | Present in the Purchasing page; usable to complete the manual Share step in Mouser. |
| 12 | Verify DigiKey MyList/list ID | Present in the Purchasing page. |
| 13 | Verify PartsBox project/storage | Same-name project + storage created/reused; storage carries the `production` tag. |
| 14 | Restart/redeploy the app | Loads cleanly; `runs/` may be empty (expected on an ephemeral host) -- start a new run. |
| 15 | Confirm DigiKey integration still works after restart | Requires a durable token-store backend actually configured (§2) -- if only `memory` is configured, expect this to require re-authorization, which is the documented, accepted limitation, not a bug. |
| 16 | Open AutoBOM from a second browser/incognito session | Independent session state; no visibility into session 1's run. |
| 17 | Run steps 2-13 concurrently in both sessions with the same filename | Both complete independently; no file collision (`runs/<run_id>/` isolation), no cross-session data leakage. |

## Tests and results

```
python -m unittest discover -s tests -v
Ran 272 tests in 13.970s
OK

python -m py_compile app.py src/*.py tests/*.py
(clean, no output)
```

New/changed test files this pass: `tests/test_digikey_token_persistence.py`
(+18 tests), `tests/test_run_retention.py` (new, 10 tests),
`tests/test_config_validation.py` (new, 12 tests),
`tests/test_http_error_utils.py` (+4 tests). No existing test was deleted
or weakened to make the suite pass.

## Remaining manual limitations

1. DigiKey MyLists automation is only as durable as whichever
   `DIGIKEY_TOKEN_STORE` backend is actually configured for the real
   deployment -- this pass makes durable options available and default
   behavior clearly warned-about, but does not itself stand up an external
   store (that requires a team infrastructure decision, per the durable-
   token strategy doc).
2. Mouser sharing remains manual (Model B) -- no supported/private share
   API has been verified.
3. DigiKey share identifier is unavailable -- not confirmed to exist in the
   current API.
4. PartsBox saved-filter creation remains a manual step -- no supported API
   confirmed.
5. Live vendor response-shape verification (Mouser CartKey location,
   DigiKey MyLists fields, PartsBox schema) is still outstanding --
   checklist in §4, not results.
6. A restart-triggered Streamlit session loss (in-progress, unsaved BOM
   review) is an inherent Community Cloud/single-process hosting
   characteristic, not something this pass engineered around, since doing
   so would mean persisting run state beyond what the product's non-goals
   allow ("treat local cloud filesystem as ephemeral... do not use it as
   the authoritative... database").
7. No systematic operator-facing error-message rewrite was done (§16) --
   vendor HTTP errors are now uniformly sanitized, but a full UX pass over
   every message string was judged out of scope for this pass.
8. Two legacy, unused files were noticed and left untouched (not part of
   the live `app.py`/`workflow_runner.py` call graph, so out of scope for
   a hardening pass to touch without being asked): `src/main.py` (a
   standalone CLI-style script using shared, non-isolated `input`/`output`
   paths -- never imported by `app.py`) and `src/nexar_client.py`/
   `src/supplier_matcher.py` (an unused Nexar integration, imported only by
   each other, not by any live code path).

## Final release verdict

**READY WITH DOCUMENTED MANUAL LIMITATION.**

All automated engineering work achievable without live vendor
credentials/test-mode access is complete and tested (272/272 passing): the
durable DigiKey token backend and its concurrency safety, run-directory
retention, configuration validation, and a secret-exposure gap in vendor
error handling that this review surfaced and fixed. The application is
architecturally ready for hosted team use on Streamlit Community Cloud
(private, team-restricted) or an equivalent host.

**Before enabling `DIGIKEY_MYLISTS_ENABLED=true` in the real deployment**,
the team must select and configure an actual durable `DIGIKEY_TOKEN_STORE`
backend (§2/§6 of the deployment guide) -- this is not optional, and the
app's own startup banner will say so if it's missing. Live vendor response-
shape verification (§4) should happen against the real deployment with real
credentials before the team fully relies on Mouser CartKey extraction,
DigiKey MyLists field mapping, or PartsBox field assumptions -- none of
these were falsified in this review, but none were freshly confirmed
either, and the code already treats them as best-effort pending that
confirmation.

No future procurement-intelligence development follows from this report.
