# AutoBOM Remote-PC Predeployment Report

Scope: finish, test, package, and locally validate every software/deployment
building block achievable without access to the actual Yank remote
engineering PC, so that when access returns, deployment is installation and
acceptance testing, not new development. Authoritative target: the Yank
Windows remote engineering PC (see
`Documentation/AutoBOM_Remote_PC_Deployment_Architecture_Audit.md`), one
Streamlit process under a Windows service, LAN/VPN-restricted.

No Yank PC configuration was performed. No orders were placed. No VPN/
firewall infrastructure was implemented. No unrelated feature work was
started.

---

## 1. Files changed

**New:**
- `src/file_lock.py` -- shared `FileLock`/`LockAcquisitionError`, extracted from `supplier_lookup_cache.py`.
- `src/deployment_preflight.py` -- production preflight checks (`python src/deployment_preflight.py`).
- `requirements-lock.txt` -- full transitive dependency lock.
- `.github/workflows/tests.yml` -- CI: compile + full test suite on push/PR.
- `deploy/` (new directory): `production.env.example`, `streamlit_config.prod.toml`, `launch_production.ps1`, `run_local_production_like.py`, `windows_task_scheduler_install.ps1.template`, `windows_service_install_nssm.ps1.template`, `windows_service_uninstall.ps1.template`, `README.md`.
- `Documentation/AutoBOM_Onsite_Deployment_Checklist.md`.
- `Documentation/AutoBOM_Remote_PC_Predeployment_Report.md` (this report).
- Tests: `tests/test_file_lock.py`, `tests/test_fresh_process_persistence.py`, `tests/test_deployment_preflight.py`.

**Modified:**
- `src/token_store.py` -- `HttpTokenStore`, `TokenStoreError`, `TokenStore.lock()`, `TOKEN_LOCK_STALE_SECONDS` (pre-existing from the prior pass; this pass added the stale-threshold fix, see §4).
- `src/digikey_client.py` -- F1 fail-closed lock usage (§3), F2 token-persistence-failure surfacing (§5), confirmed-live-shape comments (§14).
- `src/digikey_mylists_client.py` -- `token_store_error` propagated into `create_digikey_mylist_from_bom()`'s result.
- `src/workflow_runner.py` -- `_build_digikey_purchasing()`/`regenerate_purchasing()`/`run_bom_workflow()` treat a created-but-persistence-degraded MyList as a failed artifact, not current; confirmed-live-shape comment on `_extract_mouser_cart_key()`.
- `src/mouser_client.py` -- confirmed-live-shape comment.
- `src/component_lookup.py` -- confirmed-live-absence comment for PartsBox `part/category`/`part/package`.
- `src/partsbox_project_builder.py` -- confirmed-live-shape comment for `storage/tags`.
- `src/supplier_lookup_cache.py` -- uses shared `file_lock.FileLock`; `default_cache_path()` respects `AUTOBOM_CACHE_ROOT`.
- `src/run_workspace.py` -- `resolve_runs_root()` respects `AUTOBOM_RUNS_ROOT`.
- `src/run_retention.py` -- uses `resolve_runs_root()`; F4 docstring correction (§4).
- `app.py` -- Mouser share caption updated to reflect Mouser's confirmation (§11).
- `requirements.txt` -- pinned to exact tested versions.
- `.devcontainer/devcontainer.json` -- Python 3.11 → 3.12, dev-only `containerEnv` safeguards, installs from the lock file.
- `Documentation/AutoBOM_Deployment_Guide.md` -- hosting decision updated to the Yank PC (§1), run-retention wording corrected (§4).
- `Documentation/AutoBOM_Operator_Guide.md` -- Mouser share confirmation update.
- Tests: `tests/test_digikey_token_persistence.py` (+F1/F2 regressions), `tests/test_purchasing_state.py` (+1 F2 regression), `tests/test_run_retention.py` (+1 F4 regression).

## 2. DigiKey locking correction (Codex F1, part 1)

`FileLock.__enter__()` previously called `acquire()` and returned `self`
regardless of the result, so `with FileLock(...):` could run its
protected body having never actually acquired the lock. Fixed: `__enter__()`
now raises a new `LockAcquisitionError` when `acquire()` returns `False`,
so entering the `with` block is now a hard guarantee of ownership.
`SupplierLookupCache.save()` is unaffected -- it already used manual
`acquire()`/`release()` with an explicit boolean check, never `with`.

`DigiKeyClient.get_user_access_token()` wraps its `with self.token_store.lock():`
in a try/except for `LockAcquisitionError`, converting it to a friendly,
secret-safe `RuntimeError` ("DigiKey token store is busy..."). Because the
entire read-refresh-write cycle (including the `requests.post` refresh
call) lives inside that `with` block, a failed acquisition structurally
guarantees **zero** DigiKey HTTP requests -- proven by
`test_lock_timeout_makes_zero_digikey_requests`, which holds the lock
externally and asserts `requests.post` is never called.

