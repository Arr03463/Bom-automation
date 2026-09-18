# AutoBOM Team Release — Phase 2 Implementation Report

**Scope completed:** the two remaining confirmed P1 hosting blockers — supplier lookup cache concurrency safety, and DigiKey refresh-token persistence.
**Scope explicitly not touched:** Results Workspace, shared component search/filter engine, Needs Review UI. Per instructions, this phase stops before that work begins.

## Files changed

**New:**
- `src/token_store.py` — token persistence abstraction (`TokenStore`, `MemoryTokenStore`, `EnvFileTokenStore`, `FileTokenStore`, `build_token_store()`)
- `tests/test_supplier_lookup_cache_concurrency.py`
- `tests/test_digikey_token_persistence.py`

**Modified:**
- `src/supplier_lookup_cache.py`
- `src/digikey_client.py`
- `src/digikey_oauth_setup.py`

## 1. Supplier lookup cache concurrency

**Problem (from the audit):** `SupplierLookupCache.save()` wrote the whole in-memory dict directly to one shared JSON file with no locking or atomic replacement. Two concurrent runs could interleave writes (partial JSON) or silently lose each other's updates (last full overwrite wins).

**Approach — smallest reliable fix, no new infrastructure:**
- **Atomic write:** `_atomic_write_json()` writes to a uniquely-named temp file in the same directory, then `os.replace()`s it into place. `os.replace` is atomic on both POSIX and Windows, so a concurrent reader always sees either the old file or the new one, never a partial write.
- **Advisory file lock:** `_FileLock` (new, ~50 lines, standard library only) uses `O_CREAT | O_EXCL` to claim a `<cache>.lock` marker file. A lock left behind by a crashed process is reclaimed after 30 seconds so one dead run can't wedge every future run. No new dependency was added (considered `filelock` from PyPI; the stdlib approach is smaller and sufficient for the team's expected concurrency level).
- **Merge-on-save, not overwrite-on-save:** `save()` now, under the lock: re-reads the current file from disk, applies *only this run's own pending updates* on top, and writes that merged result. Previously it wrote the entire in-memory snapshot (which could be stale relative to another process's save that happened after this process's own `load()`). Now two runs updating different cache keys both survive; two runs updating the *exact same* key still resolve last-write-wins for that key, which is the correct/expected semantics for a lookup cache.

**Interface unchanged:** `get()`, `set()`, `save()` keep the same signatures and semantics from the caller's point of view. `src/sourcing_engine.py` — which creates one `SupplierLookupCache()` per `apply_sourcing_decisions()` call, accumulates `.set()` calls, and calls `.save()` once at the end — required **no changes**. Mouser-first/DigiKey-fallback/no-split sourcing decision logic is untouched.

## 2. DigiKey token persistence

**Problem (from the audit):** `DigiKeyClient.get_user_access_token()` called `_update_env_value()` on refresh-token rotation, which rewrote the repository's `.env` file directly — unsafe on read-only or ephemeral hosting, and unsafe as shared state across concurrent runs/users.

**Approach — small abstraction, no auth-flow redesign:**

`src/token_store.py` defines a two-method `TokenStore` interface (`get(key)` / `set(key, value)`) with three backends:

| Backend | Behavior | When selected |
|---|---|---|
| `EnvFileTokenStore` | Rewrites a `KEY=value` line in a `.env` file (creates the file/line if absent) | `DIGIKEY_TOKEN_STORE=env_file`, or automatically when a local `.env` exists and no backend is explicitly set — preserves today's local-dev behavior with zero config change |
| `FileTokenStore` | Writes each key to its own file under a configured directory, using the same atomic-replace technique as the supplier cache | `DIGIKEY_TOKEN_STORE=file` with `DIGIKEY_TOKEN_STORE_PATH=<dir>` — for a host that provides a writable persistent directory outside the repo |
| `MemoryTokenStore` | In-process dict only | Default when no local `.env` exists and no backend is explicitly configured (e.g. Streamlit Community Cloud) |

`build_token_store()` does the selection; nothing is hardcoded to Streamlit specifically. `DigiKeyClient.__init__` now accepts an optional `token_store` parameter (defaults to `build_token_store()`), and `_load_refresh_token()` checks the store before falling back to the static `DIGIKEY_REFRESH_TOKEN` env value — so a rotated token persists across `DigiKeyClient()` instances within the same process even on the `memory` backend. `get_user_access_token()`'s control flow is otherwise identical to before; only the persistence call changed (`self.token_store.set(...)` in place of `_update_env_value(...)`).

