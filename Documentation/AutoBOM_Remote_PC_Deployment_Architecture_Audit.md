# AutoBOM Deployment Architecture Audit

**Audit date:** 2026-09-22  
**Repository baseline:** `4a5c9376fa9d8b0ff31d900b4d199b07f49c247b`  
**Scope:** Current repository and supplied deployment documents. This is an independent review; statements in implementation reports were treated as claims to verify against code and tests. No application or deployment implementation was changed.

## Executive decision

Deploy AutoBOM on the existing shared Windows engineering PC, subject to the release gates in this report. This is the smallest practical architecture for this team because the host already supplies persistent local storage, internal network reachability, and an administrative path through RDP. It avoids adding an external writable secret service solely to keep the rotating DigiKey refresh token alive.

Use one dedicated production checkout and Python virtual environment, run one Streamlit process as a Windows service, and expose it only to the trusted corporate LAN or VPN. Team members should use a browser; RDP should remain an administrative and development path. Do not run production from the VS Code Dev Container.

The current build is **conditionally deployable for an internal pilot**, with purchasing integrations disabled or tightly controlled. It is **not ready for unattended, concurrent production use with DigiKey MyLists enabled** until the refresh-token locking and persistence-failure findings below are corrected and exercised against the live vendor.

## Verification performed

- Read the current application, workspace, retention, token-store, file-lock, configuration-validation, purchasing, and test code.
- Compared the code with the implementation specification, deployment hardening report, deployment guide, operator guide, and durable-token strategy.
- Ran `python -m unittest discover -s tests -q`: **272 tests passed**.
- Ran `python -m compileall -q app.py src tests`: **passed**.
- Confirmed `.env`, `Documentation/env`, `.cache/`, and `runs/` are ignored by Git.
- Did not inspect or reproduce secret values and did not call live vendor APIs.

Automated success establishes regression coverage; it does not close the live integration, restart, multi-browser, host security, or backup tests listed later.

## Architecture comparison

| Criterion | Streamlit Community Cloud | Existing remote Windows PC |
|---|---|---|
| Rotating DigiKey token | Requires a separate writable HTTPS store. The implemented HTTP store has no distributed lock. | `FileTokenStore` can use a local NTFS directory that persists across process and machine restarts. |
| Run files and cache | Ephemeral and lost on restart/hibernation. | Can reside on persistent local disk and follow the existing retention policy. |
| Team access | Convenient hosted URL and platform access controls. | Stable internal DNS name/IP is required; restrict to LAN/VPN and approved users. |
| Maintenance | Platform handles the runtime; app hibernates after inactivity. | Team owns Windows patching, service startup, disk capacity, backups, and recovery. |
| External dependencies | Git host, Community Cloud, vendor APIs, and a new token service. | Windows host and vendor APIs; no new token service. |
| Failure recovery | Redeploy is simple, but in-memory sessions and local files disappear. | Service restart is simple; disk artifacts survive, but active Streamlit sessions do not. |
| Security boundary | Private app configuration is essential; no AutoBOM login exists. | LAN/VPN and Windows Firewall are the primary boundary; no AutoBOM login exists. |
| Operational fit | Reasonable only after choosing and proving an external atomic token service. | Best fit for the stated small engineering team and available always-on host. |

Streamlit documents that Community Cloud apps without traffic hibernate after 12 hours. That behavior increases the importance of an external durable token store for the cloud model: [Streamlit Community Cloud app management](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app).

## Verified strengths

1. **Per-run file isolation is sound.** Each run receives a UUID and its own `runs/<run_id>/input` and `output` directories. Uploaded filenames are reduced to a basename and sanitized.
2. **Browser session state is separated by Streamlit session.** Each session owns its `current_run` and user-interface state.
3. **Purchasing side effects have an explicit user boundary.** Cart and MyList regeneration is reached through the Purchasing action, and the test suite covers reruns, navigation, filtering, stale state, and partial failures.
4. **The file token backend uses local durable storage and atomic replacement.** With a correctly held lock and a local NTFS directory, it is the appropriate current backend for the Windows host.
5. **Secrets and generated data are Git ignored.** The repository does not track the inspected secret paths or runtime directories.
6. **Vendor HTTP error bodies are sanitized.** This reduces the chance of returning token-bearing response content to an operator.

## Findings

### F1 — Critical: a timed-out refresh-token lock does not stop token rotation

`FileLock.acquire()` returns `False` on timeout and its own documentation says callers must skip the protected operation. `FileLock.__enter__()` ignores that result. `DigiKeyClient.get_user_access_token()` uses `with self.token_store.lock():` without checking `lock.acquired`, so a caller that times out continues the read-refresh-write sequence without owning the lock.