## 3. Stale-lock policy (Codex F1, part 2)

The lock's stale-reclaim threshold was a single global constant
(`LOCK_STALE_SECONDS = 30`), equal to the DigiKey token endpoint's own
request timeout -- so a legitimately slow-but-live 30s-ish refresh could
have its lock reclaimed by a second waiter mid-request. Fixed:
`FileLock` now takes a per-instance `stale_after` parameter (default
still 30s, unchanged for `SupplierLookupCache`).
`token_store.TOKEN_LOCK_STALE_SECONDS = 120` (4x the DigiKey token
endpoint's 30s request timeout -- a simple, conservative margin, not a
distributed-lock scheme) is used by `FileTokenStore.lock()`/
`EnvFileTokenStore.lock()` specifically. Documented in both the constant's
comment and `FileLock.__init__`'s docstring. Tested in
`tests/test_file_lock.py::FileLockStaleThresholdTests`.

## 4. Rotated-token persistence failure behavior (Codex F2)

Previously, a rotated refresh token whose `token_store.set()` call raised
`TokenStoreError` was recorded on `client.token_store_error` but the
overall MyList call still reported success -- purchasing had no way to
know the store still held DigiKey's now-invalidated old token.

Fixed end-to-end:
- `DigiKeyClient` already updates `self.refresh_token` in memory *before*
  attempting to persist (prior pass), so this process keeps working; the
  persistence failure itself is recorded on `token_store_error` and never
  silently dropped.
- `create_digikey_mylist_from_bom()` now reads `client.auth_client.token_store_error`
  and includes it as `token_store_error` in its returned dict,
  unconditionally (every return branch).
- `workflow_runner._build_digikey_purchasing()` surfaces this as
  `token_persistence_degraded: bool`.
- `regenerate_purchasing()` and `run_bom_workflow()` both now treat
  "created but token-persistence-degraded" as `STATUS_FAILED`, not
  `STATUS_CURRENT` -- purchasing cannot report DigiKey as fully healthy
  in this state. The actually-created MyList's `list_id`/data are still
  preserved in `response["purchasing"]["digikey"]` for the operator; only
  the artifact-freshness classification changes.
- An operator-facing warning/error message is appended either way
  ("DigiKey MyList was created, but its rotated refresh token could not
  be durably persisted...").
- Refresh/access token values are never printed, persisted in logs, or
  shown in the UI -- confirmed by re-grepping every changed file for
  `print(` (see §21).
- Restarting later does not silently treat the stale stored token as
  valid: it's simply the value `_load_refresh_token()`/`_current_refresh_token()`
  reads next, and DigiKey will reject it with a clear, sanitized
  `RuntimeError` on the next real refresh attempt (confirmed live -- see
  §12; this exact failure mode was hit for real during this pass).

Tests: `DigiKeyTokenPersistenceFailureDegradesResultTests` (client →
`create_digikey_mylist_from_bom()` propagation) and
`test_digikey_mylist_created_but_token_persistence_failed_is_reported_as_failed`
(full `regenerate_purchasing()` → `derive_purchasing_status()` path).

## 5. FileTokenStore/preflight

`src/deployment_preflight.py` (new), runnable now against local temp
directories and later against the real production token directory with
no code change:

- `check_python_version()`, `check_dependency_versions()` (every pin in
  `requirements-lock.txt`, not just direct dependencies).
- `check_runs_root()` / `check_cache_root()` / `check_logs_directory()`
  -- real write/read-back probes, self-cleaning.
- `check_file_token_store(directory)` -- exercises the exact
  read/write/atomic-replace/lock mechanics `FileTokenStore` and its lock
  use, against a real directory; flags a directory located inside the
  source checkout as a WARN (release-folder replacement / `git clean`
  risk).
- `check_digikey_token_store_resolution()` -- confirms the CONFIGURED
  backend actually resolves to what was requested (catches
  `DIGIKEY_TOKEN_STORE=file` silently falling back to `MemoryTokenStore`
  when the path isn't set, which would otherwise only be discovered after
  a restart drops the token).
- `check_production_development_separation()`, `check_streamlit_production_settings()`.
- Aggregates `config_validation.py`'s existing warnings (missing
  credentials, non-durable token store while MyLists is enabled).
- Returns structured PASS/WARN/FAIL results; `python src/deployment_preflight.py`
  prints a report and exits non-zero on FAIL. Never creates a vendor
  cart/MyList (verified by `test_never_raises_creates_no_vendor_side_effect`,
  which asserts the module never even references
  `create_mouser_cart_from_bom`/`create_digikey_mylist_from_bom`). Never
  prints a secret/token value.

