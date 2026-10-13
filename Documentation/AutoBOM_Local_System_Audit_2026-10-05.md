# AutoBOM local system audit — October 5, 2026

## Follow-up setup and verification

The original findings below are retained as the initial audit. Following the user's authorization to work through the issues, the missing local runtime was installed and verified:

- Created `.venv` using uv-managed Python 3.12.14.
- Installed all 42 packages from `requirements-lock.txt`; `uv pip check` reports that all installed packages are compatible.
- Normalized the inline comments in `PARTSBOX_DRY_RUN`, `SUPPLIER_DRY_RUN`, and `SUPPLIER_MODE`, preserving the parsed values and all credential values.
- Ran the actual checkout's deployment preflight: no failures; warnings remain for unspecified log capture and production data separation. Runs and cache directories are writable, and the DigiKey token store resolves to `EnvFileTokenStore`.
- Ran the complete suite in a temporary copy with a dry-run `.env` containing no real credentials: **620 tests passed in 64.396 seconds**. This includes app smoke tests.
- Started a temporary Streamlit server on loopback port 8517: health endpoint returned `200 ok`, and the root web page returned HTTP 200. Stopped that server after the check. Browser interaction remains a separate operator check.
- Verified live read-only supplier calls from this PC: PartsBox project listing succeeded (117 records), Mouser sample part search succeeded (2 records), and DigiKey sample keyword search succeeded (1 record). No projects, carts, lists, or orders were created. DigiKey used client-credentials product search; legacy MyLists refresh-token validity was not tested.
- Processed both supplied sample CSV BOMs with sourcing and PartsBox operations disabled: both returned success with zero errors and produced nonempty cleaned CSV, XLSX, and JSON run summaries in a temporary output directory.

**Updated status: the local runtime, automated suite, server startup, and normal supplier read access are verified.** Remaining work is operator browser acceptance and, if requested, team hosting/logging/data-location setup. Legacy MyLists OAuth is only relevant if that CLI integration will be used.

### Team hosting follow-up

The user confirmed teammates will use browsers on the same Wi-Fi. Installed the **AutoBOM Team Host** scheduled task and **AutoBOM-Team-WiFi-8502** local-subnet firewall rule. The host now listens on **10.105.44.193:8502** and returns HTTP 200 for the page and health endpoint. Port 8501 is already used by an unrelated Windows HTTP service and was preserved. The running team-host preflight passes all checks, with run/cache/log/token folders under `C:\Yank\AutoBoM\AutoBOM-data` outside the checkout. The task starts at Yank Tech's sign-in and remains available while the session is locked; before-login startup is not configured. See `AutoBOM_Team_Host_Quick_Start.md` for controls and remaining cross-machine acceptance checks.

## Verdict

**This checkout is not ready to launch yet.** The immediate blockers are the missing project virtual environment and missing application dependencies. Existing code and historical verification reports do not establish that this machine's current installation works.

This audit inspected the local checkout, configuration, launcher, dependency declarations, frontend assets, and available interpreter; it performed syntax checks, selected automated tests, and a temporary workspace write/read probe. No application settings or secrets were changed, and no supplier API requests, projects, carts, or lists were created.

## Confirmed results

| Check | Result | Evidence |
| --- | --- | --- |
| Python available on machine | PASS with setup issue | `uv python list --only-installed` finds CPython 3.14.7. `python` and `python3` on PATH resolve to Windows Store aliases; `py` is unavailable. |
| Project virtual environment | FAIL | `.venv/Scripts/python.exe` is absent; both Windows launch scripts require it. |
| Application dependencies | FAIL | The discovered Python 3.14.7 interpreter has none of `requests`, `pandas`, `openpyxl`, `python-dotenv`, or `streamlit` installed. |
| Python syntax | PASS | Parsed all 87 Python files in `app.py`, `src`, and `tests` using Python's AST parser. This checks syntax, not imports or runtime behavior. |
| Selected automated tests | PASS | 74 tests passed across engineering units, record filtering, pagination, and file locking. |
| PowerShell syntax | PASS | `launch_local.ps1`, `launch_production.ps1`, and `Create_AutoBOM_Desktop_Shortcut.ps1` parsed with zero syntax errors. Scripts were not launched. |
| Configuration JSON | PASS | Customer reference registry and storage space rules parse successfully. |
| Assets and launch files | PRESENT | Application logo files, launch scripts, deployment config template, dependency files, and test BOM fixtures are present. |
| Workspace write/read | PASS | A temporary probe was written, read, and removed successfully. Specific run/cache/token directories still need the application preflight. |
| Disk capacity | PASS | Approximately 1,725 GiB free on the workspace volume. |
| Secrets file | PRESENT | `.env` exists and is ignored by Git; `git ls-files .env` returns no tracked file. Secret values were withheld from audit output. |
| Supplier credential fields | PRESENT, NOT VERIFIED | PartsBox key, Mouser search/cart keys, DigiKey client ID/secret and refresh token are populated. Presence does not establish validity, entitlement, or expiry. |
| DigiKey endpoints | PASS structurally | Configured base and token URLs match the production endpoint strings expected by the client. No connectivity/authentication request was made. |

