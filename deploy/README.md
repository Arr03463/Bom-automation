# deploy/

Deployment building blocks for the Yank remote engineering PC target
(see `Documentation/AutoBOM_Deployment_Guide.md` and
`Documentation/AutoBOM_Onsite_Deployment_Checklist.md`). Nothing in this
directory has been installed/run against the real production host --
these are prepared, locally-tested-where-possible templates and scripts,
ready for on-site installation.

| File | Purpose |
|---|---|
| `production.env.example` | Production-flavored environment template (paths outside the checkout, durable token store). Narrower than the root `.env.example`. |
| `streamlit_config.prod.toml` | Production Streamlit config template. Copy to `<checkout>/.streamlit/config.toml` on the production host -- never auto-loaded from here. |
| `launch_production.ps1` | **Core launch mechanism**, wrapper-independent: loads env, runs preflight, starts Streamlit. Any service wrapper should invoke this as its start command. Safe to run manually to verify AutoBOM starts correctly. |
| `run_local_production_like.py` | Runs AutoBOM locally right now with production-like config (separate runs/cache/token directories outside the repo, DIGIKEY_TOKEN_STORE=file) -- no host access needed. |
| `windows_task_scheduler_install.ps1.template` | Registers AutoBOM to start at boot via Task Scheduler -- needs nothing beyond Windows itself. TEMPLATE: review and adapt before running. |
| `windows_service_install_nssm.ps1.template` | Alternative: wraps AutoBOM as a real Windows service via NSSM (if already approved/installed). TEMPLATE: review and adapt before running. |
| `windows_service_uninstall.ps1.template` | Rollback/removal for either install path above. TEMPLATE: review and adapt before running. |

None of the `.template` files were executed as part of this pass --
installing a Windows service on the real host is explicitly out of scope
until the team has physical/remote access again (see the predeployment
report's HOST SETUP PENDING list).