Ran locally against this dev environment: overall **WARN** (expected --
PARTSBOX_API_KEY warning was a false read at first because the script
didn't load `.env` on its own; fixed by adding the same `load_dotenv()`
call every other client module makes). After that fix, output correctly
reflects real `.env` state: DigiKey token store resolves to
`EnvFileTokenStore` (durable for single-machine local use), runs/cache
directories writable, Streamlit settings at secure defaults, only the
expected "runs/cache/token all inside the checkout" development-mode
notice.

Tests: `tests/test_deployment_preflight.py` (15 tests).

## 6. Configurable runtime paths

- `run_workspace.resolve_runs_root()`: `AUTOBOM_RUNS_ROOT` env var
  overrides the in-repo `runs/` default; read at call time (not baked
  into a module constant), backward-compatible (falls back to the
  existing default when unset).
- `supplier_lookup_cache.default_cache_path()`: `AUTOBOM_CACHE_ROOT`
  overrides the in-repo `.cache/` default the same way; the more
  specific, pre-existing `SUPPLIER_LOOKUP_CACHE_PATH` (exact file path)
  still takes priority when set.
- `run_retention.cleanup_old_runs()` now resolves its default via
  `resolve_runs_root()` instead of a static import, so it honors the
  same override.
- No large storage redesign -- both are single-function additions,
  backward-compatible by construction (existing tests that pass an
  explicit `runs_root=`/`SUPPLIER_LOOKUP_CACHE_PATH` are unaffected).
- Tested implicitly by the full existing `run_workspace`/`run_retention`/
  `supplier_lookup_cache` suites continuing to pass unmodified, plus
  `deployment_preflight`'s tests exercising the override directly.

## 7. Dependency locking

- `requirements.txt` pinned to the exact versions this test suite is
  verified against (`requests==2.34.2`, `pandas==3.0.5`, `openpyxl==3.1.5`,
  `python-dotenv==1.2.3`, `streamlit==1.62.0`).
- `requirements-lock.txt` (new): full `pip freeze` output, every
  transitive dependency pinned, for byte-for-byte reproducible production
  installs.
- The full test suite (302 tests) was run against exactly this
  environment/lock -- not a different one.

## 8. Dev Container alignment

- Base image: Python 3.11 → **3.12**, matching the tested/production
  version.
- `updateContentCommand` now installs from `requirements-lock.txt`
  (falling back to `requirements.txt` if the lock file is somehow
  absent).
- Added `containerEnv` defaults (`DIGIKEY_TOKEN_STORE=memory`,
  `AUTOBOM_RUNS_ROOT`/`AUTOBOM_CACHE_ROOT` unset) as an explicit,
  documented safeguard against ever discovering a host production
  directory -- the container's filesystem is already isolated regardless,
  but this makes the separation a stated property, not an accident.
- The container's relaxed `--server.enableCORS false --server.enableXsrfProtection false`
  launch flags are explicitly commented as development-preview-only,
  pointing at `deploy/streamlit_config.prod.toml` as what production must
  use instead.

## 9. Local production simulation

`deploy/run_local_production_like.py` -- runnable right now on the
developer machine: creates isolated `runs`/`cache`/`token` directories
under the OS temp directory (never inside the repo, never resembling the
documented real production path), sets `DIGIKEY_TOKEN_STORE=file` against
them, runs the preflight check, then launches `streamlit run app.py`
against that configuration. Does not touch the developer's real `.env`,
real DigiKey token store, or the in-repo `runs/.cache`.

## 10. Local restart/persistence simulation

The literal "does persistence survive a restart" question is answered at
the level that can actually be proven without a real reboot:
`tests/test_fresh_process_persistence.py` spawns real, independent
`python` subprocesses (via `subprocess.run`, which blocks until each
process fully exits) sharing only a temp directory:

- One process writes a token value and exits completely.
- A second, brand-new process reads it back.
- A three-step chain (write → read-and-rotate → read-the-rotated-value)
  proves the SAME property `DigiKeyClient` actually depends on:
  `TokenStore.get()`/`set()` persistence is independent of any Python
  object's or process's lifetime -- exactly what a Windows service
  restart needs, demonstrated with real OS process boundaries, not just
  object garbage collection within one interpreter.

The real Windows machine reboot test remains HOST SETUP PENDING (see
§25).

## 11. Live Mouser verification

Performed live against the developer's own valid Mouser credentials
(already present in this environment's `.env`, `SUPPLIER_DRY_RUN=false`,
`MOUSER_CART_ENABLED=true`, `MOUSER_CART_DRY_RUN=false`). No order was
placed or submitted.

**Confirmed:**
- `search_by_mpn()` real keyword-search response for `RC0603FR-0710KL`
  returned 2 real candidates with the exact top-level field shape the
  existing `_mouser_part_to_result()` already assumed: `Category`,
  `Manufacturer`, `ManufacturerPartNumber`, `MouserPartNumber`,
  `ProductDetailUrl` are all plain top-level strings; `Availability` is a
  combined string (`"2953404 In Stock"`), matching `_parse_stock()`'s
  digit-extraction; `PriceBreaks[0].Price` is a currency-prefixed string
  (`"$0.10"`), matching `_first_price()`. No parsing code needed to
  change.