## Issues to address

### 1. Create the runtime environment and install dependencies

The launcher stops when `.venv/Scripts/python.exe` is absent. Python 3.14.7 exists through uv, but the repository's CI and lock-file comments identify Python 3.12 as the previously tested environment. For the first validated installation, use Python 3.12 and `requirements-lock.txt`; alternatively, Python 3.14 needs a successful dependency install and complete test run before being accepted.

The README's “Python 3.9+” guidance is inconsistent with the deployment preflight's 3.12 target. Follow the tested 3.12 setup for now. The audit did not download Python, create a venv, or install packages because the user's request was to identify readiness issues for joint follow-up.

### 2. Normalize inline comments in `.env`

The current file contains values including `false #true` for dry-run settings and `mouser_then_digikey #digikey_only` for supplier mode. The PowerShell production launcher splits on `=` and preserves inline comments as part of the value; python-dotenv strips comments from unquoted values. Some modules load dotenv without overriding environment variables, whereas `app.py` and DigiKey use `override=True`.

The present `false #true` values compare unequal to `true`, so they still produce live mode; this is not evidence that the current false setting becomes true. However, the parser disagreement is fragile: a future `true #false` could fail to enable dry run when preserved by the launcher, and a commented `digikey_only` could fail the CLI's exact mode comparison. Move comments to separate lines and use plain boolean/mode values before validation.

### 3. Confirm intended live-operation settings

PartsBox and supplier dry-run settings currently indicate live operation. `MOUSER_CART_ENABLED=true`, `MOUSER_CART_DRY_RUN=false`, and `DIGIKEY_MYLISTS_ENABLED=true` also enable legacy CLI integrations.

The current Streamlit purchasing path uses a Mouser CSV export and DigiKey FastAdd link; legacy cart/MyLists flags do not mean that the normal UI creates those remote resources. The README still describes older cart/MyList toggles and should be brought into agreement with the current implementation. Initial testing should use explicit mocks or a safely isolated dry-run configuration, then separately verify read-only supplier calls.

### 4. Finish host configuration if this will serve the team

No explicit run/cache/log/token directory overrides are present in `.env`. Defaults keep runs/cache within the checkout and select `.env` as the DigiKey token store. That is supported for local use, but production requires a decision about persistent data locations, token-file permissions, backups, and stdout/stderr capture.

The supplied Streamlit template binds to `127.0.0.1:8501`: it supports browsers on this machine. Team access from other computers requires a deliberate network configuration. Always-on service installation, restart behavior, and other-machine access were not verified in this audit.

## Verification still required

After setup, complete these checks before calling the system ready:

1. Install the locked dependencies and check dependency compatibility (`python -m pip check`). Package availability and compatibility have not been verified by installation.
2. Run `python src/deployment_preflight.py` to check dependencies and actual writable run/cache/token paths.
3. Run the complete test suite with supplier operations safely isolated. The checkout contains 620 `def test_` declarations; 74 tests were executed during this audit. Historical pass counts in documentation are not current results.
4. Start Streamlit and verify its health endpoint and browser UI, including custom search input behavior.
5. Process both sample CSV BOMs with remote writes disabled; verify cleaned CSV/XLSX, sourcing reports, purchasing exports, and downloads.
6. Make read-only PartsBox, Mouser, and DigiKey checks with the current credentials to verify connectivity, authentication, and usable results. Do not infer these from populated credential fields.
7. If legacy DigiKey MyLists is actually required, verify OAuth refresh and durable token persistence separately. A present refresh token may be expired or revoked.
8. If team hosting is required, verify service startup/restart, intended network access, and separate browser sessions on the actual host.

## Commands actually executed for code verification

Python syntax was checked by AST parsing, without creating bytecode. The selected tests ran using the discovered uv-managed interpreter:

```powershell
& 'C:\Users\Yank Tech\AppData\Roaming\uv\python\cpython-3.14.7-windows-x86_64-none\python.exe' -B -m unittest tests.test_engineering_units tests.test_record_filter tests.test_pagination tests.test_file_lock
```

Result: `Ran 74 tests ... OK`.