The stale threshold is 30 seconds, equal to the DigiKey HTTP request timeout. A slow but valid refresh can therefore also have its live lock reclaimed while still in progress. Concurrent refresh-token use can invalidate one caller's token and leave the persistent store with the wrong generation.

**Deployment consequence:** do not claim safe concurrent DigiKey MyLists operation. Until corrected and tested, keep `DIGIKEY_MYLISTS_ENABLED=false`, or impose a documented one-operator purchasing window. A single Streamlit process reduces cross-process contention but does not remove concurrent browser threads.

**Required correction after this audit:** fail closed when the lock is not acquired, use a stale interval comfortably longer than the maximum protected operation or a renewable/owner-liveness design, and add a test proving a timed-out caller makes no token request.

### F2 — High: a failed rotated-token write can produce a successful but unrecoverable request

After DigiKey returns a new refresh token, `DigiKeyClient` catches `TokenStoreError` from `set()`, records text in `token_store_error`, and continues returning the access token. A later client can then load the old, invalid refresh token from disk. The write failure is not guaranteed to be visible on the successful Purchasing action.

**Deployment consequence:** a permissions error, full disk, antivirus hold, or damaged token directory can strand the integration after an apparently successful call.

**Required correction after this audit:** surface persistence failure as an explicit operator-visible degraded state and prevent the purchasing result from being represented as fully healthy. Exercise this path with a forced read-only/full-disk equivalent before release.

### F3 — High: AutoBOM has no application authentication or authorization

The application has no login, user roles, per-user audit identity, or authorization check around live purchasing. Anyone who can reach the Streamlit port can upload BOMs, view that browser session's results, query configured services, and initiate enabled purchasing actions.

**Deployment consequence:** direct Internet exposure is unacceptable. LAN access is acceptable only when the LAN/VPN membership is the intended trust boundary. If that assumption is false, put an organization-managed reverse proxy with SSO in front of Streamlit before enabling live supplier actions.

### F4 — Medium: retention can delete another active session's run directory

Cleanup runs when a new run is created and protects only the new run ID passed to that cleanup call. It has no registry of all active Streamlit sessions. An older active session can lose its files if its directory crosses the age or count limit. The deployment guide's statement that “the currently active run is never deleted” is too broad.

**Deployment consequence:** keep conservative limits for the pilot, monitor disk usage, and tell operators that old open browser sessions do not reserve their files. A future correction should protect all active run IDs or perform cleanup only when no session is using a candidate directory.

### F5 — Medium: production builds are not reproducible

`requirements.txt` lists package names without versions or hashes. The deployment guide says dependencies are pinned, but they are not. A reinstall or rollback can resolve newer dependency versions and behave differently from the tested build. The Dev Container uses Python 3.11 while the guide specifies Python 3.12.

**Deployment consequence:** capture and approve a tested production lock before go-live. Store it with the release and rebuild the virtual environment from that lock. Keep the Dev Container mismatch out of production acceptance evidence.

### F6 — Medium: runtime state is only partly durable

Run input/output files survive on the Windows disk, but the canonical active BOM and purchasing state live in `st.session_state`. Restarting the service or losing the browser session ends the in-progress workflow; the application has no resume path from a run directory.

**Deployment consequence:** schedule updates outside active work, announce restarts, and have operators download required outputs before maintenance. This is an accepted architecture limit, not a reason to add a database for the current team size.

### F7 — Medium: deployment readiness checks are incomplete

Startup validation detects several missing credentials and non-durable token selection, but it does not prove that the token path is writable, on persistent local storage, protected by a restrictive ACL, or able to complete an atomic replace. File and HTTP backend misconfiguration can fall back to memory and produce warnings, but no automated deployment probe validates the entire production data layout. There is also no repository-supplied service definition or health check.

**Deployment consequence:** use the preflight and acceptance procedure in this report; do not treat a clean page load alone as readiness.

### F8 — Low: fixed runtime paths couple data to the checkout

`RUNS_ROOT` is fixed at `<checkout>/runs`; the default cache is `<checkout>/.cache`. The token directory is configurable. This works for one stable production checkout, but release-folder replacement and ad hoc `git clean` operations can remove or strand runtime data.

**Deployment consequence:** keep the production checkout stable, exclude runtime directories from cleanup, and back up or intentionally discard run artifacts according to the policy below. If containers are adopted later, mount these exact paths explicitly.

## Recommended Windows production design