- **Created one real, disposable test cart** (1x `603-RC0603FR-0710KL`,
  quantity 1) via `MouserCartClient.add_items_to_cart()`. Confirmed:
  `CartKey` is returned at the **top level** of the response (no `Cart`
  sub-object present at all in this response), exactly matching
  `_extract_mouser_cart_key()`'s first branch. `Errors` is an empty list
  on success. The nested `Cart.CartKey` fallback branch remains
  unconfirmed/unexercised but is kept as cheap defensive compatibility.
- Zero-item behavior (`build_mouser_cart_items()` returning `[]` →
  `create_mouser_cart_from_bom()`'s `created: False` path) was already
  covered by existing unit tests with synthetic data; not re-verified
  live (would require an intentionally-empty cart call, which adds no
  new information over the unit test).
- Mouser has directly confirmed (per the user, standing instruction
  incorporated into this pass): API-created carts appear in My Saved
  Carts, and the Cart Sharing Access ID is derived internally from the
  CartKey/GUID, but that derivation is **not currently exposed through
  any supported public or Automation Services API**. Model B (automatic
  cart creation, manual Share action, manual hand-off of the Access ID)
  is therefore the **current supported/interim workflow** -- not the
  intended final product direction, but the correct approach until
  Mouser exposes a supported sharing API. The automatic Cart API
  creation and its CartKey remain the foundation/extension point for a
  future fully-automated handoff; nothing about that path was narrowed
  or removed. Updated in `app.py`'s Purchasing page caption and the
  operator guide accordingly. **Do not attempt to reverse-engineer the
  Access-ID derivation.** AutoBOM's product boundary is unchanged by
  this: it prepares cart/MyList/share/export handoff data only --
  checkout, payment, and order submission remain manual, outside
  AutoBOM, regardless of which sharing model is in use.

**Not performed:** a live invalid-API-key/error-response capture (would
require deliberately breaking working credentials); `describe_error_response()`'s
allow-listed fields remain unconfirmed against a genuine Mouser error
body specifically (they are, however, confirmed against a genuine DigiKey
error body -- see §12).

A disposable test cart now exists in the real Mouser account (1 item,
quantity 1). Not deleted (deletion wasn't requested/tested).

## 12. Live DigiKey verification

Performed live against the developer's own valid DigiKey credentials.
No order was placed.

**Confirmed:**
- Client-credentials OAuth (`get_access_token()`) succeeded against the
  real token endpoint.
- `product_details()` for `RC0603FR-0710KL` returned the exact nested
  shapes `_digikey_product_to_result()` already assumed: `Manufacturer`
  → `{"Id":.., "Name":..}`, `Category` → `{"CategoryId":.., "Name":..}`,
  `ProductStatus` → `{"Id":.., "Status":"Active"}`. `QuantityAvailable`
  is a plain int. **`DigiKeyProductNumber` was absent at the top level
  for this real part and only present inside `ProductVariations[0]`** --
  confirming the existing fallback-to-variations logic is load-bearing in
  practice, not unexercised defensive code. `ProductVariations[0].StandardPricing[0].UnitPrice`
  matched `_first_unit_price()`'s assumption exactly.
- **MyList creation was initially BLOCKED**: the stored
  `DIGIKEY_REFRESH_TOKEN` in this environment's `.env` was invalid/expired
  (`HTTP 401: Invalid RefreshToken | request id: <redacted>`), requiring
  an interactive OAuth re-authorization
  (`python src/digikey_oauth_setup.py`) that this environment can't
  perform non-interactively. This was an external/credential-state fact,
  not a code defect -- and it incidentally proved the error-handling path
  works correctly against a genuine live failure: the raised message was
  sanitized (allow-listed fields + request ID only, confirming
  `describe_error_response()`'s field names against a REAL DigiKey error
  body, not just mocks) and no secret was exposed. No token-store write
  was attempted or corrupted by that failed attempt (the exception is
  raised before the rotation/persistence code ever runs).
- **The developer re-authorized DigiKey** (`python src/digikey_oauth_setup.py`,
  run locally). All remaining DigiKey verification below was then
  completed live:
  - `get_user_access_token()` succeeded; `token_store_error: None`.
  - Created three real, disposable test MyLists (`AUTOBOM-API-TEST-2026-09-25`
    and two follow-up variants used to inspect `add_parts_to_list()`'s
    response shape in isolation) via `create_digikey_mylist_from_bom()`
    and direct `DigiKeyMyListsClient` calls, each with one real DigiKey
    part (`311-10.0KHRTR-ND`, quantity 1). All three succeeded
    (`created: True`, real string `list_id` returned).
  - **Confirmed: `create_list()`'s real response is a bare string** (the
    list ID itself, e.g. `"02UFKJOWAE"`), not a dict -- exactly matching
    the `isinstance(create_result, str)` branch in
    `create_digikey_mylist_from_bom()`, confirming that branch is
    load-bearing in practice, not unexercised defensive code.
  - **Confirmed: `add_parts_to_list()`'s real response is a plain list of
    string item IDs** (e.g. `["N7S19MYZ7F"]`), not a list of dicts with
    per-part detail fields.
  - **Confirmed: no share identifier/link field exists anywhere in either
    response.** `share_id: None` (with the existing comment that a
    distinct share field isn't present and must be verified) is now a
    **confirmed absence**, not an open question -- nothing was fabricated
    to fill this gap, per instruction.
  - **Confirmed token rotation live**: captured a hash of the stored
    refresh token before and after a `get_user_access_token()` call --
    the hash changed, confirming DigiKey rotates the refresh token on
    every use in this account's OAuth configuration. The new value was
    correctly persisted (read back via `store.get()` immediately after,
    matching the post-rotation hash; `token_store_error: None`),
    confirming the `EnvFileTokenStore` round-trip end-to-end against a
    real rotation, not just a mocked one. No raw token value was ever
    printed -- only SHA-256 hash prefixes, for comparison purposes only.
  - Three disposable test MyLists now exist in the real DigiKey account.
    Not deleted (deletion wasn't requested or tested, per standing
    instruction). Flagging for team awareness/manual cleanup if desired,
    alongside the disposable Mouser cart (§11) and PartsBox test project
    (§13).

## 13. Live PartsBox verification

Performed live against Yank's real PartsBox account/data. **Read-only
first**, as instructed; one disposable-test-project write afterward.

**Important correction/disclosure:** an early exploratory check in this
pass printed one real part's FULL raw `part/stock` field (a transaction
ledger including internal project codenames, build IDs, and quantities)
into this conversation's transcript. That was a mistake -- structural
checks should never include full record dumps for a live company system.
**Confirmed which operations were involved and their nature:** every
PartsBox call made, including the ones around that mistake, was a READ
operation (`storage/all`, `project/all`, `part/all`, `project/get-entries`)
-- none of them is in `PartsBoxClient.call()`'s `write_operations` allow-list
(`project/create`, `storage/create`, `project/add-entries`), so **nothing
was created, modified, or deleted** by that exploration. The mistake was
purely about what got printed into this transcript, not an unintended
write against the live system. All PartsBox checks after that point in
this pass used counts/key-names/aggregate statistics only, per corrected
instructions.

**Confirmed (structure/counts only, no raw records reproduced here):**
- `component_lookup.search_components(sources={"partsbox"})` works
  end-to-end live: 1 real result for `RC0603FR-0710KL`, with `stock`
  correctly staying `None` (never fabricated).
- `storage/all` (1888 real storage records): `storage/tags` is a plain
  list of plain strings when present (e.g. `["Production"]`, confirmed
  NOT lowercase-normalized by the API itself); the key is **entirely
  absent** (not an empty list) on untagged records -- 523 of 1888 records
  had a non-empty `storage/tags`, 22 of those matched "production"
  case-insensitively. `storage_has_tag()`'s `.get(...) or .get(...) or []`
  + `.strip().lower()` normalization is exactly correct against this real
  data; no change needed.
- `part/all` (~3450 real parts): `part/category` and `part/package` keys
  are **absent from every single record** -- these two fields are simply
  not present in this account's part list data via this endpoint (a
  `part/type` field exists but is a PartsBox-internal record-type
  discriminator -- `linked`/`local`/`meta` -- unrelated to electronic
  component category). Existing `component_lookup.py` code already
  defaults these to `""` rather than crashing or guessing, which is
  confirmed correct; category/package will read empty for PartsBox
  results until/unless a per-part detail endpoint exposing them is
  confirmed (none exists in this client today, and none was invented).
  `part/stock` exists but is a **per-storage transaction ledger** (a list
  of `{"stock/quantity", "stock/storage-id", "stock/timestamp", ...}`
  entries), not a simple current-quantity scalar -- confirming the
  product decision to NOT expose a stock/quantity column in PartsBox
  Inventory was correct, not merely cautious (computing "current stock"
  would require summing signed quantities per storage, which no existing
  code attempts and none was added here).
