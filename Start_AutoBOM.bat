@echo off
rem Double-click launcher for local/operator testing.
rem
rem Locates this checkout from its OWN location (not a hardcoded path),
rem then runs deploy\launch_local.ps1, which reuses the existing
rem launch/configuration logic in deploy\launch_production.ps1 -- it
rem does not start AutoBOM a second, different way.
rem
rem Production note: once AutoBOM is installed as a Windows service on
rem the Yank engineering PC, normal team users should NOT run this file
rem to start the server -- the service is already running. Their
rem shortcut should simply open the AutoBOM URL in a browser. See the
rem "One-Click Local Launcher" section in README.md.

setlocal
set "SCRIPT_DIR=%~dp0"

powershell -NoExit -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%deploy\launch_local.ps1" -RepoPath "%SCRIPT_DIR%"
