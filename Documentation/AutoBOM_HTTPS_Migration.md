# AutoBOM HTTPS backend migration — October 12, 2026

Team entry: **https://autobom.tools.yanktech.net**.
Target: **Caddy on 443 → 127.0.0.1:8502 → Streamlit**.

Repository preparation does not migrate the running process. The existing
LAN listener and Caddy upstream remain working until the administrator
performs the coordinated cutover below. A task restart before the Caddy
upstream change will temporarily break HTTPS. Schedule a brief outage;
active browser sessions and unsaved session state may be lost.

## Application-side verification

- Final full existing suite: **620 tests passed in 60.144 seconds**, in an
  isolated copy with mock/dry-run settings and no production credentials.
- All eight deployment PowerShell scripts/templates parsed without errors.
- Updated production launcher passed an isolated startup/health test on
  `127.0.0.1:8517`. A deliberately conflicting `.env` specified `0.0.0.0:8599`;
  explicit launcher arguments won, and preflight correctly reported loopback
  8517. The staging process tree was stopped afterward.
- Caddy accepted the repository example as valid; no live reload was performed.
- The existing HTTPS health endpoint returned **200 / ok** after preparation.
- The live backend remained `10.105.44.193:8502`, PID 18532, throughout checks.
- Live Caddyfile SHA-256 stayed
  `9E4CA2E495388326A770241E36CA6296A0A03278070E7A6AC4C261812860D675`.
- Search found no active production launcher/config reference to the old LAN
  IP. Remaining references are cutover/rollback instructions and the dated
  October 5 audit. No supplier/application workflow code was changed.

**Application preparation passed. Live migration and unattended boot acceptance
are pending the administrator steps below.** No live task, service, firewall,
DNS, certificate, or private-key configuration was changed.

## Findings and prepared changes

`deploy/launch_team.ps1` previously discovered `Wi-Fi 2` and assigned that
address to `STREAMLIT_SERVER_ADDRESS`; it set port 8502. It now enforces
loopback 8502 through explicit arguments to `launch_production.ps1` and
Streamlit. Those arguments take precedence over `.env`. Preflight also
receives these arguments so its report matches the actual listener.

Production config and environment templates now default to loopback 8502.
The installed task invokes `launch_team.ps1`, so the existing task action
does not require modification for the bind change. The desktop launcher
opens/checks HTTPS when the installed task exists. Development without
that task retains its explicit loopback port 8501 defaults.

The live task is interactive, starts at Yank Tech sign-in, retries failures
999 times at one-minute intervals, and has no execution time limit. It is
not before-login hosting. A password-backed boot task is the smallest
unattended change; a new Windows service is not necessary for this migration.
The optional NSSM template uses the same team launcher if a service is
later approved. NSSM is not installed or executed by this change.

## Manual administrator cutover

Run these in **Administrator PowerShell on the host**, after notifying
users. Do not change DNS, certificates, or firewall rules.

```powershell
$repo = 'C:\Yank\AutoBoM\Bom-automation'
$caddy = 'C:\Yank\Infrastructure\Caddy\caddy.exe'
$caddyConfig = 'C:\Yank\Infrastructure\Caddy\Caddyfile'
Set-Location $repo
Copy-Item -LiteralPath $caddyConfig -Destination "$caddyConfig.before-autobom-loopback" -ErrorAction Stop
Export-ScheduledTask -TaskName 'AutoBOM Team Host' | Set-Content -LiteralPath "$repo\.cache\AutoBOM-Team-Host-before-cutover.xml" -Encoding Unicode
Stop-ScheduledTask -TaskName 'AutoBOM Team Host'
Start-Sleep -Seconds 3
Get-NetTCPConnection -LocalPort 8502 -State Listen -ErrorAction SilentlyContinue
```

**If a listener remains, stop here:** identify its process and ensure the
existing AutoBOM process actually stopped. Do not kill unrelated processes
or start a second backend.

Start the existing task with the updated launcher:

```powershell
Start-ScheduledTask -TaskName 'AutoBOM Team Host'
Start-Sleep -Seconds 10
Get-NetTCPConnection -LocalPort 8502 -State Listen | Format-Table LocalAddress,LocalPort,OwningProcess
Invoke-WebRequest 'http://127.0.0.1:8502/_stcore/health' -UseBasicParsing
```

Require **only `127.0.0.1:8502`** and health **HTTP 200 / `ok`** before
switching Caddy. Inspect `C:\Yank\AutoBoM\AutoBOM-data\logs` if startup fails.

Edit only the existing AutoBOM upstream line in the live Caddyfile:

```caddyfile
# Before
reverse_proxy 10.105.44.193:8502
# After
reverse_proxy 127.0.0.1:8502
```

Preserve the hostname, TLS certificate/key paths, and all other configuration.
`deploy/Caddyfile.autobom.example` is a reference, not a replacement for
other sites in a live configuration.