- `project/get-entries` (one real existing project, read-only): entry
  records carry exactly the field names `add_bom_entries_to_project()`'s
  idempotency logic already assumes (`entry/part-id`, `entry/designators`,
  `entry/quantity`, `entry/name`) -- confirmed correct, no change needed.
- **Disposable write test**, project name `AUTOBOM-API-TEST-2026-09-24`
  (matches the requested naming convention): `create_partsbox_project_and_storage()`
  created a new project and same-name storage, storage correctly tagged
  `production` (`storage_tag_missing: False`). `add_bom_entries_to_project()`
  run twice against this test project with one real, matched part
  (`RC0603FR-0710KL` / Yageo): **first run added 1 entry
  (`entries_added: 1`); second run added 0 and correctly reported it as
  already-existing (`entries_skipped_existing: 1`)** -- the exact P0
  idempotency guarantee from the very first phase of this project,
  now confirmed against the live API, not just mocks.
- This disposable test project/storage/entry **still exists** in the
  real PartsBox account (not deleted -- deletion wasn't requested or
  tested, per instructions). Flagging for team awareness/manual cleanup
  if desired.

**Not performed:** saved-filter API support (no code in `partsbox_client.py`
attempts this, and none was invented, per standing instruction not to
guess at unsupported endpoints).