`src/digikey_oauth_setup.py` (the local, interactive, one-time OAuth bootstrap CLI — opens a browser, prompts for a pasted redirect URL) had its own near-duplicate `_set_env_value()` function performing the identical `.env` line-rewrite. It now reuses `EnvFileTokenStore` instead, removing the second implementation of the same logic — this script still only ever rewrites the local `.env`, since that's its explicit purpose, but it no longer duplicates the mutation code.

## Cloud limitation — documented, not papered over

**Streamlit Community Cloud provides no writable persistent storage for secrets.** On that host, `MemoryTokenStore` is selected by default (no local `.env` file present in that environment), and a rotated refresh token survives only for the life of the running process — it is lost on restart or redeploy. This is stated directly in `token_store.py`'s docstrings rather than assumed away. Practical implication: if DigiKey issues single-use rotating refresh tokens and the app restarts between requests, re-authorization via `digikey_oauth_setup.py` (run locally, values then placed into the host's own secret manager) will be needed. If your Streamlit Cloud plan or an alternate host *does* expose a writable persistent volume, `FileTokenStore` can be pointed at it via `DIGIKEY_TOKEN_STORE=file` + `DIGIKEY_TOKEN_STORE_PATH` with no further code changes.

## Security check (per this phase's instructions)

- `Documentation/env` (live unredacted credentials, found in Phase 1) remains excluded via `.gitignore` and was not read into or reproduced by any new code.
- Grepped every new/changed file for `print(`/logging calls: no new call logs a key, token, refresh token, or authorization header. The pre-existing `print(response.text)` calls in `digikey_oauth_setup.py`'s error paths are unchanged from before this phase and are local-only interactive-script behavior, not something this phase introduced.
- A dedicated test (`test_rotated_refresh_token_is_persisted_and_not_logged`) patches `print` during a full mocked refresh-token rotation and asserts it is never called.

## Tests

All 51 tests pass (25 from Phase 1 + 26 new). Full `py_compile` clean across `app.py`, `src/`, and `tests/`.

New coverage:
- **Cache concurrency** (`test_supplier_lookup_cache_concurrency.py`): basic set/save/reload round-trip; two sequential runs updating different keys both survive; 8 threaded concurrent writers each keep their own key with no lost updates; a corrupted/partial JSON file is treated as empty rather than fatal; atomic write leaves no leftover temp file; disabled cache never touches disk.
- **Token persistence** (`test_digikey_token_persistence.py`): all three `TokenStore` backends individually (round-trip, missing-file/missing-key behavior, file creation, no leftover temp files); `build_token_store()`'s backend-selection logic for every combination of env vars; `DigiKeyClient` refresh-token precedence (stored value wins over static env value); dry-run short-circuit never touches the store; missing-refresh-token still raises `ValueError` as before; a mocked successful rotation persists the new token and logs nothing; a mocked non-rotation (same token returned) does not write to the store.

## Regression risk

Low. `SupplierLookupCache`'s public interface and `sourcing_engine.py` are unchanged — verified by the full existing `test_sourcing_accuracy.py` suite still passing unmodified. `DigiKeyClient`'s public methods and control flow are unchanged except for the persistence call; `digikey_mylists_client.py` (which constructs `DigiKeyClient()` with no arguments) needed no changes since the new `token_store` parameter defaults sensibly.

## Remaining external API verification items (carried over from Phase 1, unaffected by this phase)

- Mouser CartKey response shape and DigiKey MyLists share-ID field are still unverified against live APIs.
- PartsBox saved-filter and storage-tag-update endpoint support is still unverified (`Documentation/partsbox api rules.pdf` could not be parsed in this environment).

## New risks introduced

- The advisory file lock is best-effort: under its timeout it proceeds without the lock rather than hard-failing a run, favoring availability over strict mutual exclusion for a low-concurrency internal tool. For the team's expected usage (a handful of concurrent users), this is judged acceptable; if usage grows substantially, revisit with a stricter wait/fail policy.
- `MemoryTokenStore`'s non-persistence on Streamlit Community Cloud is a real limitation of that host, not of this implementation — flagged above so it isn't discovered by surprise during deployment.

## Recommended next phase

Resume the phased UI work: Results Workspace (Phase 3 of the original spec numbering), built on the structured `run_bom_workflow()` contract already in place from Phase 1.
