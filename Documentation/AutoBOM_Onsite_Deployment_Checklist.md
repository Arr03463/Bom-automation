# AutoBOM On-Site Deployment Checklist (Yank Remote Engineering PC)

Audience: whoever performs the actual installation once physical/remote
access to the target PC is available. Everything here is HOST SETUP
PENDING as of this writing -- none of it has been executed against the
real machine.

Prerequisites this checklist assumes are already true (see
`Documentation/AutoBOM_Remote_PC_Predeployment_Report.md` for what's
already done and verified without the host):

- A tagged, approved release commit exists.
- `requirements-lock.txt` reflects that release's tested dependencies.
- The team has decided which service-supervision approach to use (Task
  Scheduler or NSSM -- see `deploy/README.md`).
- A dedicated service account (or a decision to use an existing one) has
  been identified.
- Live Mouser/DigiKey/PartsBox credentials for the PRODUCTION vendor
  accounts (not the developer's own, if different) are available through
  the team's secret-handling process.

## Steps

1. Select the approved release/tag to install.
2. Verify Python 3.12 is installed on the host (`python --version`).
3. Create the production checkout, e.g. `C:\AutoBOM\prod\repo` --
   `git clone`/checkout the approved tag. Do not develop directly in this
   checkout.
4. Create the production virtual environment, e.g. `C:\AutoBOM\prod\.venv`:
   ```
   python -m venv C:\AutoBOM\prod\.venv
   C:\AutoBOM\prod\.venv\Scripts\pip install -r requirements-lock.txt
   ```
5. Create persistent directories:
   - `C:\AutoBOM\prod\data\runs`
   - `C:\AutoBOM\prod\data\cache`
   - `C:\AutoBOM\prod\logs`
   - `C:\ProgramData\AutoBOM\tokens`
6. Create/confirm the service account for running AutoBOM.
7. Apply NTFS permissions: service account gets Modify on the five
   directories above; read/execute on the checkout; no ordinary-user
   access to the token directory.
8. Configure production secrets: copy `deploy/production.env.example` to
   the production checkout's `.env` (or your team's secret-injection
   mechanism), filling in real values -- Mouser/DigiKey/PartsBox
   credentials, `AUTOBOM_RUNS_ROOT`, `AUTOBOM_CACHE_ROOT`,
   `AUTOBOM_LOGS_DIR`, `DIGIKEY_TOKEN_STORE=file` +
   `DIGIKEY_TOKEN_STORE_PATH`. Never commit this filled-in file.
9. Set `DIGIKEY_TOKEN_STORE=file` and confirm `DIGIKEY_TOKEN_STORE_PATH`
   points at the dedicated token directory from step 5.
10. Run the deployment preflight from the production checkout:
    ```
    C:\AutoBOM\prod\.venv\Scripts\python src\deployment_preflight.py
    ```
    Resolve every FAIL before continuing. Review WARNs and accept or fix
    each one deliberately.
11. Install the service (Task Scheduler or NSSM -- see `deploy/README.md`
    for the corresponding template). This invokes `deploy/launch_production.ps1`
    as its start command either way.
12. Start the service.
13. Test `http://localhost:8501` (or the configured port) from the host
    itself.
14. Confirm persistent storage: after a dry-run BOM upload, confirm files
    appear under `AUTOBOM_RUNS_ROOT`, not inside the checkout.
15. Run a dry-run BOM (sourcing/PartsBox/cart/MyList flags off, or with
    `SUPPLIER_DRY_RUN=true`/`PARTSBOX_DRY_RUN=true` still set) to confirm
    the application works end-to-end before touching live vendor data.
16. Verify PartsBox: run one real BOM against a disposable/known test
    project (not an active production project) and confirm project/
    storage/entries behave as expected -- see the predeployment report's
    LIVE VENDOR VERIFIED section for what to expect.
17. Verify Mouser: confirm a real cart can be created (small/disposable)
    and CartKey is captured. Do not proceed through Mouser checkout.
18. Verify DigiKey: run `python src\digikey_oauth_setup.py` locally
    first if the stored refresh token is invalid/expired (this affected
    the developer's own account as of this pass -- confirm production
    credentials work before assuming otherwise), then confirm a MyList
    can be created and its list ID captured.
19. Restart the service (`Restart-ScheduledTask`/`Restart-Service`, or
    manually stop and start it) and confirm it comes back automatically.
20. Verify DigiKey token persistence: after the restart, confirm DigiKey
    MyLists still works without needing to re-run the OAuth setup --
    this is the actual proof that `DIGIKEY_TOKEN_STORE=file` is durable
    on this host, not just in a unit test.
21. Open a second browser (or an incognito window / a different
    machine) and confirm session isolation: run a BOM with the SAME
    uploaded filename as the first session and confirm both complete
    independently with no file collisions.
22. Configure initial trusted-team network accessibility (Windows
    Firewall rule restricting the port to the approved subnet/VPN --
    see `Documentation/AutoBOM_Deployment_Guide.md`).
23. Begin the team pilot with the trusted team.
24. Continue firewall/VPN/SSO/reverse-proxy hardening separately, per the
    Security Hardening Backlog in the predeployment report -- this is
    NOT a gate on starting the pilot (see that report for the reasoning).
25. At a planned maintenance window, reboot the host and confirm the
    service auto-starts and DigiKey token persistence survives a full
    machine restart (not just a service restart) -- the strongest form of
    the restart-survival property this whole pass worked to prove at the
    code level.
26. Verify service auto-recovery: stop the AutoBOM process directly
    (not via the service manager) and confirm the supervisor restarts it
    within its configured restart interval.
27. Get team sign-off that the pilot is ready to widen beyond the
    initial trusted group, if/when that's the plan.

## If something fails

- Preflight FAIL: fix the specific check named before continuing --
  don't work around it.
- DigiKey 401/invalid refresh token: re-run
  `python src\digikey_oauth_setup.py` locally, then set the resulting
  refresh token as `DIGIKEY_REFRESH_TOKEN` for this deployment's initial
  value (the durable store then takes over from there).
- Service won't start: check the log files under `AUTOBOM_LOGS_DIR` (or
  the service wrapper's own log location) for the actual Python
  traceback -- `launch_production.ps1` does not suppress it.
- Anything unexpected involving vendor credentials: stop, do not guess --
  escalate to whoever owns the vendor account relationship.