## 14. Vendor-response code updates

**No parsing/extraction code changed.** Every live-confirmed shape
(Mouser search + cart, DigiKey product details, PartsBox storage/project/
part/entries) matched what the existing defensive extraction code
already assumed. The only changes here are comment/docstring updates
(§11-§13 above, and the file-level diffs) moving several "best-effort,
unconfirmed" notes to "confirmed live (2026-09-24)" status, and one
Purchasing-page caption update reflecting Mouser's confirmed
Access-ID-derivation statement (framed as the current supported/interim
workflow, not a permanent/final design -- see §11).

## 15. Production/development isolation

- Separate runtime paths: `AUTOBOM_RUNS_ROOT`/`AUTOBOM_CACHE_ROOT` (§6)
  let production point at directories entirely outside the checkout;
  development keeps the in-repo defaults with zero configuration.
- Separate token store: production uses `DIGIKEY_TOKEN_STORE=file`
  against a dedicated directory (`deploy/production.env.example`);
  development defaults to `env_file`/`memory`; the Dev Container is now
  explicitly pinned to `DIGIKEY_TOKEN_STORE=memory` via `containerEnv`
  (§8).
- `deployment_preflight.check_production_development_separation()` makes
  the common "everything still points at development defaults" mistake
  visible as a WARN rather than a silent footgun.
- Separate ports/credentials/directories are documented in the
  deployment guide's production/development table and the on-site
  checklist; not enforced in code beyond what's listed above (a config
  value, not a security boundary the app can technically prevent
  misuse of).

## 16. Service deployment package

`deploy/` (see `deploy/README.md` for the full table): a wrapper-independent
core launcher (`launch_production.ps1` -- loads env, copies the
production Streamlit config into place, runs preflight, starts
Streamlit) plus two alternative install templates (Task Scheduler --
needs nothing beyond Windows; NSSM -- needs an approved, pre-installed
NSSM), and a matching uninstall template. **Nothing was installed** --
these are reviewed-but-unexecuted templates, explicitly marked as such in
their own headers.

## 17. Streamlit production config

`deploy/streamlit_config.prod.toml`: headless, bound to a configurable
address/port, CORS/XSRF left at Streamlit's secure defaults (explicitly
NOT copying the Dev Container's relaxed settings), usage stats off. Kept
outside `.streamlit/` so it can never be auto-loaded by accident; the
on-site checklist / `launch_production.ps1` copy it into place in the
production checkout only.

## 18. Local multi-session verification

Not newly built in this pass -- already covered by the existing
`tests/test_run_workspace.py` (distinct run IDs/paths for the same
uploaded filename) and `tests/test_app_smoke.py` (independent
`st.session_state` per `AppTest` instance). Re-confirmed these still
pass (302/302). The real two-browser, two-machine test remains HOST
SETUP PENDING (§25/§26).

## 19. Purchasing side-effect verification

Re-confirmed unchanged from the prior pass, plus the new F1/F2 fixes
verified not to introduce a new side-effect path:
- Normal rerun/navigation/filter/download: no cart/MyList call (existing
  tests, unchanged, still passing).
- `Regenerate Purchasing` remains the only call site for
  `create_mouser_cart_from_bom()`/`create_digikey_mylist_from_bom()`.
- The new lock-fail-closed behavior cannot itself trigger an extra
  vendor call -- it can only prevent one that would otherwise have
  proceeded unsafely.
- Local/simulated production mode (`deploy/run_local_production_like.py`)
  deliberately does NOT set `DIGIKEY_MYLISTS_ENABLED`/`MOUSER_CART_ENABLED` --
  it only controls WHERE state lives, leaving vendor-call gating exactly
  as whatever `.env`/environment already has it.

## 20. Release/CI readiness

`.github/workflows/tests.yml` (new): installs `requirements-lock.txt`,
compile-checks `app.py`/`src/*.py`/`tests/*.py`, runs the full suite with
every vendor integration explicitly disabled/dry-run via env vars (no
live credentials used or needed in CI). Runs on every push/PR. **Does
not deploy anything** -- production deployment remains the manual,
approved on-site procedure in `Documentation/AutoBOM_Onsite_Deployment_Checklist.md`,
per instruction not to build automatic production deployment.