```text
Engineering browsers
        |
   Corporate LAN/VPN
        |
Windows Firewall: allow TCP 8501 only from approved subnet(s)
        |
One Streamlit process, dedicated Windows service account
        |
  +-----+----------------------+-------------------+
  |                            |                   |
production checkout/runs   production cache   C:\ProgramData\AutoBOM\tokens
  |                                                |
optional run backup                         FileTokenStore on local NTFS
        |
Outbound HTTPS to Mouser, DigiKey, PartsBox
```

### Process model

Use one native Python 3.12 virtual environment and one Streamlit process supervised by a Windows service wrapper approved by the organization. Configure automatic start after networking, restart on failure with backoff, stdout/stderr capture, and a dedicated noninteractive service account. Do not use Task Scheduler as the primary supervisor; its job semantics and log handling are less clear for a continuously serving process.

Bind Streamlit to the host's internal interface and a fixed port. Permit that port only from the approved corporate subnet or VPN. Microsoft recommends narrowly scoped inbound rules and supports limiting them by program, port, profile, and remote address: [Windows Firewall rule guidance](https://learn.microsoft.com/en-us/windows/security/threat-protection/windows-firewall/best-practices-configuring).

If the team already operates Docker Engine reliably as a boot-time service on this PC, a single-service Compose deployment is a valid second choice. Mount persistent host directories for `/app/runs`, `/app/.cache`, and the token directory, and use `restart: unless-stopped`. Docker documents the behavior and limits of restart policies here: [Docker restart policies](https://docs.docker.com/engine/containers/start-containers-automatically/). Do not add Docker Desktop solely for this app without first confirming unattended boot, licensing, patch ownership, and service-account behavior.

### Persistent layout

Recommended host layout:

```text
C:\AutoBOM\prod\repo\                  production checkout; service account read/execute
C:\AutoBOM\prod\.venv\                 production virtual environment
C:\AutoBOM\prod\logs\                  service stdout/stderr with size/time rotation
C:\AutoBOM\backup\                      protected local or managed backup target
C:\ProgramData\AutoBOM\tokens\          service account + administrators only
```

The current code requires `runs` and `.cache` inside the checkout unless links/mounts are used. For the first deployment, keep the stable checkout at `C:\AutoBOM\prod\repo` and let those ignored directories live there. Do not develop in this checkout.

Set:

```text
DIGIKEY_TOKEN_STORE=file
DIGIKEY_TOKEN_STORE_PATH=C:\ProgramData\AutoBOM\tokens
SUPPLIER_LOOKUP_CACHE_PATH=C:\AutoBOM\prod\repo\.cache\supplier_lookup_cache.json
```

Grant the service account Modify permission only where writes are required (`runs`, `.cache`, `logs`, and `tokens`). Grant it read/execute on application code. Remove ordinary-user access from the token directory. Windows access control supports assigning permissions to specific users and groups: [Microsoft access control overview](https://learn.microsoft.com/en-us/windows/security/identity-protection/access-control/access-control).

### Secrets

Prefer service-level environment variables managed outside the repository. Ensure the production checkout contains no `.env`, because the application calls `load_dotenv(..., override=True)` and a local file can override service environment values. If operational constraints require a production `.env`, place it only in the dedicated production checkout, restrict its ACL to the service account and administrators, and treat it as a secret file during backup and incident response.

Never share the production token directory with development. Do not place it on a synced folder or ordinary SMB share; the current atomic-replace and lock assumptions are safest on local NTFS.

### Production and development separation

| Area | Production | Development |
|---|---|---|
| Checkout | Dedicated release checkout | Existing developer checkout/Dev Container |
| Account | Dedicated service account | Named developer account |
| Port | Fixed internal port | Different localhost-only port |
| Credentials | Production vendor credentials | Test credentials or dry run |
| Token store | Dedicated production file directory | Separate `.env`, memory, or separate dev token directory |
| Runs/cache | Production-only paths | Developer checkout paths |
| Updates | Tagged/approved release procedure | Normal branch workflow |

The checked-in Dev Container starts Python 3.11, disables CORS and XSRF protection, and launches an interactive development server on attach. These settings make it development-only.

## Release and update procedure

1. Build and test a candidate commit in development.
2. Record a release tag and a tested dependency lock.
3. Back up current configuration and record the current commit. Treat token backup limitations as described below.
4. Confirm no team run is active; announce the maintenance window.
5. Stop the Windows service.
6. Fast-forward the dedicated production checkout to the approved tag. Never develop, merge, or resolve conflicts in production.
7. Rebuild or update the production virtual environment from the approved lock.
8. Run configuration preflight, compilation, unit tests, and an offline/dry-run smoke test.
9. Start the service and check its health endpoint/page and logs.
10. Run the post-deploy acceptance checks. If they fail, stop the service, restore the previous tag and environment, restart, and repeat the smoke check.

Full CI/CD is optional at this team size. A CI job that runs compilation and all unit tests on every proposed release is useful. Automatic production deployment is unnecessary until release frequency or operator burden justifies it.

## Backup and recovery policy

### Back up

- Production configuration and service definition after every approved change.
- The tested dependency lock and release tag in source control.
- Run outputs only if the business needs historical artifacts; otherwise rely on the existing 14-day/200-run retention and operator downloads.
- The token directory as a protected secret, understanding that a copied rotating token can become obsolete immediately after the next successful rotation.

### Do not assume a token backup guarantees recovery

DigiKey refresh tokens rotate. Restoring yesterday's file after a later rotation may restore an invalid token. The reliable recovery path for lost or inconsistent token state is to run the authorization bootstrap again, seed the new token into the production store, and verify a live MyLists call. Document who can perform that action and where the vendor account recovery material is held.

### Recovery targets

- **Service/process failure:** automatic restart, then browser smoke test.
- **Machine reboot:** automatic service start after networking; confirm local disk paths and token read.
- **Bad application release:** restore previous tag and matching virtual environment; no schema migration exists.
- **Disk/host loss:** rebuild the service from the release tag and configuration backup; restore optional run artifacts; reauthorize DigiKey if token validity is uncertain.
- **Token corruption or concurrency incident:** disable MyLists, preserve logs, reauthorize, then re-enable only after the locking issue is corrected.

## Production preflight checklist

- [ ] Dedicated production checkout, virtual environment, and service account exist.
- [ ] Production checkout has no developer `.env`, or its ACL and values have been explicitly approved.
- [ ] Production and development use different ports, paths, accounts, and vendor credentials.
- [ ] `DIGIKEY_TOKEN_STORE=file` and the path resolves to local persistent NTFS.
- [ ] Token directory ACL permits only the service account and administrators.
- [ ] Service account can create, replace, read, and delete a test file in each writable directory.
- [ ] Windows Firewall allows the service port only from approved LAN/VPN ranges and the intended network profile.
- [ ] The port is not reachable from the public Internet.
- [ ] A tested dependency lock exists and Python/runtime versions match the accepted test environment.
- [ ] All 272+ automated tests and compilation pass on the release candidate.
- [ ] Dry-run BOM smoke test produces isolated input and output artifacts.
- [ ] Log rotation and free-disk monitoring are configured.
- [ ] Restart-on-failure and automatic boot start have been tested while no administrator is logged in.
- [ ] Credential rotation status has been verified with each vendor; repository inspection cannot prove this.
- [ ] DigiKey MyLists remains disabled until F1 and F2 are corrected, or the temporary one-operator control is formally accepted.

## Acceptance tests on the actual host

1. From two separate browsers, create simultaneous dry-run BOM jobs with the same uploaded filename; verify different run IDs and files.
2. Verify one session cannot see or mutate the other session's in-memory results through normal navigation.
3. Confirm plain reruns, navigation, filters, and downloads create no cart or MyList.
4. Restart the service and confirm the URL returns without an interactive Windows login.
5. Verify active browser workflows are lost on restart and record this expected behavior in operator training.
6. Verify run files survive restart and retention removes only eligible directories; include a test with an older open session to demonstrate the F4 limitation.
7. Force a token-directory permission failure in a controlled nonproduction setup and confirm the F2 behavior before correcting it.
8. After F1 is corrected, run two concurrent token-refresh attempts and prove only one refresh uses each token generation.
9. With approved live test credentials, validate Mouser CartKey, DigiKey MyList fields, PartsBox schema, and recovery after one full service restart.
10. Verify backup restoration of code/config and separately rehearse DigiKey reauthorization; do not use a stale-token restore as the recovery proof.

## Final verdict

**Recommended target:** existing Windows remote engineering PC.  
**Recommended runtime:** one native Streamlit process under a Windows service, unless an already-supported boot-time Docker Engine environment exists.  
**Exposure:** trusted LAN/VPN only; add organization SSO at a reverse proxy if network membership is not a sufficient authorization boundary.  
**Production status:** **conditional internal pilot** with dry run and non-purchasing workflows. Live Mouser and PartsBox actions still require host acceptance against vendor test access. DigiKey MyLists is a **release gate** until F1 and F2 are corrected or a time-limited, single-operator exception is explicitly owned.

This design reuses current hardware and current file-backed mechanisms while keeping production separate from development. It adds no database, orchestration platform, or external token service to the initial deployment.
