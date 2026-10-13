@echo off
rem Double-click launcher: local development/operator testing, AND a
rem valid way to start AutoBOM manually on the actual deployment
rem machine (e.g. the Yank engineering PC) -- for example before a
rem formal Windows service is installed, or for an ad hoc restart.
rem
rem Locates this checkout from its OWN location (not a hardcoded path),
rem then runs deploy\launch_local.ps1, which reuses the existing
rem launch/configuration logic in deploy\launch_production.ps1 -- the
rem SAME script a formal Windows service (Task Scheduler/NSSM, see
rem deploy\README.md) would invoke. This is not a second, parallel
rem startup path; it's that same mechanism plus "wait for it to respond,
rem then open the browser."
rem
rem When AutoBOM Team Host is installed, this opens that server on port
rem HTTPS and starts its scheduled task only if needed. It does not start
rem a second server. Without that task, the original local flow applies.

setlocal
set "SCRIPT_DIR=%~dp0"

rem %~dp0 always ends with a trailing backslash. Passed straight through
rem as -RepoPath "%SCRIPT_DIR%", that trailing backslash sits directly
rem before the closing double-quote, which Windows' command-line parser
rem reads as an ESCAPED quote (\") rather than end-of-argument -- the
rem quote gets swallowed into the path itself and everything after it on
rem the command line merges into the same argument. Stripping the
rem trailing backslash here (for this one use, only when quoted) avoids
rem that entirely.
set "REPO_PATH=%SCRIPT_DIR%"
if "%REPO_PATH:~-1%"=="\" set "REPO_PATH=%REPO_PATH:~0,-1%"

powershell -NoExit -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%deploy\launch_local.ps1" -RepoPath "%REPO_PATH%"