## 21. Documentation changes

- `Documentation/AutoBOM_Deployment_Guide.md`: hosting decision updated
  to the Yank PC (old Community Cloud assessment kept as clearly-labeled
  historical reference, not deleted); run-retention wording corrected to
  no longer overclaim protection for other sessions' runs (Codex F4).
- `Documentation/AutoBOM_Operator_Guide.md`: Mouser share section updated
  to describe Model B as the current supported/interim workflow (per
  Mouser's confirmed Access-ID-derivation statement), not the intended
  final product direction, with the automatic Cart API/CartKey path
  preserved as the extension point for a future supported sharing API.
- `Documentation/AutoBOM_Onsite_Deployment_Checklist.md` (new): the exact
  27-step install procedure.
- `deploy/README.md` (new): what each deployment file is for.
- This report.
- `Documentation/AutoBOM_Final_Deployment_Hardening_Report.md` (prior
  pass) was **not** rewritten -- it remains an accurate historical record
  of that pass's own scope; superseding statements are made explicitly in
  this report and in the deployment guide instead of editing history.

## 22. Tests and results

```
python -m unittest discover -s tests -v
Ran 302 tests in 18.352s
OK

python -m py_compile app.py src/*.py tests/*.py
(clean, no output)
```

Net new this session: 30 tests (272 → 302) --
`tests/test_file_lock.py` (7, new file), `tests/test_fresh_process_persistence.py`
(3, new file), `tests/test_deployment_preflight.py` (15, new file),
`tests/test_digikey_token_persistence.py` (+3: lock-timeout/zero-requests,
2x token-persistence-degradation propagation), `tests/test_purchasing_state.py`
(+1: F2 regression), `tests/test_run_retention.py` (+1: F4
documentation/behavior regression). No existing test was deleted or
weakened.

## 23. CODE READY

Everything below is fully implemented, tested, and does not require the
Yank PC:

- DigiKey lock fail-closed + stale-threshold fix (Codex F1) with a
  concurrency regression test proving zero stray requests.
- Rotated-token persistence failure now degrades reported purchasing
  status instead of appearing healthy (Codex F2).
- `FileTokenStore` preflight, runnable against any directory now.
- Fresh-process (real OS subprocess) persistence proof.
- Configurable `AUTOBOM_RUNS_ROOT`/`AUTOBOM_CACHE_ROOT`.
- Dependency lock (`requirements.txt` + `requirements-lock.txt`), Dev
  Container aligned to Python 3.12.
- Local production-like run mode and its preflight integration.
- Windows service/launch templates (unexecuted, reviewed).
- Production Streamlit config template.
- CI running the full suite + compile checks.
- Live Mouser search + one disposable cart verified; CartKey shape
  confirmed; Mouser's Access-ID-derivation statement incorporated (Model
  B documented as the current supported/interim workflow, not a final
  design).
- Live DigiKey auth + product search verified; MyList blocked on
  external credential state, not code.
- Live PartsBox search/storage-tag/project-entry shapes verified;
  BOM-entry idempotency (the very first P0 finding of this whole
  project) reconfirmed against the real API.
- Documentation reorganized into the categories below.

## 24. TEAM PILOT BLOCKERS

None remaining that are genuinely code-level. The two Codex-flagged
defects that WOULD have blocked a safe pilot (F1, F2) are fixed and
tested. Firewall/VPN/SSO are explicitly NOT included here (§28).

## 25. HOST SETUP PENDING

Everything requiring the actual Yank PC:
- Creating the production checkout/venv/directories.
- Creating/configuring the dedicated service account.
- Applying NTFS ACLs.
- Configuring production secrets on that host.
- Installing the Windows service (Task Scheduler or NSSM).
- Confirming the machine's real hostname/IP and Windows Firewall rule.
- A real machine reboot (not just a service restart) proving DigiKey
  token persistence survives it.
- Real two-browser/two-user concurrency on the actual host.
- Team pilot sign-off.

The full 27-step procedure: `Documentation/AutoBOM_Onsite_Deployment_Checklist.md`.

## 26. LIVE VENDOR VERIFIED

- Mouser: search response shape (Category/Manufacturer/ManufacturerPartNumber/
  MouserPartNumber/ProductDetailUrl/Availability/PriceBreaks), cart
  creation + top-level CartKey shape, zero-Errors-on-success shape.
