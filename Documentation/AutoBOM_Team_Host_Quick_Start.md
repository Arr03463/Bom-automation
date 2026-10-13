# AutoBOM team host quick start

Team URL: **https://autobom.tools.yanktech.net**.

Caddy provides HTTPS on port 443. The prepared production backend is
**127.0.0.1:8502**. The live backend remains unchanged until the manual
cutover in [HTTPS migration](AutoBOM_HTTPS_Migration.md).

The desktop shortcut detects the existing AutoBOM Team Host task and opens
the HTTPS URL. Without the task, local development retains its original behavior.

Current task: sign-in startup as Yank Tech. Before-login startup requires
manual administrator execution of the prepared boot-task configuration.
Locking the screen does not stop the current interactive task; signing out does.

Data and logs: `C:\Yank\AutoBoM\AutoBOM-data` (runs/cache/logs/tokens).
Each start creates a log; the newest 30 launch logs are retained. A single
long-running log is not size-limited. Customer reference registry remains
in `config/customer_reference_registry.json`; include it in backups.

Caddy service: `YankInternalToolsCaddy`, already automatic. Its installation,
DNS, certificates, and firewall are maintained separately. The existing
8502 firewall rule is retained; after cutover there should be no LAN listener
on that port. HTTPS does not itself add application login or user authorization.

Use the migration document for exact administrator cutover, health checks,
unattended startup, and rollback. Do not run the legacy Wi-Fi installer.