```powershell
& $caddy validate --config $caddyConfig --adapter caddyfile
if ($LASTEXITCODE -ne 0) { throw 'Caddy validation failed; do not reload.' }
& $caddy reload --config $caddyConfig --adapter caddyfile
if ($LASTEXITCODE -ne 0) { throw 'Caddy reload failed; inspect the existing service/admin endpoint configuration.' }
Invoke-WebRequest 'https://autobom.tools.yanktech.net/_stcore/health' -UseBasicParsing
Invoke-WebRequest 'https://autobom.tools.yanktech.net/' -UseBasicParsing
Get-NetTCPConnection -LocalPort 8502 -State Listen | Format-Table LocalAddress,LocalPort,OwningProcess
```

Reload uses Caddy's existing admin endpoint; if it is disabled or customized,
coordinate the correct reload method with the infrastructure owner rather
than changing the Caddy service. Require HTTPS health 200/ok, successful
browser rendering and interaction from another PC, and no LAN/IPv6 wildcard
listener on 8502. From that other PC, `Test-NetConnection 10.105.44.193 -Port
8502` should fail while HTTPS continues to work. Keep the existing 8502
firewall rule until separately authorized to remove it.

## Optional unattended boot task — manual only

After the HTTPS cutover works, convert the task at a separate maintenance
window. The account needs a real Windows password, batch-logon rights,
read/execute access to the repo and Python installation, read access to
`.env`, and modify access to `AutoBOM-data`, `.streamlit`, and the customer
reference registry. `.venv` depends on uv Python under Yank Tech's profile;
another service account needs its access verified or a separately installed
runtime. Do not default to LocalSystem.

```powershell
Set-Location 'C:\Yank\AutoBoM\Bom-automation'
Stop-ScheduledTask -TaskName 'AutoBOM Team Host'
Start-Sleep -Seconds 3
Get-NetTCPConnection -LocalPort 8502 -State Listen -ErrorAction SilentlyContinue
# Continue only after the listener is gone.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy\configure_team_boot_task.ps1 -UserName "$env:COMPUTERNAME\Yank Tech"
# The script prompts for the Windows password and backs up the existing XML.
Start-ScheduledTask -TaskName 'AutoBOM Team Host'
```

The prepared tool changes the existing task to password-backed AtStartup,
30-second startup delay, normal permissions, restart-on-failure, no time
limit, and duplicate-instance protection. It does not start the task itself.
It does not touch Caddy, firewall, or services. Password changes may require
updating stored task credentials. Verify availability after sign-out and a
reboot before calling unattended startup complete.

## Rollback

Pre-migration launch/config copies are in
`C:\Yank\AutoBoM\Bom-automation\.cache\autobom-https-rollback`. Keep this
ignored directory until acceptance; do not run `git clean` against it.

In Administrator PowerShell, during a maintenance window:

```powershell
$repo = 'C:\Yank\AutoBoM\Bom-automation'
$caddy = 'C:\Yank\Infrastructure\Caddy\caddy.exe'
$caddyConfig = 'C:\Yank\Infrastructure\Caddy\Caddyfile'
Stop-ScheduledTask -TaskName 'AutoBOM Team Host'
Start-Sleep -Seconds 3
Get-NetTCPConnection -LocalPort 8502 -State Listen -ErrorAction SilentlyContinue
# Continue only once the old listener has stopped.
foreach ($name in 'launch_team.ps1','launch_local.ps1','launch_production.ps1','streamlit_config.prod.toml','production.env.example') {
    Copy-Item -LiteralPath "$repo\.cache\autobom-https-rollback\$name" -Destination "$repo\deploy\$name" -Force
}
Start-ScheduledTask -TaskName 'AutoBOM Team Host'
Start-Sleep -Seconds 10
Invoke-WebRequest 'http://10.105.44.193:8502/_stcore/health' -UseBasicParsing
```

Restore **only the AutoBOM upstream** to `reverse_proxy 10.105.44.193:8502`,
validate and reload Caddy using the commands above, then verify HTTPS. The
whole Caddyfile backup can be restored only if no unrelated infrastructure
changes occurred since it was taken.

If task conversion was performed, restore its pre-cutover interactive XML:

```powershell
Stop-ScheduledTask -TaskName 'AutoBOM Team Host'
Register-ScheduledTask -TaskName 'AutoBOM Team Host' -Xml (Get-Content -LiteralPath "$repo\.cache\AutoBOM-Team-Host-before-cutover.xml" -Raw) -Force
Start-ScheduledTask -TaskName 'AutoBOM Team Host'
```

Restore the task while the original Yank Tech account is signed in. If the
backup came from a password-backed task instead, re-supply its credentials;
exported XML does not include passwords. Verify no leftover process occupies
8502 before any restart. No DNS/certificate/firewall rollback is needed because
those components were not changed by the application preparation.