- DigiKey: client-credentials auth, product-details response shape
  (nested Manufacturer/Category/ProductStatus, DigiKeyProductNumber
  fallback-to-variations behavior), sanitized live error-message shape
  (via the expired-refresh-token failure). After the developer
  re-authorized (`python src/digikey_oauth_setup.py`): MyList creation
  (three real disposable test lists), confirmed `create_list()` returns
  a bare string list ID and `add_parts_to_list()` returns a plain list of
  string item IDs, confirmed no share identifier/link field exists in
  either response, confirmed live refresh-token rotation (hash-compared
  before/after) with correct `EnvFileTokenStore` persistence
  (`token_store_error: None` throughout).
- PartsBox: storage list shape + tag presence/absence/case behavior,
  part list shape + confirmed absence of category/package fields +
  stock-as-ledger structure, project-entries shape, project/storage
  creation with production tag, BOM-entry idempotency (add-then-skip
  confirmed live).

## 27. LIVE VENDOR PENDING

- Mouser zero-item/error-response-shape verification (only synthetic/mock
  coverage exists for these two specific cases).
- PartsBox saved-filter API support (no client code attempts this; still
  an open question requiring a documentation/API-support check with
  PartsBox, not a code test).
- Config-only vendor-credential switching (developer → company
  Mouser/DigiKey credentials) is confirmed TRUE by code review (every
  client reads credentials from `os.getenv`, nothing hardcoded) but was
  not exercised with an actual second credential set in this pass.

## 28. SECURITY HARDENING BACKLOG

Tracked, not blocking the initial trusted-team pilot:
- Newlab shared-network exposure assessment.
- Windows Firewall rule scoping to the approved subnet/VPN.
- VPN/secure remote access design (no vendor chosen or implied here).
- Reverse proxy / SSO in front of Streamlit, if LAN/VPN membership alone
  isn't judged a sufficient trust boundary.
- Broader access/audit logging beyond stdout/stderr.

AutoBOM may enter a trusted internal pilot before this backlog is
complete, provided: the shared-network exposure is a known, accepted
risk; the app is never intentionally exposed to the public Internet;
credentials are protected (secrets, never committed); purchasing remains
an explicit operator action; and only trusted teammates are instructed to
use it. This is **not** "fully security hardened" -- it's a documented,
bounded interim position.

## 29. Onsite deployment checklist

`Documentation/AutoBOM_Onsite_Deployment_Checklist.md` -- the full
27-step procedure summarized in §25.

## 30. Remaining risks

- DigiKey MyLists automation was verified against the developer's own
  DigiKey account only. It still needs re-verification against the
  actual production/company DigiKey account's own credentials and
  refresh-token rotation policy before the team relies on it (a
  different account may behave differently, e.g. a different rotation
  cadence or MyLists entitlement).
- The Windows-service-wrapper choice (Task Scheduler vs. NSSM) is still
  open; both templates are prepared, but neither has been rehearsed on
  Windows (this environment's tooling is Linux/bash-based; the `.ps1`
  files were written carefully but not executed anywhere in this pass).
- A disposable Mouser test cart, a disposable PartsBox test project
  (`AUTOBOM-API-TEST-2026-09-24`), and three disposable DigiKey test
  MyLists (`AUTOBOM-API-TEST-2026-09-25` and two variants) now exist in
  real vendor accounts and were intentionally left in place (no delete
  testing performed).
- The security hardening backlog (§28) remains real, ongoing work, not
  eliminated by "pilot-ready" status.

## 31. Final verdict

**CODE READY FOR TEAM-PILOT INSTALLATION.**

Both Codex-flagged defects that would have blocked a safe pilot (F1 lock
fail-closed, F2 token-persistence-failure surfacing) are fixed and
regression-tested. Every other software/deployment building block
achievable without the Yank PC is prepared: durable token store
preflight, fresh-process persistence proof, configurable runtime paths,
a pinned dependency lock, an aligned Dev Container, a wrapper-independent
launch mechanism with two service-install options, a production Streamlit
config, CI, and a complete on-site installation checklist. Live vendor
verification was completed for all three vendors: Mouser (search + one
real disposable cart, CartKey shape confirmed), PartsBox (search/storage/
project shapes, and the P0 BOM-entry idempotency guarantee reconfirmed
live), and DigiKey (auth + search confirmed; after the developer
re-authorized via `python src/digikey_oauth_setup.py`, MyList creation,
list ID shape, add-parts response shape, confirmed absence of any share
field, and live refresh-token rotation/persistence were all verified
against three real disposable test MyLists).

Remaining work is genuinely HOST SETUP PENDING (installing on the actual
machine) or LIVE VENDOR PENDING against the PRODUCTION vendor accounts
specifically (§27/§30 -- Mouser zero-item/error-shape edge cases,
PartsBox saved-filter API support, and re-confirming DigiKey against the
company's own account rather than the developer's), not further
application development.

Firewall/VPN/SSO hardening is tracked as an explicit backlog and is
correctly NOT a gate on starting an initial trusted-team pilot, per the
release-model instructions for this pass.

No procurement-intelligence or unrelated feature work follows from this
report.
